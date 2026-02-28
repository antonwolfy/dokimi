"""Tests for LibraryRegistry."""
import textwrap
from pathlib import Path

import pytest
import yaml

from doc_benchmarks.registry import LibraryEntry, LibraryRegistry


def _write_registry(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "libraries.yaml"
    p.write_text(yaml.dump(data))
    return p


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def test_loads_all_entries(tmp_path):
    reg_path = _write_registry(tmp_path, {
        "libraries": {
            "onetbb": {
                "name": "oneTBB",
                "description": "Parallel library",
                "repo": "uxlfoundation/oneTBB",
                "context7_id": "uxlfoundation/onetbb",
                "doc_sources": ["context7"],
            },
            "onemkl": {
                "name": "oneMKL",
                "description": "Math library",
                "doc_sources": ["url:https://example.com/mkl"],
            },
        }
    })
    reg = LibraryRegistry(path=reg_path)
    assert len(reg.list()) == 2
    assert set(reg.keys()) == {"onetbb", "onemkl"}


def test_missing_file_does_not_raise(tmp_path):
    reg = LibraryRegistry(path=tmp_path / "nonexistent.yaml")
    assert reg.list() == []


def test_empty_file_does_not_raise(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("")
    reg = LibraryRegistry(path=p)
    assert reg.list() == []


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------

def test_get_returns_entry(tmp_path):
    reg_path = _write_registry(tmp_path, {
        "libraries": {
            "onetbb": {
                "name": "oneTBB",
                "description": "desc",
                "repo": "uxlfoundation/oneTBB",
                "context7_id": "uxlfoundation/onetbb",
                "doc_sources": ["context7"],
            }
        }
    })
    reg = LibraryRegistry(path=reg_path)
    entry = reg.get("onetbb")
    assert entry.name == "oneTBB"
    assert entry.repo == "uxlfoundation/oneTBB"
    assert entry.context7_id == "uxlfoundation/onetbb"
    assert entry.doc_sources == ["context7"]


def test_get_case_insensitive(tmp_path):
    reg_path = _write_registry(tmp_path, {
        "libraries": {"onetbb": {"name": "oneTBB", "description": "x"}}
    })
    reg = LibraryRegistry(path=reg_path)
    assert reg.get("ONETBB").key == "onetbb"
    assert reg.get("OneTBB").key == "onetbb"


def test_get_missing_raises_key_error(tmp_path):
    reg_path = _write_registry(tmp_path, {
        "libraries": {"onetbb": {"name": "oneTBB", "description": "x"}}
    })
    reg = LibraryRegistry(path=reg_path)
    with pytest.raises(KeyError, match="notexist"):
        reg.get("notexist")


def test_get_key_error_lists_available(tmp_path):
    reg_path = _write_registry(tmp_path, {
        "libraries": {
            "onetbb": {"name": "oneTBB", "description": "x"},
            "onemkl": {"name": "oneMKL", "description": "y"},
        }
    })
    reg = LibraryRegistry(path=reg_path)
    with pytest.raises(KeyError) as exc_info:
        reg.get("nope")
    assert "onetbb" in str(exc_info.value)
    assert "onemkl" in str(exc_info.value)


# ---------------------------------------------------------------------------
# contains / defaults
# ---------------------------------------------------------------------------

def test_contains(tmp_path):
    reg_path = _write_registry(tmp_path, {
        "libraries": {"onetbb": {"name": "oneTBB", "description": "x"}}
    })
    reg = LibraryRegistry(path=reg_path)
    assert "onetbb" in reg
    assert "missing" not in reg


def test_default_doc_sources(tmp_path):
    """Entry without explicit doc_sources defaults to ['context7']."""
    reg_path = _write_registry(tmp_path, {
        "libraries": {"onetbb": {"name": "oneTBB", "description": "x"}}
    })
    reg = LibraryRegistry(path=reg_path)
    assert reg.get("onetbb").doc_sources == ["context7"]


def test_multiple_doc_sources(tmp_path):
    reg_path = _write_registry(tmp_path, {
        "libraries": {
            "onemkl": {
                "name": "oneMKL",
                "description": "x",
                "doc_sources": ["context7", "url:https://example.com/mkl"],
            }
        }
    })
    reg = LibraryRegistry(path=reg_path)
    entry = reg.get("onemkl")
    assert len(entry.doc_sources) == 2
    assert "url:https://example.com/mkl" in entry.doc_sources


# ---------------------------------------------------------------------------
# Default registry (bundled libraries.yaml)
# ---------------------------------------------------------------------------

def test_default_registry_loads():
    reg = LibraryRegistry()
    keys = reg.keys()
    assert "onetbb" in keys
    assert len(keys) >= 4


def test_default_registry_onetbb_has_repo():
    reg = LibraryRegistry()
    entry = reg.get("onetbb")
    assert entry.repo is not None
    assert entry.context7_id is not None
    assert len(entry.doc_sources) >= 1
