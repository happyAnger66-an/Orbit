"""Session Manager - manages agent sessions.

加密适配：
- 原先直接以 JSON 形式明文写入磁盘；
- 现在改为优先使用 `EncryptedFileStore` 进行加密读写；
- 为了平滑迁移，若文件不是加密格式，可按明文 JSON 读入并在下一次保存时写成加密格式。
"""

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import time

from ...crypto import get_default_encrypted_store, EncryptionConfigError  # type: ignore[attr-defined]


@dataclass
class SessionEntry:
    """Session entry - similar to OpenClaw's SessionEntry"""

    session_id: str
    session_key: str
    agent_id: Optional[str] = None
    created_at: int = 0
    updated_at: int = 0
    message_count: int = 0
    total_tokens: int = 0
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.created_at == 0:
            self.created_at = int(time.time() * 1000)
        if self.updated_at == 0:
            self.updated_at = self.created_at


class SessionManager:
    """Manages agent sessions - similar to OpenClaw's SessionManager"""

    def __init__(self, session_file: str):
        """
        Args:
            session_file: Path to session file (JSON or encrypted JSON)
        """
        self.session_file = Path(session_file)
        self.sessions: Dict[str, SessionEntry] = {}
        self._load()

    def _load(self) -> None:
        """Load sessions from file (encrypted first, fallback to plaintext)."""
        if not self.session_file.exists():
            return
        try:
            store = get_default_encrypted_store()
            data = store.read_json(str(self.session_file), fallback_plaintext=True)
        except EncryptionConfigError:
            # 未配置密钥时，退化为明文 JSON 读取（开发/测试场景）
            try:
                with open(self.session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:  # pragma: no cover - 容错路径
                print(f"Warning: Failed to load sessions (plaintext fallback): {e}")
                return
        except Exception as e:
            print(f"Warning: Failed to load sessions (encrypted): {e}")
            return

        if isinstance(data, dict) and "sessions" in data:
            for session_data in data["sessions"]:
                try:
                    entry = SessionEntry(**session_data)
                except TypeError:
                    continue
                self.sessions[entry.session_id] = entry

    def _save(self) -> None:
        """Save sessions to file (prefer encrypted; fallback to plaintext)."""
        try:
            self.session_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "sessions": [asdict(entry) for entry in self.sessions.values()],
            }
            try:
                store = get_default_encrypted_store()
                store.write_json(str(self.session_file), payload)
            except EncryptionConfigError:
                # 无密钥时，退化为原始明文 JSON 写入（开发/测试模式）
                with open(self.session_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to save sessions: {e}")

    def get_session(self, session_id: str) -> Optional[SessionEntry]:
        """Get session by ID"""
        return self.sessions.get(session_id)

    def get_or_create_session(
        self,
        session_id: str,
        session_key: str,
        agent_id: Optional[str] = None,
    ) -> SessionEntry:
        """Get or create a session"""
        if session_id in self.sessions:
            entry = self.sessions[session_id]
            entry.updated_at = int(time.time() * 1000)
            self._save()
            return entry

        entry = SessionEntry(
            session_id=session_id,
            session_key=session_key,
            agent_id=agent_id,
        )
        self.sessions[session_id] = entry
        self._save()
        return entry

    def update_session(self, session_id: str, **kwargs) -> None:
        """Update session metadata"""
        if session_id not in self.sessions:
            return
        entry = self.sessions[session_id]
        entry.updated_at = int(time.time() * 1000)
        for key, value in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        self._save()

    def list_sessions(self, agent_id: Optional[str] = None) -> List[SessionEntry]:
        """List all sessions, optionally filtered by agent_id"""
        sessions = list(self.sessions.values())
        if agent_id:
            sessions = [s for s in sessions if s.agent_id == agent_id]
        return sorted(sessions, key=lambda s: s.updated_at, reverse=True)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            self._save()
            return True
        return False
