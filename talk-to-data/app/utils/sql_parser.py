"""
SQL parsing utilities using regex only (no sqlparse dependency).

Bug-fix focus:
- clean_sql removes multiple-statement blocks, markdown fences, <think> tags
- extract_first_statement isolates the first valid SELECT when the LLM
  accidentally emits multiple queries (the root cause of Errors 1-3)
"""

import re


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_sql(sql: str) -> str:
    """
    Sanitize LLM output into a single, executable SELECT statement.

    Handles:
    - Markdown ```sql ... ``` fences
    - <think>...</think> reasoning blocks
    - Multiple statements separated by ; or ---
    - Leading/trailing whitespace and stray semicolons
    """
    if not sql:
        return ""

    # 1. Strip <think>...</think> blocks (some models emit chain-of-thought)
    sql = re.sub(r"<think>.*?</think>", "", sql, flags=re.DOTALL | re.IGNORECASE)

    # 2. Strip markdown code fences (```sql ... ``` or ``` ... ```)
    sql = re.sub(r"```(?:sql)?", "", sql, flags=re.IGNORECASE)

    # 3. Extract just the first SELECT statement when the LLM produced multiple
    sql = extract_first_statement(sql)

    # 4. Remove trailing semicolons and whitespace
    sql = sql.strip().rstrip(";").strip()

    return sql


def extract_first_statement(sql: str) -> str:
    """
    Bug fix for Error 1 (multiple statements) and Error 2 (SELECT after SELECT).

    Strategy:
    1. Split on --- delimiters first (the pattern_templates suggest --- as separator)
    2. Among the parts, take the first that starts with SELECT
    3. If the chosen part itself contains a bare second SELECT (not inside
       parentheses or a subquery), trim at that point.
    """
    if not sql:
        return ""

    # Split on --- separator used in CHANGE_ANALYSIS template
    parts = re.split(r"\n---+\n", sql)

    # Find first part that contains a SELECT
    chosen = ""
    for part in parts:
        stripped = part.strip()
        if re.search(r"^\s*SELECT\b", stripped, re.IGNORECASE):
            chosen = stripped
            break

    # Fallback: use whatever we have
    if not chosen:
        chosen = sql.strip()

    # Now remove any second top-level SELECT that isn't inside parentheses.
    # We do this by scanning character by character to track paren depth.
    chosen = _strip_second_top_level_select(chosen)

    return chosen.strip()


def extract_tables(sql: str) -> list[str]:
    """Extract table names referenced in FROM and JOIN clauses."""
    # Match: FROM table_name [alias] and JOIN table_name [alias]
    pattern = re.compile(
        r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        re.IGNORECASE,
    )
    tables = [m.group(1).lower() for m in pattern.finditer(sql)]
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for t in tables:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def extract_columns(sql: str) -> list[str]:
    """
    Extract bare column references from SELECT, WHERE, GROUP BY, ORDER BY clauses.
    This is intentionally permissive — used only for schema whitelist checking.
    """
    # Remove subqueries first (content inside parens) to avoid false positives
    flat = _remove_parens_content(sql)

    # Strip known keywords and function names
    flat = re.sub(
        r"\b(SELECT|FROM|WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|JOIN|ON|AND|OR|"
        r"NOT|AS|CASE|WHEN|THEN|ELSE|END|DISTINCT|LIMIT|OFFSET|IN|BETWEEN|LIKE|"
        r"IS|NULL|TRUE|FALSE|COUNT|SUM|AVG|MIN|MAX|ROUND|CAST|COALESCE|"
        r"strftime|date|INNER|LEFT|RIGHT|OUTER|CROSS)\b",
        " ",
        flat,
        flags=re.IGNORECASE,
    )

    # Extract identifiers — may be table.column or plain column
    raw = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?", flat)
    columns = []
    for ref in raw:
        if "." in ref:
            columns.append(ref.split(".")[1])
        else:
            columns.append(ref)
    return list(set(columns))


def is_select_only(sql: str) -> bool:
    """Return True if SQL contains no mutation keywords."""
    dangerous = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE)\b",
        re.IGNORECASE,
    )
    return not bool(dangerous.search(sql))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_second_top_level_select(sql: str) -> str:
    """
    Walk the SQL string; when we encounter a SELECT keyword at depth 0
    (not inside parentheses) for the second time, truncate there.

    This fixes Error 2: "near SELECT: syntax error" caused by the LLM
    concatenating two queries without a separator.
    """
    depth = 0
    select_count = 0
    i = 0
    n = len(sql)
    upper = sql.upper()

    while i < n:
        ch = sql[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and upper[i:i+6] == "SELECT":
            # Make sure it's a word boundary
            before_ok = (i == 0 or not sql[i-1].isalnum() and sql[i-1] != "_")
            after_ok = (i + 6 >= n or not sql[i+6].isalnum() and sql[i+6] != "_")
            if before_ok and after_ok:
                select_count += 1
                if select_count == 2:
                    # Truncate before this second top-level SELECT
                    return sql[:i].rstrip().rstrip(",").rstrip()
        i += 1

    return sql


def _remove_parens_content(sql: str) -> str:
    """Replace content inside parentheses with spaces (handles nesting)."""
    result = list(sql)
    depth = 0
    for i, ch in enumerate(result):
        if ch == "(":
            depth += 1
            result[i] = " "
        elif ch == ")":
            depth = max(0, depth - 1)
            result[i] = " "
        elif depth > 0:
            result[i] = " "
    return "".join(result)
