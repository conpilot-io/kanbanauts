from __future__ import annotations

from typing import Any

import pytest
from kanbanauts.core.broker import (
    BROKER_PERMISSIONS,
    OidcError,
    TokenBroker,
    is_central_agent_workflow_ref,
)

from tests.helpers_oidc import FakeJwkClient, make_oidc_token, rsa_keypair

AUD = "https://kanbanauts.example.com"


@pytest.fixture
def broker_and_key() -> tuple[TokenBroker, Any]:
    key = rsa_keypair()
    broker = TokenBroker(
        expected_audience=AUD,
        jwks_client=FakeJwkClient(key),
    )
    return broker, key


def test_verify_ok(broker_and_key: tuple[TokenBroker, Any]) -> None:
    broker, key = broker_and_key
    token = make_oidc_token(key, aud=AUD)
    claims = broker.verify_oidc(token)
    assert claims.repository == "acme/app"
    assert claims.job_workflow_ref.startswith("conpilot-io/kanbanauts/")
    broker.authorize(claims, default_branch="main", installation_owner_id="12345")


def test_wrong_audience(broker_and_key: tuple[TokenBroker, Any]) -> None:
    broker, key = broker_and_key
    token = make_oidc_token(key, aud="https://evil.example.com")
    with pytest.raises(OidcError):
        broker.verify_oidc(token)


def test_wrong_owner(broker_and_key: tuple[TokenBroker, Any]) -> None:
    broker, key = broker_and_key
    token = make_oidc_token(key, aud=AUD)
    claims = broker.verify_oidc(token)
    with pytest.raises(OidcError, match="repository_owner_id"):
        broker.authorize(claims, default_branch="main", installation_owner_id="999")


def test_wrong_branch(broker_and_key: tuple[TokenBroker, Any]) -> None:
    broker, key = broker_and_key
    token = make_oidc_token(key, aud=AUD, ref="refs/heads/feature")
    claims = broker.verify_oidc(token)
    with pytest.raises(OidcError, match="default branch"):
        broker.authorize(claims, default_branch="main", installation_owner_id="12345")


def test_customer_made_workflow_rejected(broker_and_key: tuple[TokenBroker, Any]) -> None:
    broker, key = broker_and_key
    token = make_oidc_token(
        key,
        aud=AUD,
        job_workflow_ref="acme/app/.github/workflows/agent-plan.lock.yml@refs/heads/main",
    )
    claims = broker.verify_oidc(token)
    with pytest.raises(OidcError, match="central"):
        broker.authorize(claims, default_branch="main", installation_owner_id="12345")


def test_wrong_central_path_rejected(broker_and_key: tuple[TokenBroker, Any]) -> None:
    broker, key = broker_and_key
    token = make_oidc_token(
        key,
        aud=AUD,
        job_workflow_ref=(
            "conpilot-io/kanbanauts/.github/workflows/ci.yml@refs/heads/main"
        ),
    )
    claims = broker.verify_oidc(token)
    with pytest.raises(OidcError, match="central"):
        broker.authorize(claims, default_branch="main", installation_owner_id="12345")


def test_is_central_agent_workflow_ref() -> None:
    assert is_central_agent_workflow_ref(
        "conpilot-io/kanbanauts/.github/workflows/agent-plan-claude.lock.yml@v1"
    )
    assert not is_central_agent_workflow_ref(
        "acme/app/.github/workflows/agent-plan.lock.yml@refs/heads/main"
    )
    assert not is_central_agent_workflow_ref(
        "conpilot-io/kanbanauts/.github/workflows/release.yml@refs/tags/v1.0.0"
    )


def test_broker_permissions_have_no_workflows() -> None:
    assert "workflows" not in BROKER_PERMISSIONS


def test_authorize_release(broker_and_key: tuple[TokenBroker, Any]) -> None:
    broker, key = broker_and_key
    token = make_oidc_token(
        key,
        aud=AUD,
        repository="conpilot-io/kanbanauts",
        workflow_ref=(
            "conpilot-io/kanbanauts/.github/workflows/release.yml@refs/tags/v1.0.0"
        ),
        job_workflow_ref=(
            "conpilot-io/kanbanauts/.github/workflows/release.yml@refs/tags/v1.0.0"
        ),
    )
    claims = broker.verify_oidc(token)
    broker.authorize_release(claims)


def test_authorize_release_rejects_other_repo(
    broker_and_key: tuple[TokenBroker, Any],
) -> None:
    broker, key = broker_and_key
    token = make_oidc_token(key, aud=AUD)
    claims = broker.verify_oidc(token)
    with pytest.raises(OidcError, match="conpilot-io/kanbanauts"):
        broker.authorize_release(claims)
