from __future__ import annotations

import pytest
from kanbanauts.core.config import (
    CancelAction,
    MoveToAction,
    RunAction,
    is_agent_workflow_path,
    load_config_yaml,
)
from pydantic import ValidationError


def test_load_sample_config(sample_config_yaml: str) -> None:
    cfg = load_config_yaml(sample_config_yaml)
    assert cfg.project_owner == "acme"
    assert cfg.project_number == 7
    assert cfg.column("plan") is not None
    plan = cfg.column("Plan")
    assert plan is not None
    assert isinstance(plan.on_enter[0], RunAction)
    assert plan.on_enter[0].run == "plan"
    assert isinstance(plan.on_leave[0], CancelAction)
    doit = cfg.column("DoIt")
    assert doit is not None
    assert isinstance(doit.on_success, MoveToAction)
    assert doit.on_success.move_to == "Review"
    assert cfg.phase_for_column("DoIt") == "doit"


def test_invalid_project_url() -> None:
    with pytest.raises(ValidationError):
        load_config_yaml(
            """
version: 1
project: https://github.com/acme/repo
columns: {}
phases: {}
"""
        )


def test_custom_status_field(sample_config_yaml: str) -> None:
    text = sample_config_yaml.replace("status_field: Status", "status_field: Agent stage")
    cfg = load_config_yaml(text)
    assert cfg.status_field == "Agent stage"


def test_is_agent_workflow_path() -> None:
    assert is_agent_workflow_path(
        "acme/app/.github/workflows/agent-plan.lock.yml@refs/heads/main"
    )
    assert is_agent_workflow_path(
        "acme/app/.github/workflows/agent-doit.lock.yml@refs/heads/main"
    )
    assert not is_agent_workflow_path(
        "acme/app/.github/workflows/ci.yml@refs/heads/main"
    )
    assert not is_agent_workflow_path(
        "acme/app/.github/workflows/agent-plan.yml@refs/heads/main"
    )


def test_default_phases_when_omitted() -> None:
    cfg = load_config_yaml(
        """
version: 1
project: https://github.com/orgs/acme/projects/1
columns:
  Plan:
    on_enter: [{ run: plan }]
"""
    )
    plan = cfg.phase_for_run("plan")
    doit = cfg.phase_for_run("doit")
    assert plan is not None
    assert doit is not None
    assert plan.workflow == "kanbanauts.yml"
    assert doit.workflow == "kanbanauts.yml"
