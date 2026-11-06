---
# Preflight: skip the agent if the ticket left the phase column.
# Importing workflows set env GH_AW_KANBAN_PHASE.
permissions:
  id-token: write

pre-agent-steps:
  - name: Kanbanauts preflight
    env:
      KANBANAUTS_URL: ${{ vars.KANBANAUTS_URL || 'https://kanbanauts-fn.azurewebsites.net/api' }}
      PHASE: ${{ env.GH_AW_KANBAN_PHASE }}
      ISSUE: ${{ inputs.issue_number }}
    run: |
      set -euo pipefail
      if [ "${KANBANAUTS_SKIP:-0}" = "1" ]; then
        echo "Already skipped (setup check)"
        exit 0
      fi
      OIDC=$(curl -sSL -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
        "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=${KANBANAUTS_URL}" | jq -r .value)
      RESP=$(curl -sSL -G "${KANBANAUTS_URL}/preflight" \
        --data-urlencode "issue=${ISSUE}" \
        --data-urlencode "phase=${PHASE}" \
        -H "Authorization: Bearer ${OIDC}")
      echo "$RESP"
      SKIP=$(printf '%s' "$RESP" | jq -r '.skip // true')
      if [ "$SKIP" = "true" ]; then
        echo "::notice::Preflight skip — ticket is not in the expected column"
        echo "KANBANAUTS_SKIP=1" >> "$GITHUB_ENV"
        exit 0
      fi
      echo "KANBANAUTS_SKIP=0" >> "$GITHUB_ENV"
---
<!-- Shared Kanbanauts preflight check. -->
