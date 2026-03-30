from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..agents.agent_manager import AgentManager
from ..agents.runner.runner import AgentRunner
from ..agents.types import AgentRunParams
from ..config.paths import get_state_dir, normalize_agent_id
from ..llm.backends import _call_openai_chat, _thinking_extra_body, list_providers  # type: ignore
from ..memory.bootstrap import load_bootstrap_system_prompt

from .dag_spec import MAX_UPSTREAM_SNIPPET, normalize_dag_dict


def _now_ms() -> int:
    return int(time.time() * 1000)


def _orchestrations_root_dir() -> str:
    return os.path.join(get_state_dir(), "orchestrations")


def _orch_dir(orch_id: str) -> str:
    return os.path.join(_orchestrations_root_dir(), orch_id)


def _orch_state_path(orch_id: str) -> str:
    return os.path.join(_orch_dir(orch_id), "orch.json")


@dataclass
class OrchMessage:
    id: str
    ts: int
    round: int
    speaker: str  # "user" or agentId
    role: str  # "user"|"assistant"
    text: str
    nodeId: str = ""  # DAG node id when strategy=dag and role=assistant


@dataclass
class OrchState:
    orchId: str
    sessionKey: str
    createdAt: int
    updatedAt: int
    status: str  # idle|running|error|aborted
    name: str = ""
    strategy: str = "round_robin"  # round_robin|router_llm|dag
    maxRounds: int = 8  # round_robin: assistant turns per user message; dag: largely ignored (one run per node)
    routerLlm: Optional[Dict[str, str]] = None
    participants: List[str] = field(default_factory=list)
    agentSessions: Dict[str, str] = field(default_factory=dict)  # agentId -> sessionId
    currentRound: int = 0
    messages: List[OrchMessage] = field(default_factory=list)
    error: Optional[str] = None
    orchSchemaVersion: int = 1
    dagSpec: Optional[Dict[str, Any]] = None  # normalized {nodes, parallelism}; optional position per node for Web editor
    dagProgress: Optional[Dict[str, Any]] = None  # nodeId -> {status, outputPreview, error?}
    dagParallelism: int = 4
    dagNodeSessions: Dict[str, str] = field(default_factory=dict)  # DAG node id -> sessionId


class Orchestrator:
    def __init__(self, *, agent_manager: AgentManager, runner: AgentRunner) -> None:
        self.agent_manager = agent_manager
        self.runner = runner
        self._tasks: Dict[str, asyncio.Task] = {}

    def _save(self, st: OrchState) -> None:
        st.updatedAt = _now_ms()
        root = Path(_orch_dir(st.orchId))
        root.mkdir(parents=True, exist_ok=True)
        payload = asdict(st)
        ds = payload.get("dagSpec")
        if isinstance(ds, dict):
            payload["dagSpec"] = {k: v for k, v in ds.items() if k != "topologicalOrder"}
        Path(_orch_state_path(st.orchId)).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _load(self, orch_id: str) -> Optional[OrchState]:
        p = Path(_orch_state_path(orch_id))
        if not p.is_file():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        msgs_raw = data.get("messages") if isinstance(data.get("messages"), list) else []
        msgs: List[OrchMessage] = []
        for m in msgs_raw:
            if not isinstance(m, dict):
                continue
            msgs.append(
                OrchMessage(
                    id=str(m.get("id") or ""),
                    ts=int(m.get("ts") or 0) or 0,
                    round=int(m.get("round") or 0) or 0,
                    speaker=str(m.get("speaker") or ""),
                    role=str(m.get("role") or ""),
                    text=str(m.get("text") or ""),
                    nodeId=str(m.get("nodeId") or m.get("node_id") or ""),
                )
            )
        dag_raw = data.get("dagSpec")
        dag_spec: Optional[Dict[str, Any]] = dict(dag_raw) if isinstance(dag_raw, dict) else None
        dag_prog = data.get("dagProgress")
        dag_progress: Optional[Dict[str, Any]] = dict(dag_prog) if isinstance(dag_prog, dict) else None
        dns = data.get("dagNodeSessions")
        dag_node_sess: Dict[str, str] = dict(dns) if isinstance(dns, dict) else {}
        try:
            dpar = int(data.get("dagParallelism") or data.get("dag_parallelism") or 4)
        except (TypeError, ValueError):
            dpar = 4
        dpar = max(1, min(32, dpar))
        try:
            osv = int(data.get("orchSchemaVersion") or 1)
        except (TypeError, ValueError):
            osv = 1
        return OrchState(
            orchId=str(data.get("orchId") or orch_id),
            sessionKey=str(data.get("sessionKey") or ""),
            createdAt=int(data.get("createdAt") or 0) or 0,
            updatedAt=int(data.get("updatedAt") or 0) or 0,
            status=str(data.get("status") or ""),
            name=str(data.get("name") or ""),
            strategy=str(data.get("strategy") or "round_robin"),
            maxRounds=int(data.get("maxRounds") or 8) or 8,
            routerLlm=dict(data.get("routerLlm") or {}) or None,
            participants=[str(x) for x in (data.get("participants") or []) if str(x).strip()],
            agentSessions=dict(data.get("agentSessions") or {}),
            currentRound=int(data.get("currentRound") or 0) or 0,
            messages=msgs,
            error=str(data.get("error") or "") or None,
            orchSchemaVersion=osv,
            dagSpec=dag_spec,
            dagProgress=dag_progress,
            dagParallelism=dpar,
            dagNodeSessions=dag_node_sess,
        )

    def get(self, orch_id: str) -> Optional[OrchState]:
        return self._load(orch_id)

    def delete(self, orch_id: str) -> bool:
        """Delete an orchestration directory and all persisted state."""
        oid = (orch_id or "").strip()
        if not oid:
            raise ValueError("orchId is required")
        root = Path(_orch_dir(oid)).resolve()
        if not root.exists():
            return False
        if not root.is_dir():
            raise ValueError("orchestration path is not a directory")
        # Safety: ensure under orchestrations root
        base = Path(_orchestrations_root_dir()).resolve()
        if base != root and base not in root.parents:
            raise ValueError("refusing to delete path outside orchestrations root")
        shutil.rmtree(root)
        return True

    def is_running(self, orch_id: str) -> bool:
        st = self._load(orch_id)
        return bool(st and st.status == "running")

    def list(self) -> List[OrchState]:
        root = Path(_orchestrations_root_dir())
        if not root.exists() or not root.is_dir():
            return []
        items: List[OrchState] = []
        for p in root.iterdir():
            if not p.is_dir():
                continue
            st = self._load(p.name)
            if st:
                items.append(st)
        items.sort(key=lambda s: int(s.updatedAt or 0), reverse=True)
        return items

    def create(
        self,
        *,
        session_key: str,
        name: str,
        participants: List[str],
        max_rounds: int = 8,
        strategy: str = "round_robin",
        router_llm: Optional[Dict[str, str]] = None,
        dag: Optional[Dict[str, Any]] = None,
    ) -> OrchState:
        orch_id = str(uuid.uuid4())
        strat = (strategy or "round_robin").strip() or "round_robin"
        dag_spec: Optional[Dict[str, Any]] = None
        dag_progress: Optional[Dict[str, Any]] = None
        dag_parallelism = 4
        dag_node_sess: Dict[str, str] = {}

        if dag is not None:
            dag_spec = normalize_dag_dict(dag if isinstance(dag, dict) else {})
            strat = "dag"
            dag_parallelism = int(dag_spec.get("parallelism") or 4)
            parts = sorted(
                {normalize_agent_id(n["agentId"]) for n in dag_spec["nodes"]},
                key=lambda x: x,
            )
            if not parts:
                parts = ["main"]
            dag_progress = {
                str(n["id"]): {"status": "pending", "outputPreview": ""} for n in dag_spec["nodes"]
            }
            dag_node_sess = {str(n["id"]): str(uuid.uuid4()) for n in dag_spec["nodes"]}
            agent_sess = {p: str(uuid.uuid4()) for p in parts}
        else:
            if strat.lower() == "dag":
                raise ValueError("dag spec is required when strategy is dag")
            parts = [normalize_agent_id(x) for x in participants if str(x).strip()]
            parts = [p for i, p in enumerate(parts) if p and p not in parts[:i]]
            if not parts:
                parts = ["main"]
            agent_sess = {p: str(uuid.uuid4()) for p in parts}

        now = _now_ms()
        st = OrchState(
            orchId=orch_id,
            sessionKey=session_key,
            createdAt=now,
            updatedAt=now,
            status="idle",
            name=(name or "").strip(),
            strategy=strat,
            maxRounds=max(1, int(max_rounds or 8)),
            routerLlm=(dict(router_llm) if isinstance(router_llm, dict) and router_llm else None),
            participants=parts,
            agentSessions=agent_sess,
            currentRound=0,
            messages=[],
            orchSchemaVersion=1,
            dagSpec=dag_spec,
            dagProgress=dag_progress,
            dagParallelism=dag_parallelism,
            dagNodeSessions=dag_node_sess,
        )
        self._save(st)
        return st

    def run(
        self,
        *,
        session_key: str,
        message: str,
        participants: List[str],
        max_rounds: int = 8,
        strategy: str = "round_robin",
        router_llm: Optional[Dict[str, str]] = None,
        dag: Optional[Dict[str, Any]] = None,
    ) -> OrchState:
        # Back-compat: create + send
        st = self.create(
            session_key=session_key,
            name="",
            participants=participants,
            max_rounds=max_rounds,
            strategy=strategy,
            router_llm=router_llm,
            dag=dag,
        )
        self.send(orch_id=st.orchId, message=message)
        return self._load(st.orchId) or st

    def send(self, *, orch_id: str, message: str) -> OrchState:
        st = self._load(orch_id)
        if not st:
            raise ValueError("orchestration not found")
        if st.status == "running":
            raise ValueError("orchestration is running")
        text = (message or "").strip()
        if not text:
            raise ValueError("message required")
        st.status = "running"
        st.error = None
        if (st.strategy or "").strip() == "dag" and st.dagSpec and isinstance(st.dagSpec.get("nodes"), list):
            nodes_raw = st.dagSpec["nodes"]
            st.dagProgress = {
                str(n.get("id") or ""): {"status": "pending", "outputPreview": ""}
                for n in nodes_raw
                if isinstance(n, dict) and str(n.get("id") or "").strip()
            }
        st.messages.append(
            OrchMessage(
                id=str(uuid.uuid4()),
                ts=_now_ms(),
                round=st.currentRound,
                speaker="user",
                role="user",
                text=text,
            )
        )
        self._save(st)
        self._start_background(st.orchId)
        return st

    def _start_background(self, orch_id: str) -> None:
        if orch_id in self._tasks and not self._tasks[orch_id].done():
            return

        st0 = self._load(orch_id)
        if st0 and (st0.strategy or "").strip() == "dag":
            self._tasks[orch_id] = asyncio.create_task(self._task_dag(orch_id))
            return

        async def _task_linear() -> None:
            st = self._load(orch_id)
            if not st:
                return
            if st.status != "running":
                return
            try:
                last_text = st.messages[-1].text if st.messages else ""
                start_round = int(st.currentRound or 0)
                target_round = start_round + int(st.maxRounds or 8)
                for r in range(start_round, target_round):
                    st = self._load(orch_id)
                    if not st or st.status != "running":
                        return
                    # Speaker selection (phase A):
                    # - round_robin: deterministic rotation
                    # - router_llm: choose via LLM if configured, else fallback to round_robin
                    agent_id = st.participants[r % max(1, len(st.participants))]
                    if (st.strategy or "").strip() == "router_llm" and st.routerLlm:
                        try:
                            router = st.routerLlm
                            agent_list = ", ".join(st.participants)
                            prompt = (
                                "You are a router for a multi-agent team.\n"
                                f"Candidates: [{agent_list}]\n"
                                "Pick exactly ONE next speaker from candidates. Return ONLY the agent id.\n\n"
                                f"Conversation last message:\n{last_text}\n"
                            )
                            provider = (router.get("provider") or "").strip() or "openai"
                            model = (router.get("model") or "").strip() or "gpt-4o-mini"
                            base_url = (router.get("base_url") or router.get("baseUrl") or "").strip()
                            api_key = (router.get("api_key") or router.get("apiKey") or "").strip()
                            thinking_level = (router.get("thinking_level") or router.get("thinkingLevel") or "").strip()
                            if provider not in ("", "echo") and provider not in list_providers():
                                # Still allow "openai" even if not registered in list_providers() (it is).
                                provider = "openai"
                            # Router uses a minimal OpenAI-compatible caller.
                            reply, _usage = await asyncio.to_thread(
                                _call_openai_chat,
                                prompt,
                                model=model,
                                api_key=api_key or "none",
                                base_url=base_url or "https://api.openai.com",
                                extra_body=_thinking_extra_body(provider, thinking_level),
                            )
                            pick = (reply or "").strip().splitlines()[0].strip().strip("`").strip()
                            if pick in st.participants:
                                agent_id = pick
                        except Exception:
                            pass
                    session_id = st.agentSessions.get(agent_id) or str(uuid.uuid4())
                    st.agentSessions[agent_id] = session_id

                    cfg = self.agent_manager.get_or_create(agent_id)
                    workspace_dir = cfg.workspace_dir
                    bootstrap = load_bootstrap_system_prompt(workspace_dir)
                    orch_hint = (
                        "You are part of a multi-agent orchestration.\n"
                        "Reply concisely, and include actionable outputs.\n"
                    )
                    extra_system_prompt = f"{bootstrap}\n\n{orch_hint}".strip() if bootstrap else orch_hint

                    result = await self.runner.run(
                        AgentRunParams(
                            message=last_text,
                            run_id=str(uuid.uuid4()),
                            session_key=f"orch:{orch_id}",
                            session_id=session_id,
                            agent_id=agent_id,
                            channel="orchestrator",
                            deliver=False,
                            extra_system_prompt=extra_system_prompt,
                            workspace_dir=workspace_dir,
                        )
                    )
                    out_text = "\n".join([p.text or "" for p in result.payloads if (p.text or "").strip()]).strip()
                    if not out_text:
                        out_text = "(no output)"
                    last_text = out_text

                    st = self._load(orch_id)
                    if not st:
                        return
                    st.currentRound = r + 1
                    st.messages.append(
                        OrchMessage(
                            id=str(uuid.uuid4()),
                            ts=_now_ms(),
                            round=r + 1,
                            speaker=agent_id,
                            role="assistant",
                            text=out_text,
                        )
                    )
                    self._save(st)

                st = self._load(orch_id)
                if st and st.status == "running":
                    st.status = "idle"
                    self._save(st)
            except Exception as e:
                st = self._load(orch_id)
                if st:
                    st.status = "error"
                    st.error = str(e)
                    self._save(st)

        self._tasks[orch_id] = asyncio.create_task(_task_linear())

    async def _run_single_dag_node(
        self,
        orch_id: str,
        *,
        nid: str,
        node: Dict[str, Any],
        orig_user_message: str,
        outputs: Dict[str, str],
        wave: int,
    ) -> str:
        """Execute one DAG node; returns assistant text (may raise)."""
        agent_id = normalize_agent_id(str(node.get("agentId") or "main"))
        parts: List[str] = [f"[Orchestration task]\n{orig_user_message}\n"]
        for dep in node.get("dependsOn") or []:
            ds = str(dep).strip()
            raw = (outputs.get(ds) or "").strip()
            snippet = raw[:MAX_UPSTREAM_SNIPPET] if raw else "(no output)"
            parts.append(f"\n## Upstream node `{ds}`\n{snippet}\n")
        full_message = "".join(parts)

        st = self._load(orch_id)
        if not st:
            return "(no state)"
        session_id = (st.dagNodeSessions or {}).get(nid) or str(uuid.uuid4())
        st.dagNodeSessions[nid] = session_id
        self._save(st)

        cfg = self.agent_manager.get_or_create(agent_id)
        workspace_dir = cfg.workspace_dir
        bootstrap = load_bootstrap_system_prompt(workspace_dir)
        orch_hint = (
            "You are part of a multi-agent DAG orchestration.\n"
            f"Current node id: {nid!r}. Reply concisely with actionable output.\n"
        )
        extra_system_prompt = f"{bootstrap}\n\n{orch_hint}".strip() if bootstrap else orch_hint

        result = await self.runner.run(
            AgentRunParams(
                message=full_message,
                run_id=str(uuid.uuid4()),
                session_key=f"orch:{orch_id}",
                session_id=session_id,
                agent_id=agent_id,
                channel="orchestrator",
                deliver=False,
                extra_system_prompt=extra_system_prompt,
                workspace_dir=workspace_dir,
            )
        )
        out_text = "\n".join([p.text or "" for p in result.payloads if (p.text or "").strip()]).strip()
        if not out_text:
            out_text = "(no output)"
        return out_text

    async def _task_dag(self, orch_id: str) -> None:
        try:
            st = self._load(orch_id)
            if not st or st.status != "running" or not st.dagSpec:
                return
            try:
                spec = normalize_dag_dict(dict(st.dagSpec))
            except ValueError as e:
                st = self._load(orch_id)
                if st:
                    st.status = "error"
                    st.error = str(e)
                    self._save(st)
                return

            nodes = spec["nodes"]
            nodes_by_id = {str(n["id"]): n for n in nodes}
            all_ids = sorted(nodes_by_id.keys(), key=lambda x: x)
            children: Dict[str, List[str]] = {i: [] for i in all_ids}
            rem: Dict[str, int] = {i: 0 for i in all_ids}
            for nid, n in nodes_by_id.items():
                deps = [str(d).strip() for d in (n.get("dependsOn") or []) if str(d).strip()]
                rem[nid] = len(deps)
                for d in deps:
                    if d in children:
                        children[d].append(nid)

            user_msgs = [m for m in st.messages if m.role == "user"]
            orig_user_message = user_msgs[-1].text if user_msgs else ""

            outputs: Dict[str, str] = {}
            pending = set(all_ids)
            wave = 0
            par = max(1, min(32, int(st.dagParallelism or spec.get("parallelism") or 4)))
            sem = asyncio.Semaphore(par)

            while pending:
                ready = sorted([nid for nid in pending if rem.get(nid, 0) == 0])
                if not ready:
                    st = self._load(orch_id)
                    if st:
                        st.status = "error"
                        st.error = "dag scheduling stuck (cycle or invalid state)"
                        self._save(st)
                    return
                wave += 1

                async def _bound(nid: str) -> tuple:
                    async with sem:
                        st2 = self._load(orch_id)
                        if not st2 or st2.status != "running":
                            return nid, None, "aborted"
                        prog = st2.dagProgress or {}
                        ent = dict(prog.get(nid) or {})
                        ent["status"] = "running"
                        prog[nid] = ent
                        st2.dagProgress = prog
                        self._save(st2)
                        try:
                            text = await self._run_single_dag_node(
                                orch_id,
                                nid=nid,
                                node=nodes_by_id[nid],
                                orig_user_message=orig_user_message,
                                outputs=outputs,
                                wave=wave,
                            )
                            return nid, text, None
                        except Exception as ex:
                            return nid, None, str(ex)

                batch = await asyncio.gather(*[_bound(nid) for nid in ready])
                for item in batch:
                    nid, text, err = item
                    if err:
                        st = self._load(orch_id)
                        if st:
                            st.status = "error"
                            st.error = err or f"node {nid} failed"
                            prog = dict(st.dagProgress or {})
                            prog[nid] = {
                                "status": "error",
                                "outputPreview": "",
                                "error": err,
                            }
                            st.dagProgress = prog
                            self._save(st)
                        return
                    assert text is not None
                    outputs[nid] = text
                    st = self._load(orch_id)
                    if not st or st.status != "running":
                        return
                    preview = text[:2000]
                    prog = dict(st.dagProgress or {})
                    prog[nid] = {"status": "done", "outputPreview": preview, "error": ""}
                    st.dagProgress = prog
                    st.currentRound = wave
                    agent_id = normalize_agent_id(str(nodes_by_id[nid].get("agentId") or "main"))
                    st.messages.append(
                        OrchMessage(
                            id=str(uuid.uuid4()),
                            ts=_now_ms(),
                            round=wave,
                            speaker=agent_id,
                            role="assistant",
                            text=text,
                            nodeId=nid,
                        )
                    )
                    self._save(st)
                    pending.discard(nid)
                    for c in children.get(nid) or []:
                        rem[c] = max(0, rem.get(c, 0) - 1)

            st = self._load(orch_id)
            if st and st.status == "running":
                st.status = "idle"
                self._save(st)
        except Exception as e:
            st = self._load(orch_id)
            if st:
                st.status = "error"
                st.error = str(e)
                self._save(st)

