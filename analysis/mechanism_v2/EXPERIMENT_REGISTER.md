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
| E1 | Same-code clean/options × fixed/shuffled-format input | synthesis E1 | yes | complete: 200 cases × 8 arms; option visibility raises paired top-1 by 41.0pp hierarchical and 40.2pp flat under fixed format, but the effect is label-copy/format sensitive and is not a full-production APHHM result |
| E2 | Strict completeness + identifiability blinded adjudication | synthesis E2; independent §12.1 | heterogeneous proxy reviewers + final audit | design frozen: weighted 400/800 sample (DA/MCR 200 each), all 69 mapper-harm and all 37 primary stable-exclusive cases retained; two heterogeneous reviews and root adjudication pending |
| E3 | Claim ledger and frozen analysis dependencies | synthesis E3 | no | implemented |
| E4 | Fixed-pool selector crossover | synthesis E4; independent E4 | yes | complete: 400 cases × 5 arms; Forest +2.0pp vs e7 (9/1, p=.0215), but all strict gain is MCR and 3/9 gains are surface/scope artifacts; pairwise adds cost without beating Forest |
| E5 | Candidate-set interference / IIA | synthesis E5; independent E3 | yes | complete: 200 cases × 9 arms; sibling −10.91pp (Holm p=.0147), width 8 −16.46pp (Holm p=.000114), and width 6→8 −7.93pp; direct capture dominates MCR while shared-candidate reordering dominates DA; manual audit shows major synonym-bridge and component-direction error |
| E6 | Raw vs flat facts vs typed relation graph | synthesis E6/E12; independent E2 | yes | complete: 300 selected, 258 builder-valid; root-corrected semantic graph vs raw complete-equivalence −7.63pp (24/5, p=.00055), with relation errors in 25/30 manually audited graphs; the tested generated graph is harmful, not evidence that all structured graphs are harmful |
| E6x | Remove flat sentinel padding without changing facts | newly exposed by E6 tokenizer telemetry; absent from both source audits | yes | complete: removing padding cuts mean input tokens 64.9% but changes complete equivalence only +1.57pp (7/11, p=.481) and complete+partial −3.53pp (19/10, p=.136); padding is a severe cost confound, not a unidirectional quality explanation |
| E7 | Substring vs exact-synonym vs typed registry | synthesis E7; independent E1 | selector replay | complete: E7a offline replay + E7b 400-case fresh blinded selector; exact identity restores exposure, generic relation edge adds no top-1 benefit |
| E7c | Directional clinical relation + bounded evidence inheritance after safe identity | newly exposed by E7b; not specified in either source audit | relation typing + fresh selector | complete: 299 unsafe-fold cases; actual noisy typed graph was -0.67 pp vs exact and bounded inheritance was net zero; only 64.8% internal direction agreement and 80.6% repeated-pair consistency, so this falsifies the implementation, not the ideal mechanism |
| E8 | Atemporal hard veto vs time/scope-aware soft veto | synthesis E8; independent E5 | yes | complete: 220 fixed-pool cases; all 9 hard reference vetoes were manually invalid (8 overreach, 1 construction-induced), but soft vs hard paired accuracy was only +1.64pp (2/5, p=.453); invalid time and legal row order each flip about one quarter of champions with near-zero net accuracy, so absolute veto is unsafe while soft-ranker superiority remains unconfirmed |
| E9 | Forest real/duplicate/shuffled view independence | synthesis E9; independent E6 | selector replay | complete: 400 cases x 4 selector arms plus heterogeneous semantic audit and 70-case root review; real views improve strict top-1 by 2.25pp over the balanced single-view anchor (10/1), but only 6/10 strict gains are clinical and just 3 are true new capture; role rotation and exact repetition both expose substantial selector instability |
| E10 | B06 isolated/sequential × supervisor/RRF | synthesis E10 | yes | complete: 400-case paired 2×2 with shared Doctor A/frozen doctors; sequential history compresses mean union 6.82→5.21 and Jaccard .689→.954, but raises root-audited clinical Top-2 through rank conversion (RRF +4.50pp, Supervisor +3.25pp) while erasing documented rare correct candidates; closed-pool Supervisor is a small isolated-panel semantic rescue, not the diversity bottleneck |
| E11 | B07 retrieval off/on/random/hard-negative × refine off/on | synthesis E11 | yes, RAG | complete: 400-case 4×2 factorial; query-top relevant vs off clinical-complete Top-1 −2.00pp (10/2, Holm q=.270) but disease-family-sensitive +0.50pp; only 6.62% relevant chunks were case-specific, hard-negative was gold-contaminated, and refine showed conditional specificity rescue plus systematic rare-candidate deletion |
| E12 | e7 representation × width × comparator | synthesis E12 | yes | complete: 300-case 3×2×3 factorial plus depth1/2/3 path; raw pairwise beats frozen first by +4.67pp at k5 (Holm q=.0499) and +5.00pp at k10 (q=.0284), while raw-vs-S1, width and depth effects do not survive the 39-test family; root audit localizes destructive S1 evidence deletion, graph relation failures, candidate interference and mostly non-identifiable repeated-selector depth flips |
| E14x | Exploratory runtime-gate utility without multi-run latent labels | synthesis E14; RCR Call-4 gate | no additional call | complete: 300 strict-gate pairs plus 200 legacy permissive-gate pairs; no primary pair has identical G1/G2, so no causal coefficient is claimed; 90 strict-gate calls add 135 new frozen-identity entities but zero strict reference discoveries, and root review of all 34 triggered champion flips finds 6 observed repairs, 15 harms and 13 neutral; old Call-4 gate disabled by default |
| RCR3 | End-to-end relation-preserving 3-call system | independent §11/E7 | yes | complete: root clinical Top-1 Lite/RCR/Compact4=29/20/18 and Top-2=42/31/26; RCR vs Lite complete Top-1 −3.00pp (Holm q=.1567), Top-2 −3.67pp (q=.1045), while strict frontier exposure was −7.00pp (q=.000311); root mechanism audit found 20/60 stratified relation edges wrong/unsupported, at least 69/119 material evidence drops, three raw→frontier reference losses, and only 9/66 selector self-complete champions root-complete |

The independent report's width, ranker and clean-Compact tests map to E5, E4
and RCR3 respectively.  Its seven tests therefore remain separately
identifiable even though the numbering is consolidated.

## Endpoint contract

Every arm records the complete transition:

`runtime text → representation → raw nominations → typed registry → actual
selector payload → pre-mapper diagnosis → task projection`.

Primary mechanism endpoints are strict/exact-or-frozen-synonym diagnosis,
clinical-complete proxy adjudication, raw/post-registry/exposure recall,
gold-in-exposure conversion, active-veto rescue/harm, rank/top-1 flips and
mapper rescue/harm.  Legacy substring `label_match` is retained only as a
debugging endpoint.

## Commit rule

Each row above receives its own code/result/log commit after all of its stated
conditions finish.  Failed or partially served calls remain in the artifact and
are not silently dropped; their cases appear in an intention-to-analyse table.
