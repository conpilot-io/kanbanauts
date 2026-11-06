from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

SETUP_PIN = re.compile(r"github/gh-aw-actions/setup@([0-9a-f]{40})")
SHA_VAR = re.compile(r"^\s*SHA=([0-9a-f]{40})\s*$", re.MULTILINE)


def _lock_pins() -> dict[str, set[str]]:
    pins: dict[str, set[str]] = {}
    for path in sorted(WORKFLOWS_DIR.glob("agent-*.lock.yml")):
        pins[path.name] = set(
            SETUP_PIN.findall(path.read_text(encoding="utf-8"))
        )
    return pins


def test_lock_files_use_one_gh_aw_actions_pin() -> None:
    """All locks must use the same gh-aw-actions/setup commit."""
    pins = _lock_pins()
    assert pins, "no lock files found"
    for name, shas in pins.items():
        assert len(shas) == 1, f"{name} has pins: {sorted(shas)}"
    assert len({next(iter(s)) for s in pins.values()}) == 1


def test_lock_pin_matches_ci_and_release_compile_sha() -> None:
    """Compiler (gh-aw CLI) and runtime (gh-aw-actions) must be the same release.

    A lock compiled by gh-aw v1.2.0 but pinned to the v1.0.1 setup action made
    the `activation` job fail with
    `Prompt render item must specify exactly one content_env or file`.
    """
    lock_sha = next(iter(next(iter(_lock_pins().values()))))
    for workflow in ("ci.yml", "release.yml"):
        text = (WORKFLOWS_DIR / workflow).read_text(encoding="utf-8")
        found = SHA_VAR.findall(text)
        assert found, f"{workflow} has no SHA= compile pin"
        assert set(found) == {lock_sha}, (
            f"{workflow} compile SHA {found} != lock pin {lock_sha}"
        )


def test_lock_files_allow_the_kanbanauts_bot() -> None:
    """The App dispatches the caller as `kanbanauts[bot]` (repo permission `none`).

    Without `on.bots`, gh-aw's membership check sets `activated=false`, every
    job after `pre_activation` is skipped, and the run still shows green.
    """
    for name in _lock_pins():
        text = (WORKFLOWS_DIR / name).read_text(encoding="utf-8")
        assert 'GH_AW_ALLOWED_BOTS: "kanbanauts[bot]"' in text, name


def test_sources_enable_inlined_imports() -> None:
    """Cross-repo workflow_call cannot check out the callee's .github folder."""
    sources = sorted(WORKFLOWS_DIR.glob("agent-*.md"))
    assert sources, "no agent markdown sources found"
    for path in sources:
        text = path.read_text(encoding="utf-8")
        assert "inlined-imports: true" in text, path.name


def test_lock_files_have_no_runtime_imports_or_author_file() -> None:
    """Runtime imports and author_file need files that only exist in kanbanauts.

    Without inlined-imports, activation fails with:
    Failed to resolve runtime import path .github/workflows/agent-plan-*.md
    """
    for name in _lock_pins():
        text = (WORKFLOWS_DIR / name).read_text(encoding="utf-8")
        assert "runtime-import" not in text, name
        assert "author_file" not in text, name
