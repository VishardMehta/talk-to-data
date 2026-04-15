# Talk to Data - Multi-Agent AI Analytics Platform

Ask questions about your data in plain English. Get accurate answers, charts, and transparent reasoning through a custom multi-agent pipeline.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-LLM-F55036?style=flat-square)
![License](https://img.shields.io/badge/License-Apache_2.0-blue?style=flat-square)

---

## Overview

Talk to Data is a multi-agent analytics system for non-technical users.
Users upload their own dataset, ask questions in natural language, and receive:

- SQL-backed answers
- interactive charts
- follow-up suggestions
- transparent query details

The platform is now upload-only by design. Demo dataset mode and demo routing were removed to ensure all analysis is grounded in user-provided data.

---

## Features

### AI Pipeline

- Multi-agent architecture: Router -> SQL Generator -> Executor/Validator -> Answer Generator.
- Pattern-aware SQL generation for breakdowns, comparisons, change analysis, summaries, and general analytical prompts.
- Self-healing SQL retry on execution errors with error-feedback regeneration.
- Query classification and semantic caching for faster repeated questions.
- Strict upload-only execution path (no demo fallback).

### Data Intelligence

- Auto-semantic profiling on upload (column types, distributions, inferred metrics/dimensions).
- Robust JSON ingestion with multi-strategy loading and fallback normalization.
- DuckDB in-memory query engine for high-performance analytics.
- Auto-generated verified query examples from uploaded schema context.

### UX and Transparency

- React 19 + Vite premium chat interface.
- SSE streaming for step-by-step thinking events.
- Smart chart payload conversion with metric-priority selection.
- Follow-up question suggestions per response.
- Technical transparency panel (SQL + timing + confidence).

---

## Upload-Only Data Sources

The current codebase is designed to analyze user-uploaded datasets only.

Supported file types in the app flow:

- CSV
- JSON
- SQLite/DB files
- Parquet (accepted by upload components and DuckDB reader)

---

## Install and Run

### Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- Groq API key

### 1. Backend setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment setup

```bash
copy .env.example .env
```

Set your key in `.env`:

```env
GROQ_API_KEY=gsk_your_actual_key_here
```

### 3. Run API backend

```bash
uvicorn api.server:app --reload --port 8000
```

Backend health:

```text
http://localhost:8000/api/health
```

### 4. Run frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

---

## Architecture

## Query Flow

```text
User Question
	-> Semantic Cache check
	-> Router (intent + pattern)
	-> Upload SQL Generator (DuckDB-aware)
	-> DuckDB execute
	-> Retry with error feedback (if needed)
	-> Answer Generator
	-> Chart payload converter
	-> SSE result to frontend
```

## API Endpoints

- `GET /api/health`
- `POST /api/upload`
- `POST /api/query/stream`
- `POST /api/query`
- `POST /api/session/clear`

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| AI/LLM | Groq API | Routing, SQL generation, answer synthesis |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) | Semantic cache similarity |
| Database Engine | DuckDB | In-memory analytics on uploaded files |
| Backend API | FastAPI + Uvicorn | Upload/query/session APIs |
| Frontend | React 19 + TypeScript + Vite | Chat UI and visual interaction |
| Styling | TailwindCSS + Framer Motion | Responsive premium interface |
| Charts | Recharts | Interactive chart rendering |
| State | Zustand | Client-side app/session state |
| Config | PyYAML | Prompt template and config support |

---

## Usage Example

1. Start backend and frontend.
2. Upload your dataset.
3. Ask questions like:

```text
Top 10 players by tournament wins
Which player has the highest win rate among the top 10?
Show trend over time
```

Expected behavior:

- answers are generated from uploaded data only
- chart axes prioritize real metrics (for example `wins`) over identifier columns
- follow-up questions remain contextual to the same uploaded dataset/session

---

## Current Constraints

- Single active uploaded dataset per session in the main query path.
- LLM quality and latency depend on Groq model availability and rate limits.
- No built-in auth/multi-tenant persistence yet.
- Vector stores and caches are in-memory per runtime/session.

---

## Folder Structure

```text
.
├── api/
│   ├── server.py
│   ├── session.py
│   └── chart_converter.py
├── app/
│   ├── agents/
│   │   ├── router.py
│   │   ├── sql_generator.py
│   │   ├── upload_sql_generator.py
│   │   ├── validator.py
│   │   └── answer_generator.py
│   ├── core/
│   │   ├── auto_semantic.py
│   │   ├── cache.py
│   │   ├── duckdb_engine.py
│   │   ├── groq_client.py
│   │   ├── query_classifier.py
│   │   ├── state.py
│   │   └── vector_store.py
│   └── utils/
│       ├── chart_generator.py
│       └── sql_parser.py
├── data/
│   └── uploads/
├── frontend/
│   ├── src/
│   └── package.json
├── assets/
├── requirements.txt
└── .env.example
```

---

## Notes

- This repository intentionally does not rely on agent orchestration frameworks.
- Core agent behavior is implemented as explicit Python modules for clarity and debuggability.
