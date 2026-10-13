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
- `docker-probe` — no LLM, free. Runs an isolation probe in exactly the work
  tree and environment `docker-claude` would get, writes
  `isolation_probe.json`, and passes only when nothing in
  [What the agent can reach](#what-the-agent-can-reach) is open. Run it before
  a paid sweep. `docker-probe:<skill-path>` also forbids that skill. Use it
  when the with-skill arm's skill lives outside the task's checkout, so the
  baseline is checked against the treatment it must not see.

### What the agent can reach

A task's `solution/` and `tests/` live beside the skills in one content
checkout. A solver that can read them copies the answer instead of solving the
task. A baseline arm that can read the skills is no longer a baseline. The
probe reports six leak classes. Each is `open` or `closed`; `n/a` (nothing to
protect was declared) passes, and `untested` (the image lacks the tool, or the
probe timed out) fails like `open`. The result is in `metrics.isolation_probe`
and `isolation_probe.json`:

| class | what the probe tries |
|---|---|
| `task_files` | read the task's `solution/`, `tests/`, `oracle/` or `verifier/`, or this task's output dir (the other arms' work trees, prompts and transcripts), by absolute path |
| `treatment` | read any `skills/` on the way up from the task (with or without a `.git`), or the `docker-probe:<skill>` skill, by absolute path. `n/a` if neither exists: nothing was tested, and that is not the same as `closed` |
| `operator_config` | read the operator's `~/.claude`, `~/.claude.json`, or `$CLAUDE_CONFIG_DIR` and its `.claude.json` |
| `checkout_walk` | find a `.git`, `task.toml`, or `CLAUDE.md` in a directory above the work tree |
| `network` | fetch `https://example.com/` through whatever proxy variables it was given |
| `env` | find the host value of a variable the allowlist drops in the environ of the probe, its parent chain or PID 1 (`/proc/<pid>/environ`). `n/a` if the allowlist dropped nothing |

`docker-claude` runs the agent on the host. It cannot hide an absolute path or
close the network there, so it states what it does and does not seal in every
run's `metrics.isolation`. It does the following:

- solves in a fresh `abrun-*` temp tree outside any checkout;
- points `HOME` and `CLAUDE_CONFIG_DIR` at empty scratch dirs;
- passes only an allowlist of variables: provider credentials, proxy, locale;
- runs `claude` with `--tools Read,Edit,Write,Bash,Glob,Grep --setting-sources ""
  --strict-mcp-config --no-session-persistence`. Before this change it used
  `--allowedTools`, which only pre-approves tools, so `WebFetch`, `Agent`,
  `Skill` and the operator's skills, CLAUDE.md files and MCP servers loaded in
  both arms. The Bash tool can still start a nested `claude -p` with the
  default tool set; its spend is not in the outer `total_cost_usd`.

A host probe reports `checkout_walk` closed, and `task_files`, `treatment`,
`operator_config`, `network` and `env` open. `env` is open because the agent
runs as the operator's uid: it can read the harness's `/proc/<pid>/environ`
(every variable the allowlist dropped) and its command line and cwd
(`--tasks-root`, `--output-dir`, the skill arm's path). Yama `ptrace_scope=1`
does not stop this; it only gates attach.

Provider credentials come from the environment, for example
`AWS_BEARER_TOKEN_BEDROCK`, `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`.
The `env` block of the operator's `~/.claude/settings.json` (or
`$CLAUDE_CONFIG_DIR/settings.json`) is merged in over the process
environment, as Claude Code applies it, through the same allowlist; a
malformed `settings.json` is logged and ignored. These are not visible from
the scratch `HOME`: an `apiKeyHelper`, an interactive OAuth login, or an
`~/.aws` profile unless `AWS_CONFIG_FILE` / `AWS_SHARED_CREDENTIALS_FILE`
point at it (they pass through).

Every run records how the CLI ended it in `metrics.terminal_reason`. A run
the CLI ended with an error before any attempt (no output tokens, or at most
one turn: missing or rejected credentials, a flagged first request, an
unknown model id) also carries `metrics.solver_error`. The runner counts that
cell as errored, like `metrics.error`: it is out of `pass_rate` and out of the
McNemar pairing (`n_excluded`), so do not drop cells by hand. An error after
an attempt (a 529 at turn 40, `prompt_too_long` in a skill arm that read too
much) is the arm's own outcome and is scored. So is a CLI that dies with no
result object (`terminal_reason: no_result`) after it edited the work tree; with
the tree untouched it is a `solver_error`. Without `--model`,
`metrics.model` is the `modelUsage` entry that cost the most.

`docker-probe*` and `docker-oracle` rows are never compared against
`--baseline-harness`: they are checks of the setup, not arms, and would only
enlarge the Holm family.

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

This contract was written against Harbor 0.22.0; CI no longer installs or runs
Harbor, so treat that as the version the notes below were observed on rather
than a validated pin. Harbor does not propagate a non-zero process exit code
for errored/cancelled trials, and this repo's CI runner has hit Harbor
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
  --tasks-root <content-checkout>/evaluation/harbor/tasks \
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
  --tasks-root <content-checkout>/evaluation/harbor/tasks \
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

No descriptor is committed here — a subject names evaluation content, so you write
one against your own checkout:

```toml
# my-subject.toml
baseline = "baseline"

[subject]
id = "onetbb-quickstart-skill"
kind = "skill"
ref = "<content-checkout>/skills/onetbb-quickstart"

[suite]
products = ["oneTBB"]
questions = ["<content-checkout>/questions/onetbb_golden.json"]
tasks = []

[[matrix.cells]]
id = "arms-runner"
model = "gpt-4o-mini"
provider = "openai"
harness = "arms-runner"
plugins = []
```

```bash
python cli.py subjects run my-subject.toml \
  --work-harnesses docker-claude,docker-claude-skill:<content-checkout>/skills/onetbb-quickstart \
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
  --tasks-root <content-checkout>/evaluation/harbor/tasks \
  --tasks intel-perf-serial-accumulator,intel-perf-false-sharing,intel-perf-missing-restrict \
  --harnesses docker-claude,docker-claude-skill:<content-checkout>/skills/intel-performance-patterns/SKILL.md \
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

What the harnesses handle for you:
pass the host proxy through to `docker build` (corporate networks), run
solve/verify as root for images that set a non-root `USER`, expose the whole
skill tree to the agent (not just `SKILL.md`), and recompile inside the
container using the `g++`/`gcc` command from `instruction.md` — the agent edits
source on the host, whose newer glibc would otherwise break the binary in the
older task image.

For a single throwaway oracle check, run one task through `docker-oracle`
rather than reaching for a shell script — it is the same Docker flow and it
still writes the artifact:

```bash
python cli.py tasks run --tasks <task-name> \
  --tasks-root <checkout>/evaluation/harbor/tasks \
  --harnesses docker-oracle --out-json results/oracle-check.json
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
- `summary.per_harness`: pass rate with a `pass_rate_ci{}` interval, elapsed
  time, operation totals, `skill_invocation_rate` / `skill_invocation_n`, a
  rolled-up `cost{}` block (`total_cost_usd` is `null` when no call was priced;
  `cost_per_pass_usd`), and a `per_task{}` pass breakdown.
- `summary.comparisons`: `pass_rate_delta`, `normalized_gain`,
  `normalized_change`, `passed_delta`, `cost_delta_usd`, and a `mcnemar{}`
  significance block against `--baseline-harness` (below).

The artifact is schema-validated on write, like question/answer/eval/arms
artifacts. Per-run detail (the agent's `claude --output-format json` result, the
prompt, and `run.log`) is written under each cell's output directory.

## Statistics on the execution-verified track

Ground truth here is binary: the task's own test suite exited 0 or it did not.
That rules out the paired t-test the judged Q&A track uses — on 0/1 outcomes the
per-task deltas are `{-1, 0, +1}`, badly non-normal, and all of the information
about a difference sits in the *disagreements*.

So `summary.comparisons.<harness>.mcnemar` holds **McNemar's exact test**
(`agent_benchmarks/eval/binary_stats.py`), pairing on the `(task, repeat)` cell
against the baseline harness. It is computed automatically whenever
`--baseline-harness` is set; no flag to enable. The report renders it as
_Paired significance vs baseline (McNemar)_.

The block reports the whole 2×2 table, not just a p-value:

| Field | Meaning |
|---|---|
| `n_gained` | cells the treatment passed and the baseline failed |
| `n_lost` | cells the baseline passed and the treatment failed |
| `n_both_passed` / `n_both_failed` | the concordant cells |
| `paired_pass_rate_delta`, `ci_lo`, `ci_hi` | paired delta and its bootstrap interval |
| `p_exact` | two-sided exact binomial on the discordant count |
| `p_adjusted` | Holm-corrected across the non-baseline harnesses in the sweep |
| `correction_family` | always `harnesses` — the judged track's arm and interaction families are corrected separately |
| `n_excluded` | cells dropped from the pairing (see below) |
| `n_units`, `pseudo_replicated` | independent tasks behind `n` pairs, and whether they are fewer |

Note the two similarly named deltas. `mcnemar.paired_pass_rate_delta` is
`(n_gained - n_lost) / n` over the **shared** cells; its sibling
`comparisons.<harness>.pass_rate_delta` subtracts two marginal pass rates.

An errored cell is one whose harness raised (`metrics.error`: a docker build
failure or timeout, or an exec failure), or whose solver CLI made no attempt
(`metrics.solver_error`). It produced no verdict, so it is
missing data, not a 0. An agent that exceeds its timeout, or a verifier that
does, is a failure (reward 0, returncode 124), not an error: otherwise an arm
that hangs would score above one that fails fast.

- `per_harness.<h>` carries `errored` and `scored = n - errored`, and
  `pass_rate = passed / scored`. `per_task` carries `errored` too.
- `pass_rate_delta`, `passed_delta` and `cost_delta_usd` are null when the two
  arms lost different cells to errors, since an arm with fewer verdicts would
  look like fewer passes and less cost. Cells both arms lost cancel out. Each
  comparison also carries `errored` and `baseline_errored`.
- McNemar always pairs only the cells both arms scored; `n_excluded` counts
  the rest.

Four properties are worth internalising before reading the number:

- **Only discordant cells count.** Adding ten easy tasks both arms already solve
  changes `paired_pass_rate_delta` (it is a rate over all tasks) but leaves
  `p_exact` untouched. `n_both_passed` is reported so a null result can be told
  apart from a suite with no headroom left.
- **A small suite cannot reach significance.** Four fixes and zero regressions
  gives *p* = 0.125; six and zero gives 0.0312. That is the honest floor of a
  20-task suite, not a defect.
- **`--repeats` does not buy the power it looks like.** Repeats are paired as
  separate `(task, repeat)` cells, so `n` grows but the independent units do not:
  repeats of one task share its difficulty, and McNemar assumes independent
  pairs. `n_units` reports the distinct tasks, `pseudo_replicated` flags
  `n_units < n`, and the report prints a caveat — the p-value is then
  anti-conservative and should be read as a screening signal, not a claim at α.
  Adding *tasks* adds real power; adding repeats mostly reduces per-cell noise.
- **No discordant pair at all means no verdict.** `p_exact` and `significant` are
  `null`, and the report shows a dash. Absent evidence is not evidence of no
  difference.

`n_excluded` counts cells left out of the pairing, measured against every cell
either harness *attempted*: present for one harness only, or belonging to a row
whose harness itself errored (`metrics.error`, e.g. a docker build failure, or
`metrics.solver_error`).
Those are missing data, not verified failures — scoring them as failures would
charge infrastructure flakiness to the treatment.

The exact binomial is used rather than the chi-square approximation because the
discordant count on a suite this size is routinely under 10, where the
approximation is unreliable. It needs no SciPy, so this test is always available
— unlike the judged track's `p_ttest`.

Alongside the paired test, each harness and comparison carries per-arm lift
numbers. They use SkillsBench's lift formula but are not its leaderboard
numbers, so do not read the two side by side without the caveats below:

| Field | Meaning |
|---|---|
| `per_harness.<h>.pass_rate_ci` | Wilson 95% interval on `pass_rate`, over the same scored (non-errored) cells; same independence caveat as McNemar under `--repeats`. SkillsBench does not use Wilson: its paper uses a Wald interval (v4, App. G; a percentile bootstrap in v1) and its leaderboard a task-level `1.96·stdev(per-task means)/√87`, which is wider under repeats |
| `per_harness.<h>.skill_invocation_rate` | share of the rows reporting `metrics.n_skill_invocations` (errored rows excluded) where it is > 0; `null` when no row reports it. Only harnesses that write `metrics.n_skill_invocations` contribute; the key counts invocations of the treatment skill. A row marked `metrics.solver_error` is errored too and is left out |
| `per_harness.<h>.skill_invocation_n` | the rows behind `skill_invocation_rate` |
| `per_harness.<h>.cost.cost_per_pass_usd` | total cost / passes, only when every row, errored rows included, carries `metrics.cost_usd`. A runner-errored row (no `cost_usd`) or an agent timeout whose result was never parsed therefore nulls it for the arm |
| `comparisons.<h>.normalized_gain` | Hake's `(arm − base) / (1 − base)`, as SkillsBench uses it: the share of the baseline's headroom gained. It equals SkillsBench's per-configuration value only when every cell scored and rewards are binary (they average per-task mean rewards and count a missing cell as 0). Unbounded below (0.5 vs 0.95 is −9), so read regressions from the next field; `null` when the baseline passes everything, or when `pass_rate_delta` is withheld |
| `comparisons.<h>.normalized_change` | the Marx & Cummings piecewise formula applied to aggregate pass rates, in [−1, 1]: the gain above for a gain, `(arm − base) / base` (share of baseline passes lost) for a loss, 0 when equal. The halves are on different scales — at a 0.8 baseline +0.2 is +4 pp, −0.2 is −16 pp — so compare signs, not magnitudes across signs; `null` when both rates are 0% or both 100% (M&C drop that case), or when `pass_rate_delta` is withheld |

A with-skill arm whose `skill_invocation_rate` is near zero measures the
listing, not the skill: the lift, if any, did not come from the agent reading
it.

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
The two therefore need different statistics — continuous scores against a
baseline arm ([benchmarking-and-comparison.md](benchmarking-and-comparison.md))
versus paired binary outcomes against a baseline harness (above) — and their
numbers are not interchangeable. A skill that wins on the judged track has not
been shown to make anything run.

## External Sources

Executable tasks always come from a checkout of a content repository (there is
no bundled task tree), and skills can come from one too. Nothing here clones
anything — point the existing flags (`--tasks-root`, `skill:<path>`) at a
checkout you already have.
[external-content.md](external-content.md) is the canonical page for that: how
to lay a checkout out, how to scan it before you spend money on it, and what
every command does when a root is missing. This section covers only the
harness-specific part.

Scan the checkout first (`python cli.py catalog scan --root <checkout>`), then
use the entries it reports the same way as local ones:

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
task's own `task.toml` for the task *container*, defaulting to no network — a
task whose container legitimately needs network can declare
`network_mode = "public"`, alongside `cpus`/`memory_mb` if declared. The
`docker-claude` agent itself runs on the host and solves with the host's
network whatever the task declares (`metrics.isolation.network: open`).
