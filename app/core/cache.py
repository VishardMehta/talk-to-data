from __future__ import annotations
"""
Semantic Cache — redesigned to fix the "same answer for all queries" bug.

Root causes fixed:
  1. Threshold was 0.90 → way too permissive for analytics queries.
     "count of regions" and "revenue breakdown by region" both score >0.90
     on all-MiniLM-L6-v2 because they share region/orders vocabulary.
     Fixed: default threshold raised to 0.97, with per-type overrides.

  2. Cache stored only 8 fields (missing route, pattern, follow_ups,
     confidence, chart, rag_docs).  When a cache hit occurred, the returned
     dict was incomplete and render_response() fell back to empty defaults.
     Fixed: store the COMPLETE response dict.

  3. No query-type gate.  A COUNT query could hit a COMPARISON cache entry
     (same topic, different analytical intent) and return the wrong answer.
     Fixed: entries are tagged with query_type; find_similar only matches
     entries of the same type.
"""
import numpy as np
from datetime import datetime, timedelta
from sentence_transformers import SentenceTransformer


class SemanticCache:
    TTL_SECONDS = 3600  # 1 hour

    def __init__(self, model: SentenceTransformer = None):
        self._model = model
        self._entries: list[dict] = []
        self._enabled = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            try:
                print("[cache] Loading sentence transformer model…")
                self._model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception as e:
                # Fail open: app keeps running without semantic cache.
                self._enabled = False
                print(f"[cache] Disabled semantic cache: failed to load embedding model ({e})")
                return None
        return self._model

    def _embed(self, text: str) -> np.ndarray:
        model = self._get_model()
        if (not self._enabled) or model is None:
            return None
        vec = model.encode([text], normalize_embeddings=True)[0]
        return vec.astype(np.float32)

    def _cosine(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))  # normalized vectors → dot == cosine

    def _prune_expired(self):
        cutoff = datetime.now() - timedelta(seconds=self.TTL_SECONDS)
        self._entries = [e for e in self._entries if e["timestamp"] >= cutoff]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_similar(
        self,
        question: str,
        threshold: float = 0.97,
        query_type: str = "INSIGHT",
    ) -> dict | None:
        """
        Return a cached response if a sufficiently similar question of the
        SAME query type was asked before.

        Args:
          threshold:   minimum cosine similarity (default 0.97, raised from
                       the broken 0.90 that caused same-answer-for-all).
          query_type:  only matches cache entries of the same analytical type.
                       Prevents "count of regions" hitting a "revenue
                       comparison" cache entry.
        """
        self._prune_expired()
        if not self._enabled:
            return None
        if not self._entries:
            return None

        q_vec = self._embed(question)
        if q_vec is None:
            return None
        best_score = -1.0
        best_entry = None

        for entry in self._entries:
            # Type gate: different analytical intent → never share cache
            entry_type = entry.get("query_type", "INSIGHT")
            if entry_type != query_type:
                continue

            score = self._cosine(q_vec, entry["embedding"])
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_score >= threshold and best_entry is not None:
            return best_entry
        return None

    def store(
        self,
        question: str,
        result: dict,
        query_type: str = "INSIGHT",
    ):
        """
        Store the COMPLETE response dict in the cache.

        Fix: previously only 8 fields were stored (sql, results, answer,
        tables_used, …), causing cache hits to return incomplete dicts
        missing route, pattern, follow_ups, confidence, and chart.
        Now the entire pipeline response is preserved.
        """
        self._prune_expired()
        if not self._enabled:
            return
        vec = self._embed(question)
        if vec is None:
            return

        entry = {
            **result,                       # everything the pipeline produced
            "question": question,
            "embedding": vec,
            "query_type": query_type,       # for type-gated retrieval
            "timestamp": datetime.now(),
        }
        self._entries.append(entry)

    def clear(self):
        self._entries = []

    def size(self) -> int:
        self._prune_expired()
        return len(self._entries)
