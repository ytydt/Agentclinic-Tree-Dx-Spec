# Pack 1: source-first inventory notes

Reviewer: `source_inventory_1`, an AI reviewer performing direct source reading; not an independent clinician gold standard. All 16 windows were read in full from `source_only_pack_1.json` before any reveal/output file was read. The inventory was built against the frozen protocol; no LLM API calls, production edits, or Git mutations were made.

The inventory contains **102 source units: 100 adjudicable and 2 ambiguous**. Three zero-rule windows are retained (S1-06, S1-10, S1-14). Counts are source-rule units, not output assertions or individual group members.

| Window | Source units | Ambiguous | Non-target spans/categories |
|---|---:|---:|---:|
| S1-01 | 1 | 0 | 2 |
| S1-02 | 1 | 0 | 9 |
| S1-03 | 6 | 0 | 2 |
| S1-04 | 4 | 0 | 1 |
| S1-05 | 20 | 0 | 4 |
| S1-06 | 0 | 0 | 4 |
| S1-07 | 17 | 0 | 1 |
| S1-08 | 10 | 0 | 4 |
| S1-09 | 5 | 0 | 4 |
| S1-10 | 0 | 0 | 2 |
| S1-11 | 1 | 1 | 0 |
| S1-12 | 1 | 1 | 1 |
| S1-13 | 2 | 0 | 5 |
| S1-14 | 0 | 0 | 1 |
| S1-15 | 9 | 0 | 1 |
| S1-16 | 25 | 0 | 2 |

Segmentation and semantic decisions:

- A distinct named disease with a diagnostic association is a source unit. Thus the congenital-heart classification table and RLQ differential table contribute multiple disease-target units. Repetition of the same disease/category in prose and table does not duplicate a source unit. These are classification or weak differential associations, never proofs from one symptom or mandatory negative conditions.
- Descriptive manifestations sharing a disease target and effect are one `association_set`, not artificially necessary AND criteria. Independent etiologic definitions, risk associations, and distinct diagnostic targets are kept separate. The incidental inherited syndromes in the osteosarcoma window were fully inventoried, including general retinoblastoma's red-reflex assertion separately from hereditary retinoblastoma's profile.
- The entire Alvarado scoring program is **one** source unit. Nausea OR vomiting earns one point, the weighted total controls the effect, <=3 means unlikely, and >=7/4–6 trigger actions. The temperature label contains 37.3 C/99.1 F but no explicit comparator; the inventory preserves this unspecified comparator instead of inventing >= or >. Score action branches are retained as part of the program without becoming additional diagnostic source units.
- S1-12 is one **ambiguous whole major/minor framework**, with a missing combination gate. It contains lesion/Darier, histology, and updated activating-KIT criteria, normal-count exceptions, tissue scope, and historical codon broadening. No invented major+one, major+two, all, or any threshold is allowed. Its individual leaves are not separate source-denominator units.
- S1-11 is an ambiguous unanchored three-item differential list. A reference-like metadata title does not supply a trustworthy missing index condition; the inventory does not infer findings from disease names alone.
- NICE's >=1 symptom AND >=1 risk factor is a **testing eligibility rule**, not a B12 diagnostic rule. Its entire logic is documented under non-target source so an output promoting it to diagnostic sufficiency can be traced as distortion rather than no-source fabrication.
- The IDSA window contains imaging selection, evidence summaries, references and technical performance modifiers. Only the explicit postoperative abscess association is inventoried as a diagnostic-context feature. Modality choice, contrast use and stopping imaging are not disease predicates.
- Source text is the fidelity reference, not asserted medical truth. Examples include source Fabry/glycogen terminology, the acute-GBS four-week progressive phase, the age wording in history-taking, and syndrome spelling. External clinical knowledge did not silently repair any of them.
- S1-13's intracellular ALD pathway is separately marked pure pathogenesis rather than fabricated into a diagnostic assay. The explicit disease identity and genetic etiology remain source rules. DSM numerical codes and normal anatomy remain non-target even though recognizable disease/body labels appear.

Representability labels assess the available raw schema, not the current executor. `variant_of` allows simple subtype/category relations; homogeneous flat ALL is representable if group semantics and a shared relation are retained. Nested patterns, comparative conditional effects and weighted score programs require more than atomic relation plus one group-logic slot. Short context/predicate text can preserve some scoped assertions lexically, without implying the current executor can evaluate their semantics.

Flat-schema inventory counts: {"exact": 74, "lossy": 19, "impossible": 7, "ambiguous": 2}. These labels remain reviewer judgments for a subsequent schema-focused review.

No output-side faithfulness, omission, distortion, or hallucination label has been assigned in phase 1. The source inventory must be hash-frozen before phase 2 disclosure. Source-only text quote anchors were mechanically checked as exact substrings of the actual selected input windows; every window and all consecutive rule IDs were validated.
