from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationState:
    topic: str = ""
    filters_applied: dict = field(default_factory=dict)
    tables_used: list = field(default_factory=list)
    last_sql: str = ""
    last_results: Any = None
    last_answer: str = ""
    last_question: str = ""

    def update(self, question: str, sql: str, results: Any, answer: str, tables: list):
        self.last_question = question
        self.last_sql = sql or ""
        self.last_results = results
        self.last_answer = answer
        self.tables_used = tables or []
        # Derive topic from the question
        self.topic = question[:120]

    def get_context_for_followup(self) -> str:
        if not self.last_question:
            return ""
        parts = [f'Previous question: "{self.last_question}"']
        if self.last_answer:
            parts.append(f'Previous answer: "{self.last_answer[:200]}"')
        if self.last_sql:
            parts.append(f"SQL used: {self.last_sql[:300]}")
        if self.tables_used:
            parts.append(f"Tables referenced: {', '.join(self.tables_used)}")
        return "\n".join(parts)

    def clear(self):
        self.topic = ""
        self.filters_applied = {}
        self.tables_used = []
        self.last_sql = ""
        self.last_results = None
        self.last_answer = ""
        self.last_question = ""
