# DiagnosisArena d2_seq100：基线 + synonym_bind mapper

在已有 `typed_llm_disagreement_rag` 投影上离线施加 Approach A `synonym_bind_repair`（`min_score=0.70`），写入各臂 `mapper_synonym_bind/`，便于与本方法 **compat + synonym_bind**（@1=0.81）对照。

> 说明：基线仍是「合成 Top-2 叶 + typed map」；本方法是「树叶短列表 + compat rematch + bind」。协议仍有结构差，但 **同义修绑步骤已对齐**。

| 臂 | n | @1 (bind) | @2 (bind) | MRR@2 | @1 (原) | @2 (原) | 修绑病例数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `B15-medprompt-style` | 100 | **0.81** | 0.95 | 0.88 | 0.52 | 0.57 | 74 |
| `B17-imedrag` | 100 | **0.81** | 0.95 | 0.88 | 0.6 | 0.67 | 68 |
| `B01-cot-rag` | 100 | **0.8** | 0.95 | 0.875 | 0.55 | 0.63 | 67 |
| `B11b-cod-prompt-shared-kb` | 100 | **0.8** | 0.91 | 0.855 | 0.54 | 0.55 | 74 |
| `B16-medrag-kg` | 100 | **0.8** | 0.94 | 0.87 | 0.48 | 0.52 | 72 |
| `B02-flat-matched-rerank` | 100 | **0.78** | 0.96 | 0.87 | 0.56 | 0.63 | 71 |
| `B07-meddxagent-complete` | 100 | **0.78** | 0.96 | 0.87 | 0.62 | 0.71 | 69 |
| `B06-mac-single-vendor` | 100 | **0.77** | 0.92 | 0.845 | 0.61 | 0.67 | 72 |
| `B13-self-refine-1` | 100 | **0.75** | 0.92 | 0.835 | 0.57 | 0.62 | 78 |
| `B04-dual-inf` | 100 | **0.74** | 0.92 | 0.83 | 0.6 | 0.7 | 64 |
| `B12-sc-cot-5` | 100 | **0.74** | 0.9 | 0.82 | 0.52 | 0.61 | 74 |
| `B11a-official-diagnosisgpt` | 100 | **0.71** | 0.8 | 0.755 | 0.14 | 0.14 | 87 |
| `B03-flat-beam` | 100 | **0.7** | 0.91 | 0.805 | 0.52 | 0.6 | 74 |
| `B05-mdagents` | 100 | **0.7** | 0.9 | 0.8 | 0.58 | 0.67 | 76 |
| `B00-direct-cot` | 100 | **0.69** | 0.88 | 0.785 | 0.54 | 0.61 | 73 |
| `B02-flat-compute-matched` | 100 | **0.68** | 0.93 | 0.805 | 0.48 | 0.59 | 72 |
| `B02-flat-compute-matched-sc10` | 100 | **0.66** | 0.92 | 0.79 | 0.47 | 0.59 | 75 |

本方法锚点：`analysis/l1_recall_failure_v1/smoke_synonym_bind_live/` R_compat_synonym_bind_live **@1=0.81 / @2=0.93**。

TSV：[`diagnosisarena_d2_seq100_baselines_synonym_bind.tsv`](diagnosisarena_d2_seq100_baselines_synonym_bind.tsv)
