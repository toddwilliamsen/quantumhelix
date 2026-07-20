#!/usr/bin/env bash
# Deploy Quantum Helix (Flask API + React static) to Azure App Service.
#
# Fixes vs previous script:
#   - Forces PYTHON|3.12 (numpy 2.5.x is incompatible with Oryx's default 3.11)
#   - Uses slim requirements-azure.txt (no Streamlit)
#   - Zips only runtime files (not frontend/, logs, docs, .venv)
#   - Synchronous zip deploy with status polling (no false "success")
#   - Non-interactive RG rebuild via REBUILD_RG=y
#
# Usage:
#   ./deploy_azure.sh
#   REBUILD_RG=y ./deploy_azure.sh          # delete + recreate resource group
#   WEB_APP_NAME=my-unique-name ./deploy_azure.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

RESOURCE_GROUP="${RESOURCE_GROUP:-QuantumPoC-RG}"
LOCATION="${LOCATION:-westus2}"
WEB_APP_NAME="${WEB_APP_NAME:-quantum-helix-demo-alpha8}"
REBUILD_RG="${REBUILD_RG:-n}"
DEPLOY_TIMEOUT_SEC="${DEPLOY_TIMEOUT_SEC:-1800}"
DEPLOY_TIMEOUT_MS=$((DEPLOY_TIMEOUT_SEC * 1000))
PYTHON_STACK="PYTHON|3.12"

log()  { printf '\n==> %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required"; }

need az
need npm
need zip
need python3

log "Starting Azure deployment (stack=${PYTHON_STACK}, app=${WEB_APP_NAME})"

# --- Frontend build ----------------------------------------------------------
log "Building React frontend..."
(
  cd frontend
  npm install
  npm run build
)
rm -rf static
cp -R frontend/dist static
[[ -f static/index.html ]] || die "frontend build missing static/index.html"

# --- Azure login -------------------------------------------------------------
az account show >/dev/null 2>&1 || die "Not logged in. Run: az login"

# --- Resource group ----------------------------------------------------------
RG_EXISTS="$(az group exists --name "$RESOURCE_GROUP")"
if [[ "$RG_EXISTS" == "true" ]]; then
  if [[ "${REBUILD_RG}" =~ ^[Yy]$ ]]; then
    log "Deleting resource group ${RESOURCE_GROUP} (async)..."
    az group delete --name "$RESOURCE_GROUP" --yes --no-wait
    log "Waiting for delete to finish (can take several minutes)..."
    while az group exists --name "$RESOURCE_GROUP" 2>/dev/null | grep -qi true; do
      printf '.'
      sleep 15
    done
    printf '\n'
    log "Creating resource group ${RESOURCE_GROUP} in ${LOCATION}"
    az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
  else
    log "Using existing resource group ${RESOURCE_GROUP} (set REBUILD_RG=y to recreate)"
  fi
else
  log "Creating resource group ${RESOURCE_GROUP} in ${LOCATION}"
  az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
fi

# --- ARM template ------------------------------------------------------------
log "Deploying ARM template (App Service + plan)..."
az deployment group create \
  --name "QuantumDeployment-$(date +%Y%m%d%H%M%S)" \
  --resource-group "$RESOURCE_GROUP" \
  --template-file azuredeploy.json \
  --parameters "webAppName=${WEB_APP_NAME}" "location=${LOCATION}" "linuxFxVersion=${PYTHON_STACK}" \
  --output none

# Force runtime + build flags even on incremental updates of an old site
log "Forcing ${PYTHON_STACK} and Oryx build settings..."
az webapp config set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEB_APP_NAME" \
  --linux-fx-version "$PYTHON_STACK" \
  --startup-file "gunicorn --bind=0.0.0.0:8000 --timeout 600 --threads 4 api:app" \
  --output none

az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEB_APP_NAME" \
  --settings \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true \
    ENABLE_ORYX_BUILD=true \
    WEBSITES_PORT=8000 \
  --output none

RUNTIME="$(az webapp config show -g "$RESOURCE_GROUP" -n "$WEB_APP_NAME" --query linuxFxVersion -o tsv)"
[[ "$RUNTIME" == "$PYTHON_STACK" ]] || die "Runtime is '${RUNTIME}', expected '${PYTHON_STACK}'"
log "Confirmed App Service runtime: ${RUNTIME}"

# --- Package only what App Service needs -------------------------------------
log "Packaging deploy.zip (runtime files only)..."
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/quantum-deploy.XXXXXX")"
cleanup() { rm -rf "$STAGE" "${ROOT}/deploy.zip"; }
trap cleanup EXIT

PY_MODULES=(
  api.py
  models.py
  alerter.py
  apt_corpus.py
  benchmark.py
  classical_baselines.py
  data_processor.py
  ensemble.py
  normalization.py
  quantum_engine.py
  quantum_kernel.py
  cmdb.py
  itsm.py
)

for f in "${PY_MODULES[@]}"; do
  [[ -f "$f" ]] || die "Missing required file: $f"
  cp "$f" "$STAGE/"
done

cp requirements-azure.txt "$STAGE/requirements.txt"
cp -R static "$STAGE/static"

(
  cd "$STAGE"
  zip -r "$ROOT/deploy.zip" . >/dev/null
)

ZIP_MB="$(python3 -c "import os; print(f'{os.path.getsize(\"deploy.zip\")/1e6:.2f}')")"
log "deploy.zip is ${ZIP_MB} MB"

# Give ARM a moment before Kudu accepts publish
sleep 5

# --- Async zip deploy + status poll ------------------------------------------
# Sync deploy on B1 routinely returns HTTP 504 while Oryx is still building
# (PennyLane/sklearn pip install exceeds the front-door gateway timeout).
# Upload async, disable startup health tracking (cold start is slow), then poll Kudu.
log "Uploading package (async). Remote Oryx build can take 10-25 min on B1..."

az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEB_APP_NAME" \
  --settings \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true \
    ENABLE_ORYX_BUILD=true \
    SCM_COMMAND_IDLE_TIMEOUT=3600 \
    WEBSITES_CONTAINER_START_TIME_LIMIT=1800 \
  --output none

set +e
az webapp deploy \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEB_APP_NAME" \
  --src-path deploy.zip \
  --type zip \
  --async true \
  --track-status false \
  --clean true \
  --timeout "$DEPLOY_TIMEOUT_MS"
DEPLOY_RC=$?
set -e

wait_for_deployment() {
  local deadline=$((SECONDS + DEPLOY_TIMEOUT_SEC))
  local last=""
  local ticks=0
  log "Polling Kudu deployment status (Ctrl+C stops the waiter only; Azure keeps building)..."
  while (( SECONDS < deadline )); do
    local status id
    status="$(az webapp log deployment list \
      --resource-group "$RESOURCE_GROUP" \
      --name "$WEB_APP_NAME" \
      --query "[0].status" -o tsv 2>/dev/null || true)"
    id="$(az webapp log deployment list \
      --resource-group "$RESOURCE_GROUP" \
      --name "$WEB_APP_NAME" \
      --query "[0].id" -o tsv 2>/dev/null || true)"

    # Kudu: 4=Success, 3=Failed, 1/2=Building/Deploying
    if [[ "$status" != "$last" ]]; then
      log "Deployment status: ${status:-unknown} (id=${id:-n/a})"
      last="$status"
    else
      printf '.'
      ticks=$((ticks + 1))
      if (( ticks % 6 == 0 )); then
        printf '\n'
        # Periodically surface the latest build lines so it doesn't look hung
        az webapp log deployment show \
          --resource-group "$RESOURCE_GROUP" \
          --name "$WEB_APP_NAME" \
          --deployment-id "${id:-}" 2>/dev/null \
          | tail -n 8 \
          | sed 's/^/    /' || true
      fi
    fi

    case "$status" in
      4|Success|success)
        printf '\n'
        return 0
        ;;
      3|Failed|failed)
        printf '\n'
        echo "----- Deployment log (tail) -----"
        az webapp log deployment show \
          --resource-group "$RESOURCE_GROUP" \
          --name "$WEB_APP_NAME" \
          --deployment-id "$id" 2>/dev/null | tail -n 100 || true
        return 1
        ;;
    esac
    sleep 20
  done
  printf '\n'
  die "Timed out after ${DEPLOY_TIMEOUT_SEC}s waiting for deployment"
}

# 504 / non-zero from sync-ish paths is OK if Kudu still has an in-progress deploy
if [[ $DEPLOY_RC -ne 0 ]]; then
  log "Upload command exited ${DEPLOY_RC} (504 gateway timeouts are common on B1). Checking Kudu..."
fi
wait_for_deployment || die "Remote build/deploy failed. Check: az webapp log deployment show -g ${RESOURCE_GROUP} -n ${WEB_APP_NAME}"

log "Restarting web app..."
az webapp restart --resource-group "$RESOURCE_GROUP" --name "$WEB_APP_NAME" --output none

URL="https://${WEB_APP_NAME}.azurewebsites.net"
echo ""
echo "✅ Deployment finished successfully."
echo "   App URL:  ${URL}"
echo "   Login:    admin / quantum123"
echo ""
echo "If the site 5xx's on first hit, wait 1-2 minutes for gunicorn cold start"
echo "(PCA + quantum kernel warm-up can be slow on B1)."
