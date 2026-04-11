"""
Agent 2 — SQL Generator
Generates SQL queries from natural language using the 70B model.

Takes semantic layer context, pattern templates, and verified query examples
to produce accurate SQLite-compatible SQL.
"""

import os
import yaml
from app.core.groq_client import call_llm

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PATTERNS_PATH = os.path.join(_BASE_DIR, "config", "pattern_templates.yaml")

# Load pattern templates once
with open(_PATTERNS_PATH, "r") as f:
    _PATTERNS = yaml.safe_load(f).get("patterns", {})


SQL_GENERATOR_SYSTEM_PROMPT = """You are an expert SQL query generator for SQLite databases. Generate precise, efficient SQL.

{pattern_instructions}

=== DATABASE SCHEMA ===
{semantic_context}

=== RULES ===
1. Use ONLY SQLite syntax. Use date(), strftime(), date('now'), date('now', '-1 month'), date('now', 'start of month').
2. Do NOT use ILIKE — use LIKE with LOWER() instead.
3. Do NOT use DATEADD, DATEDIFF, NOW() — these are NOT SQLite functions.
4. Always use table aliases in JOINs (e.g., orders o, customers c).
5. Never invent columns not shown in the schema above.
6. Use the pre-defined metrics and filters when they match the question.
7. Include appropriate GROUP BY, ORDER BY, and LIMIT clauses.
8. Handle NULLs with COALESCE or IS NOT NULL where appropriate.

{verified_example}

{error_feedback}

{followup_context}

Return ONLY valid JSON with this exact structure:
{{
    "sql": "SELECT ...",
    "confidence": 8,
    "tables_used": ["orders", "customers"],
    "reasoning": "Brief explanation of approach"
}}"""


def generate_sql(
    question: str,
    pattern: str,
    semantic_context: str,
    verified_query: dict | None = None,
    conversation_state: str = "",
    error_feedback: str | None = None,
) -> dict:
    """
    Generate a SQL query for the user's question.

    Args:
        question: Natural language question
        pattern: Analytical pattern (CHANGE_ANALYSIS, COMPARISON, etc.)
        semantic_context: Enriched DDL from semantic layer
        verified_query: Best matching verified query for few-shot example
        conversation_state: Previous conversation context
        error_feedback: Error from a previous failed attempt (for retry)

    Returns:
        Dict with 'sql', 'confidence', 'tables_used', 'reasoning'
    """
    # Get pattern-specific instructions
    pattern_config = _PATTERNS.get(pattern, _PATTERNS.get("GENERAL", {}))
    pattern_instructions = pattern_config.get("system_prompt", "Generate accurate SQL for the question.")

    # Build verified example section
    verified_section = ""
    if verified_query:
        verified_section = f"""
=== EXAMPLE (similar question) ===
Question: {verified_query['question']}
SQL: {verified_query['sql']}
"""

    # Build error feedback section
    error_section = ""
    if error_feedback:
        error_section = f"""
=== PREVIOUS ATTEMPT FAILED ===
Error: {error_feedback}
Fix the SQL to address this error. Do NOT repeat the same mistake.
"""

    # Build follow-up context section
    followup_section = ""
    if conversation_state:
        followup_section = f"""
=== CONVERSATION CONTEXT ===
{conversation_state}
"""

    system = SQL_GENERATOR_SYSTEM_PROMPT.format(
        pattern_instructions=pattern_instructions,
        semantic_context=semantic_context,
        verified_example=verified_section,
        error_feedback=error_section,
        followup_context=followup_section,
    )

    try:
        result = call_llm(
            model_key="smart",
            system_prompt=system,
            user_message=question,
            temperature=0.0,
            json_mode=True,
        )

        # Validate response
        if "sql" not in result or not result["sql"]:
            raise ValueError("No SQL in response")
        
        if "confidence" not in result:
            result["confidence"] = 5
        if "tables_used" not in result:
            result["tables_used"] = []
        if "reasoning" not in result:
            result["reasoning"] = ""

        # Clean the SQL
        from app.utils.sql_parser import clean_sql
        result["sql"] = clean_sql(result["sql"])

        return result

    except Exception as e:
        return {
            "sql": "",
            "confidence": 0,
            "tables_used": [],
            "reasoning": f"Failed to generate SQL: {str(e)[:200]}",
        }
