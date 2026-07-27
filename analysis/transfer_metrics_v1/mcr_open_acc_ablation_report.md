# MCR Open Acc@1 Ablation Report

- created_at: `2026-07-25T08:33:21.436636+00:00`
- run_dir: `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1`
- primary_metric: `diagnostic_accuracy_single_trajectory` (Prompt7 / Gemini 2.5 Flash)
- dry_calib: `True`

## Primary table (LLM Acc@1)

| arm | source | K | LLM Acc@1 | Δ vs B0 | lex Acc@1 | lex any-hit@K | empty_fb |
|-----|--------|---|-----------|---------|-----------|---------------|----------|
| B0 | `compat_parallel_final_ranking` | 5 | 0.5000 | +0.0000 | 0.5000 | 0.6000 | 2 |
| B1 | `shared_trees_global_leaf_posterior_topk` | 5 | 0.2400 | -0.2600 | 0.2800 | 0.5900 | 0 |
| R1 | `shared_trees_global_leaf_posterior_topk` | 5 | 0.2400 | -0.2600 | 0.2800 | 0.5900 | 0 |
| R1k7 | `shared_trees_global_leaf_posterior_topk` | 7 | 0.2400 | -0.2600 | 0.2800 | 0.6300 | 0 |
| R2 | `compat_then_pad_posterior` | 5 | 0.5000 | +0.0000 | 0.5000 | 0.6900 | 2 |
| R3 | `compat_gate_on_posterior_pool` | 5 | 0.2600 | -0.2400 | 0.2900 | 0.5900 | 0 |
| R3live | `compat_gate_on_posterior_pool` | 5 | 0.3000 | -0.2000 | 0.3300 | 0.5900 | 0 |
| R4 | `calib_only_on_posterior_topk` | 5 | 0.2600 | -0.2400 | 0.3000 | 0.5900 | 0 |
| R4live | `calib_only_on_posterior_topk` | 5 | 0.3000 | -0.2000 | 0.3300 | 0.5900 | 0 |

## Gates

- G1 promote (≥0.55 and ≥B0+0.03): **none**
- G2 transfer (≥0.60): **none**
- G3 reject (Δ≤-0.02): **R3, R3live, R4, R4live**
- G4 any-hit@K ok: R1k7, R2
- G4 any-hit drop warn: R1, R3, R3live, R4, R4live

## R5 (secondary any-hit@K, not Acc main table)

- best pool arm for any-hit: **R2** (lex any-hit@K=0.6900)
- protocol: `any_hit_topk_posterior_v1 / any_hit_compat_list_v1 (lexical)`

## Verdict

- **G1/G2 未过**：无一臂 LLM Acc@1 ≥ 0.55；默认开放投影源仍为 **B0 compat**。
- **R2**：Acc@1 持平 0.50，any-hit@K 0.60→0.69（覆盖增益；设计上保 compat Top-1，故不抬 Acc）。
- **R3/R4（dry+live）G3 REJECT**：后验池上 calib/gate 伤 Acc（0.26–0.30）。
- **Wave-2 E**：15/15 `axis_absent` → **deferred_generation**（不做限量子集补叶）。
- **下一步（非本轮默认）**：compat 列表内重排吃 C；生成侧吃 E；勿用 mapper @1 宣称开放 Acc。

## Boundaries

- Primary metric is Prompt7 LLM Acc@1; mapper option_top1 must not be mixed in.
- single_trajectory_v1 ≠ paper 10-shot Acc.
- Wave-1 offline rerank; trees not rebuilt.
- R4 default dry_calib is near-identity prior order; use --live-calib for true calib.
- E-class requires generation / limited L2 expand; see e_audit.decision.

## Baseline miss taxonomy (B0 compat LLM, n=50)

- E_gold_absent_from_tree_leaves: 15
- D_gold_leaf_in_tree_but_dropped_by_compat: 18
- C_gold_in_compat_list_not_rank1: 10
- B_top1_equiv_but_judge_n: 5
- A_empty_compat_ranking: 2

## Wave-2 E-class coverage audit

- n_E: 15
- axis_in_leaf_out: 0
- axis_absent: 15
- decision: **deferred_generation**
- detail: `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/analysis/transfer_metrics_v1/mcr_e_class_coverage_audit.json`
