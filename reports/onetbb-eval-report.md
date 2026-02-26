# oneTBB Documentation Quality Evaluation Report

> **Date:** February 25, 2026  
> **Product:** [oneTBB](https://github.com/uxlfoundation/oneTBB) — oneAPI Threading Building Blocks  
> **Evaluation model (judge):** GPT-4o  
> **Answer model:** GPT-4o-mini  
> **Documentation source:** [Context7](https://context7.com) (`uxlfoundation/onetbb`)

---

## Executive Summary

We evaluated how much oneTBB documentation improves LLM-generated answers to 27 technical questions across 6 categories. Each question was answered **twice**: once with documentation context (Condition B) and once without (Condition A), then scored by GPT-4o across 5 quality criteria.

| | With Documentation | Without Documentation | Delta |
|---|---|---|---|
| **Average score (0–100)** | **85.3** | **82.6** | **+2.7** |
| Best question | 93 | 90 | +48 (on partitioners) |
| Worst question | 68 | 38 | –18 (Python bindings) |

**Bottom line:** Documentation provides a meaningful boost (+2.7 average), with exceptional value in performance-tuning topics (+9.2). The biggest gap is missing coverage of Python bindings.

---

## Methodology

### Experiment Design

```
┌─────────────────────────────────────────────────────────────────┐
│  For each question Q:                                            │
│                                                                  │
│  Condition A: LLM(Q)             → answer_A (no docs)           │
│                                                                  │
│  Condition B: Context7(Q) → docs                                │
│               LLM(Q + docs)      → answer_B (with docs)         │
│                                                                  │
│  Judge: GPT-4o scores answer_A and answer_B on 5 criteria       │
└─────────────────────────────────────────────────────────────────┘
```

### Question Design

27 questions were crafted across 6 categories, targeting realistic developer use cases:

| Category | # Questions | Description |
|---|---|---|
| `getting_started` | 3 | Installation, first parallel loop, core concepts |
| `api_reference` | 4 | Flow graph, concurrent containers, parallel_reduce |
| `integration` | 6 | CMake, Conan, vcpkg, OpenMP, std::execution, Python |
| `performance_tuning` | 5 | Grainsize, task_arena, NUMA, partitioners, profiling |
| `migration` | 4 | Legacy TBB → oneTBB, deprecated APIs, std::thread replacement |
| `troubleshooting` | 5 | Perf regressions, deadlocks, race conditions, profiling |

### Scoring Criteria

GPT-4o evaluates each answer on 5 dimensions (0–100 each), averaged to `aggregate`:

| Criterion | What it measures |
|---|---|
| **Correctness** | Factual accuracy |
| **Completeness** | Fully addresses the question |
| **Specificity** | oneTBB-specific (not generic C++ advice) |
| **Code Quality** | Code examples are correct and runnable |
| **Actionability** | User can apply the answer immediately |

---

## Results

### Overall Scores by Criterion

| Criterion | With Docs | Without Docs | Δ |
|---|---|---|---|
| Correctness | 84.6 | 82.8 | **+1.9** |
| Completeness | 88.5 | 86.3 | **+2.2** |
| **Specificity** | **81.3** | **76.9** | **+4.4** ← biggest gain |
| Code Quality | 83.3 | 81.3 | **+2.0** |
| Actionability | 88.9 | 85.9 | **+3.0** |
| **Aggregate** | **85.3** | **82.6** | **+2.7** |

> **Key insight:** Documentation most significantly improves *specificity* (+4.4) — the degree to which answers reference oneTBB APIs, patterns, and idioms rather than generic parallel programming advice.

---

### Results by Category

| Category | N | With Docs | Without Docs | Δ | Interpretation |
|---|---|---|---|---|---|
| `performance_tuning` | 5 | 86.0 | 76.8 | **+9.2** | 🏆 Docs are critical |
| `api_reference` | 4 | 85.2 | 82.5 | **+2.8** | Docs help with API details |
| `integration` | 6 | 84.2 | 82.3 | **+1.8** | Moderate benefit |
| `migration` | 4 | 86.0 | 84.8 | **+1.2** | Slight benefit |
| `troubleshooting` | 5 | 86.0 | 85.8 | **+0.2** | Model already knows patterns |
| `getting_started` | 3 | 84.7 | 85.0 | **−0.3** | Model knows basics well |

---

### Question-Level Results

#### ✅ Top 5: Documentation Helped Most

| Question | With | Without | Δ |
|---|---|---|---|
| What's the difference between `auto_partitioner`, `simple_partitioner`, and `affinity_partitioner`? | 86 | 38 | **+48** |
| Can I use oneTBB with `std::execution` parallel algorithms? | 86 | 73 | +13 |
| How do I implement parallel reduction (sum, min, max) using `parallel_reduce`? | 86 | 73 | +13 |
| How do I use oneTBB with Conan package manager? | 86 | 77 | +9 |
| How do I integrate oneTBB with CMake? | 93 | 86 | +7 |

> **Notable outlier:** The partitioners question shows a +48 delta — one of the most specific oneTBB topics where GPT-4o-mini without docs was severely underinformed (score 38/100).

#### ⚠️ Bottom 5: Documentation Hurt or Didn't Help

| Question | With | Without | Δ |
|---|---|---|---|
| How do I use oneTBB from a **Python** application? | 68 | 86 | **−18** |
| Differences between `concurrent_vector`, `concurrent_queue`, and `concurrent_hash_map`? | 83 | 90 | −7 |
| How do I install oneTBB on Ubuntu and verify the installation? | 81 | 86 | −5 |
| I'm migrating from legacy TBB (2020) to oneTBB. What are the breaking changes? | 85 | 89 | −4 |
| How do I optimize `parallel_for` grainsize? | 86 | 88 | −2 |

> **Notable gap:** The Python bindings question (−18) is the clearest documentation gap. The LLM knows more about Python parallel programming in general than what the oneTBB documentation currently covers on this topic in Context7's index.

---

## Key Findings

### Where Documentation Adds the Most Value

1. **Low-level performance tuning** (+9.2 avg): partitioner semantics, NUMA-aware algorithms, `task_arena` — topics where general knowledge is insufficient
2. **API specifics**: exact method signatures, behavior of concurrent containers, flow graph topology
3. **Integration recipes**: CMake snippets, Conan configuration — users need copy-paste-ready code

### Where Documentation Gap Exists

1. **Python bindings**: No useful Python documentation in Context7 index for oneTBB. The model's generic Python threading knowledge outperforms what's indexed.
2. **Installation/getting started**: GPT-4o-mini already knows Ubuntu package installation — documentation retrieval adds noise rather than signal.
3. **Migration guides**: The LLM's training data already contains migration advice; documentation is not significantly more helpful.

---

## Raw Data Summary

| Question ID | Category | With Docs | Without Docs | Δ |
|---|---|---|---|---|
| tbb-gs-01 | getting_started | 81 | 86 | −5 |
| tbb-gs-02 | getting_started | 86 | 86 | 0 |
| tbb-gs-03 | getting_started | 87 | 83 | +4 |
| tbb-api-01 | api_reference | 86 | 81 | +5 |
| tbb-api-02 | api_reference | 83 | 90 | −7 |
| tbb-api-03 | api_reference | 86 | 73 | +13 |
| tbb-api-04 | api_reference | 86 | 86 | 0 |
| tbb-int-01 | integration | 93 | 86 | +7 |
| tbb-int-02 | integration | 86 | 77 | +9 |
| tbb-int-03 | integration | 86 | 86 | 0 |
| tbb-int-04 | integration | 86 | 86 | 0 |
| tbb-int-05 | integration | 86 | 73 | +13 |
| tbb-int-06 | integration | 68 | 86 | −18 |
| tbb-perf-01 | performance_tuning | 86 | 88 | −2 |
| tbb-perf-02 | performance_tuning | 86 | 86 | 0 |
| tbb-perf-03 | performance_tuning | 86 | 86 | 0 |
| tbb-perf-04 | performance_tuning | 86 | 38 | +48 |
| tbb-perf-05 | performance_tuning | 86 | 66 | +20 |
| tbb-mig-01 | migration | 85 | 89 | −4 |
| tbb-mig-02 | migration | 86 | 79 | +7 |
| tbb-mig-03 | migration | 87 | 85 | +2 |
| tbb-mig-04 | migration | 86 | 86 | 0 |
| tbb-trouble-01 | troubleshooting | 86 | 86 | 0 |
| tbb-trouble-02 | troubleshooting | 86 | 85 | +1 |
| tbb-trouble-03 | troubleshooting | 86 | 86 | 0 |
| tbb-trouble-04 | troubleshooting | 86 | 86 | 0 |
| tbb-trouble-05 | troubleshooting | 86 | 86 | 0 |

---

## Recommendations

| Priority | Action | Category |
|---|---|---|
| 🔴 High | Add Python bindings documentation to oneTBB docs | Coverage gap |
| 🔴 High | Expand partitioner documentation — this is the biggest LLM knowledge gap | Quality |
| 🟡 Medium | Review concurrent container docs — the model currently outperforms docs here | Quality |
| 🟢 Low | Installation / getting-started content is adequate; model knowledge is sufficient | Maintenance |

---

## Tooling

This evaluation was produced by [doc-benchmark](https://github.com/napetrov/doc-benchmark) — an open framework for measuring documentation quality using LLM-as-judge methodology.

**Pipeline:**
1. `cli.py answers generate` — generates WITH/WITHOUT doc answers via GPT-4o-mini + Context7
2. `cli.py eval score` — judges all answers with GPT-4o (5 criteria, 0–100)
3. `cli.py report generate` — produces this report

---

*Generated by doc-benchmark · oneTBB · Feb 25, 2026*
