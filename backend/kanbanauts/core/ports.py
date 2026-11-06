"""Hosting ports — hosts implement these interfaces."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class HttpRequest:
    method: str
    path: str
    headers: Mapping[str, str]
    body: bytes
    query: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def json(cls, status: int, payload: Mapping[str, object]) -> HttpResponse:
        import json

        data = json.dumps(payload).encode("utf-8")
        return cls(
            status=status,
            body=data,
            headers={"content-type": "application/json"},
        )

    @classmethod
    def text(cls, status: int, message: str) -> HttpResponse:
        return cls(
            status=status,
            body=message.encode("utf-8"),
            headers={"content-type": "text/plain; charset=utf-8"},
        )


class SecretProvider(Protocol):
    """Provide secrets (App private key, webhook secret, etc.)."""

    def get(self, name: str) -> str: ...
