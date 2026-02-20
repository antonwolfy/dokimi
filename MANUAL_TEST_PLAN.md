# Manual Testing Plan

## Prerequisites
```bash
pip install PyYAML
# or
pip install -r requirements.txt
```

## Test 1: Basic Run (Non-blocking)

**Command:**
```bash
python cli.py run --root . --spec benchmarks/spec.v1.yaml \
  --out-json test-run/snapshot.json \
  --out-md test-run/report.md
```

**Expected output:**
- JSON summary printed to stdout
- `test-run/snapshot.json` created with:
  - `summary.docs` (count)
  - `summary.score` (0.0-1.0)
  - `summary.coverage`, `freshness_lite`, `readability`, `example_pass_rate`
  - `gate.soft.enabled`, `.passed`, `.min_score`
  - `docs[]` array with per-doc metrics
- `test-run/report.md` created with sections:
  - Summary (scores)
  - Soft Gate (if enabled)
  - Docs (per-file breakdown)

**Validation:**
```bash
# Check summary
jq '.summary' test-run/snapshot.json

# Check gate status
jq '.gate.soft' test-run/snapshot.json

# View report
cat test-run/report.md
```

---

## Test 2: Spec Validation

**Command:**
```bash
make validate-benchmark-spec
```

**Expected output:**
```
Checking YAML parse for benchmarks/spec.v1.yaml
Converting YAML -> JSON and validating against benchmarks/spec.schema.json
✅ Benchmark spec is valid
```

**Test invalid spec:**
```bash
# Temporarily break spec
echo "invalid: [" >> benchmarks/spec.v1.yaml
make validate-benchmark-spec
# Should fail with parse error
git checkout benchmarks/spec.v1.yaml
```

---

## Test 3: Compare with Regression Detection

**Setup:**
```bash
# Create baseline
cp test-run/snapshot.json test-run/baseline.json

# Simulate regression: lower score manually
jq '.summary.score -= 0.10 | .summary.coverage -= 0.08' test-run/baseline.json > test-run/regressed.json
```

**Command:**
```bash
python cli.py compare \
  --base test-run/baseline.json \
  --candidate test-run/regressed.json \
  --spec benchmarks/spec.v1.yaml \
  --out-json test-run/compare.json \
  --out-md test-run/compare-report.md
```

**Expected output:**
- `test-run/compare.json` with:
  - `diff.score`: -0.10
  - `diff.coverage`: -0.08
  - `regressions.score.severity`: "CRITICAL" (drop > 0.08)
  - `regressions.metrics[0].severity`: "WARN" (coverage drop > 0.05)
  - `regressions.has_critical`: true
- `test-run/compare-report.md` with:
  - 🔴 **CRITICAL regressions detected**
  - 🔴 **Score:** -0.1000 (CRITICAL)
  - 🟡 **coverage:** -0.0800 (WARN)

**Validation:**
```bash
jq '.regressions' test-run/compare.json
cat test-run/compare-report.md
```

---

## Test 4: Soft Gate Enabled

**Setup:**
```bash
# Edit spec: enable soft_gate, set high min_score
yq -i '.future.soft_gate.enabled = true | .future.soft_gate.min_score = 0.90' benchmarks/spec.v1.yaml
```

**Command:**
```bash
python cli.py run --root . --spec benchmarks/spec.v1.yaml \
  --out-json test-run/gate-snapshot.json \
  --out-md test-run/gate-report.md
```

**Expected output:**
- Snapshot: `gate.soft.enabled: true`, `.passed: false` (if score < 0.90)
- Report MD has section:
  ```
  ## Soft Gate
  ❌ **Status:** FAIL
  - Min score: 0.9000
  - Actual score: 0.xxxx
  ```

**Cleanup:**
```bash
git checkout benchmarks/spec.v1.yaml
```

---

## Test 5: Hard Gate + Strict Mode

**Setup:**
```bash
# Enable hard_gate in spec
yq -i '.future.hard_gate.enabled = true | .future.hard_gate.min_score = 0.95' benchmarks/spec.v1.yaml
```

**Command (non-strict — should pass):**
```bash
python cli.py run --root . --spec benchmarks/spec.v1.yaml \
  --out-json test-run/hard-snapshot.json \
  --out-md test-run/hard-report.md
echo "Exit code: $?"
# Expected: 0 (non-strict ignores hard gate)
```

**Command (strict — should fail if score < 0.95):**
```bash
python cli.py run --root . --spec benchmarks/spec.v1.yaml \
  --out-json test-run/hard-snapshot.json \
  --out-md test-run/hard-report.md \
  --strict
echo "Exit code: $?"
# Expected: 1 (hard gate enforced)
# Stderr: ❌ HARD GATE FAILED: score 0.xxxx < 0.9500
```

**Cleanup:**
```bash
git checkout benchmarks/spec.v1.yaml
```

---

## Test 6: Critical Bands

**Setup:**
```bash
# Lower critical band threshold so it triggers
yq -i '.critical_bands.fail_on[0].value = 0.80' benchmarks/spec.v1.yaml
# (assumes current score < 0.80)
```

**Command:**
```bash
python cli.py run --root . --spec benchmarks/spec.v1.yaml \
  --out-json test-run/band-snapshot.json \
  --out-md test-run/band-report.md \
  --strict
echo "Exit code: $?"
# Expected: 1 if score < 0.80
# Stderr:
# ❌ CRITICAL BAND VIOLATIONS:
#   - score_below: 0.xxxx < 0.8000
```

**Cleanup:**
```bash
git checkout benchmarks/spec.v1.yaml
```

---

## Test 7: Example Execution

**Setup:**
```bash
# Create a test markdown with code examples
cat > docs/test-examples.md <<'EOMD'
# Test Examples

## Python
```python
print(2 + 2)
```

## Bash
```bash
echo "hello"
```

## Invalid Python
```python
import nonexistent_module
```
EOMD
```

**Command:**
```bash
python cli.py run --root . --spec benchmarks/spec.v1.yaml \
  --out-json test-run/examples-snapshot.json \
  --out-md test-run/examples-report.md
```

**Expected output:**
- Snapshot includes `docs[].example_results[]` for `test-examples.md`:
  - `{index: 0, lang: "python", passed: true, error: null}`
  - `{index: 1, lang: "bash", passed: true, error: null}`
  - `{index: 2, lang: "python", passed: false, error: "Exit code 1: ModuleNotFoundError..."}`
- Summary: `example_pass_rate: 0.6667` (2/3 passed)

**Validation:**
```bash
jq '.docs[] | select(.path | contains("test-examples"))' test-run/examples-snapshot.json
```

**Cleanup:**
```bash
rm docs/test-examples.md
```

---

## Test 8: Unknown Condition (Fail-Fast)

**Setup:**
```bash
# Add typo in critical_bands
yq -i '.critical_bands.fail_on += [{"condition": "typo_below", "value": 0.5}]' benchmarks/spec.v1.yaml
```

**Command:**
```bash
python cli.py run --root . --spec benchmarks/spec.v1.yaml \
  --out-json test-run/typo-snapshot.json \
  --out-md test-run/typo-report.md \
  --strict
# Expected: ValueError with message:
# "Unknown critical_bands condition: typo_below (known: coverage_below, freshness_below, readability_below, score_below)"
```

**Cleanup:**
```bash
git checkout benchmarks/spec.v1.yaml
```

---

## Summary Checklist

- [ ] Basic run produces valid snapshot + report
- [ ] Spec validation passes for valid spec, fails for invalid
- [ ] Compare detects regressions (WARN/CRITICAL)
- [ ] Soft gate shows PASS/FAIL in report (non-blocking)
- [ ] Hard gate exits 0 in non-strict, exits 1 in strict
- [ ] Critical bands exit 1 when violated in strict mode
- [ ] Example execution runs code, reports pass/fail
- [ ] Unknown conditions raise ValueError (fail-fast)

All tests can be automated in pytest later.
