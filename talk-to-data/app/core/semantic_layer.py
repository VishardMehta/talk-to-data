from __future__ import annotations
import os
import yaml
from pathlib import Path


def _load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class SemanticLayer:
    def __init__(self, config_path: str = None):
        if config_path is None:
            base = Path(__file__).resolve().parent.parent.parent
            config_path = str(base / "config" / "semantic_layer.yaml")
        self._cfg = _load_yaml(config_path)
        self._models = self._cfg.get("models", {})
        self._relationships = self._cfg.get("relationships", {})
        self._metrics = self._cfg.get("metrics", {})
        self._filters = self._cfg.get("filters", {})

    # ------------------------------------------------------------------
    # Basic accessors
    # ------------------------------------------------------------------

    def get_all_valid_tables(self) -> list[str]:
        return list(self._models.keys())

    def get_all_valid_columns(self, table: str) -> list[str]:
        model = self._models.get(table, {})
        return list(model.get("columns", {}).keys())

    def get_database_path(self) -> str:
        return self._cfg.get("database", "data/demo.db")

    # ------------------------------------------------------------------
    # Schema summary (short — for router)
    # ------------------------------------------------------------------

    def get_schema_summary(self) -> str:
        lines = ["Available tables:"]
        for name, model in self._models.items():
            lines.append(f"  - {name}: {model.get('description', '')}")
        lines.append("\nAvailable document collections:")
        lines.append("  - complaints (free-text complaint documents, for semantic search)")
        lines.append("  - feedback (free-text customer feedback, for semantic search)")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Metric / filter resolution
    # ------------------------------------------------------------------

    def get_metric_definition(self, alias: str) -> str | None:
        alias_lower = alias.lower()
        for name, m in self._metrics.items():
            if alias_lower == name.lower():
                return m["sql"]
            if alias_lower in [a.lower() for a in m.get("aliases", [])]:
                return m["sql"]
        return None

    def get_filter_sql(self, alias: str) -> str | None:
        alias_lower = alias.lower()
        for name, f in self._filters.items():
            if alias_lower == name.lower():
                return f["sql"]
            if alias_lower in [a.lower() for a in f.get("aliases", [])]:
                return f["sql"]
        return None

    def get_relationship(self, table1: str, table2: str) -> str | None:
        for rel in self._relationships.values():
            tables = {rel["from_table"], rel["to_table"]}
            if tables == {table1, table2}:
                return rel["join_sql"]
        return None

    # ------------------------------------------------------------------
    # Enriched DDL for SQL generator prompt
    # ------------------------------------------------------------------

    def generate_ddl_with_context(self, table_names: list[str] = None) -> str:
        if table_names is None:
            table_names = self.get_all_valid_tables()

        # Always include all tables so the LLM has full context
        all_tables = self.get_all_valid_tables()
        table_names = list(dict.fromkeys(list(table_names) + all_tables))

        parts = []
        for tname in table_names:
            model = self._models.get(tname)
            if not model:
                continue
            lines = [
                f"-- Table: {tname}",
                f"-- Description: {model.get('description', '')}",
                f"CREATE TABLE {tname} (",
            ]
            cols = model.get("columns", {})
            col_lines = []
            for cname, cinfo in cols.items():
                comment = cinfo.get("description", "")
                samples = cinfo.get("sample_values", [])
                if samples:
                    comment += f". Values: {', '.join(str(s) for s in samples)}"
                col_lines.append(f"    {cname} {cinfo['type']}  -- {comment}")
            lines.append(",\n".join(col_lines))
            lines.append(");\n")
            parts.append("\n".join(lines))

        # Relationships
        rel_lines = ["-- Relationships (use these for JOINs):"]
        for rel in self._relationships.values():
            rel_lines.append(
                f"-- {rel['from_table']}.{rel['from_column']} -> "
                f"{rel['to_table']}.{rel['to_column']} ({rel['type']})"
            )
            rel_lines.append(f"--   JOIN condition: {rel['join_sql']}")
        parts.append("\n".join(rel_lines) + "\n")

        # Pre-defined metrics
        metric_lines = ["-- Pre-defined metrics (use these SQL expressions exactly):"]
        for mname, m in self._metrics.items():
            aliases = ", ".join(m.get("aliases", []))
            metric_lines.append(f"-- {mname} = {m['sql']}  [aliases: {aliases}]")
        parts.append("\n".join(metric_lines) + "\n")

        # Pre-defined filters
        filter_lines = ["-- Pre-defined filters (use these WHERE conditions exactly):"]
        for fname, f in self._filters.items():
            aliases = ", ".join(f.get("aliases", []))
            filter_lines.append(f"-- {fname} = {f['sql']}  [aliases: {aliases}]")
        parts.append("\n".join(filter_lines))

        return "\n".join(parts)


# Module-level singleton (lazy-loaded)
_instance: SemanticLayer | None = None


def get_semantic_layer() -> SemanticLayer:
    global _instance
    if _instance is None:
        _instance = SemanticLayer()
    return _instance
