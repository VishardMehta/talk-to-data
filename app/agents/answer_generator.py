"""
Agent 4 — Answer Generator
Synthesizes natural language answers from SQL results and/or RAG documents.

Uses Llama 3.3 70B with pattern-specific prompts to produce
clear, business-friendly answers with chart suggestions and follow-ups.
"""
from __future__ import annotations

import os
import yaml
from app.core.groq_client import call_llm

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PATTERNS_PATH = os.path.join(_BASE_DIR, "config", "pattern_templates.yaml")

# Load pattern templates once
with open(_PATTERNS_PATH, "r") as f:
    _PATTERNS = yaml.safe_load(f).get("patterns", {})


ANSWER_SYSTEM_PROMPT = """You are a data analyst presenting findings to a non-technical business user.

{answer_instructions}

{results_section}

{rag_section}

{state_section}

RULES:
- Answer in plain English, no technical jargon, no SQL
- Use ₹ symbol for currency amounts
- Format large numbers with commas (e.g., ₹4,50,000 or ₹4.5L for lakhs)
- Be specific: use exact numbers from the data, don't be vague
- Always suggest 2 relevant follow-up questions as natural next steps
- Suggest an appropriate chart type that would visualize this data well

Return ONLY valid JSON:
{{
    "answer": "Your clear, concise answer here.",
    "follow_up_questions": [
        "Natural follow-up question 1?",
        "Natural follow-up question 2?"
    ],
    "chart_suggestion": {{
        "type": "bar",
        "x_column": "column_name",
        "y_column": "column_name",
        "title": "Chart Title"
    }}
}}"""


def _format_results_table(sql_results: dict) -> str:
    """Format SQL results as a readable table for the LLM."""
    if not sql_results or not sql_results.get("results"):
        return ""

    columns = sql_results.get("columns", [])
    results = sql_results["results"]

    lines = ["=== QUERY RESULTS ==="]
    
    # Header
    lines.append(" | ".join(str(c) for c in columns))
    lines.append("-" * (len(" | ".join(str(c) for c in columns))))
    
    # Rows (limit to 20 for prompt size)
    for row in results[:20]:
        lines.append(" | ".join(str(v) for v in row))
    
    if len(results) > 20:
        lines.append(f"... and {len(results) - 20} more rows")
    
    lines.append(f"\nTotal rows: {len(results)}")
    
    return "\n".join(lines)


def _format_rag_docs(documents: list) -> str:
    """Format RAG documents for the LLM context."""
    if not documents:
        return ""

    lines = ["=== ADDITIONAL CONTEXT FROM DOCUMENTS ==="]
    
    for i, doc in enumerate(documents[:5], 1):
        text = doc.get("text", "")
        region = doc.get("region", "")
        category = doc.get("category", "")
        date = doc.get("date", "")
        score = doc.get("score", 0)
        
        lines.append(f"\n[Document {i}] (relevance: {score:.2f})")
        if region:
            lines.append(f"Region: {region}")
        if category:
            lines.append(f"Category: {category}")
        if date:
            lines.append(f"Date: {date}")
        lines.append(f"Content: {text}")
    
    return "\n".join(lines)


def generate_answer(
    question: str,
    pattern: str,
    sql_results: dict | None = None,
    rag_documents: list | None = None,
    sql_used: str | None = None,
    conversation_state: str | None = None,
) -> dict:
    """
    Generate a natural language answer from data results.

    Args:
        question: Original user question
        pattern: Analytical pattern (CHANGE_ANALYSIS, COMPARISON, etc.)
        sql_results: Dict with 'results', 'columns' from validator
        rag_documents: List of documents from vector search
        sql_used: The SQL query that was executed
        conversation_state: Previous conversation context

    Returns:
        Dict with 'answer', 'follow_up_questions', 'chart_suggestion'
    """
    # Get pattern-specific answer instructions
    pattern_config = _PATTERNS.get(pattern, _PATTERNS.get("GENERAL", {}))
    answer_instructions = pattern_config.get("answer_prompt", "Answer clearly and concisely.")
    chart_type = pattern_config.get("chart_type", "bar")

    # Build results section
    results_section = ""
    if sql_results:
        results_section = _format_results_table(sql_results)
        if sql_used:
            results_section += f"\n\nSQL used: {sql_used}"

    # Build RAG section
    rag_section = _format_rag_docs(rag_documents) if rag_documents else ""

    # Build state section
    state_section = ""
    if conversation_state:
        state_section = f"\n=== CONVERSATION CONTEXT ===\n{conversation_state}"

    system = ANSWER_SYSTEM_PROMPT.format(
        answer_instructions=answer_instructions,
        results_section=results_section,
        rag_section=rag_section,
        state_section=state_section,
    )

    try:
        result = call_llm(
            model_key="smart",
            system_prompt=system,
            user_message=question,
            temperature=0.3,  # Slightly creative for natural language
            json_mode=True,
        )

        # Validate response
        if "answer" not in result:
            result["answer"] = "I found the data but couldn't formulate a clear answer."
        if "follow_up_questions" not in result:
            result["follow_up_questions"] = []
        if "chart_suggestion" not in result:
            # Default chart suggestion based on pattern
            result["chart_suggestion"] = {
                "type": chart_type,
                "x_column": "",
                "y_column": "",
                "title": "Data Visualization",
            }

        return result

    except Exception as e:
        # Graceful fallback
        fallback_answer = "I retrieved the data but encountered an issue generating the analysis."
        
        if sql_results and sql_results.get("results"):
            columns = sql_results.get("columns", [])
            first_row = sql_results["results"][0]
            fallback_answer += f" Here's the raw data: {dict(zip(columns, first_row))}"

        return {
            "answer": fallback_answer,
            "follow_up_questions": [
                "Could you rephrase your question?",
                "Would you like to see the raw data?",
            ],
            "chart_suggestion": None,
        }
