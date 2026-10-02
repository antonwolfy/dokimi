# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Text file I/O in the package names its encoding.

Without one, Python uses the locale's: cp1252 on most Windows machines, which
cannot write the emoji in our reports or read back the UTF-8 we write elsewhere.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "agent_benchmarks"


def _has_encoding(call: ast.Call, positional_slot: int) -> bool:
    return len(call.args) > positional_slot or any(k.arg == "encoding" for k in call.keywords)


def _is_binary_open(call: ast.Call) -> bool:
    mode = call.args[1] if len(call.args) > 1 else next(
        (k.value for k in call.keywords if k.arg == "mode"), None
    )
    return isinstance(mode, ast.Constant) and "b" in str(mode.value)


def _unencoded(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            if not _is_binary_open(node) and not _has_encoding(node, 3):
                yield node.lineno
        elif isinstance(func, ast.Attribute) and func.attr == "read_text":
            if not _has_encoding(node, 0):
                yield node.lineno
        elif isinstance(func, ast.Attribute) and func.attr == "write_text":
            if not _has_encoding(node, 1):
                yield node.lineno


def test_package_text_io_names_its_encoding():
    missing = [
        f"{path.relative_to(PACKAGE.parent).as_posix()}:{line}"
        for path in sorted(PACKAGE.rglob("*.py"))
        for line in _unencoded(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert not missing, "text I/O without encoding=: " + ", ".join(missing)


def test_checker_flags_what_it_should():
    flagged = list(_unencoded(ast.parse(
        "open(p)\nopen(p, 'w')\np.read_text()\np.write_text(s)\n"
        "open(p, 'rb')\nopen(p, encoding='utf-8')\np.read_text(encoding='utf-8')\n"
        "p.write_text(s, encoding='utf-8')\nwebbrowser.open(u)\n"
    )))
    assert flagged == [1, 2, 3, 4]
