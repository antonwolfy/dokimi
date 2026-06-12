"""Tests for the MCP-protocol doc client and its factory wiring."""

import builtins

import pytest

from agent_benchmarks.mcp.factory import create_doc_source_client
from agent_benchmarks.mcp.mcp_protocol import MCPProtocolClient, _require_mcp
from agent_benchmarks.mcp import MCPConnectionError


# ── factory parsing ─────────────────────────────────────────────────────
def test_factory_parses_stdio_ref():
    client = create_doc_source_client("mcp:cmd=npx -y @upstash/context7-mcp")
    assert isinstance(client, MCPProtocolClient)
    assert client.transport == "stdio"
    assert client.command == "npx"
    assert client.args == ["-y", "@upstash/context7-mcp"]


def test_factory_parses_http_ref_with_options():
    client = create_doc_source_client(
        "mcp:http=https://mcp.context7.com/mcp;tool=get-library-docs;id=uxlfoundation/oneTBB"
    )
    assert client.transport == "http"
    assert client.url == "https://mcp.context7.com/mcp"
    assert client.docs_tool == "get-library-docs"
    assert client.default_library_id == "uxlfoundation/oneTBB"


def test_factory_parses_sse_ref():
    client = create_doc_source_client("mcp:sse=https://example.com/sse")
    assert client.transport == "sse"
    assert client.url == "https://example.com/sse"


def test_factory_rejects_bad_ref():
    with pytest.raises(ValueError):
        create_doc_source_client("mcp:bogus")  # no '='
    with pytest.raises(ValueError):
        create_doc_source_client("mcp:ftp=foo")  # unknown transport


def test_constructor_validates_transport_args():
    with pytest.raises(ValueError):
        MCPProtocolClient(transport="stdio")  # missing command
    with pytest.raises(ValueError):
        MCPProtocolClient(transport="http")  # missing url


# ── helpers ──────────────────────────────────────────────────────────────
def test_pick_tool_by_hint():
    tools = ["resolve-library-id", "get-library-docs", "ping"]
    assert MCPProtocolClient._pick_tool(tools, None, ("get-library-docs",)) == "get-library-docs"
    # explicit but absent -> None
    assert MCPProtocolClient._pick_tool(tools, "nope", ("docs",)) is None
    # explicit present
    assert MCPProtocolClient._pick_tool(tools, "ping", ()) == "ping"


def test_result_text_flattens_blocks():
    class _Block:
        def __init__(self, text):
            self.text = text

    class _Result:
        content = [_Block("part one"), _Block("part two")]

    assert MCPProtocolClient._result_text(_Result()) == "part one\n\npart two"
    # dict form
    assert MCPProtocolClient._result_text({"content": [{"text": "x"}]}) == "x"
    # empty
    assert MCPProtocolClient._result_text(object()) == ""


def test_resolve_library_id_uses_default_without_sdk():
    """With a fixed id configured, resolve must not touch the SDK."""
    client = MCPProtocolClient(transport="http", url="http://x", default_library_id="fixed/id")
    assert client.resolve_library_id("whatever") == "fixed/id"


def test_require_mcp_raises_helpful_error(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            raise ImportError("no mcp")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(MCPConnectionError) as exc:
        _require_mcp()
    assert "pip install mcp" in str(exc.value)


def test_check_connection_false_without_sdk(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            raise ImportError("no mcp")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    client = MCPProtocolClient(transport="stdio", command="npx")
    assert client.check_connection() is False
