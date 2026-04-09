"""Execute apply_patch against a workspace directory."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from .apply_patch_parse import parse_patch_text
from .apply_patch_update import apply_update_hunk


@dataclass
class ApplyPatchSummary:
    added: List[str] = field(default_factory=list)
    modified: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)


def _resolve_path(path: str, workspace_dir: str) -> str:
    path = (path or "").strip()
    if not path:
        raise ValueError("apply_patch: path is required")
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(workspace_dir, path))


def _ensure_under_root(resolved: str, root: str) -> None:
    root = os.path.normpath(os.path.abspath(root))
    resolved = os.path.normpath(os.path.abspath(resolved))
    if not resolved.startswith(root):
        raise PermissionError(f"apply_patch: path is outside workspace root: {root}")


def _record(
    summary: ApplyPatchSummary,
    seen: Dict[str, Set[str]],
    bucket: str,
    value: str,
) -> None:
    s = seen.setdefault(bucket, set())
    if value in s:
        return
    s.add(value)
    getattr(summary, bucket).append(value)


def _format_summary(summary: ApplyPatchSummary) -> str:
    lines = ["Success. Updated the following files:"]
    for f in summary.added:
        lines.append(f"A {f}")
    for f in summary.modified:
        lines.append(f"M {f}")
    for f in summary.deleted:
        lines.append(f"D {f}")
    return "\n".join(lines)


def run_apply_patch(
    patch_input: str,
    *,
    workspace_dir: str,
    workspace_only: bool,
) -> Tuple[ApplyPatchSummary, str]:
    """Parse and apply patch. Raises ValueError / PermissionError / OSError on failure."""
    hunks, _ = parse_patch_text(patch_input)
    if not hunks:
        raise ValueError("No files were modified.")

    summary = ApplyPatchSummary()
    seen: Dict[str, Set[str]] = {}
    ws = os.path.abspath(os.path.normpath(workspace_dir))

    def resolve_display(file_path: str) -> Tuple[str, str]:
        resolved = _resolve_path(file_path, ws)
        if workspace_only:
            _ensure_under_root(resolved, ws)
        rel = os.path.relpath(resolved, ws)
        display = rel if not rel.startswith("..") else resolved
        return resolved, display

    for hunk in hunks:
        kind = hunk.get("kind")
        if kind == "add":
            resolved, display = resolve_display(hunk["path"])
            parent = os.path.dirname(resolved) or "."
            os.makedirs(parent, exist_ok=True)
            with open(resolved, "w", encoding="utf-8") as f:
                f.write(hunk.get("contents") or "")
            _record(summary, seen, "added", display)
            continue

        if kind == "delete":
            resolved, display = resolve_display(hunk["path"])
            if workspace_only:
                _ensure_under_root(resolved, ws)
            if os.path.isdir(resolved):
                raise ValueError(f"apply_patch: delete target is a directory: {display}")
            try:
                os.remove(resolved)
            except FileNotFoundError:
                raise ValueError(f"apply_patch: file not found for delete: {display}") from None
            _record(summary, seen, "deleted", display)
            continue

        if kind == "update":
            resolved, display = resolve_display(hunk["path"])
            chunks = hunk.get("chunks") or []

            def read_file(p: str) -> str:
                with open(p, encoding="utf-8") as rf:
                    return rf.read()

            applied = apply_update_hunk(resolved, chunks, read_file=read_file)
            move_path = hunk.get("move_path")
            if move_path:
                move_resolved, move_display = resolve_display(move_path)
                parent = os.path.dirname(move_resolved) or "."
                os.makedirs(parent, exist_ok=True)
                with open(move_resolved, "w", encoding="utf-8") as wf:
                    wf.write(applied)
                os.remove(resolved)
                _record(summary, seen, "modified", move_display)
            else:
                with open(resolved, "w", encoding="utf-8") as wf:
                    wf.write(applied)
                _record(summary, seen, "modified", display)
            continue

        raise ValueError(f"apply_patch: unknown hunk kind: {kind!r}")

    return summary, _format_summary(summary)
