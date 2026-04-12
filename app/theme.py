from __future__ import annotations
"""
Talk to Data — Premium Theme & CSS
Inspired by Julius AI + WrenAI: dark glassmorphism, clean typography, premium feel.
"""

CUSTOM_CSS = """
<style>
/* ── Import Google Fonts ─────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Root Variables ──────────────────────────────────────────── */
:root {
    --bg-primary: #0F1117;
    --bg-secondary: #1A1D2E;
    --bg-card: #1E2235;
    --bg-hover: #262A40;
    --border-color: rgba(255,255,255,0.06);
    --border-glow: rgba(99,102,241,0.3);
    --text-primary: #F1F3F9;
    --text-secondary: #8B92A5;
    --text-muted: #5A6178;
    --accent-primary: #6366F1;
    --accent-secondary: #818CF8;
    --accent-gradient: linear-gradient(135deg, #6366F1 0%, #8B5CF6 50%, #A78BFA 100%);
    --success: #34D399;
    --warning: #FBBF24;
    --error: #F87171;
    --info: #60A5FA;
    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --radius-xl: 20px;
    --shadow-sm: 0 2px 8px rgba(0,0,0,0.2);
    --shadow-md: 0 4px 20px rgba(0,0,0,0.3);
    --shadow-lg: 0 8px 40px rgba(0,0,0,0.4);
    --shadow-glow: 0 0 20px rgba(99,102,241,0.15);
}

/* ── Global Reset ────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: var(--font-sans) !important;
    color: var(--text-primary) !important;
}

.stApp {
    background: var(--bg-primary) !important;
}

/* ── Streamlit Header Bar ────────────────────────────────────── */
header[data-testid="stHeader"] {
    background: rgba(15,17,23,0.8) !important;
    backdrop-filter: blur(12px) !important;
    border-bottom: 1px solid var(--border-color) !important;
}

/* ── Sidebar ─────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: var(--bg-secondary) !important;
    border-right: 1px solid var(--border-color) !important;
}

section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stMarkdown li {
    color: var(--text-secondary) !important;
    font-size: 0.88rem !important;
    line-height: 1.6 !important;
}

section[data-testid="stSidebar"] hr {
    border-color: var(--border-color) !important;
    margin: 1rem 0 !important;
}

/* ── Sidebar Logo / Title ────────────────────────────────────── */
.sidebar-logo {
    text-align: center;
    padding: 1.5rem 0 1rem;
}
.sidebar-logo .logo-text {
    font-size: 1.75rem;
    font-weight: 700;
    background: var(--accent-gradient);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -0.5px;
}
.sidebar-logo .logo-sub {
    font-size: 0.78rem;
    color: var(--text-muted);
    margin-top: 4px;
    letter-spacing: 2px;
    text-transform: uppercase;
}

/* ── Mode Selector (Radio as Tabs) ───────────────────────────── */
div[data-testid="stRadio"] > div {
    display: flex !important;
    gap: 4px !important;
    background: var(--bg-card) !important;
    border-radius: var(--radius-md) !important;
    padding: 3px !important;
    border: 1px solid var(--border-color) !important;
}

div[data-testid="stRadio"] > div > label {
    flex: 1 !important;
    border-radius: var(--radius-sm) !important;
    padding: 8px 12px !important;
    text-align: center !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
    cursor: pointer !important;
    color: var(--text-secondary) !important;
}

div[data-testid="stRadio"] > div > label[data-checked="true"],
div[data-testid="stRadio"] > div > label:has(input:checked) {
    background: var(--accent-primary) !important;
    color: white !important;
    box-shadow: var(--shadow-glow) !important;
}

div[data-testid="stRadio"] > div > label > div:first-child {
    display: none !important; /* Hide radio circles */
}

/* ── Sidebar Buttons (Example Questions) ─────────────────────── */
section[data-testid="stSidebar"] .stButton > button {
    width: 100% !important;
    background: var(--bg-card) !important;
    color: var(--text-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-sm) !important;
    padding: 10px 14px !important;
    font-size: 0.82rem !important;
    font-weight: 400 !important;
    text-align: left !important;
    transition: all 0.25s ease !important;
    margin-bottom: 4px !important;
}

section[data-testid="stSidebar"] .stButton > button:hover {
    background: var(--bg-hover) !important;
    border-color: var(--accent-primary) !important;
    color: var(--text-primary) !important;
    transform: translateX(3px) !important;
    box-shadow: var(--shadow-glow) !important;
}

/* ── Main Title ──────────────────────────────────────────────── */
.main-hero {
    text-align: center;
    padding: 2rem 0 1.5rem;
}
.main-hero h1 {
    font-size: 2.2rem !important;
    font-weight: 700 !important;
    background: var(--accent-gradient);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 8px !important;
}
.main-hero p {
    color: var(--text-muted) !important;
    font-size: 0.95rem !important;
}

/* ── Chat Messages ───────────────────────────────────────────── */
.stChatMessage {
    background: transparent !important;
    border: none !important;
    padding: 0.75rem 0 !important;
}

/* User messages */
.stChatMessage[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    justify-content: flex-end !important;
}

.stChatMessage[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) > div:last-child {
    background: var(--accent-primary) !important;
    border-radius: var(--radius-lg) var(--radius-lg) 4px var(--radius-lg) !important;
    padding: 12px 18px !important;
    max-width: 75% !important;
    box-shadow: var(--shadow-sm) !important;
}

.stChatMessage[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) p {
    color: white !important;
}

/* Assistant messages */
.stChatMessage[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) > div:last-child {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 4px var(--radius-lg) var(--radius-lg) var(--radius-lg) !important;
    padding: 16px 20px !important;
    max-width: 85% !important;
    box-shadow: var(--shadow-sm) !important;
}

/* ── Chat Input ──────────────────────────────────────────────── */
.stChatInput {
    border-radius: 0 !important;
}

.stChatInput > div {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-xl) !important;
    box-shadow: var(--shadow-md) !important;
    transition: all 0.3s ease !important;
}

.stChatInput > div:focus-within {
    border-color: var(--accent-primary) !important;
    box-shadow: var(--shadow-glow), var(--shadow-md) !important;
}

.stChatInput textarea {
    color: var(--text-primary) !important;
    font-family: var(--font-sans) !important;
    font-size: 0.92rem !important;
}

/* ── Expander ("How I got this") ──────────────────────────────── */
.streamlit-expanderHeader {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-secondary) !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}

.streamlit-expanderHeader:hover {
    border-color: var(--accent-primary) !important;
    color: var(--text-primary) !important;
}

.streamlit-expanderContent {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-color) !important;
    border-top: none !important;
    border-radius: 0 0 var(--radius-sm) var(--radius-sm) !important;
}

/* ── Code blocks ─────────────────────────────────────────────── */
.stCodeBlock, pre, code {
    background: #151827 !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-sm) !important;
    font-size: 0.82rem !important;
}

/* ── File Uploader ───────────────────────────────────────────── */
.stFileUploader > div {
    background: var(--bg-card) !important;
    border: 2px dashed var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    transition: all 0.3s ease !important;
}

.stFileUploader > div:hover {
    border-color: var(--accent-primary) !important;
    background: var(--bg-hover) !important;
}

/* ── Follow-Up Buttons (Main Area) ───────────────────────────── */
.stButton > button {
    background: var(--bg-card) !important;
    color: var(--text-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-xl) !important;
    padding: 8px 20px !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    transition: all 0.25s ease !important;
}

.stButton > button:hover {
    background: var(--accent-primary) !important;
    color: white !important;
    border-color: var(--accent-primary) !important;
    box-shadow: var(--shadow-glow) !important;
    transform: translateY(-1px) !important;
}

/* ── Metric Badges ───────────────────────────────────────────── */
.meta-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 100px;
    font-size: 0.72rem;
    font-weight: 600;
    font-family: var(--font-sans);
    letter-spacing: 0.3px;
    text-transform: uppercase;
}
.meta-badge.intent   { background: rgba(99,102,241,0.15); color: #818CF8; }
.meta-badge.pattern  { background: rgba(139,92,246,0.15); color: #A78BFA; }
.meta-badge.cached   { background: rgba(52,211,153,0.15); color: #34D399; }
.meta-badge.time     { background: rgba(255,255,255,0.06); color: var(--text-muted); }

/* ── Confidence Meter ────────────────────────────────────────── */
.confidence-meter {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 8px 0;
}
.confidence-bar {
    width: 100px;
    height: 6px;
    background: var(--bg-primary);
    border-radius: 3px;
    overflow: hidden;
}
.confidence-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s ease;
}
.confidence-fill.high   { background: var(--success); }
.confidence-fill.medium { background: var(--warning); }
.confidence-fill.low    { background: var(--error); }
.confidence-label {
    font-size: 0.75rem;
    font-weight: 600;
    font-family: var(--font-sans);
}
.confidence-label.high   { color: var(--success); }
.confidence-label.medium { color: var(--warning); }
.confidence-label.low    { color: var(--error); }

/* ── Data Preview Table ──────────────────────────────────────── */
.stDataFrame {
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
}

/* ── Spinner ─────────────────────────────────────────────────── */
.stSpinner > div {
    border-color: var(--accent-primary) !important;
}

/* ── Info / Success / Error Alerts ────────────────────────────── */
.stAlert {
    border-radius: var(--radius-md) !important;
    border: none !important;
}

div[data-testid="stAlert"] {
    border-radius: var(--radius-md) !important;
}

/* ── Column Metrics Cards ────────────────────────────────────── */
.stMetric {
    background: var(--bg-card) !important;
    padding: 16px !important;
    border-radius: var(--radius-md) !important;
    border: 1px solid var(--border-color) !important;
}

/* ── Source File Tag ──────────────────────────────────────────── */
.source-tag {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(96,165,250,0.1);
    color: var(--info);
    padding: 4px 12px;
    border-radius: 100px;
    font-size: 0.72rem;
    font-weight: 600;
    font-family: var(--font-sans);
    margin-bottom: 8px;
}

/* ── Scrollbar ───────────────────────────────────────────────── */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: var(--bg-primary);
}
::-webkit-scrollbar-thumb {
    background: var(--bg-hover);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: var(--text-muted);
}

/* ── Caption ─────────────────────────────────────────────────── */
.stCaption, small {
    color: var(--text-muted) !important;
    font-size: 0.75rem !important;
}

/* ── Animations ──────────────────────────────────────────────── */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(12px); }
    to   { opacity: 1; transform: translateY(0); }
}

.stChatMessage {
    animation: fadeInUp 0.35s ease-out !important;
}

/* ── Plotly Chart Wrapper ────────────────────────────────────── */
.js-plotly-plot {
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
    box-shadow: var(--shadow-sm) !important;
}

/* ── Empty State ─────────────────────────────────────────────── */
.empty-state {
    text-align: center;
    padding: 3rem 2rem;
    color: var(--text-muted);
}
.empty-state .icon {
    font-size: 3rem;
    margin-bottom: 1rem;
    opacity: 0.5;
}
.empty-state h3 {
    color: var(--text-secondary) !important;
    font-weight: 600;
    margin-bottom: 8px;
}
.empty-state p {
    font-size: 0.88rem;
    max-width: 400px;
    margin: 0 auto;
    line-height: 1.6;
}
</style>
"""


# ── HTML Helpers ─────────────────────────────────────────────────

def sidebar_logo_html() -> str:
    return """
    <div class="sidebar-logo">
        <div class="logo-text">🗣️ Talk to Data</div>
        <div class="logo-sub">Self-Service Intelligence</div>
    </div>
    """


def hero_html(mode: str = "demo") -> str:
    if mode == "upload":
        return """
        <div class="main-hero">
            <h1>Talk to Your Data</h1>
            <p>Upload any CSV or Parquet file and start asking questions instantly</p>
        </div>
        """
    return """
    <div class="main-hero">
        <h1>Talk to Data</h1>
        <p>Ask natural language questions — get instant, verified insights</p>
    </div>
    """


def empty_state_html(mode: str = "demo") -> str:
    if mode == "upload":
        return """
        <div class="empty-state">
            <div class="icon">📁</div>
            <h3>No data loaded yet</h3>
            <p>Upload a CSV or Parquet file from the sidebar to start asking questions about your data.</p>
        </div>
        """
    return """
    <div class="empty-state">
        <div class="icon">💬</div>
        <h3>Start a conversation</h3>
        <p>Ask a question about orders, customers, products, or complaints. Try one of the examples in the sidebar!</p>
    </div>
    """


def meta_badges_html(route: dict, cached: bool, time_ms: float) -> str:
    parts = []
    if cached:
        parts.append('<span class="meta-badge cached">⚡ Cached</span>')
    if route:
        intent = route.get("intent", "")
        pattern = route.get("pattern", "")
        if intent:
            parts.append(f'<span class="meta-badge intent">{intent}</span>')
        if pattern:
            parts.append(f'<span class="meta-badge pattern">{pattern}</span>')
    parts.append(f'<span class="meta-badge time">⏱ {time_ms:.0f}ms</span>')
    return " ".join(parts)


def confidence_html(score: int | None) -> str:
    if score is None:
        return ""
    if score >= 8:
        level = "high"
    elif score >= 5:
        level = "medium"
    else:
        level = "low"
    pct = score * 10
    return f"""
    <div class="confidence-meter">
        <div class="confidence-bar">
            <div class="confidence-fill {level}" style="width: {pct}%"></div>
        </div>
        <span class="confidence-label {level}">{score}/10</span>
    </div>
    """


def source_tag_html(filename: str, rows: int = 0) -> str:
    row_str = f" • {rows:,} rows" if rows else ""
    return f'<span class="source-tag">📄 {filename}{row_str}</span>'
