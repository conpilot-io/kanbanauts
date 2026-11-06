---
# Mint a short-lived Kanbanauts App token via OIDC.
# Top-level pre-steps cover the agent job; safe_outputs pre-steps cover
# the safe_outputs job. Use per-output github-token (not global) so the
# conclusion job does not require steps.kanban.
# Default backend URL; override with vars.KANBANAUTS_URL for self-hosting.
permissions:
  id-token: write

pre-steps:
  - name: Mint Kanbanauts token
    id: kanban
    env:
      KANBANAUTS_URL: ${{ vars.KANBANAUTS_URL || 'https://kanbanauts-fn.azurewebsites.net/api' }}
    run: |
      set -euo pipefail
      OIDC=$(curl -sSL -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
        "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=${KANBANAUTS_URL}" | jq -r .value)
      RESP=$(curl -sSL -X POST "${KANBANAUTS_URL}/token" \
        -H "Content-Type: application/json" \
        -d "{\"oidc_token\":$(jq -n --arg t "$OIDC" '$t')}")
      TOKEN=$(printf '%s' "$RESP" | jq -r .token)
      if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
        echo "::error::Failed to mint Kanbanauts token: $RESP"
        exit 1
      fi
      echo "::add-mask::$TOKEN"
      echo "token=$TOKEN" >> "$GITHUB_OUTPUT"

jobs:
  safe_outputs:
    pre-steps:
      - name: Mint Kanbanauts token
        id: kanban
        env:
          KANBANAUTS_URL: ${{ vars.KANBANAUTS_URL || 'https://kanbanauts-fn.azurewebsites.net/api' }}
        run: |
          set -euo pipefail
          OIDC=$(curl -sSL -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=${KANBANAUTS_URL}" | jq -r .value)
          RESP=$(curl -sSL -X POST "${KANBANAUTS_URL}/token" \
            -H "Content-Type: application/json" \
            -d "{\"oidc_token\":$(jq -n --arg t "$OIDC" '$t')}")
          TOKEN=$(printf '%s' "$RESP" | jq -r .token)
          if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
            echo "::error::Failed to mint Kanbanauts token: $RESP"
            exit 1
          fi
          echo "::add-mask::$TOKEN"
          echo "token=$TOKEN" >> "$GITHUB_OUTPUT"
---
<!-- Shared OIDC → Kanbanauts /token minting. -->
