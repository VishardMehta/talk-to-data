"""
FAISS-based vector store for three purposes:
1. document_index — RAG over complaint/feedback documents
2. schema_index   — table selection for TAG (Table-Augmented Generation)
3. verified_query_index — few-shot retrieval from golden queries
"""
from __future__ import annotations

import os
import json
import numpy as np
import faiss
import yaml


_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class VectorStore:
    """Manages three FAISS indexes for document search, schema search, and query matching."""

    def __init__(self, embedding_model):
        """
        Args:
            embedding_model: SentenceTransformer model instance (shared with cache)
        """
        self._model = embedding_model
        
        # Document index (RAG)
        self._doc_index = None
        self._doc_metadata: list[dict] = []
        
        # Schema index (table selection)
        self._schema_index = None
        self._schema_metadata: list[dict] = []
        
        # Verified query index (few-shot)
        self._query_index = None
        self._query_metadata: list[dict] = []

    def _embed(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts and L2-normalize."""
        vecs = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        # Normalize for cosine similarity via inner product
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return (vecs / norms).astype("float32")

    # ── Initialization ───────────────────────────────────────────────────

    def initialize_document_index(self):
        """Load complaint and feedback documents into FAISS index."""
        docs_dir = os.path.join(_BASE_DIR, "data", "documents")
        all_docs = []
        
        # Load complaints
        complaints_path = os.path.join(docs_dir, "complaints.json")
        if os.path.exists(complaints_path):
            with open(complaints_path, "r") as f:
                complaints = json.load(f)
            for doc in complaints:
                all_docs.append({
                    "text": doc["text"],
                    "category": doc.get("category", ""),
                    "region": doc.get("region", ""),
                    "date": doc.get("date", ""),
                    "source": "complaints",
                })
        
        # Load feedback
        feedback_path = os.path.join(docs_dir, "feedback.json")
        if os.path.exists(feedback_path):
            with open(feedback_path, "r") as f:
                feedbacks = json.load(f)
            for doc in feedbacks:
                all_docs.append({
                    "text": doc["text"],
                    "sentiment": doc.get("sentiment", ""),
                    "region": doc.get("region", ""),
                    "date": doc.get("date", ""),
                    "source": "feedback",
                })
        
        if not all_docs:
            return
        
        texts = [d["text"] for d in all_docs]
        embeddings = self._embed(texts)
        
        dim = embeddings.shape[1]
        self._doc_index = faiss.IndexFlatIP(dim)
        self._doc_index.add(embeddings)
        self._doc_metadata = all_docs

    def initialize_schema_index(self):
        """Load table descriptions from semantic layer into FAISS index."""
        config_path = os.path.join(_BASE_DIR, "config", "semantic_layer.yaml")
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        models = config.get("models", {})
        texts = []
        metadata = []
        
        for table_name, model_info in models.items():
            # Concatenate table description + column descriptions
            desc = model_info.get("description", "")
            col_descs = []
            for col_name, col_info in model_info.get("columns", {}).items():
                col_desc = col_info.get("description", "")
                sample = col_info.get("sample_values", [])
                col_text = f"{col_name}: {col_desc}"
                if sample:
                    col_text += f" (values: {', '.join(str(v) for v in sample)})"
                col_descs.append(col_text)
            
            full_text = f"Table {table_name}: {desc}. Columns: {'; '.join(col_descs)}"
            texts.append(full_text)
            metadata.append({"table_name": table_name, "description": desc})
        
        if not texts:
            return
        
        embeddings = self._embed(texts)
        dim = embeddings.shape[1]
        self._schema_index = faiss.IndexFlatIP(dim)
        self._schema_index.add(embeddings)
        self._schema_metadata = metadata

    def initialize_verified_query_index(self):
        """Load verified queries from YAML into FAISS index for few-shot retrieval."""
        config_path = os.path.join(_BASE_DIR, "config", "verified_queries.yaml")
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        queries = config.get("verified_queries", [])
        if not queries:
            return
        
        texts = [q["question"] for q in queries]
        embeddings = self._embed(texts)
        
        dim = embeddings.shape[1]
        self._query_index = faiss.IndexFlatIP(dim)
        self._query_index.add(embeddings)
        self._query_metadata = queries

    def initialize_all(self):
        """Initialize all three indexes."""
        self.initialize_document_index()
        self.initialize_schema_index()
        self.initialize_verified_query_index()

    # ── Search methods ───────────────────────────────────────────────────

    def search_documents(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Search complaint/feedback documents via semantic similarity.

        Returns list of dicts with 'text', 'category', 'region', 'date', 'score'.
        """
        if self._doc_index is None or self._doc_index.ntotal == 0:
            return []
        
        query_vec = self._embed([query])
        scores, indices = self._doc_index.search(query_vec, min(top_k, self._doc_index.ntotal))
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            doc = self._doc_metadata[idx].copy()
            doc["score"] = float(score)
            results.append(doc)
        
        return results

    def search_tables(self, query: str, top_k: int = 5) -> list[str]:
        """
        Find most relevant tables for a query.

        Returns list of table names ordered by relevance.
        """
        if self._schema_index is None or self._schema_index.ntotal == 0:
            return []
        
        query_vec = self._embed([query])
        k = min(top_k, self._schema_index.ntotal)
        scores, indices = self._schema_index.search(query_vec, k)
        
        tables = []
        for idx in indices[0]:
            if idx < 0:
                continue
            tables.append(self._schema_metadata[idx]["table_name"])
        
        return tables

    def find_similar_query(self, question: str, pattern: str = None) -> dict | None:
        """
        Find the best matching verified query for few-shot prompting.

        Args:
            question: User's question
            pattern: Optional pattern filter (e.g., "CHANGE_ANALYSIS")

        Returns:
            Best matching verified query dict with 'question', 'sql', 'pattern', or None
        """
        if self._query_index is None or self._query_index.ntotal == 0:
            return None
        
        query_vec = self._embed([question])
        # Fetch more candidates than needed so we can filter by pattern
        k = min(10, self._query_index.ntotal)
        scores, indices = self._query_index.search(query_vec, k)
        
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            candidate = self._query_metadata[idx]
            
            # If pattern specified, prefer matching pattern
            if pattern and candidate.get("pattern") == pattern:
                return {
                    "question": candidate["question"],
                    "sql": candidate["sql"],
                    "pattern": candidate["pattern"],
                    "score": float(score),
                }
        
        # Fallback: return best match regardless of pattern
        if indices[0][0] >= 0:
            best = self._query_metadata[indices[0][0]]
            return {
                "question": best["question"],
                "sql": best["sql"],
                "pattern": best["pattern"],
                "score": float(scores[0][0]),
            }
        
        return None

    @property
    def document_count(self) -> int:
        """Number of documents in the document index."""
        return self._doc_index.ntotal if self._doc_index else 0

    @property
    def table_count(self) -> int:
        """Number of tables in the schema index."""
        return self._schema_index.ntotal if self._schema_index else 0

    @property
    def query_count(self) -> int:
        """Number of verified queries in the query index."""
        return self._query_index.ntotal if self._query_index else 0
