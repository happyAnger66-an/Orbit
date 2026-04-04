"""Smoke test: agent tool -> gateway RPC (ls) roundtrip.

Run:
  python3 tests/test_gateway_tool_ls.py
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import urllib.request
import json

# Ensure local repo sources take precedence over any installed orbit package.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from orbit.agents.tools.gateway_tool import GatewayLsTool


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_health(base_url: str, deadline_s: float = 8.0) -> None:
    start = time.time()
    while time.time() - start < deadline_s:
        try:
            raw = urllib.request.urlopen(base_url + "/health", timeout=1.0).read().decode("utf-8")
            data = json.loads(raw)
            if data.get("ok") is True:
                return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError("gateway not healthy")


async def main_async() -> None:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    session_file = "/tmp/orbit.test.gateway.ls.sessions.json"

    cmd = [
        sys.executable,
        "-m",
        "orbit",
        "gateway",
        "run",
        "--bind",
        "127.0.0.1",
        "--port",
        str(port),
        "--session-file",
        session_file,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        _wait_health(base_url)
        tool = GatewayLsTool()
        # Ensure the tool uses our gateway instance
        result = await tool.execute("toolcall-1", {"path": "."}, context={"gateway_base_url": base_url})
        assert result.success is True, f"tool failed: {result.error} details={result.result}"
        payload = result.result or {}
        entries = payload.get("entries") if isinstance(payload, dict) else None
        assert isinstance(entries, list) and len(entries) > 0, f"unexpected entries: {payload}"
        # Expect repo has setup.py at root when listing '.'
        assert "setup.py" in entries, f"expected setup.py in entries, got: {entries[:20]}"
        print("[ok] gateway_ls tool returned entries")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    asyncio.run(main_async())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

