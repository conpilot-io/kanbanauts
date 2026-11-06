from __future__ import annotations

from kanbanauts.core.commands import (
    CommandName,
    has_write_permission,
    parse_command,
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


def test_ignores_at_mention() -> None:
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


def test_permissions() -> None:
    assert has_write_permission("admin")
    assert has_write_permission("write")
    assert has_write_permission("maintain")
    assert not has_write_permission("read")
    assert not has_write_permission(None)
