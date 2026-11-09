"""Prompt safety: HTML comments must not appear; doit falls back to the issue."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = REPO_ROOT / ".github" / "workflows" / "shared" / "prompts"


def _prompt_paths() -> list[Path]:
    paths = sorted(PROMPTS_DIR.glob("*.md"))
    assert paths, "no shared prompt files found"
    return paths


def test_prompts_have_no_html_comments() -> None:
    """gh aw compile deletes HTML comments from prompts, leaving empty markers."""
    for path in _prompt_paths():
        text = path.read_text(encoding="utf-8")
        assert "<!--" not in text, f"{path.name} contains an HTML comment"


def test_doit_prompt_falls_back_to_issue_body() -> None:
    text = (PROMPTS_DIR / "doit.md").read_text(encoding="utf-8")
    assert "A missing plan comment is not a reason to stop" in text
    assert "issue title, body, and the other comments are" in text
    assert "the specification" in text


def test_doit_prompt_stops_on_unanswered_plan_question() -> None:
    text = (PROMPTS_DIR / "doit.md").read_text(encoding="utf-8")
    assert "open question" in text
    assert "no later human comment answers" in text
    assert "status=blocked" in text


def test_plan_prompt_requires_plain_marker() -> None:
    text = (PROMPTS_DIR / "plan.md").read_text(encoding="utf-8")
    assert "`kanbanauts-plan`" in text


def test_review_prompt_uses_plain_markers() -> None:
    text = (PROMPTS_DIR / "review.md").read_text(encoding="utf-8")
    assert "kanbanauts-plan" in text
    assert "`kanbanauts-review`" in text
    assert "When no plan comment exists" in text
