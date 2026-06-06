#!/usr/bin/env python3
"""Verifier for ipp-dotprod: ippsDotProd_64f vs serial reference."""
import os
import re
import subprocess
from pathlib import Path

BINARY = Path("/app/ipp_dot")
SERIAL = Path("/app/ipp_serial")
TARGET_SOURCE = Path("/app/ipp_dot.c")
ARGS = ["4000000"]
KEYWORDS = ["ippsDotProd_64f", "ipp.h"]
TIMEOUT_SEC = 15.0


def _run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SEC + 10)
    assert result.returncode == 0, (
        f"{cmd} exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "VALID" in result.stdout, f"expected VALID in stdout, got {result.stdout!r}"
    return result.stdout


def _dot(text):
    m = re.search(r"dot=([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", text)
    assert m, f"no dot=<value> found in {text!r}"
    return float(m.group(1))


def test_binary_exists():
    assert BINARY.exists(), f"{BINARY} not found; compile the IPP binary"
    assert os.access(BINARY, os.X_OK), f"{BINARY} is not executable"
    assert SERIAL.exists(), f"{SERIAL} not found; serial reference binary is required"


def test_matches_serial_reference():
    s = _dot(_run([str(SERIAL), *ARGS]))
    m = _dot(_run([str(BINARY), *ARGS]))
    tol = max(1.0, abs(s) * 1e-9)
    assert abs(s - m) <= tol, f"IPP dot product {m} differs from serial reference {s}"


def test_rejects_bad_args():
    result = subprocess.run([str(BINARY), "0"], capture_output=True, text=True, timeout=20)
    assert result.returncode != 0, "expected non-zero exit for zero-length input"


def test_source_uses_required_ipp_api():
    assert TARGET_SOURCE.exists(), f"{TARGET_SOURCE} not found"
    text = TARGET_SOURCE.read_text(errors="replace")
    missing = [kw for kw in KEYWORDS if kw not in text]
    assert not missing, f"missing required IPP markers {missing} in {TARGET_SOURCE}"
