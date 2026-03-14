"""Parse skill Markdown files (SKILL.md) with YAML frontmatter — OpenClaw compatible.

OpenClaw uses:
  - workspaceDir/skills/<skillName>/SKILL.md
  - Frontmatter between --- with: name, description, optional metadata.
  - Markdown body after frontmatter as skill content/prompt.

This module parses such files into the same dict shape as JSON skills:
  name, description, tools?, examples?, enabled?, content? (body).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

# Frontmatter delimiter
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def parse_skill_markdown(content: str) -> Dict[str, Any]:
    """Parse a SKILL.md-style string (YAML frontmatter + Markdown body) into a skill dict.

    Compatible with OpenClaw SKILL.md: frontmatter has at least `name` and `description`.
    Optional: `metadata` (e.g. requires.bins -> tools), `enabled`, etc.

    Returns:
        Dict with keys: name, description; optionally tools, examples, enabled, content.
        Always includes "content" with the raw Markdown body when present.
    """
    content = content.strip()
    if not content.startswith("---"):
        return _dict_from_body_only(content)

    match = FRONTMATTER_RE.match(content)
    if not match:
        return _dict_from_body_only(content)

    frontmatter_str, body = match.group(1).strip(), match.group(2).strip()
    data: Dict[str, Any] = {}

    if yaml is None:
        # Fallback: minimal key: value parsing
        data = _parse_frontmatter_minimal(frontmatter_str)
    else:
        try:
            data = yaml.safe_load(frontmatter_str)
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = _parse_frontmatter_minimal(frontmatter_str)

    # Normalize to our schema: name, description, tools?, examples?, enabled?
    name = data.get("name") or data.get("title")
    if isinstance(name, str):
        data["name"] = name.strip()
    desc = data.get("description") or data.get("desc")
    if isinstance(desc, str):
        data["description"] = desc.strip()
    elif desc is not None and not isinstance(desc, str):
        data["description"] = str(desc).strip()

    # OpenClaw metadata: optional requires.anyBins / requires.bins -> tools
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        claw = metadata.get("clawdbot") or metadata.get("clawbot")
        if isinstance(claw, dict):
            req = claw.get("requires") or {}
            if isinstance(req, dict):
                bins = req.get("anyBins") or req.get("bins") or []
                if isinstance(bins, list) and bins:
                    data["tools"] = [str(b) for b in bins]
    # Direct optional fields
    if "tools" not in data and data.get("tools"):
        t = data["tools"]
        data["tools"] = t if isinstance(t, list) else [t]
    if "examples" in data and not isinstance(data["examples"], list):
        data["examples"] = [data["examples"]] if data["examples"] else []
    if "enabled" not in data:
        data["enabled"] = True

    if body:
        data["content"] = body

    return data


def _parse_frontmatter_minimal(text: str) -> Dict[str, Any]:
    """Simple key: value parser when YAML is not available."""
    out: Dict[str, Any] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if not key:
            continue
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1].replace('\\"', '"')
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("\\'", "'")
        if key == "enabled":
            out[key] = value.lower() in ("true", "1", "yes", "on")
        else:
            out[key] = value
    return out


def _dict_from_body_only(content: str) -> Dict[str, Any]:
    """When no frontmatter, treat whole content as description/body."""
    return {
        "name": "",
        "description": content.strip()[:500] if content else "",
        "content": content.strip() if content else "",
        "enabled": True,
    }
