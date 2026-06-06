# Design: the feedback loop — making the scorecard living

> **Status:** DRAFT — for team review. Defines how the cycle in the
> [architecture](architecture.md) closes: real use and upstream change flow back
> into re-scoring and re-authoring. No code yet.
> **Date:** 2026-06-02

## 1. The problem: a scorecard stamped once goes stale

A package ships with a [scorecard](packaging.md) — its credential. But that
credential is true only for the moment it was generated: a fixed question set, a
fixed judge, a fixed library version. Two things erode it over time:

1. **Reality drifts from the test set.** Real developers ask things our
   persona-generated questions never covered; the expert hits problems the
   benchmark never posed.
2. **Upstream drifts from the package.** The library's docs and APIs change; the
   skill and the scorecard silently fall behind.

An honest "vetted, not trending" catalog ([`discovery.md`](discovery.md)) cannot
rest on a stale stamp. The loop must keep the credential current.

## 2. Three feedback arrows

```text
   SERVE ───── real questions, failures, corrections ─────► MEASURE
   (telemetry)                                              (new golden questions,
                                                             re-score → new scorecard)

   UPSTREAM docs change ── freshness signal ──► PACKAGE
   (libraries.yaml sources)                     (mark scorecard stale, re-evaluate)

   TELEMETRY ── gaps, mis-triggers, loops ──► AUTHOR
                                              (what to distill / fix next)
```

### 2.1 Serve → Measure (the living test set)

Production telemetry from [serving](serving.md) is exactly the input the
`questions` track wants:

- Real problem statements become candidate **golden questions** (run through the
  existing `questions generate`/`refine`/`panel` validation, so the test set
  grows from reality rather than only from synthetic personas).
- Observed failures become *targeted* questions that probe known weak spots.
- Re-running the arms (`eval/arm_runner.py`) on the expanded set produces a fresh
  scorecard. The package's credential is now *living*, not a one-shot stamp.

### 2.2 Upstream → Package (freshness-triggered re-packaging)

The static benchmark already scores files by modification age
(`freshness_lite`). Point it the other way:

- When a library's tracked doc sources (`libraries.yaml`) change, mark every
  package that depends on it as **scorecard-stale** in the discovery graph.
- CI re-evaluates stale packages and re-emits the scorecard; the catalog shows
  "last verified against oneTBB vX; docs unchanged since `<date>`".
- This answers the packaging-format versioning question: a package version is
  tied to (library version × question-set hash), and staleness is a first-class,
  visible property — not a guess.

### 2.3 Telemetry → Author (what to build next)

Where agents loop, mis-trigger a skill, or work around a missing capability tells
the [author](authoring.md) track precisely what to distill or repair — turning
diffuse usage into a prioritized authoring backlog. A skill whose trigger
description is too narrow (never fires) or too broad (fires wrongly) shows up here
before it shows up as a bad review.

## 3. Trust: the scorecard as a dated, reproducible credential

Because the loop re-scores, every scorecard must be **reproducible and dated**:
which benchmark, question-set hash, judge model, library version, and date. This
keeps re-scores comparable over time and makes the credential auditable — the
foundation any "vetted catalog" claim rests on. Making that credential *portable*
— signed so a third-party catalog can verify it without trusting us — is the
cross-cutting [attestation](attestation.md) design, built directly on this
reproducible-and-dated foundation.

## 4. Guardrails

- **No silent ranking drift.** When a re-score changes a package's catalog
  ranking, that is a visible, logged event — not an invisible reshuffle.
- **Confounder discipline carries over.** The benchmark's existing rule (hold
  model, question set, and judge fixed across arms) applies to re-scores too:
  compare like with like, or the "living" scorecard becomes noise.
- **Telemetry is opt-in and aggregated.** See the privacy open question in
  [`serving.md`](serving.md) §7.

## 5. Open questions

- **Question-set growth policy.** How fast does the golden set grow from
  telemetry, and how is it kept balanced (not flooded by one popular problem)?
- **Re-score cadence & cost.** On every upstream change, on a schedule, or on a
  staleness threshold? Re-scoring N packages × M arms × a judge is not free.
- **Promotion/demotion.** Does a dropped re-score auto-demote a package in the
  catalog, or flag it for maintainer review first?

## 6. Relationship to the rest of the project

Feedback is the arrow that turns the linear pipe into a cycle. It connects
[serve](serving.md) back to [measure](../doc-benchmark/) and
[author](authoring.md), and it is what lets [discover](discovery.md) honestly
claim its rankings reflect *current* demonstrated value.
