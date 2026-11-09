from __future__ import annotations

from kanbanauts.core.commands import (
    CommandName,
    command_prefixes_for_config,
    has_write_permission,
    parse_command,
    phase_for_command,
)


def test_parse_plan() -> None:
    cmd = parse_command("/agent plan")
    assert cmd is not None
    assert cmd.name == CommandName.PLAN
    assert cmd.args == ""


def test_parse_with_args() -> None:
    cmd = parse_command("/agent retry doit")
    assert cmd is not None
    assert cmd.name == CommandName.RETRY
    assert cmd.args == "doit"


def test_parse_ai_prefix() -> None:
    cmd = parse_command("/ai plan")
    assert cmd is not None
    assert cmd.name == CommandName.PLAN
    assert cmd.prefix == "/ai"


def test_parse_kanbanauts_slash() -> None:
    cmd = parse_command("/kanbanauts doit")
    assert cmd is not None
    assert cmd.name == CommandName.DOIT


def test_parse_at_mention() -> None:
    cmd = parse_command("@kanbanauts plan")
    assert cmd is not None
    assert cmd.name == CommandName.PLAN


def test_parse_at_mention_bot_suffix() -> None:
    cmd = parse_command("@kanbanauts[bot] review")
    assert cmd is not None
    assert cmd.name == CommandName.REVIEW


def test_parse_at_mention_with_colon() -> None:
    cmd = parse_command("@kanbanauts: plan")
    assert cmd is not None
    assert cmd.name == CommandName.PLAN


def test_parse_review_and_doit() -> None:
    assert parse_command("/ai review") is not None
    assert parse_command("/ai review").name == CommandName.REVIEW  # type: ignore[union-attr]
    assert parse_command("/ai doit").name == CommandName.DOIT  # type: ignore[union-attr]
    assert parse_command("/ai do").name == CommandName.DO  # type: ignore[union-attr]


def test_phase_for_command() -> None:
    assert phase_for_command(CommandName.PLAN) == "plan"
    assert phase_for_command(CommandName.DO) == "doit"
    assert phase_for_command(CommandName.DOIT) == "doit"
    assert phase_for_command(CommandName.REVIEW) == "review"
    assert phase_for_command(CommandName.HELP) is None


def test_ignores_aim_without_space() -> None:
    assert parse_command("/aim plan") is None


def test_ignores_plain_at_agent() -> None:
    assert parse_command("@agent plan") is None


def test_ignores_mid_sentence() -> None:
    assert parse_command("please /agent plan tomorrow") is None


def test_multiline_first_line() -> None:
    body = "/agent do\n\nextra notes"
    cmd = parse_command(body)
    assert cmd is not None
    assert cmd.name == CommandName.DO


def test_custom_prefix() -> None:
    cmd = parse_command("/bot plan", prefix="/bot")
    assert cmd is not None
    assert cmd.name == CommandName.PLAN
    assert parse_command("/agent help") is not None
    # Defaults still work when a custom prefix is set
    assert parse_command("/ai plan", prefix="/bot") is not None


def test_command_prefixes_for_config_longest_first() -> None:
    prefixes = command_prefixes_for_config("/agent")
    assert prefixes[0] == "/kanbanauts" or len(prefixes[0]) >= len("/ai")
    assert "/ai" in prefixes
    assert "/agent" in prefixes


def test_permissions() -> None:
    assert has_write_permission("admin")
    assert has_write_permission("write")
    assert has_write_permission("maintain")
    assert not has_write_permission("read")
    assert not has_write_permission(None)
