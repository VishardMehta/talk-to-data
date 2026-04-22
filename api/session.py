"""
Per-session state management — one isolated DuckDB connection per chat session.

Key design:
  - Each Session owns its own duckdb.connect() — fully data-isolated.
    Two users uploading different files never see each other's data.
  - IngestionService loads uploaded files into that connection as named tables.
  - AutoSemantic profiles those tables once and caches the results.
  - ConversationState tracks the last question/SQL/answer for follow-up context.
  - Clearing a session drops everything and creates a fresh connection.
  - Uploaded data NEVER touches permanent disk — temp files are deleted
    immediately after DuckDB loading inside IngestionService.

Session lifecycle:
  1. Frontend generates a session_id (UUID) on page load.
  2. SessionManager.get(session_id) creates a new Session on first access.
  3. User uploads files → IngestionService fills the DuckDB connection.
  4. User asks questions → pipeline reads from session.profiles and session.con.
  5. User clicks "New Chat" → session.clear() resets everything.
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
    """
    All state for one chat session.

    Attributes:
      con                     — in-memory DuckDB connection (all uploaded data lives here)
      ingestion               — loads files into DuckDB, tracks table names and schemas
      semantic                — profiles tables and caches enriched context for SQL generation
      conversation_state      — last Q&A turn, used to handle follow-up questions
      profiles                — table_name → enriched profile dict (from auto_semantic)
      table_names             — ordered list of table names uploaded in this session
      uploaded_filename_tables — filename → [table names] (for re-upload deduplication)
      uploaded_file_cache     — filename+hash → [table names] (content-based dedup)
    """

    def __init__(self):
        self.con = duckdb.connect()                   # in-memory, session-scoped
        self.ingestion = IngestionService(self.con)
        self.semantic  = AutoSemantic(self.con)
        self.conversation_state = ConversationState()

        self.profiles: dict[str, dict] = {}
        self.table_names: list[str] = []
        self.uploaded_filename_tables: dict[str, list[str]] = {}
        self.uploaded_file_cache: dict[str, list[str]] = {}

    @property
    def has_data(self) -> bool:
        """Return True if at least one table has been uploaded to this session."""
        return bool(self.table_names)

    @property
    def primary_table(self) -> str | None:
        """
        Return the first uploaded table name.
        Used for single-file sessions where there is only one table to query.
        """
        return self.table_names[0] if self.table_names else None

    @property
    def primary_profile(self) -> dict | None:
        """
        Return the enriched profile for the first uploaded table.
        Used by the answer generator to build dataset context for the LLM prompt.
        """
        t = self.primary_table
        return self.profiles.get(t) if t else None

    def remove_table(self, table_name: str) -> bool:
        """
        Remove a single table from the session and clean up all references to it.

        This is called when the user clicks the "×" button next to a file in
        the sidebar.  We drop the DuckDB table, remove it from all tracking
        dicts, and clear the conversation state so stale follow-up context
        from the deleted table doesn't affect future queries.

        Returns True if the table was found and removed, False otherwise.
        """
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

        # Remove from every tracking structure
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

        # Dataset changed — clear conversation state to avoid stale follow-up refs
        self.conversation_state.clear()
        return True

    def clear(self):
        """
        Full session reset — drop all DuckDB tables and recreate a fresh connection.

        Called when the user starts a new chat.  We close the existing DuckDB
        connection (freeing all in-memory data), then create a brand-new one
        so the next upload starts with a completely empty database.
        """
        self.ingestion.reset()
        self.semantic.clear()
        self.conversation_state.clear()
        self.profiles = {}
        self.table_names = []
        self.uploaded_filename_tables = {}
        self.uploaded_file_cache = {}

        # Close the old connection to free memory, then create a fresh one
        try:
            self.con.close()
        except Exception:
            pass
        self.con = duckdb.connect()
        self.ingestion = IngestionService(self.con)
        self.semantic  = AutoSemantic(self.con)


class SessionManager:
    """
    Global registry of active sessions, keyed by session_id (UUID string).

    The frontend generates a session_id on page load and sends it with every
    API request.  SessionManager.get() creates a new Session on first access
    so sessions are lazily initialised — no pre-registration needed.
    """

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def get(self, session_id: str) -> Session:
        """
        Return the Session for a given ID, creating it if it doesn't exist yet.
        This is the standard access pattern — every API endpoint calls this.
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = Session()
        return self._sessions[session_id]

    def clear(self, session_id: str):
        """
        Reset the session (keep the session_id alive, wipe all uploaded data).
        Called by the /api/session/clear endpoint when the user starts a new chat.
        """
        if session_id in self._sessions:
            self._sessions[session_id].clear()

    def delete(self, session_id: str):
        """
        Completely remove a session from the registry and close its DuckDB connection.
        Used for cleanup when a session is no longer needed (e.g. tab closed).
        """
        if session_id in self._sessions:
            try:
                self._sessions[session_id].con.close()
            except Exception:
                pass
            del self._sessions[session_id]
