# Vendor ops (private details)

This file uses **placeholders** only. Put real Azure names, subscription IDs, and App IDs in a private repo (for example `conpilot-io/kanbanauts-ops`) or a local `setup.md` (gitignored).

## Before making the repo public

1. Confirm `setup.md` is gitignored and not tracked: `git ls-files setup.md` must print nothing.
2. Scrub history (only 3 early commits may still contain identifiers):

```bash
cd /path/to/kanbanauts
git checkout --orphan clean-main
git add -A
git commit -m "feat(kanbanauts): initial public release"
git branch -M clean-main main
git push --force origin main
```

3. Scan:

```bash
brew install gitleaks
gitleaks detect --source . --log-opts="--all"
```

4. GitHub → Settings → General → Danger Zone → Make public.
5. Enable **Secret scanning** and **Push protection**.
6. Actions → Fork pull request workflows: require approval for outside collaborators.

## Deploy checklist (fill in privately)

| Item | Placeholder |
|---|---|
| Subscription ID | `<subscription-id>` |
| Resource group | `<resource-group>` |
| Region | `<region>` |
| Key Vault | `<key-vault>` |
| Function App | `kanbanauts-fn` (or yours) |
| Public base URL | `https://<function-app>.azurewebsites.net/api` |
| GitHub App ID | `<app-id>` |

```bash
az account set --subscription "<subscription-id>"
az deployment group create \
  -g "<resource-group>" \
  -f infra/main.bicep \
  -p appId=<app-id> \
     keyVaultName=<key-vault> \
     functionAppName=kanbanauts-fn
./scripts/publish-function.sh kanbanauts-fn
```

Grant the Function identity **Key Vault Secrets User** on `<key-vault>`.
Humans who set secrets need **Key Vault Secrets Officer**.

## Release checklist (every release)

The release workflow calls the **deployed** Function (`/admin/rollout`). That
Function renders the customer caller from its own bundled template. If you tag
before you publish, customers get an old template under a new version number
and their runs end in "Startup failure".

1. Merge to `main` and wait for CI to pass.
2. Publish the Function: `./scripts/publish-function.sh kanbanauts-fn`.
3. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.
4. Check the Release run. The rollout step fails with HTTP 409 if the deployed
   Function is older than the release. In that case, do step 2 and re-run the
   Release job.
5. Merge the "Upgrade Kanbanauts caller" PR in each customer repo.
6. Move a test item to **Plan** and check that nested jobs
   (`plan_<engine> / activation` and so on) appear.

Note: the rollout skips repos that are already at the target caller version.
If a wrong file was merged under the right version number, copy
`templates/workflows-kanbanauts.yml` into the customer repo by hand.

## Tag ruleset

Settings → Rules → Rulesets → New tag ruleset `release-tags`, pattern `refs/tags/v*.*.*` (semver only — leave floating majors like `v1` unprotected so Release can move them), restrict updates and deletions, bypass: Repository admin.
