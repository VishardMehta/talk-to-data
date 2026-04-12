from __future__ import annotations
import json
import numpy as np
import faiss
from pathlib import Path
from sentence_transformers import SentenceTransformer
import yaml


class VectorStore:
    def __init__(self, model: SentenceTransformer = None):
        self._model = model or SentenceTransformer("all-MiniLM-L6-v2")
        self._dim = 384  # all-MiniLM-L6-v2 output dim

        # Document index (RAG)
        self._doc_index: faiss.IndexFlatIP | None = None
        self._doc_metadata: list[dict] = []

        # Schema index (table selection)
        self._schema_index: faiss.IndexFlatIP | None = None
        self._schema_tables: list[str] = []

        # Verified query index (few-shot)
        self._query_index: faiss.IndexFlatIP | None = None
        self._query_entries: list[dict] = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return vecs.astype(np.float32)

    def _build_index(self, vecs: np.ndarray) -> faiss.IndexFlatIP:
        index = faiss.IndexFlatIP(self._dim)
        index.add(vecs)
        return index

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def init_document_index(self, docs_dir: str):
        """Load complaints.json and feedback.json and build FAISS index."""
        docs_path = Path(docs_dir)
        documents = []

        for fname in ("complaints.json", "feedback.json"):
            fpath = docs_path / fname
            if fpath.exists():
                with open(fpath, "r", encoding="utf-8") as f:
                    entries = json.load(f)
                for entry in entries:
                    documents.append(entry)

        if not documents:
            return

        texts = [d.get("text", "") for d in documents]
        vecs = self._embed(texts)
        self._doc_index = self._build_index(vecs)
        self._doc_metadata = documents

    def init_schema_index(self, semantic_layer_path: str):
        """Embed table descriptions for schema/table selection."""
        with open(semantic_layer_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        models = cfg.get("models", {})
        texts = []
        tables = []
        for tname, model in models.items():
            desc = model.get("description", tname)
            col_descs = " ".join(
                f"{cname}: {cinfo.get('description', '')}"
                for cname, cinfo in model.get("columns", {}).items()
            )
            texts.append(f"{tname} — {desc}. Columns: {col_descs}")
            tables.append(tname)

        vecs = self._embed(texts)
        self._schema_index = self._build_index(vecs)
        self._schema_tables = tables

    def init_verified_query_index(self, verified_queries_path: str):
        """Embed verified questions for few-shot retrieval."""
        with open(verified_queries_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        entries = cfg.get("verified_queries", [])
        if not entries:
            return

        texts = [e["question"] for e in entries]
        vecs = self._embed(texts)
        self._query_index = self._build_index(vecs)
        self._query_entries = entries

    # ------------------------------------------------------------------
    # Search methods
    # ------------------------------------------------------------------

    def search_documents(self, query: str, top_k: int = 5) -> list[dict]:
        if self._doc_index is None or self._doc_index.ntotal == 0:
            return []
        vec = self._embed([query])
        scores, indices = self._doc_index.search(vec, min(top_k, self._doc_index.ntotal))
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            entry = dict(self._doc_metadata[idx])
            entry["score"] = float(score)
            results.append(entry)
        return results

    def search_tables(self, query: str, top_k: int = 5) -> list[str]:
        if self._schema_index is None or self._schema_index.ntotal == 0:
            return []
        vec = self._embed([query])
        scores, indices = self._schema_index.search(vec, min(top_k, self._schema_index.ntotal))
        tables = []
        for idx in indices[0]:
            if idx >= 0:
                tables.append(self._schema_tables[idx])
        return tables

    def find_similar_query(self, question: str, pattern: str = None) -> dict | None:
        """
        Find the best verified query example for few-shot SQL generation.

        Bugs fixed:
          1. Minimum score threshold added (0.75) — previously any result was
             returned even with near-zero similarity, giving the SQL generator
             a misleading example.
          2. Fallback to wrong pattern removed — previously, when no entry
             matched the requested pattern in the top-10, the method returned
             the highest-scoring entry regardless of pattern.  This caused a
             COUNT query (GENERAL pattern) to receive a CHANGE_ANALYSIS
             example and produce time-series SQL instead of COUNT SQL.
             Fix: return None when no pattern match found above threshold.
             The SQL generator has a safe default and handles None correctly.
        """
        if self._query_index is None or self._query_index.ntotal == 0:
            return None

        vec = self._embed([question])
        k = min(10, self._query_index.ntotal)
        scores, indices = self._query_index.search(vec, k)

        # Minimum similarity — don't use a dissimilar example as few-shot
        MIN_SCORE = 0.75

        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            if score < MIN_SCORE:
                # FAISS returns results in descending score order; once we
                # drop below the threshold we can stop scanning.
                break
            entry = self._query_entries[idx]
            if pattern is None or entry.get("pattern") == pattern:
                return entry

        # No match above threshold for the requested pattern.
        # Return None rather than a wrong-pattern example that would mislead
        # the SQL generator into producing the wrong query structure.
        return None
