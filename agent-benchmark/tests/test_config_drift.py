"""Tests for products config loading and cross-registry drift detection."""

from __future__ import annotations

import textwrap

from agent_benchmarks.config import (
    detect_registry_drift,
    load_products_config,
)
from agent_benchmarks.registry import LibraryRegistry


def test_committed_configs_have_no_drift():
    """libraries.yaml and config/products.yaml must agree on shared identity."""
    assert detect_registry_drift() == []


def test_load_products_config():
    cfg = load_products_config()
    assert "oneTBB" in cfg.products
    assert cfg.llm  # answerer/judge/generator block present


def _registry(tmp_path, body: str) -> LibraryRegistry:
    p = tmp_path / "libs.yaml"
    p.write_text(body)
    return LibraryRegistry(path=p)


def test_drift_detected(tmp_path, monkeypatch):
    reg = _registry(
        tmp_path,
        textwrap.dedent(
            """
            libraries:
              foo:
                name: Foo
                description: x
                repo: org-a/foo
            """
        ),
    )
    products = load_products_config()
    # Synthesize a products config that disagrees on repo.
    products.products = {"foo": {"github_repo": "org-b/foo"}}
    issues = detect_registry_drift(registry=reg, products=products)
    assert len(issues) == 1
    assert "foo" in issues[0]


def test_unregistered_product_is_not_drift(tmp_path):
    reg = _registry(tmp_path, "libraries:\n  foo:\n    name: Foo\n    description: x\n    repo: org-a/foo\n")
    products = load_products_config()
    products.products = {"bar": {"github_repo": "org-b/bar"}}  # not in registry
    assert detect_registry_drift(registry=reg, products=products) == []


def test_config_check_cli_passes():
    from agent_benchmarks.config_check import main

    assert main() == 0
