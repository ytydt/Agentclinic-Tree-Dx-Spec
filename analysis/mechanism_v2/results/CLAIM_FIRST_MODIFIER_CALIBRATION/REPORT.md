# Claim-first modifier availability calibration

Status: **EXECUTED — NO_GO_MEASUREMENT**

Claim freezing substantially repaired the first census's decomposition confound,
but did not make the model panel reliable enough for a C2/C3 decision.

## Execution

- Deterministic sample: 50 DA cases from the frozen C1 set.
- Reference-only construction: 50/50 valid under
  `anthropic/claude-sonnet-4.6`.
- Frozen claim universe: 83 claims over 50 cases; 4 cases have zero additional
  modifiers.
- Corrected availability service: Gemini 49/50; Claude 50/50.
- Literal-grounding downgrades: Gemini 5 claims; Claude 2 claims.

The first availability transport run exposed an exact-coverage defect: Gemini
invented IDs on zero-claim cards and Claude often returned only `M01`. No
agreement statistic had been computed. `OPERATIONAL_CORRECTION.md` records the
pre-analysis repair: explicit expected IDs/count, deterministic empty response
for zero-claim cards, symmetric re-run and SHA-preserved prior outputs.

## Frozen reliability gate

| Check | Required | Observed | Result |
|---|---:|---:|---|
| Construction service | >=0.90 | 1.000 | pass |
| Gemini service | >=0.90 | 0.980 | pass |
| Claude service | >=0.90 | 1.000 | pass |
| Coarse determinable/not exact agreement | >=0.80 | **0.7108** | fail |
| Coarse Gwet AC1 | >=0.60 | **0.5531** | fail |

All operational checks pass. Both reliability checks fail, so the claim universe
is not a released clinical substrate and no headroom estimate may select C2 or
C3.

For scale only, not as released endpoints, consensus calls 52/83 claims
determinable (0.6265) and all claims determinable in 26/50 cases (0.520).
Because construction is model-generated and the panel gate fails, neither rate
is clinically interpretable.

## What claim freezing fixed

The free-generation census had coarse exact agreement 0.1542 and AC1 −0.6818.
Claim-first calibration raises those to 0.7108 and 0.5531. Most of the earlier
failure was therefore indeed a decomposition-universe failure.

The remaining 24 coarse disagreements are perfectly directional:

- Gemini `not_determinable`, Claude `clinically_inferable`: 20;
- Gemini `not_determinable`, Claude `explicitly_stated`: 4;
- no coarse disagreement occurs in the reverse direction.

Disagreement is largest for subtype (9/20), composite components (3/7) and
time/stage (2/5), with smaller but still material rates for etiology (5/22),
complication (3/13) and anatomy (2/16). Representative disputes include whether
the record establishes `advanced/third-degree`, `atypical`, `ancient`,
`pressure-induced`, `radiation-induced`, `Bayés syndrome`, or dual AV pathways.

The panel is not disagreeing about literal text alone. It has no stable shared
threshold for **clinical inferability**: Claude systematically accepts an
indirect reasoning chain that Gemini declines.

## Post-hoc diagnostic, not a revised gate

If the positive class is narrowed after the fact to `explicitly_stated` only,
agreement is 0.7952 and AC1 0.6017, with nearly identical positive counts
(Gemini 35, Claude 34). AC1 would clear its threshold and exact agreement would
miss by 0.0048.

This cannot rescue the preregistered gate: it is a post-outcome endpoint change.
It does, however, localize the unstable construct. Literal support is close to
measurable; unconstrained clinical inference is not.

## Decision before user-authorized manual adjudication

The frozen result is:

`NO_GO_MEASUREMENT: claim freezing did not make model-panel availability
reliable; do not run C2/C3 efficacy experiments`.

The user subsequently authorized the agent to act as a manual annotation
surrogate and to search medical sources for uncertain relations. That work is a
new, explicitly labelled adjudication layer. It does not retroactively turn the
failed model-panel calibration into a pass and is never called human/root truth.

## User-authorized manual-surrogate result

All 50 frozen cases were independently corrected in five primary batches. A
25-case queue covering low/medium confidence, web-supported claims and duplicate
disagreements received a second blind review; the parent then adjudicated every
scientific change. Three parent overrides are documented in
`manual_surrogate/PARENT_ADJUDICATION.md`.

- Final cases: 50
- Final claims: 85
- Determinable claims: 74/85 (0.871)
- Cases with all claims determinable: 35/50 (**0.700**)
- Availability: 23 explicitly stated, 51 clinically inferable, 11 not
  determinable
- Confidence: 65 high, 20 medium
- Final artifact SHA-256:
  `2211c6c769188fae49aa46a174ae70a7f310dfaae13928f8ca35a99fe3c0ea45`

The manual-surrogate protocol's 0.25 routing threshold is therefore exceeded:
`PROCEED_C2_BINARY_COPRIMARY`. This is evidence that a modifier-aware
representation is technically plausible because the vignette usually contains
the needed modifier information. It is not a publication-level prevalence
estimate and does not repair the failed model-panel reliability gate.

The resumed frozen C2 topology probe subsequently failed its independent map
gate before selector execution. That failure localizes the next bottleneck to
the automatic factorizer/binder, not to modifier availability: the current C2
map is not reliable enough to test efficacy, and C3 evidence acquisition is not
indicated by this calibration.
