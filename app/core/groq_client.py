"""
Shared Groq client wrapper.
All agents import from here for LLM calls.
"""

import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODELS = {
    "fast": "llama-3.1-8b-instant",      # Router, fast tasks
    "smart": "llama-3.3-70b-versatile",   # SQL gen, answer gen
}


def call_llm(
    model_key: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.0,
    json_mode: bool = False,
) -> str | dict:
    """
    Single LLM call via Groq SDK.
    
    Args:
        model_key: "fast" (8B) or "smart" (70B)
        system_prompt: System message for the LLM
        user_message: User message / query
        temperature: Sampling temperature (0.0 = deterministic)
        json_mode: If True, request JSON output and parse it
    
    Returns:
        String response, or parsed dict if json_mode=True
    """
    kwargs = {
        "model": MODELS[model_key],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
        "max_tokens": 2048,
    }
    
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    
    response = client.chat.completions.create(**kwargs)
    text = response.choices[0].message.content
    
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
