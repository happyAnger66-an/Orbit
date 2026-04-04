"""Register node-host CLI commands."""

import click
from typing import Optional
from ..context import ProgramContext
from ...node_host.client import run_node_host


def register_node_host_cli(program: click.Group, ctx: ProgramContext) -> None:
    """Register node-host commands (OpenClaw-compatible node)."""

    @program.group("node-host", help="Run as an OpenClaw-compatible node (connect to Gateway, execute node.invoke)")
    @click.pass_context
    def node_host_group(click_ctx: click.Context):
        pass

    @node_host_group.command("run", help="Run node-host: connect to Gateway and handle node.invoke (e.g. system.run)")
    @click.option("--url", required=True, help="Gateway WebSocket URL (e.g. ws://127.0.0.1:18789)")
    @click.option("--node-id", default="orbit-node", show_default=True, help="Node ID (must be paired with Gateway)")
    @click.option("--display-name", help="Display name for this node")
    @click.option("--token", help="Gateway auth token (if Gateway requires auth)")
    @click.option("--no-reconnect", is_flag=True, help="Exit on disconnect instead of reconnecting")
    @click.pass_context
    def node_host_run(
        click_ctx: click.Context,
        url: str,
        node_id: str,
        display_name: Optional[str],
        token: Optional[str],
        no_reconnect: bool,
    ):
        """Run the node-host and process node.invoke requests from the Gateway."""
        url = url.strip().rstrip("/")
        if not url.startswith("ws://") and not url.startswith("wss://"):
            raise click.BadParameter("URL must be ws:// or wss://")
        reconnect_delay = 0.0 if no_reconnect else 5.0
        click.echo(f"Node-host connecting to {url} as node {node_id}")
        if token:
            click.echo("Using provided token for auth")
        run_node_host(
            ws_url=url,
            node_id=node_id.strip() or "orbit-node",
            display_name=display_name.strip() if display_name else None,
            token=token.strip() if token else None,
            reconnect_delay=reconnect_delay,
        )
