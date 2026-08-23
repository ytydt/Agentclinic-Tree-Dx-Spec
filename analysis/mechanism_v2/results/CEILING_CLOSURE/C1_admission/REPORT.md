# C1 qualified-frontier admission closure

Status: **EXECUTED — NO_GO**

All four arms were executed on 400 cases. The frozen efficacy gate fails on two
counts: no arm reaches the required 0.98 service rate, and the qualified
frontier does not clear 3 pp over its equal-width sham with a positive lower
bound. Details in "Executed result" below; the readiness history that preceded
execution is retained in full because it explains the service shortfall.

The 2026-08-15 operational No-Go is retained verbatim as
`REPORT.md.pre_resume`, together with the pre-resume freeze, typing directory,
readiness gate, gate and decision artifacts. This page describes the state
after OpenRouter capacity was restored on 2026-08-18.

## What was executed

Typing was run online through `ceiling_closure_online admission-typing` under
the preregistered construction identity `google/gemini-2.5-flash` at
temperature 0, 24 workers, via the repository's own `RobustLLMClient` — the same
transport the original run used, so **no model, gateway or executor
substitution was involved**.

| Stage | Before | After |
|---|---:|---:|
| Typing task identities valid | 0 of 800 | **800 of 800** |
| Cases with annotation success | 0 of 400 | **400 of 400** |
| `requested_object` coverage | 0.000 | **1.000** |
| Ledger partition rate | 1.000 | 1.000 |
| Readiness-gate failures | 801 | **4** |

The first pass returned 798 of 800 valid task identities. Two
`requested_object` tasks failed schema validation
(`explicit_modifier_axes must be a unique list`; `unknown requested modifier
axis`). Following the `recover-reviewer` precedent, both raw invalid cache
records were copied to `typing/online/quarantine` with their SHA-256 recorded in
`invalid_cache_ledger.jsonl`, removed from the active cache, and re-called under
the identical immutable identity. Both returned valid annotations, so typing
ends with zero failures and nothing imputed or deleted.

## Freeze rebinding

The admission freeze was rebuilt with the completed typing bound as a source
artifact. The case selection is unchanged by construction — it is derived
outcome-blind from the E4 pools at `k=4` and never depended on typing:

| Field | Pre-resume | Current |
|---|---|---|
| `case_n` | 400 | 400 |
| `family_n` | DA 200 / MCR 200 | DA 200 / MCR 200 |
| `k` | 4 | 4 |
| `arms` | four frozen arms | four frozen arms |
| `cases_sha256` | `a7b19244…` | `6e0fdbb8…` |
| `freeze_id` | `06d9ed73…` | `fe803025…` |

`cases_sha256` and `freeze_id` change because the typed and qualified arms are
now populated instead of uniformly empty. That is the resume path named in the
pre-resume `decision.json`, not a redefinition of the sample.

Main-frontier widths under the rebuilt freeze:

| Arm | Mean main width | Zero-width cases |
|---|---:|---:|
| `fixed_k` | 4.00 | 0 |
| `typed_fixed_k` | 3.86 | 4 |
| `qualified_frontier` | 3.63 | 12 |
| `sham_qualification` | 3.63 | 12 |

The sham matches the qualified arm's width distribution exactly, which is the
required control property: any qualified-arm effect cannot be attributed to
narrowing alone.

## Why the readiness gate still fails

All 4 remaining failures are `typed_frontier_empty`, on
`DA_d2_heldout100/321`, `DA_d2_seq100/83`, `MCR_seq200b/470` and
`MCR_v1_seq100/56`. These are **not** execution artifacts. In each of them the
annotator resolved the requested object as `disease_entity` while typing every
pool candidate as `disease_subtype`, so the frozen strict-equality rule in
`_admission_type_match` admits nobody.

The candidate labels make the inconsistency explicit. `DA_d2_seq100/83` offers
Choroideremia, Stargardt disease, Gyrate atrophy, Leber congenital amaurosis and
Retinitis pigmentosa; `MCR_v1_seq100/56` offers Undifferentiated pleomorphic
sarcoma, Osteosarcoma, Leiomyosarcoma and Inflammatory myofibroblastic tumour.
By any ordinary clinical reading these are disease entities. The annotator
appears to demote specific named diseases to `disease_subtype` when they sit
inside a recognisable family such as the retinal dystrophies or the soft-tissue
sarcomas, while still calling the request itself entity-level.

The effect is a bounded tail rather than a pervasive breakdown. Across all
3,673 candidates the typing distribution is 85.90% `disease_entity`, 7.32%
`disease_subtype`, 5.20% `finding`, 1.12% `complication` and 0.60% spread over
stage, etiology, episode, intervention, other and one unresolved. Per case, the
median share of candidates matching the requested kind is 1.000 and the mean is
0.860; 28 cases fall below 50% and only these 4 reach 0%.

Eight further cases have an empty `qualified_frontier` without an empty typed
frontier, so the same object-level brittleness also propagates into the primary
treatment arm through its same-requested-object admission criterion.

## Convergence with the C0 result

This is the second independent place in the same closure round where the
**object/relation taxonomy**, not coverage or capacity, is the unreliable
component. C0's completed panel passes the complete/not-complete boundary at
0.9857 raw and AC1 0.9843 but fails fine-label agreement at 0.7210 against a
required 0.80, with disagreements concentrated on
`conflicting_subtype_or_scope` versus `not_equivalent` and
`partial_parent_or_component` versus `manifestation_or_related`. C1 now fails
its readiness gate because entity-versus-subtype cannot be drawn consistently by
the same annotator within a single case.

## Pre-arm amendment and readiness pass

`PRE_ARM_AMENDMENT.md` records, before any selector job was compiled, that an
empty typed frontier blocks readiness only when it reflects missing annotation.
When the request is positively resolved and every candidate is positively typed,
the emptiness is the frozen rule's own outcome: the case is carried into the arm
and scored as no evaluable Top-1 under the already-frozen ITA rule. Under that
amendment the readiness gate passes with `requested_object_coverage` 1.000,
`ledger_partition_rate` 1.000 and the four cases recorded as
`substantively_empty_typed_frontier`. The case set is unchanged;
`cases_sha256` stayed `6e0fdbb8…` across the amendment and only `freeze_id`
moved, because it binds the gate's own code hash.

## Endpoint construction

The clinical-complete endpoint was joined from the completed C0 model panel on
the preregistered key `(case_key, normalized label)`. The join is exact: all
3,673 C1 candidates matched a census row, with zero unmatched and zero
normalized-label collisions, which independently confirms that C1's E4 pool lies
entirely inside the C0 census universe. Relation distribution over the 3,673
candidates is 133 complete-equivalent, 711 partial, 782 conflicting-scope, 518
manifestation, 1,421 not-equivalent and 108 uncertain.

Only 3.6% of pool candidates are clinical-complete. That is the dominant fact
about this experiment and it is a property of the pools, not of any arm.

## Executed result

1,600 comparator calls were made, 400 per arm, under `google/gemini-2.5-flash`
at temperature 0. Official verdict: **NO_GO**, with failures
`fixed_k:service_below_0.98`, `typed_fixed_k:service_below_0.98`,
`qualified_frontier:service_below_0.98`, `sham_qualification:service_below_0.98`
and `qualified_not_3pp_and_positive_lower_bound_over_equal_width_sham`.

| Arm | Service | ITA complete | Complete exposure |
|---|---:|---:|---:|
| `fixed_k` | 0.9125 | 0.0675 | 0.1100 |
| `typed_fixed_k` | 0.8700 | 0.0725 | 0.1175 |
| `qualified_frontier` | 0.8725 | 0.0775 | 0.1425 |
| `sham_qualification` | 0.8450 | 0.0675 | 0.1300 |

Pooled contrasts are +1.0 pp for qualified over fixed-k (bootstrap 95% lower
−0.020) and +1.0 pp over the equal-width sham (lower −0.015), against a required
3 pp with a positive lower bound. The paired transition ledger is directionally
favourable: 18 complete rescues against 8 catastrophic substitutions, net +10,
with 4 scope compressions. The frozen exposure guard
`qualified_complete_exposure_lower_than_fixed` did not fire — the admission rule
does raise complete exposure, from 0.1100 to 0.1425.

### The pooled number hides opposite signs

DA and MCR are separate primary strata under the measurement contract, and they
disagree:

| Stratum | Arm | ITA complete | Exposure | vs `fixed_k` | vs sham |
|---|---|---:|---:|---|---|
| DA (n=200) | `fixed_k` | 0.0250 | 0.0350 | — | — |
| DA | `typed_fixed_k` | 0.0200 | 0.0300 | | |
| DA | `qualified_frontier` | 0.0050 | 0.0350 | −2.0 pp, 0/4 discordant, p=0.125 | −1.0 pp, 0/2, p=0.500 |
| DA | `sham_qualification` | 0.0150 | 0.0400 | | |
| MCR (n=200) | `fixed_k` | 0.1100 | 0.1850 | — | — |
| MCR | `typed_fixed_k` | 0.1250 | 0.2050 | | |
| MCR | `qualified_frontier` | 0.1500 | 0.2500 | +4.0 pp, 18/10, p=0.185 | +3.0 pp, 15/9, p=0.308 |
| MCR | `sham_qualification` | 0.1200 | 0.2200 | | |

The pooled +1.0 pp is the average of −2.0 pp on DA and +4.0 pp on MCR. Neither
stratum reaches significance by exact McNemar. On MCR the point estimate does
clear the 3 pp bar against both controls and exposure rises from 0.1850 to
0.2500, which is the designed mechanism visibly operating. On DA the effect is
negative and the substrate is nearly empty: complete exposure is 0.0350, so at
most 7 of 200 DA cases could ever be scored complete, and `qualified_frontier`
did not raise exposure there at all. The DA discordance of 0 wins against 4
losses rests on a base of 5 completes and should not be read as a DA-specific
harm result.

### Why service falls short

Two independent causes, one instrumental and one structural.

The instrumental cause was a defective response contract. The selector was
required to return `decisive_spans` with correct `start`/`end` integers into the
vignette, and 1,515 of 1,600 first-pass responses failed exactly that check —
models do not count characters reliably. Re-checking the same cached responses
under a verbatim-quotation rule, which is how this repository's own span locator
works, passed 1,399 of those 1,515. The repair was applied to the decisive-span
check only and deliberately not to `_valid_span`, whose offsets bind a modifier
to a position inside a short candidate label for C2 and enforce temporal
ordering for C3, where they carry real meaning. Re-validation consumed no new
calls, because the cache identity does not include the validator. The residual
201 failures are 116 paraphrases that do not occur verbatim, 49 invalid
runner-up IDs, 28 empty frontiers and 7 champions taken from the residual
ledger.

The structural cause cannot be repaired by any prompt. `qualified_frontier` and
`sham_qualification` each empty their own main frontier on 12 of 400 cases,
which under the amendment's ITA scoring are unservable by construction. Their
service rate is therefore capped at 0.97, below the frozen 0.98 requirement.
The frozen service tolerance of 2% and the qualification rule's 3% refusal rate
are mathematically incompatible. This was foreseeable from the freeze before the
amendment was written and was not flagged there; it is recorded here.

Two prompt defects remain unrepaired and were not fixed, because doing so after
seeing the contrasts would be outcome-informed tuning: the contract does not
tell the model to leave `runner_up_id` empty when the main frontier holds a
single candidate, which accounts for 30 of the 49 runner-up failures across 78
width-1 jobs, and its verbatim-quotation instruction is too weak to prevent
paraphrase. The identical `support_spans` offset defect still sits in the C2
modifier validator and will surface there unless addressed before C2 runs.

## Interpretation boundary

This is a genuine executed C1 result and it does not support the qualified
frontier at the preregistered bar. It also does not refute the underlying
mechanism: exposure rose as designed, rescues outnumbered catastrophic
substitutions 18 to 8, and the MCR point estimate cleared 3 pp against both
controls. What defeats the claim is the combination of a 3.6% complete-candidate
density in the pools, a comparator that malforms 12.5% of its responses, and a
qualification rule whose own refusal rate exceeds the protocol's service
tolerance.

No threshold was moved to reach this verdict, no case was dropped from any arm,
and all four arms kept a denominator of 400. Because the service gate fails, the
efficacy contrasts above are reported as recorded values and are not a released
estimate.
