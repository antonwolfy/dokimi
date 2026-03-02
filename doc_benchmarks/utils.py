import sys

def normalize_model_ref(provider: str, model: str) -> str:
    """Normalize provider and model names for comparison."""
    return f"{(provider or '').strip().lower()}/{(model or '').strip().lower()}"
