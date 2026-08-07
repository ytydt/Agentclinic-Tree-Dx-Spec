# MedCaseReasoning mcr_val_seq100_v1 基线正式评估汇总

生成时间：2026-07-26（核验：全臂 100/100 推理 + LLM 正式评测完成；**2026-07-27 并入本方法 Acc=0.50 / LLM RR=0.753**）

## 1. 实验设定

| 项 | 值 |
|---|---|
| 子集 | `data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1`（100 例） |
| 输入契约 | 开放 vignette（无 Options）→ 有序 Top-2（`list_k=2`） |
| 预测协议 | `baseline_ordered_topk_v1` / `single_trajectory_v1` |
| 评分 | `run_baseline_ox_mcr_eval.py` → `paper_aligned_judge_v1` |
| 裁判 | Gemini 2.5 Flash（`google/gemini-2.5-flash`） |
| 环境契约 | `conda gnn-llm` + `clashon` + `--workers 50` |
| 骨干模型 | `meta-llama/llama-3.3-70b-instruct` |
| 共享 KB（RAG 臂） | `data/corpus/rag_index` + `data/corpus/cpg_index` |
| 产物根目录 | `runs/paper_v1/medcasereasoning_mcr_val_seq100_v1/` |

### 1.1 边界（不得静默横比论文主表）

- 字段名为 `diagnostic_accuracy_single_trajectory`，**不是**官方 10-shot Acc。
- Reasoning Recall 基于模板投影 `pred_reasoning_trace`（来自 `reasoning_summary`），非端到端 CoT 采样。
- 与 DiagnosisArena Mapper `option_top1` **分表**。

## 2. 主结果（按 Acc 降序）

| 排名 | 臂 | 类别 | n | err | Acc (single traj.) | Hits | Reasoning Recall |
|---:|---|---|---:|---:|---:|---:|---:|
| — | **Ours**（compat B0） | 本方法（树） | 100 | 0 | **0.50** | 50 | **0.753**（LLM Prompt 5） |
| 1 | `B07-meddxagent-complete` | API+shared RAG | 100 | 0 | 0.24 | 24 | 0.412 |
| 2 | `B06-mac-single-vendor` | API pure | 100 | 0 | 0.23 | 23 | 0.527 |
| 3 | `B01-cot-rag` | API+shared RAG | 100 | 0 | 0.22 | 22 | 0.478 |
| 4 | `B03-flat-beam` | API+shared RAG | 100 | 0 | 0.21 | 21 | 0.447 |
| 5 | `B13-self-refine-1` | API pure | 100 | 0 | 0.21 | 21 | 0.447 |
| 6 | `B05-mdagents` | API pure | 100 | 0 | 0.20 | 20 | 0.570 |
| 7 | `B17-imedrag` | API+shared RAG | 100 | 0 | 0.19 | 19 | 0.482 |
| 8 | `B12-sc-cot-5` | API pure | 100 | 0 | 0.19 | 19 | 0.369 |
| 9 | `B00-direct-cot` | API pure | 100 | 0 | 0.18 | 18 | 0.510 |
| 10 | `B15-medprompt-style` | API+shared RAG | 100 | 0 | 0.18 | 18 | 0.294 |
| 11 | `B16-medrag-kg` | API+shared RAG | 100 | 0 | 0.17 | 17 | 0.557 |
| 12 | `B04-dual-inf` | API pure | 100 | 0 | 0.17 | 17 | 0.444 |
| 13 | `B02-flat-matched-rerank` | API+shared RAG | 100 | 0 | 0.17 | 17 | 0.404 |
| 14 | `B11b-cod-prompt-shared-kb` | API+shared RAG | 100 | 0 | 0.14 | 14 | 0.430 |

## 3. 分组对比

### 3.1 纯模型

| 臂 | Acc | Reasoning Recall | 说明 |
|---|---:|---:|---|
| `B06-mac-single-vendor` | 0.23 | 0.527 | 3 doctors + supervisor；Acc 次高 |
| `B13-self-refine-1` | 0.21 | 0.447 | draft → critique → revise |
| `B05-mdagents` | 0.20 | 0.570 | 全表最高 Reasoning Recall |
| `B12-sc-cot-5` | 0.19 | 0.369 | 5-sample RRF |
| `B00-direct-cot` | 0.18 | 0.510 | 最低复杂度 CoT |
| `B04-dual-inf` | 0.17 | 0.444 | Dual-Inf 四模块 |

### 3.2 共享 RAG / 知识库

| 臂 | Acc | Reasoning Recall | 说明 |
|---|---:|---:|---|
| `B07-meddxagent-complete` | 0.24 | 0.412 | 全表最高 Acc |
| `B01-cot-rag` | 0.22 | 0.478 | planner RAG |
| `B03-flat-beam` | 0.21 | 0.447 | 无 L1 平面 beam |
| `B17-imedrag` | 0.19 | 0.482 | i-MedRAG 迭代 follow-up |
| `B15-medprompt-style` | 0.18 | 0.294 | MedPrompt 共享 KB；Recall 最低 |
| `B16-medrag-kg` | 0.17 | 0.557 | MedRAG-elicited；高 Recall |
| `B02-flat-matched-rerank` | 0.17 | 0.404 | 固定查询 retrieve→rerank |
| `B11b-cod-prompt-shared-kb` | 0.14 | 0.430 | CoD prompt + shared KB；Acc 最低 |

- Pure 臂均值 Acc=0.197，Recall=0.478（n=6）
- RAG 臂均值 Acc=0.190，Recall=0.438（n=8）

## 4. 主要观察

1. **本方法最优臂 Acc=0.50、LLM Reasoning Recall=0.753**（`compat` B0），高于外部基线最高的 B07（Acc 0.24 / RR 0.412）。
2. **外部基线中 B07 仍为 Acc 最高（0.24）**，与 DiagnosisArena Mapper 排序一致；绝对数值远低于 DA @1，属开放诊断协议差异。
3. **最高基线 Reasoning Recall 为 B05（0.570）**，其次 B16（0.557）与 B06（0.527）；Acc 与 Recall 排序不完全一致。
4. **B04 Dual-Inf 在 MCR 上 Acc 偏低（0.17）**，相对其在 DA 上的高位（@1=0.60）落差更大。

本方法评测：`logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate/official_eval_llm_compat_rr/`；短记 [`mcr_compat_llm_reasoning_recall.md`](../../../analysis/transfer_metrics_v1/mcr_compat_llm_reasoning_recall.md)。跨集对照总表：[`diagnosisarena_d2_seq100_baselines_summary.md`](../diagnosisarena_d2_seq100_baselines_summary.md) §7。

## 4.1 B02 预算匹配对照（native vs matched）

| 臂 | 模式 | Acc (single traj.) | Hits | Reasoning Recall | 均值 LLM | G5 |
|---|---|---:|---:|---:|---:|---|
| `B02-flat-matched-rerank` | native | 0.17 | 17 | 0.404 | ~2 | — |
| `B02-flat-compute-matched` | matched | 0.17 | 17 | 0.378 | 9.32 | **PASS** |

专档：[`../medcasereasoning_b02_compute_matched_v1/b02_compute_matched_summary.md`](../medcasereasoning_b02_compute_matched_v1/b02_compute_matched_summary.md)。RQ4 / 公平主检验应报 matched 行。

## 5. 复现命令

```bash
bash /home/wanghongyi/clashctl/clashon.sh
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate gnn-llm
JUDGE=llm EVAL_WORKERS=50 WORKERS=20 RESUME=1 \
  bash scripts/paper/run_baselines_mcr_val_seq100.sh
```

仅重跑评测：

```bash
SKIP_INFER=1 JUDGE=llm EVAL_WORKERS=50 \
  bash scripts/paper/run_baselines_mcr_val_seq100.sh
```

TSV：[`mcr_val_seq100_baselines_summary.tsv`](mcr_val_seq100_baselines_summary.tsv)

