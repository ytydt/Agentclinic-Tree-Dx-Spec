# Source-only inventory: pack 2

Reviewer: AI source-first reviewer `source_inventory_2`. Read all 16 windows (26,771 characters) before seeing any extraction output. No output, reveal pack, cache, or model call was inspected. This is an auditable AI reading, not independent clinician adjudication.

48 complete source-rule units were identified: **40 adjudicable, 8 ambiguous_source**. Four windows have zero target rules and remain in the inventory. These are source counts only; no extraction fidelity judgment has yet been made.

| Window | All source units | Adjudicable | Ambiguous |
|---|---:|---:|---:|
| S2-01 | 0 | 0 | 0 |
| S2-02 | 0 | 0 | 0 |
| S2-03 | 13 | 10 | 3 |
| S2-04 | 3 | 3 | 0 |
| S2-05 | 2 | 1 | 1 |
| S2-06 | 2 | 2 | 0 |
| S2-07 | 0 | 0 | 0 |
| S2-08 | 4 | 4 | 0 |
| S2-09 | 1 | 1 | 0 |
| S2-10 | 0 | 0 | 0 |
| S2-11 | 2 | 2 | 0 |
| S2-12 | 1 | 1 | 0 |
| S2-13 | 3 | 3 | 0 |
| S2-14 | 4 | 2 | 2 |
| S2-15 | 3 | 2 | 1 |
| S2-16 | 10 | 9 | 1 |

The audit intentionally includes more than the apparent focus disease: e.g. infection, delirium, depression, neurosyphilis and hypothyroidism in the dementia window; CKD in the FGF23 window; both Brugada and ARVC; and all explicitly described electrolyte/neuropathy targets. This inventory does not silently condition its denominator on whatever disease the extractor may later have been asked to focus on.

Segmentation decisions:

- A contiguous clinical phenotype is one nonrigid association set, not a mandatory AND group. Dementia stages retain separate stage scopes. Brugada and ARVC columns each constitute one typical-portrait set; 14 table rows are not 14 independent required criteria. A table comparison must retain alternatives, normal findings and population qualifiers without promoting them to exclusion criteria.
- The dementia clinical criterion remains a whole unit: short-term memory loss AND at least one missing-domain deficit AND per-deficit impairment/decline AND not solely during delirium. Its absent domain prevents a closed executable oracle; the visible connective/necessity direction remains auditable.
- Catatonia-associated-with-other-mental-disorder is one nested whole criterion unit, retaining the mental-disorder scope, marked psychomotor disturbance, at-least-three-of-twelve requirement and medical-cause exclusions. Only four tail features are visible. No absent members are supplied from medical knowledge, and visible leaves are not double counted.
- Spinal infection suspicion is kept at whole nested conditional level. Two independent named targets (vertebral osteomyelitis and discitis) are recorded separately. The ambiguous lab wording “CRP, WBC, and or ESR” is not silently resolved into all-of or any-of. This is suspicion/evaluation support, never definitive confirmation. Possible bony erosion/instability are separately asserted structural manifestations.
- Named image panels without accessible image observations (S2-07) are not fabricated into feature criteria. MRI/CT order recommendations, treatments, recurrence prevention, surgical complication rates, pure mechanism and mortality/prognosis are documented in `non_target_source` instead of becoming diagnostic predicates.
- Pure named-disease lists are not always target rules: a figure caption listing diseases provides no observable predicate. By contrast, an explicit sentence naming treatable causes of cognitive impairment asserts a causal clinical association and is inventoried. A workup instruction alone is non-target; a full conditional that raises suspicion of a named diagnosis is weak diagnostic support and is retained.
- Repeated Kaposi introduction and multiple studies of the same explicitly summarized psoriasis comorbidity association are not multiplied into duplicate source-rule units. Case-specific Meckel captions corroborate/illustrate the generalized morphology; their ages and appendix-visibility outcomes are not universal population-level criteria.
- Broad nonrigid sets can be covered by several faithful atomic feature assertions; their leaves do not need a synthetic hard group. A rigid criterion, however, requires faithful joint condition and effect. `flat_schema` refers to the legacy raw schema, not whether the execution engine actually obeys it. The inspected schema supports atomic relation/polarity/modality/threshold/context and flat all/any/at_least_n grouping, but not nested children, group-level effect, NOT nodes, or quantified domains. Accordingly flat homogeneous representation is not automatically marked impossible.

Eight source ambiguities: S2-03 detached comparison fragment, missing dementia criterion domain, and missing vitamin-B subtype; S2-05 absent Alzheimer criterion domain referenced by an explicit non-exclusion caveat; S2-14 ambiguous laboratory connective for each of two infection targets; S2-15 incomplete 12-member catatonia domain; S2-16 truncated upper-motor-neuron comparator. A truncated cross-reference alone does not make a completed assertion ambiguous: the medication-to-catatonia causal statement remains adjudicable.

All anchors in the JSON were verified as exact substrings of their corresponding source windows. No output correspondence is included before parent-managed hash freezing/reveal authorization.
