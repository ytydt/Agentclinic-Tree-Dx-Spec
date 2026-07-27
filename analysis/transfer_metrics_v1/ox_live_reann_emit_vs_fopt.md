# OX live 重标注：emit+锁定F vs 无emit+锁定F

日期：2026-07-26
锁定预算：L1=4 / L2local=4 / between=2 / cand_max=6
短列表：fresh `closed_live_mac_supervisor` @ pool15/K5 + LLM judge
机器表：[`ox_live_reann_emit_vs_fopt.json`](ox_live_reann_emit_vs_fopt.json)

## 结果

| 臂 | P | R | F1 | LLM Interp Acc | ΔF1 vs 原live | live树写回 |
|----|---|---|-----|----------------|--------------|-----------|
| 原 closed_live（无重标） | 0.5660 | 0.6034 | 0.5841 | — | — | — |
| B00 | 0.5260 | 0.5608 | 0.5428 | 0.233 | −0.041 | — |
| MAC | 0.5520 | 0.5885 | 0.5697 | 0.221 | −0.014 | — |
| emit离线inject+fresh live（旧） | 0.5700 | 0.6077 | 0.5882 | — | +0.004 | — |
| **emit_v1 + locked F (live reann)** | 0.6253 | 0.6652 | **0.6446** | 0.366（366/1001） | **+0.061** | 100* |
| **no-emit + locked F (live reann)** | 0.6313 | 0.6716 | **0.6508** | **0.355（357/1007）** | **+0.067** | 100 |

Interp Acc：`judge=llm`，`ox.interpretation_consistency`（非 lexical）。

\* emit 臂 LLM 评测时树为 live；报告汇总前曾被误覆盖，写回计数来自 `case_results.annotated_tree_write`。

## 结论

1. **live 后验重标 + 锁定 F 预算**是主要增益来源：两臂相对原 closed_live（0.584）均提升约 +0.06 F1，且超过 B00/MAC/离线 emit。
2. **force-emit 未带来额外收益**：emit 臂全例 `force_emit_n_total=0`（缺口补叶未触发），F1（0.645）略低于无 emit 臂（0.651）。
3. 无 emit 臂说明：仅把 F 旋到重校准最优（L1=4 / L2local=4 / cand=6）并做在线后验写回，即可达到当前最优。

## 说明

- live 重标注：Config A（可选 force-emit）+ joint 局部证据 → 局部后验写回叶 + cand_max 截断 → 覆盖 `annotate/shared_trees` → fresh closed_live + LLM。
- 运行目录：
  - `logs/open_xddx_ox_seq100_v1/compat_synonym_emit_locked_live_v1`
  - `logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1`
- 编排脚本：`scripts/paper/run_ox_live_reann_arms.py`（已修：`--skip-annotate` 不再覆盖 live 树）。
- 机制学详解：[`ox_specific_mechanisms_explainer.md`](ox_specific_mechanisms_explainer.md)。
