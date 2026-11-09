# Kanbanauts onboarding

## TL;DR

- Install the Kanbanauts GitHub App on your organization.
- Merge the setup pull request the App opens.
- Add one org secret (`KANBANAUTS_AI_API_KEY`) and one variable (`KANBANAUTS_AI_MODEL`).
- Move a ticket to Plan — a plan comment appears on the issue.

---

## Customer setup (3 steps)

1. Open https://github.com/apps/kanbanauts, click **Install**, select the org and repositories.
2. Merge the pull request **Set up Kanbanauts** (adds `.github/workflows/kanbanauts.yml` and `.github/kanbanauts.yml`).
3. Org **Settings → Secrets and variables → Actions**:
   - Secret: `KANBANAUTS_AI_API_KEY`
   - Variables: `KANBANAUTS_AI_MODEL`, and optionally `KANBANAUTS_ENGINE` (`claude` | `codex` | `gemini`), `KANBANAUTS_AI_BASE_URL`
   - For Azure OpenAI + Codex, set `KANBANAUTS_AI_BASE_URL=https://<resource>.openai.azure.com/openai/v1` (include `/openai/v1`; do not append `/responses`)
   - Set repository access to all repos or the selected repos.

Then:

- Confirm Project columns match the config: Plan, DoIt, Review, Tests, Done (or edit `.github/kanbanauts.yml`).
- Optional: add `AGENTS.md` with project rules.
- Test: create an issue, add it to the Project, move it to Plan. Expect `agent:queued` → plan comment → `agent:succeeded`.

### Tickets that need no agent

- Keep them out of Plan/DoIt, or
- Add label `agent:skip`, or
- Set `mode: opt_in` and only label code tickets with `agent`.

You do **not** run `gh aw add` or `gh aw compile`. Agent logic runs from `conpilot-io/kanbanauts@v1` and updates when that tag moves.

---

## Vendor: GitHub App (one time)

1. GitHub → **Org → Settings → Developer settings → GitHub Apps → New GitHub App**.
2. Name: `Kanbanauts`. Homepage URL: your docs URL.
3. Webhook: active. URL: `https://<function-app>.azurewebsites.net/api/webhook`. Secret: `openssl rand -hex 32`.
4. Repository permissions:
   - Actions, Contents, Issues, Pull requests: **Read & write**
   - Metadata, Checks: **Read**
   - **Workflows: Read & write** (needed so the App can open setup/upgrade PRs that touch `.github/workflows/`)
5. Organization permissions: Projects **Read & write**, Members **Read**.
6. Subscribe to events: Issue comment, Pull request review, Workflow run, Projects v2 item.
   (`installation` and `installation_repositories` are always delivered — no checkbox.)
7. Where can this app be installed: **Any account**. Create the App.
8. Record App ID. Generate a private key (`.pem`). Store it only in Key Vault.

After a permission change, each installing org must **Accept new permissions** under Settings → GitHub Apps.

## Vendor: deploy the backend

Keep Azure resource names and subscription IDs in a **private** ops note (see [VENDOR_OPS.md](VENDOR_OPS.md)). Do not commit them to this public repo.

1. Put secrets in Key Vault: `github-app-private-key`, `github-webhook-secret`.
2. Deploy with `infra/main.bicep` into your resource group (placeholders in VENDOR_OPS.md).
3. Publish: `./scripts/publish-function.sh <function-app-name>`
4. Health check: `curl -sS https://<function-app>.azurewebsites.net/api/health`
5. Confirm `POST /api/report` with `Authorization: Bearer x` returns **401**.

Alternative (ASGI):

```bash
export GITHUB_APP_ID=...
export GITHUB_APP_PRIVATE_KEY="..."
export GITHUB_WEBHOOK_SECRET=...
export KANBANAUTS_URL=https://your.public.url
uvicorn kanbanauts.hosting.asgi:app --host 0.0.0.0 --port 8000
```

## Vendor: release and protect tags

1. Make `conpilot-io/kanbanauts` **public** only after scrubbing ops docs and cleaning git history (see VENDOR_OPS.md).
2. Tag ruleset on `refs/tags/v*.*.*` (semver only; do not protect floating majors like `v1`): restrict updates and deletions.
3. `git tag v1.0.0 && git push origin v1.0.0` — release workflow compiles, moves major tag `v1`, and calls `/admin/rollout` when the caller version changes.

## Self-hosters

Override `vars.KANBANAUTS_URL` in the customer org to point at your backend. Default is the vendor Function URL baked into the shared workflow imports.
