"""apply_patch parse + workspace application."""

from __future__ import annotations

from pathlib import Path

import pytest

from orbit.agents.tools.apply_patch_impl import run_apply_patch
from orbit.agents.tools.apply_patch_parse import parse_patch_text
from orbit.agents.tools.apply_patch_tool import ApplyPatchTool


def test_parse_update_minimal() -> None:
    text = """*** Begin Patch
*** Update File: x.py
@@
-a
+b
*** End Patch"""
    hunks, _ = parse_patch_text(text)
    assert len(hunks) == 1
    assert hunks[0]["kind"] == "update"
    assert hunks[0]["path"] == "x.py"
    assert len(hunks[0]["chunks"]) == 1
    assert hunks[0]["chunks"][0]["old_lines"] == ["a"]
    assert hunks[0]["chunks"][0]["new_lines"] == ["b"]


def test_run_add_and_update(tmp_path: Path) -> None:
    patch = """*** Begin Patch
*** Add File: new.txt
+one
+two
*** Update File: old.txt
@@
-foo
+bar
*** End Patch"""
    (tmp_path / "old.txt").write_text("foo\n", encoding="utf-8")
    summary, out = run_apply_patch(
        patch,
        workspace_dir=str(tmp_path),
        workspace_only=True,
    )
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "one\ntwo\n"
    assert (tmp_path / "old.txt").read_text(encoding="utf-8") == "bar\n"
    assert "new.txt" in summary.added
    assert "old.txt" in summary.modified
    assert "Success" in out


def test_run_delete(tmp_path: Path) -> None:
    (tmp_path / "gone.txt").write_text("x", encoding="utf-8")
    patch = """*** Begin Patch
*** Delete File: gone.txt
*** End Patch"""
    summary, _ = run_apply_patch(
        patch,
        workspace_dir=str(tmp_path),
        workspace_only=True,
    )
    assert not (tmp_path / "gone.txt").exists()
    assert "gone.txt" in summary.deleted


def test_run_move(tmp_path: Path) -> None:
    (tmp_path / "src.txt").write_text("content\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: src.txt
*** Move to: dst.txt
@@
-content
+changed
*** End Patch"""
    summary, _ = run_apply_patch(
        patch,
        workspace_dir=str(tmp_path),
        workspace_only=True,
    )
    assert not (tmp_path / "src.txt").exists()
    assert (tmp_path / "dst.txt").read_text(encoding="utf-8") == "changed\n"
    assert "dst.txt" in summary.modified


def test_workspace_only_rejects_escape(tmp_path: Path) -> None:
    patch = """*** Begin Patch
*** Add File: ../outside.txt
+bad
*** End Patch"""
    with pytest.raises(PermissionError):
        run_apply_patch(patch, workspace_dir=str(tmp_path), workspace_only=True)


@pytest.mark.asyncio
async def test_tool_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    tool = ApplyPatchTool()
    r = await tool.execute("id", {"input": "*** Begin Patch\n*** End Patch"}, {"workspace_dir": str(tmp_path)})
    assert r.success is False
    assert "disabled" in (r.error or "").lower()


@pytest.mark.asyncio
async def test_tool_runs_when_enabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "orbit.agents.tools.apply_patch_tool.is_apply_patch_enabled",
        lambda: True,
    )
    patch = """*** Begin Patch
*** Add File: a.md
+hi
*** End Patch"""
    tool = ApplyPatchTool()
    r = await tool.execute(
        "id",
        {"input": patch},
        {"workspace_dir": str(tmp_path), "tools_fs_workspace_only": True},
    )
    assert r.success is True
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "hi\n"
