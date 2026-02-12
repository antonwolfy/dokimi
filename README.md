# Intel Documentation Quality Benchmark

Automated evaluation of Intel oneAPI documentation quality for AI agents and MCP servers.

## Problem

AI coding agents (Cursor, Claude, Copilot) are becoming primary consumers of technical documentation. Intel's docs were designed for humans → agents get generic/hallucinated code instead of Intel-optimized solutions.

**We need:** a systematic way to evaluate documentation quality, identify specific gaps, and give product teams actionable fix lists.

## Approach

Two evaluation tracks running in parallel:

### Track 1: Raw Documentation Scan
Evaluate if documentation structure is AI-agent friendly:
- Code blocks present and runnable
- API references complete with parameters/return types
- Version-specific tags (oneAPI 2024.2 vs 2025.0)
- No visual-only content (images without text alternatives)
- Modular chunks suitable for retrieval

### Track 2: MCP Output Quality
Evaluate what AI agents actually receive via MCP (Context7):
- Generate 100+ realistic questions per product
- Test LLM answers WITH docs vs WITHOUT docs
- Score on multiple dimensions
- Identify where docs fail to help

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Question Generation                       │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ML Engineer│  │HPC Dev   │  │Student   │  │AI Agent   │  │
│  │8 questions│  │8 questions│  │8 questions│  │8 questions│  │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬─────┘  │
│        └──────────┬──┴───────────┬──┘             │         │
│                   ▼              ▼                 ▼         │
│            ┌──────────────────────────┐                     │
│            │  ~48 questions/product   │                     │
│            └────────────┬────────────┘                     │
└─────────────────────────┼───────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Context7 API │  │  Raw Docs    │  │  RAGAS        │
│ fetch docs   │  │  Scanner     │  │  Eval Engine  │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       ▼                 ▼                 ▼
┌──────────────────────────────────────────────────┐
│                 LLM Evaluation                    │
│                                                  │
│  ┌────────────┐          ┌────────────┐          │
│  │Answer WITH │          │Answer W/O  │          │
│  │docs context│          │docs (base) │          │
│  └─────┬──────┘          └─────┬──────┘          │
│        └───────────┬───────────┘                 │
│                    ▼                             │
│           ┌───────────────┐                      │
│           │ Multi-dim     │                      │
│           │ Scoring       │                      │
│           │ • correctness │                      │
│           │ • completeness│                      │
│           │ • specificity │                      │
│           │ • code quality│                      │
│           │ • actionability│                     │
│           └───────┬───────┘                      │
└───────────────────┼──────────────────────────────┘
                    ▼
┌──────────────────────────────────────────────────┐
│              Gap Reports                          │
│                                                  │
│  Per-product:                                    │
│  • Score breakdown by dimension                  │
│  • Doc gaps by category (API, install, perf...)  │
│  • Hallucination risks                           │
│  • Per-persona weak spots                        │
│  • Actionable fix list for product team          │
└──────────────────────────────────────────────────┘
```

## Tech Stack

| Component | Tool | Why |
|-----------|------|-----|
| **Eval framework** | [RAGAS](https://github.com/explodinggradients/ragas) | Reference-free RAG metrics, synthetic Q generation, Python native |
| **Doc retrieval** | [Context7](https://context7.com) API | MCP-standard doc serving, already indexes oneAPI repos |
| **LLM for scoring** | Claude (internal) | Unlimited access, high quality evaluation |
| **Question generation** | Custom + RAGAS | Persona-based generation on top of RAGAS knowledge graphs |
| **Reporting** | Custom | Markdown + optional Sheets export |

### Why RAGAS?

- **Generates synthetic questions** from doc corpus via knowledge graphs (diverse: simple, reasoning, multi-hop)
- **Reference-free metrics** — no ground truth needed, evaluates from docs alone
- **Context precision/recall** — directly measures if docs cover what's needed
- **Faithfulness** — catches hallucinations when docs are missing
- **Python native** (`pip install ragas`)

### Why not just Context7's built-in benchmark?

Context7 generates ~10-15 generic questions per library. We need:
- 100+ questions with persona-specific angles
- Multi-dimensional scoring (not just "can it answer?")
- Gap categorization (API coverage, install, performance, migration...)
- Comparative analysis (with docs vs without)
- Actionable reports per product team

## Products in Scope

### Open Source (via Context7)
| Product | Context7 ID | Status |
|---------|-------------|--------|
| oneTBB | uxlfoundation/onetbb | ✅ 290K tokens, 853 snippets |
| oneDNN | uxlfoundation/onednn | ✅ 411K tokens, 941 snippets |
| oneDAL | TBD | ❓ Check availability |
| scikit-learn-intelex | TBD | ❓ Check availability |
| Intel Distribution for Python | TBD | ❓ Check availability |
| optimization-zone | intel/optimization-zone | ✅ 32K tokens, 295 snippets |

### Proprietary (Custom MCP needed)
| Product | Notes |
|---------|-------|
| Intel MKL (binary) | Not on Context7, needs custom ingestion |
| VTune Profiler | Proprietary docs |
| Intel Advisor | Proprietary docs |

## Personas

| Persona | Focus Areas | Difficulty Mix |
|---------|-------------|----------------|
| **ML Engineer** | PyTorch/TF integration, training optimization, batch processing | 2B + 3I + 3A |
| **HPC Developer** | Parallel algorithms, NUMA, vectorization, memory mgmt | 2B + 3I + 3A |
| **CS Student** | Getting started, basic examples, installation, concepts | 2B + 3I + 3A |
| **DevOps Engineer** | Install, config, env vars, Docker, monitoring | 2B + 3I + 3A |
| **Migration Engineer** | CUDA→oneAPI, OpenMP→TBB, API mapping, interop | 2B + 3I + 3A |
| **AI Coding Agent** | API refs, code snippets, best practices, error handling | 2B + 3I + 3A |

*B=Beginner, I=Intermediate, A=Advanced. 8 questions per persona × 6 personas = 48 questions per product.*

## Scoring Dimensions

| Dimension | What it measures | Scale |
|-----------|-----------------|-------|
| **Correctness** | Are facts, APIs, code examples accurate? | 0-100 |
| **Completeness** | Does answer cover expected topics? | 0-100 |
| **Specificity** | Intel-specific APIs/functions vs generic advice? | 0-100 |
| **Code Quality** | Working, idiomatic, copy-paste ready? | 0-100 |
| **Actionability** | Can developer immediately use this? | 0-100 |

Plus RAGAS metrics:
- **Context Precision** — are relevant doc chunks retrieved?
- **Context Recall** — do docs cover what's needed?
- **Faithfulness** — does answer stick to doc facts?

## Output: Gap Reports

Each product team gets:
1. **Score card** — overall and per-dimension scores
2. **Gap list** — specific missing documentation, categorized
3. **Hallucination risks** — where LLMs make up Intel APIs
4. **Persona pain points** — which user types are worst served
5. **Priority fixes** — ranked by impact

## Development Plan

- [ ] **Phase 1:** Setup & pilot (oneTBB)
  - [ ] RAGAS integration
  - [ ] Context7 API connector
  - [ ] Persona question generator
  - [ ] Scoring pipeline
  - [ ] Run pilot on oneTBB, validate methodology
- [ ] **Phase 2:** Scale to all products
  - [ ] Run benchmarks for oneDNN, oneDAL, scikit-learn-intelex
  - [ ] Add raw doc scanner (Track 1)
  - [ ] Generate per-team reports
- [ ] **Phase 3:** Automation & CI
  - [ ] Scheduled re-runs (track quality over time)
  - [ ] Dashboard or summary notifications
  - [ ] Integration with doc build pipelines

## Setup

```bash
pip install ragas datasets openai anthropic
# or
pip install -r requirements.txt
```

## Usage

```bash
# Run benchmark for a single product
python benchmark.py oneTBB

# Run all products
python benchmark.py

# Generate report only (from existing results)
python report.py results/
```

## License

Internal Intel use.
