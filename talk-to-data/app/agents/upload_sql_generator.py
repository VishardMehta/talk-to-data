from __future__ import annotations
"""
SQL Generator for Upload Mode — DuckDB-specific.
Generates SQL for arbitrary uploaded CSV/Parquet files.
"""

from app.core.groq_client import call_llm
from app.utils.sql_parser import clean_sql


_DUCKDB_SYSTEM = """You are a SQL expert generating DuckDB SQL queries for data stored in CSV/Parquet files.

CRITICAL DuckDB RULES:
1. ALWAYS query using the exact read function shown in the schema (e.g. read_csv_auto('/path/file.csv'))
   NEVER use bare table names.
2. DuckDB supports ILIKE for case-insensitive string matching.
3. DuckDB date functions:
   - current_date (not CURDATE or NOW())
   - date_part('year', col), date_part('month', col)
   - date_trunc('month', col) for truncating
   - strftime(col, '%Y-%m') for formatting
   - col + INTERVAL '1 month'
4. Column names with spaces or special chars MUST be double-quoted: "Column Name"
5. DuckDB supports GROUP BY ALL, SELECT * EXCLUDE (col)
6. Aggregate functions: SUM, AVG, COUNT, MIN, MAX, MEDIAN, MODE
7. Window functions: ROW_NUMBER(), RANK(), LAG(), LEAD()
8. For % of total: SUM(col) * 100.0 / SUM(SUM(col)) OVER ()
9. NEVER use SQLite-specific syntax (date(), strftime with SQLite format, etc.)
10. Return EXACTLY ONE SELECT statement. No semicolons. No markdown.

{enriched_context}

{pattern_instructions}

{verified_section}

{error_section}

{state_section}

Return JSON:
{{"sql": "...", "confidence": 1-10, "tables_used": [...], "reasoning": "..."}}
"""


def generate_sql(
    question: str,
    pattern: str,
    enriched_context: str,
    verified_query: dict | None,
    filepath: str,
    conversation_state: str = "",
    error_feedback: str = None,
) -> dict:
    pattern_map = {
        "BREAKDOWN": "Break down the data by one or more dimension columns. Use GROUP BY.",
        "COMPARISON": "Compare values across categories or time periods side by side.",
        "CHANGE_ANALYSIS": "Analyze trends or changes over time. Use date columns for time series.",
        "SUMMARY": "Provide key summary statistics: totals, averages, counts.",
        "GENERAL": "Answer the specific question accurately using the available columns.",
    }
    pattern_instructions = pattern_map.get(pattern, pattern_map["GENERAL"])

    verified_section = ""
    if verified_query:
        verified_section = (
            "## VERIFIED EXAMPLE\n"
            f"Question: {verified_query.get('question', '')}\n"
            f"SQL: {verified_query.get('sql', '')}\n"
        )

    error_section = ""
    if error_feedback:
        error_section = (
            f"## PREVIOUS ATTEMPT FAILED\n"
            f"Error: {error_feedback}\n"
            f"Fix the SQL to resolve this error. DuckDB errors are precise — read them carefully.\n"
        )

    state_section = ""
    if conversation_state:
        state_section = f"## CONVERSATION CONTEXT\n{conversation_state}\n"

    system_prompt = _DUCKDB_SYSTEM.format(
        enriched_context=enriched_context,
        pattern_instructions=f"## ANALYTICAL PATTERN: {pattern}\n{pattern_instructions}",
        verified_section=verified_section,
        error_section=error_section,
        state_section=state_section,
    )

    raw = call_llm(
        model_key="smart_sql",
        system_prompt=system_prompt,
        user_message=f'Generate DuckDB SQL for: "{question}"\n\nReturn ONLY the JSON object. Do not include any thinking or reasoning process outside the JSON.',
        temperature=0.0,
        json_mode=True,
    )

    raw_sql = raw.get("sql", "")
    # Don't run clean_sql (strips read_csv_auto patterns) — just strip fences
    raw_sql = raw_sql.replace("```sql", "").replace("```", "").strip()
    raw["sql"] = raw_sql

    raw.setdefault("confidence", 5)
    raw.setdefault("tables_used", [])
    raw.setdefault("reasoning", "")

    return raw
