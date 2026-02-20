# Doc-Benchmark Status Update
**Date:** 2026-02-20  
**Branch:** main  
**Commits since start:** 7

---

## ✅ Completed (MVP Scope)

### Task 1: Spec + Validation
- `benchmarks/spec.v1.yaml` — benchmark configuration
- `benchmarks/spec.schema.json` — JSON Schema validation
- `Makefile` target: `validate-benchmark-spec`
- **Result:** Spec-driven configuration, deterministic runs

### Task 2: Core Runner + 3 Metrics
- **Metrics:**
  - `coverage` — heading/code/body signals (weight 0.35)
  - `freshness_lite` — file age-based (weight 0.25)
  - `readability` — Flesch-Kincaid grade (weight 0.20)
- **Runner:** markdown ingest (loader + chunker), deterministic scoring
- **CLI:** `run | compare | report` subcommands
- **CI:** non-blocking GitHub Actions workflow with artifact upload
- **Result:** Baseline + compare workflow functional

### Task 3: Example Execution
- **Metric:** `example_pass_rate` (weight 0.20)
- **Runner:** isolated subprocess (python, bash, sh) with timeout
- **Features:**
  - Case-insensitive language tags
  - Metadata support (```python title="x.py")
  - Per-example results in output
  - Configurable timeout from spec
- **Result:** Code examples validated automatically

### Task 4: Soft Gate + Regression Detection
- **Modules:**
  - `gate/soft_gate.py` — PASS/FAIL/DISABLED status (report-only)
  - `gate/regression.py` — OK/WARN/CRITICAL classification
- **Integration:**
  - Run snapshots include gate status
  - Compare includes regression analysis (when spec provided)
  - Markdown reports show gate + regression sections
- **Result:** Visibility into score regressions and gate violations without CI failures

### Task 5: Hard Gate + Critical Bands
- **Modules:**
  - `gate/hard_gate.py` — enforced gate check
  - `gate/critical_bands.py` — score_below, coverage_below, freshness_below, readability_below
- **CLI:** `--strict` flag for `run` subcommand
- **Behavior:**
  - Default (non-strict): report-only, backward compatible
  - Strict mode: exit 1 on hard gate fail or critical band violation
- **Result:** Optional CI enforcement for quality gates

---

## 📊 Current Capabilities

**Metrics (4 active):**
- Coverage: 35%
- Freshness: 25%
- Readability: 20%
- Example pass rate: 20%
- **Total weight:** 100% (normalized)

**Gates:**
- Soft gate: report-only, non-blocking
- Hard gate: exit 1 in --strict mode

**Regression detection:**
- Score drops: WARN (>3%), CRITICAL (>8%)
- Metric drops: WARN (>5%), CRITICAL (>12%)

**Critical bands:**
- Configurable fail_on conditions
- Default: score <0.60, coverage <0.70

---

## 🔧 Usage Examples

### Basic run (non-blocking)
```bash
python cli.py run --root . --spec benchmarks/spec.v1.yaml \
  --out-json baselines/current.json --out-md reports/current.md
```

### Compare with regression analysis
```bash
python cli.py compare --base baselines/baseline.json \
  --candidate baselines/current.json \
  --spec benchmarks/spec.v1.yaml \
  --out-json reports/compare.json --out-md reports/compare.md
```

### Strict mode (CI blocking)
```bash
python cli.py run --root . --spec benchmarks/spec.v1.yaml \
  --out-json baselines/current.json --out-md reports/current.md \
  --strict
# Exits 1 if hard gate fails or critical band violated
```

### Validate spec
```bash
make validate-benchmark-spec
```

---

## 📁 Structure

```
doc-benchmark/
├── benchmarks/
│   ├── spec.v1.yaml          # Benchmark configuration
│   └── spec.schema.json      # JSON Schema validation
├── doc_benchmarks/
│   ├── ingest/
│   │   ├── loader.py         # Markdown discovery + loading
│   │   └── chunker.py        # Text chunking
│   ├── metrics/
│   │   ├── coverage.py       # Structure coverage scorer
│   │   ├── freshness_lite.py # File age scorer
│   │   ├── readability.py    # FK grade scorer
│   │   └── example_runner.py # Isolated code execution
│   ├── runner/
│   │   ├── run.py            # Benchmark orchestration
│   │   └── compare.py        # Snapshot comparison + regressions
│   ├── report/
│   │   ├── json_report.py    # JSON writer
│   │   └── markdown_report.py# MD report renderer
│   └── gate/
│       ├── soft_gate.py      # Report-only gate
│       ├── hard_gate.py      # Enforced gate (strict mode)
│       ├── regression.py     # Regression classification
│       └── critical_bands.py # Threshold enforcement
├── cli.py                    # CLI entry point
├── Makefile                  # Validation targets
└── .github/workflows/
    └── docs-quality.yml      # CI workflow
```

---

## ⚠️ Known Limitations

1. **No unit tests:** Only manual smoke tests + CI integration tests
2. **Example runner:** Supports python/bash/sh only (extensible via EXECUTORS dict)
3. **CI workflow:** Always non-blocking (--strict not enabled in CI yet)
4. **LLM eval:** Not implemented (future metric, weight 0.0)

---

## 🚀 Next Steps (Post-MVP)

1. **Unit tests:** pytest suite for gate/regression modules
2. **README:** Usage guide, --strict mode docs, metric descriptions
3. **CI enhancement:** workflow_dispatch input for strict runs
4. **LLM eval:** Optional 5th metric for semantic quality (large effort)

---

## 🎯 Success Metrics

- ✅ All spec-defined features implemented
- ✅ Backward compatible (default non-blocking)
- ✅ CI green on all PRs
- ✅ Deterministic scoring (reproducible results)
- ✅ Clear error messages (fail-fast on bad config)
- ✅ Comprehensive reports (JSON + Markdown)

**Current score on own docs:** TBD (will test below)
