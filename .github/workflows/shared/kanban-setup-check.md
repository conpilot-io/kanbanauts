---
# Fail closed with a blocked report when the AI API key secret is missing.
permissions:
  id-token: write

pre-agent-steps:
  - name: Kanbanauts setup check
    env:
      KANBANAUTS_URL: ${{ vars.KANBANAUTS_URL || 'https://kanbanauts-fn.azurewebsites.net/api' }}
      PHASE: ${{ env.GH_AW_KANBAN_PHASE }}
      ISSUE: ${{ inputs.issue_number }}
      KANBANAUTS_AI_API_KEY: ${{ secrets.KANBANAUTS_AI_API_KEY }}
    run: |
      set -euo pipefail
      if [ -n "${KANBANAUTS_AI_API_KEY:-}" ]; then
        exit 0
      fi
      echo "::error::KANBANAUTS_AI_API_KEY is not set"
      MSG="Kanbanauts is blocked: missing secret \`KANBANAUTS_AI_API_KEY\`.
      Add it under **Settings → Secrets and variables → Actions** (org or repo), then re-run or move the ticket again.
      Docs: https://github.com/conpilot-io/kanbanauts/blob/main/docs/ONBOARDING.md"
      OIDC=$(curl -sSL -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
        "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=${KANBANAUTS_URL}" | jq -r .value)
      BODY=$(jq -n \
        --arg status "blocked" \
        --arg phase "${PHASE:-plan}" \
        --argjson issue "${ISSUE:-0}" \
        --arg msg "$MSG" \
        --arg oidc "$OIDC" \
        '{status:$status, phase:$phase, issue_number:$issue, message:$msg, oidc_token:$oidc}')
      curl -sSL -X POST "${KANBANAUTS_URL}/report" \
        -H "Content-Type: application/json" \
        -d "$BODY" || true
      echo "KANBANAUTS_SKIP=1" >> "$GITHUB_ENV"
---
<!-- Shared setup check for missing KANBANAUTS_AI_API_KEY. -->
