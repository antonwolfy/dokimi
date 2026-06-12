"""Tests for IntentRegistry (intents.yaml problem/intent space)."""
from pathlib import Path

import pytest
import yaml

from agent_benchmarks.intents import IntentRegistry
from agent_benchmarks.registry import ProductRegistry


def _write_intents(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "intents.yaml"
    p.write_text(yaml.dump(data))
    return p


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def test_loads_domains(tmp_path):
    path = _write_intents(tmp_path, {
        "domains": {
            "debugging": {
                "name": "Debugging",
                "description": "Find bugs",
                "products": ["inspector", "gdb_intel"],
                "example_intents": ["Find the data race"],
            },
            "math": {
                "name": "Math",
                "description": "Numerics",
                "products": ["onemkl"],
            },
        }
    })
    reg = IntentRegistry(path=path)
    assert set(reg.keys()) == {"debugging", "math"}
    domain = reg.get("debugging")
    assert domain.name == "Debugging"
    assert domain.products == ["inspector", "gdb_intel"]
    assert domain.example_intents == ["Find the data race"]


def test_missing_file_does_not_raise(tmp_path):
    reg = IntentRegistry(path=tmp_path / "nonexistent.yaml")
    assert reg.list() == []


def test_empty_file_does_not_raise(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("")
    reg = IntentRegistry(path=p)
    assert reg.list() == []


def test_get_missing_raises_key_error(tmp_path):
    path = _write_intents(tmp_path, {
        "domains": {"math": {"name": "Math", "description": "x", "products": []}}
    })
    reg = IntentRegistry(path=path)
    with pytest.raises(KeyError, match="nope"):
        reg.get("nope")


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def test_products_for_and_reverse_lookup(tmp_path):
    path = _write_intents(tmp_path, {
        "domains": {
            "debugging": {"name": "D", "description": "x", "products": ["inspector", "gdb_intel"]},
            "gpu": {"name": "G", "description": "x", "products": ["gdb_intel", "dpnp"]},
        }
    })
    reg = IntentRegistry(path=path)
    assert reg.products_for("debugging") == ["inspector", "gdb_intel"]
    assert reg.domains_for("gdb_intel") == ["debugging", "gpu"]
    assert reg.domains_for("dpnp") == ["gpu"]
    assert reg.domains_for("unknown") == []


# ---------------------------------------------------------------------------
# Validation against the product registry
# ---------------------------------------------------------------------------

def test_validate_flags_unknown_products(tmp_path):
    products_path = tmp_path / "products.yaml"
    products_path.write_text(yaml.dump({
        "products": {"onetbb": {"name": "oneTBB", "description": "x"}}
    }))
    intents_path = _write_intents(tmp_path, {
        "domains": {
            "parallel": {"name": "P", "description": "x", "products": ["onetbb", "ghost"]},
        }
    })
    reg = IntentRegistry(path=intents_path)
    issues = reg.validate(ProductRegistry(path=products_path))
    assert len(issues) == 1
    assert "ghost" in issues[0]
    assert "parallel" in issues[0]


# ---------------------------------------------------------------------------
# Bundled intents.yaml
# ---------------------------------------------------------------------------

def test_default_intents_load():
    reg = IntentRegistry()
    assert len(reg.keys()) >= 5
    assert "performance-optimization" in reg


def test_default_intents_reference_only_registered_products():
    assert IntentRegistry().validate() == []
