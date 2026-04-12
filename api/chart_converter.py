"""Convert SQL results to recharts-compatible format for the React frontend."""
from __future__ import annotations
import re


def _is_date_col(col: str, values: list) -> bool:
    date_pat = re.compile(r"^\d{4}-\d{2}")
    return any(isinstance(v, str) and date_pat.match(v) for v in values[:5])


def to_chart_payload(
    results: list[tuple],
    columns: list[str],
    pattern: str = "GENERAL",
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

    # Single stat card
    if len(results) == 1 and len(columns) <= 3 and numeric_cols:
        return {"chart_type": "stat_card", "data": data, "columns": columns, "rows": rows_as_lists}

    # Time series → line
    if date_cols and numeric_cols:
        return {
            "chart_type": "line",
            "data": data,
            "x_key": date_cols[0],
            "y_key": numeric_cols[0],
            "columns": columns,
            "rows": rows_as_lists,
        }

    # Breakdown with ≤6 categories → pie
    if pattern == "BREAKDOWN" and cat_cols and numeric_cols and len(results) <= 6:
        return {
            "chart_type": "pie",
            "data": data,
            "name_key": cat_cols[0],
            "value_key": numeric_cols[0],
            "columns": columns,
            "rows": rows_as_lists,
        }

    # Categorical + numeric → bar
    if cat_cols and numeric_cols:
        return {
            "chart_type": "bar",
            "data": data,
            "x_key": cat_cols[0],
            "y_key": numeric_cols[0],
            "columns": columns,
            "rows": rows_as_lists,
        }

    # Fallback → table
    return {"chart_type": "table", "data": data, "columns": columns, "rows": rows_as_lists}
