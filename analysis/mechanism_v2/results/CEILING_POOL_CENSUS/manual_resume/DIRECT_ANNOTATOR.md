# Direct annotator protocol

You are the annotator. Read the assigned cards yourself. Type the labels yourself. Do not generate labels with code.

Do **not** call OpenRouter or any network LLM API.

## You must

1. **Read** the entire assigned batch JSON with the Read tool. Do not skip `clinical_record`.
2. For every candidate on every card, decide `relation` from the record vs the full `reference_diagnosis`.
3. **Write/StrReplace the output `.jsonl` file directly.** One JSON object per line, same card order as the input.

## Forbidden (hard)

- Any Python/Shell that builds, formats, or dumps the JSONL (`json.dump`, helper `.py`, heredoc generators, `print(json.dumps(...))`)
- ApplyPatch/Write of a generator script
- Fill-in reason templates keyed by relation type
- Defaulting unlisted candidates to `not_equivalent`
- String overlap / Jaccard / regex classifiers
- Cloning one sentence across candidates with only the label swapped

## Clinical labels

- `complete_equivalent`: same final diagnostic object including required subtype/etiology/anatomy/time/state/complication/stage/composite. Harmless aliases OK.
- `partial_parent_or_component`: compatible family/parent/child/cause/component but missing required specificity.
- `conflicting_subtype_or_scope`: related but incompatible subtype, anatomy, cause, time/state, stage, or composite.
- `manifestation_or_related`: manifestation, complication, association, or differential — not the requested final object.
- `not_equivalent`: different diagnostic entity.
- `uncertain`: the record genuinely cannot resolve the relation.

Do not upgrade a merely plausible diagnosis to complete equivalence. Missing tests are unknown, not negative.

Each `reason` is one sentence citing a finding from **this** record that distinguishes **this** candidate.

`scope_detail` is a short boundary for this candidate, or `"none"`.

`case_quality_flags` is a list.

`confidence` ∈ {high, medium, low}

Cover every `candidate_id` exactly once.

```json
{"blind_card_id":"RC...","candidate_relations":[{"candidate_id":"C001","relation":"not_equivalent","scope_detail":"...","reason":"...","confidence":"high"}],"case_quality_flags":[]}
```

Print JSONL line count vs input card count when done. Allowed tools after reading: **Write** and **StrReplace** on the output jsonl only (Read of the batch is required first).
