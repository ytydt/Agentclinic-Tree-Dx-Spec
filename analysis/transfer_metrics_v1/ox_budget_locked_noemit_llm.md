# OX：无 emit + 重校准锁定参数 — LLM 对照

问题：不用 force-emit，仅用 Stage2 锁定的 F/预算与短列表参数，LLM 表现如何？

锁定参数：`L1=4`，`L2 local=4`，`cand_max=6`，`pool=15`，`K=5`，`closed_live_mac_supervisor`。

**重要边界**：证据预算在此为离线家族/叶保留代理（截断子叶），**不是** live 重跑 F2/F4/F6 证据轮。短列表侧与既有无 emit live（pool15）同族。

机器表：[`ox_budget_locked_noemit_llm.json`](ox_budget_locked_noemit_llm.json)

## LLM micro

| 臂 | P | R | F1 |
|----|---|---|-----|
| B00 | 0.5260 | 0.5608 | 0.5428 |
| MAC | 0.5520 | 0.5885 | 0.5697 |
| 无 emit live（原树，已有） | 0.5660 | 0.6034 | 0.5841 |
| 无 emit + 预算代理 + live remap | 0.5680 | 0.6055 | 0.5862 |
| 无 emit + 预算代理 + fresh live | 0.5600 | 0.5970 | 0.5779 |
| emit_v1 + fresh live（对照） | 0.5700 | 0.6077 | 0.5882 |

## 逐例 ΔF1（fresh live 预算代理 vs 对照）

- vs 无 emit 原 live：mean=-0.007222222222222222 CI[-0.01930303030303031, 0.004954545454545457]
- vs B00：mean=0.02935137085137085 CI[-0.01448412698412698, 0.07158369408369408]

## 一句话

无 emit 仅套锁定参数（预算代理+closed_live）LLM F1=**0.578**，相对原无 emit live **0.584** 为 -0.006。
