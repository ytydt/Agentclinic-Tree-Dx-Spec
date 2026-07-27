# OX emit_v1 + 锁定组合 — 正式 LLM 门控（Stage 3）

协议：`paper_aligned_judge_v1`  
新臂：`emit_v1` + locked budget 代理 + **fresh** `closed_live_mac_supervisor` @ pool=15 / K=5  
机器表：[`ox_emit_locked_llm_gate.json`](ox_emit_locked_llm_gate.json)  
路径总文：[`ox_emit_rerank_path.md`](ox_emit_rerank_path.md)

## 对照表（micro）

| 臂 | P | R | F1 |
|----|---|---|-----|
| B00 | 0.526 | 0.561 | 0.543 |
| MAC B06 | — | — | 0.570 |
| gated_hybrid_mcr | — | — | 0.547 |
| closed_live (no emit) | 0.566 | 0.603 | 0.584 |
| emit remap（参考） | 0.568 | 0.606 | 0.586 |
| **emit_v1 + fresh live** | **0.570** | **0.608** | **0.588** |

## 逐例 ΔF1

- emit − live：mean≈+0.003，95% CI 含 0  
- emit − B00：mean≈+0.040，95% CI **[-0.004, +0.082]**（含 0）

## 门控

- 结果：**REJECT**
- F1≥0.570 或 vs live ΔF1≥+1.5pp 且 P 掉≤3pp：**过**（F1=0.588）
- vs B00 95% CI 下界 >0：**未过**
- 全树 R 不降：**过**

## 边界

- 正式臂为 emit overlay 树上的 fresh closed_live（非冻结 B06 补叶）。
- 预算 L1=4 / L2local=4 / cand6 为离线代理锁定；本 LLM 臂未做 live 证据重 annotate。
- `E_open_oracle` 未进入正式分。
