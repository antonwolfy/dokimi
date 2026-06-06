"""Tests for example execution policy and sandbox boundaries."""

from __future__ import annotations


from doc_benchmarks.metrics.example_runner import (
    ExecutionPolicy,
    extract_examples,
    run_example,
    score_examples,
)


def test_extract_examples_with_metadata():
    md = "text\n```python title=\"x.py\"\nprint(1)\n```\nmore\n```bash\nls\n```\n"
    examples = extract_examples(md)
    assert examples == [("python", "print(1)"), ("bash", "ls")]


def test_default_backend_does_not_execute(tmp_path, monkeypatch):
    """Default policy is 'none': nothing runs, examples are skipped."""
    monkeypatch.delenv("DOC_BENCH_EXAMPLE_BACKEND", raising=False)
    called = {"ran": False}
    import doc_benchmarks.metrics.example_runner as er

    def _boom(*a, **k):
        called["ran"] = True
        raise AssertionError("subprocess must not run under backend=none")

    monkeypatch.setattr(er.subprocess, "run", _boom)

    res = run_example("python", "print('hi')", ExecutionPolicy(backend="none"))
    assert res.status == "skipped"
    assert res.passed is None
    assert called["ran"] is False


def test_subprocess_refuses_without_allow_host():
    res = run_example("python", "print('x')", ExecutionPolicy(backend="subprocess", allow_host=False))
    assert res.status == "failed"
    assert "allow_host" in (res.error or "")


def test_language_allow_list():
    res = run_example("ruby", "puts 1", ExecutionPolicy(backend="subprocess", allow_host=True))
    assert res.status == "skipped"
    assert "disallowed" in (res.error or "") or "Unsupported" in (res.error or "")


def test_subprocess_executes_when_opted_in(tmp_path):
    res = run_example(
        "python", "print('ok')", ExecutionPolicy(backend="subprocess", allow_host=True, timeout=10)
    )
    assert res.status == "passed"
    assert res.passed is True


def test_subprocess_reports_failure(tmp_path):
    res = run_example(
        "python", "import sys; sys.exit(3)",
        ExecutionPolicy(backend="subprocess", allow_host=True, timeout=10),
    )
    assert res.status == "failed"
    assert "Exit code 3" in (res.error or "")


def test_subprocess_timeout_enforced():
    res = run_example(
        "python", "import time; time.sleep(30)",
        ExecutionPolicy(backend="subprocess", allow_host=True, timeout=1),
    )
    assert res.status == "failed"
    assert "Timeout" in (res.error or "")


def test_score_examples_skipped_scores_one(tmp_path):
    doc = tmp_path / "d.md"
    doc.write_text("```python\nprint(1)\n```\n")
    rate, results = score_examples(doc, ExecutionPolicy(backend="none"))
    assert rate == 1.0
    assert results[0].status == "skipped"


def test_score_examples_no_examples(tmp_path):
    doc = tmp_path / "d.md"
    doc.write_text("no code here")
    rate, results = score_examples(doc, ExecutionPolicy(backend="none"))
    assert rate == 1.0
    assert results == []


def test_from_config_env_override(monkeypatch):
    monkeypatch.setenv("DOC_BENCH_EXAMPLE_BACKEND", "none")
    policy = ExecutionPolicy.from_config({"execution": {"backend": "subprocess", "allow_host": True}})
    assert policy.backend == "none"


def test_from_config_nested_and_legacy():
    nested = ExecutionPolicy.from_config({"execution": {"backend": "docker", "timeout": 9}})
    assert nested.backend == "docker" and nested.timeout == 9
    legacy = ExecutionPolicy.from_config({"timeout": 7})
    assert legacy.backend == "none" and legacy.timeout == 7


def test_docker_backend_missing_docker(monkeypatch):
    """Docker backend surfaces a clear error if docker is absent."""
    import doc_benchmarks.metrics.example_runner as er

    def _no_docker(*a, **k):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(er.subprocess, "run", _no_docker)
    res = run_example("python", "print(1)", ExecutionPolicy(backend="docker"))
    assert res.status == "failed"
    assert "docker is not installed" in (res.error or "")


def test_error_status_counts_as_failure(tmp_path):
    """An unknown backend yields status=error and must not score 1.0."""
    doc = tmp_path / "d.md"
    doc.write_text("```python\nprint(1)\n```\n")
    rate, results = score_examples(doc, ExecutionPolicy(backend="bogus"))
    assert results[0].status == "error"
    assert rate == 0.0
