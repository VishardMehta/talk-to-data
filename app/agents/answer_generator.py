from __future__ import annotations
"""
Answer Generator — Agent 4.

Key behaviours:
  - Entity locking: for ranking/best/worst questions, winner is determined
    deterministically from SQL rows BEFORE the LLM call.
  - Grounding check: after the LLM generates a narrative, we verify it
    mentions the locked entity; if not, we fall back to the deterministic
    template instead of returning a hallucinated answer.
  - Generic domain: no India-specific formatting, no e-commerce assumptions.
  - Insight-first narrative for complex queries, precise factual for counts.
"""

import yaml
import json
import re
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


def _parse_answer_payload(raw: str | dict) -> dict:
    """Parse model output into the expected answer payload safely."""
    if isinstance(raw, dict):
        return raw

    text = (raw or "").strip()
    if not text:
        return {"answer": "I was unable to generate an answer.", "follow_up_questions": []}

    cleaned = text
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            payload = json.loads(match.group(0))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

    # Final fallback: treat model output as plain answer text.
    return {"answer": cleaned, "follow_up_questions": []}


def _normalize_sql_results(sql_results: dict | list | None) -> dict:
    """Normalize varied SQL result payload shapes into a dict contract."""
    if isinstance(sql_results, dict):
        return sql_results

    if isinstance(sql_results, list):
        if not sql_results:
            return {"success": False, "results": [], "columns": []}

        first = sql_results[0]
        if isinstance(first, dict):
            columns = list(first.keys())
            rows = [tuple(item.get(c) for c in columns) for item in sql_results]
            return {"success": True, "results": rows, "columns": columns}

        if isinstance(first, (list, tuple)):
            col_count = len(first)
            columns = [f"col_{i + 1}" for i in range(col_count)]
            rows = [tuple(r) if isinstance(r, (list, tuple)) else (r,) for r in sql_results]
            return {"success": True, "results": rows, "columns": columns}

        return {"success": True, "results": [(v,) for v in sql_results], "columns": ["value"]}

    return {"success": False, "results": [], "columns": []}


def _is_ranking_question(question: str) -> bool:
    q = (question or "").lower()
    ranking_terms = (
        "best", "worst", "highest", "lowest", "most", "least",
        "top", "bottom", "winner", "champion", "maximum", "minimum",
    )
    return any(t in q for t in ranking_terms)


def _pick_metric_index(columns: list[str], rows: list[tuple], question: str) -> int | None:
    numeric_idxs: list[int] = []
    for idx, _col in enumerate(columns):
        vals = [r[idx] for r in rows if len(r) > idx and r[idx] is not None]
        if vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            numeric_idxs.append(idx)

    if not numeric_idxs:
        return None

    q = (question or "").lower()
    best_idx = numeric_idxs[0]
    best_score = -10_000
    for idx in numeric_idxs:
        col = columns[idx].lower()
        score = 0
        if any(k in col for k in ("win", "wins", "count", "total", "score", "rate", "avg", "sum")):
            score += 30
        if any(tok in q for tok in col.replace("_", " ").split()):
            score += 20
        if col == "id" or col.endswith("_id"):
            score -= 100
        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx


def _fmt_value(value: float) -> str:
    """Format a number cleanly without domain-specific currency assumptions."""
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _extract_locked_entity(
    sql_results: dict | None,
    question: str,
) -> dict | None:
    """
    Deterministically extract the ranking winner from SQL rows.

    Returns a dict:
      {
        "label": str,          # the winning entity name
        "metric_name": str,    # column name of the metric
        "value": float,        # winner's metric value
        "adjective": str,      # "highest" | "lowest"
        "peers": [{"label": str, "value": float}, ...],   # all ranked entities
      }

    Returns None if this is not a ranking question or rows are missing.
    """
    if not sql_results or not sql_results.get("success"):
        return None
    if not _is_ranking_question(question):
        return None

    rows = sql_results.get("results") or []
    columns = sql_results.get("columns") or []
    if not rows or not columns:
        return None

    metric_idx = _pick_metric_index(columns, rows, question)
    if metric_idx is None:
        return None

    # Use first non-numeric, non-id column as label; fallback to column 0.
    label_idx = 0
    for idx in range(len(columns)):
        if idx == metric_idx:
            continue
        col = columns[idx].lower()
        if col == "id" or col.endswith("_id"):
            continue
        vals = [r[idx] for r in rows if len(r) > idx and r[idx] is not None]
        if vals and any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in vals):
            label_idx = idx
            break

    pairs: list[tuple[str, float]] = []
    for r in rows:
        if len(r) <= max(label_idx, metric_idx):
            continue
        label = str(r[label_idx])
        try:
            value = float(r[metric_idx])
        except Exception:
            continue
        pairs.append((label, value))

    if not pairs:
        return None

    q = (question or "").lower()
    choose_min = any(k in q for k in ("worst", "lowest", "least", "bottom", "minimum"))
    ordered = sorted(pairs, key=lambda p: p[1], reverse=not choose_min)
    winner_label, winner_value = ordered[0]
    adjective = "lowest" if choose_min else "highest"

    return {
        "label": winner_label,
        "metric_name": columns[metric_idx].replace("_", " "),
        "value": winner_value,
        "adjective": adjective,
        "peers": [{"label": lb, "value": vl} for lb, vl in ordered],
    }


def _build_deterministic_answer(locked: dict) -> dict:
    """Build a plain-text answer from the locked entity without LLM."""
    winner = locked["label"]
    adjective = locked["adjective"]
    metric = locked["metric_name"]
    value_str = _fmt_value(locked["value"])
    peers = locked["peers"]

    top_peers = peers[:5]
    comparison = ", ".join(
        f"{p['label']} ({_fmt_value(p['value'])})" for p in top_peers
    )

    # Margin over second place
    margin_clause = ""
    if len(peers) >= 2:
        second_val = peers[1]["value"]
        if second_val and second_val != 0:
            margin_pct = abs((locked["value"] - second_val) / second_val * 100)
            margin_clause = (
                f" — {round(margin_pct)}% ahead of {peers[1]['label']} "
                f"({_fmt_value(second_val)})"
            )

    answer = (
        f"{winner} leads with the {adjective} {metric} at {value_str}{margin_clause}. "
        f"Full ranking: {comparison}."
    )

    return {
        "answer": answer,
        "follow_up_questions": [
            f"What other stats does {winner} have compared to the rest?",
            f"Show this {metric} comparison as a bar chart.",
        ],
    }


# ── System prompts ─────────────────────────────────────────────────────────────

_ANALYST_SYSTEM = """You are a sharp, senior data analyst presenting findings to a business executive.

RULES:
1. Lead with the KEY INSIGHT, not just the number. "South region is dragging down overall growth" beats "South has a lower value."
2. Format numbers cleanly: commas for thousands (1,234), two decimal places for non-integers.
3. Always compare to something — another entity, an average, or a baseline. Raw numbers without context are meaningless.
4. Provide REASONING: explain WHY the pattern exists or what it implies, not just WHAT the number is.
5. If data shows something surprising or concerning, flag it explicitly: "This is unusual because..." or "This warrants attention."
6. End with a specific, actionable observation — not generic advice.
7. NEVER say "Based on the data" or "According to the results" — state the insight directly.
8. Give 3-5 sentences for most queries. Complex comparisons or breakdowns deserve 5-7 sentences with clear structure.
9. Use ONLY column names and values that appear in the SQL results. Do NOT invent domain terminology.
10. For multi-entity results, identify the leader/outlier AND explain the spread or distribution pattern.

For follow-up suggestions, make them SPECIFIC to what the data showed:
- If one entity dominates → suggest investigating WHY it leads and what others could learn from it
- If there's a trend → suggest comparing with another period, dimension, or related metric
- If there's an anomaly → suggest drilling into the root cause
- If there's a spread → suggest examining the bottom performers or the average
- NEVER suggest generic questions like "Would you like more details?"
"""

_FACTUAL_SYSTEM = """You are a precise data analyst answering a direct factual question.

RULES:
1. Answer the question directly with the exact number or list from the data.
2. State the fact FIRST. Then add 1-2 sentences of context that make the number meaningful.
3. Format numbers cleanly: commas for thousands (1,234), two decimal places for non-integers.
4. For counts or rankings, list the top items with their values.
5. NEVER say "Based on the data" or "According to the results".
6. Use ONLY column names and values that appear in the SQL results.
7. If there are multiple rows, summarize the pattern (e.g., "Electronics dominates at 1,240, nearly double the next category").

EXAMPLES:
  Q: "How many regions are there?"
  A: "There are 4 regions: North, South, East, and West. North and East account for the majority of activity."

  Q: "Total count per category?"
  A: "Electronics leads with 1,240 items (38% of total), followed by Clothing (980), Food (870), and Home (760). The top two categories make up over 68% of all items."
"""


def generate_answer(
    question: str,
    pattern: str,
    sql_results: dict | None,
    rag_documents: list | None = None,
    sql_used: str | None = None,
    conversation_state: str | None = None,
    query_type: str = "INSIGHT",
    dataset_context: str | None = None,
) -> dict:
    """
    Generate a grounded answer for the given question and SQL results.

    For ranking questions:
      1. Deterministically extract the winner from SQL rows (entity lock).
      2. Inject the locked entity + full peer list into the LLM prompt.
      3. After LLM call, verify the locked entity's name appears in the answer.
      4. If not, fall back to the deterministic template.
    """
    normalized_sql_results = _normalize_sql_results(sql_results)
    rows = normalized_sql_results.get("results") or []
    columns = normalized_sql_results.get("columns") or []

    # ── Entity locking (ranking questions) ────────────────────────────────────
    locked = _extract_locked_entity(normalized_sql_results, question)

    templates = _get_templates()
    pattern_cfg = templates.get(pattern, templates.get("GENERAL", {}))
    pattern_answer_prompt = pattern_cfg.get("answer_prompt", "")

    # ── Build context sections ─────────────────────────────────────────────────
    data_section = ""
    if normalized_sql_results and normalized_sql_results.get("success"):
        table_str = _format_results(rows, columns)
        data_section = f"\n## SQL Query Results\n```\n{table_str}\n```\n"

    rag_section = ""
    if rag_documents:
        doc_texts = []
        for d in rag_documents[:5]:
            text = d.get("text", "")
            region = d.get("region", "")
            date = d.get("date", "")
            doc_texts.append(f"- [{region} | {date}] {text}")
        rag_section = "\n## Supporting documents\n" + "\n".join(doc_texts) + "\n"

    state_section = ""
    if conversation_state:
        state_section = f"\n## Conversation context\n{conversation_state}\n"

    # ── Locked entity injection ────────────────────────────────────────────────
    lock_section = ""
    if locked:
        peers = locked["peers"]
        peer_list = "\n".join(
            f"  {i+1}. {p['label']}: {_fmt_value(p['value'])}"
            for i, p in enumerate(peers)
        )
        # Pre-compute margin for the prompt
        margin_hint = ""
        if len(peers) >= 2:
            second_val = peers[1]["value"]
            if second_val and second_val != 0:
                margin_pct = abs((locked["value"] - second_val) / second_val * 100)
                margin_hint = (
                    f"\nMargin over 2nd place ({peers[1]['label']}): "
                    f"{round(margin_pct)}% ({_fmt_value(locked['value'])} vs {_fmt_value(second_val)})"
                )

        lock_section = f"""
## ENTITY LOCK (deterministic — do NOT contradict this)
Winner: **{locked['label']}** — {locked['adjective']} {locked['metric_name']} = {_fmt_value(locked['value'])}{margin_hint}

Full ranking from the data:
{peer_list}

MANDATORY RULES:
1. You MUST name {locked['label']!r} as the winner in your answer.
2. Mention the margin over second place — it tells the user HOW dominant the winner is.
3. If the data has other columns beyond {locked['metric_name']!r}, mention them to explain WHY this entity leads (e.g. other metrics, ratios, patterns visible in the rows).
4. Do NOT invent rankings or values not in the data above.
"""

    # ── Response style ─────────────────────────────────────────────────────────
    q_lower = (question or "").lower()
    wants_expanded = bool(locked) or any(
        k in q_lower for k in (
            "compare", "across", "all", "detailed", "detail", "explain",
            "why", "how", "breakdown", "analysis", "trend",
        )
    )
    if locked:
        response_style = (
            "Give a 2-4 sentence answer: (1) name the winner and their metric value, "
            "(2) state the margin over second place, "
            "(3) if other columns are present, note what else the data shows about why this entity leads."
        )
    elif wants_expanded or pattern in ("COMPARISON", "CHANGE_ANALYSIS", "BREAKDOWN"):
        response_style = "Give a richer answer (4-6 sentences) with comparison details when helpful."
    else:
        response_style = "Keep it concise (1-3 sentences)."

    is_factual = query_type in ("COUNT", "COUNT_DISTINCT", "AGGREGATION", "RANKING", "LIST")
    base_system = _FACTUAL_SYSTEM if is_factual else _ANALYST_SYSTEM

    # ── Domain guard (upload mode) ─────────────────────────────────────────────
    upload_domain_rules = ""
    if dataset_context:
        upload_domain_rules = f"""
## DATASET CONTEXT
{dataset_context}

## CRITICAL DOMAIN RULES
You are analysing the ACTUAL dataset described above.
Use ONLY the column names and values that appear in the SQL results.
Do NOT assume any domain — no e-commerce, no finance, no geography — unless those words appear in the data itself.
"""

    system_prompt = f"""{base_system}{upload_domain_rules}{lock_section}
## RESPONSE STYLE
{response_style}

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

    try:
        raw = call_llm(
            model_key="answer_writer",
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.3,
            json_mode=False,
            max_tokens=8192,
        )
        result = _parse_answer_payload(raw)
    except Exception:
        result = {"answer": "I was unable to generate an answer.", "follow_up_questions": []}

    # ── Grounding check ────────────────────────────────────────────────────────
    if locked:
        answer_text = result.get("answer", "")
        if locked["label"].lower() not in answer_text.lower():
            # LLM hallucinated a different entity — use deterministic fallback
            print(
                f"[answer_generator] grounding failure: locked={locked['label']!r} "
                f"not found in answer — using deterministic template"
            )
            result = _build_deterministic_answer(locked)

    result.setdefault("answer", "I was unable to generate an answer.")
    result.setdefault("follow_up_questions", [])
    result.setdefault("chart_suggestion", None)
    return result
