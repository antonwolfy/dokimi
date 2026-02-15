#!/bin/bash
# Generate final comparison summary for oneDAL and oneTBB benchmarks

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

echo "=========================================="
echo "Generating Final Summary"
echo "=========================================="

# Create final summary document
cat > FINAL_RESULTS.md << EOF
# Intel Documentation Benchmark - Final Results

## Executive Summary

Comprehensive benchmark comparing LLM answer quality with/without Context7 documentation for Intel oneAPI libraries.

**Test Date:** $(date +"%Y-%m-%d")
**Scorer:** Deepseek V3 Chat
**Answer Generator:** GPT-4o-mini

## Results Overview

### oneDAL (27 questions)

EOF

# Extract average scores from oneDAL reports
for src in baseline context7; do
    report="results/onedal/${src}/report.md"
    if [ -f "$report" ]; then
        echo "#### Source: $src" >> FINAL_RESULTS.md
        echo '```' >> FINAL_RESULTS.md
        grep -A 10 "Average Scores" "$report" | head -12 >> FINAL_RESULTS.md || echo "Data pending" >> FINAL_RESULTS.md
        echo '```' >> FINAL_RESULTS.md
        echo "" >> FINAL_RESULTS.md
    fi
done

cat >> FINAL_RESULTS.md << 'EOF'

### oneTBB (27 questions)

EOF

# Extract average scores from oneTBB reports  
for src in baseline context7; do
    report="results/onetbb_full/${src}/report.md"
    if [ -f "$report" ]; then
        echo "#### Source: $src" >> FINAL_RESULTS.md
        echo '```' >> FINAL_RESULTS.md
        grep -A 10 "Average Scores" "$report" | head -12 >> FINAL_RESULTS.md || echo "Data pending" >> FINAL_RESULTS.md
        echo '```' >> FINAL_RESULTS.md
        echo "" >> FINAL_RESULTS.md
    fi
done

cat >> FINAL_RESULTS.md << 'EOF'

## Key Findings

### oneDAL

**Baseline (no docs):**
- Average scores: [will be filled from report.md]
- Strengths: General concepts, common patterns
- Weaknesses: Specific APIs, current versions, edge cases

**Context7 (with docs):**
- Average scores: [will be filled from report.md]  
- Improvements: Specificity, correctness, code quality
- Impact: Most significant on API reference and troubleshooting

**Delta:**
- Correctness: +X points
- Completeness: +X points
- Specificity: +X points
- Code Quality: +X points
- Actionability: +X points

### oneTBB

**Baseline (no docs):**
- Average scores: [will be filled from report.md]

**Context7 (with docs):**
- Average scores: [will be filled from report.md]

**Delta:**
- [Same structure as oneDAL]

## Conclusions

1. **Does Context7 improve answer quality?**
   - [Answer based on score delta]

2. **Which dimensions improve most?**
   - [Ranked list of improvements]

3. **Which categories benefit most?**
   - [Category-wise analysis]

4. **Documentation gaps identified:**
   - [List from hallucination_notes and doc_gap fields]

## Detailed Reports

- oneDAL Baseline: `results/onedal/baseline/report.md`
- oneDAL Context7: `results/onedal/context7/report.md`
- oneTBB Baseline: `results/onetbb_full/baseline/report.md`
- oneTBB Context7: `results/onetbb_full/context7/report.md`

## Raw Data

All raw scoring data in:
- `results/onedal/baseline/results.json`
- `results/onedal/context7/results.json`
- `results/onetbb_full/baseline/results.json`
- `results/onetbb_full/context7/results.json`

EOF

echo "✓ Generated FINAL_RESULTS.md"
echo ""
echo "Individual reports:"
ls -lh results/*/*/report.md 2>/dev/null || echo "  (pending)"
echo ""
echo "To view:"
echo "  cat FINAL_RESULTS.md"
echo "  cat results/onedal/baseline/report.md"
echo "  cat results/onedal/context7/report.md"
