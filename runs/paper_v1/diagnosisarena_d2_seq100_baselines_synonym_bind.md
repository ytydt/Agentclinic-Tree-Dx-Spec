# DiagnosisArena d2_seq100：基线 + synonym_bind mapper

在已有 `typed_llm_disagreement_rag` 投影上离线施加 Approach A `synonym_bind_repair`（`min_score=0.70`，**pair_match_score 修后**；不再误用 syn:leaf 自 chunk=1.0），写入各臂 `mapper_synonym_bind/`，便于与本方法 **compat + synonym_bind** 对照。

> 说明：基线仍是「合成 Top-2 叶 + typed map」；本方法是「树叶短列表 + compat rematch + bind」。协议仍有结构差，但 **同义修绑步骤已对齐**。2026-07-27 修复：桥接加分仅用 option↔leaf pair 分。

| 臂 | n | @1 (bind) | @2 (bind) | MRR@2 | @1 (原) | @2 (原) | 修绑病例数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `B07-meddxagent-complete` | 100 | **0.67** | 0.77 | 0.72 | 0.62 | 0.71 | 17 |
| `B13-self-refine-1` | 100 | **0.65** | 0.73 | 0.69 | 0.57 | 0.62 | 26 |
| `B06-mac-single-vendor` | 100 | **0.64** | 0.72 | 0.68 | 0.61 | 0.67 | 22 |
| `B17-imedrag` | 100 | **0.63** | 0.74 | 0.685 | 0.6 | 0.67 | 17 |
| `B04-dual-inf` | 100 | **0.62** | 0.74 | 0.68 | 0.6 | 0.7 | 12 |
| `B05-mdagents` | 100 | **0.62** | 0.74 | 0.68 | 0.58 | 0.67 | 21 |
| `B02-flat-matched-rerank` | 100 | **0.6** | 0.68 | 0.64 | 0.56 | 0.63 | 12 |
| `B00-direct-cot` | 100 | **0.59** | 0.68 | 0.635 | 0.54 | 0.61 | 21 |
| `B01-cot-rag` | 100 | **0.59** | 0.69 | 0.64 | 0.55 | 0.63 | 18 |
| `B11b-cod-prompt-shared-kb` | 100 | **0.58** | 0.59 | 0.585 | 0.54 | 0.55 | 14 |
| `B12-sc-cot-5` | 100 | **0.58** | 0.68 | 0.63 | 0.52 | 0.61 | 20 |
| `B15-medprompt-style` | 100 | **0.57** | 0.63 | 0.6 | 0.52 | 0.57 | 16 |
| `B03-flat-beam` | 100 | **0.55** | 0.64 | 0.595 | 0.52 | 0.6 | 11 |
| `B02-flat-compute-matched` | 100 | **0.53** | 0.64 | 0.585 | 0.48 | 0.59 | 15 |
| `B16-medrag-kg` | 100 | **0.53** | 0.58 | 0.555 | 0.48 | 0.52 | 12 |
| `B02-flat-compute-matched-sc10` | 100 | **0.49** | 0.64 | 0.565 | 0.47 | 0.59 | 14 |
| `B11a-official-diagnosisgpt` | 100 | **0.14** | 0.14 | 0.14 | 0.14 | 0.14 | 0 |

本方法锚点（**pair_match_score 修后**）：`analysis/l1_recall_failure_v1/smoke_synonym_bind_live/` R_compat_synonym_bind_live **@1=0.73 / @2=0.82**（修前误用自 chunk 曾报 0.81/0.93，已作废）。

有 bug 的旧基线表：[`diagnosisarena_d2_seq100_baselines_synonym_bind_BUGGED_selfchunk.md`](diagnosisarena_d2_seq100_baselines_synonym_bind_BUGGED_selfchunk.md)。

TSV：[`diagnosisarena_d2_seq100_baselines_synonym_bind.tsv`](diagnosisarena_d2_seq100_baselines_synonym_bind.tsv)
