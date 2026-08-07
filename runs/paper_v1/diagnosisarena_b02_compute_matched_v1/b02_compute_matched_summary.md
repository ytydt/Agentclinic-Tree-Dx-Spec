# B02 compute-matched（DA d2_seq100）汇总

生成时间：2026-07-27  
状态：**G5 通过**（逐病例预算偏差 ≤5%，含已声明豁免）

> **机制说明（与主方法区别 + 预算匹配实现）**：  
> [`b02_vs_main_method_and_budget_match.md`](b02_vs_main_method_and_budget_match.md)

## 1. 匹配方案（structural_proxy_v1）

因 M00 尚无正式 token/call 账本，从主方法 `shared_trees` 结构反推逐例预算（**不含** M00 候选/推理/金标）：

| 维度 | 来源 | 映射到 B02 |
|---|---|---|
| `unique_candidates` | L2 叶数 `n_leaf` | 候选生成目标长度 |
| `retrieval_snippets` | `clamp(n_static, 8, 24)` | `max_chunks` |
| `retrieval_calls` | `n_queries × 2`（双索引） | 固定查询数（可 >4） |
| `llm_calls` | `cand_batches + 1(fill) + n_l1 + 1(rerank)` | 候选批 + 平面 evidence 轮 + rerank |

声明：

- 协议名：`structural_proxy_v1`（非官方 token ledger；token 维 `deferred_no_m00_ledger`）
- B02 **只读数值上限**，不读树候选/结果
- `unique_candidates`：允许 ±1 绝对松弛；若 LLM 预算用尽且覆盖 ≥80%，记 `llm_diversity_cap`（本 run：1 例）

Schedule：[`configs/paper_experiments/paper_v1_budget_schedule_diagnosisarena.jsonl`](../../configs/paper_experiments/paper_v1_budget_schedule_diagnosisarena.jsonl)

## 2. 运行设定

| 项 | 值 |
|---|---|
| 臂 | `B02-flat-compute-matched` |
| 子集 | `d2_seq100_v1`（100） |
| `budget_mode` | `matched` |
| 骨干 | `meta-llama/llama-3.3-70b-instruct` |
| 评分 | Mapper `typed_llm_disagreement_rag` |
| 产物 | `runs/paper_v1/diagnosisarena_b02_compute_matched_v1/` |

## 3. 预算核验（G5）

| 维度 | mean rel err | n_mismatch |
|---|---:|---:|
| llm_calls | 0.000 | 0 |
| retrieval_calls | 0.000 | 0 |
| retrieval_snippets | 0.000 | 0 |
| unique_candidates | 0.000 | 0 |

- match_rate = **1.00**；G5 = **PASS**
- 明细：[`b02_compute_matched_budget_audit.md`](b02_compute_matched_budget_audit.md)
- 实际均值：llm=9.24 / retrieval_calls=12.02 / snippets=17.18 / uniq=17.78（与 schedule 对齐）
- `llm_diversity_cap`：`diagnosisarena__000249`

## 4. 准确率（vs native B02）

| 臂 | 模式 | @1 | @2 | MRR@2 |
|---|---|---:|---:|---:|
| `B02-flat-matched-rerank` | native（固定 2 LLM / 4 query） | 0.56 | 0.63 | 0.595 |
| `B02-flat-compute-matched` | matched（本 run） | **0.48** | **0.59** | **0.535** |

观察：在匹配主方法结构预算后，平面 retrieve→rerank **未**因更高调用/候选预算而提升；相对 native 略降。支持「收益不来自额外计算」叙事的 matched 对照。

## 5. 复现

```bash
bash scripts/paper/run_b02_compute_matched_d2_seq100.sh
# 或
python3 scripts/paper/build_budget_schedule.py --dataset diagnosisarena
PYTHONPATH=src:scripts:scripts/paper python3 scripts/paper/run_baseline.py \
  --arms B02-flat-compute-matched \
  --budget-mode matched \
  --budget-schedule configs/paper_experiments/paper_v1_budget_schedule_diagnosisarena.jsonl \
  --subset-dir data/benchmarks/diagnosisarena/subsets/d2_seq100_v1 \
  --runs-root runs/paper_v1/diagnosisarena_b02_compute_matched_v1 \
  --workers 20 --score --mapper-mode typed_llm_disagreement_rag
```
