"""Drift guard: ``agent.md`` and ``claude.md`` must be byte-identical.

The repository policy in ``agent.md`` is that any update Claude makes to
``agent.md`` must be mirrored to ``claude.md`` (and vice versa) so the
project always carries a record of the policy as the AI agent understands
it. This test enforces parity automatically.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
AGENT_MD = ROOT_DIR / "agent.md"
CLAUDE_MD = ROOT_DIR / "claude.md"


@pytest.mark.unit
def test_agent_md_and_claude_md_are_byte_identical() -> None:
    assert AGENT_MD.exists(), f"{AGENT_MD} is missing"
    assert CLAUDE_MD.exists(), f"{CLAUDE_MD} is missing"
    agent_bytes = AGENT_MD.read_bytes()
    claude_bytes = CLAUDE_MD.read_bytes()
    assert agent_bytes == claude_bytes, (
        "agent.md and claude.md have diverged. "
        "Project policy requires they be byte-identical. "
        "Run: `cp agent.md claude.md` (or the PowerShell equivalent) and re-commit."
    )
