"""Root config: single file ~/.mw4agent/mw4agent.json for llm, skills, channels, etc."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from .manager import ConfigManager

# 默认全局配置文件路径，所有配置项（llm、skills、channels 等）均存于此文件
ROOT_CONFIG_FILENAME = "mw4agent.json"


def get_root_config_dir() -> Path:
    """Return the directory containing the root config file.

    Uses MW4AGENT_CONFIG_DIR if set (e.g. for tests), otherwise ~/.mw4agent.
    """
    env_dir = os.environ.get("MW4AGENT_CONFIG_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".mw4agent"


def _get_root_config_manager() -> ConfigManager:
    """Config manager that targets the root config directory.

    The single file used is mw4agent.json; all sections (llm, skills, channels, etc.)
    live inside that JSON object.
    """
    return ConfigManager(config_dir=str(get_root_config_dir()))


def get_root_config_path() -> Path:
    """Return the absolute path to the root config file (~/.mw4agent/mw4agent.json)."""
    return get_root_config_dir() / ROOT_CONFIG_FILENAME


def read_root_config() -> Dict[str, Any]:
    """Read the full root config (~/.mw4agent/mw4agent.json)."""
    mgr = _get_root_config_manager()
    return mgr.read_config(ROOT_CONFIG_FILENAME.replace(".json", ""), default={})


def write_root_config(data: Dict[str, Any]) -> None:
    """Write the full root config (~/.mw4agent/mw4agent.json)."""
    mgr = _get_root_config_manager()
    mgr.write_config(ROOT_CONFIG_FILENAME.replace(".json", ""), data)


def read_root_section(section: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Read one section (e.g. llm, skills, channels) from the root config file."""
    root = read_root_config()
    val = root.get(section)
    if isinstance(val, dict):
        return val
    return default if default is not None else {}


def write_root_section(section: str, data: Dict[str, Any]) -> None:
    """Write one section into the root config file (merge, then write)."""
    root = read_root_config()
    root[section] = data
    write_root_config(root)


class RootConfigManager(ConfigManager):
    """Config manager that reads/writes sections of the single root config file.

    read_config("llm") returns the "llm" key from ~/.mw4agent/mw4agent.json.
    write_config("llm", {...}) merges into that file.
    This is the default config manager so all config (llm, skills, channels, etc.)
    lives in one file by default.
    """

    def __init__(self) -> None:
        super().__init__(config_dir=str(get_root_config_dir()))

    def read_config(self, name: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Read a section by name from the root config file."""
        return read_root_section(name, default=default or {})

    def write_config(self, name: str, data: Dict[str, Any]) -> None:
        """Write a section by name into the root config file."""
        write_root_section(name, data)

    def delete_config(self, name: str) -> bool:
        """Remove a section from the root config file."""
        root = read_root_config()
        if name not in root:
            return False
        del root[name]
        write_root_config(root)
        return True

    def list_configs(self) -> list[str]:
        """List section names (top-level keys) in the root config file."""
        root = read_root_config()
        return sorted(k for k in root if isinstance(root[k], dict))

