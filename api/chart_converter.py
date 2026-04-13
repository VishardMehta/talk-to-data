"""Convert SQL results to recharts-compatible format for the React frontend."""
from __future__ import annotations
import re


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

    # Classify columns
    numeric_cols = [c for c in columns if all(isinstance(r.get(c), (int, float)) for r in data)]
    text_cols = [c for c in columns if c not in numeric_cols]
    date_cols = [c for c in text_cols if _is_date_col(c, [r.get(c) for r in data])]
    cat_cols = [c for c in text_cols if c not in date_cols]
    y_metric = _pick_metric_col(numeric_cols, question)

    # Bug 5 fix: Single-row result → stat card (not a chart)
    if len(results) == 1 and numeric_cols:
        return {"chart_type": "stat_card", "data": data, "columns": columns, "rows": rows_as_lists}

    # Bug 5 fix: Lookup question with ≤3 rows → stat card or table (not a chart)
    if _is_lookup_question(question) and len(results) <= 3:
        if len(results) == 1:
            return {"chart_type": "stat_card", "data": data, "columns": columns, "rows": rows_as_lists}
        return {"chart_type": "table", "data": data, "columns": columns, "rows": rows_as_lists}

    # Bug 5 fix: Need at least 3 rows before showing a bar/pie chart
    if len(results) < 3:
        if numeric_cols and len(results) == 1:
            return {"chart_type": "stat_card", "data": data, "columns": columns, "rows": rows_as_lists}
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
