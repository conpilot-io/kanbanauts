from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from kanbanauts.core.ports import HttpRequest, HttpResponse
from kanbanauts.core.webhook import WebhookRouter, verify_signature


def _sig(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_verify_signature_ok() -> None:
    body = b'{"ok":true}'
    assert verify_signature("s3cret", body, _sig("s3cret", body))


def test_verify_signature_bad() -> None:
    body = b'{"ok":true}'
    assert not verify_signature("s3cret", body, _sig("other", body))
    assert not verify_signature("s3cret", body, None)


@pytest.mark.asyncio
async def test_router_ping() -> None:
    router = WebhookRouter(secret="s3cret", handlers={})
    body = b"{}"
    req = HttpRequest(
        method="POST",
        path="/webhook",
        headers={
            "x-hub-signature-256": _sig("s3cret", body),
            "x-github-event": "ping",
        },
        body=body,
    )
    resp = await router.handle(req)
    assert resp.status == 200
    assert json.loads(resp.body)["pong"] is True


@pytest.mark.asyncio
async def test_router_rejects_bad_sig() -> None:
    router = WebhookRouter(secret="s3cret", handlers={})
    req = HttpRequest(
        method="POST",
        path="/webhook",
        headers={"x-hub-signature-256": "sha256=dead", "x-github-event": "ping"},
        body=b"{}",
    )
    resp = await router.handle(req)
    assert resp.status == 401


@pytest.mark.asyncio
async def test_router_dispatches() -> None:
    seen: list[str] = []

    async def handler(event: str, payload: dict, headers: dict) -> HttpResponse:
        seen.append(event)
        return HttpResponse.json(200, {"handled": True})

    router = WebhookRouter(secret="s3cret", handlers={"issue_comment": handler})
    body = b'{"action":"created"}'
    req = HttpRequest(
        method="POST",
        path="/webhook",
        headers={
            "x-hub-signature-256": _sig("s3cret", body),
            "x-github-event": "issue_comment",
        },
        body=body,
    )
    resp = await router.handle(req)
    assert resp.status == 200
    assert seen == ["issue_comment"]
