"""Strict agent command parser and permission helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

# Built-in prefixes. Customers may add another via `command_prefix` in config.
# Longest match wins so `/kanbanauts` beats `/k` if that were ever added.
DEFAULT_COMMAND_PREFIXES: tuple[str, ...] = (
    "/kanbanauts",
    "@kanbanauts[bot]",
    "@kanbanauts",
    "/agent",
    "/ai",
)


class CommandName(StrEnum):
    PLAN = "plan"
    DO = "do"
    DOIT = "doit"
    REVIEW = "review"
    RETRY = "retry"
    STATUS = "status"
    CANCEL = "cancel"
    HELP = "help"


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    name: CommandName
    args: str
    raw: str
    prefix: str


_CMD_NAMES = "plan|doit|do|review|retry|status|cancel|help"


def _normalize_prefixes(extra: str | None) -> list[str]:
    """Return unique prefixes sorted longest-first (case-folded for matching)."""
    seen: set[str] = set()
    out: list[str] = []
    for prefix in (*DEFAULT_COMMAND_PREFIXES, *( (extra,) if extra else () )):
        key = prefix.strip()
        if not key:
            continue
        folded = key.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        out.append(key)
    out.sort(key=len, reverse=True)
    return out


def parse_command(
    body: str,
    prefix: str | None = None,
    *,
    prefixes: list[str] | None = None,
) -> ParsedCommand | None:
    """
    Parse a strict agent command from a comment body.

    Only the first matching line counts. Ordinary discussion without a known
    prefix does not trigger anything. Prefix must be followed by whitespace
    so `/aim` does not match `/ai`.
    """
    if not body:
        return None
    candidates = prefixes if prefixes is not None else _normalize_prefixes(prefix)
    if not candidates:
        return None
    # Optional trailing : or , after the mention/slash prefix.
    alt = "|".join(re.escape(p) for p in candidates)
    pattern = re.compile(
        rf"(?m)^\s*(?P<prefix>{alt})\s*[:,]?\s+"
        rf"(?P<cmd>{_CMD_NAMES})"
        rf"(?:\s+(?P<args>.+))?\s*$",
        re.IGNORECASE,
    )
    match = pattern.search(body)
    if match is None:
        return None
    raw_cmd = match.group("cmd").casefold()
    # `do` is an alias for `doit` as a command name stored as DO.
    if raw_cmd == "doit":
        cmd = CommandName.DOIT
    else:
        cmd = CommandName(raw_cmd)
    args = (match.group("args") or "").strip()
    return ParsedCommand(
        name=cmd,
        args=args,
        raw=match.group(0).strip(),
        prefix=match.group("prefix"),
    )


def command_prefixes_for_config(command_prefix: str | None) -> list[str]:
    """Prefixes accepted for a customer config (defaults + optional override)."""
    return _normalize_prefixes(command_prefix)


WRITE_PERMISSIONS = frozenset({"admin", "maintain", "write"})


def has_write_permission(permission: str | None) -> bool:
    if permission is None:
        return False
    return permission.casefold() in WRITE_PERMISSIONS


def phase_for_command(name: CommandName) -> str | None:
    """Map a run-style command to a workflow phase name."""
    if name == CommandName.PLAN:
        return "plan"
    if name in (CommandName.DO, CommandName.DOIT):
        return "doit"
    if name == CommandName.REVIEW:
        return "review"
    return None


HELP_TEXT = """\
Kanbanauts commands:

- `/ai plan` — start or rerun planning
- `/ai doit` — start implementation (`/ai do` also works)
- `/ai review` — AI review of the linked draft PR (comment only)
- `/ai retry` — retry the last failed phase
- `/ai status` — show current agent state
- `/ai cancel` — stop the active agent run
- `/ai help` — show this message

Trailing text is allowed, for example: `/ai doit use option A`.
Agent replies end with a **Next step** that names the command to run next.

Also accepted: `/kanbanauts`, `@kanbanauts`, and `/agent`.
Only users with write access may run these commands.
Tickets with the `agent:skip` label are ignored.
The issue does not need to be on a Project board.
"""


def status_next_step(state: object | None) -> str:
    """One Next step line for `/ai status`, based on the current agent label."""
    # Import locally to avoid a circular import with state helpers used elsewhere.
    from kanbanauts.core.state import AgentState

    if state is None:
        return "**Next step:** Comment `/ai plan` to start."
    if state == AgentState.QUEUED or state == AgentState.RUNNING:
        return "**Next step:** Wait for the run, or comment `/ai cancel` to stop it."
    if state == AgentState.SUCCEEDED:
        return (
            "**Next step:** Comment `/ai doit` to implement, "
            "or `/ai review` if a draft PR already exists."
        )
    if state == AgentState.BLOCKED:
        return (
            "**Next step:** Answer any open questions, then comment "
            "`/ai doit <your answers>`."
        )
    if state == AgentState.FAILED:
        return "**Next step:** Comment `/ai retry` to retry the last failed phase."
    return "**Next step:** Comment `/ai help` for available commands."
