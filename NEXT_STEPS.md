# Next Steps — Post-MVP Priorities

**Current state:** MVP complete (all gate/metric/CLI features working)

---

## Priority 1: Documentation (30-60 min)

### README Update
**Goal:** Users can understand and use the tool without reading code

**Sections to add:**
1. **Quick Start**
   - Installation: `pip install -r requirements.txt`
   - Basic run: `python cli.py run ...`
   - Compare: `python cli.py compare ...`

2. **Metrics Overview**
   - Coverage (0.35): heading/code/body signals
   - Freshness (0.25): file age-based
   - Readability (0.20): Flesch-Kincaid grade
   - Example pass rate (0.20): isolated code execution

3. **Gate & Regression Features**
   - Soft gate: report-only, visible in snapshot/report
   - Hard gate: `--strict` mode, exit 1 on fail
   - Critical bands: configurable thresholds
   - Regression detection: WARN/CRITICAL classification

4. **CLI Reference**
   - `run`: benchmark docs
   - `compare`: diff snapshots with regression analysis
   - `report`: render JSON to MD
   - `--strict`: enforce gates/bands (exit 1 on fail)

5. **Spec Configuration**
   - `benchmarks/spec.v1.yaml` structure
   - Weights (must sum to 1.0 when normalized)
   - Thresholds (regressions)
   - Gates (soft/hard)
   - Critical bands

6. **CI Integration**
   - Example workflow
   - Artifact upload
   - Optional strict mode

**Deliverable:** Updated `README.md` with complete usage guide

---

## Priority 2: Unit Tests (2-3 hours)

### Test Coverage Targets
**Goal:** Prevent regressions, validate core logic

**Test modules:**
1. `tests/test_gate_soft.py`
   - PASS/FAIL/DISABLED scenarios
   - Edge cases (empty spec, score=min_score)

2. `tests/test_gate_hard.py`
   - Same as soft_gate
   - Exit behavior validation (mock sys.exit in CLI tests)

3. `tests/test_regression.py`
   - OK/WARN/CRITICAL classification
   - Boundary conditions (exactly at threshold)
   - Empty diff (no regressions)

4. `tests/test_critical_bands.py`
   - Each condition type (score_below, coverage_below, etc.)
   - Multiple violations
   - Unknown condition ValueError

5. `tests/test_metrics.py`
   - Coverage scorer: various markdown structures
   - Freshness: old/new files
   - Readability: simple/complex text
   - Example runner: pass/fail/timeout/unsupported lang

6. `tests/test_cli.py`
   - run subcommand exit codes
   - compare subcommand output structure
   - --strict flag behavior

**Setup:**
- `pytest` + `pytest-cov`
- Target: 80%+ coverage on gate/metrics modules
- CI integration: `pytest --cov=doc_benchmarks`

**Deliverable:** `tests/` directory with pytest suite

---

## Priority 3: CI Enhancement (30 min)

### Workflow Improvements
**Goal:** Make strict mode available on-demand in CI

**Changes to `.github/workflows/docs-quality.yml`:**
1. Add `workflow_dispatch` input:
   ```yaml
   on:
     push:
       branches: [ main ]
     pull_request:
     workflow_dispatch:
       inputs:
         strict:
           description: 'Enable strict mode (exit 1 on gate/band fail)'
           required: false
           type: boolean
           default: false
   ```

2. Conditional strict flag:
   ```yaml
   - name: Run benchmark
     run: |
       python cli.py run --root . --spec benchmarks/spec.v1.yaml \
         --out-json baselines/current.json --out-md reports/current.md \
         ${{ github.event.inputs.strict == 'true' && '--strict' || '' }}
   ```

3. Update `continue-on-error`:
   ```yaml
   continue-on-error: ${{ github.event.inputs.strict != 'true' }}
   ```

**Result:** Manual runs can enable strict mode, default remains non-blocking

**Deliverable:** Updated workflow file

---

## Priority 4: Baseline Management (optional, 1 hour)

### Automated Baseline Updates
**Goal:** Track quality over time without manual snapshot management

**Approach:**
1. Store baselines by git ref:
   ```
   baselines/
     main.json         # Latest main
     pr-123.json       # PR snapshot
     release-v1.0.json # Tagged releases
   ```

2. CLI subcommand: `update-baseline`
   ```bash
   python cli.py update-baseline --from baselines/current.json --to baselines/main.json
   ```

3. CI: auto-update main baseline on merge to main:
   ```yaml
   - name: Update baseline
     if: github.ref == 'refs/heads/main'
     run: |
       cp baselines/current.json baselines/main.json
       git add baselines/main.json
       git commit -m "Update main baseline [skip ci]"
       git push
   ```

**Deliverable:** Baseline versioning system

---

## Priority 5: LLM Eval Metric (large, 4-6 hours)

### Semantic Quality Scoring
**Goal:** 5th metric for doc quality beyond structural checks

**Scope:**
1. Module: `doc_benchmarks/metrics/llm_eval.py`
2. Prompt templates for:
   - Clarity (is the doc easy to understand?)
   - Completeness (are key topics covered?)
   - Accuracy (technical correctness signals)
3. API integration:
   - OpenAI (gpt-4o-mini)
   - Anthropic (claude-3-haiku)
   - Local models (via ollama)
4. Caching: avoid re-running on unchanged docs
5. Rate limiting: respect API quotas

**Challenges:**
- Cost (API calls per doc)
- Speed (slower than structural metrics)
- Determinism (LLM variance)
- Config: API keys in env vars

**Deliverable:** `llm_eval` metric with weight 0.0 (opt-in)

---

## Recommended Order

**Week 1:**
1. README update (Priority 1) — immediate value for users
2. Unit tests (Priority 2) — prevent regressions as code evolves
3. CI enhancement (Priority 3) — enable strict mode on-demand

**Week 2+:**
4. Baseline management (Priority 4) — nice-to-have, automates workflow
5. LLM eval (Priority 5) — experimental, high effort

---

## Decision Points

**Question 1:** Do we need unit tests before merging more features?
- **Yes:** Write tests now (Priority 2 first)
- **No:** Document first, tests later (Priority 1 first)

**Question 2:** Should strict mode be opt-in or default in CI?
- **Current:** Opt-in (safer, backward compatible)
- **Alternative:** Default strict on main (enforces quality)

**Question 3:** LLM eval scope?
- **Minimal:** Single provider (OpenAI), simple prompt
- **Full:** Multi-provider, configurable prompts, caching

---

**Immediate next task:** README update (Priority 1)

Starting now?
