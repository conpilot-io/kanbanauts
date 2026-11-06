"""Open setup PRs when the App is installed on a repository."""

from __future__ import annotations

import logging
from typing import Any

from kanbanauts.core.broker import ONBOARDING_PERMISSIONS
from kanbanauts.core.caller import (
    AGENT_LABELS,
    CALLER_WORKFLOW_PATH,
    CONFIG_PATH,
    render_caller_workflow,
    render_config,
    setup_pr_body,
)
from kanbanauts.core.github_app import GitHubApp
from kanbanauts.core.ports import HttpResponse

logger = logging.getLogger(__name__)

SETUP_BRANCH = "kanbanauts/setup"
SETUP_PR_TITLE = "Set up Kanbanauts"


class OnboardingService:
    def __init__(self, github: GitHubApp) -> None:
        self.github = github

    async def handle_event(
        self, event: str, payload: dict[str, Any]
    ) -> HttpResponse:
        action = str(payload.get("action") or "")
        installation = payload.get("installation") or {}
        installation_id = int(installation.get("id") or 0)
        if not installation_id:
            return HttpResponse.json(200, {"ok": True, "ignored": "no_installation"})

        repos: list[dict[str, Any]] = []
        if event == "installation" and action in (
            "created",
            "new_permissions_accepted",
        ):
            repos = list(payload.get("repositories") or [])
            if not repos:
                # Fall back to API listing
                token = await self.github.installation_token(
                    installation_id, permissions=ONBOARDING_PERMISSIONS
                )
                repos = await self.github.list_installation_repos(token)
        elif event == "installation_repositories" and action == "added":
            repos = list(payload.get("repositories_added") or [])
        else:
            logger.info("Onboarding ignore event=%s action=%s", event, action)
            return HttpResponse.json(200, {"ok": True, "ignored": action})

        results: list[dict[str, Any]] = []
        for repo in repos:
            try:
                result = await self.setup_repo(installation_id, repo)
                results.append(result)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Onboarding failed for %s", repo.get("full_name") or repo.get("name")
                )
                results.append(
                    {
                        "repo": repo.get("full_name") or repo.get("name"),
                        "ok": False,
                        "error": str(exc),
                    }
                )
        return HttpResponse.json(200, {"ok": True, "results": results})

    async def setup_repo(
        self, installation_id: int, repo: dict[str, Any]
    ) -> dict[str, Any]:
        owner = str(
            (repo.get("owner") or {}).get("login")
            or str(repo.get("full_name") or "").split("/")[0]
        )
        name = str(repo.get("name") or "")
        full = str(repo.get("full_name") or f"{owner}/{name}")
        if repo.get("archived"):
            return {"repo": full, "ok": True, "skipped": "archived"}
        if not owner or not name:
            return {"repo": full, "ok": False, "error": "missing owner/name"}

        try:
            token = await self.github.installation_token(
                installation_id,
                repositories=[name],
                permissions=ONBOARDING_PERMISSIONS,
            )
        except Exception as exc:  # noqa: BLE001
            # Permissions may not be accepted yet
            logger.warning("Token for onboarding %s failed: %s", full, exc)
            return {"repo": full, "ok": False, "error": str(exc)}

        existing = await self.github.get_repo_file(
            token, owner, name, CALLER_WORKFLOW_PATH
        )
        if existing is not None:
            return {"repo": full, "ok": True, "skipped": "already_configured"}

        await self._ensure_labels(token, owner, name)

        account_type = str((repo.get("owner") or {}).get("type") or "Organization")
        project_url: str | None = None
        candidates: list[str] = []
        if account_type.casefold() == "organization" or "/" in full:
            try:
                projects = await self.github.list_org_projects(token, owner)
                candidates = [str(p["url"]) for p in projects if p.get("url")]
                if len(candidates) == 1:
                    project_url = candidates[0]
            except Exception:  # noqa: BLE001
                logger.exception("list_org_projects failed for %s", owner)

        repo_data = await self.github.get_repository(token, owner, name)
        default_branch = str(repo_data.get("default_branch") or "main")
        base_sha = await self.github.get_ref_sha(
            token, owner, name, f"heads/{default_branch}"
        )
        if not base_sha:
            return {"repo": full, "ok": False, "error": "missing_default_branch_sha"}

        # Reuse or create setup branch
        branch_sha = await self.github.get_ref_sha(
            token, owner, name, f"heads/{SETUP_BRANCH}"
        )
        if branch_sha is None:
            await self.github.create_ref(
                token,
                owner,
                name,
                ref=f"refs/heads/{SETUP_BRANCH}",
                sha=base_sha,
            )

        caller = render_caller_workflow()
        config = render_config(
            project_url=project_url, project_candidates=candidates
        )
        await self.github.put_file(
            token,
            owner,
            name,
            CALLER_WORKFLOW_PATH,
            content=caller,
            message="chore(kanbanauts): add caller workflow",
            branch=SETUP_BRANCH,
        )
        await self.github.put_file(
            token,
            owner,
            name,
            CONFIG_PATH,
            content=config,
            message="chore(kanbanauts): add config",
            branch=SETUP_BRANCH,
        )

        # Open PR if none exists
        head = f"{owner}:{SETUP_BRANCH}"
        open_prs = await self.github.list_pull_requests(
            token, owner, name, head=head, state="open"
        )
        if open_prs:
            return {
                "repo": full,
                "ok": True,
                "pr": open_prs[0].get("html_url"),
                "skipped": "pr_exists",
            }

        pr = await self.github.create_pull_request(
            token,
            owner,
            name,
            title=SETUP_PR_TITLE,
            head=SETUP_BRANCH,
            base=default_branch,
            body=setup_pr_body(
                project_url=project_url, project_candidates=candidates
            ),
        )
        return {"repo": full, "ok": True, "pr": pr.get("html_url")}

    async def _ensure_labels(self, token: str, owner: str, repo: str) -> None:
        for name, color in AGENT_LABELS.items():
            try:
                await self.github.ensure_label(
                    token, owner, repo, name, color=color, description="Kanbanauts"
                )
            except Exception:  # noqa: BLE001
                logger.exception("ensure_label %s failed on %s/%s", name, owner, repo)
