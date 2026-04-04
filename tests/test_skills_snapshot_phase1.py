from __future__ import annotations

import json
from pathlib import Path

import orbit.skills.manager as skills_manager_mod
from orbit.agents.skills.snapshot import build_skill_snapshot
from orbit.config.root import write_root_config
from orbit.plugin import get_plugin_skill_source


def _write_skill_json(path: Path, name: str, desc: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"name": name, "description": desc}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_build_skill_snapshot_includes_version_sources_and_filter(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / "cfg"
    workspace = tmp_path / "workspace"
    home_skills = tmp_path / "home_skills"
    extra_skills = tmp_path / "extra_skills"
    plugin_skills = tmp_path / "plugin_skills"

    monkeypatch.setenv("ORBIT_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("ORBIT_SKILLS_DIR", str(home_skills))
    monkeypatch.setenv("ORBIT_SECRET_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

    _write_skill_json(workspace / "skills" / "ws_only.json", "ws_only", "Workspace skill")
    _write_skill_json(home_skills / "home_only.json", "home_only", "Home skill")
    _write_skill_json(extra_skills / "cfg_only.json", "cfg_only", "Config extra skill")
    _write_skill_json(plugin_skills / "plugin_only.json", "plugin_only", "Plugin skill")

    source = get_plugin_skill_source()
    source._dirs.clear()
    source.add_dir(plugin_skills)

    write_root_config(
        {
            "skills": {
                "load": {"extra_dirs": [str(extra_skills)]},
                "filter": ["ws_only", "plugin_only"],
            }
        }
    )

    snapshot = build_skill_snapshot(workspace_dir=str(workspace))
    names = [s["name"] for s in snapshot["skills"]]
    assert names == ["plugin_only", "ws_only"]
    assert snapshot["count"] == 2
    assert isinstance(snapshot.get("version"), str) and len(snapshot["version"]) == 12
    assert snapshot.get("skill_filter") == ["ws_only", "plugin_only"]
    assert sorted(snapshot.get("filtered_out") or []) == ["cfg_only", "home_only"]
    sources = {s["name"] for s in snapshot.get("sources") or []}
    assert "workspace" in sources
    assert "plugin" in sources
    assert snapshot.get("prompt_count") == 2
    assert snapshot.get("prompt_truncated") is False


def test_build_skill_snapshot_applies_prompt_budget(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / "cfg"
    workspace = tmp_path / "workspace"
    home_skills = tmp_path / "home_skills"
    monkeypatch.setenv("ORBIT_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("ORBIT_SKILLS_DIR", str(home_skills))
    monkeypatch.setenv("ORBIT_SECRET_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    monkeypatch.setattr(skills_manager_mod, "_default_skill_manager", None)
    source = get_plugin_skill_source()
    source._dirs.clear()
    home_skills.mkdir(parents=True, exist_ok=True)

    for i in range(5):
        _write_skill_json(workspace / "skills" / f"s{i}.json", f"s{i}", f"skill {i}")

    write_root_config(
        {
            "skills": {
                "limits": {
                    "maxSkillsInPrompt": 2,
                    "maxSkillsPromptChars": 120,
                }
            }
        }
    )
    snapshot = build_skill_snapshot(workspace_dir=str(workspace))
    assert snapshot["count"] == 5
    assert snapshot["prompt_count"] <= 2
    assert snapshot["prompt_truncated"] is True

