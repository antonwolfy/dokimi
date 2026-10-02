# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Content novelty: what a context artifact *adds* to a specific model.

The arm comparison answers "does this artifact help?". This package answers the two
questions an author asks next — which parts help, and which parts is the model repeating
back — by extracting checkable atoms from the text, probing each one with and without the
artifact, and attributing the result back to the spans it came from.

See ``docs/skill-novelty.md`` for the concept and ``docs/skill-novelty-evidence.md`` for the
study behind the defaults and its open questions.
"""

from .analyze import AnalyzeConfig, AnalyzeResult, analyze, load_artifact_text
from .atoms import Atom, extract_atoms, verify_atoms
from .client import LLMClient, roll_up_cost
from .measure import MeasureResult, SelfJudgeError, atom_outcomes, run_measurement
from .needs import NeedGraph, build_need_graph
from .probes import Probe, build_probes
from .report import build_novelty_artifact, render_annotated_html, render_novelty_markdown
from .retention import RetentionOracle
from .spans import Span, segment, span_summary

__all__ = [
    "AnalyzeConfig",
    "AnalyzeResult",
    "Atom",
    "LLMClient",
    "MeasureResult",
    "NeedGraph",
    "Probe",
    "RetentionOracle",
    "SelfJudgeError",
    "Span",
    "analyze",
    "atom_outcomes",
    "build_need_graph",
    "build_novelty_artifact",
    "build_probes",
    "extract_atoms",
    "load_artifact_text",
    "render_annotated_html",
    "render_novelty_markdown",
    "roll_up_cost",
    "run_measurement",
    "segment",
    "span_summary",
    "verify_atoms",
]
