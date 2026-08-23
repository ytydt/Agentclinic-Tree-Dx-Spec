# DA modifier-headroom census: frozen protocol

Declared 2026-08-19, **before any call is made**. The reliability gate and the
decision rule below are fixed now precisely so that they cannot be chosen after
seeing the headroom number.

## Why this census exists

C1 executed all four admission arms and returned NO_GO. Its most informative
output was not the treatment contrast but the substrate measurement behind it.
Joining the completed C0 panel onto C1's pool on the preregistered
`(case_key, normalized label)` key matched 3,673 of 3,673 candidates and showed:

| Bottleneck | Evidence | Share of cases |
|---|---|---:|
| Nothing related in the pool at all | 12 of 400 | 3.0% |
| A clinical-complete candidate already in the pool | DA 17/200, MCR 85/200 | DA 8.5%, MCR 42.5% |
| Core present, reference adds modifiers | DA 107/200, MCR 15/200 | DA 53.5%, MCR 7.5% |

The DA references are composite: "Ichthyosiform mycosis fungoides" against a
pool holding "Mycosis Fungoides"; "Intergluteal and sacral hyperhidrosis"
against "Localized Hyperhidrosis"; "Subacute left ventricular free wall rupture
complicating acute myocardial infarction" against "Myocardial Infarction". The
ceiling on DA is therefore a scope/modifier commitment problem, not an
information-retrieval or a re-ranking problem.

Whether that gap is *recoverable* is unknown. A crude verbatim token check found
only 28.7% of the missing DA modifier terms present literally in the vignette,
with all terms present in just 8 of 107 cases. Lexical matching is a lower
bound, since "ichthyosiform" may appear as a description of scaling and
"stage IIIC" as a description of spread, so the real figure needs annotation.

C1 spent 1,600 comparator calls inside a DA ceiling of 8.5% that was computable
offline beforehand. This census exists to avoid repeating that error at C2's
scale: it costs 400 calls and decides whether C2 is worth running at all.

## Frozen universe

All 200 DA cases in the C1 admission freeze, `cases_sha256`
`6e0fdbb85ff7350a1cfea2510d0c0693059ce95367052d5a9d1dbee478923342`. The set is
deliberately not narrowed to the 107 lexically-identified modifier cases,
because that subset was defined by an ad-hoc tokenizer and must not become a
frozen sampling frame. MCR is out of scope: its modifier-addressable share is
7.5% and the C2-versus-C3 decision does not turn on it.

## Task

Each reviewer receives the vignette, the reference diagnosis and the frozen pool
candidate registry, and returns:

1. the reference decomposed into one core entity plus zero or more modifier
   claims, each on the frozen axis vocabulary `etiology`, `anatomy`,
   `time_stage`, `subtype`, `complication`, `composite_components`;
2. the pool candidate that best matches the core entity, or an explicit none;
3. for every modifier claim, an availability class of `explicitly_stated`,
   `clinically_inferable` or `not_determinable`; and
4. for every claim that is not `not_determinable`, a verbatim quotation from the
   vignette supporting it.

Quotations are checked by literal occurrence, not by model-reported character
offsets. C1 established that the offset requirement fails 94.7% of first-pass
responses for reasons unrelated to the science being measured.

## Provenance boundary

This is an annotation of the measurement substrate, not a system decision
surface. It receives the reference diagnosis, exactly as the C0 census did, and
its outputs may never be placed in a comparator or selector payload. It is a
two-model panel and is not human or root adjudication.

## Reviewers and fail-closed policy

Reviewer A is `google/gemini-2.5-flash`; reviewer B is
`anthropic/claude-sonnet-4.6`. Temperature 0, immutable cache identity per
`(model, module, prompt, payload, temperature)`.

A failed, schema-invalid or unrecoverable response is **not** deleted or
imputed. Its claims default to `not_determinable`, which lowers the measured
headroom. The conservative direction is deliberate: an operational failure must
never manufacture a reason to spend C2's budget.

## Pre-declared reliability gate

The headroom estimate is released only if all of the following hold:

- coarse availability agreement between A and B, where `determinable` unions
  `explicitly_stated` and `clinically_inferable` against `not_determinable`:
  exact agreement >= 0.80 **and** Gwet AC1 >= 0.60;
- core-match agreement, scored as the same pool candidate identifier or both
  explicitly none: >= 0.70.

The fine three-way availability distinction is reported descriptively only. C0
established that this model panel draws a reliable complete/not-complete
boundary at 0.9857 but cannot hold a five-way scope taxonomy above 0.7210
against a required 0.80, so no fine-grained claim is preregistered here.

Agreement is aligned on the six frozen modifier axes rather than exact claim
wording. For example, `DAH` and `diffuse alveolar hemorrhage` both occupy
`complication`; demanding byte-identical values would measure lexical choice,
not availability. If either reviewer places any non-determinable claim on an
axis, that reviewer's axis status is `not_determinable`. An axis omitted by one
reviewer but asserted by the other is also `not_determinable` for the omitting
reviewer. Thus wording variation is tolerated, but missing scope is fail-closed.

If the gate fails, the headroom estimate is not released and **C2 does not
proceed on the strength of this census**. A gate failure means the modifier axis
is not reliably measurable by a model panel, which is itself the finding, and
the next step becomes endpoint and measurement work rather than either C2 or C3.

## Pre-declared primary quantity

`all_axes_determinable_rate`: the share of the 200 DA cases in which

- the reviewers agree a pool candidate matches the reference core, and
- every modifier claim on that case is `determinable` under both reviewers.

Consensus is a conservative AND: a claim counts as determinable only when both
reviewers say so. Secondary and descriptive: `axis_determinable_rate` over all
individual modifier claims, and the per-axis breakdown, which is what a graded
endpoint would consume.

## Pre-declared decision rule

| `all_axes_determinable_rate` | Decision |
|---|---|
| >= 0.25 | Run C2 on DA as primary. The binary clinical-complete endpoint may serve as co-primary alongside a modifier-axis endpoint, because the ceiling would rise from 0.085 to roughly 0.25 and a 3 pp effect is then detectable at n=200. |
| 0.10 to < 0.25 | Run C2, but a graded modifier-axis endpoint is the only admissible primary. The binary complete endpoint is under-powered at this ceiling and must not be primary. |
| < 0.10 | Do not run C2. The DA modifier gap is not recoverable from the vignette as supplied, and the C3 acquisition track becomes the indicated next step. |

Any axis-level endpoint introduced for C2 must carry its own reliability gate.
C0's fine-taxonomy failure at 0.7210 forbids assuming that a graded scope
judgement is measurable merely because a coarse one is.
