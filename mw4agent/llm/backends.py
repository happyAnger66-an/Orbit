"""LLM backends: extensible provider registry (echo, OpenAI, DeepSeek, vLLM, etc.).

Design:
- Default backend is 'echo' (no external calls) for stable tests.
- HTTP-based providers use a single OpenAI-compatible Chat Completions caller.
- New providers are added by registering a ProviderSpec in _OPENAI_COMPAT_SPECS;
  each spec defines default base_url, default model, API key env var, and requirements.
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


@dataclass
class _ProviderSpec:
    """Spec for an OpenAI-compatible HTTP provider. Add an entry here to support a new provider."""

    default_base_url: Optional[str] = None  # None = must come from config/env
    default_model: str = ""
    api_key_env: str = "MW4AGENT_LLM_API_KEY"
    require_api_key: bool = True
    base_url_required: bool = False  # True = no default_base_url, must set in config/env


# Registry: provider_id -> ProviderSpec. Extend this to add new providers.
_OPENAI_COMPAT_SPECS: Dict[str, _ProviderSpec] = {
    "openai": _ProviderSpec(
        default_base_url="https://api.openai.com",
        default_model="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
        require_api_key=True,
    ),
    "deepseek": _ProviderSpec(
        default_base_url="https://api.deepseek.com",
        default_model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        require_api_key=True,
    ),
    "vllm": _ProviderSpec(
        default_base_url=None,
        default_model="",
        api_key_env="MW4AGENT_LLM_API_KEY",
        require_api_key=False,
        base_url_required=True,
    ),
    "aliyun-bailian": _ProviderSpec(
        default_base_url=None,
        default_model="",
        api_key_env="MW4AGENT_LLM_API_KEY",
        require_api_key=False,
        base_url_required=True,
    ),
}


def _load_llm_config() -> Dict[str, Any]:
    """Load LLM config from the default config store (~/.mw4agent/mw4agent.json, section \"llm\")."""
    try:
        mgr = get_default_config_manager()
        cfg = mgr.read_config("llm", default={})
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _call_openai_chat(
    prompt: str,
    *,
    model: str,
    api_key: str,
    base_url: str,
    timeout_s: float = 30.0,
) -> Tuple[str, LLMUsage]:
    """Call an OpenAI-compatible Chat Completions API (minimal subset)."""
    base = base_url.rstrip("/")
    # Avoid double /v1 when user sets base_url to https://api.example.com/v1
    if base.endswith("/v1"):
        url = f"{base}/chat/completions"
    else:
        url = f"{base}/v1/chat/completions"
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
    cfg_base_url: Optional[str] = None
    cfg_api_key: Optional[str] = None
    if isinstance(cfg, dict):
        cfg_provider = str(cfg.get("provider") or "").strip().lower()
        cfg_model = str(cfg.get("model") or cfg.get("model_id") or "").strip()
        raw_base = str(cfg.get("base_url") or "").strip()
        cfg_base_url = raw_base or None
        raw_key = str(cfg.get("api_key") or "").strip()
        cfg_api_key = raw_key or None

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
    ).strip()

    # Echo backend (default, local only)
    if provider in ("", "echo", "debug"):
        default_model = "gpt-4o-mini"  # for display only
        reply = f"Agent (echo) reply: {params.message}"
        return reply, "echo", model or default_model, LLMUsage()

    # Resolve model default from provider spec if registered
    spec = _OPENAI_COMPAT_SPECS.get(provider)
    if spec and not model:
        model = spec.default_model or ""

    # Unknown provider → echo
    if spec is None:
        reply = f"Agent (unknown-provider:{provider}) reply: {params.message}"
        return reply, provider or "echo", model or "gpt-4o-mini", LLMUsage()

    # Resolve base_url: config > env > spec default
    base_url = cfg_base_url or os.getenv("MW4AGENT_LLM_BASE_URL", "").strip() or spec.default_base_url or ""
    if spec.base_url_required and not base_url:
        reply = f"Agent (echo:no-base-url:{provider}) reply: {params.message}"
        return reply, "echo", model, LLMUsage()

    # Resolve api_key: config > env
    api_key = (cfg_api_key or os.getenv(spec.api_key_env, "").strip() or "")
    if spec.require_api_key and not api_key:
        reply = f"Agent (echo:no-api-key:{provider}) reply: {params.message}"
        return reply, "echo", model, LLMUsage()

    prompt = params.message
    if params.extra_system_prompt:
        prompt = params.extra_system_prompt.strip() + "\n\n" + prompt

    try:
        text, usage = _call_openai_chat(
            prompt,
            model=model or spec.default_model or "gpt-4o-mini",
            api_key=api_key or "none",
            base_url=base_url,
        )
        return text or "", provider, model or spec.default_model, usage
    except Exception as e:
        fallback = f"Agent ({provider}-error) reply: {params.message}\n\n[error: {e}]"
        return fallback, provider, model, LLMUsage()


def list_providers() -> Tuple[str, ...]:
    """Return registered OpenAI-compatible provider ids (excluding echo)."""
    return tuple(_OPENAI_COMPAT_SPECS.keys())
