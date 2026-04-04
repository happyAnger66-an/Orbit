from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

# Ensure local repo sources take precedence over any installed orbit package.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_health(base_url: str, deadline_s: float = 10.0) -> None:
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


def _rpc(base_url: str, method: str, params: dict) -> dict:
    body = {"id": f"t-{method}-{int(time.time()*1000)}", "method": method, "params": params or {}}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=base_url + "/rpc",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    raw = urllib.request.urlopen(req, timeout=5.0).read().decode("utf-8")
    return json.loads(raw)


def test_dashboard_config_sections_rpc_e2e(tmp_path):
    """E2E: start gateway, list/get/set config sections via RPC.

    This covers dashboard sub-config tabs: config.sections.list / config.section.get / config.section.set.
    """
    # Create an isolated config dir so this test doesn't read user's ~/.orbit
    cfg_dir = tmp_path / "orbit-config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = os.path.join(str(cfg_dir), "orbit.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "llm": {"provider": "echo"},
                "tools": {"profile": "coding", "deny": ["write"]},
                "channels": {"feishu": {"app_id": "x", "app_secret": "y"}},
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    session_file = os.path.join(str(cfg_dir), "sessions.json")

    env = dict(os.environ)
    env["ORBIT_CONFIG_DIR"] = str(cfg_dir)
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
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    try:
        _wait_health(base_url)

        # list sections
        res_list = _rpc(base_url, "config.sections.list", {})
        assert res_list.get("ok") is True, res_list
        sections = (res_list.get("payload") or {}).get("sections") or []
        assert "llm" in sections
        assert "tools" in sections
        assert "channels" in sections

        # get section
        res_get = _rpc(base_url, "config.section.get", {"section": "tools"})
        assert res_get.get("ok") is True, res_get
        assert (res_get.get("payload") or {}).get("section") == "tools"
        assert (res_get.get("payload") or {}).get("value") == {"profile": "coding", "deny": ["write"]}

        # set section (update tools)
        res_set = _rpc(base_url, "config.section.set", {"section": "tools", "value": {"profile": "minimal"}})
        assert res_set.get("ok") is True, res_set

        # verify persisted by reading back
        res_get2 = _rpc(base_url, "config.section.get", {"section": "tools"})
        assert res_get2.get("ok") is True, res_get2
        assert (res_get2.get("payload") or {}).get("value") == {"profile": "minimal"}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

