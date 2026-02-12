#!/usr/bin/env python3
"""
Intel Documentation Quality Benchmark
Generates persona-based questions, tests with/without Context7 docs, scores quality.
"""

import json
import os
import sys
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from openai import OpenAI

# --- Config ---
PRODUCTS = {
    "oneTBB": {
        "context7_id": "uxlfoundation/onetbb",
        "github": "https://github.com/uxlfoundation/oneTBB",
        "description": "C++ parallel programming library with work-stealing scheduler, concurrent containers, flow graph",
        "docs_url": "https://oneapi-src.github.io/oneTBB/",
    },
    "oneDNN": {
        "context7_id": "uxlfoundation/onednn",
        "github": "https://github.com/uxlfoundation/oneDNN",
        "description": "Performance library for deep learning: convolutions, RNNs, normalization, pooling on Intel CPUs/GPUs",
        "docs_url": "https://oneapi-src.github.io/oneDNN/",
    },
    "optimization-zone": {
        "context7_id": "intel/optimization-zone",
        "github": "https://github.com/intel/optimization-zone",
        "description": "Intel tuning guides and optimization recipes for software performance on Intel hardware",
        "docs_url": "https://github.com/intel/optimization-zone",
    },
}

PERSONAS = [
    {
        "id": "ml_engineer",
        "name": "ML Engineer",
        "description": "Building production ML pipelines, needs to optimize training/inference on Intel hardware",
        "focus": ["performance optimization", "integration with PyTorch/TensorFlow", "batch processing", "GPU offload"],
    },
    {
        "id": "hpc_developer",
        "name": "HPC Developer",
        "description": "Writing high-performance C++ code for scientific computing, familiar with OpenMP/MPI",
        "focus": ["parallel algorithms", "NUMA awareness", "vectorization", "memory management", "scalability"],
    },
    {
        "id": "student",
        "name": "CS Student",
        "description": "Learning parallel programming, first time using Intel libraries, needs clear examples",
        "focus": ["getting started", "basic examples", "conceptual understanding", "installation", "hello world"],
    },
    {
        "id": "devops",
        "name": "DevOps/Platform Engineer",
        "description": "Deploying and tuning Intel-optimized workloads in containers/cloud",
        "focus": ["installation", "configuration", "environment variables", "Docker", "benchmarking", "monitoring"],
    },
    {
        "id": "migrator",
        "name": "Migration Engineer",
        "description": "Porting existing code from CUDA/OpenMP/std::thread to Intel oneAPI",
        "focus": ["migration guides", "API mapping", "compatibility", "drop-in replacement", "interop"],
    },
    {
        "id": "ai_agent",
        "name": "AI Coding Agent",
        "description": "Autonomous agent generating Intel-optimized code from user requests",
        "focus": ["API reference", "code snippets", "best practices", "error handling", "version-specific APIs"],
    },
]

QUESTIONS_PER_PERSONA = 8  # 6 personas × 8 = 48 questions per product, ~150 total

# LLM clients
def get_openai_client():
    key = Path(os.path.expanduser("~/.config/openai/api_key")).read_text().strip()
    return OpenAI(api_key=key)

def get_deepseek_client():
    key = Path(os.path.expanduser("~/.config/deepseek/api_key")).read_text().strip()
    return OpenAI(api_key=key, base_url="https://api.deepseek.com")


# --- Context7 MCP fetch ---
def fetch_context7_docs(product_id: str, query: str, max_tokens: int = 8000) -> str:
    """Fetch relevant docs from Context7 via their public API."""
    import urllib.request
    import urllib.parse
    
    url = f"https://context7.com/{product_id}/llms.txt?tokens={max_tokens}&topic={urllib.parse.quote(query)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Intel-Doc-Benchmark/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        return f"[Context7 fetch failed: {e}]"


# --- Question Generation ---
def generate_questions(client: OpenAI, product: dict, product_name: str, persona: dict) -> list[dict]:
    """Generate realistic questions a persona would ask about a product."""
    prompt = f"""You are generating realistic technical questions that a {persona['name']} ({persona['description']}) would ask about {product_name}.

Product: {product_name}
Description: {product['description']}
Docs: {product.get('docs_url', 'N/A')}

Persona focus areas: {', '.join(persona['focus'])}

Generate exactly {QUESTIONS_PER_PERSONA} questions. Mix difficulty levels:
- 2 beginner (getting started, basic usage)
- 3 intermediate (specific features, integration, common patterns)  
- 3 advanced (optimization, edge cases, architecture decisions)

Each question should be something a real developer would type into an AI coding assistant (Cursor, Claude, Copilot).

Return JSON array of objects with fields:
- "question": the actual question text
- "difficulty": "beginner" | "intermediate" | "advanced"
- "category": short category label (e.g. "installation", "api_usage", "performance", "migration", "conceptual")
- "expected_topics": array of topics a good answer should cover

Return ONLY the JSON array, no markdown."""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
    )
    
    text = resp.choices[0].message.content.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    
    questions = json.loads(text)
    for q in questions:
        q["persona"] = persona["id"]
        q["product"] = product_name
    return questions


# --- Answer Generation ---
def answer_question(client: OpenAI, question: str, context: str = None, model: str = "gpt-4o-mini") -> str:
    """Generate answer with or without documentation context."""
    if context:
        system = f"""You are an expert developer assistant. Answer the question using the provided documentation context. Be specific, include code examples when relevant, and cite specific APIs/functions.

Documentation context:
{context}"""
    else:
        system = """You are an expert developer assistant. Answer the question based on your training knowledge. Be specific, include code examples when relevant."""

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ],
        temperature=0.3,
        max_tokens=1500,
    )
    return resp.choices[0].message.content.strip()


# --- Quality Scoring ---
def score_answer(client: OpenAI, question: dict, answer_with_docs: str, answer_without_docs: str) -> dict:
    """Score both answers on multiple dimensions."""
    prompt = f"""You are evaluating documentation quality by comparing two answers to a technical question.

Question: {question['question']}
Product: {question['product']}
Expected topics: {', '.join(question.get('expected_topics', []))}
Difficulty: {question['difficulty']}

=== ANSWER A (with documentation context) ===
{answer_with_docs[:3000]}

=== ANSWER B (without documentation, LLM knowledge only) ===
{answer_without_docs[:3000]}

Score each answer on these dimensions (0-100):

1. **correctness**: Are the facts, APIs, and code examples accurate?
2. **completeness**: Does it cover the expected topics?
3. **specificity**: Does it reference specific Intel APIs/functions/parameters (not generic advice)?
4. **code_quality**: Are code examples working, idiomatic, and copy-paste ready?
5. **actionability**: Can the developer immediately use this to solve their problem?

Also provide:
- **doc_gap**: What information was MISSING from the documentation context that would have improved Answer A?
- **hallucination_risk**: Did Answer B hallucinate any Intel-specific APIs or features? (yes/no + details)
- **verdict**: "docs_better" | "same" | "knowledge_better"

Return JSON object:
{{
  "answer_a_scores": {{"correctness": N, "completeness": N, "specificity": N, "code_quality": N, "actionability": N}},
  "answer_b_scores": {{"correctness": N, "completeness": N, "specificity": N, "code_quality": N, "actionability": N}},
  "doc_gap": "description of missing info",
  "hallucination_risk": "yes/no + details",
  "verdict": "docs_better|same|knowledge_better",
  "notes": "brief explanation"
}}

Return ONLY JSON, no markdown."""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    
    text = resp.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


# --- Main Pipeline ---
def run_benchmark(products: list[str] = None, output_dir: str = "results"):
    """Run full benchmark pipeline."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    client = get_openai_client()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    all_results = []
    
    target_products = {k: v for k, v in PRODUCTS.items() if not products or k in products}
    
    for product_name, product_info in target_products.items():
        print(f"\n{'='*60}")
        print(f"BENCHMARKING: {product_name}")
        print(f"{'='*60}")
        
        product_results = {
            "product": product_name,
            "timestamp": timestamp,
            "questions": [],
        }
        
        # Step 1: Generate questions from all personas
        all_questions = []
        for persona in PERSONAS:
            print(f"\n  Generating questions for persona: {persona['name']}...")
            try:
                questions = generate_questions(client, product_info, product_name, persona)
                all_questions.extend(questions)
                print(f"    Generated {len(questions)} questions")
            except Exception as e:
                print(f"    ERROR generating questions: {e}")
        
        print(f"\n  Total questions for {product_name}: {len(all_questions)}")
        
        # Step 2: For each question, get answers with/without docs and score
        for i, question in enumerate(all_questions):
            qid = f"{product_name}_{question['persona']}_{i}"
            print(f"\n  [{i+1}/{len(all_questions)}] {question['question'][:80]}...")
            
            # Fetch relevant docs
            print(f"    Fetching Context7 docs...")
            docs = fetch_context7_docs(product_info["context7_id"], question["question"])
            has_docs = not docs.startswith("[Context7 fetch failed")
            
            # Generate answers
            print(f"    Generating answer WITH docs...")
            answer_with = answer_question(client, question["question"], context=docs if has_docs else None)
            
            print(f"    Generating answer WITHOUT docs...")
            answer_without = answer_question(client, question["question"], context=None)
            
            # Score
            print(f"    Scoring...")
            try:
                scores = score_answer(client, question, answer_with, answer_without)
            except Exception as e:
                print(f"    ERROR scoring: {e}")
                scores = {"error": str(e)}
            
            result = {
                "id": qid,
                "question": question,
                "docs_available": has_docs,
                "docs_length": len(docs) if has_docs else 0,
                "answer_with_docs": answer_with,
                "answer_without_docs": answer_without,
                "scores": scores,
            }
            
            product_results["questions"].append(result)
            
            # Rate limiting
            time.sleep(0.5)
        
        # Save per-product results
        product_file = output_path / f"{product_name}_{timestamp}.json"
        with open(product_file, "w") as f:
            json.dump(product_results, f, indent=2, ensure_ascii=False)
        print(f"\n  Saved: {product_file}")
        
        all_results.append(product_results)
    
    # Generate summary report
    generate_report(all_results, output_path, timestamp)
    
    return all_results


def generate_report(all_results: list, output_path: Path, timestamp: str):
    """Generate markdown summary report."""
    report = [f"# Intel Documentation Quality Benchmark Report\n"]
    report.append(f"**Date:** {timestamp}")
    report.append(f"**Products:** {', '.join(r['product'] for r in all_results)}")
    report.append(f"**Personas:** {', '.join(p['name'] for p in PERSONAS)}")
    report.append(f"**Questions per product:** ~{QUESTIONS_PER_PERSONA * len(PERSONAS)}\n")
    
    for product_result in all_results:
        product = product_result["product"]
        questions = product_result["questions"]
        
        report.append(f"\n## {product}\n")
        
        # Aggregate scores
        a_scores = {"correctness": [], "completeness": [], "specificity": [], "code_quality": [], "actionability": []}
        b_scores = {"correctness": [], "completeness": [], "specificity": [], "code_quality": [], "actionability": []}
        verdicts = {"docs_better": 0, "same": 0, "knowledge_better": 0}
        doc_gaps = []
        hallucinations = []
        
        for q in questions:
            s = q.get("scores", {})
            if "error" in s:
                continue
            
            verdict = s.get("verdict", "same")
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
            
            for dim in a_scores:
                if "answer_a_scores" in s and dim in s["answer_a_scores"]:
                    a_scores[dim].append(s["answer_a_scores"][dim])
                if "answer_b_scores" in s and dim in s["answer_b_scores"]:
                    b_scores[dim].append(s["answer_b_scores"][dim])
            
            if s.get("doc_gap") and s["doc_gap"] not in ("None", "N/A", ""):
                doc_gaps.append({
                    "question": q["question"]["question"],
                    "persona": q["question"]["persona"],
                    "category": q["question"].get("category", "unknown"),
                    "gap": s["doc_gap"],
                })
            
            if s.get("hallucination_risk", "").lower().startswith("yes"):
                hallucinations.append({
                    "question": q["question"]["question"],
                    "detail": s["hallucination_risk"],
                })
        
        # Score summary table
        report.append("### Quality Scores (avg, 0-100)\n")
        report.append("| Dimension | With Docs | Without Docs | Delta |")
        report.append("|-----------|-----------|--------------|-------|")
        for dim in a_scores:
            avg_a = sum(a_scores[dim]) / len(a_scores[dim]) if a_scores[dim] else 0
            avg_b = sum(b_scores[dim]) / len(b_scores[dim]) if b_scores[dim] else 0
            delta = avg_a - avg_b
            sign = "+" if delta > 0 else ""
            report.append(f"| {dim} | {avg_a:.1f} | {avg_b:.1f} | {sign}{delta:.1f} |")
        
        # Verdict
        total = sum(verdicts.values()) or 1
        report.append(f"\n### Verdict Distribution\n")
        report.append(f"- **Docs better:** {verdicts.get('docs_better', 0)} ({verdicts.get('docs_better', 0)/total*100:.0f}%)")
        report.append(f"- **Same quality:** {verdicts.get('same', 0)} ({verdicts.get('same', 0)/total*100:.0f}%)")
        report.append(f"- **LLM knowledge better:** {verdicts.get('knowledge_better', 0)} ({verdicts.get('knowledge_better', 0)/total*100:.0f}%)")
        
        # Documentation gaps (THE KEY OUTPUT)
        if doc_gaps:
            report.append(f"\n### 🔴 Documentation Gaps ({len(doc_gaps)} found)\n")
            # Group by category
            by_category = {}
            for gap in doc_gaps:
                cat = gap["category"]
                by_category.setdefault(cat, []).append(gap)
            
            for cat, gaps in sorted(by_category.items(), key=lambda x: -len(x[1])):
                report.append(f"\n**{cat}** ({len(gaps)} gaps)")
                for g in gaps:
                    report.append(f"- Q: _{g['question'][:100]}_")
                    report.append(f"  Gap: {g['gap']}")
        
        # Hallucination risks
        if hallucinations:
            report.append(f"\n### ⚠️ Hallucination Risks ({len(hallucinations)} found)\n")
            for h in hallucinations:
                report.append(f"- Q: _{h['question'][:100]}_")
                report.append(f"  Risk: {h['detail']}")
        
        # Per-persona breakdown
        report.append(f"\n### Per-Persona Scores\n")
        report.append("| Persona | Avg Score (with docs) | Avg Score (without) | Delta |")
        report.append("|---------|----------------------|---------------------|-------|")
        for persona in PERSONAS:
            persona_qs = [q for q in questions if q["question"]["persona"] == persona["id"] and "error" not in q.get("scores", {})]
            if not persona_qs:
                continue
            avg_a = []
            avg_b = []
            for q in persona_qs:
                s = q["scores"]
                if "answer_a_scores" in s:
                    avg_a.append(sum(s["answer_a_scores"].values()) / len(s["answer_a_scores"]))
                if "answer_b_scores" in s:
                    avg_b.append(sum(s["answer_b_scores"].values()) / len(s["answer_b_scores"]))
            
            ma = sum(avg_a) / len(avg_a) if avg_a else 0
            mb = sum(avg_b) / len(avg_b) if avg_b else 0
            delta = ma - mb
            sign = "+" if delta > 0 else ""
            report.append(f"| {persona['name']} | {ma:.1f} | {mb:.1f} | {sign}{delta:.1f} |")
    
    # Write report
    report_text = "\n".join(report)
    report_file = output_path / f"report_{timestamp}.md"
    with open(report_file, "w") as f:
        f.write(report_text)
    print(f"\n{'='*60}")
    print(f"REPORT: {report_file}")
    print(f"{'='*60}")
    print(report_text)


if __name__ == "__main__":
    products = sys.argv[1:] if len(sys.argv) > 1 else None
    run_benchmark(products=products, output_dir="results")
