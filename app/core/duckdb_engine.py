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
            return f"read_json_auto('{fp}')"
        return f"read_csv_auto('{fp}')"

    def register_file(self, filepath: str) -> dict:
        """Profile uploaded file. Returns schema_profile dict."""
        read_fn = self._read_fn(filepath)
        fp = filepath.replace("\\", "/")

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

        table_name = Path(filepath).stem

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
