"""Per-session state — replaces st.session_state for the FastAPI server."""
from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.state import ConversationState
from app.core.duckdb_engine import DuckDBEngine
from app.core.auto_semantic import AutoSemantic


class Session:
    def __init__(self):
        self.conversation_state = ConversationState()
        self.duckdb_engine = DuckDBEngine()
        self.auto_semantic = AutoSemantic(self.duckdb_engine)
        self.profiled_files: dict = {}   # filepath -> profile dict
        self.app_mode: str = "demo"      # "demo" | "upload"

    def clear(self):
        self.conversation_state.clear()
        self.profiled_files = {}
        self.app_mode = "demo"
        self.duckdb_engine = DuckDBEngine()
        self.auto_semantic = AutoSemantic(self.duckdb_engine)


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
        self._sessions.pop(session_id, None)
