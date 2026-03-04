import sys
import os

def normalize_model_ref(provider: str, model: str) -> str:
    """Normalize provider and model names for comparison."""
    return f"{(provider or '').strip().lower()}/{(model or '').strip().lower()}"


def _read_key(value: str) -> str:
    """Resolve API key value: supports 'file:~/path' references."""
    if not value:
        return value
    if value.startswith("file:"):
        path = os.path.expanduser(value[5:])
        try:
            return open(path).read().strip()
        except Exception:
            return value
    return value


def get_llm(provider: str, model: str, api_key: str = None):
    """Helper to get a litellm-compatible Chat model regardless of provider."""
    from typing import Optional
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatResult, ChatGeneration
    from litellm import completion

    api_key = _read_key(api_key)

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    elif provider == "google-vertex":
        from langchain_google_vertexai import ChatVertexAI
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        # Force a real region — 'global' doesn't work for most Gemini models
        if location in ("global", ""):
            location = "us-central1"
        return ChatVertexAI(model_name=model, location=location)

    else:
        # Fallback: pure litellm wrapper (openrouter, bedrock, etc.)
        class LiteLLMWrapper(BaseChatModel):
            model: str
            api_key: Optional[str] = None
            api_base: Optional[str] = None
            default_max_tokens: Optional[int] = None

            @property
            def _llm_type(self) -> str:
                return "litellm"

            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                msgs = [
                    {"role": "user" if m.type == "human" else m.type, "content": m.content}
                    for m in messages
                ]
                extra = {}
                if self.api_base:
                    extra["api_base"] = self.api_base
                # Apply default_max_tokens unless caller already specified
                if self.default_max_tokens and "max_tokens" not in kwargs:
                    extra["max_tokens"] = self.default_max_tokens
                res = completion(
                    model=self.model,
                    messages=msgs,
                    api_key=self.api_key,
                    **extra,
                    **kwargs,
                )
                return ChatResult(
                    generations=[
                        ChatGeneration(message=AIMessage(content=res.choices[0].message.content))
                    ]
                )

        if provider == "openrouter":
            key = api_key or _read_key(os.environ.get("OPENROUTER_API_KEY", ""))
            # litellm native OpenRouter: prefix model with "openrouter/"
            # e.g. "anthropic/claude-sonnet-4-5" → "openrouter/anthropic/claude-sonnet-4-5"
            if model.startswith("openrouter/"):
                litellm_model = model
            else:
                litellm_model = f"openrouter/{model}"
            # Default max_tokens=2000 to avoid OpenRouter reserving full context window
            return LiteLLMWrapper(model=litellm_model, api_key=key, default_max_tokens=2000)

        elif provider == "amazon-bedrock":
            bearer = _read_key(os.environ.get("AWS_BEARER_TOKEN_BEDROCK", ""))
            region = os.environ.get("AWS_REGION", "us-east-2")
            # Use the Bedrock ARN from ANTHROPIC_DEFAULT_SONNET_MODEL if model looks like a name
            if not model.startswith("arn:") and not model.startswith("anthropic."):
                model = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", model)
            litellm_model = f"bedrock/{model}"
            return LiteLLMWrapper(model=litellm_model, api_key=bearer)

        else:
            # Generic litellm prefix
            litellm_model = model if "/" in model else f"{provider}/{model}"
            return LiteLLMWrapper(model=litellm_model, api_key=api_key)
