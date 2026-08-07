# B02 compute-matched（OX ox_seq100）汇总

生成时间：2026-07-27  
状态：**G5 通过**（逐病例预算偏差 ≤5%，含已声明豁免）

> **机制说明**：[`../diagnosisarena_b02_compute_matched_v1/b02_vs_main_method_and_budget_match.md`](../diagnosisarena_b02_compute_matched_v1/b02_vs_main_method_and_budget_match.md)

## 1. 匹配方案（structural_proxy_v1）

与 DA 相同：从主方法 `shared_trees` 结构反推逐例预算（**不含**树候选/推理/金标）。

- 树根：`logs/open_xddx_ox_seq100_v1/compat_synonym_v1/frozen/shared_trees`
- Schedule：[`configs/paper_experiments/paper_v1_budget_schedule_open_xddx.jsonl`](../../configs/paper_experiments/paper_v1_budget_schedule_open_xddx.jsonl)

## 2. 运行设定

| 项 | 值 |
|---|---|
| 臂 | `B02-flat-compute-matched` |
| 子集 | `ox_seq100_v1`（100） |
| `list_k` | 5 |
| `budget_mode` | `matched` |
| 骨干 | `meta-llama/llama-3.3-70b-instruct` |
| 评分 | `paper_aligned_judge_v1` / Gemini 2.5 Flash |
| 并发 | infer `workers=50`；eval `workers=50` |
| 产物 | `runs/paper_v1/open_xddx_b02_compute_matched_v1/` |

## 3. 预算核验（G5）

| 维度 | mean rel err | n_mismatch |
|---|---:|---:|
| llm_calls | 0.000 | 0 |
| retrieval_calls | 0.000 | 0 |
| retrieval_snippets | 0.000 | 0 |
| unique_candidates | 0.000 | 0 |

- match_rate = **1.00**；G5 = **PASS**
- 明细：[`b02_compute_matched_budget_audit.md`](b02_compute_matched_budget_audit.md)
- 实际均值：llm=8.98 / retrieval_calls=9.64 / snippets=13.58 / uniq=17.12

## 4. 准确率（vs native B02）

| 臂 | 模式 | micro-P | micro-R | micro-F1 | Interp Acc |
|---|---|---:|---:|---:|---:|
| `B02-flat-matched-rerank` | native | 0.480 | 0.512 | 0.495 | 0.419 |
| `B02-flat-compute-matched` | matched | **0.464** | **0.495** | **0.479** | **0.445** |

观察：匹配主方法结构预算后，平面 retrieve→rerank 的 micro-F1 **略降**（0.495→0.479）；Interp Acc 略升。与 DA 一致：更高预算未转化为诊断 F1 优势。

正式评测：[`B02-flat-compute-matched/replicate_01/annotate/official_eval_llm/summary.md`](B02-flat-compute-matched/replicate_01/annotate/official_eval_llm/summary.md)

## 5. 复现

```bash
WORKERS=50 EVAL_WORKERS=50 JUDGE=llm \
  DATASETS=open_xddx \
  bash scripts/paper/run_b02_compute_matched_ox_mcr.sh
```
