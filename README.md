# Kanbanauts

GitHub Projects + AI agents. Tickets move on a Kanban board; agents plan and implement in the customer's GitHub Actions using the customer's AI keys.

See [Design.md](Design.md) for the architecture and [docs/ONBOARDING.md](docs/ONBOARDING.md) for install steps.

## How distribution works

1. Install the [Kanbanauts GitHub App](https://github.com/apps/kanbanauts).
2. Merge the setup PR (static caller + config).
3. Set org secret `KANBANAUTS_AI_API_KEY` and variable `KANBANAUTS_AI_MODEL`.

Agent logic runs from this public repo at tag `v1`. When we move `v1`, every installed repo gets the update on the next run.

## Repository layout

| Path | Purpose |
|---|---|
| `backend/kanbanauts/` | Stateless Python backend (webhooks, OIDC broker, onboarding, rollout) |
| `.github/workflows/` | gh-aw sources + compiled reusable `agent-*.lock.yml` |
| `templates/` | Customer caller + config templates |
| `infra/main.bicep` | Azure Functions skeleton |
| `docs/` | Onboarding, vendor ops placeholders, spikes |

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check backend tests scripts
mypy --config-file mypy.ini . | mypy-baseline filter
python scripts/gen-workflows.py
```

Run the ASGI app:

```bash
export GITHUB_APP_ID=...
export GITHUB_APP_PRIVATE_KEY="$(cat app.pem)"
export GITHUB_WEBHOOK_SECRET=...
export KANBANAUTS_URL=http://localhost:8000
uvicorn kanbanauts.hosting.asgi:app --reload
```
