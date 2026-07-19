# Design: the `intel/skills` catalog — tiered publishing, benchmark-gated quality, Intel-issued certification

> **Status:** DRAFT — for team review. Proposes answers to
> [`packaging.md`](packaging.md) Q5b (org catalog & marketplace listing) and
> the signing-scheme open question in [`attestation.md`](attestation.md) §7 —
> three recommendations below, not yet team decisions. Builds on the
> competitive-signal analysis in the [README](README.md).
> **Date:** 2026-07-14

## 1. Landscape evaluation — what each existing catalog gets right, and what to avoid

Before deciding our own shape, an honest evaluation of the five approaches
already in the wild, since we intend to seed from one of them rather than
design from scratch.

| Repo | What it actually is | What to take | What to avoid / gap |
|---|---|---|---|
| [`anthropics/skills`](https://github.com/anthropics/skills) | The format-defining reference implementation + a Claude Code plugin marketplace | The `SKILL.md` frontmatter contract (`name`/`description`, progressive disclosure) — this is the substrate everything else builds on | It is a *format* reference, not a catalog-governance reference — no signing, no trust ladder, no benchmark gate. Not a model for *our* catalog, only for the artifact shape. |
| [`intel/intel-performance-skills`](https://github.com/intel/intel-performance-skills) | One hand-authored, in-repo skill collection (3 skills, composable hand-off) | Real evidence that composable, cross-runtime `SKILL.md` skills work today and that Intel can author them well | No scorecard, no trust metadata, no signing, no CI-visible validation. It is a *source*, not a catalog — confirms [`authoring.md`](authoring.md) §1's framing exactly. |
| [`nvidia/skills`](https://github.com/NVIDIA/skills) | Org-level **mirror-only** catalog: daily sync from product repos, never authored in-repo | The mirror-not-source discipline (`components.d/` per-product onboarding), the Tier-3 eval-dataset publishing gate, and an org-owned signing root (`model_signing` + `nv-agent-root-cert.pem`) that makes the credential verifiable independent of GitHub | Heavier to bootstrap (requires every product team to onboard before anything ships) and the roadmap items (security scanner, `skill-card` schema) are stated but not shown in detail — we can't audit the actual scan logic, only the claim. |
| [`amd/skills`](https://github.com/amd/skills) | Org-level **federated** catalog: explicit two paths — in-repo incubator *or* pinned-commit pointer to a product repo (`sources.yml`), with a documented "graduate" lifecycle | The **incubator → graduate** lifecycle is the single best governance idea here: a skill can start living in the catalog and move to a product repo later "with no change for installed users." Directly informs §2 below. | Self-labeled "Tech Preview" — no evidence yet of the trust/signing rigor NVIDIA or even the napetrov prototype show. |
| [`napetrov/skills`](https://github.com/napetrov/skills) | A working, code-complete prototype of an org catalog: federated `source.*`/`catalog.*` split, 5-level trust ladder, working security-pattern scanner, per-file SHA-256 manifest, OIDC-only release chain | This is the most *inspectable* of the five — every claim is backed by runnable code we read directly (`tools/validate-skills-security.js`, `tools/generate-skill-manifest.js`, `.github/workflows/release.yml`). Directly reusable as the seed. | v0.1.0, 2 skills, no scorecard field at all (`evals/` explicitly deferred) — the one thing it does *not* have is exactly what `agent-benchmark` supplies. |

**Verdict:** no existing catalog combines a real benchmark-driven quality gate
with org-issued signing. NVIDIA has signing but no eval engine of ours; AMD has
governance lifecycle but shallow trust tooling; napetrov's prototype has the
most rigorous trust/CI tooling but zero benchmark integration. Intel's
differentiator — and the reason to build rather than merely federate into
someone else's catalog — is `agent-benchmark` itself. Sections 2–4 propose how
to combine napetrov's tooling shape, AMD's lifecycle idea, and our own
benchmark, with a signing-authority recommendation for team review.

## 2. Proposal: a tiered publishing model, not one-size-fits-all

Not every skill deserves — or can safely have — its full content copied into
`intel/skills`. We publish in **two tiers**, decided per skill, not per source
repo:

### Tier 1 — Direct publish (full content lives in the catalog)

The catalog carries the complete `SKILL.md` (+ `references/`, trivial helper
scripts). Criteria to qualify:

- No bundled executable beyond read-only/reporting helpers (the `dpnp-quickstart`
  shape — `scripts/collect_env.py` reports environment facts, changes nothing).
- No hardware- or driver-specific setup requiring the [setup-guide](authoring.md)
  §3 artifact.
- Upstream content is stable enough that a point-in-time copy won't drift
  materially before the next scorecard re-run ([feedback.md](feedback.md) §2.2
  freshness signal still applies, but staleness risk is low).
- Passes a security-pattern scan and smoke checks with the full artifact
  present — reusing the napetrov prototype's tooling
  (`tools/validate-skills-security.js` et al., see §1's table), not a new
  checker. This is a separate, cheaper pre-check that runs before the §3
  benchmark gate, not part of it.

### Tier 2 — Reference publish (thin wrapper; content stays at the source)

The catalog carries only a **trigger-and-pointer skill**: a short `SKILL.md`
that states *when to engage* and names the authoritative source, plus a pinned
`ref` (commit or tag) — no copy of the deep workflow content. This is not a
new format we're inventing: it is exactly the shape already shipped in
[`napetrov/skills`](https://github.com/napetrov/skills)'s
[`linux-perf-repair`](https://github.com/napetrov/skills/tree/main/skills/linux-perf-repair)
skill, which wraps `intel/intel-performance-skills` this way today. Criteria
that route a skill here:

- Bundled scripts that need provenance/licensing review before distribution
  (mirrors the terminal-bench `PROVENANCE.md` discipline already required in
  [`packaging.md`](packaging.md) §6).
- Hardware/environment setup guides (Gaudi, Xeon/AMX, GPU Max, NPU bootstrap) —
  the highest-value, highest-risk artifact per [`authoring.md`](authoring.md) §3;
  these must stay owned and versioned by the product team, not forked.
- Product teams that want to retain editorial control and their own release
  cadence — the AMD "graduate" lifecycle direction (§1 above), inverted: it
  starts *and stays* at the source; the catalog only ever points at it.
- Content that changes fast enough that a daily-mirror model (NVIDIA's
  approach) would still drift between benchmark re-scores — a pinned-ref
  pointer makes that staleness a visible, checkable property (`ref` age)
  instead of a silent copy divergence.

### Routing is a benchmark-pipeline output, not a manual call

Whether a skill lands in Tier 1 or Tier 2 falls out of the existing
[`authoring.md`](authoring.md) §2 distill → measure → refine loop: if
distillation converges on a self-contained thin skill with no bundled
executable and no setup-guide dependency, it ships Tier 1; if the candidate's
value is inseparable from scripts, a setup guide, or fast-moving upstream docs,
it ships Tier 2. The loop already produces this signal today — packaging just
has to read it.

## 3. Proposal: the benchmark is what makes either tier a *good* skill

Both tiers pass through the **same quality gate** — tiering only decides where
content physically lives, never whether it was benchmarked. Concretely:

1. No skill — hand-authored or distilled — enters `intel/skills` without first
   running the existing arms machinery
   ([`authoring.md`](authoring.md) §2: `skill:`/`skill-agent:` treatments via
   `agent-benchmark/agent_benchmarks/eval/arm_runner.py`) against baseline.
2. The existing hand-authored fixtures (`onetbb-quickstart`,
   `intel-performance-patterns`, `dpnp-quickstart` in
   `agent-benchmark/data/skills/`) are **not exempt** — they get retrofitted
   through this same loop before their catalog entry ships, exactly as
   [`authoring.md`](authoring.md) §1 already commits to ("ingest them … score
   them through the same arms as any other skill").
3. `BENCHMARK.md` — a file name and shape [`napetrov/skills`](https://github.com/napetrov/skills)
   already requires per skill — should stop being a placeholder and become a
   rendering of the per-arm delta [`packaging.md`](packaging.md) §2's
   `scorecard` object already defines (baseline vs. candidate score, and the
   question-set hash). Note this rendering step does not exist today:
   `agent-benchmark/agent_benchmarks/report/arms_report.py` currently produces
   a generic treatment-arm comparison, not a per-skill `BENCHMARK.md` file, and
   has no terminal-bench pass-rate field — wiring that output into a
   per-skill `BENCHMARK.md` (and, per open question in §6, possibly into
   `skill-card.json`) is new work this proposal creates, not something
   `agent-benchmark` already does.
4. Refine loops on low-scoring questions ([`authoring.md`](authoring.md) §2)
   before acceptance — a skill that doesn't move the score against baseline is
   rejected outright, Tier 1 or Tier 2.
5. [`feedback.md`](feedback.md)'s re-scoring loop applies identically to both
   tiers post-publish: Tier 1 re-scores on a schedule against the copied
   content; Tier 2 re-scores whenever the pinned `ref` is bumped.

This would be the concrete difference from every peer catalog in §1's
landscape table: none of them pairs tiered publishing with a real,
already-built benchmark engine as the shared gate.

## 4. Proposal: Intel as the certification/signing authority

Recommendation: the catalog's credential should be **signed by Intel**, not
left at GitHub-native attestation alone. This follows NVIDIA's model
([`nvidia/skills`](https://github.com/NVIDIA/skills): `model_signing` verified
against a bundled `nv-agent-root-cert.pem` trust anchor) rather than the
napetrov prototype's lighter `github-attested`-only status, and would answer
[`attestation.md`](attestation.md) §7's "Signing scheme & key custody" open
question as **org key, not Sigstore-keyless** — a security-sensitive,
hard-to-reverse choice that needs explicit team sign-off before any
implementation starts, not just this document's recommendation.

- **Ordering unchanged**: [`attestation.md`](attestation.md) §4's
  reproducible-then-signed sequence still governs — the scorecard from §3 must
  be reproducible and dated *before* Intel signs it. Signing a non-reproducible
  number is still theatre.
- **What gets signed differs by tier**: Tier 1 would sign the full artifact
  hash (mirroring `napetrov/skills`'s per-file SHA-256 `skills.lock.json`,
  extended with an Intel signature over the aggregate hash instead of only a
  GitHub attestation). Tier 2 would sign the wrapper + pinned `ref`, not the
  upstream content Intel does not own — the signature would be a claim about
  "Intel vetted this pointer and its scorecard," not "Intel authored this
  content."
- **Verification path**: unchanged from [`attestation.md`](attestation.md) §5 —
  a consumer could verify the signature against an Intel-published trust
  anchor (our equivalent of `nv-agent-root-cert.pem`), inspect the provenance
  fields, or reproduce the run themselves. Three escalating trust levels, same
  as designed.
- **Why not GitHub-attestation-only**: `attestation.md` §1 already frames the
  goal as a credential a *third-party* catalog can verify "without trusting
  the issuer." A GitHub Artifact Attestation is still, ultimately, a claim
  rooted in trusting GitHub's OIDC issuer; an Intel-issued signature would
  travel the way that section's code-signing-certificate analogy implies.
  **Caveat, unlike the NVIDIA comparison in §1**: this document has no
  evidence Intel already operates equivalent signing/PKI infrastructure for
  other artifacts — [`attestation.md`](attestation.md) §6 explicitly lists
  "the specific signing scheme / key custody / PKI" as out of scope and
  deliberately deferred. Standing up an Intel-held root of trust may be new
  infrastructure work, not reuse of an existing capability; that cost needs
  to be scoped before this recommendation is adopted.
- **Key custody / rotation** stays fully open (still tracked in
  [`attestation.md`](attestation.md) §7) — this section only recommends *who*
  would hold signing authority (Intel), not the custody or rotation mechanics.

## 5. Proposed answers to existing open questions

None of the below is a team decision yet — this section states what this
document recommends for each open question, pending review:

- [`packaging.md`](packaging.md) Q5b ("do we stand up an official `intel/skills`
  catalog … which marketplace(s) do we list on") — **proposed**: yes, seeded
  from [`napetrov/skills`](https://github.com/napetrov/skills)'s tooling
  shape, with the Tier 1/Tier 2 split from §2. External marketplace listing
  (skills.sh, plugin marketplaces, ClawHub, Hermes Hub) would be sequenced
  *after* the certification chain in §4, same order NVIDIA follows (sign
  first, syndicate second) — which marketplace(s) exactly is not addressed
  here and stays open.
- [`attestation.md`](attestation.md) §7 "Signing scheme & key custody" —
  **proposed**: org key held by Intel, not Sigstore-keyless (see §4's caveat
  on the infrastructure cost this implies). Custody and rotation mechanics
  remain fully open.
- [`authoring.md`](authoring.md) §6 "Reuse across scopes" (one bullet in that
  section's open-questions list) — this proposal suggests Tier 2 as one
  answer: a reuse mechanism for setup guides and hardware-specific content
  across multiple experts, since the catalog would only ever hold a pointer to
  one authoritative copy. Not the only possible answer to that bullet.

## 6. Remaining open questions

- **Tooling adoption mechanics.** Fork `napetrov/skills` directly into an
  `intel`-org repo, or reimplement its scripts against this repo's Python
  tooling conventions for consistency with `agent-benchmark`'s own CI?
- **Tier migration.** Can a Tier 2 skill later graduate to Tier 1 (AMD's
  incubator lifecycle, inverted), e.g. once a setup-guide dependency is removed?
- **`scorecard` field placement.** Does it live in `skill-card.json` (extending
  napetrov's schema) as its own object, or only in the manifest-level
  `package.yaml` from [`packaging.md`](packaging.md) §2? Affects whether a
  bare, unpackaged catalog skill can carry a scorecard on its own.
- **Certificate rollout scope.** Does every Tier 1/Tier 2 entry require an Intel
  signature before merge, or only before promotion to a "verified" status
  (mirroring the napetrov trust ladder's distinction between `smoke-tested` and
  `verified`)?

## 7. Relationship to the rest of the project

This doc sits at the intersection of [authoring](authoring.md) (the benchmark
loop that would qualify a skill for either tier), [packaging](packaging.md)
(the manifest/scorecard shape each tier's entry would carry), and
[attestation](attestation.md) (the signing-authority recommendation above). It
does not propose a new track — it is a proposed answer, pending team review,
to "where does a benchmarked skill actually go" that the six-track cycle
([architecture.md](architecture.md)) left open.
