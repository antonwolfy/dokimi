#!/usr/bin/env python3
"""Verifier for sklearnex-classification."""
import ast
import re
import subprocess
from pathlib import Path

SOLUTION = Path("/app/solution.py")
REFERENCE = Path("/app/reference.py")
# Per-subprocess budget. Two subprocesses (reference + solution) run in
# test_accuracy_matches_reference, so keep 2*TIMEOUT_SEC under the verifier
# timeout in task.toml to avoid harness-level termination.
TIMEOUT_SEC = 45.0
ACC_TOL = 0.02


def _run(script):
    result = subprocess.run(
        ["python3", str(script)], capture_output=True, text=True, timeout=TIMEOUT_SEC
    )
    assert result.returncode == 0, (
        f"{script} exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "VALID" in result.stdout, f"expected VALID in stdout, got {result.stdout!r}"
    return result.stdout


def _acc(text):
    m = re.search(r"acc=([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", text)
    assert m, f"no acc=<value> found in {text!r}"
    return float(m.group(1))


def test_files_exist():
    assert SOLUTION.exists(), f"{SOLUTION} not found; create the sklearnex solution"
    assert REFERENCE.exists(), f"{REFERENCE} not found; stock reference is required"


def _calls_patch_sklearn(tree):
    """True if the AST contains an actual call to patch_sklearn(...).

    A substring search is bypassable here because the reference is stock
    scikit-learn: a plain-sklearn submission that merely mentions
    ``patch_sklearn`` in a comment or string would pass both the marker check
    and the accuracy check. Parsing the AST ignores comments/strings and
    requires the call to really execute. Handles both
    ``from sklearnex import patch_sklearn; patch_sklearn()`` and
    ``import sklearnex; sklearnex.patch_sklearn()`` forms.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "patch_sklearn":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "patch_sklearn":
            return True
    return False


def test_solution_calls_patch_sklearn():
    tree = ast.parse(SOLUTION.read_text(errors="replace"), filename=str(SOLUTION))
    assert _calls_patch_sklearn(tree), (
        f"{SOLUTION} must actually call sklearnex.patch_sklearn(); a plain "
        "scikit-learn solution (even one mentioning sklearnex in a comment) "
        "does not satisfy the task"
    )


def test_accuracy_matches_reference():
    ref_acc = _acc(_run(REFERENCE))
    sol_acc = _acc(_run(SOLUTION))
    assert sol_acc >= 0.60, f"accuracy {sol_acc} unexpectedly low"
    assert abs(sol_acc - ref_acc) <= ACC_TOL, (
        f"sklearnex accuracy {sol_acc} differs from stock reference {ref_acc} "
        f"by more than {ACC_TOL}"
    )
