"""Tests for Markdown skill format (SKILL.md / frontmatter) — OpenClaw compatible."""

from __future__ import annotations

import pytest

from mw4agent.skills.format_md import parse_skill_markdown


def test_parse_skill_markdown_openclaw_style() -> None:
    """OpenClaw-style: YAML frontmatter with name, description, metadata."""
    content = """---
name: file-ops
description: List and read files in a directory. Use when user asks to list or read files.
metadata: {"clawdbot":{"emoji":"📁","requires":{"anyBins":["ls","cat"]},"os":["linux","darwin"]}}
---

# File operations

When to use: user asks to list directory or read file contents.
"""
    data = parse_skill_markdown(content)
    assert data["name"] == "file-ops"
    assert "List and read files" in data["description"]
    assert data.get("tools") == ["ls", "cat"]
    assert "content" in data
    assert "When to use" in data["content"]


def test_parse_skill_markdown_minimal() -> None:
    """Minimal frontmatter: only name and description."""
    content = """---
name: demo_skill
description: A minimal skill for tests.
---

# Demo

Body text here.
"""
    data = parse_skill_markdown(content)
    assert data["name"] == "demo_skill"
    assert data["description"] == "A minimal skill for tests."
    assert data.get("enabled") is True
    assert "Body text here" in data.get("content", "")


def test_parse_skill_markdown_no_frontmatter() -> None:
    """Content without --- is treated as body-only."""
    content = "Just a paragraph."
    data = parse_skill_markdown(content)
    assert data.get("name") == ""
    assert data["description"] == "Just a paragraph."
    assert data["content"] == "Just a paragraph."


def test_parse_skill_markdown_description_or_desc() -> None:
    """Accept both description and desc in frontmatter."""
    content = """---
name: test
desc: Short desc key.
---
"""
    data = parse_skill_markdown(content)
    assert data["description"] == "Short desc key."
