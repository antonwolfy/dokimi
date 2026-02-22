# RUNBOOK: Doc Quality Evaluation Pipeline

**Quick start guide for running the full pipeline**

---

## Prerequisites

### 1. API Keys (Required)

```bash
# OpenAI (for question generation & answering)
export OPENAI_API_KEY="sk-..."

# Anthropic (for judging - separate model to avoid bias)
export ANTHROPIC_API_KEY="sk-ant-..."

# GitHub (optional - increases rate limit from 60 to 5000/hour)
export GITHUB_TOKEN="ghp_..."
```

### 2. Install Dependencies

```bash
cd doc-benchmark
pip install -r requirements.txt

# Installs:
# - langchain-openai, langchain-anthropic (LLM orchestration)
# - openai (embeddings for deduplication)
# - PyGithub (optional, gh CLI fallback works)
# - httpx (Context7 MCP client)
# - numpy (optional, exact-match fallback works)
# - ragas (topic extraction)
```

---

## Pipeline Steps

### Step 1: Discover Personas

```bash
python cli.py personas discover \
  --product oneTBB \
  --repo uxlfoundation/oneTBB \
  --count 5 \
  --save-analysis
```

**Output:** `personas/oneTBB.json`

**What it does:**
- Analyzes GitHub repo (README, issues, API patterns)
- Generates 5-8 user personas via LLM
- Each persona has: id, name, description, skill_level, concerns, typical_questions

**Review & edit:**
```bash
cat personas/oneTBB.json
# Edit if needed: add/remove/adjust personas
vim personas/oneTBB.json
```

**Approve:**
```bash
python cli.py personas approve --file personas/oneTBB.json
```

---

### Step 2: Generate Questions

```bash
python cli.py questions generate \
  --product oneTBB \
  --personas personas/oneTBB.json \
  --count 2 \
  --validate \
  --model gpt-4o-mini
```

**Output:** `questions/oneTBB.json`

**What it does:**
1. Extracts seed topics from docs (via Context7)
2. Generates questions per persona × topic
3. Validates questions (LLM scoring, threshold 60/100)
4. Deduplicates via embeddings (similarity > 0.85)
5. Merges personas for duplicate questions

**Expected result:** 30-50 unique validated questions

**Review:**
```bash
cat questions/oneTBB.json | jq '.questions[] | {id, text, personas, validation_score}'
```

---

### Step 3: Generate Answers

```bash
python cli.py answers generate \
  --product oneTBB \
  --questions questions/oneTBB.json \
  --model gpt-4o \
  --max-tokens 4000
```

**Output:** `answers/oneTBB.json`

**What it does:**
- For each question:
  - **WITH docs:** Context7 retrieves relevant docs → LLM answers with context
  - **WITHOUT docs:** LLM answers from knowledge only (baseline)

**Timeline:** ~10 minutes for 35 questions (70 LLM calls)

**Cost estimate:** ~$5 (gpt-4o)

**Review:**
```bash
# See answer pairs
cat answers/oneTBB.json | jq '.answers[0]'

# Compare WITH vs WITHOUT
cat answers/oneTBB.json | jq '.answers[] | {id: .question_id, with: .with_docs.answer[:100], without: .without_docs.answer[:100]}'
```

---

### Step 4: Evaluate Answers

```bash
python cli.py eval score \
  --product oneTBB \
  --answers answers/oneTBB.json \
  --judge-model claude-sonnet-4 \
  --judge-provider anthropic
```

**Output:** `eval/oneTBB.json`

**What it does:**
- LLM-as-judge scores each answer on 5 dimensions (0-100):
  1. **Correctness** — factually accurate?
  2. **Completeness** — fully addresses question?
  3. **Specificity** — oneTBB-specific vs generic?
  4. **Code Quality** — if code included, is it correct?
  5. **Actionability** — can user apply immediately?
- Calculates aggregate (average of 5)
- Calculates delta (WITH docs - WITHOUT docs)

**Timeline:** ~10 minutes for 35 questions (70 judge calls)

**Cost estimate:** ~$7 (claude-sonnet-4)

**Review:**
```bash
# Summary stats
cat eval/oneTBB.json | jq '{
  with_avg: [.evaluations[].with_docs.aggregate] | add/length,
  without_avg: [.evaluations[].without_docs.aggregate] | add/length,
  delta_avg: [.evaluations[].delta] | add/length
}'

# Find doc gaps (where WITH < 70)
cat eval/oneTBB.json | jq '.evaluations[] | select(.with_docs.aggregate < 70) | {id: .question_id, score: .with_docs.aggregate, question: .question_text}'

# Find hallucination risks (WHERE WITHOUT high but wrong)
cat eval/oneTBB.json | jq '.evaluations[] | select(.without_docs.aggregate > 75 and .delta > 20) | {id: .question_id, without: .without_docs.aggregate, delta}'
```

---

## Quick Run (All Steps)

```bash
# Set API keys first!
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."

# Run full pipeline
PRODUCT=oneTBB
REPO=uxlfoundation/oneTBB

python cli.py personas discover --product $PRODUCT --repo $REPO --count 5
python cli.py personas approve --file personas/$PRODUCT.json

python cli.py questions generate --product $PRODUCT --personas personas/$PRODUCT.json --validate

python cli.py answers generate --product $PRODUCT --questions questions/$PRODUCT.json --model gpt-4o

python cli.py eval score --product $PRODUCT --answers answers/$PRODUCT.json --judge-model claude-sonnet-4

# View results
echo "Personas: $(jq '.personas | length' personas/$PRODUCT.json)"
echo "Questions: $(jq '.questions | length' questions/$PRODUCT.json)"
echo "Evaluations: $(jq '.evaluations | length' eval/$PRODUCT.json)"
```

---

## Troubleshooting

### "No module named langchain"
```bash
pip install langchain-openai langchain-anthropic
```

### "No module named numpy"
Pipeline still works - falls back to exact text match deduplication.
```bash
pip install numpy  # Optional
```

### "GitHub client not available"
Pipeline still works - uses `gh` CLI fallback.
```bash
pip install PyGithub  # Optional
```

### "Context7 timeout"
Increase timeout in `config/products.yaml`:
```yaml
context7:
  timeout: 60  # seconds
```

### Rate limiting
- OpenAI: default 10K TPM on gpt-4o
- Anthropic: default 10K TPM on claude-sonnet
- GitHub: 60/hour unauthenticated, 5K/hour with token

Add delays between calls if needed.

---

## Output Files

```
personas/oneTBB.json      # 5-8 user personas
questions/oneTBB.json     # 30-50 validated questions
answers/oneTBB.json       # WITH/WITHOUT answer pairs
eval/oneTBB.json          # Scores + deltas
```

---

## Cost Estimation

**For 35 questions:**
- Persona discovery: $0.50 (gpt-4o-mini)
- Question generation: $0.50 (gpt-4o-mini)
- Answer generation: $5 (gpt-4o, 70 calls)
- Evaluation: $7 (claude-sonnet-4, 70 calls)
- **Total: ~$13**

Scale linearly with question count.

---

## Next Steps (Optional)

### Phase 5: Report Generation (Not Yet Implemented)

```bash
# TODO: Aggregate and visualize results
python cli.py report llm-eval \
  --eval eval/oneTBB.json \
  --personas personas/oneTBB.json \
  --output reports/oneTBB_report.json
```

Would include:
- Per-persona breakdown
- Per-dimension heatmaps
- Doc gap analysis
- Hallucination risk matrix
- Recommendations

---

**Last updated:** 2026-02-22  
**Version:** Phase 0-4 complete
