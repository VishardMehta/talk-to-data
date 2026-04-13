"""
FastAPI backend for the React frontend.

Endpoints (all under /api):
  GET  /health
  POST /upload          — multipart file upload
  POST /query/stream    — SSE streaming query
  POST /query           — non-streaming fallback
  POST /session/clear   — reset session state
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ── Shared backend resources (loaded once at startup) ──────────────────────
from sentence_transformers import SentenceTransformer
from app.core.cache import SemanticCache
from app.core.query_classifier import classify_query
from app.agents import router, answer_generator
from app.agents import upload_sql_generator
from api.session import SessionManager
from api.chart_converter import to_chart_payload

print("[server] Loading sentence transformer model…")
_model = SentenceTransformer("all-MiniLM-L6-v2")

_cache = SemanticCache(_model)
_sessions = SessionManager()

# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(title="Talk to Data API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/response models ────────────────────────────────────────────────
class QueryRequest(BaseModel):
    question: str
    session_id: str
    data_source: str = "csv"   # "csv" | "database" | "json"


class ClearRequest(BaseModel):
    session_id: str


# ── Helper: emit SSE line ──────────────────────────────────────────────────
def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _thinking(step_type: str, message: str, detail: str | None = None) -> tuple[str, str]:
    sid = str(uuid.uuid4())[:8]
    return sid, _sse({"type": "thinking_step", "id": sid, "step_type": step_type,
                      "message": message, "detail": detail})


def _done(sid: str) -> str:
    return _sse({"type": "thinking_done", "id": sid})


# ── Core pipeline (sync — runs in thread) ─────────────────────────────────
def _find_best_verified(question: str, verified_queries: list) -> dict | None:
    if not verified_queries:
        return None
    q_lower = question.lower()
    best, best_score = None, 0
    for vq in verified_queries:
        score = sum(1 for w in q_lower.split() if w in vq.get("question", "").lower())
        if score > best_score:
            best_score, best = score, vq
    return best


def _run_upload_pipeline(question: str, session_id: str, emit) -> dict:
    """Run the upload (DuckDB) pipeline."""
    session = _sessions.get(session_id)
    start = time.time()

    if not session.profiled_files:
        print(f"[upload_pipeline] ERROR: no profiled files for session {session_id}")
        return {"answer": "Please upload a file first.", "cached": False, "time_ms": 0}

    filepath = list(session.profiled_files.keys())[0]
    profile = session.profiled_files[filepath]
    total_rows = profile["schema_profile"]["total_rows"]
    col_names = list(profile["schema_profile"]["columns"].keys())
    print(f"[upload_pipeline] file={filepath!r} rows={total_rows} cols={col_names}")

    classification = classify_query(question)
    query_type = classification["query_type"]
    print(f"[upload_pipeline] query_type={query_type} question={question!r}")

    cached = _cache.find_similar(question, threshold=classification["cache_threshold"],
                                 query_type=query_type)
    if cached:
        print(f"[upload_pipeline] cache hit")
        if cached.get("answer"):
            session.conversation_state.update(
                question, cached.get("sql"), cached.get("results"),
                cached.get("answer", ""), cached.get("tables_used", []))
        return {**cached, "cached": True, "time_ms": (time.time() - start) * 1000}

    state_ctx = session.conversation_state.get_context_for_followup()

    emit("routing", "Classifying your question")
    route = router.route(question, profile["schema_summary"], state_ctx)
    route["intent"] = "STRUCTURED"
    print(f"[upload_pipeline] route pattern={route.get('pattern')}")

    emit("sql", "Generating SQL query for your dataset")
    verified = _find_best_verified(question, profile["verified_queries"])
    gen_result = upload_sql_generator.generate_sql(
        question=question, pattern=route["pattern"],
        enriched_context=profile["enriched_context"],
        verified_query=verified, filepath=filepath,
        conversation_state=state_ctx)

    sql_used = gen_result["sql"]
    print(f"[upload_pipeline] generated SQL: {sql_used!r}")

    emit("executing", "Running the query")
    exec_result = session.duckdb_engine.execute(sql_used)
    print(f"[upload_pipeline] exec success={exec_result['success']} "
          f"rows={len(exec_result.get('results') or [])} "
          f"cols={exec_result.get('columns')} "
          f"error={exec_result.get('error')}")

    if not exec_result["success"]:
        print(f"[upload_pipeline] retry after error: {exec_result['error']}")
        gen_result = upload_sql_generator.generate_sql(
            question=question, pattern=route["pattern"],
            enriched_context=profile["enriched_context"],
            verified_query=verified, filepath=filepath,
            conversation_state=state_ctx, error_feedback=exec_result["error"])
        sql_used = gen_result["sql"]
        print(f"[upload_pipeline] retry SQL: {sql_used!r}")
        exec_result = session.duckdb_engine.execute(sql_used)
        print(f"[upload_pipeline] retry exec success={exec_result['success']} "
              f"rows={len(exec_result.get('results') or [])} "
              f"error={exec_result.get('error')}")

    if not exec_result["success"]:
        read_fn = profile["schema_profile"]["read_fn"]
        print(f"[upload_pipeline] both attempts failed, returning preview")
        fallback = session.duckdb_engine.execute(f"SELECT * FROM {read_fn} LIMIT 20")
        return {"answer": "Had trouble querying this data. Here's a preview.",
                "sql": sql_used, "results": fallback if fallback["success"] else None,
                "error": True, "time_ms": (time.time() - start) * 1000}

    row_count = len(exec_result.get("results") or [])
    print(f"[upload_pipeline] final result: {row_count} rows, passing to answer_generator")

    emit("answering", "Generating answer")
    # Bug 9: pass dataset context so answer uses correct domain language
    table_name = profile["schema_profile"]["table_name"]
    table_desc = profile.get("auto_semantic", {}).get("table_description", "")
    dataset_context = f"Table: {table_name}\nDescription: {table_desc}\nColumns: {', '.join(col_names[:15])}"
    answer_result = answer_generator.generate_answer(
        question, route["pattern"], exec_result, None, sql_used, state_ctx,
        query_type=query_type, dataset_context=dataset_context)

    session.conversation_state.update(
        question, sql_used, exec_result, answer_result["answer"], [])

    elapsed = (time.time() - start) * 1000
    response = {
        "answer": answer_result["answer"],
        "sql": sql_used,
        "results": exec_result,
        "confidence": gen_result.get("confidence"),
        "follow_ups": answer_result.get("follow_up_questions", []),
        "route": route,
        "cached": False,
        "time_ms": elapsed,
    }
    _cache.store(question, response, query_type=query_type)
    return response


# ── Convert pipeline response → QueryResult (React type) ──────────────────
def _to_query_result(question: str, resp: dict) -> dict:
    sql_results = resp.get("results")
    pattern = resp.get("pattern", "GENERAL") or "GENERAL"
    chart_payload = {}

    if sql_results and sql_results.get("success") and sql_results.get("results"):
        chart_payload = to_chart_payload(
            sql_results["results"], sql_results["columns"], pattern, question)

    return {
        "question": question,
        "answer": resp.get("answer", ""),
        "sql": resp.get("sql"),
        "interpreted_as": resp.get("route", {}).get("reasoning"),
        "follow_ups": resp.get("follow_ups") or resp.get("follow_up_questions", []),
        "confidence": resp.get("confidence"),
        "cached": resp.get("cached", False),
        "time_ms": resp.get("time_ms"),
        **chart_payload,
    }


# ── Routes ─────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0"}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), session_id: str = Form(...)):
    session = _sessions.get(session_id)
    upload_dir = ROOT / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    filepath = str(upload_dir / file.filename)
    contents = await file.read()
    with open(filepath, "wb") as f:
        f.write(contents)

    try:
        profile = await asyncio.to_thread(
            session.auto_semantic.profile_and_enrich, filepath)
        session.profiled_files[filepath] = profile
        session.app_mode = "upload"

        # Bug 10 / Bug 4: generate suggested questions from auto_semantic data
        auto_sem = profile.get("auto_semantic", {})
        suggested_qs = auto_sem.get("suggested_questions", [])
        if not suggested_qs:
            # fallback: use verified_queries questions
            suggested_qs = [vq["question"] for vq in profile.get("verified_queries", [])[:5]]

        return {
            "success": True,
            "message": f"Uploaded {file.filename}",
            "filename": file.filename,
            "rows": profile["schema_profile"]["total_rows"],
            "columns": len(profile["schema_profile"]["columns"]),
            "suggested_questions": suggested_qs[:5],
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/api/query/stream")
async def query_stream(req: QueryRequest):
    requested_upload_source = req.data_source in ("csv", "database", "json")
    session = _sessions.get(req.session_id)
    if not requested_upload_source:
        async def unsupported_source_error():
            yield _sse({
                "type": "error",
                "message": "Only uploaded datasets are supported. Use data_source: csv, database, or json.",
            })
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            unsupported_source_error(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if not session.profiled_files:
        async def upload_missing_error():
            yield _sse({
                "type": "error",
                "message": "No uploaded dataset found for this session. Please upload your file again before querying.",
            })
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            upload_missing_error(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def generate():
        loop = asyncio.get_event_loop()
        _queue: asyncio.Queue = asyncio.Queue()

        def emit(step_type: str, message: str, detail: str | None = None):
            sid, start_sse = _thinking(step_type, message, detail)
            # Thread-safe: schedule put_nowait on the event loop from the pipeline thread
            loop.call_soon_threadsafe(_queue.put_nowait, (sid, start_sse, _done(sid)))

        print(f"[stream] session={req.session_id} source={req.data_source} "
              f"is_upload=True question={req.question[:80]!r}")

        async def run_pipeline():
            try:
                result = await asyncio.to_thread(_run_upload_pipeline, req.question, req.session_id, emit)
                loop.call_soon_threadsafe(_queue.put_nowait, ("__result__", result, None))
            except Exception as e:
                import traceback
                print(f"[stream] pipeline error: {traceback.format_exc()}")
                loop.call_soon_threadsafe(_queue.put_nowait, ("__error__", str(e), None))

        task = asyncio.create_task(run_pipeline())

        # Drain the queue, forwarding events as they arrive
        while True:
            try:
                item = await asyncio.wait_for(_queue.get(), timeout=120.0)
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

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/query")
async def query_direct(req: QueryRequest):
    """Non-streaming fallback."""
    session = _sessions.get(req.session_id)
    if req.data_source not in ("csv", "database", "json"):
        raise HTTPException(
            status_code=400,
            detail="Only uploaded datasets are supported. Use data_source: csv, database, or json.",
        )

    if not session.profiled_files:
        raise HTTPException(
            status_code=400,
            detail="No uploaded dataset found for this session. Please upload your file again before querying.",
        )

    def noop_emit(*_): pass

    try:
        resp = await asyncio.to_thread(_run_upload_pipeline, req.question, req.session_id, noop_emit)
        return _to_query_result(req.question, resp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/session/clear")
def session_clear(req: ClearRequest):
    _sessions.clear(req.session_id)
    _cache.clear()
    return {"ok": True}
