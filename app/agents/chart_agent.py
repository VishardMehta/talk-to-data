"""
Agent 5 — Chart Selector.

What this agent does:
  After the SQL results are ready, this agent decides the best visualization
  for the frontend.  It receives the question, the analytical pattern, and
  a preview of the result rows, then returns a chart spec.

Chart types supported:
  stat_card  — single KPI (1 row, 1-2 numeric columns)
  line       — time-series trend (date x-axis + numeric y-axis)
  bar        — category comparison (categorical x + numeric y)
  pie        — composition breakdown (≤6 categories)
  table      — fallback for complex or ambiguous result shapes

The frontend (ChartRenderer.tsx) reads the returned x_key / y_key /
name_key / value_key to map result columns onto chart axes.
"""
from __future__ import annotations

from app.core.llm_client import call_llm


_SYSTEM = """You are a chart selection expert for data analytics.

Choose a visualization for the given question and SQL result preview.

Allowed chart_type values:
- stat_card  (single KPI)
- line       (time trends)
- bar        (category comparison)
- pie        (small composition breakdown)
- table      (fallback)

Rules:
1. If only 1 row and at least one numeric column -> stat_card.
2. If question asks trend/time and data has date-like x axis -> line.
3. If comparing categories with numeric metric -> bar.
4. Use pie only when <= 6 categories and explicit composition/breakdown intent.
5. For very sparse/ambiguous data, prefer table.
6. Return keys that exist in provided columns.

Return ONLY valid JSON:
{
  "chart_type": "stat_card|line|bar|pie|table",
  "x_key": "<column or empty>",
  "y_key": "<column or empty>",
  "name_key": "<column or empty>",
  "value_key": "<column or empty>",
  "reasoning": "one sentence"
}
"""


def suggest_chart(
    question: str,
    pattern: str,
    columns: list[str],
    rows_preview: list[list],
) -> dict:
    """
    Choose the best chart type for a given question and SQL result shape.

    Parameters:
      question      — original user question (used to detect "trend", "compare", etc.)
      pattern       — analytical pattern from the Router (BREAKDOWN, CHANGE_ANALYSIS, etc.)
      columns       — list of column names in the result set
      rows_preview  — up to 40 rows of result data for the model to inspect

    Returns a chart spec dict:
      {
        "chart_type": "bar",
        "x_key":      "category",
        "y_key":      "total_revenue",
        "name_key":   "",
        "value_key":  "",
        "reasoning":  "comparing revenue across categories → bar chart"
      }

    Falls back to {"chart_type": "table"} if the LLM fails or returns
    an invalid response — a plain table is always safe to render.
    """
    payload = {
        "question":     question,
        "pattern":      pattern,
        "columns":      columns,
        "rows_preview": rows_preview[:40],  # keep token count reasonable
    }

    try:
        result = call_llm(
            model_key="chart_agent",
            system_prompt=_SYSTEM,
            user_message=str(payload),
            temperature=0.0,
            json_mode=True,
        )
    except Exception as e:
        print(f"[chart_agent] LLM call failed, defaulting to table: {e}")
        result = {}

    # Normalise response shape
    if isinstance(result, list):
        result = result[0] if result and isinstance(result[0], dict) else {}
    elif not isinstance(result, dict):
        result = {}

    # Fill in defaults so the frontend always gets a complete spec
    result.setdefault("chart_type", "table")
    result.setdefault("x_key",      "")
    result.setdefault("y_key",      "")
    result.setdefault("name_key",   "")
    result.setdefault("value_key",  "")
    result.setdefault("reasoning",  "")
    return result
