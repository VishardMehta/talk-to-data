"""
Agent 2 — SQL Generator for uploaded data.

Generates DuckDB SQL queries that reference TABLE NAMES (not file paths).
Data is loaded into in-memory DuckDB tables on upload and never persisted to disk.
"""
from __future__ import annotations
import re

from app.core.llm_client import call_llm


_DUCKDB_SYSTEM = """You are a DuckDB SQL expert. Generate a SQL query that answers the user's question.

CRITICAL DuckDB RULES:
1. Query using TABLE NAMES — data is pre-loaded into DuckDB.
   e.g.  SELECT * FROM "sales"   or   SELECT * FROM "my_data"
   NEVER use read_csv_auto(), read_json_auto(), read_parquet() or any file-read function.
2. Always double-quote column names and table names: "column_name", "table_name"
3. DuckDB date functions:
   - date_trunc('month', col)  for month/year truncation
   - CURRENT_DATE              for today
   - CURRENT_DATE - INTERVAL '30 days'  for relative dates
   - ILIKE                     for case-insensitive string matching
4. For % of total: SUM(col) * 100.0 / SUM(SUM(col)) OVER ()
5. TRY_CAST(col AS TYPE) for safe type conversion
6. GROUP BY ALL  is valid DuckDB syntax
7. Window functions: ROW_NUMBER() OVER (...), RANK() OVER (...), LAG(), LEAD()
8. RANKING QUERIES — always return the full sorted comparison set so the frontend can show a chart:
   - "best X" / "most X" / "highest X" with NO explicit count → ORDER BY metric DESC LIMIT 10
   - "top N X" / "bottom N X" with explicit number → ORDER BY metric DESC/ASC LIMIT N
   - "top 1" or "single best" explicitly → ORDER BY metric DESC LIMIT 1
   - NEVER default to LIMIT 1 for a generic "best/worst/highest/lowest" question with no number
9. NEVER include semicolons. NEVER use markdown fences. Return ONLY the SQL.
10. For multi-table queries use explicit JOIN with ON clause.

{enriched_context}

{pattern_instructions}

{verified_section}

{error_section}

{state_section}

Respond with ONLY valid JSON:
{{"sql": "...", "confidence": <1-10>, "tables_used": [...], "reasoning": "..."}}
"""


def _extract_primary_table(enriched_context: str) -> str | None:
    """Find first table name from context comments: -- Table name: "foo"."""
    m = re.search(r'--\s*Table\s+name:\s*"([^"]+)"', enriched_context or "")
    if m:
        return m.group(1)
    return None


def generate_sql(
    question: str,
    pattern: str,
    enriched_context: str,
    verified_query: dict | None,
    filepath: str = "",          # kept for signature compat, not used
    conversation_state: str = "",
    error_feedback: str | None = None,
) -> dict:
    pattern_map = {
        "BREAKDOWN":      "Break down the data by one or more dimension columns. Use GROUP BY.",
        "COMPARISON":     "Compare values across categories or time periods side by side.",
        "CHANGE_ANALYSIS":"Analyze trends or changes over time. Use date columns for time series.",
        "SUMMARY":        "Provide key summary statistics: totals, averages, counts.",
        "GENERAL":        "Answer the specific question accurately using the available columns.",
    }
    pattern_instructions = (
        f"## ANALYTICAL PATTERN: {pattern}\n"
        f"{pattern_map.get(pattern, pattern_map['GENERAL'])}"
    )

    verified_section = ""
    if verified_query:
        verified_section = (
            "## VERIFIED EXAMPLE (working SQL for a similar question)\n"
            f"Question: {verified_query.get('question', '')}\n"
            f"SQL: {verified_query.get('sql', '')}\n"
        )

    error_section = ""
    if error_feedback:
        error_section = (
            "## PREVIOUS ATTEMPT FAILED — FIX THIS ERROR\n"
            f"Error: {error_feedback}\n"
            "Read the error carefully. Fix the specific issue. "
            "Do NOT use file-read functions — query the table directly.\n"
        )

    state_section = ""
    if conversation_state:
        state_section = f"## CONVERSATION CONTEXT\n{conversation_state}\n"

    system_prompt = _DUCKDB_SYSTEM.format(
        enriched_context=enriched_context,
        pattern_instructions=pattern_instructions,
        verified_section=verified_section,
        error_section=error_section,
        state_section=state_section,
    )

    try:
        raw = call_llm(
            model_key="sql_generator",
            system_prompt=system_prompt,
            user_message=f'Generate DuckDB SQL for: "{question}"',
            temperature=0.0,
            json_mode=True,
        )
    except Exception as e:
        print(f"[sql_generator] LLM JSON response failed, using fallback SQL: {e}")
        raw = {}

    # Some models return arrays or plain strings despite json_mode.
    if isinstance(raw, list):
        raw = raw[0] if raw and isinstance(raw[0], dict) else {}
    elif isinstance(raw, str):
        raw = {"sql": raw}
    elif not isinstance(raw, dict):
        raw = {}

    raw_sql = str(raw.get("sql", "") or "")
    # Strip any accidental markdown fences
    raw_sql = raw_sql.replace("```sql", "").replace("```", "").strip()
    # Remove trailing semicolons
    raw_sql = raw_sql.rstrip(";").strip()

    # Final guard: if SQL is still empty, fall back safely to a deterministic query.
    if not raw_sql:
        if verified_query and isinstance(verified_query, dict):
            raw_sql = str(verified_query.get("sql", "") or "").rstrip(";").strip()
        if not raw_sql:
            table_name = _extract_primary_table(enriched_context)
            if table_name:
                raw_sql = f'SELECT * FROM "{table_name}" LIMIT 20'
            else:
                raw_sql = "SELECT 1 AS value"

    raw["sql"] = raw_sql

    raw.setdefault("confidence", 5)
    raw.setdefault("tables_used", [])
    raw.setdefault("reasoning", "")
    return raw
