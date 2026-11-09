---
# DoIt only: if the issue already has an open same-repo PR that
# closes/fixes/resolves it, check out that branch before the agent runs.
# gh-aw removes git credentials before the agent, so fetch must happen here.
permissions:
  id-token: write

pre-agent-steps:
  - name: Kanbanauts checkout existing PR
    id: existing-pr
    env:
      ISSUE: ${{ inputs.issue_number }}
      GH_TOKEN: ${{ steps.kanban.outputs.token }}
      GITHUB_REPOSITORY: ${{ github.repository }}
      KANBANAUTS_URL: ${{ vars.KANBANAUTS_URL || 'https://kanbanauts-fn.azurewebsites.net/api' }}
      PHASE: ${{ env.GH_AW_KANBAN_PHASE }}
    run: |
      set -euo pipefail
      if [ "${KANBANAUTS_SKIP:-0}" = "1" ]; then
        echo "Already skipped; leaving default checkout"
        exit 0
      fi
      if [ -z "${GH_TOKEN:-}" ] || [ "${GH_TOKEN}" = "null" ]; then
        echo "::warning::No Kanbanauts token; leaving default checkout"
        exit 0
      fi
      export GH_TOKEN
      OWNER="${GITHUB_REPOSITORY%%/*}"
      REPO="${GITHUB_REPOSITORY#*/}"

      # List open PRs (first 100). Selection is pure jq so unit tests can run it.
      PRS_JSON=$(gh api \
        -H "Accept: application/vnd.github+json" \
        "/repos/${OWNER}/${REPO}/pulls?state=open&per_page=100&sort=updated&direction=desc")

      # BEGIN kanban-select-existing-pr
      SELECTED=$(printf '%s' "$PRS_JSON" | jq -c --argjson issue "${ISSUE}" '
        def closing($n):
          (.body // "") | test("(?i)\\b(closes|fixes|resolves)\\s+#" + ($n | tostring) + "\\b");
        def same_repo:
          (.head.repo.full_name // "") != ""
          and (.head.repo.full_name // "") == (.base.repo.full_name // "");
        def is_fork:
          (.head.repo.full_name // "") != ""
          and (.head.repo.full_name // "") != (.base.repo.full_name // "");
        ($issue | tonumber) as $n
        | [
            .[]
            | select((.state // "open") == "open")
            | select(closing($n))
          ] as $matches
        | ($matches | map(select(same_repo)) | sort_by(.updated_at) | reverse | .[0] // null) as $same
        | if $same != null then
            {kind: "same_repo", pr: $same}
          elif ($matches | map(select(is_fork)) | length) > 0 then
            {kind: "fork_only", pr: ($matches | map(select(is_fork)) | sort_by(.updated_at) | reverse | .[0])}
          else
            {kind: "none", pr: null}
          end
      ')
      # END kanban-select-existing-pr

      KIND=$(printf '%s' "$SELECTED" | jq -r '.kind')
      if [ "$KIND" = "none" ]; then
        echo "No open same-repo PR for issue #${ISSUE}; leaving default checkout"
        echo "KANBANAUTS_EXISTING_PR=" >> "$GITHUB_ENV"
        exit 0
      fi

      if [ "$KIND" = "fork_only" ]; then
        PR_NUM=$(printf '%s' "$SELECTED" | jq -r '.pr.number')
        MSG="Kanbanauts found open pull request #${PR_NUM} for this issue, but it is from a fork.
      The agent cannot push to a fork branch. Do not open a second pull request.

      **Next step:** Open a same-repository branch/PR that closes this issue, then comment \`/ai doit\` again."
        # Backend posts the message on blocked reports (no gh write in agent job).
        OIDC=$(curl -sSL -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
          "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=${KANBANAUTS_URL}" | jq -r .value)
        BODY=$(jq -n \
          --arg status "blocked" \
          --arg phase "${PHASE:-doit}" \
          --argjson issue "${ISSUE:-0}" \
          --arg msg "$MSG" \
          --arg oidc "$OIDC" \
          '{status:$status, phase:$phase, issue_number:$issue, message:$msg, oidc_token:$oidc}')
        curl -sSL -X POST "${KANBANAUTS_URL}/report" \
          -H "Content-Type: application/json" \
          -d "$BODY" || true
        echo "KANBANAUTS_SKIP=1" >> "$GITHUB_ENV"
        echo "KANBANAUTS_EXISTING_PR=" >> "$GITHUB_ENV"
        echo "::notice::Existing PR #${PR_NUM} is a fork; skipping agent"
        exit 0
      fi

      PR_NUM=$(printf '%s' "$SELECTED" | jq -r '.pr.number')
      HEAD_REF=$(printf '%s' "$SELECTED" | jq -r '.pr.head.ref')
      HEAD_SHA=$(printf '%s' "$SELECTED" | jq -r '.pr.head.sha')
      HEAD_REPO=$(printf '%s' "$SELECTED" | jq -r '.pr.head.repo.full_name')

      echo "::notice::Reusing open PR #${PR_NUM} on branch ${HEAD_REF} (${HEAD_SHA})"
      git fetch --depth=1 origin "${HEAD_REF}"
      git checkout -B "${HEAD_REF}" "FETCH_HEAD"

      {
        echo "KANBANAUTS_EXISTING_PR=${PR_NUM}"
        echo "GH_AW_PR_HEAD_BASE_PR_NUMBER=${PR_NUM}"
        echo "GH_AW_PR_HEAD_BASE_BRANCH=${HEAD_REF}"
        echo "GH_AW_PR_HEAD_BASE_REF=${HEAD_REF}"
        echo "GH_AW_PR_HEAD_BASE_SHA=${HEAD_SHA}"
        echo "GH_AW_PR_HEAD_BASE_REPO=${HEAD_REPO}"
        echo "GH_AW_PR_HEAD_REPO=${HEAD_REPO}"
        echo "GH_AW_TARGET_REPO_SLUG=${GITHUB_REPOSITORY}"
      } >> "$GITHUB_ENV"

      echo "checked_out=true" >> "$GITHUB_OUTPUT"
      echo "pr_number=${PR_NUM}" >> "$GITHUB_OUTPUT"
---
<!-- Shared DoIt checkout of an existing linked pull request. -->
