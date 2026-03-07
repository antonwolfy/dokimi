"""Thin LLM wrapper using litellm — one interface for all providers.

Usage:
    from doc_benchmarks.llm import llm_call
    text = llm_call("Your prompt", model="gpt-4o-mini", provider="openai")
"""
import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Backward-compatibility shims for existing tests/modules.
LANGCHAIN_AVAILABLE = True

# Errors that are worth retrying (rate limits, timeouts, transient network)
_RETRYABLE_SUBSTRINGS = (
    "rate_limit", "ratelimit", "rate limit",
    "timeout", "timed out",
    "connection", "server error", "503", "502", "529",
    "overloaded",
)


class _Resp:
    def __init__(self, content: str):
        self.content = content


class ChatOpenAI:
    """LangChain-compatible shim backed by llm_call."""

    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        self.model = model
        self.api_key = api_key

    def invoke(self, prompt: str):
        """Invoke the model with a prompt."""
        return _Resp(llm_call(prompt, self.model, provider="openai", api_key=self.api_key))


class ChatAnthropic:
    """LangChain-compatible shim backed by llm_call."""

    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        self.model = model
        self.api_key = api_key

    def invoke(self, prompt: str):
        """Invoke the model with a prompt."""
        return _Resp(llm_call(prompt, self.model, provider="anthropic", api_key=self.api_key))


def _is_retryable(exc: Exception) -> bool:
    """Return True if the exception is worth retrying."""
    msg = str(exc).lower()
    return any(s in msg for s in _RETRYABLE_SUBSTRINGS)


def _resolve_api_key(provider: str, api_key: Optional[str]) -> str:
    """Resolve API key from env vars or file: references."""
    if not api_key:
        env_map = {
            "anthropic":  "ANTHROPIC_API_KEY",
            "openai":     "OPENAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "bedrock":    "AWS_ACCESS_KEY_ID",
            "google":     "GEMINI_API_KEY",
            "gemini":     "GEMINI_API_KEY",
        }
        api_key = os.environ.get(env_map.get(provider, "OPENAI_API_KEY"), "")
    if api_key and api_key.startswith("file:"):
        key_path = os.path.expanduser(api_key[len("file:"):])
        try:
            with open(key_path) as _f:
                api_key = _f.read().strip()
        except OSError as exc:
            raise ValueError(f"Cannot read API key from file '{key_path}': {exc}") from exc
    return api_key


def _build_litellm_model(model: str, provider: str) -> str:
    """Build litellm model string from model + provider."""
    if provider == "openrouter":
        return model if model.startswith("openrouter/") else f"openrouter/{model}"
    elif provider == "openai-codex":
        return f"openai/{model}"
    elif "/" in model:
        return model
    elif provider == "openai":
        return model
    elif provider in ("google", "gemini", "google-vertex"):
        return f"vertex_ai/{model}"
    elif provider == "amazon-bedrock":
        return f"bedrock/{model}"
    else:
        return f"{provider}/{model}"


def llm_call(
    prompt: str,
    model: str,
    provider: str = "openai",
    api_key: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> str:
    """Call any LLM via litellm with automatic retry on transient errors.

    Args:
        prompt: User prompt string.
        model: Model name (e.g. "gpt-4o-mini", "claude-3-5-sonnet-20241022").
        provider: Provider name — "openai", "anthropic", "openrouter", "bedrock".
        api_key: Optional API key (falls back to env var).
        max_retries: Max retry attempts on transient errors (default 3).
        retry_delay: Initial delay in seconds; doubles each attempt (exponential backoff).

    Returns:
        Model response as a plain string.
    """
    text, _ = llm_call_with_usage(
        prompt=prompt, model=model, provider=provider,
        api_key=api_key, max_retries=max_retries, retry_delay=retry_delay,
    )
    return text


def llm_call_with_usage(
    prompt: str,
    model: str,
    provider: str = "openai",
    api_key: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> "tuple[str, dict]":
    """Like llm_call, but returns (text, usage_dict).

    usage_dict keys: prompt_tokens, completion_tokens, total_tokens.
    All values default to 0 if the provider doesn't return usage.

    Returns:
        (response_text: str, usage: dict)
    """
    from litellm import completion

    api_key = _resolve_api_key(provider, api_key)
    litellm_model = _build_litellm_model(model, provider)

    last_exc: Optional[Exception] = None
    delay = retry_delay

    for attempt in range(max_retries + 1):
        try:
            resp = completion(
                model=litellm_model,
                messages=[{"role": "user", "content": prompt}],
                api_key=api_key or None,
            )
            text = resp.choices[0].message.content

            # Extract usage — litellm always provides .usage when available
            usage: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            if hasattr(resp, "usage") and resp.usage:
                u = resp.usage
                usage["prompt_tokens"] = getattr(u, "prompt_tokens", 0) or 0
                usage["completion_tokens"] = getattr(u, "completion_tokens", 0) or 0
                usage["total_tokens"] = getattr(u, "total_tokens", 0) or 0

            return text, usage

        except Exception as exc:
            last_exc = exc
            if attempt < max_retries and _is_retryable(exc):
                logger.warning(
                    f"LLM call failed (attempt {attempt+1}/{max_retries+1}), "
                    f"retrying in {delay:.0f}s: {exc}"
                )
                time.sleep(delay)
                delay *= 2
            else:
                raise

    raise last_exc  # should never reach here


# ── Robust JSON extraction ─────────────────────────────────────────────────────

import re as _re

def extract_json_object(text: str) -> dict:
    """Extract a JSON object from LLM output, handling markdown fences and leading text."""
    text = (text or "").strip()
    if not text:
        raise ValueError("LLM returned empty response")
    # Direct parse
    try:
        return __import__("json").loads(text)
    except Exception:
        pass
    # Markdown fence
    fence = _re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        try:
            return __import__("json").loads(fence.group(1).strip())
        except Exception:
            pass
    # First { ... } block
    m = _re.search(r"\{[\s\S]*\}", text)
    if m:
        return __import__("json").loads(m.group(0))
    raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")


def extract_json_array(text: str) -> list:
    """Extract a JSON array from LLM output, handling markdown fences and leading text."""
    text = (text or "").strip()
    if not text:
        raise ValueError("LLM returned empty response")
    # Direct parse
    try:
        result = __import__("json").loads(text)
        if isinstance(result, list):
            return result
    except Exception:
        pass
    # Markdown fence
    fence = _re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        try:
            result = __import__("json").loads(fence.group(1).strip())
            if isinstance(result, list):
                return result
        except Exception:
            pass
    # First [ ... ] block
    m = _re.search(r"\[[\s\S]*\]", text)
    if m:
        result = __import__("json").loads(m.group(0))
        if isinstance(result, list):
            return result
    raise ValueError(f"No JSON array found in LLM response: {text[:200]!r}")
