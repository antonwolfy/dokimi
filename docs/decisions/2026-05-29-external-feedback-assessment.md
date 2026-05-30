# Assessment of external review feedback + productization plan

**Status:** Implemented in PR #56 (as of 2026-05-29 this was *proposed*; the
P0–P2 items were subsequently implemented in the same PR). This is an evaluation
of an external code-review of the repository and the prioritized plan that was
acted on; the actionable items are mirrored in
[../../BACKLOG.md](../../BACKLOG.md) (#57).

**Date:** 2026-05-29

---

## 1. What this is

We received a detailed external review covering (a) reusable ecosystem /
integration candidates, (b) a hardening plan with missing-test analysis, and
(c) a roadmap + risk assessment. This document grades each claim against the
**actual current state of the repo**, discards what is stale or already done,
and turns the rest into a sequenced plan.

The review is high quality and mostly accurate. The two things to correct are:

- **Ragas is already integrated**, not a future candidate
  (`doc_benchmarks/eval/ragas_eval.py`, `doc_benchmarks/questions/ragas_seed.py`,
  pinned in `requirements.txt`). The opportunity is to *deepen* it, not adopt it.
- **HF Datasets** is already a transitive dependency (pulled in by Ragas) but is
  **not** used as an artifact transport — that recommendation stands.
- HTML dashboard and a CI/automation pipeline are already tracked
  (BACKLOG #30, #31).

Everything else in the review checks out (verified below).

---

## 2. Claim verification (evidence)

| Review claim | Verdict | Evidence |
|---|---|---|
| No LICENSE / SECURITY.md / CONTRIBUTING.md | **True** | None present at root. README §License: "does not yet ship an open-source license; currently maintained for internal Intel use." |
| No `pyproject.toml` / `setup.py`; install is ad hoc | **True (nuanced)** | No build metadata exists. A real `doc_benchmarks/` package already exists, so it's not *structureless* — only unpackaged. |
| `cli.py` is a ~1,700-line monolith | **True** | `cli.py` is 1,706 lines; covers benchmark run/batch, baselines, personas, questions, answers, judging, dashboard, arms. |
| `libraries.yaml` and `config/products.yaml` overlap → drift | **True** | Both encode product identity (repo, context7 id, description) for oneTBB/oneDAL/… `libraries.yaml` feeds the static track; `config/products.yaml` feeds the LLM track. |
| `_load_spec()` only does partial checks, not schema validation | **True** | `doc_benchmarks/runner/run.py:40-70` hand-checks a few keys; `benchmarks/spec.schema.json` exists but is never loaded at runtime. |
| `golden_manifest` declared but not enforced | **True** | `run.py:85` calls `discover_markdown(root / "docs")` directly; include/exclude/min_docs/max_docs are ignored. |
| `example_runner.py` runs fenced code on the host unsandboxed | **True** | `metrics/example_runner.py` runs python/bash/sh via `subprocess.run()` with only a timeout — no network/fs/cpu/mem isolation. Docstring claims "isolated" but it is not. |
| No output schemas / `schema_version` for artifacts | **True** | No `schema_version` anywhere; `questions/`, `answers/`, `eval/` JSON have no schema. |
| CI: only py3.11 tests + benchmark; no lint/type/schema | **True** | `.github/workflows/docs-quality.yml`: jobs are terminal-bench-verify(+oneapi), `test` (3.11 only), `benchmark`. No ruff/mypy/schema/matrix. |
| Stale PR template | **True** | `.github/pull_request_template.md` is the "Add tests for Phase 0-1" change description, not a generic template. |
| Quickstart references LangChain though it was dropped | **True** | `docs/quickstart.md` mentions langchain; LangChain was removed in PR #17 for LiteLLM (BACKLOG, `doc_benchmarks/llm.py`). |
| Dependencies not locked | **True** | `requirements.txt` uses unpinned ranges; no lockfile. |
| Markdown-only ingestion (Docling gap is real) | **True** | `ingest/loader.py` only `rglob("*.md")`. LLM track adds `url:`/`context7` sources but no PDF/Office/scan path. |
| Ragas is a future candidate | **FALSE — already integrated** | `eval/ragas_eval.py`, `questions/ragas_seed.py`, `ragas~=0.2.0` in `requirements.txt`, tests `test_eval_ragas.py` / `test_questions_ragas.py`. |
| HTML dashboard / CI pipeline are missing roadmap items | **Already tracked** | BACKLOG #30 (HTML dashboard), #31 (CI/Jenkins). |

---

## 3. Integration candidates — recommendation

| Candidate | Decision | Rationale |
|---|---|---|
| **HF Datasets (as artifact transport)** | **Adopt (P2)** | Dep already present transitively; use it to version/share `questions`/`answers`/`eval`/`arms` with dataset cards + revision pinning. Pairs with the output-schema work. |
| **Ragas** | **Deepen (P2)** | Already wired. Add grounding/citation metrics + confidence intervals *alongside* the existing judge, not replacing it. |
| **Docling** | **Adopt as optional ingestion (P2)** | Cleanest way to extend the markdown-only static track to PDF/Office/scans while preserving structure. Gate behind an `ocr`/`ingest` extra so the core loader stays light. |
| Unstructured / Tika / Tesseract | **Defer** | Only relevant if Docling proves insufficient. Pick one structured-ingestion stack (Docling) first; these are fallbacks. |
| DeepEval | **Skip for now** | Overlaps the existing judge-panel + Ragas; another abstraction to maintain for little marginal value. |
| Distilabel | **Defer** | Maintainer transition noted upstream; revisit when synthetic-set scaling is the bottleneck. |

Sequence: standardize artifacts (schemas) → export via HF Datasets → deepen
Ragas metrics → add Docling ingestion. Minimal disruption, earliest payoff.

---

## 4. Prioritized plan

### P0 — Trust & contracts (highest leverage, mostly low/medium effort)

1. **Licensing & distribution posture.** *Decision required (owner).* Either
   ship a proprietary/internal-use `LICENSE` notice matching the README, or
   pick an OSS license. Then add `SECURITY.md`, `CONTRIBUTING.md`, and issue
   templates. Blocks any external reuse.
2. **Runtime spec validation.** Load `benchmarks/spec.schema.json` and validate
   in `_load_spec()` with `jsonschema` (Draft 2020-12); surface human-readable
   errors; run in CI and CLI. Closes the spec/runtime gap — the review's #1
   engineering fix.
3. **`golden_manifest` enforcement.** Replace the hardcoded
   `discover_markdown(root / "docs")` with glob selection driven by
   `include`/`exclude`; fail when doc counts violate `min_docs`/`max_docs`.
4. **Sandbox example execution.** Stop running fenced snippets in-process on the
   host. Default to *no* host execution; offer a container-backed runner
   (`--network none`, read-only mounts, CPU/RAM/time limits) as opt-in. Critical
   before benchmarking any non-self-owned corpus.
5. **Docs drift + PR template.** Remove LangChain-era instructions from
   `docs/quickstart.md`; replace the PR template with a generic
   summary/risk/test checklist.

### P1 — Packaging & reproducibility

6. **`pyproject.toml`** with metadata, console entrypoint
   (`doc-benchmark = "doc_benchmarks.cli:main"`), and extras (`dev`, `ocr`,
   `mcp`, `embeddings`). Pin/lock deps (uv or pip-tools).
7. **Output schemas** (`schemas/questions.v1.json`, `answers.v1.json`,
   `eval.v1.json`, `arms.v1.json`) + `schema_version` fields; validate in
   save/load paths with fixture tests.
8. **Run manifest.** Emit `run_manifest.json` per artifact set: git SHA, prompt
   version, model/provider, doc-source hash, config hash, dependency lock.
9. **CI depth.** Add ruff, mypy/pyright, schema validation, a py3.11–3.13
   matrix, plus CLI-help and `pip install .` smoke jobs.

### P2 — Structure & breadth

10. **Split `cli.py`** into `doc_benchmarks/commands/{run,evaluate,arms,baseline,…}`
    behind argparse subparsers; keep a thin compatibility wrapper.
11. **Config unification.** One canonical registry (merge `libraries.yaml` +
    `config/products.yaml`) validated with dataclasses/Pydantic; record config
    version in outputs.
12. **HF Datasets export** of artifacts with dataset cards + revision pinning.
13. **Deepen Ragas:** grounding/citation metrics, sampled multi-judge checks,
    confidence intervals — added before any score becomes blocking.
14. **Docling optional ingestion** path for PDF/Office/scans.
15. **CODEOWNERS** boundaries for the three subsystems (static metrics, LLM eval,
    terminal-bench tasks); per-release fixture refresh + docs-drift checklist.

---

## 5. Missing tests (adopt the review's list)

Add, roughly in P0→P2 order:

- **CLI integration / exit codes** — subprocess tests for `run`, `compare`,
  `baseline save/list/compare`, `arms run`, and strict-gate failures.
- **Spec-manifest enforcement** — include/exclude glob selection and
  min/max doc-count violations.
- **Safe example execution** — assert network denial, timeout, read-only fs,
  language allow-list.
- **Artifact schema compatibility** — validate questions/answers/eval/arms JSON.
- **Orchestrator smoke** — offline, fixture-driven `evaluate` with mocked
  LLM/doc-source clients (`doc_benchmarks/orchestrator/pipeline.py`).
- **Deterministic ordering** — repeated concurrent answer/judge runs yield
  byte-stable output.
- **Optional-dependency degradation** — minimal env without
  sentence-transformers / mcp / ocr extras.
- **Packaging smoke** — venv + `pip install .` + `doc-benchmark --help` + core
  imports.

---

## 6. Risks (from the review, confirmed)

| Risk | Severity | Mitigation (maps to plan) |
|---|---|---|
| No clear license posture | High | P0-1 |
| Reproducibility drift in LLM evals | High | P1-6 (lock), P1-8 (manifest) |
| Unsafe example execution | High | P0-4 |
| Spec/runtime divergence | Med-high | P0-2, P0-3 |
| Documentation drift | Medium | P0-5 + docs-drift checklist (P2-15) |
| Maintenance breadth | Medium | P2-10, P2-15 (CODEOWNERS) |

---

## 7. Minimal viable enhancement set

If only six things ship, do these: P0-1 (license), P1-6 (`pyproject.toml` +
entrypoint), P0-2 + P0-3 (runtime spec validation + manifest enforcement), P1-8
(run manifest) + lock, P0-5 (docs cleanup), and the CLI/integration +
packaging smoke tests. That alone makes the repo materially easier to trust,
install, maintain, and reuse.
