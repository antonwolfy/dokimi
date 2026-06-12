#!/usr/bin/env python3
import os
import re
import subprocess
from pathlib import Path

REFERENCE = Path("/app/saxpy_aliasing")
BINARY = Path("/app/saxpy_restrict")
SOURCE = Path("/app/saxpy_restrict.c")
ARGS = ["2000000", "40"]
TIMEOUT = 20.0


def _run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    assert result.returncode == 0, f"{cmd} exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    assert "VALID" in result.stdout
    match = re.search(r"checksum=([-+0-9.eE]+)", result.stdout)
    assert match, f"missing checksum=<value> in {result.stdout!r}"
    return float(match.group(1))


def test_binary_exists():
    assert SOURCE.exists(), "write /app/saxpy_restrict.c"
    assert BINARY.exists(), "compile /app/saxpy_restrict"
    assert os.access(BINARY, os.X_OK), "/app/saxpy_restrict is not executable"


def test_result_matches_reference():
    reference = _run([str(REFERENCE), *ARGS])
    actual = _run([str(BINARY), *ARGS])
    tolerance = max(1e-6, abs(reference) * 1e-10)
    assert abs(reference - actual) <= tolerance, f"checksum mismatch: reference={reference} actual={actual}"


def test_source_declares_restrict_contract_and_vectorizes():
    text = SOURCE.read_text(errors="replace")
    assert "restrict" in text, "non-overlapping pointer parameters should use C restrict"
    compile_result = subprocess.run(
        ["gcc", "-O3", "-std=c11", "-fopt-info-vec-optimized=/tmp/restrict_vec.log", str(SOURCE), "-lm", "-o", "/tmp/restrict_check"],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )
    assert compile_result.returncode == 0, compile_result.stderr
    vec_log = Path("/tmp/restrict_vec.log").read_text(errors="replace")
    assert "vectorized" in vec_log.lower(), f"expected vectorization evidence, got {vec_log!r}"
