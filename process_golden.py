import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
inbound_dir = BASE_DIR.parent / "media" / "inbound"
files = [
    "file_1564---c23adc35-4806-44af-ae3a-96709e741dae.md",
    "file_1565---dbb78bb8-7d80-4152-808e-770fce8ddc42.md",
    "file_1566---13a0ce56-be97-460d-a297-5e09dd53ca2f.md",
]

static_must_haves = {
    "oneTBB": ["Q013", "Q001"],
    "oneMKL": ["Q022", "Q003", "Q005", "Q018", "Q023"],
    "oneDAL": ["Q005", "Q010", "Q021", "Q020"],
}

for fname in files:
    fpath = inbound_dir / fname
    if not fpath.exists():
        print(f"Warning: file not found, skipping: {fpath}")
        continue

    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end != 0:
            try:
                data = json.loads(content[start:end])
            except json.JSONDecodeError:
                print(f"Warning: invalid JSON payload in {fpath}, skipping")
                continue
        else:
            print(f"Warning: JSON block not found in {fpath}, skipping")
            continue

    library = data.get("library")
    if not isinstance(library, str) or not library.strip():
        print(f"Warning: missing/invalid library field in {fpath}, skipping")
        continue
    library_lower = library.lower()

    must_haves = static_must_haves.get(library, [])

    transformed_questions = []
    for q in data.get("questions", []):
        q_id = q.get("id")
        q_text = q.get("question")
        if not q_id or not q_text:
            print(f"Warning: malformed question in {library} (id={q_id}), skipping")
            continue

        tq = {
            "id": f"{library_lower}-{q_id}",
            "text": q_text,
            "category": q.get("category", "general"),
            "difficulty": str(q.get("difficulty", "intermediate")),
            "expected_topics": q.get("expected_answer_points", []),
            "metadata": {
                "persona": q.get("persona", ""),
                "must_cite": q.get("must_cite", []),
                "why_it_matters": q.get("why_it_matters", ""),
                "is_static_golden": q_id in must_haves,
                "original_id": q_id,
            },
        }
        transformed_questions.append(tq)

    output_data = {
        "library": library,
        "library_id": f"intel/{library_lower}",
        "description": f"Golden regression set for {library}",
        "version_or_doc_snapshot": data.get("version_or_doc_snapshot", ""),
        "questions": transformed_questions,
    }

    output_path = BASE_DIR / "questions" / f"{library_lower}_golden.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"Saved {library} -> {output_path} with {len(transformed_questions)} questions.")
