from __future__ import annotations
"""
SQL Generator Agent — Agent 2.
Uses Qwen3-32B for 95%+ SQL accuracy.

Improvements over v1:
  - Chain-of-thought step forces structured reasoning before SQL
  - Value-aware prompting includes sample values with case warnings
  - Pattern-specific metric definitions prevent wrong aggregations
  - Explicit filter extraction catches mentioned dimensions
"""

import yaml
from pathlib import Path
from app.core.groq_client import call_llm
from app.utils.sql_parser import clean_sql


def _load_pattern_templates() -> dict:
    base = Path(__file__).resolve().parent.parent.parent
    path = base / "config" / "pattern_templates.yaml"
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("patterns", {})


_PATTERN_TEMPLATES = None


def _get_templates() -> dict:
    global _PATTERN_TEMPLATES
    if _PATTERN_TEMPLATES is None:
        _PATTERN_TEMPLATES = _load_pattern_templates()
    return _PATTERN_TEMPLATES


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

_BASE_RULES = """
## ABSOLUTE SQL RULES — any violation causes a runtime crash:
1. Output EXACTLY ONE SELECT statement. Period.
2. NEVER output multiple queries. NEVER use semicolons (;) to separate statements.
3. NEVER use --- as a query delimiter.
4. Every item in the SELECT list MUST be separated by a comma.
5. Subqueries inside parentheses are allowed — but the outer query must be a single SELECT.
6. Use SQLite syntax only:
   - Date functions: date(), strftime(), 'start of month', 'start of year', etc.
   - No ILIKE — use LOWER(col) LIKE '%term%' instead.
7. Always alias tables in JOINs (e.g. JOIN products p ON ...).
8. Never invent columns or tables not listed in the schema.
9. Return ONLY the raw SQL — no markdown fences, no ```sql, no explanation text.
10. Do NOT include a trailing semicolon.

## METRIC DEFINITIONS — use these EXACT formulas:
- "total revenue" or "sales" = SUM(amount)
- "number of orders" or "how many orders" = COUNT(order_id)
- "average order value" or "AOV" = AVG(amount)
- "unique customers" = COUNT(DISTINCT customer_id)
- "complaint rate" = CAST(COUNT(DISTINCT complaint_id) AS REAL) / COUNT(DISTINCT order_id) * 100
- "return rate" = COUNT(CASE WHEN status='returned' THEN 1 END) * 100.0 / COUNT(*)
NEVER guess an aggregation. If unsure, use COUNT(*).

## CASE-SENSITIVE VALUES — use EXACT values as shown in schema:
- status values: 'completed', 'pending', 'cancelled', 'returned'
- region values: 'North', 'South', 'East', 'West'
- channel values: 'online', 'retail', 'wholesale'
- segment values: 'regular', 'premium', 'enterprise'
- category values: 'Electronics', 'Clothing', 'Home', 'Food', 'Beauty'
WARNING: SQLite string comparison is case-sensitive. Use exact casing above.

## CHAIN OF THOUGHT — before writing SQL, think:
1. What metric is being asked? (identify the aggregation)
2. What filters are mentioned? (region, time period, status, category)
3. What grouping is needed? (GROUP BY what?)
4. What ordering is needed? (TOP N = ORDER BY + LIMIT)
5. What tables need to be joined?
Include this reasoning in the "reasoning" field of your JSON response.

## OUTPUT FORMAT (JSON):
{{
  "sql": "<single SELECT statement here>",
  "confidence": <integer 1-10>,
  "tables_used": ["table1", "table2"],
  "reasoning": "Step-by-step: 1) metric=SUM(amount), 2) filter=region='South', 3) group=month, 4) order=month ASC"
}}

Return ONLY the JSON object. Do not include any thinking or reasoning process outside the JSON.
"""

_SYSTEM_TEMPLATE = """{pattern_instructions}

## DATABASE SCHEMA
{semantic_context}

## BEST MATCHING EXAMPLE
Question: {example_question}
SQL:
{example_sql}

{error_section}{state_section}{base_rules}
"""


def generate_sql(
    question: str,
    pattern: str,
    semantic_context: str,
    verified_query: dict | None,
    conversation_state: str,
    error_feedback: str = None,
    query_hints: list[str] = None,
) -> dict:
    templates = _get_templates()
    pattern_cfg = templates.get(pattern, templates.get("GENERAL", {}))
    pattern_instructions = pattern_cfg.get("system_prompt", "Generate accurate SQL.")

    # Few-shot example
    # Bug fix: the old default was always "Show total revenue by region" which
    # biased the SQL generator toward GROUP BY region revenue queries even for
    # unrelated questions (e.g. "count of regions", "list customers").
    # Now: pick a default that matches the pattern, not one generic example.
    _PATTERN_DEFAULTS = {
        "GENERAL": (
            "How many distinct regions are there?",
            "SELECT COUNT(DISTINCT region) AS region_count\nFROM orders",
        ),
        "BREAKDOWN": (
            "Show revenue breakdown by region",
            "SELECT region, SUM(amount) AS revenue,\n"
            "       ROUND(SUM(amount) * 100.0 / (SELECT SUM(amount) FROM orders WHERE status='completed'), 1) AS pct\n"
            "FROM orders\nWHERE status = 'completed'\nGROUP BY region\nORDER BY revenue DESC",
        ),
        "COMPARISON": (
            "Compare North vs South revenue",
            "SELECT region, SUM(amount) AS total_revenue, COUNT(*) AS total_orders\n"
            "FROM orders\nWHERE region IN ('North','South') AND status='completed'\nGROUP BY region",
        ),
        "CHANGE_ANALYSIS": (
            "Why did revenue drop last month?",
            "SELECT strftime('%Y-%m', order_date) AS month, SUM(amount) AS revenue, COUNT(*) AS order_count\n"
            "FROM orders\nWHERE order_date >= date('now','-2 months') AND status='completed'\n"
            "GROUP BY month\nORDER BY month",
        ),
        "SUMMARY": (
            "Give me a summary of key metrics",
            "SELECT SUM(amount) AS total_revenue, COUNT(*) AS total_orders,\n"
            "       AVG(amount) AS avg_order_value, COUNT(DISTINCT customer_id) AS unique_customers\n"
            "FROM orders\nWHERE order_date >= date('now','start of month')",
        ),
    }

    if verified_query:
        example_question = verified_query.get("question", "")
        example_sql = verified_query.get("sql", "").strip()
    else:
        default_q, default_sql = _PATTERN_DEFAULTS.get(
            pattern, _PATTERN_DEFAULTS["GENERAL"]
        )
        example_question = default_q
        example_sql = default_sql

    # Query classifier hints section
    hints_section = ""
    if query_hints:
        hints_section = (
            "## QUERY CLASSIFICATION HINTS (read carefully before writing SQL)\n"
            + "\n".join(f"- {h}" for h in query_hints)
            + "\n\n"
        )

    # Error feedback section (retry path)
    error_section = ""
    if error_feedback:
        error_section = (
            f"## PREVIOUS ATTEMPT FAILED\n"
            f"Error: {error_feedback}\n"
            f"Fix the SQL to resolve this error before responding.\n\n"
        )

    # Conversation state section
    state_section = ""
    if conversation_state:
        state_section = f"## CONVERSATION CONTEXT (for follow-up questions)\n{conversation_state}\n\n"

    system_prompt = _SYSTEM_TEMPLATE.format(
        pattern_instructions=pattern_instructions,
        semantic_context=semantic_context,
        example_question=example_question,
        example_sql=example_sql,
        error_section=hints_section + error_section,
        state_section=state_section,
        base_rules=_BASE_RULES,
    )

    raw = call_llm(
        model_key="smart_sql",  # Qwen3-32B for best SQL accuracy
        system_prompt=system_prompt,
        user_message=f'Generate SQL for: "{question}"',
        temperature=0.0,
        json_mode=True,
    )

    # Post-process: enforce single-statement, strip fences, etc.
    raw_sql = raw.get("sql", "")
    cleaned = clean_sql(raw_sql)
    raw["sql"] = cleaned

    # Ensure required keys
    raw.setdefault("confidence", 5)
    raw.setdefault("tables_used", [])
    raw.setdefault("reasoning", "")

    return raw
