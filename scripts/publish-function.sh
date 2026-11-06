#!/usr/bin/env bash
# Publish Kanbanauts Azure Function App code.
# Usage:
#   ./scripts/publish-function.sh
#   ./scripts/publish-function.sh kanbanauts-fn
set -euo pipefail

FUNCTION_APP_NAME="${1:-kanbanauts-fn}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v func >/dev/null 2>&1; then
  echo "error: Azure Functions Core Tools (func) not found." >&2
  echo "Install: brew tap azure/functions && brew install azure-functions-core-tools@4" >&2
  exit 1
fi

DEPLOY_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$DEPLOY_DIR"
}
trap cleanup EXIT

echo "Repo:       $ROOT_DIR"
echo "Deploy dir: $DEPLOY_DIR"
echo "App name:   $FUNCTION_APP_NAME"

cp backend/kanbanauts/hosting/azure_functions/function_app.py "$DEPLOY_DIR/"
cp backend/kanbanauts/hosting/azure_functions/host.json "$DEPLOY_DIR/"
cp -R backend/kanbanauts "$DEPLOY_DIR/kanbanauts"

cat > "$DEPLOY_DIR/requirements.txt" <<'EOF'
httpx>=0.27
PyJWT[crypto]>=2.9
cryptography>=43
pydantic>=2.8
pydantic-settings>=2.4
PyYAML>=6.0
starlette>=0.38
azure-functions>=1.21
azure-identity>=1.17
azure-keyvault-secrets>=4.8
EOF

touch "$DEPLOY_DIR/kanbanauts/py.typed"

cd "$DEPLOY_DIR"
func azure functionapp publish "$FUNCTION_APP_NAME" --python

echo "Published to $FUNCTION_APP_NAME"
