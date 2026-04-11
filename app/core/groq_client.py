from __future__ import annotations
import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Model strategy: best model for each task
# - fast:         Llama 3.1 8B — Router, chart agent, classification (30 RPM)
# - smart_sql:    Qwen3-32B — SQL generation, 95%+ accuracy (60 RPM)
# - smart_answer: Llama 3.3 70B — Natural language answers (30 RPM)
# - smart:        Alias for smart_answer (backward compat)
MODELS = {
    "fast": "llama-3.1-8b-instant",
    "smart_sql": "qwen/qwen3-32b",
    "smart_answer": "llama-3.3-70b-versatile",
    "smart": "llama-3.3-70b-versatile",  # backward compat
}


def call_llm(
    model_key: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.0,
    json_mode: bool = False,
) -> str | dict:
    """Single LLM call. Returns string (or parsed dict if json_mode)."""
    kwargs = {
        "model": MODELS[model_key],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    text = response.choices[0].message.content

    # Strip Qwen3 thinking tags if present
    if "<think>" in text:
        import re
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    if json_mode:
        # Clean potential markdown wrapping
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return json.loads(cleaned.strip())
    return text
