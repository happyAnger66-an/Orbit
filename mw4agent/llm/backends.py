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
from ..config.root import read_root_config


@dataclass
class LLMUsage:
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


def _load_llm_config() -> Dict[str, Any]:
    """Load LLM config from config files.

    优先级（低 → 高）：
    - 旧版加密配置 llm.json（~/.mw4agent/config/llm.json）
    - 根配置 ~/.mw4agent/mw4agent.json 中的 llm 段
    """
    cfg: Dict[str, Any] = {}
    # 1) 兼容旧版：llm.json
    try:
        mgr = get_default_config_manager()
        legacy = mgr.read_config("llm", default={})
        if isinstance(legacy, dict):
            cfg.update(legacy)
    except Exception:
        pass

    # 2) 新版：根配置 mw4agent.json 下的 llm 段（具有更高优先级）
    try:
        root = read_root_config()
        llm_root = root.get("llm")
        if isinstance(llm_root, dict):
            cfg.update(llm_root)
    except Exception:
        pass

    return cfg


def _call_openai_chat(
    prompt: str,
    *,
    model: str,
    api_key: str,
    base_url: Optional[str] = None,
    timeout_s: float = 30.0,
) -> Tuple[str, LLMUsage]:
    """Call an OpenAI-compatible Chat Completions API (minimal subset)."""
    effective_base = (
        base_url or os.getenv("MW4AGENT_OPENAI_BASE_URL") or "https://api.openai.com"
    ).rstrip("/")
    url = f"{effective_base}/v1/chat/completions"
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
        # 兼容旧字段名 "model" 与新字段名 "model_id"
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
        or "gpt-4o-mini"
    ).strip()

    # Echo backend (default, local only)
    if provider in ("", "echo", "debug"):
        reply = f"Agent (echo) reply: {params.message}"
        return reply, "echo", model, LLMUsage()

    # OpenAI backend (requires OPENAI_API_KEY or cfg.api_key)
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip() or (cfg_api_key or "")
        if not api_key:
            # Fallback to echo if no API key
            reply = f"Agent (echo:no-api-key) reply: {params.message}"
            return reply, "echo", model, LLMUsage()
        prompt = params.message
        if params.extra_system_prompt:
            prompt = params.extra_system_prompt.strip() + "\n\n" + prompt
        try:
            text, usage = _call_openai_chat(
                prompt,
                model=model,
                api_key=api_key,
                base_url=cfg_base_url,
            )
            return text or "", provider, model, usage
        except Exception as e:
            # Fail closed to echo so agent仍可工作
            fallback = f"Agent (openai-error) reply: {params.message}\n\n[error: {e}]"
            return fallback, provider, model, LLMUsage()

    # vLLM / 阿里云百炼等 OpenAI 兼容后端
    if provider in ("vllm", "aliyun-bailian"):
        # 优先使用配置中的 api_key/base_url，其次环境变量
        api_key = (cfg_api_key or os.getenv("MW4AGENT_LLM_API_KEY", "").strip())
        base_url = (cfg_base_url or os.getenv("MW4AGENT_LLM_BASE_URL", "").strip() or None)
        if not base_url:
            reply = f"Agent (echo:no-base-url:{provider}) reply: {params.message}"
            return reply, "echo", model, LLMUsage()
        # 对某些本地部署的 vLLM，可以无需 api_key；这里不强制要求
        prompt = params.message
        if params.extra_system_prompt:
            prompt = params.extra_system_prompt.strip() + "\n\n" + prompt
        try:
            text, usage = _call_openai_chat(
                prompt,
                model=model,
                api_key=api_key or "none",
                base_url=base_url,
            )
            return text or "", provider, model, usage
        except Exception as e:
            fallback = f"Agent ({provider}-error) reply: {params.message}\n\n[error: {e}]"
            return fallback, provider, model, LLMUsage()

    # Unknown provider → echo
    reply = f"Agent (unknown-provider:{provider}) reply: {params.message}"
    return reply, provider or "echo", model, LLMUsage()

