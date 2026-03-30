"""Tests for AgentManager.create_agent."""

from __future__ import annotations

from pathlib import Path

import pytest

from mw4agent.agents.agent_manager import AgentManager


def test_create_agent_writes_config_and_custom_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MW4AGENT_STATE_DIR", str(tmp_path / "mw_state"))
    monkeypatch.delenv("MW4AGENT_WORKSPACE_DIR", raising=False)

    am = AgentManager()
    ws = tmp_path / "custom_ws"
    cfg = am.create_agent(
        "demo_agent",
        workspace_dir=str(ws),
        llm={"provider": "openai", "model": "gpt-4o-mini"},
    )
    assert cfg.agent_id == "demo_agent"
    assert cfg.workspace_dir == str(ws.resolve())
    assert cfg.llm == {"provider": "openai", "model": "gpt-4o-mini"}

    again = am.get("demo_agent")
    assert again is not None
    assert again.workspace_dir == str(ws.resolve())

    with pytest.raises(ValueError, match="already exists"):
        am.create_agent("demo_agent")


def test_create_agent_rejects_invalid_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MW4AGENT_STATE_DIR", str(tmp_path / "mw_state2"))
    monkeypatch.delenv("MW4AGENT_WORKSPACE_DIR", raising=False)
    am = AgentManager()
    with pytest.raises(ValueError, match="must not contain"):
        am.create_agent("bad/id")


def test_create_agent_persists_avatar(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MW4AGENT_STATE_DIR", str(tmp_path / "mw_state_av"))
    monkeypatch.delenv("MW4AGENT_WORKSPACE_DIR", raising=False)
    am = AgentManager()
    cfg = am.create_agent("av_test", avatar="icon-a-124.png")
    assert cfg.avatar == "icon-a-124.png"
    again = am.get("av_test")
    assert again is not None
    assert again.avatar == "icon-a-124.png"


def test_create_agent_rejects_avatar_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MW4AGENT_STATE_DIR", str(tmp_path / "mw_state_av2"))
    monkeypatch.delenv("MW4AGENT_WORKSPACE_DIR", raising=False)
    am = AgentManager()
    with pytest.raises(ValueError, match="path"):
        am.create_agent("av_bad", avatar="../../etc/passwd")


def test_set_avatar_updates_and_clears(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MW4AGENT_STATE_DIR", str(tmp_path / "mw_state_sa"))
    monkeypatch.delenv("MW4AGENT_WORKSPACE_DIR", raising=False)
    am = AgentManager()
    am.create_agent("sa1", avatar="花生.png")
    u = am.set_avatar("sa1", avatar="牛人.png")
    assert u.avatar == "牛人.png"
    c = am.set_avatar("sa1", avatar="")
    assert c.avatar is None
