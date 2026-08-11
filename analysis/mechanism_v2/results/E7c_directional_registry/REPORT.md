# E7c — directional clinical registry and bounded inheritance

## Decision

The realised E7c treatment does **not** improve strict pre-mapper top-1 on the
299 E7a unsafe-fold development cases. Directional relation typing loses two
net cases against the exact-identity control (19/299 vs 21/299), while adding
the bounded inheritance policy produces two gains and two harms relative to
the directional graph, for zero net change.

This is not evidence that a correct typed registry cannot help. It is evidence
that the implemented LLM-typed registry is not yet a valid test of that ideal:
its direction fidelity is poor, repeated instances of the same label pair are
not stable, and relation-bearing payloads move the selector even when the edge
is unrelated to the competing champions. The proper conclusion is therefore:

1. reject this E7c implementation as a deployable mechanism;
2. do not credit its isolated gains to relation semantics;
3. require deterministic direction, inverse, duplicate and cycle checks before
   the relation graph is admitted to RCR-3.

## Frozen design

- Population: all 299 cases where E7a found an unsafe substring fold, comprising
  167 DiagnosisArena (DA) and 132 MedCaseReasoning (MCR) cases.
- Candidate pool and order: the exact-identity E7b registry, fixed across arms.
- Online blinding: no gold label, answer options, old rank, old score, source
  model identity, old response or evaluator field was sent.
- Relation annotator: `google/gemini-2.5-flash`, in chunks of at most six pairs.
- Selector: `deepseek/deepseek-v4-flash-0731`; the prompt and candidate order
  were identical across the four arms.
- Arms: no graph (`exact_control`), non-semantic edges
  (`generic_non_equivalence`), typed directional edges
  (`directional_relation`), and the same typed edges plus explicit bounded
  inheritance policy (`bounded_inheritance`).
- Primary endpoint: displayed-label exact/frozen-synonym top-1 before any answer
  mapper. Terminal failures are incorrect in the intention-to-analyse (ITA)
  denominator.
- Status: development/mechanism evidence, not a new confirmation cohort.

The preregistration was written before calls and is retained in
`preregistration.json`.

## Primary result

| Arm | ITA correct | ITA rate | Served | Terminal failures |
|---|---:|---:|---:|---:|
| Exact control | 21/299 | 7.02% | 299 | 0 |
| Generic non-equivalence | 21/299 | 7.02% | 296 | 3 |
| Directional relation | 19/299 | 6.35% | 297 | 2 |
| Bounded inheritance | 19/299 | 6.35% | 297 | 2 |

| ITA comparison | Gain | Harm | Delta | Case-bootstrap 95% CI | Exact McNemar p | Champion flips |
|---|---:|---:|---:|---:|---:|---:|
| Directional − exact | 1 | 3 | -0.67 pp | [-2.01, +0.67] pp | 0.625 | 48/299 |
| Bounded − directional | 2 | 2 | 0.00 pp | [-1.34, +1.34] pp | 1.000 | 45/299 |
| Bounded − exact | 1 | 3 | -0.67 pp | [-2.01, +0.67] pp | 0.625 | 53/299 |
| Generic − exact | 1 | 1 | 0.00 pp | [-1.00, +1.00] pp | 1.000 | 47/299 |

The served-pair and complete-relation-typing sensitivities preserve the same
direction. Restricting to the 290 cases with complete relation typing gives
directional 6.55% versus exact 7.24% (delta -0.69 pp). The null intervals are
wide because only 33/299 fixed candidate pools expose an exact/frozen-synonym
gold label; E7c is a conditional selector test, not an overall benchmark score.

DA and MCR must not be pooled as if interchangeable. On DA, directional loses
one case and gains none (2/167 vs 3/167). On MCR, it gains one and loses two
(17/132 vs 18/132). Neither family contains evidence of a positive net effect.

## Treatment fidelity

The relation annotator served 350/359 chunks and 1,155 pair instances; 290/299
cases have complete relation typing. Nine chunks failed schema validation and
were retained as missing typed edges rather than imputed.

Two independent internal diagnostics show that the treatment itself is noisy:

- On 776 lexically proper-containment edges where predicate direction can be
  checked without clinical gold, only 503 agree with the declared
  parent/subtype/refinement direction: **64.82%**. Agreement is 45.45% for
  anatomic refinement, 53.28% for `parent_of`, 68.74% for `subtype_of`, 72.73%
  for etiologic refinement and 75.00% for temporal refinement.
- E7a accidentally supplies useful internal replicates. Among 345 label-pair
  groups typed more than once, 67 receive incompatible semantic signatures
  even after normalising inverse parent/subtype wording: **80.58% repeat
  consistency**, with inconsistency in 41 cases.

These are lower-bound structural checks rather than clinical ground truth. The
manual audit confirms that the discrepancies include clinically substantive
errors, not merely wording differences. For example, generic histoplasmosis is
typed as a subtype of laryngeal histoplasmosis, generic hypophosphatemic rickets
as a subtype of HHRH, and ovarian cyst as a subtype of ovarian
cystadenocarcinoma. The same NF1/fibromatosis pair is variously called
`parent_of`, `subtype_of` and `unrelated`.

## What moved the selector

The selector is highly sensitive to the presence and wording of graph context:

- Directional vs exact changes 48 champions. In 36/48, at least one competing
  champion is a graph node; in 15/48 the two champions are directly connected.
- Bounded vs directional changes 45 champions even though the clinical edges
  are the same and only inheritance-policy prose differs.
- The non-semantic generic graph changes 47 champions despite having no
  directional clinical information; 15 of those flips involve neither
  champion as a graph node.

This pattern separates three mechanisms:

1. **True relation-treatment failure.** Wrong direction and contradictory edges
   can push the selector toward the wrong level of specificity, as in laryngeal
   versus disseminated histoplasmosis.
2. **Graph salience without task projection.** Correct but irrelevant edges can
   draw attention to a related distractor, as in orbital meningioma versus
   meningioma while the correct candidate is fibrous dysplasia.
3. **Context/placebo instability.** An irrelevant or explicitly non-semantic
   graph can change a winner. The ECR gain occurs in a case where the only graph
   edge is between two periodontitis labels, not between ECR and pulpitis; it
   therefore cannot be credited to typed clinical semantics.

Relation-type heterogeneity does not rescue a subgroup. The 202 cases containing
`subtype_of` account for the directional arm's one gain and three harms. No
other relation family shows a positive net directional effect.

## Reliability and resource ledger

- 1,493 semantic calls and 2,052 physical attempts were recorded.
- 2,117,331 input tokens and 5,375,381 output tokens were reported by providers.
- 359 relation calls account for 69,531 output tokens; selector reasoning and
  JSON retries account for almost all remaining output volume.
- Seven selector conditions fail downstream schema validation. Four semantic
  telemetry records are themselves terminal failures; the difference is parsed
  but schema-invalid responses (for example `champion` instead of
  `champion_id`). ITA scores all seven conditions as incorrect.
- The environment lacks the `openai`, `httpx`, `requests` and `pytest` packages.
  The existing client therefore used its stdlib OpenRouter compatibility path.
  The runner still retains the official OpenAI SDK path for environments where
  it is installed.

The first offline cost table incorrectly joined the runner's canonical JSON
hash to the client's wire-JSON hash and consequently labelled selector calls as
unassociated. `e7c_analysis.py` now reconstructs the wire payload, the regression
test covers the distinction, and the corrected allocation is in
`analysis_summary.json`. Outcome statistics were never affected.

## Consequence for RCR-3

RCR-3 should not simply reuse these graph edges. Before a typed edge reaches the
selector it needs deterministic safeguards:

1. canonicalise duplicate labels and collapse repeated pair proposals;
2. enforce predicate signatures (`specific -> general` for subtype/refinement,
   `general -> specific` for parent) and automatically invert obvious lexical
   containment errors;
3. reject mutually incompatible directions and relation classes for one pair;
4. detect specificity cycles and quarantine the affected component;
5. bind qualifier evidence to the refinement endpoint;
6. separate task-object projection (etiology, manifestation, complication,
   subtype, composite) from graph specificity;
7. expose only the graph component relevant to the final comparison, so an
   unrelated edge cannot become a salience cue;
8. trigger the optional fourth call only on these explicit alarms.

E7c therefore supplies a useful negative mechanism result: safe identity is
necessary, but adding unconstrained LLM-typed relations after identity repair is
not sufficient and can reintroduce a new form of aggregation error.
