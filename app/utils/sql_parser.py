"""
SQL parsing utilities using regex.
Extracts tables, columns, validates safety, and cleans LLM output.
"""

import re


def extract_tables(sql: str) -> list[str]:
    """
    Extract table names from FROM and JOIN clauses.
    
    Handles:
    - FROM table_name
    - FROM table_name alias
    - JOIN table_name ON ...
    - LEFT/RIGHT/INNER/OUTER JOIN table_name ...
    """
    sql_clean = sql.strip().upper()
    
    # Remove string literals to avoid false matches
    sql_no_strings = re.sub(r"'[^']*'", "''", sql)
    
    tables = set()
    
    # Match FROM clause (handles multiple tables with commas)
    from_pattern = r'\bFROM\s+(\w+)'
    for match in re.finditer(from_pattern, sql_no_strings, re.IGNORECASE):
        tables.add(match.group(1).lower())
    
    # Match JOIN clauses
    join_pattern = r'\bJOIN\s+(\w+)'
    for match in re.finditer(join_pattern, sql_no_strings, re.IGNORECASE):
        tables.add(match.group(1).lower())
    
    # Filter out SQL keywords that might be caught
    sql_keywords = {
        "select", "where", "group", "order", "having", "limit",
        "union", "intersect", "except", "values", "set", "as",
        "on", "and", "or", "not", "in", "between", "like",
        "case", "when", "then", "else", "end", "null",
    }
    tables -= sql_keywords
    
    return list(tables)


def extract_columns(sql: str) -> list[str]:
    """
    Extract column references from SQL.
    Returns column names (without table prefixes).
    """
    # Remove string literals
    sql_no_strings = re.sub(r"'[^']*'", "''", sql)
    
    columns = set()
    
    # Match table.column patterns
    dot_pattern = r'(\w+)\.(\w+)'
    for match in re.finditer(dot_pattern, sql_no_strings, re.IGNORECASE):
        col = match.group(2).lower()
        # Filter out SQL functions and keywords
        if col not in {"as", "on", "and", "or", "not", "in", "desc", "asc"}:
            columns.add(col)
    
    return list(columns)


def is_select_only(sql: str) -> bool:
    """
    Check that SQL contains only SELECT statements, no mutations.
    Returns True if safe, False if contains dangerous statements.
    """
    # Normalize
    sql_upper = sql.strip().upper()
    
    # Remove string literals to avoid false positives
    sql_clean = re.sub(r"'[^']*'", "''", sql_upper)
    
    # Check for dangerous keywords at word boundaries
    dangerous = [
        r'\bINSERT\b', r'\bUPDATE\b', r'\bDELETE\b',
        r'\bDROP\b', r'\bALTER\b', r'\bCREATE\b',
        r'\bTRUNCATE\b', r'\bREPLACE\b', r'\bEXEC\b',
        r'\bEXECUTE\b', r'\bGRANT\b', r'\bREVOKE\b',
    ]
    
    for pattern in dangerous:
        if re.search(pattern, sql_clean):
            return False
    
    return True


def clean_sql(sql: str) -> str:
    """
    Clean SQL output from LLM.
    
    Removes:
    - ```sql``` code blocks
    - <think>...</think> tags
    - Trailing semicolons
    - Extra whitespace
    - Leading/trailing explanation text
    """
    cleaned = sql.strip()
    
    # Remove <think>...</think> tags (Groq sometimes adds these)
    cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL)
    
    # Remove ```sql ... ``` blocks — extract just the SQL
    code_block = re.search(r'```(?:sql)?\s*\n?(.*?)```', cleaned, re.DOTALL | re.IGNORECASE)
    if code_block:
        cleaned = code_block.group(1)
    
    # Remove any remaining ``` markers
    cleaned = cleaned.replace("```", "")
    
    # Remove "sql" prefix if LLM prepended it
    cleaned = re.sub(r'^sql\s*\n', '', cleaned, flags=re.IGNORECASE)
    
    # Strip whitespace
    cleaned = cleaned.strip()
    
    # Remove trailing semicolons (SQLite doesn't need them and they can cause issues)
    cleaned = cleaned.rstrip(";").strip()
    
    # If there's explanatory text before SELECT, extract just the SQL
    select_match = re.search(r'(SELECT\s+.*)', cleaned, re.DOTALL | re.IGNORECASE)
    if select_match:
        cleaned = select_match.group(1).rstrip(";").strip()
    
    return cleaned
