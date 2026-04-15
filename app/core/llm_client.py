"""
Multi-model LLM client.

Priority:
  1. OpenRouter (if OPENROUTER_API_KEYS or OPENROUTER_API_KEY is set)
  2. Groq (if GROQ_API_KEY is set and no OpenRouter key)

Per-agent model assignment follows the spec:
  schema_analyst  → qwen/qwen3-coder:free     (schema YAML generation)
    router          → meta-llama/llama-3.3-70b-instruct:free  (fast classification)
  sql_generator   → qwen/qwen3-coder:free     (best SQL accuracy)
    answer_writer   → openai/gpt-oss-120b:free  (long-form insight)
    chart_agent     → meta-llama/llama-3.3-70b-instruct:free  (fast chart selection)
  result_verifier → qwen/qwen3-coder:free     (sanity check)

Groq fallback model mapping:
  schema_analyst  → qwen/qwen3-32b
  router          → llama-3.1-8b-instant
  sql_generator   → qwen/qwen3-32b
  answer_writer   → llama-3.3-70b-versatile
  chart_agent     → llama-3.1-8b-instant
  result_verifier → qwen/qwen3-32b
"""
from __future__ import annotations

import json
import os
import re
from itertools import cycle
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ── Provider detection ────────────────────────────────────────────────────────

_OR_KEYS_RAW = os.getenv("OPENROUTER_API_KEYS", os.getenv("OPENROUTER_API_KEY", ""))
_OPENROUTER_KEYS = [k.strip() for k in _OR_KEYS_RAW.split(",") if k.strip()]
_GROQ_KEY = os.getenv("GROQ_API_KEY", "")

USE_OPENROUTER = bool(_OPENROUTER_KEYS)
HAS_GROQ = bool(_GROQ_KEY)
USE_GROQ = HAS_GROQ and not USE_OPENROUTER  # Groq primary only when no OR keys

if USE_OPENROUTER:
    print(f"[llm_client] Provider: OpenRouter ({len(_OPENROUTER_KEYS)} key(s))")
    if HAS_GROQ:
        print("[llm_client] Groq fallback is enabled")
elif USE_GROQ:
    print("[llm_client] Provider: Groq (fallback)")
else:
    print("[llm_client] WARNING: No LLM API keys found!")

# ── OpenRouter model registry ─────────────────────────────────────────────────

_OR_MODELS: dict[str, str] = {
    "schema_analyst": os.getenv("MODEL_SCHEMA_ANALYST", "qwen/qwen3-coder:free"),
    "router": os.getenv("MODEL_ROUTER", "meta-llama/llama-3.1-8b-instruct:free"),
    "sql_generator": os.getenv("MODEL_SQL_GENERATOR", "qwen/qwen3-coder:free"),
    "answer_writer": os.getenv("MODEL_ANSWER_WRITER", "meta-llama/llama-3.3-70b-instruct:free"),
    "chart_agent": os.getenv("MODEL_CHART_AGENT", "meta-llama/llama-3.1-8b-instruct:free"),
    "result_verifier": os.getenv("MODEL_RESULT_VERIFIER", "qwen/qwen3-coder:free"),
    # Backward compat aliases used by existing agents
    "fast": os.getenv("MODEL_ROUTER", "meta-llama/llama-3.1-8b-instruct:free"),
    "smart_sql": os.getenv("MODEL_SQL_GENERATOR", "qwen/qwen3-coder:free"),
    "smart_answer": os.getenv("MODEL_ANSWER_WRITER", "meta-llama/llama-3.3-70b-instruct:free"),
    "smart": os.getenv("MODEL_ANSWER_WRITER", "meta-llama/llama-3.3-70b-instruct:free"),
}
_OR_FALLBACK = os.getenv("MODEL_FALLBACK", "meta-llama/llama-3.3-70b-instruct:free")

# ── Groq model registry (backward compat) ────────────────────────────────────

_GROQ_MODELS: dict[str, str] = {
    "fast": "llama-3.1-8b-instant",
    "smart_sql": "qwen/qwen3-32b",
    "smart_answer": "llama-3.3-70b-versatile",
    "smart": "llama-3.3-70b-versatile",
    "schema_analyst": "qwen/qwen3-32b",
    "router": "llama-3.1-8b-instant",
    "sql_generator": "qwen/qwen3-32b",
    "answer_writer": "llama-3.3-70b-versatile",
    "chart_agent": "llama-3.1-8b-instant",
    "result_verifier": "qwen/qwen3-32b",
}

# Key rotation cycle (only for OpenRouter)
_key_cycle = cycle(_OPENROUTER_KEYS) if _OPENROUTER_KEYS else None


def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks produced by Qwen/DeepSeek models."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _clean_json_text(text: str) -> str:
    """Strip markdown fences and think blocks from potential JSON output."""
    cleaned = _strip_think(text).strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _parse_json(text: str) -> Any:
    """Parse JSON from LLM output, with fallback extraction."""
    cleaned = _clean_json_text(text)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    # Try to find a JSON object or array in the text
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = cleaned.find(start_char)
        end = cleaned.rfind(end_char) + 1
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end])
            except Exception:
                pass
    raise ValueError(f"Could not parse JSON from LLM response: {cleaned[:200]!r}")


# ── OpenRouter async call ─────────────────────────────────────────────────────

async def _call_openrouter(
    model_key: str,
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int = 4000,
    json_mode: bool = False,
) -> str:
    """Async OpenRouter call with key rotation, 429 retry, and model fallback."""
    import asyncio
    import httpx

    api_key = next(_key_cycle) if _key_cycle else ""
    model = _OR_MODELS.get(model_key, _OR_FALLBACK)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://talk-to-data.app",
        "X-Title": "Talk-To-Data",
    }

    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        # Some OR models support response_format; we'll request it but handle failure
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=90.0) as client:
        last_error: Exception | None = None

        async def _try_model(model_name: str, allow_response_format: bool) -> str | None:
            nonlocal last_error
            for attempt in range(3):
                if _key_cycle:
                    headers["Authorization"] = f"Bearer {next(_key_cycle)}"

                payload["model"] = model_name
                if json_mode and allow_response_format:
                    payload["response_format"] = {"type": "json_object"}
                else:
                    payload.pop("response_format", None)

                try:
                    resp = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"] or ""
                    return _strip_think(content)
                except httpx.HTTPStatusError as e:
                    last_error = e
                    status = e.response.status_code if e.response is not None else None
                    if status == 429 and attempt < 2:
                        retry_after = None
                        if e.response is not None:
                            retry_after = e.response.headers.get("retry-after")
                        try:
                            wait_s = float(retry_after) if retry_after else (1.5 * (attempt + 1))
                        except Exception:
                            wait_s = 1.5 * (attempt + 1)
                        await asyncio.sleep(min(max(wait_s, 0.5), 8.0))
                        continue
                    break
                except Exception as e:
                    last_error = e
                    break

            return None

        primary = await _try_model(model, allow_response_format=True)
        if primary is not None:
            return primary

        fallback_candidates = [
            _OR_FALLBACK,
            "qwen/qwen3-coder:free",
            "meta-llama/llama-3.1-8b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
            "meta-llama/llama-3.3-70b-instruct:free",
        ]
        tried = {model}
        for candidate in fallback_candidates:
            if not candidate or candidate in tried:
                continue
            tried.add(candidate)

            text = await _try_model(candidate, allow_response_format=False)
            if text is not None:
                return text

        raise RuntimeError(
            f"OpenRouter call failed for model={model}: {last_error}"
        )


# ── Groq sync call (existing interface) ──────────────────────────────────────

def _call_groq_sync(
    model_key: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.0,
    json_mode: bool = False,
) -> str | dict:
    """Sync Groq call — preserves the existing groq_client.call_llm interface."""
    from groq import Groq

    groq_client = Groq(api_key=_GROQ_KEY)
    model = _GROQ_MODELS.get(model_key, "llama-3.3-70b-versatile")

    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        resp = groq_client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content or ""
    except Exception:
        if not json_mode:
            raise
        # Retry without response_format
        kwargs.pop("response_format", None)
        kwargs["messages"][-1]["content"] += (
            "\n\nReturn ONLY valid JSON. Do not include markdown fences."
        )
        resp = groq_client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content or ""

    text = _strip_think(text)

    if json_mode:
        cleaned = _clean_json_text(text)
        try:
            return json.loads(cleaned)
        except Exception:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                return json.loads(match.group(0))
            raise

    return text


# ── Public sync interface (backward compat with groq_client.call_llm) ─────────

def call_llm(
    model_key: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.0,
    json_mode: bool = False,
    max_tokens: int = 4096,
) -> str | dict:
    """
    Sync LLM call.  Dispatches to OpenRouter (via asyncio) or Groq.
    Returns string (or parsed dict if json_mode=True).
    """
    if USE_OPENROUTER:
        import asyncio

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None

        try:
            if loop is not None and loop.is_running():
                # We're inside an async context — use a thread executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        _run_async_in_new_loop,
                        model_key, messages, temperature,
                        max_tokens,
                        json_mode,
                    )
                    text = future.result(timeout=120)
            elif loop is not None:
                text = loop.run_until_complete(
                    _call_openrouter(model_key, messages, temperature, max_tokens, json_mode)
                )
            else:
                text = _run_async_in_new_loop(
                    model_key, messages, temperature, max_tokens, json_mode
                )

            if json_mode:
                return _parse_json(text)
            return text
        except Exception as openrouter_err:
            if HAS_GROQ:
                print(f"[llm_client] OpenRouter failed, falling back to Groq: {openrouter_err}")
                return _call_groq_sync(
                    model_key, system_prompt, user_message, temperature, json_mode
                )
            raise

    elif USE_GROQ:
        return _call_groq_sync(
            model_key, system_prompt, user_message, temperature, json_mode
        )
    else:
        raise RuntimeError(
            "No LLM provider configured. Set OPENROUTER_API_KEYS or GROQ_API_KEY in .env"
        )


def _run_async_in_new_loop(
    model_key: str,
    messages: list,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
) -> str:
    """Run the async OpenRouter call in a fresh event loop (for sync contexts)."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            _call_openrouter(model_key, messages, temperature, max_tokens, json_mode)
        )
    finally:
        loop.close()


# ── Async interface (for new code) ────────────────────────────────────────────

async def call_llm_async(
    model_key: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.0,
    max_tokens: int = 4000,
    json_mode: bool = False,
) -> str | dict:
    """
    Async LLM call.  Prefers OpenRouter; falls back to Groq (sync-in-thread).
    Returns string or parsed dict (if json_mode=True).
    """
    if USE_OPENROUTER:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        try:
            text = await _call_openrouter(model_key, messages, temperature, max_tokens, json_mode)
            if json_mode:
                return _parse_json(text)
            return text
        except Exception as openrouter_err:
            if HAS_GROQ:
                import asyncio
                print(f"[llm_client] OpenRouter async failed, falling back to Groq: {openrouter_err}")
                return await asyncio.to_thread(
                    _call_groq_sync,
                    model_key, system_prompt, user_message, temperature, json_mode,
                )
            raise

    elif USE_GROQ:
        import asyncio

        result = await asyncio.to_thread(
            _call_groq_sync,
            model_key, system_prompt, user_message, temperature, json_mode,
        )
        return result

    else:
        raise RuntimeError(
            "No LLM provider configured. Set OPENROUTER_API_KEYS or GROQ_API_KEY in .env"
        )
