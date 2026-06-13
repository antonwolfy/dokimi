#!/usr/bin/env python3
import os
import platform
import re
import subprocess
import time
from pathlib import Path

import pytest

BINARY = Path("/app/crc_fast")
SOURCE = Path("/app/crc_fast.cpp")
REFERENCE = Path("/app/crc_bad")
BIG = "67108864"   # 64 MiB throughput run
TIMEOUT = 60.0

# Known reference value for length 1000003 (computed from the reflected
# 0x82F63B78 polynomial over the deterministic buffer fill). A hardware CRC32C
# implementation must reproduce this exactly.
KNOWN_LEN = "1000003"
KNOWN_CRC = 3160327329


def _strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//.*", "", text)


def _function_bodies(src):
    bodies = {}
    pattern = re.compile(
        r"\b(?:__attribute__\s*\(\([^)]*\)\)\s*)?(?:static\s+)?(?:inline\s+)?"
        r"(?:std::)?(?:uint32_t|uint64_t|unsigned|auto)\s+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*"
        r"(?:__attribute__\s*\(\([^)]*\)\)\s*)?\{"
    )
    for match in pattern.finditer(src):
        start = match.end()
        depth = 1
        for pos in range(start, len(src)):
            if src[pos] == "{":
                depth += 1
            elif src[pos] == "}":
                depth -= 1
                if depth == 0:
                    bodies[match.group(1)] = src[start:pos]
                    break
    return bodies


def _run(cmd):
    start = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    elapsed = time.perf_counter() - start
    assert result.returncode == 0, f"{cmd} exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    match = re.search(r"crc=(\d+)", result.stdout)
    assert match, f"missing crc=<value> in {result.stdout!r}"
    return int(match.group(1)), elapsed


def _best_time(cmd, rounds=3):
    _run(cmd)  # warmup
    times = []
    val = None
    for _ in range(rounds):
        val, sec = _run(cmd)
        times.append(sec)
    return val, min(times)


def _host_supports_sse42():
    machine = platform.machine().lower()
    if machine not in {"x86_64", "amd64", "i386", "i686"}:
        return False
    cpuinfo = Path("/proc/cpuinfo")
    if not cpuinfo.exists():
        return False
    flags = cpuinfo.read_text(errors="replace").lower().replace("_", ".")
    return "sse4.2" in flags


def test_binary_exists():
    assert SOURCE.exists(), "write /app/crc_fast.cpp"
    assert BINARY.exists(), "compile /app/crc_fast"
    assert os.access(BINARY, os.X_OK), "/app/crc_fast is not executable"


def test_matches_known_vector():
    value, _ = _run([str(BINARY), KNOWN_LEN])
    assert value == KNOWN_CRC, f"crc mismatch vs known vector: got {value} expected {KNOWN_CRC}"


def test_matches_reference_and_is_faster():
    ref_value, ref_time = _best_time([str(REFERENCE), BIG])
    fast_value, fast_time = _best_time([str(BINARY), BIG])
    assert fast_value == ref_value, f"crc mismatch vs reference: ref={ref_value} fast={fast_value}"
    if not _host_supports_sse42():
        pytest.skip("host lacks SSE4.2; scalar fallback is expected and not speed-gated")
    # Hardware CRC32C should clearly beat bit-at-a-time scalar code, but CI
    # hosts vary enough that a 4x gate has rejected valid SSE4.2 oracle runs.
    assert fast_time < ref_time / 3.0, (
        f"expected >=3x speedup; reference={ref_time:.4f}s fast={fast_time:.4f}s"
    )


def test_source_uses_hw_crc_with_dispatch():
    src = _strip_comments(SOURCE.read_text(errors="replace"))
    has_hw = bool(re.search(r"_mm_crc32_u(8|16|32|64)", src))
    has_runtime_probe = bool(re.search(r"__get_cpuid|__builtin_cpu_supports|getauxval|cpuid", src))
    hw_functions = [
        name
        for name, body in _function_bodies(src).items()
        if re.search(r"_mm_crc32_u(8|16|32|64)", body)
    ]
    dispatch_blocks = re.findall(
        r"\bif\s*\([^)]*(?:sse|crc|cpu|cpuid|hw|getauxval)[^)]*\)\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
        src,
        flags=re.I | re.S,
    )
    guarded_hw = any(re.search(r"_mm_crc32_u(8|16|32|64)", block) for block in dispatch_blocks)
    guarded_hw = guarded_hw or any(
        re.search(rf"\b{re.escape(name)}\s*\(", block)
        for block in dispatch_blocks
        for name in hw_functions
    )
    guarded_hw = guarded_hw or any(
        re.search(rf"\b(?:sse|crc|cpu|cpuid|hw|getauxval)[^?;]*\?\s*{re.escape(name)}\s*\(", src, re.I | re.S)
        or re.search(rf"\?\s*[^:;]*:\s*{re.escape(name)}\s*\(", src, re.I | re.S)
        for name in hw_functions
    )
    guarded_hw = guarded_hw or any(
        re.search(
            rf"\b(?:return\s+)?{re.escape(name)}\s*\([^;]*\)\s*;",
            src[max(0, match.start() - 160):match.start()],
            flags=re.I | re.S,
        )
        for name in hw_functions
        for match in re.finditer(r"__builtin_cpu_supports|__get_cpuid|getauxval|cpuid", src)
    )
    has_fallback = bool(re.search(r"0x82F63B78", src))
    assert has_hw, "use the hardware CRC32C intrinsic (_mm_crc32_u64/_u8)"
    assert has_runtime_probe, "probe CPU support at runtime before using SSE4.2 CRC intrinsics"
    assert guarded_hw, "call the hardware CRC path only behind a runtime dispatch check"
    assert has_fallback, "keep a portable scalar fallback (reflected 0x82F63B78 polynomial)"
