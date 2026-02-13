#!/usr/bin/env python3
"""
Documentation Quality Benchmark
Evaluate documentation quality by comparing LLM answers with and without
documentation context from MCP servers (Context7, etc.)

Usage:
    python benchmark.py scan -q questions/onetbb.json --source context7:uxlfoundation/onetbb
    python benchmark.py scan -q questions/onetbb.json --source baseline
    python benchmark.py scan -q questions/onetbb.json --source context7:uxlfoundation/onetbb --source baseline
    python benchmark.py compare results/run_*.json
    python benchmark.py docs --repo uxlfoundation/oneTBB
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

QUESTIONS_DIR = Path(__file__).parent / "questions"
RESULTS_DIR = Path(__file__).parent / "results"
CACHE_DIR = Path(__file__).parent / ".cache"

# Scoring rubric — defines what "good" means for each dimension
SCORING_RUBRIC = {
    "correctness": {
        "description": "Are the facts, APIs, code examples, and technical details accurate?",
        "scale": "1-5",
        "criteria": {
            1: "Major factual errors, wrong APIs, broken code",
            2: "Some inaccuracies, outdated info, partially wrong code",
            3: "Mostly correct, minor issues, code needs tweaks",
            4: "Accurate, working code, correct APIs",
            5: "Fully accurate, verified APIs, production-ready code",
        },
    },
    "completeness": {
        "description": "Does the answer cover all aspects the question needs?",
        "scale": "1-5",
        "criteria": {
            1: "Misses most key topics, superficial",
            2: "Covers some topics, significant gaps",
            3: "Covers main topics, some gaps remain",
            4: "Thorough coverage, minor omissions",
            5: "Comprehensive, covers all expected topics",
        },
    },
    "specificity": {
        "description": "Does it reference specific library APIs, functions, parameters (not generic advice)?",
        "scale": "1-5",
        "criteria": {
            1: "Completely generic, no library-specific content",
            2: "Mostly generic with vague library mentions",
            3: "Some specific APIs/functions mentioned",
            4: "Good specificity, concrete API references",
            5: "Highly specific, exact functions/params/signatures",
        },
    },
    "code_quality": {
        "description": "Are code examples working, idiomatic, and copy-paste ready?",
        "scale": "1-5",
        "criteria": {
            1: "No code or completely broken examples",
            2: "Code present but won't compile/run",
            3: "Code works with modifications needed",
            4: "Working code, mostly idiomatic",
            5: "Production-quality, idiomatic, copy-paste ready",
        },
    },
    "actionability": {
        "description": "Can the developer immediately use this to solve their problem?",
        "scale": "1-5",
        "criteria": {
            1: "Not actionable, too vague or wrong",
            2: "Partially actionable, needs significant research",
            3: "Actionable with some additional work",
            4: "Directly actionable, clear next steps",
            5: "Immediately actionable, complete solution",
        },
    },
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Question:
    id: str
    text: str
    category: str = "general"
    difficulty: str = "intermediate"
    expected_topics: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class Answer:
    question_id: str
    source: str  # "baseline", "context7:uxlfoundation/onetbb", etc.
    text: str
    context_used: Optional[str] = None
    context_length: int = 0
    model: str = ""
    tokens_used: int = 0
    latency_ms: int = 0


@dataclass
class Score:
    question_id: str
    source: str
    correctness: int = 0
    completeness: int = 0
    specificity: int = 0
    code_quality: int = 0
    actionability: int = 0
    doc_gap: str = ""
    hallucination_notes: str = ""
    scorer_notes: str = ""
    scorer_model: str = ""

    @property
    def total(self) -> float:
        return (self.correctness + self.completeness + self.specificity +
                self.code_quality + self.actionability) / 5.0


# ---------------------------------------------------------------------------
# LLM Clients
# ---------------------------------------------------------------------------

def get_client(provider: str = "openai"):
    """Get OpenAI-compatible client."""
    from openai import OpenAI

    def _read_key(env_var: str, file_path: str) -> str:
        key = os.environ.get(env_var, "")
        if key:
            return key
        path = Path(os.path.expanduser(file_path))
        if path.exists():
            return path.read_text().strip()
        raise FileNotFoundError(
            f"API key not found. Set {env_var} env var or create {file_path}"
        )

    if provider == "openai":
        key = _read_key("OPENAI_API_KEY", "~/.config/openai/api_key")
        return OpenAI(api_key=key)
    elif provider == "deepseek":
        key = _read_key("DEEPSEEK_API_KEY", "~/.config/deepseek/api_key")
        return OpenAI(api_key=key, base_url="https://api.deepseek.com")
    elif provider == "anthropic":
        from openai import OpenAI
        key = _read_key("ANTHROPIC_API_KEY", "~/.config/anthropic/api_key")
        return OpenAI(api_key=key, base_url="https://api.anthropic.com/v1/")
    else:
        raise ValueError(f"Unknown provider: {provider}")


# ---------------------------------------------------------------------------
# Source: Context7 MCP
# ---------------------------------------------------------------------------

def fetch_context7(library_id: str, query: str, max_tokens: int = 8000) -> str:
    """Fetch docs from Context7. Caches responses locally."""
    import hashlib

    cache_key = hashlib.sha256(f"{library_id}:{query}:{max_tokens}".encode()).hexdigest()
    cache_file = CACHE_DIR / "context7" / f"{cache_key}.txt"

    if cache_file.exists():
        return cache_file.read_text()

    url = (
        f"https://context7.com/{library_id}/llms.txt"
        f"?tokens={max_tokens}"
        f"&topic={urllib.parse.quote(query)}"
    )

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "DocBenchmark/1.0"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8")

            # Validate response
            if len(text.strip()) < 50:
                print(f"    ⚠ Context7 returned very short response ({len(text)} chars)")

            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(text)
            return text

        except Exception as e:
            if attempt < 2:
                print(f"    ⚠ Context7 retry {attempt+1}: {e}")
                time.sleep(2 ** attempt)
            else:
                return f"[FETCH_FAILED: {e}]"

    return "[FETCH_FAILED: max retries]"


def get_context(source: str, query: str) -> Optional[str]:
    """Get documentation context from a source."""
    if source == "baseline":
        return None
    elif source.startswith("context7:"):
        library_id = source.split(":", 1)[1]
        text = fetch_context7(library_id, query)
        if text.startswith("[FETCH_FAILED"):
            return None
        return text
    else:
        raise ValueError(f"Unknown source: {source}")


# ---------------------------------------------------------------------------
# Answer Generation
# ---------------------------------------------------------------------------

def generate_answer(client, question: Question, source: str,
                    model: str = "gpt-4o-mini") -> Answer:
    """Generate an answer for a question, optionally with doc context."""
    start = time.time()
    context = get_context(source, question.text)

    if context:
        system = (
            "You are an expert developer assistant. Answer the question using "
            "the provided documentation. Be specific, include code examples, "
            "and cite specific APIs/functions.\n\n"
            f"Documentation:\n{context}"
        )
    else:
        system = (
            "You are an expert developer assistant. Answer based on your "
            "training knowledge. Be specific, include code examples."
        )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": question.text},
        ],
        temperature=0.3,
        max_tokens=2000,
    )

    elapsed = int((time.time() - start) * 1000)
    usage = resp.usage

    return Answer(
        question_id=question.id,
        source=source,
        text=resp.choices[0].message.content.strip(),
        context_used=context,
        context_length=len(context) if context else 0,
        model=model,
        tokens_used=usage.total_tokens if usage else 0,
        latency_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Scoring (LLM-as-Judge)
# ---------------------------------------------------------------------------

def build_scoring_prompt(question: Question, answer: Answer) -> str:
    """Build the scoring prompt with rubric."""
    rubric_text = ""
    for dim, info in SCORING_RUBRIC.items():
        rubric_text += f"\n### {dim}\n{info['description']}\n"
        for score, desc in info["criteria"].items():
            rubric_text += f"  {score}: {desc}\n"

    context_note = ""
    if answer.context_used:
        context_note = (
            f"\n[This answer was generated WITH documentation context "
            f"({answer.context_length} chars from {answer.source})]\n"
        )
    else:
        context_note = (
            "\n[This answer was generated WITHOUT documentation context "
            "(LLM knowledge only)]\n"
        )

    return f"""You are evaluating the quality of a technical answer.

## Question
{question.text}

Expected topics: {', '.join(question.expected_topics) if question.expected_topics else 'N/A'}
Difficulty: {question.difficulty}
{context_note}
## Answer to Evaluate
{answer.text[:4000]}

## Scoring Rubric
Rate each dimension on a 1-5 scale:
{rubric_text}

## Additional Analysis
- **doc_gap**: What information is MISSING that would improve this answer?
- **hallucination_notes**: Are there any fabricated APIs, wrong function signatures, or made-up features?

## Output Format
Return ONLY a JSON object (no markdown fences):
{{
  "correctness": <1-5>,
  "completeness": <1-5>,
  "specificity": <1-5>,
  "code_quality": <1-5>,
  "actionability": <1-5>,
  "doc_gap": "<what's missing>",
  "hallucination_notes": "<any hallucinations found>",
  "scorer_notes": "<brief justification>"
}}"""


def score_answer(client, question: Question, answer: Answer,
                 model: str = "gpt-4o-mini") -> Score:
    """Score an answer using LLM-as-judge with rubric."""
    prompt = build_scoring_prompt(question, answer)

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=500,
    )

    text = resp.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print("    ⚠ Failed to parse scorer response, using defaults")
        data = {}

    def _clamp(val, lo=0, hi=5):
        try:
            return max(lo, min(hi, int(val)))
        except (TypeError, ValueError):
            return 0

    return Score(
        question_id=answer.question_id,
        source=answer.source,
        correctness=_clamp(data.get("correctness", 0)),
        completeness=_clamp(data.get("completeness", 0)),
        specificity=_clamp(data.get("specificity", 0)),
        code_quality=_clamp(data.get("code_quality", 0)),
        actionability=_clamp(data.get("actionability", 0)),
        doc_gap=data.get("doc_gap", ""),
        hallucination_notes=data.get("hallucination_notes", ""),
        scorer_notes=data.get("scorer_notes", ""),
        scorer_model=model,
    )


# ---------------------------------------------------------------------------
# Questions I/O
# ---------------------------------------------------------------------------

def load_questions(path: Path) -> list[Question]:
    """Load questions from a JSON file."""
    with open(path) as f:
        data = json.load(f)

    questions = []
    for i, q in enumerate(data.get("questions", data if isinstance(data, list) else [])):
        if "id" not in q or "text" not in q:
            raise ValueError(
                f"Question entry {i} missing required 'id' or 'text' field"
            )
        questions.append(Question(
            id=q["id"],
            text=q["text"],
            category=q.get("category", "general"),
            difficulty=q.get("difficulty", "intermediate"),
            expected_topics=q.get("expected_topics", []),
            metadata=q.get("metadata", {}),
        ))
    return questions


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------

def generate_report(results: dict, output_path: Path):
    """Generate markdown report from benchmark results."""
    lines = ["# Documentation Quality Benchmark Report\n"]
    meta = results.get("metadata", {})
    lines.append(f"**Date:** {meta.get('timestamp', 'N/A')}")
    lines.append(f"**Questions:** {meta.get('questions_file', 'N/A')}")
    lines.append(f"**Sources:** {', '.join(meta.get('sources', []))}")
    lines.append(f"**Answer model:** {meta.get('answer_model', 'N/A')}")
    lines.append(f"**Scorer model:** {meta.get('scorer_model', 'N/A')}")
    lines.append("")

    # Per-source summary
    for source in meta.get("sources", []):
        source_scores = [
            s for s in results.get("scores", [])
            if s["source"] == source
        ]
        if not source_scores:
            continue

        lines.append(f"\n## Source: `{source}`\n")

        # Average scores
        dims = ["correctness", "completeness", "specificity", "code_quality", "actionability"]
        lines.append("### Average Scores\n")
        lines.append("| Dimension | Score (1-5) |")
        lines.append("|-----------|-------------|")
        for dim in dims:
            vals = [s[dim] for s in source_scores if s[dim] > 0]
            avg = sum(vals) / len(vals) if vals else 0
            bar = "█" * int(avg) + "░" * (5 - int(avg))
            lines.append(f"| {dim} | {avg:.1f} {bar} |")

        total_vals = [
            sum(s[d] for d in dims) / len(dims)
            for s in source_scores if all(s[d] > 0 for d in dims)
        ]
        overall = sum(total_vals) / len(total_vals) if total_vals else 0
        lines.append(f"\n**Overall: {overall:.1f}/5.0**\n")

        # By category
        categories = set(
            r["question"]["category"]
            for r in results.get("evaluations", [])
            if r["score"]["source"] == source
        )
        if categories:
            lines.append("### By Category\n")
            lines.append("| Category | Avg Score | Questions |")
            lines.append("|----------|-----------|-----------|")
            for cat in sorted(categories):
                cat_scores = [
                    sum(s[d] for d in dims) / len(dims)
                    for r in results.get("evaluations", [])
                    for s in [r["score"]]
                    if s["source"] == source
                    and r["question"]["category"] == cat
                    and all(s[d] > 0 for d in dims)
                ]
                avg = sum(cat_scores) / len(cat_scores) if cat_scores else 0
                lines.append(f"| {cat} | {avg:.1f} | {len(cat_scores)} |")

        # Doc gaps
        gaps = [
            s for s in source_scores
            if s.get("doc_gap") and s["doc_gap"] not in ("None", "N/A", "none", "")
        ]
        if gaps:
            lines.append(f"\n### Documentation Gaps ({len(gaps)})\n")
            for g in gaps:
                q = next(
                    (r["question"] for r in results.get("evaluations", [])
                     if r["score"]["question_id"] == g["question_id"]
                     and r["score"]["source"] == source),
                    {},
                )
                lines.append(f"- **Q:** _{q.get('text', g['question_id'])[:100]}_")
                lines.append(f"  **Gap:** {g['doc_gap']}")

        # Hallucinations
        halluc = [
            s for s in source_scores
            if s.get("hallucination_notes")
            and not s["hallucination_notes"].lower().startswith("no")
            and s["hallucination_notes"] not in ("None", "N/A", "none", "")
        ]
        if halluc:
            lines.append(f"\n### ⚠ Hallucination Risks ({len(halluc)})\n")
            for h in halluc:
                q = next(
                    (r["question"] for r in results.get("evaluations", [])
                     if r["score"]["question_id"] == h["question_id"]
                     and r["score"]["source"] == source),
                    {},
                )
                lines.append(f"- **Q:** _{q.get('text', h['question_id'])[:100]}_")
                lines.append(f"  **Risk:** {h['hallucination_notes']}")

    # Comparison table (if multiple sources)
    sources = meta.get("sources", [])
    if len(sources) > 1:
        lines.append("\n## Comparison\n")
        lines.append("| Question | " + " | ".join(sources) + " |")
        lines.append("|----------|" + "|".join(["-------"] * len(sources)) + "|")

        question_ids = list(dict.fromkeys(
            s["question_id"] for s in results.get("scores", [])
        ))
        for qid in question_ids:
            q_text = next(
                (r["question"]["text"] for r in results.get("evaluations", [])
                 if r["question"]["id"] == qid),
                qid,
            )
            row = f"| {q_text[:60]}... |"
            for src in sources:
                s = next(
                    (s for s in results.get("scores", [])
                     if s["question_id"] == qid and s["source"] == src),
                    None,
                )
                if s:
                    total = sum(s[d] for d in ["correctness", "completeness",
                                               "specificity", "code_quality",
                                               "actionability"]) / 5
                    row += f" {total:.1f} |"
                else:
                    row += " - |"
            lines.append(row)

    report_text = "\n".join(lines)
    report_file = output_path / "report.md"
    report_file.write_text(report_text)
    print(f"\n📊 Report: {report_file}")
    return report_text


# ---------------------------------------------------------------------------
# Main: scan command
# ---------------------------------------------------------------------------

def cmd_scan(args):
    """Run benchmark scan."""
    from openai import OpenAI

    # Load questions
    questions_file = Path(args.questions)
    if not questions_file.exists():
        print(f"❌ Questions file not found: {questions_file}")
        sys.exit(1)

    questions = load_questions(questions_file)
    print(f"📋 Loaded {len(questions)} questions from {questions_file.name}")

    sources = args.source
    print(f"🔌 Sources: {', '.join(sources)}")

    # Setup clients
    answer_client = get_client("openai")
    scorer_client = get_client("openai")  # TODO: separate scorer model

    answer_model = args.answer_model
    scorer_model = args.scorer_model

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_DIR / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    all_evaluations = []
    all_scores = []

    for source in sources:
        print(f"\n{'='*60}")
        print(f"SOURCE: {source}")
        print(f"{'='*60}")

        for i, question in enumerate(questions):
            print(f"\n  [{i+1}/{len(questions)}] {question.text[:70]}...")

            # Generate answer
            print(f"    Generating answer ({answer_model})...")
            answer = generate_answer(answer_client, question, source, model=answer_model)

            # Score answer
            print(f"    Scoring ({scorer_model})...")
            score = score_answer(scorer_client, question, answer, model=scorer_model)

            evaluation = {
                "question": asdict(question),
                "answer": {
                    "question_id": answer.question_id,
                    "source": answer.source,
                    "text": answer.text,
                    "context_length": answer.context_length,
                    "model": answer.model,
                    "tokens_used": answer.tokens_used,
                    "latency_ms": answer.latency_ms,
                },
                "score": asdict(score),
            }

            # Store full context separately (large)
            if answer.context_used:
                safe_qid = re.sub(r"[^a-zA-Z0-9_-]", "_", question.id)
                safe_src = re.sub(r"[^a-zA-Z0-9_-]", "_", source)
                ctx_file = run_dir / f"context_{safe_qid}_{safe_src}.txt"
                ctx_file.write_text(answer.context_used)

            all_evaluations.append(evaluation)
            all_scores.append(asdict(score))

            total = score.total
            print(f"    Score: {total:.1f}/5 "
                  f"(C:{score.correctness} Co:{score.completeness} "
                  f"S:{score.specificity} Q:{score.code_quality} "
                  f"A:{score.actionability})")

            time.sleep(0.3)  # Rate limiting

    # Save results
    results = {
        "metadata": {
            "timestamp": timestamp,
            "questions_file": str(questions_file),
            "sources": sources,
            "answer_model": answer_model,
            "scorer_model": scorer_model,
            "total_questions": len(questions),
            "total_evaluations": len(all_evaluations),
        },
        "evaluations": all_evaluations,
        "scores": all_scores,
    }

    results_file = run_dir / "results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Results: {results_file}")

    # Generate report
    generate_report(results, run_dir)


# ---------------------------------------------------------------------------
# Main: compare command
# ---------------------------------------------------------------------------

def cmd_compare(_args):
    """Compare multiple benchmark runs."""
    print("TODO: compare command")


# ---------------------------------------------------------------------------
# Main: docs command
# ---------------------------------------------------------------------------

def cmd_docs(_args):
    """Scan raw documentation structure."""
    print("TODO: docs scanner")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Documentation Quality Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # scan
    scan_parser = subparsers.add_parser("scan", help="Run benchmark scan")
    scan_parser.add_argument(
        "-q", "--questions", required=True,
        help="Path to questions JSON file",
    )
    scan_parser.add_argument(
        "-s", "--source", action="append", required=True,
        help="Documentation source (baseline, context7:<library_id>, ...)",
    )
    scan_parser.add_argument(
        "--answer-model", default="gpt-4o-mini",
        help="Model for generating answers (default: gpt-4o-mini)",
    )
    scan_parser.add_argument(
        "--scorer-model", default="gpt-4o-mini",
        help="Model for scoring answers (default: gpt-4o-mini)",
    )
    scan_parser.set_defaults(func=cmd_scan)

    # compare
    compare_parser = subparsers.add_parser("compare", help="Compare runs")
    compare_parser.add_argument("runs", nargs="+", help="Result JSON files")
    compare_parser.set_defaults(func=cmd_compare)

    # docs
    docs_parser = subparsers.add_parser("docs", help="Scan raw docs")
    docs_parser.add_argument("--repo", required=True, help="GitHub repo")
    docs_parser.set_defaults(func=cmd_docs)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
