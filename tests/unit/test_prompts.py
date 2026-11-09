"""Prompt safety: HTML comments must not appear; doit falls back to the issue."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = REPO_ROOT / ".github" / "workflows" / "shared" / "prompts"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


def _prompt_paths() -> list[Path]:
    paths = sorted(PROMPTS_DIR.glob("*.md"))
    assert paths, "no shared prompt files found"
    return paths


def test_prompts_have_no_html_comments() -> None:
    """gh aw compile deletes HTML comments from prompts, leaving empty markers."""
    for path in _prompt_paths():
        text = path.read_text(encoding="utf-8")
        assert "<!--" not in text, f"{path.name} contains an HTML comment"


def test_comment_style_requires_next_step() -> None:
    text = (PROMPTS_DIR / "comment-style.md").read_text(encoding="utf-8")
    assert "Next step" in text
    assert "/ai doit" in text


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


def test_doit_prompt_reuses_existing_pr() -> None:
    text = (PROMPTS_DIR / "doit.md").read_text(encoding="utf-8")
    assert "KANBANAUTS_EXISTING_PR" in text
    assert "push_to_pull_request_branch" in text
    assert "Do not call `create_pull_request`" in text
    assert "Do NOT run `git commit` or `git push`" in text
    assert "Omit `pr_number`" in text
    assert "pass the numeric `pr_number`" in text


def test_doit_sources_import_existing_pr_checkout() -> None:
    for engine in ("claude", "codex", "gemini"):
        text = (WORKFLOWS_DIR / f"agent-doit-{engine}.md").read_text(encoding="utf-8")
        assert "shared/kanban-checkout-existing-pr.md" in text, engine
        assert "fallback-as-pull-request: false" in text, engine
        assert 'target: "*"' in text, engine
        assert 'fetch: ["*"]' in text, engine
    for path in WORKFLOWS_DIR.glob("agent-plan-*.md"):
        assert "kanban-checkout-existing-pr.md" not in path.read_text(encoding="utf-8")
    for path in WORKFLOWS_DIR.glob("agent-review-*.md"):
        assert "kanban-checkout-existing-pr.md" not in path.read_text(encoding="utf-8")


def test_phase_prompts_require_next_step() -> None:
    for name in ("plan.md", "doit.md", "review.md"):
        text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
        assert "Next step" in text, name


def test_plan_prompt_requires_plain_marker() -> None:
    text = (PROMPTS_DIR / "plan.md").read_text(encoding="utf-8")
    assert "`kanbanauts-plan`" in text


def test_review_prompt_uses_plain_markers() -> None:
    text = (PROMPTS_DIR / "review.md").read_text(encoding="utf-8")
    assert "kanbanauts-plan" in text
    assert "`kanbanauts-review`" in text
    assert "When no plan comment exists" in text


def test_agent_sources_import_comment_style() -> None:
    sources = sorted(WORKFLOWS_DIR.glob("agent-*.md"))
    assert sources, "no agent markdown sources found"
    for path in sources:
        text = path.read_text(encoding="utf-8")
        assert "shared/prompts/comment-style.md" in text, path.name
