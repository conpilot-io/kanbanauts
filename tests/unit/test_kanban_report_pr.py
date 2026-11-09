"""Regression: temporary #aw_ ids must not break the Kanbanauts report step."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_MD = REPO_ROOT / ".github" / "workflows" / "shared" / "kanban-report.md"

_RESOLVE_MARKER = re.compile(
    r"# BEGIN kanban-report-resolve-pr\n(.*?)\n\s*# END kanban-report-resolve-pr",
    re.DOTALL,
)
_JQ_PR_FILTER = re.compile(
    r'pr_number:\s*\(if \(\$pr \| test\("\^\[0-9\]\+\$"\)\) then \(\$pr\|tonumber\) else null end\)'
)


def _resolve_block() -> str:
    text = REPORT_MD.read_text(encoding="utf-8")
    match = _RESOLVE_MARKER.search(text)
    assert match, "kanban-report-resolve-pr block missing from kanban-report.md"
    return match.group(1)


def _resolve_pr(pr: str, created: str) -> str:
    """Run the marked shell fragment and print the resolved PR."""
    script = f"""
set -euo pipefail
PR={pr!r}
CREATED_PR_NUMBER={created!r}
{_resolve_block()}
printf '%s' "$PR"
"""
    result = subprocess.run(
        ["bash", "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    # Drop warning lines from stdout; keep the final printf value.
    lines = [line for line in result.stdout.splitlines() if not line.startswith("::")]
    return lines[-1] if lines else ""


@pytest.mark.parametrize(
    ("pr", "created", "expected"),
    [
        ("#aw_audit3320", "3331", "3331"),
        ("3331", "", "3331"),
        ("3331", "9999", "3331"),
        ("", "3331", "3331"),
        ("#aw_audit3320", "", ""),
        ("null", "3331", "3331"),
    ],
)
def test_resolve_pr_number(pr: str, created: str, expected: str) -> None:
    assert _resolve_pr(pr, created) == expected


def test_jq_pr_filter_accepts_temporary_id() -> None:
    text = REPORT_MD.read_text(encoding="utf-8")
    assert _JQ_PR_FILTER.search(text), "safe pr_number jq filter missing"

    result = subprocess.run(
        [
            "jq",
            "-n",
            "--arg",
            "pr",
            "#aw_audit3320",
            '{pr_number: (if ($pr | test("^[0-9]+$")) then ($pr|tonumber) else null end)}',
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == {"pr_number": None}


def test_doit_prompt_omits_pr_number() -> None:
    prompt = (
        REPO_ROOT / ".github" / "workflows" / "shared" / "prompts" / "doit.md"
    ).read_text(encoding="utf-8")
    assert "Omit `pr_number`" in prompt
    assert "#aw_..." in prompt
    assert "pr_number` set" not in prompt
