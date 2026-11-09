---
# Report phase status to the Kanbanauts backend.
# Importing workflows set env GH_AW_KANBAN_PHASE.
safe-outputs:
  jobs:
    kanban-report:
      description: "Report agent phase status to Kanbanauts"
      runs-on: ubuntu-latest
      output: "Kanbanauts report processed"
      needs: [safe_outputs]
      permissions:
        contents: read
        id-token: write
      inputs:
        status:
          description: "succeeded, no_code, blocked, failed, or running"
          required: true
          type: string
        pr_number:
          description: "Pull request number when a PR was created"
          required: false
          type: string
          default: ""
        message:
          description: "Optional message posted on the issue (e.g. setup help)"
          required: false
          type: string
          default: ""
      steps:
        - name: Report to Kanbanauts
          env:
            KANBANAUTS_URL: ${{ vars.KANBANAUTS_URL || 'https://kanbanauts-fn.azurewebsites.net/api' }}
            PHASE: ${{ env.GH_AW_KANBAN_PHASE }}
            ISSUE: ${{ inputs.issue_number }}
            CREATED_PR_NUMBER: ${{ needs.safe_outputs.outputs.created_pr_number }}
          run: |
            set -euo pipefail
            if [ -z "${GH_AW_AGENT_OUTPUT:-}" ] || [ ! -f "$GH_AW_AGENT_OUTPUT" ]; then
              # Setup-check / preflight may report without agent output via message path
              if [ -z "${GH_AW_KANBAN_REPORT_STATUS:-}" ]; then
                echo "::warning::No agent output; skipping report"
                exit 0
              fi
            fi
            STATUS="${GH_AW_KANBAN_REPORT_STATUS:-}"
            PR=""
            MSG="${GH_AW_KANBAN_REPORT_MESSAGE:-}"
            if [ -z "$STATUS" ] && [ -n "${GH_AW_AGENT_OUTPUT:-}" ] && [ -f "$GH_AW_AGENT_OUTPUT" ]; then
              STATUS=$(jq -r '
                [.items[]? | select(.type == "kanban_report") | .status] | first // empty
              ' "$GH_AW_AGENT_OUTPUT")
              PR=$(jq -r '
                [.items[]? | select(.type == "kanban_report") | .pr_number] | first // empty
              ' "$GH_AW_AGENT_OUTPUT")
              MSG=$(jq -r '
                [.items[]? | select(.type == "kanban_report") | .message] | first // empty
              ' "$GH_AW_AGENT_OUTPUT")
              if [ -z "$STATUS" ]; then
                WANTED=$(jq -r '[.items[]? | select(.type == "create_pull_request")] | length' "$GH_AW_AGENT_OUTPUT")
                if [ "$WANTED" -gt 0 ] && [ -n "${CREATED_PR_NUMBER:-}" ] && [ "$CREATED_PR_NUMBER" != "null" ]; then
                  STATUS=succeeded
                  PR="$CREATED_PR_NUMBER"
                else
                  echo "No kanban_report in agent output; skipping"
                  exit 0
                fi
              fi
            fi
            # BEGIN kanban-report-resolve-pr
            # Agents may pass a temporary id (#aw_...) before the PR exists.
            # Prefer digits; otherwise use CREATED_PR_NUMBER from safe_outputs.
            RAW_PR="${PR:-}"
            if [[ ! "${PR:-}" =~ ^[0-9]+$ ]]; then
              if [ -n "${PR:-}" ] && [ "${PR}" != "null" ]; then
                echo "::warning::Ignoring non-numeric pr_number='$PR'; using CREATED_PR_NUMBER if available"
              fi
              PR=""
              if [[ "${CREATED_PR_NUMBER:-}" =~ ^[0-9]+$ ]]; then
                PR="$CREATED_PR_NUMBER"
              fi
            fi
            # END kanban-report-resolve-pr
            OIDC=$(curl -sSL -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
              "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=${KANBANAUTS_URL}" | jq -r .value)
            BODY=$(jq -n \
              --arg status "$STATUS" \
              --arg phase "${PHASE:-plan}" \
              --argjson issue "${ISSUE:-0}" \
              --arg pr "${PR:-}" \
              --arg msg "${MSG:-}" \
              --arg oidc "$OIDC" \
              '{
                status: $status,
                phase: $phase,
                issue_number: $issue,
                pr_number: (if ($pr | test("^[0-9]+$")) then ($pr|tonumber) else null end),
                message: (if $msg == "" then null else $msg end),
                oidc_token: $oidc
              }')
            curl -sSL -X POST "${KANBANAUTS_URL}/report" \
              -H "Content-Type: application/json" \
              -d "$BODY"
            echo "Reported status=$STATUS phase=${PHASE:-plan} issue=$ISSUE pr=${PR:-} raw_pr=${RAW_PR:-}"
---
<!-- Shared Kanbanauts report safe-output job. -->
