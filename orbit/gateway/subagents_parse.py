"""Pure parsing helpers for ``/subagents`` (no FastAPI / gateway imports)."""

from __future__ import annotations

import shlex
from typing import List, Tuple


def is_subagents_command_line(message: str) -> bool:
    raw = (message or "").strip()
    if not raw:
        return False
    return raw.split(None, 1)[0].lower() == "/subagents"


def split_subagents_args(rest: str) -> List[str]:
    rest = (rest or "").strip()
    if not rest:
        return []
    return shlex.split(rest)


def parse_spawn_agent_and_task(args: List[str]) -> Tuple[str, str]:
    """After verb ``spawn``, args are [agentId, ...task parts]."""
    if len(args) < 2:
        raise ValueError("用法: `/subagents spawn <agentId> <任务…>`")
    aid = args[0].strip()
    task = " ".join(args[1:]).strip()
    if not aid or not task:
        raise ValueError("agentId 与任务不能为空")
    return aid, task
