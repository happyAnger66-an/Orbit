"""编排开启 ``orchTraceEnabled`` 时写入 ``trace.jsonl``（假 Runner + EventStream）。"""

from __future__ import annotations

import asyncio
import json

import pytest

from orbit.agents.agent_manager import AgentManager
from orbit.agents.events.stream import EventStream
from orbit.agents.types import AgentPayload, AgentRunMeta, AgentRunResult, AgentRunStatus
from orbit.gateway.orch_trace import read_trace_events
from orbit.gateway.orchestrator import Orchestrator


class _FakeRunner:
    """与 ``Orchestrator`` 订阅 ``event_stream`` 兼容。"""

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
async def test_trace_enabled_send_writes_user_and_agent_rows(orch: Orchestrator) -> None:
    st = orch.create(
        session_key="sk",
        name="t",
        participants=["main"],
        orch_trace_enabled=True,
    )
    oid = st.orchId
    assert st.orchTraceEnabled is True
    assert st.orchTraceSeq == 0

    orch.send(orch_id=oid, message="hi trace")

    for _ in range(200):
        await asyncio.sleep(0.05)
        cur = orch.get(oid)
        if cur and cur.status == "idle":
            break
    final = orch.get(oid)
    assert final is not None
    assert final.status == "idle"
    assert final.orchTraceSeq >= 1

    events = read_trace_events(oid, limit=50)
    types = [str(e.get("type") or "") for e in events]
    assert "user_message" in types
    assert "agent_input" in types
    assert "agent_output" in types


@pytest.mark.asyncio
async def test_trace_disabled_no_trace_file_rows(orch: Orchestrator) -> None:
    st = orch.create(session_key="sk", name="t", participants=["main"], orch_trace_enabled=False)
    oid = st.orchId
    orch.send(orch_id=oid, message="no trace")
    for _ in range(200):
        await asyncio.sleep(0.05)
        cur = orch.get(oid)
        if cur and cur.status == "idle":
            break
    assert read_trace_events(oid, after_seq=0, limit=20) == []
