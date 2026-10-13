# Coding Harnesses And Task Runs

Executable task runs measure whether an agent can do the work, not only answer
questions about an API. The `tasks run` command runs executable task
directories through named harnesses, records operation telemetry, and compares
pass rate against a baseline harness.

## Task Layouts

Two layouts are read, and a root may mix them. `task.md` is read by
`tasks list`, `coverage` and `catalog scan`. No built-in harness runs a
`task.md` task yet (`benchflow:*` will, once #75 lands); a `command:` harness
runs whatever it is given. What each harness refuses follows the files it
reads: the `docker-*` harnesses record an errored cell, instead of a verdict,
for a task whose scripts are in `oracle/` or `verifier/` (they copy to
`/solution` and `/tests`), and the Harbor-backed ones (`codex`, `claude-code`,
`terminal-bench:<agent>`) for a task without a `task.toml`. A directory left by
`bench tasks migrate` that kept `task.toml`, `solution/` and `tests/` runs.

| Layout | Files | Oracle | Verifier |
|---|---|---|---|
| Harbor / terminal-bench | `task.toml` + `instruction.md` | `solution/solve.sh` | `tests/test.sh` |
| BenchFlow `task.md` (SkillsBench) | `task.md` (YAML frontmatter + instruction body) | `oracle/solve.sh` | `verifier/test.sh` |

Both carry the same tables (`metadata`, `verifier`, `agent`, and the sandbox
table, which BenchFlow schema 1.3 renamed from `environment` to `sandbox`;
either name is read, and a file declaring both is rejected, as BenchFlow
rejects it). A directory holding both files loads as `task.md` only when its
frontmatter has a BenchFlow key (`schema_version`, `metadata`, `verifier`,
`agent`, `sandbox`/`environment`, `oracle`); any other `task.md` there (no
frontmatter, Jekyll/Hugo frontmatter, an unclosed block) is an author's note,
and the task loads from `task.toml` with a warning (none for a note without
frontmatter). Discovery skips a lone `task.md` without frontmatter with a
warning; `load_task` on it raises. A lone `task.md` with frontmatter is a
task, whatever its keys. YAML and TOML dates and times become ISO strings, and
YAML sets sorted lists.

As in BenchFlow, a `task.md` body with a `## prompt` heading gives the agent
only that section; `## role:<name>`, `## scene:<name>` and `## user-persona`
sections are left out of it. Multi-role documents (`agents`, `scenes`, `user`
in the frontmatter) are not run as such: the one agent gets the base prompt.
BenchFlow's frontmatter shorthands (`verifier: <path>`, `oracle: <path>`,
`image:`, `profile:` / `profiles:`) are rejected with an error naming the key,
rather than read past: write the canonical tables. Other BenchFlow keys
(`agent.prompt_prefix`, `verifier.type`, `solution:`, `sandbox.image`, ...)
are not checked yet and are read past.

To convert between the two, use BenchFlow's own `bench tasks migrate`
(split → `task.md`) and `bench tasks export --target harbor` (`task.md` →
split) rather than a converter here.

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
- `docker-claude` — solve with `claude -p --output-format stream-json`
  **inside the task container**, with egress to the LLM endpoint only (see
  [What the agent can reach](#what-the-agent-can-reach)). The final result
  event carries `total_cost_usd`, token `usage`, `duration_ms`, `ttft_ms`, and
  `num_turns`, which are folded into the run artifact's `metrics{}`, together
  with `tool_calls` (by tool name) and `offered_skills`. A run the CLI
  ended with an error before any attempt carries `metrics.solver_error` and
  is counted as errored, not as a miss (see below). A solve that ran out of
  time is a miss: it carries `metrics.solver_timeout`, and stays in the
  comparison unless it also carries `solver_error` (a skill arm whose plugin
  did not load).
- `docker-claude-skill:<skill-path>` — `docker-claude` with the skill installed
  the way Claude Code installs one. This is the **with-skill treatment arm**;
  compare it against `docker-claude` (without-skill) as the baseline. See
  [How the skill arm offers the skill](#how-the-skill-arm-offers-the-skill).
- `docker-probe` — no LLM, free. Runs an isolation probe in exactly the work
  tree and environment `docker-claude` would get, writes
  `isolation_probe.json`, and passes only when nothing in
  [What the agent can reach](#what-the-agent-can-reach) is open. Run it before
  a paid sweep. `docker-probe:<skill-path>` also forbids that skill. Use it
  when the with-skill arm's skill lives outside the task's checkout, so the
  baseline is checked against the treatment it must not see.
- `docker-claude-host`, `docker-claude-host-skill:<skill-path>`,
  `docker-probe-host`, `docker-probe-host:<skill-path>` — the same, with the
  agent on the host. These are weaker: use them only where the in-container
  launch cannot run, and do not compare a host arm against a container
  baseline (`tasks run` warns).

### What the agent can reach

A task's `solution/` and `tests/` live beside the skills in one content
checkout. A solver that can read them copies the answer instead of solving the
task. A baseline arm that can read the skills is no longer a baseline. The
probe reports eight leak classes. Each is `open` or `closed`; `n/a` (nothing
to protect was declared) passes, and `untested` (the image lacks the tool, the
gateway lookup returned nothing, or the probe timed out) fails like `open`.
The result is in `metrics.isolation_probe` and `isolation_probe.json`:

| class | what the probe tries |
|---|---|
| `task_files` | read the task's `solution/`, `tests/`, `oracle/` or `verifier/`, or this task's output dir (the other arms' work trees, prompts and transcripts), by absolute path |
| `treatment` | read any `skills/` on the way up from the task (with or without a `.git`), or the `docker-probe:<skill>` skill, by absolute path. `n/a` if neither exists: nothing was tested, and that is not the same as `closed` |
| `operator_config` | read the operator's `~/.claude`, `~/.claude.json`, or `$CLAUDE_CONFIG_DIR` and its `.claude.json` |
| `checkout_walk` | find a `.git`, `task.toml`, or `CLAUDE.md` in a directory above the work tree |
| `network` | fetch `https://example.com/` through whatever proxy variables it was given; with `bash`, also a raw `CONNECT example.com:443` and a plain-HTTP `GET http://example.com/` through the proxy, and a direct TCP connect to `1.1.1.1:443` that ignores it. `untested` with no client at all |
| `env` | find the host value of a variable the allowlist drops in the environ of the probe, its parent chain or PID 1 (`/proc/<pid>/environ`); names in `env_leaked`. `n/a` if the allowlist dropped nothing |
| `docker_api` | a writable Docker or podman socket (rootful, rootless `/run/user/<uid>/...`, Desktop), or a daemon on the gateway's 2375/2376 (the host's loopback for a host launch); either gets around every other wall. `untested` when the gateway is unknown or not an IPv4 address. A `DOCKER_HOST` over tcp/ssh is not checked |
| `dns` | resolve a public name (`example.com`); an answer means queries reach a resolver outside the sandbox, e.g. a podman `--internal` network that forwards DNS upstream |

`docker-claude` runs the agent inside the task container, as uid 10001:

- **Grader files.** `solution/` and `tests/` are copied in only by the
  verifier, after the agent has exited.
- **Mounts.** Nothing is bind-mounted. Host files reach the container only
  by `docker cp`: the `claude` binary, the files named by the file-valued
  variables below (CA bundles, `AWS_SHARED_CREDENTIALS_FILE` with every
  profile in it, `AWS_CONFIG_FILE`, `GOOGLE_APPLICATION_CREDENTIALS`), and
  the skill arm's plugin at `/opt/abskill` (built with symlinks followed, as
  for the host arm).
- **Image needs.** A glibc image (the host's `claude` binary is copied in; a
  musl image fails the `--version` check), and an `/app` that uid 10001 can
  own (it is `chown`ed before the agent starts).
- **Memory.** The agent's CLI and its tmpfs HOME run inside the task's
  cgroup, so they count against `environment.memory_mb` (about 100 MB for a
  short session); the host launch ran outside it.
- **Network.** The container sits on a per-run `--internal` Docker network,
  which has no route out. The agent reaches the LLM through an allowlisting
  CONNECT proxy (`harnesses/egress_proxy.py`, stdlib only). It runs in a
  sidecar container on that network and the default bridge, and listens on
  its internal-network address only. The sidecar image is
  `python:3.12-slim` pinned by digest; set `AGENT_BENCH_PROXY_IMAGE` to a
  mirror (an offline runner, a Docker Hub rate limit). The sidecar holds the
  upstream proxy URL, credentials included.
  - **Allowlist.** Entries are `host:port`: the provider's hosts on 443 (the
    provider chosen as the CLI chooses it: Bedrock, then Foundry, then
    Vertex, each only for `1`/`true`/`yes`/`on`; Vertex's host follows
    `CLOUD_ML_REGION` as the CLI maps it, `global`, `us`, `eu` included), the
    `ANTHROPIC_BASE_URL` host on its own port, and the task's
    `environment.egress` entries. A bare `host` there means `host:443`; no
    wildcards, commas or leading/trailing dots.
  - **Plain HTTP.** An `http://` gateway such as LiteLLM is forwarded only
    directly. The request is rewritten to origin-form with `Connection: close`,
    so each connection carries one checked request. Plain HTTP is never
    chained through an upstream proxy, so a host behind one must be listed
    in `NO_PROXY`.
  - **Loopback.** A loopback base URL (`localhost`, `127.*`) fails fast,
    because no container can reach it; use `docker-claude-host` instead.
  - **Logging.** Every proxy decision is saved as `egress.jsonl` (an allowed
    one before the connect, so a pending CONNECT is logged too), and
    `metrics.egress` carries the `allowed`, `denied` and `errors` host sets
    and `denied_entries` (`host:port`).
- **`network_mode = "public"`.** It applies to the verifier only. The
  container joins the default bridge after the agent exits. Every
  uxlfoundation/skills task declares it, and none of their solutions or tests
  uses the network, so a task whose solve needs a host must list it under
  `environment.egress`.
- **Environment.** HOME is its own tmpfs, `/run/abhome`; the image's `/tmp`
  is left alone. The environment is:
  - the provider-credential allowlist;
  - the proxy (also as `ALL_PROXY` and `FTP_PROXY`), and
    `NO_PROXY=localhost,127.0.0.1,::1`. They replace what the Docker client
    injects from `proxies.default`: a `NO_PROXY` would send an LLM host around
    the proxy, an `ALL_PROXY` would hand the agent the client's credentials;
  - `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`;
  - file-valued variables (`NODE_EXTRA_CA_CERTS`, `SSL_CERT_FILE`,
    `AWS_SHARED_CREDENTIALS_FILE`, `GOOGLE_APPLICATION_CREDENTIALS`, ...),
    whose file is copied in and re-pointed.

  It reaches `docker exec` in a 0600 `--env-file`, never on argv. The `docker`
  CLI keeps the operator's environment, so its context and `DOCKER_HOST` stay
  the operator's.
- **Fails before the agent starts.** A setup that cannot work in a container
  errors the cell after its image build: a loopback base URL or upstream
  proxy, Bedrock with only an `AWS_PROFILE` or SSO login, Vertex without
  `GOOGLE_APPLICATION_CREDENTIALS` or `CLAUDE_CODE_SKIP_VERTEX_AUTH`, a
  provider the allowlist has no hosts for (`anthropicAws`, `mantle`, ...), or
  an `environment.egress` entry that is a URL. A `claude` binary that cannot
  run in the image (a musl image) is caught after the container starts.
- **Lifetime.** The task container lives for the solve timeout plus the
  verifier timeout plus 10 minutes (at least 30). A verifier that finds the
  container gone errors the cell instead of scoring it 0.
- **Leftovers.** The network, sidecar and task container carry the label
  `agent-bench.run=<id>`, and the sidecar exits after 4 h on its own. A
  killed harness can also leave its `abenv-*` dir, whose env file holds the
  agent's credentials. Clean up with:

  ```bash
  docker ps -aq --filter label=agent-bench.run | xargs -r docker rm -f
  docker network ls -q --filter label=agent-bench.run | xargs -r docker network rm
  rm -rf "${TMPDIR:-/tmp}"/abenv-*
  ```

The launch goes only through the Docker API, never through a bind mount or a
listener in the harness process. It therefore works the same with a local
daemon and on a Docker-in-Docker CI runner. CI's `external-catalog-smoke`
job requires a container probe to report every class closed. It also
requires the proxy to have denied the probe's `example.com` CONNECT (`:443`)
and its plain-HTTP GET (`:80`), which shows both reached the sidecar.

One gap remains: a service on the Docker host that listens on the internal
network's gateway address or on `0.0.0.0` is reachable.

The `-host` variants run the agent on the host instead. The host cannot hide an
absolute path or close the network, so these harnesses state what they seal in
every run's `metrics.isolation`. What they do:

- solve in a fresh `abrun-*` temp tree outside any checkout;
- point `HOME` and `CLAUDE_CONFIG_DIR` at empty scratch dirs;
- pass only an allowlist of variables;
- reach `task_files`, `treatment`, `operator_config`, `network` and `env` by
  absolute path, proxy or `/proc`, as a host probe shows.

`env` is open on the host because the agent runs as the operator's uid: it can
read the harness's `/proc/<pid>/environ` (every variable the allowlist
dropped) and its command line and cwd (`--tasks-root`, `--output-dir`, the
skill arm's path). Yama `ptrace_scope=1` does not stop this; it only gates
attach.

Both launches run `claude` with `--tools Read,Edit,Write,Bash,Glob,Grep,Skill
--setting-sources "" --strict-mcp-config --no-session-persistence`, built-in
plugins disabled through `--settings`, and
`CLAUDE_CODE_DISABLE_BUNDLED_SKILLS=1`. An older launch used `--allowedTools`,
which only pre-approves tools, so `WebFetch`, `Agent`, `Skill`, and the
operator's skills, CLAUDE.md files and MCP servers were loaded in both arms.
The Bash tool can still start a nested `claude -p` with the default tool set;
its spend is not in the outer `total_cost_usd`.

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
unknown model id), or a skill arm whose plugin did not load ("treatment not
offered"), also carries `metrics.solver_error`. The runner counts that cell
as errored, like `metrics.error`: it is out of `pass_rate` and out of the
McNemar pairing (`n_excluded`), so do not drop cells by hand. An error after
an attempt (a 529 at turn 40, `prompt_too_long` in a skill arm that read too
much) is the arm's own outcome and is scored. So is a host-launch CLI that dies with no
result object (`terminal_reason: no_result`) after it edited the work tree; with
the tree untouched, or in the container launch, it is a `solver_error`. A timed-out solve is a model miss and
is not marked `solver_error` (it carries `metrics.solver_timeout`); it stays in,
or the arm that times out more would look better than it is. Without `--model`,
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

### How the skill arm offers the skill

The arms differ by the skill and one notice, and by nothing else:

- **Delivery.** The skill directory is wrapped in a one-skill plugin and passed
  with `--plugin-dir`, at `/opt/abskill` in the container (outside `/app`, and
  removed before the verifier runs) or beside the scratch work tree on the
  host. The agent loads it with its own `Skill` tool. The skill's top-level
  `evals/` (its prompts and expected outputs) is not copied. Symlinks are
  copied as the files they point to, and only when they point inside the
  skill directory and outside its `evals/`: a link out of the skill could
  ship a task's `solution/` and `tests/`, and a link to an ancestor would copy
  the checkout into itself. Such a skill fails the cell before the image build.
  - `$CLAUDE_CONFIG_DIR/skills` does not work here: it is not loaded under
    `--setting-sources ""` (measured, Claude Code 2.1.286).
  - `--setting-sources project` would also read the task tree's own
    `.claude/settings.json` and `CLAUDE.md`.
- **Tool set.** Both arms have the `Skill` tool. With it on, Claude Code also
  offers 13 bundled skills, two built-in plugins' skills, and any managed
  (policy) skill under `/etc/claude-code`. Both arms switch those off. In the
  container only the core `doctor` command remains; the host route also lists
  `design`, which the model cannot invoke. Any other offered skill is recorded
  in `metrics.unexpected_skills`, so a later CLI that adds one to both arms
  shows up in the rows.
- **Frontmatter.** The skill's frontmatter is part of the treatment. A skill
  with `model:` or `context: fork` is refused (a forked subagent can switch
  models mid-cell), and so is one with `disable-model-invocation: true` (the
  agent could never load it) or `hooks:` (code or another model runs in the
  skill arm only, and none of it shows in `tool_calls`).
- **Notice.** The skill arm's prompt opens with a fixed notice: a skill named
  `<plugin>:<plugin>` (the id the CLI lists it under) is installed; load it before you start, and trust the environment
  where it disagrees. The notice names no task, API or fix, and follows
  intel/skills' `evaluation/harbor/instructions/use-<skill>.md`. Without it the
  arm would also measure whether the description gets the skill selected,
  which is a second variable in the reward delta. Measure discoverability
  separately. Changing the notice changes what past deltas mean.
- **Evidence it reached the agent.** Read from the stream, per cell:
  - `metrics.offered_plugins` and `metrics.offered_skills` are what the
    session's `init` event lists, with `metrics.plugin_errors` when it reports
    any. If the treatment's plugin is not in `offered_plugins`, it did not
    load, and the cell gets `metrics.solver_error: "treatment not offered:
    ..."`. (`offered_skills` lists what a user can invoke, so a
    `user-invocable: false` skill is missing from it even when it loaded.)
  - `metrics.n_skill_invocations`, on skill-arm rows only, counts `Skill`
    calls for the treatment that the CLI did not reject: by `<plugin>:<plugin>`
    or the frontmatter name (a leading `/` is stripped), or by the command the
    CLI resolved the call to. At 0 the agent never loaded the skill through
    the `Skill` tool; it may still have `Read` the `SKILL.md` under the plugin
    directory, which this does not count. BenchFlow rows use the same key but
    count every successful skill load, distractors included, so the two are
    not the same rate.
  - `metrics.treatment` records the skill's name and the plugin id it was
    installed under. The plugin id is a slug of the name (`[a-z0-9_-]`),
    because Claude Code refuses a plugin name with whitespace or any of
    `@ : / \`.
  - A solve that timed out keeps the stream it produced before it was killed,
    so these fields are filled in for it too. It is marked
    `metrics.solver_timeout`, and counts as a miss unless the plugin also did
    not load (`solver_error`).
- **Comparability.** The baseline changed with this delivery: it now has the
  `Skill` tool, with the bundled, built-in-plugin and policy skills off.
  `docker-claude` numbers from before it are not a baseline for runs after it.
- **Inputs.** `docker-claude-skill:<path>` takes a skill directory or its
  `SKILL.md`. A path with no loadable `SKILL.md`, a refused link or refused
  frontmatter fails the cell before the image build, rather than announcing a
  skill that is not there.
- **Tokens.** `prompt_tokens` and the other token counts are summed over the
  result's `modelUsage`, which also covers helper models; the result's own
  `usage` covers the parent session only. `metrics.models_used` lists them.

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
pass the host proxy through to `docker build` (corporate networks), run the
oracle and the verifier as root for images that set a non-root `USER` (the
agent runs as uid 10001), install the skill tree as a plugin (not just
`SKILL.md`; without its top-level `evals/`), and re-run the `g++`/`gcc` command from `instruction.md` inside
the container after the solve — a `-host` agent builds against the host's
newer glibc, and an in-container agent may not have built at all.

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
- `results[].passed`: verifier pass/fail. If a reward file is present, its
  number is `results[].reward`: `1.0` passes, and anything lower, including
  partial credit such as `0.75`, is kept as the reward and counts as a fail. If
  no reward is found, the adapter's exit code is used as the fallback.
- `results[].metrics`: for LLM harnesses (`docker-claude*`), the per-run
  `UsageRecord` fields — `cost_usd`, `prompt_tokens`, `completion_tokens`,
  `total_tokens`, `cache_read_tokens`, `cache_write_tokens`, `latency_sec`,
  `ttft_sec`, `n_calls` (agent turns) — plus `operation_count` /
  `operations_by_type`, `model`, `models_used`, `terminal_reason`,
  `tool_calls` and `offered_skills`, and when set `offered_plugins`,
  `plugin_errors`, `unexpected_skills`, `solver_error`, `solver_timeout` and
  `recompile_failed`. Skill-arm rows add `treatment` and
  `n_skill_invocations`. The `docker-claude*` and `docker-probe*` rows
  also carry `isolation` (`agent_location`, `work_tree`, `operator_config`,
  `env`, `tools`, `host_filesystem`, `network`, and `memory` for the
  container launch); container rows carry `egress`, probe rows
  `isolation_probe`.
- `summary.per_harness`: pass rate with a `pass_rate_ci{}` interval, elapsed
  time, operation totals, `skill_invocation_rate` / `skill_invocation_n`, a
  rolled-up `cost{}` block (`total_cost_usd` is `null` when no call was priced;
  `cost_per_pass_usd`), and a `per_task{}` pass breakdown.
- `summary.comparisons`: `pass_rate_delta`, `normalized_gain`,
  `normalized_change`, `passed_delta`, `cost_delta_usd`, and a `mcnemar{}`
  significance block against `--baseline-harness` (below).

The artifact is schema-validated on write, like question/answer/eval/arms
artifacts. Per-run detail is written under each cell's output directory: the
agent's result event (`solver.json`) and full stream (`solver.jsonl`; the
values of the agent's credential variables are redacted, also line by line and
in their JSON-escaped form, but anything else the agent printed, such as a credential file's contents, is not, so do not share
it),
`prompt.txt`, `run.log`, `reward.txt`, the agent's final tree (`work/`),
`egress.jsonl` for a container launch and `isolation_probe.json` for a probe.

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

The `docker-*` harnesses read `network_mode` from the task's sandbox table (`[environment]` in
`task.toml`), alongside `cpus`/`memory_mb`. Without it the task container has
no network. `network_mode = "public"` gives `docker-oracle` bridge for its
solve and verify, but for `docker-claude` it applies to the **verifier only**:
the agent solves on the internal network, and a solve that needs a host (pip,
a package mirror) must list it under `environment.egress`. A `-host` agent
solves with the host's network whatever the task declares
(`metrics.isolation.network: open`).
