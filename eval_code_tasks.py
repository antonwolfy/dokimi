#!/usr/bin/env python3
"""
eval_code_tasks.py — Evaluate model-generated code against ground truth.

Evaluation strategy per level:
  L1 / L2 — LLM judge (with ground truth injected as context)
  L3       — Structural regex verification (no LLM needed)

Usage:
    python eval_code_tasks.py \
        --tasks questions/onedal_code_tasks.json \
        --answers results/onedal_code/answers.json \
        --ground-truth api_ground_truth/onedal.json \
        --judge-model gemini-2.5-pro \
        --judge-provider google \
        --out results/onedal_code/eval.json
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from doc_benchmarks.llm import call_llm


CODE_JUDGE_SYSTEM = """You are a strict code reviewer for {library_name} with access to the official API reference.

REAL API entities (ground truth):
{api_entities}

REAL code examples from docs:
{code_examples}

Your job: evaluate whether the submitted code correctly uses {library_name} APIs.
Score 0-100 on each dimension. Use ONLY the ground truth above as the reference.
If the code uses API names NOT present in the ground truth, penalise heavily."""

CODE_JUDGE_PROMPT = """Question: {question}

Ground truth answer:
```
{ground_truth_code}
```

Submitted answer:
```
{submitted_code}
```

Required APIs: {required_apis}
Verification hints: {verification_hints}

Evaluate on these dimensions (0-100 each):
1. api_correctness — Are the API function/class names correct and real (vs hallucinated)?
2. signature_correctness — Are function arguments, parameter names, types correct?
3. completeness — Does the code fully answer the question (includes, namespace, main logic)?
4. compilability — Would this code compile/run without modification? (best-effort estimate)
5. correctness — Is the algorithmic logic correct for the task?

Return STRICT JSON:
{{
  "api_correctness": <0-100>,
  "signature_correctness": <0-100>,
  "completeness": <0-100>,
  "compilability": <0-100>,
  "correctness": <0-100>,
  "aggregate": <weighted average>,
  "issues": ["list of specific problems found"],
  "hallucinated_apis": ["any API names used that don't exist in ground truth"],
  "rationale": "brief explanation"
}}

Weights: api_correctness=30%, signature_correctness=25%, completeness=20%, compilability=15%, correctness=10%
Return ONLY the JSON."""


def verify_l3_structural(answer_code: str, patterns: list) -> dict:
    """Structurally verify L3 task using regex patterns."""
    results = []
    passed = 0
    for pattern in patterns:
        try:
            match = bool(re.search(pattern, answer_code, re.MULTILINE))
        except re.error:
            match = False
        results.append({"pattern": pattern, "passed": match})
        if match:
            passed += 1

    score = round(passed / len(patterns) * 100) if patterns else 0
    return {
        "method": "structural_regex",
        "patterns_checked": len(patterns),
        "patterns_passed": passed,
        "details": results,
        "aggregate": score,
        "api_correctness": score,
        "signature_correctness": score,
        "completeness": score,
        "compilability": None,  # not checked
        "correctness": score,
    }


def judge_code_llm(
    question: str,
    ground_truth_code: str,
    submitted_code: str,
    required_apis: list,
    verification_hints: list,
    library_name: str,
    api_entities_text: str,
    code_examples_text: str,
    model: str,
    provider: str,
) -> dict:
    """Use LLM judge to evaluate code quality."""
    system = CODE_JUDGE_SYSTEM.format(
        library_name=library_name,
        api_entities=api_entities_text,
        code_examples=code_examples_text[:3000],
    )
    prompt = CODE_JUDGE_PROMPT.format(
        question=question,
        ground_truth_code=ground_truth_code[:1500],
        submitted_code=submitted_code[:2000],
        required_apis=", ".join(required_apis),
        verification_hints=", ".join(verification_hints),
    )

    try:
        response = call_llm(
            prompt=prompt,
            system_prompt=system,
            model=model,
            provider=provider,
            temperature=0.0,
        )
        text = response.strip()
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)
        result = json.loads(text)
        # Compute weighted aggregate if not present
        if "aggregate" not in result:
            result["aggregate"] = round(
                result.get("api_correctness", 0) * 0.30
                + result.get("signature_correctness", 0) * 0.25
                + result.get("completeness", 0) * 0.20
                + result.get("compilability", 0) * 0.15
                + result.get("correctness", 0) * 0.10
            )
        return result
    except Exception as e:
        return {
            "error": str(e),
            "aggregate": None,
            "api_correctness": None,
            "signature_correctness": None,
            "completeness": None,
            "compilability": None,
            "correctness": None,
        }


def evaluate_code_tasks(
    tasks_path: str,
    answers_path: str,
    ground_truth_path: str,
    out_path: str,
    model: str = "gemini-2.5-pro",
    provider: str = "google",
    concurrency: int = 3,
):
    with open(tasks_path) as f:
        tasks_data = json.load(f)
    with open(answers_path) as f:
        answers_data = json.load(f)
    with open(ground_truth_path) as f:
        gt = json.load(f)

    tasks_by_id = {t["question_id"]: t for t in tasks_data["tasks"]}
    answers_by_id = {a["question_id"]: a for a in answers_data.get("answers", [])}
    library_name = gt["library_name"]

    # Format ground truth for prompts
    def fmt_entities(entities):
        parts = []
        for cat, items in entities.items():
            if items:
                parts.append(f"{cat.upper()}: " + ", ".join(items[:20]))
        return " | ".join(parts)

    def fmt_examples(examples, n=8):
        return "\n\n".join(
            f"```{ex['language']}\n{ex['code'][:400]}\n```"
            for ex in examples[:n]
        )

    api_text = fmt_entities(gt["api_entities"])
    code_text = fmt_examples(gt["code_examples"])

    evaluations = []

    def eval_one(qid):
        task = tasks_by_id.get(qid)
        answer = answers_by_id.get(qid)
        if not task or not answer:
            return None

        submitted = answer.get("code", answer.get("answer", ""))
        level = task.get("level", "")

        if level.startswith("L3") and task.get("verification_patterns"):
            score_data = verify_l3_structural(submitted, task["verification_patterns"])
        else:
            score_data = judge_code_llm(
                question=task["question_text"],
                ground_truth_code=task.get("ground_truth_code", ""),
                submitted_code=submitted,
                required_apis=task.get("required_apis", []),
                verification_hints=task.get("verification_hints", []),
                library_name=library_name,
                api_entities_text=api_text,
                code_examples_text=code_text,
                model=model,
                provider=provider,
            )

        return {
            "question_id": qid,
            "question_text": task["question_text"],
            "level": level,
            "difficulty": task.get("difficulty"),
            "required_apis": task.get("required_apis", []),
            "scores": score_data,
            "aggregate": score_data.get("aggregate"),
            "hallucinated_apis": score_data.get("hallucinated_apis", []),
        }

    all_ids = list(set(tasks_by_id.keys()) & set(answers_by_id.keys()))
    print(f"Evaluating {len(all_ids)} code tasks (concurrency={concurrency})...")

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = {ex.submit(eval_one, qid): qid for qid in all_ids}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            if result:
                evaluations.append(result)
                agg = result.get("aggregate")
                hallu = result.get("hallucinated_apis", [])
                print(f"  [{i}/{len(all_ids)}] {result['question_id']} score={agg} "
                      f"hallucinated={len(hallu)}")

    # Summary stats
    valid = [e for e in evaluations if e.get("aggregate") is not None]
    by_level = {}
    for e in valid:
        lvl = (e.get("level") or "unknown")[:2]
        by_level.setdefault(lvl, []).append(e["aggregate"])

    output = {
        "library_name": library_name,
        "judge_model": model,
        "judge_provider": provider,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(evaluations),
        "summary": {
            "avg_score": round(sum(e["aggregate"] for e in valid) / len(valid), 1) if valid else 0,
            "by_level": {k: round(sum(v) / len(v), 1) for k, v in by_level.items()},
            "hallucination_rate": round(
                sum(1 for e in evaluations if e.get("hallucinated_apis")) / len(evaluations) * 100
            ) if evaluations else 0,
        },
        "evaluations": evaluations,
    }

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    s = output["summary"]
    print(f"\n✅ Eval saved to: {out_path}")
    print(f"   Avg score: {s['avg_score']}  By level: {s['by_level']}")
    print(f"   Hallucination rate: {s['hallucination_rate']}%")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--answers", required=True)
    parser.add_argument("--ground-truth", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--judge-model", default="gemini-2.5-pro")
    parser.add_argument("--judge-provider", default="google")
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()

    evaluate_code_tasks(
        args.tasks, args.answers, args.ground_truth, args.out,
        args.judge_model, args.judge_provider, args.concurrency,
    )


if __name__ == "__main__":
    main()
