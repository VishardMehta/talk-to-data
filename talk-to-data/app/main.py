"""
Talk to Data — Streamlit Chat UI
Entry point: streamlit run app/main.py
"""

import os
import sys
import time
from pathlib import Path

# Make sure project root is on the path regardless of cwd
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.core.semantic_layer import SemanticLayer
from app.core.cache import SemanticCache
from app.core.vector_store import VectorStore
from app.core.state import ConversationState
from app.agents import router, sql_generator, validator, answer_generator
from app.utils.chart_generator import generate_chart, format_indian_number, is_currency_column, _fmt_col
from app.agents.chart_agent import generate_chart_figure
from app.core.duckdb_engine import DuckDBEngine
from app.core.auto_semantic import AutoSemantic
from app.agents import upload_sql_generator

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Talk to Data",
    page_icon="🗣️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Heavy resources — initialised once per session
# ---------------------------------------------------------------------------

@st.cache_resource
def load_resources():
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")

    sl = SemanticLayer(str(ROOT / "config" / "semantic_layer.yaml"))

    vs = VectorStore(model)
    vs.init_document_index(str(ROOT / "data" / "documents"))
    vs.init_schema_index(str(ROOT / "config" / "semantic_layer.yaml"))
    vs.init_verified_query_index(str(ROOT / "config" / "verified_queries.yaml"))

    cache = SemanticCache(model)

    return sl, vs, cache


semantic_layer, vector_store, cache = load_resources()

DB_PATH = str(ROOT / "data" / "demo.db")

# Upload mode resources (not cached — per-session)
if "duckdb_engine" not in st.session_state:
    st.session_state.duckdb_engine = DuckDBEngine()
if "auto_semantic" not in st.session_state:
    st.session_state.auto_semantic = AutoSemantic(st.session_state.duckdb_engine)
if "profiled_files" not in st.session_state:
    st.session_state.profiled_files = {}  # filepath -> profile dict

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

if "conversation_state" not in st.session_state:
    st.session_state.conversation_state = ConversationState()

if "app_mode" not in st.session_state:
    st.session_state.app_mode = "demo"

# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def _find_best_verified(question: str, verified_queries: list) -> dict | None:
    """Simple keyword match to find best verified query."""
    if not verified_queries:
        return None
    q_lower = question.lower()
    best = None
    best_score = 0
    for vq in verified_queries:
        vq_lower = vq.get("question", "").lower()
        score = sum(1 for w in q_lower.split() if w in vq_lower)
        if score > best_score:
            best_score = score
            best = vq
    return best


def process_upload_query(question: str) -> dict:
    """Upload mode pipeline: DuckDB + auto-semantic context."""
    start = time.time()

    profiled_files = st.session_state.profiled_files
    if not profiled_files:
        return {
            "answer": "Please upload a CSV or Parquet file first.",
            "cached": False,
            "time_ms": 0,
        }

    filepath = list(profiled_files.keys())[0]
    profile = profiled_files[filepath]

    duckdb_engine = st.session_state.duckdb_engine
    auto_sem = st.session_state.auto_semantic
    state_ctx = st.session_state.conversation_state.get_context_for_followup()

    # 1. Semantic cache check
    cached = cache.find_similar(question)
    if cached:
        return {**cached, "cached": True, "time_ms": (time.time() - start) * 1000}

    # 2. Build schema summary for multi-file context
    schema_summary = profile["schema_summary"]
    if len(profiled_files) > 1:
        rels = auto_sem.get_relationships(list(profiled_files.keys()))
        if rels:
            join_hints = "\n".join(
                f"  {r['from_file']} <-> {r['to_file']} on '{r['column']}'"
                for r in rels
            )
            schema_summary += f"\n\nRelationships detected:\n{join_hints}"

    # 3. Route (upload mode: always STRUCTURED, no UNSTRUCTURED/HYBRID)
    route = router.route(question, schema_summary, state_ctx)
    if route["intent"] == "OUT_OF_SCOPE":
        return {
            "answer": "This question can't be answered with the uploaded data.",
            "cached": False,
            "route": route,
            "time_ms": (time.time() - start) * 1000,
        }
    # Force STRUCTURED for upload mode
    route["intent"] = "STRUCTURED"

    # Build enriched context (combine all files if multiple)
    enriched_context = profile["enriched_context"]
    if len(profiled_files) > 1:
        all_ctx = []
        for fp, p in profiled_files.items():
            all_ctx.append(p["enriched_context"])
        enriched_context = "\n\n".join(all_ctx)
        rels = auto_sem.get_relationships(list(profiled_files.keys()))
        if rels:
            enriched_context += "\n\n-- Multi-file joins:\n"
            for r in rels:
                fp1 = profiled_files[r["from_file"]]["schema_profile"]["read_fn"] if r["from_file"] in profiled_files else r["from_file"]
                fp2 = profiled_files[r["to_file"]]["schema_profile"]["read_fn"] if r["to_file"] in profiled_files else r["to_file"]
                enriched_context += (
                    f'-- JOIN hint: {fp1} t1 JOIN {fp2} t2 ON t1."{r["column"]}" = t2."{r["column"]}"\n'
                )

    # 4. Generate SQL
    verified = _find_best_verified(question, profile["verified_queries"])
    gen_result = upload_sql_generator.generate_sql(
        question=question,
        pattern=route["pattern"],
        enriched_context=enriched_context,
        verified_query=verified,
        filepath=filepath,
        conversation_state=state_ctx,
    )

    # 5. Execute
    exec_result = duckdb_engine.execute(gen_result["sql"])

    # 6. Retry once on failure
    if not exec_result["success"]:
        gen_result = upload_sql_generator.generate_sql(
            question=question,
            pattern=route["pattern"],
            enriched_context=enriched_context,
            verified_query=verified,
            filepath=filepath,
            conversation_state=state_ctx,
            error_feedback=exec_result["error"],
        )
        exec_result = duckdb_engine.execute(gen_result["sql"])

    # 7. Fallback: show raw data if all fails
    if not exec_result["success"]:
        read_fn = profile["schema_profile"]["read_fn"]
        fallback = duckdb_engine.execute(f"SELECT * FROM {read_fn} LIMIT 20")
        return {
            "answer": (
                "I had trouble querying this data. "
                "Here's a preview of your dataset. Try asking a simpler question."
            ),
            "sql": gen_result["sql"],
            "results": fallback if fallback["success"] else None,
            "error": True,
            "route": route,
            "time_ms": (time.time() - start) * 1000,
            "cached": False,
        }

    # 8. Generate answer (reuse existing answer_generator)
    answer_result = answer_generator.generate_answer(
        question, route["pattern"], exec_result, None, gen_result["sql"], state_ctx
    )

    # 9. Update conversation state
    st.session_state.conversation_state.update(
        question, gen_result["sql"], exec_result, answer_result["answer"], []
    )

    elapsed = (time.time() - start) * 1000
    response = {
        "answer": answer_result["answer"],
        "sql": gen_result["sql"],
        "results": exec_result,
        "question": question,
        "confidence": gen_result.get("confidence"),
        "follow_ups": answer_result.get("follow_up_questions", []),
        "chart": answer_result.get("chart_suggestion"),
        "route": route,
        "cached": False,
        "time_ms": elapsed,
    }
    cache.store(question, response)
    return response


def process_query(question: str) -> dict:
    if st.session_state.app_mode == "upload":
        return process_upload_query(question)

    start = time.time()

    # 1. Semantic cache
    cached = cache.find_similar(question)
    if cached:
        elapsed = (time.time() - start) * 1000
        return {**cached, "cached": True, "time_ms": elapsed}

    # 2. Route
    schema_summary = semantic_layer.get_schema_summary()
    state_ctx = st.session_state.conversation_state.get_context_for_followup()
    route = router.route(question, schema_summary, state_ctx)

    if route["intent"] == "OUT_OF_SCOPE":
        return {
            "answer": (
                "I can answer questions about orders, customers, products, and "
                "complaints. This question is outside my data scope."
            ),
            "cached": False,
            "route": route,
            "time_ms": (time.time() - start) * 1000,
        }

    sql_results = None
    rag_docs = None
    sql_used = None
    gen_result = {}

    # 3a. Structured path (SQL)
    if route["intent"] in ("STRUCTURED", "HYBRID"):
        relevant_tables = vector_store.search_tables(question, top_k=5)
        semantic_ctx = semantic_layer.generate_ddl_with_context(relevant_tables)
        verified = vector_store.find_similar_query(question, route["pattern"])

        gen_result = sql_generator.generate_sql(
            question, route["pattern"], semantic_ctx, verified, state_ctx
        )
        sql_used = gen_result["sql"]

        exec_result = validator.validate_and_execute(sql_used, semantic_layer, DB_PATH)

        # Retry once on SCHEMA or SYNTAX error
        if not exec_result["success"] and exec_result["error_type"] in ("SCHEMA", "SYNTAX"):
            gen_result = sql_generator.generate_sql(
                question, route["pattern"], semantic_ctx, verified, state_ctx,
                error_feedback=exec_result["error"],
            )
            sql_used = gen_result["sql"]
            exec_result = validator.validate_and_execute(sql_used, semantic_layer, DB_PATH)

        # Result verification — catch logical errors that pass syntax check
        if exec_result["success"]:
            check = validator.verify_result(
                question, sql_used, exec_result["results"], exec_result["columns"]
            )
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

        if not exec_result["success"]:
            return {
                "answer": f"I couldn't generate a valid query for this question. {exec_result['error']}",
                "error": True,
                "sql": sql_used,
                "route": route,
                "time_ms": (time.time() - start) * 1000,
            }

        sql_results = exec_result

    # 3b. Unstructured path (RAG)
    if route["intent"] in ("UNSTRUCTURED", "HYBRID"):
        rag_docs = vector_store.search_documents(question, top_k=5)

    # 4. Generate answer
    answer_result = answer_generator.generate_answer(
        question, route["pattern"], sql_results, rag_docs, sql_used, state_ctx
    )

    # 5. Update conversation state
    tables_used = gen_result.get("tables_used", [])
    st.session_state.conversation_state.update(
        question, sql_used, sql_results, answer_result["answer"], tables_used
    )

    elapsed = (time.time() - start) * 1000
    response = {
        "answer": answer_result["answer"],
        "sql": sql_used,
        "results": sql_results,
        "question": question,
        "rag_docs": rag_docs,
        "tables_used": tables_used,
        "confidence": gen_result.get("confidence") if sql_results else None,
        "follow_ups": answer_result.get("follow_up_questions", []),
        "chart": answer_result.get("chart_suggestion"),
        "route": route,
        "cached": False,
        "time_ms": elapsed,
    }

    cache.store(question, response)
    return response


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _confidence_badge(score: int | None) -> str:
    if score is None:
        return ""
    if score >= 8:
        color = "green"
    elif score >= 5:
        color = "orange"
    else:
        color = "red"
    return f'<span style="color:{color};font-weight:bold;">Confidence: {score}/10</span>'


def render_response(resp: dict):
    answer = resp.get("answer", "")
    st.markdown(answer)

    # Chart — use smart chart agent
    sql_results = resp.get("results")
    route = resp.get("route", {})
    if sql_results and sql_results.get("success"):
        results = sql_results["results"]
        columns = sql_results["columns"]
        pattern = route.get("pattern")
        question = resp.get("question", "")

        # Single-value KPI → st.metric instead of chart
        if len(results) == 1 and len(columns) == 1:
            value = results[0][0]
            col_name = columns[0]
            if isinstance(value, (int, float)):
                is_cur = is_currency_column(col_name)
                st.metric(label=_fmt_col(col_name), value=format_indian_number(value, is_cur))
        elif len(results) == 1 and len(columns) <= 4:
            # Multi-column single row → metric row
            metric_cols = st.columns(len(columns))
            for i, col_name in enumerate(columns):
                value = results[0][i]
                if isinstance(value, (int, float)):
                    is_cur = is_currency_column(col_name)
                    metric_cols[i].metric(label=_fmt_col(col_name), value=format_indian_number(value, is_cur))
        else:
            # Use chart agent for multi-row results
            fig, chart_type = generate_chart_figure(
                results=results,
                columns=columns,
                pattern=pattern,
                question=question,
            )
            if fig:
                st.plotly_chart(fig, use_container_width=True, config={
                    "displayModeBar": False,
                    "responsive": True,
                })

        # Raw data expander
        import pandas as pd
        with st.expander("View raw data"):
            st.dataframe(pd.DataFrame(results, columns=columns))

    # Expander: "How I got this"
    sql = resp.get("sql")
    route = resp.get("route", {})
    confidence = resp.get("confidence")
    tables_used = resp.get("tables_used", [])
    cached = resp.get("cached", False)
    time_ms = resp.get("time_ms", 0)

    meta_parts = []
    if cached:
        meta_parts.append("⚡ **Cached**")
    if route:
        meta_parts.append(f"Intent: **{route.get('intent','')}** | Pattern: **{route.get('pattern','')}**")
    meta_parts.append(f"⏱ {time_ms:.0f}ms")
    st.caption("  ·  ".join(meta_parts))

    with st.expander("How I got this"):
        if sql:
            st.code(sql, language="sql")
        if tables_used:
            st.markdown(f"**Tables used:** {', '.join(tables_used)}")
        if confidence is not None:
            st.markdown(_confidence_badge(confidence), unsafe_allow_html=True)
        if route.get("reasoning"):
            st.markdown(f"**Routing reasoning:** {route['reasoning']}")

    # Follow-up question buttons
    follow_ups = resp.get("follow_ups", [])
    if follow_ups:
        st.markdown("**You might also ask:**")
        cols = st.columns(len(follow_ups))
        for i, fq in enumerate(follow_ups):
            if cols[i].button(fq, key=f"fu_{hash(fq)}_{time_ms}"):
                st.session_state.pending_followup = fq
                st.rerun()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🗣️ Talk to Data")

    # Mode toggle
    mode_choice = st.radio(
        "Data source",
        ["📊 Demo Dataset", "📁 Upload Your Own"],
        index=0 if st.session_state.app_mode == "demo" else 1,
    )

    new_mode = "upload" if mode_choice == "📁 Upload Your Own" else "demo"
    if new_mode != st.session_state.app_mode:
        st.session_state.app_mode = new_mode
        st.session_state.messages = []
        st.session_state.conversation_state.clear()
        cache.clear()
        st.rerun()

    st.divider()

    if st.session_state.app_mode == "demo":
        st.markdown(
            "Ask natural language questions about your e-commerce data.\n\n"
            "**Available data:**\n"
            "- Orders (Jan 2024 – Mar 2025)\n"
            "- Customers & Products\n"
            "- Complaints & Feedback\n"
        )
        st.markdown(f"**Cache entries:** {cache.size()}")

        if st.button("Clear conversation"):
            st.session_state.messages = []
            st.session_state.conversation_state.clear()
            cache.clear()
            st.rerun()

        st.divider()
        st.markdown("**Example questions:**")
        examples = [
            "Why did revenue drop in the South region?",
            "Compare North vs South revenue",
            "Show revenue breakdown by category",
            "Give me a summary of March 2025",
            "Top 5 customers by spending",
            "What are customers complaining about?",
        ]
        for ex in examples:
            if st.button(ex, key=f"ex_{ex}"):
                st.session_state.pending_followup = ex
                st.rerun()

    else:  # upload mode
        uploaded_files = st.file_uploader(
            "Upload CSV or Parquet files",
            type=["csv", "parquet"],
            accept_multiple_files=True,
        )

        if uploaded_files:
            upload_dir = ROOT / "data" / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)

            for f in uploaded_files:
                filepath = str(upload_dir / f.name)
                # Save file
                with open(filepath, "wb") as out:
                    out.write(f.getbuffer())

                if filepath not in st.session_state.profiled_files:
                    with st.spinner(f"Analyzing {f.name}..."):
                        try:
                            profile = st.session_state.auto_semantic.profile_and_enrich(filepath)
                            st.session_state.profiled_files[filepath] = profile
                            st.success(
                                f"✅ {f.name} — "
                                f"{profile['schema_profile']['total_rows']} rows"
                            )
                        except Exception as e:
                            st.error(f"Failed to analyze {f.name}: {e}")

            # Show suggested questions from first file
            if st.session_state.profiled_files:
                first_profile = list(st.session_state.profiled_files.values())[0]
                suggested = first_profile["auto_semantic"].get("suggested_questions", [])
                if suggested:
                    st.markdown("**Try asking:**")
                    for q in suggested[:3]:
                        if st.button(q, key=f"sq_{hash(q)}"):
                            st.session_state.pending_followup = q
                            st.rerun()

        st.divider()
        st.markdown(f"**Cache entries:** {cache.size()}")
        if st.button("Clear conversation"):
            st.session_state.messages = []
            st.session_state.conversation_state.clear()
            cache.clear()
            st.rerun()

        if st.button("Clear uploaded files"):
            st.session_state.profiled_files = {}
            st.session_state.duckdb_engine = DuckDBEngine()
            st.session_state.auto_semantic = AutoSemantic(st.session_state.duckdb_engine)
            st.rerun()

# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------

if st.session_state.app_mode == "upload":
    st.title("Talk to Data — Upload Mode")
    if not st.session_state.profiled_files:
        st.info("Upload a CSV or Parquet file from the sidebar to get started.")
else:
    st.title("Talk to Data")

# Render existing messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and "response" in msg:
            render_response(msg["response"])
        else:
            st.markdown(msg["content"])

# Handle pending follow-up (from button clicks)
pending = st.session_state.pop("pending_followup", None)
user_input = st.chat_input("Ask a question about your data...") or pending

if user_input:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Process and show response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            resp = process_query(user_input)
        render_response(resp)

    st.session_state.messages.append({
        "role": "assistant",
        "content": resp.get("answer", ""),
        "response": resp,
    })
