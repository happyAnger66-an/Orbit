from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .manager import ConfigManager


def _get_root_config_manager() -> ConfigManager:
    """Config manager that targets the root ~/.mw4agent directory.

    This is used for global config like LLM provider/model, channels, skills, etc.
    """
    home = Path.home()
    root_dir = home / ".mw4agent"
    return ConfigManager(config_dir=str(root_dir))


def get_root_config_path() -> Path:
    """Return the absolute path to the root config file (~/.mw4agent/mw4agent.json)."""
    home = Path.home()
    return home / ".mw4agent" / "mw4agent.json"


def read_root_config() -> Dict[str, Any]:
    """Read the root config (~/.mw4agent/mw4agent.json)."""
    mgr = _get_root_config_manager()
    return mgr.read_config("mw4agent", default={})


def write_root_config(data: Dict[str, Any]) -> None:
    """Write the root config (~/.mw4agent/mw4agent.json)."""
    mgr = _get_root_config_manager()
    mgr.write_config("mw4agent", data)

