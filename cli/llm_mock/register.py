"""Register `mw4agent llm-mock` CLI commands to run the mock LLM server."""

from __future__ import annotations

from typing import Optional

import click

from ..context import ProgramContext


def register_llm_mock_cli(program: click.Group, ctx: ProgramContext) -> None:
    """Register the llm-mock command group."""

    @program.group("llm-mock", help="Run a mock OpenAI-compatible LLM server for testing")
    @click.pass_context
    def llm_mock_group(click_ctx: click.Context) -> None:  # pragma: no cover - wiring
        pass

    @llm_mock_group.command("run", help="Run the mock LLM server (foreground)")
    @click.option("--host", default="127.0.0.1", show_default=True, help="Bind address")
    @click.option("--port", type=int, default=8089, show_default=True, help="Port to listen on")
    @click.pass_context
    def llm_mock_run(click_ctx: click.Context, host: str, port: int) -> None:
        """Run the mock LLM server using uvicorn."""
        click.echo(f"Running mock LLM server on http://{host}:{port}")

        try:
            import uvicorn  # type: ignore[import-not-found]
        except Exception as e:  # pragma: no cover - environment dependent
            raise click.ClickException(f"uvicorn not available: {e}")

        from ...llm.mock_server import create_app

        app = create_app()
        uvicorn.run(app, host=host, port=port, log_level="info")

