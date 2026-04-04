"""channels feishu add CLI."""

from __future__ import annotations

import json

import click
from click.testing import CliRunner

from orbit.cli.channels.register import register_channels_cli
from orbit.cli.context import create_program_context
from orbit.config.root import read_root_config


def _build_cli() -> click.Group:
    @click.group()
    def cli() -> None:
        return None

    register_channels_cli(cli, create_program_context("0.0.0"))
    return cli


def test_feishu_add_writes_channels_section(tmp_path, monkeypatch) -> None:
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ORBIT_CONFIG_DIR", str(cfg_dir))
    # Avoid encrypted orbit.json (would make raw json.loads on file fail in CI).
    monkeypatch.delenv("ORBIT_SECRET_KEY", raising=False)

    runner = CliRunner()
    res = runner.invoke(
        _build_cli(),
        [
            "channels",
            "feishu",
            "add",
            "--app-id",
            "cli_app_1",
            "--app-secret",
            "secret_value_9",
            "--connection-mode",
            "websocket",
        ],
    )
    assert res.exit_code == 0, res.output

    assert (cfg_dir / "orbit.json").exists()
    data = read_root_config()
    feishu = (data.get("channels") or {}).get("feishu") or {}
    assert feishu.get("app_id") == "cli_app_1"
    assert feishu.get("app_secret") == "secret_value_9"
    assert feishu.get("connection_mode") == "websocket"


def test_feishu_add_json_output_redacts_secret(tmp_path, monkeypatch) -> None:
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ORBIT_CONFIG_DIR", str(cfg_dir))
    monkeypatch.delenv("ORBIT_SECRET_KEY", raising=False)

    runner = CliRunner()
    res = runner.invoke(
        _build_cli(),
        ["channels", "feishu", "add", "--app-id", "a", "--app-secret", "b", "--json"],
    )
    assert res.exit_code == 0, res.output
    raw = res.output
    brace = raw.find("{")
    assert brace >= 0, raw
    out = json.loads(raw[brace:])
    assert out.get("ok") is True
    assert out["feishu"]["app_secret"] == "********"
    assert out["feishu"]["app_id"] == "a"


def test_feishu_list_shows_single_default_account(tmp_path, monkeypatch) -> None:
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ORBIT_CONFIG_DIR", str(cfg_dir))
    monkeypatch.delenv("ORBIT_SECRET_KEY", raising=False)

    runner = CliRunner()
    add_res = runner.invoke(
        _build_cli(),
        ["channels", "feishu", "add", "--app-id", "app_default_1", "--app-secret", "sec_1"],
    )
    assert add_res.exit_code == 0, add_res.output

    list_res = runner.invoke(_build_cli(), ["channels", "feishu", "list", "--json"])
    assert list_res.exit_code == 0, list_res.output
    raw = list_res.output
    brace = raw.find("{")
    assert brace >= 0, raw
    out = json.loads(raw[brace:])
    assert out.get("ok") is True
    items = out.get("items") or []
    assert len(items) == 1
    row = items[0]
    assert row.get("account") == "default"
    assert row.get("channel") == "feishu"
    assert row.get("app_id") == "app_default_1"


def test_feishu_list_shows_multiple_accounts(tmp_path, monkeypatch) -> None:
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ORBIT_CONFIG_DIR", str(cfg_dir))
    monkeypatch.delenv("ORBIT_SECRET_KEY", raising=False)

    runner = CliRunner()
    r1 = runner.invoke(
        _build_cli(),
        [
            "channels",
            "feishu",
            "add",
            "--account",
            "coders",
            "--app-id",
            "app_coders",
            "--app-secret",
            "sec_coders",
            "--agent-id",
            "agent_coders",
        ],
    )
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(
        _build_cli(),
        [
            "channels",
            "feishu",
            "add",
            "--account",
            "ops",
            "--app-id",
            "app_ops",
            "--app-secret",
            "sec_ops",
            "--agent-id",
            "agent_ops",
        ],
    )
    assert r2.exit_code == 0, r2.output

    list_res = runner.invoke(_build_cli(), ["channels", "feishu", "list", "--json"])
    assert list_res.exit_code == 0, list_res.output
    raw = list_res.output
    brace = raw.find("{")
    assert brace >= 0, raw
    out = json.loads(raw[brace:])
    items = out.get("items") or []
    by_acct = {x.get("account"): x for x in items}
    assert by_acct["coders"]["app_id"] == "app_coders"
    assert by_acct["coders"]["channel"] == "feishu:coders"
    assert by_acct["ops"]["app_id"] == "app_ops"
    assert by_acct["ops"]["channel"] == "feishu:ops"
