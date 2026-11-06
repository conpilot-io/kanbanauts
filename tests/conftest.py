"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

SAMPLE_CONFIG = """
version: 1
project: https://github.com/orgs/acme/projects/7
status_field: Status
command_prefix: /agent
mode: opt_out
skip_label: agent:skip
columns:
  Plan:
    on_enter: [{ run: plan }]
    on_leave: [{ cancel: true }]
    on_no_code: { move_to: Done }
  DoIt:
    on_enter: [{ run: doit }]
    on_leave: [{ cancel: true }]
    on_success: { move_to: Review }
  Review:
    on_pr_approved: { move_to: Tests }
  Tests:
    on_enter: []
  Done: {}
"""


@pytest.fixture
def sample_config_yaml() -> str:
    return SAMPLE_CONFIG
