# Compact forest geometry transplant (R6 §13.11 P0)

## Goal
Bring MOSAIC forest's **generator geometry** (multi-axis pool → high `top_margin`, low `unexplained_specific_evidence`) into a **low-call** APHHM-facing arm, because X1 proved advantage lives in the pool, not the selector family.

## Constraints
- Target budget: **≈3–4 LLM calls** (collapse3c territory).
- Keep APHHM candev selector (or equivalent) for decision.
- Do **not** revive C4/ledger.

## v0 skeleton (implemented)
`scripts/paper/run_compact_forest_aphhm.py`
- 3× mosaic axis generators (`ax_syndrome/mechanism/modality`)
- `GlobalConceptRegistry.score` + `two_lane_frontier`
- Adaptive A1 **off** (budget lock)
- 1× `aphhm_c_frontier_selector_candev`
- Optional `--near-dedup-shortlist`

Calls ≈ **4**. This is the X1 configuration made into a first-class arm.

## v1 (DONE — 800 eval 2026-08-10)
Single-call `MosaicBatchedAxes` + APHHM candev selector (**2 calls**). Runner: `scripts/paper/run_compact_forest_v1.py`.

| arm | n=800 chain |
|---|---:|
| forest | 0.266 |
| compact_forest_v0 | 0.254 |
| **compact_forest_v1** | **0.244** |
| collapse3c | 0.211 |

Beats collapse3c; residual gap to forest ≈2.2pp (mostly MCR). Evidence-X3 harms v1 (−1.7pp) / null on v0 — do not enable.

## Acceptance (status)
1. ✅ DA+MCR chain > collapse3c; approaches forest (not fully closed).
2. ⏳ optional `_r2` not required for the main claim.
3. ✅ near-match reported in `compact_v1_summary.json`.

## Non-goals
- Selector prompt rewriting from reject-reason taxonomy
- Shared-span stripping
- Ledger/veto revival

## v1.1 (DONE — 800 eval)
3-call: `MosaicKeyFacts` + `MosaicBatchedAxes` + APHHM selector (`compact_forest_v11_facts`).

| arm | n=800 chain |
|---|---:|
| forest | 0.266 |
| **v11_facts** | **0.258** |
| v0 | 0.254 |
| v1 | 0.244 |
| collapse3c | 0.211 |

2-call prompt-only `v11` failed pilot (hurt DA). Prefer v11_facts for endogenous; v0 if forest pool reusable.
