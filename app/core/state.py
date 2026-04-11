"""
Conversation state management for multi-turn support.
Tracks the current topic, last query context, and enables follow-up questions.
"""


class ConversationState:
    """Simple conversation state for multi-turn context."""

    def __init__(self):
        self.topic: str = ""
        self.filters_applied: dict = {}
        self.tables_used: list = []
        self.last_sql: str = ""
        self.last_results: any = None
        self.last_answer: str = ""
        self.last_question: str = ""
        self._history: list[dict] = []

    def update(
        self,
        question: str,
        sql: str | None,
        results: any,
        answer: str,
        tables: list[str],
    ) -> None:
        """Update state after processing a query."""
        self.last_question = question
        self.last_sql = sql or ""
        self.last_results = results
        self.last_answer = answer
        self.tables_used = tables or []
        
        # Extract topic from question (first few meaningful words)
        self.topic = question.strip()
        
        # Maintain history (last 5 turns)
        self._history.append({
            "question": question,
            "sql": sql,
            "answer": answer,
            "tables": tables,
        })
        if len(self._history) > 5:
            self._history.pop(0)

    def get_context_for_followup(self) -> str:
        """
        Return a compact string summarizing the conversation context
        for use by the router and SQL generator on follow-up questions.
        """
        if not self.last_question:
            return ""
        
        lines = [
            f"Previous context: The user asked: \"{self.last_question}\"",
        ]
        
        if self.last_sql:
            # Truncate SQL if too long
            sql_preview = self.last_sql[:300]
            if len(self.last_sql) > 300:
                sql_preview += "..."
            lines.append(f"The SQL was: {sql_preview}")
        
        if self.last_answer:
            # Truncate answer if too long
            answer_preview = self.last_answer[:200]
            if len(self.last_answer) > 200:
                answer_preview += "..."
            lines.append(f"The answer was: {answer_preview}")
        
        if self.tables_used:
            lines.append(f"Tables used: {', '.join(self.tables_used)}")
        
        lines.append("The user may be asking a follow-up about the same topic.")
        
        return "\n".join(lines)

    def clear(self) -> None:
        """Reset all conversation state."""
        self.topic = ""
        self.filters_applied = {}
        self.tables_used = []
        self.last_sql = ""
        self.last_results = None
        self.last_answer = ""
        self.last_question = ""
        self._history.clear()

    @property
    def has_context(self) -> bool:
        """Check if there is previous context available."""
        return bool(self.last_question)

    @property
    def turn_count(self) -> int:
        """Number of conversation turns."""
        return len(self._history)
