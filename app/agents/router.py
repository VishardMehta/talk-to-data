"""
Agent 1 — Router
Classifies user intent (STRUCTURED/UNSTRUCTURED/HYBRID/OUT_OF_SCOPE)
and identifies the analytical pattern (CHANGE_ANALYSIS/COMPARISON/BREAKDOWN/SUMMARY/GENERAL).

Uses Llama 3.1 8B (fast model) for quick classification.
"""

from app.core.groq_client import call_llm


ROUTER_SYSTEM_PROMPT = """You are a query router for a data analytics system. Your job is to classify the user's question.

{schema_summary}

You must classify the question into:

INTENT (what type of data is needed):
- STRUCTURED: The question requires SQL queries against the database tables (orders, customers, products, complaints). Examples: "total revenue", "orders by region", "top customers"
- UNSTRUCTURED: The question requires searching through complaint/feedback text documents. Examples: "what are people complaining about?", "customer sentiment", "common issues"  
- HYBRID: The question needs BOTH SQL data AND document search. Examples: "why did revenue drop and what complaints explain it?", "which region has issues and what are customers saying?"
- OUT_OF_SCOPE: The question cannot be answered with the available data (e-commerce orders, customers, products, complaints). Examples: "what's the weather?", "tell me a joke", "stock price of Apple"

PATTERN (what type of analysis):
- CHANGE_ANALYSIS: Question asks WHY something changed, increased, or decreased. Trigger words: "why", "what caused", "reason for", "drop", "increase", "spike", "change"
- COMPARISON: Question compares two or more things. Trigger words: "compare", "vs", "versus", "difference between", "which is better"
- BREAKDOWN: Question asks for decomposition of a metric. Trigger words: "breakdown", "composition", "what makes up", "by category", "by region", "distribution"
- SUMMARY: Question asks for an overview or summary. Trigger words: "summary", "overview", "dashboard", "key metrics", "how are we doing"
- GENERAL: Any other data question that doesn't fit above patterns. Default if unsure.

{state_context}

Return ONLY valid JSON with this exact structure:
{{
    "intent": "STRUCTURED" | "UNSTRUCTURED" | "HYBRID" | "OUT_OF_SCOPE",
    "pattern": "CHANGE_ANALYSIS" | "COMPARISON" | "BREAKDOWN" | "SUMMARY" | "GENERAL",
    "reasoning": "one sentence explaining the classification",
    "is_followup": true | false
}}"""


def route(question: str, schema_summary: str, conversation_state: str = "") -> dict:
    """
    Classify the user's question by intent and analytical pattern.

    Args:
        question: The user's natural language question
        schema_summary: Short summary of available tables/documents
        conversation_state: Previous conversation context (empty if first turn)

    Returns:
        Dict with 'intent', 'pattern', 'reasoning', 'is_followup'
    """
    state_section = ""
    if conversation_state:
        state_section = f"\nConversation context:\n{conversation_state}\nIf the question seems like a follow-up to the previous context, set is_followup to true."

    system = ROUTER_SYSTEM_PROMPT.format(
        schema_summary=schema_summary,
        state_context=state_section,
    )

    try:
        result = call_llm(
            model_key="fast",
            system_prompt=system,
            user_message=question,
            temperature=0.0,
            json_mode=True,
        )
        
        # Validate the response
        valid_intents = {"STRUCTURED", "UNSTRUCTURED", "HYBRID", "OUT_OF_SCOPE"}
        valid_patterns = {"CHANGE_ANALYSIS", "COMPARISON", "BREAKDOWN", "SUMMARY", "GENERAL"}
        
        if result.get("intent") not in valid_intents:
            result["intent"] = "STRUCTURED"
        if result.get("pattern") not in valid_patterns:
            result["pattern"] = "GENERAL"
        if "is_followup" not in result:
            result["is_followup"] = False
        if "reasoning" not in result:
            result["reasoning"] = ""
        
        return result

    except Exception as e:
        # Fallback classification
        return {
            "intent": "STRUCTURED",
            "pattern": "GENERAL",
            "reasoning": f"Fallback classification due to error: {str(e)[:100]}",
            "is_followup": False,
        }
