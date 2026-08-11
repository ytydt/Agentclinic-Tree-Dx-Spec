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
| E1 | Same-code clean/options × fixed/shuffled-format input | synthesis E1 | yes | 200-case, 8-arm input-sensitive APHHM/AB02 micro-pipeline frozen; executing (explicitly not full production APHHM) |
| E2 | Strict completeness + identifiability blinded adjudication | synthesis E2; independent §12.1 | heterogeneous proxy reviewers + final audit | queued |
| E3 | Claim ledger and frozen analysis dependencies | synthesis E3 | no | implemented |
| E4 | Fixed-pool selector crossover | synthesis E4; independent E4 | yes | complete: 400 cases × 5 arms; Forest +2.0pp vs e7 (9/1, p=.0215), but all strict gain is MCR and 3/9 gains are surface/scope artifacts; pairwise adds cost without beating Forest |
| E5 | Candidate-set interference / IIA | synthesis E5; independent E3 | yes | queued |
| E6 | Raw vs flat facts vs typed relation graph | synthesis E6/E12; independent E2 | yes | queued |
| E7 | Substring vs exact-synonym vs typed registry | synthesis E7; independent E1 | selector replay | complete: E7a offline replay + E7b 400-case fresh blinded selector; exact identity restores exposure, generic relation edge adds no top-1 benefit |
| E7c | Directional clinical relation + bounded evidence inheritance after safe identity | newly exposed by E7b; not specified in either source audit | relation typing + fresh selector | complete: 299 unsafe-fold cases; actual noisy typed graph was -0.67 pp vs exact and bounded inheritance was net zero; only 64.8% internal direction agreement and 80.6% repeated-pair consistency, so this falsifies the implementation, not the ideal mechanism |
| E8 | Atemporal hard veto vs time/scope-aware soft veto | synthesis E8; independent E5 | yes | queued |
| E9 | Forest real/duplicate/shuffled view independence | synthesis E9; independent E6 | selector replay | queued |
| E10 | B06 isolated/sequential × supervisor/RRF | synthesis E10 | yes | queued |
| E11 | B07 retrieval off/on/random/hard-negative × refine off/on | synthesis E11 | yes, RAG | queued |
| E12 | e7 representation × width × comparator | synthesis E12 | yes | queued |
| E14x | Exploratory runtime-gate utility without multi-run latent labels | synthesis E14; RCR Call-4 gate | no additional call | queued; inferentially downgraded |
| RCR3 | End-to-end relation-preserving 3-call system | independent §11/E7 | yes | queued |

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
