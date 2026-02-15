# Intel Documentation Benchmark - oneDAL & oneTBB Full Results

## Summary

This benchmark evaluates documentation quality for Intel oneAPI libraries by comparing LLM answer quality with and without documentation context from Context7.

**Libraries Tested:**
- **oneDAL** (oneAPI Data Analytics Library) - 27 questions
- **oneTBB** (Threading Building Blocks) - 27 questions

**Test Configuration:**
- Answer Model: `gpt-4o-mini` (OpenAI)
- Scorer Model: `deepseek-chat` (Deepseek V3)
  - Note: Originally planned to use `claude-sonnet-4-20250514`, but switched to Deepseek due to insufficient Anthropic API credits
- Documentation Sources:
  - Baseline: LLM knowledge only (no docs)
  - Context7: oneDAL at `oneapi-src/onedal`, oneTBB at `uxlfoundation/onetbb`

## Questions Created

### oneDAL Question Set (27 questions)

Covers critical oneDAL use cases with known documentation gaps:

**Distribution:**
- Getting Started (3): installation, hello-world, interface overview
- Integration (6): sklearnex patching, scikit-learn compatibility, Spark, pandas/numpy interop, daal4py vs sklearnex, DPC++/SYCL
- Performance Tuning (5): GPU offload, batch modes, threading, memory layout (homogen vs SOA), profiling
- Troubleshooting (5): patch verification, accuracy differences, OOM/online learning, GPU diagnostics, thread safety
- API Reference (4): table types, algorithm parameters (K-Means, PCA), train/infer workflow
- Migration (4): DAAL→oneDAL, daal4py→sklearnex, deprecations, scikit-learn adoption

**Known Documentation Issues Tested:**
- sklearnex patching documentation scattered
- GPU support matrix unclear
- Distributed mode documentation minimal
- Online learning API poorly documented
- daal4py vs sklearnex vs oneDAL C++ layering confusing
- DAAL→oneDAL migration guide incomplete

## Benchmark Runs

All benchmarks running sequentially (estimated 60-90 minutes total):

1. ✅ **oneDAL Baseline** - completed
2. ⏳ **oneDAL Context7** - running
3. ⏳ **oneTBB Baseline** - queued
4. ⏳ **oneTBB Context7** - queued

## Scoring Rubric

Each answer scored on 5 dimensions (1-20 each, max 100):

1. **Correctness** (20): Factual accuracy, correct APIs, working code
2. **Completeness** (20): Covers all expected topics
3. **Specificity** (20): Library-specific APIs vs generic advice
4. **Code Quality** (20): Working, idiomatic, copy-paste ready
5. **Actionability** (20): Immediately usable solution

## Expected Insights

### Key Questions to Answer:
1. Does Context7 documentation improve answer quality?
2. How much improvement (if any) by dimension?
3. Are there specific categories where documentation helps more? (e.g., API Reference vs Getting Started)
4. Does Deepseek V3 scorer provide meaningful discrimination vs GPT-4o-mini?
5. Are the known documentation gaps reflected in the scores?

### Hypothesis:
- **Context7 should improve:**
  - Specificity (exact API names, parameters)
  - Correctness (current APIs, not deprecated)
  - Code Quality (real examples from docs)
  
- **Baseline may still do well on:**
  - Getting Started (general patterns)
  - Conceptual questions (architecture, when to use)
  
- **Troubleshooting category** likely shows biggest gap
  - Known issues, workarounds typically only in docs
  - Generic LLM knowledge won't have specifics

## Results Location

After completion:
```
results/
├── onedal/
│   ├── baseline/
│   │   ├── results.json
│   │   └── report.md
│   └── context7/
│       ├── results.json
│       └── report.md
└── onetbb_full/
    ├── baseline/
    │   ├── results.json
    │   └── report.md
    └── context7/
        ├── results.json
        └── report.md
```

## Changes Made

1. **Created** `questions/onedal.json` - 27-question benchmark covering oneDAL use cases
2. **Modified** `benchmark.py`:
   - Added Anthropic SDK support (for future use)
   - Switched scorer from GPT-4o-mini to Deepseek V3 (cost: $0.14/1M input, $0.28/1M output)
   - Updated default scorer model in CLI arguments
   - Made client detection work for both OpenAI and Anthropic APIs
3. **Created** automation script for running all benchmarks sequentially

## Next Steps

Once benchmarks complete:
1. Analyze full scoring tables
2. Compare baseline vs context7 performance by category
3. Identify specific documentation gaps causing low scores
4. Generate executive summary with key findings
5. Commit all results and push to `feature/mvp-benchmark`
