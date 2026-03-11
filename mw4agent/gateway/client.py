"""Minimal Gateway client (HTTP JSON RPC) for CLI tooling."""

from __future__ import annotations

import json
import uuid
import urllib.request
from typing import Any, Dict, Optional


def call_rpc(
    *,
    base_url: str,
    method: str,
    params: Optional[Dict[str, Any]] = None,
    timeout_ms: int = 30_000,
) -> Dict[str, Any]:
    req_id = str(uuid.uuid4())
    body = {"id": req_id, "method": method, "params": params or {}}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/rpc",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=max(1, timeout_ms / 1000.0)) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)

