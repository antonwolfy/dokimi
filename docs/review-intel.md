# Intel Product Perspective Review

**Date:** 2026-02-12  
**Reviewer:** Intel Advisor (product & organizational)

## Strengths

- Strategic value HIGH — AI agents becoming primary developer interface
- If agents can't answer Intel questions, Intel products become invisible
- APPROVE with modifications

## Persona Gaps (Critical)

Current 6 personas miss key user types:

| Missing Persona | Why Critical |
|----------------|-------------|
| **Migration/Interop Developer** | #1 use case for Intel adoption — CUDA→oneAPI, OpenMP→TBB |
| **CI/CD Engineer** | Tool integration is a major adoption blocker |

## Question Coverage (Rebalance Needed)

Current: likely over-indexes on API reference (~40%). AI agents already handle API lookups well.

**Recommended distribution:**
| Category | Current (est.) | Recommended |
|----------|---------------|-------------|
| API reference | ~40% | 15% |
| Integration/interop | ~10% | 22% |
| Error/troubleshooting | ~5% | 18% |
| Performance tuning | ~15% | 20% |
| Getting started | ~15% | 12% |
| Migration | ~5% | 13% |

## Known Documentation Problems (Per Product)

| Product | Known Issues |
|---------|-------------|
| **oneTBB** | Flow graph docs sparse, CMake integration scattered across multiple pages |
| **oneDNN** | Good API ref, terrible tutorials, framework integration (PyTorch/TF) barely exists |
| **oneMKL** | Interface vs binary confusion kills AI agents, unclear which to use when |
| **VTune/Advisor** | CLI docs are second-class citizens, metrics glossary missing |
| **All products** | "Quick Start → API Ref" cliff — no middle ground (tutorials, patterns, recipes) |

## Proprietary Products Approach

1. VTune/Advisor docs not on GitHub — need to scrape intel.com
2. Get legal approval first
3. Build Markdown converter for HTML docs
4. Ingest into Context7 (or custom pipeline)
5. Long-term: create public GitHub doc mirrors (enables community contributions)

## Report Format: Jira or Bust

Academic reports get filed and ignored. Product teams need:

- **Jira-ready action items** with named owners, effort estimates, deadlines
- **Severity** based on % questions failing in that category
- **Impact metric** — how many developer queries affected
- **Specific fix** — not "improve docs" but "add parallel_for example to Getting Started section"

**Recommended process:**
1. Pilot with one product (oneTBB) — prove ROI
2. Show results to product team, iterate on report format
3. Scale to other products

## Political/Organizational Concerns

**Turf war risk:** DevRel vs Engineering vs Tech Writers all claim doc ownership

**Mitigation:**
- Get VP-level exec sponsor before scaling
- Cross-functional tiger team (1 person from each)
- Central DevRel funding for infrastructure
- Frame as "helping teams" not "auditing teams"
- Tie to OKRs, show ROI via support ticket reduction

**Resistance points:**
- Tech writers feel audited → counter: this helps prioritize their work
- Eng teams say "no time for docs" → counter: better docs = fewer support tickets
- DevRel says "we already know what's broken" → counter: data-driven prioritization

## Scoring Improvements

"Specificity" is good but insufficient alone (prone to false positives from hallucinated Intel APIs).

**Add signals:**
- Code snippet density and runnability
- Cross-product reference accuracy
- Error code coverage
- Platform/version clarity
- Recency (outdated API versions)
