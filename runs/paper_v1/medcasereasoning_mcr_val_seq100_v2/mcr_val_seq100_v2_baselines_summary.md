# MedCaseReasoning mcr_val_seq100_v2 主方法+基线汇总（**不入论文**）

生成时间：2026-07-30T21:27:20.465161+00:00

> **本批结果暂不记入论文 / paper_aaai。** 切片为 v1 顺序延后的第二批 100 例；消融未跑。

## 1. 实验设定

| 项 | 值 |
|---|---|
| 子集 | `data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v2`（100 例，id 129–247） |
| 采样 | 同脚本 `extract_diagnosisarena_subset.py`；`--skip-rows 128` + exclude v1 ids |
| 重叠核验 | id / pmcid / source_row_key 与 v1 重叠均为 **0** |
| 主方法 | `run_compat_synonym_transfer_harness.py` → staged vp→trees→p5→annotate→mapper |
| 主方法参数 | model=`llama-3.3-70b-instruct`，`--granularity-mode compat`，`--l1-calib off`，`--synonym-bind-repair`，workers=8（与 v1/`paper_aaai` 一致） |
| 主方法评测 | `--ddx-source compat`，Gemini 2.5 Flash，Prompt7 Acc + Prompt5 RR |
| 基线 | 同 `run_baselines_mcr_val_seq100.sh` 14 臂，`list_k=2`，LLM judge |
| 产物 | 主方法 `logs/.../mcr_val_seq100_v2/compat_synonym_v1/`；基线 `runs/paper_v1/medcasereasoning_mcr_val_seq100_v2/` |

## 2. 主结果（按 Acc 降序）

| 排名 | 臂 | 类别 | n | err | Acc (single traj.) | Hits | Reasoning Recall |
|---:|---|---|---:|---:|---:|---:|---:|
| — | **Ours**（compat B0） | 本方法（树） | 100 | 0 | **0.46** | 46 | **0.803**（LLM Prompt 5） |
| 1 | `B06-mac-single-vendor` | API pure | 100 | 0 | 0.31 | 31 | 0.499 |
| 2 | `B07-meddxagent-complete` | API+shared RAG | 100 | 0 | 0.25 | 25 | 0.421 |
| 3 | `B00-direct-cot` | API pure | 100 | 0 | 0.24 | 24 | 0.517 |
| 4 | `B01-cot-rag` | API+shared RAG | 100 | 0 | 0.23 | 23 | 0.496 |
| 5 | `B04-dual-inf` | API pure | 100 | 0 | 0.23 | 23 | 0.502 |
| 6 | `B12-sc-cot-5` | API pure | 100 | 0 | 0.23 | 23 | 0.383 |
| 7 | `B17-imedrag` | API+shared RAG | 100 | 0 | 0.22 | 22 | 0.451 |
| 8 | `B05-mdagents` | API pure | 100 | 0 | 0.21 | 21 | 0.542 |
| 9 | `B13-self-refine-1` | API pure | 100 | 0 | 0.21 | 21 | 0.480 |
| 10 | `B03-flat-beam` | API+shared RAG | 100 | 0 | 0.20 | 20 | 0.424 |
| 11 | `B16-medrag-kg` | API+shared RAG | 100 | 0 | 0.20 | 20 | 0.486 |
| 12 | `B02-flat-matched-rerank` | API+shared RAG | 100 | 0 | 0.19 | 19 | 0.388 |
| 13 | `B11b-cod-prompt-shared-kb` | API+shared RAG | 100 | 0 | 0.19 | 19 | 0.415 |
| 14 | `B15-medprompt-style` | API+shared RAG | 100 | 0 | 0.18 | 18 | 0.330 |

## 3. 相对 v1 切片（仅内部对照，不入论文）

| 切片 | Ours Acc | Ours RR | 最强基线 Acc |
|---|---:|---:|---:|
| v1 `mcr_val_seq100_v1` | 0.50 | 0.753 | B07 0.24 |
| v2 `mcr_val_seq100_v2` | 0.46 | 0.803 | B06-mac-single-vendor 0.31 |

## 4. 管线核验

- pipeline `exit_code` = **0**，n=100
- Acc 产物：`annotate/official_eval_llm_compat/`（Acc=0.46，跳过 RR）
- RR 产物：`annotate/official_eval_llm_compat_rr/`（Acc=0.46，RR=0.803）
- 启动 flags 与 v1 一致（仅 cases-json / cases / output-dir 路径不同）

## 5. 边界

- `diagnostic_accuracy_single_trajectory` ≠ 官方 10-shot Acc
- 不与 mapper option@1 / DA 表横比
- **不写入 paper_aaai / paper/*.tex**

