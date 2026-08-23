# Claim-first modifier availability calibration

Declared 2026-08-19, before construction or availability calls.

## Purpose

The 200-case DA modifier-headroom census failed its measurement gate. The
failure was not localized to core selection: among the 89 cards where both
reviewers were schema-valid, core-candidate exact agreement was 0.809. The
dominant failure was that each reviewer generated a different modifier universe:
their six-axis sets were identical in only 0.202 of cases, with 191
Gemini-missing/Claude-determinable axis occurrences.

This calibration removes that confound. It freezes one claim universe before
availability review, assigns immutable claim IDs, and asks both reviewers only
whether the same claims are determined by the vignette.

This is an **instrument calibration**, not a headroom census. The available
environment cannot provide human/root decomposition, so a model-generated claim
universe is never relabelled as clinical truth and cannot authorize C2 or C3 by
itself.

## Frozen sample

Fifty DA cases selected from the 200-case C1 freeze by ascending
`sha256("claim-first-v1|" + case_key)`. This selection is independent of
reference content, prior modifier outputs, reviewer success and all endpoint
values.

## Phase 1: reference-only construction

Construction model: `anthropic/claude-sonnet-4.6`, temperature 0.

Payload contains only:

- case key;
- reference diagnosis; and
- frozen candidate IDs and labels.

It does **not** contain the vignette, prior modifier reviews, C0 relations,
selector outputs, arm names or endpoint values. The constructor returns:

- one core entity;
- one supplied candidate ID matching that core, or empty; and
- zero or more canonical claims on the frozen axes `etiology`, `anatomy`,
  `time_stage`, `subtype`, `complication`, `composite_components`.

Claims receive deterministic IDs `M01`, `M02`, ... after sorting by
`(axis, normalized value)`. A failed or invalid construction card remains
explicit and is excluded from availability calls; it is never inferred from a
vignette.

Because construction is model-generated, its clinical correctness is not an
endpoint. If the availability instrument passes calibration, the same 50 claim
cards must still receive human/root correction before they can estimate
headroom.

## Phase 2: claim-first availability

Reviewer A: `google/gemini-2.5-flash`.

Reviewer B: `anthropic/claude-sonnet-4.6`.

Both use temperature 0 and receive byte-identical claim cards containing the
vignette, frozen core and immutable claim IDs. They may not add, remove, merge,
rename or re-axis a claim. For every claim they return exactly one of:

- `explicitly_stated`;
- `clinically_inferable`; or
- `not_determinable`.

The first two require a verbatim quotation from the vignette. Character offsets
are not requested. A non-verbatim or empty quotation does not invalidate the
whole card; that claim alone is deterministically downgraded to
`not_determinable`, with `grounding_downgraded=true`. This rule is frozen before
calls because the previous census showed that whole-card invalidation confounds
availability with one malformed quotation.

A failed card contributes `not_determinable` for every frozen claim.

## Reliability gate

The panel passes only if:

- construction success is at least 0.90 over the 50 selected cases;
- each availability reviewer returns schema-valid coverage on at least 0.90 of
  constructed cards;
- coarse agreement, where both positive classes collapse to `determinable`,
  has exact agreement >= 0.80 and Gwet AC1 >= 0.60 over identical claim IDs.

The fine three-way distinction is descriptive only. No reliability threshold is
defined for it.

## Decision

- If the gate passes, the availability-only instrument is calibrated. Next:
  human/root-correct the 50 frozen decompositions, re-run availability on any
  changed claims, then expand to the 200-case claim-first census.
- If construction or reviewer service fails, repair only the operational
  instrument while outcomes remain unreleased.
- If service passes but coarse agreement fails, modifier availability is not
  reliably measurable by this model panel even after claim freezing. Stop C2/C3
  efficacy work and move to human evidence adjudication or deterministic
  evidence rules.

No modifier-headroom rate from this calibration selects C2 or C3.
