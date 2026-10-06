# Benchmarking and comparison guide

This guide describes how to run the supported benchmark flows and how to compare
results. Run all commands from `agent-benchmark/`.

## Comparison modes

`agent-benchmark` has four practical comparison modes:

- **Static snapshot comparison**: compare documentation quality snapshots from
  `python cli.py run`.
- **LLM context comparison**: compare one answer model's context-arm and
  baseline answers. Persisted JSON keeps the legacy `with_docs` and
  `without_docs` keys for compatibility.
- **Multi-model comparison**: run multiple answer models on the same question
  set and compare their evaluated JSON outputs.
- **Treatment-arm comparison**: compare `baseline` against docs, MCP, skills,
  profiles, or agentic tool-use arms.

Keep only one axis variable at a time. For example, a model comparison should
reuse the same questions, doc source, judge setup, and retrieval configuration.

## Static documentation benchmark

Use the static benchmark when the question is "did this documentation snapshot
get structurally better or worse?"

```bash
python cli.py run \
  --root . \
  --spec benchmarks/spec.v1.yaml \
  --out-json baselines/current.json \
  --out-md reports/current.md
```

The JSON snapshot contains summary metrics such as coverage, freshness,
readability, and example pass rate. The Markdown report is a human-readable
view of the same run.

Compare a candidate snapshot with a saved baseline. The repository ships no
committed baseline — the base is a snapshot you generated yourself and kept,
so keep the first `baselines/current.json` you are happy with:

```bash
cp baselines/current.json baselines/baseline.json   # once, after a clean run

python cli.py compare \
  --base baselines/baseline.json \
  --candidate baselines/current.json \
  --spec benchmarks/spec.v1.yaml \
  --out-json reports/compare.json \
  --out-md reports/compare.md
```

The compare command computes candidate-minus-baseline deltas and, when `--spec`
is passed, applies configured regression thresholds. Both snapshots must come
from the same docs corpus definition, otherwise the deltas are meaningless.

Equivalent Make targets are available from the repository root; `BASE` defaults
to `baselines/baseline.json`:

```bash
make benchmark-run
make benchmark-compare                       # uses baselines/baseline.json
make benchmark-compare BASE=path/to/base.json
```

## LLM context benchmark

Use the LLM benchmark when the question is "does documentation or another
context artifact improve answers?"

For registered libraries, prefer the one-command wrapper:

```bash
python cli.py benchmark run \
  --library onetbb \
  --model gpt-5.5 \
  --provider openai \
  --judge-model claude-sonnet-4-5-20250929 \
  --judge-provider anthropic \
  --output-dir results/onetbb_gpt55
```

The run writes:

- `results/onetbb_gpt55/personas/onetbb.json`
- `results/onetbb_gpt55/questions/onetbb.json`
- `results/onetbb_gpt55/answers/onetbb.json`
- `results/onetbb_gpt55/eval/onetbb.json`
- `results/onetbb_gpt55/reports/onetbb.md`

The comparison inside one run is always:

```text
delta = context-arm score - baseline score
```

Positive delta means the context helped on that judged question. Negative delta
means either retrieval hurt the answer, the model already knew enough without
context, or the retrieved chunks were irrelevant.

For stability-sensitive claims, run the same configuration several times:

```bash
python cli.py benchmark run \
  --library onetbb \
  --model gpt-5.5 \
  --judge-model claude-sonnet-4-5-20250929 \
  --judge-provider anthropic \
  --multi-run 3 \
  --output-dir results/onetbb_gpt55
```

Multi-run mode creates numbered run directories and prints the mean and
standard deviation of the context-arm average.

## Fair multi-model comparison

A fair model comparison must use the same questions for every model. First
create or choose a seed run:

```bash
python cli.py benchmark run \
  --library onedal \
  --model gpt-5.5 \
  --judge-model claude-sonnet-4-5-20250929 \
  --judge-provider anthropic \
  --output-dir results/onedal_seed
```

Then reuse that question set for each model:

```bash
python cli.py benchmark run \
  --library onedal \
  --questions-from results/onedal_seed \
  --model gpt-5.1 \
  --provider openai \
  --judge-model claude-sonnet-4-5-20250929 \
  --judge-provider anthropic \
  --output-dir results/onedal_gpt51

python cli.py benchmark run \
  --library onedal \
  --questions-from results/onedal_seed \
  --model anthropic/claude-sonnet-4-6 \
  --provider openrouter \
  --judge-model claude-sonnet-4-5-20250929 \
  --judge-provider anthropic \
  --output-dir results/onedal_sonnet46
```

Interpret model comparisons using two separate signals:

- **Absolute quality**: the context-arm average from each run.
- **Context benefit**: the average `delta` from each run.

Do not rank models by delta alone. A strong model can have a small delta because
its baseline score is already high.

Generate a cross-run dashboard when you have multiple eval files:

```bash
python cli.py dashboard generate \
  --results-dir results \
  --output-dir reports
```

The dashboard reads evaluation artifacts and writes `reports/DASHBOARD.md` and
`reports/dashboard.json`.

## Standalone pipeline commands

Use the lower-level commands when you need explicit control over each artifact:

```bash
python cli.py answers generate \
  --product oneTBB \
  --questions <content-checkout>/questions/onetbb_golden.json \
  --output results/onetbb_golden/answers/onetbb.json \
  --model gpt-5.5 \
  --provider openai \
  --debug-retrieval

python cli.py eval score \
  --product oneTBB \
  --answers results/onetbb_golden/answers/onetbb.json \
  --output results/onetbb_golden/eval/onetbb.json \
  --judge-model claude-sonnet-4-5-20250929 \
  --judge-provider anthropic

python cli.py report eval \
  --product oneTBB \
  --eval results/onetbb_golden/eval/onetbb.json \
  --out results/onetbb_golden/reports/oneTBB_full.md
```

Use `report generate` instead of `report eval` when you also want the questions
file included in the report generator:

```bash
python cli.py report generate \
  --product oneTBB \
  --eval results/onetbb_golden/eval/onetbb.json \
  --questions <content-checkout>/questions/onetbb_golden.json \
  --output results/onetbb_golden/reports/oneTBB.md \
  --format markdown
```

## Treatment-arm comparison

Use treatment arms when comparing context artifacts rather than models:

```bash
python cli.py arms run \
  --product oneTBB \
  --questions <content-checkout>/questions/onetbb_golden.json \
  --arms "baseline,docs,skill:<content-checkout>/skills/onetbb-quickstart" \
  --judge \
  --out-json results/arms/onetbb_skill.json \
  --out-md results/arms/onetbb_skill.md
```

The `baseline` arm is the control. Every other arm is compared against it. Keep
the answer model and judge fixed when comparing arms.

### Reading the significance tables

Arms are compared **paired per question** against the one shared `baseline`
sample: a question contributes a pair only when both arms produced an aggregate,
so the delta varies by treatment rather than by a re-drawn control.

Because one run tests several arms at once, p-values are corrected for
multiplicity — with several arms, the chance that at least one clears 0.05 by
luck is well above 0.05. `--stats-correction` picks the method:

```bash
python cli.py arms run ... --stats-correction bh
```

- `holm` (default) — Holm-Bonferroni, controls the family-wise error rate. The
  honest choice with one baseline and a handful of arms.
- `bh` — Benjamini-Hochberg, controls the false discovery rate. Use it when
  screening many arms and some false positives are acceptable.

Arm contrasts and factorial-interaction contrasts are corrected as **separate
families** — pooling them would inflate the multiplier on both — and each row
records its `correction_family`, `family_size`, and `family_tested`.

The **Sig.** column follows the *adjusted* p-value, not the raw one. Three
values are possible:

| Sig. | Meaning |
|---|---|
| `yes` | adjusted p < 0.05 **and** Wilcoxon < 0.05 when it could be computed |
| `no` | the tests ran and did not clear 0.05 |
| `—` | no test could run — fewer than 6 complete pairs, or the deltas are constant (a degenerate sample, where Cohen's d_z is *unbounded* rather than negligible) |

A `—` is not a null result. Cohen's d_z and the p columns render `—` in the same
situation rather than printing `0.00`, which would read as a measured no-effect.

The 95% CI is a Student-t interval on the paired deltas, so it excludes zero
exactly when the t-test rejects; `ci_method` records which estimator produced it
(`student_t`, `percentile_bootstrap`, or `degenerate`).

The judged artifact carries the whole block at
`summary.per_arm.<arm>.significance`, so the table above is renderable from the
JSON alone.

When arm names form a `a`, `b`, `a+b` triple (see `CombinedTreatment`), the
artifact also gets `summary.interactions`: the contrast
`AB − A − B + baseline` computed per question against one shared baseline, which
is what tells you whether combining two treatments beats the sum of their
separate effects. Running the arms separately and subtracting run averages does
not answer that question — the baselines drift between runs.

Everything above assumes the judge's continuous 0–100 score. The
execution-verified task track (`cli.py tasks run`) has a binary outcome per task
and uses McNemar's exact test instead — see
[coding-harnesses.md](coding-harnesses.md).

## Multi-model comparison

Use `report model-compare` to compare judged treatment-arm JSON files from
multiple models.

The intended input is one judged arms JSON file per model for regular questions
and/or golden questions. The report extracts the `baseline_arm` score as the
baseline and the treatment arm as the context arm, then computes:

- overall context-arm, baseline, and delta per run,
- statistical significance of context-arm minus baseline (paired t-test,
  Wilcoxon signed-rank, Cohen's d_z), corrected across the compared runs \u2014
  every run tests the same "did the treatment help?" question, so they form one
  family; `--stats-correction holm|bh` selects the method and the table shows
  the raw p alongside the adjusted one. scipy is a hard dependency, so these are
  always computed; they report `None` only when a run has fewer than
  `eval.stats.MIN_PAIRS_FOR_TEST` (6) complete pairs or the deltas are constant,
- difficulty breakdown on common question IDs,
- head-to-head winners on common question IDs,
- ranking by absolute context-arm score and by delta.

**All summary, significance, difficulty, and head-to-head metrics use only the
common question set** (intersection of question IDs across all runs).

```bash
python cli.py report model-compare \
  --regular-runs results/arms/dpnp_regular_sonnet46.json results/arms/dpnp_regular_opus48.json \
  --golden-runs  results/arms/dpnp_golden_sonnet46.json  results/arms/dpnp_golden_opus48.json \
  --run-ids sonnet46,opus48 \
  --out results/dpnp_compare.md
```

Regular and golden options may be used independently:

```bash
# Regular questions only
python cli.py report model-compare \
  --regular-runs results/arms/dpnp_regular_sonnet46.json results/arms/dpnp_regular_opus48.json \
  --run-ids sonnet46,opus48 \
  --out results/dpnp_regular_compare.md

# Golden questions only
python cli.py report model-compare \
  --golden-runs results/arms/dpnp_golden_sonnet46.json results/arms/dpnp_golden_opus48.json \
  --run-ids sonnet46,opus48 \
  --out results/dpnp_golden_compare.md
```

When a run contains more than one non-baseline arm, specify which one to score:

```bash
python cli.py report model-compare \
  --regular-runs run_a.json run_b.json \
  --run-ids a,b \
  --treatment-arm with-skill \
  --out compare.md
```

Consistency is validated before the report is written:

- Different `baseline_arm` values across runs in the same group abort with an
  error.
- **Different treatment arms** across runs abort with an error: each run's delta
  would measure a different treatment (one run's `profile:` arm beside another's
  `skill:` arm is confounded, not a model comparison). Pin the shared arm with
  `--treatment-arm` to override — it makes the choice explicit, and a run missing
  that arm then fails on its own.
- **One arm name carrying two different prompt digests** aborts with an error. A
  `profile:` arm is named after the profile's frontmatter `id`, so editing a
  profile in place leaves old and new cells sharing a name while measuring
  different prompts; pooling them averages two treatments. Artifacts written
  before provenance stamping carry no digest and are not affected.
- Diverging `question_set_hash` values (when present) produce a warning on
  stderr.
- Runs that share the same model and provider produce a warning (likely
  duplicate rather than a real comparison).

The report names the arm it scored rather than calling everything "Context arm":
"Models Compared" gains a **Treatment arm** column (per run, or `— (baseline
only)`), and the summary, ranking, and benefit headers read the arm name — e.g.
`### By absolute quality (profile:concise_expert)`. The generic label survives only
when the runs disagree or no arm was scored. The name is taken from the extracted
score records, not the artifact header, so the label cannot disagree with the
numbers beside it.

For programmatic use, import from the package directly:

```python
from agent_benchmarks.report.model_compare import (
    check_run_consistency,
    generate_combined_report,
    load_run,
    non_baseline_arms,   # the arm names in one artifact other than its baseline
    prompt_digests,      # the profile_prompt_sha256 values stamped for one arm
)
```

## Caching

Two independent caches sit behind the LLM chokepoint
(`agent_benchmarks/caching.py`). Both are about cost, not about results: the text
the model sees is byte-identical whether they are on or off.

### Provider prompt caching

Providers charge a fraction of the input price for a request prefix they have
already seen. Anthropic-family models need an explicit breakpoint
(`cache_control`); OpenAI and Gemini cache long prefixes on their own.

Two conditions must hold, and the second used to fail silently here:

1. The breakpoint has to be set — done automatically, on prefixes of at least
   12000 characters (`MIN_CACHEABLE_PREFIX_CHARS`). Below the provider's minimum
   the prefix is ignored and the write surcharge is pure loss; the minimum is
   1024 tokens for most Anthropic models and 2048 for the small ones, so at ~4
   characters per token 12000 is the first round figure that clears the higher
   floor with margin.
2. The reused text has to be an actual **prefix**. The answer prompt now puts
   the injected context *before* the question for exactly this reason. Earlier
   versions asked the question first, so a 12k-character skill document could
   never be a reusable prefix and `cache_hit_ratio` was always 0.0%.

   **This reorder changes model output.** Scores from runs made before it are
   not directly comparable with scores made after.

Only *question-independent* context is offered for caching. A skill body is the
same for every question (`context_is_static=True`); `docs` retrieval is reranked
per query, so annotating it would pay the write surcharge on every call and never
hit. A combined arm is cacheable only when every context-bearing part is.

The judge rubric is deliberately not cached: at ~1–2k characters it is far below
the provider minimum.

`AGENT_BENCHMARK_PROMPT_CACHE=0` turns the breakpoints off (default: on). The
`Cache hit` column in the arms report reads `cache_hit_ratio` from
`cost_summary`, which is `cache_read_tokens / prompt_tokens` as the provider
reported them — so the column is now a real measurement rather than a constant
zero.

### Response caching

Off unless `AGENT_BENCHMARK_RESPONSE_CACHE` names a directory:

```bash
AGENT_BENCHMARK_RESPONSE_CACHE=.cache/responses python cli.py arms run ...
```

A byte-identical request (same model, message text, streaming flag, and
`max_tokens`) replays the stored completion instead of calling the provider. It
pays off mainly for the `baseline` arm, which is identical across treatment runs,
and for re-running a pipeline after changing only the reporting code.

The key is computed over the message **text**, not the request structure, which
is what keeps the two caches independent: a prompt-cache breakpoint splits one
string into two `text` blocks without changing a character of what the model
reads, so hashing the raw structure would make `AGENT_BENCHMARK_PROMPT_CACHE=0`
discard every entry already paid for. `max_tokens` *is* in the key — a truncated
completion is a different answer.

`AGENT_BENCHMARK_RESPONSE_CACHE` accepts the same off values as the prompt-cache
switch (`0`, `false`, `no`, `off`, empty), so disabling one the way you disable
the other does not create a cache directory named `0`. Pointing it at an existing
*file* is a configuration error and raises, rather than presenting as a cache
that never hits.

A replayed entry reports the **stored** usage record — tokens, cost and latency
as measured when the call was really made, not `$0`/`0s`, so cost stays
comparable across runs. The flip side: latency from a cached run is a recording,
not a measurement. That is why this cache is opt-in, and why it should stay off
for any run whose latency numbers you intend to quote.

## Baselines

Save meaningful eval outputs as named baselines:

```bash
python cli.py baseline save \
  --from-eval results/onetbb_gpt55/eval/onetbb.json \
  --name onetbb-gpt55-docs
```

Compare a future eval against a saved baseline:

```bash
python cli.py baseline compare \
  --baseline onetbb-gpt55-docs \
  --eval results/onetbb_candidate/eval/onetbb.json
```

Use baselines for release-to-release tracking. Use `--questions-from` for
model-to-model fairness.

## What to commit

Commit curated *inputs* under `data/` when the framework itself needs them:

- `data/skills/fastcontext/SKILL.md`
- `data/agent_profiles/*.md`
- `data/explore_tasks/*.yaml`

Question sets and product skills are evaluation content: commit them to the
content repository and pass them in with `--questions` / `--questions-root` and
`skill:<path>`.

Answer runs, judge scores and static-benchmark snapshots are outputs, not
fixtures: keep them under `results/`, `reports/`, `answers/`, `eval/` or
`baselines/`, which are git-ignored. Their schemas are locked by
`agent_benchmarks/schemas/*.json` and `tests/test_artifacts.py`; the only
committed artifacts are the one-per-schema fixtures in `tests/fixtures/artifacts/`,
which every later edit of that schema version must still accept.
