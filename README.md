# Kanbanauts

GitHub Projects + AI agents. Tickets move on a Kanban board, or you comment an `/ai` command on an issue. Agents run in the customer's GitHub Actions using the customer's AI keys.

See [Manual commands](#manual-commands) for every comment command, [Design.md](Design.md) for the architecture, and [docs/ONBOARDING.md](docs/ONBOARDING.md) for install steps.

## Manual commands

Comment on an issue. The issue does not need to be on a Project board. Only a user with write access can run a command. The label `agent:skip` blocks the command.

| Command | Effect |
|---|---|
| `/ai plan` | Start or run planning again. Comment on the issue, not on the pull request. |
| `/ai doit` | Start implementation. `/ai do` is the same command. Comment on the issue, not on the pull request. When the issue already has an open same-repo pull request that closes it, the agent commits to that pull request. Otherwise it opens a new draft. |
| `/ai review` | Review the linked draft pull request. The agent posts comments only. It does not approve and it does not merge. |
| `/ai retry` | Run a phase again. Add the phase name (`/ai retry doit`). With no name, the phase is `plan`. |
| `/ai status` | Post the current agent state and the active runs. |
| `/ai cancel` | Stop the active agent run. |
| `/ai help` | Post this command list on the issue. |

These prefixes also work: `/kanbanauts`, `@kanbanauts`, `@kanbanauts[bot]`, and `/agent`. You can put `:` or `,` after the prefix (`/ai: plan`).

`/ai review`, `/ai retry`, `/ai status`, and `/ai cancel` also work on a pull request when the pull request body contains `Closes #<issue>`.

If an agent is already queued or running, run `/ai cancel` before `/ai plan`, `/ai doit`, or `/ai review`.

## How distribution works

1. Install the [Kanbanauts GitHub App](https://github.com/apps/kanbanauts).
2. Merge the setup PR (static caller + config).
3. Set the org secret and variables for your AI vendor (see [AI vendor examples](#ai-vendor-examples)).

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
# Match the gh-aw pin in .github/workflows/ci.yml (currently v1.2.0)
gh extension install github/gh-aw --pin v1.2.0
# After `gh aw compile`, preserve Azure OpenAI base paths in Codex locks:
python scripts/patch_codex_awf_baseurl.py
```

Run the ASGI app:

```bash
export GITHUB_APP_ID=...
export GITHUB_APP_PRIVATE_KEY="$(cat app.pem)"
export GITHUB_WEBHOOK_SECRET=...
export KANBANAUTS_URL=http://localhost:8000
uvicorn kanbanauts.hosting.asgi:app --reload
```

## AI vendor examples

Set these under the org (or repo) **Settings → Secrets and variables → Actions**.  
Pick one engine with `KANBANAUTS_ENGINE` (default: `claude`).

| Name | Kind | Required |
|---|---|---|
| `KANBANAUTS_AI_API_KEY` | Secret | Yes |
| `KANBANAUTS_AI_MODEL` | Variable | Yes |
| `KANBANAUTS_ENGINE` | Variable | No (`claude`, `codex`, or `gemini`) |
| `KANBANAUTS_AI_BASE_URL` | Variable | No (Claude / Codex custom or Azure endpoints) |

### Claude (Anthropic)

```text
KANBANAUTS_ENGINE=claude
KANBANAUTS_AI_API_KEY=<anthropic-api-key>
KANBANAUTS_AI_MODEL=claude-sonnet-4-5
```

Azure AI Foundry / Anthropic-compatible base URL:

```text
KANBANAUTS_ENGINE=claude
KANBANAUTS_AI_API_KEY=<azure-or-gateway-key>
KANBANAUTS_AI_MODEL=<deployment-or-model-name>
KANBANAUTS_AI_BASE_URL=https://<resource>.services.ai.azure.com
```

### Codex (OpenAI)

```text
KANBANAUTS_ENGINE=codex
KANBANAUTS_AI_API_KEY=<openai-api-key>
KANBANAUTS_AI_MODEL=gpt-5
```

Azure OpenAI (Responses API via AWF; keep the `/openai/v1` path, not `/responses`):

```text
KANBANAUTS_ENGINE=codex
KANBANAUTS_AI_API_KEY=<azure-openai-key>
KANBANAUTS_AI_MODEL=<deployment-name>
KANBANAUTS_AI_BASE_URL=https://<resource>.openai.azure.com/openai/v1
```

### Gemini (Google)

```text
KANBANAUTS_ENGINE=gemini
KANBANAUTS_AI_API_KEY=<gemini-api-key>
KANBANAUTS_AI_MODEL=gemini-2.5-pro
```

Network allow-lists are fixed at compile time for Anthropic, OpenAI, Azure AI, and Google hosts. Custom hosts outside those need a workflow change in this repo.
