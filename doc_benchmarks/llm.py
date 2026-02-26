"""Thin LLM wrapper using litellm — one interface for all providers.

Usage:
    from doc_benchmarks.llm import llm_call
    text = llm_call("Your prompt", model="gpt-4o-mini", provider="openai")
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Backward-compatibility shims for existing tests/modules.
LANGCHAIN_AVAILABLE = True


class _Resp:
    def __init__(self, content: str):
        self.content = content


class ChatOpenAI:
    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        self.model = model
        self.api_key = api_key

    def invoke(self, prompt: str):
        return _Resp(llm_call(prompt, self.model, provider="openai", api_key=self.api_key))


class ChatAnthropic:
    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        self.model = model
        self.api_key = api_key

    def invoke(self, prompt: str):
        return _Resp(llm_call(prompt, self.model, provider="anthropic", api_key=self.api_key))


def llm_call(
    prompt: str,
    model: str,
    provider: str = "openai",
    api_key: Optional[str] = None,
) -> str:
    """Call any LLM via litellm with a plain string API key (no async issues)."""
    from litellm import completion

    # Always resolve key as plain string from env — never async
    if not api_key:
        if provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        elif provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")
        elif provider == "openrouter":
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
        elif provider == "bedrock":
            api_key = os.environ.get("AWS_ACCESS_KEY_ID", "") # Simplification
        else:
            api_key = os.environ.get("OPENAI_API_KEY", "")

    # Build litellm model string
    if "/" in model:
        litellm_model = model          # already prefixed, e.g. "anthropic/claude-3"
    elif provider == "openai":
        litellm_model = model          # openai models work as-is
    else:
        litellm_model = f"{provider}/{model}"

    resp = completion(
        model=litellm_model,
        messages=[{"role": "user", "content": prompt}],
        api_key=api_key or None,
    )
    return resp.choices[0].message.content
