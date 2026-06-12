#!/usr/bin/env python3
"""Verifier for onedpl-transform-reduce."""
import os
import re
import subprocess
import time
from pathlib import Path

BINARY = Path("/app/dpl_reduce")
SERIAL = Path("/app/reduce_serial")
TARGET_SOURCE = Path("/app/dpl_reduce.cpp")
ARGS = ["4000000"]
KEYWORDS = ["oneapi/dpl", "transform_reduce", "par_unseq"]
TIMEOUT_SEC = 10.0


def _run(cmd):
    start = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SEC + 10)
    elapsed = time.perf_counter() - start
    assert result.returncode == 0, (
        f"{cmd} exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "VALID" in result.stdout, f"expected VALID in stdout, got {result.stdout!r}"
    return result.stdout, elapsed


def _sig(text):
    m = re.search(r"sig=([-+]?\d+)", text)
    assert m, f"no sig=<value> found in {text!r}"
    return int(m.group(1))


def test_binary_exists():
    assert BINARY.exists(), f"{BINARY} not found; compile the oneDPL binary"
    assert os.access(BINARY, os.X_OK), f"{BINARY} is not executable"
    assert SERIAL.exists(), f"{SERIAL} not found; serial reference binary is required"


def test_matches_serial_reference():
    serial_out, _ = _run([str(SERIAL), *ARGS])
    dpl_out, elapsed = _run([str(BINARY), *ARGS])
    assert _sig(serial_out) == _sig(dpl_out), "oneDPL signature differs from serial reference"
    assert elapsed < TIMEOUT_SEC, f"execution took {elapsed:.2f}s, expected under {TIMEOUT_SEC}s"


def test_rejects_bad_args():
    result = subprocess.run([str(BINARY), "0"], capture_output=True, text=True, timeout=20)
    assert result.returncode != 0, "expected non-zero exit for zero-length input"


def test_source_uses_required_onedpl_api():
    assert TARGET_SOURCE.exists(), f"{TARGET_SOURCE} not found"
    text = TARGET_SOURCE.read_text(errors="replace")
    missing = [kw for kw in KEYWORDS if kw not in text]
    assert not missing, f"missing required oneDPL markers {missing} in {TARGET_SOURCE}"
