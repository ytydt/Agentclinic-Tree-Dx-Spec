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
| E2 | Full-800 five-endpoint root adjudication + reference identifiability | synthesis E2; independent §12.1 | no new LLM for census completion; historical screens retained as provenance | complete: 800/800-case root census across 9 arms and 7,200 case-arm outputs, replaying safe-exact / legacy-chain / clinical-complete / partial / task under one contract. Clinical-complete is the diagnostic-ability primary; 455/800 references are uniquely identifiable at full specificity. No overall ten-contrast Holm result is significant; in the separately frozen MCR ten-contrast family Collapse3c exceeds IMPC by 5.50pp (`q=.045615`), while the DA–MCR interaction is not multiplicity-confirmed (`q=.228489`), so no universal winner is claimed. DA task is an option-mapper interface endpoint; MCR task is a separately calibrated semantic judge and the two are never pooled |
| E3 | Claim ledger and frozen analysis dependencies | synthesis E3 | no | implemented |
| E4 | Fixed-pool selector crossover | synthesis E4; independent E4 | yes | complete: 400 cases × 5 arms; Forest safe-exact +2.0pp vs e7 (9/1, p=.0215), but all safe-exact gain is MCR and 3/9 reviewed gains are surface/scope artifacts; the bounded 17-discordance + 12-case audit does not establish full-cohort clinical-complete superiority, and pairwise adds cost without beating Forest on the frozen endpoint |
| E5 | Candidate-set interference / IIA | synthesis E5; independent E3 | yes | complete: 200 cases × 9 arms; safe-exact sibling −10.91pp (Holm p=.0147), width 8 −16.46pp (Holm p=.000114), and width 6→8 −7.93pp; direct capture dominates MCR while shared-candidate reordering dominates DA; the 339-judgment targeted audit exposes synonym-bridge and component-direction error but is not an all-output clinical score |
| E6 | Raw vs flat facts vs typed relation graph | synthesis E6/E12; independent E2 | yes | complete: 300 selected, 258 builder-valid; the external-screen/root-corrected clinical-complete* sensitivity gives graph vs raw −7.63pp (24/5, p=.00055), with root review of 94 cases/262 outputs and relation errors in 25/30 audited graphs; this falsifies the tested generated graph, not all structured graphs, and is not an E2-cohort clinical rate |
| E6x | Remove flat sentinel padding without changing facts | newly exposed by E6 tokenizer telemetry; absent from both source audits | yes | complete: removing padding cuts mean input tokens 64.9% but changes targeted clinical-complete* sensitivity only +1.57pp (7/11, p=.481) and complete+partial* −3.53pp (19/10, p=.136); root review covers 63 cases/126 judgments, so padding is a cost confound without an established whole-cohort clinical effect |
| E7 | Substring vs exact-synonym vs typed registry | synthesis E7; independent E1 | selector replay | complete: E7a offline replay + E7b 400-case fresh blinded selector; all arms use one displayed-label safe-exact endpoint. `legacy_substring` names a registry treatment, not the historical legacy-chain scoring endpoint; the frozen 40-case clinical queue supports mechanism attribution only, while exact identity restores safe-exact exposure and a generic relation edge adds no safe-exact top-1 benefit |
| E7c | Directional clinical relation + bounded evidence inheritance after safe identity | newly exposed by E7b; not specified in either source audit | relation typing + fresh selector | complete: 299 unsafe-fold cases under displayed-label safe-exact ITA; the noisy typed graph was −0.67pp vs exact and bounded inheritance was net zero. The 84-case discordance/edge audit is not a 299-case clinical leaderboard; 64.8% internal direction agreement and 80.6% repeated-pair consistency falsify this implementation, not the ideal mechanism |
| E8 | Atemporal hard veto vs time/scope-aware soft veto | synthesis E8; independent E5 | yes | complete: 220 fixed-pool cases; all 9 hard reference vetoes were manually invalid (8 overreach, 1 construction-induced), but soft vs hard safe-exact was only +1.64pp (2/5, p=.453). The 30-case targeted root audit does not yield a full-cohort clinical rate; absolute veto is unsafe while soft-ranker superiority remains unconfirmed |
| E9 | Forest real/duplicate/shuffled view independence | synthesis E9; independent E6 | selector replay | complete: 400 cases × 4 selector arms plus proposition clustering and a 70-case root review; real views improve safe-exact top-1 by 2.25pp over the balanced single-view anchor (10/1), but only 6/10 audited safe-exact gains are clinical and just 3 are true new capture. The remaining 330 cases are clinically unadjudicated, so role/repetition flips establish instability rather than a full clinical effect |
| E10 | B06 isolated/sequential × supervisor/RRF | synthesis E10 | yes | complete: 400-case paired 2×2 with shared Doctor A/frozen doctors; sequential history compresses mean union 6.82→5.21 and Jaccard .689→.954, while root-priority/proxy-completed clinical-complete* sensitivity raises Top-2 through rank conversion (RRF +4.50pp, Supervisor +3.25pp). Root review covers 166/400 cases; the result is not a full manual clinical census |
| E11 | B07 retrieval off/on/random/hard-negative × refine off/on | synthesis E11 | yes, RAG | complete: 400-case 4×2 factorial; query-top relevant vs off clinical-complete* sensitivity is −2.00pp (10/2, Holm q=.270), while complete+partial* is +0.50pp. Root review covers the endpoint-critical queue, with the other occurrences proxy-completed; only 6.62% of relevant chunks are case-specific, hard-negative is gold-contaminated, and refine shows conditional specificity rescue plus rare-candidate deletion |
| E12 | e7 representation × width × comparator | synthesis E12 | yes | complete: 300-case 3×2×3 factorial plus depth1/2/3 path; on root-priority/proxy-completed clinical-complete*, raw pairwise beats frozen first by +4.67pp at k5 (Holm q=.0499) and +5.00pp at k10 (q=.0284), while raw-vs-S1, width and depth effects do not survive the 39-test family. Root review covers 154 cases/385 relations, not every candidate relation |
| E14x | Exploratory runtime-gate utility without multi-run latent labels | synthesis E14; RCR Call-4 gate | no additional call | complete: 300 conservative-gate pairs (artifact field `strict_gate`) plus 200 legacy permissive-gate pairs; no primary pair has identical G1/G2, so no causal coefficient is claimed. Ninety conservative-gate calls add 135 new frozen-identity entities but zero safe-exact reference discoveries; the 34 triggered-flip outcomes (6 repair/15 harm/13 neutral) are a mechanism-enriched root queue, not 300-case clinical rates |
| RCR3 | End-to-end relation-preserving 3-call system | independent §11/E7 | yes | complete: root-priority/proxy-completed clinical-complete* Top-1 Lite/RCR/Compact4=29/20/18 and Top-2=42/31/26; RCR vs Lite complete* Top-1 −3.00pp (Holm q=.1567), Top-2 −3.67pp (q=.1045), while safe-exact frontier exposure is −7.00pp (q=.000311). Root review covers all endpoint-critical selected relations but not all 3,533 candidate relations |

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

## Endpoint contract

Every arm records the complete transition:

`runtime text → representation → raw nominations → typed registry → actual
selector payload → pre-mapper diagnosis → task projection`.

The unified E2 replay records five distinct columns: **safe-exact** (exact or
frozen-safe-synonym conservative lower bound), **legacy-chain** (historical
substring/resolver replay), **clinical-complete** (the diagnostic-ability
primary), **partial** (compatible but incomplete object) and **task**.  DA task
is an option-mapper interface result; MCR task is a separately calibrated
semantic judge.  They are reported by family and never pooled as one ability
endpoint.

Other experiments retain their frozen cohort and scoring contract.  A local
`clinical-complete*` denotes a report-specific root-priority/proxy-completed
sensitivity analysis unless that report explicitly states exhaustive root
coverage; it must not be relabeled as the E2 full-800 census.  Unreviewed
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
