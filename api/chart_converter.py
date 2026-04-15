"""Convert SQL results to recharts-compatible format for the React frontend."""
from __future__ import annotations
import os
import re

from app.agents.chart_agent import suggest_chart


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


LLM_CHART_AGENT_ENABLED = _env_bool("LLM_CHART_AGENT_ENABLED", True)


def _is_date_col(col: str, values: list) -> bool:
    date_pat = re.compile(r"^\d{4}-\d{2}")
    return any(isinstance(v, str) and date_pat.match(v) for v in values[:5])


def _is_lookup_question(question: str) -> bool:
    """Return True if the question is a simple lookup/ranking query (single answer expected)."""
    q = question.lower().strip()
    lookup_patterns = [
        "who ", "who's ", "which ", "what is the name", "what was the name",
        "top 1 ", "first place", "show me the best", "give me the best",
    ]
    lookup_keywords = [
        "best", "worst", "highest", "lowest", "most", "least", "winner",
        "champion", "maximum", "minimum", "largest", "smallest",
    ]
    if any(q.startswith(p) for p in lookup_patterns):
        return True
    # "who had", "which player", "what player" etc. starting with who/which/what
    if q.startswith(("who ", "which ", "what ")) and len(q.split()) <= 10:
        return True
    if any(kw in q for kw in lookup_keywords) and ("?" in q or len(q.split()) <= 8):
        return True
    return False


def _is_ranking_question(question: str) -> bool:
    q = (question or "").lower()
    ranking_terms = (
        "best", "worst", "highest", "lowest", "most", "least",
        "top", "bottom", "winner", "champion", "maximum", "minimum",
    )
    return any(term in q for term in ranking_terms)


def _is_numeric_col(col: str, data: list) -> bool:
    """Return True if column contains numeric (int/float) values, ignoring nulls.
    Returns False if any non-null, non-numeric value is found, or if all values are None/bool."""
    has_value = False
    for r in data:
        v = r.get(col)
        if v is None:
            continue
        if isinstance(v, bool):
            return False
        if isinstance(v, (int, float)):
            has_value = True
        else:
            return False
    return has_value


def _metric_score(col: str, question: str) -> int:
    """Higher score means better candidate for y-axis metric."""
    c = col.lower()
    q = (question or "").lower()
    score = 0

    # Prefer business/analysis metrics
    if any(k in c for k in ("win", "wins", "count", "total", "sum", "avg", "mean", "score", "rate", "ratio", "pct", "percent", "value", "amount", "revenue")):
        score += 40

    # Prefer columns explicitly mentioned in question
    if any(tok in q for tok in c.replace("_", " ").split()):
        score += 20

    # Strongly de-prioritize identifiers and keys
    if c == "id" or c.endswith("_id") or c.startswith("id_"):
        score -= 100
    if any(k in c for k in ("key", "uuid", "guid")):
        score -= 60

    # Mildly de-prioritize helper numeric fields
    if any(k in c for k in ("rank", "index", "year", "month", "day")):
        score -= 20

    return score


def _pick_metric_col(numeric_cols: list[str], question: str) -> str:
    if not numeric_cols:
        return ""
    return sorted(numeric_cols, key=lambda c: _metric_score(c, question), reverse=True)[0]


def to_chart_payload(
    results: list[tuple],
    columns: list[str],
    pattern: str = "GENERAL",
    question: str = "",
) -> dict:
    """
    Returns a dict with:
      chart_type, data, x_key, y_key, name_key, value_key, columns, rows
    """
    if not results or not columns:
        return {"chart_type": "table", "columns": columns, "rows": [], "data": []}

    rows_as_lists = [list(r) for r in results]

    # Convert to list-of-dicts for recharts
    data = [dict(zip(columns, row)) for row in rows_as_lists]

    # Classify columns — use null-safe numeric check so columns with some NULLs still qualify
    numeric_cols = [c for c in columns if _is_numeric_col(c, data)]
    text_cols = [c for c in columns if c not in numeric_cols]
    date_cols = [c for c in text_cols if _is_date_col(c, [r.get(c) for r in data])]
    cat_cols = [c for c in text_cols if c not in date_cols]
    y_metric = _pick_metric_col(numeric_cols, question)

    # Optional LLM chart selection with validation + deterministic fallback.
    if LLM_CHART_AGENT_ENABLED:
        try:
            llm_choice = suggest_chart(
                question=question,
                pattern=pattern,
                columns=columns,
                rows_preview=rows_as_lists,
            )

            chart_type = llm_choice.get("chart_type", "table")
            if chart_type in ("stat_card", "table"):
                return {
                    "chart_type": chart_type,
                    "data": data,
                    "columns": columns,
                    "rows": rows_as_lists,
                }

            if chart_type == "line":
                x_key = llm_choice.get("x_key") or (date_cols[0] if date_cols else "")
                y_key = llm_choice.get("y_key") or y_metric
                if x_key in columns and y_key in columns:
                    return {
                        "chart_type": "line",
                        "data": data,
                        "x_key": x_key,
                        "y_key": y_key,
                        "columns": columns,
                        "rows": rows_as_lists,
                    }

            if chart_type == "bar":
                x_key = llm_choice.get("x_key") or (cat_cols[0] if cat_cols else "")
                y_key = llm_choice.get("y_key") or y_metric
                if x_key in columns and y_key in columns:
                    return {
                        "chart_type": "bar",
                        "data": data,
                        "x_key": x_key,
                        "y_key": y_key,
                        "columns": columns,
                        "rows": rows_as_lists,
                    }

            if chart_type == "pie":
                name_key = llm_choice.get("name_key") or (cat_cols[0] if cat_cols else "")
                value_key = llm_choice.get("value_key") or y_metric
                if name_key in columns and value_key in columns:
                    return {
                        "chart_type": "pie",
                        "data": data,
                        "name_key": name_key,
                        "value_key": value_key,
                        "columns": columns,
                        "rows": rows_as_lists,
                    }
        except Exception:
            # Safety fallback to deterministic rules below.
            pass

    # Single-row result → stat card (nothing to compare)
    if len(results) == 1:
        if numeric_cols:
            return {"chart_type": "stat_card", "data": data, "columns": columns, "rows": rows_as_lists}
        return {"chart_type": "table", "data": data, "columns": columns, "rows": rows_as_lists}

    # Ranking questions with multiple rows → always bar chart for comparison
    # (takes priority over the lookup heuristic — "best player" should show all players)
    if _is_ranking_question(question) and len(results) >= 2 and cat_cols and y_metric:
        return {
            "chart_type": "bar",
            "data": data,
            "x_key": cat_cols[0],
            "y_key": y_metric,
            "columns": columns,
            "rows": rows_as_lists,
        }

    # Two-row result with no ranking context → table (not enough for a meaningful chart)
    if len(results) == 2:
        return {"chart_type": "table", "data": data, "columns": columns, "rows": rows_as_lists}

    # Time series → line
    if date_cols and y_metric:
        return {
            "chart_type": "line",
            "data": data,
            "x_key": date_cols[0],
            "y_key": y_metric,
            "columns": columns,
            "rows": rows_as_lists,
        }

    # Breakdown with ≤6 categories → pie
    if pattern == "BREAKDOWN" and cat_cols and y_metric and len(results) <= 6:
        return {
            "chart_type": "pie",
            "data": data,
            "name_key": cat_cols[0],
            "value_key": y_metric,
            "columns": columns,
            "rows": rows_as_lists,
        }

    # Categorical + numeric → bar
    if cat_cols and y_metric:
        return {
            "chart_type": "bar",
            "data": data,
            "x_key": cat_cols[0],
            "y_key": y_metric,
            "columns": columns,
            "rows": rows_as_lists,
        }

    # Fallback → table
    return {"chart_type": "table", "data": data, "columns": columns, "rows": rows_as_lists}
