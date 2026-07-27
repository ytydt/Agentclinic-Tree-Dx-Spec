# OX 正式评测异常根因审核

状态：审计结论（非正式 claim）  
日期：2026-07-26  
范围：`logs/open_xddx_ox_seq100_v1/compat_synonym_v1`  
复算脚本口径：`transfer_eval.matching.greedy_set_match` + `leaf_match_score≥0.7`（lexical）

---

## 0. 一句话结论

**不是算子写错，是三套不可比指标被横比。**

| 用户看到的“异常” | 实测 | 根因 |
|------------------|------|------|
| micro-P 远低于 mapping | 主表 LLM P=**0.50** vs mapper `option_top1`=**0.80** | **任务不同 + 列表不同**；同列表开放评测 P≈**0.81** |
| micro-R 远低于全 L2 的 R | 主表 LLM R=**0.53** vs 全叶 lexical R=**0.70** | **Top-5 截断丢掉 ~108 个 TP**；全叶 R 是覆盖上界，不是正式表 |

---

## 1. 三套指标各自量什么

| 名称 | 定义 | 分母 | 本 run 输入列表 |
|------|------|------|----------------|
| **Official micro-P** | \(\sum tp / \sum \|pred\|\)（一对一贪心集合匹配） | 预测诊断条数 | 默认：全局叶后验 **Top-5**（\|pred\|=500） |
| **Official micro-R** | \(\sum tp / \sum \|gold\|\) | 金标 `ddx_set` 条数（均值 4.69，∑=469） | 同上 |
| **Mapper `option_top1`** | 金标 MCQ 选项的 `gold_option_rank≤1` | **病例数**（Hit@1） | compat `final_ranking` 短列表（均值 **1.72**） |
| **全 L2 R**（审计用） | 同上 micro-R，但 pred=树上全部叶去重 | 金标条数 | 均值 **16.9** 叶 |

代码锚点：

- Official：`scripts/paper/transfer_eval/ox_metrics.py` + `matching.py`
- Mapper：`annotate/mapper/summary.json`（`option_top1=0.80`）
- 投影：`build_eval_projection.py`（`top_leaf_posterior` vs `ddx_from_compat_ranking`）

---

## 2. 复算对照表（同一金标、同一 lexical 匹配）

| 候选源 | 均长 | micro-P | micro-R | micro-F1 | 备注 |
|--------|-----:|--------:|--------:|---------:|------|
| 全局叶后验 Top-5 | 5.00 | 0.444 | 0.473 | 0.458 | ≡ `official_eval` lexical |
| compat `final_ranking` | 1.55 | **0.723** | 0.239 | 0.359 | 与 mapper 同列表家族 |
| **全部 L2 叶** | 16.87 | 0.196 | **0.704** | 0.306 | 覆盖上界；P 崩 |
| 后验 **仅 Top-1**（集合大小=1） | 1.00 | **0.740** | 0.158 | 0.260 | 数量级接近 mapper |

已落盘 LLM 正式表：

| 臂 | micro-P | micro-R | micro-F1 |
|----|--------:|--------:|---------:|
| `official_eval_llm`（后验 Top-5） | 0.500 | 0.533 | 0.516 |
| `official_eval_llm_compat`（短列表） | **0.806** | 0.284 | 0.420 |
| `official_eval_llm_compat_then_pad` | 0.508 | 0.542 | 0.524 |

**桥接事实**：开放集合评测若改用 **与 mapper 相同的 compat 短列表**，micro-P=**0.806 ≈ option_top1=0.80**。主表 P=0.50 并非“漏算 mapping”，而是换了更长的开放列表。

---

## 3. 根因分解

### 3.1 micro-P ≪ mapper（H1+H3，主因）

1. **语义不同**：mapper 是闭集 MCQ 病例 Hit@1；micro-P 是开放 DDx 集合 precision。不可代数替换。
2. **列表不同**：mapper / compat 均值 ~1.7 条（高精）；主表固定灌 **5** 条。
3. **稀释效应**（同树后验序，对“是否命中任一金标”的粗命中率）：  
   rank1→5 ≈ **0.74 / 0.64 / 0.53 / 0.43 / 0.36**。  
   贪心一对一后 micro-P=0.444（lexical）；尾部低质叶拉低分母侧精度。
4. **非 bug 证据**：复算与 `official_eval/summary.json` 逐位一致；金标 `|ddx|` 均值 4.69（非整例 Right Option）。

### 3.2 micro-R ≪ 全 L2 R（H2，主因）

| 量 | 值 |
|----|---:|
| 全叶匹配 TP（lexical） | 330 |
| Top-5 匹配 TP | 222 |
| **截断丢掉的 TP** | **108** |
| 全叶 R | 0.704 |
| Top-5 R | 0.473 |

机制：金标 ~4.7 条，全树 ~17 叶已覆盖其中 ~70%；截到 K=5 后，排在 6+ 的真阳不可见。  
这是 **§5.4 已写明的设计取舍**：全叶 R 高但 P=0.20，不能当正式提交列表。

### 3.3 次要因素（不解释量级差）

| 因素 | 影响 |
|------|------|
| LLM vs lexical | 同投影 Top-5：P/R 0.444/0.473 → 0.500/0.533（+~0.06），解释不了 vs 0.80 |
| 后验序 ≠ compat/joint 序 | case 级命中模式分叉（mapper@1 vs 后验 Top1∈gold：both=62, map_only=18, set_only=12） |
| compat merge 过短 | 解释 **compat 臂** R=0.28；主表改 Top-5 正是为抬 R |

---

## 4. 正确读表方式

| 问题 | 应读 | 勿与…横比 |
|------|------|-----------|
| 开放 DDx 质量（正式形态） | `official_eval_llm` 的 **P/R/F1 分列** | mapper `option_top1` |
| 与 mapper **同列表**的开放 precision | `official_eval_llm_compat`（P≈0.81） | 主表 Top-5 P |
| 树池覆盖上界 | 全 L2 R（本审计 0.70）或 gap §5.4 | Top-K micro-R |
| 长度对齐后的折中 | `compat_then_pad`（P/R≈0.51/0.54） | 单独吹 P 或单独吹 R |

**判定**：当前 OX 主表数字与 mapper / 全 L2 的落差是 **协议预期行为**，不是实现故障。若论文叙述把 0.50 的 micro-P 写成“接近 mapping 0.80”或把 0.53 的 R 写成“接近全叶覆盖”，才会构成表述错误。

---

## 5. 建议（工程 / 写作）

1. 所有 OX summary / 基线总表继续保留 boundaries：**禁止与 mapper option_top1 混表**。
2. 若需“对齐 mapping 量级”的监控列：并列 `compat_list micro-P` 或 `option_top1`，标注闭集。
3. 若需“对齐全叶覆盖”的监控列：并列 `full_L2_recall`（审计协议名建议 `pool_coverage_full_l2_v1`），**不进**正式 Eq.1 主表。
4. 无需为“抬 P 到 0.8”而把正式 `pred_ddx` 改回 compat 短列表——那会把 R 打回 ~0.28（已在 `official_eval_llm_compat` 证实）。

相关：Recall 分型根因见 [`ox_recall_low_rootcause_audit.md`](ox_recall_low_rootcause_audit.md)。
