# B02 compute-matched budget audit

- pred_dir: `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/runs/paper_v1/open_xddx_b02_compute_matched_sc10_v1/B02-flat-compute-matched-sc10/replicate_01`
- schedule: `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/configs/paper_experiments/paper_v1_budget_schedule_open_xddx.jsonl`
- tolerance: 0.05
- n_cases: 100
- n_mismatch_cases: 0
- match_rate: 1.0
- G5 pass (all cases ≤5%): **YES**

## Per-dimension

| dim | mean rel err | n_mismatch |
|---|---:|---:|
| `llm_calls` | 0.0000 | 0 |
| `retrieval_calls` | 0.0000 | 0 |
| `retrieval_snippets` | 0.0000 | 0 |
| `unique_candidates` | 0.0000 | 0 |
