"""Label state machine and duplicate-run helpers."""

from __future__ import annotations

from enum import StrEnum


class AgentState(StrEnum):
    QUEUED = "agent:queued"
    RUNNING = "agent:running"
    SUCCEEDED = "agent:succeeded"
    FAILED = "agent:failed"
    BLOCKED = "agent:blocked"


STATE_LABELS: frozenset[str] = frozenset(s.value for s in AgentState)

ACTIVE_STATES: frozenset[AgentState] = frozenset({AgentState.QUEUED, AgentState.RUNNING})


def next_state(current: AgentState | None, event: str) -> AgentState:
    """
    Transition table.

    Events: queue | start | succeed | fail | block | clear
    """
    if event == "clear":
        # Caller removes all state labels; no new label.
        raise ValueError("clear removes labels; use clear_state_labels")
    if event == "queue":
        return AgentState.QUEUED
    if event == "start":
        return AgentState.RUNNING
    if event == "succeed":
        return AgentState.SUCCEEDED
    if event == "fail":
        return AgentState.FAILED
    if event == "block":
        return AgentState.BLOCKED
    raise ValueError(f"Unknown state event: {event}")


def labels_to_remove(existing: set[str], new_state: AgentState | None) -> list[str]:
    """State labels that must be removed before applying new_state (or clearing)."""
    to_remove = [label for label in existing if label in STATE_LABELS]
    if new_state is not None and new_state.value in to_remove:
        to_remove = [label for label in to_remove if label != new_state.value]
    return to_remove


def labels_to_add(existing: set[str], new_state: AgentState) -> list[str]:
    if new_state.value in existing:
        return []
    return [new_state.value]


def current_state(labels: set[str]) -> AgentState | None:
    found = [AgentState(label) for label in labels if label in STATE_LABELS]
    if not found:
        return None
    # Prefer active states if multiple somehow present.
    for preferred in (AgentState.RUNNING, AgentState.QUEUED):
        if preferred in found:
            return preferred
    return found[0]


def is_active(labels: set[str]) -> bool:
    state = current_state(labels)
    return state in ACTIVE_STATES


def run_name(phase: str, issue_number: int) -> str:
    return f"agent {phase} #{issue_number}"


def parse_run_name(name: str) -> tuple[str, int] | None:
    """Parse 'agent <phase> #<issue>'."""
    if not name.startswith("agent "):
        return None
    rest = name[len("agent ") :]
    if " #" not in rest:
        return None
    phase, _, num = rest.partition(" #")
    try:
        return phase.strip(), int(num.strip())
    except ValueError:
        return None


def concurrency_group(issue_number: int) -> str:
    return f"kanbanauts-{issue_number}"
