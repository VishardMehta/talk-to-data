"""
Agent 5 — Chart Selector.

Chooses the best visualization payload for frontend rendering.
Falls back safely if model output is invalid.
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
    payload = {
        "question": question,
        "pattern": pattern,
        "columns": columns,
        "rows_preview": rows_preview[:40],
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
        print(f"[chart_agent] LLM JSON response failed, using table fallback: {e}")
        result = {}

    if isinstance(result, list):
        result = result[0] if result and isinstance(result[0], dict) else {}
    elif not isinstance(result, dict):
        result = {}

    result.setdefault("chart_type", "table")
    result.setdefault("x_key", "")
    result.setdefault("y_key", "")
    result.setdefault("name_key", "")
    result.setdefault("value_key", "")
    result.setdefault("reasoning", "")
    return result
