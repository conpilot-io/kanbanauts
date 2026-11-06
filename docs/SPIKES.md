# Spike results

## 1. gh-aw remote imports

**Result:** Customer workflow files can stay thin.

- Shared files can export `engine`, `tools`, `safe-outputs` (including custom `jobs`), `pre-steps`, prompts, and network allow-lists.
- When the main file and an import both set the same key, the main file wins.
- For the same job, imported `pre-steps` run first; main `pre-steps` run after.
- Remote imports use `owner/repo/path@ref` and are cached by commit SHA at compile time.
- `on:` (triggers) should stay in the customer/main workflow so each phase keeps a clear entry point. Shared pieces cover engines, token minting, report jobs, and prompts.

## 2. `projects_v2_item.edited` payload

**Result:** The webhook includes from/to. No GraphQL read is required for the move itself.

For a single-select field change, the payload contains:

```json
"changes": {
  "field_value": {
    "field_node_id": "...",
    "field_type": "single_select",
    "field_name": "Status",
    "project_number": 18,
    "from": { "id": "...", "name": "Todo", "color": "GREEN", "description": "..." },
    "to":   { "id": "...", "name": "In Progress", "color": "YELLOW", "description": "..." }
  }
}
```

Notes:
- `from` or `to` can be `null` when the value is cleared or set for the first time.
- A Status clear may omit `from`/`to` keys. Treat that as no actionable transition.
- Item id is numeric; use `node_id` (`PVTI_…`) for GraphQL.
- Content type (`Issue` vs draft) is on the item; drafts have no linked issue/repo.

## 3. Token minting with `pre-steps` + `safe-outputs.github-token`

**Result:** Supported.

- `safe-outputs.github-token` accepts `${{ steps.<id>.outputs.<name> }}`.
- Put the minting step in `pre-steps` (runs before checkout and token use). Do not put it in `safe-outputs.steps` (that runs too late).
- Pattern for Kanbanauts: a shared import defines `pre-steps` that exchange the Actions OIDC token for a short-lived App installation token via `GET/POST /token`, then:

```yaml
safe-outputs:
  github-token: ${{ steps.kanban.outputs.token }}
  create-pull-request:
    max: 1
```

- Global `safe-outputs.github-token` that uses a step output works inside the `safe_outputs` job. The conclusion job still needs a secret or compiler-managed App auth if it also writes; our report job uses the broker token via its own `pre-steps`.

## 4. `on: workflow_call` reusable workflows (auto-distribution)

**Result:** Supported by gh-aw v1.0.1. Primary plan (caller → central `.lock.yml@v1`) is viable. Fallback (upgrade PR per release) is not required.

### Compile check (local spike)

Source frontmatter:

```yaml
on:
  workflow_call:
    inputs:
      issue_number:
        type: number
        required: true
```

Compiled lock file keeps `on.workflow_call`, preserves `inputs.issue_number`, and injects `on.workflow_call.secrets` for every `${{ secrets.* }}` reference (required: false). Body and jobs see `${{ inputs.issue_number }}` and env `GH_AW_INPUTS_ISSUE_NUMBER`.

Compile notes:
- Strict mode needs SHA-pinned actions. Use `gh aw compile --force-refresh-action-pins` (or `--action-mode action` with a resolved SHA). `--allow-action-refs` works for a local spike only.
- The compiler adds its own concurrency group (`gh-aw-<name>-${{ github.run_id }}`). Do not put a custom issue-based concurrency group on the callee. Put it only on the customer caller.
- Official docs show the caller pattern: `uses: owner/repo/.github/workflows/name.lock.yml@v1` with explicit secrets across orgs (`secrets: inherit` works only in the same org/enterprise).

### Cross-org and OIDC

- The callee repo must be **public** for other orgs to call it.
- Caller vars (`vars.KANBANAUTS_*`) resolve in the callee jobs (lock file uses `${{ vars.* }}`).
- For a reusable workflow job, GitHub OIDC claim `job_workflow_ref` points at the **callee** lock file (`conpilot-io/kanbanauts/.github/workflows/agent-….lock.yml@…`). Claim `workflow_ref` points at the **caller**. The broker must check `job_workflow_ref`.
- Cross-org call was not run end-to-end here (needs a public central repo). Docs and compile output match the plan. Final check is manual step G.

### Token minting note (gh-aw v1.0.1)

Do **not** set a global `safe-outputs.github-token: ${{ steps.kanban.outputs.token }}`. The conclusion job cannot run a user minting step. Use **per-output** `github-token` on `add-comment` / `create-pull-request` / `push-to-pull-request-branch`, and declare the mint step in both top-level `pre-steps` (agent job) and `jobs.safe_outputs.pre-steps`.
