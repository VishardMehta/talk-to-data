"""
FastAPI backend for Talk-To-Data.

Key design decisions:
  - Uploaded files are NEVER saved to disk permanently.
    Each file is written to a temp file, loaded into the session's in-memory
    DuckDB connection, then the temp file is deleted immediately.
  - One DuckDB connection per chat session — full data isolation.
  - Multiple files per session are supported; each becomes a named DuckDB table.
  - Clearing a session destroys the DuckDB connection and all data.

Endpoints:
  GET  /api/health
  POST /api/upload          — multipart, supports multiple files
  POST /api/query/stream    — SSE streaming query
  POST /api/query           — non-streaming fallback
  POST /api/session/clear   — reset session
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import List, Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.cache import SemanticCache
from app.core.query_classifier import classify_query
from app.agents import router as agent_router
from app.agents import answer_generator
from app.agents import upload_sql_generator
from api.session import SessionManager
from api.chart_converter import to_chart_payload
from app.core.auto_semantic import (
    profile_table as _profile_table_fn,
    _generate_semantic_enrichment,
    _normalize_llm_response,
    _build_fallback_semantic,
    generate_verified_queries as _generate_verified_queries,
    build_enriched_context as _build_enriched_context,
)

print("[server] Semantic cache uses lazy embedding model loading")
_cache = SemanticCache()
_sessions = SessionManager()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


FAST_UPLOAD_MODE_DEFAULT = _env_bool("FAST_UPLOAD_MODE", True)
UPLOAD_PROFILE_CONCURRENCY = max(1, int(os.getenv("UPLOAD_PROFILE_CONCURRENCY", "4")))
UPLOAD_STREAM_HEARTBEAT_SECONDS = max(3, int(os.getenv("UPLOAD_STREAM_HEARTBEAT_SECONDS", "8")))

app = FastAPI(title="Talk-To-Data API", version="3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:4173"],
    # Vite picks the next free port (e.g. 5174) when 5173 is busy.
    # Allow all localhost/127.0.0.1 ports for local development to avoid CORS fetch failures.
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/response models ────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    session_id: str
    data_source: str = "csv"


class ClearRequest(BaseModel):
    session_id: str


class RemoveTableRequest(BaseModel):
    session_id: str
    table_name: str


# ── SSE helpers ────────────────────────────────────────────────────────────────

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _thinking(step_type: str, message: str, detail: str | None = None) -> tuple[str, str]:
    sid = str(uuid.uuid4())[:8]
    return sid, _sse({
        "type": "thinking_step", "id": sid,
        "step_type": step_type, "message": message, "detail": detail,
    })


def _done(sid: str) -> str:
    return _sse({"type": "thinking_done", "id": sid})


def _friendly_runtime_error(err: Exception) -> str:
    msg = str(err)
    if "429" in msg or "Too Many Requests" in msg:
        return (
            "LLM provider is rate-limited right now (429). "
            "Please retry in 20-60 seconds."
        )
    return msg


# ── SQL execution helper ───────────────────────────────────────────────────────

def _execute_sql(session, sql: str) -> dict:
    """Execute SQL against the session's in-memory DuckDB connection."""
    try:
        result = session.con.execute(sql)
        rows = result.fetchall()
        columns = [d[0] for d in result.description] if result.description else []
        return {"success": True, "results": rows, "columns": columns, "error": None}
    except Exception as e:
        return {"success": False, "results": None, "columns": None, "error": str(e)}


def _validate_sql(session, sql: str) -> dict:
    """Agent 3 — pure Python validation: EXPLAIN check."""
    try:
        session.con.execute(f"EXPLAIN {sql}")
        return {"valid": True, "error": None}
    except Exception as e:
        return {"valid": False, "error": str(e)}


# ── Verified query matcher ────────────────────────────────────────────────────

def _find_best_verified(question: str, verified_queries: list) -> dict | None:
    if not verified_queries:
        return None
    q_lower = question.lower()
    best, best_score = None, 0
    for vq in verified_queries:
        score = sum(1 for w in q_lower.split() if w in vq.get("question", "").lower())
        if score > best_score:
            best_score, best = score, vq
    return best if best_score > 0 else None


# ── Core query pipeline ────────────────────────────────────────────────────────

def _run_query_pipeline(question: str, session_id: str, emit) -> dict:
    session = _sessions.get(session_id)
    start = time.time()
    timings: dict[str, float] = {}

    if not session.has_data:
        return {"answer": "Please upload a data file first.", "cached": False, "time_ms": 0}

    # Build combined context across all uploaded tables
    table_names = session.table_names
    profiles = session.profiles

    # Combined enriched context for SQL generator
    enriched_context = session.semantic.get_combined_context(table_names)
    schema_summary = session.semantic.get_combined_schema_summary(table_names)

    # Query classification for cache threshold
    classification = classify_query(question)
    query_type = classification["query_type"]

    # Cache lookup
    cached = _cache.find_similar(
        question,
        threshold=classification["cache_threshold"],
        query_type=query_type,
    )
    if cached:
        return {**cached, "cached": True, "time_ms": (time.time() - start) * 1000}

    state_ctx = session.conversation_state.get_context_for_followup()

    # Step 1: Route (Agent 1)
    emit("routing", "Classifying your question")
    t0 = time.time()
    route = agent_router.route(question, schema_summary, state_ctx)
    timings["route_ms"] = round((time.time() - t0) * 1000)
    route["intent"] = "STRUCTURED"   # always structured for uploaded data
    pattern = route.get("pattern", "GENERAL")
    print(f"[pipeline][timing] route={timings['route_ms']}ms pattern={pattern} question={question[:80]!r}")

    if route.get("intent") == "OUT_OF_SCOPE":
        return {
            "answer": "I can't answer that with the uploaded data. Try asking about the dataset directly.",
            "cached": False,
            "time_ms": (time.time() - start) * 1000,
            "debug_timings": timings,
        }

    # Step 2: Generate SQL (Agent 2)
    emit("sql", "Generating SQL query")
    t0 = time.time()

    # Gather verified queries from all tables
    all_verified: list = []
    for t in table_names:
        all_verified.extend(profiles.get(t, {}).get("verified_queries", []))
    best_verified = _find_best_verified(question, all_verified)

    gen_result = upload_sql_generator.generate_sql(
        question=question,
        pattern=pattern,
        enriched_context=enriched_context,
        verified_query=best_verified,
        conversation_state=state_ctx,
    )
    sql = gen_result["sql"]
    timings["sql_gen_ms"] = round((time.time() - t0) * 1000)
    print(f"[pipeline][timing] sql_gen={timings['sql_gen_ms']}ms SQL={sql!r}")

    # Step 3: Validate (Agent 3 — no LLM)
    validation = _validate_sql(session, sql)

    if not validation["valid"]:
        print(f"[pipeline] validation failed: {validation['error']}, retrying…")
        emit("sql", "Fixing SQL query")
        t0 = time.time()
        gen_result = upload_sql_generator.generate_sql(
            question=question,
            pattern=pattern,
            enriched_context=enriched_context,
            verified_query=best_verified,
            conversation_state=state_ctx,
            error_feedback=validation["error"],
        )
        sql = gen_result["sql"]
        timings["sql_gen_ms"] = round((time.time() - t0) * 1000 + timings.get("sql_gen_ms", 0))
        validation = _validate_sql(session, sql)

    # Step 4: Execute
    emit("executing", "Running the query")
    t0 = time.time()
    exec_result = _execute_sql(session, sql)
    timings["sql_exec_ms"] = round((time.time() - t0) * 1000)
    print(
        f"[pipeline][timing] sql_exec={timings['sql_exec_ms']}ms "
        f"success={exec_result['success']} "
        f"rows={len(exec_result.get('results') or [])} "
        f"error={exec_result.get('error')}"
    )

    # Retry on execution error
    if not exec_result["success"]:
        print(f"[pipeline] exec error, retrying: {exec_result['error']}")
        emit("sql", "Retrying with corrected query")
        t0 = time.time()
        gen_result = upload_sql_generator.generate_sql(
            question=question,
            pattern=pattern,
            enriched_context=enriched_context,
            verified_query=best_verified,
            conversation_state=state_ctx,
            error_feedback=exec_result["error"],
        )
        sql = gen_result["sql"]
        exec_result = _execute_sql(session, sql)
        timings["sql_exec_ms"] = round((time.time() - t0) * 1000 + timings.get("sql_exec_ms", 0))
        print(
            f"[pipeline][timing] retry sql_exec={timings['sql_exec_ms']}ms "
            f"success={exec_result['success']} "
            f"error={exec_result.get('error')}"
        )

    if not exec_result["success"]:
        return {
            "answer": f"I couldn't execute the query. Error: {exec_result['error']}. Try rephrasing.",
            "sql": sql,
            "cached": False,
            "time_ms": (time.time() - start) * 1000,
            "debug_timings": timings,
        }

    # Step 5: Generate answer (Agent 4)
    emit("answering", "Generating answer")

    # Build dataset context for the answer writer
    primary = session.primary_profile
    if primary:
        table_name = primary["table_name"]
        table_desc = primary.get("auto_semantic", {}).get("table_description", "")
        col_names = list(primary["schema_profile"]["columns"].keys())[:15]
        dataset_context = (
            f"Table: {table_name}\nDescription: {table_desc}\n"
            f"Columns: {', '.join(col_names)}"
        )
    else:
        dataset_context = f"Tables: {', '.join(table_names)}"

    t0 = time.time()
    answer_result = answer_generator.generate_answer(
        question=question,
        pattern=pattern,
        sql_results=exec_result,
        sql_used=sql,
        conversation_state=state_ctx,
        query_type=query_type,
        dataset_context=dataset_context,
    )
    timings["answer_ms"] = round((time.time() - t0) * 1000)
    print(f"[pipeline][timing] answer={timings['answer_ms']}ms")

    session.conversation_state.update(
        question, sql, exec_result, answer_result["answer"], table_names
    )

    elapsed = round((time.time() - start) * 1000)
    timings["total_ms"] = elapsed
    print(f"[pipeline][timing] total={elapsed}ms breakdown={timings}")

    response = {
        "answer": answer_result["answer"],
        "sql": sql,
        "results": exec_result,
        "confidence": gen_result.get("confidence"),
        "follow_ups": answer_result.get("follow_up_questions", []),
        "route": route,
        "cached": False,
        "time_ms": elapsed,
        "debug_timings": timings,
    }
    _cache.store(question, response, query_type=query_type)
    return response


# ── Convert pipeline response → QueryResult (React type) ─────────────────────

def _to_query_result(question: str, resp: dict) -> dict:
    sql_results = resp.get("results")

    # Backward/defensive payload normalization: some legacy/cache paths may
    # contain list-shaped results instead of {success, results, columns} dicts.
    if isinstance(sql_results, list):
        if sql_results and isinstance(sql_results[0], dict):
            columns = list(sql_results[0].keys())
            rows = [tuple(item.get(c) for c in columns) for item in sql_results]
            sql_results = {"success": True, "results": rows, "columns": columns}
        elif sql_results and isinstance(sql_results[0], (list, tuple)):
            col_count = len(sql_results[0])
            columns = [f"col_{i + 1}" for i in range(col_count)]
            rows = [tuple(r) if isinstance(r, (list, tuple)) else (r,) for r in sql_results]
            sql_results = {"success": True, "results": rows, "columns": columns}
        else:
            rows = [(v,) for v in sql_results]
            sql_results = {"success": bool(rows), "results": rows, "columns": ["value"]}

    pattern = resp.get("route", {}).get("pattern", "GENERAL") or "GENERAL"
    chart_payload = {}

    if sql_results and sql_results.get("success") and sql_results.get("results"):
        chart_payload = to_chart_payload(
            sql_results["results"], sql_results["columns"], pattern, question
        )

    return {
        "question": question,
        "answer": resp.get("answer", ""),
        "sql": resp.get("sql"),
        "interpreted_as": resp.get("route", {}).get("reasoning"),
        "follow_ups": resp.get("follow_ups") or [],
        "confidence": resp.get("confidence"),
        "cached": resp.get("cached", False),
        "time_ms": resp.get("time_ms"),
        "debug_timings": resp.get("debug_timings"),
        **chart_payload,
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "3.0"}


def _emit_upload_progress(
    progress_cb: Callable[[dict], None] | None,
    percent: int,
    stage: str,
    message: str,
    filename: str | None = None,
    table_name: str | None = None,
) -> None:
    if progress_cb is None:
        return
    progress_cb({
        "percent": max(0, min(100, int(percent))),
        "stage": stage,
        "message": message,
        "filename": filename,
        "table_name": table_name,
    })


async def _run_upload_pipeline(
    files: List[UploadFile],
    session_id: str,
    fast_mode: bool,
    progress_cb: Callable[[dict], None] | None = None,
) -> dict:
    """
    Core upload pipeline shared by /api/upload and /api/upload/stream.

    Stage model (for progress UI):
      dataset uploaded -> duckdb -> yaml-engine -> yaml generated -> semantic embedding -> ready
    """
    session = _sessions.get(session_id)
    upload_start = time.time()
    print(f"[upload] session={session_id} files={len(files)} fast_mode={fast_mode}")

    all_tables: list[dict] = []
    all_errors: list[str] = []
    to_profile: list[tuple[str, str, str]] = []

    _emit_upload_progress(progress_cb, 1, "dataset_uploaded", "Upload request received")

    def _drop_tables_for_filename(filename_key: str) -> None:
        old_tables = list(session.uploaded_filename_tables.get(filename_key, []))
        if not old_tables:
            return

        for table_name in old_tables:
            try:
                session.con.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            except Exception:
                pass

            session.profiles.pop(table_name, None)
            if table_name in session.table_names:
                session.table_names.remove(table_name)
            if table_name in session.ingestion.tables:
                session.ingestion.tables.remove(table_name)
            session.ingestion.table_schemas.pop(table_name, None)

        session.uploaded_filename_tables.pop(filename_key, None)
        stale_keys = [k for k in session.uploaded_file_cache.keys() if k.startswith(f"{filename_key}:")]
        for k in stale_keys:
            session.uploaded_file_cache.pop(k, None)

    total_files = max(1, len(files))

    # Phase 1 (5 -> 45): receive, dedupe, ingest to DuckDB.
    for idx, uploaded_file in enumerate(files, start=1):
        filename = uploaded_file.filename or "upload"
        filename_key = filename.lower()
        file_start = time.time()

        phase_start = int(5 + ((idx - 1) / total_files) * 40)
        phase_end = int(5 + (idx / total_files) * 40)

        _emit_upload_progress(
            progress_cb,
            phase_start,
            "dataset_uploaded",
            f"Dataset uploaded: {filename} ({idx}/{total_files})",
            filename=filename,
        )

        content = await uploaded_file.read()
        file_hash = hashlib.sha256(content).hexdigest()
        cache_key = f"{filename_key}:{file_hash}"
        print(f"[upload] ingest start file={filename!r} bytes={len(content)}")

        cached_tables = session.uploaded_file_cache.get(cache_key)
        if cached_tables:
            _emit_upload_progress(
                progress_cb,
                min(phase_end, phase_start + 8),
                "duckdb",
                f"Checking cached DuckDB tables for {filename}",
                filename=filename,
            )
            reused_any = False
            for table_name in cached_tables:
                profile = session.profiles.get(table_name)
                if profile is None:
                    continue
                try:
                    session.con.execute(f'SELECT 1 FROM "{table_name}" LIMIT 1')
                except Exception:
                    continue

                reused_any = True
                row_count = profile["schema_profile"].get("total_rows", 0)
                col_count = len(profile["schema_profile"].get("columns", []))
                if table_name not in session.table_names:
                    session.table_names.append(table_name)
                all_tables.append({
                    "name": table_name,
                    "filename": filename,
                    "rows": row_count,
                    "columns": col_count,
                    "reused": True,
                })

            if reused_any:
                session.uploaded_filename_tables[filename_key] = list(cached_tables)
                _emit_upload_progress(
                    progress_cb,
                    phase_end,
                    "duckdb",
                    f"Data unchanged for {filename}; reused cached DuckDB tables",
                    filename=filename,
                )
                print(
                    f"[upload] reuse file={filename!r} tables={len(cached_tables)} "
                    f"elapsed_ms={round((time.time() - file_start) * 1000)}"
                )
                continue

        _emit_upload_progress(
            progress_cb,
            min(phase_end, phase_start + 12),
            "duckdb",
            (
                f"Loading {filename} ({round(len(content) / (1024 * 1024), 1)} MB) into DuckDB"
                if len(content) >= 1024 * 1024
                else f"Loading {filename} into DuckDB"
            ),
            filename=filename,
        )

        # Same filename with different content: replace old tables before re-ingesting.
        _drop_tables_for_filename(filename_key)

        try:
            result = await asyncio.to_thread(
                session.ingestion.ingest_file_bytes, filename, content
            )
            print(
                f"[upload] ingest done file={filename!r} tables={len(result.get('tables') or [])} "
                f"elapsed_ms={round((time.time() - file_start) * 1000)}"
            )
        except Exception as e:
            all_errors.append(f"{filename}: {str(e)}")
            print(f"[upload] ingest error file={filename!r} err={e}")
            continue

        if result.get("errors"):
            all_errors.extend(result["errors"])

        if not result.get("tables"):
            if not result.get("errors"):
                all_errors.append(f"{filename}: no tables could be loaded")
            continue

        for table_name in result["tables"]:
            to_profile.append((filename, table_name, cache_key))

        _emit_upload_progress(
            progress_cb,
            phase_end,
            "duckdb",
            f"DuckDB ingestion complete for {filename}",
            filename=filename,
        )

    # Phase 2 (45 -> 95): schema profiling + semantic context generation.
    total_tables_to_profile = max(1, len(to_profile))
    for idx, (filename, table_name, cache_key) in enumerate(to_profile, start=1):
        table_base = int(45 + ((idx - 1) / total_tables_to_profile) * 50)
        table_end = int(45 + (idx / total_tables_to_profile) * 50)

        _emit_upload_progress(
            progress_cb,
            table_base,
            "yaml_engine",
            f"Profiling schema for {table_name}",
            filename=filename,
            table_name=table_name,
        )

        try:
            schema_profile = await asyncio.to_thread(_profile_table_fn, session.con, table_name)
        except Exception as e:
            all_errors.append(f"{filename} → {table_name}: profiling failed: {e}")
            continue

        _emit_upload_progress(
            progress_cb,
            min(table_end, table_base + 10),
            "yaml_engine",
            f"Running YAML engine for {table_name}",
            filename=filename,
            table_name=table_name,
        )

        if fast_mode:
            auto_semantic = _build_fallback_semantic(schema_profile)
            _emit_upload_progress(
                progress_cb,
                min(table_end, table_base + 20),
                "yaml_generated",
                f"Semantic YAML generated (fast mode) for {table_name}",
                filename=filename,
                table_name=table_name,
            )
        else:
            try:
                auto_semantic = await asyncio.to_thread(_generate_semantic_enrichment, schema_profile)
                auto_semantic = _normalize_llm_response(auto_semantic)
                _emit_upload_progress(
                    progress_cb,
                    min(table_end, table_base + 20),
                    "yaml_generated",
                    f"Semantic YAML generated for {table_name}",
                    filename=filename,
                    table_name=table_name,
                )
            except Exception:
                auto_semantic = _build_fallback_semantic(schema_profile)
                _emit_upload_progress(
                    progress_cb,
                    min(table_end, table_base + 20),
                    "yaml_generated",
                    f"Semantic YAML fallback generated for {table_name}",
                    filename=filename,
                    table_name=table_name,
                )

        _emit_upload_progress(
            progress_cb,
            min(table_end, table_base + 35),
            "semantic_embedding",
            f"Building semantic query context for {table_name}",
            filename=filename,
            table_name=table_name,
        )

        try:
            verified_queries = await asyncio.to_thread(
                _generate_verified_queries,
                session.con,
                schema_profile,
                auto_semantic,
            )
        except Exception:
            verified_queries = []

        try:
            enriched_context = await asyncio.to_thread(
                _build_enriched_context,
                schema_profile,
                auto_semantic,
            )
        except Exception:
            enriched_context = (
                f'-- Table: "{table_name}"\n'
                f"-- Total rows: {schema_profile['total_rows']}\n"
            )

        suggested_qs = []
        col_names = ", ".join(list(schema_profile["columns"].keys())[:10])
        profile = {
            "schema_profile": schema_profile,
            "auto_semantic": auto_semantic,
            "verified_queries": verified_queries,
            "enriched_context": enriched_context,
            "schema_summary": (
                f"Table: {table_name}, "
                f"{schema_profile['total_rows']} rows, "
                f"columns: {col_names}"
            ),
            "suggested_questions": suggested_qs,
            "table_name": table_name,
        }

        session.semantic._cache[table_name] = profile
        session.profiles[table_name] = profile
        if table_name not in session.table_names:
            session.table_names.append(table_name)

        row_count = schema_profile["total_rows"]
        col_count = len(schema_profile["columns"])
        all_tables.append({
            "name": table_name,
            "filename": filename,
            "rows": row_count,
            "columns": col_count,
            "reused": False,
        })

        session.uploaded_file_cache.setdefault(cache_key, []).append(table_name)
        session.uploaded_filename_tables.setdefault(filename.lower(), []).append(table_name)

        _emit_upload_progress(
            progress_cb,
            table_end,
            "semantic_embedding",
            f"Data understanding complete for {table_name}",
            filename=filename,
            table_name=table_name,
        )

    if not all_tables:
        print(
            f"[upload] failed session={session_id} elapsed_ms={round((time.time() - upload_start) * 1000)} "
            f"errors={len(all_errors)}"
        )
        return {
            "success": False,
            "message": "; ".join(all_errors) if all_errors else "No tables loaded",
            "errors": all_errors,
        }

    _emit_upload_progress(
        progress_cb,
        98,
        "semantic_embedding",
        "Finalizing dataset context",
    )

    # Suggestions are deferred to query-time to keep upload fast.
    unique_suggestions: list[str] = []

    reused_count = sum(1 for t in all_tables if t.get("reused"))
    loaded_count = len(all_tables) - reused_count

    if loaded_count > 0 and reused_count == 0:
        msg = f"Loaded {loaded_count} table(s)"
    elif reused_count > 0 and loaded_count == 0:
        msg = f"Ready — {reused_count} table(s) from cache (data unchanged)"
    else:
        msg = f"Loaded {loaded_count} new + {reused_count} cached table(s)"

    first = all_tables[0]
    print(
        f"[upload] success session={session_id} loaded={loaded_count} reused={reused_count} "
        f"elapsed_ms={round((time.time() - upload_start) * 1000)}"
    )

    _emit_upload_progress(
        progress_cb,
        100,
        "ready",
        "Data is ready. You can now query.",
    )

    return {
        "success": True,
        "message": msg,
        "tables": all_tables,
        "reused_count": reused_count,
        "loaded_count": loaded_count,
        "filename": first["filename"],
        "rows": first["rows"],
        "columns": first["columns"],
        "suggested_questions": unique_suggestions,
        "suggestions_deferred": True,
        "fast_mode": fast_mode,
        "errors": all_errors,
    }


@app.post("/api/upload")
async def upload(
    files: List[UploadFile] = File(...),
    session_id: str = Form(...),
    fast_mode: bool = Form(default=FAST_UPLOAD_MODE_DEFAULT),
):
    """
    Upload one or more data files.
    Files are loaded into in-memory DuckDB tables and NOT saved to disk.
    """
    return await _run_upload_pipeline(files, session_id, fast_mode, progress_cb=None)


@app.post("/api/upload/stream")
async def upload_stream(
    files: List[UploadFile] = File(...),
    session_id: str = Form(...),
    fast_mode: bool = Form(default=FAST_UPLOAD_MODE_DEFAULT),
):
    """Stream upload pipeline progress as SSE, then emit final upload result."""

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    last_progress = {
        "percent": 1,
        "stage": "dataset_uploaded",
        "message": "Upload request received",
        "filename": None,
        "table_name": None,
    }

    def emit_progress(payload: dict):
        nonlocal last_progress
        last_progress = {
            "percent": payload.get("percent", last_progress["percent"]),
            "stage": payload.get("stage", last_progress["stage"]),
            "message": payload.get("message", last_progress["message"]),
            "filename": payload.get("filename", last_progress.get("filename")),
            "table_name": payload.get("table_name", last_progress.get("table_name")),
        }
        loop.call_soon_threadsafe(queue.put_nowait, ("progress", payload))

    async def run_upload():
        try:
            result = await _run_upload_pipeline(files, session_id, fast_mode, progress_cb=emit_progress)
            loop.call_soon_threadsafe(queue.put_nowait, ("result", result))
        except Exception as e:
            import traceback
            print(f"[upload_stream] pipeline error:\n{traceback.format_exc()}")
            loop.call_soon_threadsafe(queue.put_nowait, ("error", str(e)))

    async def generate():
        task = asyncio.create_task(run_upload())
        while True:
            try:
                kind, payload = await asyncio.wait_for(
                    queue.get(), timeout=float(UPLOAD_STREAM_HEARTBEAT_SECONDS)
                )
            except asyncio.TimeoutError:
                if task.done():
                    if task.exception():
                        yield _sse({"type": "error", "message": _friendly_runtime_error(task.exception())})
                        yield "data: [DONE]\n\n"
                        break
                    # Task might be done while terminal event is still queued.
                    continue

                keepalive_payload = dict(last_progress)
                keepalive_payload["message"] = (
                    f"{keepalive_payload.get('message', 'Processing dataset')}. "
                    "Still processing — large JSON files can take a few minutes."
                )
                keepalive_payload["keepalive"] = True
                yield _sse({"type": "upload_progress", **keepalive_payload})
                continue

            if kind == "progress":
                yield _sse({"type": "upload_progress", **payload})
            elif kind == "result":
                yield _sse({"type": "upload_result", "data": payload})
                yield "data: [DONE]\n\n"
                break
            else:
                yield _sse({"type": "error", "message": payload})
                yield "data: [DONE]\n\n"
                break
        await task

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/query/stream")
async def query_stream(req: QueryRequest):
    session = _sessions.get(req.session_id)

    if not session.has_data:
        async def _no_data():
            yield _sse({"type": "error", "message": "No data loaded. Please upload a file first."})
            yield "data: [DONE]\n\n"
        return StreamingResponse(_no_data(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async def generate():
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def emit(step_type: str, message: str, detail: str | None = None):
            sid, start_sse = _thinking(step_type, message, detail)
            loop.call_soon_threadsafe(queue.put_nowait, (sid, start_sse, _done(sid)))

        async def run_pipeline():
            try:
                result = await asyncio.to_thread(
                    _run_query_pipeline, req.question, req.session_id, emit
                )
                loop.call_soon_threadsafe(queue.put_nowait, ("__result__", result, None))
            except Exception as e:
                import traceback
                print(f"[stream] pipeline error:\n{traceback.format_exc()}")
                loop.call_soon_threadsafe(queue.put_nowait, ("__error__", _friendly_runtime_error(e), None))

        task = asyncio.create_task(run_pipeline())

        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=120.0)
            except asyncio.TimeoutError:
                yield _sse({"type": "error", "message": "Pipeline timed out"})
                break

            sid, payload, done_sse = item

            if sid == "__result__":
                query_result = _to_query_result(req.question, payload)
                yield _sse({"type": "result", "data": query_result})
                yield "data: [DONE]\n\n"
                break
            elif sid == "__error__":
                yield _sse({"type": "error", "message": payload})
                yield "data: [DONE]\n\n"
                break
            else:
                yield payload
                yield done_sse

        await task

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/query")
async def query_direct(req: QueryRequest):
    """Non-streaming fallback."""
    session = _sessions.get(req.session_id)
    if not session.has_data:
        raise HTTPException(status_code=400, detail="No data loaded. Please upload a file first.")

    def noop_emit(*_): pass
    try:
        resp = await asyncio.to_thread(_run_query_pipeline, req.question, req.session_id, noop_emit)
        return _to_query_result(req.question, resp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=_friendly_runtime_error(e))


@app.post("/api/session/clear")
def session_clear(req: ClearRequest):
    _sessions.clear(req.session_id)
    _cache.clear()
    return {"ok": True}


@app.post("/api/session/remove-table")
def session_remove_table(req: RemoveTableRequest):
    session = _sessions.get(req.session_id)
    removed = session.remove_table(req.table_name)
    if removed:
        _cache.clear()
    return {
        "ok": True,
        "removed": removed,
        "remaining_tables": len(session.table_names),
    }
