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
| **LLM for answering** | gpt-4o-mini or Claude | Generate answers with/without docs |
| **LLM for scoring** | Claude (different from answering model) | Eliminates self-evaluation bias |
| **Question generation** | Custom + RAGAS | Persona-based generation on top of RAGAS knowledge graphs |
| **Reporting** | Custom | Jira-ready action items + markdown summary |

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
| **DevOps/CI Engineer** | Install, config, env vars, Docker, CI/CD integration, monitoring | 2B + 3I + 3A |
| **Migration Engineer** | CUDA→oneAPI, OpenMP→TBB, std::thread→TBB, API mapping, interop | 2B + 3I + 3A |
| **AI Coding Agent** | API refs, code snippets, best practices, error handling | 2B + 3I + 3A |
| **Troubleshooter** | Error messages, debugging, performance regression, common pitfalls | 2B + 3I + 3A |
| **Framework Integrator** | Using Intel libs inside PyTorch/TF/JAX/ONNX, plugin architecture | 2B + 3I + 3A |

*B=Beginner, I=Intermediate, A=Advanced. 8 questions per persona × 8 personas = 64 questions per product.*

### Question Category Distribution

Target distribution to avoid over-indexing on API reference:

| Category | Target % | Rationale |
|----------|----------|-----------|
| Integration/interop | 22% | #1 adoption driver, AI agents struggle here |
| Performance tuning | 20% | Core Intel value prop |
| Error/troubleshooting | 18% | Most common real-world queries |
| API reference | 15% | AI agents already handle well from training data |
| Migration | 13% | Key for CUDA→oneAPI conversion |
| Getting started | 12% | Important for students/new users |

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

Each product team gets **Jira-ready action items**, not academic reports:

1. **Score card** — overall and per-dimension scores
2. **Gap list** — specific missing documentation with severity (% questions failing)
3. **Hallucination risks** — where LLMs make up Intel APIs (high severity)
4. **Persona pain points** — which user types are worst served
5. **Priority fixes** — ranked by impact, with specific fix description (e.g., "Add parallel_for example to Getting Started section"), effort estimate, suggested owner

### Report Example
```
## oneTBB: Score 67/100

### Top Issue: Flow Graph Examples Missing (8 questions failed)
- Severity: HIGH (affects 3 personas)
- Example query: "How do I build a data flow pipeline with oneTBB?"
- Retrieved context: [2 snippets, low relevance]
- Fix: Add flow graph tutorial with producer-consumer example
- Effort: 2-3 days
- Owner: TBB doc team
```

### Known Documentation Problems (Pre-existing)

| Product | Known Issues |
|---------|-------------|
| oneTBB | Flow graph docs sparse, CMake integration scattered |
| oneDNN | Good API ref, poor tutorials, framework integration barely documented |
| oneMKL | Interface vs binary confusion, unclear which to use when |
| VTune/Advisor | CLI docs second-class, metrics glossary missing |
| All products | "Quick Start → API Ref" cliff with no middle ground |

## Architecture Decisions

### Separate Generation and Evaluation Models
Use different LLMs for answering questions vs scoring answers. Prevents self-evaluation bias where a model rates its own style favorably.

### Retrieval Quality Validation
Before scoring answers, validate that Context7 returned relevant context. Flag cases where retrieval failed — don't blame docs for retrieval problems. Store all retrieved context for audit trail.

### RAGAS: Hybrid Approach
- RAGAS for retrieval quality metrics (context precision, context recall)
- Custom LLM-as-judge for answer quality (correctness, specificity, actionability)
- RAGAS requires specific data formats; use selectively, not as monolith

### Caching Layer
Cache Context7 responses locally (keyed by product + query). Reduces API calls during iterative testing, enables offline development.

### Full Artifact Storage
Every run stores: raw LLM responses, retrieved context, prompt templates, model configs, token counts. Enables auditing and dispute resolution.

## Development Plan

- [ ] **Phase 1:** Setup & pilot (oneTBB)
  - [ ] Context7 API connector with retry/cache
  - [ ] Persona question generator (8 personas × 8 questions)
  - [ ] Separate answering model from scoring model
  - [ ] Retrieval relevance validation
  - [ ] Full artifact storage (raw responses, context, prompts)
  - [ ] RAGAS integration (context precision/recall)
  - [ ] Scoring pipeline with cost tracking
  - [ ] Run pilot on oneTBB, validate scores against known doc issues
  - [ ] Create 5-10 gold standard Q&A for scorer calibration
- [ ] **Phase 2:** Track 1 — Raw Doc Scanner
  - [ ] Define structural metrics (code blocks, API completeness, version tags, link validity)
  - [ ] Implement scanner (Vale/markdownlint + custom checks)
  - [ ] Correlate structural issues with answer quality issues
- [ ] **Phase 3:** Scale to all products
  - [ ] Run benchmarks for oneDNN, oneDAL, scikit-learn-intelex
  - [ ] Solve proprietary doc ingestion (MKL, VTune, Advisor) — legal approval needed
  - [ ] Generate Jira-ready per-team reports
  - [ ] Pilot report with oneTBB team, iterate format
- [ ] **Phase 4:** Automation & CI
  - [ ] Scheduled re-runs (track quality over time)
  - [ ] Dashboard or summary notifications
  - [ ] Integration with doc build pipelines

## Organizational Prerequisites

- [ ] **VP-level exec sponsor** — needed before scaling beyond pilot
- [ ] **Legal approval** for proprietary doc scraping (VTune, Advisor, MKL binary)
- [ ] **Cross-functional alignment** — DevRel, Eng, Tech Writers (frame as "helping prioritize" not "auditing")
- [ ] **Pilot buy-in** from oneTBB team

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

## Docs benchmark MVP runner (Task 2)

Run:
```bash
python cli.py run --root . --spec benchmarks/spec.v1.yaml \
  --out-json baselines/current.json --out-md reports/current.md
```

Create baseline once:
```bash
cp baselines/current.json baselines/baseline.json
```

Compare:
```bash
python cli.py compare --base baselines/baseline.json --candidate baselines/current.json \
  --out-json reports/compare.json --out-md reports/compare.md
```

MVP metrics: `coverage`, `freshness_lite`, `readability`.
