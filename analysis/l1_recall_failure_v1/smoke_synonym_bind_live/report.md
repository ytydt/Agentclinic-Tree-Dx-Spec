# Approach A live: synonym bind-repair on compat_parallel

**generated**: `2026-07-24T22:13:23.212378+00:00`
**cohort**: `all100`
**protocol**: `compat_parallel` (gold_g2 off, at1_compat cache) → synonym bind → rematch
**KB**: lexical leaf_match + `disease_name_bridge`
**no typed LLM**

## Main table (live rematch protocol)

| arm | @1 | @2 | MRR | gold_matched | repair_case_rate |
|-----|---:|---:|----:|-------------:|-----------------:|
| R_compat_live | 0.710 | 0.780 | 0.748 | 0.790 | — |
| **R_compat_synonym_bind_live** | **0.810** | **0.930** | **0.877** | **0.950** | 0.670 |
| formal anchor compat_parallel | 0.72 | 0.78 | — | — | — |

## Gate

- decision: **PASS**
- claim_allowed: `True`
- production_default: **off**
- synonym_bind_live vs compat_live Δ@1=+0.100 Δ@2=+0.150
- opt1 guard (Δ≥0): OK
- opt2 guard (Δ≥-0.01): OK
- matched 0.790 → 0.950
- vs formal 0.72/0.78: Δ@1=+0.090 Δ@2=+0.150
- baseline reproduce check: compat_live @1=0.710 @2=0.780

## Notes

- Live table is comparable to formal **0.72/0.78** (same compat_parallel path).
- Empty ranking (e.g. case 97 calib_only) scored as miss 0/0 for both arms (at1口径).
- Baseline reproduce: this run compat **0.71/0.78** (formal 0.72/0.78; only case **214** @1 differs).
- Frozen rematch A/B lives in `smoke_synonym_bind_rematch/` (I5: do not mix).
- Even on PASS: default stays off until explicitly enabled.

```bash
PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/run_synonym_bind_live_smoke.py \
    --cohort all100 --auto-escalate
```
