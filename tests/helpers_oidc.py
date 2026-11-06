"""Shared helpers to mint test OIDC JWTs."""

from __future__ import annotations

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWKClient


def rsa_keypair() -> Any:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJwkClient(PyJWKClient):
    def __init__(self, private_key: Any) -> None:
        self._private_key = private_key

    def get_signing_key_from_jwt(self, token: str) -> Any:  # type: ignore[override]
        class _Key:
            def __init__(self, key: Any) -> None:
                self.key = key.public_key()

        return _Key(self._private_key)


def make_oidc_token(
    private_key: Any,
    *,
    aud: str,
    repository: str = "acme/app",
    repository_owner_id: str = "12345",
    ref: str = "refs/heads/main",
    workflow_ref: str = (
        "acme/app/.github/workflows/kanbanauts.yml@refs/heads/main"
    ),
    job_workflow_ref: str = (
        "conpilot-io/kanbanauts/.github/workflows/"
        "agent-plan-claude.lock.yml@refs/tags/v1"
    ),
    extra: dict[str, Any] | None = None,
    exp_offset: int = 300,
) -> str:
    now = int(time.time())
    owner = repository.split("/", 1)[0]
    payload: dict[str, Any] = {
        "iss": "https://token.actions.githubusercontent.com",
        "aud": aud,
        "sub": f"repo:{repository}:ref:{ref}",
        "iat": now,
        "exp": now + exp_offset,
        "repository": repository,
        "repository_owner": owner,
        "repository_owner_id": repository_owner_id,
        "repository_id": "999",
        "ref": ref,
        "workflow_ref": workflow_ref,
        "job_workflow_ref": job_workflow_ref,
        "workflow": "Kanbanauts",
        "run_id": "1",
        "actor": "octocat",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, private_key, algorithm="RS256")
