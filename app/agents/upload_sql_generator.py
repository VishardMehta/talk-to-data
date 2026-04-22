"""
Agent 2 — SQL Generator for uploaded data.

What this agent does:
  Takes the user's natural-language question and converts it into a valid
  DuckDB SQL query that runs against the in-memory tables created during upload.

Key design points:
  - Queries reference TABLE NAMES, never file paths.
    Data is pre-loaded by IngestionService; the SQL generator must use
    SELECT ... FROM "table_name", not read_csv_auto() or similar.
  - The full enriched context (from the YAML engine) is injected into the
    system prompt so the model knows exactly what columns exist and what
    they mean.
  - If a similar verified query exists (from upload-time generation), it is
    provided as a working example for few-shot guidance.
  - On validation or execution failure the server calls this function again
    with the error text, giving the model one retry to self-correct.
  - Returns JSON: {"sql": "...", "confidence": 1-10, "tables_used": [...], "reasoning": "..."}

DuckDB syntax rules enforced in the system prompt:
  - Always double-quote identifiers: "column_name", "table_name"
  - date_trunc('month', col) for date grouping (NOT strftime)
  - ILIKE for case-insensitive string matching
  - TRY_CAST() for safe type conversion
  - GROUP BY ALL is valid DuckDB syntax
  - Window functions: ROW_NUMBER(), RANK(), LAG(), LEAD()
  - No semicolons, no markdown fences in the output
"""
from __future__ import annotations
import re

from app.core.llm_client import call_llm


# The system prompt template — filled with per-request context before each call.
# Sections that may be empty (verified_section, error_section, state_section)
# are formatted as empty strings and effectively invisible to the model.
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

{hint_section}

{verified_section}

{error_section}

{state_section}

Respond with ONLY valid JSON:
{{"sql": "...", "confidence": <1-10>, "tables_used": [...], "reasoning": "..."}}
"""


def _extract_primary_table(enriched_context: str) -> str | None:
    """
    Extract the primary table name from the enriched context string.

    The context block always contains a line like:
      -- Table name: "sales"
    This regex extracts that table name so we can build a safe fallback
    query ("SELECT * FROM 'table_name' LIMIT 20") when the LLM returns empty SQL.
    """
    m = re.search(r'--\s*Table\s+name:\s*"([^"]+)"', enriched_context or "")
    if m:
        return m.group(1)
    return None


def generate_sql(
    question: str,
    pattern: str,
    enriched_context: str,
    verified_query: dict | None,
    filepath: str = "",           # kept for backwards compatibility, not used
    conversation_state: str = "",
    error_feedback: str | None = None,
    query_hints: list[str] | None = None,
) -> dict:
    """
    Main entry point — generate a DuckDB SQL query from a natural-language question.

    How it works:
      1. Select the right pattern instruction (BREAKDOWN / COMPARISON / etc.)
         to inject analytical hints into the prompt.
      2. If a verified query exists for a similar question, include it as a
         working example so the model has a concrete reference.
      3. If this is a retry (error_feedback is set), include the previous
         error so the model can fix the specific problem.
      4. Call the SQL generator LLM (qwen/qwen3-coder by default).
      5. Clean the response: strip markdown fences, trailing semicolons.
      6. If SQL is still empty, fall back to the verified query or a safe
         "SELECT * FROM table LIMIT 20".

    Parameters:
      question          — the user's original question
      pattern           — analytical pattern from the Router (BREAKDOWN, SUMMARY, etc.)
      enriched_context  — the schema + column descriptions from the YAML engine
      verified_query    — a pre-tested example query for a similar question (optional)
      conversation_state — context from the previous turn for follow-up questions
      error_feedback    — validation or execution error from a previous attempt (for retry)
      query_hints       — optional classifier hints that constrain SQL shape

    Returns a dict:
      {
        "sql":         "SELECT ...",
        "confidence":  7,           # 1–10 self-reported confidence
        "tables_used": ["sales"],
        "reasoning":   "..."
      }
    """
    # Map each analytical pattern to a one-line instruction that steers the SQL style.
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

    # Optional low-latency classifier hints to reduce SQL ambiguity.
    hint_section = ""
    if query_hints:
        hint_lines = [f"- {h}" for h in query_hints if str(h).strip()]
        if hint_lines:
            hint_section = "## QUERY CLASSIFIER HINTS\n" + "\n".join(hint_lines)

    # Inject the verified query as a working few-shot example when available.
    # This dramatically improves accuracy because the model sees a tested query
    # with the exact table name and column quoting style expected.
    verified_section = ""
    if verified_query:
        verified_section = (
            "## VERIFIED EXAMPLE (working SQL for a similar question)\n"
            f"Question: {verified_query.get('question', '')}\n"
            f"SQL: {verified_query.get('sql', '')}\n"
        )

    # On retry, include the full error message so the model can fix the root cause.
    error_section = ""
    if error_feedback:
        error_section = (
            "## PREVIOUS ATTEMPT FAILED — FIX THIS ERROR\n"
            f"Error: {error_feedback}\n"
            "Read the error carefully. Fix the specific issue. "
            "Do NOT use file-read functions — query the table directly.\n"
        )

    # Include previous conversation context for follow-up questions
    # (e.g. "show me that by month" referencing a previous breakdown).
    state_section = ""
    if conversation_state:
        state_section = f"## CONVERSATION CONTEXT\n{conversation_state}\n"

    system_prompt = _DUCKDB_SYSTEM.format(
        enriched_context=enriched_context,
        pattern_instructions=pattern_instructions,
        hint_section=hint_section,
        verified_section=verified_section,
        error_section=error_section,
        state_section=state_section,
    )

    try:
        raw = call_llm(
            model_key="sql_generator",
            system_prompt=system_prompt,
            user_message=f'Generate DuckDB SQL for: "{question}"',
            temperature=0.0,   # deterministic — SQL must be exact, not creative
            json_mode=True,
        )
    except Exception as e:
        print(f"[sql_generator] LLM call failed, using fallback SQL: {e}")
        raw = {}

    # Normalise the raw response — some models return arrays or plain strings
    # despite json_mode=True.
    if isinstance(raw, list):
        raw = raw[0] if raw and isinstance(raw[0], dict) else {}
    elif isinstance(raw, str):
        raw = {"sql": raw}
    elif not isinstance(raw, dict):
        raw = {}

    raw_sql = str(raw.get("sql", "") or "")

    # Strip any accidental markdown fences the model added
    raw_sql = raw_sql.replace("```sql", "").replace("```", "").strip()
    # Remove trailing semicolons — DuckDB accepts them but they can cause issues
    # when the pipeline embeds the query in EXPLAIN or multi-statement contexts.
    raw_sql = raw_sql.rstrip(";").strip()

    # Safety net: if SQL is completely empty after cleaning, provide a valid fallback
    # so the pipeline never crashes with an empty query string.
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

    # Set default values for optional fields the model might have omitted
    raw.setdefault("confidence", 5)
    raw.setdefault("tables_used", [])
    raw.setdefault("reasoning", "")
    return raw
