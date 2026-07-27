# 阶段 0：协议对齐（protocol_alignment）

**产出日期**：2026-07-23  
**病例表**：`data/benchmarks/diagnosisarena/subsets/d2_seq100_v1`（100 例）  
**分析根目录**：`analysis/at1_gap_v1/`

## 1. 三系统资产路径

| 系统 | 预测 / 中间量 | Mapper 记录 | 汇总口径 |
|------|----------------|-------------|----------|
| 本方法 merged_100 | Pilot：`logs/.../downstream_top2_w12_v1/case_results`；Remain：`logs/.../pipeline_remaining76_v1/annotate/case_results` | 同目录 `mapper/projections/{id}.json` | `logs/.../merged_100_metrics/` |
| B04 Dual-Inf | `runs/paper_v1/diagnosisarena_fixed_v1/B04-dual-inf/replicate_01/predictions.jsonl` | `.../mapper/records.json`（含 `source_id`） | `runs/paper_v1/diagnosisarena_d2_seq100_baselines_summary.md` |
| B06 MAC | `.../B06-mac-single-vendor/replicate_01/` | 同上 | 同上 |

病例主键对齐：基线 `source_id` ↔ 本方法 `case_id`（字符串数字，如 `"3"`）。

## 2. Mapper 模式混杂（必须写明）

| 侧 | 模式 | 影响 |
|----|------|------|
| 本方法 merged_100 | **`typed_llm`** | 无 disagreement RAG 二次仲裁 |
| 基线汇总 | **`typed_llm_disagreement_rag`** | 对不一致映射可检索再裁定 |

**结论（阶段 0 默认）**：

1. **先用现有结果做机制对比**（本框架主体）。
2. 跨系统 Δ@1（本方法 0.59 vs MAC 0.61 / DualInf 0.60）**可能部分被评分器模式解释**；交叉表与机制迁移结论须标注「评分器不完全同构」。
3. 若后续要把 Δ@1 写成硬宣称，应加一项：**本方法同模式重评**（`typed_llm_disagreement_rag`）对照。

## 3. 本方法可复用中间量（离线分析已用）

来自 `case_results` / joint 产物：

- `l1.l1_posteriors`：L1 后验与父节点序
- `l2.final_ranking_labels`：joint 叶序（id / label / parent / rank）
- Mapper `projection.option_maps`：`relation_type`、`matched_leaf_ids` / `clone_leaf_ids`、`option_rank`
- Joint 规格：dynamic champions + between evidence selector + A3 arbiter（见 `scripts/paper/diagnosisarena_l2_pipeline.py` `run_joint_primary`）

## 4. 主指标复验（option，merged_100）

| 系统 | @1 | @2 | MRR | P(@1\|@2) | @2−@1 |
|------|---:|---:|----:|----------:|------:|
| 本方法 | 0.59 | **0.78** | 0.688 | 0.756 | **+0.19** |
| B06 MAC | **0.61** | 0.67 | 0.640 | **0.910** | +0.06 |
| B04 Dual-Inf | 0.60 | 0.70 | 0.650 | 0.857 | +0.10 |

现象确认：**覆盖强、首位校准弱**；转化效率 P(@1|gold∈Top2) 明显低于 MAC/DualInf。

## 5. 分析脚本

- `scripts/paper/analyze_at1_gap_v1.py` → taxonomy / sets / 初版 L2–L1
- 公平 option 重匹配摘要：`analysis/at1_gap_v1/l2_vs_l1_summary.json`

## 6. 阶段 0 验收

- [x] 100 例主键可对齐
- [x] Mapper 模式差异已文档化
- [x] 中间量登记完毕
- [x] 不阻塞阶段 1–5（对照重评列为可选后续）
