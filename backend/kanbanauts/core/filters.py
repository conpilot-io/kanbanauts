"""Ticket filters — project match, draft, skip, opt-in."""

from __future__ import annotations

from dataclasses import dataclass

from kanbanauts.core.config import KanbanautsConfig, Mode


@dataclass(frozen=True, slots=True)
class FilterResult:
    allow: bool
    reason: str

    @classmethod
    def ok(cls) -> FilterResult:
        return cls(True, "")

    @classmethod
    def deny(cls, reason: str) -> FilterResult:
        return cls(False, reason)


def filter_ticket(
    config: KanbanautsConfig,
    *,
    labels: set[str],
    has_issue: bool,
    project_owner: str,
    project_number: int,
) -> FilterResult:
    if not has_issue:
        return FilterResult.deny("draft_or_no_issue")
    if (
        config.project_owner.casefold() != project_owner.casefold()
        or config.project_number != project_number
    ):
        return FilterResult.deny("wrong_project")
    if config.skip_label in labels:
        return FilterResult.deny("skip_label")
    if config.mode == Mode.OPT_IN and config.opt_in_label not in labels:
        return FilterResult.deny("opt_in_missing_label")
    return FilterResult.ok()


def validate_column_names(
    config: KanbanautsConfig, field_options: set[str]
) -> list[str]:
    """Return config column names that are missing from the Project field options."""
    option_folded = {name.casefold() for name in field_options}
    missing: list[str] = []
    for name in config.column_names():
        if name.casefold() not in option_folded:
            missing.append(name)
    return missing
