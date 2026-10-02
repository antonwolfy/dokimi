# Evidence: a 33-skill content-novelty study

The numbers quoted in [skill-novelty.md](skill-novelty.md) come from one study, recorded here so
every claim has a method and a caveat attached.

**Subject:** `https://github.com/intel/skills` pinned at `2891d7a7d1ba7c262833a6beaf0ac533f9023c65`,
clean tree, 33 skills. The repo's own checks passed at that commit (`validate_skills.py` OK 33,
`run_evals.py --validate` OK 10 files / 30 cases), so the study measured content quality on a
structurally valid corpus, not a broken one.

**Provenance:** run with a prototype outside this repository, against a LiteLLM proxy in front of
Bedrock. Nothing in the subject repository was modified. Phase E.1 of this layer reimplements the
pipeline inside `agent_benchmarks/novelty/` so the measurement becomes reproducible from this repo;
until then, treat the tables below as evidence for the design, not as a regression baseline.

**Model scope:** current-generation models only. Two previous-generation models were measured early
and are excluded from every table here, because "what does this artifact add" is only interesting for
models someone would deploy today.

---

## 1. Method, and the constraints it had to satisfy

| stage | what it produced |
|---|---|
| inventory | 33 skills, token counts, frontmatter, eval files |
| need graph | 13 graphs, 1076 nodes, 1536 edges — built from name + description only |
| atom extraction | 4770 knowledge atoms with span-level provenance |
| faithfulness check | 4411 supported / 329 distorted / 30 unsupported |
| value + category | 2422 atoms judged (capped at 250 per skill) |
| span map | 4796 spans, atom ↔ span index, protection flags |
| probes | 19524 graded probe runs over 10 models and 6 arms |
| shortening | 462 candidate scorings, 15 candidates × 4 skills |
| behaviour | 104 generated tasks (66 discriminating), 651 task runs |
| routing | 891 routing decisions over 3 menu seeds |

Four constraints shaped the design, and each was verified rather than assumed:

1. **The artifact must not define its own relevance.** The need graph's author never saw a skill
   body — only its name and description. 100 nodes were labelled `out-of-scope` on purpose, as
   negative controls.
2. **Never grade with the model that wrote the answer key.** Extraction, answering and grading were
   three separate models. A second grader double-scored 2143 responses.
3. **Never use self-confidence as the correctness score.** Verified as necessary: the correlation
   between stated confidence and graded score was ≤0.454 and as low as 0.018.
4. **Baseline isolation.** A baseline probe received one question and nothing else — no repository
   contents, no skill text, no answer key, no prior turns.

### Judge reliability — the caveat on every level below

2143 double-graded responses: **exact agreement on the 6-way verdict scale 0.664**, agreement on the
correct-ish binary collapse **0.852**. The largest confusion was `partially_correct` vs `wrong_other`
(247 cases). Consequently the 6-way scale is not used for any conclusion, every score appears under
both a lenient and a strict collapse, and paired comparisons are preferred over levels.

Human review sheets were generated for a gold subset (40 atoms, 40 graded responses, plus the
constructed equivalence pairs) but **have not yet been filled in**. Until they are, the absolute
level of every score rests on an LLM judge.

---

## 2. What the models already knew (K0)

Prior recall over the skills' own knowledge, no artifact in context. `reversal_resisted` is the
fraction of planted-inversion probes the model refused.

| model | K0 lenient | K0 strict | adversarial | reversal resisted | conf↔score corr |
|---|---|---|---|---|---|
| gpt-5.6-luna | 0.499 | 0.240 | 0.478 | 0.804 | 0.112 |
| kimi-k3 | 0.494 | 0.276 | 0.491 | 0.807 | 0.390 |
| claude-opus-5 | 0.472 | 0.250 | 0.440 | 0.793 | 0.257 |
| claude-sonnet-5 | 0.452 | 0.209 | 0.421 | 0.811 | 0.312 |
| nemotron-super-3-120b | 0.358 | 0.129 | 0.367 | 0.873 | 0.201 |
| grok-4.6 | 0.352 | 0.182 | 0.322 | 0.787 | 0.392 |
| claude-haiku-4-5 | 0.340 | 0.112 | 0.328 | 0.843 | 0.454 |
| deepseek-v3.2 | 0.336 | 0.082 | 0.303 | 0.872 | 0.270 |
| glm-5 | 0.331 | 0.110 | 0.300 | 0.860 | 0.386 |
| nemotron-nano-12b | 0.257 | 0.033 | 0.255 | 0.890 | 0.018 |

**An inversion worth designing around:** the strongest models resist reversal probes *least*
(0.787–0.811), the weakest most (0.890). A weak model abstains and thereby dodges a planted
inversion; a strong model engages and sometimes accepts it. A stale or reversed line in a skill is
therefore most dangerous to the best models — and the skill in this corpus with the most conflicting
content also had one of the highest routing rates, so it loads reliably and then misinforms.

## 3. What the skill added

Paired per probe; four exhaustive outcomes.

| model | n | added | already knew | degraded | still missing |
|---|---|---|---|---|---|
| **lenient grading** | | | | | |
| claude-opus-5 | 573 | 0.209 | **0.700** | 0.019 | 0.072 |
| gpt-5.6-luna | 573 | 0.131 | **0.775** | 0.030 | 0.065 |
| grok-4.6 | 573 | **0.307** | 0.537 | 0.024 | 0.131 |
| claude-haiku-4-5 | 263 | 0.232 | 0.597 | 0.049 | 0.122 |
| nemotron-nano-12b | 263 | 0.293 | 0.498 | **0.076** | 0.133 |
| **strict grading** | | | | | |
| claude-opus-5 | 573 | 0.363 | 0.216 | 0.038 | 0.382 |
| gpt-5.6-luna | 573 | 0.286 | 0.220 | 0.033 | 0.461 |
| grok-4.6 | 573 | 0.356 | 0.157 | 0.024 | 0.463 |
| claude-haiku-4-5 | 263 | 0.304 | 0.103 | 0.030 | 0.563 |
| nemotron-nano-12b | 263 | 0.266 | 0.019 | 0.027 | **0.688** |

Read the two gradings together. Under lenient grading a skill mostly repeats what the model knows;
under strict grading its real job appears — the gap between `added` lenient (0.209) and strict
(0.363) on `claude-opus-5` is exactly the class *"the model knew the shape, the skill supplied the
precision"*. **Qualifiers and exact values are what these skills are for.**

### Control arms

The `no_skill` column is §2's K0 lenient, not a rate over §3's paired cells: there
`claude-opus-5` is right without the skill on 0.700 + 0.019 = 0.719 of probes.

| model | no_skill | root (`SKILL.md` only) | routed | full | placebo | shuffled |
|---|---|---|---|---|---|---|
| claude-opus-5 | 0.472 | 0.686 | 0.728 | 0.730 | 0.418 | **0.750** |
| gpt-5.6-luna | 0.499 | 0.667 | 0.709 | 0.698 | 0.482 | **0.735** |
| grok-4.6 | 0.352 | 0.537 | 0.627 | 0.671 | **0.104** | 0.690 |
| claude-haiku-4-5 | 0.340 | 0.540 | 0.595 | 0.597 | 0.130 | **0.637** |
| nemotron-nano-12b | 0.257 | 0.464 | 0.471 | 0.505 | 0.184 | 0.483 |

- **`placebo`** is domain-mismatched text of the same length. It sits far *below* `no_skill` on
  `grok-4.6` (0.104 vs 0.352) and `claude-haiku-4-5` (0.130 vs 0.340): irrelevant context actively
  damages those models, so the `full` gain is not a prompt-length artifact. On `claude-opus-5` and
  `gpt-5.6-luna` placebo ≈ `no_skill` — they ignore irrelevant context instead of being hurt by it.
- **`shuffled`** keeps the same spans and destroys their order. It scores *at least as high* as
  `full` on four of five models. Ordering and narrative are not carrying knowledge in this corpus.

## 4. Content categories

2422 judged atoms, primary lens `claude-opus-5`:

| category | n | share |
|---|---|---|
| scaffolding | 947 | 39.1% |
| novel_useful | 718 | 29.6% |
| known_useful | 331 | 13.7% |
| novel_inert | 257 | 10.6% |
| harmful_conflicting | 97 | 4.0% |
| known_inert | 72 | 3.0% |

**Uncertainty:** an independent reviewer (853 atoms) agreed on 71.6%. The disagreements are
systematic, not noise — `novel_useful → novel_inert` 70, `known_useful → novel_useful` 48,
`known_useful → novel_inert` 27, `novel_useful → scaffolding` 26. Both axes that slip are the judged
ones. Treat useful-vs-inert as ±3 points and known-vs-novel as ±2; the scaffolding share is the most
robust number in the table, and it is also the largest.

88 atoms were flagged as internally contradictory or contradicting a sibling skill, concentrated in
one skill (30 of 88).

## 5. Per-skill results

Judged atoms (250/skill cap) / spans / tokens / share of tokens carrying no atom / novel_useful /
scaffolding / harmful / inert / routing accuracy:

| skill | atoms | spans | tokens | dead tok | nov_useful | scaffold | harmful | inert | routing |
|---|---|---|---|---|---|---|---|---|---|
| performance-patterns | 279 | 2087 | 59248 | **74%** | 42 | 82 | 11 | 64 | 0.771 |
| linux-perf | 271 | 1042 | 28421 | **50%** | 28 | 108 | 5 | 89 | 0.583 |
| model-config-recommend | 262 | 203 | 24501 | 12% | 138 | 80 | 5 | 12 | 0.381 |
| xpu-system-setup | 259 | 159 | 17371 | 6% | 77 | 120 | 11 | 30 | 0.333 |
| mkl-extension-advisor | 259 | 316 | 9421 | 17% | 76 | 108 | **33** | 20 | 0.810 |
| model-can-it-fit | 252 | 227 | 14267 | 7% | 123 | 79 | 8 | 6 | 0.813 |
| vllm-xpu-run | 224 | 203 | 8304 | 5% | 82 | 88 | 12 | 25 | 0.292 |
| xpu-runtime-preflight | 145 | 72 | 6617 | 2% | 60 | 36 | 4 | 37 | 0.604 |
| xpu-deploy-plan | 139 | 87 | 6280 | 4% | 28 | 78 | 2 | 29 | **0.146** |
| vllm-xpu-bench | 104 | 152 | 4107 | 9% | 28 | 51 | 0 | 6 | 0.625 |
| dpnp-troubleshooting | 84 | 86 | 2445 | 12% | 28 | 37 | 4 | 6 | 0.438 |
| dpnp-quickstart | 83 | 95 | 2351 | 13% | 21 | 53 | 2 | 1 | 0.292 |
| onetbb-quickstart | 61 | 67 | 2049 | 14% | 12 | 27 | 0 | 4 | 0.813 |

Four distinct failure modes appear, and they need different fixes:

- **Bulk without knowledge** — `performance-patterns` (74% dead tokens), `linux-perf` (50%), which
  also hold the two largest inert counts. Shorten.
- **Correctness risk** — `mkl-extension-advisor`: 33 conflicting atoms in 9.4k tokens, and it routes
  at 0.810, so it *will* be loaded. Fix content before shortening.
- **Routing failure** — six skills below 0.50, `xpu-deploy-plan` at 0.146. Their descriptions do not
  claim their own queries; content work there is unrecoverable spend.
- **Clean but inert** — `xpu-runtime-preflight`: 2% dead tokens and 60 novel_useful atoms, but 37
  inert atoms and middling routing.

## 6. Shortening, with behaviour measured rather than estimated

Candidate packages were rendered and then **actually run** through the generated task suite, so the
retention oracle's estimate can be checked against behaviour:

| skill | candidate | tok frac | knowledge | protection | measured Δ task vs full |
|---|---|---|---|---|---|
| performance-patterns | safety-pinned 0.75 | 0.66 | 0.957 | 1.000 | opus +0.08, luna −0.01, grok +0.05 |
| performance-patterns | safety-pinned 0.50 | 0.60 | 0.812 | 1.000 | opus +0.14, luna −0.00, grok −0.08 |
| performance-patterns | **value-only 0.50** | **0.21** | 0.916 | **0.158** | opus +0.05, luna −0.07, grok +0.16 |
| mkl-extension-advisor | **value-only 0.50** | 0.50 | 0.844 | **0.625** | haiku +0.06, opus **+0.21**, nano −0.07 |
| dpnp-quickstart | safety-pinned 0.50 | 0.59 | 0.783 | 1.000 | haiku +0.13, opus +0.05, nano **−0.19** |
| xpu-system-setup | safety-pinned 0.75 | **0.94** | 0.967 | 1.000 | opus 0.00, haiku **+0.30**, nano +0.06 |

1. **No shortened candidate lost more than 0.08 against the full package on a strong model.** Every
   task-score loss beyond −0.08 belonged to the smallest model (−0.10, −0.15, −0.19).
2. **The knowledge oracle cannot see the safety loss.** The 21%-token candidate reports knowledge
   0.916 and protection 0.158. Negations, version gates and ordering constraints are exactly the
   low-value-per-token spans a greedy selector discards, because their value is conditional on a
   failure the atom statement does not encode. This is why the five axes stay separate.
3. **Some artifacts cannot be shortened.** `xpu-system-setup` under any safety-pinned strategy lands
   at 0.94 token fraction: nearly every span is protected or a sole carrier. Its problem is content,
   not length.
4. **Deduplication found nothing.** A dedupe-only pass on `performance-patterns` returned token
   fraction 1.01. Its 74% dead tokens are not duplicated knowledge — they are text that never
   carried knowledge.

## 7. Behaviour and routing

Generated suite: 104 tasks, 102 usable, 66 discriminating, balanced across correctness (22),
debugging (21), integration (21), selection (19), performance (19). 651 graded runs, 0 failures.

| skill | model | no_skill | root | full | best shortened |
|---|---|---|---|---|---|
| performance-patterns | claude-opus-5 | 0.272 | 0.431 | 0.459 | **0.600** |
| performance-patterns | gpt-5.6-luna | 0.406 | 0.459 | 0.416 | 0.428 |
| performance-patterns | grok-4.6 | **0.537** | 0.047 | 0.397 | 0.553 |
| dpnp-quickstart | claude-opus-5 | 0.344 | **0.591** | 0.400 | 0.581 |
| dpnp-quickstart | nemotron-nano-12b | 0.078 | 0.334 | 0.281 | 0.281 |

**The 0.047 cell is a content defect, not a harness bug.** `grok-4.6` abstained on 6 of 8 tasks when
given that `SKILL.md` alone, answering with a deferral instead of an answer — verbatim: *"I'll look
up the performance-pattern guidance for `-Ofast` vs. numerical correctness, then give you the exact
flag split. I'll start with the write-time and source-review checklists."* The grader recorded
`abstained: true` with all five requirements unmet. The skill's progressive-disclosure phrasing
teaches the model to postpone answering; with no skill at all the same model scored 0.537. Every
other model/arm cell had ≤2 abstentions, except `claude-opus-5 / no_skill` (12/31), which is honest
ignorance.

**Routing.** All 33 real descriptions as a menu; the correct skill must be chosen per task.
Accuracy: 166/306, 168/306, 160/306 across three menu-order seeds — a ±1.3-point sensitivity,
measured rather than assumed. Shortened candidates are routing-invariant by construction
(frontmatter is pinned) and measured as such. **Shortening does not threaten routing; the
descriptions were already the weak part.**

## 8. Which matcher can decide "is this the same knowledge?"

Two places in the pipeline ask a comparison question, and they are not the same question:

| where | question | wrong answer costs |
|---|---|---|
| retention oracle | is atom `A` still recoverable from shortened text `T`? | a shortening is accepted that silently dropped a rule |
| atom ↔ need match | does atom `A` answer need node `N`? | relevance, and therefore `value`, is assigned to the wrong atoms |

Both were benchmarked on the same 714 constructed pairs (restates / entails / unrelated / reverses),
construction-blind agreement 0.961:

| approach | macro-F1 | LLM calls | contradiction recall |
|---|---|---|---|
| llm_direct | 0.953 | 100% | high |
| hybrid (retrieval → NLI → LLM band) | 0.848 | 25.6% | high |
| nli | 0.732 | 0% | moderate |
| graph matcher | 0.551 | 0% | — |
| lexical | 0.446 | 0% | **0.00** |
| embeddings (potion / bge) | 0.444 / 0.438 | 0% | **0.00** |

Three conclusions, in order of how much they changed the design:

1. **Embedding and lexical matchers cannot distinguish *restates* from *reverses*.** Contradiction
   recall 0.00 for both. A purely vector-based content tool would score a reversed claim as
   faithfully retained — the exact failure the layer exists to catch.
2. **The hybrid is the shipped oracle**: retrieval prefilter → two-way NLI → LLM adjudication only
   in the ambiguous band. It keeps high contradiction recall at 25.6% of the LLM calls of direct
   judging, and it degrades in the safe direction — without an adjudicator the band resolves to
   *absent*, so reported `knowledge` is a floor, never an overstatement.
3. **The graph matcher is the second-worst scorer here (0.551) and that is not an argument against
   the graph.** Structural overlap is the wrong instrument for semantic equivalence. What the graph
   is good at is the previous step — deciding *which question is being asked at all*, see §9.

## 9. The need graph: what it decides, what it cannot, and how it compares

The graph exists to satisfy one constraint: **an artifact must not define both the problem scope and
its own relevance to that scope.** Its author saw a skill's `name` and `description` and nothing
else — never the body, never the atoms, never an eval file.

**Measured build.** 13 graphs, 1076 nodes, 1536 edges.

| node type | n | path class | n | weight used in `value` |
|---|---|---|---|---|
| intent | 325 | rare_critical | 356 | 1.0 |
| evidence | 220 | core | 311 | 1.0 |
| action | 198 | branch | 275 | 0.7 |
| constraint | 168 | supporting | 34 | 0.4 |
| decision | 165 | out_of_scope | 100 | 0.0 |

`rare_critical` carries the same weight as `core` deliberately. A rule that fires on one query in a
hundred but prevents a corrupted run is not low-value; frequency and criticality are different axes,
and collapsing them is how safety text gets deleted. The 100 `out_of_scope` nodes were planted as
negative controls: needs a reader might plausibly bring that this artifact is *not* responsible for.

Relevance of an atom is then a sum over the needs it serves, rather than a similarity score:

```
R(a) = Σ_t  P(t) · Need(a,t) · Criticality(a,t) · Uniqueness(a,t)
```

`P(t)` — how often the need actually arises — is **not measured** in this study. Descriptions,
issues and support queries would supply it; absent that, every `value` number here is reported under
uniform `P(t)`, and the honest use is ranking within one artifact, not comparing artifacts.

### 9.1 Graph-derived relevance vs. plain similarity

If the graph were decorative, relevance derived from it would track embedding similarity, and the
cheaper instrument would win. It does not track it:

| comparison | result | reading |
|---|---|---|
| corr(path-weighted relevance, top retrieval similarity) | **0.368** | the two rankings measure different things |
| top-quartile overlap | 261/605 | they disagree on **57%** of the atoms each calls most relevant |
| atoms whose best match is `out_of_scope` | **32 (1.3%)** | a category similarity cannot express at all |
| author ↔ independent critic on path labels | 925/1076 (**86%**) | the 14% is the noise floor on relevance-weighted `value` (open question O6) |

The 1.3% is the point, not the size. Similarity ranking answers *how close is this text to the
topic*; it has no way to return "this sentence answers a question this artifact is not responsible
for". Being on-topic and being in-scope are different properties, and only the second one licenses
spending tokens.

### 9.2 Edges do the work that node similarity cannot

Atoms are not only propositions. The most consequential content in this corpus was **negative
edges** — short clauses that block an inference a model would otherwise make. Five examples found in
the static audit, each one a single clause whose deletion flips an edge from
`evidence IMPLIES conclusion` to `evidence DOES_NOT_IMPLY conclusion`:

| clause (paraphrased) | edge it blocks |
|---|---|
| a successful `import` does not mean the array landed on the GPU | import success → device placement |
| `threadpool_info()` seeing MKL does not mean NumPy's BLAS/FFT are wired to it | library visible → library in use |
| bare device discovery reports no memory figure | device listed → capacity known |
| FITS against physical VRAM does not mean it will launch now | static fit → runtime launch |
| do not chain the child skills by hand, use the single entrypoint | sub-skill exists → call it directly |

Each is cheap in tokens, invisible to a frequency or perplexity ranking, and expensive to lose. This
is why `protection` is a separate axis (§6) and why the vocabulary the graph needs is **qualified**
edges — `only_if`, `not_evidence_for`, `before`, `fallback_when`, `halts_on` — not a single
`related_to`. The qualified-edge vocabulary is design, taken from the audit; the node and path counts
above are measured.

### 9.3 Five things the graph is not allowed to decide

The graph organizes the question space. It is a retrieval and exploration layer — the role GraphRAG
plays — and explicitly not the scorer:

| the graph cannot say | what actually answers it |
|---|---|
| whether a claim is **true** | external primary sources; not done here (§10.2) |
| how **often** a need arises | intent telemetry, issues, support queries — the missing `P(t)` |
| what **this model** already knows | paired probes per (atom, model) — §2, §3 |
| which span **caused** a behaviour change | deletion / leave-one-out arms — §6 |
| whether the knowledge is **useful downstream** | the task suite — §7 |

Every one of those is a separate measurement in this study, which is why the headline output is a
dashboard and not a single graph score. A run that reported only graph coverage would have called
`performance-patterns` healthy and missed both its 74% dead tokens and the deferral defect that cost
`grok-4.6` 0.49 of task score against no skill at all.

## 10. Known gaps in this study

1. **Human gold review is not done.** Sheets exist; absolute levels rest on an LLM judge until they
   are filled. Paired comparisons are much less affected, because judge bias cancels within a pair.
2. **No external primary-source verification.** Temporal and version-bound atoms were checked for
   internal consistency and cross-skill conflict, not against vendor documentation. The 88 conflicts
   say "these disagree", not "this one is wrong".
3. **Behaviour covers 4 of 33 skills.** Shortening is behaviourally validated only where candidate
   packages were rendered and run.
4. **Single-lens extraction.** Faithfulness was verified; recall was not. Knowledge the extractor
   missed is invisible to every number here, including `dead tokens` — some of which may be
   knowledge it could not formalize. This is the largest open hole and open question O1.
5. **`shuffled ≥ full` needs an adversarial follow-up.** Either order genuinely does not matter, or
   per-atom probing rewards fact lookup over procedure following (open question O5).
6. **Need frequency `P(t)` is not measured.** All relevance weighting assumes uniform need
   frequency, so `value` ranks atoms *within* one artifact honestly and must not be compared across
   artifacts. Closing this needs real query or issue traffic, not another judge.
