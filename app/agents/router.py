"""
Agent 1 — Query Router.

Classifies a user question into intent + analytical pattern.
Dataset-agnostic: no hardcoded domain assumptions.
"""
from app.core.llm_client import call_llm

_SYSTEM = """You are a query router for a data analytics assistant.

Your job: classify the user's question into an intent and an analytical pattern.

## Available data
{schema_summary}

## Intents
- STRUCTURED   — answer requires running SQL against the uploaded data tables
- OUT_OF_SCOPE — question cannot be answered with the available data (e.g. general knowledge, unrelated topics)

## Analytical Patterns (for STRUCTURED)
- CHANGE_ANALYSIS — "how did X change", trend over time, month-over-month, "why did it drop/rise"
- COMPARISON      — "compare A vs B", "which is better/more/higher", side-by-side evaluation
- BREAKDOWN       — "by category/region/team", distribution, "group by", top-N per group
- SUMMARY         — "overview", "key metrics", "tell me about", "how many total"
- GENERAL         — specific lookup, single-row fetch, "who/what/which is X", ranking

## Classification Rules
- Any question that can be answered by querying the uploaded tables → STRUCTURED
- Only use OUT_OF_SCOPE if the question is CLEARLY unrelated to the available data
- Follow-up questions (e.g. "why?", "show by month", "what about last year") → STRUCTURED
- Questions mentioning column names or values from the schema → STRUCTURED

## Pattern selection hints
- CHANGE_ANALYSIS: "trend", "over time", "monthly", "weekly", "how did", "increase/decrease"
- COMPARISON: "compare", "vs", "versus", "difference", "better", "higher/lower than"
- BREAKDOWN: "by X", "breakdown", "distribution", "top N", "per category"
- SUMMARY: "summary", "overview", "total", "how many", "count", "average", "mean"
- GENERAL: specific entity lookup, "who won", "what is the value of X", "show me row where"

{state_context}

Return ONLY valid JSON:
{{
  "intent": "STRUCTURED" | "OUT_OF_SCOPE",
  "pattern": "CHANGE_ANALYSIS" | "COMPARISON" | "BREAKDOWN" | "SUMMARY" | "GENERAL",
  "reasoning": "one sentence",
  "is_followup": true | false,
  "requires_long_answer": true | false
}}

Set requires_long_answer=true for: multi-entity analysis, "compare all X", "detailed breakdown", COMPARISON of 3+ items.
"""


def route(question: str, schema_summary: str, conversation_state: str) -> dict:
    state_section = ""
    if conversation_state:
        state_section = f"\n## Previous conversation context\n{conversation_state}\n"

    system = _SYSTEM.format(
        schema_summary=schema_summary,
        state_context=state_section,
    )

    try:
        result = call_llm(
            model_key="router",
            system_prompt=system,
            user_message=question,
            temperature=0.0,
            json_mode=True,
        )
    except Exception as e:
        print(f"[router] LLM JSON response failed, using safe defaults: {e}")
        result = {}

    # Some models return arrays or raw strings even in json_mode.
    if isinstance(result, list):
        result = result[0] if result and isinstance(result[0], dict) else {}
    elif not isinstance(result, dict):
        result = {}

    result.setdefault("intent", "STRUCTURED")
    result.setdefault("pattern", "GENERAL")
    result.setdefault("reasoning", "")
    result.setdefault("is_followup", False)
    result.setdefault("requires_long_answer", False)

    # Normalize to supported enum values.
    if result.get("intent") not in ("STRUCTURED", "OUT_OF_SCOPE"):
        result["intent"] = "STRUCTURED"
    if result.get("pattern") not in (
        "CHANGE_ANALYSIS", "COMPARISON", "BREAKDOWN", "SUMMARY", "GENERAL"
    ):
        result["pattern"] = "GENERAL"

    return result
