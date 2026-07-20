#!/usr/bin/env bash
# =============================================================================
# Quantum Helix — Deploy Azure dummy security telemetry for testing
#
# Creates a disposable resource group, storage account, blob containers, and
# (optionally) a Log Analytics workspace, then uploads CIM-compatible Activity
# Log / NSG Flow–style JSON that Quantum Helix can parse via parse_azure.
#
# Prerequisites:
#   - Azure CLI (`az`) installed and logged in:  az login
#   - Permissions to create RG / Storage / Log Analytics in the target subscription
#   - Python 3.11+ (for local telemetry generation; no Azure SDK required)
#
# Usage:
#   chmod +x azure/deploy_dummy_data.sh
#   ./azure/deploy_dummy_data.sh
#   ./azure/deploy_dummy_data.sh --subscription <SUB_ID> --location eastus
#   ./azure/deploy_dummy_data.sh --destroy
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Defaults (override via flags or env)
SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-}"
LOCATION="${AZURE_LOCATION:-eastus}"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-rg-Quantum Helix-test}"
STORAGE_PREFIX="${AZURE_STORAGE_PREFIX:-qssgdummy}"
LAW_NAME="${AZURE_LAW_NAME:-law-Quantum Helix-test}"
NORMAL_COUNT="${AZURE_NORMAL_COUNT:-40}"
ATTACK_COUNT="${AZURE_ATTACK_COUNT:-5}"
CREATE_LAW=1
DRY_RUN=0
DESTROY=0
SKIP_UPLOAD=0
LOCAL_OUT="${ROOT_DIR}/azure/.generated"

if [[ -t 1 ]]; then
  C_GREEN='\033[0;32m'; C_CYAN='\033[0;36m'; C_YELLOW='\033[1;33m'
  C_RED='\033[0;31m'; C_BOLD='\033[1m'; C_RESET='\033[0m'
else
  C_GREEN=''; C_CYAN=''; C_YELLOW=''; C_RED=''; C_BOLD=''; C_RESET=''
fi

info() { echo -e "${C_CYAN}[INFO]${C_RESET}  $*"; }
ok()   { echo -e "${C_GREEN}[OK]${C_RESET}    $*"; }
warn() { echo -e "${C_YELLOW}[WARN]${C_RESET}  $*"; }
fail() { echo -e "${C_RED}[ERROR]${C_RESET} $*"; exit 1; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --subscription ID     Azure subscription ID (or set AZURE_SUBSCRIPTION_ID)
  --location LOC        Azure region (default: ${LOCATION})
  --resource-group NAME Resource group (default: ${RESOURCE_GROUP})
  --storage-prefix PFX  Storage account name prefix (default: ${STORAGE_PREFIX})
  --normal-count N      Normal events per channel (default: ${NORMAL_COUNT})
  --attack-count N      Attack events per channel (default: ${ATTACK_COUNT})
  --no-law              Skip Log Analytics workspace creation
  --skip-upload         Generate local files only (no Azure calls except auth check)
  --dry-run             Print actions without creating/uploading
  --destroy             Delete the resource group and all deployed test data
  -h, --help            Show this help

Examples:
  ./azure/deploy_dummy_data.sh
  ./azure/deploy_dummy_data.sh --subscription 00000000-0000-0000-0000-000000000000
  ./azure/deploy_dummy_data.sh --destroy
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --subscription) SUBSCRIPTION_ID="$2"; shift 2 ;;
    --location) LOCATION="$2"; shift 2 ;;
    --resource-group) RESOURCE_GROUP="$2"; shift 2 ;;
    --storage-prefix) STORAGE_PREFIX="$2"; shift 2 ;;
    --normal-count) NORMAL_COUNT="$2"; shift 2 ;;
    --attack-count) ATTACK_COUNT="$2"; shift 2 ;;
    --no-law) CREATE_LAW=0; shift ;;
    --skip-upload) SKIP_UPLOAD=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --destroy) DESTROY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Unknown option: $1 (use --help)" ;;
  esac
done

require_az() {
  command -v az >/dev/null 2>&1 || fail "Azure CLI (az) not found. Install: https://learn.microsoft.com/cli/azure/install-azure-cli"
  az account show >/dev/null 2>&1 || fail "Not logged in. Run: az login"
}

resolve_subscription() {
  if [[ -z "${SUBSCRIPTION_ID}" ]]; then
    SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
  fi
  [[ -n "${SUBSCRIPTION_ID}" ]] || fail "Could not resolve Azure subscription ID"
  az account set --subscription "${SUBSCRIPTION_ID}" >/dev/null
  local name
  name="$(az account show --query name -o tsv)"
  ok "Using subscription: ${name} (${SUBSCRIPTION_ID})"
}

storage_account_name() {
  # Storage accounts: 3–24 chars, lowercase alphanumeric only.
  local suffix
  suffix="$(echo -n "${SUBSCRIPTION_ID}${RESOURCE_GROUP}" | shasum -a 256 | cut -c1-8)"
  local name
  name="$(echo "${STORAGE_PREFIX}${suffix}" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')"
  echo "${name:0:24}"
}

destroy_stack() {
  require_az
  resolve_subscription
  info "Destroying resource group ${RESOURCE_GROUP} (subscription ${SUBSCRIPTION_ID})…"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    warn "DRY-RUN: would delete RG ${RESOURCE_GROUP}"
    exit 0
  fi
  if az group exists --name "${RESOURCE_GROUP}" | grep -qi true; then
    az group delete --name "${RESOURCE_GROUP}" --yes --no-wait
    ok "Delete initiated for ${RESOURCE_GROUP} (async). Monitor with: az group show -n ${RESOURCE_GROUP}"
  else
    warn "Resource group ${RESOURCE_GROUP} does not exist — nothing to destroy"
  fi
  exit 0
}

generate_local_telemetry() {
  local py
  if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    py="${ROOT_DIR}/.venv/bin/python"
  else
    py="$(command -v python3 || command -v python)"
  fi
  [[ -n "${py}" ]] || fail "Python not found"

  info "Generating dummy Activity / NSG telemetry…"
  rm -rf "${LOCAL_OUT}"
  mkdir -p "${LOCAL_OUT}"
  "${py}" "${SCRIPT_DIR}/generate_telemetry.py" \
    --out-dir "${LOCAL_OUT}" \
    --subscription-id "${SUBSCRIPTION_ID}" \
    --resource-group "${RESOURCE_GROUP}" \
    --normal-count "${NORMAL_COUNT}" \
    --attack-count "${ATTACK_COUNT}"
  ok "Local telemetry ready at ${LOCAL_OUT}"
}

deploy_azure() {
  local storage_name
  storage_name="$(storage_account_name)"

  info "Resource group: ${RESOURCE_GROUP}"
  info "Location:       ${LOCATION}"
  info "Storage:        ${storage_name}"
  [[ "${CREATE_LAW}" -eq 1 ]] && info "Log Analytics:  ${LAW_NAME}"

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    warn "DRY-RUN: skipping Azure resource creation and upload"
    return 0
  fi

  info "Creating resource group…"
  az group create \
    --name "${RESOURCE_GROUP}" \
    --location "${LOCATION}" \
    --tags "project=Quantum Helix" "purpose=dummy-telemetry" "managed-by=deploy_dummy_data.sh" \
    --output none
  ok "Resource group ready"

  info "Creating storage account (this can take a minute)…"
  az storage account create \
    --name "${storage_name}" \
    --resource-group "${RESOURCE_GROUP}" \
    --location "${LOCATION}" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --allow-blob-public-access false \
    --min-tls-version TLS1_2 \
    --tags "project=Quantum Helix" "purpose=dummy-telemetry" \
    --output none
  ok "Storage account ${storage_name} created"

  local account_key
  account_key="$(az storage account keys list \
    --resource-group "${RESOURCE_GROUP}" \
    --account-name "${storage_name}" \
    --query '[0].value' -o tsv)"

  for container in activity-logs nsg-flow-logs attack-scenarios meta; do
    info "Ensuring container: ${container}"
    az storage container create \
      --name "${container}" \
      --account-name "${storage_name}" \
      --account-key "${account_key}" \
      --output none >/dev/null
  done
  ok "Blob containers ready"

  info "Uploading Activity Log dummy data…"
  az storage blob upload-batch \
    --account-name "${storage_name}" \
    --account-key "${account_key}" \
    --destination activity-logs \
    --source "${LOCAL_OUT}/activity-logs" \
    --overwrite true \
    --output none
  ok "Uploaded activity-logs"

  info "Uploading NSG Flow dummy data…"
  az storage blob upload-batch \
    --account-name "${storage_name}" \
    --account-key "${account_key}" \
    --destination nsg-flow-logs \
    --source "${LOCAL_OUT}/nsg-flow-logs" \
    --overwrite true \
    --output none
  ok "Uploaded nsg-flow-logs"

  info "Uploading named attack scenarios + manifest…"
  az storage blob upload \
    --account-name "${storage_name}" \
    --account-key "${account_key}" \
    --container-name attack-scenarios \
    --file "${LOCAL_OUT}/attack-scenarios/named_attacks.json" \
    --name named_attacks.json \
    --overwrite true \
    --output none
  az storage blob upload \
    --account-name "${storage_name}" \
    --account-key "${account_key}" \
    --container-name meta \
    --file "${LOCAL_OUT}/manifest.json" \
    --name manifest.json \
    --overwrite true \
    --output none
  ok "Uploaded attack-scenarios and meta/manifest.json"

  if [[ "${CREATE_LAW}" -eq 1 ]]; then
    info "Creating Log Analytics workspace ${LAW_NAME}…"
    az monitor log-analytics workspace create \
      --resource-group "${RESOURCE_GROUP}" \
      --workspace-name "${LAW_NAME}" \
      --location "${LOCATION}" \
      --tags "project=Quantum Helix" "purpose=dummy-telemetry" \
      --output none
    ok "Log Analytics workspace ready (placeholder for future Diagnostic Settings)"
  fi

  # Write a local connection file (gitignored path) — no account key persisted.
  local conn_file="${LOCAL_OUT}/azure_deployment.json"
  cat > "${conn_file}" <<EOF
{
  "subscription_id": "${SUBSCRIPTION_ID}",
  "resource_group": "${RESOURCE_GROUP}",
  "location": "${LOCATION}",
  "storage_account": "${storage_name}",
  "containers": ["activity-logs", "nsg-flow-logs", "attack-scenarios", "meta"],
  "log_analytics_workspace": $( [[ "${CREATE_LAW}" -eq 1 ]] && echo "\"${LAW_NAME}\"" || echo "null" ),
  "blob_prefixes": {
    "activity_normal": "activity-logs/normal.ndjson",
    "activity_attacks": "activity-logs/attacks.ndjson",
    "nsg_normal": "nsg-flow-logs/normal.ndjson",
    "nsg_attacks": "nsg-flow-logs/attacks.ndjson",
    "named_attacks": "attack-scenarios/named_attacks.json",
    "manifest": "meta/manifest.json"
  },
  "fetch_command": "python azure/fetch_and_score.py --resource-group ${RESOURCE_GROUP} --storage-account ${storage_name}"
}
EOF

  # 1-hour read-only SAS for local testing (optional convenience)
  local expiry sas_activity
  expiry="$(date -u -v+1H +%Y-%m-%dT%H:%MZ 2>/dev/null || date -u -d '+1 hour' +%Y-%m-%dT%H:%MZ)"
  sas_activity="$(az storage container generate-sas \
    --account-name "${storage_name}" \
    --account-key "${account_key}" \
    --name activity-logs \
    --permissions rl \
    --expiry "${expiry}" \
    -o tsv 2>/dev/null || true)"

  echo
  echo -e "${C_GREEN}${C_BOLD}+======================================================================+${C_RESET}"
  echo -e "${C_GREEN}${C_BOLD}|     AZURE DUMMY TELEMETRY DEPLOYED FOR Quantum Helix TEST        |${C_RESET}"
  echo -e "${C_GREEN}${C_BOLD}+======================================================================+${C_RESET}"
  echo
  echo "  Subscription : ${SUBSCRIPTION_ID}"
  echo "  Resource group: ${RESOURCE_GROUP}"
  echo "  Storage       : ${storage_name}"
  echo "  Containers    : activity-logs, nsg-flow-logs, attack-scenarios, meta"
  [[ "${CREATE_LAW}" -eq 1 ]] && echo "  Log Analytics : ${LAW_NAME}"
  echo "  Local mirror  : ${LOCAL_OUT}"
  echo "  Deployment JSON: ${conn_file}"
  echo
  echo "  Download + score against QNN:"
  echo "    source .venv/bin/activate"
  echo "    python azure/fetch_and_score.py --resource-group ${RESOURCE_GROUP} --storage-account ${storage_name}"
  echo
  echo "  List blobs:"
  echo "    az storage blob list --account-name ${storage_name} --container-name activity-logs -o table"
  if [[ -n "${sas_activity}" ]]; then
    echo
    echo "  Read-only SAS (activity-logs, ~1h):"
    echo "    https://${storage_name}.blob.core.windows.net/activity-logs?${sas_activity}"
  fi
  echo
  echo "  Tear down when finished:"
  echo "    ./azure/deploy_dummy_data.sh --destroy --subscription ${SUBSCRIPTION_ID}"
  echo
  warn "Dummy data only — do not use for production SOC decisions."
}

main() {
  echo -e "${C_BOLD}Quantum Helix — Azure dummy data deployment${C_RESET}"
  echo

  if [[ "${DESTROY}" -eq 1 ]]; then
    destroy_stack
  fi

  require_az
  resolve_subscription

  if [[ "${SKIP_UPLOAD}" -eq 1 ]]; then
    generate_local_telemetry
    ok "Skip-upload mode complete (files only under ${LOCAL_OUT})"
    exit 0
  fi

  generate_local_telemetry
  deploy_azure
}

main
