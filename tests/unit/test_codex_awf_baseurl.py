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


def test_patch_text_rewrites_host_target_and_base_url() -> None:
    sample = (
        f"printf '{{{patch.OLD_OPENAI_TARGET}}}'\n"
        f"          {patch.OLD_OPENAI_BASE_URL}\n"
    )
    patched, targets, bases = patch.patch_text(sample)
    assert targets == 1
    assert bases == 1
    assert patch.NEW_OPENAI_TARGET in patched
    assert patch.OLD_OPENAI_TARGET not in patched
    assert patch.NEW_OPENAI_BASE_URL in patched
    assert patch.OLD_OPENAI_BASE_URL not in patched


def test_patch_text_is_idempotent() -> None:
    once, t1, b1 = patch.patch_text(
        f"x{patch.OLD_OPENAI_TARGET}y\n{patch.OLD_OPENAI_BASE_URL}\n"
    )
    twice, t2, b2 = patch.patch_text(once)
    assert t1 == 1 and b1 == 1
    assert t2 == 0 and b2 == 0
    assert twice == once


def test_committed_codex_locks_use_baseurlenv() -> None:
    patch.assert_codex_locks_patched(WORKFLOWS_DIR)
    for name in patch.CODEX_LOCKS:
        text = (WORKFLOWS_DIR / name).read_text(encoding="utf-8")
        assert text.count(patch.NEW_OPENAI_TARGET) >= 2, name
        assert "api.openai.com/v1" in text, name


def test_engine_codex_defaults_openai_base_url() -> None:
    text = ENGINE_CODEX.read_text(encoding="utf-8")
    assert "vars.KANBANAUTS_AI_BASE_URL || 'https://api.openai.com/v1'" in text


def test_ci_and_release_run_codex_awf_patch() -> None:
    for name in ("ci.yml", "release.yml"):
        text = (WORKFLOWS_DIR / name).read_text(encoding="utf-8")
        assert "scripts/patch_codex_awf_baseurl.py" in text, name


def test_assert_codex_locks_patched_detects_host_only(tmp_path: Path) -> None:
    bad = tmp_path / "agent-plan-codex.lock.yml"
    bad.write_text(
        f"printf '{patch.OLD_OPENAI_TARGET}'\n{patch.OLD_OPENAI_BASE_URL}\n",
        encoding="utf-8",
    )
    other = tmp_path / "agent-doit-codex.lock.yml"
    other.write_text("unrelated\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="still has openai host"):
        patch.assert_codex_locks_patched(tmp_path)
