# `data/` — curated benchmark fixtures

This directory holds the **curated, version-controlled inputs and reference
fixtures** for the LLM-evaluation track. Everything here is meant to be small,
reviewed, and reproducible — it is the committed counterpart to the throwaway
output that CLI runs write to the git-ignored `results/`, `reports/`, and the
default scratch dirs (`answers/`, `eval/`, `questions/`, `personas/`,
`baselines/`) at the repo root.

> Keep these names distinct from the Python package: `data/skills/` is *sample
> skill content*, while `doc_benchmarks/skills/` is the *loader code* for it.
> The same holds for `data/agent_profiles`, `data/questions`, and `data/eval`.

## Layout

| Path | What it is | Produced by / consumed by |
| --- | --- | --- |
| `questions/<product>_golden.json` | Hand-reviewed "golden" question sets | Auto-included by `cli.py evaluate`; input to `answers generate` / `arms run` |
| `questions/<product>.json` | Sample generated question sets | `cli.py questions generate` (curated snapshots) |
| `answers/<product>.json` | Sample WITH/WITHOUT answer pairs | Reference output of `cli.py answers generate` |
| `eval/<product>.json` | Sample judge scores | Reference output of `cli.py eval score` |
| `baselines/baseline.json` | Static docs-benchmark baseline snapshot | Compared against by `cli.py compare` |
| `skills/<name>/SKILL.md` | Agent skill fixtures (progressive-disclosure docs) | `skill:`/`skill-agent:` treatment arms |
| `agent_profiles/<name>.md` | Agent persona (system-prompt) fixtures | `profile:` treatment arm |

## Regenerating fixtures

These files are snapshots of the pipeline output. To refresh one, run the
relevant command and copy the result here, e.g.:

```bash
# regenerate the sample oneTBB answers fixture
python cli.py answers generate --product oneTBB \
  --questions data/questions/onetbb_golden.json \
  --output data/answers/onetbb.json
```

Only commit a regenerated fixture when the change is intentional and part of a
reproducible benchmark — otherwise let it land in the git-ignored scratch dirs.
