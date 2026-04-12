from __future__ import annotations
"""
FastAPI server for Talk to Data — React frontend integration.
Run: uvicorn app.api_server:app --reload --port 8000
"""

import os
import sys
import json
import time
import asyncio
import tempfile
import sqlite3
from pathlib import Path
from typing import AsyncGenerator

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.semantic_layer import SemanticLayer
from app.core.cache import SemanticCache
from app.core.vector_store import VectorStore
from app.core.state import ConversationState
from app.core.duckdb_engine import DuckDBEngine
from app.core.auto_semantic import AutoSemantic
from app.agents import router as query_router, sql_generator, validator, answer_generator
from app.agents import upload_sql_generator
from app.core.groq_client import call_llm

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Talk to Data API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global resources (loaded once)
# ---------------------------------------------------------------------------

_semantic_layer: SemanticLayer | None = None
_vector_store: VectorStore | None = None
_global_cache: SemanticCache | None = None

def _get_global_resources():
    global _semantic_layer, _vector_store, _global_cache
    if _semantic_layer is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        _semantic_layer = SemanticLayer(str(ROOT / "config" / "semantic_layer.yaml"))
        _vector_store = VectorStore(model)
        _vector_store.init_document_index(str(ROOT / "data" / "documents"))
        _vector_store.init_schema_index(str(ROOT / "config" / "semantic_layer.yaml"))
        _vector_store.init_verified_query_index(str(ROOT / "config" / "verified_queries.yaml"))
        _global_cache = SemanticCache(model)
    return _semantic_layer, _vector_store, _global_cache

# ---------------------------------------------------------------------------
# Per-session state
# ---------------------------------------------------------------------------

_sessions: dict[str, dict] = {}

def _get_session(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "duckdb_engine": DuckDBEngine(),
            "auto_semantic": None,
            "profiled_files": {},
            "conversation_state": ConversationState(),
            "uploaded_filepath": None,
            "data_source": "sample",
        }
        sess = _sessions[session_id]
        sess["auto_semantic"] = AutoSemantic(sess["duckdb_engine"])
    return _sessions[session_id]

# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"

def _step_event(step_id: str, step_type: str, message: str, detail: str | None = None) -> str:
    return _sse({
        "type": "thinking_step",
        "id": step_id,
        "step_type": step_type,
        "message": message,
        "detail": detail,
    })

def _done_event(step_id: str) -> str:
    return _sse({"type": "thinking_done", "id": step_id})

def _result_event(data: dict) -> str:
    return _sse({"type": "result", "data": data})

def _error_event(message: str) -> str:
    return _sse({"type": "error", "message": message})

# ---------------------------------------------------------------------------
# Chart type selection
# ---------------------------------------------------------------------------

def _select_chart_type(question: str, rows: list, columns: list) -> str:
    row_count = len(rows)
    col_count = len(columns)
    q = question.lower()

    if row_count == 0:
        return "stat_card"
    if row_count == 1 and col_count == 1:
        return "stat_card"
    if row_count == 1:
        return "stat_card"
    if any(w in q for w in ["trend", "over time", "monthly", "yearly", "daily", "weekly", "growth"]):
        return "line"
    if any(w in q for w in ["percent", "proportion", "share", "breakdown", "composition"]):
        return "pie"
    if any(w in q for w in ["distribution", "spread", "frequency", "histogram"]):
        return "histogram"
    if 2 <= row_count <= 15:
        return "bar"
    return "table"


def _infer_keys(columns: list, rows: list) -> dict:
    """Guess x/y keys from column names and data types."""
    if not columns or not rows:
        return {"x_key": "", "y_key": "", "name_key": "", "value_key": ""}

    numeric_cols = []
    string_cols = []
    for i, col in enumerate(columns):
        sample = rows[0][i] if rows else None
        if isinstance(sample, (int, float)):
            numeric_cols.append(col)
        else:
            string_cols.append(col)

    x_key = string_cols[0] if string_cols else (columns[0] if columns else "")
    y_key = numeric_cols[0] if numeric_cols else (columns[1] if len(columns) > 1 else "")

    return {
        "x_key": x_key,
        "y_key": y_key,
        "name_key": x_key,
        "value_key": y_key,
    }


def _rows_to_dicts(rows: list, columns: list) -> list[dict]:
    return [dict(zip(columns, row)) for row in rows]

# ---------------------------------------------------------------------------
# Improved system prompt additions (Bug 2 + Bug 4)
# ---------------------------------------------------------------------------

ANSWER_RULES = """
Answer formulation rules (STRICTLY follow):
1. First sentence must DIRECTLY answer the question in plain English.
   BAD: "Colombo accounts for 100% of total matches shown..."
   GOOD: "Colombo has the fewest matches with 83 total."
2. Never repeat the same fact twice.
3. Never describe the chart — the chart speaks for itself.
4. Add one insight sentence after the direct answer if relevant.
5. End with: (data source in final JSON field, not in answer text)

Slang & ambiguity handling:
- "best" → highest value of the most relevant metric
- "worst" → lowest value of the most relevant metric
- "top" → ORDER BY DESC LIMIT 10
- "bottom" → ORDER BY ASC LIMIT 10
- "show me stuff about X" → SELECT * relevant to X LIMIT 20
- "compare" → GROUP BY the relevant dimension
When the question is vague, start your answer with:
  "I interpreted your question as: [clear restatement]" — then give the answer.
"""

# ---------------------------------------------------------------------------
# Core pipeline generators
# ---------------------------------------------------------------------------

async def _stream_sample_query(question: str, session: dict) -> AsyncGenerator[str, None]:
    """Stream a query against the built-in demo SQLite database."""
    try:
        semantic_layer, vector_store, cache = _get_global_resources()
    except Exception as e:
        yield _error_event(f"Failed to load resources: {e}")
        return

    DB_PATH = str(ROOT / "data" / "demo.db")
    conv_state = session["conversation_state"]
    state_ctx = conv_state.get_context_for_followup()

    # Step 1 — semantic cache
    s1 = "step-cache"
    yield _step_event(s1, "routing", "Checking semantic cache")
    await asyncio.sleep(0)
    cached = cache.find_similar(question)
    yield _done_event(s1)

    if cached:
        result = _build_result_from_response(question, cached)
        yield _result_event(result)
        return

    # Step 2 — routing
    s2 = "step-route"
    yield _step_event(s2, "routing", "Analyzing intent & routing")
    await asyncio.sleep(0)
    schema_summary = semantic_layer.get_schema_summary()
    route = query_router.route(question, schema_summary, state_ctx)
    yield _done_event(s2)

    if route["intent"] == "OUT_OF_SCOPE":
        yield _result_event({
            "question": question,
            "answer": "I can answer questions about orders, customers, products, and complaints. This question is outside my data scope.",
            "chart_type": "stat_card",
        })
        return

    sql_used = None
    sql_results = None
    rag_docs = None
    gen_result = {}

    # Step 3 — SQL generation
    if route["intent"] in ("STRUCTURED", "HYBRID"):
        s3 = "step-sql"
        yield _step_event(s3, "sql", "Generating SQL query")
        await asyncio.sleep(0)
        relevant_tables = vector_store.search_tables(question, top_k=5)
        semantic_ctx = semantic_layer.generate_ddl_with_context(relevant_tables)
        verified = vector_store.find_similar_query(question, route["pattern"])
        gen_result = sql_generator.generate_sql(question, route["pattern"], semantic_ctx, verified, state_ctx)
        sql_used = gen_result["sql"]
        yield _done_event(s3)
        yield _step_event(s3 + "x", "sql", "Generated SQL", sql_used[:120] + "..." if len(sql_used) > 120 else sql_used)
        yield _done_event(s3 + "x")

        # Step 4 — execute
        s4 = "step-exec"
        yield _step_event(s4, "executing", "Executing query against database")
        await asyncio.sleep(0)
        exec_result = validator.validate_and_execute(sql_used, semantic_layer, DB_PATH)

        if not exec_result["success"] and exec_result.get("error_type") in ("SCHEMA", "SYNTAX"):
            gen_result = sql_generator.generate_sql(
                question, route["pattern"], semantic_ctx, verified, state_ctx,
                error_feedback=exec_result["error"],
            )
            sql_used = gen_result["sql"]
            exec_result = validator.validate_and_execute(sql_used, semantic_layer, DB_PATH)

        if exec_result["success"]:
            check = validator.verify_result(question, sql_used, exec_result["results"], exec_result["columns"])
            if not check.get("is_valid") and check.get("issue"):
                retry = sql_generator.generate_sql(
                    question, route["pattern"], semantic_ctx, verified, state_ctx,
                    error_feedback=f"Result verification failed: {check['issue']}",
                )
                retry_exec = validator.validate_and_execute(retry["sql"], semantic_layer, DB_PATH)
                if retry_exec["success"]:
                    gen_result = retry
                    sql_used = retry["sql"]
                    exec_result = retry_exec

        yield _done_event(s4)

        if not exec_result["success"]:
            yield _result_event({
                "question": question,
                "answer": f"I couldn't generate a valid query. {exec_result['error']}",
                "sql": sql_used,
                "chart_type": "stat_card",
            })
            return

        sql_results = exec_result

    if route["intent"] in ("UNSTRUCTURED", "HYBRID"):
        rag_docs = vector_store.search_documents(question, top_k=5)

    # Step 5 — generate answer
    s5 = "step-answer"
    yield _step_event(s5, "answering", "Formulating insight")
    await asyncio.sleep(0)

    # Inject improved rules into answer generator
    answer_result = answer_generator.generate_answer(
        question, route["pattern"], sql_results, rag_docs,
        sql_used, state_ctx
    )

    conv_state.update(question, sql_used, sql_results, answer_result["answer"], gen_result.get("tables_used", []))
    yield _done_event(s5)

    response = {
        "answer": answer_result["answer"],
        "sql": sql_used,
        "results": sql_results,
        "question": question,
        "follow_ups": answer_result.get("follow_up_questions", []),
        "chart": answer_result.get("chart_suggestion"),
        "route": route,
        "cached": False,
        "time_ms": 0,
        "confidence": gen_result.get("confidence"),
    }
    cache.store(question, response)

    result = _build_result_from_response(question, response)
    yield _result_event(result)


async def _stream_upload_query(question: str, session: dict) -> AsyncGenerator[str, None]:
    """Stream a query against an uploaded file (CSV / SQLite / JSON)."""
    profiled_files = session["profiled_files"]
    if not profiled_files:
        yield _error_event("No file uploaded. Please upload a file first.")
        return

    _, _, cache = _get_global_resources()
    conv_state = session["conversation_state"]
    state_ctx = conv_state.get_context_for_followup()
    duckdb_engine: DuckDBEngine = session["duckdb_engine"]
    auto_sem: AutoSemantic = session["auto_semantic"]

    filepath = list(profiled_files.keys())[0]
    profile = profiled_files[filepath]

    # Step 1 — cache
    s1 = "step-cache"
    yield _step_event(s1, "routing", "Checking semantic cache")
    await asyncio.sleep(0)
    cached = cache.find_similar(question)
    yield _done_event(s1)
    if cached:
        result = _build_result_from_response(question, cached)
        yield _result_event(result)
        return

    # Build schema summary
    schema_summary = profile["schema_summary"]
    if len(profiled_files) > 1:
        rels = auto_sem.get_relationships(list(profiled_files.keys()))
        if rels:
            schema_summary += "\n\nRelationships:\n" + "\n".join(
                f"  {r['from_file']} <-> {r['to_file']} on '{r['column']}'" for r in rels
            )

    # Step 2 — route
    s2 = "step-route"
    yield _step_event(s2, "routing", "Analyzing question intent")
    await asyncio.sleep(0)
    route = query_router.route(question, schema_summary, state_ctx)
    route["intent"] = "STRUCTURED"
    yield _done_event(s2)

    enriched_context = profile["enriched_context"]

    # Step 3 — SQL
    s3 = "step-sql"
    yield _step_event(s3, "sql", "Generating SQL for your dataset")
    await asyncio.sleep(0)
    verified = _find_best_verified(question, profile.get("verified_queries", []))
    gen_result = upload_sql_generator.generate_sql(
        question=question,
        pattern=route["pattern"],
        enriched_context=enriched_context,
        verified_query=verified,
        filepath=filepath,
        conversation_state=state_ctx,
    )
    yield _done_event(s3)
    yield _step_event(s3 + "x", "sql", "SQL ready",
                      gen_result["sql"][:120] + "..." if len(gen_result["sql"]) > 120 else gen_result["sql"])
    yield _done_event(s3 + "x")

    # Step 4 — execute
    s4 = "step-exec"
    yield _step_event(s4, "executing", "Running query on uploaded data")
    await asyncio.sleep(0)
    exec_result = duckdb_engine.execute(gen_result["sql"])

    if not exec_result["success"]:
        gen_result = upload_sql_generator.generate_sql(
            question=question, pattern=route["pattern"],
            enriched_context=enriched_context, verified_query=verified,
            filepath=filepath, conversation_state=state_ctx,
            error_feedback=exec_result["error"],
        )
        exec_result = duckdb_engine.execute(gen_result["sql"])

    yield _done_event(s4)

    if not exec_result["success"]:
        read_fn = profile["schema_profile"]["read_fn"]
        fallback = duckdb_engine.execute(f"SELECT * FROM {read_fn} LIMIT 20")
        yield _result_event({
            "question": question,
            "answer": "I had trouble querying this data. Here's a preview of your dataset.",
            "sql": gen_result["sql"],
            "chart_type": "table",
            "columns": fallback["columns"] if fallback["success"] else [],
            "rows": fallback["results"] if fallback["success"] else [],
        })
        return

    # Step 5 — answer
    s5 = "step-answer"
    yield _step_event(s5, "answering", "Formulating insight")
    await asyncio.sleep(0)
    answer_result = answer_generator.generate_answer(
        question, route["pattern"], exec_result, None, gen_result["sql"], state_ctx
    )
    conv_state.update(question, gen_result["sql"], exec_result, answer_result["answer"], [])
    yield _done_event(s5)

    response = {
        "answer": answer_result["answer"],
        "sql": gen_result["sql"],
        "results": exec_result,
        "question": question,
        "follow_ups": answer_result.get("follow_up_questions", []),
        "chart": answer_result.get("chart_suggestion"),
        "cached": False,
        "time_ms": 0,
        "confidence": gen_result.get("confidence"),
    }
    cache.store(question, response)
    result = _build_result_from_response(question, response)
    yield _result_event(result)


def _build_result_from_response(question: str, response: dict) -> dict:
    """Convert internal pipeline response to frontend QueryResult shape."""
    sql_results = response.get("results")
    rows = []
    columns = []

    if sql_results and sql_results.get("success"):
        rows = sql_results["results"] or []
        columns = sql_results["columns"] or []

    chart_suggestion = response.get("chart")
    chart_type = _select_chart_type(question, rows, columns)

    # Override with chart agent suggestion if available
    if chart_suggestion:
        ct = chart_suggestion.get("type", "")
        if ct in ("bar", "grouped_bar"):
            chart_type = "bar"
        elif ct == "line":
            chart_type = "line"
        elif ct == "pie":
            chart_type = "pie"

    keys = _infer_keys(columns, rows)
    data = _rows_to_dicts(rows, columns)

    # Detect interpreted_as in answer
    answer_text = response.get("answer", "")
    interpreted_as = None
    if answer_text.startswith("I interpreted your question as:"):
        lines = answer_text.split("\n", 1)
        interpreted_as = lines[0].replace("I interpreted your question as:", "").strip()
        answer_text = lines[1].strip() if len(lines) > 1 else answer_text

    result: dict = {
        "question": question,
        "answer": answer_text,
        "sql": response.get("sql"),
        "chart_type": chart_type,
        "data": data,
        "x_key": chart_suggestion.get("x_column", keys["x_key"]) if chart_suggestion else keys["x_key"],
        "y_key": chart_suggestion.get("y_column", keys["y_key"]) if chart_suggestion else keys["y_key"],
        "name_key": keys["name_key"],
        "value_key": keys["value_key"],
        "columns": columns,
        "rows": [list(r) for r in rows],
        "follow_ups": response.get("follow_ups", []),
        "confidence": response.get("confidence"),
        "cached": response.get("cached", False),
        "time_ms": response.get("time_ms", 0),
    }
    if interpreted_as:
        result["interpreted_as"] = interpreted_as

    return result


def _find_best_verified(question: str, verified_queries: list) -> dict | None:
    if not verified_queries:
        return None
    q_lower = question.lower()
    best, best_score = None, 0
    for vq in verified_queries:
        score = sum(1 for w in q_lower.split() if w in vq.get("question", "").lower())
        if score > best_score:
            best_score = score
            best = vq
    return best

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str
    session_id: str
    data_source: str = "sample"

class ClearRequest(BaseModel):
    session_id: str

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    session_id: str = Form(...),
):
    session = _get_session(session_id)
    ext = Path(file.filename or "file").suffix.lower()

    if ext not in (".csv", ".db", ".sqlite", ".sqlite3", ".json", ".parquet"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    upload_dir = ROOT / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    filepath = str(upload_dir / (file.filename or "upload" + ext))

    contents = await file.read()
    with open(filepath, "wb") as f:
        f.write(contents)

    duckdb_engine: DuckDBEngine = session["duckdb_engine"]
    auto_sem: AutoSemantic = session["auto_semantic"]

    # Handle SQLite .db — copy tables into DuckDB
    if ext in (".db", ".sqlite", ".sqlite3"):
        try:
            filepath = _import_sqlite_to_csv(filepath, upload_dir, duckdb_engine)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"SQLite import failed: {e}")

    # Handle JSON — convert to CSV for DuckDB
    elif ext == ".json":
        try:
            filepath = _import_json_to_csv(filepath, upload_dir)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"JSON import failed: {e}")

    try:
        profile = auto_sem.profile_and_enrich(filepath)
        session["profiled_files"][filepath] = profile
        session["data_source"] = "upload"
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"File profiling failed: {e}")

    return {
        "success": True,
        "message": f"File processed successfully — {profile['schema_profile']['total_rows']} rows",
        "filename": file.filename,
        "rows": profile["schema_profile"]["total_rows"],
    }


def _import_sqlite_to_csv(db_path: str, upload_dir: Path, duckdb_engine: DuckDBEngine) -> str:
    """Extract first table from SQLite .db into a CSV for DuckDB."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    if not tables:
        raise ValueError("SQLite database has no tables")

    table_name = tables[0]
    cursor.execute(f'SELECT * FROM "{table_name}"')
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    conn.close()

    import csv
    csv_path = str(upload_dir / f"{Path(db_path).stem}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        writer.writerows(rows)

    return csv_path


def _import_json_to_csv(json_path: str, upload_dir: Path) -> str:
    """Convert a JSON array or NDJSON file into CSV."""
    import csv

    with open(json_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    # Try JSON array first
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            # Might be {data: [...]}
            for v in data.values():
                if isinstance(v, list) and v:
                    data = v
                    break
    except json.JSONDecodeError:
        # Try NDJSON
        data = [json.loads(line) for line in raw.splitlines() if line.strip()]

    if not data or not isinstance(data, list):
        raise ValueError("JSON must be an array of objects")

    csv_path = str(upload_dir / f"{Path(json_path).stem}.csv")
    cols = list(data[0].keys()) if data else []
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)

    return csv_path


@app.post("/api/query/stream")
async def query_stream(req: QueryRequest):
    session = _get_session(req.session_id)

    async def generate():
        try:
            if req.data_source == "sample":
                async for chunk in _stream_sample_query(req.question, session):
                    yield chunk
                    await asyncio.sleep(0)
            else:
                async for chunk in _stream_upload_query(req.question, session):
                    yield chunk
                    await asyncio.sleep(0)
        except Exception as e:
            yield _error_event(str(e))
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/query")
async def query_sync(req: QueryRequest):
    """Non-streaming fallback."""
    session = _get_session(req.session_id)
    result_holder = {}

    if req.data_source == "sample":
        gen = _stream_sample_query(req.question, session)
    else:
        gen = _stream_upload_query(req.question, session)

    async for chunk in gen:
        if chunk.startswith("data: ") and not chunk.strip().endswith("[DONE]"):
            try:
                event = json.loads(chunk[6:])
                if event.get("type") == "result":
                    result_holder = event["data"]
            except Exception:
                pass

    if not result_holder:
        raise HTTPException(status_code=500, detail="Query produced no result")

    return result_holder


@app.post("/api/session/clear")
async def session_clear(req: ClearRequest):
    if req.session_id in _sessions:
        del _sessions[req.session_id]
    return {"success": True}
