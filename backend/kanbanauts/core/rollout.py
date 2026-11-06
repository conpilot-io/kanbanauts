"""Open upgrade PRs when the customer caller version is behind."""

from __future__ import annotations

import logging
from typing import Any

from kanbanauts.core.broker import ONBOARDING_PERMISSIONS
from kanbanauts.core.caller import (
    CALLER_VERSION,
    CALLER_WORKFLOW_PATH,
    parse_caller_version,
    render_caller_workflow,
)
from kanbanauts.core.github_app import GitHubApp

logger = logging.getLogger(__name__)

UPGRADE_BRANCH = "kanbanauts/upgrade-caller"
UPGRADE_PR_TITLE = "Upgrade Kanbanauts caller"


class RolloutService:
    def __init__(self, github: GitHubApp) -> None:
        self.github = github

    async def run(
        self, *, caller_version: int = CALLER_VERSION, dry_run: bool = False
    ) -> dict[str, Any]:
        installations = await self.github.list_installations()
        upgraded: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for inst in installations:
            installation_id = int(inst.get("id") or 0)
            if not installation_id:
                continue
            try:
                token = await self.github.installation_token(
                    installation_id, permissions=ONBOARDING_PERMISSIONS
                )
                repos = await self.github.list_installation_repos(token)
            except Exception as exc:  # noqa: BLE001
                errors.append({"installation": installation_id, "error": str(exc)})
                continue

            for repo in repos:
                owner = str((repo.get("owner") or {}).get("login") or "")
                name = str(repo.get("name") or "")
                full = str(repo.get("full_name") or f"{owner}/{name}")
                if repo.get("archived") or not owner or not name:
                    skipped.append({"repo": full, "reason": "archived_or_invalid"})
                    continue
                try:
                    result = await self._maybe_upgrade_repo(
                        token,
                        owner,
                        name,
                        full,
                        target_version=caller_version,
                        dry_run=dry_run,
                    )
                    if result.get("upgraded"):
                        upgraded.append(result)
                    else:
                        skipped.append(result)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("rollout failed for %s", full)
                    errors.append({"repo": full, "error": str(exc)})

        return {
            "dry_run": dry_run,
            "target_version": caller_version,
            "upgraded": upgraded,
            "skipped": skipped,
            "errors": errors,
        }

    async def _maybe_upgrade_repo(
        self,
        token: str,
        owner: str,
        name: str,
        full: str,
        *,
        target_version: int,
        dry_run: bool,
    ) -> dict[str, Any]:
        text = await self.github.get_repo_file(
            token, owner, name, CALLER_WORKFLOW_PATH
        )
        if text is None:
            return {"repo": full, "upgraded": False, "reason": "no_caller"}
        current = parse_caller_version(text)
        if current is None:
            return {"repo": full, "upgraded": False, "reason": "no_version_header"}
        if current >= target_version:
            return {
                "repo": full,
                "upgraded": False,
                "reason": "up_to_date",
                "version": current,
            }

        new_text = render_caller_workflow(version=target_version)
        if dry_run:
            return {
                "repo": full,
                "upgraded": True,
                "dry_run": True,
                "from": current,
                "to": target_version,
            }

        repo_data = await self.github.get_repository(token, owner, name)
        default_branch = str(repo_data.get("default_branch") or "main")
        base_sha = await self.github.get_ref_sha(
            token, owner, name, f"heads/{default_branch}"
        )
        if not base_sha:
            return {"repo": full, "upgraded": False, "reason": "missing_sha"}

        branch_sha = await self.github.get_ref_sha(
            token, owner, name, f"heads/{UPGRADE_BRANCH}"
        )
        if branch_sha is None:
            await self.github.create_ref(
                token,
                owner,
                name,
                ref=f"refs/heads/{UPGRADE_BRANCH}",
                sha=base_sha,
            )

        sha = await self.github.get_file_sha(
            token, owner, name, CALLER_WORKFLOW_PATH, ref=UPGRADE_BRANCH
        )
        await self.github.put_file(
            token,
            owner,
            name,
            CALLER_WORKFLOW_PATH,
            content=new_text,
            message=f"chore(kanbanauts): upgrade caller to {target_version}",
            branch=UPGRADE_BRANCH,
            sha=sha,
        )

        head = f"{owner}:{UPGRADE_BRANCH}"
        open_prs = await self.github.list_pull_requests(
            token, owner, name, head=head, state="open"
        )
        if open_prs:
            return {
                "repo": full,
                "upgraded": True,
                "pr": open_prs[0].get("html_url"),
                "from": current,
                "to": target_version,
            }

        pr = await self.github.create_pull_request(
            token,
            owner,
            name,
            title=UPGRADE_PR_TITLE,
            head=UPGRADE_BRANCH,
            base=default_branch,
            body=(
                f"Upgrade the Kanbanauts caller from version `{current}` "
                f"to `{target_version}`.\n\n"
                "Agent logic still comes from "
                "`conpilot-io/kanbanauts@v1`. Merge to keep receiving updates."
            ),
        )
        return {
            "repo": full,
            "upgraded": True,
            "pr": pr.get("html_url"),
            "from": current,
            "to": target_version,
        }
