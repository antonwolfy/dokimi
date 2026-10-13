# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MkDocs hook: point links that leave ``docs/`` at the file on GitHub.

The pages link into the source tree with relative paths (``../dokimi/eval/judge.py``,
``../../README.md``), which resolve when the Markdown is read on GitHub. The site
only contains ``docs/``, so those links would 404 there; this rewrites them to
``<repo_url>/blob/main/<path>`` (``tree`` for directories) before the page is
rendered. Links inside ``docs/`` and absolute URLs are left alone.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

# Inline links `[text](target)` and reference definitions `[id]: target`.
_INLINE = re.compile(r"(\]\()([^)\s]+)(\))")
_REFDEF = re.compile(r"^(\s*\[[^\]]+\]:\s*)(\S+)", re.MULTILINE)
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def on_page_markdown(markdown, page, config, files):
    docs_dir = Path(config["docs_dir"]).resolve()
    repo_root = Path(config["config_file_path"]).resolve().parents[1]
    base = config["repo_url"].rstrip("/")
    page_dir = posixpath.dirname(page.file.src_uri)

    def rewrite(target: str) -> str:
        if target.startswith(("#", "/")) or _SCHEME.match(target):
            return target
        path, sep, frag = target.partition("#")
        resolved = (docs_dir / page_dir / path).resolve()
        if resolved.is_relative_to(docs_dir):
            return target
        rel = resolved.relative_to(repo_root).as_posix()
        kind = "tree" if resolved.is_dir() else "blob"
        return f"{base}/{kind}/main/{rel}{sep}{frag}"

    markdown = _INLINE.sub(lambda m: m[1] + rewrite(m[2]) + m[3], markdown)
    return _REFDEF.sub(lambda m: m[1] + rewrite(m[2]), markdown)
