"""
Semantic cache using sentence-transformer embeddings.
Caches question→answer pairs and retrieves them via cosine similarity
to avoid redundant LLM calls for semantically similar questions.
"""

import time
import numpy as np
from datetime import datetime, timedelta


class SemanticCache:
    """In-memory semantic cache with embedding-based similarity lookup."""

    def __init__(self, embedding_model, ttl_seconds: int = 3600):
        """
        Args:
            embedding_model: SentenceTransformer model instance
            ttl_seconds: Time-to-live for cache entries (default 1 hour)
        """
        self._model = embedding_model
        self._ttl = timedelta(seconds=ttl_seconds)
        self._entries: list[dict] = []

    def _embed(self, text: str) -> np.ndarray:
        """Embed a text string and L2-normalize."""
        vec = self._model.encode(text, convert_to_numpy=True)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def find_similar(self, question: str, threshold: float = 0.90) -> dict | None:
        """
        Find a cached result that is semantically similar to the question.

        Args:
            question: The user's question
            threshold: Cosine similarity threshold (0.90 = very similar)

        Returns:
            Cached result dict or None if no match above threshold
        """
        if not self._entries:
            return None

        query_vec = self._embed(question)
        now = datetime.now()

        best_score = -1.0
        best_entry = None

        for entry in self._entries:
            # Skip expired entries
            if now - entry["timestamp"] > self._ttl:
                continue

            score = float(np.dot(query_vec, entry["embedding"]))
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_score >= threshold and best_entry is not None:
            return {
                "answer": best_entry["answer"],
                "sql": best_entry.get("sql"),
                "results": best_entry.get("results"),
                "tables_used": best_entry.get("tables_used", []),
                "follow_ups": best_entry.get("follow_ups", []),
                "chart": best_entry.get("chart"),
                "route": best_entry.get("route"),
                "response_time_ms": best_entry.get("response_time_ms", 0),
            }

        return None

    def store(self, question: str, result: dict) -> None:
        """
        Store a question→result pair in the cache.

        Args:
            question: The original question
            result: The full response dict from the pipeline
        """
        embedding = self._embed(question)

        entry = {
            "question": question,
            "embedding": embedding,
            "sql": result.get("sql"),
            "results": result.get("results"),
            "answer": result.get("answer", ""),
            "tables_used": result.get("tables_used", []),
            "follow_ups": result.get("follow_ups", []),
            "chart": result.get("chart"),
            "route": result.get("route"),
            "response_time_ms": result.get("time_ms", 0),
            "timestamp": datetime.now(),
        }

        self._entries.append(entry)

    def clear(self) -> None:
        """Clear all cache entries."""
        self._entries.clear()

    @property
    def size(self) -> int:
        """Number of entries in the cache."""
        return len(self._entries)

    def cleanup_expired(self) -> int:
        """Remove expired entries and return count of removed items."""
        now = datetime.now()
        before = len(self._entries)
        self._entries = [
            e for e in self._entries
            if now - e["timestamp"] <= self._ttl
        ]
        return before - len(self._entries)
