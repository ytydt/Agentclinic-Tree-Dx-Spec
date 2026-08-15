# C3 active-evidence closure

Status: **NOT_EXECUTED_OPERATIONAL_NO_GO**

## What was closed

The outcome-blind retrospective design was frozen for 200 E5 cases (100 DA and
100 MCR) with the preregistered `no_acquisition`, `typed_action`, and
`cost_matched_random` arms. The freeze binds the E5 source archive by SHA-256
and preserves the raw historical source from which a future builder must
extract actually performed actions and exact result offsets. No structured
action bank or offset set was produced in this closure.

The implementation now requires two separate fail-closed gates:

1. a construction gate over the action bank, independent reviews, and
   pre-release predictions; and
2. a post-policy gate that projects the frozen blind audits onto the selected
   action and cost-band control before any post-release clinical comparison.

The second gate makes need-resolution precision/recall, action relevance,
ordinal information gain per cost, wrong episode/object binding, and
unnecessary high-risk action explicit endpoints. Missing safety fields are no
longer treated as false.

The frozen artifact identities are:

| Artifact | SHA-256 |
|---|---|
| `freeze/freeze.json` | `10e75683de6ad82eb1bfac85e020961d4a4fc04f16cb1245458f2b4de2d885d6` |
| `freeze/cases.jsonl` (file bytes) | `5fe3676ec7cade5d846984a796d69d464d41ac6c8ff6db8bc1bce35ebc2e6150` |
| E5 joined source | `cbf39ef3878e956521224a2d30ac1c11deb0a874d79fa4ea58a80a2342127df4` |

The canonical cases hash is
`0ab0c95d059209f57e7c3f6f8b1d6e88182bb7b5449bc93eb88188df8e514447`,
the freeze ID is
`9f714d4b0cbcfac0cfdc751bc531bd384f90252d7c2ff0469f29d9dd4c92f997`,
and the protocol source commit is
`bfd6755978693435d0929efe513f70e1a893ccfe`.

## Why no scientific result was produced

C0 remained `NO_GO_COVERAGE_RELIABILITY_AUDIT_ONLY`, and the recorded provider
incident was `OpenRouter / HTTP_402_INSUFFICIENT_CREDITS`. No model substitution,
threshold change, imputation, or partial execution was permitted. Consequently,
none of the 200 builder tasks, 400 independent-review tasks, or 200 pre-release
prediction tasks was executed. The planned downstream maxima—up to 64 admitted
policy tasks and up to 192 post-release comparator tasks—were therefore never
compiled or executed. No policy or post-release job ledger was produced.

The machine-readable gate therefore records every preregistered construction,
policy, safety, and clinical endpoint value as `null`,
`scientific_result=NOT_EVALUATED`, and `scientific_negative=false`. Its call
count is also `null`: the evidence is that official execution products and
runner/provider telemetry are absent, not a provider-account usage log. The
gate binds the freeze, C0 decision, operational incident, and gate code by
SHA-256.

The machine-readable `gate.json` and `decision.json` SHA-256 values are,
respectively,
`1e1f0e84e0dd7a660abdef4b9ad606d7769ddce46c3601fc01c1611b5c6cf81e`
and
`605f087b7ac484afd2986e958e88cd02b60aabf7e4643675470a944d1ccc90ac`.
The decision's recorded gate hash matches the former value. All 79 listed
scientific endpoint fields are `null`; this is an explicit non-evaluation
schema, not a vector of zero effects.

## Offline integrity closure for a future resume

No case-bearing call was made, but the executable path was hardened and tested
offline. A future construction gate must reconstruct the exact blinded builder,
two heterogeneous reviewer and pre-release prediction task identities from the
freeze; validate their product, stage, raw-response and telemetry manifests;
replay the same response validators; and deterministically reproduce the
eligible SHA-ranked 32 DA / 32 MCR sample.

The post-policy gate must likewise bind the 64 immutable policy jobs and their
raw selector responses before projecting independent action-bank audits onto
the typed action and deterministic cost-band control. Post-release analysis is
restricted to exactly 64 cases × 3 arms = 192 immutable jobs, with bound raw
responses, model identity, telemetry, post gate and exact truth manifest.
Changing the freeze, annotations, selected actions, prompts, payloads, job
hashes, response model or denominator fails closed.

Offline reproduction of the present operational decision is:

```bash
python -m analysis.mechanism_v2.ceiling_breakthrough_experiments \
  active freeze \
  --out analysis/mechanism_v2/results/CEILING_CLOSURE/C3_active_evidence/freeze

python -m analysis.mechanism_v2.ceiling_breakthrough_experiments \
  active not-executed-gate \
  --freeze analysis/mechanism_v2/results/CEILING_CLOSURE/C3_active_evidence/freeze \
  --upstream-decision analysis/mechanism_v2/results/CEILING_POOL_CENSUS/analysis/analysis_summary.json \
  --operational-incident analysis/mechanism_v2/results/CEILING_POOL_CENSUS/operational_incident.json \
  --out analysis/mechanism_v2/results/CEILING_CLOSURE/C3_active_evidence/gate.json \
  --decision-out analysis/mechanism_v2/results/CEILING_CLOSURE/C3_active_evidence/decision.json
```

## Interpretation boundary

This result does not show that active evidence acquisition succeeds or fails.
It shows only that the frozen experiment could not enter execution under its
preconditions. If capacity is restored, the same frozen identities must be
resumed and both gates must pass before any effect claim.

Even after a future successful run, this design remains retrospective and
off-policy: it reveals results of historically executed actions. It is not a
prospective trial in which a decision maker orders a new test or intervention.
