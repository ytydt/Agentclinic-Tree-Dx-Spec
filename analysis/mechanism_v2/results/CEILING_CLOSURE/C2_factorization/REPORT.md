# C2 executable core/modifier factorization: closure result

Status: **NOT_EXECUTED_OPERATIONAL_NO_GO**

Scientific result: **NOT_EVALUATED**. This status is not evidence that core/
modifier factorization is ineffective, harmful or scientifically negative.

## Frozen design

The preregistered E5 `base4` cohort was frozen without an online call. It has
200 gold-exposed conditional-conversion cases: 100 DiagnosisArena and 100
MedCaseReasoning. It is not an overall-recall or open-diagnosis cohort.

The five frozen arms are flat labels, exact identity, executable core/member
lattice, singleton structure sham and deterministic corrupted-modifier
mapping. Every treatment arm must return an existing surface candidate ID; it
cannot synthesize a new answer. The freeze binds:

| Artifact | SHA-256 |
|---|---|
| `freeze/freeze.json` | `3fb2315d0f75d8751b899c190a9e7e01e7b94012269edca3ff29520855f9a12b` |
| `freeze/cases.jsonl` (file bytes) | `1f6e4ec065a55cf26832d7032d203512c35fe7f8a3a631d1423576a5c069c9b9` |
| E5 joined source | `cbf39ef3878e956521224a2d30ac1c11deb0a874d79fa4ea58a80a2342127df4` |
| Disease-name bridge | `b67901c33685bedd8758620522a2a5740cf529eaf0e64b5ab20f784740732d74` |

The manifest's canonical row hash is
`1be9453cbcca2c9f496d58868d62064987416492f9f70a2b3f1f24bf778613ab`,
and its freeze ID is
`071c26d28666802bb3959d236dfb8514c7e31d84aa8779d6479f5619ffa1615e`.
The protocol source commit was
`bfd6755978693435d0929efe513f70e1a893ccfe`.

## Why the probe was not executed

The C0 model-panel release gate is
`NO_GO_COVERAGE_RELIABILITY_AUDIT_ONLY`. Separately, the bound operational
incident records OpenRouter `HTTP_402_INSUFFICIENT_CREDITS`. The outcome-blind
factorizer/modifier annotations and the two independent map reviews therefore
do not exist. No substitute model, imputation, changed threshold or fabricated
response was used.

The bound C1 operational gate is also
`NOT_EXECUTED_OPERATIONAL_NO_GO` (`passed=false`). Without a passed C1
admission gate, C2 could only be interpreted as an isolated topology probe.
That allowed scope does not turn missing annotations or reviews into a result:
the isolated probe itself is **NOT_EXECUTED**.

| Stage or endpoint | Result |
|---|---:|
| Completed annotation cases | 0 |
| Completed independent review rows | 0 |
| Compiled selector jobs | 0 |
| Official C2 execution state | not started due to prerequisites |
| Provider-account call count | not audited (`null`) |
| Pair precision | not evaluated (`null`) |
| Modifier-axis precision | not evaluated (`null`) |
| Unsafe-merge and unresolved rates | not evaluated (`null`) |
| Reviewer agreement / Gwet AC1 | not evaluated (`null`) |
| Five-arm clinical contrasts | not evaluated (`null`) |

The ordinary scientific gate could not represent this state safely: omitting
its required annotation/review arguments exits before writing an artifact,
while empty ledgers can create numeric defaults that look like endpoint
measurements. The new shared `not-executed-gate` path instead emits null
scientific metrics, `scientific_result=NOT_EVALUATED`,
`scientific_negative=false` and `passed=false`. The normal job compiler rejects
this gate.

## Machine-readable decision and provenance

`gate.json` is the detailed fail-closed gate and `decision.json` is its compact
decision record. Their SHA-256 values are respectively
`52393d93805d03a1b4f7d1f30adc85431bb1a0ec033994acae4b89627de4c7bf`
and
`35a8aaf2237f4c43e2cb7c2c8b2556182edc85a079260b9a32724e02507105a7`.
The gate binds the C0 decision
(`9a493eaac9392a53796e25d88ef2273ffd7a88476838231c0cdfa9a49f5a6c4d`)
and the 402 incident
(`f0848a8a0fb63f409360f898f35f69abb4f826fa751df065ac80d63dcd6353c5`),
plus the C1 operational gate
(`36346d7a64a855c0bb495719d769b499eef966f9f36b7d279e0ca1b39119d6b4`).

Reproduction is offline:

```bash
python -m analysis.mechanism_v2.ceiling_breakthrough_experiments \
  factorization freeze \
  --out analysis/mechanism_v2/results/CEILING_CLOSURE/C2_factorization/freeze

python -m analysis.mechanism_v2.ceiling_breakthrough_experiments \
  factorization not-executed-gate \
  --freeze analysis/mechanism_v2/results/CEILING_CLOSURE/C2_factorization/freeze \
  --upstream-decision analysis/mechanism_v2/results/CEILING_POOL_CENSUS/analysis/analysis_summary.json \
  --operational-incident analysis/mechanism_v2/results/CEILING_POOL_CENSUS/operational_incident.json \
  --admission-gate analysis/mechanism_v2/results/CEILING_CLOSURE/C1_admission/gate.json \
  --out analysis/mechanism_v2/results/CEILING_CLOSURE/C2_factorization/gate.json \
  --decision-out analysis/mechanism_v2/results/CEILING_CLOSURE/C2_factorization/decision.json
```

If capacity is restored, the only permitted continuation is to resume the
same frozen annotation and reviewer identities, then apply the preregistered
gate and five-arm comparison without changing the sample, models, arms or
thresholds.

## Offline implementation closure for a future resume

The four previously open fail-closed findings are now implemented and covered
by offline tests, without running a case-bearing call:

- the canonical review payload binds each original `surface_label`, exact
  `modifier_source_obligations`, and explicit hashed core-pair/modifier-axis
  units;
- the gate rejects either empty review class and requires every expected unit
  to have exactly the two frozen heterogeneous reviewer models, with annotation,
  review-product, stage, payload and unit hashes bound;
- every C2 selector response must contain a validator-checked boolean
  `modifier_hallucination`; absence is non-evaluable rather than `false`, and
  the analysis now reports rescue against scope compression, hallucination,
  catastrophic substitution and their combined case-level harm union;
- C2 analysis requires a bound truth manifest, immutable five-arm job manifest
  and exact 200-case/1,000-job denominator, selector-response product/stage/raw
  manifests and telemetry, plus exact response job/payload/prompt/cache hashes.
  The analysis deterministically reconstructs the derived response rows from
  the raw model ledger; hash drift or a substituted model remains an ITA
  failure and blocks Go.

The operational gate's absence-of-execution statement is explicitly design-
state evidence, not provider-account telemetry; `online_call_n` is therefore
`null`. The formal-freeze check also recomputes `freeze_id`, verifies source
artifact hashes and enforces the frozen cohort/family/arm contracts.

Until then, C2 supplies a reusable frozen design and an operational No-Go—not
a scientific effect estimate and not deployment evidence.
