from __future__ import annotations
"""
Auto-generate semantic context for uploaded files.
Profile once on upload, cache in session state.
"""

import json
from pathlib import Path
from app.core.groq_client import call_llm


def _normalize_llm_response(result: dict) -> dict:
    """
    Normalize LLM response to handle cases where the model returns
    'columns' as a list instead of a dict.

    Expected: {"columns": {"col1": {"description": "..."}, ...}}
    Actual sometimes: {"columns": [{"name": "col1", "description": "..."}, ...]}
    """
    columns = result.get("columns", {})

    if isinstance(columns, list):
        print(f"[auto_semantic] WARNING: LLM returned columns as list, converting to dict. Raw: {json.dumps(columns[:2])}")
        col_dict = {}
        for item in columns:
            if isinstance(item, dict):
                # Try common key names for the column name
                name = (
                    item.get("name")
                    or item.get("column_name")
                    or item.get("column")
                    or item.get("col")
                )
                if name:
                    col_dict[name] = {k: v for k, v in item.items() if k not in ("name", "column_name", "column", "col")}
        result["columns"] = col_dict
    elif not isinstance(columns, dict):
        print(f"[auto_semantic] WARNING: LLM returned columns as unexpected type {type(columns)}, defaulting to empty dict.")
        result["columns"] = {}

    # Normalize column_aliases — should be a dict, sometimes comes as list or None
    aliases = result.get("column_aliases", {})
    if isinstance(aliases, list):
        print(f"[auto_semantic] WARNING: column_aliases is a list, converting.")
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


def _format_columns_with_stats(columns: dict) -> str:
    lines = []
    for col_name, info in columns.items():
        line = f"  {col_name} ({info['type']})"
        if "sample_values" in info:
            vals = info["sample_values"][:10]
            line += f"\n    Sample values: {vals}"
            line += f"\n    Distinct count: {info.get('distinct_count', '?')}"
        if "min" in info:
            line += f"\n    Range: {info['min']} to {info['max']}, Avg: {info['avg']}"
        if "min_date" in info:
            line += f"\n    Date range: {info['min_date']} to {info['max_date']}"
        if info.get("null_count", 0) > 0:
            line += f"\n    Nulls: {info['null_count']}"
        lines.append(line)
    return "\n".join(lines)


def _generate_auto_semantic(schema_profile: dict) -> dict:
    """One LLM call to enrich schema with descriptions, metrics, aliases."""
    col_stats = _format_columns_with_stats(schema_profile["columns"])
    sample_str = str(schema_profile["sample_data"][:5])

    # List column names explicitly so the LLM uses exact keys
    col_names_list = list(schema_profile["columns"].keys())

    prompt = f"""You are a data analyst examining a dataset you've never seen before. Be SPECIFIC.

BAD column description: "This column contains text data"
GOOD column description: "Player name — the full name of the cricket player (e.g., 'Virat Kohli')"

BAD column description: "Numeric value"
GOOD column description: "Runs scored — total runs by the batsman in this innings, ranges 0–200+"

Table: {schema_profile['table_name']}
Total rows: {schema_profile['total_rows']}

Columns:
{col_stats}

Sample data (first 5 rows):
{sample_str}

For each column, provide:
- What it represents in real-world terms (be specific, not generic)
- Whether it's a thing to count/sum (metric) or a thing to group by (dimension)
- For text columns: what kind of values it contains (names? categories? codes?)
- For numeric columns: what unit it's in and what range is typical

Return a JSON object with EXACTLY these keys:
1. "table_description": one sentence describing what this data is about (specific, not generic)
2. "columns": a JSON OBJECT (NOT an array/list) where each KEY is a column name and the VALUE is an object with:
   - "description": specific real-world description of what this column represents
   - "is_metric": true if measurable numeric value (revenue, count, amount, price, quantity, score, runs, wickets)
   - "is_dimension": true if categorical/groupable (region, category, name, status, type, team, player)
   - "is_date": true if date/time field
   IMPORTANT: "columns" MUST be a JSON object like {{"col_name": {{...}}, "col_name2": {{...}}}}
   NOT a list/array like [{{"name": "col_name", ...}}]
   Use EXACTLY these column names as keys: {col_names_list}
3. "suggested_metrics": list of useful aggregation strings (e.g., "SUM(amount) as total_revenue")
4. "suggested_questions": list of 5 example questions a user might ask about this data
5. "column_aliases": a JSON OBJECT mapping common user terms to actual column names
   e.g., {{"revenue": "amount", "sales": "amount"}}
   MUST be a JSON object, NOT a list.

Be precise. Only mark is_metric=true for numeric columns. Only mark is_date=true for date/timestamp columns."""

    result = call_llm(
        model_key="smart",
        system_prompt="You are a data analyst. Respond with valid JSON only. The 'columns' field MUST be a JSON object with column names as keys, never a list.",
        user_message=prompt,
        temperature=0.0,
        json_mode=True,
    )

    print(f"[auto_semantic] Raw LLM response type check — columns type: {type(result.get('columns'))}")
    if isinstance(result.get("columns"), list):
        print(f"[auto_semantic] columns (first item): {json.dumps(result['columns'][0]) if result['columns'] else '[]'}")
    elif isinstance(result.get("columns"), dict):
        first_key = next(iter(result["columns"]), None)
        print(f"[auto_semantic] columns (first key): {first_key}")

    result = _normalize_llm_response(result)
    return result


def _generate_auto_verified_queries(filepath: str, schema_profile: dict, auto_semantic: dict) -> list:
    """Generate basic verified queries for any dataset."""
    read_fn = schema_profile["read_fn"]
    queries = []

    # 1. Row count
    queries.append({
        "question": "How many rows are in the dataset?",
        "sql": f"SELECT COUNT(*) as total_rows FROM {read_fn}",
    })

    sem_cols = auto_semantic.get("columns", {})
    if not isinstance(sem_cols, dict):
        print(f"[auto_semantic] _generate_auto_verified_queries: sem_cols is {type(sem_cols)}, forcing empty dict")
        sem_cols = {}

    # 2. SUM of first metric
    for col_name, col_info in sem_cols.items():
        if col_info.get("is_metric") and col_name in schema_profile["columns"]:
            desc = col_info.get("description", col_name)
            queries.append({
                "question": f"What is the total {desc}?",
                "sql": f'SELECT SUM("{col_name}") as total FROM {read_fn}',
            })
            break

    # 3. GROUP BY first dimension + first metric
    metric_col = next(
        (c for c, i in sem_cols.items() if i.get("is_metric") and c in schema_profile["columns"]),
        None,
    )
    for col_name, col_info in sem_cols.items():
        if col_info.get("is_dimension") and col_name in schema_profile["columns"]:
            if metric_col:
                queries.append({
                    "question": f"Breakdown by {col_name}",
                    "sql": (
                        f'SELECT "{col_name}", SUM("{metric_col}") as total '
                        f"FROM {read_fn} "
                        f'GROUP BY "{col_name}" ORDER BY total DESC'
                    ),
                })
            break

    # 4. Date trend
    for col_name, col_info in sem_cols.items():
        if col_info.get("is_date") and col_name in schema_profile["columns"]:
            agg = f'SUM("{metric_col}")' if metric_col else "COUNT(*)"
            queries.append({
                "question": "Trend over time",
                "sql": (
                    f"SELECT date_trunc('month', \"{col_name}\") as month, "
                    f"{agg} as total FROM {read_fn} "
                    f'GROUP BY month ORDER BY month'
                ),
            })
            break

    # 5. Top 10
    queries.append({
        "question": "Show top 10 rows",
        "sql": f"SELECT * FROM {read_fn} LIMIT 10",
    })

    return queries


def _build_enriched_context(schema_profile: dict, auto_semantic: dict) -> str:
    """Build the context string for SQL generator prompt."""
    read_fn = schema_profile["read_fn"]
    table_desc = auto_semantic.get("table_description", "")
    sem_cols = auto_semantic.get("columns", {})

    # Safety: ensure sem_cols is a dict (normalizer should have fixed this, but double-check)
    if not isinstance(sem_cols, dict):
        print(f"[auto_semantic] _build_enriched_context: sem_cols is {type(sem_cols)}, forcing empty dict")
        sem_cols = {}

    context = (
        f"-- Dataset: {table_desc}\n"
        f"-- Source: {read_fn}\n"
        f"-- Total rows: {schema_profile['total_rows']}\n"
        f"-- Query using: SELECT ... FROM {read_fn}\n\n"
        "-- Schema:\n"
    )

    metrics = []
    dimensions = []
    dates = []

    for col_name, col_info in schema_profile["columns"].items():
        sem = sem_cols.get(col_name, {})
        desc = sem.get("description", "")
        line = f'-- "{col_name}" ({col_info["type"]}): {desc}'

        if "sample_values" in col_info:
            vals = col_info["sample_values"][:10]
            line += f"\n--   Values: {vals}"
        if "min" in col_info:
            line += f"\n--   Range: {col_info['min']} to {col_info['max']}, Avg: {col_info['avg']}"
        if "min_date" in col_info:
            line += f"\n--   Date range: {col_info['min_date']} to {col_info['max_date']}"
        if col_info.get("null_count", 0) > 0:
            line += f"\n--   Contains {col_info['null_count']} NULL values"

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
        context += f"-- DATE columns (time filters): {', '.join(dates)}\n"

    if auto_semantic.get("suggested_metrics"):
        context += "\n-- Useful metrics:\n"
        for m in auto_semantic["suggested_metrics"]:
            context += f"--   {m}\n"

    if auto_semantic.get("column_aliases"):
        context += "\n-- Column aliases:\n"
        for alias, actual in auto_semantic["column_aliases"].items():
            context += f'--   "{alias}" means column "{actual}"\n'

    return context


def _detect_relationships(file_profiles: dict) -> list:
    """Find common column names across files (potential join keys)."""
    relationships = []
    files = list(file_profiles.keys())
    for i, f1 in enumerate(files):
        for f2 in files[i + 1:]:
            cols1 = set(file_profiles[f1]["columns"].keys())
            cols2 = set(file_profiles[f2]["columns"].keys())
            common = cols1 & cols2
            for col in common:
                relationships.append({
                    "from_file": f1,
                    "to_file": f2,
                    "column": col,
                    "join_hint": (
                        f'"{file_profiles[f1]["read_fn"]}" t1 '
                        f'JOIN "{file_profiles[f2]["read_fn"]}" t2 '
                        f'ON t1."{col}" = t2."{col}"'
                    ),
                })
    return relationships


class AutoSemantic:
    def __init__(self, duckdb_engine):
        self.engine = duckdb_engine
        self._cache = {}  # filepath -> enriched profile

    def profile_and_enrich(self, filepath: str) -> dict:
        """Full pipeline: profile + LLM enrich + verified queries + context string."""
        if filepath in self._cache:
            return self._cache[filepath]

        # Step 1: DuckDB profiling
        print(f"[auto_semantic] Step 1: profiling {filepath}")
        schema_profile = self.engine.register_file(filepath)
        print(f"[auto_semantic] Step 1 done: {schema_profile['total_rows']} rows, {len(schema_profile['columns'])} columns")

        # Step 2: LLM semantic enrichment
        print(f"[auto_semantic] Step 2: LLM enrichment")
        try:
            auto_semantic = _generate_auto_semantic(schema_profile)
        except Exception as e:
            print(f"[auto_semantic] Step 2 FAILED: {e}")
            raise RuntimeError(f"LLM enrichment failed: {e}") from e

        cols_type = type(auto_semantic.get("columns"))
        print(f"[auto_semantic] Step 2 done: columns type={cols_type}, keys={list(auto_semantic.get('columns', {}).keys())[:5]}")

        # Step 3: Auto verified queries
        print(f"[auto_semantic] Step 3: generating verified queries")
        try:
            verified_queries = _generate_auto_verified_queries(filepath, schema_profile, auto_semantic)
        except Exception as e:
            print(f"[auto_semantic] Step 3 FAILED: {e}, columns={auto_semantic.get('columns')}")
            raise RuntimeError(f"Verified query generation failed: {e}") from e

        # Step 4: Build enriched context
        print(f"[auto_semantic] Step 4: building enriched context")
        try:
            enriched_context = _build_enriched_context(schema_profile, auto_semantic)
        except Exception as e:
            print(f"[auto_semantic] Step 4 FAILED: {e}, sem_cols type={type(auto_semantic.get('columns'))}")
            raise RuntimeError(f"Context building failed: {e}") from e

        col_names = ", ".join(list(schema_profile["columns"].keys())[:10])
        schema_summary = (
            f"File: {Path(filepath).name}, "
            f"{schema_profile['total_rows']} rows, "
            f"columns: {col_names}"
        )

        result = {
            "schema_profile": schema_profile,
            "auto_semantic": auto_semantic,
            "verified_queries": verified_queries,
            "enriched_context": enriched_context,
            "schema_summary": schema_summary,
        }
        self._cache[filepath] = result
        print(f"[auto_semantic] profile_and_enrich complete for {Path(filepath).name}")
        return result

    def get_schema_summary(self, filepath: str) -> str:
        return self.profile_and_enrich(filepath)["schema_summary"]

    def get_enriched_context(self, filepath: str) -> str:
        return self.profile_and_enrich(filepath)["enriched_context"]

    def get_verified_queries(self, filepath: str) -> list:
        return self.profile_and_enrich(filepath)["verified_queries"]

    def get_relationships(self, filepaths: list) -> list:
        profiles = {fp: self.engine.files[fp] for fp in filepaths if fp in self.engine.files}
        return _detect_relationships(profiles)
