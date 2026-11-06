"""OIDC token broker — exchange Actions OIDC for a short-lived App token."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from kanbanauts.core.config import default_branch_ref_ok

logger = logging.getLogger(__name__)

GITHUB_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
GITHUB_OIDC_JWKS = f"{GITHUB_OIDC_ISSUER}/.well-known/jwks"

# Reusable agent workflows live in the public central repo. For workflow_call
# jobs, GitHub sets job_workflow_ref to the callee path.
CENTRAL_AGENT_WORKFLOW_PREFIX = (
    "conpilot-io/kanbanauts/.github/workflows/agent-"
)
_AGENT_LOCK_RE = re.compile(r"^agent-.+\.lock\.yml$")

# Vendor release workflow allowed to call /admin/rollout.
CENTRAL_RELEASE_WORKFLOW_PREFIX = (
    "conpilot-io/kanbanauts/.github/workflows/release.yml@"
)


@dataclass(slots=True)
class OidcClaims:
    sub: str
    aud: str | list[str]
    iss: str
    repository: str
    repository_owner: str
    repository_owner_id: str
    repository_id: str
    ref: str
    workflow_ref: str
    workflow: str
    run_id: str
    actor: str
    job_workflow_ref: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def owner(self) -> str:
        return self.repository.split("/", 1)[0]

    @property
    def repo(self) -> str:
        return self.repository.split("/", 1)[1]

    @property
    def effective_job_workflow_ref(self) -> str:
        """Prefer job_workflow_ref (callee); fall back to workflow_ref."""
        return self.job_workflow_ref or self.workflow_ref


class OidcError(Exception):
    """OIDC verification or authorization failed."""


def is_central_agent_workflow_ref(workflow_ref: str) -> bool:
    """True when the ref is a central Kanbanauts agent-*.lock.yml workflow."""
    if not workflow_ref.startswith(CENTRAL_AGENT_WORKFLOW_PREFIX):
        return False
    path = workflow_ref.split("@", 1)[0]
    name = path.rsplit("/", 1)[-1]
    return bool(_AGENT_LOCK_RE.match(name))


def is_central_release_workflow_ref(workflow_ref: str) -> bool:
    return workflow_ref.startswith(CENTRAL_RELEASE_WORKFLOW_PREFIX) or (
        workflow_ref.split("@", 1)[0]
        == "conpilot-io/kanbanauts/.github/workflows/release.yml"
    )


@dataclass(slots=True)
class TokenBroker:
    """
    Verify GitHub Actions OIDC JWTs and mint repo-scoped App installation tokens.

    ``jwks_client`` can be injected for tests (fake JWKS).
    """

    expected_audience: str
    jwks_url: str = GITHUB_OIDC_JWKS
    issuer: str = GITHUB_OIDC_ISSUER
    jwks_client: PyJWKClient | None = None
    _jwks: PyJWKClient | None = field(default=None, init=False, repr=False)

    def _client(self) -> PyJWKClient:
        if self.jwks_client is not None:
            return self.jwks_client
        if self._jwks is None:
            self._jwks = PyJWKClient(self.jwks_url)
        return self._jwks

    def verify_oidc(self, token: str, *, now: int | None = None) -> OidcClaims:
        try:
            signing_key = self._client().get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.expected_audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise OidcError(f"OIDC verification failed: {exc}") from exc

        # Optional clock skew check already handled by PyJWT; expose now for tests.
        if now is not None and int(payload.get("exp", 0)) < now:
            raise OidcError("OIDC token expired")

        def req(key: str) -> str:
            value = payload.get(key)
            if value is None or value == "":
                raise OidcError(f"OIDC claim missing: {key}")
            return str(value)

        job_ref = str(payload.get("job_workflow_ref") or "")
        return OidcClaims(
            sub=req("sub"),
            aud=payload["aud"],
            iss=req("iss"),
            repository=req("repository"),
            repository_owner=req("repository_owner"),
            repository_owner_id=req("repository_owner_id"),
            repository_id=req("repository_id"),
            ref=req("ref"),
            workflow_ref=req("workflow_ref"),
            workflow=req("workflow"),
            run_id=str(payload.get("run_id", "")),
            actor=str(payload.get("actor", "")),
            job_workflow_ref=job_ref,
            raw=dict(payload),
        )

    def authorize(
        self,
        claims: OidcClaims,
        *,
        default_branch: str,
        installation_owner_id: str | int,
    ) -> None:
        if str(claims.repository_owner_id) != str(installation_owner_id):
            raise OidcError("repository_owner_id does not match installation")
        if not default_branch_ref_ok(claims.ref, default_branch):
            raise OidcError(
                f"ref {claims.ref!r} is not the default branch {default_branch!r}"
            )
        job_ref = claims.effective_job_workflow_ref
        if not is_central_agent_workflow_ref(job_ref):
            raise OidcError(
                f"job_workflow_ref {job_ref!r} is not a central "
                "conpilot-io/kanbanauts agent-*.lock.yml workflow"
            )

    def authorize_release(self, claims: OidcClaims) -> None:
        """Authorize the vendor release.yml workflow for /admin/rollout."""
        if claims.repository != "conpilot-io/kanbanauts":
            raise OidcError("release caller must be conpilot-io/kanbanauts")
        ref = claims.effective_job_workflow_ref
        if not is_central_release_workflow_ref(ref):
            raise OidcError(
                f"workflow_ref {ref!r} is not the central release.yml workflow"
            )


# Limited permissions for broker-minted tokens (no workflows permission).
BROKER_PERMISSIONS: dict[str, str] = {
    "actions": "write",
    "contents": "write",
    "issues": "write",
    "pull_requests": "write",
    "metadata": "read",
    "checks": "read",
}

# Permissions for onboarding / rollout PRs that edit workflow files.
ONBOARDING_PERMISSIONS: dict[str, str] = {
    "contents": "write",
    "pull_requests": "write",
    "issues": "write",
    "workflows": "write",
    "metadata": "read",
}


@dataclass(slots=True)
class InstallationResolver:
    """Resolve installation id for an org/user from App API."""

    app_jwt_fn: Any  # callable returning JWT
    http: httpx.AsyncClient

    async def installation_for_owner(self, owner: str) -> dict[str, Any]:
        # Try org first, then user.
        for path in (f"/orgs/{owner}/installation", f"/users/{owner}/installation"):
            response = await self.http.get(
                path,
                headers={
                    "Authorization": f"Bearer {self.app_jwt_fn()}",
                    "Accept": "application/vnd.github+json",
                },
            )
            if response.status_code == 404:
                continue
            response.raise_for_status()
            data = response.json()
            assert isinstance(data, dict)
            return data
        raise OidcError(f"No App installation for owner {owner}")


def mint_now() -> int:
    return int(time.time())
