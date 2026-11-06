"""Strict `/agent <cmd>` parser and permission helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class CommandName(StrEnum):
    PLAN = "plan"
    DO = "do"
    RETRY = "retry"
    STATUS = "status"
    CANCEL = "cancel"
    HELP = "help"


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    name: CommandName
    args: str
    raw: str


_CMD_NAMES = "plan|do|retry|status|cancel|help"


def parse_command(body: str, prefix: str = "/agent") -> ParsedCommand | None:
    """
    Parse a strict agent command from a comment body.

    Only the first matching line counts. Ordinary discussion without the prefix
    does not trigger anything.
    """
    if not body:
        return None
    escaped = re.escape(prefix.strip())
    pattern = re.compile(
        rf"(?m)^\s*(?P<prefix>{escaped})\s+(?P<cmd>{_CMD_NAMES})"
        rf"(?:\s+(?P<args>.+))?\s*$",
        re.IGNORECASE,
    )
    match = pattern.search(body)
    if match is None:
        return None
    cmd = CommandName(match.group("cmd").casefold())
    args = (match.group("args") or "").strip()
    return ParsedCommand(name=cmd, args=args, raw=match.group(0).strip())


WRITE_PERMISSIONS = frozenset({"admin", "maintain", "write"})


def has_write_permission(permission: str | None) -> bool:
    if permission is None:
        return False
    return permission.casefold() in WRITE_PERMISSIONS


HELP_TEXT = """\
Kanbanauts commands:

- `/agent plan` — start or rerun planning
- `/agent do` — start implementation
- `/agent retry` — retry the last failed phase
- `/agent status` — show current agent state
- `/agent cancel` — stop the active agent run
- `/agent help` — show this message

Only users with write access may run these commands.
Tickets with the `agent:skip` label are ignored.
"""
