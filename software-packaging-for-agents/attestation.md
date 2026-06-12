# Design: the scorecard as a portable trust standard (attestation)

> **Status:** DRAFT — for team review. A cross-cutting design concern spanning
> [packaging](packaging.md), [discovery](discovery.md), and [feedback](feedback.md):
> how the scorecard becomes a *verifiable, portable credential* rather than a
> claim you have to take on faith. No code yet; a deliberate strategic bet, later
> than the core cycle.
> **Date:** 2026-06-02

## 1. The distinction: a better listing vs. the trust layer under every listing

The [scorecard](packaging.md) makes a package *vetted, not merely listed* — but
only if you trust *us*. Today the scorecard is evidence embedded in a package;
its credibility lives and dies with our platform.

The bet here is to make the scorecard a **signed, reproducible attestation** that
any consumer — including a *third-party* catalog — can verify without trusting
the issuer. That changes what the project is:

- **Without attestation:** we build a nice vetted catalog. It is *our* catalog;
  its trust does not travel.
- **With attestation:** the scorecard is a credential format others adopt. A
  marketplace (cursor.directory et al.) could ingest an Intel package *and its
  attestation* and rank it on demonstrated value, because the claim is verifiable
  independently of us. We stop competing with the marketplace and instead supply
  the **trust layer it structurally lacks**.

The analogy is a code-signing certificate or a TLS cert: the value is not the
certificate itself, it is that the whole ecosystem agrees to check it. A signed
scorecard is the agent-artifact equivalent — *proof of demonstrated value*,
portable across catalogs.

## 2. Why this is the natural answer to "vetted, not trending"

[`discovery.md`](discovery.md) argues popularity ranking buries niche
HPC/numerical tools, so the catalog must rank by *fit × vetted scorecard*. That
ranking is only as trustworthy as the scorecard behind it. An *attested*
scorecard is what lets the anti-trending claim survive contact with the outside
world: a never-trending oneMKL accuracy expert can carry a credential that a
third party can check and rank on — without the third party re-running the
benchmark or trusting our word.

This is the strategic complement to the un-trendy-expertise argument: the most
valuable expertise is the least trendy, *and* the way to make markets reward it
anyway is a credential they can verify.

## 3. What an attested scorecard contains

The repo already produces most of the provenance; attestation is making it
**complete, reproducible, and signed**, not inventing new measurement.

| Field | Source today | Role in the credential |
|---|---|---|
| `benchmark` + version | `agent-benchmark` git SHA; `schema_version` (`agent_benchmarks/artifacts.py`) | which engine/version produced the claim |
| `question_set_hash` | already threaded through the pipeline | *what* was tested — pins the test set |
| `judge_model` | eval config | *how* it was judged |
| `arms` + deltas | `report/arms_report.py` | the result (baseline vs package) |
| `task_results` | terminal-bench pass-rates (behavioral signal, see feedback.md §2.1) | hard outcome evidence, not just judge opinion |
| `target_version` | library/hardware version under test | what the claim is valid *against* |
| `run_manifest` | `agent_benchmarks/runner/manifest.py` | environment/inputs for reproducibility |
| `generated` (date) | run time | when — drives staleness ([feedback.md](feedback.md)) |
| `signature` | **new** | makes all of the above tamper-evident |

The first eight rows are the **reproducible-and-dated** foundation already called
for in [`feedback.md`](feedback.md) §3. Attestation adds the last row and a
verification path.

## 4. Reproducible first, signed second

Signing a non-reproducible number is theatre. The ordering is deliberate:

1. **Reproducible.** Given the same `run_manifest` + `question_set_hash` +
   `judge_model` + `target_version`, re-running yields the same scorecard (within
   a stated tolerance — judges are stochastic, so the credential records the
   tolerance/seed, not a false-exact value).
2. **Dated & versioned.** Every scorecard is a point-in-time claim tied to a
   library/hardware version; the [feedback loop](feedback.md) re-issues it.
3. **Signed.** Then, and only then, sign the canonicalized scorecard so a
   verifier can confirm it was issued by the named benchmark and not altered.

## 5. Verification path

A consumer (catalog, runtime, or auditor) can:

- **verify the signature** → the scorecard is authentic and unmodified;
- **inspect provenance** → see exactly what was tested, how, and against which
  version;
- **optionally re-run** → reproduce the claim from the `run_manifest` if they
  don't want to trust even a signed number.

Three escalating levels of trust — take the signature, inspect the provenance, or
reproduce it yourself — so the credential is useful to a casual consumer and to a
skeptical auditor alike.

## 6. Scope and non-goals

- **In scope (design):** the credential's complete field set, the
  reproducible-then-signed ordering, the verification path, and the federation
  intent.
- **Out of scope (for now):** the specific signing scheme / key custody / PKI,
  building a verifier service, and any standards-body or external-catalog
  negotiation. These are deliberately deferred — this doc fixes the *intent* and
  the field set so the core cycle can record everything a future attestation will
  need.

## 7. Open questions

- **Signing scheme & key custody.** Sigstore-style keyless, an org key, or
  in-toto/SLSA-style attestation? Who holds keys and how are they rotated?
- **Reproducibility tolerance.** What judge-score variance is acceptable for two
  runs to count as "the same" credential, and how is the seed/tolerance recorded?
- **Federation target.** Which external catalog(s) would consume an attested
  scorecard first, and what format do they need (e.g. an existing attestation
  envelope vs our own)?
- **Revocation.** When the [feedback loop](feedback.md) finds a scorecard stale or
  wrong, how is the old attestation revoked or superseded?

## 8. Relationship to the rest of the project

Attestation sits on top of the [scorecard](packaging.md) and depends on the
[feedback loop](feedback.md) keeping it reproducible and current; it is what lets
[discovery](discovery.md) rank on *verifiable* demonstrated value and what lets a
[served expert](serving.md) carry a credential anywhere it is spawned.
