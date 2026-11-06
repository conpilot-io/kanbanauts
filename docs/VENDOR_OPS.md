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

## Tag ruleset

Settings → Rules → Rulesets → New tag ruleset `release-tags`, pattern `v*`, restrict updates and deletions, bypass: Repository admin.
