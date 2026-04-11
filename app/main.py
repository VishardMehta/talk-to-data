"""
Talk to Data — Streamlit Chat UI
Entry point: streamlit run app/main.py
"""

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
from app.utils.chart_generator import generate_chart

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

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

if "conversation_state" not in st.session_state:
    st.session_state.conversation_state = ConversationState()

# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def process_query(question: str) -> dict:
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

    # Chart
    chart_suggestion = resp.get("chart")
    sql_results = resp.get("results")
    if chart_suggestion and sql_results and sql_results.get("success"):
        fig = generate_chart(
            sql_results["results"],
            sql_results["columns"],
            chart_suggestion,
        )
        if fig:
            st.plotly_chart(fig, use_container_width=True)

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
    st.markdown(
        "Ask natural language questions about your e-commerce data.\n\n"
        "**Available data:**\n"
        "- Orders (Jan 2024 – Mar 2025)\n"
        "- Customers & Products\n"
        "- Complaints & Feedback\n"
    )
    st.divider()
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

# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------

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
