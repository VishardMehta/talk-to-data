import time
import numpy as np
from datetime import datetime, timedelta
from sentence_transformers import SentenceTransformer


class SemanticCache:
    TTL_SECONDS = 3600  # 1 hour

    def __init__(self, model: SentenceTransformer = None):
        self._model = model  # injected or lazy-loaded
        self._entries: list[dict] = []

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
        return self._model

    def _embed(self, text: str) -> np.ndarray:
        vec = self._get_model().encode([text], normalize_embeddings=True)[0]
        return vec.astype(np.float32)

    def _cosine(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))  # already normalized

    def _prune_expired(self):
        cutoff = datetime.now() - timedelta(seconds=self.TTL_SECONDS)
        self._entries = [e for e in self._entries if e["timestamp"] >= cutoff]

    def find_similar(self, question: str, threshold: float = 0.90) -> dict | None:
        self._prune_expired()
        if not self._entries:
            return None
        q_vec = self._embed(question)
        best_score = -1.0
        best_entry = None
        for entry in self._entries:
            score = self._cosine(q_vec, entry["embedding"])
            if score > best_score:
                best_score = score
                best_entry = entry
        if best_score >= threshold and best_entry:
            return best_entry
        return None

    def store(self, question: str, result: dict):
        self._prune_expired()
        vec = self._embed(question)
        entry = {
            "question": question,
            "embedding": vec,
            "sql": result.get("sql"),
            "results": result.get("results"),
            "answer": result.get("answer"),
            "tables_used": result.get("tables_used", []),
            "timestamp": datetime.now(),
            "response_time_ms": int(result.get("time_ms", 0)),
        }
        self._entries.append(entry)

    def clear(self):
        self._entries = []

    def size(self) -> int:
        self._prune_expired()
        return len(self._entries)
