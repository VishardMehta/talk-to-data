from app.core.groq_client import call_llm


_SYSTEM = """You are a query router for a data analytics assistant.

Your job: classify the user's question into an intent and an analytical pattern.

{schema_summary}

## Intents
- STRUCTURED   — answer requires running SQL against database tables
- UNSTRUCTURED — answer requires semantic search over complaint/feedback documents only
- HYBRID       — answer requires BOTH SQL results AND document search
- OUT_OF_SCOPE — question cannot be answered with the available data

## Analytical Patterns (for STRUCTURED / HYBRID)
- CHANGE_ANALYSIS — "why did X change", "what caused the drop/rise", trend explanation
- COMPARISON      — "compare A vs B", "which is better", side-by-side evaluation
- BREAKDOWN       — "breakdown by", "what makes up", "show distribution", "by category/region"
- SUMMARY         — "give me a summary", "overview", "key metrics", "how are we doing"
- GENERAL         — specific lookup, ranking, top-N, anything that doesn't fit above

## Rules
- If the question references order amounts, revenue, products, customers, regions, channels → STRUCTURED
- If the question asks about customer complaints in free-text / sentiment / "what are people saying" → HYBRID or UNSTRUCTURED
- If the question is completely unrelated to e-commerce data → OUT_OF_SCOPE
- If previous context exists and the question is a short follow-up (e.g. "why?", "show me that by category") → set is_followup=true

{state_context}

Return ONLY valid JSON:
{{
  "intent": "STRUCTURED" | "UNSTRUCTURED" | "HYBRID" | "OUT_OF_SCOPE",
  "pattern": "CHANGE_ANALYSIS" | "COMPARISON" | "BREAKDOWN" | "SUMMARY" | "GENERAL",
  "reasoning": "one sentence",
  "is_followup": true | false
}}
"""


def route(question: str, schema_summary: str, conversation_state: str) -> dict:
    state_section = ""
    if conversation_state:
        state_section = f"\n## Previous conversation context\n{conversation_state}\n"

    system = _SYSTEM.format(
        schema_summary=schema_summary,
        state_context=state_section,
    )

    result = call_llm(
        model_key="fast",
        system_prompt=system,
        user_message=question,
        temperature=0.0,
        json_mode=True,
    )

    # Ensure required keys exist
    result.setdefault("intent", "STRUCTURED")
    result.setdefault("pattern", "GENERAL")
    result.setdefault("reasoning", "")
    result.setdefault("is_followup", False)
    return result
