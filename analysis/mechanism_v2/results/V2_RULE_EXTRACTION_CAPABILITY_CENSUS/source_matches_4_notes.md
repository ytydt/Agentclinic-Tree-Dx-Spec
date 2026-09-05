# Source inventory 4: paired raw-output adjudication

Inventory was frozen at SHA256 `745351976758a670f4829bdf57dd644762258e41e423f7d334b04fd53a56acb8` before opening the reveal pack. All 62 frozen source units are matched to both historical prompt arms. `raw_indices` are zero-based within each selected cache; global assertion indices are supplied separately. Review considered complete raw outputs, including conflicting descendants, not only the best-looking row. The original and passage-scoped prompts were read directly from `run_trial_extraction.py`.

Unweighted counts within this pack only:

| Raw prompt arm | Faithful | Distorted, including partial | Omitted | Source ambiguous |
|---|---:|---:|---:|---:|
| Old/v2 | 4 | 31 | 26 | 1 |
| Free-group/v2 | 6 | 32 | 23 | 1 |

These are not population rates. Many distortions are incomplete or unscoped association sets, not invented facts. In particular, a correct individual feature does not make a source unit fully faithful when the frozen unit also includes clinically material subtype, age, exception or alternative-branch information. Quantitative synthesis should separately expose partial-only versus contradictory errors and should not label all 31/32 distortions equally dangerous.

## Three paired witnesses

1. **S4-03, Sarcomatoid urothelial carcinoma: group effect and atomic compression.** Old raw rows 0–2 share `g1`, `any`, `n=1`; epithelial origin is `required_for`, but cytokeratin and GATA3 are only `feature_of`. The count/connective is broadly right while the group's common necessity effect is incoherent. New rows 2–3 use homogeneous `required_for`, `at_least_n`, `n=1`, improving effect consistency. However, the epithelial morphological/cytokeratin evidence alternatives collapse into the opaque predicate `epithelial origin`; the separate biphasic definition also drops explicit epithelial and mesenchymal components from executable fields. Calling new `n=1` a quantifier error would be incorrect. This example is partial group improvement with remaining predicate/evidence-method loss.
2. **S4-05, light-chain restriction: a named macro is not a compiled cell-domain rule.** Old raw row 0 calls light-chain restriction a typical feature of B-cell lymphomas. New row 0 makes it obligatory and `required_for`. The source describes all relevant sampled lymphocytes restricted to kappa **or** all restricted to lambda, establishing a lymphocytic clone. It neither requires a single marker in isolation nor states that all B-cell lymphoma diagnoses require observed restriction. The stronger new relation is a direct raw-generation change. A trusted definition resolver could make the old macro useful; this pipeline has no such compiled resolver, so opaque lexical retention and executable group fidelity must be reported separately. Even a permissive lexical-macro scoring sensitivity would not repair new necessity reversal.
3. **S4-12, post-transplant intra-abdominal infection: descriptive list becomes `all`.** Both outputs recover fever, hypotension, ileus and abdominal pain. Old g1 is `any`; new g1 is `all`. The source gives a soft symptom set and expressly warns that immunosuppression can mask pain. Both lose that exception and transplant scope; the new prompt's definition of `all` as every member required makes its conversion especially unsafe. The symptom member recall is 4/4 in both arms, yet whole-rule fidelity is not achieved. Actual executor behavior is a separate question; the `all` raw structure alone does not prove a measured case-level veto.

Additional clear paired failures include PRP clinical **overlap** rendered `distinguishes_from` even when the new predicate explicitly says overlap (S4-10), less-common erythroderma rendered an `excludes`/negated rule (both arms), and infant osteomyelitis-to-suppurative-arthritis age conditions being lost despite improved quote selection (S4-11). VSD outputs repeatedly invert consequence direction into `VSD caused_by pulmonary hypertension/right ventricular overload` (S4-02).

## Source-zero windows reveal a different problem

Source-side omission counts cannot detect false diagnostic promotion in windows with no diagnostic rules; these require the separate output-side denominator. Relevant observed raw outputs are saved in `source_non_target_observations_4.json`:

- A Crohn/brodalumab contraindication becomes `Inflammatory bowel disease / Crohn disease progression / excludes` in both arms (S4-07).
- A bare subtype list becomes six `existence / feature_of / obligatory` assertions in the free-group arm (S4-09).
- A bibliography's “230 neuropathologically verified cases” becomes an obligatory diagnostic requirement for CJD in both arms (S4-14).
- Admission for complicated diverticulitis changes from `required_for` to `sufficient_for` in the free-group arm (S4-16), while the actual coffee-bean-sign rule is omitted.

Every example has a readily identifiable source ancestor. None should be called an untraceable fabrication merely because the resulting diagnostic relation is false.

## Attribution and representation boundaries

Raw origin is directly observed (B). The complete saved raw JSON already contains the loss/reversal, before normalization, gates, binding and execution. This identifies first damage; it does not identify the unique psychological or model-capacity cause. The prompt's focus preference, unrestricted “every assertion” remit, short noun phrase demand, underspecified relation directions and forced splitting of joined findings are plausible contributors (C) unless independently controlled.

Schema-only defects are separated from semantic labels. For example, both TB-spondylitis comparison sets faithfully preserve all six source features and the >3-level threshold, even though `comparator` is populated for `feature_of`, which the prompt schema disallows. An asserted predicate `absence of fever` remains semantically negative; it is not automatically a polarity reversal. String `"null"`, numeric strings and non-verbatim quotes are listed in `schema_errors`, not used alone to declare medical semantic distortion.

Some scope-loss judgments are deliberately strict: source transplant-specific microbial distributions, PRP lower-extremity scale preference, pediatric subtype/age restrictions, or the morphology-method expansion of epithelial origin are required for complete fidelity. These should be sensitivity-reviewed rather than silently relaxed after seeing outputs. The source inventory remains unchanged.
