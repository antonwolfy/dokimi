# LLM evaluation pipeline — quickstart

End-to-end recipe for running the LLM-assisted documentation evaluation:
persona discovery → question generation → answer generation (WITH/WITHOUT docs)
→ judge scoring → analysis report.

For the static documentation benchmark (`coverage`, `freshness`, `readability`,
`example_pass_rate`), see the top-level [README](../README.md#static-benchmark-metrics).

## Prerequisites

### 1. API keys

```bash
# OpenAI (question generation, answering)
export OPENAI_API_KEY="sk-..."

# Anthropic (judging — separate provider to reduce self-evaluation bias)
export ANTHROPIC_API_KEY="sk-ant-..."

# GitHub (optional — raises persona-discovery rate limit from 60 to 5000/hour)
export GITHUB_TOKEN="ghp_..."
```

### 2. Dependencies

```bash
pip install -r requirements.txt
pip install -r requirements-test.txt
```

The pipeline degrades gracefully if optional deps are missing — see
[Troubleshooting](#troubleshooting).

## Pipeline

All commands run from the repo root and use `python cli.py …`. Use
`--help` on any subcommand for the full option list.

### Step 1 — Discover personas

```bash
python cli.py personas discover \
  --product oneTBB \
  --repo uxlfoundation/oneTBB \
  --count 5 \
  --save-analysis
```

Reads the GitHub repo (README, issues, API patterns), generates 5–8 user
personas via LLM, and writes `personas/oneTBB.json`. Each persona has `id`,
`name`, `description`, `skill_level`, `concerns`, and `typical_questions`.

Review and approve:

```bash
$EDITOR personas/oneTBB.json
python cli.py personas approve --file personas/oneTBB.json
```

### Step 2 — Generate questions

```bash
python cli.py questions generate \
  --product oneTBB \
  --personas personas/oneTBB.json \
  --count 2 \
  --validate \
  --model gpt-4o-mini
```

Extracts seed topics from the docs, generates questions per persona × topic,
LLM-validates them (threshold 60/100), and deduplicates via embeddings
(similarity > 0.85). Expected output: ~30–50 unique questions in
`questions/oneTBB.json`.

### Step 3 — Generate answers (WITH + WITHOUT docs)

```bash
python cli.py answers generate \
  --product oneTBB \
  --questions questions/oneTBB.json \
  --output answers/oneTBB.json \
  --model gpt-4o-mini \
  --provider openai \
  --top-k 5 \
  --rerank-threshold 0.3 \
  --debug-retrieval
```

For each question, two answers are produced: WITH docs (retrieved via the
configured `--doc-source`, default Context7) and WITHOUT docs (model knowledge
only). Use `--doc-source local:<path>` or `--doc-source url:<url>` for
alternative sources — see [adding-doc-source.md](adding-doc-source.md).

### Step 4 — Score answers

```bash
python cli.py eval score \
  --product oneTBB \
  --answers answers/oneTBB.json \
  --output eval/oneTBB.json \
  --judge-model claude-sonnet-4 \
  --judge-provider anthropic
```

LLM-as-judge scores each answer on five 0–100 dimensions
(correctness, completeness, specificity, code_quality, actionability), then
computes an aggregate and the WITH–WITHOUT delta.

Multi-judge panel (see [BACKLOG.md](../BACKLOG.md) #29):

```bash
python cli.py eval panel-score \
  --product oneTBB \
  --answers answers/oneTBB.json \
  --output eval/oneTBB.panel.json
```

### Step 5 — Generate the analysis report

```bash
python cli.py report generate \
  --product oneTBB \
  --eval eval/oneTBB.json \
  --questions questions/oneTBB.json \
  --output reports/oneTBB.md \
  --format markdown
```

`reports/oneTBB.md` contains summary stats (min/max/avg WITH/WITHOUT/delta),
top-N best and worst answers, top improvements and degradations, topic and
persona clustering, and recommendations. The `reports/` directory is
git-ignored.

### Step 6 — Dashboard (optional)

```bash
python cli.py dashboard generate
```

Aggregates per-library results from `eval/*.json` into `DASHBOARD.md` /
`dashboard.json` for cross-library comparison.

## Full run (single command)

```bash
PRODUCT=oneTBB
REPO=uxlfoundation/oneTBB

python cli.py personas discover --product $PRODUCT --repo $REPO --count 5 && \
python cli.py personas approve --file personas/$PRODUCT.json && \
python cli.py questions generate --product $PRODUCT --personas personas/$PRODUCT.json --validate && \
python cli.py answers generate --product $PRODUCT --questions questions/$PRODUCT.json --model gpt-4o-mini && \
python cli.py eval score --product $PRODUCT --answers answers/$PRODUCT.json --judge-model claude-sonnet-4 --judge-provider anthropic && \
python cli.py report generate --product $PRODUCT --eval eval/$PRODUCT.json --questions questions/$PRODUCT.json --output reports/$PRODUCT.md
```

Or use the single-command wrapper:

```bash
python cli.py evaluate --product $PRODUCT --repo $REPO
```

## Output layout

| File | Content |
| --- | --- |
| `personas/<product>.json` | 5–8 user personas |
| `questions/<product>.json` | Validated, deduped questions |
| `answers/<product>.json` | WITH/WITHOUT answer pairs + retrieval metadata + token counts |
| `eval/<product>.json` | Per-question scores (5 dimensions) + aggregates + deltas |
| `reports/<product>.md` | Human-readable analysis (git-ignored) |
| `DASHBOARD.md` | Cross-library summary |

Curated fixtures under `answers/`, `eval/`, `questions/`, and `baselines/` can
be committed when they are part of a reproducible benchmark; ad-hoc runs
should stay under `reports/` and `results/` (both ignored).

## Cost estimate

For 35 questions on `gpt-4o` + `claude-sonnet-4`:

| Step | Calls | Approx. cost |
| --- | --- | --- |
| Persona discovery | a few | $0.50 |
| Question generation | ~35 | $0.50 |
| Answer generation | ~70 (WITH + WITHOUT) | $5 |
| Judge scoring | ~70 | $7 |
| **Total** | | **~$13** |

Costs scale roughly linearly with question count. Token counts are recorded
per answer in `answers/<product>.json`.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `No module named langchain` | `pip install langchain-openai langchain-anthropic` |
| `No module named numpy` | Pipeline falls back to exact-text dedup; install numpy for embedding-based dedup |
| `GitHub client not available` | Pipeline uses `gh` CLI fallback; `pip install PyGithub` to silence |
| Context7 timeout | Raise `context7.timeout` in `config/products.yaml` |
| Rate limiting | OpenAI 10K TPM default, Anthropic 10K TPM default; lower `--concurrency` |

## Where to look next

- [adding-doc-source.md](adding-doc-source.md) — point the pipeline at local
  files, a single URL, or a custom MCP-style client.
- [architecture.md](architecture.md) — high-level data flow and module
  boundaries.
- [contributing-metric.md](contributing-metric.md) — add a new static
  documentation metric.
- [contributing-terminal-bench-task.md](contributing-terminal-bench-task.md)
  — add an executable oneTBB / oneAPI task.
- [decisions/](decisions/) — historical design reviews and trade-off notes.
