from __future__ import annotations

import time

from kanbanauts.core.grants import (
    GRANT_TTL_SECONDS,
    grant_comment_allows,
    make_grant_comment,
)


def test_grant_allows_matching_comment() -> None:
    now = time.time()
    body = make_grant_comment(
        secret="s3cret",
        owner="Acme",
        repo="App",
        issue_number=42,
        phase="plan",
        now=now,
    )
    assert grant_comment_allows(
        secret="s3cret",
        owner="acme",
        repo="app",
        issue_number=42,
        phase="plan",
        comments=[body],
        now=now + 10,
    )


def test_grant_rejects_other_phase_issue_and_expiry() -> None:
    now = time.time()
    body = make_grant_comment(
        secret="s3cret",
        owner="acme",
        repo="app",
        issue_number=42,
        phase="plan",
        now=now,
    )
    assert not grant_comment_allows(
        secret="s3cret",
        owner="acme",
        repo="app",
        issue_number=42,
        phase="doit",
        comments=[body],
        now=now,
    )
    assert not grant_comment_allows(
        secret="s3cret",
        owner="acme",
        repo="app",
        issue_number=7,
        phase="plan",
        comments=[body],
        now=now,
    )
    assert not grant_comment_allows(
        secret="s3cret",
        owner="acme",
        repo="app",
        issue_number=42,
        phase="plan",
        comments=[body],
        now=now + GRANT_TTL_SECONDS + 5,
    )
    tampered = body.replace("phase=plan", "phase=doit")
    assert not grant_comment_allows(
        secret="s3cret",
        owner="acme",
        repo="app",
        issue_number=42,
        phase="doit",
        comments=[tampered],
        now=now,
    )
