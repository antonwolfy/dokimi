#!/usr/bin/env python3
import os
import re
import subprocess
import time
from pathlib import Path

BAD = Path("/app/shared_counter_bad")
BINARY = Path("/app/shared_counter_fixed")
SOURCE = Path("/app/shared_counter_fixed.cpp")
ARGS = ["4", "5000000"]
TIMEOUT = 25.0


def _run(cmd):
    start = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    elapsed = time.perf_counter() - start
    assert result.returncode == 0, f"{cmd} exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    assert "VALID" in result.stdout
    total = int(re.search(r"total=(\d+)", result.stdout).group(1))
    checksum = int(re.search(r"checksum=(\d+)", result.stdout).group(1))
    return total, checksum, elapsed


def _best(cmd, rounds=3):
    _run(cmd)  # warmup: absorb cold-cache and CPU-frequency-ramp effects before timing
    last_total = last_checksum = None
    elapsed = []
    for _ in range(rounds):
        last_total, last_checksum, seconds = _run(cmd)
        elapsed.append(seconds)
    return last_total, last_checksum, min(elapsed)


def test_binary_exists():
    assert SOURCE.exists(), "write /app/shared_counter_fixed.cpp"
    assert BINARY.exists(), "compile /app/shared_counter_fixed"
    assert os.access(BINARY, os.X_OK), "/app/shared_counter_fixed is not executable"


def test_correct_and_faster_than_global_atomic_baseline():
    bad_total, bad_checksum, bad_time = _best([str(BAD), *ARGS])
    fixed_total, fixed_checksum, fixed_time = _best([str(BINARY), *ARGS])
    assert fixed_total == bad_total == int(ARGS[0]) * int(ARGS[1])
    assert fixed_checksum == bad_checksum
    assert fixed_time < bad_time * 0.75, (
        f"expected local aggregation speedup; bad={bad_time:.4f}s fixed={fixed_time:.4f}s"
    )


def test_source_uses_local_aggregation():
    text = SOURCE.read_text(errors="replace")
    assert "local" in text.lower() or "thread" in text.lower(), "source should make per-thread/local aggregation clear"
    assert text.count("fetch_add") <= 1, "do not use global atomic fetch_add in the hot loop"
