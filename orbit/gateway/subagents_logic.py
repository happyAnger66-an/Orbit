"""Pure logic for desktop ``/subagents`` (no FastAPI); used by ``subagents_cmd`` and tests."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class DesktopSubagentRecord:
    """A background run spawned from a parent session via ``/subagents spawn``."""

    run_id: str
    parent_agent_id: str
    parent_session_id: str
    parent_session_key: str
    child_session_id: str
    child_session_key: str
    target_agent_id: str
    task: str
    created_ms: int = field(default_factory=_now_ms)
    asyncio_task: Any = None
    status: str = "running"  # running|done|error|cancelled


def filter_subagents_for_parent(
    records: Iterable[Any],
    parent_agent_id: str,
    parent_session_id: str,
) -> List[DesktopSubagentRecord]:
    """Return matching records sorted by ``created_ms`` (oldest first)."""
    out: List[DesktopSubagentRecord] = []
    for r in records:
        if not isinstance(r, DesktopSubagentRecord):
            continue
        if r.parent_agent_id == parent_agent_id and r.parent_session_id == parent_session_id:
            out.append(r)
    out.sort(key=lambda x: x.created_ms)
    return out


def resolve_subagent_list_spec(
    records_sorted: List[DesktopSubagentRecord],
    spec: str,
) -> Optional[DesktopSubagentRecord]:
    """Resolve ``#N`` (1-based) or unique ``run_id`` prefix."""
    spec = (spec or "").strip()
    if not spec:
        return None
    if spec.startswith("#"):
        try:
            n = int(spec[1:].strip() or "0")
        except ValueError:
            return None
        if n < 1 or n > len(records_sorted):
            return None
        return records_sorted[n - 1]
    matches = [r for r in records_sorted if r.run_id.startswith(spec)]
    if len(matches) == 1:
        return matches[0]
    return None


def resolve_transcript_path_for_manager(session_manager: Any, session_id: str, agent_id: str) -> str:
    try:
        return session_manager.resolve_transcript_path(session_id, agent_id=agent_id)  # type: ignore[call-arg]
    except TypeError:
        return session_manager.resolve_transcript_path(session_id)


def subagents_help_markdown() -> str:
    return (
        "**子智能体（/subagents）** — 绑定当前主会话（派活框的 agent + session）。\n\n"
        "- `/subagents list` — 列出从本会话派生的子运行\n"
        "- `/subagents spawn <agentId> <任务…>` — 后台启动子会话（独立 transcript，可与主会话并行）\n"
        "- `/subagents info <#序号|runId前缀>` — 查看一条记录\n"
        "- `/subagents kill <#|runId前缀|all>` — 尽力取消子运行\n"
        "- `/subagents log <#|runId前缀> [行数]` — 查看子会话 transcript 尾部（默认 40 行）\n\n"
        "子运行完成后状态变为 done/error；主聊天不会自动插入子结果，请用 `list` / `log` 查看。"
    )


def read_text_file_tail(path: str, max_lines: int) -> str:
    """Read last ``max_lines`` lines (clamped 1..500); on error return parenthetical message."""
    max_lines = max(1, min(int(max_lines), 500))
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        return f"(无法读取 transcript: {e})"
    tail = lines[-max_lines:]
    return "".join(tail).strip() or "(空)"
