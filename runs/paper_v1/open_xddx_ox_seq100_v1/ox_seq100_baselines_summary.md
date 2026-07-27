# Open-XDDx ox_seq100_v1 基线正式评估汇总

生成时间：2026-07-26（核验：全臂 100/100 推理 + LLM 正式评测完成；**2026-07-27 并入本方法最优臂 F1=0.651 / LLM Interp Acc=0.355**）

## 1. 实验设定

| 项 | 值 |
|---|---|
| 子集 | `data/benchmarks/open_xddx/subsets/ox_seq100_v1`（100 例） |
| 输入契约 | 开放 vignette（无 Options）→ 有序 Top-5（`list_k=5`） |
| 预测协议 | `baseline_ordered_topk_v1` / `single_trajectory_v1` |
| 评分 | `run_baseline_ox_mcr_eval.py` → `paper_aligned_judge_v1` |
| 裁判 | Gemini 2.5 Flash（`google/gemini-2.5-flash`） |
| 环境契约 | `conda gnn-llm` + `clashon` + `--workers 50` |
| 骨干模型 | `meta-llama/llama-3.3-70b-instruct` |
| 共享 KB（RAG 臂） | `data/corpus/rag_index` + `data/corpus/cpg_index` |
| 产物根目录 | `runs/paper_v1/open_xddx_ox_seq100_v1/` |

### 1.1 边界（不得静默横比论文主表）

- 主指标为 Diagnostic **micro P/R/F1** + Interpretation Acc，**不是** Mapper `option@k`，也不是 MCR Acc。
- `list_k=5` 与树系统 `ddx_k` 对齐；禁止与 DiagnosisArena Top-2 Mapper 混表。
- Interpretation 来自基线 / 树侧 `reasoning_summary` 模板投影，非端到端解释生成；部分臂投影为空时 IAcc=0。
- **Interp Acc 一律为 LLM 裁判**（`judge=llm`，模板 `ox.interpretation_consistency` / Gemini 2.5 Flash），**不是**词汇 `leaf_match` / lexical。本方法最优：357/1007 ≈ **0.355**。

## 2. 主结果（按 micro-F1 降序）

| 排名 | 臂 | 类别 | n | err | micro-P | micro-R | micro-F1 | macro-F1 | Interp Acc |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| — | **Ours**（锁定F + live重标 + closed_live） | 本方法（树） | 100 | 0 | **0.631** | **0.672** | **0.651** | 0.643 | **0.355** |
| 1 | `B06-mac-single-vendor` | API pure | 100 | 0 | 0.552 | 0.588 | 0.570 | 0.570 | 0.221 |
| 2 | `B00-direct-cot` | API pure | 100 | 0 | 0.526 | 0.561 | 0.543 | 0.544 | 0.233 |
| 3 | `B05-mdagents` | API pure | 100 | 0 | 0.526 | 0.561 | 0.543 | 0.543 | 0.424 |
| 4 | `B12-sc-cot-5` | API pure | 100 | 0 | 0.522 | 0.557 | 0.539 | 0.538 | 0.000 |
| 5 | `B13-self-refine-1` | API pure | 100 | 0 | 0.514 | 0.548 | 0.530 | 0.529 | 0.206 |
| 6 | `B15-medprompt-style` | API+shared RAG | 100 | 0 | 0.506 | 0.539 | 0.522 | 0.525 | 0.000 |
| 7 | `B03-flat-beam` | API+shared RAG | 100 | 0 | 0.494 | 0.527 | 0.510 | 0.509 | 0.642 |
| 8 | `B04-dual-inf` | API pure | 100 | 0 | 0.504 | 0.510 | 0.507 | 0.502 | 0.319 |
| 9 | `B02-flat-matched-rerank` | API+shared RAG | 100 | 0 | 0.480 | 0.512 | 0.495 | 0.500 | 0.419 |
| 10 | `B07-meddxagent-complete` | API+shared RAG | 100 | 0 | 0.476 | 0.507 | 0.491 | 0.493 | 0.403 |
| 11 | `B16-medrag-kg` | API+shared RAG | 100 | 0 | 0.474 | 0.497 | 0.485 | 0.485 | 0.224 |
| 12 | `B11b-cod-prompt-shared-kb` | API+shared RAG | 100 | 0 | 0.461 | 0.490 | 0.475 | 0.478 | 0.215 |
| 13 | `B01-cot-rag` | API+shared RAG | 100 | 0 | 0.452 | 0.482 | 0.466 | 0.467 | 0.240 |
| 14 | `B17-imedrag` | API+shared RAG | 100 | 0 | 0.700 | 0.299 | 0.419 | 0.431 | 0.237 |

## 3. 分组对比

### 3.1 纯模型

| 臂 | micro-F1 | Interp Acc | 说明 |
|---|---:|---:|---|
| `B06-mac-single-vendor` | 0.570 | 0.221 | 3 doctors + supervisor；全表最高 micro-F1 |
| `B00-direct-cot` | 0.543 | 0.233 | 最低复杂度 CoT；F1 次高 |
| `B05-mdagents` | 0.543 | 0.424 | 复杂度自适应协作；IAcc 最高之一 |
| `B12-sc-cot-5` | 0.539 | 0.000 | 5-sample RRF；解释投影为空 → IAcc=0 |
| `B13-self-refine-1` | 0.530 | 0.206 | draft → critique → revise |
| `B04-dual-inf` | 0.507 | 0.319 | Dual-Inf 四模块 |

### 3.2 共享 RAG / 知识库

| 臂 | micro-F1 | Interp Acc | 说明 |
|---|---:|---:|---|
| `B15-medprompt-style` | 0.522 | 0.000 | MedPrompt 共享 KB；解释投影为空 → IAcc=0 |
| `B03-flat-beam` | 0.510 | 0.642 | 无 L1 平面 beam；IAcc 最高 |
| `B02-flat-matched-rerank` | 0.495 | 0.419 | 固定查询 retrieve→rerank |
| `B07-meddxagent-complete` | 0.491 | 0.403 | MEDDx complete-profile；DA/MCR 强但 OX F1 中游 |
| `B16-medrag-kg` | 0.485 | 0.224 | MedRAG-elicited（非 i-MedRAG） |
| `B11b-cod-prompt-shared-kb` | 0.475 | 0.215 | CoD prompt + shared KB |
| `B01-cot-rag` | 0.466 | 0.240 | planner RAG |
| `B17-imedrag` | 0.419 | 0.237 | i-MedRAG；高 P 低 R → F1 最低（列表偏短/偏窄） |

- Pure 臂均值 micro-F1=0.539，Interp Acc=0.234（n=6）
- RAG 臂均值 micro-F1=0.483，Interp Acc=0.298（n=8）

## 4. 主要观察

1. **本方法最优臂 micro-F1=0.651、LLM Interp Acc=0.355**（357/1007；`ox.interpretation_consistency`），高于全表外部基线最高的 B06（F1 0.570 / IAcc 0.221）。
2. **外部基线中 B06 最高（0.570）**，其次 B00/B05（0.543）；与 DA/MCR 上 B07 领先的格局不同。
3. **B17 i-MedRAG 呈高 P（0.700）低 R（0.299）**，micro-F1 最低（0.419）；可能有效候选偏短/偏窄，不宜与 DA @1 强项直接等同解读。
4. **B12 / B15 的 Interp Acc=0**：解释边投影为空（非诊断集合评测失败）；读 IAcc 时需排除这两臂。
5. **B03 的 Interp Acc 最高（0.642）**，但诊断 F1 仅中游；诊断集合与解释一致性排序不一致。

本方法配置与产物：`logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1/annotate/official_eval_llm_closed_live_mac/`；机制见 [`ox_specific_mechanisms_explainer.md`](../../../analysis/transfer_metrics_v1/ox_specific_mechanisms_explainer.md)。跨集对照总表：[`diagnosisarena_d2_seq100_baselines_summary.md`](../diagnosisarena_d2_seq100_baselines_summary.md) §7。

## 5. 复现命令

```bash
bash /home/wanghongyi/clashctl/clashon.sh
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate gnn-llm
JUDGE=llm EVAL_WORKERS=50 WORKERS=20 RESUME=1 \
  bash scripts/paper/run_baselines_ox_seq100.sh
```

仅重跑评测：

```bash
SKIP_INFER=1 JUDGE=llm EVAL_WORKERS=50 \
  bash scripts/paper/run_baselines_ox_seq100.sh
```

TSV：[`ox_seq100_baselines_summary.tsv`](ox_seq100_baselines_summary.tsv)
