"""State dir default: ~/.orbit; legacy ~/.mw4agent is not auto-selected."""

from __future__ import annotations

from pathlib import Path

from orbit.config.paths import _default_state_dir_home


def test_default_state_dir_ignores_legacy_mw4agent_when_absent_orbit(tmp_path: Path) -> None:
    (tmp_path / ".mw4agent").mkdir()
    assert _default_state_dir_home(tmp_path).resolve() == (tmp_path / ".orbit").resolve()


def test_default_state_dir_prefers_dot_orbit_when_both_exist(tmp_path: Path) -> None:
    (tmp_path / ".orbit").mkdir()
    (tmp_path / ".mw4agent").mkdir()
    assert _default_state_dir_home(tmp_path).resolve() == (tmp_path / ".orbit").resolve()


def test_default_state_dir_prefers_non_hidden_orbit_when_no_dot_orbit(tmp_path: Path) -> None:
    (tmp_path / "orbit").mkdir()
    (tmp_path / ".mw4agent").mkdir()
    assert _default_state_dir_home(tmp_path).resolve() == (tmp_path / "orbit").resolve()
