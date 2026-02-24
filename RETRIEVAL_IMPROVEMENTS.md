# Retrieval Improvements Plan

## Problem Summary

Current pipeline retrieves **1 chunk per question** from Context7, often with weak relevance:
- Avg delta (WITH - WITHOUT): **-0.8** (docs hurt quality)
- Low-relevance examples anchor the model poorly
- No fallback when retrieval misses

**Root cause:** Single-shot retrieval without quality control.

---

## Proposed Improvements

### 1. Top-K Retrieval (Priority: HIGH)

**Current:** 1 chunk  
**Target:** 3-5 chunks with ranking

**Files to modify:**
- `doc_benchmarks/eval/answerer.py`
  - `_retrieve_docs()`: request top_k=5 from Context7
  - Add parameter `top_k: int = 5`
  
**Implementation:**
```python
def _retrieve_docs(self, library_id, question, max_tokens, top_k=5):
    docs = self.mcp_client.get_library_docs(
        library_id=library_id,
        query=question,
        max_tokens=max_tokens,
        top_k=top_k  # NEW
    )
    return docs  # Now returns 5 chunks instead of 1
```

**Context7 MCP support:** Check if `get_library_docs()` already supports `top_k` or if we need to call it N times.

---

### 2. Relevance Scoring & Reranking (Priority: HIGH)

**Goal:** Score each chunk's relevance to the question, keep only good matches.

**Files to add:**
- `doc_benchmarks/eval/reranker.py`

**Implementation:**
```python
from typing import List, Dict, Any
import re

class SimpleReranker:
    """Rerank retrieved docs by lexical + semantic overlap."""
    
    def __init__(self, threshold: float = 0.3):
        self.threshold = threshold
    
    def score_relevance(self, question: str, doc_snippet: str) -> float:
        """
        Score 0-1 based on:
        - Lexical overlap (keywords)
        - Length penalty (too short = bad)
        - Code presence bonus (if question mentions code)
        """
        q_tokens = set(self._tokenize(question))
        d_tokens = set(self._tokenize(doc_snippet))
        
        overlap = len(q_tokens & d_tokens) / max(len(q_tokens), 1)
        length_score = min(len(doc_snippet) / 500, 1.0)  # Prefer longer chunks
        
        # Bonus if both mention code-like tokens
        code_pattern = r'\b(function|class|template|namespace|tbb::)\b'
        q_has_code = bool(re.search(code_pattern, question, re.I))
        d_has_code = bool(re.search(code_pattern, doc_snippet, re.I))
        code_bonus = 0.2 if (q_has_code and d_has_code) else 0
        
        return (overlap * 0.6) + (length_score * 0.2) + code_bonus
    
    def rerank(self, question: str, docs: List[Dict]) -> List[Dict]:
        """Rerank docs by relevance, filter below threshold."""
        scored = []
        for doc in docs:
            score = self.score_relevance(question, doc.get('content', ''))
            if score >= self.threshold:
                doc['relevance_score'] = score
                scored.append((score, doc))
        
        scored.sort(reverse=True, key=lambda x: x[0])
        return [doc for _, doc in scored]
    
    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.findall(r'\b[a-zA-Z_]{3,}\b', text.lower())
```

**Integrate into `answerer.py`:**
```python
from doc_benchmarks.eval.reranker import SimpleReranker

class Answerer:
    def __init__(self, ..., rerank_threshold=0.3):
        self.reranker = SimpleReranker(threshold=rerank_threshold)
    
    def _retrieve_docs(self, library_id, question, max_tokens, top_k=5):
        raw_docs = self.mcp_client.get_library_docs(...)
        ranked_docs = self.reranker.rerank(question, raw_docs)
        return ranked_docs[:3]  # Keep top 3 after reranking
```

---

### 3. Fallback to NO-DOCS Mode (Priority: MEDIUM)

**Goal:** If all retrieved docs score < threshold, skip them entirely (use baseline answer).

**Files to modify:**
- `doc_benchmarks/eval/answerer.py`
  - `_generate_answer_pair()`: check if `retrieved_docs` is empty after reranking

**Implementation:**
```python
def _generate_answer_pair(self, library_name, library_id, question, max_tokens):
    question_text = question["text"]
    
    # Retrieve + rerank
    retrieved_docs = self._retrieve_docs(library_id, question_text, max_tokens, top_k=5)
    
    if retrieved_docs:
        with_docs_answer = self._generate_with_docs(question_text, retrieved_docs)
    else:
        # FALLBACK: No good docs found, use baseline
        logger.warning(f"No relevant docs for {question['id']}, using baseline")
        with_docs_answer = {
            "answer": "[FALLBACK: No relevant documentation found]",
            "retrieved_docs": [],
            "model": self.model,
            "doc_source": "fallback_baseline",
            "fallback_reason": "low_relevance"
        }
    
    without_docs_answer = self._generate_without_docs(question_text)
    ...
```

---

### 4. Logging & Debugging Output (Priority: MEDIUM)

**Goal:** Track retrieval quality for analysis.

**Files to modify:**
- `doc_benchmarks/eval/answerer.py`
  - Add `retrieval_metadata` to output

**Output format:**
```json
{
  "question_id": "q_031",
  "with_docs": {
    "answer": "...",
    "retrieved_docs": [...],
    "retrieval_metadata": {
      "raw_count": 5,
      "after_rerank": 2,
      "top_score": 0.45,
      "avg_score": 0.38,
      "fallback_triggered": false
    }
  }
}
```

**Usage:** Run `python cli.py answers generate --debug-retrieval` to save extended metadata.

---

### 5. Optional: Semantic Reranker (Priority: LOW)

**Goal:** Use embedding-based reranking for better accuracy.

**Files to add:**
- `doc_benchmarks/eval/reranker.py` (extend with `SentenceTransformerReranker`)

**Implementation:**
```python
from sentence_transformers import SentenceTransformer, util

class SentenceTransformerReranker:
    def __init__(self, model_name="all-MiniLM-L6-v2", threshold=0.5):
        self.model = SentenceTransformer(model_name)
        self.threshold = threshold
    
    def rerank(self, question: str, docs: List[Dict]) -> List[Dict]:
        q_emb = self.model.encode(question, convert_to_tensor=True)
        doc_texts = [d.get('content', '') for d in docs]
        d_embs = self.model.encode(doc_texts, convert_to_tensor=True)
        
        scores = util.cos_sim(q_emb, d_embs)[0].cpu().tolist()
        
        ranked = []
        for score, doc in zip(scores, docs):
            if score >= self.threshold:
                doc['relevance_score'] = score
                ranked.append((score, doc))
        
        ranked.sort(reverse=True, key=lambda x: x[0])
        return [doc for _, doc in ranked]
```

**Tradeoff:** Requires extra dependency (`sentence-transformers`), slower inference.  
**When to use:** If lexical reranking doesn't improve delta enough.

---

## Implementation Priority

### Phase 1: Quick Wins (2-3 hours)
1. ✅ Top-K retrieval (modify `answerer.py`)
2. ✅ Simple lexical reranker (new `reranker.py`)
3. ✅ Integrate reranker into `_retrieve_docs()`

### Phase 2: Quality Control (1-2 hours)
4. ✅ Fallback logic (modify `_generate_answer_pair()`)
5. ✅ Logging/metadata (extend output schema)

### Phase 3: Advanced (optional, 2-4 hours)
6. ⏸️ Semantic reranker (if lexical insufficient)
7. ⏸️ BM25 scoring (if retrieval still weak)

---

## Testing Plan

1. **Before/After Comparison:**
   - Re-run `python cli.py answers generate` on oneTBB
   - Compare delta: expect **+2 to +5 points** improvement

2. **Spot Check:**
   - Manually review q_031, q_003, q_017 (current worst cases)
   - Verify reranked docs are more relevant

3. **Metrics to Track:**
   - Avg delta (WITH - WITHOUT)
   - % questions with fallback triggered
   - Avg `top_score` in retrieval_metadata

---

## Success Criteria

- **Delta improvement:** -0.8 → **+2.0 or higher**
- **Fallback rate:** < 20% (means retrieval works most of the time)
- **Manual inspection:** q_031 answer with docs should score ≥ WITHOUT

---

## CLI Changes

Add flags to `cli.py answers generate`:
```bash
python cli.py answers generate \
  --product oneTBB \
  --questions questions/oneTBB.json \
  --top-k 5 \              # NEW
  --rerank-threshold 0.3 \ # NEW
  --debug-retrieval        # NEW (saves extended metadata)
```

---

## Files to Create/Modify

**New files:**
- `doc_benchmarks/eval/reranker.py` (SimpleReranker + optional SentenceTransformerReranker)
- `tests/test_eval_reranker.py` (unit tests for reranking logic)

**Modify:**
- `doc_benchmarks/eval/answerer.py` (integrate reranker, fallback, metadata)
- `doc_benchmarks/mcp/context7.py` (check if `get_library_docs` supports `top_k`)
- `cli.py` (add new flags: `--top-k`, `--rerank-threshold`, `--debug-retrieval`)

**Documentation:**
- `END_TO_END_WORKFLOW.md` (update Phase 3 section with new retrieval flow)

---

## Next Steps

1. Implement `SimpleReranker` class
2. Modify `answerer.py` to use reranker
3. Test on 5-10 questions manually
4. Re-run full eval on oneTBB
5. Compare delta before/after
6. If delta < +2.0, consider semantic reranker (Phase 3)
