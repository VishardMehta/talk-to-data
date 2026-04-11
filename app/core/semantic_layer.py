"""
Semantic Layer — loads config/semantic_layer.yaml and provides
structured access to table schemas, relationships, metrics, and filters.

Used by SQL generator to build accurate, context-rich prompts.
"""
from __future__ import annotations

import os
import yaml

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_PATH = os.path.join(_BASE_DIR, "config", "semantic_layer.yaml")


class SemanticLayer:
    """Loads and queries the semantic layer YAML configuration."""

    def __init__(self, config_path: str = _CONFIG_PATH):
        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)
        
        self.models = self._config.get("models", {})
        self.relationships = self._config.get("relationships", {})
        self.metrics = self._config.get("metrics", {})
        self.filters = self._config.get("filters", {})
        self.db_path = self._config.get("database", "data/demo.db")

    # ── Schema access ────────────────────────────────────────────────────

    def get_all_valid_tables(self) -> list[str]:
        """Return list of all table names."""
        return list(self.models.keys())

    def get_all_valid_columns(self, table: str) -> list[str]:
        """Return list of column names for a given table."""
        model = self.models.get(table, {})
        return list(model.get("columns", {}).keys())

    def get_table_description(self, table: str) -> str:
        """Return the description of a table."""
        return self.models.get(table, {}).get("description", "")

    def get_schema_summary(self) -> str:
        """Short summary of all tables — used by router agent."""
        lines = ["Available tables:"]
        for name, model in self.models.items():
            desc = model.get("description", "")
            cols = ", ".join(model.get("columns", {}).keys())
            lines.append(f"  - {name}: {desc} (columns: {cols})")
        
        lines.append("\nAvailable document collections:")
        lines.append("  - complaints: Customer complaint text documents with category, region, date")
        lines.append("  - feedback: Customer feedback text documents with sentiment, region, date")
        
        return "\n".join(lines)

    # ── Full context for SQL generator ───────────────────────────────────

    def get_full_context(self, table_names: list[str] = None) -> str:
        """Detailed context for specific tables — used by SQL generator."""
        if table_names is None:
            table_names = self.get_all_valid_tables()
        
        return self.generate_ddl_with_context(table_names)

    def generate_ddl_with_context(self, table_names: list[str] = None) -> str:
        """
        Generate CREATE TABLE statements enriched with descriptions,
        sample values, relationships, metrics, and filters for LLM prompt.
        """
        if table_names is None:
            table_names = self.get_all_valid_tables()
        
        sections = []
        
        # ── Table DDLs ──
        for table_name in table_names:
            model = self.models.get(table_name)
            if not model:
                continue
            
            lines = []
            lines.append(f"-- Table: {table_name}")
            lines.append(f"-- Description: {model.get('description', '')}")
            lines.append(f"CREATE TABLE {table_name} (")
            
            columns = model.get("columns", {})
            col_lines = []
            for col_name, col_info in columns.items():
                col_type = col_info.get("type", "TEXT")
                col_desc = col_info.get("description", "")
                sample = col_info.get("sample_values", None)
                
                comment = f"-- {col_desc}"
                if sample:
                    comment += f". Values: {', '.join(str(v) for v in sample)}"
                
                pk = " PRIMARY KEY" if col_name.endswith("_id") and col_name == f"{table_name[:-1]}_id" else ""
                # Handle special case for primary keys
                if col_name == "order_id" and table_name == "orders":
                    pk = " PRIMARY KEY"
                elif col_name == "customer_id" and table_name == "customers":
                    pk = " PRIMARY KEY"
                elif col_name == "product_id" and table_name == "products":
                    pk = " PRIMARY KEY"
                elif col_name == "complaint_id" and table_name == "complaints":
                    pk = " PRIMARY KEY"
                else:
                    pk = ""
                
                col_lines.append(f"    {col_name} {col_type}{pk},  {comment}")
            
            # Remove trailing comma from last column
            if col_lines:
                col_lines[-1] = col_lines[-1].replace(",  --", "   --")
            
            lines.extend(col_lines)
            lines.append(");")
            sections.append("\n".join(lines))
        
        # ── Relationships ──
        rel_lines = ["\n-- Relationships:"]
        for rel_name, rel_info in self.relationships.items():
            from_t = rel_info.get("from_table", "")
            to_t = rel_info.get("to_table", "")
            if from_t in table_names or to_t in table_names:
                join_sql = rel_info.get("join_sql", "")
                desc = rel_info.get("description", "")
                rel_lines.append(f"-- JOIN: {join_sql}  ({desc})")
        
        if len(rel_lines) > 1:
            sections.append("\n".join(rel_lines))
        
        # ── Metrics ──
        metric_lines = ["\n-- Pre-defined metrics:"]
        for metric_name, metric_info in self.metrics.items():
            tables = metric_info.get("tables", [])
            if any(t in table_names for t in tables):
                sql = metric_info.get("sql", "")
                aliases = metric_info.get("aliases", [])
                alias_str = ", ".join(aliases) if aliases else ""
                metric_lines.append(f"-- {metric_name} = {sql} [aliases: {alias_str}]")
        
        if len(metric_lines) > 1:
            sections.append("\n".join(metric_lines))
        
        # ── Filters ──
        filter_lines = ["\n-- Pre-defined filters:"]
        for filter_name, filter_info in self.filters.items():
            sql = filter_info.get("sql", "")
            aliases = filter_info.get("aliases", [])
            alias_str = ", ".join(aliases) if aliases else ""
            filter_lines.append(f"-- {filter_name} = {sql} [aliases: {alias_str}]")
        
        if len(filter_lines) > 1:
            sections.append("\n".join(filter_lines))
        
        return "\n\n".join(sections)

    # ── Metric / Filter resolution ───────────────────────────────────────

    def get_metric_definition(self, alias: str) -> dict | None:
        """Resolve a metric alias (e.g., 'revenue') to its SQL definition."""
        alias_lower = alias.lower().strip()
        
        for metric_name, metric_info in self.metrics.items():
            if metric_name == alias_lower:
                return metric_info
            if alias_lower in [a.lower() for a in metric_info.get("aliases", [])]:
                return metric_info
        
        return None

    def get_filter_sql(self, alias: str) -> str | None:
        """Resolve a filter alias (e.g., 'high value') to its SQL WHERE clause."""
        alias_lower = alias.lower().strip()
        
        for filter_name, filter_info in self.filters.items():
            if filter_name == alias_lower:
                return filter_info.get("sql")
            if alias_lower in [a.lower() for a in filter_info.get("aliases", [])]:
                return filter_info.get("sql")
        
        return None

    # ── Relationship access ──────────────────────────────────────────────

    def get_relationship(self, table1: str, table2: str) -> dict | None:
        """Return the relationship between two tables, if one exists."""
        for rel_name, rel_info in self.relationships.items():
            from_t = rel_info.get("from_table")
            to_t = rel_info.get("to_table")
            if (from_t == table1 and to_t == table2) or \
               (from_t == table2 and to_t == table1):
                return rel_info
        return None

    def get_join_sql(self, table1: str, table2: str) -> str | None:
        """Get the JOIN SQL for two tables."""
        rel = self.get_relationship(table1, table2)
        if rel:
            return rel.get("join_sql")
        return None


# ── Module-level instance ─────────────────────────────────────────────────────

_instance = None

def get_semantic_layer(config_path: str = _CONFIG_PATH) -> SemanticLayer:
    """Get or create the singleton SemanticLayer instance."""
    global _instance
    if _instance is None:
        _instance = SemanticLayer(config_path)
    return _instance
