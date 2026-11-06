"""Rollout must refuse to run when the deployed function is older than the release."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from kanbanauts.core.caller import CALLER_VERSION
from kanbanauts.core.ports import HttpRequest
from kanbanauts.core.rollout import RolloutService, StaleDeploymentError
from kanbanauts.core.service import KanbanautsService

from tests.helpers_oidc import make_oidc_token
from tests.integration.test_lifecycle import FakeGitHub, service  # noqa: F401
from tests.integration.test_onboarding import FakeOnboardGitHub

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_REF = "conpilot-io/kanbanauts/.github/workflows/release.yml@refs/tags/v1.0.5"


def _rollout_request(
    key: Any, aud: str, *, caller_version: int
) -> HttpRequest:
    token = make_oidc_token(
        key,
        aud=aud,
        repository="conpilot-io/kanbanauts",
        workflow_ref=RELEASE_REF,
        job_workflow_ref=RELEASE_REF,
    )
    body = json.dumps(
        {"oidc_token": token, "caller_version": caller_version, "dry_run": True}
    ).encode()
    return HttpRequest(
        method="POST", path="/admin/rollout", headers={}, body=body
    )


@pytest.mark.asyncio
async def test_rollout_service_rejects_newer_version_than_deployed() -> None:
    gh = FakeOnboardGitHub()
    svc = RolloutService(github=gh)  # type: ignore[arg-type]
    with pytest.raises(StaleDeploymentError, match="publish-function"):
        await svc.run(caller_version=CALLER_VERSION + 1, dry_run=False)
    assert gh.put_calls == []
    assert gh.prs == []


@pytest.mark.asyncio
async def test_rollout_http_returns_409_when_function_is_stale(
    service: tuple[KanbanautsService, FakeGitHub, Any],  # noqa: F811
) -> None:
    svc, _gh, key = service
    aud = svc.settings.oidc_audience
    resp = await svc.handle_http(
        _rollout_request(key, aud, caller_version=CALLER_VERSION + 1)
    )
    assert resp.status == 409
    payload = json.loads(resp.body)
    assert payload["ok"] is False
    assert "publish-function" in payload["error"]


def test_release_workflow_fails_on_rollout_http_error() -> None:
    """Without --fail-with-body, curl exits 0 on HTTP 409 and the release looks green."""
    text = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    assert "--fail-with-body" in text
    assert "/admin/rollout" in text


def test_vendor_ops_documents_publish_before_tag() -> None:
    text = (REPO_ROOT / "docs" / "VENDOR_OPS.md").read_text(encoding="utf-8")
    publish = text.index("publish-function.sh kanbanauts-fn", text.index("Release checklist"))
    tag = text.index("git tag vX.Y.Z", text.index("Release checklist"))
    assert publish < tag
