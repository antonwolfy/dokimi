# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Repository sources: a working tree, or a commit in a cached clone.

A source spec is either a local path (``/src/oneDAL``), a local path pinned to
a revision (``/src/oneDAL@a492e703``), or a remote URL pinned to a revision
(``https://github.com/uxlfoundation/oneDAL@a492e703``). Remote sources are
cloned once, bare and blob-less, into a cache directory and reused; the
revision is fetched on demand. Both kinds are read through the same
:class:`RepoTree` interface, so manifest validation never needs a checkout.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Protocol

# A revision is a SHA, tag or single-segment branch, optionally with ^ / ~N
# suffixes. No "/" (so "user@host:path" URLs are not split) and no leading "-"
# (so a revision can never be read as a git option).
_REV_RE = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._^~-]*$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
_REMOTE_PREFIXES = ("https://", "ssh://", "file://", "git@")
_GIT_TIMEOUT_S = 1800


class SourceError(ValueError):
    """Raised for an unusable source spec or a git operation that failed."""


@dataclass(frozen=True)
class RepoSource:
    """A parsed source spec. ``rev`` is ``None`` for an unpinned working tree."""

    location: str
    rev: str | None
    remote: bool

    @classmethod
    def parse(cls, spec: str) -> RepoSource:
        spec = spec.strip()
        if not spec or spec.startswith("-"):
            raise SourceError(f"invalid repository source: {spec!r}")
        location, rev = spec, None
        head, sep, tail = spec.rpartition("@")
        if sep and head and _REV_RE.match(tail):
            location, rev = head, tail
        remote = location.startswith(_REMOTE_PREFIXES)
        if location.startswith("http://"):
            raise SourceError("plain http:// sources are refused; use https://")
        if remote and rev is None:
            raise SourceError(f"a remote source must be pinned to a revision: {spec}@<sha>")
        if not remote and not Path(location).is_dir():
            raise SourceError(f"local source is not a directory: {location}")
        return cls(location=location, rev=rev, remote=remote)

    def __str__(self) -> str:
        return self.location if self.rev is None else f"{self.location}@{self.rev}"


class RepoTree(Protocol):
    """Read-only view of one repository snapshot. Paths are POSIX, root-relative."""

    label: str

    def files(self) -> list[str]: ...

    def is_file(self, path: str) -> bool: ...

    def is_dir(self, path: str) -> bool: ...

    def read_text(self, path: str) -> str: ...


class WorkTree:
    """A directory on disk, read as it is (uncommitted changes included)."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.label = str(self.root)
        self._files: list[str] | None = None

    def _resolve(self, path: str) -> Path:
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root):
            raise SourceError(f"path escapes the repository: {path}")
        return target

    def files(self) -> list[str]:
        if self._files is None:
            out: list[str] = []
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames[:] = [d for d in dirnames if d != ".git"]
                rel = Path(dirpath).relative_to(self.root)
                out.extend((rel / name).as_posix() for name in filenames)
            self._files = sorted(p.removeprefix("./") for p in out)
        return self._files

    def is_file(self, path: str) -> bool:
        return self._resolve(path).is_file()

    def is_dir(self, path: str) -> bool:
        return self._resolve(path).is_dir()

    def read_text(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")


class GitTree:
    """One commit of a git repository, read with ``git ls-tree`` / ``git show``."""

    def __init__(self, git_dir: str | Path, sha: str, label: str | None = None):
        self.git_dir = Path(git_dir)
        self.sha = sha
        self.label = label or f"{self.git_dir}@{sha[:12]}"
        self._files: list[str] | None = None
        self._dirs: set[str] | None = None

    def files(self) -> list[str]:
        if self._files is None:
            out = _git(self.git_dir, "ls-tree", "-r", "-z", "--name-only", self.sha)
            self._files = sorted(p for p in out.split("\0") if p)
        return self._files

    def _dir_set(self) -> set[str]:
        if self._dirs is None:
            dirs: set[str] = set()
            for path in self.files():
                dirs.update(str(parent) for parent in PurePosixPath(path).parents)
            self._dirs = dirs
        return self._dirs

    def is_file(self, path: str) -> bool:
        return _norm(path) in set(self.files())

    def is_dir(self, path: str) -> bool:
        return _norm(path) in self._dir_set()

    def read_text(self, path: str) -> str:
        return _git(self.git_dir, "show", f"{self.sha}:{_norm(path)}")


def default_cache_dir() -> Path:
    """Where remote sources are cloned: ``$AGENT_BENCHMARK_REPO_CACHE`` or ~/.cache."""
    env = os.environ.get("AGENT_BENCHMARK_REPO_CACHE")
    return Path(env) if env else Path.home() / ".cache" / "agent-benchmark" / "repos"


def cache_path(url: str, cache_dir: Path) -> Path:
    """Stable per-URL clone directory: readable slug plus a hash of the full URL."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", url.rstrip("/").rsplit("/", 1)[-1]) or "repo"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return cache_dir / f"{slug.removesuffix('.git')}-{digest}.git"


def open_source(source: RepoSource, cache_dir: Path | None = None) -> RepoTree:
    """Return a readable tree for ``source``, cloning or fetching as needed."""
    if not source.remote:
        if source.rev is None:
            return WorkTree(source.location)
        # ls-tree lists paths relative to -C, git show reads them from the root.
        prefix = _git(Path(source.location), "rev-parse", "--show-prefix").strip()
        if prefix:
            raise SourceError(f"{source.location} is {prefix!r} inside a repository; give its root")
        sha = resolve_rev(Path(source.location), source.rev)
        return GitTree(Path(source.location), sha, label=f"{source.location}@{sha[:12]}")
    git_dir = ensure_clone(source.location, cache_dir or default_cache_dir())
    assert source.rev is not None  # parse() refuses unpinned remotes
    sha = ensure_rev(git_dir, source.rev)
    return GitTree(git_dir, sha, label=f"{source.location}@{sha[:12]}")


def base_opener(source: RepoSource, tree: RepoTree) -> Callable[[str], RepoTree] | None:
    """Open other commits of the repository behind ``tree``, such as task bases.

    ``None`` when ``tree`` has no git history to read them from. A remote
    clone fetches a missing commit; a local repository is only read.
    """
    if isinstance(tree, GitTree):
        git_dir = tree.git_dir
    elif isinstance(tree, WorkTree) and (tree.root / ".git").exists():
        git_dir = tree.root
    else:
        return None
    shallow = _git(git_dir, "rev-parse", "--is-shallow-repository").strip() == "true"

    def open_base(rev: str) -> RepoTree:
        try:
            sha = ensure_rev(git_dir, rev) if source.remote else resolve_rev(git_dir, rev)
        except SourceError as exc:
            if not shallow:
                raise
            raise SourceError(f"{exc}; the clone is shallow, so the base may only be missing: "
                              "fetch the full history (actions/checkout: fetch-depth: 0)") from exc
        return GitTree(git_dir, sha, label=f"{source.location}@{sha[:12]}")

    return open_base


def ensure_clone(url: str, cache_dir: Path) -> Path:
    """Clone ``url`` bare and blob-less into the cache once; return the git dir."""
    git_dir = cache_path(url, cache_dir)
    if (git_dir / "HEAD").is_file():
        return git_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = git_dir.with_name(git_dir.name + ".partial")
    if tmp.exists():
        shutil.rmtree(tmp)
    _git(None, "clone", "--bare", "--filter=blob:none", "--", url, str(tmp))
    tmp.rename(git_dir)
    return git_dir


def ensure_rev(git_dir: Path, rev: str) -> str:
    """Resolve ``rev`` in the cached clone; a branch or tag is re-fetched on every call."""
    base = re.split(r"[\^~]", rev, maxsplit=1)[0]
    if _SHA_RE.match(base):
        try:
            return resolve_rev(git_dir, rev)
        except SourceError:
            pass
        try:
            _git(git_dir, "fetch", "--filter=blob:none", "origin", "--", base)
            return resolve_rev(git_dir, rev)
        except SourceError:
            pass
    _fetch_refs(git_dir)
    try:
        return resolve_rev(git_dir, rev)
    except SourceError as exc:
        short = _SHA_RE.match(base) and len(base) < 40
        hint = "; a short SHA on no branch or tag cannot be fetched, give the full SHA" if short else ""
        raise SourceError(f"revision not found in origin: {rev}{hint}") from exc


def _fetch_refs(git_dir: Path) -> None:
    _git(git_dir, "fetch", "--filter=blob:none", "origin",
         "+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*")


def resolve_rev(git_dir: Path, rev: str) -> str:
    """Full commit SHA for ``rev``; raises :class:`SourceError` if unknown."""
    if not _REV_RE.match(rev):
        raise SourceError(f"invalid revision: {rev!r}")
    return _git(git_dir, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}").strip()


def _norm(path: str) -> str:
    return PurePosixPath(path).as_posix().removeprefix("./").rstrip("/") or "."


def _git(git_dir: Path | None, *args: str) -> str:
    cmd = ["git"] + (["-C", str(git_dir)] if git_dir is not None else []) + list(args)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env,
                              timeout=_GIT_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceError(f"git {args[0]} failed: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.strip().splitlines()[-1:] or [f"exit {proc.returncode}"]
        raise SourceError(f"git {args[0]} failed: {detail[0]}")
    return proc.stdout
