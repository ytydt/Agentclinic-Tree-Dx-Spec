# Paired source-rule audit: pack 2

The frozen inventory SHA256 is `039e03c0494fe43d417aa25e21bfe2d45ee710966f60d07c1d2c2773cced2c0a`. It remains unchanged. Reveal was authorized after the parent freeze. The reviewer subsequently read all old/new raw assertion arrays, the source text, `GUIDELINE_PROMPT`, and `FREE_GROUP_BLOCK` in `run_trial_extraction.py`. This is AI adjudication, not a clinical expert panel.

Every one of the 48 frozen source rules has exactly one row in `source_matches_2.json`. `raw_indices` are zero-based indices local to the relevant old/new raw cache, not global assertion numbers. Multi-source descendants may appear in more than one correspondence: the shared malformed dementia group and the Brugada/ARVC negative contrast are explicitly identified rather than assigned opportunistically to only a convenient correct ancestor.

| Unweighted source-unit result | Old prompt/v2 | New prompt/v2 |
|---|---:|---:|
| Faithful | 5 | 4 |
| Distorted, including partial whole-rule representation | 20 | 20 |
| Omitted, no recognizable descendant | 15 | 16 |
| Ambiguous source, excluded from the adjudicable denominator | 8 | 8 |
| Adjudicable denominator | 40 | 40 |

These are pack-level sample counts, not the stratified population estimates. On the adjudicable **whole source-unit** denominator, strict complete fidelity is 12.5% versus 10%, distortion/partial is 50% in both arms, and complete omission is 37.5% versus 40%. This does **not** imply that 87.5–90% of individual emitted atoms are false. One clinical portrait with numerous correct atoms but missing key scope or branches is incomplete at the frozen whole-rule level. Source-side completeness must be distinguished from output-side precision and from source-free fabrication. The eight source ambiguities remain ambiguous in both arms even where additional directly visible output mistakes can be documented.

The only categorical paired flips are:

- **S2-04-R01: distorted → omitted.** The old IPAH output at least preserved “no identifiable disorder” as a weak feature; the new output omits the IPAH defining condition entirely.
- **S2-15-R02: faithful → distorted/partial.** The old catatonia output preserves inpatient context, up-to-35% among people with schizophrenia, and the majority-of-catatonia-cases association with depressive/bipolar disorders. The new output drops the last clause. It is partial set coverage, not complete omission or inversion of the prevalence denominator.

Categorical stability hides major worsening within an already-distorted source unit:

1. **Dementia screening is promoted into a malformed mandatory group (S2-03-R08/R09).** Old raw18 contains a direct numeric defect: source “within 3 to 5 min” becomes `<3` with `value_high=5`. New raw24–26 instead combine short-term memory, category naming, and generic cognitive deficits in `g1`. The first two use `logic=all`; the third uses `at_least_n,n=1`. Category naming is a screening association in source, not a stated mandatory criterion. Source’s true clinical-criterion member domain is missing, so R09 remains `ambiguous_source`; that limitation does not excuse these visible cross-rule grouping errors. The prompt explicitly requires shared logic/n and restricts `required_for` to source necessity. There is no need to invoke downstream normalization to explain this failure: the raw cache already contains it.

2. **A competitor’s normal table row becomes a hard negative (S2-11-R01/R02).** Old output covers a partial but largely recognizable typical Brugada/ARVC portrait. New raw11 takes `Normal` from the ARVC AV-conduction row and emits Brugada `Normal AV conduction / excludes / negated`, while raw12 emits a correct ARVC normal-conduction feature. The same table cell therefore has correct and wrong-target descendants. The source gives typical differential portraits, not categorical exclusions. This also shows why checking one best quote or one correct descendant overestimates fidelity.

3. **An author citation attracts disease identity (S2-06-R01).** The payload focus is Pott’s disease even though the passage discusses phosphate/FGF23 and mentions `Pott et al.` as authors of reference standards. Old output includes an all-null Pott object (raw3), while new raw0 asserts Pott’s disease has elevated FGF23. The FGF23 predicate clearly descends from the CKD sentence; new raw1 correctly attaches the same predicate to CKD. This is source-traceable entity rebinding, **not** source-free fabrication. The raw failure is observed; a causal role for prefer-focus wording is plausible but not isolated by this comparison.

4. **Spinal-infection group membership collapses further (S2-14-R01/R02).** Source has an outer conjunction of a risk-factor OR, atraumatic back/neck pain, and an internally ambiguous inflammatory-laboratory combination. Old groups separately attach an `any` group to discitis and osteomyelitis, already losing the outer conjunction and risk/atrauma scope. New uses one `g1` across both diseases and duplicated lab/pain atoms. Because the underlying lab `and or` is genuinely ambiguous, the source rules remain ambiguous; dropping the explicit outer context and mixing target memberships are nevertheless independently visible errors.

5. **Whole-rule caveats disappear while familiar features survive.** Inattention→delirium loses the advanced-dementia exception, Alzheimer “deviation does not exclude” becomes `clinical criteria / required_for`, and Meckel “can mimic appendicitis/mucocele” becomes `distinguishes_from` with the comparator disease itself as predicate. These are different failures: lost scope, unsupported necessity, and substitution of a differential-membership statement for an actual discriminating finding. None requires absent external source content to trace its origin.

6. **Improved quotations do not guarantee executable structure.** S2-16 new raw5–6 quote the full radial-nerve localization sentences, including site-dependent proximal weakness and dorsal-hand sensory distribution, yet predicates remain generic wrist/finger weakness and sensory loss. Provenance improves while anatomical constraints remain absent from the actual assertion fields. The many other named electrolyte/nerve conditions in that source are still completely omitted; mechanism, workup and treatment assertions about the focus disease do not cover them.

Faithful examples are deliberately retained. The Meckel abdominal-pain/fever/vomiting set can be represented by three weak `feature_of` atoms without an artificial AND group. Psoriasis comorbidity associations are semantically faithful across both arms, although `associated_with` and `comorbidity` violate the declared enums. Kaposi immunosuppression/AIDs/transplant examples can also be weak independent associations; the source does not authorize making each required. Medication→possible catatonia is correctly preserved. These examples limit any conclusion that all atomization is inherently harmful: atomization is appropriate for nonrigid sets when its scope and modality are respected.

Four source windows have zero target criteria and therefore contribute no source-rule rows, but their output is not harmless:

- S2-01 converts “do not offer drugs to prevent recurrence” into `acute diverticulitis / recurrence / excludes / negated` in both arms.
- S2-02 turns an initial MRI order into `sufficient_for` under the old prompt and `required_for/obligatory` under the new; optional CT is sufficient in both, although no test-result criterion is supplied.
- S2-07 generates 14/13 statements from missing-image panel labels, sometimes calling `differential diagnosis` an obligatory feature or a discriminating predicate. Pairwise disease membership is traceable to captions; it is not a supplied imaging finding.
- S2-10 emits surgery-specific SSI incidences as generic disease thresholds; old additionally turns no between-technique difference into `excludes/negated`.

These outputs should be handled in the **output-side** denominator and provenance audit. They must not be added to the source denominator as though the pipeline had discovered true diagnostic criteria, and they must not automatically be called untraceable hallucinations: their treatment, workup, statistical or caption ancestors are visible.

Cause attribution remains bounded. Direct raw-vs-source contradictions and explicit prompt violations are evidence B for where the erroneous representation is already present. Missing AST children/group-level effect/scoped negation/domain completeness is a schema fact (A). Short-predicate design and absent scope preservation checks are plausible contributing prompt/schema factors, not proof that one extra instruction would repair the model. A complete raw omission is localized but its internal cause remains U; it is not diagnosed as model capacity, intentional filtering, or truncation without evidence. The phase did not inspect normalization/gates/execution and does not attribute these raw defects to those later stages.

Enum/JSON conformance and clinical semantics are separately recorded. Normal imaging/biopsy with an asserted *normal* predicate is not automatically a clinical polarity inversion—the predicate itself carries normality—but it does violate the prompt’s requested canonical negated-abnormal form. Quotation length/verbatim deviations, invalid predicate-kind/relation/context enums, null group objects and string numerals are reported in `schema_errors`; those alone do not turn a source-faithful medical statement into fabricated content.

No frozen source segmentation was changed after reveal. A later granularity sensitivity analysis could split long nonrigid portraits into smaller predeclared organ/test subunits, but that would be a separate endpoint; changing the frozen unitization in response to these outputs would contaminate the denominator.
