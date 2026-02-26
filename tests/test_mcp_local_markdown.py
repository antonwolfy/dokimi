"""Tests for LocalMarkdownClient."""

import pytest
from pathlib import Path
from doc_benchmarks.mcp.local_markdown import LocalMarkdownClient


@pytest.fixture
def docs_dir(tmp_path):
    """Create a small local docs tree."""
    (tmp_path / "install.md").write_text(
        "# Installation\n\nRun `pip install onetbb` to install the library.\n"
        "The installer sets up all required components automatically."
    )
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "parallel_for.md").write_text(
        "# parallel_for\n\nThe `parallel_for` function divides a range into chunks "
        "and processes them in parallel using a thread pool."
    )
    (tmp_path / "api" / "task_group.md").write_text(
        "# task_group\n\nA task_group allows spawning multiple independent tasks "
        "that run concurrently."
    )
    (tmp_path / "about.html").write_text(
        "<html><body><h1>About</h1><p>oneTBB is a C++ template library.</p></body></html>"
    )
    return tmp_path


def test_check_connection_existing_dir(docs_dir):
    client = LocalMarkdownClient(docs_dir)
    assert client.check_connection() is True


def test_check_connection_missing_dir(tmp_path):
    client = LocalMarkdownClient(tmp_path / "nonexistent")
    assert client.check_connection() is False


def test_check_connection_empty_dir(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    client = LocalMarkdownClient(empty)
    assert client.check_connection() is False


def test_resolve_library_id(docs_dir):
    client = LocalMarkdownClient(docs_dir)
    library_id = client.resolve_library_id("oneTBB")
    assert library_id == f"local:{docs_dir}"


def test_get_library_docs_returns_results(docs_dir):
    client = LocalMarkdownClient(docs_dir)
    docs = client.get_library_docs("local:oneTBB", "parallel_for thread pool")
    assert len(docs) > 0
    assert all("content" in d for d in docs)
    assert all("source" in d for d in docs)
    assert all(d["source"] == "local" for d in docs)


def test_get_library_docs_relevance_ordering(docs_dir):
    client = LocalMarkdownClient(docs_dir)
    docs = client.get_library_docs("local:oneTBB", "parallel_for", max_results=3)
    # The parallel_for.md should score highest
    assert "parallel_for" in docs[0]["content"].lower()


def test_get_library_docs_html_stripped(docs_dir):
    client = LocalMarkdownClient(docs_dir)
    docs = client.get_library_docs("local:oneTBB", "about oneTBB", max_results=5)
    for d in docs:
        assert "<html>" not in d["content"]
        assert "<body>" not in d["content"]


def test_get_library_docs_respects_max_results(docs_dir):
    client = LocalMarkdownClient(docs_dir)
    docs = client.get_library_docs("local:oneTBB", "library", max_results=2)
    assert len(docs) <= 2


def test_get_library_docs_single_file(tmp_path):
    single = tmp_path / "readme.md"
    single.write_text("# README\n\nThis is the main documentation file.")
    client = LocalMarkdownClient(single)
    assert client.check_connection() is True
    docs = client.get_library_docs(f"local:{single}", "documentation")
    assert len(docs) == 1
    assert "documentation" in docs[0]["content"].lower()


def test_get_library_docs_missing_path_raises(tmp_path):
    from doc_benchmarks.mcp import MCPConnectionError
    client = LocalMarkdownClient(tmp_path / "missing")
    with pytest.raises(MCPConnectionError):
        client.get_library_docs("local:missing", "anything")


def test_relevance_score_in_output(docs_dir):
    client = LocalMarkdownClient(docs_dir)
    docs = client.get_library_docs("local:oneTBB", "install pip")
    assert all("relevance_score" in d for d in docs)
    assert all(0.0 <= d["relevance_score"] <= 1.0 for d in docs)
