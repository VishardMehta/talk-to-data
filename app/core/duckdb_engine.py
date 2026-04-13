"""
DuckDB engine for upload mode.
Handles CSV/Parquet file profiling and query execution.
"""

import os
import duckdb
from pathlib import Path


class DuckDBEngine:
    def __init__(self):
        self.conn = duckdb.connect()  # in-memory
        self.files = {}  # filepath -> schema_profile

    def _read_fn(self, filepath: str) -> str:
        ext = Path(filepath).suffix.lower()
        fp = filepath.replace("\\", "/")
        if ext == ".parquet":
            return f"read_parquet('{fp}')"
        if ext == ".json":
            return f"read_json_auto('{fp}')"  # fallback read_fn for context strings
        return f"read_csv_auto('{fp}')"

    def _load_json_robust(self, filepath: str) -> str:
        """Bug 2 fix: multi-strategy JSON loading with pandas fallback."""
        fp = filepath.replace("\\", "/")
        table_name = Path(filepath).stem.replace("-", "_").replace(" ", "_")

        strategies = [
            f"""CREATE OR REPLACE TABLE \"{table_name}\" AS
                SELECT * FROM read_json_auto('{fp}',
                    maximum_object_size=16777216, sample_size=-1, format='auto')""",
            f"""CREATE OR REPLACE TABLE \"{table_name}\" AS
                SELECT * FROM read_json_auto('{fp}',
                    maximum_object_size=16777216, records='true', sample_size=-1)""",
            f"""CREATE OR REPLACE TABLE \"{table_name}\" AS
                SELECT * FROM read_ndjson_auto('{fp}')""",
        ]

        last_error = None
        for sql in strategies:
            try:
                self.conn.execute(sql)
                count = self.conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
                if count == 0:
                    self.conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                    continue
                print(f"[duckdb_engine] JSON loaded via strategy: {sql[:60]!r}")
                return table_name
            except Exception as e:
                last_error = e
                try:
                    self.conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                except Exception:
                    pass

        # Pandas fallback
        try:
            import pandas as pd
            import json as json_lib
            with open(filepath, encoding="utf-8") as fh:
                raw = json_lib.load(fh)
            if isinstance(raw, list):
                df = pd.json_normalize(raw)
            elif isinstance(raw, dict):
                # Look for a list-of-dicts value
                df = None
                for val in raw.values():
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        df = pd.json_normalize(val)
                        break
                if df is None:
                    df = pd.json_normalize([raw])
            else:
                raise ValueError(f"Unexpected JSON root type: {type(raw)}")

            # Flatten column names (nested keys become col1.col2)
            df.columns = [c.replace(".", "_") for c in df.columns]
            self.conn.execute(f'CREATE OR REPLACE TABLE "{table_name}" AS SELECT * FROM df')
            count = self.conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            if count == 0:
                raise ValueError("Pandas fallback loaded 0 rows")
            print(f"[duckdb_engine] JSON loaded via pandas fallback: {count} rows")
            return table_name
        except Exception as e:
            raise ValueError(
                f"Failed to load JSON file after all strategies.\n"
                f"Last DuckDB error: {last_error}\nPandas error: {e}"
            ) from e

    def register_file(self, filepath: str) -> dict:
        """Profile uploaded file. Returns schema_profile dict."""
        ext = Path(filepath).suffix.lower()

        # Bug 2: use robust JSON loader instead of raw read_json_auto
        if ext == ".json":
            json_table_name = self._load_json_robust(filepath)
            read_fn = f'"{json_table_name}"'
        else:
            read_fn = self._read_fn(filepath)
            json_table_name = None

        # Basic schema
        schema_rows = self.conn.execute(f"DESCRIBE SELECT * FROM {read_fn}").fetchall()

        # Row count
        total_rows = self.conn.execute(f"SELECT COUNT(*) FROM {read_fn}").fetchone()[0]

        # Sample data
        sample_df = self.conn.execute(f"SELECT * FROM {read_fn} LIMIT 5").fetchdf()
        sample_data = sample_df.to_dict(orient="records")

        columns = {}
        for row in schema_rows:
            col_name = row[0]
            col_type = row[1].upper()
            col_info = {"type": col_type}

            try:
                # Null count
                null_count = self.conn.execute(
                    f'SELECT COUNT(*) FROM {read_fn} WHERE "{col_name}" IS NULL'
                ).fetchone()[0]
                col_info["null_count"] = null_count

                base_type = col_type.split("(")[0].strip()

                if base_type in ("VARCHAR", "TEXT", "STRING", "CHAR"):
                    distinct = self.conn.execute(
                        f'SELECT DISTINCT "{col_name}" FROM {read_fn} '
                        f'WHERE "{col_name}" IS NOT NULL LIMIT 20'
                    ).fetchall()
                    col_info["sample_values"] = [r[0] for r in distinct]
                    col_info["distinct_count"] = self.conn.execute(
                        f'SELECT COUNT(DISTINCT "{col_name}") FROM {read_fn}'
                    ).fetchone()[0]

                elif base_type in ("INTEGER", "BIGINT", "HUGEINT", "SMALLINT",
                                   "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "REAL"):
                    result = self.conn.execute(
                        f'SELECT MIN("{col_name}"), MAX("{col_name}"), '
                        f'ROUND(AVG(CAST("{col_name}" AS DOUBLE)), 2), '
                        f'COUNT(DISTINCT "{col_name}") FROM {read_fn}'
                    ).fetchone()
                    col_info["min"] = result[0]
                    col_info["max"] = result[1]
                    col_info["avg"] = result[2]
                    col_info["distinct_count"] = result[3]

                elif base_type in ("DATE", "TIMESTAMP", "TIMESTAMPTZ"):
                    result = self.conn.execute(
                        f'SELECT MIN("{col_name}"), MAX("{col_name}"), '
                        f'COUNT(DISTINCT "{col_name}") FROM {read_fn}'
                    ).fetchone()
                    col_info["min_date"] = str(result[0])
                    col_info["max_date"] = str(result[1])
                    col_info["distinct_count"] = result[2]

            except Exception:
                pass  # Skip profiling errors gracefully

            columns[col_name] = col_info

        table_name = Path(filepath).stem if json_table_name is None else json_table_name
        # JSON tables are already registered; for read_fn sources, keep read_fn as-is
        # but record the actual table name for display

        profile = {
            "table_name": table_name,
            "filepath": filepath,
            "read_fn": read_fn,
            "total_rows": total_rows,
            "columns": columns,
            "sample_data": sample_data,
        }
        self.files[filepath] = profile
        return profile

    def execute(self, sql: str, timeout: int = 10) -> dict:
        """Execute DuckDB SQL. Returns success/results/columns/error."""
        try:
            result = self.conn.execute(sql)
            rows = result.fetchall()
            columns = [d[0] for d in result.description] if result.description else []
            return {
                "success": True,
                "results": rows,
                "columns": columns,
                "error": None,
            }
        except Exception as e:
            return {
                "success": False,
                "results": None,
                "columns": None,
                "error": str(e),
            }

    def get_valid_columns(self, filepath: str) -> list:
        if filepath in self.files:
            return list(self.files[filepath]["columns"].keys())
        profile = self.register_file(filepath)
        return list(profile["columns"].keys())

    def sniff_file(self, filepath: str) -> str:
        try:
            fp = filepath.replace("\\", "/")
            result = self.conn.execute(f"SELECT * FROM sniff_csv('{fp}')").fetchdf()
            return result.to_string()
        except Exception as e:
            return str(e)
