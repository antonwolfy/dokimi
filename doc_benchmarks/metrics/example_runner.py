"""Isolated example execution and validation."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExampleResult:
    """Single example execution result."""

    index: int
    lang: str
    code: str
    passed: bool
    error: str | None = None


# Supported languages with execution commands
EXECUTORS = {
    "python": ["python3", "-c"],
    "bash": ["bash", "-c"],
    "sh": ["sh", "-c"],
}


def extract_examples(markdown: str) -> list[tuple[str, str]]:
    """Extract fenced code blocks with language tags from markdown.

    Supports optional metadata after language tag (e.g. ```python title="x.py").
    Normalizes language tags to lowercase.
    Returns list of (language, code) tuples.
    """
    pattern = re.compile(r"```(\w+)[^\n]*\n(.*?)```", re.DOTALL)
    return [(m.group(1).lower(), m.group(2).strip()) for m in pattern.finditer(markdown)]


def run_example(lang: str, code: str, timeout: int = 5) -> tuple[bool, str | None]:
    """Execute code in isolated subprocess.

    Returns (success, error_message).
    """
    if lang not in EXECUTORS:
        return False, f"Unsupported language: {lang}"

    cmd = EXECUTORS[lang] + [code]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode == 0:
            return True, None
        return False, f"Exit code {result.returncode}: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, f"Timeout after {timeout}s"
    except Exception as exc:
        return False, f"Execution error: {type(exc).__name__}: {exc}"


def score_examples(doc_path: Path, timeout: int = 5) -> tuple[float, list[ExampleResult]]:
    """Run all examples in a document and return pass rate and per-example results.

    Returns (pass_rate, results). No examples = perfect score (1.0, []).
    """
    text = doc_path.read_text(encoding="utf-8", errors="replace")
    examples = extract_examples(text)

    if not examples:
        return 1.0, []

    results: list[ExampleResult] = []
    for idx, (lang, code) in enumerate(examples):
        passed, error = run_example(lang, code, timeout=timeout)
        results.append(ExampleResult(
            index=idx,
            lang=lang,
            code=code[:100],
            passed=passed,
            error=error,
        ))

    pass_count = sum(1 for r in results if r.passed)
    return round(pass_count / len(results), 4), results
