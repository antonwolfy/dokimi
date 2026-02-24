# Orchestrator: One-Command Evaluation

## Quick Start

Evaluate documentation quality for any project with a single command:

```bash
.venv/bin/python cli.py evaluate \
  --product oneDNN \
  --repo oneapi-src/oneDNN
```

This runs the full pipeline:
1. **Discover personas** from GitHub repo analysis
2. **Generate questions** from personas + topics
3. **Merge custom questions** (if provided via `--custom-questions`)
4. **Deduplicate** with source tracking
5. **Generate answers** (WITH docs via MCP + WITHOUT docs baseline)
6. **Evaluate quality** (LLM-as-judge scoring)
7. **Generate report** (analysis, clustering, recommendations)

## Output

All results saved to current directory (or `--output-dir`):

```text
personas/oneDNN.json       # Discovered user personas
questions/oneDNN.json      # Generated + custom questions (deduplicated)
answers/oneDNN.json        # WITH/WITHOUT answers
eval/oneDNN.json          # Evaluation scores
reports/oneDNN.md         # Final analysis report
```

## Custom Questions

Add manual questions to test specific scenarios:

```bash
.venv/bin/python cli.py evaluate \
  --product mylib \
  --repo org/mylib \
  --custom-questions my_questions.json
```

**Format for `my_questions.json`:**
```json
{
  "questions": [
    {
      "id": "manual_001",
      "text": "How do I configure X for production?",
      "persona_id": "manual"
    }
  ]
}
```

Custom questions are merged with generated ones and deduplicated.

## Source Tracking

Each question tracks its origin:

```json
{
  "id": "q_001",
  "text": "How do I...",
  "source_type": "generated" | "manual",
  "persona_id": "performance_engineer"
}
```

- `generated`: Created by LLM from persona + topics
- `manual`: Loaded from `--custom-questions`

## Advanced Options

```bash
.venv/bin/python cli.py evaluate \
  --product mylib \
  --repo org/mylib \
  --model gpt-4o \                    # Better quality (more expensive)
  --judge-model claude-sonnet-4 \     # Different judge to avoid bias
  --personas-count 8 \                # More diverse personas
  --questions-per-topic 3 \           # More questions
  --top-k 10 \                        # Retrieve more docs
  --rerank-threshold 0.5 \            # Stricter relevance filter
  --debug-retrieval                   # Include metadata for debugging
```

## Example: Full Run

```bash
# Evaluate oneDNN documentation
.venv/bin/python cli.py evaluate \
  --product oneDNN \
  --repo oneapi-src/oneDNN

# View results
cat reports/oneDNN.md
```

**Output:**
```text
Starting full evaluation pipeline for oneDNN
Repository: oneapi-src/oneDNN
Output directory: .

✓ Discovered 5 personas
✓ Generated 47 questions from personas
✓ Merged to 47 unique questions (47 generated, 0 manual)
✓ Generated answers for 47 questions
✓ Evaluated 47 answers: WITH=85.3, WITHOUT=84.1, delta=+1.2
✓ Generated report: reports/oneDNN.md

================================================================================
✅ Pipeline completed successfully!
================================================================================

Output files:
  Personas:   personas/oneDNN.json
  Questions:  questions/oneDNN.json
  Answers:    answers/oneDNN.json
  Evaluation: eval/oneDNN.json
  Report:     reports/oneDNN.md

Results:
  WITH docs avg:    85.3
  WITHOUT docs avg: 84.1
  Delta:            +1.2

📊 View full report: cat reports/oneDNN.md
```

## Comparison with Manual Steps

**Before (6 commands):**
```bash
python cli.py personas discover --product X --repo Y
python cli.py questions generate --product X --personas personas/X.json
python cli.py answers generate --product X --questions questions/X.json
python cli.py eval score --product X --answers answers/X.json
python cli.py report generate --product X --eval eval/X.json --questions questions/X.json
```

**Now (1 command):**
```bash
python cli.py evaluate --product X --repo Y
```

## Pipeline Architecture

```text
GitHub Repo
    ↓
Persona Discovery (analyze repo structure, README, issues)
    ↓
Topic Extraction (RAGAS seed topics from docs)
    ↓
Question Generation (LLM generates from persona × topics)
    ↓
[Optional] Merge Custom Questions
    ↓
Deduplication (with source tracking)
    ↓
Answer Generation (WITH docs via MCP, WITHOUT docs baseline)
    ↓
Evaluation (LLM-as-judge scores on 5 dimensions)
    ↓
Report Generation (clustering, analysis, recommendations)
    ↓
reports/PRODUCT.md (actionable insights)
```

## Next Steps

After running evaluation:

1. **Review report:** `cat reports/PRODUCT.md`
2. **Identify gaps:** Check "Bottom 10 degradations" section
3. **Fix docs:** Focus on topics with negative delta
4. **Re-run:** Verify improvements

---

See `QUICKSTART.md` for more examples and `RETRIEVAL_IMPROVEMENTS.md` for technical details.
