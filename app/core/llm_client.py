"""
Multi-model LLM Client — the single place where all AI calls happen.

How it works:
  Every agent in the pipeline (Router, SQL Generator, Answer Writer, etc.)
  calls `call_llm(model_key=...)` with a role name instead of a model ID.
  This file maps each role to the right model and handles the actual HTTP
  request to OpenRouter (or falls back to Groq if OpenRouter fails).

Provider priority:
  1. OpenRouter  — if OPENROUTER_API_KEYS or OPENROUTER_API_KEY is set
  2. Groq        — if GROQ_API_KEY is set and no OpenRouter key is present

Per-agent model assignment (matches MASTER_IMPLEMENTATION.md):
  schema_analyst  → qwen/qwen3-coder:free      (schema + YAML generation)
  router          → meta-llama/llama-3.3-70b   (fast intent classification)
  sql_generator   → qwen/qwen3-coder:free      (best open-source SQL accuracy)
  answer_writer   → openai/gpt-oss-120b:free   (long-form business insight)
  chart_agent     → meta-llama/llama-3.3-70b   (fast chart type selection)
  result_verifier → qwen/qwen3-coder:free      (sanity-check on answers)

Key design decisions:
  - Key rotation: multiple API keys are cycled round-robin to stay within
    per-key rate limits on free-tier models.
  - 429 retry with back-off: if a model is rate-limited we wait and retry
    up to 3 times before falling back to an alternative model.
  - sync + async interfaces: backend endpoints use the async path; any
    blocking (background thread) code uses the sync wrapper.
  - <think> stripping: Qwen models emit reasoning wrapped in <think> tags;
    those are stripped so agents only see the final answer.
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

# Support both a single key (OPENROUTER_API_KEY) and a comma-separated list
# (OPENROUTER_API_KEYS) for round-robin rotation across free-tier limits.
_OR_KEYS_RAW = os.getenv("OPENROUTER_API_KEYS", os.getenv("OPENROUTER_API_KEY", ""))
_OPENROUTER_KEYS = [k.strip() for k in _OR_KEYS_RAW.split(",") if k.strip()]
_GROQ_KEY = os.getenv("GROQ_API_KEY", "")

USE_OPENROUTER = bool(_OPENROUTER_KEYS)
HAS_GROQ = bool(_GROQ_KEY)
USE_GROQ = HAS_GROQ and not USE_OPENROUTER  # Groq is primary only when no OR keys

if USE_OPENROUTER:
    print(f"[llm_client] Provider: OpenRouter ({len(_OPENROUTER_KEYS)} key(s))")
    if HAS_GROQ:
        print("[llm_client] Groq fallback is enabled")
elif USE_GROQ:
    print("[llm_client] Provider: Groq (fallback)")
else:
    print("[llm_client] WARNING: No LLM API keys found!")

# ── OpenRouter model registry ─────────────────────────────────────────────────

# Maps agent role names → OpenRouter model IDs.
# Each model is chosen for its strengths: Qwen for code/SQL, Llama for speed,
# GPT-OSS for long-form answers.  All use free-tier variants.
_OR_MODELS: dict[str, str] = {
    "schema_analyst": os.getenv("MODEL_SCHEMA_ANALYST", "qwen/qwen3-coder:free"),
    "router":         os.getenv("MODEL_ROUTER",         "meta-llama/llama-3.1-8b-instruct:free"),
    "sql_generator":  os.getenv("MODEL_SQL_GENERATOR",  "qwen/qwen3-coder:free"),
    "answer_writer":  os.getenv("MODEL_ANSWER_WRITER",  "meta-llama/llama-3.3-70b-instruct:free"),
    "chart_agent":    os.getenv("MODEL_CHART_AGENT",    "meta-llama/llama-3.1-8b-instruct:free"),
    "result_verifier":os.getenv("MODEL_RESULT_VERIFIER","qwen/qwen3-coder:free"),
    # Backward-compat aliases used by older agent code
    "fast":           os.getenv("MODEL_ROUTER",         "meta-llama/llama-3.1-8b-instruct:free"),
    "smart_sql":      os.getenv("MODEL_SQL_GENERATOR",  "qwen/qwen3-coder:free"),
    "smart_answer":   os.getenv("MODEL_ANSWER_WRITER",  "meta-llama/llama-3.3-70b-instruct:free"),
    "smart":          os.getenv("MODEL_ANSWER_WRITER",  "meta-llama/llama-3.3-70b-instruct:free"),
}
# Used when the primary model is down or rate-limited and no specific fallback applies.
_OR_FALLBACK = os.getenv("MODEL_FALLBACK", "meta-llama/llama-3.3-70b-instruct:free")

# ── Groq model registry ───────────────────────────────────────────────────────

# Maps role names → Groq model IDs for the fallback provider.
_GROQ_MODELS: dict[str, str] = {
    "fast":           "llama-3.1-8b-instant",
    "smart_sql":      "qwen/qwen3-32b",
    "smart_answer":   "llama-3.3-70b-versatile",
    "smart":          "llama-3.3-70b-versatile",
    "schema_analyst": "qwen/qwen3-32b",
    "router":         "llama-3.1-8b-instant",
    "sql_generator":  "qwen/qwen3-32b",
    "answer_writer":  "llama-3.3-70b-versatile",
    "chart_agent":    "llama-3.1-8b-instant",
    "result_verifier":"qwen/qwen3-32b",
}

# Round-robin key iterator — moves to the next API key on every call so that
# heavy use is spread across multiple keys, avoiding per-key rate limits.
_key_cycle = cycle(_OPENROUTER_KEYS) if _OPENROUTER_KEYS else None


def _strip_think(text: str) -> str:
    """
    Remove <think>...</think> chain-of-thought blocks from model output.

    Qwen and some DeepSeek models emit their internal reasoning wrapped in
    these tags before the actual answer.  We strip them so downstream agents
    only receive the final, clean response text.
    """
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _clean_json_text(text: str) -> str:
    """
    Strip markdown code fences and think blocks from potential JSON output.

    Models sometimes wrap their JSON in triple-backtick fences (```json...```)
    even when instructed not to.  This helper normalizes the text so that
    json.loads() can parse it reliably.
    """
    cleaned = _strip_think(text).strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _parse_json(text: str) -> Any:
    """
    Parse JSON from LLM output with a fallback extraction strategy.

    First tries a straight json.loads on the cleaned text.  If that fails,
    scans the string for the first { ... } or [ ... ] block and tries again.
    This handles cases where the model includes a short preamble before
    the JSON object despite being told not to.
    """
    cleaned = _clean_json_text(text)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    # Scan for an embedded JSON object or array
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = cleaned.find(start_char)
        end   = cleaned.rfind(end_char) + 1
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
    """
    Make an async HTTP call to OpenRouter with key rotation, 429 retry, and model fallback.

    Workflow:
      1. Pick the model for this agent role from the registry.
      2. Rotate to the next API key (round-robin across available keys).
      3. POST to OpenRouter chat completions endpoint.
      4. On 429 (rate-limit): wait and retry up to 3 times with exponential back-off.
      5. On repeated failure: try a list of fallback models before raising.

    Returns the model's text response (think-blocks already stripped).
    """
    import asyncio
    import httpx

    api_key = next(_key_cycle) if _key_cycle else ""
    model   = _OR_MODELS.get(model_key, _OR_FALLBACK)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://talk-to-data.app",
        "X-Title":       "Talk-To-Data",
    }

    payload: dict = {
        "model":       model,
        "messages":    messages,
        "temperature": temperature,
        "max_tokens":  max_tokens,
    }
    if json_mode:
        # Ask the model to return a JSON object; not all models support this
        # but we handle the case where it doesn't in _parse_json().
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=90.0) as client:
        last_error: Exception | None = None

        async def _try_model(model_name: str, allow_response_format: bool) -> str | None:
            """
            Attempt one model up to 3 times, backing off on 429 errors.
            Returns the response text on success, or None on final failure.
            """
            nonlocal last_error
            for attempt in range(3):
                # Rotate key on each attempt so we don't keep hammering the same one.
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
                    data    = resp.json()
                    content = data["choices"][0]["message"]["content"] or ""
                    return _strip_think(content)

                except httpx.HTTPStatusError as e:
                    last_error = e
                    status = e.response.status_code if e.response is not None else None
                    if status == 429 and attempt < 2:
                        # Rate-limited: honour the Retry-After header if present,
                        # otherwise wait 1.5s × attempt number.
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

        # Try the primary model first.
        primary = await _try_model(model, allow_response_format=True)
        if primary is not None:
            return primary

        # Primary failed — try fallback models in order.  We skip response_format
        # for fallbacks because some smaller models reject it.
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


# ── Groq sync call ────────────────────────────────────────────────────────────

def _call_groq_sync(
    model_key: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.0,
    json_mode: bool = False,
) -> str | dict:
    """
    Synchronous Groq call — used as a fallback when OpenRouter is unavailable.

    Groq provides extremely fast inference on open-source models (Llama, Qwen)
    and is used here as a secondary provider.  If json_mode=True and the model
    rejects response_format, we retry with an inline instruction to return JSON.

    Returns a parsed dict if json_mode=True, otherwise a plain string.
    """
    from groq import Groq

    groq_client = Groq(api_key=_GROQ_KEY)
    model = _GROQ_MODELS.get(model_key, "llama-3.3-70b-versatile")

    kwargs: dict = {
        "model":    model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
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
        # Some Groq models don't support response_format — retry without it
        # but add an explicit instruction to the message instead.
        kwargs.pop("response_format", None)
        kwargs["messages"][-1]["content"] += (
            "\n\nReturn ONLY valid JSON. Do not include markdown fences."
        )
        resp = groq_client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content or ""

    text = _strip_think(text)

    if json_mode:
        # Parse the JSON response, handling fences or preamble text.
        cleaned = _clean_json_text(text)
        try:
            return json.loads(cleaned)
        except Exception:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                return json.loads(match.group(0))
            raise

    return text


# ── Public sync interface ─────────────────────────────────────────────────────

def call_llm(
    model_key: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.0,
    json_mode: bool = False,
    max_tokens: int = 4096,
) -> str | dict:
    """
    The main synchronous LLM call used by all agents.

    Agents call this like:
        result = call_llm(model_key="sql_generator", system_prompt=..., user_message=..., json_mode=True)

    Internally this:
      1. Checks which provider is active (OpenRouter or Groq).
      2. For OpenRouter: runs the async HTTP call via asyncio.
         - If we're already inside an async event loop (FastAPI handler), we spin
           up a new thread with its own event loop to avoid "loop already running" errors.
         - If there's no running loop, we run directly.
      3. Falls back to Groq if OpenRouter raises any exception.

    Returns a string for text responses, or a parsed dict when json_mode=True.
    """
    if USE_OPENROUTER:
        import asyncio

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ]
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None

        try:
            if loop is not None and loop.is_running():
                # We're inside an async context (e.g. FastAPI called asyncio.to_thread).
                # Spin up a dedicated thread + event loop to avoid nested-loop errors.
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        _run_async_in_new_loop,
                        model_key, messages, temperature, max_tokens, json_mode,
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
    """
    Run the async OpenRouter call in a brand-new event loop.

    This is used when call_llm is invoked from a thread that doesn't have
    a running event loop (e.g. a background thread spawned by asyncio.to_thread).
    Creating a new loop avoids conflicts with the FastAPI event loop.
    """
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            _call_openrouter(model_key, messages, temperature, max_tokens, json_mode)
        )
    finally:
        loop.close()


# ── Async interface (for new async code) ──────────────────────────────────────

async def call_llm_async(
    model_key: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.0,
    max_tokens: int = 4000,
    json_mode: bool = False,
) -> str | dict:
    """
    Async version of call_llm for use directly in async FastAPI handlers.

    Prefer this over call_llm when you're already inside an async function,
    as it avoids the thread-pool overhead of the sync wrapper.

    Falls back to Groq (run in a thread) if OpenRouter fails.
    Returns a string, or a parsed dict when json_mode=True.
    """
    if USE_OPENROUTER:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
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
        return await asyncio.to_thread(
            _call_groq_sync,
            model_key, system_prompt, user_message, temperature, json_mode,
        )
    else:
        raise RuntimeError(
            "No LLM provider configured. Set OPENROUTER_API_KEYS or GROQ_API_KEY in .env"
        )
