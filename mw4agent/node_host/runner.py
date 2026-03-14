"""Simple system.run executor: run a command and return stdout/stderr/exitCode."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Dict, List, Optional


def run_system_run(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute system.run-style params (argv, cwd, env, timeoutMs).
    Returns payload suitable for node.invoke.result: { stdout, stderr, exitCode }.
    """
    argv = params.get("command") or params.get("argv")
    if not isinstance(argv, list) or len(argv) == 0:
        return {
            "ok": False,
            "error": {"code": "INVALID_REQUEST", "message": "command/argv required and must be non-empty array"},
        }
    argv = [str(x) for x in argv]
    cwd = params.get("cwd")
    if cwd is not None:
        cwd = str(cwd).strip() or None
    env_overrides = params.get("env")
    if isinstance(env_overrides, dict):
        env = dict(os.environ)
        for k, v in env_overrides.items():
            if v is None:
                env.pop(k, None)
            else:
                env[str(k)] = str(v)
    else:
        env = None
    timeout_ms = params.get("timeoutMs")
    timeout_sec: Optional[float] = None
    if isinstance(timeout_ms, (int, float)) and timeout_ms > 0:
        timeout_sec = timeout_ms / 1000.0

    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            timeout=timeout_sec,
            text=True,
        )
        return {
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "exitCode": result.returncode,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "stdout": (e.stdout or "") if isinstance(e.stdout, str) else "",
            "stderr": (e.stderr or "") if isinstance(e.stderr, str) else str(e),
            "exitCode": -1,
            "timeout": True,
            "message": "command timed out",
        }
    except FileNotFoundError as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exitCode": -1,
            "error": {"code": "NOT_FOUND", "message": str(e)},
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exitCode": -1,
            "error": {"code": "EXEC_ERROR", "message": str(e)},
        }
