# DiagnosisArena d2_seq100_v1 基线结果汇总

生成时间：2026-07-24（**v7：并入三分集本方法最佳配置**；v6 并入 OX；v5 并入 MCR；v4 并入 B17）

## 1. 实验设定

| 项 | 值 |
|---|---|
| 子集 | `data/benchmarks/diagnosisarena/subsets/d2_seq100_v1`（100 例） |
| 输入契约 | 开放 vignette（无 Options）→ 有序 Top-2 |
| 评分 | `RelationAwareAnswerMapper`，模式 `typed_llm_disagreement_rag` |
| 指标 | option @1 / option @2 / MRR@2 |
| API 骨干模型 | `meta-llama/llama-3.3-70b-instruct` |
| B11a 模型 | 本地 `DiagnosisGPT-6B`（GPU，官方 disease DB） |
| 共享知识库（RAG 臂） | `data/corpus/rag_index` + `data/corpus/cpg_index` |

### 1.1 非消融覆盖

| 臂 | 状态 | 目录 |
|---|---|---|
| B01–B02, B04–B06, B11a/b, B15–B16 | 已完成 | `fixed_v1` / `rag_smoke_live` / `b11a_smoke` |
| B00, B03, B07, B12, B13 | 已完成 | `diagnosisarena_remaining_v1` |
| **B17 i-MedRAG** | **已完成** | `diagnosisarena_imedrag_v1` |
| B08 / B09 | 门控：RareBench/RareArena | — |
| B10 | 门控：多厂商（同 backbone 用 B06） | — |
| B14 / A\* | 结构消融，不入强度主表 | — |

## 2. 主结果（按 option @1 降序）

| 排名 | 臂 | 类别 | n | err | @1 | @2 | MRR@2 |
|---:|---|---|---:|---:|---:|---:|---:|
| — | **Ours**（compat + synonym_bind） | 本方法（树） | 100 | 0 | **0.81** | **0.93** | **0.95** |
| 1 | `B07-meddxagent-complete` | API+shared RAG | 100 | 0 | 0.62 | 0.71 | 0.665 |
| 2 | `B06-mac-single-vendor` | API pure multi-step | 100 | 0 | 0.61 | 0.67 | 0.640 |
| 3 | `B04-dual-inf` | API pure multi-step | 100 | 0 | 0.60 | 0.70 | 0.650 |
| 4 | `B17-imedrag` | API+shared RAG | 100 | 0 | 0.60 | 0.67 | 0.635 |
| 5 | `B05-mdagents` | API pure multi-step | 100 | 0 | 0.58 | 0.67 | 0.625 |
| 6 | `B13-self-refine-1` | API pure multi-step | 100 | 0 | 0.57 | 0.62 | 0.595 |
| 7 | `B02-flat-matched-rerank` | API+shared RAG | 100 | 0 | 0.56 | 0.63 | 0.595 |
| 8 | `B01-cot-rag` | API+shared RAG | 100 | 0 | 0.55 | 0.63 | 0.590 |
| 9 | `B00-direct-cot` | API pure | 100 | 0 | 0.54 | 0.61 | 0.575 |
| 10 | `B11b-cod-prompt-shared-kb` | API+shared RAG | 100 | 0 | 0.54 | 0.55 | 0.545 |
| 11 | `B12-sc-cot-5` | API pure | 100 | 0 | 0.52 | 0.61 | 0.565 |
| 12 | `B03-flat-beam` | API+shared RAG | 100 | 0 | 0.52 | 0.60 | 0.560 |
| 13 | `B15-medprompt-style` | API+shared RAG | 100 | 0 | 0.52 | 0.57 | 0.545 |
| 14 | `B16-medrag-kg` | API+shared RAG | 100 | 0 | 0.48 | 0.52 | 0.500 |
| 15 | `B11a-official-diagnosisgpt` | Local GPU | 100 | 0 | 0.14 | 0.14 | 0.140 |

## 3. 分组对比

### 3.1 纯模型

| 臂 | @1 | @2 | MRR@2 | 说明 |
|---|---:|---:|---:|---|
| `B06-mac-single-vendor` | 0.61 | 0.67 | 0.640 | 3 doctors + supervisor |
| `B04-dual-inf` | 0.60 | 0.70 | 0.650 | Dual-Inf 四模块；@2 次高 |
| `B05-mdagents` | 0.58 | 0.67 | 0.625 | 复杂度自适应协作 |
| `B13-self-refine-1` | 0.57 | 0.62 | 0.595 | draft → critique → revise |
| `B00-direct-cot` | 0.54 | 0.61 | 0.575 | 最低复杂度 CoT |
| `B12-sc-cot-5` | 0.52 | 0.61 | 0.565 | 5-sample RRF；未超过单次 CoT |

### 3.2 共享 RAG / 知识库

| 臂 | @1 | @2 | MRR@2 | 说明 |
|---|---:|---:|---:|---|
| `B07-meddxagent-complete` | 0.62 | 0.71 | 0.665 | MEDDx complete-profile；全表最高 |
| **`B17-imedrag`** | **0.60** | **0.67** | **0.635** | **i-MedRAG 迭代 follow-up；强 RAG，共享 KB** |
| `B02-flat-matched-rerank` | 0.56 | 0.63 | 0.595 | 固定查询 retrieve→rerank |
| `B01-cot-rag` | 0.55 | 0.63 | 0.590 | planner RAG |
| `B11b-cod-prompt-shared-kb` | 0.54 | 0.55 | 0.545 | CoD prompt + shared KB |
| `B03-flat-beam` | 0.52 | 0.60 | 0.560 | 无 L1 平面 beam |
| `B15-medprompt-style` | 0.52 | 0.57 | 0.545 | MedPrompt 共享 KB 适配 |
| `B16-medrag-kg` | 0.48 | 0.52 | 0.500 | MedRAG-elicited（WWW'25 KG 风格；非 i-MedRAG） |

### 3.3 资源非匹配

| 臂 | @1 | @2 | MRR@2 | 说明 |
|---|---:|---:|---:|---|
| `B11a-official-diagnosisgpt` | 0.14 | 0.14 | 0.140 | DiagnosisGPT-6B + 官方 disease DB |

## 4. 主要观察

1. **本方法（compat + synonym_bind）@1/@2=0.81/0.93**，高于全表外部基线最高的 B07（0.62/0.71）。无 bind 的正式 compat 锚点仍为 0.72/0.78。
2. **B17 i-MedRAG（@1=0.60）显著强于 B01/B02 等单轮 RAG**，接近 Dual-Inf / MAC，仍略低于 B07（0.62）。
3. **外部基线中 B07 仍为最高**（@1=0.62, @2=0.71）；B17 为最强纯迭代 RAG 对照。
4. **B16（KG-elicited）≠ B17（i-MedRAG）**：前者为诊断差异 elicitation；后者为官方迭代 follow-up 查询循环。
5. **B08/B09/B10 仍门控**；全部已跑非消融臂均为 100/100、0 error。

## 5. 跨数据集对照：MedCaseReasoning `mcr_val_seq100_v1`（指标数值）

> **分表声明**：下表为 MCR 正式形态指标（`paper_aligned_judge_v1` / Gemini 2.5 Flash / `workers=50`），**不是** DiagnosisArena Mapper `option@k`。字段 `diagnostic_accuracy_single_trajectory` ≠ 官方 10-shot Acc。重叠臂便于相对排序对照，**禁止与 §2 混算或静默横比论文 MCR 主表**。

| 排名 | 臂 | 类别 | n | err | Acc (single traj.) | Hits | Reasoning Recall | DA @1（§2，仅对照） |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| — | **Ours**（compat B0） | 本方法（树） | 100 | 0 | **0.50** | 50 | **0.753**（LLM） | 0.81 |
| 1 | `B07-meddxagent-complete` | API+shared RAG | 100 | 0 | 0.24 | 24 | 0.412 | 0.62 |
| 2 | `B06-mac-single-vendor` | API pure | 100 | 0 | 0.23 | 23 | 0.527 | 0.61 |
| 3 | `B01-cot-rag` | API+shared RAG | 100 | 0 | 0.22 | 22 | 0.478 | 0.55 |
| 4 | `B03-flat-beam` | API+shared RAG | 100 | 0 | 0.21 | 21 | 0.447 | 0.52 |
| 5 | `B13-self-refine-1` | API pure | 100 | 0 | 0.21 | 21 | 0.447 | 0.57 |
| 6 | `B05-mdagents` | API pure | 100 | 0 | 0.20 | 20 | 0.570 | 0.58 |
| 7 | `B17-imedrag` | API+shared RAG | 100 | 0 | 0.19 | 19 | 0.482 | 0.60 |
| 8 | `B12-sc-cot-5` | API pure | 100 | 0 | 0.19 | 19 | 0.369 | 0.52 |
| 9 | `B00-direct-cot` | API pure | 100 | 0 | 0.18 | 18 | 0.510 | 0.54 |
| 10 | `B15-medprompt-style` | API+shared RAG | 100 | 0 | 0.18 | 18 | 0.294 | 0.52 |
| 11 | `B16-medrag-kg` | API+shared RAG | 100 | 0 | 0.17 | 17 | 0.557 | 0.48 |
| 12 | `B04-dual-inf` | API pure | 100 | 0 | 0.17 | 17 | 0.444 | 0.60 |
| 13 | `B02-flat-matched-rerank` | API+shared RAG | 100 | 0 | 0.17 | 17 | 0.404 | 0.56 |
| 14 | `B11b-cod-prompt-shared-kb` | API+shared RAG | 100 | 0 | 0.14 | 14 | 0.430 | 0.54 |

分组均值（MCR）：Pure Acc=0.197 / Recall=0.478（n=6）；RAG Acc=0.190 / Recall=0.438（n=8）。

权威 MCR 专表：[`medcasereasoning_mcr_val_seq100_v1/mcr_val_seq100_baselines_summary.md`](medcasereasoning_mcr_val_seq100_v1/mcr_val_seq100_baselines_summary.md) · TSV 同目录 `.tsv`。

## 6. 跨数据集对照：Open-XDDx `ox_seq100_v1`（指标数值）

> **分表声明**：下表为 OX 正式形态指标（`paper_aligned_judge_v1` / Gemini 2.5 Flash / `workers=50` / `list_k=5`），**不是** DiagnosisArena Mapper `option@k`，也不是 MCR Acc。主读 Diagnostic micro P/R/F1 + Interp Acc；重叠臂便于相对排序对照，**禁止与 §2/§5 混算或静默横比论文 OX 主表**。

| 排名 | 臂 | 类别 | n | err | micro-P | micro-R | micro-F1 | Interp Acc | DA @1（§2，仅对照） |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| — | **Ours**（锁定F + live重标 + closed_live） | 本方法（树） | 100 | 0 | **0.631** | **0.672** | **0.651** | **0.355** | 0.81 |
| 1 | `B06-mac-single-vendor` | API pure | 100 | 0 | 0.552 | 0.588 | 0.570 | 0.221 | 0.61 |
| 2 | `B00-direct-cot` | API pure | 100 | 0 | 0.526 | 0.561 | 0.543 | 0.233 | 0.54 |
| 3 | `B05-mdagents` | API pure | 100 | 0 | 0.526 | 0.561 | 0.543 | 0.424 | 0.58 |
| 4 | `B12-sc-cot-5` | API pure | 100 | 0 | 0.522 | 0.557 | 0.539 | 0.000 | 0.52 |
| 5 | `B13-self-refine-1` | API pure | 100 | 0 | 0.514 | 0.548 | 0.530 | 0.206 | 0.57 |
| 6 | `B15-medprompt-style` | API+shared RAG | 100 | 0 | 0.506 | 0.539 | 0.522 | 0.000 | 0.52 |
| 7 | `B03-flat-beam` | API+shared RAG | 100 | 0 | 0.494 | 0.527 | 0.510 | 0.642 | 0.52 |
| 8 | `B04-dual-inf` | API pure | 100 | 0 | 0.504 | 0.510 | 0.507 | 0.319 | 0.60 |
| 9 | `B02-flat-matched-rerank` | API+shared RAG | 100 | 0 | 0.480 | 0.512 | 0.495 | 0.419 | 0.56 |
| 10 | `B07-meddxagent-complete` | API+shared RAG | 100 | 0 | 0.476 | 0.507 | 0.491 | 0.403 | 0.62 |
| 11 | `B16-medrag-kg` | API+shared RAG | 100 | 0 | 0.474 | 0.497 | 0.485 | 0.224 | 0.48 |
| 12 | `B11b-cod-prompt-shared-kb` | API+shared RAG | 100 | 0 | 0.461 | 0.490 | 0.475 | 0.215 | 0.54 |
| 13 | `B01-cot-rag` | API+shared RAG | 100 | 0 | 0.452 | 0.482 | 0.466 | 0.240 | 0.55 |
| 14 | `B17-imedrag` | API+shared RAG | 100 | 0 | 0.700 | 0.299 | 0.419 | 0.237 | 0.60 |

分组均值（OX micro-F1）：Pure=0.539（n=6）；RAG=0.483（n=8）。B12/B15 Interp Acc=0 为解释投影空，非诊断评测失败。

权威 OX 专表：[`open_xddx_ox_seq100_v1/ox_seq100_baselines_summary.md`](open_xddx_ox_seq100_v1/ox_seq100_baselines_summary.md) · TSV 同目录 `.tsv`。

## 7. 三分集：本方法最佳配置 vs 最强外部基线（一览）

> **分表**：三数据集主指标不同，**禁止横比绝对数**；本表仅并列本方法最优配置与各集最强 Bxx。  
> 机制说明：[`CURRENT_HIERARCHICAL_DIAGNOSIS_RESEARCH_PIPELINE_EXPLAINER.md`](../../CURRENT_HIERARCHICAL_DIAGNOSIS_RESEARCH_PIPELINE_EXPLAINER.md) §9；OX 专论 [`ox_specific_mechanisms_explainer.md`](../../analysis/transfer_metrics_v1/ox_specific_mechanisms_explainer.md)。

| 数据集 | 主指标 | **Ours 最佳配置** | Ours | 最强外部基线 | 基线分 |
|--------|--------|-------------------|------|--------------|--------|
| **DA** `d2_seq100` | Mapper option @1/@2 | `compat_parallel` + **`--synonym-bind-repair`**（Approach A live） | **0.81 / 0.93** | B07 MEDDx | 0.62 / 0.71 |
| **MCR** `mcr_val_seq100` | LLM Acc / Reasoning Recall | `compat`（B0 `compat_parallel_final_ranking`）；F6 默认预算 | **0.50 / 0.753** | B07 MEDDx | 0.24 / 0.412 |
| **OX** `ox_seq100` | LLM micro-F1 / Interp Acc（K=5） | **无 emit**；L1=4 / L2local=4 / between=2 / cand=6；**live 后验写回**；`closed_live_mac_supervisor` @15/5 | **F1 0.651** / **IAcc 0.355**（P0.631 / R0.672） | B06 MAC | F1 0.570 / IAcc 0.221 |

配置与产物锚点：

| 数据集 | 运行目录 / 评测出口 |
|--------|---------------------|
| DA | Approach A live：`analysis/l1_recall_failure_v1/smoke_synonym_bind_live/`（@1/@2=0.81/0.93）；正式无 bind 锚点仍为 0.72/0.78 |
| MCR | `logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate/official_eval_llm_compat_rr/` |
| OX | `logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1/annotate/official_eval_llm_closed_live_mac/` |

## 8. 产物路径

| 类别 | 路径 |
|---|---|
| **B17 i-MedRAG** | `runs/paper_v1/diagnosisarena_imedrag_v1/` |
| 补齐臂 B00/B03/B07/B12/B13 | `runs/paper_v1/diagnosisarena_remaining_v1/` |
| 修正多步/RAG | `runs/paper_v1/diagnosisarena_fixed_v1/` |
| B01 / B11b | `runs/paper_v1/diagnosisarena_rag_smoke_live/` |
| B11a | `runs/paper_v1/diagnosisarena_b11a_smoke/` |
| MCR 全量基线 + LLM 评测 | `runs/paper_v1/medcasereasoning_mcr_val_seq100_v1/` |
| OX 全量基线 + LLM 评测 | `runs/paper_v1/open_xddx_ox_seq100_v1/` |
| OX 本方法最优（live 重标） | `logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1/` |
| 统一 TSV（DA Mapper） | `runs/paper_v1/diagnosisarena_d2_seq100_baselines_summary.tsv` |
| 本汇总 | `runs/paper_v1/diagnosisarena_d2_seq100_baselines_summary.md` |

```bash
bash scripts/paper/run_b17_imedrag_d2_seq100.sh
JUDGE=llm EVAL_WORKERS=50 bash scripts/paper/run_baselines_mcr_val_seq100.sh
JUDGE=llm EVAL_WORKERS=50 bash scripts/paper/run_baselines_ox_seq100.sh
```
