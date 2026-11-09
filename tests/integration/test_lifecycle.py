"""Integration tests for column enter/leave, skip, cancel, and report."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from kanbanauts.core.config import load_config_yaml
from kanbanauts.core.github_app import GitHubApp
from kanbanauts.core.ports import HttpRequest
from kanbanauts.core.service import KanbanautsService, Settings

from tests.conftest import SAMPLE_CONFIG


def _sig(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class FakeGitHub(GitHubApp):
    def __init__(self) -> None:
        super().__init__(app_id="1", private_key_pem="unused")
        self.dispatched: list[dict[str, Any]] = []
        self.cancelled: list[int] = []
        self.comments: list[str] = []
        self.reactions: list[dict[str, Any]] = []
        self.label_ops: list[tuple[list[str], list[str]]] = []
        self.labels: set[str] = set()
        self.runs: list[dict[str, Any]] = []
        self.config_text = SAMPLE_CONFIG
        self.current_column = "Plan"
        self.field_options = ["Backlog", "Plan", "DoIt", "Review", "Tests", "Done"]
        self.moved_to: list[str] = []
        self.permission: str | None = "write"
        self.project_items: list[dict[str, Any]] | None = None
        self.caller_text: str | None = None
        self.dispatch_error: Exception | None = None

    async def installation_token(self, installation_id: int, **kwargs: Any) -> str:
        return "inst-token"

    async def get_repo_file(
        self, token: str, owner: str, repo: str, path: str, *, ref: str | None = None
    ) -> str | None:
        if path == ".github/kanbanauts.yml":
            return self.config_text
        if path == ".github/workflows/kanbanauts.yml":
            return self.caller_text
        return None

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
        self.label_ops.append((remove, add))
        for label in remove:
            self.labels.discard(label)
        for label in add:
            self.labels.add(label)

    async def add_issue_comment(
        self, token: str, owner: str, repo: str, issue_number: int, body: str
    ) -> Any:
        self.comments.append(body)
        return {"id": 1}

    async def add_comment_reaction(
        self,
        token: str,
        owner: str,
        repo: str,
        comment_id: int,
        content: str = "eyes",
    ) -> Any:
        self.reactions.append({"comment_id": comment_id, "content": content})
        return {"id": 1}

    async def list_issue_comments(
        self,
        token: str,
        owner: str,
        repo: str,
        issue_number: int,
        *,
        since: str | None = None,
    ) -> list[str]:
        return list(self.comments)

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
        if self.dispatch_error is not None:
            raise self.dispatch_error
        self.dispatched.append(
            {"workflow": workflow_id, "ref": ref, "inputs": inputs}
        )

    async def list_workflow_runs(
        self,
        token: str,
        owner: str,
        repo: str,
        *,
        status: str | None = None,
        per_page: int = 50,
    ) -> list[dict[str, Any]]:
        return [r for r in self.runs if status is None or r.get("status") == status]

    async def cancel_workflow_run(
        self, token: str, owner: str, repo: str, run_id: int
    ) -> None:
        self.cancelled.append(run_id)

    async def get_repository(self, token: str, owner: str, repo: str) -> dict[str, Any]:
        return {"default_branch": "main", "name": repo}

    async def graphql(
        self, token: str, query: str, variables: dict[str, Any] | None = None
    ) -> Any:
        if "projectItems" in query:
            nodes = self.project_items
            if nodes is None:
                nodes = [
                    {
                        "id": "PVTI_1",
                        "project": {"number": 7, "owner": {"login": "acme"}},
                    }
                ]
            else:
                normalized: list[dict[str, Any]] = []
                for raw in nodes:
                    item = dict(raw)
                    item.setdefault(
                        "project", {"number": 7, "owner": {"login": "acme"}}
                    )
                    normalized.append(item)
                nodes = normalized
            return {"node": {"projectItems": {"nodes": nodes}}}
        if "fieldValues" in query and "node(id:" in query.replace(" ", ""):
            # ITEM_WITH_CONTENT or similar
            if "ProjectV2Item" in query or "fieldValues" in query:
                return {
                    "node": {
                        "id": "PVTI_1",
                        "type": "ISSUE",
                        "content": {
                            "__typename": "Issue",
                            "number": 42,
                            "title": "Test",
                            "repository": {
                                "name": "app",
                                "nameWithOwner": "acme/app",
                                "owner": {"login": "acme"},
                            },
                        },
                        "fieldValues": {
                            "nodes": [
                                {
                                    "name": self.current_column,
                                    "field": {"name": "Status"},
                                }
                            ]
                        },
                    }
                }
        if "projectV2" in query and "fields" in query:
            project = {
                "id": "PVT_1",
                "fields": {
                    "nodes": [
                        {
                            "id": "FIELD_1",
                            "name": "Status",
                            "options": [
                                {"id": f"opt-{n}", "name": n} for n in self.field_options
                            ],
                        }
                    ]
                },
            }
            if "user(login:" in query:
                return {"user": {"projectV2": project}}
            return {"organization": {"projectV2": project}}
        if "updateProjectV2ItemFieldValue" in query:
            option_id = str((variables or {}).get("optionId", ""))
            for name in self.field_options:
                if option_id == f"opt-{name}":
                    self.moved_to.append(name)
                    self.current_column = name
                    break
            return {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_1"}}}
        if "items(first:" in query:
            nodes = self.project_items
            if nodes is None:
                nodes = [{"id": "PVTI_1", "content": {"id": "I_1"}}]
            return {
                "organization": {
                    "projectV2": {
                        "items": {
                            "nodes": nodes
                        }
                    }
                }
            }
        return {}

    async def get(self, path: str, token: str, *, params: dict[str, Any] | None = None) -> Any:
        if "/issues/" in path:
            return {"node_id": "I_1", "number": 42}
        return {}

    async def collaborator_permission(
        self, token: str, owner: str, repo: str, username: str
    ) -> str | None:
        return self.permission


@pytest.fixture
def service() -> tuple[KanbanautsService, FakeGitHub, Any]:
    gh = FakeGitHub()
    settings = Settings(
        app_id="1",
        private_key_pem="not-a-real-key",
        webhook_secret="s3cret",
        oidc_audience="https://kanbanauts.example.com",
    )
    # Bypass JWT for tests — we never call app_jwt in these paths when token is mocked
    svc = KanbanautsService(settings=settings, github=gh, broker=AsyncMock())
    from kanbanauts.core.broker import TokenBroker

    from tests.helpers_oidc import FakeJwkClient, rsa_keypair

    key = rsa_keypair()
    svc.broker = TokenBroker(
        expected_audience=settings.oidc_audience,
        jwks_client=FakeJwkClient(key),
    )
    return svc, gh, key


def _install_client(svc: KanbanautsService, *, owner_id: int = 12345) -> None:
    def _jwt(*, now: int | None = None) -> str:
        return "jwt"

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"id": 99, "account": {"id": owner_id, "login": "acme"}}

    class _Client:
        async def get(self, *args: Any, **kwargs: Any) -> _Resp:
            return _Resp()

    object.__setattr__(svc.github, "app_jwt", _jwt)
    object.__setattr__(svc.github, "_client", lambda: _Client())  # type: ignore[misc,return-value]


def _project_edited_payload(
    *, from_name: str | None, to_name: str, project_number: int = 7
) -> dict[str, Any]:
    return {
        "action": "edited",
        "organization": {"login": "acme"},
        "installation": {"id": 99},
        "projects_v2_item": {
            "id": 1,
            "node_id": "PVTI_1",
            "content_type": "Issue",
        },
        "changes": {
            "field_value": {
                "field_node_id": "FIELD_1",
                "field_type": "single_select",
                "field_name": "Status",
                "project_number": project_number,
                "from": {"id": "a", "name": from_name} if from_name else None,
                "to": {"id": "b", "name": to_name},
            }
        },
    }


async def _post_webhook(
    svc: KanbanautsService, event: str, payload: dict[str, Any]
) -> Any:
    body = json.dumps(payload).encode()
    req = HttpRequest(
        method="POST",
        path="/webhook",
        headers={
            "x-hub-signature-256": _sig("s3cret", body),
            "x-github-event": event,
            "x-github-delivery": "d1",
        },
        body=body,
    )
    return await svc.handle_http(req)


@pytest.mark.asyncio
async def test_enter_plan_dispatches(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    resp = await _post_webhook(
        svc, "projects_v2_item", _project_edited_payload(from_name="Backlog", to_name="Plan")
    )
    assert resp.status == 200
    assert gh.dispatched
    assert gh.dispatched[0]["workflow"] == "kanbanauts.yml"
    assert gh.dispatched[0]["inputs"]["phase"] == "plan"
    assert gh.dispatched[0]["inputs"]["source"] == "board"
    assert "agent:queued" in gh.labels


@pytest.mark.asyncio
async def test_unconfigured_column_noop(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    resp = await _post_webhook(
        svc,
        "projects_v2_item",
        _project_edited_payload(from_name="Backlog", to_name="Backlog"),
    )
    # Backlog not in columns → ignored after enter check
    data = json.loads(resp.body)
    assert data.get("ignored") == "unconfigured_column" or not gh.dispatched


@pytest.mark.asyncio
async def test_wrong_project_ignored(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    resp = await _post_webhook(
        svc,
        "projects_v2_item",
        _project_edited_payload(from_name="Backlog", to_name="Plan", project_number=99),
    )
    assert json.loads(resp.body)["ignored"] == "wrong_project"
    assert not gh.dispatched


@pytest.mark.asyncio
async def test_skip_label_blocks(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    gh.labels.add("agent:skip")
    resp = await _post_webhook(
        svc, "projects_v2_item", _project_edited_payload(from_name="Backlog", to_name="Plan")
    )
    assert json.loads(resp.body)["ignored"] == "skip_label"
    assert not gh.dispatched


@pytest.mark.asyncio
async def test_leave_doit_cancels_then_plan(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    gh.runs = [
        {
            "id": 555,
            "status": "in_progress",
            "name": "agent doit #42",
            "display_title": "agent doit #42",
            "html_url": "https://github.com/acme/app/actions/runs/555",
        }
    ]
    gh.labels.add("agent:running")
    resp = await _post_webhook(
        svc, "projects_v2_item", _project_edited_payload(from_name="DoIt", to_name="Plan")
    )
    assert resp.status == 200
    assert 555 in gh.cancelled
    assert any("Stopped" in c for c in gh.comments)
    assert gh.dispatched
    assert gh.dispatched[0]["workflow"] == "kanbanauts.yml"


@pytest.mark.asyncio
async def test_bad_column_name_comments(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    gh.field_options = ["Todo", "Doing", "Done"]  # missing Plan etc.
    resp = await _post_webhook(
        svc, "projects_v2_item", _project_edited_payload(from_name="Todo", to_name="Plan")
    )
    assert resp.status == 200
    assert any("config error" in c for c in gh.comments)
    assert not gh.dispatched


@pytest.mark.asyncio
async def test_no_config_ignored(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    gh.config_text = ""  # get_repo_file returns "" which fails yaml — use None path
    gh.config_text = None  # type: ignore[assignment]

    async def no_file(*args: Any, **kwargs: Any) -> None:
        return None

    gh.get_repo_file = no_file  # type: ignore[method-assign]
    resp = await _post_webhook(
        svc, "projects_v2_item", _project_edited_payload(from_name="Backlog", to_name="Plan")
    )
    assert json.loads(resp.body)["ignored"] == "no_config"


@pytest.mark.asyncio
async def test_workflow_run_intentional_cancel(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    gh.current_column = "Backlog"  # left DoIt
    payload = {
        "action": "completed",
        "installation": {"id": 99},
        "repository": {"name": "app", "owner": {"login": "acme"}},
        "workflow_run": {
            "conclusion": "cancelled",
            "name": "agent doit #42",
            "display_title": "agent doit #42",
            "html_url": "https://example/run/1",
        },
    }
    resp = await _post_webhook(svc, "workflow_run", payload)
    assert json.loads(resp.body).get("ignored") == "intentional_cancel"
    assert "agent:failed" not in gh.labels


@pytest.mark.asyncio
async def test_workflow_run_real_failure(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    gh.current_column = "DoIt"
    payload = {
        "action": "completed",
        "installation": {"id": 99},
        "repository": {"name": "app", "owner": {"login": "acme"}},
        "workflow_run": {
            "conclusion": "failure",
            "name": "agent doit #42",
            "display_title": "agent doit #42",
            "html_url": "https://example/run/2",
        },
    }
    resp = await _post_webhook(svc, "workflow_run", payload)
    assert json.loads(resp.body).get("marked") == "failed"
    assert "agent:failed" in gh.labels


@pytest.mark.asyncio
async def test_report_no_code(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    from tests.helpers_oidc import make_oidc_token

    svc, gh, key = service
    _install_client(svc)
    oidc = make_oidc_token(key, aud=svc.settings.oidc_audience)
    body = json.dumps(
        {
            "status": "no_code",
            "phase": "plan",
            "issue_number": 42,
            "oidc_token": oidc,
            # Spoofed body fields must be ignored
            "owner": "evil",
            "repo": "other",
            "installation_id": 1,
        }
    ).encode()
    req = HttpRequest(
        method="POST",
        path="/report",
        headers={},
        body=body,
    )
    resp = await svc.handle_http(req)
    assert resp.status == 200
    assert "agent:succeeded" in gh.labels
    # on_no_code moves to Done
    assert "Done" in gh.moved_to or gh.moved_to == ["Done"] or "Done" in gh.moved_to


@pytest.mark.asyncio
async def test_report_rejects_missing_oidc(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, _gh, _key = service
    body = json.dumps(
        {"status": "no_code", "phase": "plan", "issue_number": 42}
    ).encode()
    req = HttpRequest(
        method="POST",
        path="/report",
        headers={},
        body=body,
    )
    resp = await svc.handle_http(req)
    assert resp.status == 401


@pytest.mark.asyncio
async def test_report_rejects_fake_bearer(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, _gh, _key = service
    body = json.dumps(
        {"status": "no_code", "phase": "plan", "issue_number": 42}
    ).encode()
    req = HttpRequest(
        method="POST",
        path="/report",
        headers={"Authorization": "Bearer x"},
        body=body,
    )
    resp = await svc.handle_http(req)
    assert resp.status == 403


@pytest.mark.asyncio
async def test_report_rejects_other_repo_token(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    from tests.helpers_oidc import make_oidc_token

    svc, _gh, key = service
    _install_client(svc)
    oidc = make_oidc_token(
        key,
        aud=svc.settings.oidc_audience,
        repository="other/repo",
        repository_owner_id="99999",
    )
    body = json.dumps(
        {
            "status": "succeeded",
            "phase": "plan",
            "issue_number": 42,
            "oidc_token": oidc,
        }
    ).encode()
    req = HttpRequest(method="POST", path="/report", headers={}, body=body)
    resp = await svc.handle_http(req)
    assert resp.status == 403


@pytest.mark.asyncio
async def test_issue_comment_plan(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    payload = {
        "action": "created",
        "installation": {"id": 99},
        "repository": {"name": "app", "owner": {"login": "acme"}},
        "issue": {"number": 42, "labels": []},
        "comment": {
            "id": 9001,
            "body": "/agent plan",
            "user": {"login": "alice", "type": "User"},
        },
    }
    resp = await _post_webhook(svc, "issue_comment", payload)
    assert resp.status == 200
    assert gh.dispatched
    assert gh.dispatched[0]["workflow"] == "kanbanauts.yml"
    assert gh.dispatched[0]["inputs"]["phase"] == "plan"
    assert gh.dispatched[0]["inputs"]["source"] == "command"
    assert gh.reactions and gh.reactions[0]["content"] == "eyes"


@pytest.mark.asyncio
async def test_issue_comment_ai_prefix_no_board(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    gh.config_text = """
version: 1
command_prefix: /agent
mode: opt_out
skip_label: agent:skip
columns: {}
"""
    payload = {
        "action": "created",
        "installation": {"id": 99},
        "repository": {"name": "app", "owner": {"login": "acme"}},
        "issue": {"number": 7, "labels": []},
        "comment": {
            "id": 1,
            "body": "/ai review",
            "user": {"login": "alice", "type": "User"},
        },
    }
    resp = await _post_webhook(svc, "issue_comment", payload)
    assert resp.status == 200
    assert gh.dispatched
    assert gh.dispatched[0]["inputs"] == {
        "issue_number": "7",
        "phase": "review",
        "source": "command",
    }


@pytest.mark.asyncio
async def test_issue_comment_bot_ignored(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    payload = {
        "action": "created",
        "installation": {"id": 99},
        "repository": {"name": "app", "owner": {"login": "acme"}},
        "issue": {"number": 42, "labels": []},
        "comment": {
            "id": 1,
            "body": "/ai plan",
            "user": {"login": "kanbanauts[bot]", "type": "Bot"},
        },
    }
    resp = await _post_webhook(svc, "issue_comment", payload)
    assert json.loads(resp.body)["ignored"] == "bot"
    assert not gh.dispatched


@pytest.mark.asyncio
async def test_issue_comment_readonly_refused(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    gh.permission = "read"
    payload = {
        "action": "created",
        "installation": {"id": 99},
        "repository": {"name": "app", "owner": {"login": "acme"}},
        "issue": {"number": 42, "labels": []},
        "comment": {
            "id": 1,
            "body": "/ai plan",
            "user": {"login": "bob", "type": "User"},
        },
    }
    resp = await _post_webhook(svc, "issue_comment", payload)
    assert json.loads(resp.body)["error"] == "forbidden"
    assert not gh.dispatched
    assert any("write access" in c for c in gh.comments)


@pytest.mark.asyncio
async def test_issue_comment_skip_label_blocks(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    gh.labels.add("agent:skip")
    payload = {
        "action": "created",
        "installation": {"id": 99},
        "repository": {"name": "app", "owner": {"login": "acme"}},
        "issue": {"number": 42, "labels": [{"name": "agent:skip"}]},
        "comment": {
            "id": 1,
            "body": "/ai plan",
            "user": {"login": "alice", "type": "User"},
        },
    }
    resp = await _post_webhook(svc, "issue_comment", payload)
    assert json.loads(resp.body)["ignored"] == "skip_label"
    assert not gh.dispatched
    assert not gh.reactions


@pytest.mark.asyncio
async def test_issue_comment_plan_on_pr_refused(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    payload = {
        "action": "created",
        "installation": {"id": 99},
        "repository": {"name": "app", "owner": {"login": "acme"}},
        "issue": {"number": 99, "labels": [], "pull_request": {"url": "https://x"}},
        "comment": {
            "id": 1,
            "body": "/ai plan",
            "user": {"login": "alice", "type": "User"},
        },
    }
    resp = await _post_webhook(svc, "issue_comment", payload)
    assert json.loads(resp.body)["error"] == "use_issue"
    assert not gh.dispatched
    assert not gh.reactions
    assert any("issue" in c.casefold() for c in gh.comments)


@pytest.mark.asyncio
async def test_preflight_command_skips_column_check(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    from tests.helpers_oidc import make_oidc_token

    import time

    from kanbanauts.core.grants import make_grant_comment

    svc, gh, key = service
    _install_client(svc)
    gh.current_column = "Backlog"
    gh.comments.append(
        make_grant_comment(
            secret="s3cret",
            owner="acme",
            repo="app",
            issue_number=42,
            phase="plan",
            now=time.time(),
        )
    )
    oidc = make_oidc_token(key, aud=svc.settings.oidc_audience)
    req = HttpRequest(
        method="GET",
        path="/preflight",
        headers={"Authorization": f"Bearer {oidc}"},
        body=b"",
        query={"issue": "42", "phase": "plan", "source": "command"},
    )
    resp = await svc.handle_http(req)
    assert resp.status == 200
    data = json.loads(resp.body)
    assert data["skip"] is False
    assert "agent:running" in gh.labels


@pytest.mark.asyncio
async def test_preflight_board_column_mismatch(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    from tests.helpers_oidc import make_oidc_token

    svc, gh, key = service
    _install_client(svc)
    gh.current_column = "Backlog"
    oidc = make_oidc_token(key, aud=svc.settings.oidc_audience)
    req = HttpRequest(
        method="GET",
        path="/preflight",
        headers={"Authorization": f"Bearer {oidc}"},
        body=b"",
        query={"issue": "42", "phase": "plan", "source": "board"},
    )
    resp = await svc.handle_http(req)
    assert resp.status == 200
    data = json.loads(resp.body)
    assert data["skip"] is True
    assert data["reason"] == "column_mismatch"


@pytest.mark.asyncio
async def test_report_succeeded_without_board_item(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    from tests.helpers_oidc import make_oidc_token

    svc, gh, key = service
    _install_client(svc)
    gh.project_items = []  # issue not on board
    oidc = make_oidc_token(key, aud=svc.settings.oidc_audience)
    body = json.dumps(
        {
            "status": "succeeded",
            "phase": "doit",
            "issue_number": 42,
            "oidc_token": oidc,
        }
    ).encode()
    req = HttpRequest(method="POST", path="/report", headers={}, body=body)
    resp = await svc.handle_http(req)
    assert resp.status == 200
    assert "agent:succeeded" in gh.labels
    assert gh.moved_to == []


@pytest.mark.asyncio
async def test_preflight_command_without_grant_skips(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    from tests.helpers_oidc import make_oidc_token

    svc, gh, key = service
    _install_client(svc)
    gh.current_column = "Plan"
    oidc = make_oidc_token(key, aud=svc.settings.oidc_audience)
    req = HttpRequest(
        method="GET",
        path="/preflight",
        headers={"Authorization": f"Bearer {oidc}"},
        body=b"",
        query={"issue": "42", "phase": "plan", "source": "command"},
    )
    resp = await svc.handle_http(req)
    data = json.loads(resp.body)
    assert data["skip"] is True
    assert data["reason"] == "no_command_grant"
    assert "agent:running" not in gh.labels


@pytest.mark.asyncio
async def test_preflight_command_skip_label(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    import time

    from kanbanauts.core.grants import make_grant_comment
    from tests.helpers_oidc import make_oidc_token

    svc, gh, key = service
    _install_client(svc)
    gh.labels.add("agent:skip")
    gh.comments.append(
        make_grant_comment(
            secret="s3cret",
            owner="acme",
            repo="app",
            issue_number=42,
            phase="doit",
            now=time.time(),
        )
    )
    oidc = make_oidc_token(key, aud=svc.settings.oidc_audience)
    req = HttpRequest(
        method="GET",
        path="/preflight",
        headers={"Authorization": f"Bearer {oidc}"},
        body=b"",
        query={"issue": "42", "phase": "doit", "source": "command"},
    )
    resp = await svc.handle_http(req)
    data = json.loads(resp.body)
    assert data["skip"] is True
    assert data["reason"] == "skip_label"


@pytest.mark.asyncio
async def test_issue_comment_review_on_pr_uses_linked_issue(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    payload = {
        "action": "created",
        "installation": {"id": 99},
        "repository": {"name": "app", "owner": {"login": "acme"}},
        "issue": {
            "number": 99,
            "labels": [],
            "body": "Closes #42",
            "pull_request": {"url": "https://x"},
        },
        "comment": {
            "id": 7,
            "body": "/ai review",
            "user": {"login": "alice", "type": "User"},
        },
    }
    resp = await _post_webhook(svc, "issue_comment", payload)
    assert resp.status == 200
    assert gh.dispatched
    assert gh.dispatched[0]["inputs"]["issue_number"] == "42"
    assert gh.dispatched[0]["inputs"]["phase"] == "review"
    assert gh.dispatched[0]["inputs"]["source"] == "command"
    assert gh.reactions[0]["comment_id"] == 7
    assert any("kanbanauts:grant" in c and "phase=review" in c for c in gh.comments)


@pytest.mark.asyncio
async def test_caller_v5_omits_source(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    gh.caller_text = "# kanbanauts-caller: 5\non:\n  workflow_dispatch:\n"
    payload = {
        "action": "created",
        "installation": {"id": 99},
        "repository": {"name": "app", "owner": {"login": "acme"}},
        "issue": {"number": 42, "labels": []},
        "comment": {
            "id": 1,
            "body": "/ai plan",
            "user": {"login": "alice", "type": "User"},
        },
    }
    resp = await _post_webhook(svc, "issue_comment", payload)
    assert json.loads(resp.body)["ok"] is True
    assert "source" not in gh.dispatched[0]["inputs"]
    assert gh.dispatched[0]["inputs"]["phase"] == "plan"


@pytest.mark.asyncio
async def test_dispatch_failure_clears_queued_label(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    gh.dispatch_error = RuntimeError("422 Unexpected inputs")
    resp = await _post_webhook(
        svc, "projects_v2_item", _project_edited_payload(from_name="Backlog", to_name="Plan")
    )
    assert json.loads(resp.body)["error"] == "dispatch_failed"
    assert "agent:queued" not in gh.labels
    assert any("could not start" in c for c in gh.comments)


@pytest.mark.asyncio
async def test_report_no_code_does_not_move_from_other_column(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    from tests.helpers_oidc import make_oidc_token

    svc, gh, key = service
    _install_client(svc)
    gh.current_column = "Review"
    oidc = make_oidc_token(key, aud=svc.settings.oidc_audience)
    body = json.dumps(
        {"status": "no_code", "phase": "plan", "issue_number": 42, "oidc_token": oidc}
    ).encode()
    req = HttpRequest(method="POST", path="/report", headers={}, body=body)
    resp = await svc.handle_http(req)
    assert resp.status == 200
    assert "agent:succeeded" in gh.labels
    assert gh.moved_to == []


@pytest.mark.asyncio
async def test_report_doit_does_not_move_from_done(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    from tests.helpers_oidc import make_oidc_token

    svc, gh, key = service
    _install_client(svc)
    gh.current_column = "Done"
    oidc = make_oidc_token(key, aud=svc.settings.oidc_audience)
    body = json.dumps(
        {"status": "succeeded", "phase": "doit", "issue_number": 42, "oidc_token": oidc}
    ).encode()
    req = HttpRequest(method="POST", path="/report", headers={}, body=body)
    resp = await svc.handle_http(req)
    assert resp.status == 200
    assert gh.moved_to == []


@pytest.mark.asyncio
async def test_report_doit_moves_user_project_when_in_column(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    from tests.helpers_oidc import make_oidc_token

    svc, gh, key = service
    _install_client(svc)
    gh.config_text = SAMPLE_CONFIG.replace(
        "https://github.com/orgs/acme/projects/7",
        "https://github.com/users/acme/projects/7",
    )
    gh.current_column = "DoIt"
    oidc = make_oidc_token(key, aud=svc.settings.oidc_audience)
    body = json.dumps(
        {"status": "succeeded", "phase": "doit", "issue_number": 42, "oidc_token": oidc}
    ).encode()
    req = HttpRequest(method="POST", path="/report", headers={}, body=body)
    resp = await svc.handle_http(req)
    assert resp.status == 200
    assert gh.moved_to == ["Review"]


@pytest.mark.asyncio
async def test_enter_review_dispatches_review(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    gh.config_text = SAMPLE_CONFIG.replace(
        "  Review:\n    on_pr_approved: { move_to: Tests }",
        "  Review:\n"
        "    on_enter: [{ run: review }]\n"
        "    on_leave: [{ cancel: true }]\n"
        "    on_pr_approved: { move_to: Tests }",
    )
    resp = await _post_webhook(
        svc, "projects_v2_item", _project_edited_payload(from_name="DoIt", to_name="Review")
    )
    assert resp.status == 200
    assert gh.dispatched
    assert gh.dispatched[0]["inputs"]["phase"] == "review"
    assert gh.dispatched[0]["inputs"]["source"] == "board"


@pytest.mark.asyncio
async def test_leave_review_without_run_stays_quiet(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    gh.config_text = SAMPLE_CONFIG.replace(
        "  Review:\n    on_pr_approved: { move_to: Tests }",
        "  Review:\n"
        "    on_enter: [{ run: review }]\n"
        "    on_leave: [{ cancel: true }]\n"
        "    on_pr_approved: { move_to: Tests }",
    )
    gh.labels.add("agent:succeeded")
    resp = await _post_webhook(
        svc, "projects_v2_item", _project_edited_payload(from_name="Review", to_name="Tests")
    )
    assert resp.status == 200
    assert not gh.cancelled
    assert not any("Stopped" in c for c in gh.comments)
    assert "agent:succeeded" in gh.labels
    assert not gh.dispatched


@pytest.mark.asyncio
async def test_cancelled_command_run_off_column_marks_failed(
    service: tuple[KanbanautsService, FakeGitHub, Any],
) -> None:
    svc, gh, _key = service
    gh.current_column = "Backlog"
    gh.labels.add("agent:running")
    payload = {
        "action": "completed",
        "installation": {"id": 99},
        "repository": {"name": "app", "owner": {"login": "acme"}},
        "workflow_run": {
            "conclusion": "cancelled",
            "name": "agent plan #42",
            "display_title": "agent plan #42",
            "html_url": "https://example/run/9",
        },
    }
    resp = await _post_webhook(svc, "workflow_run", payload)
    assert json.loads(resp.body).get("marked") == "failed"
    assert "agent:running" not in gh.labels
    assert "agent:failed" in gh.labels


def test_config_loads() -> None:
    cfg = load_config_yaml(SAMPLE_CONFIG)
    assert cfg.phase_for_run("plan") is not None
