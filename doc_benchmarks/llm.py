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
    from litellm import completion

    # Resolve api_key from env if not provided
    if not api_key:
        env_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai":    "OPENAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "bedrock":   "AWS_ACCESS_KEY_ID",
        }
        api_key = os.environ.get(env_map.get(provider, "OPENAI_API_KEY"), "")

    # Build litellm model string
    if "/" in model:
        litellm_model = model           # already prefixed
    elif provider == "openai":
        litellm_model = model           # openai models work as-is
    else:
        litellm_model = f"{provider}/{model}"

    last_exc: Optional[Exception] = None
    delay = retry_delay

    for attempt in range(max_retries + 1):
        try:
            resp = completion(
                model=litellm_model,
                messages=[{"role": "user", "content": prompt}],
                api_key=api_key or None,
            )
            return resp.choices[0].message.content

        except Exception as exc:
            last_exc = exc
            if attempt < max_retries and _is_retryable(exc):
                logger.warning(
                    f"LLM call failed (attempt {attempt+1}/{max_retries+1}), "
                    f"retrying in {delay:.0f}s: {exc}"
                )
                time.sleep(delay)
                delay *= 2          # exponential backoff
            else:
                raise

    raise last_exc  # should never reach here
