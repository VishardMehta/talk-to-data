"""
groq_client.py — backward-compatibility shim.

All actual LLM logic has moved to app/core/llm_client.py which supports
both OpenRouter (preferred) and Groq (fallback).

Existing code that imports call_llm from here continues to work unchanged.
"""
from app.core.llm_client import call_llm  # noqa: F401

# Expose a MODELS dict so any legacy code that reads it keeps working.
MODELS = {
    "fast": "llama-3.1-8b-instant",
    "smart_sql": "qwen/qwen3-32b",
    "smart_answer": "llama-3.3-70b-versatile",
    "smart": "llama-3.3-70b-versatile",
}
