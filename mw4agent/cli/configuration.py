"""Configuration CLI for MW4Agent.

Phase 1: configure LLM provider/model and store in ~/.mw4agent/mw4agent.json.

Reserved for future extensions:
- channels configuration
- skills configuration
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import click

from ..config.root import get_root_config_path, read_root_config, write_root_config


def _update_llm_section(
    cfg: Dict[str, Any],
    provider: str,
    model_id: str,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    next_cfg = dict(cfg)
    llm = dict(next_cfg.get("llm") or {})
    llm["provider"] = provider
    llm["model_id"] = model_id
    if base_url is not None:
        llm["base_url"] = base_url
    if api_key is not None:
        llm["api_key"] = api_key
    next_cfg["llm"] = llm
    return next_cfg


def _run_interactive_wizard() -> None:
    """Run an interactive configuration wizard (LLM first, reserved for more sections)."""
    click.echo("MW4Agent configuration wizard")
    click.echo("")

    current = read_root_config()
    llm = current.get("llm") or {}
    if llm:
        click.echo("Current LLM configuration:")
        click.echo(f"  provider : {llm.get('provider')}")
        click.echo(f"  model_id : {llm.get('model_id')}")
        if llm.get("base_url"):
            click.echo(f"  base_url : {llm.get('base_url')}")
        if llm.get("api_key"):
            click.echo("  api_key : ********")
        click.echo("")

    if click.confirm("Configure LLM provider/model now?", default=True):
        provider = click.prompt(
            "Select provider [vllm/aliyun-bailian]",
            type=click.Choice(["vllm", "aliyun-bailian"], case_sensitive=False),
            default=str(llm.get("provider") or "vllm"),
            show_default=True,
        )
        default_model = str(llm.get("model_id") or "").strip() or "YOUR_MODEL_ID"
        model_id = click.prompt(
            "Model ID",
            default=default_model,
            show_default=True,
        )
        default_base_url = str(llm.get("base_url") or "").strip()
        base_url = click.prompt(
            "Base URL (leave empty to use provider default)",
            default=default_base_url,
            show_default=bool(default_base_url),
        ).strip() or None

        existing_api_key = str(llm.get("api_key") or "").strip()
        api_key_prompt_default = "********" if existing_api_key else ""
        api_key_input = click.prompt(
            "API Key (leave empty to keep current / unset)",
            default=api_key_prompt_default,
            show_default=bool(api_key_prompt_default),
        ).strip()
        if api_key_input == "********":
            api_key: Optional[str] = existing_api_key or None
        elif api_key_input:
            api_key = api_key_input
        else:
            api_key = None

        updated = _update_llm_section(
            current,
            provider.strip(),
            model_id.strip(),
            base_url=base_url,
            api_key=api_key,
        )
        write_root_config(updated)
        click.echo(f"LLM configuration saved to {get_root_config_path()}")
        current = updated

    click.echo("")
    click.echo("Channels and skills configuration will be added in future versions.")


def register_configuration_cli(program: click.Group, _ctx) -> None:
    @program.group(
        name="configuration",
        help="Configure MW4Agent (LLM, channels, skills, etc.)",
        invoke_without_command=True,
    )
    @click.pass_context
    def configuration_group(ctx: click.Context) -> None:
        # No subcommand → run interactive wizard.
        if ctx.invoked_subcommand is None:
            _run_interactive_wizard()

    @configuration_group.command(name="set-llm", help="Set LLM provider and model id")
    @click.option(
        "--provider",
        type=click.Choice(["vllm", "aliyun-bailian"], case_sensitive=False),
        required=True,
        help="LLM provider (vllm or aliyun-bailian)",
    )
    @click.option(
        "--model-id",
        required=True,
        help="Model identifier for the selected provider",
    )
    @click.option(
        "--base-url",
        required=False,
        help="Optional base URL for the selected provider (e.g. http://127.0.0.1:8000)",
    )
    @click.option(
        "--api-key",
        required=False,
        help="Optional API key for the selected provider",
    )
    def set_llm(provider: str, model_id: str, base_url: Optional[str], api_key: Optional[str]) -> None:
        """Update LLM config and persist to ~/.mw4agent/mw4agent.json."""
        current = read_root_config()
        normalized_provider = provider.strip()
        updated = _update_llm_section(
            current,
            normalized_provider,
            model_id.strip(),
            base_url.strip() if base_url else None,
            api_key.strip() if api_key else None,
        )
        write_root_config(updated)
        path = get_root_config_path()
        click.echo(f"LLM configuration updated in {path}")

    @configuration_group.command(name="show", help="Show current root configuration")
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="Output raw JSON",
    )
    def show(as_json: bool) -> None:
        cfg = read_root_config()
        path = get_root_config_path()
        if as_json:
            click.echo(json.dumps(cfg, ensure_ascii=False, indent=2))
        else:
            click.echo(f"Config file: {path}")
            if not cfg:
                click.echo("No configuration set yet.")
                return
            llm = cfg.get("llm") or {}
            if llm:
                click.echo("LLM configuration:")
                click.echo(f"  provider : {llm.get('provider')}")
                click.echo(f"  model_id : {llm.get('model_id')}")
                if llm.get("base_url"):
                    click.echo(f"  base_url : {llm.get('base_url')}")
                if llm.get("api_key"):
                    click.echo("  api_key : ********")
            else:
                click.echo("LLM configuration: not set")

