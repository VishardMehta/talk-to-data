"""
Agent 0.5 - Dataset Metadata Responder.

This agent intercepts dataset-description questions and answers directly from
already-loaded DuckDB metadata and upload-time schema profiles.

No LLM calls are made in this module.
"""
from __future__ import annotations

from typing import Any

import duckdb


_DATASET_DESCRIPTION_PATTERNS = [
    "what is this dataset",
    "what is this data",
    "what does this dataset",
    "what does this data",
    "tell me about this dataset",
    "tell me about this data",
    "tell me about the data",
    "describe this dataset",
    "describe this data",
    "describe the data",
    "what data do i have",
    "what data is this",
    "what's in this dataset",
    "what's in this data",
    "what's this dataset",
    "what's this data about",
    "what is this about",
    "what are the columns",
    "what columns",
    "show me the schema",
    "what tables",
    "what fields",
    "explain the data",
    "overview of the data",
    "data overview",
    "dataset overview",
    "what am i looking at",
    "what did i upload",
]

_NUMERIC_TYPES = {
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "UTINYINT",
    "USMALLINT",
    "UINTEGER",
    "UBIGINT",
    "FLOAT",
    "DOUBLE",
    "REAL",
    "DECIMAL",
    "NUMERIC",
}
_DATE_TYPES = {
    "DATE",
    "TIMESTAMP",
    "TIMESTAMPTZ",
    "TIMESTAMP_S",
    "TIMESTAMP_MS",
    "TIMESTAMP_NS",
    "TIME",
}
_TEXT_TYPES = {"VARCHAR", "TEXT", "CHAR", "STRING"}


def _base_type(type_name: str) -> str:
    return (type_name or "").upper().split("(")[0].strip()


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _humanize(name: str) -> str:
    return str(name).replace("_", " ").strip().title()


def is_dataset_description_query(question: str) -> bool:
    """Return True when the user asks what the uploaded dataset contains."""
    q = (question or "").lower().strip()
    if not q:
        return False
    return any(pattern in q for pattern in _DATASET_DESCRIPTION_PATTERNS)


def _get_table_columns(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    table_schemas: dict[str, list[dict[str, Any]]] | None,
) -> list[dict[str, str]]:
    cached = (table_schemas or {}).get(table_name)
    if cached:
        return [
            {"name": str(c.get("name", "")), "type": str(c.get("type", ""))}
            for c in cached
            if c.get("name")
        ]

    rows = con.execute(f"DESCRIBE {_quote_ident(table_name)}").fetchall()
    return [{"name": str(r[0]), "type": str(r[1])} for r in rows]


def generate_dataset_description(
    con: duckdb.DuckDBPyConnection,
    tables: list[str],
    table_schemas: dict[str, list[dict[str, Any]]] | None,
    profiles: dict[str, dict[str, Any]] | None = None,
    yaml_data: dict[str, Any] | None = None,
) -> dict:
    """
    Build a rich dataset description from metadata and schema profiles.

    This path avoids all external model/network dependency.
    """
    if not tables:
        return {
            "answer": "No dataset is loaded yet. Please upload a file first.",
            "results": None,
            "sql": None,
            "confidence": 10,
            "follow_ups": [],
            "pattern": "SUMMARY",
            "route": {
                "intent": "STRUCTURED",
                "pattern": "SUMMARY",
                "reasoning": "Dataset metadata fast-path",
            },
        }

    profiles = profiles or {}
    parts: list[str] = []
    all_follow_ups: list[str] = []

    db_desc = (((yaml_data or {}).get("database") or {}).get("description") or "").strip()
    if db_desc and db_desc != "Uploaded dataset":
        parts.append(db_desc)

    for table_name in tables:
        profile = profiles.get(table_name, {})
        schema_profile = profile.get("schema_profile", {}) if isinstance(profile, dict) else {}
        auto_semantic = profile.get("auto_semantic", {}) if isinstance(profile, dict) else {}
        semantic_cols = auto_semantic.get("columns", {}) if isinstance(auto_semantic, dict) else {}

        row_count = schema_profile.get("total_rows")
        if not isinstance(row_count, int):
            row_count = con.execute(
                f"SELECT COUNT(*) FROM {_quote_ident(table_name)}"
            ).fetchone()[0]

        columns = _get_table_columns(con, table_name, table_schemas)

        numeric_cols: list[str] = []
        text_cols: list[str] = []
        date_cols: list[str] = []
        col_details: list[str] = []

        schema_columns = schema_profile.get("columns", {}) if isinstance(schema_profile, dict) else {}

        for col in columns:
            col_name = col["name"]
            col_type = col["type"]
            base_type = _base_type(col_type)
            clean_name = _humanize(col_name)
            col_profile = schema_columns.get(col_name, {}) if isinstance(schema_columns, dict) else {}
            semantic_info = semantic_cols.get(col_name, {}) if isinstance(semantic_cols, dict) else {}
            semantic_desc = str(semantic_info.get("description", "")).strip()

            if base_type in _NUMERIC_TYPES:
                if col_name.lower() == "id" or col_name.lower().endswith("_id"):
                    detail = f"{clean_name} (ID)"
                else:
                    numeric_cols.append(clean_name)
                    if "min" in col_profile and "max" in col_profile:
                        detail = (
                            f"{clean_name} (numeric, range: "
                            f"{col_profile.get('min')} to {col_profile.get('max')})"
                        )
                    else:
                        detail = f"{clean_name} (numeric)"
            elif base_type in _DATE_TYPES:
                date_cols.append(clean_name)
                min_date = col_profile.get("min_date")
                max_date = col_profile.get("max_date")
                if min_date and max_date:
                    detail = f"{clean_name} (dates from {min_date} to {max_date})"
                else:
                    detail = f"{clean_name} (date/time)"
            elif base_type in _TEXT_TYPES:
                text_cols.append(clean_name)
                distinct = col_profile.get("distinct_count")
                samples = col_profile.get("sample_values") or []
                sample_text = ", ".join(str(v) for v in samples[:8])
                if isinstance(distinct, int) and distinct <= 20 and sample_text:
                    detail = f"{clean_name} ({distinct} categories: {sample_text})"
                elif isinstance(distinct, int) and sample_text:
                    detail = f"{clean_name} ({distinct} unique values, e.g.: {sample_text})"
                elif isinstance(distinct, int):
                    detail = f"{clean_name} ({distinct} unique values)"
                else:
                    detail = f"{clean_name} (text)"
            else:
                detail = f"{clean_name} ({col_type})"

            if semantic_desc and semantic_desc.lower() != clean_name.lower():
                detail += f" - {semantic_desc}"
            col_details.append(detail)

        display_name = _humanize(table_name)
        table_desc = f"**{display_name}** - {row_count:,} rows, {len(columns)} columns"

        table_summary = str(auto_semantic.get("table_description", "")).strip()
        if table_summary and table_summary != f"Dataset with {row_count} rows":
            table_desc += f"\n{table_summary}"

        cryptic_cols = [
            c["name"]
            for c in columns
            if len(c["name"]) <= 3 or c["name"].startswith("col") or c["name"].startswith("c_")
        ]
        if columns and len(cryptic_cols) > len(columns) * 0.5:
            table_desc += "\nNote: many column names are abbreviated; semantic descriptions are included where available."

        table_desc += "\nColumns:"
        for detail in col_details:
            table_desc += f"\n  - {detail}"

        parts.append(table_desc)

        if numeric_cols:
            all_follow_ups.append(f"What is the total {numeric_cols[0].lower()}?")
        if text_cols and numeric_cols:
            all_follow_ups.append(f"{numeric_cols[0]} by {text_cols[0].lower()}")
        if date_cols and numeric_cols:
            all_follow_ups.append(f"How has {numeric_cols[0].lower()} changed over time?")
        if text_cols:
            all_follow_ups.append(f"What is the breakdown by {text_cols[0].lower()}?")
        all_follow_ups.append("How many records are there?")

    answer = "\n\n".join(parts)
    if len(tables) > 1:
        answer = f"You have uploaded {len(tables)} tables:\n\n" + answer

    deduped_follow_ups = list(dict.fromkeys(all_follow_ups))[:5]

    return {
        "answer": answer,
        "results": None,
        "sql": None,
        "data": None,
        "chart": None,
        "confidence": 10,
        "follow_ups": deduped_follow_ups,
        "pattern": "SUMMARY",
        "route": {
            "intent": "STRUCTURED",
            "pattern": "SUMMARY",
            "reasoning": "Dataset metadata fast-path",
        },
    }
