# 🗣️ Talk to Data — Multi-Agent AI Analytics Platform

> Ask questions about your data in plain English. Get instant, accurate answers with charts, insights, and full transparency — powered by a custom multi-agent AI pipeline.

<p align="left">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black" />
  <img src="https://img.shields.io/badge/Groq-Llama_3.3-F55036?style=flat-square" />
  <img src="https://img.shields.io/badge/License-Apache_2.0-blue?style=flat-square" />
</p>

---

## 📖 Overview

**Talk to Data** is a multi-agent AI system that enables non-technical users to query structured and unstructured data using natural language.

Instead of writing SQL or navigating dashboards, users simply type a question — like:

> *"Why did revenue drop in the South region?"*

…and receive a clear, executive-friendly answer backed by charts and reasoning.

It solves **data democratization** by removing dependency on data teams.

---

## ✨ Features

### ⚙️ Core AI Pipeline

* Multi-agent architecture (Router → SQL Generator → Validator → Answer Generator)
* Intent classification (SQL / RAG / Hybrid)
* Pattern-aware SQL generation
* Self-healing SQL retries
* SQL safety validation (only SELECT allowed)

### 🧠 Semantic Intelligence

* YAML-based semantic layer
* Few-shot retrieval using FAISS
* Semantic caching (~50ms responses)
* RAG over documents

### 🎯 UX

* Upload your own dataset (CSV / Parquet)
* Auto data profiling
* Interactive charts (Plotly)
* KPI cards + follow-up suggestions
* Conversation memory
* Transparency panel (SQL + reasoning)

---

## 🛠️ Setup

### 1. Clone

```bash
git clone https://github.com/VishardMehta/talk-to-data.git
cd talk-to-data
```

### 2. Backend

```bash
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 3. Env

```bash
cp .env.example .env
```

Add:

```
GROQ_API_KEY=your_key
```

### 4. Seed DB

```bash
python data/seed.py
```

### 5. Run

```bash
streamlit run app/main.py
```

---

## 🚀 Usage

Try:

```
What is total revenue?
Revenue by region
Why did revenue drop in March?
Compare North vs South
```

---

## 🧠 Architecture

<p align="center">
  <img src="assets/architecture.svg" width="700"/>
</p>

---

## 🧰 Tech Stack

* Groq (LLMs)
* FAISS (vector search)
* DuckDB + SQLite
* Streamlit (backend UI)
* React + Vite (frontend)
* Plotly (charts)

---

## ⚠️ Limitations

* Groq free tier limits
* No real-time DB connections
* FAISS is in-memory
* Single-user sessions

---

## 🔮 Future Work

* Persistent vector DB
* Multi-user auth
* Live DB connectors
* Streaming responses
* Advanced charts

---

## 📁 Structure

```
app/
config/
data/
frontend/
```

---

## 🏁 Final Note

Built for NatWest Hackathon 2026 🚀
