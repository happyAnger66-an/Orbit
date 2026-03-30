"""Gateway RPC agent.session.history — resume desktop chat from stored transcript."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient


@pytest.fixture()
def gateway_client(tmp_path, monkeypatch):
    monkeypatch.setenv("MW4AGENT_STATE_DIR", str(tmp_path / ".mw4agent"))
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MW4AGENT_CONFIG_DIR", str(cfg_dir))
    (cfg_dir / "mw4agent.json").write_text(json.dumps({"llm": {"provider": "echo"}}), encoding="utf-8")

    from mw4agent.gateway.server import create_app

    app = create_app(session_file="")
    with TestClient(app) as client:
        yield client


def _write_main_session_with_transcript(*, state_root: Path, session_id: str) -> None:
    main_sessions = state_root / "agents" / "main" / "sessions"
    main_sessions.mkdir(parents=True, exist_ok=True)
    store = {
        "sessions": [
            {
                "session_id": session_id,
                "session_key": "desktop-app",
                "agent_id": "main",
                "created_at": 1700000000000,
                "updated_at": 1700000000001,
                "message_count": 2,
                "total_tokens": 0,
                "metadata": {},
            }
        ]
    }
    (main_sessions / "sessions.json").write_text(
        json.dumps(store, ensure_ascii=False), encoding="utf-8"
    )
    transcript = main_sessions / f"{session_id}.jsonl"
    lines = [
        json.dumps(
            {
                "type": "session",
                "version": 2,
                "id": session_id,
                "timestamp": "2026-01-01T00:00:00+00:00",
                "cwd": "/tmp",
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {"id": "u1", "parentId": None, "message": {"role": "user", "content": "prior ask"}},
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "id": "a1",
                "parentId": "u1",
                "message": {"role": "assistant", "content": "prior answer"},
            },
            ensure_ascii=False,
        ),
        json.dumps({"type": "leaf", "leafId": "a1"}, ensure_ascii=False),
    ]
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_agent_session_history_returns_messages_and_session_id(
    gateway_client: TestClient, tmp_path
) -> None:
    state_root = tmp_path / ".mw4agent"
    sid = "shist1"
    _write_main_session_with_transcript(state_root=state_root, session_id=sid)

    res = gateway_client.post(
        "/rpc",
        json={
            "id": "h1",
            "method": "agent.session.history",
            "params": {"agentId": "main", "sessionKey": "desktop-app"},
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True
    payload = body.get("payload") or {}
    assert payload.get("sessionId") == sid
    msgs = payload.get("messages") or []
    assert len(msgs) == 2
    assert msgs[0] == {"role": "user", "text": "prior ask"}
    assert msgs[1] == {"role": "assistant", "text": "prior answer"}


def test_agent_session_history_falls_back_from_desktop_app_to_main_session_key(
    gateway_client: TestClient, tmp_path
) -> None:
    """Legacy RPC used default sessionKey 'main'; UI queries 'desktop-app' — history should still resolve."""
    state_root = tmp_path / ".mw4agent"
    sid = "slegacy-main"
    main_sessions = state_root / "agents" / "main" / "sessions"
    main_sessions.mkdir(parents=True, exist_ok=True)
    store = {
        "sessions": [
            {
                "session_id": sid,
                "session_key": "main",
                "agent_id": "main",
                "created_at": 1700000000000,
                "updated_at": 1700000000001,
                "message_count": 1,
                "total_tokens": 0,
                "metadata": {},
            }
        ]
    }
    (main_sessions / "sessions.json").write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    lines = [
        json.dumps(
            {"type": "session", "version": 2, "id": sid, "timestamp": "2026-01-01T00:00:00+00:00", "cwd": "/tmp"},
            ensure_ascii=False,
        ),
        json.dumps(
            {"id": "u1", "parentId": None, "message": {"role": "user", "content": "from main key"}},
            ensure_ascii=False,
        ),
        json.dumps(
            {"id": "a1", "parentId": "u1", "message": {"role": "assistant", "content": "reply"}},
            ensure_ascii=False,
        ),
        json.dumps({"type": "leaf", "leafId": "a1"}, ensure_ascii=False),
    ]
    (main_sessions / f"{sid}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    res = gateway_client.post(
        "/rpc",
        json={
            "id": "h3",
            "method": "agent.session.history",
            "params": {"agentId": "main", "sessionKey": "desktop-app"},
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True
    payload = body.get("payload") or {}
    assert payload.get("sessionId") == sid
    msgs = payload.get("messages") or []
    assert len(msgs) == 2
    assert msgs[0]["text"] == "from main key"


def test_agent_session_history_empty_when_no_session(gateway_client: TestClient) -> None:
    res = gateway_client.post(
        "/rpc",
        json={
            "id": "h2",
            "method": "agent.session.history",
            "params": {"agentId": "main", "sessionKey": "desktop-app"},
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True
    payload = body.get("payload") or {}
    assert payload.get("sessionId") is None
    assert payload.get("messages") == []
