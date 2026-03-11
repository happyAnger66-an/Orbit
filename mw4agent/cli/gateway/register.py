"""Register gateway CLI commands"""

import click
import json
from typing import Optional
from ..context import ProgramContext


def register_gateway_cli(program: click.Group, ctx: ProgramContext) -> None:
    """Register gateway commands - similar to registerGatewayCli in OpenClaw"""
    
    @program.group("gateway", help="Run, inspect, and query the WebSocket Gateway")
    @click.pass_context
    def gateway(ctx: click.Context):
        """Gateway command group"""
        pass

    @gateway.command("run", help="Run the WebSocket Gateway (foreground)")
    @click.option("--port", type=int, default=18789, help="Gateway port")
    @click.option("--bind", default="127.0.0.1", help="Bind address")
    @click.option("--force", is_flag=True, help="Kill existing gateway on port")
    @click.option("--dev", is_flag=True, help="Dev profile")
    @click.pass_context
    def gateway_run(ctx: click.Context, port: int, bind: str, force: bool, dev: bool):
        """Run the gateway"""
        click.echo(f"Running gateway on {bind}:{port}")
        if force:
            click.echo("Force mode: killing existing gateway...")
        if dev:
            click.echo("Dev profile enabled")
        # TODO: Implement actual gateway startup
        click.echo("Gateway started (not implemented yet)")

    @gateway.command("status", help="Show gateway service status + probe the Gateway")
    @click.option("--url", help="Gateway WebSocket URL")
    @click.option("--token", help="Gateway token")
    @click.option("--timeout", type=int, default=3000, help="Timeout in ms")
    @click.option("--json", is_flag=True, help="Output JSON")
    @click.pass_context
    def gateway_status(ctx: click.Context, url: Optional[str], token: Optional[str], timeout: int, json: bool):
        """Show gateway status"""
        if json:
            result = {
                "status": "unknown",
                "reachable": False,
                "url": url or "ws://127.0.0.1:18789",
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo("Gateway Status")
            click.echo(f"  URL: {url or 'ws://127.0.0.1:18789'}")
            click.echo(f"  Status: Unknown (not implemented)")
            # TODO: Implement actual status check

    @gateway.command("call", help="Call a Gateway method")
    @click.argument("method", required=True)
    @click.option("--params", default="{}", help="JSON object string for params")
    @click.option("--url", help="Gateway WebSocket URL")
    @click.option("--token", help="Gateway token")
    @click.option("--timeout", type=int, default=30000, help="Timeout in ms")
    @click.option("--json", is_flag=True, help="Output JSON")
    @click.pass_context
    def gateway_call(
        ctx: click.Context,
        method: str,
        params: str,
        url: Optional[str],
        token: Optional[str],
        timeout: int,
        json: bool,
    ):
        """Call a gateway RPC method"""
        try:
            params_obj = json.loads(params)
        except json.JSONDecodeError:
            click.echo(f"Error: Invalid JSON in --params: {params}", err=True)
            ctx.exit(1)

        if json:
            result = {
                "method": method,
                "params": params_obj,
                "result": None,  # TODO: Implement actual RPC call
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"Gateway call: {method}")
            click.echo(f"Params: {json.dumps(params_obj, indent=2)}")
            click.echo("(RPC call not implemented yet)")

    @gateway.command("health", help="Fetch Gateway health")
    @click.option("--url", help="Gateway WebSocket URL")
    @click.option("--token", help="Gateway token")
    @click.option("--json", is_flag=True, help="Output JSON")
    @click.pass_context
    def gateway_health(ctx: click.Context, url: Optional[str], token: Optional[str], json: bool):
        """Fetch gateway health"""
        if json:
            result = {
                "status": "ok",
                "duration_ms": None,
                "channels": {},
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo("Gateway Health")
            click.echo("  Status: OK (not implemented)")
            # TODO: Implement actual health check

    @gateway.command("discover", help="Discover gateways via Bonjour (local + wide-area if configured)")
    @click.option("--timeout", type=int, default=2000, help="Per-command timeout in ms")
    @click.option("--json", is_flag=True, help="Output JSON")
    @click.pass_context
    def gateway_discover(ctx: click.Context, timeout: int, json: bool):
        """Discover gateways"""
        if json:
            result = {
                "timeout_ms": timeout,
                "domains": ["local."],
                "count": 0,
                "beacons": [],
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo("Gateway Discovery")
            click.echo(f"  Found 0 gateway(s) · domains: local.")
            click.echo("  (Discovery not implemented yet)")

    @gateway.command("probe", help="Show gateway reachability + discovery + health + status summary")
    @click.option("--url", help="Explicit Gateway WebSocket URL")
    @click.option("--token", help="Gateway token")
    @click.option("--timeout", type=int, default=3000, help="Overall probe budget in ms")
    @click.option("--json", is_flag=True, help="Output JSON")
    @click.pass_context
    def gateway_probe(
        ctx: click.Context,
        url: Optional[str],
        token: Optional[str],
        timeout: int,
        json: bool,
    ):
        """Probe gateway"""
        if json:
            result = {
                "reachable": False,
                "url": url or "ws://127.0.0.1:18789",
                "status": "unknown",
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo("Gateway Probe")
            click.echo(f"  URL: {url or 'ws://127.0.0.1:18789'}")
            click.echo("  Status: Unknown (not implemented)")
            # TODO: Implement actual probe
