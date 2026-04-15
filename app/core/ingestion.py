"""
Multi-format File Ingestion Service.

Design principles:
  - Data is NEVER saved to disk permanently. Files are loaded into an
    in-memory DuckDB connection (passed in from outside) using temp files
    that are immediately deleted after loading.
  - Every uploaded file becomes one or more named DuckDB tables.
  - SQL generators query table names (e.g. SELECT * FROM "sales"),
    never file paths.
  - Session isolation: each Session gets its own DuckDB connection;
    clearing a session drops all tables automatically.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import duckdb
import pandas as pd


class IngestionService:
    """Ingests uploaded files into an in-memory DuckDB connection."""

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con
        self.tables: List[str] = []               # ordered list of table names
        self.table_schemas: Dict[str, list] = {}  # table_name -> [{"name":..,"type":..}]
        self.unstructured_docs: List[dict] = []   # for future RAG

    def reset(self):
        """Drop all ingested tables and reset state."""
        for t in list(self.tables):
            try:
                self.con.execute(f'DROP TABLE IF EXISTS "{t}"')
            except Exception:
                pass
        self.tables = []
        self.table_schemas = {}
        self.unstructured_docs = []

    # ── Public entry point ─────────────────────────────────────────────────

    def ingest_file_bytes(self, filename: str, content: bytes) -> Dict:
        """
        Ingest raw file bytes (from an HTTP upload).
        Writes to a temp file, loads into DuckDB, then deletes the temp file.
        Returns: {"tables": [...], "errors": [...], "docs_indexed": int}
        """
        ext = Path(filename).suffix.lower()
        results: Dict = {"tables": [], "errors": [], "docs_indexed": 0}

        # Write to a temp file with the correct extension so DuckDB/pandas
        # can detect the format.
        suffix = ext if ext else ".tmp"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            tables = self._load_from_path(tmp_path, filename, results)
            results["tables"].extend(tables)
        except Exception as e:
            results["errors"].append(f"{filename}: {str(e)}")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return results

    # ── Format dispatchers ─────────────────────────────────────────────────

    def _load_from_path(
        self, tmp_path: str, original_name: str, results: Dict
    ) -> List[str]:
        ext = Path(original_name).suffix.lower()
        base_name = Path(original_name).stem

        if ext == ".csv":
            return [self._load_csv(tmp_path, base_name)]
        elif ext == ".tsv":
            return [self._load_csv(tmp_path, base_name, delimiter="\t")]
        elif ext == ".json":
            return [self._load_json(tmp_path, base_name)]
        elif ext in (".jsonl", ".ndjson"):
            return [self._load_jsonl(tmp_path, base_name)]
        elif ext in (".parquet", ".pq"):
            return [self._load_parquet(tmp_path, base_name)]
        elif ext == ".xlsx":
            return self._load_xlsx(tmp_path, base_name)
        elif ext == ".xls":
            return self._load_xls_legacy(tmp_path, base_name)
        elif ext in (".db", ".sqlite", ".sqlite3"):
            return self._load_sqlite(tmp_path, base_name)
        elif ext in (".txt", ".md", ".log"):
            self._load_text(tmp_path, original_name)
            results["docs_indexed"] += 1
            return []
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    # ── Loaders ────────────────────────────────────────────────────────────

    def _load_csv(self, path: str, base_name: str, delimiter: str = ",") -> str:
        table_name = self._unique_table_name(base_name)
        fp = path.replace("\\", "/")
        delim_arg = f", delim='{delimiter}'" if delimiter != "," else ""

        # Pass 1: load all as VARCHAR (zero data loss on messy CSVs)
        self.con.execute(f"""
            CREATE TABLE "{table_name}" AS
            SELECT * FROM read_csv_auto('{fp}',
                all_varchar=true, sample_size=-1,
                ignore_errors=true, null_padding=true{delim_arg})
        """)

        self._normalize_columns(table_name)
        self._smart_cast_columns(table_name)
        self._register_table(table_name)
        return table_name

    def _load_json(self, path: str, base_name: str) -> str:
        table_name = self._unique_table_name(base_name)
        fp = path.replace("\\", "/")
        loaded = False

        # Strategy 1: DuckDB native (try multiple record modes)
        for records_flag in ("auto", "true", "false"):
            if loaded:
                break
            try:
                self.con.execute(f"""
                    CREATE OR REPLACE TABLE "{table_name}" AS
                    SELECT * FROM read_json_auto('{fp}',
                        maximum_object_size=67108864,
                        sample_size=2000, records='{records_flag}')
                """)
                count = self.con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
                if count > 0:
                    loaded = True
                else:
                    self.con.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            except Exception:
                try:
                    self.con.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                except Exception:
                    pass

        # Strategy 2: pandas json_normalize fallback
        if not loaded:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)

            if isinstance(raw, list):
                df = pd.json_normalize(raw, max_level=2)
            elif isinstance(raw, dict):
                df = None
                for val in raw.values():
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        df = pd.json_normalize(val, max_level=2)
                        break
                if df is None:
                    df = pd.json_normalize([raw], max_level=2)
            else:
                raise ValueError(f"Unexpected JSON root type: {type(raw)}")

            df.columns = [c.replace(".", "_").replace(" ", "_") for c in df.columns]
            self.con.execute(f'CREATE OR REPLACE TABLE "{table_name}" AS SELECT * FROM df')
            loaded = True

        if not loaded:
            raise ValueError("Failed to load JSON file with all strategies")

        self._normalize_columns(table_name)
        self._smart_cast_columns(table_name)
        self._register_table(table_name)
        return table_name

    def _load_jsonl(self, path: str, base_name: str) -> str:
        table_name = self._unique_table_name(base_name)
        fp = path.replace("\\", "/")
        self.con.execute(f"""
            CREATE TABLE "{table_name}" AS
            SELECT * FROM read_ndjson_auto('{fp}', sample_size=-1)
        """)
        self._normalize_columns(table_name)
        self._smart_cast_columns(table_name)
        self._register_table(table_name)
        return table_name

    def _load_parquet(self, path: str, base_name: str) -> str:
        table_name = self._unique_table_name(base_name)
        fp = path.replace("\\", "/")
        self.con.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM read_parquet(\'{fp}\')')
        self._normalize_columns(table_name)
        self._register_table(table_name)
        return table_name

    def _load_xlsx(self, path: str, base_name: str) -> List[str]:
        """Load all non-empty sheets from an .xlsx file."""
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheet_names = wb.sheetnames
        wb.close()

        tables = []
        for sheet in sheet_names:
            df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
            if df.empty:
                continue
            suffix = f"_{self._sanitize(sheet)}" if len(sheet_names) > 1 else ""
            table_name = self._unique_table_name(base_name + suffix)
            self.con.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM df')
            self._normalize_columns(table_name)
            self._smart_cast_columns(table_name)
            self._register_table(table_name)
            tables.append(table_name)

        return tables

    def _load_xls_legacy(self, path: str, base_name: str) -> List[str]:
        xls = pd.ExcelFile(path)
        tables = []
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            if df.empty:
                continue
            suffix = f"_{self._sanitize(sheet)}" if len(xls.sheet_names) > 1 else ""
            table_name = self._unique_table_name(base_name + suffix)
            self.con.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM df')
            self._normalize_columns(table_name)
            self._register_table(table_name)
            tables.append(table_name)
        return tables

    def _load_sqlite(self, path: str, base_name: str) -> List[str]:
        fp = path.replace("\\", "/")
        try:
            self.con.execute("INSTALL sqlite; LOAD sqlite;")
        except Exception:
            pass  # already loaded
        self.con.execute(f"ATTACH '{fp}' AS _src_db (TYPE sqlite, READ_ONLY)")

        src_tables = self.con.execute("""
            SELECT name FROM _src_db.sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """).fetchall()

        tables = []
        for (tbl,) in src_tables:
            table_name = self._unique_table_name(f"{base_name}_{self._sanitize(tbl)}")
            self.con.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM _src_db."{tbl}"')
            count = self.con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            if count > 0:
                self._normalize_columns(table_name)
                self._register_table(table_name)
                tables.append(table_name)
            else:
                self.con.execute(f'DROP TABLE IF EXISTS "{table_name}"')

        self.con.execute("DETACH _src_db")
        return tables

    def _load_text(self, path: str, original_name: str):
        try:
            with open(path, "r", errors="replace") as fh:
                content = fh.read()
            if content.strip():
                self.unstructured_docs.append({
                    "source": original_name,
                    "content": content,
                })
        except Exception:
            pass

    # ── DuckDB helpers ─────────────────────────────────────────────────────

    def _normalize_columns(self, table_name: str):
        """Rename columns to lowercase_underscore, no special chars."""
        try:
            cols = self.con.execute(f'DESCRIBE "{table_name}"').fetchall()
        except Exception:
            return
        for row in cols:
            col_name = row[0]
            clean = re.sub(r"[^a-zA-Z0-9_]", "_", col_name.strip())
            clean = re.sub(r"_+", "_", clean).strip("_").lower()
            if not clean:
                clean = "col"
            if clean != col_name:
                try:
                    self.con.execute(
                        f'ALTER TABLE "{table_name}" RENAME COLUMN "{col_name}" TO "{clean}"'
                    )
                except Exception:
                    pass

    def _smart_cast_columns(self, table_name: str):
        """Try to cast VARCHAR columns to better types (BIGINT, DOUBLE, DATE, BOOLEAN)."""
        try:
            cols = self.con.execute(f'DESCRIBE "{table_name}"').fetchall()
        except Exception:
            return

        for col_name, col_type, *_ in cols:
            if "VARCHAR" not in col_type.upper():
                continue

            try:
                samples = self.con.execute(f"""
                    SELECT DISTINCT "{col_name}" FROM "{table_name}"
                    WHERE "{col_name}" IS NOT NULL AND TRIM("{col_name}") != ''
                    LIMIT 500
                """).fetchall()
            except Exception:
                continue

            values = [str(r[0]) for r in samples]
            if not values:
                continue

            target = self._detect_type(values)
            if target and target != "VARCHAR":
                try:
                    self.con.execute(f"""
                        ALTER TABLE "{table_name}"
                        ALTER COLUMN "{col_name}"
                        SET DATA TYPE {target}
                        USING TRY_CAST("{col_name}" AS {target})
                    """)
                except Exception:
                    pass

    def _detect_type(self, values: List[str]) -> str:
        if not values:
            return "VARCHAR"

        # Boolean
        bool_vals = {"true", "false", "yes", "no", "y", "n", "1", "0", "t", "f"}
        if all(v.lower() in bool_vals for v in values):
            return "BOOLEAN"

        # Integer (skip leading-zero codes like zip codes)
        int_ok = True
        for v in values:
            clean = v.replace(",", "").replace(" ", "")
            try:
                int(clean)
                if clean.startswith("0") and len(clean) > 1:
                    int_ok = False
                    break
            except ValueError:
                int_ok = False
                break
        if int_ok:
            return "BIGINT"

        # Float
        float_ok = all(self._is_float(v) for v in values)
        if float_ok:
            return "DOUBLE"

        # Date
        date_patterns = [
            r"^\d{4}-\d{2}-\d{2}",
            r"^\d{2}/\d{2}/\d{4}",
            r"^\d{2}-\d{2}-\d{4}",
        ]
        for pattern in date_patterns:
            sample = values[:50]
            if sample and sum(1 for v in sample if re.match(pattern, v)) > len(sample) * 0.9:
                return "DATE"

        return "VARCHAR"

    @staticmethod
    def _is_float(v: str) -> bool:
        try:
            float(v.replace(",", "").replace(" ", ""))
            return True
        except ValueError:
            return False

    def _register_table(self, table_name: str):
        self.tables.append(table_name)
        try:
            cols = self.con.execute(f'DESCRIBE "{table_name}"').fetchall()
            self.table_schemas[table_name] = [
                {"name": c[0], "type": c[1]} for c in cols
            ]
        except Exception:
            self.table_schemas[table_name] = []

    def _unique_table_name(self, base: str) -> str:
        """Sanitize and ensure uniqueness among already-registered tables."""
        name = self._sanitize(base)
        if name not in self.tables:
            return name
        # Append counter
        i = 2
        while f"{name}_{i}" in self.tables:
            i += 1
        return f"{name}_{i}"

    @staticmethod
    def _sanitize(name: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        clean = re.sub(r"_+", "_", clean).strip("_").lower()
        if clean and clean[0].isdigit():
            clean = "t_" + clean
        return clean or "unnamed_table"

    # ── Schema helpers ─────────────────────────────────────────────────────

    def get_row_count(self, table_name: str) -> int:
        try:
            return self.con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        except Exception:
            return 0

    def get_sample(self, table_name: str, n: int = 5) -> List[dict]:
        try:
            df = self.con.execute(f'SELECT * FROM "{table_name}" LIMIT {n}').fetchdf()
            return df.to_dict(orient="records")
        except Exception:
            return []

    def detect_relationships(self) -> List[dict]:
        """Find FK-like relationships across tables by name + data matching."""
        relationships = []
        for i, t_a in enumerate(self.tables):
            cols_a = {c["name"]: c for c in self.table_schemas.get(t_a, [])}
            for t_b in self.tables[i + 1:]:
                cols_b = {c["name"]: c for c in self.table_schemas.get(t_b, [])}
                common = set(cols_a.keys()) & set(cols_b.keys())
                for col in common:
                    # Only treat *_id columns or "id" as join keys
                    if col == "id" or col.endswith("_id"):
                        relationships.append({
                            "from_table": t_a,
                            "from_column": col,
                            "to_table": t_b,
                            "to_column": col,
                            "join_sql": f'"{t_a}"."{col}" = "{t_b}"."{col}"',
                        })
        return relationships
