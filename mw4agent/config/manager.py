"""Configuration manager with encrypted file storage.

This module provides a unified interface for reading/writing MW4Agent configuration files
with automatic encryption support.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..crypto import EncryptionConfigError, get_default_encrypted_store


class ConfigManager:
    """Manages MW4Agent configuration files with encryption support.

    Configuration files are stored in `~/.mw4agent/config/` by default.
    All files are automatically encrypted using the encryption framework.
    """

    def __init__(self, config_dir: Optional[str] = None) -> None:
        """Initialize config manager.

        Args:
            config_dir: Base directory for config files. Defaults to `~/.mw4agent/config/`.
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            home = Path.home()
            self.config_dir = home / ".mw4agent" / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _get_config_path(self, name: str) -> Path:
        """Get full path for a config file."""
        if not name.endswith(".json"):
            name = f"{name}.json"
        return self.config_dir / name

    def read_config(self, name: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Read a configuration file.

        Args:
            name: Config file name (with or without .json extension).
            default: Default value if file doesn't exist.

        Returns:
            Configuration dictionary.
        """
        path = self._get_config_path(name)
        if not path.exists():
            return default or {}

        try:
            store = get_default_encrypted_store()
            data = store.read_json(str(path), fallback_plaintext=True)
            if isinstance(data, dict):
                return data
            return default or {}
        except EncryptionConfigError as e:
            # If encryption is not configured, try plaintext fallback
            print(f"Warning: Encryption not configured, falling back to plaintext: {e}")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
                    return default or {}
            except Exception as e2:
                print(f"Warning: Failed to load plaintext config: {e2}")
                return default or {}

    def write_config(self, name: str, data: Dict[str, Any]) -> None:
        """Write a configuration file (encrypted).

        Args:
            name: Config file name (with or without .json extension).
            data: Configuration dictionary to write.
        """
        path = self._get_config_path(name)
        try:
            store = get_default_encrypted_store()
            store.write_json(str(path), data)
        except EncryptionConfigError:
            # Fallback to plaintext if encryption is not configured
            print("Warning: Encryption not configured, writing plaintext config")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def delete_config(self, name: str) -> bool:
        """Delete a configuration file.

        Returns:
            True if file was deleted, False if it didn't exist.
        """
        path = self._get_config_path(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_configs(self) -> list[str]:
        """List all configuration file names (without .json extension)."""
        if not self.config_dir.exists():
            return []
        configs = []
        for path in self.config_dir.glob("*.json"):
            configs.append(path.stem)
        return sorted(configs)


_default_config_manager: Optional[ConfigManager] = None


def get_default_config_manager() -> ConfigManager:
    """Get the default config manager instance."""
    global _default_config_manager
    if _default_config_manager is None:
        _default_config_manager = ConfigManager()
    return _default_config_manager
