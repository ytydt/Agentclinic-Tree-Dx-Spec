# B02 compute-matched budget audit

- pred_dir: `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/runs/paper_v1/diagnosisarena_b02_compute_matched_v1/B02-flat-compute-matched/replicate_01`
- schedule: `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/configs/paper_experiments/paper_v1_budget_schedule_diagnosisarena.jsonl`
- tolerance: 0.05
- n_cases: 100
- n_mismatch_cases: 0
- match_rate: 1.0
- G5 pass (all cases ≤5%): **YES**

豁免（计入通过，已入 notes）：`unique_candidates` 允许 ±1 绝对松弛；LLM 预算用尽且覆盖 ≥80% 时记 `llm_diversity_cap`（本 run：`diagnosisarena__000249`）。

## Per-dimension

| dim | mean rel err | n_mismatch |
|---|---:|---:|
| `llm_calls` | 0.0000 | 0 |
| `retrieval_calls` | 0.0000 | 0 |
| `retrieval_snippets` | 0.0000 | 0 |
| `unique_candidates` | 0.0000 | 0 |
