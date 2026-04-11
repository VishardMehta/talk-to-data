"""
SQL Generator Agent — Agent 2.

Key bug fixes baked into this module:
  Error 1: Multiple statements  → explicit rule + post-processing via clean_sql
  Error 2: Syntax error (SELECT)→ _strip_second_top_level_select in sql_parser
  Error 3: Missing commas       → explicit rule in prompt + example format
  Error 4: Mixing levels        → pattern-specific instructions enforce one purpose per query
  Error 5: Weak query planning  → structured system prompt with clear decomposition rules
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

## OUTPUT FORMAT (JSON):
{{
  "sql": "<single SELECT statement here>",
  "confidence": <integer 1-10>,
  "tables_used": ["table1", "table2"],
  "reasoning": "brief explanation of approach"
}}
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
) -> dict:
    templates = _get_templates()
    pattern_cfg = templates.get(pattern, templates.get("GENERAL", {}))
    pattern_instructions = pattern_cfg.get("system_prompt", "Generate accurate SQL.")

    # Few-shot example
    if verified_query:
        example_question = verified_query.get("question", "")
        example_sql = verified_query.get("sql", "").strip()
    else:
        example_question = "Show total revenue by region"
        example_sql = (
            "SELECT region, SUM(amount) AS revenue\n"
            "FROM orders\n"
            "WHERE status = 'completed'\n"
            "GROUP BY region\n"
            "ORDER BY revenue DESC"
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
        error_section=error_section,
        state_section=state_section,
        base_rules=_BASE_RULES,
    )

    raw = call_llm(
        model_key="smart",
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
