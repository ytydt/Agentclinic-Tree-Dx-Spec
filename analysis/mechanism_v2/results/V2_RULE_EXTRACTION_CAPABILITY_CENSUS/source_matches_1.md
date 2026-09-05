# Pack 1: phase-2 source-to-output matching notes

All 102 rules in the **final source-only frozen inventory** were matched against the old/new prompt cache outputs in `source_reveal_pack_1.json`. Rule IDs and source segmentation were not edited after reveal. Root recorded the initial premature-freeze race and final refreeze; the final source-only inventory SHA256 is `258105e00c76e14c6f0678b20688b7ef6ecf1ed672e595f88323c13e8c7a6122`.

`source_matches_1.json` contains one row per frozen source rule and two complete judgments. All raw indices are **zero-based local cache-output assertion indices**. Cache IDs accompany every arm. A raw assertion can be a descendant of two source rules when it fuses their clauses, as with Chagas caused-by T. cruzi plus Chagas cardiac manifestations becoming Chagas caused-by myocarditis. Disease names or quoted content belonging solely to another independent source rule do not count as recovery.

Initial source-side counts (100 adjudicable + 2 ambiguous):

- Old: faithful **10**, distorted **29**, omitted **61**, ambiguous **2**.
- New: faithful **11**, distorted **31**, omitted **58**, ambiguous **2**.

These are pack-local unweighted counts, not estimates for all windows, documents, diagnoses, or the full guideline library. The full sampling design and other packs determine the population estimates. All named-disease rules are eligible because the actual prompt says to extract every assertion about named diseases, while preferring the focus. Source tables contribute many weak nonfocus relations; this should be kept visible when interpreting omissions rather than changing the denominator after seeing outputs.

| Window | Source units | Old F/D/O/A | New F/D/O/A | Raw assertions old/new |
|---|---:|---:|---:|---:|
| S1-01 | 1 | 0/1/0/0 | 0/1/0/0 | 6 / 6 |
| S1-02 | 1 | 0/0/1/0 | 0/0/1/0 | 7 / 5 |
| S1-03 | 6 | 0/3/3/0 | 0/4/2/0 | 14 / 6 |
| S1-04 | 4 | 1/2/1/0 | 1/2/1/0 | 10 / 6 |
| S1-05 | 20 | 0/5/15/0 | 2/5/13/0 | 9 / 11 |
| S1-06 | 0 | 0/0/0/0 | 0/0/0/0 | 6 / 16 |
| S1-07 | 17 | 6/2/9/0 | 6/2/9/0 | 8 / 8 |
| S1-08 | 10 | 1/4/5/0 | 0/5/5/0 | 14 / 11 |
| S1-09 | 5 | 1/3/1/0 | 1/3/1/0 | 8 / 13 |
| S1-10 | 0 | 0/0/0/0 | 0/0/0/0 | 0 / 0 |
| S1-11 | 1 | 0/0/0/1 | 0/0/0/1 | 3 / 4 |
| S1-12 | 1 | 0/0/0/1 | 0/0/0/1 | 6 / 7 |
| S1-13 | 2 | 1/1/0/0 | 1/1/0/0 | 5 / 4 |
| S1-14 | 0 | 0/0/0/0 | 0/0/0/0 | 8 / 8 |
| S1-15 | 9 | 0/6/3/0 | 0/6/3/0 | 13 / 10 |
| S1-16 | 25 | 0/2/23/0 | 0/2/23/0 | 11 / 11 |

### Reviewer calibration preserved separately

Initial judgments treated unquantified `can/may` promoted to `typical` as a strict strength error. Root identified a reviewer-consistency issue: these statements do not supply measured frequencies, and other reviewers do not automatically reject `typical` on this ground alone. The five affected arm-rule judgments are **explicitly isolated** in `source_strength_review_candidates_1.json` for direct review:

- S1-01-R01, old and new, raw 0–3.
- S1-04-R01, old and new, raw 0–3.
- S1-09-R02, new, raw 5–8.

If all five are treated as faithful under a harmonized semantic convention, old becomes F12/D27/O61/A2 and new F14/D28/O58/A2. The initial matching file is preserved; root calibration overrides must be recorded rather than silently replacing reviewer labels. Other strength errors here co-occur with omissions, scope loss, causal inversion or hardening an explicit limit/action and do not disappear under that sensitivity.

### Paired mechanisms

1. **Source completeness versus effect correctness.** Alvarado S1-16-R25 has all eight item names in both outputs. Old creates an ANY group without weights; new removes the group. Both convert score <=3 from unlikely into obligatory exclusion. Old converts >=7 surgical consultation into sufficiency; new converts it into necessity. Neither has weights, a score-total expression, or the 4–6 consider-CT branch. Eight out of eight recognizable leaves therefore coexist with zero faithful score programs.
2. **Simple ALL failure even where schema can represent it.** Inflammatory cardiomyopathy S1-08-R03 is myocarditis AND ventricular remodeling AND dysfunction. Both outputs retain only myocarditis as a typical feature. This is not a source parsing gap or proof that every error requires a nested AST: the missing other two members are present in one input sentence and a homogeneous ALL could represent the structure.
3. **Improved leaves, still unresolved or wrong grouping.** Cutaneous mastocytosis S1-12 restores a skin-lesion atom with the new prompt but still gives ANY across major/minor/redundant histologic entries. Both negate the predicate normal mast cell counts despite the sentence saying some patients have normal counts. The source gate is incomplete, so the whole rule stays ambiguous while these local literal, tissue-scope and group-membership errors remain directly observable. Old additionally binds Darier sign to the focus Darier disease rather than mastocytosis. Source ambiguity is not permission to invent a gate, and it does not conceal separately decidable local errors.
4. **Full source association set becomes partial.** S1-08-R04 retains all seven inflammatory-cardiomyopathy cause categories with old prompt but only viral infection with new. S1-04-R04 loses the three dermoscopic strawberry-pattern components with new; both lose nonpigmented facial scope. S1-03-R06 decreases from three CIDP course descriptors to one while neither preserves the longer-course comparison.
5. **Causal argument reversal outside groups.** Fabry/HCM/CHF becomes Fabry caused-by hypertrophic cardiomyopathy in new. Chagas caused-by T. cruzi and Chagas commonly causing cardiac manifestations become Chagas caused-by myocarditis in both. Osteosarcoma-predisposing hereditary syndromes become syndrome caused-by osteosarcoma risk. No group representation issue is needed to generate these errors; subject, predicate role and causal direction must be audited independently.
6. **Differential overlap becomes discrimination or exclusion.** Inflammatory-systemic-disease co-occurrences with mononeuritis multiplex are labelled distinguishes_from. DID symptoms that resemble personality disorders become distinguishing features; substance etiologic attribution becomes a negated excludes rule for DID. Old/new changes in relation labels can alter strength without preserving polarity, the conditional cause, or conjunctive scope.
7. **Raw semantic fidelity and schema conformity separate.** New S1-05-R01 faithfully states primitive bone-forming mesenchymal derivation but uses relation and predicate_kind `definition`, outside the declared enums. This is a semantically faithful raw extraction with a compiler/schema compatibility problem; it is not called a hallucination or falsely scored medically distorted solely for the enum.
8. **More output from non-diagnostic input.** S1-06 has zero patient-level diagnostic source rules but 6 old/16 new outputs. S1-14 is a numerical diagnosis-code index with zero source diagnostic rules but 8 outputs per arm. These windows are retained, and their outputs cannot be evaluated by a source-rule denominator of zero. The separate output-side denominator is necessary.

### Non-target-source ancestry

`source_pack_1_non_target_descendants.json` records 15 mechanism notes with full raw assertions and exact cache indices. Examples include testing eligibility -> B12 requirements; imaging selection/question -> CT sufficiency/US exclusion; CT radiation harms -> causes of abscess; comparative lower BCC aggressiveness -> absolute negation; less-frequent need for systemic chemotherapy -> excludes; treatment menus -> expanded feature groups; code labels -> underlying-disease typical features. Each has a visible source ancestor. Whether a treatment feature is ultimately used diagnostically also depends on downstream context enforcement; these notes do not invent a diagnostic harm for every out-of-scope atom.

These notes are **not** an extra probability sample of output rules and are not added to the output-side rate denominator. They ensure that a missing source diagnostic rule is not mistaken for proof of no-source fabrication. No untraceable-fabrication rate is estimated from source pack 1.

### Attribution limits

The raw-cache comparison localizes every listed extraction loss to source-to-raw generation before normalization, gate, candidate binding or execution (evidence B). It does not isolate why a generation failed. `prompt/model cause unisolated` is therefore retained. Explicit missing score weights/branch/group-effect slots give an A-level schema representability limitation; underspecified directional labels, focus preference, and atomic decomposition instructions are C-level causal hypotheses unless a controlled intervention or deterministic witness establishes more. There were no new API calls, no pipeline modifications, and no claim that a one-pair prompt contrast measures model-inherent capacity.

Source-side ambiguous rules are kept outside F/D/O rather than being forced into a desired rate. The review is by AI source readers, not independent clinical specialists. Short quoted fragments, enum failures and quote punctuation mismatch are separately recorded; none alone demonstrates lack of a medical source ancestor.
