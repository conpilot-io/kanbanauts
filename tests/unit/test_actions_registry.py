from __future__ import annotations

from typing import Any

import pytest
from kanbanauts.core.actions import ActionRunner, TicketContext
from kanbanauts.core.config import CancelAction, CommentAction, RunAction, load_config_yaml
from kanbanauts.core.state import AgentState

from tests.conftest import SAMPLE_CONFIG


class _Gh:
    def __init__(self) -> None:
        self.dispatched: list[str] = []
        self.comments: list[str] = []
        self.cancelled: list[int] = []
        self.labels: set[str] = set()
        self.runs: list[dict[str, Any]] = []

    async def installation_token(
        self,
        installation_id: int,
        *,
        repositories: list[str] | None = None,
        permissions: dict[str, str] | None = None,
    ) -> str:
        return "t"

    async def list_issue_labels(
        self, token: str, owner: str, repo: str, issue_number: int
    ) -> set[str]:
        return set(self.labels)

    async def set_issue_state_label(
        self,
        token: str,
        owner: str,
        repo: str,
        issue_number: int,
        *,
        remove: list[str],
        add: list[str],
    ) -> None:
        for label in remove:
            self.labels.discard(label)
        self.labels.update(add)

    async def add_issue_comment(
        self, token: str, owner: str, repo: str, issue_number: int, body: str
    ) -> Any:
        self.comments.append(body)
        return {}

    async def dispatch_workflow(
        self,
        token: str,
        owner: str,
        repo: str,
        workflow_id: str,
        *,
        ref: str,
        inputs: dict[str, Any],
    ) -> None:
        self.dispatched.append(workflow_id)

    async def list_workflow_runs(
        self,
        token: str,
        owner: str,
        repo: str,
        *,
        status: str | None = None,
        per_page: int = 50,
    ) -> list[dict[str, Any]]:
        return list(self.runs)

    async def cancel_workflow_run(
        self, token: str, owner: str, repo: str, run_id: int
    ) -> None:
        self.cancelled.append(run_id)

    async def graphql(
        self, token: str, query: str, variables: dict[str, Any] | None = None
    ) -> Any:
        return {}

    async def get_repository(self, token: str, owner: str, repo: str) -> dict[str, Any]:
        return {"default_branch": "main"}


@pytest.mark.asyncio
async def test_run_and_comment() -> None:
    cfg = load_config_yaml(SAMPLE_CONFIG)
    gh = _Gh()
    runner = ActionRunner(github=gh, config=cfg)
    ctx = TicketContext(owner="acme", repo="app", issue_number=1, installation_id=1)
    await runner.run_one(ctx, RunAction(run="plan"))
    assert gh.dispatched == ["kanbanauts.yml"]
    assert AgentState.QUEUED.value in gh.labels
    await runner.run_one(ctx, CommentAction(comment="hello"))
    assert gh.comments[-1] == "hello"


@pytest.mark.asyncio
async def test_cancel_filters_by_issue() -> None:
    cfg = load_config_yaml(SAMPLE_CONFIG)
    gh = _Gh()
    gh.runs = [
        {
            "id": 1,
            "status": "in_progress",
            "name": "agent doit #1",
            "html_url": "http://x/1",
        },
        {
            "id": 2,
            "status": "in_progress",
            "name": "agent doit #99",
            "html_url": "http://x/2",
        },
    ]
    runner = ActionRunner(github=gh, config=cfg)
    ctx = TicketContext(
        owner="acme",
        repo="app",
        issue_number=1,
        installation_id=1,
        to_column="Backlog",
    )
    await runner.run_one(ctx, CancelAction(cancel=True))
    assert gh.cancelled == [1]
    assert any("Stopped" in c for c in gh.comments)


@pytest.mark.asyncio
async def test_cancel_with_no_runs_is_quiet() -> None:
    cfg = load_config_yaml(SAMPLE_CONFIG)
    gh = _Gh()
    gh.labels.add("agent:succeeded")
    runner = ActionRunner(github=gh, config=cfg)
    ctx = TicketContext(
        owner="acme",
        repo="app",
        issue_number=1,
        installation_id=1,
        labels=set(gh.labels),
        to_column="Tests",
    )
    await runner.run_one(ctx, CancelAction(cancel=True))
    assert gh.cancelled == []
    assert gh.comments == []
    assert "agent:succeeded" in gh.labels
