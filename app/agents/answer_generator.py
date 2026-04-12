from __future__ import annotations
"""
Answer Generator — Agent 4.
Uses Llama 3.3 70B for best natural language fluency.

Key improvements:
  - Insight-first answers (lead with the story, not the number)
  - Indian number formatting (₹45L, ₹2.3Cr)
  - Specific, context-aware follow-up questions
  - No chart suggestion (handled by chart_generator now)
"""

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


# The core insight-first answer prompt
_ANALYST_SYSTEM = """You are a sharp, senior data analyst presenting findings to a business executive.

RULES:
1. Lead with the INSIGHT, not the number. "The South region is dragging down overall growth" is better than "South region revenue is ₹12L."
2. Format numbers for Indian readability:
   - Under ₹1L: show exact (₹45,000)
   - ₹1L-₹1Cr: use lakhs (₹45.2L)
   - Above ₹1Cr: use crores (₹2.3Cr)
   - For counts: use commas (1,234 orders)
3. Always compare to something — a previous period, another region, an average. Raw numbers without context are meaningless.
4. Use ONE strong sentence, not three weak ones.
5. If the data shows something surprising or concerning, SAY SO. "This is unusual" or "This needs attention" adds value.
6. End with a specific, actionable observation — not generic advice.
7. NEVER say "Based on the data" or "According to the results" — just state the insight directly.
8. Keep it under 3 sentences for simple queries, 4-5 for complex analysis.

BAD: "The total revenue for Q1 is ₹4,500,000. The North region has the highest revenue at ₹1,800,000."
GOOD: "Q1 revenue landed at ₹45L, but the real story is the South — at just ₹9L, it's pulling in half of what North generates. That's your gap to close."

For follow-up suggestions, make them SPECIFIC to what the data showed:
- If one region dominates → suggest investigating WHY
- If there's a trend → suggest comparing with previous period
- If there's an anomaly → suggest drilling into it
- NEVER suggest generic questions like "Would you like more details?"
"""


def generate_answer(
    question: str,
    pattern: str,
    sql_results: dict | None,
    rag_documents: list | None = None,
    sql_used: str | None = None,
    conversation_state: str | None = None,
    query_type: str = "INSIGHT",
) -> dict:
    templates = _get_templates()
    pattern_cfg = templates.get(pattern, templates.get("GENERAL", {}))
    pattern_answer_prompt = pattern_cfg.get("answer_prompt", "")

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
        rag_section = "\n## Customer feedback & complaints\n" + "\n".join(doc_texts) + "\n"

    state_section = ""
    if conversation_state:
        state_section = f"\n## Conversation context\n{conversation_state}\n"

    # Bug fix: the _ANALYST_SYSTEM prompt always forces insight-first narrative,
    # which produces "North dominates at ₹18.5L…" even for a simple COUNT query.
    # Factual/aggregation queries need a direct, precise answer style.
    _FACTUAL_SYSTEM = """You are a precise data analyst answering a direct factual question.

RULES FOR FACTUAL QUERIES:
1. Answer the question directly with the exact number or list from the data.
2. State the fact FIRST. One sentence max for the core answer.
3. You may add one sentence of business context ONLY if it adds real value.
4. Format numbers for Indian readability:
   - Counts: use commas (1,234)
   - Currency under ₹1L: ₹45,000 | ₹1L-₹1Cr: ₹45.2L | above ₹1Cr: ₹2.3Cr
5. NEVER produce a narrative when a number is the answer.
6. NEVER say "Based on the data" or "According to the results".

EXAMPLES:
  Q: "How many regions are there?"
  A: "There are 4 regions: North, South, East, and West."

  Q: "Total number of orders per region?"
  A: "North leads with 1,240 orders, followed by South (980), East (870), and West (760)."

  Q: "Which region has the most accepted orders?"
  A: "North has the highest count of completed orders at 1,240 — roughly 30% more than second-place South."
"""

    is_factual = query_type in (
        "COUNT", "COUNT_DISTINCT", "AGGREGATION", "RANKING", "LIST"
    )
    base_system = _FACTUAL_SYSTEM if is_factual else _ANALYST_SYSTEM

    system_prompt = f"""{base_system}

## PATTERN-SPECIFIC GUIDANCE
{pattern_answer_prompt}

{data_section}{rag_section}{state_section}
Return ONLY valid JSON:
{{
  "answer": "<{"direct factual answer" if is_factual else "insight-first plain English answer"}>",
  "follow_up_questions": ["<specific question based on what data showed>", "<another specific question>"]
}}

Do NOT include chart_suggestion — charts are handled separately.
"""

    user_message = f'Question: "{question}"'
    if sql_used:
        user_message += f"\nSQL used: {sql_used[:300]}"

    result = call_llm(
        model_key="smart_answer",  # Llama 3.3 70B for best natural language
        system_prompt=system_prompt,
        user_message=user_message,
        temperature=0.3,
        json_mode=True,
    )

    result.setdefault("answer", "I was unable to generate an answer.")
    result.setdefault("follow_up_questions", [])
    # No chart_suggestion — handled by chart_generator deterministically
    result.setdefault("chart_suggestion", None)
    return result
