# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Parse and record the result object ``claude -p --output-format json`` prints."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from agent_benchmarks.metrics.usage import UsageRecord

from .models import OperationRecord


def _parse_claude_json(stdout: str, task: str, model: str, latency: float) -> Optional[UsageRecord]:
    """Parse ``claude -p --output-format json`` into a :class:`UsageRecord`.

    The CLI prints a single result object with ``total_cost_usd``, a nested
    ``usage`` block (input/output/cache tokens), ``duration_ms``, ``ttft_ms``,
    and ``num_turns``. Returns ``None`` when no parseable object is found (the
    elapsed wall-clock ``latency`` is used as a fallback for ``latency_sec``).
    """
    obj = _last_json_object(stdout)
    if obj is None:
        return None
    if not model:  # no --model: record what the CLI actually used, not ""
        model = _main_model(obj.get("modelUsage"))
    u = obj.get("usage") or {}
    input_tokens = int(u.get("input_tokens", 0) or 0)
    output_tokens = int(u.get("output_tokens", 0) or 0)
    cache_read = int(u.get("cache_read_input_tokens", 0) or 0)
    cache_write = int(u.get("cache_creation_input_tokens", 0) or 0)
    duration_ms = obj.get("duration_ms")
    ttft_ms = obj.get("ttft_ms")
    cost = obj.get("total_cost_usd")
    return UsageRecord(
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        cost_usd=float(cost) if cost is not None else None,
        latency_sec=(duration_ms / 1000.0) if duration_ms is not None else latency,
        ttft_sec=(ttft_ms / 1000.0) if ttft_ms is not None else None,
        model=model,
        provider="claude-code",
        n_calls=int(obj.get("num_turns", 1) or 1),
        cost_known_calls=1 if cost is not None else 0,
    )


def _main_model(model_usage: object) -> str:
    """The ``modelUsage`` entry that cost the most (the first key may be a helper model)."""
    if not isinstance(model_usage, dict) or not model_usage:
        return ""

    def cost(item: tuple) -> float:
        entry = item[1] if isinstance(item[1], dict) else {}
        try:
            return float(entry.get("costUSD") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return str(max(model_usage.items(), key=cost)[0])


def _last_json_object(text: str) -> Optional[dict]:
    """Return the last top-level JSON object printed on stdout, if any."""
    if not text:
        return None
    # The result object is normally the final non-empty line.
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    # Fall back to the last {...} span anywhere in the output.
    matches = re.findall(r"\{.*\}", text, re.DOTALL)
    if matches:
        try:
            return json.loads(matches[-1])
        except json.JSONDecodeError:
            return None
    return None


def solver_error(stdout: str, edited: bool = False) -> Optional[str]:
    """Why the CLI made no attempt at all, or ``None`` if it made one.

    No result object on stdout is a CLI that died; it counts as no attempt only
    while the work tree is untouched (*edited* false). After real edits (a node
    out-of-memory, the kernel OOM killer) the verifier decides, as for any error
    after an attempt.

    Missing or rejected credentials, a flagged first request or an unknown model
    id end a run with ``is_error`` before any output: a tooling failure, which
    the runner leaves out like a harness error. An error *after* an attempt (a
    529 at turn 40, ``prompt_too_long`` from a skill arm reading too much) is
    the arm's outcome and is scored; :func:`terminal_reason` records it.
    """
    obj = _last_json_object(stdout)
    if obj is None:
        return None if edited else "no result object on stdout"
    if not (obj.get("is_error") or obj.get("terminal_reason") == "api_error"):
        return None
    usage = obj.get("usage")
    output_tokens = int(usage.get("output_tokens", 0) or 0) if isinstance(usage, dict) else 0
    if output_tokens > 0 and int(obj.get("num_turns", 0) or 0) > 1:
        return None  # it tried; the error ends an attempt, it does not replace one
    errors = obj.get("errors")
    errors = errors if isinstance(errors, list) else []
    message = str(obj.get("result") or "").strip() or "\n".join(str(e) for e in errors).strip()
    first = message.splitlines()[:1]
    return f"{obj.get('terminal_reason') or obj.get('subtype') or 'error'}: {first[0] if first else ''}"[:300]


def terminal_reason(stdout: str) -> Optional[str]:
    """How the CLI ended the run (``terminal_reason``, else ``subtype``), for every row."""
    obj = _last_json_object(stdout)
    if obj is None:
        return None
    reason = obj.get("terminal_reason") or obj.get("subtype")
    return str(reason) if reason else None


def record_solver(proc: subprocess.CompletedProcess, task: str, model: Optional[str],
                  latency: float, output_dir: Path, operations: list[OperationRecord], log,
                  extra_metrics: dict[str, Any], edited: bool = False) -> Optional[UsageRecord]:
    """Log one solver run, save ``solver.json``, and fold its telemetry into the run.

    *edited*: the work tree changed during the run (see :func:`solver_error`).
    """
    log.write(proc.stdout or "")
    log.write(proc.stderr or "")
    error = solver_error(proc.stdout, edited=edited)
    if error:  # no attempt was made: the runner leaves the cell out, like metrics.error
        extra_metrics["solver_error"] = error
    usage = _parse_claude_json(proc.stdout, task, model or "", latency)
    reason = terminal_reason(proc.stdout) or ("no_result" if usage is None else None)
    if reason:
        extra_metrics["terminal_reason"] = reason
    (output_dir / "solver.json").write_text(proc.stdout or "", encoding="utf-8")
    if usage is not None:
        # Kept if a later step fails (the copy back): the solve was paid for either way.
        extra_metrics.update(usage.as_metrics_dict())
        if usage.model:
            extra_metrics["model"] = usage.model
        operations.append(
            OperationRecord(type="loop", name="claude-turns", elapsed_sec=usage.latency_sec,
                            metadata={"n_calls": usage.n_calls})
        )
    return usage
