#!/usr/bin/env python3
import os
import re
import subprocess
import time
from pathlib import Path

BINARY = Path("/app/sort_fast")
SOURCE = Path("/app/sort_fast.cpp")
REFERENCE = Path("/app/sort_bad")
N = "20000000"
CORRECTNESS_SIZES = ["137", "104729", "1234567"]
TIMEOUT = 60.0


def _run(cmd):
    start = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    elapsed = time.perf_counter() - start
    assert result.returncode == 0, f"{cmd} exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    assert "VALID" in result.stdout, f"missing VALID (NOT_SORTED?) in {result.stdout!r} {result.stderr!r}"
    match = re.search(r"sig=([-+0-9.eE]+)", result.stdout)
    assert match, f"missing sig=<value> in {result.stdout!r}"
    return float(match.group(1)), elapsed


def _best_time(cmd, rounds=3):
    _run(cmd)  # warmup
    val = None
    times = []
    for _ in range(rounds):
        val, sec = _run(cmd)
        times.append(sec)
    return val, min(times)


def test_binary_exists():
    assert SOURCE.exists(), "write /app/sort_fast.cpp"
    assert BINARY.exists(), "compile /app/sort_fast"
    assert os.access(BINARY, os.X_OK), "/app/sort_fast is not executable"


def test_sorted_same_multiset_and_faster():
    for size in CORRECTNESS_SIZES:
        ref_sig, _ = _run([str(REFERENCE), size])
        fast_sig, _ = _run([str(BINARY), size])
        tolerance = max(1e-3, abs(ref_sig) * 1e-9)
        assert abs(ref_sig - fast_sig) <= tolerance, (
            f"signature mismatch at n={size}: ref={ref_sig} fast={fast_sig}"
        )

    ref_sig, ref_time = _best_time([str(REFERENCE), N])
    fast_sig, fast_time = _best_time([str(BINARY), N])
    tolerance = max(1e-3, abs(ref_sig) * 1e-9)
    assert abs(ref_sig - fast_sig) <= tolerance, (
        f"signature mismatch at n={N}: ref={ref_sig} fast={fast_sig}"
    )
    # radix/vectorized sort beats std::sort comfortably; require >=1.8x.
    # Measured margin is ~4x, so this threshold is conservative.
    assert fast_time < ref_time / 1.8, (
        f"expected >=1.8x speedup; reference={ref_time:.4f}s fast={fast_time:.4f}s"
    )


def test_source_does_not_use_std_sort_on_hot_path():
    text = SOURCE.read_text(errors="replace")
    # strip comments so a comment mentioning std::sort does not trip the check
    no_block = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    no_line = re.sub(r"//.*", "", no_block)
    assert not re.search(r"std\s*::\s*(sort|stable_sort)\b", no_line), (
        "replace std::sort/std::stable_sort on the hot path with a faster sort"
    )
