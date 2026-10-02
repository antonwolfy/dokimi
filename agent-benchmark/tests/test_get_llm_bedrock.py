# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""get_llm maps only bare model names to ANTHROPIC_DEFAULT_SONNET_MODEL on Bedrock."""

from __future__ import annotations

import pytest

from agent_benchmarks.utils import get_llm


@pytest.mark.parametrize("model", [
    "us.anthropic.claude-opus-4-1-20250805-v1:0",
    "anthropic.claude-3-haiku-20240307-v1:0",
    "amazon.nova-pro-v1:0",
])
def test_bedrock_model_id_is_not_replaced(monkeypatch, model):
    monkeypatch.setenv("ANTHROPIC_DEFAULT_SONNET_MODEL", "us.anthropic.sonnet")
    assert get_llm("amazon-bedrock", model).litellm_model == f"bedrock/{model}"


def test_bare_model_name_is_mapped_to_the_default_sonnet(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_DEFAULT_SONNET_MODEL", "us.anthropic.sonnet")
    assert get_llm("amazon-bedrock", "claude-sonnet-4-5").litellm_model == "bedrock/us.anthropic.sonnet"
