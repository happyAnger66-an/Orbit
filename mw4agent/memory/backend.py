"""Memory backend abstraction (Phase 0: stub delegating to file-based search).

This module introduces a minimal MemoryBackend interface and a default
implementation that simply delegates to the existing file-based memory.search /
read_file functions. Later phases can swap this out for a real MemoryIndexManager
with embeddings / hybrid search without changing tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .search import (
    MemorySearchResult,
    MemoryReadResult,
    search as file_search_search,
    read_file as file_search_read_file,
)
from .index import index_files, search_index
from ..config.root import read_root_section
from ..config.paths import resolve_agent_dir


@dataclass
class SearchOptions:
    max_results: int = 10
    min_score: float = 0.0
    session_key: Optional[str] = None
    session_id: Optional[str] = None
    agent_id: Optional[str] = None


class MemoryBackend:
    """Base interface for memory backends.

    Phase 0: only the default stub implementation is used.
    """

    def search(
        self,
        query: str,
        workspace_dir: str,
        *,
        options: SearchOptions,
    ) -> List[file_search.MemorySearchResult]:
        raise NotImplementedError

    def read_file(
        self,
        workspace_dir: str,
        rel_path: str,
        *,
        from_line: Optional[int] = None,
        lines: Optional[int] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> file_search.MemoryReadResult:
        raise NotImplementedError

    def sync(self, *, reason: str = "manual") -> None:
        """Placeholder for future index sync."""
        return None

    def note_session_delta(
        self,
        *,
        session_id: str,
        bytes_delta: int = 0,
        messages_delta: int = 0,
    ) -> None:
        """Placeholder for future session delta tracking."""
        return None

    def status(self) -> Dict[str, Any]:
        """Return backend status/diagnostics (stub for now)."""
        return {}


class StubMemoryBackend(MemoryBackend):
    """Phase 0 backend: delegate to existing file-based search/read_file."""

    def search(
        self,
        query: str,
        workspace_dir: str,
        *,
        options: SearchOptions,
    ) -> List[MemorySearchResult]:
        return file_search_search(
            query,
            workspace_dir,
            max_results=options.max_results,
            min_score=options.min_score,
            session_key=options.session_key,
            session_id=options.session_id,
            agent_id=options.agent_id,
        )

    def read_file(
        self,
        workspace_dir: str,
        rel_path: str,
        *,
        from_line: Optional[int] = None,
        lines: Optional[int] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> MemoryReadResult:
        return file_search_read_file(
            workspace_dir,
            rel_path,
            from_line=from_line,
            lines=lines,
            session_id=session_id,
            agent_id=agent_id,
        )


class LocalIndexBackend(MemoryBackend):
    """Phase 1 backend: SQLite index over workspace files (memory source only).

    This backend is intentionally minimal:
    - It only indexes MEMORY.md + memory/*.md (source='memory').
    - It uses LIKE-based search over the stored content.
    - It rebuilds the 'memory' portion of the index on first use.
    """

    def __init__(self, *, memory_cfg: Dict[str, Any]) -> None:
        self._memory_cfg = memory_cfg if isinstance(memory_cfg, dict) else {}
        self._indexed_workspaces: set[tuple[str, str]] = set()  # (agent_id, workspace_dir)

    def _db_path_for(self, agent_id: Optional[str]) -> str:
        aid = (agent_id or "").strip().lower() or "main"
        agent_dir = resolve_agent_dir(aid)
        return str(Path(agent_dir) / "memory" / "index.sqlite")

    def _ensure_index(self, *, agent_id: Optional[str], workspace_dir: str) -> str:
        key = ((agent_id or "").strip().lower() or "main", str(Path(workspace_dir).resolve()))
        db_path = self._db_path_for(agent_id)
        if key not in self._indexed_workspaces:
            index_files(db_path=db_path, workspace_dir=workspace_dir, sources=("memory",))
            self._indexed_workspaces.add(key)
        return db_path

    def search(
        self,
        query: str,
        workspace_dir: str,
        *,
        options: SearchOptions,
    ) -> List[MemorySearchResult]:
        db_path = self._ensure_index(agent_id=options.agent_id, workspace_dir=workspace_dir)
        rows = search_index(
            db_path=db_path,
            query=query,
            max_results=options.max_results,
            min_score=options.min_score,
        )
        out: List[MemorySearchResult] = []
        for row in rows:
            out.append(
                MemorySearchResult(
                    path=str(row.get("path") or ""),
                    start_line=int(row.get("start_line") or 1),
                    end_line=int(row.get("end_line") or 1),
                    score=float(row.get("score") or 1.0),
                    snippet=str(row.get("snippet") or ""),
                    source=str(row.get("source") or "memory") or "memory",
                )
            )
        return out

    def read_file(
        self,
        workspace_dir: str,
        rel_path: str,
        *,
        from_line: Optional[int] = None,
        lines: Optional[int] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> MemoryReadResult:
        # For Phase 1, delegate actual file reading to the existing implementation.
        return file_search_read_file(
            workspace_dir,
            rel_path,
            from_line=from_line,
            lines=lines,
            session_id=session_id,
            agent_id=agent_id,
        )


_default_backend: Optional[MemoryBackend] = None


def get_memory_backend() -> MemoryBackend:
    """Return the process-wide MemoryBackend instance.

    Selection logic (Phase 1):
    - If root config section "memory" has enabled=true, use LocalIndexBackend (SQLite index).
    - Otherwise fall back to StubMemoryBackend (file-based search).
    """
    global _default_backend
    if _default_backend is None:
        cfg = read_root_section("memory", default={})
        enabled = False
        if isinstance(cfg, dict):
            val = cfg.get("enabled")
            if isinstance(val, bool):
                enabled = val
        if enabled:
            _default_backend = LocalIndexBackend(memory_cfg=cfg)
        else:
            _default_backend = StubMemoryBackend()
    return _default_backend

