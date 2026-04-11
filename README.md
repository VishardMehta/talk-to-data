# Talk to Data 🗣️

A multi-agent AI system that lets non-technical users ask natural language questions about data and get accurate answers.

## Features

- **Natural Language Queries** — Ask questions in plain English, get SQL-backed answers
- **Multi-Agent Architecture** — Router → SQL Generator → Validator → Answer Generator
- **Hybrid Queries** — Combines structured (SQL) and unstructured (RAG) data
- **Semantic Cache** — Instant responses for similar questions
- **Auto Charts** — Plotly visualizations generated automatically
- **Conversation Memory** — Follow-up questions maintain context

## Tech Stack

- **LLMs**: Groq API (Llama 3.1 8B + Llama 3.3 70B) — free tier
- **Database**: SQLite
- **Vector Search**: FAISS + sentence-transformers
- **Frontend**: Streamlit
- **Charts**: Plotly

## Setup

```bash
# 1. Clone and enter
git clone https://github.com/VishardMehta/talk-to-data.git
cd talk-to-data

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment
cp .env.example .env
# Edit .env and add your Groq API key (free at console.groq.com)

# 4. Initialize demo database
python data/seed.py

# 5. Run the app
streamlit run app/main.py
```

## Architecture

```
User Question
    │
    ▼
┌─────────┐     ┌──────────────┐     ┌───────────┐     ┌──────────────────┐
│  Router  │────▶│ SQL Generator│────▶│ Validator  │────▶│ Answer Generator │
│ (8B LLM) │     │  (70B LLM)   │     │ (Code-only)│     │   (70B LLM)      │
└─────────┘     └──────────────┘     └───────────┘     └──────────────────┘
    │                                                           │
    │  UNSTRUCTURED path                                        │
    └──────────────▶ RAG Search ───────────────────────────────▶│
```

## Demo Dataset

E-commerce dataset with:
- **2000+ orders** (Jan 2024 – Mar 2025)
- **200 customers** across 10 Indian cities
- **50 products** in 5 categories
- **300 complaints** with detailed text
- **100+ unstructured documents** for RAG

## License

MIT
