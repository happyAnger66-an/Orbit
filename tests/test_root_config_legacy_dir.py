from __future__ import annotations

import json
from pathlib import Path

import pytest

from orbit.config.root import get_root_config_dir, read_root_config


def test_get_root_config_dir_prefers_legacy_when_new_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Simulate running under a temp HOME.
    monkeypatch.delenv("ORBIT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MW4AGENT_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    new_dir = tmp_path / "orbit"
    legacy_dir = new_dir / "config"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "orbit.json").write_text(json.dumps({"llm": {"provider": "echo"}}), encoding="utf-8")

    # No new path file exists, but legacy does → pick legacy dir.
    assert get_root_config_dir().resolve() == legacy_dir.resolve()
    assert read_root_config().get("llm", {}).get("provider") == "echo"


def test_get_root_config_dir_uses_new_when_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ORBIT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MW4AGENT_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    new_dir = tmp_path / "orbit"
    new_dir.mkdir(parents=True, exist_ok=True)
    (new_dir / "orbit.json").write_text(json.dumps({"llm": {"provider": "openai"}}), encoding="utf-8")

    legacy_dir = new_dir / "config"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "orbit.json").write_text(json.dumps({"llm": {"provider": "echo"}}), encoding="utf-8")

    # New path exists → prefer new dir even if legacy exists.
    assert get_root_config_dir().resolve() == new_dir.resolve()
    assert read_root_config().get("llm", {}).get("provider") == "openai"


def test_get_root_config_dir_prefers_dot_orbit_over_visible_orbit_when_both_exist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ORBIT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MW4AGENT_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    dot = tmp_path / ".orbit"
    dot.mkdir(parents=True, exist_ok=True)
    (dot / "orbit.json").write_text(json.dumps({"llm": {"provider": "from-dot"}}), encoding="utf-8")

    visible = tmp_path / "orbit"
    visible.mkdir(parents=True, exist_ok=True)
    (visible / "orbit.json").write_text(json.dumps({"llm": {"provider": "from-visible"}}), encoding="utf-8")

    assert get_root_config_dir().resolve() == dot.resolve()
    assert read_root_config().get("llm", {}).get("provider") == "from-dot"


def test_get_root_config_dir_defaults_to_dot_orbit_when_no_config_yet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ORBIT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MW4AGENT_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert get_root_config_dir().resolve() == (tmp_path / ".orbit").resolve()


def test_get_root_config_dir_falls_back_to_dot_orbit_when_only_dot_has_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Config only under ~/.orbit (no visible ~/orbit/)."""
    monkeypatch.delenv("ORBIT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MW4AGENT_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    dot = tmp_path / ".orbit"
    dot.mkdir(parents=True, exist_ok=True)
    (dot / "orbit.json").write_text(json.dumps({"llm": {"provider": "echo"}}), encoding="utf-8")

    assert get_root_config_dir().resolve() == dot.resolve()
    assert read_root_config().get("llm", {}).get("provider") == "echo"


def test_get_root_config_dir_falls_back_to_legacy_mw4agent_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ORBIT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MW4AGENT_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    old = tmp_path / ".mw4agent"
    old.mkdir(parents=True, exist_ok=True)
    (old / "mw4agent.json").write_text(json.dumps({"llm": {"provider": "echo"}}), encoding="utf-8")

    assert get_root_config_dir().resolve() == old.resolve()
    assert read_root_config().get("llm", {}).get("provider") == "echo"

