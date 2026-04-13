# 🗣️ Talk to Data — Multi-Agent AI Analytics Platform

> Ask questions about your data in plain English. Get accurate answers, interactive charts, and transparent reasoning — powered by a custom multi-agent AI pipeline.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-LLM-F55036?style=flat-square)
![License](https://img.shields.io/badge/License-Apache_2.0-blue?style=flat-square)

---

## 📖 Overview

**Talk to Data** is a multi-agent AI analytics system that enables non-technical users to query their own datasets using natural language. Instead of writing SQL or navigating complex dashboards, users simply upload their data and ask questions like *"What are my top 10 customers by revenue?"* or *"Show me the trend over time"* — and receive clear, data-backed answers with visualizations.

The system solves the problem of **data accessibility for non-technical teams**: business analysts, product managers, and executives often depend on data teams for insights. Talk to Data removes that bottleneck by translating plain English into accurate SQL, executing it against user-uploaded data, and synthesizing results into human-readable answers — all within seconds.

The intended users are **non-technical business stakeholders** who need quick, data-driven answers without learning SQL or BI tools. The platform is intentionally **upload-only by design** — all analysis is grounded in user-provided data with no demo fallbacks.

---

## ✨ Features

### Core AI Pipeline
- **Multi-agent architecture** — Four specialized AI agents (Router → SQL Generator → Executor/Validator → Answer Generator) work in sequence to process each query with high accuracy.
- **Pattern-aware SQL generation** — Recognizes analytical patterns (Breakdown, Comparison, Change Analysis, Summary, General) and applies pattern-specific prompt templates for better SQL.
- **Self-healing SQL with retry** — If generated SQL fails execution, the system retries with error feedback for auto-correction.
- **Query classification and semantic caching** — Repeated or semantically similar questions are served from an embedding-based cache for faster responses.
- **Strict upload-only execution path** — No demo fallback ensures all analysis is grounded in user-provided data.

### Data Intelligence
- **Auto-semantic profiling on upload** — Automatically profiles column types, value distributions, inferred metrics, and dimensions to build query context.
- **Robust JSON ingestion** — Multi-strategy loading with fallback normalization for handling various data formats.
- **DuckDB in-memory query engine** — High-performance analytics on uploaded files without requiring database setup.
- **Auto-generated verified query examples** — Creates contextual examples from uploaded schema to guide the SQL generator.

### User Experience
- **React 19 + Vite premium chat interface** — Modern, responsive UI with smooth animations.
- **SSE streaming for step-by-step thinking** — Real-time visibility into the agent pipeline as it processes queries.
- **Smart chart payload conversion** — Automatic chart generation with metric-priority selection (prioritizes metrics like `wins` over identifier columns).
- **Follow-up question suggestions** — Each answer includes AI-generated follow-up questions for guided exploration.
- **Technical transparency panel** — Expandable section showing the SQL query, execution timing, and confidence scores.
- **Premium dark UI** — ChatGPT-inspired dark glassmorphism interface built with Tailwind CSS + Framer Motion.

### Data Capabilities
- **Multi-format upload support** — CSV, JSON, SQLite/DB files, and Parquet.
- **Single dataset per session** — Clean, focused analysis on one uploaded dataset at a time.
- **Session management** — Clear session state and start fresh with new data.

---

## 🛠️ Install and Run Instructions

### Prerequisites

- **Python 3.10+**
- **Node.js 18+** and **npm**
- A free [Groq API key](https://console.groq.com/) (sign up and generate a key)

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/talk-to-data.git
cd talk-to-data
```

### 2. Backend Setup (Python)

```bash
# Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
# Copy the example env file and add your Groq API key
copy .env.example .env
```

Open `.env` and replace the placeholder with your actual Groq API key:

```env
GROQ_API_KEY=gsk_your_actual_key_here
```

### 4. Run the FastAPI Backend

```bash
uvicorn api.server:app --reload --port 8000
```

Backend health check:
```
http://localhost:8000/api/health
```

### 5. Run the React Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:
```
http://localhost:5173
```

> **Note:** The React frontend connects to the backend API at `http://localhost:8000`. Both must be running for full functionality.

---

## 🧰 Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **AI / LLM** | [Groq API](https://groq.com/) | LLM inference for routing, SQL generation, and answer synthesis |
| **Embeddings** | [sentence-transformers](https://www.sbert.net/) (`all-MiniLM-L6-v2`) | Semantic similarity for caching and query classification |
| **Database Engine** | [DuckDB](https://duckdb.org/) | In-memory analytics on uploaded files |
| **Backend API** | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) | Upload, query, and session APIs |
| **Frontend** | React 19 + TypeScript + Vite | Premium chat interface |
| **Frontend Styling** | Tailwind CSS v4 + Framer Motion | Responsive design with micro-animations |
| **Charts** | [Recharts](https://recharts.org/) | Interactive chart rendering |
| **State Management** | [Zustand](https://zustand-demo.pmnd.rs/) | Lightweight client-side state |
| **UI Components** | Radix UI + Lucide Icons | Accessible, composable primitives |
| **Config** | PyYAML | Prompt templates and configuration support |
| **Languages** | Python 3.10+, TypeScript | Backend intelligence + Frontend UI |

> **Design constraint:** No LangChain, no CrewAI, no agent frameworks. All agents are implemented as explicit Python modules using raw Groq SDK calls for clarity and debuggability.

---

## 🚀 Usage Examples

Once the app is running, follow these steps:

1. **Upload your dataset** — Drag and drop a CSV, JSON, SQLite, or Parquet file.
2. **Wait for auto-profiling** — The system analyzes your data (column types, distributions, metrics, dimensions).
3. **Ask questions** like:

### Breakdown Queries

```
Top 10 players by tournament wins
```
→ Returns a ranked table + auto-generated bar chart.

```
Revenue by region
```
→ Returns a breakdown with metric-priority chart selection.

### Comparisons

```
Compare team A vs team B performance
```
→ Side-by-side comparison with percentage differences.

### Trend Analysis

```
Show trend over time
```
→ Time-series line chart with aggregated metrics.

### General Queries

```
Which player has the highest win rate among the top 10?
```
→ Complex analytical query with filtered rankings.

### Follow-ups

```
Now show me that by category
```
→ Uses conversation context from the previous query.

### Sample Input/Output

**Input:** `"Top 10 players by tournament wins"`

**Output:**
> Here are the top 10 players by tournament wins:
> 1. Player A — 45 wins
> 2. Player B — 38 wins
> ...

*+ A bar chart + data table + "How I got this" panel with the SQL query + follow-up suggestions*

---

## 🏗️ Architecture

### Multi-Agent Query Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                      User Interface                         │
│              React 19 + Vite + Tailwind CSS                 │
└────────────────────────┬────────────────────────────────────┘
                         │  User Question
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Semantic Cache                            │
│   Embedding similarity check                               │
│   Hit → return cached answer                               │
└────────────────────────┬────────────────────────────────────┘
                         │  Cache Miss
                         ▼
┌─────────────────────────────────────────────────────────────┐
│               Agent 1: Router                               │
│   Classifies → intent (STRUCTURED | UNSTRUCTURED)          │
│             → pattern (BREAKDOWN | COMPARISON |            │
│                       CHANGE_ANALYSIS | SUMMARY | GENERAL)  │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│          Agent 2: Upload SQL Generator                      │
│   Pattern-specific prompts + schema context                 │
│   DuckDB-aware SQL generation                               │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│          Agent 3: Executor / Validator                      │
│   Schema whitelist check → Execute → Empty check           │
│   Retry with error feedback (if needed)                    │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│          Agent 4: Answer Generator                          │
│   Synthesizes: SQL results → plain English                 │
│   Outputs: answer + chart suggestion + follow-up questions │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│              Chart Payload Converter                        │
│   Smart metric-priority selection                          │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│              SSE Result Stream                              │
│   Step-by-step thinking events → Frontend                  │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```
User Question
  → Semantic Cache (check)
  → Router Agent (classify intent + pattern)
  → Upload SQL Generator (pattern-specific prompts + schema context)
  → DuckDB Execute
  → Retry with error feedback (if needed)
  → Answer Generator (results → natural language + chart)
  → Chart Payload Converter (metric-priority selection)
  → Semantic Cache (store)
  → SSE Stream to Frontend (answer + chart + follow-ups)
```

### Key Design Decisions

- **No agent frameworks** — Each agent is a plain Python module that calls the Groq API directly. This keeps the system simple, debuggable, and free of abstraction overhead.
- **Pattern-aware SQL generation** — Recognizing analytical patterns (breakdown, comparison, change analysis, summary, general) allows the system to apply pattern-specific prompt templates, dramatically improving SQL accuracy.
- **Self-healing SQL** — When SQL execution fails, the error message is fed back to the SQL generator for automatic correction and retry.
- **Upload-only by design** — Removing demo fallbacks ensures all analysis is grounded in user-provided data, preventing hallucinated answers.
- **SSE streaming** — Real-time step-by-step visibility into the agent pipeline provides transparency and improves perceived performance.

---

## ⚠️ Limitations

- **Groq rate limits** — LLM quality and latency depend on Groq model availability and rate limits on the free tier.
- **Single dataset per session** — The main query path supports one active uploaded dataset per session.
- **No built-in auth/multi-tenant persistence** — Vector stores and caches are in-memory per runtime/session.
- **File-based data only** — Supports uploaded files (CSV, JSON, SQLite, Parquet) but not live database connections.
- **React frontend requires separate backend** — The premium React UI needs the FastAPI backend running independently.

---

## 🔮 Future Improvements

- **Multi-file upload with join detection** — Upload multiple files and auto-detect common columns for suggested joins.
- **Persistent vector store** — Save embedding caches to disk to avoid re-indexing on every restart.
- **Live database connectors** — Support connecting to PostgreSQL, MySQL, or BigQuery for real-time querying.
- **Multi-user authentication** — Add user accounts with session isolation and query history.
- **Export & sharing** — Allow users to export answers, charts, and data tables as PDF or shareable links.
- **Advanced visualizations** — Add heatmaps, scatter plots, and funnel charts based on richer chart suggestions.
- **Streaming LLM responses** — Implement token-by-token streaming from the LLM for a more interactive experience.

---

## 📁 Folder Structure

```
talk-to-data/
├── api/                          # FastAPI backend
│   ├── server.py                 # Main FastAPI application
│   ├── session.py                # Session management
│   └── chart_converter.py        # Chart payload conversion
├── app/                          # Core application logic
│   ├── agents/                   # AI agent modules
│   │   ├── router.py             # Agent 1 — Intent & pattern classification
│   │   ├── sql_generator.py      # Agent 2 — SQL generation (base)
│   │   ├── upload_sql_generator.py # SQL generation for uploads (DuckDB)
│   │   ├── validator.py          # Agent 3 — Schema validation + execution
│   │   └── answer_generator.py   # Agent 4 — Natural language answer synthesis
│   ├── core/                     # Core infrastructure
│   │   ├── auto_semantic.py      # Auto-profiling + LLM enrichment for uploads
│   │   ├── cache.py              # Embedding-based semantic cache
│   │   ├── duckdb_engine.py      # DuckDB engine for upload mode
│   │   ├── groq_client.py        # Shared Groq LLM client wrapper
│   │   ├── query_classifier.py   # Query classification logic
│   │   ├── state.py              # Conversation state management
│   │   └── vector_store.py       # Vector store for embeddings
│   └── utils/                    # Utility modules
│       ├── chart_generator.py    # Chart generation utilities
│       └── sql_parser.py         # SQL parsing utilities
├── data/                         # Data layer
│   └── uploads/                  # Uploaded file storage
├── frontend/                     # React premium UI
│   ├── src/
│   │   ├── components/           # UI components (ChatMessage, Sidebar, etc.)
│   │   ├── store/                # Zustand state management
│   │   ├── lib/                  # API client with SSE streaming
│   │   └── types/                # TypeScript type definitions
│   ├── package.json
│   └── vite.config.ts
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
├── .gitignore
└── README.md
```

---

## 🧪 Testing the Pipeline

After setup, verify the system works with these queries in order:

| # | Query | Expected Behavior |
|---|---|---|
| 1 | `Show me the first 5 rows` | Data preview table |
| 2 | `What columns are in this dataset?` | Schema overview |
| 3 | `Top 10 by [metric column]` | Breakdown → table + bar chart |
| 4 | `Compare [category A] vs [category B]` | Comparison → side-by-side values |
| 5 | `Show trend over time` | Time-series → line chart |
| 6 | `Summarize the data` | Summary → multi-metric overview |
| 7 | Repeat query #3 | Cache hit → faster response |

---

## 📝 Technical Depth: Why These AI Choices?

### Multi-Agent Pipeline vs. Single-Prompt

A single LLM call to go from question → SQL → answer would be brittle and hard to debug. By decomposing the task into specialized agents, each step can be validated independently:

- The **Router** classifies intent and pattern — a focused task that sets up the pipeline.
- The **Upload SQL Generator** receives pattern-specific prompts and schema context — this dramatically improves SQL accuracy over zero-shot generation.
- The **Validator** applies schema checks and executes the SQL — mostly deterministic code before expensive execution.
- The **Answer Generator** receives structured results and synthesizes them into natural language — this separation prevents the LLM from "hallucinating" data.

### Semantic Profiling for Grounding

Auto-semantic profiling acts as a **grounding mechanism**: instead of letting the LLM guess column names and types, we inject enriched schema context with descriptions, sample values, inferred metrics, and dimensions. This reduces hallucination and improves SQL correctness significantly.

### Self-Healing SQL

When SQL execution fails (syntax error, schema mismatch, etc.), the error message is captured and fed back to the SQL generator along with the original question and schema context. The generator then produces corrected SQL for retry — enabling automatic recovery without user intervention.

---

*Built with ❤️ for data democratization*
