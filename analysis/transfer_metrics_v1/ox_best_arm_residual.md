# OX 最优臂残差解剖（closed_mac_trace_rrf）

日期：2026-07-26
机器表：[`ox_best_arm_residual.json`](ox_best_arm_residual.json)

## 0. 口径

- 最优研究臂：`closed_mac_trace_rrf`（冻结 B06 doctor → 后验池映射 + RRF）
- 正式 micro-F1 来自 LLM judge summaries；逐例差分用 case_scores.f1
- FN 四桶：lexical thr=0.7，相对最优臂未命中金标

## 1. 正式 micro（LLM）

| 臂 | P | R | F1 |
|----|--:|--:|---:|
| gated_hybrid_mcr | 0.530 | 0.565 | 0.547 |
| MAC B06 | 0.552 | 0.588 | 0.570 |
| closed_mac_trace_rrf | 0.562 | 0.599 | 0.580 |

## 2. 逐例 ΔF1 稳健性

- vs MAC：win/tie/lose = **27/50/23**；mean ΔF1=0.0105，95% CI [-0.0275, 0.0461]
- vs gated：win/tie/lose = **25/58/17**；mean ΔF1=0.0329，95% CI [0.0003, 0.0658]
- Promote 口径：**mechanism_upper_bound_only**

## 3. FN 四桶（pool_n=12）

FN=212 / G=469；**主导桶 = Open**

| 桶 | 条数 | 占 FN | 占金标 |
|----|-----:|------:|-------:|
| Open | 137 | 64.6% | 29.2% |
| PoolMiss | 11 | 5.2% | 2.3% |
| RankMiss | 60 | 28.3% | 12.8% |
| MapLoss | 4 | 1.9% | 0.9% |

## 4. 池覆盖曲线（金标落在后验 Top-N）

| N | TP | R |
|--:|---:|--:|
| 5 | 222 | 0.473 |
| 12 | 315 | 0.672 |
| 15 | 325 | 0.693 |
| 20 | 330 | 0.704 |
| full | 330 | 0.704 |

## 5. MAC→池映射损耗

- doctor 名总数：1500
- 映射进池：861 (57.4%)
- 在全叶但不在池：40 (2.7%)
- 开集未映射：599 (39.9%)

## 6. D3 裁定

- 下一刀臂：**`tree_mac_pad_selective`**
- 理由：FN dominated by Open; paired ΔF1 vs MAC CI includes 0 → demote Promote to mechanism evidence.

## 7. 深挖落地结果（D2/D3）

| 臂 | 依赖 B06? | lexical F1 | LLM F1 | 裁定 |
|----|-----------|----------:|-------:|------|
| `closed_mac_trace_rrf` | 是（冻结 discussion） | 0.530 | 0.580 | **机制上界**（Δ vs MAC CI 含 0） |
| **`closed_live_mac_supervisor`** | **否**（池内 live panel） | **0.539** | **0.584** | **Promote 公平臂**（≥MAC，Δ vs gated ≈+3.7pp） |
| `tree_mac_pad_selective` | 是（predictions） | 0.458 | — | **否决**（lexical 未过门控） |

解读：
- Open 桶虽最大（≈全树缺叶率），选择性开集 pad 仍伤 F1 → 盲补洞无效。
- RankMiss 仍有 60 条；**去 MAC 依赖的 live 闭集 Supervisor** 已能追上并略超冻结 B06 映射臂，说明优势来自「池内多视角排序」而非外部开集 panel 本身。
- `closed_mac_trace_rrf` 不得再报为本方法正式 SOTA；公平对照用 `closed_live_mac_supervisor`。

## 8. 复现

```bash
PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ox_best_arm_residual.py --write-md

# 公平 live 闭集（需 gnn-llm + clashon）
PYTHONPATH=src:scripts:scripts/paper python3 scripts/paper/run_ox_mcr_official_eval.py \
  --dataset open_xddx \
  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 \
  --subset-parquet data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet \
  --judge llm --ddx-k 5 --workers 50 --build-projection \
  --ddx-source closed_live_mac_supervisor --pool-n 15 --live-closed-mac
```

