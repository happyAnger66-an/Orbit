"""Register `tools` CLI commands."""

from __future__ import annotations

import json
from typing import Dict, List

import click

from ...agents.tools import get_tool_registry
from ...agents.tools.policy import (
    filter_tools_by_policy,
    resolve_effective_policy_for_context,
    resolve_tool_policy_config,
)
from ...config import get_default_config_manager


def register_tools_cli(program: click.Group, _ctx) -> None:
    @program.group(name="tools", help="Inspect registered tools and effective enablement")
    def tools_group() -> None:
        pass

    @tools_group.command(name="list", help="List all registered tools with enablement/limits")
    @click.option("--channel", default="console", show_default=True, help="Channel context for policy resolution")
    @click.option("--user-id", default="local", show_default=True, help="User id context for policy resolution")
    @click.option("--owner/--no-owner", "is_owner", default=False, show_default=True, help="Whether caller is owner")
    @click.option("--authorized/--no-authorized", "authorized", default=True, show_default=True, help="Whether command is authorized")
    @click.option("--json", "as_json", is_flag=True, default=False, help="Output JSON")
    def tools_list(channel: str, user_id: str, is_owner: bool, authorized: bool, as_json: bool) -> None:
        cfg_mgr = get_default_config_manager()
        base = resolve_tool_policy_config(cfg_mgr)
        eff = resolve_effective_policy_for_context(
            cfg_mgr,
            base_policy=base,
            channel=channel,
            user_id=user_id,
            sender_is_owner=is_owner,
            command_authorized=authorized,
        )

        all_tools = sorted(get_tool_registry().list_tools(), key=lambda t: t.name)
        allowed_by_policy = {t.name for t in filter_tools_by_policy(all_tools, eff)}

        tools_payload: List[Dict] = []
        for tool in all_tools:
            reason_parts: List[str] = []
            enabled = True
            if tool.name not in allowed_by_policy:
                enabled = False
                reason_parts.append("blocked by tools policy")
            if tool.owner_only and not is_owner:
                enabled = False
                reason_parts.append("owner_only")
            if enabled:
                reason_parts.append("enabled")
            tools_payload.append(
                {
                    "name": tool.name,
                    "enabled": enabled,
                    "ownerOnly": bool(tool.owner_only),
                    "reason": ", ".join(reason_parts),
                    "description": tool.description,
                }
            )

        payload = {
            "context": {
                "channel": channel,
                "user_id": user_id,
                "owner": is_owner,
                "authorized": authorized,
            },
            "effectivePolicy": {
                "profile": eff.profile,
                "allow": eff.allow,
                "deny": eff.deny,
            },
            "tools": tools_payload,
        }
        if as_json:
            click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        click.echo(
            "Context: "
            f"channel={channel} user_id={user_id} owner={is_owner} authorized={authorized}"
        )
        click.echo(
            "Effective policy: "
            f"profile={eff.profile} allow={eff.allow or []} deny={eff.deny or []}"
        )
        click.echo("Tools:")
        for item in tools_payload:
            state = "ENABLED" if item["enabled"] else "DISABLED"
            owner_tag = " owner_only" if item["ownerOnly"] else ""
            click.echo(f"- {item['name']}: {state}{owner_tag} ({item['reason']})")

