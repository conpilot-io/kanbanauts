"""HMAC webhook verification and event routing."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from kanbanauts.core.ports import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)

EventHandler = Callable[[str, dict[str, Any], Mapping[str, str]], Awaitable[HttpResponse]]


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """Verify ``X-Hub-Signature-256: sha256=<hex>``."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = signature_header.removeprefix("sha256=")
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, expected)


@dataclass(slots=True)
class WebhookRouter:
    secret: str
    handlers: dict[str, EventHandler]

    async def handle(self, request: HttpRequest) -> HttpResponse:
        headers = {k.lower(): v for k, v in request.headers.items()}
        signature = headers.get("x-hub-signature-256")
        if not verify_signature(self.secret, request.body, signature):
            return HttpResponse.text(401, "invalid signature")

        event = headers.get("x-github-event", "")
        if event == "ping":
            return HttpResponse.json(200, {"ok": True, "pong": True})

        try:
            payload: dict[str, Any] = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return HttpResponse.text(400, "invalid json")

        handler = self.handlers.get(event)
        if handler is None:
            logger.info("Ignoring unhandled event %s", event)
            return HttpResponse.json(200, {"ok": True, "ignored": event})

        delivery = headers.get("x-github-delivery", "")
        logger.info("Handling %s delivery=%s", event, delivery)
        return await handler(event, payload, headers)
