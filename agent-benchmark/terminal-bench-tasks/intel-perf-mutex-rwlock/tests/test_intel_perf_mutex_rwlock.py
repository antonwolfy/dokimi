#!/usr/bin/env python3
import os
import re
import subprocess
import time
from pathlib import Path

BINARY = Path("/app/rwlock_fixed")
SOURCE = Path("/app/rwlock_fixed.cpp")
REFERENCE = Path("/app/rwlock_bad")
TIMEOUT = 60.0


def _strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//.*", "", text)


def _function_body(src, name):
    match = re.search(rf"\b{name}\s*\([^)]*\)\s*(?:const\s*)?\{{", src)
    assert match, f"missing {name}() implementation"
    start = match.end()
    depth = 1
    for pos in range(start, len(src)):
        if src[pos] == "{":
            depth += 1
        elif src[pos] == "}":
            depth -= 1
            if depth == 0:
                return src[start:pos]
    raise AssertionError(f"could not parse {name}() body")


def _run(binary, threads, ops):
    cmd = [str(binary), str(threads), str(ops)]
    start = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    elapsed = time.perf_counter() - start
    assert result.returncode == 0, f"{cmd} exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    match = re.search(r"checksum=(\d+)", result.stdout)
    assert match, f"missing checksum=<value> in {result.stdout!r}"
    return int(match.group(1)), elapsed


def test_binary_exists():
    assert SOURCE.exists(), "write /app/rwlock_fixed.cpp"
    assert BINARY.exists(), "compile /app/rwlock_fixed"
    assert os.access(BINARY, os.X_OK), "/app/rwlock_fixed is not executable"


def test_checksum_matches_reference():
    # write path must stay correct: the array checksum (driven only by writes)
    # must equal the reference build's at several thread counts
    for threads, ops in [(2, 300000), (4, 300000), (8, 200000)]:
        ref_sum, _ = _run(REFERENCE, threads, ops)
        fix_sum, _ = _run(BINARY, threads, ops)
        assert fix_sum == ref_sum, (
            f"checksum mismatch at threads={threads} ops={ops}: ref={ref_sum} fixed={fix_sum}"
        )


def test_terminates_under_load():
    # rwlock must not deadlock/starve to the point of timing out under read load
    _, elapsed = _run(BINARY, 8, 400000)
    assert elapsed < 30.0, f"run took {elapsed:.1f}s; possible deadlock/starvation"


def test_source_uses_reader_writer_lock():
    src = _strip_comments(SOURCE.read_text(errors="replace"))
    get_body = _function_body(src, "get")
    bump_body = _function_body(src, "bump")
    shared_mutexes = re.findall(r"(?:std::)?shared_mutex\s+([A-Za-z_]\w*)\s*[;{=]", src)
    assert shared_mutexes, "use std::shared_mutex for the reader-writer lock"

    def locks_shared_mutex(body, lock_type):
        for mutex in shared_mutexes:
            templated = rf"(?:std::)?{lock_type}\s*<\s*(?:std::)?shared_mutex\s*>\s+[A-Za-z_]\w*\s*\(\s*{mutex}\s*\)"
            deduced = rf"(?:std::)?{lock_type}\s+[A-Za-z_]\w*\s*\(\s*{mutex}\s*\)"
            brace_init = rf"(?:std::)?{lock_type}\s*<\s*(?:std::)?shared_mutex\s*>\s+[A-Za-z_]\w*\s*\{{\s*{mutex}\s*\}}"
            if re.search(templated, body) or re.search(deduced, body) or re.search(brace_init, body):
                return True
        return False

    has_shared_lock = locks_shared_mutex(get_body, "shared_lock")
    has_unique_lock = locks_shared_mutex(bump_body, "unique_lock") or locks_shared_mutex(bump_body, "lock_guard")
    assert has_shared_lock, "get() must take a std::shared_lock on the shared_mutex data guard"
    assert has_unique_lock, "bump() must take an exclusive lock on the same shared_mutex data guard"
