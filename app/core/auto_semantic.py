"""
Auto-Semantic Engine — the "YAML Engine" from MASTER_IMPLEMENTATION.md.

What this module does:
  After a file is loaded into DuckDB, this module analyses every table and
  column to build a rich semantic description that the SQL generator uses
  as context.  Think of it as a translator between raw data and AI-friendly
  schema understanding.

Two-phase pipeline per table:
  Phase 1 — Deep profiling (no LLM, pure DuckDB SQL):
    For every column we compute: data type, null counts, distinct values,
    min/max/avg for numerics, date ranges, and sample values for categoricals.
    This produces a schema_profile dict.

  Phase 2 — LLM enrichment (Agent 0 — Schema Analyst):
    We send the schema_profile to qwen/qwen3-coder with a structured prompt
    asking it to assign business meaning to each column:
      - "is_metric": True for SUM-able numbers (revenue, count, score)
      - "is_dimension": True for GROUP BY candidates (region, category, status)
      - "is_date": True for time-based columns
      - "description": plain-English description of what the column represents
      - "suggested_questions": example queries a user might ask

  Fast mode (FAST_UPLOAD_MODE=true):
    Skips the LLM call and uses _build_fallback_semantic() instead, which
    infers metric/dimension/date from DuckDB types alone.  This is faster
    but produces less accurate SQL generation.

The combined output is a string (enriched_context) that the SQL generator
receives as part of its system prompt — it's essentially a SQL comment block
that tells the model exactly what each column means and how to use it.
"""
from __future__ import annotations

import json
from typing import Dict, List, Any

import duckdb

from app.core.llm_client import call_llm


# ── LLM response normalizers ──────────────────────────────────────────────────

def _normalize_llm_response(result: dict) -> dict:
    """
    Fix structural inconsistencies in the LLM's JSON response.

    The Schema Analyst is told to return "columns" as a JSON object keyed
    by column name.  Some models return it as a list of objects with a "name"
    field instead.  This function converts the list form to the expected dict
    form so the rest of the pipeline always has a consistent shape.

    Also normalises "column_aliases" from list-of-dicts to a plain dict.

    Example of what gets fixed:
      Input:  {"columns": [{"name": "revenue", "is_metric": true}]}
      Output: {"columns": {"revenue": {"is_metric": true}}}
    """
    columns = result.get("columns", {})
    if isinstance(columns, list):
        col_dict = {}
        for item in columns:
            if isinstance(item, dict):
                name = (
                    item.get("name")
                    or item.get("column_name")
                    or item.get("column")
                    or item.get("col")
                )
                if name:
                    col_dict[name] = {k: v for k, v in item.items()
                                      if k not in ("name", "column_name", "column", "col")}
        result["columns"] = col_dict
    elif not isinstance(columns, dict):
        result["columns"] = {}

    aliases = result.get("column_aliases", {})
    if isinstance(aliases, list):
        alias_dict = {}
        for item in aliases:
            if isinstance(item, dict):
                alias  = item.get("alias") or item.get("user_term") or item.get("from")
                actual = item.get("actual") or item.get("column")  or item.get("to")
                if alias and actual:
                    alias_dict[alias] = actual
        result["column_aliases"] = alias_dict
    elif not isinstance(aliases, dict):
        result["column_aliases"] = {}

    return result


# ── Phase 1: Deep profiling (pure DuckDB, no LLM) ────────────────────────────

def profile_table(con: duckdb.DuckDBPyConnection, table_name: str) -> dict:
    """
    Produce a detailed statistical profile of a DuckDB table without any LLM.

    For every column this collects:
      - data type (from DuckDB's DESCRIBE)
      - null_count: how many rows are NULL
      - distinct_count: how many unique values exist
      - sample_values: up to 10-50 distinct values (for low-cardinality text)
      - min / max / avg: for numeric columns
      - min_date / max_date: for date/timestamp columns

    This structured profile is later passed to the LLM enrichment step and
    also stored in the session for use by the SQL generator context builder.

    Returns a schema_profile dict:
      {
        "table_name": str,
        "total_rows": int,
        "columns": { col_name: { "type": ..., "null_count": ..., ... } },
        "sample_data": [ { col: val, ... }, ... ]   # first 5 rows
      }
    """
    try:
        schema_rows = con.execute(f'DESCRIBE "{table_name}"').fetchall()
    except Exception as e:
        raise ValueError(f"Cannot describe table {table_name!r}: {e}") from e

    total_rows = con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]

    try:
        sample_df  = con.execute(f'SELECT * FROM "{table_name}" LIMIT 5').fetchdf()
        sample_data = sample_df.to_dict(orient="records")
    except Exception:
        sample_data = []

    columns: Dict[str, Any] = {}
    for row in schema_rows:
        col_name = row[0]
        col_type = row[1].upper()
        col_info: Dict[str, Any] = {"type": col_type}

        try:
            # Count nulls by subtracting non-null count from total
            null_count = con.execute(
                f'SELECT COUNT(*) - COUNT("{col_name}") FROM "{table_name}"'
            ).fetchone()[0]
            col_info["null_count"] = null_count

            base_type = col_type.split("(")[0].strip()

            if base_type in ("VARCHAR", "TEXT", "STRING", "CHAR"):
                # For text columns collect distinct count and sample values.
                # Low-cardinality columns (≤100 unique values) get a full value list;
                # high-cardinality ones (e.g. free-text fields) get just 10 samples.
                distinct = con.execute(
                    f'SELECT COUNT(DISTINCT "{col_name}") FROM "{table_name}"'
                ).fetchone()[0]
                col_info["distinct_count"] = distinct

                if distinct <= 100:
                    samples = con.execute(
                        f'SELECT DISTINCT "{col_name}" FROM "{table_name}" '
                        f'WHERE "{col_name}" IS NOT NULL '
                        f'ORDER BY "{col_name}" LIMIT 50'
                    ).fetchall()
                    col_info["sample_values"] = [str(r[0]) for r in samples]
                else:
                    samples = con.execute(
                        f'SELECT DISTINCT "{col_name}" FROM "{table_name}" '
                        f'WHERE "{col_name}" IS NOT NULL LIMIT 10'
                    ).fetchall()
                    col_info["sample_values"] = [str(r[0]) for r in samples]

            elif base_type in (
                "INTEGER", "BIGINT", "HUGEINT", "SMALLINT",
                "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "REAL",
            ):
                # For numeric columns get min, max, avg, and distinct count.
                result = con.execute(
                    f'SELECT MIN("{col_name}"), MAX("{col_name}"), '
                    f'ROUND(AVG(CAST("{col_name}" AS DOUBLE)), 2), '
                    f'COUNT(DISTINCT "{col_name}") FROM "{table_name}"'
                ).fetchone()
                col_info["min"]            = result[0]
                col_info["max"]            = result[1]
                col_info["avg"]            = result[2]
                col_info["distinct_count"] = result[3]

            elif base_type in ("DATE", "TIMESTAMP", "TIMESTAMPTZ"):
                # For date columns get the earliest and latest date.
                result = con.execute(
                    f'SELECT MIN("{col_name}"), MAX("{col_name}"), '
                    f'COUNT(DISTINCT "{col_name}") FROM "{table_name}"'
                ).fetchone()
                col_info["min_date"]       = str(result[0])
                col_info["max_date"]       = str(result[1])
                col_info["distinct_count"] = result[2]

        except Exception:
            pass  # Don't let profiling errors crash the upload

        columns[col_name] = col_info

    return {
        "table_name":  table_name,
        "total_rows":  total_rows,
        "columns":     columns,
        "sample_data": sample_data,
    }


# ── Phase 2: LLM enrichment (Agent 0 — Schema Analyst) ───────────────────────

def _format_columns_for_llm(columns: dict) -> str:
    """
    Format the column profile dict as a human-readable string for the LLM prompt.

    Converts the nested dict from profile_table() into a readable list that
    the Schema Analyst model can easily interpret, e.g.:

      player_name (VARCHAR)
        Sample values: ['Virat Kohli', 'Rohit Sharma', ...]
        Distinct count: 250

      runs (BIGINT)
        Range: 0 to 264, Avg: 42.3
    """
    lines = []
    for col_name, info in columns.items():
        line = f"  {col_name} ({info['type']})"
        if "sample_values" in info:
            line += f"\n    Sample values: {info['sample_values'][:10]}"
            line += f"\n    Distinct count: {info.get('distinct_count', '?')}"
        if "min" in info:
            line += f"\n    Range: {info['min']} to {info['max']}, Avg: {info['avg']}"
        if "min_date" in info:
            line += f"\n    Date range: {info['min_date']} to {info['max_date']}"
        if info.get("null_count", 0) > 0:
            line += f"\n    Nulls: {info['null_count']}"
        lines.append(line)
    return "\n".join(lines)


def _generate_semantic_enrichment(schema_profile: dict) -> dict:
    """
    Call the Schema Analyst LLM (Agent 0) to add business meaning to the schema.

    Sends the column profile to qwen/qwen3-coder and asks it to return:
      - table_description: one-sentence description of the dataset
      - columns: dict mapping each column name to its semantic role
          (is_metric / is_dimension / is_date and a plain-English description)
      - suggested_metrics: useful aggregation expressions (e.g. SUM("revenue"))
      - suggested_questions: 5 questions a user might ask about this data
      - column_aliases: mapping from user terms to column names
          (e.g. "earnings" → "revenue", "player" → "player_name")

    The returned dict is normalised by _normalize_llm_response() to ensure
    consistent structure regardless of which model answered.
    """
    col_stats  = _format_columns_for_llm(schema_profile["columns"])
    sample_str = str(schema_profile["sample_data"][:5])
    col_names_list = list(schema_profile["columns"].keys())

    prompt = f"""You are a data analyst examining a new dataset.

Table: {schema_profile['table_name']}
Total rows: {schema_profile['total_rows']}

Columns:
{col_stats}

Sample data (first 5 rows):
{sample_str}

Return a JSON object with EXACTLY these keys:
1. "table_description": one sentence describing what this data is about
2. "columns": a JSON OBJECT (NOT an array) where each KEY is a column name and the VALUE has:
   - "description": what this column likely represents
   - "is_metric": true if measurable numeric value (score, count, amount, runs, wickets, price, qty)
   - "is_dimension": true if categorical/groupable (region, team, player, category, status, name)
   - "is_date": true if date/time field
   IMPORTANT: Use EXACTLY these column names as keys: {col_names_list}
   "columns" MUST be a JSON object, NOT a list.
3. "suggested_metrics": list of useful aggregation strings (e.g. "SUM(\\"amount\\") as total_amount")
4. "suggested_questions": list of 5 example questions a user might ask about this data
5. "column_aliases": a JSON OBJECT mapping common user terms to actual column names

Be precise. Only mark is_metric=true for numeric columns. Only mark is_date=true for date/timestamp columns."""

    result = call_llm(
        model_key="schema_analyst",
        system_prompt=(
            "You are a data analyst. Respond with valid JSON only. "
            "The 'columns' field MUST be a JSON object with column names as keys."
        ),
        user_message=prompt,
        temperature=0.0,
        json_mode=True,
    )

    result = _normalize_llm_response(result)
    return result


def _build_fallback_semantic(schema_profile: dict) -> dict:
    """
    Build rule-based semantic metadata without calling any LLM.

    Used when FAST_UPLOAD_MODE=true or when the LLM call fails.
    Infers metric/dimension/date from DuckDB column types alone:
      - BIGINT / DOUBLE / DECIMAL → is_metric = True
      - DATE / TIMESTAMP          → is_date = True
      - Everything else           → is_dimension = True (categorical)

    This is faster but less accurate than LLM enrichment — the SQL generator
    won't know business aliases (e.g. "revenue" = the "amt" column) and
    suggested questions won't be available.
    """
    numeric_types = {
        "INTEGER", "BIGINT", "HUGEINT", "SMALLINT",
        "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "REAL",
    }
    date_types = {"DATE", "TIMESTAMP", "TIMESTAMPTZ"}

    columns = {}
    for col_name, col_info in schema_profile["columns"].items():
        base_type = col_info["type"].split("(")[0].strip().upper()
        columns[col_name] = {
            "description":   col_name.replace("_", " ").title(),
            "is_metric":     base_type in numeric_types,
            "is_dimension":  base_type not in numeric_types and base_type not in date_types,
            "is_date":       base_type in date_types,
        }

    return {
        "table_description":  f"Dataset with {schema_profile['total_rows']} rows",
        "columns":            columns,
        "suggested_metrics":  [],
        "suggested_questions":[],
        "column_aliases":     {},
    }


# ── Verified queries ──────────────────────────────────────────────────────────

def generate_verified_queries(
    con: duckdb.DuckDBPyConnection,
    schema_profile: dict,
    auto_semantic: dict,
) -> List[dict]:
    """
    Generate 4–6 representative SQL queries and verify they run successfully.

    These pre-tested queries serve two purposes:
      1. The upload response includes them as "suggested questions" shown to the user.
      2. When a user asks something similar, the matching verified query is injected
         into the SQL generator prompt as a working example (few-shot).

    Generated patterns (one query per applicable pattern):
      - Row count:   SELECT COUNT(*) FROM table
      - Summary:     SELECT COUNT(*), SUM(metric1), SUM(metric2) ...
      - Top 10 rows: SELECT * FROM table LIMIT 10
      - Breakdown:   SELECT dim, COUNT(*), SUM(metric) GROUP BY dim
      - Top-N:       SELECT dim, SUM(metric) GROUP BY dim ORDER BY total DESC LIMIT 10
      - Trend:       SELECT date_trunc('month', date_col), SUM(metric) GROUP BY month ORDER BY month

    Each query is tested with DuckDB before being added — if it fails or
    returns 0 rows it is silently skipped so we only store working examples.
    """
    table_name = schema_profile["table_name"]
    cols       = schema_profile["columns"]
    sem_cols   = auto_semantic.get("columns", {})
    if not isinstance(sem_cols, dict):
        sem_cols = {}

    # Identify column roles from semantic enrichment
    metrics    = [c for c, i in sem_cols.items() if i.get("is_metric")    and c in cols]
    dimensions = [c for c, i in sem_cols.items() if i.get("is_dimension") and c in cols]
    dates      = [c for c, i in sem_cols.items() if i.get("is_date")      and c in cols]

    queries = []

    def _try(sql: str) -> bool:
        """Execute SQL and return True only if it runs and returns at least one row."""
        try:
            rows = con.execute(sql).fetchall()
            return len(rows) > 0
        except Exception:
            return False

    # --- COUNT query ---
    sql = f'SELECT COUNT(*) as total_records FROM "{table_name}"'
    if _try(sql):
        queries.append({"question": f"How many records are in {table_name}?",
                        "pattern": "SUMMARY", "sql": sql})

    # --- SUMMARY query (metrics overview) ---
    if metrics:
        aggs = ", ".join(
            ["COUNT(*) as total_rows"]
            + [f'SUM("{m}") as total_{m}' for m in metrics[:3]]
        )
        sql = f'SELECT {aggs} FROM "{table_name}"'
        if _try(sql):
            queries.append({"question": f"Give me a summary of {table_name}",
                            "pattern": "SUMMARY", "sql": sql})

    # --- SAMPLE query ---
    sql = f'SELECT * FROM "{table_name}" LIMIT 10'
    if _try(sql):
        queries.append({"question": f"Show me the first 10 rows of {table_name}",
                        "pattern": "GENERAL", "sql": sql})

    # --- BREAKDOWN query (dimension × metric) ---
    if dimensions and metrics:
        dim, metric = dimensions[0], metrics[0]
        sql = (
            f'SELECT "{dim}", COUNT(*) as count, SUM("{metric}") as total_{metric} '
            f'FROM "{table_name}" '
            f'GROUP BY "{dim}" ORDER BY count DESC LIMIT 15'
        )
        if _try(sql):
            queries.append({
                "question": f"Breakdown of {table_name} by {dim}",
                "pattern": "BREAKDOWN", "sql": sql,
            })

    # --- TOP-N query ---
    if dimensions and metrics:
        dim, metric = dimensions[0], metrics[0]
        sql = (
            f'SELECT "{dim}", SUM("{metric}") as total '
            f'FROM "{table_name}" '
            f'GROUP BY "{dim}" ORDER BY total DESC LIMIT 10'
        )
        if _try(sql):
            queries.append({
                "question": f"Top 10 {dim} by {metric}",
                "pattern": "BREAKDOWN", "sql": sql,
            })

    # --- TREND query (time-series) ---
    if dates and metrics:
        date_col, metric = dates[0], metrics[0]
        sql = (
            f"SELECT date_trunc('month', \"{date_col}\") as month, "
            f'SUM("{metric}") as total_{metric}, COUNT(*) as count '
            f'FROM "{table_name}" '
            f'GROUP BY month ORDER BY month'
        )
        if _try(sql):
            queries.append({
                "question": f"Monthly trend of {metric} in {table_name}",
                "pattern": "CHANGE_ANALYSIS", "sql": sql,
            })

    return queries


# ── Context string builder ────────────────────────────────────────────────────

def build_enriched_context(schema_profile: dict, auto_semantic: dict) -> str:
    """
    Assemble the SQL-generator context string from profiling + enrichment data.

    This string is injected directly into the SQL generator's system prompt as
    a block of SQL comments.  It tells the model:
      - Which table name to query (FROM "table_name")
      - How many rows the table has
      - Every column: its type, description, sample values / range
      - Which columns are metrics (SUM-able), dimensions (GROUP BY), or dates
      - Useful aggregation expressions from the LLM
      - Column aliases (e.g. user says "revenue" → actual column "amt")

    Using SQL comment syntax (-- ...) means the context blends naturally with
    the SQL the model generates, making it less likely to confuse schema info
    with actual query content.
    """
    table_name = schema_profile["table_name"]
    table_desc = auto_semantic.get("table_description", "")
    sem_cols   = auto_semantic.get("columns", {})
    if not isinstance(sem_cols, dict):
        sem_cols = {}

    context = (
        f"-- Dataset: {table_desc}\n"
        f'-- Table name: "{table_name}"\n'
        f"-- Total rows: {schema_profile['total_rows']}\n"
        f'-- Query using: SELECT ... FROM "{table_name}"\n\n'
        "-- Schema:\n"
    )

    metrics, dimensions, dates = [], [], []

    for col_name, col_info in schema_profile["columns"].items():
        sem  = sem_cols.get(col_name, {})
        desc = sem.get("description", "")
        line = f'-- "{col_name}" ({col_info["type"]}): {desc}'

        if "sample_values" in col_info:
            line += f'\n--   Values: {col_info["sample_values"][:10]}'
        if "min" in col_info:
            line += f'\n--   Range: {col_info["min"]} to {col_info["max"]}, Avg: {col_info["avg"]}'
        if "min_date" in col_info:
            line += f'\n--   Date range: {col_info["min_date"]} to {col_info["max_date"]}'
        if col_info.get("null_count", 0) > 0:
            line += f'\n--   Contains {col_info["null_count"]} NULL values'

        context += line + "\n"

        if sem.get("is_metric"):
            metrics.append(f'"{col_name}"')
        if sem.get("is_dimension"):
            dimensions.append(f'"{col_name}"')
        if sem.get("is_date"):
            dates.append(f'"{col_name}"')

    # Summary lines so the model knows at a glance which columns to SUM vs GROUP BY
    if metrics:
        context += f"\n-- METRIC columns (use SUM/AVG/COUNT on these): {', '.join(metrics)}\n"
    if dimensions:
        context += f"-- DIMENSION columns (GROUP BY / WHERE filters): {', '.join(dimensions)}\n"
    if dates:
        context += f"-- DATE columns (time filters / trends): {', '.join(dates)}\n"

    if auto_semantic.get("suggested_metrics"):
        context += "\n-- Useful aggregation expressions:\n"
        for m in auto_semantic["suggested_metrics"]:
            context += f"--   {m}\n"

    if auto_semantic.get("column_aliases"):
        context += "\n-- Column aliases (user term → actual column name):\n"
        for alias, actual in auto_semantic["column_aliases"].items():
            context += f'--   "{alias}" means column "{actual}"\n'

    return context


# ── AutoSemantic class (session-level cache) ──────────────────────────────────

class AutoSemantic:
    """
    Session-level cache for per-table semantic profiles.

    When a file is uploaded the server calls profile_and_enrich() once per
    table.  The result is cached in self._cache so that subsequent queries
    in the same session don't re-profile the same table.

    When the session is cleared (new chat) the Session object creates a
    fresh AutoSemantic instance, discarding all cached profiles.
    """

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con
        self._cache: Dict[str, dict] = {}  # table_name → enriched profile dict

    def profile_and_enrich(
        self,
        table_name: str,
        skip_llm_enrichment: bool = False,
        defer_suggested_questions: bool = False,
    ) -> dict:
        """
        Run the full two-phase pipeline for one table and cache the result.

        Phase 1: profile_table()            — DuckDB stats, no LLM
        Phase 2: _generate_semantic_enrichment()  — LLM enrichment (Agent 0)
             or: _build_fallback_semantic()        — rule-based if LLM is skipped

        Then:
          - generate_verified_queries(): produce 4-6 tested example SQL queries
          - build_enriched_context(): produce the SQL comment block for Agent 2

        Returns the full profile dict stored in self._cache[table_name].
        Subsequent calls return the cached result directly.

        skip_llm_enrichment=True runs faster (skips Agent 0) at the cost of
        less accurate SQL generation.  Useful for very large file uploads.
        """
        if table_name in self._cache:
            return self._cache[table_name]

        print(f"[auto_semantic] Profiling table: {table_name!r}")
        schema_profile = profile_table(self.con, table_name)
        print(
            f"[auto_semantic] {schema_profile['total_rows']} rows, "
            f"{len(schema_profile['columns'])} columns"
        )

        if skip_llm_enrichment:
            print("[auto_semantic] Fast mode: skipping LLM enrichment (using fallback)")
            auto_semantic = _build_fallback_semantic(schema_profile)
        else:
            print("[auto_semantic] Calling LLM Schema Analyst (Agent 0)…")
            try:
                auto_semantic = _generate_semantic_enrichment(schema_profile)
            except Exception as e:
                print(f"[auto_semantic] LLM failed ({e}), using fallback")
                auto_semantic = _build_fallback_semantic(schema_profile)

        print("[auto_semantic] Generating verified example queries…")
        try:
            verified_queries = generate_verified_queries(
                self.con, schema_profile, auto_semantic
            )
        except Exception as e:
            print(f"[auto_semantic] Verified query generation failed ({e})")
            verified_queries = []

        print("[auto_semantic] Building enriched SQL context string…")
        try:
            enriched_context = build_enriched_context(schema_profile, auto_semantic)
        except Exception as e:
            print(f"[auto_semantic] Context build failed ({e})")
            enriched_context = (
                f'-- Table: "{table_name}"\n'
                f"-- Total rows: {schema_profile['total_rows']}\n"
            )

        col_names    = ", ".join(list(schema_profile["columns"].keys())[:10])
        schema_summary = (
            f"Table: {table_name}, "
            f"{schema_profile['total_rows']} rows, "
            f"columns: {col_names}"
        )

        # Suggested questions shown to the user after upload.
        # Deferred in fast-upload mode to keep upload latency low.
        suggested_qs = []
        if not defer_suggested_questions:
            suggested_qs = auto_semantic.get("suggested_questions", [])
            if not suggested_qs:
                suggested_qs = [vq["question"] for vq in verified_queries[:5]]

        result = {
            "schema_profile":      schema_profile,
            "auto_semantic":       auto_semantic,
            "verified_queries":    verified_queries,
            "enriched_context":    enriched_context,
            "schema_summary":      schema_summary,
            "suggested_questions": suggested_qs[:5],
            "table_name":          table_name,  # legacy key used by server.py
        }
        self._cache[table_name] = result
        print(f"[auto_semantic] Done enriching: {table_name!r}")
        return result

    def profile_all(self, table_names: List[str]) -> Dict[str, dict]:
        """
        Profile and enrich every table in the given list.
        Returns a dict mapping table_name → enriched profile.
        """
        return {t: self.profile_and_enrich(t) for t in table_names}

    def get_combined_context(self, table_names: List[str]) -> str:
        """
        Return the concatenated enriched context for multiple tables.

        Used when the user uploads several files — the SQL generator receives
        all table schemas in one prompt so it can write cross-table JOINs.
        """
        parts = []
        for t in table_names:
            profile = self.profile_and_enrich(t)
            parts.append(profile["enriched_context"])
        return "\n\n".join(parts)

    def get_combined_schema_summary(self, table_names: List[str]) -> str:
        """
        Return a single-line summary of all uploaded tables.
        Used by the Router (Agent 1) to understand what data is available
        before classifying the user's question.
        """
        parts = []
        for t in table_names:
            profile = self.profile_and_enrich(t)
            parts.append(profile["schema_summary"])
        return "; ".join(parts)

    def clear(self):
        """
        Discard all cached profiles.
        Called when the session is reset (new chat) so stale schema info
        from a previous upload can't contaminate a fresh session.
        """
        self._cache.clear()
