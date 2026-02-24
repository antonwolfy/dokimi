# Quick Start Guide: Ready-to-Use Workflow

## Prerequisites

Already done ✅:
- Virtual environment: `.venv/`
- Dependencies installed
- Reranker + CLI integrated

## Complete Workflow (No Manual Code)

### 1. Generate Answers (WITH docs via MCP + WITHOUT docs baseline)

```bash
cd doc-benchmark

.venv/bin/python cli.py answers generate \
  --product oneTBB \
  --questions questions/oneTBB.json \
  --output answers/oneTBB.rerank.json \
  --model gpt-4o-mini \
  --provider openai \
  --top-k 5 \
  --rerank-threshold 0.3 \
  --debug-retrieval
```

**Output:** `answers/oneTBB.rerank.json` (WITH + WITHOUT answers for all questions)

---

### 2. Evaluate Quality (LLM-as-Judge scoring)

```bash
.venv/bin/python cli.py eval score \
  --product oneTBB \
  --answers answers/oneTBB.rerank.json \
  --output eval/oneTBB.rerank.json \
  --judge-model gpt-4o-mini \
  --judge-provider openai
```

**Output:** `eval/oneTBB.rerank.json` (scores for each question + aggregate stats)

---

### 3. Generate Report (Analysis + Clustering + Comparisons)

```bash
.venv/bin/python cli.py report generate \
  --product oneTBB \
  --eval eval/oneTBB.rerank.json \
  --questions questions/oneTBB.json \
  --output reports/oneTBB.md \
  --format markdown
```

**Output:** `reports/oneTBB.md` (comprehensive Markdown report)

---

## What You Get

### From `eval/*.json`:
1. **Overall score:**
   - `WITH docs avg` (MCP server access)
   - `WITHOUT docs avg` (pure LLM)
   - `delta = WITH - WITHOUT`

2. **Per-question breakdown:**
   - 5 dimensions: correctness, completeness, specificity, code_quality, actionability
   - Detailed reasoning for each score

### From `reports/*.md`:
1. **Summary statistics** (min/max/avg for WITH/WITHOUT/delta)
2. **Top 10 best WITH docs** (highest quality answers with MCP)
3. **Top 10 worst WITH docs** (where docs didn't help)
4. **Top 10 improvements** (docs helped most, sorted by delta)
5. **Top 10 degradations** (docs hurt most)
6. **Clustering by topic/persona** (which themes work well, which need doc fixes)
7. **Recommendations** (actionable next steps)

---

## Quick Example (Already Working)

Sample 10 questions:
```bash
.venv/bin/python cli.py report generate \
  --product oneTBB \
  --eval eval/oneTBB.sample10.rerank.json \
  --questions questions/oneTBB.sample10.json \
  --output reports/oneTBB.sample10.md
```

**Result:** `reports/oneTBB.sample10.md`
- Delta: **+0.4** (docs helped slightly)
- Top improvement: q_008 (+5.0 points with docs)
- Biggest degradation: q_004, q_011 (-4.0 points with docs)

---

## Full Pipeline (One-Liner Chain)

```bash
cd doc-benchmark && \
.venv/bin/python cli.py answers generate \
  --product oneTBB \
  --questions questions/oneTBB.json \
  --output answers/oneTBB.rerank.json \
  --model gpt-4o-mini \
  --provider openai \
  --top-k 5 \
  --rerank-threshold 0.3 && \
.venv/bin/python cli.py eval score \
  --product oneTBB \
  --answers answers/oneTBB.rerank.json \
  --output eval/oneTBB.rerank.json \
  --judge-model gpt-4o-mini \
  --judge-provider openai && \
.venv/bin/python cli.py report generate \
  --product oneTBB \
  --eval eval/oneTBB.rerank.json \
  --questions questions/oneTBB.json \
  --output reports/oneTBB.md && \
cat reports/oneTBB.md
```

---

## Output Files Summary

| File | Content |
|------|---------|
| `answers/*.json` | Generated answers (WITH + WITHOUT docs) + retrieval metadata |
| `eval/*.json` | Evaluation scores (per-question breakdown + aggregate stats) |
| `reports/*.md` | Human-readable analysis report (tables + recommendations) |

---

## Next Steps

1. **Full run completed?** Check `/tmp/answers_full.log` or poll process
2. **Review results:** Open `reports/oneTBB.md` 
3. **Identify doc gaps:** Look at "Bottom 10 degradations" section
4. **Apply to another project:** Replace `oneTBB` with your library

---

## Zero Manual Code Required ✅

Everything above runs via CLI commands. No Python scripting needed.
