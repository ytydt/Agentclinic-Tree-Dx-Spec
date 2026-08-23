# Ceiling pool census: manual reviewer resume

You are completing **missing blinded clinical relation cards** after an OpenRouter HTTP 402 credit exhaustion. Do not call OpenRouter. Judge from the card text only.

## Output

Write **one JSONL file**. One object per input card, same order as the input file. No markdown fences. No commentary in the file.

```json
{"blind_card_id":"RC...","candidate_relations":[{"candidate_id":"C001","relation":"not_equivalent","scope_detail":"...","reason":"...","confidence":"high"}],"case_quality_flags":[]}
```

## Schema (validator will reject otherwise)

- Cover **every** `candidate_id` in that card's `candidate_registry` **exactly once**.
- `relation` must be one of:
  - `complete_equivalent`
  - `partial_parent_or_component`
  - `conflicting_subtype_or_scope`
  - `manifestation_or_related`
  - `not_equivalent`
  - `uncertain`
- `confidence` must be `high`, `medium`, or `low`.
- `reason` must be a non-empty case-grounded sentence.
- `scope_detail` should be a short boundary phrase (may be `"none"`).
- `case_quality_flags` must be a list (empty allowed).

## Clinical rules

Evaluate each candidate against the **full** `reference_diagnosis` using only `clinical_record`.

- `complete_equivalent`: same final diagnostic object with all required subtype/etiology/anatomy/time/state/complication/stage/composite components. Harmless aliases OK.
- `partial_parent_or_component`: compatible family/parent/child/cause/manifestation/component but missing required specificity or a component.
- `conflicting_subtype_or_scope`: related but incompatible subtype, anatomy, cause, time/state, stage, or composite scope.
- `manifestation_or_related`: manifestation, complication, association, or differential — not the requested final object.
- `not_equivalent`: different diagnostic entity.
- `uncertain`: the record genuinely cannot resolve the relation.

Do **not** upgrade a merely plausible diagnosis to complete equivalence. Missing tests are unknown, not negative. Candidate order and wording polish have no evidential weight. You do not know which system produced any candidate.

Keep reasons brief (one sentence). Finish **all** cards in the assigned batch.
