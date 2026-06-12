# Benchmark Methodology

This document describes how `doc-benchmark` evaluates documentation and other agent-facing context. The central measurement is comparative: hold the task and answer model fixed, then compare performance with and without a controlled context layer.

## What Can Be Benchmarked

The current implementation focuses on product documentation, but the benchmark shape is intentionally broader:

- **Documentation**: Context7, local Markdown, URL-backed docs, and curated golden question sets.
- **Skills and playbooks**: reusable instructions or procedures that change how an agent approaches a task.
- **Agent profiles**: model/provider selection, system prompts, role definitions, tool policies, retrieval settings, and other runtime context.
- **Executable task environments**: Terminal-Bench/Harbor tasks where the final score comes from tests, not judge prose.

For non-documentation context, treat the artifact as the `with_context` condition and compare it against the same model/task without that artifact. Keep the question set, task set, model, temperature, tool availability, and judge setup fixed unless the experiment is explicitly about one of those variables.

## End-to-End LLM Evaluation

The high-level pipeline is:

```text
Library registry / CLI input
    -> persona discovery or cached personas
    -> topic extraction from docs
    -> question generation or fixed golden questions
    -> answer generation with_docs and without_docs
    -> LLM judge scoring
    -> optional panel/RAGAS checks
    -> trust gate, reports, dashboards, baselines
```

Use `benchmark run` for registered libraries:

```bash
python cli.py benchmark run \
  --library onetbb \
  --model gpt-4o-mini \
  --judge-model claude-sonnet-4 \
  --judge-provider anthropic \
  --multi-run 3
```

Use `evaluate` for an ad hoc product:

```bash
python cli.py evaluate \
  --product oneDNN \
  --repo oneapi-src/oneDNN \
  --doc-source context7 \
  --context7-id intel/mkl-dnn
```

Outputs are written under `results/<library>/` or the requested `--output-dir`:

- `personas/<product>.json`: discovered or cached personas.
- `questions/<product>.json`: generated, golden, manual, or reused questions.
- `answers/<product>.json`: paired `with_docs` and `without_docs` answers plus model/token metadata.
- `eval/<product>.json`: judge scores, deltas, diagnosis, and run metadata.
- `reports/<product>.md`: human-readable summary with weak spots and trust checks.

## Model Roles

The benchmark separates model responsibilities because self-judging can inflate scores.

- **Generator model**: creates personas and questions. Default CLI value is `gpt-4o-mini` unless overridden.
- **Answer model**: answers every question in both conditions. `benchmark run` uses `--model`; standalone `answers generate` defaults to `gpt-4o`.
- **Judge model**: scores answers. It should differ from the answer model/provider for stronger evaluator independence.
- **Panel judges**: optional role-diverse judges for stricter review.

The CLI emits a warning when the normalized answer model and judge model match. Evaluation artifacts also store model/provider metadata and `question_set_hash` so later comparisons can prove they used the same question set.

Supported providers in the main pipeline include OpenAI, Anthropic, Google Vertex, OpenRouter, Amazon Bedrock, and OpenAI Codex where wired by the CLI.

## Question Sources

Questions can come from several sources:

- **Persona-based generated questions**: generated from discovered personas and extracted topics.
- **Chunk-grounded questions**: generated directly from documentation excerpts when a URL source is used; these carry `ground_truth_chunk`.
- **Golden questions**: curated regression sets such as `questions/onetbb_golden.json`, `questions/onedal_golden.json`, and `questions/onemkl_golden.json`.
- **Manual/custom questions**: passed through `--custom-questions`.
- **Reused questions**: loaded with `--questions-from` for fair multi-model comparisons.

Question records preserve source fields such as `source_type`, `question_source`, `persona`, `difficulty`, `topics`, `expected_topics`, and `ground_truth_chunk` when available.

## Question Types

Persona-based generation mixes these question families:

- **Conceptual**: what a feature is, why it exists, when to use it.
- **How-to**: installation, setup, configuration, and first working usage.
- **Troubleshooting**: errors, edge cases, common failure modes, and migration pitfalls.
- **Comparison**: differences between APIs, algorithms, modes, or competing approaches.
- **Performance**: expected speedups, limitations, overheads, and tuning trade-offs.

The prompt rejects broad "best practices" and generic programming questions because they are easy to answer without reading product docs and increase false positives.

## Difficulty Levels

The canonical difficulty labels are:

- **beginner**: installation, simple usage, terminology, basic examples.
- **intermediate**: integration, configuration, common patterns, API selection, troubleshooting.
- **advanced**: internals, performance tuning, architecture choices, edge cases, and low-level behavior.

Generated questions inherit difficulty from the persona skill level. The refiner normalizes legacy numeric difficulty values into these labels, removes trivial questions, deduplicates near matches, and can fill gaps against a target distribution. The default target distribution is balanced, while product config currently encodes `beginner: 2`, `intermediate: 3`, `advanced: 3` for a typical persona-sized set.

## Answer Generation

Each question receives two answers from the same answer model:

- **`with_docs`** retrieves documentation from the configured doc source, reranks the chunks, trims the context, and prompts the model to answer using only the provided documentation.
- **`without_docs`** uses the same question but no retrieved context, giving a baseline for what the model already knows.

Retrieval uses a single fixed semantic strategy. The current design decision is not to compare keyword, hybrid, or multiple `top_k` variants inside the same benchmark run. The primary comparison axis is `with_docs` vs `without_docs`.

When `--debug-retrieval` is enabled, answer artifacts include raw retrieval counts, reranked counts, scores, and fallback metadata. Token usage is accumulated for cost and latency analysis.

## Evaluation

The standard judge scores five dimensions from 0 to 100:

- **Correctness**: factual accuracy.
- **Completeness**: whether the answer covers the full question.
- **Specificity**: whether the answer is product-specific rather than generic.
- **Code quality**: whether included code is correct, runnable, and idiomatic.
- **Actionability**: whether the user can apply the answer immediately.

For chunk-grounded questions, the judge also scores **factual grounding** against the stored documentation excerpt. Python computes the grounded aggregate with extra weight on correctness and factual grounding.

The optional judge panel uses three roles:

- `technical_expert`: emphasizes correctness and technical depth.
- `developer_advocate`: emphasizes practical usefulness and actionability.
- `doc_reviewer`: emphasizes completeness and fidelity to context.

Panel aggregates are computed in Python from role-specific weights. The panel report includes mean score, standard deviation, agreement score, and disagreement flags.

RAGAS meta-evaluation can be run after answer generation to add faithfulness and answer-relevancy signals, especially for the `with_docs` condition.

## Trust And Reproducibility

Every serious run should answer "Can we trust this run?" before interpreting deltas. The trust gate checks:

- minimum evaluated question count,
- zero-score fraction,
- minimum `with_docs` average,
- average delta,
- score coefficient of variation,
- inter-rater agreement when panel data exists,
- retrieval hit rate,
- multi-run variance when `--multi-run N` is used.

For reproducibility:

- Prefer `--multi-run 3` or higher for stability-sensitive claims.
- Use `--questions-from` when comparing models so all models answer the same question set.
- Keep one fixed retrieval configuration per run.
- Preserve `question_set_hash`, model/provider metadata, and committed golden question sets.
- Save meaningful baselines with `python cli.py baseline save --from-eval ...`.

## Executable Agent Tasks

The `terminal-bench-tasks/` directory contains Harbor-compatible tasks for agent evaluation. A task gives the agent instructions and a Docker environment, then scores the result with automated tests and `/logs/verifier/reward.txt`.

This is the right workflow when the benchmark question is not "did the answer sound good?" but "did the agent produce working code?" Current oneTBB tasks cover sorting, streaming kernels, stencil, transpose, reductions, prefix scan, and flow graph pipelines.

These tasks can be used to evaluate:

- base agent vs context-augmented agent,
- base agent vs agent with a skill/playbook,
- different agent profiles on the same task set,
- documentation changes that should improve coding success rate.

Keep provenance and license notes in `terminal-bench-tasks/PROVENANCE.md`, update the coverage matrix, and verify oracle solutions offline with network disabled before relying on task scores.
