"""Tests for ``orbit.gateway.subagents_parse`` (no FastAPI)."""

from __future__ import annotations

import pytest

from orbit.gateway.subagents_parse import (
    is_subagents_command_line,
    parse_spawn_agent_and_task,
    split_subagents_args,
)


def test_is_subagents_command_line() -> None:
    assert is_subagents_command_line("/subagents list") is True
    assert is_subagents_command_line("  /subagents  ") is True
    assert is_subagents_command_line("/subagents") is True
    assert is_subagents_command_line("/reset") is False
    assert is_subagents_command_line("hello") is False


def test_split_subagents_args() -> None:
    assert split_subagents_args("list") == ["list"]
    assert split_subagents_args('spawn main "two words" tail') == [
        "spawn",
        "main",
        "two words",
        "tail",
    ]


def test_parse_spawn_agent_and_task() -> None:
    aid, task = parse_spawn_agent_and_task(["main", "hello", "world"])
    assert aid == "main"
    assert task == "hello world"
    with pytest.raises(ValueError):
        parse_spawn_agent_and_task(["only"])


def test_split_subagents_args_shlex_error() -> None:
    with pytest.raises(ValueError):
        split_subagents_args('spawn main "broken')
