"""Short-lived proof that the app accepted a comment command.

The workflow `source` input is chosen by the caller. Preflight accepts
`source=command` only when the issue has a matching grant comment.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import UTC, datetime, timedelta

GRANT_TTL_SECONDS = 6 * 60 * 60

_GRANT_RE = re.compile(
    r"<!--\s*kanbanauts:grant\s+phase=(?P<phase>[A-Za-z0-9_-]+)\s+"
    r"exp=(?P<exp>\d+)\s+sig=(?P<sig>[0-9a-fA-F]+)\s*-->"
)


def _payload(owner: str, repo: str, issue_number: int, phase: str, exp: int) -> str:
    return f"v1|{owner.casefold()}|{repo.casefold()}|{issue_number}|{phase.casefold()}|{exp}"


def _sign(secret: str, payload: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_grant_comment(
    *,
    secret: str,
    owner: str,
    repo: str,
    issue_number: int,
    phase: str,
    now: float,
) -> str:
    """Hidden comment body. The app posts this before it dispatches."""
    exp = int(now) + GRANT_TTL_SECONDS
    payload = _payload(owner, repo, issue_number, phase, exp)
    sig = _sign(secret, payload)
    return (
        f"Command accepted: {phase}.\n"
        f"<!-- kanbanauts:grant phase={phase} exp={exp} sig={sig} -->"
    )


def grant_since_iso(now: float) -> str:
    """GitHub `since` value that still includes a live grant."""
    moment = datetime.fromtimestamp(now, tz=UTC) - timedelta(seconds=GRANT_TTL_SECONDS)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def grant_comment_allows(
    *,
    secret: str,
    owner: str,
    repo: str,
    issue_number: int,
    phase: str,
    comments: list[str],
    now: float,
) -> bool:
    """True when one comment has an unexpired signature for this issue and phase."""
    for body in comments:
        for match in _GRANT_RE.finditer(body):
            if match.group("phase").casefold() != phase.casefold():
                continue
            exp = int(match.group("exp"))
            if exp < int(now):
                continue
            payload = _payload(owner, repo, issue_number, phase, exp)
            expected = _sign(secret, payload)
            supplied = match.group("sig").casefold()
            if len(supplied) == len(expected) and hmac.compare_digest(supplied, expected):
                return True
    return False
