# Mechanism-v2 experiment register

Baseline commit: `d987daed1c1515141e4ff27f9dc164249d00e001`  
Scope source: `INDEPENDENT_APHHM_C_MOSAIC_DEEP_TRAJECTORY_AUDIT.md` and
`CASE_TRAJECTORY_AUDIT_R1_R6_CRITICAL_SYNTHESIS.md`.

This register merges duplicated proposals but does not discard independent
factors.  The unit of inference is the case; DiagnosisArena (DA) and
MedCaseReasoning (MCR) are always reported separately.  The existing 800 cases
are development/mechanism data, not a new confirmation set.

## Explicit exclusions requested for this execution

- five-fold/full end-to-end replicate programs (synthesis E13);
- expansion to a new confirmation cohort and associated power exercise;
- provider/retry standardisation as an experimental arm;
- any experiment whose sole purpose is reduction of technical variance.

Provider failures, retries, tokens and latency are still logged as provenance.
No excluded control is silently reintroduced as a scientific factor.

## Crosswalk and execution status

| ID | Consolidated experiment | Source proposals merged | LLM required | Status |
|---|---|---|---:|---|
| E0 | Runtime, payload and cost ledger | synthesis E0; independent §12.0 | probe only | implemented |
| E1 | Same-code clean/options × fixed/shuffled-format input | synthesis E1 | yes | complete: 200 cases × 8 arms; option visibility raises paired safe-exact top-1 by 41.0pp hierarchical and 40.2pp flat under fixed format, but the effect is label-copy/format sensitive; the targeted clinical review is not an all-output clinical leaderboard or a full-production APHHM result |
| E2 | Full-800 canonical clinical-endpoint root adjudication + reference identifiability | synthesis E2; independent §12.1 | no new LLM for census completion; historical screens retained as provenance | complete: 800/800-case root census across 9 arms and 7,200 case-arm outputs, replaying safe-exact / legacy-chain / clinical-complete / compatible-partial / complete-or-compatible-partial / task under one contract. Only clinical-complete is the diagnostic-ability primary; the union is secondary coverage sensitivity. 455/800 references are uniquely identifiable at full specificity. No overall ten-contrast Holm result is significant; in the separately frozen MCR ten-contrast family Collapse3c exceeds IMPC by 5.50pp (`q=.045615`), while the DA–MCR interaction is not multiplicity-confirmed (`q=.228489`), so no universal winner is claimed. DA task is an option-mapper interface endpoint; MCR task is a separately calibrated semantic judge and the two are never pooled |
| E3 | Claim ledger and frozen analysis dependencies | synthesis E3 | no | implemented |
| E4 | Fixed-pool selector crossover | synthesis E4; independent E4 | yes | complete: 400 cases × 5 arms; Forest safe-exact +2.0pp vs e7 (9/1, p=.0215), but all safe-exact gain is MCR and 3/9 reviewed gains are surface/scope artifacts; the bounded 17-discordance + 12-case audit does not establish full-cohort clinical-complete superiority, and pairwise adds cost without beating Forest on the frozen endpoint |
| E5 | Candidate-set interference / IIA | synthesis E5; independent E3 | yes | complete: 200 cases × 9 arms; safe-exact sibling −10.91pp (Holm p=.0147), width 8 −16.46pp (Holm p=.000114), and width 6→8 −7.93pp; direct capture dominates MCR while shared-candidate reordering dominates DA; the 339-judgment targeted audit exposes synonym-bridge and component-direction error but is not an all-output clinical score |
| E6 | Raw vs flat facts vs typed relation graph | synthesis E6/E12; independent E2 | yes | complete: 300 selected, 258 builder-valid; the external-screen/root-corrected clinical-complete* sensitivity gives graph vs raw −7.63pp (24/5, p=.00055), with root review of 94 cases/262 outputs and relation errors in 25/30 audited graphs; this falsifies the tested generated graph, not all structured graphs, and is not an E2-cohort clinical rate |
| E6x | Remove flat sentinel padding without changing facts | newly exposed by E6 tokenizer telemetry; absent from both source audits | yes | complete: removing padding cuts mean input tokens 64.9% but changes the arm-blind-screen/root-corrected complete-proxy sensitivity only +1.57pp (7/11, p=.481) and complete-or-compatible-partial proxy −3.53pp (19/10, p=.136); root review covers 63 cases/126 judgments, so padding is a cost confound without an established whole-cohort or fully blinded clinical effect |
| E7 | Substring vs exact-synonym vs typed registry | synthesis E7; independent E1 | selector replay | complete: E7a offline replay + E7b 400-case fresh blinded selector; all arms use one displayed-label safe-exact endpoint. `legacy_substring` names a registry treatment, not the historical legacy-chain scoring endpoint; the frozen 40-case clinical queue supports mechanism attribution only, while exact identity restores safe-exact exposure and a generic relation edge adds no safe-exact top-1 benefit |
| E7c | Directional clinical relation + bounded evidence inheritance after safe identity | newly exposed by E7b; not specified in either source audit | relation typing + fresh selector | complete: 299 unsafe-fold cases under displayed-label safe-exact ITA; the noisy typed graph was −0.67pp vs exact and bounded inheritance was net zero. The 84-case discordance/edge audit is not a 299-case clinical leaderboard; 64.8% internal direction agreement and 80.6% repeated-pair consistency falsify this implementation, not the ideal mechanism |
| E8 | Atemporal hard veto vs time/scope-aware soft veto | synthesis E8; independent E5 | yes | complete: 220 fixed-pool cases; all 9 hard reference vetoes were manually invalid (8 overreach, 1 construction-induced), but soft vs hard safe-exact was only +1.64pp (2/5, p=.453). The 30-case targeted root audit does not yield a full-cohort clinical rate; absolute veto is unsafe while soft-ranker superiority remains unconfirmed |
| E9 | Forest real/duplicate/shuffled view independence | synthesis E9; independent E6 | selector replay | complete: 400 cases × 4 selector arms plus proposition clustering and a 70-case targeted root review; real views improve safe-exact top-1 by 2.25pp over the balanced single-view anchor (10/1). The old 6 gain/1 harm/4 neutral reclassification mixed true equivalence with missing scope, subtype or composite components and is withdrawn as a clinical-complete result. The remaining 330 cases are clinically unadjudicated, so role/repetition flips establish instability rather than a full clinical effect |
| E10 | B06 isolated/sequential × supervisor/RRF | synthesis E10 | yes | complete: 400-case paired 2×2 with shared Doctor A/frozen doctors; sequential history compresses mean union 6.82→5.21 and Jaccard .689→.954. The historical fields named `clinical-complete*` actually combine `same_entity` with `acceptable_clinical_variant`; they are now a binary acceptable proxy only. `clinical-complete`, `compatible-partial` and their union were not separately measured, so the old Top-2/exposure values cannot support a clinical-ability or complete-object conclusion |
| E11 | B07 retrieval off/on/random/hard-negative × refine off/on | synthesis E11 | yes, RAG | complete: 400-case 4×2 factorial; the reported query-top −2.00pp and broad +0.50pp are non-blind root-priority/proxy-completed sensitivities, not blinded clinical rates. Root review covers 39 cases/624 occurrences and the other 5,776 occurrences are proxy-completed; only 6.62% of relevant chunks are case-specific, hard-negative is gold-contaminated, and refine shows conditional specificity rescue plus rare-candidate deletion |
| E12 | e7 representation × width × comparator | synthesis E12 | yes | complete: 300-case 3×2×3 factorial plus depth1/2/3 path; the reported raw-pairwise signals at k5/k10 are non-blind root-priority/proxy-completed secondary sensitivities. The actual root queue exposed arm outcomes, gold and queue reasons, contrary to the preregistered blinded wording; this is a protocol deviation. Root review covers 154 cases/385 relations and 2,806 relations are proxy-completed, so the result is not a blinded clinical-complete rate |
| E14x | Exploratory runtime-gate utility without multi-run latent labels | synthesis E14; RCR Call-4 gate | no additional call | complete: 300 conservative-gate pairs (artifact field `strict_gate`) plus 200 legacy permissive-gate pairs; no primary pair has identical G1/G2, so no causal coefficient is claimed. Ninety conservative-gate calls add 135 new frozen-identity entities but zero safe-exact reference discoveries; the 34 triggered-flip outcomes (6 repair/15 harm/13 neutral) are a mechanism-enriched root queue, not 300-case clinical rates |
| RCR3 | End-to-end relation-preserving 3-call system | independent §11/E7 | yes | complete: the Top-1 29/20/18 and Top-2 42/31/26 values are non-blind root-priority/proxy-completed sensitivities, not blinded rates; 375 relations received root review, 3,151 are proxy-completed and 7 fail closed. The deployment rejection remains supported independently by safe-exact frontier exposure −7.00pp (`q=.000311`), schema failures, span loss and relation-fidelity defects |

The independent report's width, ranker and clean-Compact tests map to E5, E4
and RCR3 respectively.  Its seven tests therefore remain separately
identifiable even though the numbering is consolidated.

## Closure status

All scientifically eligible rows in the crosswalk are now implemented and
reported.  E0/E3 are infrastructure contracts rather than online arms; E1,
E2, E4–E12, E14x and RCR3 have immutable scripts, results, logs or audit
provenance, and reports.  E13 remains excluded because it is explicitly the
multi-run/provider-normalisation programme the execution request removed.
The formal E14 router proposed after E13 is not estimable without those latent
multi-run labels; the realised deployable gate was instead tested directly in
E14x and disabled.  New confirmation-set work remains excluded by request.

The cross-experiment closure audit, evidence matrix and final root synthesis
are generated by `cross_experiment_synthesis.py` and documented in
`CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md`.

This closes **scientific execution**, not endpoint migration.  The machine
coverage audit currently contains 91 registered experiment-arm rows: only the
9 E2 arms have a full blinded root census for clinical-complete,
compatible-partial and their union; the 3 E7a structural-replay arms are not applicable;
the other 79 arms across 14 experiments do not have that full contract.  The
authoritative matrix is
`results/ENDPOINT_COVERAGE_AUDIT/endpoint_coverage_matrix.json`; any missing or
duplicate arm, changed report anchor, or attempt to ingest a non-E2 row into a
clinical-capability leaderboard fails closed.

## Endpoint contract

When its runtime exposes the stage, an arm preserves the observed transition:

`runtime text → representation → raw nominations → typed registry → actual
selector payload → pre-mapper diagnosis → task projection`.

The unified E2 replay records six distinct columns: **safe-exact** (exact or
frozen-safe-synonym conservative lower bound), **legacy-chain** (historical
substring/resolver replay), **clinical-complete** (the diagnostic-ability
primary), **compatible-partial** (compatible but incomplete object),
**complete-or-compatible-partial** (secondary coverage union) and **task**. DA task
is an option-mapper interface result; MCR task is a separately calibrated
semantic judge.  They are reported by family and never pooled as one ability
endpoint.

Other experiments retain their frozen cohort and scoring contract, but this
does not make their endpoint coverage equivalent.  A local
`clinical-complete*` is at most a report-specific root-priority/proxy-completed
sensitivity unless that report proves exhaustive blinded root coverage; it
must not be relabeled as the E2 full-800 census or used for an ability ranking.
E10 is stricter still: its old field is only a binary acceptable proxy and is
neither clinical-complete nor a valid complete-or-compatible-partial union.  Unreviewed
safe-exact negatives are not clinical negatives.  The historical result field
`strict` is displayed as **safe-exact**, while legacy substring
`label_match`/legacy-chain is kept only for replay or debugging.  An arm named
`legacy_substring` (E7) is a registry treatment and does not change the
arm-invariant endpoint.  Task is reported only when the experiment actually
runs the relevant mapper/judge; it is never inferred from pre-mapper diagnosis.

Mechanism endpoints additionally include raw/post-registry exposure recall,
gold-in-exposure conversion, active-veto rescue/harm, rank/top-1 flips and
mapper rescue/harm.

## Commit rule

Each row above receives its own code/result/log commit after all of its stated
conditions finish.  Failed or partially served calls remain in the artifact and
are not silently dropped; their cases appear in an intention-to-analyse table.
