# Source-first pack 3 inventory

Reviewer: `source_inventory_3_AI_source_blinded`; this is AI source annotation, not a clinician-validated gold standard. All 16 complete `source_only_pack_3.json` windows were read before reading either extraction arm, any reveal file, or output audit pack. No API calls were made. The exact-quote anchors and sample/window identities are validated by `build_inventory_3.py`; that script reads only the source pack and transcribes the source-first annotations.

There are **74 source units: 71 adjudicable and 3 source-ambiguous**. Two windows, S3-09 and S3-12, have zero target rules and are retained. The list has 16 entries with reading notes and explicit non-target provenance, including every zero-rule window.

| Window | Source units | Source-ambiguous | Main boundary |
|---|---:|---:|---|
| S3-01 | 1 | 0 | FND descriptive fluctuation/stress; neuropathy AND no radiculopathy is treatment eligibility |
| S3-02 | 2 | 0 | EEG interpretive support and non-exclusion; no EEG pattern is supplied |
| S3-03 | 14 | 0 | Bacteremia definition, weak source/pathogen/risk associations, and differential patterns |
| S3-04 | 4 | 0 | Dementia definition/age association and scoped test limitations |
| S3-05 | 4 | 0 | Early/late imaging and calcification favoring tuberculosis; no modality-alone rule |
| S3-06 | 8 | 0 | Histology and markers, including incidental comparator targets |
| S3-07 | 7 | 0 | PH definition plus subtype taxonomy and causal/category scope |
| S3-08 | 11 | 0 | AFX descriptive features, exclusion requirement, comparator stains and exceptions |
| S3-09 | 0 | 0 | Biopsy-known diagnoses trigger referral/treatment; no new diagnostic criteria |
| S3-10 | 3 | 0 | One nonrigid feature set per melanoma, KS and palatal NHL target |
| S3-11 | 1 | 0 | PAH female predominance; endothelin mechanisms and drug response excluded |
| S3-12 | 0 | 0 | Physiology and cellular observations used only to support mechanism |
| S3-13 | 7 | 0 | Definitions, scoped priors and historical reclassification; overlap counted once |
| S3-14 | 8 | 1 | Truncated differentiator, spinal infection patterns and endocarditis counterexample |
| S3-15 | 2 | 0 | Disease-specific transmission context; screening orders excluded |
| S3-16 | 2 | 2 | Flattened gloss/list relationships lack enough hierarchy to adjudicate |

Segmentation and uncertainty decisions:

- A descriptive manifestation or marker set is one nonrigid unit. Its leaves may be covered by multiple faithful atoms; no all-of necessity was inferred from list conjunctions. Two independent disease effects, such as vascular-marker support for vascular tumor and comparative evidence against fibrosarcoma, receive separate units.
- Explicit age/site/exposure associations and diagnostic test limitations count. Population burden statistics, treatment, workup instructions with no interpretable result, pure molecular mechanisms, and bare navigation/entity names do not. The AFX Ras comparison is included because the source explicitly links the study finding to diagnostic differentiation; UV dimers/p53 mutations and FED cytochrome-oxidase observations are excluded where the passage uses them only as mechanism evidence.
- S3-07 is a **classification hierarchy**, not a set of PH diagnostic conjunctions. A condition such as CTD, HIV, hypoxia or chronic renal failure is not thereby sufficient for PH. Category-level taxonomy units are preserved for identity/causal-scope fidelity, and should also be reported separately from operational clinical criterion groups. Plain taxonomy ancestry can be expressed with `variant_of` edges; it is not called impossible merely because it is nested. Causal and conditional subtype structure may still be lossy.
- S3-08’s histologic AFX diagnosis of exclusion is one whole requirement. The competing neoplasms introduced with “including” are an **open domain**; excluding the three named examples is not a sufficient closed-list AFX criterion. Positive nonspecific stains and negative/sparse staining patterns are separate nonrigid evidence sets.
- S3-13’s historical adult subtype frequencies form one scoped descriptive distribution, with duplicated source overlap counted once. MFH reclassification is not an equivalence class making four diseases synonyms. The unfinished GIST phrase is recorded as a nonclaim, not completed from outside knowledge.
- Source ambiguity remains explicit for S3-14’s initial incomplete “bodies” sentence, S3-16’s Vincent-angina gloss, and S3-16’s indentation-free gingival-hyperplasia/drug/leukemia sequence. These will not enter a forced faithful/distorted/omitted denominator.
- `flat_schema` reflects representability using known relation, polarity, modality, numeric/context and flat all/any/at-least-n slots. It does not assume an execution bug makes an otherwise expressible source rule impossible. Some claims about insufficiency/test reliability, relative frequency distributions and causal/branch-dependent scope remain lossy even if their words can be placed into a free-text predicate.

This pack contains no quantitative score criterion. The inventory alone is not a claim about extraction quality; performance labels require the separately authorized reveal/alignment phase. Before that phase, freeze the JSON bytes/hash and keep this source inventory unchanged.
