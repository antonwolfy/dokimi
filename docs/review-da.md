# Technical Architecture Review (Devils Advocate)

**Date:** 2026-02-12  
**Reviewer:** Devils Advocate (architecture & methodology)

## Strengths

- Two-track approach (raw doc scan + MCP output quality) addresses different aspects
- Persona-driven testing mirrors real-world usage patterns
- Baseline comparison (with/without docs) is a proper control group

## Critical Issues

### P0: Self-Evaluation Bias
Same model (gpt-4o-mini) generates answers AND scores them. Creates circular validation — model rates its own style favorably.

**Fix:** Use different model for scoring (Claude). Run one product through both scorers, measure agreement. If <80% agreement, recalibrate rubric.

### P1: Track 1 Undefined
"Raw Documentation Scan" has zero implementation. Without structural metrics, can't correlate doc structure issues with answer quality.

**Fix:** Define 5-10 concrete metrics: code block count/density, API parameter completeness, link validity, version tags, section depth, example coverage.

### P2: Retrieval vs Documentation Conflation
If Context7 returns irrelevant docs for a query, we score poorly but blame docs when it's a retrieval problem.

**Fix:** Log retrieved context. Add relevance check (keyword overlap or cosine similarity). Flag low-relevance cases separately.

### P3: No Reproducibility
Not storing raw LLM responses, retrieved context, prompt versions. If product team disputes a score — nothing to show.

**Fix:** Store everything: raw responses, retrieved context, prompt templates (versioned), model configs.

## Additional Concerns

- **RAGAS:** Claimed but not integrated. Recommend hybrid: RAGAS for retrieval quality, LLM-judge for answer quality
- **Context7 API:** No retry logic, no caching, no fallback. Single point of failure
- **Cost tracking:** No instrumentation. ~1,536 LLM calls per full run — need budget alerts
- **Report format:** Too abstract for product teams. Need specific failed questions with context, not just aggregate scores
- **Question de-duplication:** 48 questions may have redundancy across personas

## Recommendations

1. Separate generation model from evaluation model
2. Add Context7 retry/cache layer
3. Version control all prompts as files
4. Define Track 1 with concrete metrics
5. Add retrieval quality validation
6. Create 5-10 gold standard answers per product for scorer calibration
7. Instrument all API calls with token counts and cost
8. Drill-down reports with specific examples and fix suggestions
