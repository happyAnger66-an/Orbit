"""
OpenClaw-compatible node-host WebSocket client.

Connects to a Gateway (e.g. OpenClaw), sends connect with role=node,
handles node.invoke.request (e.g. system.run) and replies with node.invoke.result.
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import uuid
from typing import Any, Dict, Optional

from .runner import run_system_run

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
DEFAULT_NODE_ID = "orbit-node"
DEFAULT_DISPLAY_NAME = "Orbit Node"
NODE_CAPS = ["system"]
NODE_COMMANDS = ["system.run.prepare", "system.run"]


def _connect_params(
    node_id: str,
    display_name: str,
    token: Optional[str],
) -> Dict[str, Any]:
    return {
        "minProtocol": PROTOCOL_VERSION,
        "maxProtocol": PROTOCOL_VERSION,
        "client": {
            "id": node_id,
            "displayName": display_name,
            "version": "0.1.0",
            "platform": platform.system().lower() or "unknown",
            "mode": "node",
        },
        "caps": NODE_CAPS,
        "commands": NODE_COMMANDS,
        "role": "node",
        "scopes": [],
        "auth": {"token": token} if token else None,
    }


def _handle_invoke_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle node.invoke.request payload; return result payload for node.invoke.result."""
    req_id = payload.get("id") or ""
    node_id = payload.get("nodeId") or ""
    command = payload.get("command") or ""
    params_json = payload.get("paramsJSON")
    if isinstance(params_json, str) and params_json.strip():
        try:
            params = json.loads(params_json)
        except json.JSONDecodeError:
            params = {}
    else:
        params = payload.get("params")
        if not isinstance(params, dict):
            params = {}

    if command == "system.run":
        result_payload = run_system_run(params)
        has_error = "error" in result_payload
        exit_ok = result_payload.get("exitCode", -1) == 0
        ok = not has_error and exit_ok
        return {
            "id": req_id,
            "nodeId": node_id,
            "ok": ok,
            "payload": result_payload,
            "payloadJSON": json.dumps(result_payload, ensure_ascii=False),
            "error": result_payload.get("error") if has_error else None,
        }
    if command == "system.run.prepare":
        # Minimal prepare: just echo back a plan so gateway/agent can proceed to system.run
        argv = params.get("command") or params.get("argv") or []
        if not isinstance(argv, list):
            argv = [str(argv)]
        cmd_text = " ".join(_quote_arg(a) for a in argv) if argv else ""
        plan = {
            "argv": argv,
            "commandText": cmd_text,
            "cwd": params.get("cwd"),
            "agentId": params.get("agentId"),
            "sessionKey": params.get("sessionKey"),
        }
        return {
            "id": req_id,
            "nodeId": node_id,
            "ok": True,
            "payload": {"plan": plan},
            "payloadJSON": json.dumps({"plan": plan}, ensure_ascii=False),
        }

    return {
        "id": req_id,
        "nodeId": node_id,
        "ok": False,
        "error": {"code": "UNKNOWN_COMMAND", "message": f"unsupported command: {command}"},
    }


def _quote_arg(s: str) -> str:
    if not s:
        return '""'
    if " " in s or "\"" in s or "'" in s:
        return json.dumps(s)
    return s


async def _run_loop(
    ws_url: str,
    node_id: str,
    display_name: str,
    token: Optional[str],
    reconnect_delay: float,
) -> None:
    try:
        import websockets
    except ImportError:
        raise RuntimeError("node-host requires the 'websockets' package. Install with: pip install websockets")

    while True:
        try:
            async with websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            ) as ws:
                logger.info("WebSocket connected to %s", ws_url)
                nonce: Optional[str] = None

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    if msg.get("type") == "event":
                        evt = msg.get("event")
                        payload = msg.get("payload") or {}
                        if evt == "connect.challenge":
                            nonce = (payload.get("nonce") or "").strip()
                            if not nonce:
                                logger.warning("connect.challenge missing nonce")
                                continue
                            connect_params = _connect_params(node_id, display_name, token)
                            req = {
                                "type": "req",
                                "id": str(uuid.uuid4()),
                                "method": "connect",
                                "params": connect_params,
                            }
                            await ws.send(json.dumps(req, ensure_ascii=False))
                            logger.info("Sent connect (role=node, nodeId=%s)", node_id)
                        elif evt == "node.invoke.request":
                            result = _handle_invoke_request(payload)
                            req = {
                                "type": "req",
                                "id": str(uuid.uuid4()),
                                "method": "node.invoke.result",
                                "params": result,
                            }
                            await ws.send(json.dumps(req, ensure_ascii=False))
                            logger.debug("Sent node.invoke.result id=%s ok=%s", result.get("id"), result.get("ok"))

                    elif msg.get("type") == "res":
                        res_id = msg.get("id")
                        ok = msg.get("ok") is True
                        if ok:
                            pl = msg.get("payload") or {}
                            if pl.get("type") == "hello-ok":
                                logger.info("Hello OK from gateway (connId=%s)", pl.get("server", {}).get("connId"))
                        else:
                            err = msg.get("error") or {}
                            logger.warning("Gateway response error id=%s code=%s message=%s", res_id, err.get("code"), err.get("message"))

        except Exception as e:
            logger.warning("Connection closed or error: %s", e)
        if reconnect_delay <= 0:
            break
        logger.info("Reconnecting in %.1fs...", reconnect_delay)
        await asyncio.sleep(reconnect_delay)


def run_node_host(
    ws_url: str,
    node_id: str = DEFAULT_NODE_ID,
    display_name: Optional[str] = None,
    token: Optional[str] = None,
    reconnect_delay: float = 5.0,
) -> None:
    """
    Run the node-host: connect to Gateway and handle node.invoke requests.
    Blocks until the event loop exits (e.g. Ctrl+C).
    """
    display_name = display_name or f"{DEFAULT_DISPLAY_NAME} ({node_id})"
    asyncio.run(
        _run_loop(
            ws_url=ws_url,
            node_id=node_id,
            display_name=display_name,
            token=token,
            reconnect_delay=reconnect_delay,
        )
    )
