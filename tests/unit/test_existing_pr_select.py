"""Unit tests for the DoIt existing-PR selection jq block."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKOUT_MD = (
    REPO_ROOT
    / ".github"
    / "workflows"
    / "shared"
    / "kanban-checkout-existing-pr.md"
)

_SELECT_MARKER = re.compile(
    r"# BEGIN kanban-select-existing-pr\n(.*?)\n\s*# END kanban-select-existing-pr",
    re.DOTALL,
)
_JQ_PROGRAM = re.compile(
    r"jq -c --argjson issue \"\$\{ISSUE\}\" '(.+?)'\s*\)",
    re.DOTALL,
)


def _select_jq() -> str:
    text = CHECKOUT_MD.read_text(encoding="utf-8")
    match = _SELECT_MARKER.search(text)
    assert match, "kanban-select-existing-pr block missing"
    jq_match = _JQ_PROGRAM.search(match.group(1))
    assert jq_match, "jq program missing from selection block"
    return jq_match.group(1)


def _select(prs: list[dict[str, Any]], issue: int) -> dict[str, Any]:
    program = _select_jq()
    result = subprocess.run(
        ["jq", "-c", "--argjson", "issue", str(issue), program],
        input=json.dumps(prs),
        check=True,
        capture_output=True,
        text=True,
    )
    parsed: object = json.loads(result.stdout)
    assert isinstance(parsed, dict)
    return parsed


def _pr(
    number: int,
    *,
    body: str,
    updated_at: str,
    head_repo: str = "acme/app",
    base_repo: str = "acme/app",
    state: str = "open",
    ref: str = "feature",
    sha: str = "abc123",
) -> dict[str, Any]:
    return {
        "number": number,
        "state": state,
        "body": body,
        "updated_at": updated_at,
        "head": {
            "ref": ref,
            "sha": sha,
            "repo": {"full_name": head_repo},
        },
        "base": {
            "ref": "main",
            "repo": {"full_name": base_repo},
        },
    }


def test_select_none() -> None:
    out = _select([], 42)
    assert out == {"kind": "none", "pr": None}


def test_select_ignores_non_closing_mention() -> None:
    out = _select(
        [_pr(7, body="See issue #42 for context", updated_at="2026-01-02T00:00:00Z")],
        42,
    )
    assert out["kind"] == "none"


def test_select_one_same_repo() -> None:
    out = _select(
        [_pr(12, body="Closes #42", updated_at="2026-01-02T00:00:00Z")],
        42,
    )
    assert out["kind"] == "same_repo"
    assert out["pr"]["number"] == 12


def test_select_newest_of_two() -> None:
    out = _select(
        [
            _pr(10, body="Fixes #42", updated_at="2026-01-01T00:00:00Z"),
            _pr(11, body="Resolves #42", updated_at="2026-01-03T00:00:00Z"),
        ],
        42,
    )
    assert out["kind"] == "same_repo"
    assert out["pr"]["number"] == 11


def test_select_fork_only() -> None:
    out = _select(
        [
            _pr(
                9,
                body="Closes #42",
                updated_at="2026-01-02T00:00:00Z",
                head_repo="contributor/app",
                base_repo="acme/app",
            )
        ],
        42,
    )
    assert out["kind"] == "fork_only"
    assert out["pr"]["number"] == 9


def test_select_prefers_same_repo_over_fork() -> None:
    out = _select(
        [
            _pr(
                8,
                body="Closes #42",
                updated_at="2026-01-04T00:00:00Z",
                head_repo="contributor/app",
                base_repo="acme/app",
            ),
            _pr(7, body="Closes #42", updated_at="2026-01-01T00:00:00Z"),
        ],
        42,
    )
    assert out["kind"] == "same_repo"
    assert out["pr"]["number"] == 7


@pytest.mark.parametrize(
    "body",
    [
        "closes #42",
        "Fixes #42.",
        "This Resolves #42\n",
        "Closes  #42",
    ],
)
def test_select_closing_keywords(body: str) -> None:
    out = _select([_pr(3, body=body, updated_at="2026-01-01T00:00:00Z")], 42)
    assert out["kind"] == "same_repo"
    assert out["pr"]["number"] == 3
