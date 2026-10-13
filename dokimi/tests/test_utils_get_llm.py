"""Tests for dokimi.utils.get_llm's Bedrock model-string routing."""

from dokimi.utils import get_llm


def test_get_llm_bedrock_openai_namespace_uses_converse_route(monkeypatch):
    # ANTHROPIC_DEFAULT_SONNET_MODEL, if set in the ambient shell, silently
    # substitutes any non-Anthropic-prefixed model -- clear it so this test
    # verifies routing logic, not whoever's environment it happens to run in.
    monkeypatch.delenv("ANTHROPIC_DEFAULT_SONNET_MODEL", raising=False)
    llm = get_llm("amazon-bedrock", "us.openai.gpt-5.6-terra", api_key="x")
    assert llm.litellm_model == "bedrock/converse/us.openai.gpt-5.6-terra"


def test_get_llm_bedrock_anthropic_namespace_unaffected(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_DEFAULT_SONNET_MODEL", raising=False)
    llm = get_llm("amazon-bedrock", "us.anthropic.claude-sonnet-5", api_key="x")
    assert llm.litellm_model == "bedrock/us.anthropic.claude-sonnet-5"
