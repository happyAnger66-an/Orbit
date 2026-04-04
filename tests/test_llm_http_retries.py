"""HTTP LLM path retries transient failures before fallback."""

from __future__ import annotations

from orbit.agents.types import AgentRunParams
from orbit.llm import backends as backends_mod
from orbit.llm.backends import LLMUsage, generate_reply, generate_reply_with_tools


def test_generate_reply_retries_then_succeeds(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(backends_mod.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def fake_chat(*_a, **_kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("transient")
        return ("ok", LLMUsage())

    monkeypatch.setattr(backends_mod, "_call_openai_chat", fake_chat)
    text, provider, _model, _u = generate_reply(
        AgentRunParams(message="hi", provider="openai", model="gpt-4o-mini"),
    )
    assert text == "ok"
    assert provider == "openai"
    assert calls["n"] == 3


def test_generate_reply_fallback_after_max_attempts(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(backends_mod.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def fake_chat(*_a, **_kw):
        calls["n"] += 1
        raise ConnectionError("always fail")

    monkeypatch.setattr(backends_mod, "_call_openai_chat", fake_chat)
    text, provider, _model, _u = generate_reply(
        AgentRunParams(message="m", provider="openai", model="gpt-4o-mini"),
    )
    assert "openai-error" in text
    assert "[error:" in text
    assert calls["n"] == backends_mod._LLM_HTTP_MAX_ATTEMPTS


def test_generate_reply_with_tools_retries_then_succeeds(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(backends_mod.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def fake_tools(*_a, **_kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise OSError("transient")
        return (None, [], LLMUsage())

    monkeypatch.setattr(backends_mod, "_call_openai_chat_with_tools", fake_tools)
    tools = [{"name": "t1", "description": "d", "parameters": {"type": "object", "properties": {}}}]
    content, tcalls, provider, _model, _u = generate_reply_with_tools(
        AgentRunParams(message="hi", provider="openai", model="gpt-4o-mini"),
        messages=[{"role": "user", "content": "hi"}],
        tool_definitions=tools,
    )
    assert content is None
    assert tcalls == []
    assert provider == "openai"
    assert calls["n"] == 2


def test_generate_reply_with_tools_no_tools_branch_retries(monkeypatch) -> None:
    """Empty tool_definitions uses chat path; should retry like generate_reply."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(backends_mod.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def fake_chat(*_a, **_kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise OSError("transient")
        return ("plain", LLMUsage())

    monkeypatch.setattr(backends_mod, "_call_openai_chat", fake_chat)
    content, tcalls, provider, _model, _u = generate_reply_with_tools(
        AgentRunParams(message="hi", provider="openai", model="gpt-4o-mini"),
        messages=[{"role": "user", "content": "hi"}],
        tool_definitions=[],
    )
    assert content == "plain"
    assert tcalls == []
    assert provider == "openai"
    assert calls["n"] == 2
