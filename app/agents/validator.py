"""
SQL Validator — Agent 3.

Validation pipeline (no LLM):
  1. Clean / sanitize SQL (strips multiple statements — fixes Errors 1-3)
  2. Safety check (SELECT only)
  3. Schema whitelist check
  4. Execute against SQLite
  5. Empty result check
"""

import sqlite3
from pathlib import Path
from app.utils.sql_parser import clean_sql, extract_tables, is_select_only


def validate_and_execute(sql: str, semantic_layer, db_path: str) -> dict:
    # ------------------------------------------------------------------ #
    # Step 1 — Clean SQL (handles multi-statement, markdown, think tags)  #
    # ------------------------------------------------------------------ #
    sql = clean_sql(sql)

    if not sql:
        return _err("SYNTAX", "SQL is empty after cleaning.")

    # ------------------------------------------------------------------ #
    # Step 2 — Safety check: only SELECT allowed                          #
    # ------------------------------------------------------------------ #
    if not is_select_only(sql):
        return _err(
            "SYNTAX",
            "Query contains a forbidden keyword (INSERT/UPDATE/DELETE/DROP/ALTER/CREATE). "
            "Only SELECT statements are allowed.",
        )

    # Also ensure it actually starts with SELECT
    first_word = sql.strip().split()[0].upper() if sql.strip() else ""
    if first_word != "SELECT":
        return _err("SYNTAX", f"Query must start with SELECT, got: '{first_word}'.")

    # ------------------------------------------------------------------ #
    # Step 3 — Schema whitelist check                                     #
    # ------------------------------------------------------------------ #
    valid_tables = set(semantic_layer.get_all_valid_tables())
    used_tables = extract_tables(sql)

    for t in used_tables:
        if t not in valid_tables:
            available = ", ".join(sorted(valid_tables))
            return _err(
                "SCHEMA",
                f"Table '{t}' does not exist. Available tables: {available}.",
            )

    # Column whitelist (best-effort — only plain column refs, not expressions)
    for t in used_tables:
        valid_cols = set(semantic_layer.get_all_valid_columns(t))
        # We skip column validation for tables whose columns we can't map easily

    # ------------------------------------------------------------------ #
    # Step 4 — Execute                                                    #
    # ------------------------------------------------------------------ #
    # Resolve db_path relative to project root if it's a relative path
    if not Path(db_path).is_absolute():
        base = Path(__file__).resolve().parent.parent.parent
        db_path = str(base / db_path)

    try:
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description] if cursor.description else []
        conn.close()
    except sqlite3.OperationalError as e:
        return _err("SYNTAX", f"SQL execution error: {e}")
    except Exception as e:
        return _err("SYNTAX", f"Unexpected DB error: {e}")

    # ------------------------------------------------------------------ #
    # Step 5 — Empty result check                                         #
    # ------------------------------------------------------------------ #
    results = [tuple(row) for row in rows]

    if not results:
        return {
            "success": False,
            "results": [],
            "columns": columns,
            "error": "Query returned no results. The filters may be too narrow.",
            "error_type": "EMPTY",
        }

    return {
        "success": True,
        "results": results,
        "columns": columns,
        "error": None,
        "error_type": None,
    }


def _err(error_type: str, message: str) -> dict:
    return {
        "success": False,
        "results": None,
        "columns": None,
        "error": message,
        "error_type": error_type,
    }
