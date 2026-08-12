# E2 — Blinded clinical completeness and reference-identifiability audit

## Bottom line

E2 rejects the idea that one legacy correctness flag can stand in for the
clinical object produced by a system.  In the design-weighted 800-case
mechanism universe, only 55.82% of benchmark references were uniquely
identifiable at their full recorded specificity.  Across the nine full-domain
arms, strict correctness ranged from 18.76% to 25.98%, full clinical
equivalence from 11.08% to 16.16%, and the deliberately permissive
complete-or-partial endpoint from 44.60% to 50.63%.  These endpoints rank the
systems differently.

No predefined arm contrast survives Holm correction across the 30
contrast/scope tests per endpoint.  The correct conclusion is therefore not a
new universal winner.  The durable finding is mechanistic:

1. Forest and IMPC obtain many strict wins with broad disease-family labels;
   those labels are usually clinically related, but often omit reference-
   defining etiology, anatomy, state, stage, or composite components.
2. Collapse3c preserves more complete composite/specific objects and leads the
   full-equivalence ranking, despite ranking eighth on strict correctness.
3. E7 produces more exact high-specificity successes than v0, but also retains
   substantial catastrophic or conflicting outputs, so its complete gain does
   not become a reliable accepted-rate advantage over the other systems.
4. The legacy task projection both rescues clinically valid aliases/parents and
   accepts wrong manifestations, differentials, histologies, or etiologies.
5. Heterogeneous LLM agreement is useful for finding records to inspect, but is
   not a safe endpoint.  Exhaustive root review changed 73/1,070 initially
   unreviewed accepted boundaries, predominantly removing false partials.

`complete_equivalent` is the appropriate endpoint for reproducing the full
benchmark object.  `complete + partial` is a secondary coverage/utility bound;
it must not be described as full diagnostic correctness.

## Design and estimand

The cohort was frozen before online review.  It contains 400 sampled cases,
200 DiagnosisArena (DA) and 200 MedCaseReasoning (MCR), with exact design
weights back to the existing 800-case mechanism universe (400 per family).
The selection retained all 69 known mapper-harm cases and all 37 primary
stable-exclusive cases, then filled frozen strata for mapper rescue,
all-method strict failure, composite/subtype, and background cases.

For every case, a neutral registry deduplicated all observed pre-mapper arm
answers.  Review payloads contained only the vignette, benchmark reference,
and neutral candidate IDs.  They excluded arm identity, method family,
strict/task correctness, mapper status, sampling stratum, and stable win/loss
status.

The analysis separates three objects:

- **reference identifiability**: whether the record uniquely supports every
  qualifier in the benchmark reference;
- **candidate-reference relation**: complete equivalent, partial parent or
  component, conflicting scope/subtype, manifestation/related, not equivalent,
  or uncertain;
- **task projection**: whether the legacy benchmark mapper/judge marks that
  surface output correct.

The relation question concerns candidate versus reference.  The vignette is
used to resolve whether added or missing specificity is compatible; mere
plausibility as a differential is not equivalence.

## Review and root-ownership protocol

Gemini 2.5 Flash and DeepSeek v4 Flash were the two pre-frozen method-blind
subcontractors.  Gemini returned 396/400 schema-valid cases; four malformed
`case_quality_flags` records failed closed.  DeepSeek returned 400/400 valid
cases.  Every reviewer failure, identity disagreement, accepted-boundary
disagreement, non-identity consensus-complete record, and frozen calibration
record entered the primary root queue: 243 identity decisions and 537 relation
decisions.

Sparse calibration then failed a falsification check.  Outside the primary
queue, both reviewers labelled `IgA nephropathy -> Tuberculosis`, `Miliary
tuberculosis`, and `Pulmonary tuberculosis` as partial matches.  The original
30-record consensus-partial calibration happened to contain 30 valid partials
and missed these obvious errors.  The original queue and hashes were preserved;
a supplemental method-blind queue froze every remaining non-exact relation:

`1,673 total = 537 primary root + 1,070 supplemental root + 66 frozen exact`.

GPT-4.1 was added only after this failure as a third, method-blind,
high-recall counterargument source.  It completed 400/400 cases, but did not
vote or overwrite decisions.  The root auditor reviewed all 1,070 supplemental
cards and owns the final classifications.  The full audit trail is in
`root_audit/ROOT_SWEEP_AUDIT.md`; all 73 endpoint-changing decisions have
explicit mechanism tags in
`root_audit/consensus_sweep_endpoint_corrections.jsonl`.

## Runtime and network provenance

All three review arms used non-RAG concurrency 50 without a process storm.
The managed environment's dynamic network route
(`TREE_DX_PROXY_MODE=environment`) reached OpenRouter without the repository's
VPN/Clash path.  Gemini completed through the actual Google provider without a
region-unsupported or datacenter-IP error.  GPT-4.1 completed 400 semantic and
400 physical calls with HTTP 200 throughout (399 OpenAI and one Azure provider
association).  The minimal environment lacked the official `openai` package,
so calls used the repository's audited standard-library fallback.  The same
client retains the environment-controlled official OpenAI SDK path via
`TREE_DX_LLM_TRANSPORT=openai`; this adaptation is not hard-wired to the
current container.

## Reference identifiability is part of the benchmark difficulty

The resolved identity endpoint (243 blinded root decisions plus 157 unchanged
heterogeneous-reviewer consensuses) yielded 230 unique-full, 96 family-only,
and 74 unsupported-specificity cases in the 400-case sample.

| Slice | Weighted target | Full reference uniquely identifiable |
|---|---:|---:|
| Overall | 800 | 55.82% |
| DA | 400 | 62.36% |
| MCR | 400 | 49.28% |
| All-method strict failure | 256 | 25.80% |
| Mapper rescue | 328 | 68.70% |
| Mapper harm | 69 | 57.97% |
| Stable exclusive | 37 | 78.38% |
| Background | 96 | 78.57% |
| Composite/subtype | 14 | 76.79% |

The all-method-failure stratum is not merely a collection of hard-but-valid
questions: almost three quarters of its weighted mass does not uniquely
support the full reference.  Conversely, stable-exclusive cases usually do
support the target, making them more informative for mechanism attribution.
Any aggregate score that ignores this difference mixes system failure with
reference over-specificity.

Ambiguity does not make arm choice irrelevant.  Of 400 cases, 187 (46.75%) had
mixed accepted/non-accepted outcomes across the nine core arms.  Mixed outcomes
occurred in 109/230 unique-full and 78/170 non-unique-full cases.  Non-unique
cases were much more often universally missed (69/170) than unique-full cases
(30/230), but they still contained substantial system-dependent variation.

## Full-domain arm results

Rates below are design-weighted to 800 cases.  `Accepted` means complete or a
compatible parent/component; it is not full equivalence.

| Arm | Strict | Task | Complete | Accepted |
|---|---:|---:|---:|---:|
| Collapse3c | 20.59% | 46.88% | **16.16%** | **50.63%** |
| Multistance | 21.50% | 43.70% | 14.83% | 49.21% |
| Lite | 22.22% | 42.11% | 12.29% | 47.73% |
| Forest | 25.67% | 43.56% | 12.48% | 48.98% |
| IMPC | **25.98%** | 43.84% | 12.45% | 48.41% |
| E7 | 20.85% | 41.99% | 14.29% | 46.72% |
| v0 | 18.76% | 38.95% | 11.08% | 44.60% |
| B06 | 22.48% | 44.13% | 12.92% | 49.04% |
| B07 | 20.92% | 42.96% | 12.19% | 49.93% |

The three rankings answer different questions:

- **Forest/IMPC strict advantage:** both prefer stable, common labels that the
  legacy chain recognises.  Strict-positive output is almost always at least a
  clinically compatible parent, but often not the full object.
- **Collapse3c complete advantage:** its outputs more often retain causal,
  anatomical, stage, temporal, or multi-component qualifiers.  Its lower
  strict score is partly caused by surface aliases the strict bridge misses.
- **B07 accepted/complete split:** B07 is second on accepted but eighth on
  complete.  It often lands inside the correct disease family without retaining
  the full reference scope.
- **E7 versus v0:** E7 moves from 11.08% to 14.29% complete (+3.20 pp), with a
  95% bootstrap interval of +1.29 to +5.26 pp.  The unadjusted McNemar p is
  .0072, but Holm q across the 30 complete contrasts/scopes is .209.  This is a
  useful mechanism signal, not a confirmatory win.

## DA and MCR expose different specificity regimes

| Arm | DA complete | DA accepted | MCR complete | MCR accepted |
|---|---:|---:|---:|---:|
| Collapse3c | 5.10% | 59.84% | **27.22%** | 41.43% |
| Multistance | 5.10% | 58.18% | 24.56% | 40.25% |
| Lite | 2.85% | 57.55% | 21.72% | 37.90% |
| Forest | 1.96% | 56.36% | 23.00% | 41.59% |
| IMPC | 2.62% | 58.10% | 22.27% | 38.72% |
| E7 | 4.32% | 55.96% | 24.25% | 37.48% |
| v0 | 1.55% | 51.36% | 20.61% | 37.83% |
| B06 | 1.47% | 56.12% | 24.36% | **41.97%** |
| B07 | 2.50% | 58.20% | 21.88% | 41.65% |

DA has higher reference identifiability than MCR, yet vastly lower complete
rates and higher partial acceptance.  This is not paradoxical: DA references
often encode a long composite/subtype object, while systems emit a clinically
relevant family, manifestation, or one component.  MCR references are less
often uniquely compelled by the abbreviated record, but surface answers more
often reproduce the reference label.  Identifiability and output completeness
are separate axes and must not be collapsed.

## Metric projection: what strict and task correctness are doing

Strict correctness is high precision but low recall for the permissive accepted
endpoint.  Across core arms, only zero to two sampled strict-positive cases per
arm were clinically non-accepted, but 83–116 sampled strict-negative cases per
arm were nevertheless complete or partial.  It is much less faithful to full
equivalence:

- strict-positive but not complete contributes 10.95%–16.87% of weighted mass;
- strict-negative but complete contributes 3.34%–6.52%;
- therefore IMPC's strict lead coexists with its 13.53 pp strict-minus-complete
  gap, while Collapse3c's gap is only 4.43 pp.

The task mapper is neither purely permissive nor purely conservative.  For the
nine core arms:

- task-negative but clinically accepted: 10.10%–13.16% of weighted mass;
- task-positive but clinically non-accepted: 5.37%–7.33%;
- accepted minus task rate: +3.75 to +6.96 pp.

Examples show both directions.

- **False task rejection / alias loss:** `Peeling skin disease` versus
  `CDSN-related peeling skin syndrome`, `Starvation colitis` versus
  `Hunger Strike-Related Colitis`, and `Caruncular melanoma` versus `Malignant
  melanoma of the caruncle` are root-complete despite failed strict/task
  projection.
- **False task acceptance / wrong object:** `Cutaneous Bacillus cereus
  infection with bacteremia -> Cutaneous anthrax`, `Dual AV nonreentrant
  tachycardia -> Infective endocarditis`, and `community-acquired MRSA sepsis
  with septic vasculopathy -> Purpura fulminans` were task-positive but are a
  different disease or a manifestation.
- **Strict match but missing scope:** `Recurrent infiltrative basal cell
  carcinoma -> Basal cell carcinoma`, `Unilesional folliculotropic mycosis
  fungoides -> Mycosis fungoides`, and `severe generalized RDEB with revertant
  mosaicism -> dystrophic epidermolysis bullosa` are compatible parents, not
  complete objects.

Thus the mapper explains some apparent chain gains and losses, but it is not
the sole problem.  Even strict correctness routinely erases clinically material
qualifiers.

## Exhaustive correction changed systems differentially

Had the initially unaudited A/B consensus been retained, accepted rates would
have been inflated as follows:

| Arm | Sparse-consensus accepted | Root-complete accepted | Correction |
|---|---:|---:|---:|
| Collapse3c | 52.89% | 50.63% | −2.26 pp |
| Multistance | 52.22% | 49.21% | −3.01 pp |
| Lite | 52.48% | 47.73% | −4.76 pp |
| Forest | 54.84% | 48.98% | **−5.86 pp** |
| IMPC | 53.38% | 48.41% | −4.97 pp |
| E7 | 49.10% | 46.72% | −2.39 pp |
| v0 | 47.01% | 44.60% | −2.41 pp |
| B06 | 53.43% | 49.04% | −4.39 pp |
| B07 | 54.25% | 49.93% | −4.33 pp |

This is differential measurement bias, not a uniform offset.  Reviewers were
especially likely to call broad, polished, or topically related outputs
partial; Forest, Lite, B06, and B07 emitted more such answers and benefited
more from the flawed proxy.  Publishing the sparse result would have turned a
reviewer-style preference into an apparent system advantage.

Of the 73 corrected boundaries, 70 removed acceptance and three restored it.
The dominant false-accept mechanisms were distinct tumor histology (23), a
manifestation substituted for the requested object (16), unrelated entity (8),
nonspecific differential mistaken for a parent (4), and conflicting
hematologic lineage (4).  These are semantic category errors, not minor naming
disagreements.

## Reviewer calibration diagnoses the subcontractor biases

Against full root relations:

| Reviewer | Complete precision | Complete recall | Accepted precision | Accepted recall |
|---|---:|---:|---:|---:|
| Gemini | 60.94% | 83.04% | 74.82% | 97.57% |
| DeepSeek | 67.70% | 89.47% | 79.66% | 96.35% |
| GPT-4.1 post-freeze | 79.26% | 62.57% | 68.18% | 97.57% |

Gemini and DeepSeek over-call complete and partial; GPT is more conservative
on complete but still over-calls partial.  Their errors are correlated around
the ontology boundary between a parent/component and a merely related entity.
Adding a third family increases counterexample recall but does not make
majority vote trustworthy.

Reference-identifiability review has a different bias.  Unique-full precision
is high (Gemini 92.35%, DeepSeek 96.36%, GPT 92.62%), but recall is 73.48%,
69.13%, and 49.13%, respectively.  Models tend to find a reason to withhold
full identifiability; root review is necessary to distinguish legitimate
missing specificity from generic caution.

## Case-trajectory mechanisms behind arm differences

### Collapse3c versus Forest: specificity retention versus stable parents

The overall complete delta is Forest minus Collapse3c = −3.68 pp (95% bootstrap
CI −6.20 to −1.19; unadjusted p=.0051; Holm q=.153).  The unadjusted signal is
localized to cases where Collapse3c retains the defining object and Forest
backs off or changes subtype:

- `Left ventricular free-wall rupture after MI`: Collapse3c outputs
  `myocardial infarction with cardiac rupture` (complete); Forest outputs
  `myocardial infarction` (partial).
- `Drug-induced dermatomyositis secondary to ipilimumab`: Collapse3c outputs
  `ipilimumab-induced dermatomyositis` (complete); Forest outputs
  `dermatomyositis` (partial).
- `Ostium secundum ASD`: Collapse3c retains `secundum`; Forest emits generic
  `atrial septal defect`.
- `Hepatic cystadenoma`: Collapse3c emits `biliary mucinous cystadenoma`;
  Forest emits the distinct IPMN entity.
- `Hereditary hypophosphatemic rickets with hypercalciuria`: Collapse3c retains
  hypercalciuria; Forest asserts incompatible X-linked hypophosphatemia.

Forest's strict advantage comes from the opposite preference.  It often emits
the common task-recognised parent—`stroke`, `leprosy`, `lichen planus`,
`asthma`, `myocardial infarction`—where Collapse3c emits a less canonical
component or subtype.  Those outputs are usually accepted parents, which is
why Forest's strict advantage does not become an accepted advantage.

### E7 versus v0: exact recovery with residual catastrophic tails

E7 converts several v0 parents or wrong differentials into complete objects:
`Surfer's myelopathy`, `scar endometriosis`, `familial cerebral cavernous
malformations`, `myopericarditis`, `epidermolysis bullosa pruriginosa`,
`plexiform schwannoma`, and `tumor-induced osteomalacia`.  This is consistent
with a more discriminative selector/representation path.

But E7 also produces unrelated high-specificity labels in other cases.  For
example, B07 retains partial correct components for SLE + IgA nephropathy +
rapidly progressive glomerulonephritis, while E7 asserts the conflicting
etiology `lupus nephritis`; for starvation colitis, B07 is complete while E7
outputs infectious colitis.  E7's benefit is therefore precision of a subset,
not uniform safety.

### B06 versus B07: complete specificity versus family coverage

B06 has higher strict and complete rates; B07 has higher accepted rate.  B07
often chooses a broader but compatible family/component—`catatonia`,
`Neisseria species bacteremia`, `drug-induced pneumonitis`, `breast cancer`,
or `ATAD3A-related disorder`—while the alternative arm sometimes supplies a
more specific object.  The B07 design therefore appears to trade exact scope
for a softer landing in the correct family.  The differences are small and
non-significant, so this is a trajectory mechanism, not a population ranking.

## Statistical interpretation

Ten arm contrasts were declared in the offline mechanism analysis, each in
ALL/DA/MCR scopes and four endpoints.  Holm correction is applied over 30 rows
within each endpoint.  No contrast has q<.05.

Several bootstrap intervals exclude zero before multiplicity correction:

- Forest versus E7 strict: +4.81 pp, CI +1.48 to +8.17, q=.0788;
- Forest versus Collapse3c strict: +5.08 pp, CI +1.68 to +8.53, q=.142;
- Forest versus Collapse3c complete: −3.68 pp, CI −6.20 to −1.19, q=.153;
- E7 versus v0 complete: +3.20 pp, CI +1.29 to +5.26, q=.209.

These are coherent with the audited case mechanisms, but they remain
exploratory under the declared family.  Accepted-rate contrasts are especially
weak: the full-domain spread is only 6.03 pp, all overall accepted CIs include
zero, and every accepted Holm q is 1.0.

## Threats to validity and critical limits

1. **Development target:** weights recover the existing 800 mechanism cases,
   not a new external population.  E2 diagnoses existing evidence; it is not
   confirmation-set generalisation.
2. **Post-falsification supplement:** exhaustive review fixes a demonstrated
   measurement error, but the supplemental scope was triggered by an observed
   failure.  It is corrective, not preregistered confirmatory evidence.
3. **Root judgment remains judgment:** complete manual coverage removes proxy
   consensus as a hidden endpoint, but does not create an infallible ontology.
   Fine relation categories can still be debated.  Endpoint-changing records
   are exposed for audit rather than hidden in aggregate metrics.
4. **Permissive accepted endpoint:** a correct parent or one composite component
   may be useful clinically, but is not the requested full diagnosis.  Ranking
   primarily by accepted would reward under-specification.
5. **Reference identifiability:** relation-to-reference can be complete even
   when the record does not uniquely establish that reference.  Such a result
   measures reproduction of the benchmark object, not independent diagnostic
   justification.
6. **Historical outputs:** the arms were not freshly rerun under a unified
   provider/retry stack—explicitly excluded as a variance-only exercise.  E2
   adjudicates their frozen outputs and cannot attribute differences to runtime
   randomness.

## Consequences for architecture evaluation

- Report strict, task, complete, and partial separately.  Never collapse them
  into one headline accuracy.
- Treat full-reference identifiability as a mandatory audit dimension,
  especially for all-method failures and long composite references.
- Use safe exact identity only as a deterministic shortcut.  Parent/component
  relations require direction, object type, and scope; LLM consensus is not a
  replacement for this contract.
- Optimise selectors against complete object retention, not merely stable
  disease-family selection.  Forest/IMPC's stable-parent behavior and
  Collapse3c's specificity retention are complementary strengths.
- Preserve candidate provenance through the mapper.  A task rescue can be a
  legitimate alias, a broad parent, or a wrong differential; those mechanisms
  have opposite scientific meaning.

## Reproducibility map

- frozen design: `design/selection.jsonl`, `design/blinded_cards.jsonl`;
- reviewer artifacts: `reviewer_a/`, `reviewer_b/`, `reviewer_c/`;
- primary root queue: `root_audit/identity_*`, `root_audit/relation_*`;
- supplemental queue: `root_audit/consensus_sweep_*`;
- complete decisions: `e2_root_decisions.py`,
  `e2_root_consensus_decisions.py`;
- root endpoints: `root_audit/analysis.json`,
  `root_audit/resolved_relations.jsonl`;
- transition decomposition: `root_audit/mechanism_analysis.json`,
  `root_audit/case_trajectories.jsonl`;
- immutable raw root bundle: `E2_ROOT_AUDIT_RAW.tar.gz` and SHA-256 sidecar.
