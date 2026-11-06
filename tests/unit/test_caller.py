from __future__ import annotations

from pathlib import Path

import yaml
from kanbanauts.core.caller import (
    CALLER_VERSION,
    ENGINES,
    PHASES,
    parse_caller_version,
    render_caller_workflow,
    render_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


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


def test_render_caller_passes_only_kanbanauts_ai_api_key() -> None:
    text = render_caller_workflow()
    assert "KANBANAUTS_AI_API_KEY:" in text
    assert "ANTHROPIC_API_KEY:" not in text
    assert "OPENAI_API_KEY:" not in text
    assert "GEMINI_API_KEY:" not in text


def test_caller_secrets_match_lock_workflow_call_secrets() -> None:
    """Every secret the caller passes must be declared on the reusable workflow."""
    caller = yaml.safe_load(render_caller_workflow())
    jobs = caller["jobs"]
    for phase in PHASES:
        for engine in ENGINES:
            job_id = f"{phase}_{engine}"
            lock_name = f"agent-{phase}-{engine}.lock.yml"
            lock_path = WORKFLOWS_DIR / lock_name
            assert lock_path.is_file(), f"missing lock file {lock_path}"
            lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
            # PyYAML 1.1 treats the key `on` as boolean True.
            on_block = lock.get("on") or lock.get(True) or {}
            declared = set(
                on_block.get("workflow_call", {}).get("secrets", {}).keys()
            )
            passed = set((jobs[job_id].get("secrets") or {}).keys())
            unknown = passed - declared
            assert not unknown, (
                f"{job_id} passes secrets not declared in {lock_name}: "
                f"{sorted(unknown)}; declared={sorted(declared)}"
            )


def test_release_workflow_reads_caller_version() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    assert "from kanbanauts.core.caller import CALLER_VERSION" in text
    assert "--argjson ver \"$VER\"" in text
    assert "--argjson ver 1" not in text


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
