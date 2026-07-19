# A-variant V2 案例级深挖与 Tier3 人工模拟归档

- 日期：2026-07-18
- 协议：`l2-a-variant-v2` / research_only / promotion_eligible=false
- 主终点：`resilient_legacy_actual_top2`（排名仍按冻结 gold fixture 计分）
- 质量与 GoldMatch 覆盖：以 `final_audit_human_sim.json` 为准（Tier3 人工模拟优先于 quality fixture）

## 1. 指标口径（对齐旧 AB / matrix v1）

| 指标 | 定义 |
|---|---|
| Top1% / Top2% / MRR% | 51 单元格池化均值；平衡设计下 ≡ 17 例各自 3-run 均值再平均 |
| active cov% | `active_gold_l2_coverage`（冻结 acceptable ∩ active_ids） |
| inventory cov% | 冻结 acceptable ∩ inventory（含 reserve） |
| local champion% | acceptable ∩ 各父 local champion |
| act父有效% | 仅 `active_ids` 上 `is_parent_valid`（Tier3 human-sim） |
| inv父无效% | 全库存叶 `leaf_parent_invalid_rate`（Tier3 human-sim） |
| clean% / dup-excess% | Tier3 human-sim 叶质量 |
| Tier3 active cov% | `matches_gold=true` 叶 ∩ active_ids（诊断用，未重打 Top1/2） |

## 2. 臂级完整表（Tier3 human-sim 质量）

| arm | Top1% | Top2% | MRR% | actCov% | local% | oracleT2% | act父有效% | inv父无效% | clean% | dupX% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C-prod-v2 | 37.3 | 51.0 | 46.6 | 76.5 | 64.7 | 76.5 | 98.9 | 1.1 | 54.2 | 7.6 |
| A-raw-v2 | 41.2 | 49.0 | 48.1 | 88.2 | 60.8 | 78.4 | 59.8 | 40.2 | 18.4 | 50.4 |
| A4-v2-ref | 27.5 | 49.0 | 39.5 | 80.4 | 52.9 | 66.7 | 86.2 | 13.8 | 74.1 | 6.3 |
| A4+A14-v2-ref | 33.3 | 47.1 | 41.5 | 80.4 | 51.0 | 66.7 | 86.2 | 13.8 | 74.1 | 6.3 |
| A18-parent-safe | 37.3 | 45.1 | 47.1 | 82.4 | 62.7 | 78.4 | 85.8 | 40.2 | 18.4 | 50.4 |
| A19-budget-safe | 25.5 | 33.3 | 33.8 | 86.3 | 47.1 | 68.6 | 69.9 | 40.2 | 18.4 | 50.4 |
| A20-generation-v2 | 39.2 | 47.1 | 47.5 | 82.4 | 60.8 | 78.4 | 90.2 | 40.2 | 18.4 | 50.4 |
| A21-generation-v2+F4 | 27.5 | 51.0 | 41.2 | 82.4 | 56.9 | 76.5 | 90.2 | 40.2 | 18.4 | 50.4 |
| A22-adaptive-local-rescue | 31.4 | 49.0 | 43.0 | 82.4 | 58.8 | 76.5 | 90.2 | 40.2 | 18.4 | 50.4 |

## 3. 冻结 gold vs Tier3 GoldMatch 覆盖

Tier3 coverage uses final_audit_human_sim matches_gold on source_tree leaves. Top1/Top2 ranks remain frozen-gold scored; this table diagnoses gold-definition shift only.

| arm | frozen actCov% | Tier3 actCov% | Δpp | frozen Top命中但 Tier3 无 gold 格数 |
|---|---:|---:|---:|---:|
| C-prod-v2 | 76.5 | 76.5 | 0.0 | 3 |
| A-raw-v2 | 88.2 | 86.3 | -2.0 | 3 |
| A4-v2-ref | 80.4 | 74.5 | -5.9 | 3 |
| A4+A14-v2-ref | 80.4 | 74.5 | -5.9 | 2 |
| A18-parent-safe | 82.4 | 80.4 | -2.0 | 3 |
| A19-budget-safe | 86.3 | 84.3 | -2.0 | 3 |
| A20-generation-v2 | 82.4 | 80.4 | -2.0 | 3 |
| A21-generation-v2+F4 | 82.4 | 80.4 | -2.0 | 3 |
| A22-adaptive-local-rescue | 82.4 | 80.4 | -2.0 | 3 |

解释：Tier3 GoldMatch 比冻结 fixture 更严（裸 Epiglottitis / 裸 Hyperparathyroidism 等不算匹配），
故多数臂 active cov 低约 2pp；A4 系低约 5.9pp。Top1/Top2 表仍按冻结 gold，
因此相对 Tier3 语义略偏乐观；完整重打分需重跑 459 格 ranking（未做）。

## 4. 相对 A-raw-v2 的 cell 净转移

| arm | Top1 net | Top2 net | cov net | local net | Top2 majority-loss cases |
|---|---:|---:|---:|---:|---|
| A18-parent-safe | -2 | -2 | -3 | 1 | mb83_foreignbody, mxh046 |
| A19-budget-safe | -8 | -8 | -1 | -7 | mb55_glucagonoma, mb57_kartagener, mb83_foreignbody, mxh036, mxh046 |
| A20-generation-v2 | -1 | -1 | -3 | 0 | mb55_glucagonoma |
| A21-generation-v2+F4 | -7 | 1 | -3 | -2 | mxh046 |
| A22-adaptive-local-rescue | -5 | 0 | -3 | -1 | — |
| A4+A14-v2-ref | -4 | -1 | -4 | -5 | mb83_foreignbody, mxh046 |
| A4-v2-ref | -7 | 0 | -4 | -4 | mb83_foreignbody |
| C-prod-v2 | -2 | 1 | -6 | 2 | mb34_leukemoid, mxh014 |

## 5. 错误模式（设计目标缺口）

### 5.1 A18-parent-safe

- 判决：
- parent_mismatch reserve：775/1515；uncertain=0
- 相对 audit：FP reserve=297 precision=0.6168
- 机制：M1_axis_tag_overfire; M2_fail_open_never_fires; M3_multi_parent_gold_thinning; M4_coverage_wipe_when_all_gold_mismatched; M5_fn_keeps_remain
- 修复：F1; F2; F3; F4
- 详情：`error_modes_A18.json`

### 5.2 A19-budget-safe

- 判决：A19 meets its no-hard-delete invariant but is the worst Top-2 arm because global semantic dedupe strips cross-parent gold champions into reserve, then local ranking fails to elect the remaining active gold. Reserve does not rescue Top-2.
- Top2=0.3333；LC elimination=20
- 机制：M1_cross_parent_semantic_dedupe; M2_active_gold_loses_local_rank; M3_rare_budget_overflow_of_gold_winner; M4_hard_delete_fixed_but_downstream_destroyed
- 修复：F1_parent_scoped_clustering; F2_multi_parent_gold_retention; F3_gold_aware_or_evidence_aware_cluster_winner; F4_reserve_rescue_into_local
- 详情：`error_modes_A19.json`

### 5.3 A20 / A21 / A22

- **A20-generation-v2**：Top1=39.2% Top2=47.1% local=60.8%
- **A21-generation-v2+F4**：Top1=27.5% Top2=51.0% local=56.9%
- **A22-adaptive-local-rescue**：Top1=31.4% Top2=49.0% local=58.8%
- A21 关键因：11 个 Top1 回退中 8 个为 rank==2 且 gold 仍在 local_champion_ids（F4 demotion）
- A22：相对 A21 Top1 +6/−4；challenger_won 仅 4/10 为 gold
- 详情：`error_modes_A20_A21_A22.json`

## 6. Tier3 人工模拟医学裁决

- 真分歧：55；同意 Tier1=17 / Tier2=36 / neither=2
- 相对 AI proxy 改判意图：24；联网核验：11
- 重建时 human_sim 覆盖 quality fixture：13 项
- 最终相对 proxy audit 字段值变化：15（{'is_parent_valid': 12, 'is_specific_disease': 1, 'semantic_cluster_id': 2}）
- 关键医学结论见 `tier3_human_sim_summary.md`
- 产物：`tier3_human_sim_decisions.json`、`tier3_corrections_human_sim.json`、`final_audit_human_sim.json`
- 注意：human_sim ≠ 真人签署；`human_signed_off=false`，校准门未过

## 7. 产物索引

```
logs/l2_a_variant_legacy_ab_v2/evaluation/case_deep/
  arm_performance_canonical_tier3_human_sim.{json,tsv}
  arm_case_transitions_vs_a_raw_v2.json
  case_means_3run.{json,tsv}
  error_modes_A18.json
  error_modes_A19.json
  error_modes_A20_A21_A22.json
  tier3_human_sim/
    arm_performance_canonical.json
    tier3_vs_frozen_gold_coverage.{json,tsv}
    proxy_vs_human_sim_field_diff.json
    rebuild_summary.json
  tier3_human_sim_summary.md
  V2_CASE_DEEP_TIER3_ARCHIVE.md   # 本文件
logs/l2_a_variant_matrix_v2/judge/
  final_audit_human_sim.json
  tier3_human_sim_decisions.json
  calibration_report_human_sim.json
scripts/
  analyze_l2_a_variant_v2_case_deep.py
  rebuild_l2_a_variant_v2_tier3_human_sim.py
```

