"""End-to-end smoke test for MW4Agent Gateway <-> Agent interaction.

What it does (OpenClaw-inspired semantics):
- Start gateway server on a free local port (subprocess)
- Probe /health
- Call /rpc agent (returns accepted + runId)
- Call /rpc agent.wait (returns ok|error|timeout) and assert ok
- Terminate gateway

This is intentionally a lightweight script-style test (stdlib only).

Run:
  python3 tests/test_gateway_agent_flow.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _http_get(url: str, timeout_s: float = 2.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _rpc_call(base_url: str, method: str, params: dict, timeout_s: float = 5.0) -> dict:
    body = {"id": str(uuid.uuid4()), "method": method, "params": params}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/rpc",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wait_for_health(base_url: str, deadline_s: float = 8.0) -> dict:
    start = time.time()
    last_err: Exception | None = None
    while time.time() - start < deadline_s:
        try:
            return _http_get(f"{base_url}/health", timeout_s=1.0)
        except Exception as e:
            last_err = e
            time.sleep(0.15)
    raise RuntimeError(f"gateway did not become healthy in time: {last_err}")


def main() -> int:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    session_file = "/tmp/mw4agent.test.gateway.sessions.json"

    # Start gateway in a subprocess (uses CLI to match real invocation)
    cmd = [
        sys.executable,
        "-m",
        "mw4agent",
        "gateway",
        "run",
        "--bind",
        "127.0.0.1",
        "--port",
        str(port),
        "--session-file",
        session_file,
    ]
    env = dict(os.environ)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    try:
        health = _wait_for_health(base_url)
        assert health.get("ok") is True, f"health not ok: {health}"

        idem = str(uuid.uuid4())
        agent_res = _rpc_call(
            base_url,
            "agent",
            {
                "message": "hello from test",
                "sessionKey": "rpc:test",
                "sessionId": "rpc-test",
                "agentId": "main",
                "idempotencyKey": idem,
                "deliver": False,
                "channel": "internal",
            },
            timeout_s=3.0,
        )
        assert agent_res.get("ok") is True, f"agent call failed: {agent_res}"
        payload = agent_res.get("payload") or {}
        run_id = payload.get("runId") or agent_res.get("runId")
        assert isinstance(run_id, str) and run_id, f"missing runId: {agent_res}"
        assert payload.get("status") == "accepted", f"unexpected agent status: {agent_res}"

        wait_res = _rpc_call(
            base_url,
            "agent.wait",
            {"runId": run_id, "timeoutMs": 5000},
            timeout_s=7.0,
        )
        assert wait_res.get("ok") is True, f"agent.wait failed: {wait_res}"
        wait_payload = wait_res.get("payload") or {}
        assert wait_payload.get("runId") == run_id, f"runId mismatch: {wait_res}"
        assert wait_payload.get("status") == "ok", f"expected ok, got: {wait_res}"

        print("[ok] gateway agent flow passed")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        if proc.stdout:
            # Drain remaining output for debugging, but keep it short.
            out = proc.stdout.read()
            if out:
                lines = out.strip().splitlines()
                tail = "\n".join(lines[-40:])
                print("\n[gateway output tail]\n" + tail)


if __name__ == "__main__":
    raise SystemExit(main())

