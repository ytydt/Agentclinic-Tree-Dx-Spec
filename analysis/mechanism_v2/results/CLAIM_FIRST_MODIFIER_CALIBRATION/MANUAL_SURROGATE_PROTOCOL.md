# Manual-surrogate adjudication protocol

Declared 2026-08-19 after the frozen model-panel calibration returned
NO_GO_MEASUREMENT and after the user explicitly authorized the Cursor agent to
perform the manual annotation task, including web search for uncertain medical
content.

## Provenance

This is **user-authorized Cursor agent manual-surrogate annotation**. It is not
a human clinician panel, human-root truth or external expert adjudication. Every
downstream artifact must preserve that label.

## Blinding

Annotators may read:

- the reference diagnosis;
- vignette;
- frozen candidate registry;
- reference-only constructed core and claims; and
- medical sources needed to resolve general clinical relations.

They may not read Gemini/Claude availability responses, per-claim disagreements,
calibration endpoint values or historical selector outcomes while annotating.
The final adjudicator may inspect assistant annotations and cited sources, but
must not use model-panel votes as evidence.

## Per-case tasks

1. Correct the reference decomposition:
   - one canonical core disease entity;
   - best matching supplied candidate ID or empty;
   - all and only modifiers expressed by the reference diagnosis;
   - each modifier on one frozen axis.
2. Judge each corrected modifier against the vignette:
   - `explicitly_stated`;
   - `clinically_inferable`;
   - `not_determinable`.
3. For positive judgments, provide one or more exact vignette quotations and a
   short reasoning chain.
4. Record confidence `high`, `medium` or `low`.
5. When general medical knowledge is material and uncertain, search the web and
   record source URLs. Sources establish only the general relation; they cannot
   manufacture a patient fact absent from the vignette.

## Output schema

One JSON object per case:

```json
{
  "case_key": "...",
  "core_entity": "...",
  "core_candidate_id": "D# or empty",
  "construction_changed": true,
  "claims": [
    {
      "manual_claim_id": "H01",
      "axis": "etiology|anatomy|time_stage|subtype|complication|composite_components",
      "value": "...",
      "availability": "explicitly_stated|clinically_inferable|not_determinable",
      "support_quotes": ["exact vignette substring"],
      "reasoning": "...",
      "confidence": "high|medium|low",
      "source_urls": []
    }
  ],
  "case_confidence": "high|medium|low",
  "notes": ""
}
```

Claims are deterministically renumbered `H01`, `H02`, ... by
`(axis, normalized value)` after final adjudication.

## Quality control

- Five independent assistants annotate disjoint deterministic fifths of the 50
  cases.
- Ten SHA-selected cases receive a second independent annotation.
- The parent agent reviews every low-confidence item, every web-sourced item,
  every duplicate-case disagreement and every positive claim whose quote is not
  a literal substring.
- Final output retains both raw batches and an adjudication ledger; no raw
  annotation is overwritten.

## Decision use

The 50-case manual-surrogate result is a calibration estimate, not human-root
truth. It may decide which implementation track is technically plausible:

- all-claims-determinable rate >=0.25: proceed to C2 representation work;
- 0.10–0.25: C2 only with a graded modifier endpoint;
- <0.10: C3 evidence acquisition is indicated.

Before a publication-level claim, a real clinical reviewer must validate the
manual-surrogate decomposition and all low/medium-confidence inferences.
