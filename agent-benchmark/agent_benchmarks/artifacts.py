# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Versioned, schema-validated I/O for produced artifacts.

The benchmark produces long-lived JSON artifact kinds: ``questions``,
``answers``, ``eval`` (LLM-judge scores), ``arms`` (treatment-arm comparisons),
``task_runs`` (executable task results), ``explore_runs`` (ExploreBench
localization results), ``novelty`` (what an artifact's content adds to one
model), ``guidance_reach`` (L1 reach probes) and ``repo_readiness`` (L0 claim
checks). This module stamps each with a ``schema_version`` and
validates it against the JSON Schema in ``agent_benchmarks/schemas/`` on save
and load, so fixtures and baselines stay forward-compatible and self-describing.
"""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

# kind -> current schema_version string (also the schema filename stem).
SCHEMA_VERSIONS: dict[str, str] = {
    "questions": "questions.v1",
    "answers": "answers.v1",
    "eval": "eval.v1",
    "arms": "arms.v1",
    "matrix_rollup": "matrix_rollup.v1",
    "plugin_delta": "plugin_delta.v1",
    "subject_scorecard": "subject_scorecard.v2",
    "novelty": "novelty.v1",
    "task_runs": "task_runs.v1",
    "explore_runs": "explore_runs.v1",
    "guidance_reach": "guidance_reach.v1",
    "repo_readiness": "repo_readiness.v1",
}

# kind -> superseded versions still accepted on *load*, newest first. A bump is additive by policy,
# so an older artifact is still a valid artifact and reading one must not fail; `stamp` always
# writes the current version, so nothing is written back at an old version.
SUPERSEDED_VERSIONS: dict[str, tuple[str, ...]] = {
    "subject_scorecard": ("subject_scorecard.v1",),
}


class ArtifactValidationError(ValueError):
    """Raised when an artifact does not conform to its schema."""


def _schema_path(kind: str, version: str | None = None) -> Path:
    if kind not in SCHEMA_VERSIONS:
        raise KeyError(f"Unknown artifact kind: {kind!r}. Known: {sorted(SCHEMA_VERSIONS)}")
    return SCHEMA_DIR / f"{version or SCHEMA_VERSIONS[kind]}.json"


def schema_version_for(kind: str, data: dict) -> str:
    """Which schema version ``data`` should be validated against.

    The current version, unless the payload declares a superseded one for this kind — an artifact
    written before a bump is still valid, so reading it must not fail. An unknown version string is
    *not* honoured: it falls through to the current schema, whose ``const`` then rejects it, which
    is how a typo or a future version stays an error instead of silently skipping validation.
    """
    declared = data.get("schema_version")
    if declared in SUPERSEDED_VERSIONS.get(kind, ()):
        return str(declared)
    return SCHEMA_VERSIONS[kind]


def validate_artifact(kind: str, data: dict) -> None:
    """Validate ``data`` against the schema for ``kind`` (raises on failure)."""
    from jsonschema import Draft202012Validator

    schema = json.loads(
        _schema_path(kind, schema_version_for(kind, data)).read_text(encoding="utf-8")
    )
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    if errors:
        details = "\n".join(
            f"  - {'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors
        )
        raise ArtifactValidationError(f"{kind} artifact validation failed:\n{details}")


def stamp(kind: str, data: dict) -> dict:
    """Return ``data`` with its ``schema_version`` set for ``kind``."""
    if kind not in SCHEMA_VERSIONS:
        raise KeyError(f"Unknown artifact kind: {kind!r}")
    data["schema_version"] = SCHEMA_VERSIONS[kind]
    return data


def save_artifact(kind: str, data: dict, path: Path, *, validate: bool = True) -> None:
    """Stamp, (optionally) validate, and write an artifact to ``path``.

    Operates on a shallow copy so the caller's dict is not mutated.
    """
    payload = dict(data)
    stamp(kind, payload)
    if validate:
        validate_artifact(kind, payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_artifact(kind: str, path: Path, *, validate: bool = True) -> dict:
    """Read and (optionally) validate an artifact from ``path``."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if validate:
        validate_artifact(kind, data)
    return data
