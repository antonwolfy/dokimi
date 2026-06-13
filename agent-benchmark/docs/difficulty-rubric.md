# Difficulty & Level Rubric (Performance Skills)

This rubric makes difficulty a **measured, reproducible axis** rather than an
intuition tag, and separates it from a second orthogonal axis — **level**
(how deep into the performance workflow the question reaches). Both apply to
awareness questions (`data/questions/*_golden.json`) and to executable tasks
(`terminal-bench-tasks/*`).

Why two axes: a question can be *deep in the workflow but easy* ("produce a
report" when the evidence is unambiguous) or *shallow but hard* (a single
counter reading that is a trap). Collapsing them into one `easy/medium/hard`
tag hides where a skill actually helps. Scoring lift on the full
`level × difficulty` grid is the goal.

## Axis 1 — `level` (workflow depth)

| Level | The agent must… | Output shape | Does NOT include |
| --- | --- | --- | --- |
| `triage` | Interpret symptoms/counters and **route** to the right next step or set up evidence collection. | A regime call + the next workflow/command. | Proposing a concrete code fix. |
| `diagnosis` | From evidence, **classify the specific pattern**, propose a fix *shape*, and state how to verify it. | Pattern name + fix shape + verification expectation, scoped to one bottleneck. | Rebuilding, rerunning, or producing a full deliverable. |
| `end_to_end` | Orchestrate the **full lifecycle or produce a complete deliverable**: baseline → change → rebuild → rerun → compare → report; multi-step iteration loops; new production code with dispatch/fallback/tests; or evaluation/meta design. | A plan or artifact spanning generate → build → verify → report. | (terminal level) |

## Axis 2 — `difficulty` (cognitive load)

| Tier | Definition | Discriminator |
| --- | --- | --- |
| `easy` | One clear signal maps to one canonical next step. | A correct answer needs no ruling-out of alternatives. |
| `medium` | Competing or ambiguous signals; the agent must rule out plausible distractors before committing. | At least one tempting wrong answer must be rejected with evidence. |
| `hard` | Multi-step evidence chains, ABI/semantic/FP-order risk, heterogeneous-hardware constraints, iteration/unmasking, or a **negative** case where the right answer is "do not optimize yet / gather more evidence." | Correctness depends on safety reasoning or on *not* acting, not just pattern recall. |

`difficulty` is independent of `level`: assign each separately, then place the
item in the grid.

## Coverage grid (target ≥4–6 items per cell)

The minimum-useful set in the evaluation plan (60–80 questions) should fill this
grid rather than pile onto the diagonal. Current `intel_performance_skills_golden.json`
distribution at backfill time (2026-06-12, 40 questions):

| level \\ difficulty | easy | medium | hard |
| --- | --- | --- | --- |
| `triage` | 6 | **0** | **0** |
| `diagnosis` | 2 | 21 | 3 |
| `end_to_end` | **0** | **0** | 8 |

Bold cells are gaps. The set is currently near-diagonal (triage⇒easy,
end_to_end⇒hard), which prevents isolating skill lift by level *and* difficulty.
Subsequent question growth targets the bold cells first, e.g.:

- `triage × medium/hard`: counter readings with competing signals or a
  "collect more evidence first" correct answer.
- `end_to_end × easy/medium`: a short, unambiguous report or single-fix
  lifecycle where the work is procedural, not diagnostic.
- `diagnosis × easy`: a textbook single-pattern detection with no distractor.

## Negative & adversarial cases

A `metadata.negative_case: true` flag marks items whose correct answer is to
**withhold a fix** (insufficient evidence, unsafe ABI/FP change, non-editable
artifact, wrong layer). These are the highest-signal items for distinguishing a
reasoning skill from keyword matching, and should appear across `medium` and
`hard` at every level.

## Applying the rubric

1. Assign `level` and `difficulty` independently using the tables above.
2. Record `level` as a top-level question field; keep `difficulty` as today.
3. For tasks, mirror the tags in `task.toml` `[metadata]` (`difficulty` already
   exists; add `level`).
4. When generating new items, target the bold grid cells and tag
   `negative_case` where applicable.
5. Report evaluation lift sliced by `level × difficulty`; never blend the
   awareness grid with executable task pass rate.
