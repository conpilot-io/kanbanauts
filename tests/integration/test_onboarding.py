"""Integration tests for App install onboarding PRs."""

from __future__ import annotations

from typing import Any

import pytest
from kanbanauts.core.caller import CALLER_WORKFLOW_PATH, CONFIG_PATH, parse_caller_version
from kanbanauts.core.onboarding import OnboardingService
from kanbanauts.core.rollout import RolloutService


class FakeOnboardGitHub:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.labels: set[str] = set()
        self.prs: list[dict[str, Any]] = []
        self.refs: dict[str, str] = {"heads/main": "sha-main"}
        self.projects: list[dict[str, Any]] = [
            {
                "number": 1,
                "title": "Board",
                "url": "https://github.com/orgs/acme/projects/1",
            }
        ]
        self.put_calls: list[str] = []
        self.archived = False
        self.token_permissions: dict[str, str] | None = None

    async def installation_token(
        self, installation_id: int, **kwargs: Any
    ) -> str:
        self.token_permissions = kwargs.get("permissions")
        return "tok"

    async def get_repo_file(
        self, token: str, owner: str, repo: str, path: str, *, ref: str | None = None
    ) -> str | None:
        return self.files.get(path)

    async def ensure_label(
        self, token: str, owner: str, repo: str, name: str, **kwargs: Any
    ) -> None:
        self.labels.add(name)

    async def get_repository(self, token: str, owner: str, repo: str) -> dict[str, Any]:
        return {"default_branch": "main", "name": repo, "archived": self.archived}

    async def get_ref_sha(
        self, token: str, owner: str, repo: str, ref: str
    ) -> str | None:
        return self.refs.get(ref)

    async def create_ref(
        self, token: str, owner: str, repo: str, *, ref: str, sha: str
    ) -> None:
        # refs/heads/kanbanauts/setup -> heads/kanbanauts/setup
        key = ref.removeprefix("refs/")
        self.refs[key] = sha

    async def put_file(
        self,
        token: str,
        owner: str,
        repo: str,
        path: str,
        *,
        content: str,
        message: str,
        branch: str,
        sha: str | None = None,
    ) -> dict[str, Any]:
        self.files[path] = content
        self.put_calls.append(path)
        return {"content": {"path": path}}

    async def list_pull_requests(
        self, token: str, owner: str, repo: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return [p for p in self.prs if p.get("state", "open") == "open"]

    async def create_pull_request(
        self, token: str, owner: str, repo: str, **kwargs: Any
    ) -> dict[str, Any]:
        pr = {
            "html_url": f"https://github.com/{owner}/{repo}/pull/1",
            "state": "open",
            **kwargs,
        }
        self.prs.append(pr)
        return pr

    async def list_org_projects(self, token: str, org: str) -> list[dict[str, Any]]:
        return list(self.projects)

    async def list_installations(self) -> list[dict[str, Any]]:
        return [{"id": 99}]

    async def list_installation_repos(
        self, token: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return [
            {
                "name": "app",
                "full_name": "acme/app",
                "archived": False,
                "owner": {"login": "acme", "type": "Organization"},
            }
        ]

    async def get_file_sha(
        self, token: str, owner: str, repo: str, path: str, *, ref: str
    ) -> str | None:
        return "sha-file" if path in self.files else None


@pytest.mark.asyncio
async def test_setup_opens_pr_with_both_files() -> None:
    gh = FakeOnboardGitHub()
    svc = OnboardingService(github=gh)  # type: ignore[arg-type]
    result = await svc.setup_repo(
        99,
        {
            "name": "app",
            "full_name": "acme/app",
            "archived": False,
            "owner": {"login": "acme", "type": "Organization"},
        },
    )
    assert result["ok"] is True
    assert CALLER_WORKFLOW_PATH in gh.files
    assert CONFIG_PATH in gh.files
    assert parse_caller_version(gh.files[CALLER_WORKFLOW_PATH]) == 1
    assert "https://github.com/orgs/acme/projects/1" in gh.files[CONFIG_PATH]
    assert result.get("pr")
    assert "workflows" in (gh.token_permissions or {})
    assert "agent:queued" in gh.labels


@pytest.mark.asyncio
async def test_setup_skips_when_caller_exists() -> None:
    gh = FakeOnboardGitHub()
    gh.files[CALLER_WORKFLOW_PATH] = "# kanbanauts-caller: 1\n"
    svc = OnboardingService(github=gh)  # type: ignore[arg-type]
    result = await svc.setup_repo(
        99,
        {
            "name": "app",
            "full_name": "acme/app",
            "owner": {"login": "acme", "type": "Organization"},
        },
    )
    assert result.get("skipped") == "already_configured"
    assert not gh.prs


@pytest.mark.asyncio
async def test_setup_skips_archived() -> None:
    gh = FakeOnboardGitHub()
    svc = OnboardingService(github=gh)  # type: ignore[arg-type]
    result = await svc.setup_repo(
        99,
        {
            "name": "app",
            "full_name": "acme/app",
            "archived": True,
            "owner": {"login": "acme"},
        },
    )
    assert result.get("skipped") == "archived"


@pytest.mark.asyncio
async def test_setup_lists_multiple_projects() -> None:
    gh = FakeOnboardGitHub()
    gh.projects = [
        {"number": 1, "title": "A", "url": "https://github.com/orgs/acme/projects/1"},
        {"number": 2, "title": "B", "url": "https://github.com/orgs/acme/projects/2"},
    ]
    svc = OnboardingService(github=gh)  # type: ignore[arg-type]
    await svc.setup_repo(
        99,
        {
            "name": "app",
            "full_name": "acme/app",
            "owner": {"login": "acme", "type": "Organization"},
        },
    )
    assert "Several org Projects" in gh.files[CONFIG_PATH]


@pytest.mark.asyncio
async def test_setup_idempotent_second_run() -> None:
    gh = FakeOnboardGitHub()
    svc = OnboardingService(github=gh)  # type: ignore[arg-type]
    repo = {
        "name": "app",
        "full_name": "acme/app",
        "owner": {"login": "acme", "type": "Organization"},
    }
    first = await svc.setup_repo(99, repo)
    assert first.get("pr")
    # Simulate merged / file present on default branch
    second = await svc.setup_repo(99, repo)
    assert second.get("skipped") == "already_configured"


@pytest.mark.asyncio
async def test_handle_installation_created() -> None:
    gh = FakeOnboardGitHub()
    svc = OnboardingService(github=gh)  # type: ignore[arg-type]
    resp = await svc.handle_event(
        "installation",
        {
            "action": "created",
            "installation": {"id": 99},
            "repositories": [
                {
                    "name": "app",
                    "full_name": "acme/app",
                    "owner": {"login": "acme", "type": "Organization"},
                }
            ],
        },
    )
    assert resp.status == 200
    assert gh.prs


@pytest.mark.asyncio
async def test_rollout_upgrades_old_caller() -> None:
    gh = FakeOnboardGitHub()
    gh.files[CALLER_WORKFLOW_PATH] = "# kanbanauts-caller: 0\nold\n"
    svc = RolloutService(github=gh)  # type: ignore[arg-type]
    result = await svc.run(caller_version=1, dry_run=False)
    assert result["upgraded"]
    assert parse_caller_version(gh.files[CALLER_WORKFLOW_PATH]) == 1


@pytest.mark.asyncio
async def test_rollout_dry_run_no_write() -> None:
    gh = FakeOnboardGitHub()
    gh.files[CALLER_WORKFLOW_PATH] = "# kanbanauts-caller: 0\nold\n"
    before = gh.files[CALLER_WORKFLOW_PATH]
    svc = RolloutService(github=gh)  # type: ignore[arg-type]
    result = await svc.run(caller_version=1, dry_run=True)
    assert result["upgraded"]
    assert result["upgraded"][0]["dry_run"] is True
    assert gh.files[CALLER_WORKFLOW_PATH] == before


@pytest.mark.asyncio
async def test_rollout_skips_current() -> None:
    gh = FakeOnboardGitHub()
    gh.files[CALLER_WORKFLOW_PATH] = "# kanbanauts-caller: 1\n"
    svc = RolloutService(github=gh)  # type: ignore[arg-type]
    result = await svc.run(caller_version=1, dry_run=False)
    assert not result["upgraded"]
    assert any(s.get("reason") == "up_to_date" for s in result["skipped"])
