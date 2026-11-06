from __future__ import annotations

from kanbanauts.core.caller import (
    CALLER_VERSION,
    parse_caller_version,
    render_caller_workflow,
    render_config,
)


def test_render_caller_stable_and_versioned() -> None:
    text = render_caller_workflow()
    assert f"# kanbanauts-caller: {CALLER_VERSION}" in text
    assert "uses: conpilot-io/kanbanauts/.github/workflows/agent-plan-claude.lock.yml@v1" in text
    assert "concurrency:" in text
    assert "kanbanauts-${{ inputs.issue_number }}" in text
    assert "plan_claude:" in text
    assert "doit_gemini:" in text
    assert parse_caller_version(text) == CALLER_VERSION
    # Stable across calls
    assert render_caller_workflow() == text


def test_parse_caller_version_missing() -> None:
    assert parse_caller_version("name: x\n") is None


def test_render_config_defaults_no_phases() -> None:
    text = render_config(project_url="https://github.com/orgs/acme/projects/1")
    assert "phases:" not in text
    assert "project: https://github.com/orgs/acme/projects/1" in text


def test_render_config_candidates() -> None:
    text = render_config(
        project_candidates=[
            "https://github.com/orgs/acme/projects/1",
            "https://github.com/orgs/acme/projects/2",
        ]
    )
    assert "Several org Projects" in text
    assert "YOUR_ORG" in text
