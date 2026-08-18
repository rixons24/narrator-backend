"""
llm_client.py — unified LLM client. Reads LLM_PROVIDER env var to decide
whether to call Groq (cloud, no GPU needed) or a local Ollama instance.

Set in the deployment environment:
  LLM_PROVIDER=groq        (default — for Railway/cloud deployment)
  GROQ_API_KEY=<your key>
  GROQ_MODEL=openai/gpt-oss-120b   (optional override, this is now the default)

  LLM_PROVIDER=ollama      (for local dev)
  OLLAMA_BASE_URL=http://localhost:11434
  OLLAMA_MODEL=qwen2.5:14b

Callers (scene_parser.py, alias_reconciliation.py) just call generate_json()
— they don't need to know or care which provider is active.
"""
import json
import os
import re

import httpx

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")

REQUEST_TIMEOUT_SECONDS = 120.0

# Groq's error body includes the exact wait time, e.g. "Please try again
# in 10.215s." — parsed out so retries wait exactly as long as needed,
# no more, no less.
_RETRY_AFTER_RE = re.compile(r"try again in (\d+(?:\.\d+)?)s", re.IGNORECASE)


class LLMError(Exception):
    """Raised on any provider failure — connection, HTTP error, or bad JSON."""


class LLMTimeoutError(LLMError):
    pass


class LLMRateLimitError(LLMError):
    """Raised on HTTP 429. Carries the provider's own suggested wait time
    (seconds) when it could be parsed from the error body, else None."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def _parse_retry_after(error_text: str) -> float | None:
    match = _RETRY_AFTER_RE.search(error_text)
    return float(match.group(1)) if match else None


async def generate_json(prompt: str, system: str | None = None) -> dict:
    if LLM_PROVIDER == "groq":
        return await _generate_json_groq(prompt, system)
    return await _generate_json_ollama(prompt, system)


async def _generate_json_groq(prompt: str, system: str | None) -> dict:
    if not GROQ_API_KEY:
        raise LLMError("GROQ_API_KEY is not set in the environment.")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(GROQ_URL, json=payload, headers=headers)
    except httpx.ConnectError as e:
        raise LLMError(f"Couldn't reach Groq API: {e}") from e
    except httpx.TimeoutException as e:
        raise LLMTimeoutError(f"Groq request timed out after {REQUEST_TIMEOUT_SECONDS}s") from e

    if resp.status_code == 429:
        retry_after = _parse_retry_after(resp.text)
        raise LLMRateLimitError(
            f"Groq rate limit reached (429): {resp.text[:500]}", retry_after=retry_after
        )

    if resp.status_code != 200:
        raise LLMError(f"Groq returned HTTP {resp.status_code}: {resp.text[:500]}")

    try:
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise LLMError(f"Unexpected Groq response shape: {resp.text[:500]}") from e


async def _generate_json_ollama(prompt: str, system: str | None) -> dict:
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "format": "json", "stream": False}
    if system:
        payload["system"] = system

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
    except httpx.ConnectError as e:
        raise LLMError(f"Couldn't reach Ollama at {OLLAMA_BASE_URL}. Is `ollama serve` running?") from e
    except httpx.TimeoutException as e:
        raise LLMTimeoutError("Ollama request timed out.") from e

    if resp.status_code != 200:
        raise LLMError(f"Ollama returned HTTP {resp.status_code}: {resp.text[:500]}")

    try:
        raw_output = resp.json()["response"]
        return json.loads(raw_output)
    except (KeyError, json.JSONDecodeError) as e:
        raise LLMError(f"Unexpected Ollama response: {resp.text[:500]}") from e
