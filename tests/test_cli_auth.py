from __future__ import annotations

import json
import os
import sys

import click
from click.testing import CliRunner

# Ensure local repo sources take precedence over any installed orbit package.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from orbit.cli.configuration import register_configuration_cli
from orbit.config.root import read_root_config


def _build_cli() -> click.Group:
    @click.group()
    def cli():
        return None

    register_configuration_cli(cli, None)
    return cli


def test_configuration_auth_set_and_effective(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ORBIT_CONFIG_DIR", str(cfg_dir))
    # Avoid encryption warning noise in CLI output (must be base64-encoded 32 bytes).
    monkeypatch.setenv("ORBIT_SECRET_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

    # seed config
    with open(cfg_dir / "orbit.json", "w", encoding="utf-8") as f:
        json.dump({"llm": {"provider": "echo"}}, f)

    runner = CliRunner()
    cli = _build_cli()

    # set by_channel deny write
    res = runner.invoke(
        cli,
        ["configuration", "auth", "set", "--scope", "by_channel", "--channel", "feishu", "--deny", "write"],
    )
    assert res.exit_code == 0, res.output

    cfg = read_root_config()
    assert cfg.get("tools", {}).get("by_channel", {}).get("feishu", {}).get("deny") == ["write"]

    # effective should not include write for non-owner
    res2 = runner.invoke(
        cli,
        ["configuration", "auth", "effective", "--channel", "feishu", "--user-id", "ou_x", "--no-owner", "--authorized", "--json"],
    )
    assert res2.exit_code == 0, res2.output
    out = json.loads(res2.output)
    assert "write" not in out.get("allowedTools", [])

