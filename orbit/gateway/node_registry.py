"""In-memory node registry: track connected nodes (role=node) and forward node.invoke."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from fastapi import WebSocket


@dataclass
class NodeSession:
    node_id: str
    ws: WebSocket
    conn_id: str
    display_name: Optional[str] = None
    platform: Optional[str] = None
    caps: list = field(default_factory=list)
    commands: list = field(default_factory=list)
    connected_at_ms: int = 0


@dataclass
class PendingInvoke:
    node_id: str
    request_id: str
    future: asyncio.Future
    timer: Any = None  # asyncio.Handle from loop.call_later


class NodeRegistry:
    """Registry of connected nodes; supports invoke with timeout and result callback."""

    def __init__(self) -> None:
        self._by_id: Dict[str, NodeSession] = {}
        self._by_conn: Dict[str, str] = {}  # conn_id -> node_id
        self._pending: Dict[str, PendingInvoke] = {}  # request_id -> PendingInvoke

    def register(
        self,
        ws: WebSocket,
        *,
        node_id: str,
        conn_id: str,
        display_name: Optional[str] = None,
        platform: Optional[str] = None,
        caps: Optional[list] = None,
        commands: Optional[list] = None,
    ) -> NodeSession:
        session = NodeSession(
            node_id=node_id,
            ws=ws,
            conn_id=conn_id,
            display_name=display_name,
            platform=platform,
            caps=caps or [],
            commands=commands or [],
            connected_at_ms=int(time.time() * 1000),
        )
        self._by_id[node_id] = session
        self._by_conn[conn_id] = node_id
        return session

    def unregister(self, conn_id: str) -> Optional[str]:
        node_id = self._by_conn.pop(conn_id, None)
        if not node_id:
            return None
        self._by_id.pop(node_id, None)
        # Fail any pending invokes for this node
        for rid, pending in list(self._pending.items()):
            if pending.node_id == node_id:
                if pending.timer:
                    pending.timer.cancel()
                self._pending.pop(rid, None)
                if not pending.future.done():
                    pending.future.set_exception(ConnectionError(f"node {node_id} disconnected"))
        return node_id

    def get(self, node_id: str) -> Optional[NodeSession]:
        return self._by_id.get(node_id)

    def list_connected(self) -> list[Dict[str, Any]]:
        out = []
        for s in self._by_id.values():
            out.append({
                "nodeId": s.node_id,
                "displayName": s.display_name,
                "platform": s.platform,
                "caps": s.caps,
                "commands": s.commands,
                "connectedAtMs": s.connected_at_ms,
                "connected": True,
            })
        return out

    async def send_event(self, node_id: str, event: str, payload: Any) -> bool:
        session = self._by_id.get(node_id)
        if not session:
            return False
        try:
            await session.ws.send_text(
                json.dumps({"type": "event", "event": event, "payload": payload}, ensure_ascii=False)
            )
            return True
        except Exception:
            return False

    async def invoke(
        self,
        node_id: str,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        timeout_ms: int = 30_000,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send node.invoke.request to node and wait for node.invoke.result."""
        session = self._by_id.get(node_id)
        if not session:
            return {
                "ok": False,
                "error": {"code": "NOT_CONNECTED", "message": "node not connected"},
            }
        request_id = str(uuid.uuid4())
        payload = {
            "id": request_id,
            "nodeId": node_id,
            "command": command,
            "paramsJSON": json.dumps(params or {}, ensure_ascii=False) if params else None,
            "timeoutMs": timeout_ms,
            "idempotencyKey": idempotency_key or request_id,
        }
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Dict[str, Any]] = loop.create_future()
        pending = PendingInvoke(node_id=node_id, request_id=request_id, future=future)

        def on_timeout() -> None:
            if request_id in self._pending:
                self._pending.pop(request_id, None)
            if not future.done():
                future.set_result({
                    "ok": False,
                    "error": {"code": "TIMEOUT", "message": "node invoke timed out"},
                })

        pending.timer = loop.call_later(max(0.001, timeout_ms / 1000.0), on_timeout)
        self._pending[request_id] = pending

        sent = await self.send_event(node_id, "node.invoke.request", payload)
        if not sent:
            pending.timer.cancel()
            self._pending.pop(request_id, None)
            return {
                "ok": False,
                "error": {"code": "UNAVAILABLE", "message": "failed to send invoke to node"},
            }

        try:
            return await asyncio.wait_for(future, timeout=timeout_ms / 1000.0 + 2.0)
        except asyncio.TimeoutError:
            return {
                "ok": False,
                "error": {"code": "TIMEOUT", "message": "node invoke timed out"},
            }

    def handle_invoke_result(
        self,
        request_id: str,
        node_id: str,
        ok: bool,
        payload: Optional[Dict[str, Any]] = None,
        payload_json: Optional[str] = None,
        error: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Called when node sends node.invoke.result; completes the pending invoke."""
        pending = self._pending.pop(request_id, None)
        if not pending or pending.node_id != node_id:
            return False
        if pending.timer:
            pending.timer.cancel()
        result: Dict[str, Any] = {
            "ok": ok,
            "payload": payload,
            "payloadJSON": payload_json,
            "error": error,
        }
        if not pending.future.done():
            pending.future.set_result(result)
        return True
