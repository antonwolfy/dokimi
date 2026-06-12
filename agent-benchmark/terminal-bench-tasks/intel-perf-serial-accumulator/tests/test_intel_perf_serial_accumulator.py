#!/usr/bin/env python3
import os
import re
import subprocess
import time
from pathlib import Path

BINARY = Path("/app/dot_fast")
SOURCE = Path("/app/dot_fast.cpp")
SERIAL = Path("/app/dot_serial")
N = "24000000"
TIMEOUT = 20.0


def _run(cmd):
    start = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    elapsed = time.perf_counter() - start
    assert result.returncode == 0, f"{cmd} exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    assert "VALID" in result.stdout
    match = re.search(r"dot=([-+0-9.eE]+)", result.stdout)
    assert match, f"missing dot=<value> in {result.stdout!r}"
    return float(match.group(1)), elapsed


def _best_time(cmd, rounds=3):
    _run(cmd)  # warmup: absorb cold-cache and CPU-frequency-ramp effects before timing
    values = []
    elapsed = []
    for _ in range(rounds):
        value, seconds = _run(cmd)
        values.append(value)
        elapsed.append(seconds)
    return values[-1], min(elapsed)


def test_binary_exists():
    assert SOURCE.exists(), "write /app/dot_fast.cpp"
    assert BINARY.exists(), "compile /app/dot_fast"
    assert os.access(BINARY, os.X_OK), "/app/dot_fast is not executable"


def test_result_matches_serial_and_is_faster():
    serial_value, serial_time = _best_time([str(SERIAL), N])
    fast_value, fast_time = _best_time([str(BINARY), N])
    tolerance = max(1e-5, abs(serial_value) * 1e-10)
    assert abs(serial_value - fast_value) <= tolerance, (
        f"dot mismatch: serial={serial_value} fast={fast_value}"
    )
    assert fast_time < serial_time * 0.90, (
        f"expected at least 10% speedup; serial={serial_time:.4f}s fast={fast_time:.4f}s"
    )


def test_source_breaks_single_accumulator_pattern():
    text = SOURCE.read_text(errors="replace")
    accumulator_names = len(re.findall(r"\b(acc|sum|partial)[A-Za-z0-9_]*\b", text))
    assert accumulator_names >= 4 or "std::array" in text or "vector<double>" in text, (
        "source should use multiple independent partial accumulators or an equivalent reduction structure"
    )
