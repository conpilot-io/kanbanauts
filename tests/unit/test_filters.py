from __future__ import annotations

from kanbanauts.core.config import load_config_yaml
from kanbanauts.core.filters import filter_ticket, validate_column_names


def test_wrong_project(sample_config_yaml: str) -> None:
    cfg = load_config_yaml(sample_config_yaml)
    result = filter_ticket(
        cfg, labels=set(), has_issue=True, project_owner="other", project_number=7
    )
    assert not result.allow
    assert result.reason == "wrong_project"


def test_no_project_blocks_board_filter() -> None:
    cfg = load_config_yaml(
        """
version: 1
columns:
  Plan:
    on_enter: [{ run: plan }]
"""
    )
    result = filter_ticket(
        cfg, labels=set(), has_issue=True, project_owner="acme", project_number=7
    )
    assert result.reason == "no_project"


def test_draft(sample_config_yaml: str) -> None:
    cfg = load_config_yaml(sample_config_yaml)
    result = filter_ticket(
        cfg, labels=set(), has_issue=False, project_owner="acme", project_number=7
    )
    assert result.reason == "draft_or_no_issue"


def test_skip_label(sample_config_yaml: str) -> None:
    cfg = load_config_yaml(sample_config_yaml)
    result = filter_ticket(
        cfg,
        labels={"agent:skip"},
        has_issue=True,
        project_owner="acme",
        project_number=7,
    )
    assert result.reason == "skip_label"


def test_opt_in(sample_config_yaml: str) -> None:
    text = sample_config_yaml.replace("mode: opt_out", "mode: opt_in")
    cfg = load_config_yaml(text)
    denied = filter_ticket(
        cfg, labels=set(), has_issue=True, project_owner="acme", project_number=7
    )
    assert denied.reason == "opt_in_missing_label"
    ok = filter_ticket(
        cfg,
        labels={"agent"},
        has_issue=True,
        project_owner="acme",
        project_number=7,
    )
    assert ok.allow


def test_validate_columns(sample_config_yaml: str) -> None:
    cfg = load_config_yaml(sample_config_yaml)
    missing = validate_column_names(cfg, {"Plan", "DoIt", "Review", "Tests"})
    assert "Done" in missing
    assert validate_column_names(
        cfg, {"Plan", "DoIt", "Review", "Tests", "Done", "Backlog"}
    ) == []
