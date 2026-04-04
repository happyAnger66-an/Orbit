from __future__ import annotations

import json

import click
from click.testing import CliRunner

from orbit.cli.tools.register import register_tools_cli
from orbit.config.root import write_root_config


def _build_cli() -> click.Group:
    @click.group()
    def cli():
        return None

    register_tools_cli(cli, None)
    return cli


def test_tools_list_shows_enablement_and_limits(tmp_path, monkeypatch) -> None:
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ORBIT_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("ORBIT_SECRET_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

    write_root_config({"tools": {"profile": "coding", "deny": ["write"]}})

    runner = CliRunner()
    cli = _build_cli()
    res = runner.invoke(cli, ["tools", "list", "--channel", "console", "--user-id", "u1", "--no-owner", "--json"])
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    by_name = {item["name"]: item for item in payload["tools"]}

    assert "read" in by_name
    assert by_name["read"]["enabled"] is True
    assert by_name["write"]["enabled"] is False
    assert "blocked by tools policy" in by_name["write"]["reason"]

    # owner-only tool should show disabled for non-owner
    assert "exec" in by_name
    assert by_name["exec"]["enabled"] is False
    assert "owner_only" in by_name["exec"]["reason"]

