# MCR 最佳本方法配置：LLM Reasoning Recall

日期：2026-07-27  
配置：`compat_synonym_v1` × `--ddx-source compat`（`compat_parallel_final_ranking`，B0）  
队列：`mcr_val_seq100_v1`（100 例）  
协议：`paper_aligned_judge_v1` / Gemini 2.5 Flash / `workers=50`  
产物：`logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate/official_eval_llm_compat_rr/`

此前 Acc=0.50 臂因 `--skip-reasoning-recall` 未跑 Prompt 5；本表为补跑。

| 指标 | 值 |
|------|-----|
| Diagnostic Acc (single traj., LLM Prompt 7) | **0.50**（50/100） |
| **Reasoning Recall mean (LLM Prompt 5)** | **0.753** |
| 金标推理点数 | 517（均值 5.17 / 例） |

边界：≠ 官方 10-shot Acc；≠ lexical Reasoning Recall；勿与 mapper option@1 混表。
