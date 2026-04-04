"""``Orchestrator.reset_session``: clear orch transcript + new agent session ids."""

from __future__ import annotations

import asyncio
import json

import pytest

from orbit.agents.agent_manager import AgentManager
from orbit.agents.events.stream import EventStream
from orbit.agents.types import AgentPayload, AgentRunMeta, AgentRunResult, AgentRunStatus
from orbit.gateway.orch_trace import append_trace_events, orch_trace_file_path, read_trace_events
from orbit.gateway.orchestrator import Orchestrator


class _FakeRunner:
    def __init__(self) -> None:
        self.event_stream = EventStream()

    async def run(self, params):  # noqa: ANN001
        _ = params
        return AgentRunResult(
            payloads=[AgentPayload(text="ok")],
            meta=AgentRunMeta(duration_ms=0, status=AgentRunStatus.COMPLETED),
        )


@pytest.fixture()
def orch(tmp_path, monkeypatch) -> Orchestrator:
    monkeypatch.setenv("ORBIT_STATE_DIR", str(tmp_path / ".orbit"))
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ORBIT_CONFIG_DIR", str(cfg_dir))
    (cfg_dir / "orbit.json").write_text(json.dumps({"llm": {"provider": "echo"}}), encoding="utf-8")
    return Orchestrator(agent_manager=AgentManager(), runner=_FakeRunner())


@pytest.mark.asyncio
async def test_reset_clears_messages_regenerates_sessions_and_trace(orch: Orchestrator) -> None:
    st = orch.create(
        session_key="sk",
        name="t",
        participants=["main", "a2"],
        orch_trace_enabled=True,
    )
    oid = st.orchId
    pre_sess = dict(st.agentSessions)
    append_trace_events(oid, [{"type": "x", "payload": {}}], next_seq=0)

    orch.send(orch_id=oid, message="hello")
    for _ in range(200):
        await asyncio.sleep(0.05)
        cur = orch.get(oid)
        if cur and cur.status == "idle":
            break
    loaded = orch.get(oid)
    assert loaded is not None
    assert len(loaded.messages) >= 1
    assert read_trace_events(oid, limit=20)

    out = orch.reset_session(oid)
    assert out.messages == []
    assert out.status == "idle"
    assert out.currentRound == 0
    assert out.error is None
    assert out.orchTraceSeq == 0
    for k, v in pre_sess.items():
        assert out.agentSessions.get(k) != v

    again = orch.get(oid)
    assert again is not None
    assert again.messages == []
    assert read_trace_events(oid, limit=20) == []


def test_reset_refuses_while_running(orch: Orchestrator) -> None:
    st = orch.create(session_key="sk", name="t", participants=["main"])
    oid = st.orchId
    cur = orch.get(oid)
    assert cur is not None
    cur.status = "running"
    orch._save(cur)
    with pytest.raises(ValueError, match="running"):
        orch.reset_session(oid)
