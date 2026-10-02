# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Extract knowledge atoms — checkable statements with span provenance.

An atom is the unit of *measurement*: one statement the artifact asserts, phrased as a
question with an expected answer, so it can be asked of a model with and without the
artifact in context. Everything downstream (the paired 2×2, the five categories, the
retention oracle, the shortener) is defined per atom.

Two properties are enforced here rather than hoped for:

* **Provenance.** Every atom names the span ids that assert it. An atom with no span
  is dropped — it cannot be attributed, coloured, or protected, so it would only
  inflate counts.
* **Faithfulness, separately from recall.** :func:`verify_atoms` re-reads each atom
  against its own spans and labels it ``supported`` / ``distorted`` / ``unsupported``.
  That check says nothing about what the extractor *missed*; extractor recall is
  unmeasured and is open question O1.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .client import LLMClient
from .spans import Span

ATOM_KINDS = ("proposition", "edge", "motif", "contract", "example")
ATOM_TAGS = (
    "local", "public", "temporal", "version_bound", "negative_constraint",
    "rare_critical", "procedural", "routing", "evidence",
)

_EXTRACT_SYSTEM = (
    "You extract checkable knowledge from technical documents. You never invent facts "
    "that the text does not assert, and you never soften a claim the text makes."
)

_EXTRACT_PROMPT = """\
Below are numbered spans from one document. Extract the checkable knowledge each span
asserts, as JSON.

Rules:
- One atom = one statement that could be right or wrong. Split compound claims.
- Keep exact values, versions, flags, thresholds and negations verbatim. They are the
  point; a paraphrase that drops "not" or rounds a number is a wrong atom.
- `question` must be answerable without seeing this document, and must not mention it.
- `answer` is the shortest complete correct answer the span supports.
- `span_ids` lists every span that asserts the atom (usually one).
- Skip pure navigation, formatting and restated headings. Those are not knowledge.
- kind: one of {kinds}
- tags: any of {tags}

Return ONLY a JSON array:
[{{"statement": "...", "question": "...", "answer": "...", "kind": "proposition",
   "tags": ["version_bound"], "span_ids": ["s0007"]}}]

SPANS:
{spans}
"""

_VERIFY_PROMPT = """\
Does the source text below support the statement, exactly as stated?

STATEMENT: {statement}

SOURCE:
{source}

Answer with JSON only:
{{"verdict": "supported" | "distorted" | "unsupported", "why": "<one clause>"}}

- "supported": the source asserts it, with the same qualifiers, numbers and polarity.
- "distorted": the source says something close but the statement changes a qualifier,
  a number, a version, or the polarity.
- "unsupported": the source does not assert it at all.
"""


@dataclass
class Atom:
    """One checkable statement drawn from the artifact.

    Attributes:
        id: Stable ``a<hash>`` id derived from the statement, so re-running the
            extractor on unchanged text keeps atom ids comparable.
        statement: The claim, as the artifact makes it.
        question: A probe question answerable without the artifact.
        answer: The expected answer the artifact supports.
        kind: One of :data:`ATOM_KINDS`.
        tags: Any of :data:`ATOM_TAGS`.
        span_ids: Spans that assert this atom (never empty).
        faithfulness: ``supported`` / ``distorted`` / ``unsupported`` / ``unchecked``.
    """

    statement: str
    question: str
    answer: str
    kind: str = "proposition"
    tags: tuple[str, ...] = ()
    span_ids: tuple[str, ...] = ()
    faithfulness: str = "unchecked"
    id: str = ""
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            digest = hashlib.sha256(self.statement.strip().encode("utf-8")).hexdigest()[:10]
            self.id = f"a{digest}"

    @property
    def protected(self) -> bool:
        """True for atoms whose value is conditional on a failure."""
        return bool({"negative_constraint", "version_bound", "rare_critical"} & set(self.tags))

    def as_dict(self) -> dict:
        """Serializable form."""
        return {
            "id": self.id,
            "statement": self.statement,
            "question": self.question,
            "answer": self.answer,
            "kind": self.kind,
            "tags": list(self.tags),
            "span_ids": list(self.span_ids),
            "faithfulness": self.faithfulness,
            **({"meta": self.meta} if self.meta else {}),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Atom":
        """Rebuild an atom from :meth:`as_dict` output."""
        return cls(
            statement=data["statement"],
            question=data.get("question", ""),
            answer=data.get("answer", ""),
            kind=data.get("kind", "proposition"),
            tags=tuple(data.get("tags", ())),
            span_ids=tuple(data.get("span_ids", ())),
            faithfulness=data.get("faithfulness", "unchecked"),
            id=data.get("id", ""),
            meta=data.get("meta", {}),
        )


class ExtractionError(RuntimeError):
    """Every extraction batch failed, so there is nothing to measure."""


def render_spans(spans: list[Span]) -> str:
    """Render spans for the extractor prompt, ids included."""
    return "\n".join(f"[{span.id}] ({span.kind}) {span.text}" for span in spans)


def extract_atoms(
    spans: list[Span],
    *,
    client: LLMClient,
    batch_spans: int = 25,
    cap: int | None = None,
) -> list[Atom]:
    """Extract atoms from spans, batched, keeping only atoms with valid provenance.

    Args:
        spans: Spans from :func:`~agent_benchmarks.novelty.spans.segment`.
        client: Extractor client (must not be the judge — see :mod:`.measure`).
        batch_spans: Spans per extraction call. Batching is what keeps extraction
            affordable; too large and the model starts skipping spans.
        cap: Stop after this many atoms. Recorded in the artifact as the sampling
            rule, so a capped run is never quoted as a full sweep.

    Returns:
        Atoms in extraction order, de-duplicated by id.
    """
    valid_ids = {span.id for span in spans}
    seen: set[str] = set()
    atoms: list[Atom] = []
    failure: Exception | None = None
    for start in range(0, len(spans), batch_spans):
        if cap is not None and len(atoms) >= cap:
            break
        batch = spans[start:start + batch_spans]
        prompt = _EXTRACT_PROMPT.format(
            kinds=", ".join(ATOM_KINDS), tags=", ".join(ATOM_TAGS), spans=render_spans(batch)
        )
        try:
            rows = client.json_array(prompt, system=_EXTRACT_SYSTEM)
        except Exception as exc:
            # One unparseable batch must not lose the other batches; the artifact's
            # atom count and the span coverage both make the gap visible.
            failure = exc
            continue
        for row in rows:
            atom = _atom_from_row(row, valid_ids)
            if atom is None or atom.id in seen:
                continue
            seen.add(atom.id)
            atoms.append(atom)
            if cap is not None and len(atoms) >= cap:
                break
    if not atoms and failure is not None:
        raise ExtractionError(f"no atoms: every extraction call failed ({failure})") from failure
    return atoms


def _atom_from_row(row: object, valid_ids: set[str]) -> Atom | None:
    if not isinstance(row, dict):
        return None
    statement = str(row.get("statement") or "").strip()
    question = str(row.get("question") or "").strip()
    if not statement or not question:
        return None
    span_ids = tuple(str(s) for s in row.get("span_ids", ()) if str(s) in valid_ids)
    if not span_ids:
        # No provenance means the atom cannot be attributed to text, protected, or
        # coloured. Counting it would inflate every per-artifact number.
        return None
    kind = str(row.get("kind") or "proposition")
    tags = tuple(str(t) for t in row.get("tags", ()) if str(t) in ATOM_TAGS)
    return Atom(
        statement=statement,
        question=question,
        answer=str(row.get("answer") or "").strip(),
        kind=kind if kind in ATOM_KINDS else "proposition",
        tags=tags,
        span_ids=span_ids,
    )


def verify_atoms(
    atoms: list[Atom],
    spans: list[Span],
    *,
    client: LLMClient,
    max_atoms: int | None = None,
) -> dict[str, int]:
    """Label each atom's faithfulness against its own spans (in place).

    Returns a tally of the verdicts. This bounds *distortion*, not *omission*: an atom
    set can be fully ``supported`` and still miss half the document.
    """
    by_id = {span.id: span for span in spans}
    tally = {"supported": 0, "distorted": 0, "unsupported": 0, "unchecked": 0}
    for index, atom in enumerate(atoms):
        if max_atoms is not None and index >= max_atoms:
            tally["unchecked"] += 1
            continue
        source = "\n".join(by_id[s].text for s in atom.span_ids if s in by_id)
        try:
            verdict = str(client.json_object(
                _VERIFY_PROMPT.format(statement=atom.statement, source=source)
            ).get("verdict", "")).strip()
        except Exception:
            verdict = ""
        atom.faithfulness = verdict if verdict in tally and verdict != "unchecked" else "unchecked"
        tally[atom.faithfulness] += 1
    return tally


def save_atoms(
    atoms: list[Atom], spans: list[Span], path, *,
    extractor: str | None = None, cap: int | None = None,
) -> None:
    """Write atoms plus their spans as one JSON file (input to ``novelty probe``)."""
    from pathlib import Path

    payload = {
        "extractor": extractor,
        "cap": cap,
        "atoms": [atom.as_dict() for atom in atoms],
        "spans": [span.as_dict() for span in spans],
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_atoms(path) -> tuple[list[Atom], list[Span]]:
    """Read back what :func:`save_atoms` wrote."""
    from pathlib import Path

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    atoms = [Atom.from_dict(row) for row in data.get("atoms", [])]
    spans = [
        Span(
            id=row["id"], kind=row["kind"], text=row["text"], start=row["start"], end=row["end"],
            heading_path=tuple(row.get("heading_path", ())),
            protection=tuple(row.get("protection", ())),
            atom_ids=list(row.get("atom_ids", [])),
        )
        for row in data.get("spans", [])
    ]
    return atoms, spans
