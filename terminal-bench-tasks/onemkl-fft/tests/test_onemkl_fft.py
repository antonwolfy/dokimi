#!/usr/bin/env python3
"""Verifier for onemkl-fft: DFTI forward/backward vs naive DFT reference."""
import os
import re
import subprocess
from pathlib import Path

BINARY = Path("/app/fft_mkl")
SERIAL = Path("/app/fft_serial")
TARGET_SOURCE = Path("/app/fft_mkl.c")
ARGS = ["2048"]
KEYWORDS = ["DftiComputeForward", "DftiComputeBackward", "mkl_dfti.h"]
TIMEOUT_SEC = 20.0


def _run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SEC + 10)
    assert result.returncode == 0, (
        f"{cmd} exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "VALID" in result.stdout, f"expected VALID in stdout, got {result.stdout!r}"
    return result.stdout


def _field(text, name):
    m = re.search(name + r"=([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", text)
    assert m, f"no {name}=<value> found in {text!r}"
    return float(m.group(1))


def test_binary_exists():
    assert BINARY.exists(), f"{BINARY} not found; compile the oneMKL FFT binary"
    assert os.access(BINARY, os.X_OK), f"{BINARY} is not executable"
    assert SERIAL.exists(), f"{SERIAL} not found; serial reference binary is required"
    assert os.access(SERIAL, os.X_OK), f"{SERIAL} is not executable"


def test_matches_serial_reference():
    serial_out = _run([str(SERIAL), *ARGS])
    mkl_out = _run([str(BINARY), *ARGS])
    assert int(_field(serial_out, "peak")) == int(_field(mkl_out, "peak")), (
        "dominant FFT bin differs from serial reference"
    )
    s, m = _field(serial_out, "sig"), _field(mkl_out, "sig")
    assert abs(s - m) <= abs(s) * 1e-4, f"FFT magnitude signature {m} differs from reference {s}"
    assert _field(mkl_out, "rterr") < 1e-6, "round-trip error too large; backward FFT incorrect"


def test_source_uses_required_dfti_api():
    assert TARGET_SOURCE.exists(), f"{TARGET_SOURCE} not found"
    text = TARGET_SOURCE.read_text(errors="replace")
    missing = [kw for kw in KEYWORDS if kw not in text]
    assert not missing, f"missing required oneMKL DFTI markers {missing} in {TARGET_SOURCE}"
