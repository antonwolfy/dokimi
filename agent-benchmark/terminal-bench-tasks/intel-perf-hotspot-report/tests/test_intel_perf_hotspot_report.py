#!/usr/bin/env python3
import re
from pathlib import Path

REPORT = Path("/app/hotspot_report.md")


def _text():
    assert REPORT.exists(), "write /app/hotspot_report.md"
    text = REPORT.read_text(errors="replace")
    assert len(text) > 800, "report is too short to be a structured hotspot report"
    return text


def test_required_sections_and_tables():
    text = _text().lower()
    required = [
        "system",
        "ipc",
        "cache",
        "branch",
        "top function",
        "accumulate_scores",
        "worker_update_stats",
        "observation",
    ]
    missing = [item for item in required if item not in text]
    assert not missing, f"missing report content: {missing}"
    assert "|" in text, "expected at least one markdown table"


def test_identifies_patterns_from_evidence():
    text = _text().lower()
    assert "serial accumulator" in text or "loop-carried" in text, (
        "report should identify the serial accumulator signal in accumulate_scores"
    )
    assert "false sharing" in text and ("hitm" in text or "different offsets" in text), (
        "report should identify false sharing from the c2c/HITM artifact"
    )
    assert re.search(r"0\.61|low ipc|ipc.*0", text), "report should interpret low IPC"


def test_report_only_no_fake_fix_claims():
    text = _text().lower()
    forbidden = [
        "i fixed",
        "fixed the binary",
        "changed the code",
        "applied the fix",
        "after optimization",
    ]
    bad = [phrase for phrase in forbidden if phrase in text]
    assert not bad, f"report-only task should not claim code changes: {bad}"
