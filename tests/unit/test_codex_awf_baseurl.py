from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
ENGINE_CODEX = WORKFLOWS_DIR / "shared" / "engine-codex.md"
PATCH_SCRIPT = REPO_ROOT / "scripts" / "patch_codex_awf_baseurl.py"


def _load_patch_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "patch_codex_awf_baseurl", PATCH_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


patch = _load_patch_module()

HOST_BARE = r'\"openai\":{\"host\":\"${{ vars.KANBANAUTS_AI_BASE_URL }}\"}'
HOST_WITH_DEFAULT = (
    r'\"openai\":{\"host\":\"${{ vars.KANBANAUTS_AI_BASE_URL || '
    r"'https://api.openai.com/v1' }}\"}"
)
BROKEN_FLAG = " --openai-api-base-path '/v1'\\'' }}'"


def test_patch_text_rewrites_bare_host_target() -> None:
    sample = f"printf '{{{HOST_BARE}}}'\n          {patch.OLD_OPENAI_BASE_URL}\n"
    patched, targets, bases, broken = patch.patch_text(sample)
    assert targets == 1
    assert bases == 1
    assert broken == 0
    assert patch.NEW_OPENAI_TARGET in patched
    assert HOST_BARE not in patched
    assert patch.NEW_OPENAI_BASE_URL in patched


def test_patch_text_rewrites_host_target_with_default_expression() -> None:
    sample = (
        f"printf '{{{HOST_WITH_DEFAULT}}}'\n"
        f"          {patch.NEW_OPENAI_BASE_URL}\n"
        f"awf{BROKEN_FLAG} --\n"
    )
    patched, targets, bases, broken = patch.patch_text(sample)
    assert targets == 1
    assert bases == 0
    assert broken == 1
    assert patch.NEW_OPENAI_TARGET in patched
    assert HOST_WITH_DEFAULT not in patched
    assert BROKEN_FLAG not in patched


def test_patch_text_is_idempotent() -> None:
    once, t1, b1, br1 = patch.patch_text(
        f"x{HOST_BARE}y\n{patch.OLD_OPENAI_BASE_URL}\n"
    )
    twice, t2, b2, br2 = patch.patch_text(once)
    assert t1 == 1 and b1 == 1 and br1 == 0
    assert t2 == 0 and b2 == 0 and br2 == 0
    assert twice == once


def test_committed_codex_locks_use_baseurlenv() -> None:
    patch.assert_codex_locks_patched(WORKFLOWS_DIR)
    for name in patch.CODEX_LOCKS:
        text = (WORKFLOWS_DIR / name).read_text(encoding="utf-8")
        assert text.count(patch.NEW_OPENAI_TARGET) >= 2, name
        assert "api.openai.com/v1" in text, name
        assert "--openai-api-base-path '/v1'" not in text, name


def test_engine_codex_has_no_literal_url_default() -> None:
    """Literal defaults must stay out of engine frontmatter (breaks gh-aw compile)."""
    text = ENGINE_CODEX.read_text(encoding="utf-8")
    assert "OPENAI_BASE_URL: ${{ vars.KANBANAUTS_AI_BASE_URL }}" in text
    assert "|| 'https://api.openai.com/v1'" not in text


def test_ci_and_release_run_codex_awf_patch() -> None:
    for name in ("ci.yml", "release.yml"):
        text = (WORKFLOWS_DIR / name).read_text(encoding="utf-8")
        assert "scripts/patch_codex_awf_baseurl.py" in text, name


def test_assert_codex_locks_patched_detects_host_only(tmp_path: Path) -> None:
    bad = tmp_path / "agent-plan-codex.lock.yml"
    bad.write_text(
        f"printf '{HOST_BARE}'\n{patch.OLD_OPENAI_BASE_URL}\n",
        encoding="utf-8",
    )
    other = tmp_path / "agent-doit-codex.lock.yml"
    other.write_text("unrelated\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="still has openai host"):
        patch.assert_codex_locks_patched(tmp_path)
