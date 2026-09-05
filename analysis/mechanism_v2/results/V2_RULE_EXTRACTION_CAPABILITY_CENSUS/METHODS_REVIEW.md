# Independent methods review

Reviewer: `source_inventory_2`, AI analyst. Scope: `build_samples.py`, `aggregate_census.py`, protocol/clarifications, frozen inventories and sample manifests, plus read-only checks of the referenced historical caches. Primary sampling, inventories and judgments were not changed in this review. The root agent is handling the identified code corrections separately.

The dual-denominator design is a substantial improvement over error-enriched case anecdotes. Source-first inventory, preserved zero-rule windows, raw-output grouping, distinct omission and fabrication labels, and paired old/new evaluation on common source units are appropriate. The following boundaries and repairs are necessary to make the resulting numbers interpretable.

## 1. State the finite-population estimand exactly

Observed frames:

| Quantity | Count |
|---|---:|
| Retrieved passage–case–focus job incidences, each v2 arm | 3,927 |
| Unique raw cache jobs, each v2 arm | 3,826 |
| Unique `(source, SHA256(text[:6000]))` windows | 2,736 |
| Source sample windows | 64 |
| Source sample documents | 55 |
| Source sample frozen rule units | 286 |
| New-output atomic units | 32,725 |
| New-output grouped units | 562 |
| Output sample units | 180 |
| Output sample distinct jobs/windows/documents | 173 / 170 / 133 |

The source estimator is a ratio of inverse-probability-weighted **whole rule units in deduplicated delivered text windows**, evaluated under one deterministic canonical existing focus per window. It is not the average over all 3,927 exposure incidences, all 3,826 distinct focus jobs, all unique underlying medical rules, or all guideline documents. Calling it simply the “exposure distribution” risks suggesting repeated events were frequency-weighted; they were not.

Of 2,736 windows, 749 have more than one distinct focus (524 have two, 158 three, 40 four, 13 five, eight six, four seven and two eight). Twenty-three of the 64 sampled windows are multifocus. Selection of `min(new_cache_id)` is predeclared, outcome-independent canonicalization; it does not establish that performance is constant across focus choices. Preserve the current estimator and label it accurately. A later focus-sensitivity study could audit every focus of selected windows, or explicitly probability-sample a focus and include a second-stage estimand/weight. It should not silently replace the current denominator.

The output estimator targets units emitted by the unique new-prompt/v2 raw cache jobs after the declared atomic/group unitization, conditional on having an eligible emitted unit. It therefore cannot measure missing rules or failures that yield no output. It also measures a different distribution from the source estimator: output units are frequency-weighted by how many assertions/groups the chosen jobs emit. The source and output percentages must not be combined into a single four-way partition summing to 100%.

## 2. Sampling and inclusion weights check out

The source strata contain 1,964 StatPearls, 403 PMC OA, 267 textbook, 45 Merck, 45 manifest CPG and 12 WikEM windows, sampled at 24/12/12/6/6/4. The hash ranking uses a declared fixed seed; it is reproducible pseudo-random selection, not selection on observed error or group success. Reviewer workload balancing occurs after selection and does not alter inclusion probabilities.

All 64 source `window_id`s and all 180 output `unit_id`s are unique. Every recorded inverse weight satisfies `weight × inclusion_probability = 1` numerically. Source-first metadata has no sampled disagreement with the selected job’s document. In the full frame, equal-text windows did not merge different document keys or titles. These checks support the current finite frame construction; they do not make each medical rule unique across overlapping neighboring windows.

Output grouped/atomic allocations are intentionally disproportionate. Groups account for only 562/33,287 = 1.6883% of the output-unit frame but 60/180 = 33.33% of the audit sample. Consequently report stratum-specific results next to the population-weighted pooled result. Raw pooling of all 180 reviewed units would greatly over-weight group quality failures; relying only on the weighted pooled result would obscure this clinically important small stratum.

## 3. One real frame-construction bug, with no selected-unit effect

`build_samples.py` originally discarded assertions with missing subject/predicate **before** constructing groups. A group with an invalid member could therefore be presented as a smaller cleaner group, contrary to the whole-group audit principle.

Concrete witness: new cache `e3f34571985a2c4d0deacb3bc932b20ceaa97f15`, raw row 4, has subject Ebstein anomaly, null predicate and `group_id=g1`; its five other members also have g1. The invalid member was recorded in `raw_invalid_rows` but removed from that group’s membership. A separate invalid ungrouped row occurs in cache `30e758186e66de82f70190156db08360bd9d177b`.

Neither cache contributes a unit to the fixed 180-unit output sample. Retaining the bad grouped member and an explicit invalid-member marker repairs the population representation without changing the 562 group count, any selected unit, inclusion weights or current adjudication counts. The root agent has confirmed this targeted correction. Continue to retain the invalid ungrouped row in a separate invalid-object ledger; do not disguise it as a medically adjudicable atom.

A second operational detail should be made explicit: the frame treats textual group-id sentinels `null`, `none`, `n/a` or empty strings as no group. In the current new-output frame, 60 rows across 10 jobs use literal string `null`. This is reasonable intended-null canonicalization, but it is not identical to taking every nonempty raw string as an actual group identifier. Document it as part of unitization instead of calling the frame completely unnormalized raw grouping.

## 4. Source confidence intervals: formula is appropriate for the declared design

The implemented source replicate weight multiplier is

`1 − sqrt(1−f_h) + sqrt(1−f_h) × n_h/(n_h−1) × M_hi`,

where `M_h ~ Multinomial(n_h−1, 1/n_h)`. Its weights sum to the original stratum sample weight in every replicate, and the `sqrt(1−f_h)` factor supplies the finite-population correction. Sampling whole windows preserves dependence among rules in the same window. Every current stratum has at least four sampled windows, so the `n_h−1` denominator is valid. Ratios use replicated adjudicable rule totals, retaining zero-rule windows as sampled clusters. This is a reasonable Rao–Wu rescaled stratified bootstrap for the fixed finite-window estimand.

Reinitializing the random generator identically in the old and new calls means their replicate weights coincide. The resulting new-minus-old bootstrap arrays are correctly paired, provided window ordering and source denominators remain the same. This is intentional pairing, not a random-seed bug. Add an assertion that adjudicability and rule IDs agree between arms, and report the paired point difference along with its CI.

The interval captures finite sampling of source windows. It does not include uncertainty in AI inventory segmentation, semantic adjudication, provider nondeterminism, or generalization to new guidelines/cases. Repeated documents do not by themselves invalidate finite-population SRS-within-source inference: windows are the declared sampling units with fixed outcomes. For superpopulation claims about unseen documents, however, these intervals are insufficient; a document-cluster or hierarchical sensitivity would then be appropriate. Do not mix these two inferential goals.

The code uses percentile rather than studentized bootstrap intervals, with small stratum samples and potentially skewed rule densities. Describe the interval as a design-aligned approximation, not an exact coverage guarantee. Keep unweighted sample counts and per-source results visible.

## 5. Zero observed strict fabrication is not zero uncertainty

Both initial output reviewers found zero `untraceable_fabrication` among their 90 units, and no `unresolved_provenance` units. This means no strict source-free fabrication was observed under the reviewed provenance scope; it does not establish its absence in the 33,287-unit frame or outside it.

The aggregation takes 97.5% Wilson intervals in each of the two strata and population-weights their endpoints. Under two zero-success strata, the approximate bounds are:

| Stratum | Sample | 97.5% Wilson upper bound |
|---|---:|---:|
| Atomic | 120 | 4.0183% |
| Grouped | 60 | 7.7262% |
| Weighted combined upper bound | — | 4.0809% |

Thus the reporting must not stop at “0% hallucinations.” The Bonferroni construction is a sensible cautious approximation, but Wilson coverage is approximate; calling the resulting interval mathematically guaranteed conservative overstates what this implementation proves. Exact binomial Clopper–Pearson bounds (with no FPC, conservative for this setting) or finite-population hypergeometric bounds would be preferable for a strict finite-population coverage guarantee. The source bootstrap alone would collapse to [0,0] at zero successes; correctly, it is not used for this output endpoint.

The output sample contains seven jobs contributing two units and 166 jobs contributing one. Because units were sampled directly within a fixed unit frame rather than sampling jobs first, job-level outcome similarity does not require a cluster correction for this declared finite-population SRS estimand. It does prevent reading the interval as independent-replicate model reliability or cross-document generalization.

The available context file contains same-document windows retrieved in this run, not guaranteed complete documents. Provenance wording should say actual payload plus the available same-document context searched. A missing verbatim quote, wrong subject, unsupported relation, or treatment-to-diagnosis transformation is not automatically strict source-free fabrication; all may have a visible ancestor. If future adjudication produces unresolved provenance, show it separately and provide a sensitivity in which unresolved units are potentially fabricated.

## 6. Raw semantic fidelity, contract conformance and clinical ranking require separate denominators

Three distinct performance questions are being measured or discussed:

1. **Source semantic coverage**: faithful / distorted-including-partial / omitted among frozen adjudicable whole source rules, plus source ambiguity.
2. **Output semantic precision and provenance**: faithful / distorted / traceable non-target / untraceable / unresolved among emitted atomic or whole-group units. Add a separate raw-schema conformance measure on the same output sample.
3. **Clinical diagnostic ranking**: gold binding, group execution, hard vetoes, MRR/top-1 over cases. A source rule may be faithful yet irrelevant to the vignette; a malformed output can fail schema admission before causing clinical harm; and a distorted high-weight group may dominate many correctly extracted atoms. Neither of the first two percentages alone is an estimate of clinical ranking accuracy.

The current error-code aggregation has a concrete implementation issue already identified by the root: `set(schema_errors)` fails when reviewer records contain dictionaries. Normalize each error to a stable categorical code while preserving the original detailed records. Merely stringifying each dictionary or each `raw[i]:invalid_kind=...` string would avoid the crash but fragment the counts by evidence-specific text and local raw index. Build a separate canonical code mapping and retain raw evidence. Counts of reviewer code spelling variants should not be advertised as a unified error taxonomy.

Likewise, count semantic fidelity with schema errors separately. `associated_with` may be semantically faithful to an epidemiologic association but violate the declared relation enum. An asserted predicate named “normal AV conduction” is not clinically equivalent to asserting abnormal conduction; canonical polarity instructions may still be violated. Do not label every such contract deviation a clinical polarity reversal without inspecting its predicate semantics and subsequent normalization.

## 7. Whole-rule granularity is consequential; retain the frozen endpoint and add sensitivity

Frozen source counts differ across packs (102, 48, 74, 62) even though character workloads were similar. Their source mixes and clinical density differ, so this difference is not proof of reviewer bias. It does show that source-unit rates cannot be interpreted without the unitization convention. Broad association sets lose complete fidelity if key members/qualifiers are missing; many constituent atoms may still be correct. For example, two long Brugada/ARVC portraits are two source units, whereas short disease-specific causal/definitional statements elsewhere are separate units.

Report at least: complete whole-source fidelity, partial member coverage as a secondary endpoint, and a “substantive contradiction versus incomplete-only representation” breakdown. Without that last separation, “distorted” can be read as every surviving statement being false, which the protocol explicitly does not mean. Do not modify frozen segmentation after observing outputs. A later prespecified sensitivity can split long nonrigid sets into organ/test subunits, keep rigid criteria/score algorithms intact, and recompute both arms together.

A concrete calibration illustrates the issue: initial S2-15-R02 old output was called faithful because its epidemiologic associations all survived, but the source’s explicit “majority of catatonia cases” is present only in quote, not the structured predicate/threshold. Under the same strict policy used for anatomy/time qualifiers, the root’s proposed override to distorted/partial is appropriate. The initial judgment should remain auditable, with the separate override and rationale. This is an adjudication correction, not evidence that the underlying source inventory should be rewritten.

## 8. Historical paired comparison supports localization, not a universal causal prompt claim

All 3,927 v2 job keys have both old/new records, and every paired passage SHA256 agrees. The extraction implementation uses the same model interface at temperature 0; the free-group block is the intended prompt contrast. Common source inventories and paired confidence calculations are therefore substantially better controlled than comparing unrelated runs.

Nevertheless, one realized historical cache per arm cannot identify general model capacity or the sole cause of improvement/regression. Cache keys hash `(kind, payload, model)` but not exact system-prompt text, provider endpoint/revision, generation time, or response status. Different old/free kinds prevent direct old-versus-free cache collisions, but later edits within the same kind are not protected by a prompt-content hash. Future runs should persist exact prompt SHA, payload SHA, model/provider/version metadata, request status and parsed/raw response, and repeated paired runs if estimating stochastic prompt effects.

The client also caches `{}` on exceptions. Across the unique jobs, old has 3,755 nonempty assertion lists, 58 empty assertion lists and 13 bare `{}` records; new has 3,747, 73 and six respectively. The source sample includes empty outputs at S1-10 in both arms, S3-16 new, and S4-13 new. Genuine “nothing assertable,” invalid output and transport/model-call failure cannot be fully separated from a bare cache object. Such source omissions measure the realized extraction pipeline but should not automatically be diagnosed as inability of the language model to understand the rule.

The present audit can establish that specific errors already exist in raw responses and identify source/schema/prompt contracts they violate. It cannot show that one prompt defect uniquely caused every error or that source restoration generally lowers MRR. Explaining MRR requires the separate matched case-level tracing of output admission, duplicate weighting, target binding, group evaluation and hard decisions.

## Prioritized actions

1. Complete the invalid-group-member preservation repair; retain its no-current-sample-impact record.
2. Fix heterogeneous error-record aggregation and map reviewer codes into one taxonomy without deleting evidence.
3. Label source and output estimands exactly; retain strata, counts, ambiguity and zero-fabrication uncertainty.
4. Preserve initial judgments and review overrides; add adjudicability consistency and paired point-delta checks.
5. Separate incomplete-only source representations, genuinely contradicted statements, schema inadmissibility and case-level harm.
6. Treat new focus/provider/case generalization and AST repair experiments as future validation, not as already established by these finite-cache rates.
