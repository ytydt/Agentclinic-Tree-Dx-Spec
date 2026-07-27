# L1 金标召回审计：20 例自动 `L1_MISS` 拆分

**协议**：[`protocol.md`](protocol.md)  
**表**：[`l1_miss_case_audit.tsv`](l1_miss_case_audit.tsv)  
**摘要**：[`l1_gold_recall_summary.json`](l1_gold_recall_summary.json)  
**审查覆盖**：20/20（`reviewer=agent_semi_auto_v1`；high 置信 17，medium 3）

---

## 1. 一句话结论

**80% AutoCoverage 缺口（20 例）主因是 `MAPPER_UNBIND`（映射/叶绑定失败导致的假 MISS，18/20=90%）；真·树上无可用父 `TREE_PARENT_ABSENT` 仅 2 例；`PARENT_NOT_IN_L1_SET`=0。**

因此：默认整合应优先 **映射修复 / 叶—选项绑定**，而非开放无限扩 L1 族；扩族仅针对少数真缺父（及未来盲法新发现）。

---

## 2. 漏斗分层

| 桶 | n | 占比 | 含义 |
|----|--:|-----:|------|
| `MAPPER_UNBIND` | **18** | **0.90** | 树上有可接受父（13 例还有金标近义叶），AutoCoverage 因 mapper 未绑而失败 |
| `TREE_PARENT_ABSENT` | **2** | **0.10** | 轴错位：树族无法合理容纳金标诊断 |
| `PARENT_NOT_IN_L1_SET` | **0** | 0 | 本批未见「父在树但不在 `l1_posteriors`」 |
| `L1_PRESENT_OK` | 0 | — | 不在 MISS 集合 |

全量 100 例视角：

| 量 | 值 |
|----|----:|
| AutoCoverage | 0.80 |
| 半自动修正后近似 TreeParentPresent | ≈ **0.98**（98/100；仅 67、231 真缺父） |
| 真·L1CandidateRecall（相对树父） | 对本批可接受父均已在 `l1_posteriors`（0 例 `PARENT_NOT_IN_L1_SET`） |

---

## 3. 与 mapper / 叶的交叉

| 观察 | n / 说明 |
|------|----------|
| `mapper_matched=False` | **20/20** |
| 树上存在金标近义叶 | **13/20**（如 Sweet、RCVS、JDM、SC-PMVT、Rheumatoid meningitis…） |
| mapper `relation=equivalent` 但仍未绑叶 | 至少 **97、129**（投影空 `matched_leaf_ids`） |
| `parent_source=none`（自动） | 20/20（与上轮 rank-gap 一致） |

典型假 MISS：case **27** 树叶即 `Histiocytoid Sweet Syndrome`（B2），但 mapper `unrelated` → AutoCoverage 记 MISS。

---

## 4. 真缺父两例（`TREE_PARENT_ABSENT`）

| case | gold | 问题 |
|------|------|------|
| **67** | Septic shock with anuric kidney failure | 树轴为「伴 CNS 受累」的系统病；无合适全身脓毒症/休克 L1 |
| **231** | Stage IV invasive renal urothelial carcinoma | 树轴为副肿瘤皮肤表现 / papillomatosis；金标是原发尿路上皮癌分期 |

这两例才适合 Track C 式「开放提议家族 + 树归一」或建树轴校正；**不要**用它们外推全部 20 例。

---

## 5. 与 compat @1 失败的交叉（已知量级）

上轮分析：compat_parallel 的约 **28** 例 option @1 失败中，约 **20/28** 落在自动 `L1_MISS`。  
本审计表明其中绝大多数是 **映射假 MISS**，不是「缺 L1 分支」。  
因此「修 coverage → compat 软上界 +0.08」的叙事须改写为：

- 修 **mapper/叶绑定** 可能同时抬 AutoCoverage 与 option；  
- 修 **L1 扩族** 只对 ~2% 真缺父有直接召回收益。

---

## 6. 中期分流（协议 §3）

| 若主因是… | 本轮判定 | 设计含义 |
|-----------|----------|----------|
| `MAPPER_UNBIND` | **成立（主导）** | Track B 默认：**绑定修复、叶反推父、AutoCoverage 去假**；扩族降优先 |
| `TREE_PARENT_ABSENT` | 少数（2） | Track C 小样本探索 / 轴注入 |
| `PARENT_NOT_IN_L1_SET` | **未观察到** | 暂不优先「把树上父塞进后验集」类补丁 |

---

## 7. 局限

- 半自动临床父判定，非独立双盲专家；medium 置信 3 例（11、188、242）可修订。  
- 「可接受父」允许同病多轴（偏乐观 TreeParentPresent）。  
- 未重跑 mapper；绑定失败根因（typed 过严 / 空 ranking / 同义未命中）需映射专项另开。

产出：本文件 + TSV + summary JSON。
