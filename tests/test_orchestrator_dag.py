"""Orchestrator DAG create +调度（使用假 Runner，异步等待完成）。"""

from __future__ import annotations

import asyncio
import json

import pytest

from mw4agent.agents.agent_manager import AgentManager
from mw4agent.agents.types import AgentPayload, AgentRunMeta, AgentRunResult, AgentRunStatus
from mw4agent.gateway.orchestrator import Orchestrator


class _FakeRunner:
    async def run(self, params):  # noqa: ANN001
        _ = params
        return AgentRunResult(
            payloads=[AgentPayload(text="node-ok")],
            meta=AgentRunMeta(duration_ms=0, status=AgentRunStatus.COMPLETED),
        )


@pytest.fixture()
def orch(tmp_path, monkeypatch) -> Orchestrator:
    monkeypatch.setenv("MW4AGENT_STATE_DIR", str(tmp_path / ".mw4agent"))
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MW4AGENT_CONFIG_DIR", str(cfg_dir))
    (cfg_dir / "mw4agent.json").write_text(json.dumps({"llm": {"provider": "echo"}}), encoding="utf-8")
    return Orchestrator(agent_manager=AgentManager(), runner=_FakeRunner())


@pytest.mark.asyncio
async def test_dag_create_and_run_linear(orch: Orchestrator) -> None:
    st = orch.create(
        session_key="sk",
        name="t",
        participants=[],
        dag={
            "nodes": [
                {"id": "n1", "agentId": "main", "dependsOn": []},
                {"id": "n2", "agentId": "main", "dependsOn": ["n1"]},
            ],
            "parallelism": 1,
        },
    )
    assert st.strategy == "dag"
    assert st.dagSpec
    orch.send(orch_id=st.orchId, message="do work")
    for _ in range(100):
        await asyncio.sleep(0.05)
        cur = orch.get(st.orchId)
        if cur and cur.status in ("idle", "error"):
            break
    final = orch.get(st.orchId)
    assert final is not None
    assert final.status == "idle"
    assert final.error is None
    assistants = [m for m in final.messages if m.role == "assistant"]
    assert len(assistants) == 2
    assert {m.nodeId for m in assistants} == {"n1", "n2"}


def test_strategy_dag_without_spec_raises(orch: Orchestrator) -> None:
    with pytest.raises(ValueError, match="dag spec"):
        orch.create(session_key="s", name="", participants=["main"], strategy="dag")
