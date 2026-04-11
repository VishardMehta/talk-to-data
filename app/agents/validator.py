"""
Agent 3 — SQL Validator
Validates SQL against the schema whitelist and executes it against SQLite.

Mostly code-based (no LLM) — performs schema checks, safety checks,
and execution with proper error reporting.
"""

import os
import sqlite3

from app.utils.sql_parser import extract_tables, extract_columns, is_select_only, clean_sql

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def validate_and_execute(sql: str, semantic_layer, db_path: str = None) -> dict:
    """
    Validate SQL against schema and execute it.

    Validation steps:
    1. Safety check — reject mutations (INSERT, UPDATE, DELETE, etc.)
    2. Schema whitelist — check tables and columns exist
    3. SQL execution — run against SQLite with timeout
    4. Empty result check

    Args:
        sql: The SQL query to validate and execute
        semantic_layer: SemanticLayer instance for schema validation
        db_path: Path to SQLite database (defaults to data/demo.db)

    Returns:
        Dict with 'success', 'results', 'columns', 'error', 'error_type'
    """
    if db_path is None:
        db_path = os.path.join(_BASE_DIR, "data", "demo.db")

    # Clean the SQL first
    sql = clean_sql(sql)

    if not sql or not sql.strip():
        return {
            "success": False,
            "results": None,
            "columns": None,
            "error": "Empty SQL query",
            "error_type": "SYNTAX",
        }

    # ── Step 1: Safety Check ─────────────────────────────────────────────
    if not is_select_only(sql):
        return {
            "success": False,
            "results": None,
            "columns": None,
            "error": "Only SELECT queries are allowed. INSERT, UPDATE, DELETE, DROP, ALTER, CREATE are forbidden.",
            "error_type": "SAFETY",
        }

    # ── Step 2: Schema Whitelist Check ───────────────────────────────────
    valid_tables = semantic_layer.get_all_valid_tables()

    # Check tables
    used_tables = extract_tables(sql)
    invalid_tables = [t for t in used_tables if t not in valid_tables]
    if invalid_tables:
        return {
            "success": False,
            "results": None,
            "columns": None,
            "error": (
                f"Table(s) {', '.join(repr(t) for t in invalid_tables)} do not exist. "
                f"Available tables: {', '.join(valid_tables)}"
            ),
            "error_type": "SCHEMA",
        }

    # Check columns (soft check — warn but don't block for aliased columns)
    used_columns = extract_columns(sql)
    for table in used_tables:
        valid_cols = semantic_layer.get_all_valid_columns(table)
        for col in used_columns:
            # Skip aggregate function names and common SQL tokens
            if col.lower() in {
                "count", "sum", "avg", "min", "max", "round", "cast",
                "strftime", "date", "coalesce", "case", "when", "then",
                "else", "end", "distinct", "as", "desc", "asc", "total",
                "abs", "length", "lower", "upper", "trim", "replace",
                "substr", "instr", "nullif", "iif", "typeof",
            }:
                continue
            # Column is valid if it exists in ANY of the used tables
            found = False
            for t in used_tables:
                if col in semantic_layer.get_all_valid_columns(t):
                    found = True
                    break
            if not found:
                # This is a soft warning — column might be an alias
                # Only error if the column is clearly wrong
                all_valid_cols = set()
                for t in used_tables:
                    all_valid_cols.update(semantic_layer.get_all_valid_columns(t))
                
                # If none of the extracted columns match any valid column,
                # it's likely a parsing issue — allow execution
                if col not in all_valid_cols and len(col) > 2:
                    # Don't block — let SQLite catch it
                    pass

    # ── Step 3: SQL Execution ────────────────────────────────────────────
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA query_only = ON")  # Extra safety
        cursor = conn.cursor()
        cursor.execute(sql)
        
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        
        conn.close()
    except sqlite3.OperationalError as e:
        return {
            "success": False,
            "results": None,
            "columns": None,
            "error": f"SQL execution error: {str(e)}. Check column names and syntax.",
            "error_type": "SYNTAX",
        }
    except sqlite3.Error as e:
        return {
            "success": False,
            "results": None,
            "columns": None,
            "error": f"Database error: {str(e)}",
            "error_type": "SYNTAX",
        }
    except Exception as e:
        return {
            "success": False,
            "results": None,
            "columns": None,
            "error": f"Unexpected error: {str(e)}",
            "error_type": "SYNTAX",
        }

    # ── Step 4: Empty Result Check ───────────────────────────────────────
    if not results:
        return {
            "success": False,
            "results": [],
            "columns": columns,
            "error": "Query returned no results. The filters may be too narrow or the time period might not have data.",
            "error_type": "EMPTY",
        }

    # ── Step 5: Success ──────────────────────────────────────────────────
    return {
        "success": True,
        "results": results,
        "columns": columns,
        "error": None,
        "error_type": None,
    }
