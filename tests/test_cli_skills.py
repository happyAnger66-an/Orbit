from __future__ import annotations

import json
from pathlib import Path

import click
from click.testing import CliRunner

from mw4agent.cli.skills.register import register_skills_cli
from mw4agent.config.root import write_root_config


def _build_cli() -> click.Group:
    @click.group()
    def cli():
        return None

    register_skills_cli(cli, None)
    return cli


def test_skills_list_and_check_json(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / "cfg"
    workspace = tmp_path / "workspace"
    home_skills = tmp_path / "home_skills"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (workspace / "skills").mkdir(parents=True, exist_ok=True)
    home_skills.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("MW4AGENT_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("MW4AGENT_SKILLS_DIR", str(home_skills))
    monkeypatch.setenv("MW4AGENT_SECRET_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

    (workspace / "skills" / "demo.json").write_text(
        json.dumps({"name": "demo", "description": "Demo skill"}),
        encoding="utf-8",
    )
    write_root_config({"skills": {"filter": ["demo"]}})

    runner = CliRunner()
    cli = _build_cli()

    res = runner.invoke(cli, ["skills", "list", "--workspace-dir", str(workspace), "--json"])
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["count"] == 1
    assert payload["skills"][0]["name"] == "demo"
    assert "version" in payload

    res2 = runner.invoke(cli, ["skills", "check", "--workspace-dir", str(workspace), "--json"])
    assert res2.exit_code == 0, res2.output
    check = json.loads(res2.output)
    assert check["ok"] is True
    assert check["summary"]["count"] == 1

