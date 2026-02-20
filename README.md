# Doc-Benchmark: Automated Documentation Quality Metrics

Automated benchmarking tool for documentation quality with **4 metrics**, **gate enforcement**, and **regression detection**.

---

## Quick Start

### Installation
```bash
pip install PyYAML
# or
pip install -r requirements.txt
```

### Basic Run
```bash
python cli.py run --root . --spec benchmarks/spec.v1.yaml \
  --out-json baselines/current.json \
  --out-md reports/current.md
```

### Compare Snapshots
```bash
python cli.py compare \
  --base baselines/baseline.json \
  --candidate baselines/current.json \
  --spec benchmarks/spec.v1.yaml \
  --out-json reports/compare.json \
  --out-md reports/compare.md
```

### Strict Mode (CI Blocking)
```bash
python cli.py run --root . --spec benchmarks/spec.v1.yaml \
  --out-json baselines/current.json \
  --out-md reports/current.md \
  --strict
# Exits 1 if hard gate fails or critical band violated
```

---

## Metrics (4 Active)

### 1. Coverage (weight 0.35)
**What:** Structure coverage — presence of headings, code blocks, body content  
**Scorer:** Heuristic based on:
- Headings (H1-H6): 40% weight
- Code blocks (fenced): 30% weight
- Body text (word count): 30% weight

**Range:** 0.0 (empty) → 1.0 (well-structured)

---

### 2. Freshness (`freshness_lite`) (weight 0.25)
**What:** File modification age-based scoring  
**Scorer:** Linear decay from 1.0 (fresh) to 0.0 (stale)  
**Config:** `max_age_days` (default 365) in spec

**Formula:**
```
score = 1.0 - (age_days / max_age_days)
```

**Range:** 0.0 (>365 days old) → 1.0 (recently modified)

---

### 3. Readability (weight 0.20)
**What:** Flesch-Kincaid grade level (inverse)  
**Scorer:** FK formula on text (code blocks stripped)  
**Config:** `grade_max` (default 12) in spec

**Formula:**
```
FK = 0.39 * (words/sentences) + 11.8 * (syllables/words) - 15.59
score = 1.0 - (FK / grade_max)
```

**Range:** 0.0 (complex/academic) → 1.0 (simple/clear)

---

### 4. Example Pass Rate (weight 0.20)
**What:** Percentage of runnable code examples that execute successfully  
**Executor:** Isolated subprocess (python, bash, sh)  
**Config:** `timeout` (default 5s) in spec

**Supported languages:**
- `python` (python3 -c)
- `bash` (bash -c)
- `sh` (sh -c)

**Range:** 0.0 (all examples fail) → 1.0 (all examples pass)

**Features:**
- Case-insensitive language tags (```Python → python)
- Metadata support (```python title="x.py")
- Per-example results in output (index, lang, passed, error)
- Configurable timeout

---

## Gates & Enforcement

### Soft Gate (Report-Only)
**Purpose:** Visibility into score vs. target without blocking CI

**Behavior:**
- Always runs (if enabled in spec)
- Adds `gate.soft` section to snapshot
- Shows PASS/FAIL/DISABLED in markdown report
- **Never fails CI** (exit 0)

**Config:**
```yaml
future:
  soft_gate:
    enabled: true
    min_score: 0.80
```

**Report example:**
```
## Soft Gate
❌ **Status:** FAIL
- Min score: 0.8000
- Actual score: 0.7245
```

---

### Hard Gate (Strict Mode)
**Purpose:** Block CI/PR if docs quality below threshold

**Behavior:**
- Only enforced with `--strict` flag
- Checks `future.hard_gate` in spec
- **Exits 1** if score < min_score
- Prints clear stderr message

**Config:**
```yaml
future:
  hard_gate:
    enabled: true
    min_score: 0.85
```

**Usage:**
```bash
python cli.py run --spec benchmarks/spec.v1.yaml --strict
# Exit 1 if score < 0.85
# Stderr: ❌ HARD GATE FAILED: score 0.7245 < 0.8500
```

---

### Critical Bands
**Purpose:** Fail on specific metric thresholds (score, coverage, etc.)

**Behavior:**
- Only enforced with `--strict` flag
- Checks `critical_bands.fail_on` list in spec
- **Exits 1** if any condition violated

**Supported conditions:**
- `score_below`
- `coverage_below`
- `freshness_below` (checks `freshness_lite` metric)
- `readability_below`

**Config:**
```yaml
critical_bands:
  fail_on:
    - condition: score_below
      value: 0.60
    - condition: coverage_below
      value: 0.70
```

**Example stderr:**
```
❌ CRITICAL BAND VIOLATIONS:
  - score_below: 0.5524 < 0.6000
  - coverage_below: 0.6512 < 0.7000
```

---

## Regression Detection

### Purpose
Identify quality drops between baseline and candidate snapshots

### Severity Levels
- **OK:** Improvement or drop within acceptable range
- **WARN:** Drop exceeds warning threshold (e.g. score -3%)
- **CRITICAL:** Drop exceeds critical threshold (e.g. score -8%)

### Config
```yaml
thresholds:
  regressions:
    score_drop_warn: 0.03      # 3% drop → WARN
    score_drop_critical: 0.08  # 8% drop → CRITICAL
    metric_drop_warn: 0.05     # 5% metric drop → WARN
    metric_drop_critical: 0.12 # 12% metric drop → CRITICAL
```

### Usage
```bash
python cli.py compare \
  --base baselines/baseline.json \
  --candidate baselines/current.json \
  --spec benchmarks/spec.v1.yaml \
  --out-json reports/compare.json \
  --out-md reports/compare.md
```

### Report Example
```markdown
## Regression Analysis
🔴 **CRITICAL regressions detected**

🔴 **Score:** -0.1000 (CRITICAL)
🟡 **coverage:** -0.0600 (WARN)
✅ **freshness_lite:** +0.0100 (OK)
✅ **readability:** +0.0050 (OK)
```

---

## CLI Reference

### `run` — Benchmark documentation
```bash
python cli.py run [OPTIONS]

Options:
  --root PATH         Root directory (default: .)
  --spec PATH         Spec file (default: benchmarks/spec.v1.yaml)
  --out-json PATH     Output snapshot JSON (default: baselines/current.json)
  --out-md PATH       Output report MD (default: reports/current.md)
  --strict            Enable hard gate + critical bands (exit 1 on fail)
```

**Outputs:**
- JSON snapshot: `summary` (scores), `docs[]` (per-file), `gate` (status)
- Markdown report: Summary, Gate Status (if enabled), Docs breakdown

---

### `compare` — Compare snapshots with regression analysis
```bash
python cli.py compare [OPTIONS]

Options:
  --base PATH         Baseline snapshot (required)
  --candidate PATH    Candidate snapshot (required)
  --spec PATH         Spec file for regression thresholds (optional)
  --out-json PATH     Output comparison JSON (default: reports/compare.json)
  --out-md PATH       Output report MD (default: reports/compare.md)
```

**Outputs:**
- JSON: `base`, `candidate`, `diff`, `regressions` (if spec provided)
- Markdown report: Diff, Regression Analysis (with severity)

---

### `report` — Render JSON to markdown
```bash
python cli.py report [OPTIONS]

Options:
  --input PATH        JSON snapshot or comparison (required)
  --out-md PATH       Output report MD (default: reports/report.md)
```

---

## Spec Configuration

### Structure
```yaml
version: 1
schema: ./spec.schema.json
name: doc-benchmark-spec-v1
mode: non_blocking

weights:
  coverage: 0.35
  freshness_lite: 0.25
  readability: 0.20
  example_pass_rate: 0.20
  llm_eval: 0.0  # Future metric

metrics:
  coverage:
    enabled: true
    weight: 0.35
    target: 0.90
  freshness_lite:
    enabled: true
    weight: 0.25
    max_age_days: 365
  readability:
    enabled: true
    weight: 0.20
    grade_max: 12
  example_pass_rate:
    enabled: true
    weight: 0.20
    timeout: 5

thresholds:
  score:
    green: 0.85
    yellow: 0.70
    red: 0.0
  regressions:
    score_drop_warn: 0.03
    score_drop_critical: 0.08
    metric_drop_warn: 0.05
    metric_drop_critical: 0.12

critical_bands:
  fail_on:
    - condition: score_below
      value: 0.60
    - condition: coverage_below
      value: 0.70

ci:
  policy: non_blocking
  report_formats:
    - json
    - markdown

future:
  soft_gate:
    enabled: false
    min_score: 0.80
  hard_gate:
    enabled: false
    min_score: 0.85

golden_manifest:
  min_docs: 10
  max_docs: 20
  include:
    - docs/**/*.md
  exclude:
    - docs/archive/**
```

### Weight Normalization
Weights are **automatically normalized** across active metrics. If a metric is disabled, its weight is redistributed.

Example:
- `example_pass_rate` disabled → weights rebalanced so coverage/freshness/readability sum to 1.0
- No manual adjustment needed

---

## CI Integration

### Basic Workflow (Non-Blocking)
```yaml
name: docs-quality

on:
  push:
    branches: [ main ]
  pull_request:

jobs:
  benchmark:
    runs-on: ubuntu-latest
    continue-on-error: true  # Non-blocking
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install deps
        run: pip install -r requirements.txt
      - name: Run benchmark
        run: |
          python cli.py run --root . --spec benchmarks/spec.v1.yaml \
            --out-json baselines/current.json --out-md reports/current.md
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: docs-quality-report
          path: |
            baselines/current.json
            reports/current.md
```

### Optional: Strict Mode on Demand
```yaml
on:
  workflow_dispatch:
    inputs:
      strict:
        description: 'Enable strict mode (exit 1 on gate/band fail)'
        required: false
        type: boolean
        default: false

jobs:
  benchmark:
    runs-on: ubuntu-latest
    continue-on-error: ${{ github.event.inputs.strict != 'true' }}
    steps:
      # ... same setup ...
      - name: Run benchmark
        run: |
          python cli.py run --root . --spec benchmarks/spec.v1.yaml \
            --out-json baselines/current.json --out-md reports/current.md \
            ${{ github.event.inputs.strict == 'true' && '--strict' || '' }}
```

---

## Validation

### Validate Spec
```bash
make validate-benchmark-spec
```

**Output:**
```
Checking YAML parse for benchmarks/spec.v1.yaml
Converting YAML -> JSON and validating against benchmarks/spec.schema.json
✅ Benchmark spec is valid
```

**Requirements:**
- `yq` (YAML processor)
- `npx` (or global `ajv-cli`)

---

## Project Structure

```
doc-benchmark/
├── benchmarks/
│   ├── spec.v1.yaml          # Configuration
│   └── spec.schema.json      # JSON Schema validation
├── doc_benchmarks/
│   ├── ingest/
│   │   ├── loader.py         # Markdown discovery
│   │   └── chunker.py        # Text chunking
│   ├── metrics/
│   │   ├── coverage.py       # Structure scorer
│   │   ├── freshness_lite.py # Age scorer
│   │   ├── readability.py    # FK grade scorer
│   │   └── example_runner.py # Code execution
│   ├── runner/
│   │   ├── run.py            # Orchestration
│   │   └── compare.py        # Diff + regressions
│   ├── report/
│   │   ├── json_report.py    # JSON writer
│   │   └── markdown_report.py# MD renderer
│   └── gate/
│       ├── soft_gate.py      # Report-only gate
│       ├── hard_gate.py      # Enforced gate
│       ├── regression.py     # Regression classifier
│       └── critical_bands.py # Threshold enforcer
├── cli.py                    # CLI entry point
├── Makefile                  # Validation targets
└── .github/workflows/
    └── docs-quality.yml      # CI workflow
```

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'yaml'`
**Solution:** `pip install PyYAML`

### Hard gate doesn't fail CI
**Cause:** Missing `--strict` flag  
**Solution:** Add `--strict` to `cli.py run` command

### Unknown critical_bands condition
**Cause:** Typo in `spec.v1.yaml`  
**Known conditions:** `score_below`, `coverage_below`, `freshness_below`, `readability_below`  
**Solution:** Fix typo in spec

### Example execution fails with "Unsupported language"
**Cause:** Language not in `EXECUTORS` dict  
**Supported:** python, bash, sh  
**Solution:** Extend `doc_benchmarks/metrics/example_runner.py` with new executor

---

## Roadmap

- [x] Core metrics (coverage, freshness, readability, examples)
- [x] Soft gate (report-only)
- [x] Hard gate (strict mode)
- [x] Critical bands enforcement
- [x] Regression detection (WARN/CRITICAL)
- [ ] Unit tests (pytest suite)
- [ ] LLM eval metric (semantic quality)
- [ ] Baseline versioning (auto-update on main)
- [ ] Additional languages (java, rust, c++)

---

## License

Internal Intel use.

---

## Contributing

See [MANUAL_TEST_PLAN.md](MANUAL_TEST_PLAN.md) for testing guide.
