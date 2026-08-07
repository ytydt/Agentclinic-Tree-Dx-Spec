# Approach A live: synonym bind-repair on compat_parallel

**generated**: `2026-07-27T09:24:10+00:00`（**pair_match_score 修复后重跑**）  
**cohort**: `all100`  
**protocol**: `compat_parallel` (gold_g2 off, at1_compat cache) → synonym bind → rematch  
**KB**: lexical `leaf_match_score` + `disease_name_bridge.pair_match_score`（**不含** `syn:leaf`/`syn:option` 自 chunk）  
**no typed LLM**

## Main table (live rematch protocol)

| arm | @1 | @2 | MRR | gold_matched | repair_case_rate |
|-----|---:|---:|----:|-------------:|-----------------:|
| R_compat_live | 0.710 | 0.780 | 0.748 | 0.790 | — |
| **R_compat_synonym_bind_live** | **0.730** | **0.820** | **0.778** | **0.830** | 0.280 |
| formal anchor compat_parallel | 0.72 | 0.78 | — | — | — |

> **作废**：修前误用 `search_option_leaves()[0]`（自 chunk score=1.0）曾报 **0.81/0.93**；见 `report_BUGGED_selfchunk.md` / `summary_all100_BUGGED_selfchunk.json`。

## Gate

- decision: **PASS**
- claim_allowed: `True`
- production_default: **off**
- synonym_bind_live vs compat_live Δ@1=+0.020 Δ@2=+0.040
- matched 0.790 → 0.830
- vs formal 0.72/0.78: Δ@1=+0.010 Δ@2=+0.040

## Notes

- 桥接功能保留：真实同义/粒度 pair（如 AML↔acute myeloid leukemia）仍可 ≥0.70 加分。
- 空绑不再因「叶名在库中可 resolve」一律绑到 pred_1。
- Live table comparable to formal **0.72/0.78** (same compat_parallel path).

```bash
PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/run_synonym_bind_live_smoke.py \
    --cohort all100 --dry-run
```
