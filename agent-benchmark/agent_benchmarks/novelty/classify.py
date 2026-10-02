# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Assign each atom a content category, and find the atoms that fight each other.

The categories are the product of two axes — *did the model already have it* (measured)
and *does the artifact's own task need it* (judged) — plus a conflict flag:

============= ============== =================
              needed         not needed
============= ============== =================
new to model  novel_useful   novel_inert
already known known_useful   known_inert
============= ============== =================

with ``scaffolding`` for text that is structure rather than knowledge, and
``harmful_conflicting`` for atoms that contradict another atom or the artifact itself.
That last one is the only category which can make an artifact worse than nothing, so it
is reported first regardless of size.

The known/new axis comes from the measurement, never from asking the model whether it
knew something. The needed/not-needed axis is judged, and it is the axis that moved: an
independent reviewer agreed with 71.6% of assignments in the study, with the
disagreements concentrated on useful-vs-inert (±3 points) and known-vs-novel (±2).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .atoms import Atom
from .client import LLMClient

CATEGORIES = (
    "scaffolding",
    "novel_useful",
    "known_useful",
    "novel_inert",
    "known_inert",
    "harmful_conflicting",
)

_VALUE_PROMPT = """\
For each numbered statement, judge how it functions for someone doing this task:

TASK: {task}

Return ONLY a JSON array, one object per statement, same order:
[{{"n": 1, "needed": true, "scaffolding": false}}]

- "needed": acting on this task can go wrong, or be much slower, without knowing it.
- "scaffolding": it is structure, navigation, restated headings, or workflow framing
  rather than knowledge that could be right or wrong.

STATEMENTS:
{statements}
"""

_CONFLICT_PROMPT = """\
Find pairs of statements below that cannot both be true, or that give incompatible
instructions for the same situation. Ignore pairs that merely differ in detail.

Return ONLY JSON: {{"conflicts": [{{"a": 3, "b": 17, "why": "<one clause>"}}]}}

STATEMENTS:
{statements}
"""


@dataclass
class AtomVerdict:
    """The judged half of an atom's classification."""

    atom_id: str
    needed: bool
    scaffolding: bool
    conflict: bool = False
    conflict_why: str = ""

    def category(self, outcome: str | None) -> str:
        """Combine the judged axes with the measured outcome into one label.

        ``outcome`` is the paired probe result. When it is missing (an atom that was not
        probed, because probing is sampled) the atom is labelled on the judged axes
        alone and counted as ``novel_*``: the direction that does not silently claim the
        model already knew something nobody asked it.
        """
        if self.conflict:
            return "harmful_conflicting"
        if self.scaffolding:
            return "scaffolding"
        known = outcome == "redundant" or outcome == "degraded"
        if self.needed:
            return "known_useful" if known else "novel_useful"
        return "known_inert" if known else "novel_inert"

    def as_dict(self) -> dict:
        """Serializable form."""
        return {
            "atom_id": self.atom_id,
            "needed": self.needed,
            "scaffolding": self.scaffolding,
            "conflict": self.conflict,
            "conflict_why": self.conflict_why,
        }


def judge_value(
    atoms: list[Atom], *, client: LLMClient, task: str, batch: int = 25
) -> dict[str, AtomVerdict]:
    """Judge need and scaffolding per atom.

    ``task`` must come from outside the artifact body — the artifact's name and
    description, or a need graph built from them. Letting the body state the task is what
    allows an artifact to define its own relevance and score itself useful by
    construction.
    """
    verdicts: dict[str, AtomVerdict] = {}
    for start in range(0, len(atoms), batch):
        chunk = atoms[start:start + batch]
        numbered = "\n".join(f"{i + 1}. {a.statement}" for i, a in enumerate(chunk))
        try:
            rows = client.json_array(_VALUE_PROMPT.format(task=task, statements=numbered))
        except Exception:
            rows = []
        by_index = {
            int(row["n"]): row for row in rows
            if isinstance(row, dict) and str(row.get("n", "")).isdigit()
        }
        for index, atom in enumerate(chunk, start=1):
            row = by_index.get(index, {})
            verdicts[atom.id] = AtomVerdict(
                atom_id=atom.id,
                needed=bool(row.get("needed", False)),
                scaffolding=bool(row.get("scaffolding", False)),
            )
    return verdicts


def detect_conflicts(
    atoms: list[Atom], *, client: LLMClient, batch: int = 40
) -> list[dict]:
    """Find mutually incompatible atoms.

    Scoped to *internal* consistency: a conflict says "these two disagree", not "this one
    is wrong". Deciding which side is right needs a primary source, which this layer
    deliberately does not claim to consult.
    """
    conflicts: list[dict] = []
    for start in range(0, len(atoms), batch):
        chunk = atoms[start:start + batch]
        numbered = "\n".join(f"{i + 1}. {a.statement}" for i, a in enumerate(chunk))
        try:
            rows = client.json_object(_CONFLICT_PROMPT.format(statements=numbered))
        except Exception:
            continue
        for row in rows.get("conflicts", []) or []:
            try:
                a_index, b_index = int(row["a"]) - 1, int(row["b"]) - 1
            except (KeyError, TypeError, ValueError):
                continue
            if not (0 <= a_index < len(chunk) and 0 <= b_index < len(chunk)):
                continue
            conflicts.append({
                "a": chunk[a_index].id,
                "b": chunk[b_index].id,
                "why": str(row.get("why", "")).strip(),
            })
    return conflicts


def apply_conflicts(verdicts: dict[str, AtomVerdict], conflicts: list[dict]) -> None:
    """Mark both sides of every conflict (in place)."""
    for conflict in conflicts:
        for side in ("a", "b"):
            verdict = verdicts.get(conflict.get(side, ""))
            if verdict is not None:
                verdict.conflict = True
                verdict.conflict_why = conflict.get("why", "")


def categorize(
    atoms: list[Atom],
    verdicts: dict[str, AtomVerdict],
    outcomes: dict[str, str],
) -> dict[str, str]:
    """Category per atom id."""
    return {
        atom.id: verdicts[atom.id].category(outcomes.get(atom.id))
        for atom in atoms
        if atom.id in verdicts
    }


def category_counts(categories: dict[str, str]) -> dict[str, int]:
    """Counts per category, all six keys always present so a zero is visible."""
    counted = Counter(categories.values())
    return {name: int(counted.get(name, 0)) for name in CATEGORIES}
