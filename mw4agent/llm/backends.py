"""LLM backends (echo + optional OpenAI Chat API).

Design:
- Default backend is an 'echo' model (no external calls), so tests are stable.
- When MW4AGENT_LLM_PROVIDER=openai and OPENAI_API_KEY is set, we call OpenAI's
  chat completions API to get a real answer.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from ..agents.types import AgentRunParams
from ..config import get_default_config_manager


@dataclass
class LLMUsage:
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


def _load_llm_config() -> Dict[str, Any]:
    """Load LLM config from encrypted config store (llm.json)."""
    try:
        mgr = get_default_config_manager()
        cfg = mgr.read_config("llm", default={})
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        # Fail open: fall back to env/hardcoded defaults if config unreadable.
        return {}


def _call_openai_chat(prompt: str, *, model: str, api_key: str, timeout_s: float = 30.0) -> Tuple[str, LLMUsage]:
    """Call OpenAI Chat Completions API (minimal subset)."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    obj = json.loads(raw)
    text = (
        obj.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    usage_obj = obj.get("usage") or {}
    usage = LLMUsage(
        input_tokens=usage_obj.get("prompt_tokens"),
        output_tokens=usage_obj.get("completion_tokens"),
        total_tokens=usage_obj.get("total_tokens"),
    )
    return text or "", usage


def generate_reply(params: AgentRunParams) -> Tuple[str, str, str, LLMUsage]:
    """Generate a reply for a single turn.

    Returns:
        reply_text, provider, model, usage
    """
    cfg = _load_llm_config()
    cfg_provider = ""
    cfg_model = ""
    if isinstance(cfg, dict):
        cfg_provider = str(cfg.get("provider") or "").strip().lower()
        cfg_model = str(cfg.get("model") or "").strip()

    provider = (
        params.provider
        or os.getenv("MW4AGENT_LLM_PROVIDER")
        or cfg_provider
        or "echo"
    ).strip().lower()
    model = (
        params.model
        or os.getenv("MW4AGENT_LLM_MODEL")
        or cfg_model
        or "gpt-4o-mini"
    ).strip()

    # Echo backend (default, local only)
    if provider in ("", "echo", "debug"):
        reply = f"Agent (echo) reply: {params.message}"
        return reply, "echo", model, LLMUsage()

    # OpenAI backend (requires OPENAI_API_KEY)
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            # Fallback to echo if no API key
            reply = f"Agent (echo:no-api-key) reply: {params.message}"
            return reply, "echo", model, LLMUsage()
        prompt = params.message
        if params.extra_system_prompt:
            prompt = params.extra_system_prompt.strip() + "\n\n" + prompt
        try:
            text, usage = _call_openai_chat(prompt, model=model, api_key=api_key)
            return text or "", provider, model, usage
        except Exception as e:
            # Fail closed to echo so agent仍可工作
            fallback = f"Agent (openai-error) reply: {params.message}\n\n[error: {e}]"
            return fallback, provider, model, LLMUsage()

    # Unknown provider → echo
    reply = f"Agent (unknown-provider:{provider}) reply: {params.message}"
    return reply, provider or "echo", model, LLMUsage()

