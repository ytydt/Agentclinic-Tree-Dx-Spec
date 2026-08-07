# DiagnosisArena d2_seq100_v1 基线结果汇总

生成时间：2026-07-27（**v10：修复 synonym_bind 自 chunk bug 并重评**；v9 B02 sc10+错误 bind 表；v8 B02 compute-matched；v7 三分集本方法）

## 1. 实验设定

| 项 | 值 |
|---|---|
| 子集 | `data/benchmarks/diagnosisarena/subsets/d2_seq100_v1`（100 例） |
| 输入契约 | 开放 vignette（无 Options）→ 有序 Top-2 |
| 评分（主表 §2） | `RelationAwareAnswerMapper`，模式 `typed_llm_disagreement_rag`（**无** synonym_bind） |
| 评分（对齐表 §2.1） | 同上投影 + Approach A `synonym_bind_repair`（`min_score=0.70`，**仅 pair_match_score**）→ `mapper_synonym_bind/` |
| 指标 | option @1 / option @2 / MRR@2 |
| API 骨干模型 | `meta-llama/llama-3.3-70b-instruct` |
| B11a 模型 | 本地 `DiagnosisGPT-6B`（GPU，官方 disease DB） |
| 共享知识库（RAG 臂） | `data/corpus/rag_index` + `data/corpus/cpg_index` |

### 1.1 非消融覆盖

| 臂 | 状态 | 目录 |
|---|---|---|
| B01–B02, B04–B06, B11a/b, B15–B16 | 已完成 | `fixed_v1` / `rag_smoke_live` / `b11a_smoke` |
| **B02-flat-compute-matched** | **已完成（G5 PASS）** | `diagnosisarena_b02_compute_matched_v1` |
| **B02-flat-compute-matched-sc10** | **已完成（G5 PASS）** | `diagnosisarena_b02_compute_matched_sc10_v1` |
| B00, B03, B07, B12, B13 | 已完成 | `diagnosisarena_remaining_v1` |
| **B17 i-MedRAG** | **已完成** | `diagnosisarena_imedrag_v1` |
| **全部上表臂 synonym_bind 重评** | **已完成** | 各臂 `mapper_synonym_bind/`；见 §2.1 |
| B08 / B09 | 门控：RareBench/RareArena | — |
| B10 | 门控：多厂商（同 backbone 用 B06） | — |
| B14 / A\* | 结构消融，不入强度主表 | — |

## 2. 主结果（按 option @1 降序；**无** synonym_bind）

| 排名 | 臂 | 类别 | n | err | @1 | @2 | MRR@2 |
|---:|---|---|---:|---:|---:|---:|---:|
| — | **Ours**（compat；无 bind） | 本方法（树） | 100 | 0 | **0.71** | **0.78** | **0.748** |
| — | **Ours**（compat + synonym_bind，pair 修后） | 本方法（树） | 100 | 0 | **0.73** | **0.82** | **0.778** |
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

### 2.1 严格对照：基线 + synonym_bind（pair_match_score 修后）

> 在已有 `typed_llm_disagreement_rag` 投影上离线施加 `synonym_bind_repair`（`min_score=0.70`），**不重跑 LLM map**。  
> **2026-07-27 修复**：桥接加分改为 `SynonymGranularityRetriever.pair_match_score`；禁止用 `search_option_leaves()[0]`（自 chunk=1.0）把空绑一律刷到 pred_1。修前虚高表已归档为 `*_BUGGED_selfchunk.*`。  
> 本方法锚点：树叶 + compat rematch + bind → **@1=0.73 / @2=0.82**（compat 无 bind 0.71/0.78）。  
> 专表：[`diagnosisarena_d2_seq100_baselines_synonym_bind.md`](diagnosisarena_d2_seq100_baselines_synonym_bind.md)。

| 排名 | 臂 | n | @1 (bind) | @2 (bind) | MRR@2 | @1 (原 §2) | Δ@1 |
|---:|---|---:|---:|---:|---:|---:|---:|
| — | **Ours**（compat + synonym_bind） | 100 | **0.73** | **0.82** | **0.778** | 0.71 | +0.02 |
| 1 | `B07-meddxagent-complete` | 100 | 0.67 | 0.77 | 0.72 | 0.62 | +0.05 |
| 2 | `B13-self-refine-1` | 100 | 0.65 | 0.73 | 0.69 | 0.57 | +0.08 |
| 3 | `B06-mac-single-vendor` | 100 | 0.64 | 0.72 | 0.68 | 0.61 | +0.03 |
| 4 | `B17-imedrag` | 100 | 0.63 | 0.74 | 0.685 | 0.60 | +0.03 |
| 5 | `B04-dual-inf` | 100 | 0.62 | 0.74 | 0.68 | 0.60 | +0.02 |
| 5 | `B05-mdagents` | 100 | 0.62 | 0.74 | 0.68 | 0.58 | +0.04 |
| 7 | `B02-flat-matched-rerank` | 100 | 0.60 | 0.68 | 0.64 | 0.56 | +0.04 |
| 8 | `B00-direct-cot` | 100 | 0.59 | 0.68 | 0.635 | 0.54 | +0.05 |
| 8 | `B01-cot-rag` | 100 | 0.59 | 0.69 | 0.64 | 0.55 | +0.04 |
| 10 | `B11b-cod-prompt-shared-kb` | 100 | 0.58 | 0.59 | 0.585 | 0.54 | +0.04 |
| 10 | `B12-sc-cot-5` | 100 | 0.58 | 0.68 | 0.63 | 0.52 | +0.06 |
| 12 | `B15-medprompt-style` | 100 | 0.57 | 0.63 | 0.60 | 0.52 | +0.05 |
| 13 | `B03-flat-beam` | 100 | 0.55 | 0.64 | 0.595 | 0.52 | +0.03 |
| 14 | `B02-flat-compute-matched` | 100 | 0.53 | 0.64 | 0.585 | 0.48 | +0.05 |
| 14 | `B16-medrag-kg` | 100 | 0.53 | 0.58 | 0.555 | 0.48 | +0.05 |
| 16 | `B02-flat-compute-matched-sc10` | 100 | 0.49 | 0.64 | 0.565 | 0.47 | +0.02 |
| 17 | `B11a-official-diagnosisgpt` | 100 | 0.14 | 0.14 | 0.14 | 0.14 | 0.00 |

**读表要点**：修后 bind 只带来温和增益（多数 Δ@1≈+0.02–0.08）；Ours 仍高于最强基线 B07（0.67）。修前「基线冲到 0.8」为评测 bug，已作废。

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

1. **无 bind 主表（§2）**：外部最高 B07 @1=0.62；本方法 compat 无 bind 0.71/0.78。
2. **有 bind 对齐表（§2.1，pair 修后）**：Ours **0.73/0.82**；最强基线 B07 **0.67/0.77**。bind 对基线多为 +0.02–0.08，不再出现冲到 0.8 的虚高。
3. **评测 bug（已修）**：曾误用桥接 RAG 自 chunk（score=1.0）把空绑一律刷到 pred_1；旧 0.81 锚点与旧 §2.1 表已作废（`*_BUGGED_selfchunk.*`）。
4. **B17 i-MedRAG（无 bind @1=0.60）** 仍强于多数单轮 RAG；有 bind 后 0.63。
5. **B08/B09/B10 仍门控**；全部已跑非消融臂均为 100/100、0 error。
6. **B02 compute-matched / sc10（G5 PASS）**：无 bind 0.48/0.47；pair 修后 bind 0.53/0.49。

## 4.1 B02 预算匹配对照（native vs matched）

| 臂 | 模式 | n | @1 | @2 | MRR@2 | @1 (bind, pair修后) | 均值 LLM calls | G5 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `B02-flat-matched-rerank` | native | 100 | 0.56 | 0.63 | 0.595 | 0.60 | 2.0 | — |
| `B02-flat-compute-matched` | matched（structural_proxy_v1） | 100 | 0.48 | 0.59 | 0.535 | 0.53 | 9.24 | **PASS** |
| `B02-flat-compute-matched-sc10` | matched ×10-SC + RRF | 100 | 0.47 | 0.59 | 0.530 | 0.49 | ~92.4 | **PASS** |

> matched 预算来自主方法 `shared_trees` 结构代理（叶数/静证/ L1 数），非官方 token ledger。主检验若强调 RQ4，应报 matched 行。  
> 机制专档：[`diagnosisarena_b02_compute_matched_v1/b02_vs_main_method_and_budget_match.md`](diagnosisarena_b02_compute_matched_v1/b02_vs_main_method_and_budget_match.md)。  
> **Token 差距（事后估计）**：[`../../analysis/transfer_metrics_v1/b02_vs_m00_token_gap_v1.md`](../../analysis/transfer_metrics_v1/b02_vs_m00_token_gap_v1.md) — 单轨 matched 为 call≈9；sc10 将 call 拉到 ~90 量级以贴近主方法 cache 规模。

### 4.1.1 三分集 B02 matched / sc10 一览（均 G5 PASS，workers=50）

| 数据集 | 主指标（**无 bind**） | native | matched | **sc10** | matched 均值 LLM | sc10 均值 LLM | 答案未变/复用评测 | 专档 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| DA | Mapper @1 | 0.56 | 0.48 | **0.47** | 9.24 | **92.4** | 58/100 | [`…_sc10_v1`](diagnosisarena_b02_compute_matched_sc10_v1/) |
| OX | micro-F1 | 0.495 | 0.479 | **0.487** | 8.98 | **89.8** | 10/100 | [`…_sc10_v1`](open_xddx_b02_compute_matched_sc10_v1/) |
| MCR | Acc (single traj.) | 0.17 | 0.17 | **0.15** | 9.32 | **93.2** | 56/100 | [`…_sc10_v1`](medcasereasoning_b02_compute_matched_sc10_v1/) |

> **三分集均已跑 SC10**（非仅 DA）。上表 sc10 列为**无 synonym_bind** 正式评测（DA=`mapper/`；OX/MCR=`official_eval_llm`）。  
> 缓存：`RESUME=1` + `SimpleCachedLLM`；sample0 复用单轨 matched（`sc_seed_pred_dir`，三集均为 100/100）；评测对答案未变病例 `reuse_baseline_eval_if_unchanged` / `resume-scores`。  
> 跨集专表：[`b02_compute_matched_sc10_three_datasets.md`](b02_compute_matched_sc10_three_datasets.md)。

## 5. 跨数据集对照：MedCaseReasoning `mcr_val_seq100_v1`（指标数值）

> **分表声明**：下表为 MCR 正式形态指标（`paper_aligned_judge_v1` / Gemini 2.5 Flash / `workers=50`），**不是** DiagnosisArena Mapper `option@k`。字段 `diagnostic_accuracy_single_trajectory` ≠ 官方 10-shot Acc。重叠臂便于相对排序对照，**禁止与 §2 混算或静默横比论文 MCR 主表**。

| 排名 | 臂 | 类别 | n | err | Acc (single traj.) | Hits | Reasoning Recall | DA @1（§2，仅对照） |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| — | **Ours**（compat B0） | 本方法（树） | 100 | 0 | **0.50** | 50 | **0.753**（LLM） | 0.73 |
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
| — | **Ours**（锁定F + live重标 + closed_live） | 本方法（树） | 100 | 0 | **0.631** | **0.672** | **0.651** | **0.355** | 0.73 |
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
| **DA** `d2_seq100` | Mapper option @1/@2 | `compat_parallel` + **`--synonym-bind-repair`**（pair_match_score 修后） | **0.73 / 0.82** | 无 bind：B07；有 bind（§2.1）：B07 | 无 bind 0.62；有 bind **0.67** |
| **MCR** `mcr_val_seq100` | LLM Acc / Reasoning Recall | `compat`（B0 `compat_parallel_final_ranking`）；F6 默认预算 | **0.50 / 0.753** | B07 MEDDx | 0.24 / 0.412 |
| **OX** `ox_seq100` | LLM micro-F1 / Interp Acc（K=5） | **无 emit**；L1=4 / L2local=4 / between=2 / cand=6；**live 后验写回**；`closed_live_mac_supervisor` @15/5 | **F1 0.651** / **IAcc 0.355**（P0.631 / R0.672） | B06 MAC | F1 0.570 / IAcc 0.221 |

配置与产物锚点：

| 数据集 | 运行目录 / 评测出口 |
|--------|---------------------|
| DA | Approach A live（**pair 修后**）：`analysis/l1_recall_failure_v1/smoke_synonym_bind_live/`（@1/@2=**0.73/0.82**）；compat 无 bind 0.71/0.78；正式无 bind 锚点 0.72/0.78。修前虚高 0.81/0.93 已作废 |
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
| **B02 compute-matched** | `runs/paper_v1/diagnosisarena_b02_compute_matched_v1/` |
| **B02 compute-matched 10-SC（三分集）** | DA/OX/MCR：`*_b02_compute_matched_sc10_v1/`；汇总 [`b02_compute_matched_sc10_three_datasets.md`](b02_compute_matched_sc10_three_datasets.md) |
| **DA 基线 synonym_bind 重评** | 各臂 `mapper_synonym_bind/`；汇总 [`diagnosisarena_d2_seq100_baselines_synonym_bind.md`](diagnosisarena_d2_seq100_baselines_synonym_bind.md) |
| MCR 全量基线 + LLM 评测 | `runs/paper_v1/medcasereasoning_mcr_val_seq100_v1/` |
| OX 全量基线 + LLM 评测 | `runs/paper_v1/open_xddx_ox_seq100_v1/` |
| OX 本方法最优（live 重标） | `logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1/` |
| 统一 TSV（DA Mapper，无 bind） | `runs/paper_v1/diagnosisarena_d2_seq100_baselines_summary.tsv` |
| 本汇总 | `runs/paper_v1/diagnosisarena_d2_seq100_baselines_summary.md` |

```bash
bash scripts/paper/run_b17_imedrag_d2_seq100.sh
JUDGE=llm EVAL_WORKERS=50 bash scripts/paper/run_baselines_mcr_val_seq100.sh
JUDGE=llm EVAL_WORKERS=50 bash scripts/paper/run_baselines_ox_seq100.sh
bash scripts/paper/run_b02_compute_matched_d2_seq100.sh
python3 scripts/paper/rescore_da_baselines_synonym_bind.py
```
