#!/usr/bin/env python3
"""
generate_code_tasks.py — Generate code generation tasks from API ground truth.

Three levels:
  L1 (api_usage)   — Write code using specific API functions
  L2 (migration)   — Convert scikit-learn code to library equivalent
  L3 (verification)— Generate code that can be structurally verified

Usage:
    python generate_code_tasks.py \
        --ground-truth api_ground_truth/onedal.json \
        --out questions/onedal_code_tasks.json \
        --model gpt-4o-mini \
        --count 30
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone

from doc_benchmarks.llm import call_llm


SYSTEM_PROMPT = """You are an expert benchmark question writer for {library_name}.

You have access to the library's REAL API ground truth below. Use ONLY real API names, 
real function signatures, real include paths, and real parameter names from this ground truth.

NEVER invent API names or parameters that don't exist in the ground truth.

Ground truth API entities:
{api_entities}

Ground truth code examples (reference):
{code_examples}
"""

L1_PROMPT = """Generate {count} code generation questions for {library_name} at Level 1 (API Usage).

Each question should ask the user to write code that uses SPECIFIC, REAL API functions/classes from the ground truth.

Requirements:
- Each question must reference at least one concrete API class or function from the ground truth
- Include the expected includes/headers in the ground truth answer
- Difficulty: mix of easy (single API call), intermediate (chain of calls), advanced (complex pipeline)
- Ground truth answer must be a complete, compilable code snippet

Output STRICT JSON array:
[
  {{
    "question_id": "code-L1-001",
    "question_text": "Write C++ code using oneDAL to ...",
    "difficulty": "easy|intermediate|advanced",
    "level": "L1_api_usage",
    "required_apis": ["dal::train", "df::descriptor"],
    "required_includes": ["oneapi/dal/algo/decision_forest.hpp"],
    "ground_truth_code": "// complete compilable code here",
    "verification_hints": ["must use dal::train()", "must set class_count"]
  }},
  ...
]

Generate exactly {count} questions. Return ONLY the JSON array, no markdown."""

L2_PROMPT = """Generate {count} code migration questions for {library_name} at Level 2 (Migration).

Each question provides a scikit-learn (or numpy) code snippet and asks to rewrite it using {library_name}.

Requirements:
- Source code is valid Python/scikit-learn
- Target code must use REAL {library_name} API from the ground truth
- Include both source and expected target code
- Ground truth must be compilable/runnable

Output STRICT JSON array:
[
  {{
    "question_id": "code-L2-001",
    "question_text": "Rewrite the following scikit-learn code using {library_name}:\\n```python\\nfrom sklearn.cluster import KMeans\\n...\\n```",
    "difficulty": "intermediate|advanced",
    "level": "L2_migration",
    "source_code": "from sklearn.cluster import KMeans\\n...",
    "required_apis": ["dal::kmeans::descriptor", "dal::train"],
    "required_includes": ["oneapi/dal/algo/kmeans.hpp"],
    "ground_truth_code": "// complete C++ or Python (sklearnex) code",
    "verification_hints": ["must use correct namespace", "must set n_clusters equivalent"]
  }},
  ...
]

Generate exactly {count} questions. Return ONLY the JSON array, no markdown."""

L3_PROMPT = """Generate {count} structurally verifiable code tasks for {library_name} at Level 3 (Verification).

Each task has a specific, checkable requirement — correct includes, correct function call signatures, 
correct parameter names and types. The answer can be verified by regex/AST without running the code.

Requirements:
- Each task has clear pass/fail criteria
- Verification is structural (pattern matching), not semantic
- Use ONLY real API names from the ground truth
- Include regex patterns that verify correctness

Output STRICT JSON array:
[
  {{
    "question_id": "code-L3-001",
    "question_text": "Write the correct #include directives and namespace aliases needed to use {library_name}'s decision forest classifier",
    "difficulty": "easy|intermediate",
    "level": "L3_verification",
    "required_apis": ["decision_forest"],
    "ground_truth_code": "#include \\"oneapi/dal/algo/decision_forest.hpp\\"\\n...",
    "verification_patterns": [
      "oneapi/dal/algo/decision_forest\\\\.hpp",
      "namespace.*df.*=.*dal::decision_forest"
    ],
    "verification_hints": ["must include decision_forest.hpp", "must alias namespace"]
  }},
  ...
]

Generate exactly {count} questions. Return ONLY the JSON array, no markdown."""


def format_api_entities(entities: dict) -> str:
    """Format API entities for prompt injection."""
    parts = []
    for category, items in entities.items():
        if items:
            parts.append(f"\n{category.upper()}:\n" + "\n".join(f"  - {item}" for item in items[:40]))
    return "\n".join(parts)


def format_code_examples(examples: list, max_examples: int = 15) -> str:
    """Format code examples for prompt injection."""
    parts = []
    for ex in examples[:max_examples]:
        parts.append(f"```{ex['language']}\n{ex['code'][:500]}\n```")
    return "\n\n".join(parts)


def generate_code_tasks(
    ground_truth_path: str,
    out_path: str,
    model: str = "gpt-4o-mini",
    provider: str = "openai",
    count: int = 30,
):
    with open(ground_truth_path) as f:
        gt = json.load(f)

    library_name = gt["library_name"]
    api_text = format_api_entities(gt["api_entities"])
    code_text = format_code_examples(gt["code_examples"])

    system = SYSTEM_PROMPT.format(
        library_name=library_name,
        api_entities=api_text,
        code_examples=code_text,
    )

    # Split count across levels
    l1_count = max(count // 3, 5)
    l2_count = max(count // 3, 5)
    l3_count = count - l1_count - l2_count

    all_tasks = []

    for level_name, prompt_template, level_count in [
        ("L1 (API usage)", L1_PROMPT, l1_count),
        ("L2 (migration)", L2_PROMPT, l2_count),
        ("L3 (verification)", L3_PROMPT, l3_count),
    ]:
        print(f"Generating {level_count} {level_name} tasks...")
        prompt = prompt_template.format(
            count=level_count,
            library_name=library_name,
        )

        response = call_llm(
            prompt=prompt,
            system_prompt=system,
            model=model,
            provider=provider,
            temperature=0.7,
        )

        # Parse JSON from response
        try:
            # Try to extract JSON array from response
            text = response.strip()
            # Remove markdown code fences if present
            text = re.sub(r'^```(?:json)?\s*\n?', '', text)
            text = re.sub(r'\n?```\s*$', '', text)
            tasks = json.loads(text)
            all_tasks.extend(tasks)
            print(f"  ✅ Generated {len(tasks)} tasks")
        except json.JSONDecodeError as e:
            print(f"  ❌ Failed to parse JSON for {level_name}: {e}")
            # Try to salvage partial JSON
            try:
                # Find first [ and last ]
                start = text.index('[')
                end = text.rindex(']') + 1
                tasks = json.loads(text[start:end])
                all_tasks.extend(tasks)
                print(f"  🔧 Salvaged {len(tasks)} tasks from partial JSON")
            except Exception:
                print(f"  ⚠️ Could not salvage any tasks")

    # Add metadata
    output = {
        "library_name": library_name,
        "ground_truth_source": ground_truth_path,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator_model": model,
        "task_count": len(all_tasks),
        "tasks": all_tasks,
        "level_distribution": {
            "L1_api_usage": sum(1 for t in all_tasks if t.get("level", "").startswith("L1")),
            "L2_migration": sum(1 for t in all_tasks if t.get("level", "").startswith("L2")),
            "L3_verification": sum(1 for t in all_tasks if t.get("level", "").startswith("L3")),
        }
    }

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Code tasks saved to: {out_path}")
    print(f"   Total: {len(all_tasks)} tasks")
    print(f"   L1: {output['level_distribution']['L1_api_usage']}")
    print(f"   L2: {output['level_distribution']['L2_migration']}")
    print(f"   L3: {output['level_distribution']['L3_verification']}")

    return out_path


def main():
    parser = argparse.ArgumentParser(description="Generate code tasks from API ground truth.")
    parser.add_argument("--ground-truth", required=True, help="Path to ground truth JSON")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--model", default="gpt-4o-mini", help="LLM model for generation")
    parser.add_argument("--provider", default="openai", help="LLM provider")
    parser.add_argument("--count", type=int, default=30, help="Total number of tasks to generate")
    args = parser.parse_args()

    generate_code_tasks(args.ground_truth, args.out, args.model, args.provider, args.count)


if __name__ == "__main__":
    main()
