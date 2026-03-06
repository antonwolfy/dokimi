#!/usr/bin/env python3
"""
extract_api_ground_truth.py — Extract API ground truth from library docs via Context7.

Produces a structured JSON with:
- Function/class names
- Signatures and parameters
- Code examples (ground truth snippets)
- Required includes/imports

Usage:
    python extract_api_ground_truth.py --library onedal --out api_ground_truth/onedal.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone


CONTEXT7_SCRIPT = os.path.expanduser("~/.openclaw/workspace/skills/context7/scripts/context7.py")

# Topics to query for comprehensive API coverage
API_TOPICS = [
    "API reference function signatures classes train compute infer parameters",
    "table homogen_table csr_table data management constructor",
    "SVM support vector machine training inference parameters kernel",
    "K-Means clustering training compute centroids assignments",
    "PCA principal component analysis training transform",
    "decision forest classification regression training inference",
    "linear regression training compute parameters",
    "logistic regression training inference binary multiclass",
    "KNN k-nearest neighbors training inference search",
    "gradient boosted trees training classification regression",
    "CSV data source reader loading data",
    "SYCL DPC++ queue device GPU compute",
    "distributed computing MPI SPMD",
    "oneapi dal namespace includes headers",
    "code examples usage samples complete programs",
]


def query_context7(library_id: str, topic: str, max_tokens: int = 8000) -> str:
    """Query Context7 for docs on a specific topic."""
    try:
        result = subprocess.run(
            [sys.executable, CONTEXT7_SCRIPT, "docs", library_id, topic],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout
    except Exception as e:
        print(f"  ⚠️ Error querying '{topic[:40]}...': {e}")
        return ""


def parse_code_blocks(text: str) -> list:
    """Extract code blocks with language annotation."""
    blocks = []
    # Match ```lang\ncode\n``` patterns
    for m in re.finditer(r"```(\w+)?\n(.*?)```", text, re.DOTALL):
        lang = m.group(1) or "unknown"
        code = m.group(2).strip()
        if len(code) > 20:  # skip trivial blocks
            blocks.append({"language": lang, "code": code})
    return blocks


def extract_api_entities(text: str) -> dict:
    """Extract API names, classes, functions from doc text."""
    entities = {
        "namespaces": set(),
        "classes": set(),
        "functions": set(),
        "includes": set(),
        "enums": set(),
    }

    # C++ includes
    for m in re.finditer(r'#include\s*[<"]([^>"]+)[>"]', text):
        entities["includes"].add(m.group(1))

    # Namespace aliases
    for m in re.finditer(r'namespace\s+(\w+)\s*=\s*([^;]+);', text):
        entities["namespaces"].add(f"{m.group(1)} = {m.group(2).strip()}")

    # dal:: qualified names
    for m in re.finditer(r'(dal::\w+(?:::\w+)*)', text):
        name = m.group(1)
        if '::descriptor' in name or '::train' in name or '::infer' in name:
            entities["functions"].add(name)
        else:
            entities["classes"].add(name)

    # oneapi::dal:: qualified names
    for m in re.finditer(r'(oneapi::dal::\w+(?:::\w+)*)', text):
        entities["classes"].add(m.group(1))

    # set_* / get_* methods
    for m in re.finditer(r'\.(set_\w+|get_\w+)\s*\(', text):
        entities["functions"].add(m.group(1))

    # Enum values like df::variable_importance_mode::mdi
    for m in re.finditer(r'(\w+::\w+::\w+)', text):
        val = m.group(1)
        if any(kw in val.lower() for kw in ['mode', 'method', 'metric', 'kernel', 'voting']):
            entities["enums"].add(val)

    return {k: sorted(v) for k, v in entities.items()}


def extract_ground_truth(library_id: str, library_name: str) -> dict:
    """Extract comprehensive API ground truth for a library."""
    print(f"Extracting API ground truth for {library_name} ({library_id})...")

    all_text = ""
    topic_results = []

    for i, topic in enumerate(API_TOPICS):
        print(f"  [{i+1}/{len(API_TOPICS)}] Querying: {topic[:60]}...")
        text = query_context7(library_id, topic)
        if text:
            all_text += text + "\n\n"
            code_blocks = parse_code_blocks(text)
            topic_results.append({
                "topic": topic,
                "text_length": len(text),
                "code_blocks": len(code_blocks),
                "snippets": code_blocks[:5],  # keep top 5 per topic
            })
            print(f"    → {len(text)} chars, {len(code_blocks)} code blocks")

    # Extract structured API entities
    entities = extract_api_entities(all_text)

    # Collect all unique code examples
    all_code = parse_code_blocks(all_text)
    # Deduplicate by first 100 chars
    seen = set()
    unique_code = []
    for block in all_code:
        key = block["code"][:100]
        if key not in seen:
            seen.add(key)
            unique_code.append(block)

    ground_truth = {
        "library_id": library_id,
        "library_name": library_name,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "topics_queried": len(API_TOPICS),
        "total_text_chars": len(all_text),
        "api_entities": entities,
        "code_examples": unique_code[:50],  # top 50 unique examples
        "topic_details": topic_results,
        "summary": {
            "namespaces": len(entities["namespaces"]),
            "classes": len(entities["classes"]),
            "functions": len(entities["functions"]),
            "includes": len(entities["includes"]),
            "enums": len(entities["enums"]),
            "code_examples": len(unique_code),
        }
    }

    return ground_truth


def main():
    parser = argparse.ArgumentParser(description="Extract API ground truth from library docs.")
    parser.add_argument("--library-id", required=True, help="Context7 library ID (e.g. /uxlfoundation/onedal)")
    parser.add_argument("--library-name", required=True, help="Library display name (e.g. oneDAL)")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    gt = extract_ground_truth(args.library_id, args.library_name)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(gt, f, indent=2, ensure_ascii=False)

    s = gt["summary"]
    print(f"\n✅ Ground truth saved to: {args.out}")
    print(f"   Namespaces: {s['namespaces']}, Classes: {s['classes']}, "
          f"Functions: {s['functions']}, Includes: {s['includes']}, "
          f"Enums: {s['enums']}, Code examples: {s['code_examples']}")


if __name__ == "__main__":
    main()
