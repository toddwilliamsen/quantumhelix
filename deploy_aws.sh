#!/usr/bin/env bash
# Deploy Quantum Helix to AWS Elastic Beanstalk
#
# Usage:
#   ./deploy_aws.sh
#   AWS_REGION=us-west-2 APP_NAME=quantum-helix ./deploy_aws.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

AWS_REGION="${AWS_REGION:-us-west-2}"
APP_NAME="${APP_NAME:-quantum-helix-demo}"
ENV_NAME="${ENV_NAME:-quantum-helix-env}"

log()  { printf '\n==> %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required"; }

need eb
need npm

log "Starting AWS Elastic Beanstalk deployment (region=${AWS_REGION}, app=${APP_NAME})"

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

# --- EB Deploy ---
log "Initializing Elastic Beanstalk application (if not exists)..."
eb init "$APP_NAME" --platform "Python 3.12" --region "$AWS_REGION"

# Check if environment exists
if eb status "$ENV_NAME" >/dev/null 2>&1; then
  log "Environment ${ENV_NAME} exists. Deploying update..."
  eb deploy "$ENV_NAME"
else
  log "Creating new environment ${ENV_NAME} (this takes several minutes)..."
  eb create "$ENV_NAME" \
    --instance-types t3.medium \
    --envvars FLASK_ENV=production
fi

echo ""
echo "✅ Deployment finished successfully."
echo "   Run 'eb open $ENV_NAME' to view the application."
