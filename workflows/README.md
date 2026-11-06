# Workflows moved

Kanbanauts agent workflows now live under [`.github/workflows/`](../.github/workflows/).

- Generated entry files: `agent-<phase>-<engine>.md` (from `scripts/gen-workflows.py`)
- Shared imports: `.github/workflows/shared/`
- Customer caller template: [`templates/workflows-kanbanauts.yml`](../templates/workflows-kanbanauts.yml)
- Config template: [`templates/kanbanauts.yml`](../templates/kanbanauts.yml)

Customers do **not** copy these files. The App opens a setup PR with the static caller. Agent logic runs from `conpilot-io/kanbanauts@v1`.

To regenerate after a template change, use the same gh-aw version as CI
(`v1.2.0`, pinned in `.github/workflows/ci.yml` and `release.yml`):

```bash
gh extension install github/gh-aw --pin v1.2.0
python scripts/gen-workflows.py
SHA=4607d462dc213dbe54d02f77ec31215776fd5554
gh aw compile agent-plan-claude agent-plan-codex agent-plan-gemini \
  agent-doit-claude agent-doit-codex agent-doit-gemini \
  --action-mode action --action-tag "$SHA" --approve
```
