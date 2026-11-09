from __future__ import annotations

from pathlib import Path

import yaml
from kanbanauts.core.caller import (
    CALLER_VERSION,
    ENGINES,
    PHASES,
    caller_accepts_source,
    parse_caller_version,
    render_caller_workflow,
    render_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


def test_render_caller_stable_and_versioned() -> None:
    text = render_caller_workflow()
    assert f"# kanbanauts-caller: {CALLER_VERSION}" in text
    assert CALLER_VERSION == 6
    assert "uses: conpilot-io/kanbanauts/.github/workflows/agent-plan-claude.lock.yml@v1" in text
    assert "concurrency:" in text
    assert "kanbanauts-${{ inputs.issue_number }}" in text
    assert "plan_claude:" in text
    assert "doit_gemini:" in text
    assert "review_codex:" in text
    assert "source:" in text
    assert "inputs.source || 'board'" in text
    assert parse_caller_version(text) == CALLER_VERSION
    # Stable across calls
    assert render_caller_workflow() == text


def test_render_caller_passes_only_kanbanauts_ai_api_key() -> None:
    text = render_caller_workflow()
    assert "KANBANAUTS_AI_API_KEY:" in text
    assert "ANTHROPIC_API_KEY:" not in text
    assert "OPENAI_API_KEY:" not in text
    assert "GEMINI_API_KEY:" not in text


def test_caller_permissions_cover_reusable_lock_jobs() -> None:
    """Caller GITHUB_TOKEN ceiling must cover every nested lock-file job."""
    caller = yaml.safe_load(render_caller_workflow())
    caller_perms: dict[str, str] = caller["permissions"]
    required = {
        "actions": "read",
        "checks": "read",
        "contents": "write",
        "id-token": "write",
        "issues": "write",
        "pull-requests": "write",
    }
    for key, level in required.items():
        assert caller_perms.get(key) == level, (
            f"caller permissions[{key!r}] expected {level!r}, "
            f"got {caller_perms.get(key)!r}"
        )

    rank = {"none": 0, "read": 1, "write": 2}
    for phase in PHASES:
        for engine in ENGINES:
            lock_path = WORKFLOWS_DIR / f"agent-{phase}-{engine}.lock.yml"
            lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
            for job_id, job in (lock.get("jobs") or {}).items():
                job_perms = job.get("permissions") or {}
                if not isinstance(job_perms, dict):
                    continue
                for key, level in job_perms.items():
                    assert key in caller_perms, (
                        f"{lock_path.name} job {job_id} needs {key}:{level} "
                        f"but caller omits {key}"
                    )
                    assert rank[caller_perms[key]] >= rank[level], (
                        f"{lock_path.name} job {job_id} needs {key}:{level} "
                        f"but caller only grants {caller_perms[key]}"
                    )


def test_template_matches_render_caller_workflow() -> None:
    template = (
        REPO_ROOT / "templates" / "workflows-kanbanauts.yml"
    ).read_text(encoding="utf-8")
    assert template == render_caller_workflow()


def test_caller_run_name_is_quoted() -> None:
    """Unquoted `#${{ inputs.issue_number }}` is a YAML comment and drops the number."""
    text = render_caller_workflow()
    assert (
        'run-name: "agent ${{ inputs.phase }} #${{ inputs.issue_number }}"'
        in text
    )


def test_caller_issue_number_type_matches_lock_workflows() -> None:
    """Reusable locks declare issue_number as number; caller must pass a number."""
    caller = yaml.safe_load(render_caller_workflow())
    # PyYAML 1.1 treats the key `on` as boolean True.
    caller_on = caller.get("on") or caller.get(True) or {}
    dispatch = caller_on["workflow_dispatch"]["inputs"]["issue_number"]
    assert dispatch["type"] == "number"

    for phase in PHASES:
        for engine in ENGINES:
            job_id = f"{phase}_{engine}"
            lock_path = WORKFLOWS_DIR / f"agent-{phase}-{engine}.lock.yml"
            lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
            on_block = lock.get("on") or lock.get(True) or {}
            lock_input = on_block["workflow_call"]["inputs"]["issue_number"]
            assert lock_input["type"] == "number", lock_path.name
            # A workflow_dispatch `number` input reaches `with:` as a string.
            # GitHub then rejects the reusable call (run fails with zero jobs
            # and no error), so the caller must convert it with fromJSON().
            assert (
                caller["jobs"][job_id]["with"]["issue_number"]
                == "${{ fromJSON(inputs.issue_number) }}"
            )


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
    assert "on_enter: [{ run: review }]" in text


def test_render_config_candidates() -> None:
    text = render_config(
        project_candidates=[
            "https://github.com/orgs/acme/projects/1",
            "https://github.com/orgs/acme/projects/2",
        ]
    )
    assert "Several org Projects" in text
    assert "YOUR_ORG" in text


def test_caller_accepts_source_by_version() -> None:
    assert caller_accepts_source(None) is True
    assert caller_accepts_source("") is True
    assert caller_accepts_source(render_caller_workflow()) is True
    assert caller_accepts_source("# kanbanauts-caller: 5\n") is False
    assert caller_accepts_source("name: Kanbanauts\n    source:\n") is True
