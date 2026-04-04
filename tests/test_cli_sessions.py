from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from orbit.cli.main import main as cli_main
from orbit.agents.session import MultiAgentSessionManager
from orbit.agents.agent_manager import AgentManager


def _run_cli(argv: list[str]) -> str:
    try:
        cli_main(argv)
    except SystemExit as e:
        if e.code != 0:
            raise
    return ""


def test_sessions_sessions_lists_agent_sessions(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ORBIT_STATE_DIR", str(tmp_path / ".orbit"))
    # Avoid encryption warning noise (must be base64-encoded 32 bytes).
    monkeypatch.setenv("ORBIT_SECRET_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

    mgr = MultiAgentSessionManager(agent_manager=AgentManager())
    # create 2 sessions under agent "main"
    s1 = mgr.get_or_create_session(session_id="s1", session_key="k1", agent_id="main")
    mgr.update_session(s1.session_id, agent_id="main", message_count=3)
    s2 = mgr.get_or_create_session(session_id="s2", session_key="k2", agent_id="main")
    mgr.update_session(s2.session_id, agent_id="main", message_count=7)

    _run_cli(["orbit", "sessions", "--agent", "main"])
    out = capsys.readouterr().out
    assert "Sessions (agent=main)" in out
    assert "s1" in out and "s2" in out


def test_sessions_sessions_json_output(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ORBIT_STATE_DIR", str(tmp_path / ".orbit"))
    monkeypatch.setenv("ORBIT_SECRET_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

    mgr = MultiAgentSessionManager(agent_manager=AgentManager())
    mgr.get_or_create_session(session_id="s1", session_key="k1", agent_id="main")

    _run_cli(["orbit", "sessions", "--agent", "main", "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert isinstance(data.get("sessions"), list)
    assert any(s.get("sessionId") == "s1" for s in data["sessions"])


def test_sessions_without_agent_aggregates_all_agents(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ORBIT_STATE_DIR", str(tmp_path / ".orbit"))
    monkeypatch.setenv("ORBIT_SECRET_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

    mgr = MultiAgentSessionManager(agent_manager=AgentManager())
    s_main = mgr.get_or_create_session(session_id="s_main_1", session_key="k_main", agent_id="main")
    mgr.update_session(s_main.session_id, agent_id="main", message_count=1)
    s_coders = mgr.get_or_create_session(session_id="s_coders_1", session_key="k_coders", agent_id="coders")
    mgr.update_session(s_coders.session_id, agent_id="coders", message_count=9)

    _run_cli(["orbit", "sessions", "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    rows = data.get("sessions") or []
    by_sid = {r.get("sessionId"): r for r in rows}
    assert "s_main_1" in by_sid
    assert "s_coders_1" in by_sid
    assert by_sid["s_main_1"]["agentId"] == "main"
    assert by_sid["s_coders_1"]["agentId"] == "coders"

