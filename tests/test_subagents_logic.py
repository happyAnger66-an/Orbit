"""Tests for ``orbit.gateway.subagents_logic`` (stdlib only)."""

from __future__ import annotations

from pathlib import Path

from orbit.gateway.subagents_logic import (
    DesktopSubagentRecord,
    filter_subagents_for_parent,
    read_text_file_tail,
    resolve_subagent_list_spec,
    resolve_transcript_path_for_manager,
    subagents_help_markdown,
)


def _rec(
    *,
    run_id: str,
    parent_agent_id: str = "main",
    parent_session_id: str = "sess-p",
    parent_session_key: str = "desktop-app",
    child_session_id: str = "c1",
    target_agent_id: str = "main",
    task: str = "t",
) -> DesktopSubagentRecord:
    return DesktopSubagentRecord(
        run_id=run_id,
        parent_agent_id=parent_agent_id,
        parent_session_id=parent_session_id,
        parent_session_key=parent_session_key,
        child_session_id=child_session_id,
        child_session_key=f"{parent_session_key}:subagent:{child_session_id}",
        target_agent_id=target_agent_id,
        task=task,
    )


def test_filter_subagents_for_parent_sorts_by_created_ms() -> None:
    r_old = _rec(run_id="aaaaaaaa-0000-0000-0000-000000000001", child_session_id="c1")
    r_old.created_ms = 100
    r_new = _rec(run_id="bbbbbbbb-0000-0000-0000-000000000002", child_session_id="c2")
    r_new.created_ms = 200
    other_parent = _rec(
        run_id="cccccccc-0000-0000-0000-000000000003",
        parent_session_id="other",
        child_session_id="c3",
    )
    bag = [r_new, "skip-me", r_old, other_parent]
    got = filter_subagents_for_parent(bag, "main", "sess-p")
    assert got == [r_old, r_new]


def test_resolve_subagent_list_spec_hash_and_prefix() -> None:
    r1 = _rec(run_id="aaaaaaaa-1111-1111-1111-111111111111")
    r2 = _rec(run_id="bbbbbbbb-2222-2222-2222-222222222222", child_session_id="c2")
    recs = [r1, r2]
    assert resolve_subagent_list_spec(recs, "#1") is r1
    assert resolve_subagent_list_spec(recs, "#2") is r2
    assert resolve_subagent_list_spec(recs, "#0") is None
    assert resolve_subagent_list_spec(recs, "#3") is None
    assert resolve_subagent_list_spec(recs, "aaaa") is r1
    r_amb_a = _rec(run_id="dup-aaaaaaaa-0000-0000-0000-000000000001", child_session_id="ca")
    r_amb_b = _rec(run_id="dup-aaaaaaaa-0000-0000-0000-000000000002", child_session_id="cb")
    assert resolve_subagent_list_spec([r_amb_a, r_amb_b], "dup-aaaaaaaa") is None
    assert resolve_subagent_list_spec(recs, "") is None


def test_resolve_transcript_path_for_manager_dual_signature() -> None:
    class WithAgent:
        def resolve_transcript_path(self, session_id: str, *, agent_id: str) -> str:
            return f"{session_id}:{agent_id}"

    class Legacy:
        def resolve_transcript_path(self, session_id: str) -> str:
            return session_id

    assert resolve_transcript_path_for_manager(WithAgent(), "s1", "main") == "s1:main"
    assert resolve_transcript_path_for_manager(Legacy(), "s1", "main") == "s1"


def test_read_text_file_tail(tmp_path: Path) -> None:
    p = tmp_path / "t.txt"
    p.write_text("a\nb\nc\nd\n", encoding="utf-8")
    assert read_text_file_tail(str(p), 2) == "c\nd"
    assert read_text_file_tail(str(p), 999) == "a\nb\nc\nd"
    assert "(无法读取" in read_text_file_tail(str(tmp_path / "missing"), 5)


def test_subagents_help_markdown_nonempty() -> None:
    h = subagents_help_markdown()
    assert "/subagents list" in h
    assert "spawn" in h
