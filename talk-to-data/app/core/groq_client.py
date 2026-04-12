import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODELS = {
    "fast": "llama-3.1-8b-instant",           # Router, classification
    "smart": "llama-3.3-70b-versatile",        # Legacy fallback
    "smart_sql": "qwen/qwen3-32b",             # SQL generation — 95%+ accuracy
    "smart_answer": "llama-3.3-70b-versatile", # Answer generation — best natural language
    "chart": "llama-3.1-8b-instant",           # Chart agent — fast structured output
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

    if json_mode:
        return json.loads(text)
    return text
