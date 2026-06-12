#!/usr/bin/env python3
"""CLI for agent-benchmark: thin compatibility shim.

The implementation now lives in the ``agent_benchmarks`` package. This module
keeps ``python cli.py ...`` working. Only ``main`` and ``build_parser`` are
re-exported here; import command functions from ``agent_benchmarks.commands.*``.
"""

from __future__ import annotations

from agent_benchmarks.cli import build_parser, main

__all__ = ["build_parser", "main"]

if __name__ == "__main__":
    main()
