"""
Auto-generate semantic context for uploaded data.

Works with DuckDB in-memory tables (not file paths).
Profile once per table on upload, cache in session state.
"""
from __future__ import annotations

import json
from typing import Dict, List, Any

import duckdb

from app.core.llm_client import call_llm


# ── LLM response normalizers ──────────────────────────────────────────────────

def _normalize_llm_response(result: dict) -> dict:
    """
    LLM sometimes returns 'columns' as a list instead of a dict.
    Expected: {"columns": {"col1": {...}, ...}}
    Fix both forms.
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
                alias = item.get("alias") or item.get("user_term") or item.get("from")
                actual = item.get("actual") or item.get("column") or item.get("to")
                if alias and actual:
                    alias_dict[alias] = actual
        result["column_aliases"] = alias_dict
    elif not isinstance(aliases, dict):
        result["column_aliases"] = {}

    return result


# ── Deep profiling (DuckDB SQL, no LLM) ──────────────────────────────────────

def profile_table(con: duckdb.DuckDBPyConnection, table_name: str) -> dict:
    """Deep-profile a DuckDB table. Returns schema_profile dict."""
    try:
        schema_rows = con.execute(f'DESCRIBE "{table_name}"').fetchall()
    except Exception as e:
        raise ValueError(f"Cannot describe table {table_name!r}: {e}") from e

    total_rows = con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]

    try:
        sample_df = con.execute(f'SELECT * FROM "{table_name}" LIMIT 5').fetchdf()
        sample_data = sample_df.to_dict(orient="records")
    except Exception:
        sample_data = []

    columns: Dict[str, Any] = {}
    for row in schema_rows:
        col_name = row[0]
        col_type = row[1].upper()
        col_info: Dict[str, Any] = {"type": col_type}

        try:
            null_count = con.execute(
                f'SELECT COUNT(*) - COUNT("{col_name}") FROM "{table_name}"'
            ).fetchone()[0]
            col_info["null_count"] = null_count

            base_type = col_type.split("(")[0].strip()

            if base_type in ("VARCHAR", "TEXT", "STRING", "CHAR"):
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
                result = con.execute(
                    f'SELECT MIN("{col_name}"), MAX("{col_name}"), '
                    f'ROUND(AVG(CAST("{col_name}" AS DOUBLE)), 2), '
                    f'COUNT(DISTINCT "{col_name}") FROM "{table_name}"'
                ).fetchone()
                col_info["min"] = result[0]
                col_info["max"] = result[1]
                col_info["avg"] = result[2]
                col_info["distinct_count"] = result[3]

            elif base_type in ("DATE", "TIMESTAMP", "TIMESTAMPTZ"):
                result = con.execute(
                    f'SELECT MIN("{col_name}"), MAX("{col_name}"), '
                    f'COUNT(DISTINCT "{col_name}") FROM "{table_name}"'
                ).fetchone()
                col_info["min_date"] = str(result[0])
                col_info["max_date"] = str(result[1])
                col_info["distinct_count"] = result[2]

        except Exception:
            pass  # skip profiling errors gracefully

        columns[col_name] = col_info

    return {
        "table_name": table_name,
        "total_rows": total_rows,
        "columns": columns,
        "sample_data": sample_data,
    }


# ── LLM enrichment (Agent 0 — Schema Analyst) ────────────────────────────────

def _format_columns_for_llm(columns: dict) -> str:
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
    """One LLM call → semantic metadata for the SQL generator."""
    col_stats = _format_columns_for_llm(schema_profile["columns"])
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
    """Rule-based fallback when LLM fails."""
    numeric_types = {
        "INTEGER", "BIGINT", "HUGEINT", "SMALLINT",
        "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "REAL",
    }
    date_types = {"DATE", "TIMESTAMP", "TIMESTAMPTZ"}

    columns = {}
    for col_name, col_info in schema_profile["columns"].items():
        base_type = col_info["type"].split("(")[0].strip().upper()
        columns[col_name] = {
            "description": col_name.replace("_", " ").title(),
            "is_metric": base_type in numeric_types,
            "is_dimension": base_type not in numeric_types and base_type not in date_types,
            "is_date": base_type in date_types,
        }

    return {
        "table_description": f"Dataset with {schema_profile['total_rows']} rows",
        "columns": columns,
        "suggested_metrics": [],
        "suggested_questions": [],
        "column_aliases": {},
    }


# ── Verified queries ──────────────────────────────────────────────────────────

def generate_verified_queries(
    con: duckdb.DuckDBPyConnection,
    schema_profile: dict,
    auto_semantic: dict,
) -> List[dict]:
    """Generate 4–6 representative SQL queries and test them against DuckDB."""
    table_name = schema_profile["table_name"]
    cols = schema_profile["columns"]
    sem_cols = auto_semantic.get("columns", {})
    if not isinstance(sem_cols, dict):
        sem_cols = {}

    metrics = [c for c, i in sem_cols.items()
               if i.get("is_metric") and c in cols]
    dimensions = [c for c, i in sem_cols.items()
                  if i.get("is_dimension") and c in cols]
    dates = [c for c, i in sem_cols.items()
             if i.get("is_date") and c in cols]

    queries = []

    def _try(sql: str) -> bool:
        try:
            rows = con.execute(sql).fetchall()
            return len(rows) > 0
        except Exception:
            return False

    # Row count
    sql = f'SELECT COUNT(*) as total_records FROM "{table_name}"'
    if _try(sql):
        queries.append({"question": f"How many records are in {table_name}?",
                         "pattern": "SUMMARY", "sql": sql})

    # Summary of metrics
    if metrics:
        aggs = ", ".join(
            [f'COUNT(*) as total_rows']
            + [f'SUM("{m}") as total_{m}' for m in metrics[:3]]
        )
        sql = f'SELECT {aggs} FROM "{table_name}"'
        if _try(sql):
            queries.append({"question": f"Give me a summary of {table_name}",
                             "pattern": "SUMMARY", "sql": sql})

    # Top 10 rows
    sql = f'SELECT * FROM "{table_name}" LIMIT 10'
    if _try(sql):
        queries.append({"question": f"Show me the first 10 rows of {table_name}",
                         "pattern": "GENERAL", "sql": sql})

    # Breakdown by first dimension
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

    # Top-N by metric
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

    # Trend over time
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


# ── Enriched context string ───────────────────────────────────────────────────

def build_enriched_context(schema_profile: dict, auto_semantic: dict) -> str:
    """Build the SQL-generator context string using the TABLE NAME (not file path)."""
    table_name = schema_profile["table_name"]
    table_desc = auto_semantic.get("table_description", "")
    sem_cols = auto_semantic.get("columns", {})
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
        sem = sem_cols.get(col_name, {})
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

    if metrics:
        context += f"\n-- METRIC columns (SUM/AVG/COUNT): {', '.join(metrics)}\n"
    if dimensions:
        context += f"-- DIMENSION columns (GROUP BY / WHERE): {', '.join(dimensions)}\n"
    if dates:
        context += f"-- DATE columns (time filters/trends): {', '.join(dates)}\n"

    if auto_semantic.get("suggested_metrics"):
        context += "\n-- Useful metrics:\n"
        for m in auto_semantic["suggested_metrics"]:
            context += f"--   {m}\n"

    if auto_semantic.get("column_aliases"):
        context += "\n-- Column aliases (user term → column name):\n"
        for alias, actual in auto_semantic["column_aliases"].items():
            context += f'--   "{alias}" means column "{actual}"\n'

    return context


# ── Main class ────────────────────────────────────────────────────────────────

class AutoSemantic:
    """Profile and enrich DuckDB tables with semantic metadata."""

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con
        self._cache: Dict[str, dict] = {}  # table_name -> enriched profile

    def profile_and_enrich(
        self,
        table_name: str,
        skip_llm_enrichment: bool = False,
        defer_suggested_questions: bool = False,
    ) -> dict:
        """Full pipeline: profile → enrich → verified queries → context string.

        Fast upload mode can skip LLM enrichment and/or defer suggestion generation.
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
            print("[auto_semantic] Fast mode: skipping LLM enrichment (fallback only)")
            auto_semantic = _build_fallback_semantic(schema_profile)
        else:
            print("[auto_semantic] LLM enrichment…")
            try:
                auto_semantic = _generate_semantic_enrichment(schema_profile)
            except Exception as e:
                print(f"[auto_semantic] LLM failed ({e}), using fallback")
                auto_semantic = _build_fallback_semantic(schema_profile)

        print("[auto_semantic] Generating verified queries…")
        try:
            verified_queries = generate_verified_queries(
                self.con, schema_profile, auto_semantic
            )
        except Exception as e:
            print(f"[auto_semantic] verified queries failed ({e})")
            verified_queries = []

        print("[auto_semantic] Building enriched context…")
        try:
            enriched_context = build_enriched_context(schema_profile, auto_semantic)
        except Exception as e:
            print(f"[auto_semantic] context build failed ({e})")
            enriched_context = (
                f'-- Table: "{table_name}"\n'
                f"-- Total rows: {schema_profile['total_rows']}\n"
            )

        col_names = ", ".join(list(schema_profile["columns"].keys())[:10])
        schema_summary = (
            f"Table: {table_name}, "
            f"{schema_profile['total_rows']} rows, "
            f"columns: {col_names}"
        )

        # Build suggested questions from auto_semantic + verified queries,
        # unless deferred to keep upload latency low.
        suggested_qs = []
        if not defer_suggested_questions:
            suggested_qs = auto_semantic.get("suggested_questions", [])
            if not suggested_qs:
                suggested_qs = [vq["question"] for vq in verified_queries[:5]]

        result = {
            "schema_profile": schema_profile,
            "auto_semantic": auto_semantic,
            "verified_queries": verified_queries,
            "enriched_context": enriched_context,
            "schema_summary": schema_summary,
            "suggested_questions": suggested_qs[:5],
            # Legacy key used by server.py
            "table_name": table_name,
        }
        self._cache[table_name] = result
        print(f"[auto_semantic] Done: {table_name!r}")
        return result

    def profile_all(self, table_names: List[str]) -> Dict[str, dict]:
        """Profile multiple tables. Returns {table_name: profile}."""
        return {t: self.profile_and_enrich(t) for t in table_names}

    def get_combined_context(self, table_names: List[str]) -> str:
        """Combined enriched context for all tables (for multi-file queries)."""
        parts = []
        for t in table_names:
            profile = self.profile_and_enrich(t)
            parts.append(profile["enriched_context"])
        return "\n\n".join(parts)

    def get_combined_schema_summary(self, table_names: List[str]) -> str:
        parts = []
        for t in table_names:
            profile = self.profile_and_enrich(t)
            parts.append(profile["schema_summary"])
        return "; ".join(parts)

    def clear(self):
        self._cache.clear()
