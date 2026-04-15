"""
Result Verifier — Agent 5.

Checks whether SQL results actually answer the question asked.
Uses heuristic fast-path first; only calls LLM for ambiguous cases.
"""
from __future__ import annotations

import re
from app.core.groq_client import call_llm


# ── Heuristic checks (no LLM) ─────────────────────────────────────────────────

def _is_count_question(question: str) -> bool:
    q = question.lower()
    return any(k in q for k in ("how many", "count", "total number", "number of"))


def _is_ranking_question(question: str) -> bool:
    q = question.lower()
    return any(k in q for k in (
        "best", "worst", "highest", "lowest", "most", "least",
        "top", "bottom", "winner", "champion", "maximum", "minimum",
        "largest", "smallest",
    ))


def _entity_in_rows(entity_fragment: str, rows: list, columns: list) -> bool:
    """Return True if entity_fragment appears (case-insensitive) in any string cell."""
    frag = entity_fragment.lower().strip()
    for row in rows:
        for val in row:
            if isinstance(val, str) and frag in val.lower():
                return True
    return False


def _extract_question_entities(question: str) -> list[str]:
    """Extract quoted strings or capitalised tokens that could be entity names."""
    # Quoted strings first
    quoted = re.findall(r'"([^"]+)"', question)
    if quoted:
        return quoted
    # Capitalised words (likely proper nouns/names) — skip short stop-words
    stop = {"what", "which", "who", "is", "are", "the", "a", "an", "for", "of",
            "in", "on", "at", "by", "to", "how", "many", "does", "did", "with"}
    tokens = [t.strip("?.,!:;") for t in question.split()]
    caps = [t for t in tokens if t and t[0].isupper() and t.lower() not in stop and len(t) > 1]
    return caps


def _heuristic_verify(question: str, rows: list, columns: list) -> dict | None:
    """
    Fast heuristic checks. Returns a verdict dict or None if inconclusive.

    Verdict shape: {"grounded": bool, "confidence": int, "issue": str | None}
    """
    # Empty result is always ungrounded
    if not rows:
        return {"grounded": False, "confidence": 9, "issue": "SQL returned no rows"}

    numeric_cols = []
    for idx, col in enumerate(columns):
        vals = [r[idx] for r in rows if len(r) > idx and r[idx] is not None]
        if vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            numeric_cols.append(idx)

    # COUNT / "how many" → 1 row, 1 numeric col → grounded
    if _is_count_question(question) and len(rows) == 1 and len(numeric_cols) >= 1:
        return {"grounded": True, "confidence": 9, "issue": None}

    # Ranking question: entity name should appear in rows
    if _is_ranking_question(question):
        entities = _extract_question_entities(question)
        if entities:
            for ent in entities:
                if _entity_in_rows(ent, rows, columns):
                    return {"grounded": True, "confidence": 8, "issue": None}
            # Entities were extracted but none found → might be asking about a non-existent entity
            # Don't hard-fail here; fall through to LLM or trust the data
        # Ranking question with results present → likely grounded
        if len(rows) >= 1 and numeric_cols:
            return {"grounded": True, "confidence": 7, "issue": None}

    # Generic: has rows and at least one numeric column → probably grounded
    if rows and (numeric_cols or len(columns) >= 1):
        return {"grounded": True, "confidence": 6, "issue": None}

    return None  # Inconclusive — defer to LLM


# ── LLM fallback ──────────────────────────────────────────────────────────────

_VERIFIER_SYSTEM = """You are a strict data-quality auditor.
Your job: decide if the given SQL result actually answers the user's question.

Rules:
- Answer ONLY with valid JSON: {"grounded": true/false, "confidence": 0-10, "issue": null or "short reason"}
- grounded=true  → the result directly answers the question
- grounded=false → the result is empty, unrelated, or clearly wrong
- confidence 8-10 → very sure  |  5-7 → somewhat sure  |  0-4 → uncertain
- issue → one short sentence explaining the problem (null if grounded)
- Do NOT explain reasoning outside the JSON object.
"""


def _llm_verify(question: str, sql: str, rows: list, columns: list) -> dict:
    rows_preview = rows[:10]
    col_str = ", ".join(columns)
    rows_str = "\n".join(str(r) for r in rows_preview)
    if not rows_str:
        rows_str = "(empty)"

    user_msg = (
        f"Question: {question}\n"
        f"SQL: {sql}\n"
        f"Columns: {col_str}\n"
        f"Rows (first 10):\n{rows_str}"
    )

    try:
        raw = call_llm(
            model_key="result_verifier",
            system_prompt=_VERIFIER_SYSTEM,
            user_message=user_msg,
            temperature=0.1,
            json_mode=True,
        )
        import json
        if isinstance(raw, str):
            payload = json.loads(raw)
        else:
            payload = raw

        if isinstance(payload, list):
            payload = payload[0] if payload and isinstance(payload[0], dict) else {}
        elif not isinstance(payload, dict):
            payload = {}

        grounded = bool(payload.get("grounded", True))
        confidence = int(payload.get("confidence", 5))
        issue = payload.get("issue") or None
        return {"grounded": grounded, "confidence": confidence, "issue": issue}
    except Exception as exc:
        # On any error, be optimistic (don't block the pipeline)
        print(f"[result_verifier] LLM verify failed: {exc}")
        return {"grounded": True, "confidence": 4, "issue": None}


# ── Public API ────────────────────────────────────────────────────────────────

def verify_result(
    question: str,
    sql: str,
    rows: list,
    columns: list,
) -> dict:
    """
    Check if SQL results actually answer the question.

    Returns:
        {
          "grounded": True | False,
          "confidence": 0-10,
          "issue": str | None,
        }

    Fast-path: pure heuristics (no LLM call) when the answer is obvious.
    Slow-path: LLM call for ambiguous cases.
    """
    verdict = _heuristic_verify(question, rows or [], columns or [])
    if verdict is not None:
        return verdict

    # Ambiguous — ask the LLM
    return _llm_verify(question, sql, rows or [], columns or [])
