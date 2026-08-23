# DA modifier-headroom census

Status: **EXECUTED — NO_GO_MEASUREMENT**

The census does not release a modifier-headroom estimate and does not authorize
either C2 or C3. Its pre-declared reliability gate failed on all three checks.
The result localizes the next bottleneck to the measurement instrument:
reference decomposition and evidence availability cannot be elicited reliably
in one free-generation task.

## Frozen purpose and universe

C1 established that only 17 of 200 DA pools contain any clinical-complete
candidate, while 167 of 200 contain a partial-parent candidate but no complete
one. A deterministic lexical audit further found 107 cases where a pool
candidate is a strict token-subset of the reference diagnosis: the core is
already present and the reference adds modifiers. This is 53.5% of all DA
cases, compared with 7.5% on MCR.

The census was therefore frozen before any call to decide whether those
modifiers are recoverable from the supplied vignette. It includes all 200 DA
cases from C1 freeze `cases_sha256`
`6e0fdbb85ff7350a1cfea2510d0c0693059ce95367052d5a9d1dbee478923342`,
not the tokenizer-selected 107-case subset. Each reviewer received the
vignette, reference diagnosis and frozen candidate registry, and was asked to:

1. decompose the reference into a core plus claims on six frozen modifier axes;
2. bind the core to a pool candidate or explicitly none; and
3. classify each modifier as explicitly stated, clinically inferable or not
   determinable, with a verbatim quotation for the first two classes.

Reviewer A was `google/gemini-2.5-flash`; reviewer B was
`anthropic/claude-sonnet-4.6`, both at temperature 0. The 400 task identities,
prompt and input hashes are recorded under `design/freeze.json`.

## Execution

| Reviewer | Valid | Invalid | Main invalidity |
|---|---:|---:|---|
| Gemini 2.5 Flash | 91/200 | 109 | 108 non-verbatim support claims; 1 duplicate claim |
| Claude Sonnet 4.6 | 191/200 | 9 | 9 non-verbatim support claims |

The Gemini failure is not a character-offset defect like C1's selector
instrument. Examples include claiming that `Pemphigus erythematosus`,
`Senear-Usher syndrome` or `Cutaneous malakoplakia` was explicitly stated when
that text does not occur in the clinical record. The validator checked literal
occurrence only and did not ask the model to calculate offsets. These are
substantive grounding failures, so they were not repaired or relaxed after the
calls. Per the frozen fail-closed policy, an invalid card contributes no
determinable modifier.

## Reliability gate

| Check | Required | Observed | Result |
|---|---:|---:|---|
| Coarse determinable/not-determinable exact agreement | >=0.80 | **0.1542** | fail |
| Coarse Gwet AC1 | >=0.60 | **−0.6818** | fail |
| Core-candidate exact agreement | >=0.70 | **0.3950** | fail |

The panel therefore fails its measurement gate. The fail-closed consensus
produces 6 of 200 all-axes-determinable cases (0.030) and 77 of 668
axis-occurrences (0.115), but the preregistration explicitly forbids releasing
either number as a headroom estimate when reliability fails. They are
instrument outputs, not estimates of clinical recoverability.

## Failure localization

The aggregate core agreement of 0.395 is heavily depressed by invalid Gemini
cards. Restricting only for diagnosis, not endpoint estimation, to the 89 cases
where both reviewers returned schema-valid cards:

- core-candidate exact agreement is 0.809;
- both select the same non-empty core in 0.562;
- the set of modifier axes is exactly the same in only **0.202**.

The axis-status ledger shows why. On these 89 cards there are 191 occurrences
where Gemini omits an axis that Claude calls determinable, compared with only 8
in the opposite direction. There are another 23 where Gemini calls the axis
not determinable and Claude calls it determinable. Reviewer-specific valid-card
rates are likewise incompatible:

| Axis | Gemini: asserted axis determinable | Claude: asserted axis determinable |
|---|---:|---:|
| Anatomy | 12/13 | 134/135 |
| Complication | 19/21 | 113/114 |
| Composite components | 5/5 | 22/22 |
| Etiology | 33/43 | 139/152 |
| Subtype | 9/27 | 117/123 |
| Time/stage | 8/9 | 108/110 |

This task confounds two different judgments:

1. **decomposition** — which modifiers exist in the composite reference label;
2. **availability** — whether the vignette determines each already-defined
   modifier.

The models disagree mainly on the first. Asking each reviewer to invent its own
claim universe makes availability agreement uninterpretable: an omitted axis
can mean “not part of the reference,” “overlooked,” or “not supported.” C0's
fine-relation failure and C1's entity/subtype inconsistency predicted exactly
this failure mode.

## Decision

The frozen rule returns:

`NO_GO_MEASUREMENT: axis availability not reliably measurable; C2 does not
proceed on this census`.

The result also does **not** justify C3. A measured rate below 0.10 would have
selected C3, but no rate is released because the measurement gate failed.

## Next admissible attempt: claim-first modifier census

The next experiment should repair the instrument, not the diagnosis system:

1. Freeze one canonical core and a canonical list of modifier claims per case
   before any availability review. Use a small human/root decomposition panel
   with explicit axis definitions and adjudication; do not ask the availability
   reviewers to regenerate the claim universe.
2. Present each frozen claim independently with the vignette and ask only
   `explicitly_stated`, `clinically_inferable` or `not_determinable`, requiring
   a literal quote for the first two classes.
3. Keep the same coarse reliability gate (exact >=0.80 and AC1 >=0.60), but
   compute it over identical claim IDs. This cleanly measures evidence
   availability rather than decomposition style.
4. Reuse the pre-declared decision thresholds: >=0.25 permits C2 with binary
   complete as co-primary; 0.10–0.25 permits C2 with a graded modifier endpoint
   only; <0.10 selects C3.

A 40–50 case root-annotated calibration slice should precede the full 200-case
claim-first census. If the availability-only panel still fails reliability,
model-panel modifier endpoints are not measurable and further C2/C3 efficacy
calls are not scientifically interpretable.
