# Deterministic/template base graph quality audit

## Decision

**No-go for publication or use as a clinical diagnostic assertion graph in its current form.**

The source/provenance layer is mechanically strong, but the clinical assertion layer is not. In the 72-record primary audit, all 72 evidence offsets reproduced exactly, while only 39/72 records retained their intended core relation and only 5/72 were publishable without a material correction. The dominant failures are systematic rather than isolated: stale or navigational Merck target context, a smaller set of WikEM link-to-concept and navigation errors, ontology/sense errors, and complete loss of non-atomic template logic.

The graph may be retained as an **internal authoring ledger** after its assertions are marked unreviewed. It must not be presented as a validated diagnostic KG, used as ranking evidence, or treated as an oracle until the P0 repairs and a fresh blinded audit pass.

## Audited object and graph census

- Input: `/tmp/gkg-build-all-clean-v2/graph.internal.jsonl`
- Total records: 95,041
- `DiagnosticAssertion`: 3,569
- Source-family composition of assertions:
  - WikEM: 3,211
  - Merck: 346
  - CPG: 12
- Extraction lanes:
  - `structural_wikem`: 3,211
  - deterministic template: 358
- Roles:
  - `compatible`: 3,211
  - `supporting`: 228
  - `typical`: 72
  - `necessary`: 58
- `LogicExpression`: **0**. Every one of the 3,569 assertions is represented as atomic.
- Template logic flags:
  - `atomic_surface`: 332
  - `requires_residual_review`: 26
- Every WikEM record is already marked `relation=listed_differential_for`, `enumeration_only=true`, and `ranking_eligible=false`. This is an explicit non-ranking membership contract and was honored in adjudication; these records were not judged as diagnostic criteria.

## Sampling and adjudication

The frozen, deterministic audit sample contains 72 assertions:

- CPG: all 12 assertions, a census rather than a sample.
- Merck: 36 assertions. One was selected from every observed `diagnostic_role × feature_type` stratum, then a SHA-256 seeded fill (`20260825`) preferred distinct passages.
- WikEM: 24 SHA-256 seeded distinct passages, with one assertion selected per passage. These were adjudicated as the explicitly declared non-ranking membership relation (`listed_differential_for`), not as diagnostic criteria.

Three additional records selected by the proposed high-precision template rule were reviewed as a complete filter-output supplement. They are included in the companion JSONL but not in the 72-record primary precision denominator.

Coverage included all graph roles, all feature types represented in the CPG/Merck assertions, three source families, and 72 distinct assertion decisions. Non-atomic logic could not be sampled as a graph type because the graph contains none; instead, the source evidence was checked for lost conjunction, negation, contrast, threshold, and temporality.

Each record was manually traced through:

`DiagnosticAssertion → DiagnosisExpression → Concept → criterion → EvidenceSpan → Passage → Section → DocumentVersion → SourceWork`

The checks were:

1. target identity, granularity, and concept kind;
2. whether the cited finding is genuinely diagnostic rather than treatment, pathobiology, navigation, bibliography, or an unrelated list;
3. direction, role, and necessity;
4. negation, temporality, thresholds, and Boolean structure;
5. exact half-open evidence offsets and quote equality;
6. source-heading drift, navigation contamination, and ontology over-merge.

Verdicts:

- `pass`: publishable without a material semantic correction;
- `minor_error`: target–finding core remains usable, but metadata, logic, scope, or evidence granularity requires repair;
- `fail`: target, relation, diagnostic relevance, or provenance context is materially wrong.

## Precision results

| Endpoint | Correct / reviewed | Precision | Wilson 95% CI |
|---|---:|---:|---:|
| Strict publishable assertion (`pass`) | 5 / 72 | 6.9% | 3.0–15.2% |
| Intended core relation retained (`pass + minor_error`) | 39 / 72 | 54.2% | 42.7–65.2% |
| Exact evidence offset/quote | 72 / 72 | 100.0% | 94.9–100.0% |
| CPG usable core | 8 / 12 | 66.7% | 39.1–86.2% |
| Merck usable core | 11 / 36 | 30.6% | 18.0–46.9% |
| WikEM membership core | 20 / 24 | 83.3% | 64.1–93.3% |

Verdict counts in the primary audit were 5 `pass`, 34 `minor_error`, and 33 `fail`.

These Wilson intervals describe the audited items. They are **not graph-population confidence intervals**, because rare Merck strata were deliberately oversampled and WikEM passages rather than individual edges were sampled. A deployable graph-wide estimate requires a probability sample with design weights.

## Findings

### 1. Exact citation integrity is high but does not imply semantic precision

All 72 spans reproduced exactly from their stored passages. The evidence ledger therefore solves byte-level traceability. It does not solve whether the quote belongs to the stored target, whether the statement is diagnostic, or whether its logical scope survived extraction.

This distinction is decisive: the graph can be perfectly citable and still clinically wrong.

### 2. Merck target binding is the most severe template failure

Merck produced only 11/36 clinically usable core relations. Of 36 audited assertions:

- 18 had a navigational or sentence-like target;
- 2 had target-context lag, where the evidence concerned a later disease than the inherited entry context;
- additional records had wrong target granularity, unresolved pronouns, or a concept mismatch.

The failure occurs upstream of role classification. All 8 audited Merck `necessary` assertions failed because the quoted diagnostic requirement was attached to the wrong target. Thus the lexical rule that recognizes “requires” may be locally correct while the resulting graph edge is unusable.

The concrete mechanism is old chunk metadata acting as a hard disease anchor even when the chunk has crossed into another subsection or when `entry_title` is a sentence/list heading. Representative failed assertion IDs include:

- `gkg_assertion_88ad2a4fe378ab3e63fe`
- `gkg_assertion_d836bbb2beaf87c7bc81`
- `gkg_assertion_ff3da15f608bb36ed33f`
- `gkg_assertion_92ea54cd129810fd2438`

### 3. WikEM must be evaluated as non-ranking membership, not as a criterion

The existing qualifiers correctly declare WikEM records as `relation=listed_differential_for`, `enumeration_only=true`, and `ranking_eligible=false`. Under that intended contract, 20/24 audited records retained a valid source membership. The four failures were a navigation list or an incorrect link-to-concept normalization, not absence of a diagnostic criterion. Non-disease members such as exposures, medications, or phenotype headings are not errors in a heterogeneous differential list, although their concept kind must not be forced to `disease`.

Across the complete graph, 3,211 WikEM assertions reuse only 300 evidence spans:

- median assertions per span: 7;
- 95th percentile: 29;
- maximum: 50.

The source text is therefore exact but insufficiently local to a single target. Consumers must honor the existing membership qualifiers and must not reinterpret the synthetic presentation field as a necessary, sufficient, or ranked diagnostic criterion. Item-local provenance would still materially improve auditability.

Representative navigation/sense failures include:

- `gkg_assertion_23a54b6510994aa70a6f`
- `gkg_assertion_d33a6a877b9b156f51e5`
- `gkg_assertion_efe33f176375cdef487d`
- `gkg_assertion_9eff7b0fc725542b7ac0`

### 4. CPG extraction is better at target binding but still not release-ready

Eight of twelve CPG records retained a usable core. The four failures included acronym sense confusion, a related-but-wrong target concept, bibliography extraction, and a non-diagnostic pathobiology statement.

The usable records still frequently flattened contrasts, conjunctions, negation, thresholds, or time constraints into one atomic surface. One statement contained criteria for two competing diagnoses in a single criterion; another retained an explicit absence only as text rather than polarity/logic.

### 5. Logic preservation has effectively failed in the template assertion lane

The graph contains no `LogicExpression` at all. WikEM membership records do not require Boolean diagnostic criteria, but sampled CPG/Merck template statements contained:

- conjunctions and multi-feature clusters;
- explicit absence;
- duration thresholds;
- temporal constraints;
- a contrast between two diagnoses.

Eight sampled assertions received `LOGIC_FLATTENED`, with additional specific threshold, negation, or temporality errors. The 26 graph records already tagged `requires_residual_review` were nevertheless emitted into the same assertion ledger. “Atomic surface” must not be treated as an acceptable final representation when a scope cue is present.

### 6. Feature-type accuracy is secondary but materially limits graph querying

Eight audited records had a wrong feature type. Examples included clinical history stored as laboratory evidence, pathology stored as `other`, and symptom/sign descriptions stored as `other`. This does not always destroy the core relation, but it prevents reliable modality-aware retrieval and stratified evaluation.

### 7. Literal target locality is a useful risk flag, not a precision metric

Only 49/346 Merck, 5/12 CPG, and 2,374/3,211 WikEM diagnosis labels occur literally in their evidence after simple normalization. Absence is not itself an error because headings, acronyms, and synonyms may supply valid context. However, the 85.8% non-local rate in Merck explains why target resolution is highly dependent on noisy metadata and should trigger a binding gate rather than automatic acceptance.

## Error-code frequency in the 72-record audit

| Error code | Count |
|---|---:|
| `EVIDENCE_SPAN_OVERBROAD` | 24 |
| `TARGET_NAVIGATION_CONTAMINATION` | 18 |
| `LOGIC_FLATTENED` | 8 |
| `FEATURE_TYPE_WRONG` | 8 |
| `TARGET_CONCEPT_MISMATCH` | 8 |
| `TARGET_GRANULARITY_TOO_BROAD` | 5 |
| `UNDERSPECIFIED_DIAGNOSTIC_PROCESS` | 4 |
| `CONCEPT_KIND_ERROR` | 3 |

Less frequent but high-severity errors included reference-list pollution, acronym sense failure, ontology over-merge, unresolved pronoun targets, target-context lag, and a target surface supplied only by link metadata. Error codes are non-exclusive.

## Mechanical high-precision v0.1 export rule

The safest interim product is two explicitly separate, non-ranking views. It is not a validated diagnostic KG. For reproducibility, define `norm(x)` as lowercase, replace each maximal run outside `[a-z0-9]` with one space, then trim.

### A. Template core candidate view

Retain a template assertion only when all of the following are true:

1. `qualifiers.extraction_lane == "template"`;
2. `qualifiers.template_name` is one of `characterized_by`, `diagnosed_by`, or `diagnosis_of_based_on`;
3. `qualifiers.logic_status == "atomic_surface"`;
4. `criterion_id` resolves to a `FeaturePattern` whose `feature_type` is one of `symptom`, `sign`, `laboratory`, `imaging`, `pathology`, `genetics`, `history`, or `procedure` (not `other`);
5. the diagnosis `canonical_label` has 2–10 normalized tokens and is not a generic/pronominal target;
6. the normalized exact `EvidenceSpan.quote` begins with one of:
   - `{target} is/are characterized by`;
   - `{target} is/are characterised by`;
   - `{target} is/are diagnosed by`;
   - `diagnosis of {target} is based on`;
7. the 500 passage characters preceding the span do not match `PubMed|Google Scholar|DOI` case-insensitively;
8. `direction == "supports"`, `diagnostic_role` is `typical` or `supporting`, and `necessity == "not_stated"`.

This rule retains **5/358 template assertions** (1.4%; 0.14% of all assertions):

- `gkg_assertion_7a1aa4f8426f9b40e37e`
- `gkg_assertion_d96b2702a79196775164`
- `gkg_assertion_1728b17849a40a4dfa3d`
- `gkg_assertion_06e3c0dc51903cf48908`
- `gkg_assertion_07293f221f6342fdf2a5`

All five were manually reviewed: 5/5 retained the intended core (Wilson 95% CI 56.6–100.0%), but only 2/5 were strict passes; the other three still lost logic, temporality, or feature typing. Therefore even these five must remain `review_status=unreviewed` and be exported with `ranking_eligible=false` until structured-logic review. The other **353 template assertions must be isolated** from the v0.1 assertion view.

### B. WikEM membership view

Retain a WikEM edge only when:

1. the qualifier contract is exactly `extraction_lane=structural_wikem`, `relation=listed_differential_for`, `enumeration_only=true`, and `ranking_eligible=false`;
2. `norm(DiagnosisExpression.canonical_label)` exactly equals `norm(x)` for at least one raw `wiki_links` item in the linked Passage provenance metadata;
3. the linked `Section.section_path`, flattened with spaces, does not match `\b(?:algorithms?|index|contents)\b` case-insensitively.

This retains **2,521/3,211 WikEM membership edges** (78.5%). In the primary sample it retained 18/24, and all 18 retained the intended membership (Wilson 95% CI 82.4–100.0%); the remaining six included all four membership failures. Because this rule was formulated after inspecting the audit sample, that estimate is exploratory and optimistic. It needs a fresh probability sample. All retained records must remain in a separate `membership_view` with `ranking_eligible=false`; their synthetic `FeaturePattern` must never be consumed as a diagnostic feature, and heterogeneous members must not inherit `Concept.kind=disease` by default. The other **690 WikEM edges must be isolated** pending repair.

### Export accounting and fail-closed behavior

The two rules expose 2,526/3,569 records (70.8%): five unreviewed, non-ranking template core candidates and 2,521 non-ranking membership edges. They quarantine 1,043 records (353 template + 690 WikEM). In the audited primary set the combined rules retained 20/20 intended cores (Wilson 95% CI 83.9–100.0%), but this is a post-audit, non-independent estimate and is not a release claim.

Any missing reference, non-exact quote, qualifier mismatch, unrecognized type, target-prefix failure, bibliography/navigation cue, or structured-logic cue must fail closed into quarantine. No record from either view should be promoted to ranking evidence by downstream defaults.

## Required repairs

### P0 — before any release or retrieval experiment

1. **Default-quarantine current `DiagnosticAssertion` records.** Preserve passages and provenance. The mechanical rules above may expose their small, explicitly non-ranking interim views, but neither view is validated knowledge.
2. **Honor and separate WikEM membership.** Route the existing `listed_differential_for`, `enumeration_only=true`, `ranking_eligible=false` contract into a dedicated `DifferentialMembershipAssertion` or equivalent consumer view; cite the individual list item plus its local heading, not the whole list.
3. **Replace chunk-title target binding.** Bind targets only after source-native reassembly, using the nearest valid disease/syndrome heading and an explicit span-to-heading scope interval. Reject sentence-like, treatment-like, list-intro, and pronoun-only headings.
4. **Require a two-signal target gate.** A target must be supported by a local mention/synonym or a validated disease heading in scope. Ontology mapping cannot create the clinical target by itself.
5. **Add concept-kind enforcement.** Substances, exposures, symptoms, navigation pages, and procedures must not be silently materialized as disease concepts.
6. **Block bibliography/navigation sections.** Reference entries, treatment lists, algorithm links, and navigation headings require explicit negative filters.
7. **Make the logic gate fail closed.** Any conjunction, disjunction, negation, threshold, sequence, time cue, or cross-diagnosis contrast must produce structured logic or enter residual review; it must not be published as atomic.
8. **Exclude all `requires_residual_review` records from the base graph** until they pass a second extraction/review lane.

### P1 — precision and usefulness

1. Separate diagnostic features from diagnostic processes such as generic “diagnosis is based on history.”
2. Split rationale or treatment clauses from the diagnostic finding.
3. Add modality/type verification after criterion extraction.
4. Detect duplicated source occurrences before assertion identity is finalized.
5. Preserve exact target-local evidence spans and retain broader context only as non-citable context.

## Verification experiment after repair

1. Freeze the repaired rules and ontology snapshot before sampling.
2. Draw a probability-stratified sample by source family and extraction lane; retain design weights.
3. Review at least 200 assertions per major lane, or power the sample so the Wilson lower bound can exceed the release threshold.
4. Use two blinded clinical reviewers and adjudicate target, diagnostic relevance, direction/necessity, logic, and evidence separately.
5. Report both core-edge precision and strict structured precision; do not combine exact-span validity with semantic validity.
6. Suggested release gates:
   - core semantic precision at least 95%, with Wilson lower bound at least 90%, in every source lane;
   - exact evidence precision 100%;
   - zero unresolved target-context, navigation, concept-kind, or reference-pollution failures;
   - non-atomic logic recall reported on a dedicated challenge set.

## Deliverable hygiene

The companion JSONL contains 72 primary adjudications plus three complete-filter supplement adjudications. It contains only assertion IDs, verdicts, and error codes. This report contains no guideline passages or quoted source prose.
