from __future__ import annotations
"""
Talk to Data — Premium Streamlit Chat UI
Entry point: streamlit run app/main.py

Inspired by Julius AI + WrenAI design language:
  - Dark glassmorphism theme
  - Clean, modern typography (Inter)
  - Smooth micro-animations
  - Source transparency badges
  - Confidence meters
  - Data preview on upload
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
import pandas as pd

from app.core.semantic_layer import SemanticLayer
from app.core.cache import SemanticCache
from app.core.vector_store import VectorStore
from app.core.state import ConversationState
from app.agents import router, sql_generator, validator, answer_generator
from app.utils.chart_generator import generate_chart, format_column_name, format_indian_number, is_currency_column
from app.core.duckdb_engine import DuckDBEngine
from app.core.auto_semantic import AutoSemantic
from app.agents import upload_sql_generator
from app.theme import (
    CUSTOM_CSS,
    sidebar_logo_html,
    hero_html,
    empty_state_html,
    meta_badges_html,
    confidence_html,
    source_tag_html,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Talk to Data",
    page_icon="🗣️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject custom CSS
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

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
# Core pipeline (Demo mode)
# ---------------------------------------------------------------------------

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

        if not exec_result["success"]:
            return {
                "answer": f"I couldn't generate a valid query for this question. {exec_result['error']}",
                "error": True,
                "sql": sql_used,
                "route": route,
                "time_ms": (time.time() - start) * 1000,
            }

        # Result verification (quick sanity check)
        verification = validator.verify_result(
            question, sql_used, exec_result["results"], exec_result["columns"]
        )
        if not verification.get("is_valid", True):
            # Retry with verification feedback
            gen_result = sql_generator.generate_sql(
                question, route["pattern"], semantic_ctx, verified, state_ctx,
                error_feedback=f"Result validation issue: {verification.get('issue', '')}",
            )
            sql_used = gen_result["sql"]
            exec_result = validator.validate_and_execute(sql_used, semantic_layer, DB_PATH)

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
        "rag_docs": rag_docs,
        "tables_used": tables_used,
        "confidence": gen_result.get("confidence") if sql_results else None,
        "follow_ups": answer_result.get("follow_up_questions", []),
        "chart": answer_result.get("chart_suggestion"),
        "pattern": route.get("pattern"),
        "route": route,
        "cached": False,
        "time_ms": elapsed,
    }

    cache.store(question, response)
    return response


# ---------------------------------------------------------------------------
# Upload pipeline
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
                "Here's a preview of your dataset. Try rephrasing your question."
            ),
            "sql": gen_result["sql"],
            "results": fallback if fallback["success"] else None,
            "error": True,
            "route": route,
            "time_ms": (time.time() - start) * 1000,
            "cached": False,
        }

    # 8. Generate answer
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
        "confidence": gen_result.get("confidence"),
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

def render_response(resp: dict, msg_idx: int = 0):
    """Render a complete response with badges, answer, chart, details, follow-ups."""

    route = resp.get("route", {})
    cached = resp.get("cached", False)
    time_ms = resp.get("time_ms", 0)
    confidence = resp.get("confidence")
    answer = resp.get("answer", "")

    # Source tag (upload mode)
    if st.session_state.app_mode == "upload" and st.session_state.profiled_files:
        fp = list(st.session_state.profiled_files.keys())[0]
        profile = st.session_state.profiled_files[fp]
        fname = Path(fp).name
        rows = profile["schema_profile"]["total_rows"]
        st.markdown(source_tag_html(fname, rows), unsafe_allow_html=True)

    # Meta badges
    st.markdown(meta_badges_html(route, cached, time_ms), unsafe_allow_html=True)

    # Confidence meter
    if confidence is not None:
        st.markdown(confidence_html(confidence), unsafe_allow_html=True)

    # Answer
    st.markdown(answer)

    # Smart Chart (data-shape-aware)
    sql_results = resp.get("results")
    pattern = resp.get("pattern", "")
    if sql_results and sql_results.get("success") and sql_results.get("results"):
        result_rows = sql_results["results"]
        result_cols = sql_results["columns"]

        # KPI metric display for single-value results
        if len(result_rows) == 1 and len(result_cols) <= 3:
            metric_cols = st.columns(len(result_cols))
            for i, (col_name, value) in enumerate(zip(result_cols, result_rows[0])):
                with metric_cols[i]:
                    if isinstance(value, (int, float)):
                        is_curr = is_currency_column(col_name)
                        st.metric(
                            label=format_column_name(col_name),
                            value=format_indian_number(value, is_curr),
                        )
                    else:
                        st.metric(label=format_column_name(col_name), value=str(value))

        # Chart (only if data naturally suits visualization)
        fig = generate_chart(
            result_rows, result_cols,
            chart_suggestion=resp.get("chart"),
            pattern=pattern,
        )
        if fig:
            st.plotly_chart(
                fig, use_container_width=True,
                config={"displayModeBar": False, "responsive": True},
                key=f"chart_{msg_idx}_{time_ms}",
            )

        # Data table preview
        if len(result_rows) <= 30 and len(result_cols) > 1:
            df = pd.DataFrame(result_rows, columns=result_cols)
            with st.expander("📊 View data table", expanded=False):
                st.dataframe(df, use_container_width=True, hide_index=True)

    # How I got this (Transparency)
    sql = resp.get("sql")
    tables_used = resp.get("tables_used", [])

    if sql or route.get("reasoning"):
        with st.expander("🔍 How I got this answer", expanded=False):
            if sql:
                st.code(sql, language="sql")
            if tables_used:
                st.markdown(f"**Tables used:** {', '.join(tables_used)}")
            if route.get("reasoning"):
                st.caption(f"💭 {route['reasoning']}")

    # Follow-up questions
    follow_ups = resp.get("follow_ups", [])
    if follow_ups:
        st.markdown("**💡 You might also ask:**")
        cols = st.columns(min(len(follow_ups), 3))
        for i, fq in enumerate(follow_ups[:3]):
            with cols[i]:
                if st.button(fq, key=f"fu_{msg_idx}_{i}_{hash(fq)}"):
                    st.session_state.pending_followup = fq
                    st.rerun()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(sidebar_logo_html(), unsafe_allow_html=True)

    # Mode toggle
    mode_choice = st.radio(
        "Data Source",
        ["📊 Demo Dataset", "📁 Upload Your Own"],
        index=0 if st.session_state.app_mode == "demo" else 1,
        label_visibility="collapsed",
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
            "**📦 E-Commerce Dataset**\n\n"
            "- 🛒 Orders (Jan 2024 – Mar 2025)\n"
            "- 👥 Customers & Segments\n"
            "- 📦 Products & Categories\n"
            "- 💬 Complaints & Feedback\n"
        )

        st.divider()
        st.markdown("**Try these questions:**")
        examples = [
            "Why did revenue drop in the South region?",
            "Compare North vs South revenue",
            "Show revenue breakdown by category",
            "Give me a summary of March 2025",
            "Top 5 customers by spending",
            "What are customers complaining about?",
        ]
        for ex in examples:
            if st.button(f"→ {ex}", key=f"ex_{ex}"):
                st.session_state.pending_followup = ex
                st.rerun()

    else:  # upload mode
        uploaded_files = st.file_uploader(
            "Drop your data files here",
            type=["csv", "parquet"],
            accept_multiple_files=True,
            help="Supports CSV and Parquet files up to 200MB",
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
                    with st.spinner(f"🔍 Analyzing {f.name}..."):
                        try:
                            profile = st.session_state.auto_semantic.profile_and_enrich(filepath)
                            st.session_state.profiled_files[filepath] = profile
                            st.success(
                                f"✅ **{f.name}** — "
                                f"{profile['schema_profile']['total_rows']:,} rows, "
                                f"{len(profile['schema_profile']['columns'])} columns"
                            )
                        except Exception as e:
                            st.error(f"❌ Failed to analyze {f.name}: {e}")

            # Show suggested questions from first file
            if st.session_state.profiled_files:
                first_profile = list(st.session_state.profiled_files.values())[0]
                suggested = first_profile["auto_semantic"].get("suggested_questions", [])
                if suggested:
                    st.divider()
                    st.markdown("**🎯 Suggested questions:**")
                    for q in suggested[:4]:
                        if st.button(f"→ {q}", key=f"sq_{hash(q)}"):
                            st.session_state.pending_followup = q
                            st.rerun()

    # Bottom section
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        cache_count = cache.size()
        st.caption(f"⚡ Cache: {cache_count}")
    with col2:
        msg_count = len(st.session_state.messages)
        st.caption(f"💬 Turns: {msg_count // 2}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🗑️ Clear chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.conversation_state.clear()
            cache.clear()
            st.rerun()
    with c2:
        if st.session_state.app_mode == "upload":
            if st.button("📁 Clear files", use_container_width=True):
                st.session_state.profiled_files = {}
                st.session_state.duckdb_engine = DuckDBEngine()
                st.session_state.auto_semantic = AutoSemantic(st.session_state.duckdb_engine)
                st.rerun()


# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------

# Hero header
st.markdown(hero_html(st.session_state.app_mode), unsafe_allow_html=True)

# Upload mode: Show data preview if files are loaded
if st.session_state.app_mode == "upload" and st.session_state.profiled_files:
    with st.expander("📋 Data Preview", expanded=False):
        for fp, profile in st.session_state.profiled_files.items():
            fname = Path(fp).name
            schema = profile["schema_profile"]
            st.markdown(f"**{fname}** — {schema['total_rows']:,} rows")
            sample_df = pd.DataFrame(schema["sample_data"])
            st.dataframe(sample_df, use_container_width=True, hide_index=True, height=200)

# Empty state
if not st.session_state.messages:
    if st.session_state.app_mode == "upload" and not st.session_state.profiled_files:
        st.markdown(empty_state_html("upload"), unsafe_allow_html=True)
    elif st.session_state.app_mode == "demo":
        st.markdown(empty_state_html("demo"), unsafe_allow_html=True)

# Render existing messages
for msg_idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and "response" in msg:
            render_response(msg["response"], msg_idx=msg_idx)
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
        with st.spinner("🧠 Analyzing your question..."):
            resp = process_query(user_input)
        render_response(resp, msg_idx=len(st.session_state.messages) + 999)

    st.session_state.messages.append({
        "role": "assistant",
        "content": resp.get("answer", ""),
        "response": resp,
    })
