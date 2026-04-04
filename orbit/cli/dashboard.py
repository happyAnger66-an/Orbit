"""Register `dashboard` CLI command (browser Control UI entry).

Inspired by OpenClaw `dashboard` command, but simplified:
- 不负责启动 Gateway，只负责拼出 URL 并尝试用浏览器打开。
- Dashboard 前端由 Gateway 自身在 "/" 提供（FastAPI + StaticFiles）。
"""

from __future__ import annotations

from typing import Optional

import click

from .context import ProgramContext


def register_dashboard_cli(program: click.Group, ctx: ProgramContext) -> None:
    """Register the top-level `dashboard` command."""

    @program.command("dashboard", help="Open the Orbit web dashboard in your browser")
    @click.option(
        "--url",
        help="Gateway base URL (http://host:port)",
        default="http://127.0.0.1:18790",
        show_default=True,
    )
    @click.option(
        "--no-open",
        is_flag=True,
        help="Do not try to launch a browser; just print the URL",
    )
    @click.pass_context
    def dashboard_cmd(click_ctx: click.Context, url: str, no_open: bool) -> None:
        base = url.rstrip("/")
        dashboard_url = f"{base}/"
        click.echo(f"Dashboard URL: {dashboard_url}")

        if no_open:
            return

        try:
            import webbrowser
        except Exception as e:  # pragma: no cover - extremely unlikely
            click.echo(f"Could not import webbrowser: {e}", err=True)
            return

        try:
            opened = webbrowser.open(dashboard_url)
        except Exception as e:
            click.echo(f"Could not open browser automatically: {e}", err=True)
            opened = False

        if opened:
            click.echo("Opened in your default browser. Keep that tab to control Orbit.")
        else:
            click.echo("Please open the URL above in your browser.")

