# Approach A: synonym bind-repair → rematch (compat ranking)

**generated**: `2026-07-24T21:22:36.763453+00:00`
**cohort**: `all100`
**protocol**: frozen mapper + compat `final_ranking` rematch; **no typed LLM**
**KB**: lexical leaf_match + `disease_name_bridge` boost

## Main table (rematch protocol)

| arm | @1 | @2 | MRR | gold_matched | repair_case_rate |
|-----|---:|---:|----:|-------------:|-----------------:|
| R_compat_rematch | 0.596 | 0.788 | 0.695 | 0.798 | — |
| **R_compat_synonym_bind_rematch** | **0.687** | **0.949** | **0.827** | **0.980** | 0.697 |

## Gate

- decision: **PASS**
- claim_allowed: `True`
- production_default: **off**
- synonym_bind_rematch vs compat_rematch Δ@1=+0.091 Δ@2=+0.162
- opt1 guard (Δ≥0): OK
- opt2 guard (Δ≥-0.01): OK
- matched 0.798 → 0.980

## Notes

- Formal main-table anchor remains all100 compat_parallel rematch **0.72/0.78**.
- This table is **frozen case_results rematch** A/B (not that live table).
- This arm is rematch-protocol only; do not mix with typed tables (I5).
- Even on PASS: default stays off until explicitly enabled.
- Empty `final_ranking` cases (e.g. 97) are skipped for both arms.

```bash
PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/run_synonym_bind_rematch_smoke.py \
    --cohort all100 --auto-escalate
```
