"""Tests for the optional Docling ingestion loader (graceful degradation)."""

from __future__ import annotations

import pytest

from doc_benchmarks.ingest.docling_loader import (
    convert_to_markdown,
    discover_documents,
    docling_available,
    is_supported,
)


def test_is_supported():
    assert is_supported("manual.pdf")
    assert is_supported("slides.PPTX")  # case-insensitive
    assert is_supported("scan.png")
    assert not is_supported("notes.md")
    assert not is_supported("data.csv")


def test_discover_documents_filters(tmp_path):
    (tmp_path / "a.pdf").write_text("x")
    (tmp_path / "b.docx").write_text("x")
    (tmp_path / "c.md").write_text("x")
    (tmp_path / "d.txt").write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "e.pdf").write_text("x")

    found = {p.name for p in discover_documents(tmp_path)}
    assert found == {"a.pdf", "b.docx", "e.pdf"}

    non_recursive = {p.name for p in discover_documents(tmp_path, recursive=False)}
    assert "e.pdf" not in non_recursive


def test_discover_single_file(tmp_path):
    f = tmp_path / "x.pdf"
    f.write_text("x")
    assert discover_documents(f) == [f]
    md = tmp_path / "y.md"
    md.write_text("x")
    assert discover_documents(md) == []


@pytest.mark.skipif(docling_available(), reason="docling installed; testing the missing path")
def test_convert_raises_clear_error_without_docling(tmp_path):
    f = tmp_path / "x.pdf"
    f.write_text("x")
    with pytest.raises(ImportError, match="doc-benchmark\\[ocr\\]"):
        convert_to_markdown(f)
