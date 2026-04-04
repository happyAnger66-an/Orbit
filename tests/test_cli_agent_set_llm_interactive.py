"""CLI: `orbit agent set-llm` interactive wizard."""

from __future__ import annotations

import json

import click
from click.testing import CliRunner

from orbit.agents.agent_manager import AgentManager
from orbit.cli.agent.register import register_agent_cli
from orbit.cli.context import create_program_context


def _build_cli() -> click.Group:
    @click.group()
    def cli() -> None:
        return None

    register_agent_cli(cli, create_program_context("0.0.0"))
    return cli


def test_agent_set_llm_interactive_writes_provider_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ORBIT_STATE_DIR", str(tmp_path / ".orbit"))
    mgr = AgentManager()
    mgr.get_or_create("demo")

    # Interactive prompts:
    # Provider, Model id, Base URL, API key, Thinking level, confirm write
    user_input = "\n".join(
        [
            "echo",
            "demo-model",
            "",
            "",
            "",
            "y",
            "",
        ]
    )
    r = CliRunner().invoke(
        _build_cli(),
        ["agent", "set-llm", "demo", "--interactive"],
        input=user_input,
    )
    assert r.exit_code == 0, r.output
    # Output includes interactive prompts; parse the final JSON object.
    marker = r.output.rfind('"ok"')
    assert marker >= 0, r.output
    start = r.output.rfind("{", 0, marker)
    assert start >= 0, r.output
    out = json.loads(r.output[start:])
    assert out.get("ok") is True and out.get("agentId") == "demo"
    llm = out.get("llm") or {}
    assert llm.get("provider") == "echo"
    assert llm.get("model") == "demo-model"

    cfg = mgr.get("demo")
    assert cfg is not None
    assert (cfg.llm or {}).get("provider") == "echo"
    assert (cfg.llm or {}).get("model") == "demo-model"

