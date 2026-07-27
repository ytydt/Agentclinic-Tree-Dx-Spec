# OX←MAC 机制移植臂评测

日期：2026-07-26  
根因：[`ox_vs_mac_rootcause.md`](ox_vs_mac_rootcause.md) · 残差深挖：[`ox_best_arm_residual.md`](ox_best_arm_residual.md)  
树对照：`gated_hybrid_mcr` LLM F1=**0.547**；MAC B06 LLM F1=**0.570**

门控：F1≥0.570 或 ΔF1≥+1.5pp 且 P 不崩 >3pp。

## 结果（ox_seq100，K=5，Gemini 2.5 Flash）

| 候选 | `--ddx-source` | 依赖冻结 B06? | lexical F1 | LLM P | LLM R | LLM F1 | 门控 |
|------|----------------|:------------:|----------:|------:|------:|-------:|------|
| 基线树 | `gated_hybrid_mcr` | 否 | 0.466 | 0.530 | 0.565 | **0.547** | — |
| MAC | B06 | — | 0.477 | 0.552 | 0.588 | **0.570** | — |
| C1 机制上界 | `closed_mac_trace_rrf` | **是** | 0.530 | 0.562 | 0.599 | 0.580 | 机制证据（Δ vs MAC CI 含 0） |
| **C1 公平** | **`closed_live_mac_supervisor`** | **否** | **0.539** | **0.566** | **0.603** | **0.584** | **Promote** |
| C1b | `closed_pool_rrf` | 否 | 0.471 | 0.518 | 0.552 | 0.535 | 否决 |
| C3 | `multi_arm_rrf` | 否 | 0.466 | 0.506 | 0.539 | 0.522 | 否决 |
| C2 | `tree_mac_pad` | 是 | 0.462 | 0.518 | 0.552 | 0.535 | 否决 |
| C2s（Open 桶） | `tree_mac_pad_selective` | 是 | 0.458 | — | — | — | 否决（lexical） |

## 口径订正（重要）

1. **`closed_mac_trace_rrf` = 研究/机制上界**：复用冻结 B06 doctor lists；逐例 ΔF1 vs MAC 的 95% CI 含 0 → **不得** 作为本方法正式 SOTA。
2. **正式可报公平臂：`closed_live_mac_supervisor`**：后验 Top-15 池内 live 3-doctor + supervisor（prompt 闭集 + 后处理投影），**不依赖外部 MAC run**，LLM F1=0.584 ≥ MAC 0.570。
3. 残差 FN 主导桶为 **Open（≈全树缺叶）**，但选择性开集 pad 未能抬分 → 当前增益主要来自 **闭集排序/多样性**，不是开集补洞。

## 机制解读

- Live 闭集 panel ≈ 冻结 B06 映射臂 → H2（截断/排序）可 internally 解决。
- 树内自融（C3/C1b）不够；需要真正的多视角 LLM 排序。
- Open 金标 ~29% 仍是结构性上限；建树补叶（C4）才是下一阶段，而非提交窗 pad。
- **B00/B05 地板**：OX 上 Direct CoT 与 MDAgents 均 F1=0.543（[`ox_b00_b05_anomaly.md`](ox_b00_b05_anomaly.md)）；B05≈B00。live 对 B00 的逐例 Δ 亦 CI 含 0 → 对标应含强纯 CoT，而非只盯 MAC。

## 复现

```bash
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate gnn-llm
bash /home/wanghongyi/clashctl/clashon.sh

RUN=logs/open_xddx_ox_seq100_v1/compat_synonym_v1
PARQ=data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet

# 公平 C1（推荐正式分）
PYTHONPATH=src:scripts:scripts/paper python3 scripts/paper/run_ox_mcr_official_eval.py \
  --dataset open_xddx --run-dir "$RUN" --subset-parquet "$PARQ" \
  --judge llm --ddx-k 5 --workers 50 --build-projection \
  --ddx-source closed_live_mac_supervisor --pool-n 15 --live-closed-mac

# 残差审计
PYTHONPATH=src:scripts:scripts/paper python3 scripts/paper/audit_ox_best_arm_residual.py --write-md
```

产物：`annotate/official_eval_llm_closed_live_mac/`、`eval_projection_closed_live_mac/`、`cache/closed_live_mac_supervisor.json`

机制学详解（与预算锁定、后验写回的协同）：[`ox_specific_mechanisms_explainer.md`](ox_specific_mechanisms_explainer.md)

## 代码

- 投影：[`scripts/paper/build_eval_projection.py`](../../scripts/paper/build_eval_projection.py)
- 评测：[`scripts/paper/run_ox_mcr_official_eval.py`](../../scripts/paper/run_ox_mcr_official_eval.py)（`--live-closed-mac` / `--mac-trace` / `--mac-predictions`）
- 残差：[`scripts/paper/audit_ox_best_arm_residual.py`](../../scripts/paper/audit_ox_best_arm_residual.py)
