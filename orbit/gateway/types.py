"""Gateway protocol types (minimal)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


JsonRpcId = str


@dataclass(frozen=True)
class RpcRequest:
    id: JsonRpcId
    method: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RpcError:
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class RpcResponse:
    id: JsonRpcId
    ok: bool
    payload: Optional[Dict[str, Any]] = None
    error: Optional[RpcError] = None
    run_id: Optional[str] = None


LifecyclePhase = Literal["start", "end", "error"]


@dataclass
class AgentEvent:
    """Event broadcast over WS."""

    run_id: str
    stream: Literal["lifecycle", "assistant", "tool"]
    data: Dict[str, Any] = field(default_factory=dict)
    seq: int = 0
    ts: int = 0

