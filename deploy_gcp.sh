#!/usr/bin/env bash
# Deploy Quantum Helix to Google Cloud Run
#
# Usage:
#   ./deploy_gcp.sh
#   GCP_PROJECT=my-project GCP_REGION=us-central1 SERVICE_NAME=quantum-helix ./deploy_gcp.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
GCP_REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-quantum-helix-demo}"

log()  { printf '\n==> %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required"; }

need gcloud
need npm

if [[ -z "$GCP_PROJECT" ]]; then
  die "GCP_PROJECT is not set and no default project found. Run 'gcloud config set project <PROJECT_ID>'"
fi

log "Starting GCP deployment (project=${GCP_PROJECT}, region=${GCP_REGION}, service=${SERVICE_NAME})"

# --- Frontend build ---
log "Building React frontend..."
(
  cd frontend
  npm install
  npm run build
)
rm -rf static
cp -R frontend/dist static
[[ -f static/index.html ]] || die "frontend build missing static/index.html"

# --- Cloud Run Deploy ---
log "Deploying to Cloud Run (This will build the container in Cloud Build)..."

gcloud run deploy "$SERVICE_NAME" \
  --project "$GCP_PROJECT" \
  --region "$GCP_REGION" \
  --source . \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 1 \
  --set-env-vars="FLASK_ENV=production"

echo ""
echo "✅ Deployment finished successfully."
