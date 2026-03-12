"""Register `mw4agent config` CLI commands for encrypted config read/write."""

from __future__ import annotations

import json as jsonlib
from pathlib import Path
from typing import Optional

import click

from ..context import ProgramContext
from ...config import get_default_config_manager


def register_config_cli(program: click.Group, ctx: ProgramContext) -> None:
    """Register the `config` command group."""

    @program.group("config", help="Read and write encrypted config files")
    @click.pass_context
    def config_group(click_ctx: click.Context) -> None:  # pragma: no cover - wiring
        pass

    @config_group.command("read", help="Read an encrypted config file and print JSON")
    @click.argument("name", metavar="NAME", nargs=1)
    @click.option(
        "--raw",
        "raw_output",
        is_flag=True,
        help="Print raw JSON without pretty formatting",
    )
    def config_read(name: str, raw_output: bool) -> None:
        """Read a config by NAME (without .json) from the encrypted config store."""
        mgr = get_default_config_manager()
        data = mgr.read_config(name, default={})
        if raw_output:
            click.echo(jsonlib.dumps(data, ensure_ascii=False))
        else:
            click.echo(jsonlib.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))

    @config_group.command("write", help="Write JSON into an encrypted config file")
    @click.argument("name", metavar="NAME", nargs=1)
    @click.option(
        "-i",
        "--input",
        "input_path",
        type=click.Path(dir_okay=False, exists=True, readable=True, path_type=Path),
        help="Path to a JSON file to write",
    )
    @click.option(
        "--stdin",
        "from_stdin",
        is_flag=True,
        help="Read JSON payload from stdin",
    )
    def config_write(name: str, input_path: Optional[Path], from_stdin: bool) -> None:
        """Write config by NAME (without .json) into the encrypted config store.

        Exactly one of --input / --stdin must be provided.
        """
        if bool(input_path) == bool(from_stdin):
            raise click.UsageError("Exactly one of --input or --stdin must be specified")

        if input_path:
            text = input_path.read_text(encoding="utf-8")
        else:
            # Read from stdin
            text = click.get_text_stream("stdin").read()

        try:
            obj = jsonlib.loads(text)
        except Exception as e:  # pragma: no cover - defensive
            raise click.ClickException(f"Invalid JSON: {e}") from e

        if not isinstance(obj, dict):
            raise click.ClickException("Config root must be a JSON object")

        mgr = get_default_config_manager()
        mgr.write_config(name, obj)
        click.echo(f"Wrote encrypted config '{name}.json'")

