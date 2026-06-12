#!/usr/bin/env python3
import os
import re
import subprocess
import time
from pathlib import Path

BAD = Path("/app/false_sharing_bad")
BINARY = Path("/app/false_sharing_fixed")
SOURCE = Path("/app/false_sharing_fixed.cpp")
ARGS = ["4", "8000000"]
TIMEOUT = 25.0


def _run(cmd):
    start = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    elapsed = time.perf_counter() - start
    assert result.returncode == 0, f"{cmd} exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    assert "VALID" in result.stdout
    match = re.search(r"total=(\d+)", result.stdout)
    assert match, f"missing total=<value> in {result.stdout!r}"
    return int(match.group(1)), elapsed


def _best_time(cmd, rounds=3):
    _run(cmd)  # warmup: absorb cold-cache and CPU-frequency-ramp effects before timing
    total = None
    elapsed = []
    for _ in range(rounds):
        total, seconds = _run(cmd)
        elapsed.append(seconds)
    return total, min(elapsed)


def test_binary_exists():
    assert SOURCE.exists(), "write /app/false_sharing_fixed.cpp"
    assert BINARY.exists(), "compile /app/false_sharing_fixed"
    assert os.access(BINARY, os.X_OK), "/app/false_sharing_fixed is not executable"


def test_correct_and_faster_than_false_sharing_baseline():
    expected = int(ARGS[0]) * int(ARGS[1])
    bad_total, bad_time = _best_time([str(BAD), *ARGS])
    fixed_total, fixed_time = _best_time([str(BINARY), *ARGS])
    assert bad_total == expected
    assert fixed_total == expected
    assert fixed_time < bad_time * 0.90, (
        f"expected false-sharing fix speedup; bad={bad_time:.4f}s fixed={fixed_time:.4f}s"
    )


def test_source_uses_cache_line_separation():
    text = SOURCE.read_text(errors="replace")
    assert any(marker in text for marker in ["alignas(64)", "aligned(64)", "hardware_destructive_interference_size"]), (
        "source should explicitly separate per-thread counters onto cache lines"
    )
