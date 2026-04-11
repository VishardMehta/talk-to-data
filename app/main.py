"""
Talk to Data — Streamlit Chat Application
Main entry point: streamlit run app/main.py

Multi-agent pipeline:
  Router → SQL Generator → Validator → Answer Generator
  with semantic cache, RAG, and conversation memory.
"""
from __future__ import annotations

import os
import sys
import time

# Add project root to path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Page Config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Talk to Data",
    page_icon="🗣️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* Global */
.stApp {
    font-family: 'Inter', sans-serif;
}

/* Chat message styling */
.stChatMessage {
    border-radius: 12px;
    margin-bottom: 8px;
}

/* Badge styling */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-right: 6px;
    margin-bottom: 4px;
}
.badge-cached { background: #dcfce7; color: #166534; }
.badge-structured { background: #dbeafe; color: #1e40af; }
.badge-unstructured { background: #fef3c7; color: #92400e; }
.badge-hybrid { background: #ede9fe; color: #5b21b6; }
.badge-pattern { background: #f3f4f6; color: #374151; }
.badge-time { background: #f0fdf4; color: #166534; }

/* Confidence colors */
.conf-high { color: #16a34a; font-weight: 600; }
.conf-med { color: #ca8a04; font-weight: 600; }
.conf-low { color: #dc2626; font-weight: 600; }

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1e1b4b 0%, #312e81 100%);
}
section[data-testid="stSidebar"] .stMarkdown {
    color: #e0e7ff;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: #c7d2fe !important;
}

/* Follow-up buttons */
.stButton > button {
    border-radius: 20px;
    border: 1px solid #e5e7eb;
    background: #f9fafb;
    font-size: 0.85rem;
    padding: 4px 16px;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: #ede9fe;
    border-color: #8b5cf6;
}
</style>
""", unsafe_allow_html=True)


# ── Initialize Resources (cached) ───────────────────────────────────────────

@st.cache_resource
def load_embedding_model():
    """Load SentenceTransformer model once."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


@st.cache_resource
def load_vector_store():
    """Initialize and populate vector store."""
    from app.core.vector_store import VectorStore
    model = load_embedding_model()
    vs = VectorStore(model)
    vs.initialize_all()
    return vs


@st.cache_resource
def load_semantic_layer():
    """Load semantic layer config."""
    from app.core.semantic_layer import SemanticLayer
    return SemanticLayer()


def get_cache():
    """Get or create semantic cache (per session)."""
    if "cache" not in st.session_state:
        from app.core.cache import SemanticCache
        model = load_embedding_model()
        st.session_state.cache = SemanticCache(model)
    return st.session_state.cache


def get_conversation_state():
    """Get or create conversation state (per session)."""
    if "conversation_state" not in st.session_state:
        from app.core.state import ConversationState
        st.session_state.conversation_state = ConversationState()
    return st.session_state.conversation_state


# ── Pipeline ─────────────────────────────────────────────────────────────────

def process_query(question: str) -> dict:
    """
    Main pipeline: Cache → Router → SQL Gen → Validate → Answer Gen.
    """
    from app.agents import router, sql_generator, validator, answer_generator

    start_time = time.time()
    
    semantic_layer = load_semantic_layer()
    vector_store = load_vector_store()
    cache = get_cache()
    conv_state = get_conversation_state()

    # ── 1. Cache check ──
    cached = cache.find_similar(question)
    if cached:
        elapsed = (time.time() - start_time) * 1000
        return {**cached, "cached": True, "time_ms": elapsed}

    # ── 2. Route ──
    schema_summary = semantic_layer.get_schema_summary()
    state_context = conv_state.get_context_for_followup()
    route = router.route(question, schema_summary, state_context)

    if route["intent"] == "OUT_OF_SCOPE":
        elapsed = (time.time() - start_time) * 1000
        return {
            "answer": "I can answer questions about orders, customers, products, and complaints in our e-commerce database. This question is outside my data scope. Try asking about revenue, orders, customer segments, or complaints!",
            "cached": False,
            "time_ms": elapsed,
            "route": route,
        }

    # ── 3. Process based on intent ──
    sql_results = None
    rag_docs = None
    sql_used = None
    gen_result = {}

    if route["intent"] in ("STRUCTURED", "HYBRID"):
        # Get relevant tables
        relevant_tables = vector_store.search_tables(question, top_k=5)
        if not relevant_tables:
            relevant_tables = semantic_layer.get_all_valid_tables()
        semantic_context = semantic_layer.generate_ddl_with_context(relevant_tables)

        # Find best verified query
        verified = vector_store.find_similar_query(question, route["pattern"])

        # Generate SQL
        gen_result = sql_generator.generate_sql(
            question, route["pattern"], semantic_context, verified, state_context
        )
        sql_used = gen_result.get("sql", "")

        if sql_used:
            # Validate and execute
            db_path = os.path.join(_ROOT, "data", "demo.db")
            exec_result = validator.validate_and_execute(
                sql_used, semantic_layer, db_path
            )

            # Retry once on schema/syntax errors
            if not exec_result["success"] and exec_result.get("error_type") in ("SCHEMA", "SYNTAX"):
                gen_result = sql_generator.generate_sql(
                    question, route["pattern"], semantic_context, verified,
                    state_context, error_feedback=exec_result["error"]
                )
                sql_used = gen_result.get("sql", "")
                if sql_used:
                    exec_result = validator.validate_and_execute(
                        sql_used, semantic_layer, db_path
                    )

            if not exec_result["success"]:
                elapsed = (time.time() - start_time) * 1000
                return {
                    "answer": f"I couldn't generate a valid query for this question. {exec_result.get('error', 'Unknown error')}",
                    "error": True,
                    "time_ms": elapsed,
                    "route": route,
                    "sql": sql_used,
                }

            sql_results = exec_result

    if route["intent"] in ("UNSTRUCTURED", "HYBRID"):
        rag_docs = vector_store.search_documents(question, top_k=5)

    # ── 4. Generate answer ──
    answer_result = answer_generator.generate_answer(
        question, route["pattern"], sql_results, rag_docs, sql_used, state_context
    )

    # ── 5. Update conversation state ──
    tables_used = gen_result.get("tables_used", []) if gen_result else []
    conv_state.update(
        question, sql_used, sql_results,
        answer_result.get("answer", ""), tables_used
    )

    # ── 6. Build response ──
    elapsed = (time.time() - start_time) * 1000
    response = {
        "answer": answer_result.get("answer", ""),
        "sql": sql_used,
        "results": sql_results,
        "rag_docs": rag_docs,
        "tables_used": tables_used,
        "confidence": gen_result.get("confidence") if gen_result else None,
        "follow_ups": answer_result.get("follow_up_questions", []),
        "chart": answer_result.get("chart_suggestion"),
        "route": route,
        "cached": False,
        "time_ms": elapsed,
    }

    # ── 7. Cache the response ──
    cache.store(question, response)

    return response


# ── UI Components ────────────────────────────────────────────────────────────

def render_badges(response: dict):
    """Render intent/pattern/time badges."""
    badges = []
    
    if response.get("cached"):
        badges.append('<span class="badge badge-cached">⚡ Cached</span>')
    
    route = response.get("route", {})
    intent = route.get("intent", "")
    if intent:
        intent_class = {
            "STRUCTURED": "badge-structured",
            "UNSTRUCTURED": "badge-unstructured",
            "HYBRID": "badge-hybrid",
        }.get(intent, "badge-pattern")
        badges.append(f'<span class="badge {intent_class}">{intent}</span>')
    
    pattern = route.get("pattern", "")
    if pattern:
        badges.append(f'<span class="badge badge-pattern">{pattern}</span>')
    
    time_ms = response.get("time_ms", 0)
    if time_ms:
        badges.append(f'<span class="badge badge-time">{time_ms:.0f}ms</span>')
    
    if badges:
        st.markdown(" ".join(badges), unsafe_allow_html=True)


def render_confidence(confidence: int | None):
    """Render confidence score with color."""
    if confidence is None:
        return
    
    if confidence >= 7:
        css_class = "conf-high"
        label = "High"
    elif confidence >= 4:
        css_class = "conf-med"
        label = "Medium"
    else:
        css_class = "conf-low"
        label = "Low"
    
    st.markdown(
        f'Confidence: <span class="{css_class}">{confidence}/10 ({label})</span>',
        unsafe_allow_html=True,
    )


def render_chart(response: dict):
    """Render Plotly chart if applicable."""
    chart_suggestion = response.get("chart")
    sql_results = response.get("results")
    
    if not chart_suggestion or not sql_results or not sql_results.get("results"):
        return
    
    try:
        from app.utils.chart_generator import generate_chart
        fig = generate_chart(
            sql_results["results"],
            sql_results["columns"],
            chart_suggestion,
        )
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    except Exception:
        pass  # Chart rendering is optional, never crash


def render_details(response: dict):
    """Render expandable details section."""
    with st.expander("🔍 How I got this answer", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            if response.get("sql"):
                st.markdown("**SQL Query:**")
                st.code(response["sql"], language="sql")
            
            if response.get("tables_used"):
                st.markdown(f"**Tables used:** {', '.join(response['tables_used'])}")
        
        with col2:
            render_confidence(response.get("confidence"))
            
            route = response.get("route", {})
            if route.get("reasoning"):
                st.markdown(f"**Reasoning:** {route['reasoning']}")
            
            if response.get("rag_docs"):
                st.markdown(f"**Documents searched:** {len(response['rag_docs'])} relevant documents found")
        
        # Show RAG documents if present
        if response.get("rag_docs"):
            st.markdown("---")
            st.markdown("**Relevant Documents:**")
            for doc in response["rag_docs"][:3]:
                with st.container():
                    score = doc.get("score", 0)
                    region = doc.get("region", "")
                    category = doc.get("category", "")
                    st.markdown(
                        f"📄 *[{region} | {category} | Score: {score:.2f}]* — {doc.get('text', '')[:200]}..."
                    )


def render_follow_ups(response: dict, msg_idx: int = 0):
    """Render follow-up question buttons."""
    follow_ups = response.get("follow_ups", [])
    if not follow_ups:
        return
    
    st.markdown("**💡 You might also want to know:**")
    cols = st.columns(len(follow_ups[:3]))
    for i, (col, question) in enumerate(zip(cols, follow_ups[:3])):
        with col:
            if st.button(question, key=f"followup_{msg_idx}_{i}"):
                st.session_state.pending_followup = question
                st.rerun()


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("# 🗣️ Talk to Data")
    st.markdown("*Ask questions about your e-commerce data in plain English.*")
    
    st.markdown("---")
    
    st.markdown("### 💡 Try asking:")
    example_questions = [
        "What is the total revenue?",
        "Revenue by region",
        "Why did revenue drop in March?",
        "Compare North vs South",
        "What are customers complaining about?",
        "Weekly summary of metrics",
        "Top 5 customers by spending",
    ]
    for q in example_questions:
        if st.button(q, key=f"example_{q}", use_container_width=True):
            st.session_state.pending_followup = q
            st.rerun()
    
    st.markdown("---")
    
    # System status
    st.markdown("### ⚙️ System Status")
    
    try:
        cache = get_cache()
        st.markdown(f"📦 Cache: **{cache.size}** entries")
    except Exception:
        st.markdown("📦 Cache: Initializing...")
    
    try:
        vs = load_vector_store()
        st.markdown(f"📄 Documents: **{vs.document_count}** indexed")
        st.markdown(f"🗃️ Tables: **{vs.table_count}** indexed")
        st.markdown(f"✅ Verified queries: **{vs.query_count}** loaded")
    except Exception:
        st.markdown("📄 Vector store: Initializing...")
    
    db_path = os.path.join(_ROOT, "data", "demo.db")
    db_exists = os.path.exists(db_path)
    st.markdown(f"🗄️ Database: {'**Connected** ✅' if db_exists else '**Not found** ❌'}")
    
    if not db_exists:
        st.error("Database not found! Run `python data/seed.py` first.")
    
    st.markdown("---")
    
    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.messages = []
        try:
            get_conversation_state().clear()
        except Exception:
            pass
        st.rerun()
    
    conv = get_conversation_state()
    st.markdown(f"💬 Turns: **{conv.turn_count}**")


# ── Main Chat Area ───────────────────────────────────────────────────────────

st.markdown("## 🗣️ Talk to Data")
st.markdown("Ask questions about orders, customers, products, and complaints in plain English.")

# Initialize message history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg_idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            # Assistant message with full response
            response = msg.get("response", {})
            if response:
                render_badges(response)
                st.markdown(response.get("answer", msg.get("content", "")))
                render_chart(response)
                render_details(response)
                render_follow_ups(response, msg_idx=msg_idx)
            else:
                st.markdown(msg.get("content", ""))

# Handle pending follow-up (from button click)
pending = st.session_state.pop("pending_followup", None)

# Get user input
user_input = st.chat_input("Ask a question about your data...")
question = pending or user_input

if question:
    # Display user message
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Process and display response
    with st.chat_message("assistant"):
        with st.spinner("🤔 Analyzing your question..."):
            try:
                response = process_query(question)
            except Exception as e:
                response = {
                    "answer": f"Sorry, I encountered an error: {str(e)[:200]}. Please try again or rephrase your question.",
                    "cached": False,
                    "time_ms": 0,
                    "route": {},
                }

        render_badges(response)
        st.markdown(response.get("answer", ""))
        render_chart(response)
        render_details(response)
        render_follow_ups(response, msg_idx=len(st.session_state.messages) + 999)

    # Store assistant message
    st.session_state.messages.append({
        "role": "assistant",
        "content": response.get("answer", ""),
        "response": response,
    })
