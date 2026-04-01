from __future__ import annotations

import json
from pathlib import Path

import pytest

from mw4agent.config.root import get_root_config_dir, read_root_config


def test_get_root_config_dir_prefers_legacy_when_new_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Simulate running under a temp HOME.
    monkeypatch.delenv("MW4AGENT_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    new_dir = tmp_path / ".mw4agent"
    legacy_dir = new_dir / "config"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "mw4agent.json").write_text(json.dumps({"llm": {"provider": "echo"}}), encoding="utf-8")

    # No new path file exists, but legacy does → pick legacy dir.
    assert get_root_config_dir().resolve() == legacy_dir.resolve()
    assert read_root_config().get("llm", {}).get("provider") == "echo"


def test_get_root_config_dir_uses_new_when_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MW4AGENT_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    new_dir = tmp_path / ".mw4agent"
    new_dir.mkdir(parents=True, exist_ok=True)
    (new_dir / "mw4agent.json").write_text(json.dumps({"llm": {"provider": "openai"}}), encoding="utf-8")

    legacy_dir = new_dir / "config"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "mw4agent.json").write_text(json.dumps({"llm": {"provider": "echo"}}), encoding="utf-8")

    # New path exists → prefer new dir even if legacy exists.
    assert get_root_config_dir().resolve() == new_dir.resolve()
    assert read_root_config().get("llm", {}).get("provider") == "openai"

