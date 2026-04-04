"""Gateway allowlist for agents.workspace_file.read/write (desktop editor)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orbit.agents.agent_manager import AgentManager
from orbit.gateway.server import _resolve_agent_workspace_file_abs


def test_resolve_agent_workspace_accepts_agents_md(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ORBIT_STATE_DIR", str(tmp_path / "state"))
    mgr = AgentManager()
    aid = "e2e-ws-file"
    cfg = mgr.get_or_create(aid)
    ws = Path(cfg.workspace_dir)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "AGENTS.md").write_text("# team rules\n", encoding="utf-8")

    rel, abs_path = _resolve_agent_workspace_file_abs(
        agent_manager=mgr,
        agent_id=aid,
        rel_path="AGENTS.md",
        prefer_existing_case_variant=True,
    )
    assert rel == "AGENTS.md"
    assert Path(abs_path).read_text(encoding="utf-8").startswith("# team")
