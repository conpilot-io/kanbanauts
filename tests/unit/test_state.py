from __future__ import annotations

from kanbanauts.core.state import (
    AgentState,
    concurrency_group,
    current_state,
    is_active,
    labels_to_add,
    labels_to_remove,
    next_state,
    parse_run_name,
    run_name,
)


def test_transitions() -> None:
    assert next_state(None, "queue") == AgentState.QUEUED
    assert next_state(AgentState.QUEUED, "start") == AgentState.RUNNING
    assert next_state(AgentState.RUNNING, "succeed") == AgentState.SUCCEEDED
    assert next_state(AgentState.RUNNING, "fail") == AgentState.FAILED
    assert next_state(AgentState.RUNNING, "block") == AgentState.BLOCKED


def test_label_swap() -> None:
    existing = {"bug", "agent:running"}
    remove = labels_to_remove(existing, AgentState.SUCCEEDED)
    assert "agent:running" in remove
    assert "bug" not in remove
    add = labels_to_add(existing, AgentState.SUCCEEDED)
    assert add == ["agent:succeeded"]


def test_current_and_active() -> None:
    assert current_state({"agent:queued"}) == AgentState.QUEUED
    assert is_active({"agent:running"})
    assert not is_active({"agent:failed"})
    assert current_state({"bug"}) is None


def test_run_name() -> None:
    assert run_name("doit", 42) == "agent doit #42"
    assert parse_run_name("agent plan #7") == ("plan", 7)
    assert parse_run_name("CI") is None
    assert concurrency_group(9) == "kanbanauts-9"
