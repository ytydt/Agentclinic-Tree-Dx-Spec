# Re-audit: no rule-based / template labeling

The previous JSONL for this batch is **invalid**. It used Python fill-in templates and/or defaulted unlisted candidates to `not_equivalent`. Redo every card by clinical judgment.

Do **not** call OpenRouter or any network LLM API.

## Forbidden

- Reason templates keyed only by relation type, including any of:
  - “The record supports {REF}, not the distinct diagnostic entity {LABEL}.”
  - “The case findings support {REF} rather than the distinct diagnostic entity {LABEL}.”
  - “{LABEL} is only an associated finding, complication, context, or differential…”
  - “Although clinically related, {LABEL} conflicts with the record-supported subtype…”
  - “captures only a compatible parent, cause, or component and omits required specificity”
  - “Given that {same snippet for every candidate on the card}, {LABEL} is a different diagnostic entity from {REF}.”
  - Chinese equivalents such as “属于不同的诊断实体 / 指向同一完整诊断对象 / 虽与病例涉及相近系统”
- Defaulting any candidate you did not explicitly judge to `not_equivalent`
- Assigning `relation` by string overlap, token Jaccard, regex, or keyword lists
- Copying the relation definition into `scope_detail`

Python may **serialize** judgments you already made. It must **not** decide `relation`.

## Required

Judge each candidate against the **full** `reference_diagnosis` using only `clinical_record`.

- `complete_equivalent`: same final diagnostic object including required subtype/etiology/anatomy/time/state/complication/stage/composite. Harmless aliases OK.
- `partial_parent_or_component`: compatible family/parent/child/cause/component but missing required specificity.
- `conflicting_subtype_or_scope`: related but incompatible subtype, anatomy, cause, time/state, stage, or composite.
- `manifestation_or_related`: manifestation, complication, association, or differential — not the requested final object.
- `not_equivalent`: different diagnostic entity.
- `uncertain`: the record genuinely cannot resolve the relation.

Do not upgrade a merely plausible diagnosis to complete equivalence. Missing tests are unknown, not negative.

Each `reason` must be one sentence that cites a **case-specific** finding (test, organism, anatomy, timing, histology, severity, etc.) that distinguishes **this** candidate. Two candidates on the same card must not share a cloned sentence with only the label swapped.

`scope_detail` is a short boundary phrase for this candidate (or `"none"`).

`case_quality_flags` is a list; use it when the record cannot support the reference object.

## Output

One JSON object per input card, **same order**. No markdown fences. Cover every `candidate_id` exactly once.

```json
{"blind_card_id":"RC...","candidate_relations":[{"candidate_id":"C001","relation":"not_equivalent","scope_detail":"...","reason":"...","confidence":"high"}],"case_quality_flags":[]}
```

`relation` ∈ {complete_equivalent, partial_parent_or_component, conflicting_subtype_or_scope, manifestation_or_related, not_equivalent, uncertain}

`confidence` ∈ {high, medium, low}

Print JSONL line count vs input card count when done.
