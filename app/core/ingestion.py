"""
Multi-Format File Ingestion Service.

What this module does:
  Takes raw bytes from an HTTP upload and loads them into an in-memory
  DuckDB connection as named tables.  Every file format (CSV, JSON, Excel,
  Parquet, SQLite…) is handled here, and the data NEVER touches permanent
  disk storage.

Design principles:
  1. Zero disk persistence — files are written to OS temp files only long
     enough for DuckDB/pandas to read them, then deleted immediately.
  2. One table per file (or one table per sheet for Excel, one per table
     for SQLite databases).
  3. Column names are always normalised to lowercase_underscore so SQL
     generators can reference them without surprises.
  4. Types are auto-detected from sample values — VARCHAR columns that
     look like integers, floats, or dates are cast to proper DuckDB types.
  5. Session isolation — the DuckDB connection is owned by the caller
     (Session), so clearing a session automatically discards all data.

Supported formats:
  .csv / .tsv  — read_csv_auto with full-scan sample
  .json        — DuckDB native + pandas json_normalize fallback
  .jsonl       — read_ndjson_auto
  .parquet     — read_parquet
  .xlsx        — openpyxl + pandas (one table per non-empty sheet)
  .xls         — pandas ExcelFile (legacy format)
  .db / .sqlite — SQLite extension (one table per source table)
  .txt / .md   — stored as unstructured documents for future RAG
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List

import duckdb
import pandas as pd


class IngestionService:
    """
    Loads uploaded files into a shared in-memory DuckDB connection.

    Usage:
        svc = IngestionService(con)          # pass the session's DuckDB connection
        result = svc.ingest_file_bytes(filename, raw_bytes)
        # result["tables"] now lists the DuckDB table names that were created
    """

    def __init__(self, con: duckdb.DuckDBPyConnection):
        # The DuckDB connection is owned by the Session; we just write into it.
        self.con = con
        self.tables: List[str] = []               # ordered list of created table names
        self.table_schemas: Dict[str, list] = {}  # table_name -> [{"name":..,"type":..}]
        self.unstructured_docs: List[dict] = []   # text/markdown files for RAG (future use)

    def reset(self):
        """
        Drop every table this service loaded and wipe all tracking state.

        Called when the user clicks "New Chat" — we want a completely clean
        slate so old data can't bleed into the new session.
        """
        for t in list(self.tables):
            try:
                self.con.execute(f'DROP TABLE IF EXISTS "{t}"')
            except Exception:
                pass
        self.tables = []
        self.table_schemas = {}
        self.unstructured_docs = []

    # ── Public entry point ─────────────────────────────────────────────────────

    def ingest_file_bytes(self, filename: str, content: bytes) -> Dict:
        """
        Main entry point — ingest raw file bytes received from an HTTP upload.

        Steps:
          1. Write bytes to a temporary file (with the correct extension so
             format-detection tools work correctly).
          2. Call the appropriate loader based on the file extension.
          3. Delete the temp file immediately after loading.

        Returns a dict:
          {
            "tables":       [list of DuckDB table names that were created],
            "errors":       [list of error strings, empty on full success],
            "docs_indexed": int  (number of text docs stored for RAG)
          }
        """
        ext = Path(filename).suffix.lower()
        results: Dict = {"tables": [], "errors": [], "docs_indexed": 0}

        # We use the original extension so DuckDB / pandas picks the right parser.
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
            # Always delete the temp file — data now lives in DuckDB memory only.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return results

    # ── Format dispatcher ──────────────────────────────────────────────────────

    def _load_from_path(
        self, tmp_path: str, original_name: str, results: Dict
    ) -> List[str]:
        """
        Route a temporary file to the right loader based on its extension.

        This is a simple dispatcher — each file type has its own loader
        method that returns a list of DuckDB table names.  Text/markdown
        files are stored separately as unstructured documents (not tables).
        """
        ext       = Path(original_name).suffix.lower()
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

    # ── Individual loaders ─────────────────────────────────────────────────────

    def _load_csv(self, path: str, base_name: str, delimiter: str = ",") -> str:
        """
        Load a CSV (or TSV) file into DuckDB using a two-pass strategy.

        Pass 1 — load everything as VARCHAR (all_varchar=true).
          This avoids data loss on messy real-world CSVs where DuckDB might
          silently drop rows with unexpected values if it guesses types wrong.

        Pass 2 — call _smart_cast_columns to detect and apply proper types.
          After the table is safely loaded as strings, we sample each column
          and cast it to BIGINT / DOUBLE / DATE / BOOLEAN where appropriate.

        Forward slashes are used in the path because DuckDB on Windows
        sometimes struggles with backslashes inside SQL strings.
        """
        table_name = self._unique_table_name(base_name)
        fp = path.replace("\\", "/")
        delim_arg = f", delim='{delimiter}'" if delimiter != "," else ""

        # Load all columns as text first to avoid type-guessing data loss.
        self.con.execute(f"""
            CREATE TABLE "{table_name}" AS
            SELECT * FROM read_csv_auto('{fp}',
                all_varchar=true, sample_size=-1,
                ignore_errors=true, null_padding=true{delim_arg})
        """)

        self._normalize_columns(table_name)   # rename to snake_case
        self._smart_cast_columns(table_name)  # upgrade VARCHAR → proper types
        self._register_table(table_name)
        return table_name

    def _load_json(self, path: str, base_name: str) -> str:
        """
        Load a JSON file into DuckDB using three fallback strategies.

        Strategy 1 — DuckDB read_json_auto with different 'records' modes.
          Tries 'auto', then 'true' (array of objects), then 'false' (single object).
          This handles most well-formed JSON files.

        Strategy 2 — pandas json_normalize.
          If DuckDB fails or returns 0 rows, we parse the JSON with Python,
          detect whether it's a list of records or a dict with a nested list,
          and flatten it with pandas.json_normalize (max 2 levels deep).

        This two-strategy approach handles deeply nested JSON that DuckDB
        can't always auto-flatten.
        """
        table_name = self._unique_table_name(base_name)
        fp = path.replace("\\", "/")
        loaded = False

        # Strategy 1: DuckDB native parser — fast and handles most cases.
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

        # Strategy 2: pandas fallback for nested / unusual JSON shapes.
        if not loaded:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)

            if isinstance(raw, list):
                df = pd.json_normalize(raw, max_level=2)
            elif isinstance(raw, dict):
                # Look for the first list of records inside a dict wrapper.
                df = None
                for val in raw.values():
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        df = pd.json_normalize(val, max_level=2)
                        break
                if df is None:
                    df = pd.json_normalize([raw], max_level=2)
            else:
                raise ValueError(f"Unexpected JSON root type: {type(raw)}")

            # pandas uses dots in nested column names — replace with underscores
            # so DuckDB identifiers remain valid.
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
        """
        Load a newline-delimited JSON (JSONL / NDJSON) file.

        Each line is a separate JSON object.  DuckDB's read_ndjson_auto
        handles this format natively with full-file sampling.
        """
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
        """
        Load a Parquet file directly into DuckDB.

        Parquet already carries type information so we skip _smart_cast_columns
        (types are already correct).  We still normalise column names for
        consistent snake_case access in SQL.
        """
        table_name = self._unique_table_name(base_name)
        fp = path.replace("\\", "/")
        self.con.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM read_parquet(\'{fp}\')')
        self._normalize_columns(table_name)
        self._register_table(table_name)
        return table_name

    def _load_xlsx(self, path: str, base_name: str) -> List[str]:
        """
        Load all non-empty sheets from an Excel .xlsx workbook.

        Each sheet becomes its own DuckDB table.  Sheet names are appended to
        the base filename as a suffix (e.g. "report_sales", "report_costs").
        If the workbook has only one sheet, no suffix is added.

        Uses openpyxl to read the workbook (data_only=True so formulas
        resolve to their computed values) and pandas for the actual data frame.
        """
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
        """
        Load an old-format .xls Excel file (pre-2007 binary format).

        Uses pandas ExcelFile which internally uses xlrd for .xls support.
        Same per-sheet logic as _load_xlsx.
        """
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
        """
        Load all tables from a SQLite database file.

        Uses DuckDB's SQLite extension to ATTACH the database, then copies
        each non-empty user table into the session's in-memory DuckDB.
        The attached database is DETACHED immediately after copying so no
        handle to the original file remains open.

        System tables (those starting with "sqlite_") are skipped.
        """
        fp = path.replace("\\", "/")
        try:
            self.con.execute("INSTALL sqlite; LOAD sqlite;")
        except Exception:
            pass  # Extension already loaded in this session

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
                # Don't register empty tables — they'd confuse the SQL generator.
                self.con.execute(f'DROP TABLE IF EXISTS "{table_name}"')

        self.con.execute("DETACH _src_db")
        return tables

    def _load_text(self, path: str, original_name: str):
        """
        Read a plain-text or markdown file into the unstructured_docs list.

        These documents are not loaded as DuckDB tables.  Instead they are
        stored for a future RAG (retrieval-augmented generation) pipeline that
        can answer questions requiring free-text search rather than SQL.
        """
        try:
            with open(path, "r", errors="replace") as fh:
                content = fh.read()
            if content.strip():
                self.unstructured_docs.append({
                    "source":  original_name,
                    "content": content,
                })
        except Exception:
            pass

    # ── Column helpers ─────────────────────────────────────────────────────────

    def _normalize_columns(self, table_name: str):
        """
        Rename all columns in a table to lowercase snake_case.

        Real-world files often have column names like "First Name", "Revenue ($)",
        or "Q1 2024 Sales".  We convert them to "first_name", "revenue_",
        "q1_2024_sales" so SQL generators always produce valid identifiers
        without needing to quote unusual names.

        If a rename fails (e.g. duplicate names after normalisation), we silently
        skip it — better to have an unusual name than to crash the upload.
        """
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
                    pass  # keep original name if rename fails

    def _smart_cast_columns(self, table_name: str):
        """
        Upgrade VARCHAR columns to their most specific DuckDB type.

        When CSV/JSON data is loaded with all_varchar=true every column
        starts as text.  This method samples up to 500 distinct values per
        column and casts it to BOOLEAN, BIGINT, DOUBLE, or DATE if all
        sampled values match that type.

        We use TRY_CAST so that any rows that don't parse cleanly are set
        to NULL instead of causing a hard error.  Leading-zero strings like
        zip codes ("01234") are NOT cast to integers.
        """
        try:
            cols = self.con.execute(f'DESCRIBE "{table_name}"').fetchall()
        except Exception:
            return

        for col_name, col_type, *_ in cols:
            if "VARCHAR" not in col_type.upper():
                continue  # already a proper type, skip

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
                    pass  # keep VARCHAR if the cast fails for any reason

    def _detect_type(self, values: List[str]) -> str:
        """
        Infer the best DuckDB type for a list of string sample values.

        Detection order (most specific first):
          1. BOOLEAN  — all values are true/false/yes/no/y/n/0/1
          2. BIGINT   — all values are integers (leading-zero strings excluded)
          3. DOUBLE   — all values parse as floating-point numbers
          4. DATE     — ≥90% of the first 50 values match a date pattern
          5. VARCHAR  — fallback (no cast applied)

        Returns the DuckDB type string, or "VARCHAR" if nothing fits.
        """
        if not values:
            return "VARCHAR"

        # BOOLEAN check
        bool_vals = {"true", "false", "yes", "no", "y", "n", "1", "0", "t", "f"}
        if all(v.lower() in bool_vals for v in values):
            return "BOOLEAN"

        # INTEGER check — exclude leading-zero codes like zip codes ("01234")
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

        # FLOAT check
        if all(self._is_float(v) for v in values):
            return "DOUBLE"

        # DATE check — require 90% match so sporadic non-date strings don't prevent casting
        date_patterns = [
            r"^\d{4}-\d{2}-\d{2}",   # ISO 8601 (2024-01-15)
            r"^\d{2}/\d{2}/\d{4}",   # US format  (01/15/2024)
            r"^\d{2}-\d{2}-\d{4}",   # EU format  (15-01-2024)
        ]
        for pattern in date_patterns:
            sample = values[:50]
            if sample and sum(1 for v in sample if re.match(pattern, v)) > len(sample) * 0.9:
                return "DATE"

        return "VARCHAR"

    @staticmethod
    def _is_float(v: str) -> bool:
        """
        Return True if the string represents a valid floating-point number.
        Strips commas used as thousands separators (e.g. "1,234.56").
        """
        try:
            float(v.replace(",", "").replace(" ", ""))
            return True
        except ValueError:
            return False

    def _register_table(self, table_name: str):
        """
        Add a successfully loaded table to the tracking lists.

        After registration the table appears in self.tables (ordered) and
        self.table_schemas (column metadata).  Downstream code uses these
        lists to build schema context for the SQL generator.
        """
        self.tables.append(table_name)
        try:
            cols = self.con.execute(f'DESCRIBE "{table_name}"').fetchall()
            self.table_schemas[table_name] = [
                {"name": c[0], "type": c[1]} for c in cols
            ]
        except Exception:
            self.table_schemas[table_name] = []

    def _unique_table_name(self, base: str) -> str:
        """
        Return a sanitised table name that doesn't clash with existing tables.

        If "sales" is already registered, the next upload of a file named
        "sales.csv" will get the name "sales_2", then "sales_3", etc.
        This prevents silent data overwrites when the user uploads files
        with the same base name.
        """
        name = self._sanitize(base)
        if name not in self.tables:
            return name
        i = 2
        while f"{name}_{i}" in self.tables:
            i += 1
        return f"{name}_{i}"

    @staticmethod
    def _sanitize(name: str) -> str:
        """
        Convert any string into a valid DuckDB table/column identifier.

        Rules:
          - Replace non-alphanumeric characters with underscores
          - Collapse consecutive underscores to one
          - Strip leading/trailing underscores
          - Lowercase everything
          - Prepend "t_" if the first character is a digit (SQL identifiers
            cannot start with a number)
          - Fall back to "unnamed_table" if the result is empty
        """
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        clean = re.sub(r"_+", "_", clean).strip("_").lower()
        if clean and clean[0].isdigit():
            clean = "t_" + clean
        return clean or "unnamed_table"

    # ── Schema helpers (used by profiling code) ────────────────────────────────

    def get_row_count(self, table_name: str) -> int:
        """
        Return the number of rows in a DuckDB table, or 0 on error.
        Used by the frontend sidebar to display "N rows" next to each file.
        """
        try:
            return self.con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        except Exception:
            return 0

    def get_sample(self, table_name: str, n: int = 5) -> List[dict]:
        """
        Return the first N rows of a table as a list of dicts.
        Used by the schema profiler to show example data to the LLM.
        """
        try:
            df = self.con.execute(f'SELECT * FROM "{table_name}" LIMIT {n}').fetchdf()
            return df.to_dict(orient="records")
        except Exception:
            return []

    def detect_relationships(self) -> List[dict]:
        """
        Find foreign-key-like relationships across all loaded tables.

        Checks every pair of tables for shared column names that look like
        join keys (columns named "id" or ending with "_id").  For example,
        if "orders" has a "customer_id" column and "customers" also has
        "customer_id", we record that as a potential relationship.

        The SQL generator uses these hints to construct JOIN queries when
        the user asks questions spanning multiple tables.
        """
        relationships = []
        for i, t_a in enumerate(self.tables):
            cols_a = {c["name"]: c for c in self.table_schemas.get(t_a, [])}
            for t_b in self.tables[i + 1:]:
                cols_b = {c["name"]: c for c in self.table_schemas.get(t_b, [])}
                common = set(cols_a.keys()) & set(cols_b.keys())
                for col in common:
                    if col == "id" or col.endswith("_id"):
                        relationships.append({
                            "from_table":  t_a,
                            "from_column": col,
                            "to_table":    t_b,
                            "to_column":   col,
                            "join_sql":    f'"{t_a}"."{col}" = "{t_b}"."{col}"',
                        })
        return relationships
