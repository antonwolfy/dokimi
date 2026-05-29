#!/usr/bin/env python3
"""Verifier for onemkl-dgemm: cblas_dgemm vs serial reference."""
import os
import re
import subprocess
import time
from pathlib import Path

BINARY = Path("/app/dgemm_mkl")
SERIAL = Path("/app/dgemm_serial")
TARGET_SOURCE = Path("/app/dgemm_mkl.c")
ARGS = ["640"]
KEYWORDS = ["cblas_dgemm", "mkl.h"]
TIMEOUT_SEC = 20.0


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
    m = re.search(r"sig=([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", text)
    assert m, f"no sig=<value> found in {text!r}"
    return float(m.group(1))


def test_binary_exists():
    assert BINARY.exists(), f"{BINARY} not found; compile the oneMKL binary"
    assert os.access(BINARY, os.X_OK), f"{BINARY} is not executable"
    assert SERIAL.exists(), f"{SERIAL} not found; serial reference binary is required"


def test_matches_serial_reference():
    serial_out, _ = _run([str(SERIAL), *ARGS])
    mkl_out, elapsed = _run([str(BINARY), *ARGS])
    s, m = _sig(serial_out), _sig(mkl_out)
    tol = max(1.0, abs(s) * 1e-9)
    assert abs(s - m) <= tol, f"oneMKL signature {m} differs from serial reference {s}"
    assert elapsed < TIMEOUT_SEC, f"execution took {elapsed:.2f}s, expected under {TIMEOUT_SEC}s"


def test_rejects_bad_args():
    result = subprocess.run([str(BINARY), "0"], capture_output=True, text=True, timeout=20)
    assert result.returncode != 0, "expected non-zero exit for N=0"


def test_source_uses_required_mkl_api():
    assert TARGET_SOURCE.exists(), f"{TARGET_SOURCE} not found"
    text = TARGET_SOURCE.read_text(errors="replace")
    missing = [kw for kw in KEYWORDS if kw not in text]
    assert not missing, f"missing required oneMKL markers {missing} in {TARGET_SOURCE}"
