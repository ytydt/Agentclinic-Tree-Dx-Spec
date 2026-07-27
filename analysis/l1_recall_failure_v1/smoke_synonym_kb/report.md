# Mapper synonym/granularity KB smoke (compat leaves)

**generated**: `2026-07-24T19:55:42.383063+00:00`
**cohort**: `pilot24`
**protocol**: frozen compat `final_ranking` → typed_llm vs typed_llm_synonym_kb
**KB**: `disease_name_bridge` via SynonymGranularityRetriever (symmetric)
**leaf inject**: off

## Main table

| arm | @1 | @2 | MRR | gold_matched | mean_leaves | mean_snippets |
|-----|---:|---:|----:|-------------:|------------:|--------------:|
| typed_llm (baseline) | 0.542 | 0.750 | 0.646 | 0.750 | 4.67 | 0.00 |
| **typed_llm_synonym_kb** | **0.542** | **0.708** | **0.625** | **0.708** | 4.67 | 12.67 |

## Gate (Pilot claim)

- decision: **REJECT**
- Δ@1=+0.000 Δ@2=-0.042
- opt2 guard (Δ≥-0.01): FAIL
- production_default: **off**

## Flip notes (Pilot24)

| | cases |
|--|-------|
| @1 rescue (base miss→syn hit) | 33 |
| @1 harm (base hit→syn miss) | 21 |
| gold_matched gain | (none) |
| gold_matched loss | 21 |

- Case **5**（GCRG UNBIND 典型）：两臂金标仍 `unrelated` / unmatched；同义 critic 未修好。
- 净效果：@1 持平、@2 微跌、matched 微降 → **REJECT**，默认 **off**，不 escalate all100。

## Notes

- Baseline rematch on frozen official projections is NOT this table;
  both arms re-run mapper on the same compat leaf shortlist.
- Do not mix rematch / typed tables (I5).
- Reproduce:
  `PYTHONPATH=src:scripts/paper:scripts python3 -u scripts/paper/run_mapper_synonym_kb_smoke.py --cohort pilot24 --workers 8 --resume`
