"""Pydantic schema for `.github/kanbanauts.yml`."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class Mode(StrEnum):
    OPT_OUT = "opt_out"
    OPT_IN = "opt_in"


class RunAction(BaseModel):
    run: str


class CancelAction(BaseModel):
    cancel: bool = True


class MoveToAction(BaseModel):
    move_to: str


class LabelAction(BaseModel):
    label: str


class CommentAction(BaseModel):
    comment: str


Action = RunAction | CancelAction | MoveToAction | LabelAction | CommentAction


def parse_action(raw: dict[str, Any]) -> Action:
    if "run" in raw:
        return RunAction.model_validate(raw)
    if "cancel" in raw:
        return CancelAction.model_validate(raw)
    if "move_to" in raw:
        return MoveToAction.model_validate(raw)
    if "label" in raw:
        return LabelAction.model_validate(raw)
    if "comment" in raw:
        return CommentAction.model_validate(raw)
    raise ValueError(f"Unknown action keys: {sorted(raw)}")


class ColumnConfig(BaseModel):
    on_enter: list[Action] = Field(default_factory=list)
    on_leave: list[Action] = Field(default_factory=list)
    on_success: Action | None = None
    on_no_code: Action | None = None
    on_pr_approved: Action | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_actions(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for key in ("on_enter", "on_leave"):
            if key in out and isinstance(out[key], list):
                out[key] = [parse_action(a) if isinstance(a, dict) else a for a in out[key]]
        for key in ("on_success", "on_no_code", "on_pr_approved"):
            if key in out and isinstance(out[key], dict):
                out[key] = parse_action(out[key])
        return out


class PhaseConfig(BaseModel):
    workflow: str


# Customer repos dispatch one static caller; phases default to it.
DEFAULT_CALLER_WORKFLOW = "kanbanauts.yml"
DEFAULT_PHASES: dict[str, PhaseConfig] = {
    "plan": PhaseConfig(workflow=DEFAULT_CALLER_WORKFLOW),
    "doit": PhaseConfig(workflow=DEFAULT_CALLER_WORKFLOW),
}

_PROJECT_RE = re.compile(
    r"^https://github\.com/(orgs|users)/(?P<owner>[^/]+)/projects/(?P<number>\d+)/?$"
)


class KanbanautsConfig(BaseModel):
    version: int = 1
    project: str
    status_field: str = "Status"
    command_prefix: str = "/agent"
    mode: Mode = Mode.OPT_OUT
    skip_label: str = "agent:skip"
    opt_in_label: str = "agent"
    columns: dict[str, ColumnConfig] = Field(default_factory=dict)
    phases: dict[str, PhaseConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _default_phases(self) -> KanbanautsConfig:
        if not self.phases:
            self.phases = dict(DEFAULT_PHASES)
        return self

    @field_validator("project")
    @classmethod
    def _validate_project_url(cls, value: str) -> str:
        match = _PROJECT_RE.match(value.strip())
        if not match:
            raise ValueError(
                "project must look like "
                "https://github.com/orgs/<org>/projects/<n> "
                "(or /users/<user>/projects/<n>)"
            )
        return value.rstrip("/")

    @property
    def project_owner(self) -> str:
        match = _PROJECT_RE.match(self.project)
        assert match is not None
        return match.group("owner")

    @property
    def project_number(self) -> int:
        match = _PROJECT_RE.match(self.project)
        assert match is not None
        return int(match.group("number"))

    @property
    def project_owner_type(self) -> str:
        match = _PROJECT_RE.match(self.project)
        assert match is not None
        return match.group(1)  # orgs | users

    def column(self, name: str) -> ColumnConfig | None:
        for key, cfg in self.columns.items():
            if key.casefold() == name.casefold():
                return cfg
        return None

    def column_names(self) -> list[str]:
        return list(self.columns.keys())

    def phase_for_run(self, phase: str) -> PhaseConfig | None:
        return self.phases.get(phase)

    def phase_for_column(self, column_name: str) -> str | None:
        """Return the phase name started by on_enter run actions for this column."""
        cfg = self.column(column_name)
        if cfg is None:
            return None
        for action in cfg.on_enter:
            if isinstance(action, RunAction):
                return action.run
        return None


def load_config_yaml(text: str) -> KanbanautsConfig:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("kanbanauts.yml must be a mapping")
    return KanbanautsConfig.model_validate(data)


def project_url_matches(config: KanbanautsConfig, owner: str, number: int) -> bool:
    return (
        config.project_owner.casefold() == owner.casefold()
        and config.project_number == number
    )


def parse_project_url(url: str) -> tuple[str, str, int]:
    """Return (owner_type, owner, number)."""
    match = _PROJECT_RE.match(url.rstrip("/"))
    if not match:
        raise ValueError(f"Invalid project URL: {url}")
    return match.group(1), match.group("owner"), int(match.group("number"))


def default_branch_ref_ok(ref: str, default_branch: str) -> bool:
    return ref in {f"refs/heads/{default_branch}", default_branch}


def is_agent_workflow_path(workflow_ref: str) -> bool:
    """workflow_ref basename looks like agent-*.lock.yml (legacy local path check)."""
    path = workflow_ref.split("@", 1)[0]
    name = path.rsplit("/", 1)[-1]
    return bool(re.match(r"^agent-.+\.lock\.yml$", name))


def hostname_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    return parsed.hostname
