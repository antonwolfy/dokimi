#!/usr/bin/env python3
"""
extract_ground_truth_from_repo.py — Extract API ground truth directly from
cloned repository docs (RST files + C++ headers).

This is the INDEPENDENT source for the judge — not Context7.
Architecture:
  - Answer model gets docs via Context7 (MCP)
  - Judge gets ground truth from THIS script (raw repo docs)
  → No circular dependency

Usage:
    python extract_ground_truth_from_repo.py \
        --docs-dir vendor_docs/onedal/docs/source \
        --headers-dir vendor_docs/onedal/cpp/oneapi/dal \
        --library-name oneDAL \
        --out api_ground_truth/onedal_repo.json
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


def parse_rst_api(rst_path: str) -> dict:
    """Extract API info from a single RST file."""
    text = Path(rst_path).read_text(encoding="utf-8", errors="replace")
    
    result = {
        "file": rst_path,
        "title": "",
        "namespace": "",
        "header_file": "",
        "classes": [],
        "functions": [],
        "enums": [],
        "parameters": [],
        "code_examples": [],
    }
    
    # Title
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.strip() and i + 1 < len(lines) and re.match(r'^[=]+$', lines[i + 1].strip()):
            result["title"] = line.strip()
            break
    
    # Namespace
    m = re.search(r'namespace.*?``([^`]+)``', text)
    if m:
        result["namespace"] = m.group(1)
    
    # Header file
    m = re.search(r'``(oneapi/dal/[^`]+\.hpp)``', text)
    if m:
        result["header_file"] = m.group(1)
    
    # Class declarations (RST cpp:class or .. class::)
    for m in re.finditer(r'(?:class|struct)\s+(\w+(?:<[^>]*>)?)', text):
        name = m.group(1)
        if name[0].isupper() or '_' in name:
            result["classes"].append(name)
    
    # Template descriptors
    for m in re.finditer(r'template\s*<([^>]*)>\s*class\s+(\w+)', text):
        result["classes"].append(f"{m.group(2)}<{m.group(1).strip()}>")
    
    # Function/method signatures
    for m in re.finditer(r'(?:auto|void|table|result)\s+(\w+)\s*\(([^)]*)\)', text):
        func = m.group(1)
        args = m.group(2).strip()
        result["functions"].append(f"{func}({args[:80]})")
    
    # set_*/get_* methods
    for m in re.finditer(r'\.\s*(set_\w+|get_\w+)\s*\(', text):
        result["functions"].append(m.group(1))
    
    # Enum values
    for m in re.finditer(r'enum\s+class\s+(\w+)', text):
        result["enums"].append(m.group(1))
    for m in re.finditer(r'(\w+::)+(\w+)\s+value', text, re.I):
        result["enums"].append(m.group(0).strip())
    
    # Parameters (property/field descriptions)
    for m in re.finditer(r'``(\w+)``\s*[-–]\s*(.{10,80})', text):
        result["parameters"].append({
            "name": m.group(1),
            "description": m.group(2).strip(),
        })
    
    # Code examples
    in_code = False
    code_buf = []
    code_lang = "cpp"
    for line in lines:
        if re.match(r'\.\.\s+code-block::\s*(\w+)', line):
            code_lang = re.match(r'\.\.\s+code-block::\s*(\w+)', line).group(1)
            in_code = True
            code_buf = []
        elif in_code:
            if line.strip() == "" and code_buf and not code_buf[-1].strip():
                # End of code block (two blank lines)
                code = "\n".join(code_buf).strip()
                if len(code) > 30:
                    result["code_examples"].append({"language": code_lang, "code": code})
                in_code = False
            elif line and not line[0].isspace() and code_buf:
                code = "\n".join(code_buf).strip()
                if len(code) > 30:
                    result["code_examples"].append({"language": code_lang, "code": code})
                in_code = False
            else:
                code_buf.append(line)
    
    # Deduplicate
    result["classes"] = sorted(set(result["classes"]))
    result["functions"] = sorted(set(result["functions"]))
    result["enums"] = sorted(set(result["enums"]))
    
    return result


def parse_hpp_header(hpp_path: str) -> dict:
    """Extract API declarations from a C++ header file."""
    text = Path(hpp_path).read_text(encoding="utf-8", errors="replace")
    
    result = {
        "file": hpp_path,
        "includes": [],
        "namespaces": [],
        "classes": [],
        "functions": [],
        "enums": [],
        "using_aliases": [],
    }
    
    # Includes
    for m in re.finditer(r'#include\s*[<"]([^>"]+)[>"]', text):
        result["includes"].append(m.group(1))
    
    # Namespace declarations
    for m in re.finditer(r'namespace\s+(\w+(?:::\w+)*)\s*\{', text):
        result["namespaces"].append(m.group(1))
    
    # Using aliases
    for m in re.finditer(r'using\s+(\w+)\s*=\s*([^;]+);', text):
        result["using_aliases"].append(f"{m.group(1)} = {m.group(2).strip()[:80]}")
    
    # Class/struct declarations
    for m in re.finditer(r'(?:class|struct)\s+(?:ONEDAL_EXPORT\s+)?(\w+)', text):
        name = m.group(1)
        if name not in ('public', 'private', 'protected', 'ONEDAL_EXPORT'):
            result["classes"].append(name)
    
    # Function declarations
    for m in re.finditer(r'(?:auto|void|table|\w+_result)\s+(\w+)\s*\(([^)]{0,120})\)', text):
        func = m.group(1)
        if func not in ('if', 'while', 'for', 'switch', 'return'):
            result["functions"].append(f"{func}({m.group(2).strip()[:80]})")
    
    # Enum class
    for m in re.finditer(r'enum\s+class\s+(\w+)\s*\{([^}]*)\}', text, re.DOTALL):
        name = m.group(1)
        values = [v.strip().split('=')[0].strip() for v in m.group(2).split(',') if v.strip()]
        result["enums"].append({"name": name, "values": values})
    
    result["classes"] = sorted(set(result["classes"]))
    result["functions"] = sorted(set(result["functions"]))
    
    return result


def extract_from_repo(docs_dir: str, headers_dir: str, library_name: str) -> dict:
    """Extract comprehensive ground truth from repo docs + headers."""
    print(f"Extracting ground truth from repo for {library_name}...")
    
    # Parse RST docs
    rst_files = sorted(Path(docs_dir).rglob("*.rst"))
    print(f"  Found {len(rst_files)} RST files")
    
    all_rst = []
    all_classes = set()
    all_functions = set()
    all_enums = set()
    all_headers = set()
    all_namespaces = set()
    all_params = []
    all_code_examples = []
    
    for rst in rst_files:
        parsed = parse_rst_api(str(rst))
        if parsed["classes"] or parsed["functions"] or parsed["code_examples"]:
            all_rst.append({
                "file": str(rst.relative_to(docs_dir)),
                "title": parsed["title"],
                "namespace": parsed["namespace"],
                "header_file": parsed["header_file"],
            })
        all_classes.update(parsed["classes"])
        all_functions.update(parsed["functions"])
        all_enums.update(parsed["enums"])
        if parsed["header_file"]:
            all_headers.add(parsed["header_file"])
        if parsed["namespace"]:
            all_namespaces.add(parsed["namespace"])
        all_params.extend(parsed["parameters"])
        all_code_examples.extend(parsed["code_examples"])
    
    # Parse C++ headers
    hpp_files = sorted(Path(headers_dir).rglob("*.hpp")) if headers_dir and os.path.isdir(headers_dir) else []
    # Only top-level public headers (not backend/)
    public_hpp = [h for h in hpp_files if '/backend/' not in str(h) and '/detail/' not in str(h)]
    print(f"  Found {len(public_hpp)} public HPP headers (out of {len(hpp_files)} total)")
    
    hpp_classes = set()
    hpp_functions = set()
    hpp_enums = []
    hpp_includes = set()
    
    for hpp in public_hpp:
        parsed = parse_hpp_header(str(hpp))
        hpp_classes.update(parsed["classes"])
        hpp_functions.update(parsed["functions"])
        hpp_enums.extend(parsed["enums"])
        hpp_includes.update(parsed["includes"])
    
    # Merge
    ground_truth = {
        "library_name": library_name,
        "source": "repository_docs",
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "docs_dir": docs_dir,
        "headers_dir": headers_dir,
        "api_entities": {
            "namespaces": sorted(all_namespaces),
            "classes_from_docs": sorted(all_classes),
            "classes_from_headers": sorted(hpp_classes)[:100],
            "functions_from_docs": sorted(all_functions),
            "functions_from_headers": sorted(hpp_functions)[:100],
            "includes": sorted(all_headers | hpp_includes),
            "enums_from_docs": sorted(all_enums),
            "enums_from_headers": hpp_enums[:50],
            "parameters": all_params[:200],
        },
        "code_examples": all_code_examples[:80],
        "api_files": all_rst,
        "summary": {
            "rst_files": len(rst_files),
            "hpp_files": len(public_hpp),
            "classes": len(all_classes | hpp_classes),
            "functions": len(all_functions | set(f.split('(')[0] for f in hpp_functions)),
            "includes": len(all_headers | hpp_includes),
            "code_examples": len(all_code_examples),
            "parameters": len(all_params),
        },
    }
    
    return ground_truth


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs-dir", required=True)
    parser.add_argument("--headers-dir", default="")
    parser.add_argument("--library-name", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    
    gt = extract_from_repo(args.docs_dir, args.headers_dir, args.library_name)
    
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(gt, f, indent=2, ensure_ascii=False)
    
    s = gt["summary"]
    print(f"\n✅ Repo ground truth saved to: {args.out}")
    print(f"   RST files: {s['rst_files']}, HPP headers: {s['hpp_files']}")
    print(f"   Classes: {s['classes']}, Functions: {s['functions']}")
    print(f"   Includes: {s['includes']}, Code examples: {s['code_examples']}")
    print(f"   Parameters: {s['parameters']}")


if __name__ == "__main__":
    main()
