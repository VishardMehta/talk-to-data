import yaml
from pathlib import Path
from app.core.groq_client import call_llm


def _load_templates() -> dict:
    base = Path(__file__).resolve().parent.parent.parent
    path = base / "config" / "pattern_templates.yaml"
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("patterns", {})


_TEMPLATES = None


def _get_templates() -> dict:
    global _TEMPLATES
    if _TEMPLATES is None:
        _TEMPLATES = _load_templates()
    return _TEMPLATES


def _format_results(results: list, columns: list) -> str:
    if not results or not columns:
        return "No data available."
    header = " | ".join(columns)
    sep = "-" * len(header)
    rows = [" | ".join(str(v) for v in row) for row in results[:50]]
    return "\n".join([header, sep] + rows)


def generate_answer(
    question: str,
    pattern: str,
    sql_results: dict | None,
    rag_documents: list | None = None,
    sql_used: str | None = None,
    conversation_state: str | None = None,
) -> dict:
    templates = _get_templates()
    pattern_cfg = templates.get(pattern, templates.get("GENERAL", {}))
    answer_instructions = pattern_cfg.get("answer_prompt", "Answer the question based on the data.")

    # Build context sections
    data_section = ""
    if sql_results and sql_results.get("success"):
        table_str = _format_results(sql_results["results"], sql_results["columns"])
        data_section = f"\n## SQL Query Results\n```\n{table_str}\n```\n"

    rag_section = ""
    if rag_documents:
        doc_texts = []
        for d in rag_documents[:5]:
            text = d.get("text", "")
            region = d.get("region", "")
            date = d.get("date", "")
            doc_texts.append(f"- [{region} | {date}] {text}")
        rag_section = "\n## Additional context from documents\n" + "\n".join(doc_texts) + "\n"

    state_section = ""
    if conversation_state:
        state_section = f"\n## Conversation context\n{conversation_state}\n"

    _ANALYST_RULES = """
You are a sharp, senior data analyst presenting findings to a business executive.

RULES:
1. Lead with the INSIGHT, not the number. "The South region is dragging down overall growth" beats "South region revenue is ₹12L."
2. Format numbers for readability:
   - Under ₹1L: show exact (₹45,000)
   - ₹1L–₹1Cr: use lakhs (₹45.2L)
   - Above ₹1Cr: use crores (₹2.3Cr)
3. Always compare to something — another region, an average, a previous period. Raw numbers without context are meaningless.
4. Use ONE strong sentence, not three weak ones.
5. If the data shows something surprising or concerning, SAY SO explicitly.
6. End with a specific, actionable observation — not generic advice.
7. NEVER say "Based on the data" or "According to the results" — state the insight directly.
8. Keep it under 3 sentences for simple queries, 4–5 for complex analysis.

BAD: "The total revenue for Q1 is ₹4,500,000. The North region has the highest revenue at ₹1,800,000."
GOOD: "Q1 revenue landed at ₹45L, but the real story is the South — at just ₹9L, it's pulling in half of what North generates."

For follow-up suggestions, make them SPECIFIC to what the data showed:
- If one region dominates, suggest investigating WHY
- If there's a trend, suggest comparing with previous period
- If there's an anomaly, suggest drilling into it
- NEVER suggest generic questions like "Would you like more details?"
"""

    system_prompt = f"""{_ANALYST_RULES}

{answer_instructions}

{data_section}{rag_section}{state_section}
Return ONLY valid JSON:
{{
  "answer": "<insight-first plain English answer>",
  "follow_up_questions": ["<specific question 1>", "<specific question 2>"],
  "chart_suggestion": {{
    "type": "bar" | "grouped_bar" | "pie" | "line",
    "x_column": "<column name from results>",
    "y_column": "<column name from results>",
    "title": "<chart title>"
  }}
}}
"""

    user_message = f'Question: "{question}"'
    if sql_used:
        user_message += f'\nSQL used: {sql_used[:300]}'

    result = call_llm(
        model_key="smart_answer",
        system_prompt=system_prompt,
        user_message=user_message,
        temperature=0.3,
        json_mode=True,
    )

    result.setdefault("answer", "I was unable to generate an answer.")
    result.setdefault("follow_up_questions", [])
    result.setdefault("chart_suggestion", None)
    return result
