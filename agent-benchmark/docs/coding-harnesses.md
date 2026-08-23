# Coding Harnesses And Task Runs

Executable task runs measure whether an agent can do the work, not only answer
questions about an API. The `tasks run` command runs Harbor/terminal-bench task
directories through named harnesses, records operation telemetry, and compares
pass rate against a baseline harness.

## Supported Harnesses

Harbor-backed (delegate to an installed `harbor`):

- `codex` — runs Harbor with agent id `codex`.
- `claude-code` — runs Harbor with agent id `claude-code`.
- `terminal-bench:<agent>` — runs any Harbor agent id, for example
  `terminal-bench:terminus`.

Standalone Docker (no Harbor; **full LLM telemetry** — cost, tokens, cache,
latency, turns):

- `docker-oracle` — apply the task's own `solution/solve.sh` (no LLM). Free; use
  it to validate that a task image + verifier work end to end.
- `docker-claude` — solve with `claude -p --output-format json`. The JSON result
  carries `total_cost_usd`, token `usage`, `duration_ms`, `ttft_ms`, and
  `num_turns`, which are folded into the run artifact's `metrics{}`.
- `docker-claude-skill:<skill-path>` — `docker-claude` with a skill directory
  exposed to the agent. This is the **with-skill treatment arm**; compare it
  against `docker-claude` (without-skill) as the baseline.

Custom:

- `command:<template>` or `--command-template` — runs a custom command template
  for local wrappers and CI fakes.

The Harbor adapter command is:

```bash
harbor run -p <task-path> -a <agent> -m <model> --jobs-dir <run-dir>
```

Harbor writes job/trial results under the jobs directory. If a local Harbor
version uses different flags, pass `--command-template` and keep the same output
contract. When Harbor is not installed, prefer the `docker-*` harnesses — they
build, solve, and verify against local Docker directly and record telemetry.

Harbor (pinned to 0.22.0 in CI) does not propagate a non-zero process exit
code for errored/cancelled trials, and this repo's CI runner has hit Harbor
environment-start failures: a Docker Compose v2 gap, and a `network_mode`
rejection. The latter is Harbor behaving correctly — a task declaring
`allow_internet = false` becomes `network_mode='no-network'`, which the docker
provider only accepts when the host kernel supports egress control, so on a
runner without it Harbor refuses the task instead of running it with the
internet the task forbade. A `harbor run` invocation exiting 0 is therefore
**not** sufficient evidence the trial actually passed — parse its `result.json`
(`stats.n_errored_trials`, `stats.evals.<id>.metrics[].mean`) before trusting
a Harbor-backed harness result. The `docker-*` harnesses don't have this gap:
`tasks run`'s own `task_runs.v1` artifact (`summary.per_harness.<h>.pass_rate`)
is the reliable pass/fail signal for those.

## Run Examples

List known harnesses:

```bash
python cli.py tasks harnesses
```

Run one task through Codex and compare it to Claude Code:

```bash
python cli.py tasks run \
  --tasks onetbb-parallel-reduce \
  --harnesses claude-code,codex \
  --baseline-harness claude-code \
  --model anthropic/claude-opus-4-6 \
  --out-json results/task-runs/onetbb-reduce.json
```

If `--baseline-harness` is not listed in `--harnesses`, the CLI adds it to the
run matrix and prints that it will also run the baseline harness.

Run all tasks through a custom wrapper:

```bash
python cli.py tasks run \
  --all \
  --harnesses command \
  --command-template "my-agent --task {task_path} --model {model} --out {output_dir}" \
  --model my-model
```

Use `--dry-run` to validate matrix expansion and artifact shape without invoking
external agents.

## Subject Work Suites

`subjects run` uses the same task harnesses for the subject descriptor's
`suite.tasks` entries. Task execution is explicit because the work harness may
invoke Docker, Harbor, or a billable model-backed solver. If a descriptor
declares tasks, pass `--work-harnesses` or consciously skip them with
`--skip-work`:

```bash
python cli.py subjects run subjects/onetbb-quickstart.toml \
  --work-harnesses docker-claude,docker-claude-skill:data/skills/onetbb-quickstart \
  --work-baseline-harness docker-claude \
  --work-model us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --work-repeats 3
```

The subject scorecard embeds the work status, the `task_runs.v1` artifact path,
the Markdown task report path, and the `summary.per_harness` pass-rate/cost
rollup. Use `--work-dry-run` to verify wiring without invoking the harness.

## Skill treatment experiment (without-skill vs with-skill)

The skill experiment is just two `docker-*` harnesses over one task set, with
the no-skill harness as the baseline. Everything — pass rate, cost, tokens,
per-task breakdown — lands in one schema-validated artifact:

```bash
python cli.py tasks run \
  --tasks intel-perf-serial-accumulator,intel-perf-false-sharing,intel-perf-missing-restrict \
  --harnesses docker-claude,docker-claude-skill:data/skills/intel-performance-patterns/SKILL.md \
  --baseline-harness docker-claude \
  --model us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --repeats 3 \
  --out-json results/skill-task-arms.json
```

- `--repeats 3` runs every `(task, harness)` cell three times so the pass-rate
  and cost deltas carry variance (N=1 is noisy on a binary verifier).
- `--baseline-harness docker-claude` makes the no-skill harness the reference,
  so `summary.comparisons` reports the skill arm's `pass_rate_delta` and
  `cost_delta_usd`.

### Report and raw data

`tasks run` writes a Markdown report next to `--out-json` (override with
`--out-md`), rendered by `agent_benchmarks/report/task_runs_report.py` — the same
package the Q&A `arms`/`eval` reports live in. Sections: headline, difficulty
rollup, per-harness comparison, per-task pass/cost, and a per-cell answer detail
that puts the verifier verdict next to the model's own `solver.json` self-report
(⚠️ flags cells the model claimed it solved but the verifier scored 0 — typically
correct code that misses the performance bar). Re-render any existing artifact:

```python
import json
from agent_benchmarks.report.task_runs_report import render_task_runs_report
print(render_task_runs_report(json.load(open("results/skill-task-arms.json"))))
```

For analysis, export to a flat per-cell table — one row per cell with the
telemetry promoted to `metric_*` columns, the full `metrics`/`operations` blocks
kept as JSON-encoded columns:

```bash
python cli.py dataset export --kind task_runs \
  --input results/skill-task-arms.json \
  --out-dir results/skill-task-arms-dataset --format jsonl   # or parquet / hf
```

What the harnesses handle for you (ported from the older `scripts/run_task.sh`):
pass the host proxy through to `docker build` (corporate networks), run
solve/verify as root for images that set a non-root `USER`, expose the whole
skill tree to the agent (not just `SKILL.md`), and recompile inside the
container using the `g++`/`gcc` command from `instruction.md` — the agent edits
source on the host, whose newer glibc would otherwise break the binary in the
older task image.

### Low-level single-task scripts

`scripts/run_task.sh` and `scripts/run_skill_task_arms.sh` run the same Docker
flow from bash without the CLI. They only emit `reward.txt` (no cost/token
telemetry and no saved artifact), so prefer the `docker-*` harnesses above for
any tracked experiment. The scripts remain useful for a quick one-off oracle
check:

```bash
scripts/run_task.sh oracle terminal-bench-tasks/intel-perf-serial-accumulator /tmp/out
```

## Output Artifact

`tasks run` writes a `task_runs.v1` JSON artifact. Important fields:

- `results[]`: one row per `(task, harness, model, repeat)` cell. With
  `--repeats > 1` each row carries a `repeat` index and the run lands in a
  `run<N>/` subdirectory.
- `results[].passed`: verifier pass/fail. If a reward file is present,
  `1.0` means pass and `0.0` means fail. If no reward is found, adapter exit code
  is used as the fallback.
- `results[].metrics`: for LLM harnesses (`docker-claude*`), the per-run
  `UsageRecord` fields — `cost_usd`, `prompt_tokens`, `completion_tokens`,
  `total_tokens`, `cache_read_tokens`, `cache_write_tokens`, `latency_sec`,
  `ttft_sec`, `n_calls` (agent turns) — plus `operation_count` /
  `operations_by_type`.
- `summary.per_harness`: pass rate, elapsed time, operation totals, a rolled-up
  `cost{}` block (`total_cost_usd` is `null` when no call was priced), and a
  `per_task{}` pass breakdown.
- `summary.comparisons`: `pass_rate_delta`, `passed_delta`, and `cost_delta_usd`
  against `--baseline-harness`.

The artifact is schema-validated on write, like question/answer/eval/arms
artifacts. Per-run detail (the agent's `claude --output-format json` result, the
prompt, and `run.log`) is written under each cell's output directory.

## Operation Telemetry

Every run records the top-level harness invocation. Wrappers and adapters can add
structured operation telemetry in two ways:

1. Append JSON lines to the path in `AGENT_BENCHMARK_OPERATIONS_FILE`.
2. Print a line prefixed with `AGENT_BENCHMARK_OP` followed by a JSON object.

Example:

```text
AGENT_BENCHMARK_OP {"type":"tool","name":"edit","elapsed_sec":0.12}
AGENT_BENCHMARK_OP {"type":"subagent","name":"reviewer","status":"ok"}
AGENT_BENCHMARK_OP {"type":"loop","name":"turn","elapsed_sec":3.4}
```

Unstructured stdout/stderr lines mentioning `tool`, `subagent`, or `loop` are
also counted as low-fidelity telemetry, but structured events are preferred.

## Fair Comparisons

Use one task suite, one model, and fixed task revisions when comparing harnesses.
The baseline harness is not a treatment arm; it is the reference cell for
pass-rate deltas. For example, compare `codex` to `claude-code` only when both
ran the same task set under the same model and task commit.

The Q&A `arms run` path remains separate. It measures context artifacts with an
LLM judge. The `tasks run` path measures executable work with verifier pass rate.

## External Sources

Skills and tasks can come from a checkout of another repo, not just
`data/skills/` and `terminal-bench-tasks/`. Nothing here clones anything —
point the existing flags at a checkout you already have.

`uxlfoundation/skills` (https://github.com/uxlfoundation/skills) is the
worked example: it ships `SKILL.md` packages for the same oneAPI libraries
this repo benchmarks, plus a Harbor task suite under
`evaluation/harbor/tasks/`, both in formats our loaders already read.

Clone it, then scan it before pointing anything real at it:

```bash
git clone https://github.com/uxlfoundation/skills /tmp/uxl-skills

python cli.py catalog scan --root /tmp/uxl-skills --kind skills
python cli.py catalog scan --root /tmp/uxl-skills --kind tasks
```

`catalog scan` reads the source's own manifests when present
(`skills.yaml`, `evaluation/harbor/suites.json`) and reports, per entry,
whether it loaded, or why it was skipped — some suite entries are declared
but not yet implemented (`status: "planned"`, no task directory on disk
yet) or aren't executable Harbor tasks at all (`track: "answer-quality"` /
`"hardware"`, a different evaluation track this repo's `tasks run` doesn't
drive). Skips are expected and don't fail the scan; a load *error* on an
entry that does exist does, and so does a manifest entry whose
`catalog_path` or task `name` resolves outside the checkout you pointed
`--root` at. Both print `ERROR:` and exit 1, so the scan is usable as a
pre-flight gate before `tasks run` — read the exit code, not just the
output, because "skipped" is by design not a failure. Without a manifest,
it falls back to a bare directory scan (same as
`discover_skills`/`discover_tasks`).

Once scanned, use the entries the same way as local ones:

```bash
# with-skill treatment arm using an external skill
python cli.py tasks run --tasks onetbb-histogram-local-aggregation \
  --tasks-root /tmp/uxl-skills/evaluation/harbor/tasks \
  --harnesses docker-oracle,docker-claude-skill:/tmp/uxl-skills/skills/uxl-onetbb \
  --baseline-harness docker-oracle

# or hand an external task straight to Harbor
harbor run -p /tmp/uxl-skills/evaluation/harbor/tasks/onetbb-histogram-local-aggregation -a oracle
```

`docker-claude`/`docker-oracle` read `environment.network_mode` from the
task's own `task.toml` (defaulting to no network at solve/verify time, as
every task in this repo already expects) — an external task that legitimately
needs network at solve/verify time can declare
`network_mode = "public"` and both harnesses will honor it, alongside
`cpus`/`memory_mb` if declared.
