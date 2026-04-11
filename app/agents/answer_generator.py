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

    system_prompt = f"""{answer_instructions}

{data_section}{rag_section}{state_section}
Return ONLY valid JSON:
{{
  "answer": "<plain English answer>",
  "follow_up_questions": ["<question 1>", "<question 2>"],
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
        model_key="smart",
        system_prompt=system_prompt,
        user_message=user_message,
        temperature=0.3,
        json_mode=True,
    )

    result.setdefault("answer", "I was unable to generate an answer.")
    result.setdefault("follow_up_questions", [])
    result.setdefault("chart_suggestion", None)
    return result
