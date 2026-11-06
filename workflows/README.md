# Workflows moved

Kanbanauts agent workflows now live under [`.github/workflows/`](../.github/workflows/).

- Generated entry files: `agent-<phase>-<engine>.md` (from `scripts/gen-workflows.py`)
- Shared imports: `.github/workflows/shared/`
- Customer caller template: [`templates/workflows-kanbanauts.yml`](../templates/workflows-kanbanauts.yml)
- Config template: [`templates/kanbanauts.yml`](../templates/kanbanauts.yml)

Customers do **not** copy these files. The App opens a setup PR with the static caller. Agent logic runs from `conpilot-io/kanbanauts@v1`.

To regenerate after a template change:

```bash
python scripts/gen-workflows.py
gh aw compile agent-plan-claude agent-plan-codex agent-plan-gemini \
  agent-doit-claude agent-doit-codex agent-doit-gemini \
  --force-refresh-action-pins --approve
```
