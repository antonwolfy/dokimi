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
    """Return a minimal chat wrapper with .invoke(prompt) -> object(content=...)."""
    from litellm import completion

    class _Resp:
        def __init__(self, content: str):
            self.content = content

    class _LLM:
        def __init__(self, litellm_model: str, key: str = None, default_max_tokens: int = None):
            self.litellm_model = litellm_model
            self.key = key
            self.default_max_tokens = default_max_tokens

        def invoke(self, prompt: str):
            kwargs = {}
            if self.default_max_tokens:
                kwargs["max_tokens"] = self.default_max_tokens
            res = completion(
                model=self.litellm_model,
                messages=[{"role": "user", "content": prompt}],
                api_key=self.key,
                **kwargs,
            )
            return _Resp(res.choices[0].message.content)

    api_key = _read_key(api_key)

    if provider == "openrouter":
        key = api_key or _read_key(os.environ.get("OPENROUTER_API_KEY", ""))
        litellm_model = model if model.startswith("openrouter/") else f"openrouter/{model}"
        return _LLM(litellm_model=litellm_model, key=key, default_max_tokens=2000)

    if provider in ("google", "gemini", "google-vertex"):
        # Route Gemini via Vertex AI adapter
        litellm_model = model if model.startswith("vertex_ai/") else f"vertex_ai/{model}"
        key = api_key or _read_key(os.environ.get("GEMINI_API_KEY", ""))
        return _LLM(litellm_model=litellm_model, key=key)

    if provider == "amazon-bedrock":
        bearer = _read_key(os.environ.get("AWS_BEARER_TOKEN_BEDROCK", ""))
        if not model.startswith("arn:") and not model.startswith("anthropic."):
            model = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", model)
        return _LLM(litellm_model=f"bedrock/{model}", key=bearer)

    if provider == "openai":
        key = api_key or _read_key(os.environ.get("OPENAI_API_KEY", ""))
        litellm_model = model
        return _LLM(litellm_model=litellm_model, key=key)

    if provider == "anthropic":
        key = api_key or _read_key(os.environ.get("ANTHROPIC_API_KEY", ""))
        litellm_model = model if model.startswith("anthropic/") else f"anthropic/{model}"
        return _LLM(litellm_model=litellm_model, key=key)

    key = api_key
    litellm_model = model if "/" in model else f"{provider}/{model}"
    return _LLM(litellm_model=litellm_model, key=key)
