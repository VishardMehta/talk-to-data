"""
Per-session state — one DuckDB in-memory connection per chat session.

Key design:
  - Each Session owns its own duckdb.connect() — fully isolated
  - IngestionService loads files into that connection as named tables
  - AutoSemantic profiles those tables (no file paths involved)
  - Clearing a session drops everything and creates a fresh connection
  - Uploaded data NEVER touches disk permanently (temp files are deleted
    immediately after DuckDB loading in IngestionService)
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb

from app.core.state import ConversationState
from app.core.ingestion import IngestionService
from app.core.auto_semantic import AutoSemantic


class Session:
    def __init__(self):
        self.con = duckdb.connect()                  # in-memory, session-scoped
        self.ingestion = IngestionService(self.con)
        self.semantic = AutoSemantic(self.con)
        self.conversation_state = ConversationState()

        # Filled after upload:  table_name -> enriched profile dict
        self.profiles: dict[str, dict] = {}
        # Ordered list of table names (in upload order)
        self.table_names: list[str] = []
        # Upload bookkeeping: filename -> tables and filename+hash -> tables
        self.uploaded_filename_tables: dict[str, list[str]] = {}
        self.uploaded_file_cache: dict[str, list[str]] = {}

    @property
    def has_data(self) -> bool:
        return bool(self.table_names)

    @property
    def primary_table(self) -> str | None:
        """Return the first uploaded table name (for single-file compat)."""
        return self.table_names[0] if self.table_names else None

    @property
    def primary_profile(self) -> dict | None:
        t = self.primary_table
        return self.profiles.get(t) if t else None

    def remove_table(self, table_name: str) -> bool:
        """Remove a single table and associated session metadata."""
        exists = (
            table_name in self.table_names
            or table_name in self.profiles
            or table_name in self.ingestion.table_schemas
        )

        if not exists:
            return False

        try:
            self.con.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        except Exception:
            return False

        self.table_names = [t for t in self.table_names if t != table_name]
        self.profiles.pop(table_name, None)
        self.semantic._cache.pop(table_name, None)

        self.ingestion.tables = [t for t in self.ingestion.tables if t != table_name]
        self.ingestion.table_schemas.pop(table_name, None)

        for filename, tables in list(self.uploaded_filename_tables.items()):
            filtered = [t for t in tables if t != table_name]
            if filtered:
                self.uploaded_filename_tables[filename] = filtered
            else:
                self.uploaded_filename_tables.pop(filename, None)

        for cache_key, tables in list(self.uploaded_file_cache.items()):
            filtered = [t for t in tables if t != table_name]
            if filtered:
                self.uploaded_file_cache[cache_key] = filtered
            else:
                self.uploaded_file_cache.pop(cache_key, None)

        # Dataset context changed; clear follow-up state to avoid stale references.
        self.conversation_state.clear()
        return True

    def clear(self):
        """Full reset — drop all DuckDB tables and start fresh."""
        self.ingestion.reset()
        self.semantic.clear()
        self.conversation_state.clear()
        self.profiles = {}
        self.table_names = []
        self.uploaded_filename_tables = {}
        self.uploaded_file_cache = {}
        # Recreate the connection for a truly clean slate
        try:
            self.con.close()
        except Exception:
            pass
        self.con = duckdb.connect()
        self.ingestion = IngestionService(self.con)
        self.semantic = AutoSemantic(self.con)


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def get(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session()
        return self._sessions[session_id]

    def clear(self, session_id: str):
        if session_id in self._sessions:
            self._sessions[session_id].clear()

    def delete(self, session_id: str):
        if session_id in self._sessions:
            try:
                self._sessions[session_id].con.close()
            except Exception:
                pass
            del self._sessions[session_id]
