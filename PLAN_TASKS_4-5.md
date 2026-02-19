# Task 4-5: Soft/Hard Gate + Regression Detection

## Current State Summary

**Implemented (Tasks 1-3):**
- ✅ Spec v1 + JSON Schema validation
- ✅ 4 metrics: coverage, freshness_lite, readability, example_pass_rate
- ✅ CLI: run | compare | report
- ✅ CI: non-blocking workflow with artifacts
- ✅ Weight normalization
- ✅ Backward-compatible compare

**Spec-defined but not enforced:**
- ❌ `future.soft_gate` (enabled=false, min_score=0.80)
- ❌ `future.hard_gate` (enabled=false, min_score=0.85)
- ⚠️ `thresholds.regressions` (score_drop_warn/critical, metric_drop_warn/critical)
- ⚠️ `critical_bands.fail_on` (score_below, coverage_below conditions)

---

## Task 4: Soft Gate + Regression Alerts

**Goal:** Implement soft gate logic and regression detection without blocking CI.

**Scope:**
1. **Soft gate check in runner:**
   - Read `future.soft_gate.enabled` and `min_score` from spec
   - After run_benchmark, check if `summary.score < min_score`
   - Return gate status in snapshot or separate field

2. **Regression detection in compare:**
   - Read `thresholds.regressions` from spec
   - Compute deltas: `score_drop`, `metric_drop_*`
   - Classify: `OK | WARN | CRITICAL` per threshold
   - Include regression status in compare output

3. **Report updates:**
   - **run report (MD):** Add section "Gate Status" if soft_gate enabled
   - **compare report (MD):** Add section "Regression Analysis" with color-coded warnings

4. **CI behavior:**
   - Soft gate does NOT fail CI (continue-on-error: true remains)
   - Report displays gate/regression status for visibility

**Deliverables:**
- `doc_benchmarks/gate/soft_gate.py` — gate check logic
- `doc_benchmarks/gate/regression.py` — regression classification
- Updated `runner/run.py` — call soft_gate check
- Updated `runner/compare.py` — call regression detection
- Updated `report/markdown_report.py` — render gate + regression sections
- Updated spec validation in `_load_spec` (optional soft_gate keys)

**Acceptance Criteria:**
- [ ] `soft_gate.enabled=true` with score < min_score → report shows "SOFT GATE: FAIL"
- [ ] `soft_gate.enabled=false` → no gate check, no section in report
- [ ] Regression detection classifies score/metric drops as WARN/CRITICAL
- [ ] Compare report highlights regressions with severity
- [ ] CI remains non-blocking (exit 0 even if gate fails)
- [ ] All existing tests pass

**Estimated effort:** 2-3 hours

---

## Task 5: Hard Gate + Critical Bands

**Goal:** Add strict enforcement modes (hard gate, critical bands) with CI failure.

**Scope:**
1. **Hard gate check:**
   - Similar to soft gate but with `future.hard_gate.enabled` + `min_score`
   - If enabled and score < min_score → exit 1 (fail CI)
   - Optional: add `--strict` CLI flag to override spec setting

2. **Critical bands enforcement:**
   - Read `critical_bands.fail_on` list from spec
   - Check each condition (score_below, coverage_below, etc.) after run
   - If any condition met → exit 1 (fail CI)

3. **CLI updates:**
   - Add `--strict` / `--no-strict` flag to `cli.py run`
   - Exit codes: 0=pass, 1=gate/band fail, 2=error

4. **CI workflow update:**
   - Change `continue-on-error: true` → `false` (or make conditional)
   - Optional: separate job for strict vs. report-only runs

**Deliverables:**
- `doc_benchmarks/gate/hard_gate.py` — hard gate logic
- `doc_benchmarks/gate/critical_bands.py` — band checks
- Updated `cli.py` — strict mode flag + exit code handling
- Updated `.github/workflows/docs-quality.yml` — conditional strict mode
- Updated `README.md` — document strict mode behavior

**Acceptance Criteria:**
- [ ] `hard_gate.enabled=true` with score < min_score → CLI exits 1, CI fails
- [ ] `critical_bands.fail_on` conditions met → CLI exits 1, CI fails
- [ ] `--strict` flag overrides spec settings
- [ ] Non-strict mode (default) remains non-blocking
- [ ] Reports clearly indicate why gate/band failed

**Estimated effort:** 1-2 hours

---

## Implementation Order

**Phase 1 (Task 4):** Soft gate + regressions
1. Create `doc_benchmarks/gate/` package
2. Implement `soft_gate.py` check logic
3. Implement `regression.py` classification
4. Integrate into runner (run.py, compare.py)
5. Update markdown reports
6. Test with enabled/disabled scenarios

**Phase 2 (Task 5):** Hard gate + critical bands
1. Implement `hard_gate.py` (reuse soft gate logic, change exit behavior)
2. Implement `critical_bands.py` condition checker
3. Add CLI `--strict` flag + exit code handling
4. Update CI workflow (conditional strict)
5. Document in README

---

## Testing Strategy

**Manual tests:**
- Enable soft_gate, set min_score above current → verify report shows FAIL
- Create regression (lower score in candidate) → verify WARN/CRITICAL classification
- Enable hard_gate, set min_score above current → verify CLI exit 1
- Add critical_band condition that fails → verify CLI exit 1

**Integration tests (optional, post-MVP):**
- Unit tests for gate/regression modules
- CLI exit code tests
- Snapshot comparison tests with regressions

---

## Risk Assessment

**Low risk:**
- Soft gate (report-only, no behavior change)
- Regression detection (additive, no breaking changes)

**Medium risk:**
- Hard gate + critical bands (can break CI if misconfigured)
- Mitigation: default disabled, clear docs, `--no-strict` escape hatch

**High risk:**
- None identified

---

## Open Questions

1. **Hard gate in CI:** Always strict, or add workflow input parameter?
   - Recommendation: Default non-strict, add workflow_dispatch input for strict runs

2. **Regression alerts:** Should CRITICAL regressions fail CI even in non-strict mode?
   - Recommendation: No, keep report-only; hard gate is explicit opt-in

3. **Critical bands:** Should they apply to individual metrics or only aggregate score?
   - Current spec: score_below + coverage_below (both supported)
   - Recommendation: Keep as-is, extend to other metrics if needed later

---

## Success Criteria (Overall)

After Tasks 4-5:
- ✅ Spec-defined gates/bands/regressions fully implemented
- ✅ Non-blocking default (backward compatible)
- ✅ Strict mode available when needed
- ✅ Clear reports with actionable warnings
- ✅ CI green on main, failing only when explicitly configured

---

**Next Steps:**
1. Review this plan with team
2. Create branch `feat/task4-soft-gate-regression`
3. Implement Task 4 modules + tests
4. Open PR, review, merge
5. Create branch `feat/task5-hard-gate-bands`
6. Implement Task 5, PR, merge
