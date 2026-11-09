#!/usr/bin/env python3
"""Post-compile patch: preserve Azure OpenAI base paths for Codex AWF configs.

gh-aw emits apiProxy.targets.openai.host from OPENAI_BASE_URL. When that env
value is a runtime expression (${{ vars.KANBANAUTS_AI_BASE_URL }}), the
compiler cannot extract /openai/v1 as basePath. AWF then forwards
POST /responses to https://<resource>.openai.azure.com/responses (404).

Switch the openai target to baseUrlEnv so AWF resolves host + basePath on the
runner from OPENAI_BASE_URL (see gh-aw-firewall apiProxy.targets.openai.baseUrlEnv).

Also inject a public OpenAI default into OPENAI_BASE_URL *after* compile. Putting
`|| 'https://api.openai.com/v1'` in engine-codex.md makes gh-aw treat the
literal as a real host/path and emit broken CLI flags.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# Escaped JSON inside printf '...awf-config...' strings in lock YAML.
# Match any openai host target (bare var or accidental var || default).
OPENAI_HOST_TARGET_RE = re.compile(
    r'\\"openai\\":\{\\"host\\":\\".*?\\"\}'
)
NEW_OPENAI_TARGET = '\\"openai\\":{\\"baseUrlEnv\\":\\"OPENAI_BASE_URL\\"}'

OLD_OPENAI_BASE_URL = "OPENAI_BASE_URL: ${{ vars.KANBANAUTS_AI_BASE_URL }}"
NEW_OPENAI_BASE_URL = (
    "OPENAI_BASE_URL: "
    "${{ vars.KANBANAUTS_AI_BASE_URL || 'https://api.openai.com/v1' }}"
)

# Broken flags when a literal default URL was present at compile time.
BROKEN_OPENAI_BASE_PATH_RE = re.compile(
    r" --openai-api-base-path '/v1'\\'' \}\}'"
)

CODEX_LOCKS = (
    "agent-plan-codex.lock.yml",
    "agent-doit-codex.lock.yml",
    "agent-review-codex.lock.yml",
)


def patch_text(text: str) -> tuple[str, int, int, int]:
    """Return patched text and counts of target / base-url / broken-flag fixes."""
    text, target_count = OPENAI_HOST_TARGET_RE.subn(NEW_OPENAI_TARGET, text)
    base_count = text.count(OLD_OPENAI_BASE_URL)
    text = text.replace(OLD_OPENAI_BASE_URL, NEW_OPENAI_BASE_URL)
    text, broken_count = BROKEN_OPENAI_BASE_PATH_RE.subn("", text)
    return text, target_count, base_count, broken_count


def patch_file(path: Path) -> tuple[int, int, int]:
    original = path.read_text(encoding="utf-8")
    patched, target_count, base_count, broken_count = patch_text(original)
    if patched != original:
        path.write_text(patched, encoding="utf-8")
    return target_count, base_count, broken_count


def assert_codex_locks_patched(workflows_dir: Path = WORKFLOWS) -> None:
    """Raise AssertionError if Codex locks still use host-only openai targets."""
    for name in CODEX_LOCKS:
        path = workflows_dir / name
        text = path.read_text(encoding="utf-8")
        leftover = OPENAI_HOST_TARGET_RE.findall(text)
        if leftover:
            raise AssertionError(
                f"{name} still has openai host target(s): {leftover[:2]}"
            )
        if NEW_OPENAI_TARGET not in text:
            raise AssertionError(
                f"{name} missing openai baseUrlEnv=OPENAI_BASE_URL"
            )
        if text.count(NEW_OPENAI_TARGET) < 2:
            raise AssertionError(
                f"{name} expected >=2 baseUrlEnv openai targets "
                f"(agent + threat-detect), found {text.count(NEW_OPENAI_TARGET)}"
            )
        if OLD_OPENAI_BASE_URL in text:
            raise AssertionError(
                f"{name} still has OPENAI_BASE_URL without public OpenAI default"
            )
        if NEW_OPENAI_BASE_URL not in text:
            raise AssertionError(
                f"{name} missing OPENAI_BASE_URL default to api.openai.com/v1"
            )
        if BROKEN_OPENAI_BASE_PATH_RE.search(text) or "--openai-api-base-path '/v1'" in text:
            raise AssertionError(
                f"{name} still has broken --openai-api-base-path from compile"
            )


def main() -> int:
    total_targets = 0
    total_bases = 0
    total_broken = 0
    for name in CODEX_LOCKS:
        path = WORKFLOWS / name
        if not path.is_file():
            print(f"error: missing {path}", file=sys.stderr)
            return 1
        targets, bases, broken = patch_file(path)
        total_targets += targets
        total_bases += bases
        total_broken += broken
        print(
            f"{path.relative_to(ROOT)}: openai targets={targets} "
            f"base_url={bases} broken_flags={broken}"
        )
    assert_codex_locks_patched()
    print(
        f"Patched {total_targets} openai target(s), "
        f"{total_bases} OPENAI_BASE_URL line(s), "
        f"removed {total_broken} broken base-path flag(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
