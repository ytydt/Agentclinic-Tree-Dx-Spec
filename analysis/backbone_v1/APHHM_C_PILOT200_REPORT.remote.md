# APHHM-C 落地与 200×2 试点测试报告

设计依据：[`APHHM_COMPACT_REDESIGN.md`](../../APHHM_COMPACT_REDESIGN.md)
实现：`src/agentclinic_tree_dx/aphhm_c.py`、`scripts/paper/run_aphhm_c.py`、6+1 个 `aphhm_c_*.txt` prompt
数据：DA200（`d2_seq100` + `d2_heldout100`）、MCR200（`mcr_v1` + `mcr_v2`）；模型 `meta-llama/llama-3.3-70b-instruct`
日期：2026-08-08
端点迁移修订：2026-08-13（基于 commit `71861b3e` 所含 79 臂 model-panel census 与根级综合）

> **2026-08-13 端点迁移后的阅读口径。** 本报告是历史试点与机制探索记录；下文原始 `concept`、`dc.match`、`dc.any_match`、pool recall、`conv|both` 和相应 p 值为 legacy-chain/片段匹配时代的历史数值，保留用于复核实验轨迹，不能改名为 clinical-complete，也不能直接进入当前能力榜。统一端点合同、79 臂盲法模型面板迁移和根级综合分别见 [`ALL_ARM_ENDPOINT_MIGRATION/REPORT.md`](../mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION/REPORT.md) 与 [`CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md`](../mechanism_v2/CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md)。
>
> **最初 APHHM-C 的结论仍是 No-Go，但理由已被校准。** 结构合同全部通过；确定性 ledger 排序在历史 safe/legacy 下只把约 28% 的已命中 reference 转成 Top-1，换成病例证据 selector 后 MCR 明显改善，因此“冻结分数足以替代比较器”被证伪。后续 `Collapse3c`、`MultiStance` 与 `MSplit` 的历史数值仍说明候选 admission、证据和比较结构均重要，却不能再据此宣布某个配置为 clinical winner。
>
> **旧 §17.3 的两条直线不是确定律、因果系数或 selector 上限。** 它们只是 14 个相关臂、异质切片上的 historical legacy-chain arm-level descriptive OLS：DA `conv = 0.736 − 0.0469×width`，MCR `conv = 0.820 − 0.0453×width`。E5 在冻结共享候选/顺序、base pool 已含 reference 的局部干预中，确实复现了约 **−4.48pp/新增候选**的九臂 joint-common-served model-panel complete 损失；但 DA/MCR、候选类型和干扰机制高度异质。E4 又在**同一个候选池**上仅换证据整合/selector 就把 model-panel complete 从 7.75% 抬到 17.25%，E9 的真实多视图相对单视图反而取得 +3.25pp complete（Holm `q=.01328`）。因此当前可写结论是“无门控的 flat fixed-k 扩池会造成候选干扰”，不是“conversion 只由 width 决定”或“coverage 与 conversion 数学上不可兼得”。
>
> **当前工程默认改为 Lite-like：两次独立 proposal + 一次冻结池 comparator。** `Collapse3c` 在 E2 800 例根审计中 clinical-complete 为 15.25%，是 specificity-retention reference；`MultiStance` 为 15.12%，两者净差仅 1/800，且没有总体确认性胜者。Lite 的 13.25% 并非最高，但接口简单、served 稳定，复杂替代品尚未证明净益。下一版应把 `Collapse3c` 的 specificity retention 融入 Lite comparator，而不是把 `Collapse3c` 或任何更宽系统直接设为默认。
>
> `d2_heldout200b` / `mcr_200b` 虽按原协议预留，但完整 800 例已经被反复用于算法开发和机制分析，故现在全部属于 **development evidence**，不得再称 external/sample-out confirmation。79 臂迁移完成的是 Top-1 全病例模型面板 census；它没有对旧 14 臂每个 pool candidate 做 clinical relation census，因而**不能**重算旧 14 臂的 clinical pool exposure 或 clinical exposure→Top-1 conversion。该缺口必须通过 full-pool adjudication 或新的冻结池随机实验解决。

---

## 1. 实现范围

严格按设计文档落地，未做偏离：

| 槽位 | 模块 | 固定 | 说明 |
|---|---|---:|---|
| C1 | `AphhmCFactLedger` | 是 | observed fact ledger，raw span 逐字、provisional 分栏、correlation_group |
| C2 | `AphhmCAxisContract` | 是 | family scope_in/out + fact_coverage + recall_placement + anchor 审计 |
| — | `AxisGuard` | — | 确定性，五类风险向量，**无 LLM 调用** |
| C3 | `AphhmCBatchedConcepts` | 是 | 一次展开全部 family，按 unique concept 计预算 |
| C3b | `AphhmCComplement` | 否 | gap lane，≤2 个且必须绑定未覆盖高特异 fact |
| C4 | `AphhmCGlobalMatrix` | 是 | 全局 `fact × concept` 矩阵；仅按 fact 行分块 |
| — | P3/P4/P5 + 确定性打分 + tie-break | — | 离线规则块，**无 LLM 调用** |
| C5 | `AphhmCAdjudicator` | 否 | 只改争议 cell，可 abstain，改后确定性重算 |

实测预算：**均值 4.64 calls**（分布 4/5/6），符合设计的「普通 4、困难 5–6」。

## 2. 结构性成功标准（设计 §10.4，实现可保证）

`scripts/paper/test_aphhm_c_unit.py` 8 项全过，400 例运行期指标同样为零违规：

| 标准 | 实测 | 结果 |
|---|---|---|
| 已解析 `same_as` concept 重复占位 = 0 | `resolved_duplicates_max=0` | 通过 |
| 全局计分前无 local champion hard-prune | `n_active_concepts == n_concepts`（8.19/8.19） | 通过 |
| 候选无事件不得消失 | `unexplained_disappearance_total=0` | 通过 |
| 默认 final rank 与 ledger rank 无 inversion | `ledger_final_inversion_total=0` | 通过 |
| P5 不增加在线 selector 调用 | 模块调用序列中无 P5 | 通过 |
| P3 矩阵完整率 | `1.000` | 通过 |

其余机制量：families 3.42、facts 11.56（decisive 3.57）、unique concepts 8.19、P4 准入 cell 21.9、P5 shared-phenotype veto 12.8、scope-error veto 0.05、gap lane 触发率 0.29、verifier 触发率 0.35（平均只改 0.13 个 cell）。

设计预期的三条退化通道确实被关闭了：跨 parent 重复归零（原 APHHM 重复比例中位数 47.2%）、无局部冠军瓶颈、排序状态单一权威。

## 3. 经验性结果（DA200 / MCR200，与全部同口径方法对照）

task = DA option@1 / MCR official `diagnostic_hit`；concept = `dc.match(champion, gold)`。

| 方法 | calls | DA200 task | DA200 concept | MCR200 task | MCR200 concept |
|---|---:|---:|---:|---:|---:|
| **APHHM-C** | 4.64 | 0.5950 | **0.1200** | **0.1150** | **0.1050** |
| **APHHM-C+sel**（消融，§5） | 5.29 | 0.5700 | 0.1550 | 0.1750 | 0.1650 |
| **APHHM-C+wide**（消融，§6） | 5.29 | 0.5750 | 0.1600 | 0.2050 | 0.1900 |
| **APHHM-C+rich**（消融，§6） | 5.29 | 0.5650 | 0.1500 | 0.2100 | 0.1850 |
| **APHHM-C+clean**（消融，§6） | 5.29 | 0.5400 | 0.1550 | 0.2250 | 0.1900 |
| **NoAxis**（去轴，§8） | 4.28 | 0.5700 | 0.1800 | 0.2100 | 0.1850 |
| **Collapse3**（收缩，§9） | 3.38 | 0.5950 | 0.1800 | 0.2600 | 0.2150 |
| **Collapse3w**（收缩+宽，§9） | 3.40 | 0.6000 | 0.2150 | 0.2500 | 0.2150 |
| **Collapse3c**（承诺契约，§12） | 3.31 | 0.6050 | 0.1850 | **0.2900** | 0.2150 |
| Forest | 4.06 | **0.6650** | 0.2700 | 0.2600 | 0.2600 |
| IMPC | 4.00 | 0.6250 | 0.2900 | 0.2250 | 0.2300 |
| MAC | — | 0.6100 | **0.3000** | **0.2700** | **0.3150** |
| Lite | 3.00 | 0.6000 | 0.2700 | 0.2500 | 0.2350 |
| B07 | 3.00 | 0.5700 | 0.2550 | 0.2450 | 0.2800 |
| e7 | 6.00 | 0.5850 | 0.2050 | 0.2550 | 0.1850 |
| v0 | 4.00 | 0.5650 | 0.1850 | 0.2250 | 0.1750 |
| APHHM（原） | — | 0.5900 | 0.2000 | 0.2600（n=100） | 0.1900（n=100） |

APHHM-C 的 DA task 0.595 落在基线区间内，但这是 mapper 把错误 concept 映射到正确选项的结果；一旦看不受 mapper 保护的三个指标，它是全表最低。McNemar（对手 − APHHM-C）：

- `mcr_task`：Forest 32-3、MAC 32-1、B07 30-4、Lite 30-3，全部 p<0.0001；
- `mcr_concept`：MAC 43-1、B07 37-2、Forest 34-3，全部 p<0.0001；
- `da_concept`：MAC 39-3、IMPC 40-6、Forest 37-7，全部 p<0.0001；
- `da_task`：与所有方法均无显著差异（Forest 38-24，p=0.098）。

上表按调用数排序时，走到最后的 `Collapse3w`（3.40 calls）与 Lite（3.00 calls）四指标全部不显著（§9.6），而 `Collapse3c`（3.31 calls）拿到全表最高的 MCR task 0.2900（§12.2）但 DA concept 退回 0.1850（§12.3）。中间八个消融臂（+sel / +wide / +rich / +clean / K10 / K6 / K4 / NoCond / CandEv）的完整数字见 `aphhm_c_pilot200.json`，本文只在对应小节引用它们各自要回答的那个问题。

## 4. 第一层定位：排序先于候选覆盖

（本节在 K=10 的默认宽度下比较，结论是候选覆盖够用、排序是首要瓶颈。第 7.3 节会在**同宽度**下重做这个比较，届时生成侧也会暴露问题——两者不矛盾：APHHM-C 是用近两倍的 slot 换到与 Forest 相当的覆盖。）

候选存活链（金标是否出现在各阶段）：

| 阶段 | APHHM-C DA200 | APHHM-C MCR200 | Forest DA200 | Forest MCR200 |
|---|---:|---:|---:|---:|
| registry recall | 0.425 | 0.375 | 0.455 | 0.360 |
| post-score frontier | 0.380 | 0.275 | — | — |
| final top-1 | 0.120 | 0.105 | 0.270 | 0.260 |
| **registry → top-1 转化率** | **0.282** | **0.280** | 0.593 | 0.722 |

在这个宽度下生成侧够用：unique concept 8.19 个、无重复占位、recall 与 Forest 同量级。损失几乎全部发生在计分之后，且有两段：

1. **打分把金标挤出 frontier**：MCR 上 0.375 → 0.275，即已生成的金标有 27% 在进入展示集前就被 score 压到 6 名之外；
2. **ledger rank 选不出冠军**：金标留在 registry 时，其 ledger 名次几乎均匀铺在 1–8 位（DA：24/22/12/11/6/5/4/1）。

用存档 ledger 做的离线重放（无新调用）最能说明问题——**确定性证据分排序还不如直接取生成器吐出的第一个候选**：

| 排序变体 | DA200 top-1 | MCR200 top-1 |
|---|---:|---:|
| A 当前 ledger score | 0.135 | 0.110 |
| B 加 generation-support tie-break | 0.135 | 0.110 |
| C score + 0.3×generation support | 0.140 | 0.110 |
| D 只数 admitted rule_in | 0.145 | 0.115 |
| E 只数 generation support | 0.170 | 0.140 |
| **F 生成顺序（完全不用矩阵）** | **0.185** | **0.160** |

（表内为同一批 stage 文件上的重放口径，与第 3 节 0.120/0.105 的差异来自重放未套用 protected-lane 状态写回。）

也就是说，C4 矩阵经 P3/P4/P5 与冻结序数映射之后，**净效果是抹掉而不是提取了排序信号**。原因可从机制量直接看到：约 94 个 cell 里只有 21.9 个通过 P4 准入，其中 12.8 个被 P5 判为 shared phenotype；剩余稀疏且低分辨的 cell 造成 23.5%(DA)/26.5%(MCR) 的病例 top-1 与他人同分，此时排序退化为 tie-break 顺序。

## 5. 第一个消融：确定性排序约束值多少

`APHHM-C+sel` 与 `APHHM-C` 共用同一份 LLM 缓存，C1–C4 输出逐字相同，**只把最终排序换成对 post-score frontier 的一次受限 selector 调用**（设计 §4.3 明令禁止的那条通道）。

| 指标 | APHHM-C | +sel | A−B wins | p |
|---|---:|---:|:--:|---:|
| da_task | 0.5950 | 0.5700 | 17-12 | 0.458 |
| da_concept | 0.1200 | 0.1550 | 5-12 | 0.143 |
| mcr_task | 0.1150 | 0.1750 | 0-12 | **0.00049** |
| mcr_concept | 0.1050 | 0.1650 | 0-12 | **0.00049** |

放开这条约束在 MCR 上显著有效且**零损失**（0-12，没有一例被改坏），代价是 +0.65 calls。但它只把 registry→top-1 转化率从 0.28 抬到 0.37/0.44，仍显著低于全部基线（+sel vs B07：mcr_concept 7-30，p=0.0002）。**排序约束是主因之一，但不是全部**——frontier 之前的 score 已经先丢掉了一部分金标。下一节沿这条线继续放开到边际收益为零。

## 6. 修复尝试：三级消融梯子

沿第 4 节的定位，把「排序」这一路依次放开。四个臂共用**同一份 LLM 缓存**，C1–C4 输出逐字相同，唯一差别在最终定序，因此差值可直接归因：

| 臂 | 与上一级的唯一差别 | shortlist |
|---|---|---|
| `+sel` | 定序从 ledger 换成一次受限 selector 调用 | post-score frontier（4.59） |
| `+wide` | score 不再剪裁 shortlist | 全部 active concept（8.19） |
| `+clean` | 撤掉 score 字段与名次顺序两个锚点 | 全部 active，按生成顺序 |

| 指标 | APHHM-C | +sel | +wide | +clean | base−clean wins | p |
|---|---:|---:|---:|---:|:--:|---:|
| da_task | 0.5950 | 0.5700 | 0.5750 | 0.5400 | 25-14 | 0.108 |
| da_concept | 0.1200 | 0.1550 | 0.1600 | 0.1550 | 7-14 | 0.189 |
| mcr_task | 0.1150 | 0.1750 | 0.2050 | **0.2250** | 2-24 | **0.00001** |
| mcr_concept | 0.1050 | 0.1650 | 0.1900 | **0.1900** | 4-21 | **0.00091** |

registry→top-1 转化率同步抬升：MCR 0.280 → 0.440 → 0.507 → 0.507，DA 0.282 → 0.365 → 0.376 → 0.365。

三点结论：

1. **收益几乎全部来自第一步**。放弃确定性定序拿走大部分增量；`+wide`（mcr_task 1-7，p=0.070）与 `+clean`（2-6，p=0.289）单看都不显著，只有累计的 base→clean 显著。
2. **MCR 上任务级已追平**：`+clean` 与 IMPC 打平（mcr_task 13-13，p=1.00），与 B07（p=0.597）、Forest（p=0.265）均无显著差异。
3. **concept 级仍然全面落后**，且这是没有被修复的那一半：`+clean` vs Forest 的 da_concept 5-28（p=7e-5）、mcr_concept 5-19（p=0.0066）；vs B07 的 da_concept 7-27（p=0.0008）、mcr_concept 9-27（p=0.0039）。DA 侧四个臂几乎不动（0.155±0.005），因为 DA 的 frontier 泄漏本来就小（0.425→0.380），放宽 shortlist 换来的召回不足以抵消 8 个候选带来的干扰。

转化率天花板也说明问题：即便给 selector 全部候选和全部证据，MCR 转化率停在 0.507，而 Forest 用更少候选拿到 0.722。**候选池等大、证据更全、调用更多，选得反而更差**，说明剩余差距在候选池的可判别性（symptom / 过宽实体混入 8 个 slot），而不再在排序机制。

## 7. 候选池审计：纯度与宽度都不是杠杆

第 6 节把差距推给了「候选池可判别性」。本节直接检验该假设，结论是**它也不成立**，真正的残余原因在 C3 生成本身。

### 7.1 slot 纯度审计

对每个臂生成的全部唯一 label 做一次离线 LLM 分类（`aphhm_c_label_audit.txt`，不参与任何诊断臂），分为具体诊断 / 过宽类 / 症状或体征 / 其他：

| 臂 | slot/例 | 具体诊断占比 | junk（症状+其他）/例 | 金标在池且 junk=0 时的转化率 |
|---|---:|---:|---:|---:|
| APHHM-C（v1，K=10） | 8.19 | 0.762 | 1.06 | 0.459 |
| v2 契约，K=10 | 6.50 | 0.755 | 0.83 | 0.529 |
| v2 契约，K=4 | 4.40 | 0.792 | 0.41 | 0.564 |
| Forest | 4.17 | 0.847 | 0.29 | **0.669** |
| Lite | 4.21 | 0.882 | 0.16 | **0.650** |

两点否证：

1. **纯度确实较低，但不解释差距。** 在 junk=0 的干净子集里 APHHM-C 仍只有 0.459，Forest / Lite 是 0.669 / 0.650，落后 19–21 个百分点。junk 数与转化率也不单调（v1：0.341 / 0.143 / 0.421）。
2. **收紧生成契约几乎无效。** v2 契约明确禁列症状并给出反例，纯度只从 0.762 动到 0.755（K=10）/ 0.792（K=4），远达不到 Forest 的 0.847。

### 7.2 宽度曲线

三个臂共用 v2 契约与 clean selector，只改 `unique_budget`：

| 臂 | slot/例 | DA pool | DA top-1 | DA conv | MCR pool | MCR top-1 | MCR conv |
|---|---:|---:|---:|---:|---:|---:|---:|
| v2-K10 | 6.50 / 6.85 | 0.420 | 0.175 | 0.417 | 0.335 | 0.200 | 0.597 |
| v2-K6 | 6.37 / 6.21 | 0.420 | 0.140 | 0.333 | 0.345 | 0.200 | 0.580 |
| v2-K4 | 4.40 / 4.21 | 0.390 | 0.170 | 0.436 | 0.285 | 0.185 | 0.649 |
| Forest | 4.17 / 4.45 | **0.455** | **0.270** | **0.593** | 0.360 | **0.260** | **0.722** |
| Lite | 4.21 / 4.32 | 0.400 | **0.270** | **0.675** | **0.375** | 0.235 | 0.627 |

曲线是平的：K10 与 K4 在四个指标上全部无显著差异（p≥0.39）。最好的配置 v2-K10（5.31 calls，DA 0.5900/0.1750、MCR 0.2300/0.2000）相对原始臂显著（mcr_task 1-24，p<1e-5；mcr_concept 3-22，p=0.00016），但相对第 6 节的 `+clean` **四个指标全部不显著**（p≥0.16）——也就是说 v2 契约与宽度调整没有在 selector 修复之外贡献任何可测增量。

### 7.3 同宽度同召回的对照

表中最有信息量的是 DA 上的一对：**v2-K4（4.40 slot、pool 0.390）与 Lite（4.21 slot、pool 0.400）宽度与召回都几乎相同，转化率却是 0.436 对 0.675。** 池子一样大、一样含金，选出来的却差 24 个百分点。

MCR 侧则是另一种失效：同宽度下 v2-K4 的转化率 0.649 已介于 Lite 0.627 与 Forest 0.722 之间（可接受），但 pool recall 塌到 0.285，而 Lite 用同样 4.3 个 slot 拿到 0.375。APHHM-C 要 6.85 个 slot 才够到 0.335，仍不及 Lite。

两侧合起来指向同一个上游原因：**C3 的「轴条件化 + family quota」批量生成，每个 slot 的含金量与可判别性都低于不受约束的临床生成器**。这与设计 §12 的核心主张（层次结构的价值在于组织候选与分配搜索预算）方向相反——在本数据上，轴条件化是在花预算买负收益。

## 8. 轴因子：条件化确实有害，但删掉它也补不上差距

第 7.3 节把残余原因指向 C3 的轴条件化。本节直接把它拆掉，两个臂都保留结构基座（registry / ledger / append-only 生命周期）与 clean selector，并统一用 K=10，因此唯一变量是轴：

| 臂 | C2 是否调用 | C3 是否看到 family/quota | calls |
|---|---:|---:|---:|
| `K10-v2` | 是 | 是 | 5.31 |
| `NoCond` | 是（guard/gap 仍在） | 否 | 5.30 |
| `NoAxis` | **否**（轴槽整体移除） | 否 | **4.28** |

### 8.1 slot 效率确实改善了

| 臂 | DA slot/例 | DA pool | DA recall/slot | MCR slot/例 | MCR pool | MCR recall/slot |
|---|---:|---:|---:|---:|---:|---:|
| K10-v2 | 6.50 | 0.420 | 0.0646 | 6.85 | 0.335 | 0.0489 |
| NoCond | 5.12 | 0.395 | 0.0772 | 5.83 | 0.375 | 0.0643 |
| NoAxis | 5.00 | 0.405 | 0.0809 | 6.07 | **0.380** | 0.0627 |
| Lite | 4.21 | 0.400 | 0.0950 | 4.32 | 0.375 | 0.0868 |
| Forest | 4.17 | **0.455** | **0.1091** | 4.45 | 0.360 | 0.0810 |

去掉轴条件化把每 slot 召回抬高约 25%（DA 0.0646→0.0809，MCR 0.0489→0.0627），**MCR 池召回追平 Lite**（0.380 vs 0.375），DA 池召回也与 Lite 齐平（0.405 vs 0.400）。第 7.3 节的方向判断因此得到确认：轴条件化在花预算买负收益。

### 8.2 但准确率没有跟上

| 臂 | calls | DA task | DA concept | MCR task | MCR concept | DA conv | MCR conv |
|---|---:|---:|---:|---:|---:|---:|---:|
| K10-v2 | 5.31 | 0.5900 | 0.1750 | 0.2300 | 0.2000 | 0.417 | 0.597 |
| NoCond | 5.30 | 0.5800 | 0.1750 | **0.2350** | **0.2100** | 0.443 | 0.560 |
| NoAxis | **4.28** | 0.5700 | **0.1800** | 0.2100 | 0.1850 | 0.444 | 0.487 |
| Lite | 3.00 | 0.6000 | 0.2700 | 0.2500 | 0.2350 | **0.675** | **0.627** |

三个臂之间**四个指标全部无显著差异**（K10-v2 vs NoAxis 最小 p=0.523；vs NoCond 最小 p=0.804）。相对原始 APHHM-C，NoAxis 在三个指标上显著更好（mcr_task 4-23 p=0.0003、mcr_concept 5-21 p=0.0025、da_concept 9-21 p=0.043），但这一增量与第 6 节的 selector 修复重合，不是轴因子带来的。

关键的否证在最后两列：**在池召回已经与 Lite 持平的情况下，转化率仍是 0.444 / 0.487 对 0.675 / 0.627。** 池子一样大、一样含金，选出来的还是差 19–23 个百分点。NoAxis vs Lite 的 da_concept 是 9-27（p=0.0039）、mcr_concept 7-17（p=0.064）。

### 8.3 结论：C2 是净负担，但残余瓶颈回到选择

- **C2（axis contract）确认为净负担**：一个固定调用槽换不到任何可测收益，其条件化还让每 slot 召回降低约 25%。删掉它省 1.03 calls、DA concept 反而是全部 APHHM-C 臂里最好的 0.180。设计 §6.1 把 C2 列为「固定槽位」缺乏经验支持。
- **残余瓶颈是选择，且已排除四种解释**：不是排序机制（§5–6 已换成 LLM selector）、不是 frontier 剪枝（§6 已放开）、不是 slot 纯度（§7.1，干净子集仍落后 19pp）、不是池宽或池召回（§7.2、§8.1，均已与 Lite 持平）。剩下唯一未被隔离的差异是**每候选证据的形式**：Lite 的候选各自携带生成器为它挑的 verbatim support/contradict span，而 APHHM-C 的候选只持有指向一份共享 12-fact ledger 的 fact_id，且该 ledger 经 P4/P5 后有 77% 的 cell 被判为不可准入。

### 8.4 指标口径的一个警告

按设计 §10.3 的 Binding 口径拆开（DA200）：`both=0.175`、`task_only=0.395`、`concept_only=0.005`（NoAxis）；Lite 是 `0.265 / 0.335 / 0.005`。DA 的 task 指标有 0.34–0.42 的病例是「concept 错但 mapper 仍映射到正确选项」，说明 **DA option@1 相当宽松，不能单独用来支持任何机制主张**（观察到的极端例：champion "Long QT Syndrome" 对 gold "Coronary Artery Disease with Giant R-wave Syndrome" 仍被判 task 正确）。

同时 `dc.match` 有共享噪声：全部臂都出现 "Malignant peripheral nerve sheath tumor" 对 "tumour" 这类拼写差异被判不匹配。该噪声对各臂同向，不改变排序结论，但说明 concept 绝对值被系统性低估。

## 9. 证据形式：这是真正的瓶颈，代价是设计 §2.4

§8.3 把残余原因指向最后一个未隔离的差异：Lite/Forest 的候选各自携带生成器为它挑的 verbatim span，而 APHHM-C 的候选只持有指向共享 ledger 的 fact_id。本节直接改这一项。新增 `evid` 契约要求 C3 为每个候选写 `support_spans` / `contradict_spans`（必须是 vignette 的精确子串，非子串一律丢弃），selector 只读这些 span，不再读 ledger cell。两个臂都用 axis off + K=10：

| 臂 | 组成 | calls | 选择器读到的证据 |
|---|---|---:|---|
| `NoAxis` | C1+C3+C4+sel | 4.28 | ledger 准入 cell |
| `CandEv` | C1+C3+C4+sel | 4.39 | 每候选 span |
| `Collapse3` | C1+C3+sel（**删 C4**） | **3.38** | 每候选 span |

span 存活情况：每候选平均 2.0 条 for、0.5 条 against 通过了 verbatim 校验。

### 9.1 转化率被修好了，而且反超 Lite

| 臂 | DA 宽度 | DA pool | DA conv | MCR 宽度 | MCR pool | MCR conv |
|---|---:|---:|---:|---:|---:|---:|
| NoAxis | 5.00 | 0.405 | 0.444 | 6.07 | 0.380 | 0.487 |
| CandEv | 3.85 | 0.370 | 0.514 | 4.35 | 0.330 | 0.576 |
| Collapse3 | 3.93 | 0.360 | 0.500 | 4.60 | 0.330 | **0.652** |
| Lite | 4.21 | 0.400 | 0.675 | 4.32 | 0.375 | 0.627 |
| Forest | 4.17 | 0.455 | 0.593 | 4.45 | 0.360 | 0.722 |

MCR 转化率 0.487 → 0.652，**超过 Lite 的 0.627**，逼近 Forest 的 0.722；DA 0.444 → 0.500。§5–8 四轮都没能撬动的这个量，换掉证据形式后一次撬动了 16.5 个百分点。这直接证伪设计 §2.4「evidence、score、rank 只能有一个权威来源」：把每候选自带的证据作为第二来源交给选择器，是当时已完成的 APHHM-C 消融中唯一观察到的有效修复。

### 9.2 但 C4 是第二个净负担

`Collapse3` 删掉整个 C4 矩阵后**比保留它的 `CandEv` 更好**：MCR task 0.2600 vs 0.2400、MCR concept 0.2150 vs 0.1900（mcr_concept 1-6，p=0.125），且便宜一次调用。一旦选择器不再读 ledger cell，C4 唯一的剩余用途就是构造 frontier，而 §6 已证明放开 frontier 更好。因此矩阵在花一个固定槽产出无人消费的状态。

### 9.3 3 次调用下的正面对照

| 方法 | calls | DA task | DA concept | MCR task | MCR concept |
|---|---:|---:|---:|---:|---:|
| **Collapse3** | **3.38** | 0.5950 | 0.1800 | **0.2600** | 0.2150 |
| Lite | 3.00 | 0.6000 | 0.2700 | 0.2500 | 0.2350 |
| B07 | 3.00 | 0.5700 | 0.2550 | 0.2450 | 0.2800 |
| Forest | 4.06 | 0.6650 | 0.2700 | 0.2600 | 0.2600 |
| v0 | 4.00 | 0.5650 | 0.1850 | 0.2250 | 0.1750 |

任务级第一次全线追平：**MCR task 0.2600 与 Forest 完全并列**（12-12，p=1.000），对 Lite 是 15-13（p=0.851）、对 B07 是 15-12（p=0.701）；DA task 对 Lite 27-28（p=1.000）、对 B07 30-25（p=0.590）。相对 §8 的最好臂，Collapse3 的 mcr_task 提升显著（3-13，p=0.021）。相对 v0 四个指标全部占优（未达显著）。

concept 级仍然落后：DA concept 0.1800 对 Lite 0.2700（6-24，p=0.0014）、对 B07 0.2550（9-24，p=0.014）；MCR concept 0.2150 对 Lite 0.2350（9-13，p=0.523，已不显著）、对 B07 0.2800（7-20，p=0.019）。

### 9.4 瓶颈已经换位：现在是池召回

看 9.1 的表：Collapse3 的转化率已达标（MCR 超 Lite、DA 差 17.5pp），但池召回反而退了（MCR 0.380→0.330、DA 0.405→0.360），因为 `evid` 契约让生成器把宽度从 6.07 写窄到 4.60——为每个候选写证据的负担压缩了候选数。两个效应相抵，净 top-1 只在 MCR 上得利（0.185→0.215），DA 上持平（0.180）。

这两个量看起来可解耦：证据形式管转化，宽度管召回。因此追加 `evid_wide` 契约（同样要求每候选写证据，但显式给出至少 6 个候选的下限），跑 `Collapse3w`。

### 9.5 宽度与转化不可同时拿满

`Collapse3w`（3.40 calls）的召回按预测补回来了，但转化率同步掉下去：

| 臂 | 宽度 | pool | conv | top1 | recall/slot |
|---|---:|---:|---:|---:|---:|
| Collapse3 · DA | 3.93 | 0.360 | 0.500 | 0.180 | 0.0916 |
| Collapse3w · DA | 6.45 | **0.435** | 0.494 | **0.215** | 0.0675 |
| Lite · DA | 4.21 | 0.400 | **0.675** | **0.270** | **0.0950** |
| Collapse3 · MCR | 4.60 | 0.330 | **0.652** | 0.215 | 0.0717 |
| Collapse3w · MCR | 6.38 | **0.390** | 0.551 | 0.215 | 0.0612 |
| Lite · MCR | 4.32 | 0.375 | 0.627 | 0.235 | **0.0868** |

DA 池召回 0.360 → **0.435**（超过 Lite 的 0.400，接近 Forest 的 0.455），MCR 0.330 → 0.390（超过 Lite 的 0.375）。但 MCR 转化率从 0.652 退到 0.551。两个臂的 top-1 在 MCR 上完全相同（0.215），DA 上 wide 更好（0.180 → 0.215），四个指标之间无一显著（最小 p=0.167）。

Lite 的优势不在任一端，而在两端同时成立：它用 4.2–4.3 个 slot 拿到 0.375–0.400 的召回**并且**保持 0.627–0.675 的转化。我们的两个臂各拿一端，`recall/slot` 始终是 0.061–0.092 对 Lite 的 0.087–0.095。**每 slot 的信息效率是最后一个未闭合的差距。**

### 9.6 3.40 次调用下与 Lite 全指标持平

| 方法 | calls | DA task | DA concept | MCR task | MCR concept |
|---|---:|---:|---:|---:|---:|
| **Collapse3w** | **3.40** | 0.6000 | 0.2150 | 0.2500 | 0.2150 |
| Collapse3 | 3.38 | 0.5950 | 0.1800 | **0.2600** | 0.2150 |
| Lite | 3.00 | 0.6000 | 0.2700 | 0.2500 | 0.2350 |
| B07 | 3.00 | 0.5700 | 0.2550 | 0.2450 | 0.2800 |
| Forest | 4.06 | 0.6650 | 0.2700 | 0.2600 | 0.2600 |

`Collapse3w` vs Lite：**四个指标全部不显著**，其中 da_task 24-24（p=1.000）与 mcr_task 11-11（p=1.000）是精确并列，da_concept 13-24（p=0.099）、mcr_concept 8-12（p=0.503）。vs B07 只剩 mcr_concept 显著（9-22，p=0.029）。vs Forest 四项均不显著（最小 p=0.064）但全部同向为负。相对原始 APHHM-C 是压倒性改善：mcr_task 1-28（p=3e-6）、mcr_concept 3-25（p=3e-5）、da_concept 8-27（p=0.0019）。

## 10. Go / No-Go

**当前结论分两层：原设计形态仍为 No-Go；删光其机制后的收缩形态只在历史 task/legacy 表上达到内部基线档，不再称样本外 Go 或 clinical winner。**

### 10.1 原设计形态：No-Go

不建议把设计文档所描述的 APHHM-C 扩到 400 或写入主表。原始臂在 4.64 calls 下四个指标中的三个显著劣于 3 calls 的 B07，设计 §10.4 的五条经验性标准没有一条成立。五轮修复（selector → 宽 shortlist → 去锚点 → v2 契约 → 宽度扫描 → 去轴 → 每候选证据）逐个删掉了设计的招牌部件才把结果推上来，**每一次有效的改动都是在删设计规定的东西**：

| 删掉的部件 | 设计地位 | 删掉后的效果 |
|---|---|---|
| 确定性 final rank（§4.1） | 硬约束 | MCR task +11pp（p=1e-5），零例被改坏 |
| frontier 前置剪枝（§4.2 的实现） | 默认 | 放开后 shortlist 不再丢已找到的 gold |
| 轴条件化生成（§12） | 核心主张 | 每 slot 召回 +25%，MCR 池召回追平 Lite |
| C2 axis contract（§6.1 固定槽） | 固定调用 | 省 1.03 calls，四指标 p≥0.52 |
| 单一权威证据来源（§2.4） | 架构原则 | MCR 转化率 +16.5pp，反超 Lite |
| C4 全局矩阵（§6.1 固定槽） | 固定调用 | 省 1 call，MCR task +2pp |

### 10.2 收缩形态：历史任务级内部 Go，但不是当前能力确认

`Collapse3w` = C1 事实账本 + 每候选自带 verbatim 证据的扁平生成 + selector，3.40 calls。它与 Lite（3.00 calls）**四个指标全部不显著**，其中两个任务级指标精确并列（DA 0.6000 vs 0.6000、MCR 0.2500 vs 0.2500）；对 B07 只剩 mcr_concept 显著；对 Forest 四项均不显著但同向为负。这是本轮唯一达到基线档位的配置。

但必须如实标注它的性质：**这个配置里已经不剩任何设计特有的机制**。轴、家族、配额、确定性排序、全局证据矩阵、单一权威来源全部删除，留下的是 C1 + 扁平生成 + 选择，加上不花调用的 registry / ledger 记账。它跟 Lite 的差别只是多了一次 C1 与结构记账。因此它证明的是「结构记账无害」，而不是「层次化有用」。

同一形态换上承诺契约后（`Collapse3c`，3.27–3.31 calls，§12）在历史 MCR task 上更进一步。原 §15 的预留切片中，MCR task 0.2950 是六者最高，DA task 0.6550 与同预算 B07（0.6600）打平；合并 n=400 后对 IMPC 的未校正历史比较为 p=0.017、对 Lite 为 p=0.053。这些数值仍可说明开发样本中的工程潜力，但完整 800 例已参与后续开发，且统一根级端点没有总体 winner，故不再称“样本外确认”。

因此判据要按指标分开写：

- **历史任务级：内部 Go。** 两个 development 切片方向相近，说明该收缩形态值得作为 specificity mechanism reference；不能外推为确认性胜者。
- **MCR concept：历史 legacy-chain 持平。** 0.2225 与五个基线未检出差异；§14.2 显示差距主要来自片段得分，不能解释成临床完全等价率。
- **DA concept：应退役为能力判据。** 旧值 0.2000 对部分基线显著为负，但 §14.1 表明其得分几乎全来自片段匹配；它测量 surface/family naming，而不是完整诊断正确性。
- **当前 clinical-complete：无总体 winner。** E2 根审计中 `Collapse3c` 15.25%、`MultiStance` 15.12%、Lite 13.25%；`Collapse3c` 是 specificity-retention reference，当前安全默认仍为 Lite-like 架构。

一句话结论：**原设计机制删去之后，收缩形态在当前 development 的历史任务表上达到基线档并呈 MCR 方向优势；这支持继续移植其 specificity retention，却不构成外部能力 Go。** 对原设计的 No-Go 与对收缩部件的机制保留应分开表述。

### 10.3 保留：结构基座

三件东西被证明可以零成本保有，值得移植到任何主干：全局 concept identity（重复占位归零）、append-only 候选生命周期（无事件消失为零）、write-score-then-rank 的单一权威状态（inversion 为零）。在全部 14 个臂 × 400 例上零违规，不消耗任何额外调用。这是设计 §9 Phase 1 的「结构安全补丁」，其价值独立于 Phase 2 的调用压缩。

### 10.4 被证伪的五条具体主张

1. §4.1「默认 final rank 必须是 ledger 的确定性函数」：单独造成 MCR 任务级 11pp 损失（p=1e-5），替代方案零损失。
2. §12「层次结构的价值在于组织候选与分配搜索预算」：轴条件化使每 slot 召回降低约 25%；删掉整个轴后池召回追平 Lite 且省一个槽。
3. §6.1 把 C2 列为**固定**槽位：三臂对照下换不到任何可测收益（四指标 p≥0.52）。
4. §2.4「evidence、score、rank 只有一个权威来源」：让候选携带自己的证据并交给选择器，是当时 APHHM-C 历史 legacy-chain 消融中唯一观察到的有效修复（MCR 转化率 0.487 → 0.652）。
5. §6.1 把 C4 列为**固定**槽位：一旦选择器不读 ledger cell，删掉矩阵反而更好（MCR task 0.2400 → 0.2600）且省一个槽。

两个可选槽同样没有产出：gap lane 触发 29% 但 `gap_concepts` 均值仅 0.32；verifier 触发 35% 却平均只修 0.13 个 cell。

## 11. Slot 效率诊断：候选集合逐例比对

`analysis/backbone_v1/diag_slot_efficiency.py`，全离线不花调用。把我们的候选池与基线逐例配对，并用**全语料 document frequency 作为常见度代理**（一个病被 400 例中多少个不同病例提出过；常见病反复出现，罕见病只出现一两次）。语料取全部 11 个跑满 400 的臂。

### 11.1 两边根本不在同一个假设空间里

| ours | ref | 我们宽度 | 基线宽度 | 共有 | 仅我们 | 仅基线 | Jaccard |
|---|---|---:|---:|---:|---:|---:|---:|
| Collapse3w · DA | Lite | 6.45 | 4.21 | 1.88 | 4.57 | 2.33 | 0.233 |
| Collapse3w · MCR | Lite | 6.38 | 4.32 | 2.09 | 4.29 | 2.24 | 0.269 |
| Collapse3w · MCR | Forest | 6.38 | 4.45 | 2.36 | 4.02 | 2.08 | 0.304 |

平均只有 1.9–2.4 个候选是共有的。此前所有「谁排得更好」的比较，其实建立在两个大部分不相交的候选集合上。

### 11.2 把召回和选择彻底分开：`conv|both`

只看**两边池子都含 gold** 的病例，此时覆盖被控住，剩下的纯粹是选择能力：

| 臂（证据形式 / 宽度） | DA conv\|both | vs Lite | MCR conv\|both | vs Lite |
|---|---:|---:|---:|---:|
| NoAxis（ledger cell / 5.0–6.1） | 0.541 | −19.7pp | 0.5902 | −6.6pp |
| Collapse3w（每候选证据 / 6.4） | 0.6207 | −15.5pp | **0.6562** | **±0.0pp** |
| Collapse3（每候选证据 / 3.9–4.6） | 0.6538 | −11.5pp | **0.6935** | **+3.2pp** |

**MCR 的选择问题已经解决**：Collapse3w 与 Lite 在匹配子集上完全相同（0.6562 = 0.6562，n=64），窄臂 Collapse3 反超 3.2pp（0.6935 vs 0.6613）。§9 的每候选证据改动是这一项的直接原因（0.5902 → 0.6935）。MCR 上剩下的 concept 级差异（0.2150 vs 0.2350）只来自两边各自找到 gold 的病例不重合（仅我们 0.070 / 仅 Lite 0.055），已是噪声量级而非机制。

**DA 的选择仍差 11.5pp**，且窄化只补回其中一部分（0.541 → 0.654），说明干扰项数量只是部分原因。DA 与 MCR 在这一项上性质不同。

### 11.3 我们的池子并不更差，甚至更好

gold 命中的 2×2（Collapse3w vs Lite）：

| | 都含 | 仅我们 | 仅 Lite | 都不含 |
|---|---:|---:|---:|---:|
| DA | 0.290 | **0.145** | 0.110 | 0.455 |
| MCR | 0.320 | **0.070** | 0.055 | 0.555 |

我们独占的 gold 命中比 Lite 更多（DA 0.145 vs 0.110）。绝对池召回 DA 0.435 > Lite 0.400、MCR 0.390 > 0.375。**覆盖不是问题，问题是覆盖的代价。**

### 11.4 兄弟亚型枚举：真实但只解释一小部分

按标签的中心词归族（`Primary Hyperhidrosis` / `Focal Hyperhidrosis` 同族），同族兄弟高度相关，多个 slot 买不到成比例的覆盖：

| 臂 | 族数 | slot/族 | 最大族占比 | recall/族 |
|---|---:|---:|---:|---:|
| Collapse3w · DA | 5.15 | 1.48 | 0.345 | 0.0845 |
| Collapse3 · DA | 3.32 | 1.31 | — | **0.1084** |
| Lite · DA | 3.64 | 1.24 | 0.382 | 0.1099 |
| Forest · DA | 3.57 | 1.26 | — | **0.1275** |

宽臂每族要花 1.48 个 slot（Lite 1.24），最极端的例子是 gold `Intergluteal and sacral hyperhidrosis`，我们用 6 个 slot 枚举了 6 个 hyperhidrosis 亚型（Primary / Secondary / Generalized / Focal / Medication / Axillary）而一个都没匹配上，Lite 用一个 `Hyperhidrosis` 命中。同类还有 gold `Epidermolysis bullosa pruriginosa`（我们列了 3 个其它 EB 亚型）、gold `T-cell lymphoblastic lymphoma`（我们列 Hodgkin / Non-Hodgkin）。

但归族后差距只收窄一点（recall/slot 之比 0.71 → recall/族之比 0.77），**窄臂 Collapse3 的 DA 每族召回 0.1084 已与 Lite 的 0.1099 持平**。所以兄弟枚举是宽臂特有的浪费，不是系统性差距的主因。

### 11.5 粒度不是差异来源（推翻一个候选解释）

对 gold 命中的标签做粒度分类（`coarser` = 命中标签是 gold 的片段）：DA 我们 96.6% 靠 coarser 命中，Lite 87.5%；MCR 我们 41.0%，Lite 38.7%。**我们并不比 Lite 更「细」，在 DA 上甚至更依赖粗粒度命中。** 此前怀疑「Lite 靠停在族级标签占便宜」不成立。（副产物：DA 的 gold 多为长复合描述，因此几乎所有方法都只能靠片段匹配命中，这是 DA concept 指标的固有噪声。）

### 11.6 真正的答案：我们的 slot 花在通用鉴别诊断上，基线花在本例特异的罕见病上

用 document frequency 看每一侧独占的候选：

| 对照 | 我们独占标签的常见度 | 基线独占标签的常见度 | 我们 singleton 占比 | 基线 singleton 占比 |
|---|---:|---:|---:|---:|
| Collapse3w vs Lite · DA | 3.80 | **2.69** | 0.401 | **0.483** |
| Collapse3w vs Lite · MCR | 3.55 | **2.45** | 0.435 | **0.495** |
| Collapse3w vs Forest · DA | 3.76 | **2.53** | 0.401 | **0.472** |
| Collapse3w vs Forest · MCR | 3.62 | **2.46** | 0.435 | **0.498** |

四个对照方向一致：**基线独占的候选比我们独占的候选更罕见**（2.45–2.69 对 3.55–3.80），且更大比例是只在本例出现过的 singleton（0.47–0.50 对 0.40–0.44）。

在「只有基线找到 gold」的病例上这一点最尖锐：gold 本身的常见度是 0.41（DA）/ 1.27（MCR），即几乎是全语料唯一的实体；而我们在这些病例里的池子平均常见度是 4.72 / 3.75。例子的形态高度一致——gold `Lipoblastoma` 我们给 Lipoma / Liposarcoma / Hemangioma / Fibroma；gold `Contrast-induced encephalopathy` 我们给 Cerebral Edema / Seizure Disorder / Hypoxic-Ischemic Encephalopathy；gold `Hemosiderotic fibrolipomatous tumor` 我们给 Nodular fasciitis / Liposarcoma / Dermatofibroma。

**结论：这不是先验校准问题，是承诺问题。** 我们的生成器在写一份「教科书式的通用鉴别诊断」——正确的族、合理的常见候选、可辩护但不针对本例；基线则敢于把 slot 押在本例特有的那个罕见实体上。用户问题的答案是后者：Lite 多出来的候选是**更贴合本例的罕见病**，不是更常见的病。

这也解释了为什么 §7.1 的纯度审计查不出问题（我们的标签确实都是合法的具体诊断）、§9.5 的宽度调节两头都堵（无论宽窄，多出来的 slot 都在填通用候选）。

## 12. 承诺契约：机制按预测移动，MCR 得利，DA 的回退主要是指标造成的

按 §11.6 的机制写 `evid_commit` 契约（`Collapse3c`，同 3-call 形态，3.31 calls）。三条要求：候选必须由**对它自己而言不寻常**的发现驱动，而非该族共有的表现；显式禁止「为完整性而列」「为保险而列」的通用鉴别项；同族（同中心词）最多 2 个候选。

### 12.1 机制验收：代理量确实动了

| 量 | Collapse3w | Collapse3c | Lite（同批语料） | 是否达标 |
|---|---:|---:|---:|---|
| 独占标签常见度 · DA | 3.80 | **3.12** | 2.70 | 走了约 60% |
| 独占标签常见度 · MCR | 3.55 | **3.08** | 2.34 | 走了约 40% |
| singleton 占比 · DA | 0.401 | 0.438 | 0.473 | 部分 |
| singleton 占比 · MCR | 0.435 | **0.496** | 0.492 | **追平** |
| slot/族 · DA | 1.48 | 1.34 | 1.24 | 部分 |
| 宽度 · DA / MCR | 6.45 / 6.38 | 5.27 / 5.24 | 4.21 / 4.32 | 部分 |
| 与 Lite 的 Jaccard · DA / MCR | 0.233 / 0.269 | **0.299 / 0.333** | — | 池子在靠拢 |

契约起作用了，方向与 §11.6 的预测一致：候选更罕见、同族枚举减少、池子向基线靠拢，MCR 的 singleton 占比一次追平 Lite。

### 12.2 MCR：拿到全表最高的任务级成绩

| 方法 | calls | MCR task | MCR concept |
|---|---:|---:|---:|
| **Collapse3c** | **3.31** | **0.2900** | 0.2150 |
| MAC | — | 0.2700 | 0.3150 |
| Forest | 4.06 | 0.2600 | 0.2600 |
| e7 | 6.00 | 0.2550 | 0.1850 |
| Lite | 3.00 | 0.2500 | 0.2350 |
| B07 | 3.00 | 0.2450 | 0.2800 |
| IMPC | 4.00 | 0.2250 | 0.2300 |

MCR task 0.2900 高于表中所有方法，且是最便宜的臂。检验：对 IMPC 23-10（p=0.035）显著；对 MAC 11-7（p=0.481）、Forest 17-11（p=0.345）、Lite 17-9（p=0.169）、B07 21-12（p=0.163）方向占优但不显著。相对上一臂 Collapse3w 是 8-16（p=0.152）。**须注意多重比较**：13 个臂 × 4 个指标下，单个 p=0.035 不足以单独支撑结论，这里只作为方向证据。

匹配子集上的选择也保持住了：`conv|both` MCR 0.6508 对 Lite 0.619，仍然领先。

### 12.3 DA：承诺反而有害

| 量 | Collapse3w | Collapse3c |
|---|---:|---:|
| DA concept | 0.2150 | 0.1850 |
| DA 池召回 | 0.435 | 0.385 |
| DA `conv\|both` | 0.6207 | 0.5833 |

DA concept 退到 0.1850（对 Collapse3w 是 12-6，p=0.238，未达显著但方向明确），对 Lite 重新变为显著为负（5-22，p=0.0015）。

原因可以从 §11.5 的粒度数据直接读出：**DA 的 gold 多为长复合描述**（`Acute dacryocystitis with secondary optic nerve injury`、`Inflammation-induced ocular neuropathy associated with…`），94.8% 的命中靠片段匹配。这种 gold 奖励的是停在族级的粗标签（Lite 用一个 `Dacryocystitis` 命中），而承诺契约要求押本例特有的罕见实体，恰好把候选推离那个能匹配的粗片段。

**因此两个数据集看起来要的方向相反**：MCR 的 gold 是真实病例报告里那个具体罕见实体，押它有回报；DA 的 gold 是复合描述，押具体实体会失去片段匹配。

§13 对这一节做了实质修正：DA 那 15.5pp 的转化差里，逐例判定有 8/15 是「我们补了一个**正确的**限定词导致匹配失败」。所以这里的 DA 回退**主要是指标在惩罚承诺，而不是承诺在损害诊断**。结论应改写为：承诺契约在 MCR 上有真实收益，在 DA 上的代价大部分是测量口径造成的，因此不能据此说两个数据集要的建模方向相反——只能说 DA 的 concept 指标无法用来评价承诺类改动。

## 13. DA 转化差的逐例判定：过半是正确答案被限定词判负

`Collapse3w` 在 DA 的 `conv|both` 子集（n=58）里共有 22 例未转化，其中 **15 例是 Lite 转化而我们没转化**——这 15 例就是 §11.2 那 15.5pp 的全部来源。逐例读完（`diag_da_conversion_failures.py`，输出在 `mosaic_eval/da_conversion_failures.json`）：

### 13.1 判定结果

| 类别 | n | 说明 |
|---|---:|---|
| **实质正确，匹配器因限定词失败** | **8** | 我们的 champion 与 gold 是同一个病，只是多带了一个正确的限定词 |
| 粒度偏差（正确但过粗/过偏） | 2 | 命名了正确的上位或正确的致病因子，但不是 gold 指的那个层级 |
| 真实错误（不同的病） | 5 | champion 与 gold 是不同疾病 |

八个实质正确的例子（`ours` → `gold`，Lite 拿到分数的答案在括号里）：

| 我们的 champion | gold | Lite |
|---|---|---|
| Brown Tumor of Hyperparathyroidism | Brown tumor secondary to primary hyperparathyroidism due to parathyroid carcinoma | (Brown tumor) |
| Revertant Mosaicism in Dystrophic Epidermolysis Bullosa | Severe generalized RDEB **with revertant mosaicism** | (Dystrophic Epidermolysis Bullosa) |
| Adalimumab-induced Blepharitis | Drug-induced blepharitis and ectropion associated with TNF-α inhibitors (**infliximab and adalimumab**) | (Blepharitis) |
| GGCX deficiency | Pseudoxanthoma elasticum-like disorder with coagulation **deficiency** | (Pseudoxanthoma elasticum) |
| Streptococcal endophthalmitis | Endogenous endophthalmitis with iris abscess | (Endophthalmitis) |
| Ipilimumab-induced myositis | Drug-induced dermatomyositis secondary to **ipilimumab** therapy | (Dermatomyositis) |
| MSH6-Associated Endometrial Cancer | Stage IA endometrial cancer | (Endometrial Cancer) |
| Recurrent Melanoma | Stage IIIC (T4aN3) melanoma with satellite metastases | (Melanoma) |

五个真实错误：`Mycosis Fungoides` / gold `Inverse lichen planus`；`Kaposi's sarcoma` / `Microvenular hemangioma`；`Rosacea` / `Actinic folliculitis`；`Hepatitis C-associated porphyria cutanea tarda` / `Bullous lichen planus of the nails`；`Chronic Rhinosinusitis` / `Transient abducens nerve palsy`（命名了一个候选病因而不是 gold 指的功能缺损）。

### 13.2 匹配器系统性奖励欠特异、惩罚过特异

上表右列是关键：**14/15 例里 Lite 得分靠的是 gold 的一个片段**（`Brown tumor`、`Blepharitis`、`Melanoma`），而我们因为补上了一个**正确的**限定词（正确的药名、正确的分子缺陷、正确的病原体、gold 自己也写了的 revertant mosaicism）而失分。`dc.match` 是片段包含式的，停在族级标签能匹配任何以该族为中心词的复合 gold，而加了限定词的标签匹配不上。

这条偏差正好指向 §12 承诺契约要产生的那种行为。**§12.3「DA 上承诺有害」因此需要重新表述：承诺在 DA 的 concept 指标上有害，而该指标主要奖励族级命名。**（§14.1 对本节做了进一步收紧：限定词惩罚率在各臂之间并无系统差异，因此只能说指标的性质对承诺类改动不利，不能说它专门惩罚我们。）

按这 8 例修正，我们的 DA `conv|both` 从 36/58=0.621 变为 44/58=0.759，与 Lite 的 0.776 只差 1.7pp；再计入 2 例粒度偏差则为 0.793，反超。但必须对称地声明：**Lite 的成功里也包含欠特异答案拿满分的情形**（它对那个复合 gold 只答 `Blepharitis` 就得分）。这项对称审计已在 §14 完成，结论是 DA 上的机制对各臂对称，MCR 上则不对称且不利于承诺类改动。因此本节只能得出「DA concept 的方法间差异不可靠」，不能反过来宣称我们更好。

### 13.3 mapper 也不能当裁判

把这 15 例交给 DA 的 mapper（option@1）：7/15 判我们正确。但 mapper 自己错得很明显——`Hepatitis C-associated porphyria cutanea tarda` 对 gold `Bullous lichen planus of the nails` 被判**正确**，而 `Brown Tumor of Hyperparathyroidism` 对 gold `Brown tumor secondary to primary hyperparathyroidism` 被判**错误**。这与 §8.4 观察到的 mapper 宽松性一致：DA 的两个指标一个惩罚过特异、一个既宽松又不稳定，**任何仅靠 DA 的机制主张都不可采信**。

## 14. 对称审计：DA 上的偏差是对称的，MCR 上的差距不是

§13.2 的修正只审计了我们的失败例，方向不对称。`diag_da_match_bias.py` 对每个臂做同样的分解：得分是靠 `exact`（与 gold 同名）、`fragment`（champion 是 gold 的真子串，即停在更粗的层级）还是 `extra`（比 gold 更细）；未命中里又有多少属于「池子含 gold、champion 与 gold 共享内容词」的限定词惩罚形态。

### 14.1 DA：机制对所有臂同样地起作用

DA 有 **84.5% 的 gold 是复合描述**（内容词多于 2 个）。

| 臂 | DA concept | exact | fragment | fragment 占得分 | 限定词惩罚率 |
|---|---:|---:|---:|---:|---:|
| Collapse3w | 0.215 | 1 | 42 | 0.977 | 0.523 |
| Collapse3c | 0.185 | 1 | 35 | 0.946 | 0.550 |
| Lite | 0.270 | 4 | 47 | 0.870 | **0.577** |
| Forest | 0.270 | 2 | 49 | 0.907 | 0.487 |
| IMPC | 0.290 | 3 | 54 | 0.931 | 0.333 |

**修正 §13.2 的一个说法**：限定词惩罚率在各臂之间没有系统差异（我们 0.52–0.55，Lite 0.577 反而更高），所以不能说这个指标专门惩罚我们。正确的表述是：DA concept 有 87–98% 的得分来自片段匹配，全表 200 例里 exact 命中只有 1–4 例，**它实际测量的是「谁更常命中正确的族」，而不是「谁更常命中正确的病」**。机制对各臂同样地起作用，但对一个被要求承诺到族以下的臂在性质上不利。§13.1 的 8 个逐例判定仍然成立（那些 champion 确实实质正确），只是不能据此推断存在臂间不对称。

### 14.2 MCR：基线的优势全部来自片段得分

MCR 只有 36% 的 gold 是复合描述，得分结构完全不同：

| 臂 | MCR concept | **exact** | fragment | fragment 占得分 | 限定词惩罚率 |
|---|---:|---:|---:|---:|---:|
| Collapse3c | 0.215 | **31** | 8 | 0.186 | 0.114 |
| Collapse3w | 0.215 | 30 | 8 | 0.186 | 0.171 |
| Collapse3 | 0.215 | 28 | 8 | 0.186 | 0.087 |
| NoAxis | 0.185 | 23 | 7 | 0.189 | 0.205 |
| Lite | 0.235 | 29 | 14 | 0.298 | 0.107 |
| Forest | **0.260** | **31** | **18** | 0.346 | 0.100 |
| IMPC | 0.230 | 29 | 14 | 0.304 | 0.147 |

**这是本轮最干净的一个结果：在 exact 命中上我们与最好的基线持平或更好**（Collapse3c 31 = Forest 31 > Lite 29），MCR concept 的全部差距来自片段得分（我们 8，Lite 14，Forest 18）。也就是说 Forest 的 0.260 对我们的 0.215 不是因为它更常叫准那个病，而是因为它更常在叫不准时停在一个仍能匹配的粗标签上（gold `T-cell lymphoblastic lymphoma`，答 `Lymphoma` 得分）。

这与承诺契约的设计意图完全一致：承诺的臂要么叫准要么落空，对冲的臂能收部分分。因此 **MCR concept 指标对「承诺 vs 对冲」这条轴不是中立的**，而 MCR task（官方 LLM judge）上 `Collapse3c` 是全表最高的 0.2900。两个 MCR 指标的分歧由此得到解释。

## 15. 预留 development 切片复现与 n=400 描述性功效（七方法齐全）

`d2_heldout200b` 与 `mcr_200b` 是原协议预留切片（见 `aphhm_c_pilot200.json` 的 `protocol.holdout_reserved`），全部 APHHM-C 配置先在 DA200 / MCR200 上选出，所以本节仍分开报告它们，作为**预指定的内部复现敏感性**。但在后续端点迁移、机制挖掘与系统选择中，完整 800 例均已被使用；因此这些切片不再具有 external confirmation 或最终 untouched holdout 的地位。dev+reserved 合并的 n=400 只描述当前 development sample 的精度，不支持分布外推。

### 15.1 预留切片（内部 development，n=200 each，七方法齐全）

MAC（B06）与 B07 的 holdout 产物在 `runs/paper_v1/{diagnosisarena_heldout200b_v1,medcasereasoning_mcr_val_seq200b_v1}` 下已存在，已一并接入（B07 是 3 calls 的同预算对手，MAC 是 concept 上最强的方法）。

| 臂 | calls | DA200b task | DA200b concept | MCR200b task | MCR200b concept |
|---|---:|---:|---:|---:|---:|
| **Collapse3c** | **3.23 / 3.26** | 0.6550 | 0.2150 | **0.2950** | 0.2300 |
| MultiStance | 5.13 / 5.17 | 0.6150 | 0.2250 | **0.2950** | 0.2200 |
| B07 | 3.00 | **0.6600** | 0.2250 | 0.2850 | 0.2250 |
| IMPC | 4.00 | 0.6250 | **0.2950** | 0.2600 | 0.2450 |
| MAC | — | 0.6200 | 0.2700 | 0.2800 | 0.2350 |
| Forest | 4.04 / 4.09 | 0.6100 | 0.2900 | 0.2700 | 0.2450 |
| Lite | 3.00 | 0.6050 | 0.2450 | 0.2600 | 0.2000 |

（`MultiStance` 于 §17 加入本表，其单独讨论见该节；本表沿用历史端点名称与数值。）

- **MCR task：`Collapse3c` 与 `MultiStance` 并列最高**（均 0.2950），对 B07 14-12（p=0.845）、MAC 12-9（p=0.664）、Forest 14-9（p=0.405）、Lite 17-10（p=0.248）、IMPC 19-12（p=0.281），全部方向占优但不显著。
- **DA task：与 B07 打平**（0.6550 vs 0.6600，20-21，p=1.000），高于其余四个但均不显著（p=0.212–0.461）。**补上 B07 修正了上一版「两个数据集任务级都最高」的说法**——在 DA 上有一个同预算方法与它并列。
- **DA concept：仍是短板**，对 IMPC（p=0.011）、Forest（p=0.014）、MAC（p=0.043）显著为负；但**对 B07 不显著**（0.2150 vs 0.2250，13-15，p=0.851）。
- **MCR concept：与全部五个基线均无显著差异**（p=0.307–1.000），高于 Lite 与 B07，低于 Forest / IMPC / MAC。

### 15.2 合并 n=400（功效）

MAC 与 B07 未跑满全部 dev 切片，DA 上分别只有 n=303 / n=300，对照按共有病例计。

| 臂 | calls | DA400 task | DA400 concept | MCR400 task | MCR400 concept |
|---|---:|---:|---:|---:|---:|
| **Collapse3c** | **3.27–3.30** | 0.6300 | 0.2000 | **0.2925** | 0.2225 |
| MultiStance | 5.17–5.18 | 0.6175 | 0.2325 | 0.2825 | 0.2200 |
| Forest | 4.03–4.09 | **0.6375** | 0.2800 | 0.2650 | **0.2525** |
| IMPC | 4.00 | 0.6250 | **0.2925** | 0.2425 | 0.2375 |
| MAC | — | 0.6139 | 0.2343 | 0.2750 | 0.2400 |
| B07 | 3.00 | 0.6133 | 0.2100 | 0.2650 | 0.2125 |
| Lite | 3.00 | 0.6025 | 0.2575 | 0.2550 | 0.2175 |

- **MCR task**：0.2925 为六者最高。对 IMPC 42-22（**p=0.017 显著**）、Lite 34-19（p=0.053 临界）、B07 35-24（p=0.193）、Forest 31-20（p=0.161）、MAC 23-16（p=0.337）。这是本研究里 APHHM-C 系第一次在 n=400 上对一个强基线取得显著优势。
- **MCR concept**：0.2225 与 Lite（p=0.885）、B07（p=0.652，我们更高）、MAC（p=0.349）、IMPC（p=0.519）、Forest（p=0.111）全部无显著差异。结合 §14.2，我们的 exact 命中与 Forest 相同而片段得分只有一半，这个残差主要是口径而非诊断能力。
- **DA task**：与全部五个基线不可区分（p=0.305–0.917）。
- **DA concept**：0.2000，对 Lite（p=0.0018）、Forest（8e-5）、IMPC（1e-5）显著为负，对 MAC 临界（p=0.090），**对 B07 不显著**（p=0.636）。这是唯一仍然稳固的负面结论，而 §14.1 已说明该指标 95% 以上的得分来自片段匹配、200 例里 exact 命中只有 1–4 例。

## 16. 多取向生成：把 APHHM 的召回接回来（`MultiStance`）

`Collapse3c` 的转化率是全表最好的一档，但它的池召回只有 0.385 / 0.390，而原 APHHM 是 0.555 / 0.530——用的是同一个 `dc.any_match` 匹配器（`disagreement_census.py:316` 的 `tree_recall`），可以直接比。差别在代价：APHHM 的召回是用 **31.4 / 30.6 个节点**换来的。问题因此是：能不能在不回到百次级调用的前提下把这段召回接回来。

### 16.1 先离线定上界：召回由取向多样性决定，不由预算决定

把已有各臂的候选池两两取并集（纯离线，零新增调用）：

| 池 | DA200 宽度 | DA200 召回 | MCR200 宽度 | MCR200 召回 |
|---|---:|---:|---:|---:|
| Collapse3c 单臂 | 5.26 | 0.385 | 5.24 | 0.390 |
| Collapse3c + Collapse3w | 8.93 | 0.495 | 8.68 | 0.445 |
| **我们四个臂全并** | 9.98 | 0.530 | 9.98 | 0.445 |
| Collapse3w + Forest | 8.65 | **0.545** | 8.46 | 0.440 |

贪心加取向的边际曲线（六个池混选）在 DA 上是 0.455 → 0.545 → **0.590** → 0.625，MCR 上是 0.390 → 0.455 → **0.495** → 0.515，第三个取向之后基本饱和。

两个数字定住了设计：**三个取向就能在约 10 个候选上达到 APHHM 用 31 个节点换到的召回**；但我们自己四个臂全并只有 0.530 / 0.445，必须混入 Forest / Lite 才到 0.590 / 0.495。原因是我们所有臂都条件化在同一份 C1 事实账本上——**多样性被账本锚死了，改预算和措辞都换不来召回**。

### 16.2 设计：三个取向各一次调用，决策改成锦标赛

生成侧三个取向，差别在**条件化什么**而不是措辞：

| 取向 | 条件化 | 目标 |
|---|---|---|
| `commit` | 不寻常发现（沿用 §13 的承诺契约） | 罕见、案例特异的实体 |
| `coverage` | 症候群本身 | 不能跳过的常见与危险项，允许停在族级 |
| `mechanism` | **原文叙事**，事实账本仅供引用 id | 能统一整个组合的过程，绕开账本的信息损失 |

三份输出并入同一个 registry（沿用既有的 same_as / subtype 解析与生命周期事件），`ConceptNode` 记录提名它的取向集合。

决策侧的约束来自 §9.5：转化率随 shortlist 变宽而下降（宽 4.6 时 0.652，宽 6.4 时 0.551），而并集宽度是 9。因此 selector 改成**锦标赛**：先在每个取向组内选一名决赛者，再在决赛者之间定冠军，两步都在同一次调用里输出，使任何单次比较都不超过约 5 个候选。

预算：C1 + 3 取向 + selector = **5 次调用**，gap lane 触发时 6 次。实测 5.2。

### 16.3 结果：召回接回来了，DA 上超过原 APHHM

n=400（DA200 / MCR200，与全表同口径）：

| 指标 | Collapse3c | **MultiStance** | 原 APHHM | 与 Collapse3c 的检验 |
|---|---:|---:|---:|:--|
| calls | 3.31 | 5.20 | ~100 量级 | — |
| 候选宽度 | 5.25 | 9.06 / 8.80 | 31.4 / 30.6 | — |
| **DA 池召回** | 0.385 | **0.625** | 0.555 | — |
| **MCR 池召回** | 0.390 | **0.470** | 0.530 | — |
| da_task | 0.6050 | **0.6200** | 0.5900 | 21-24, p=0.766 |
| da_concept | 0.1850 | **0.2400** | 0.2000 | 3-14, **p=0.013** |
| mcr_task | **0.2900** | 0.2700 | 0.2600 | 10-6, p=0.454 |
| mcr_concept | 0.2150 | **0.2200** | 0.1900 | 6-7, p=1.000 |

- **DA 召回 0.625 高于原 APHHM 的 0.555，用的是 9.1 个候选对它的 31.4 个、5.2 次调用对它的百次量级**；MCR 0.470 是 APHHM 0.530 的 89%。
- 四个头部指标**全部 ≥ 原 APHHM**（0.620/0.240/0.270/0.220 对 0.590/0.200/0.260/0.190），但四项都不显著（p=0.24–1.00）。
- 对 `Collapse3c` 唯一显著的变化是 **da_concept +5.5pp（3-14，p=0.013）**，这也是 §15.2 里唯一稳固的负面结论所在的指标。
- **对 Forest 与 Lite 的四项差异现在全部不显著**（p=0.13–0.83），此前 `Collapse3c` 在 da_concept 上对两者分别是 p=8e-5 / p=0.0018 的显著为负。
- 代价是 mcr_task 降 2pp（10-6，p=0.454，即 4 例），以及 +1.9 次调用。

### 16.4 转化率的漏点：两轮各漏一半，且一半是口径

`diag_stance_marginals.py` 把可召回病例的损失拆到锦标赛的两轮：

| | DA200 | MCR200 |
|---|---:|---:|
| conv\|both | 0.384 | 0.468 |
| 组内赛就没提名金标 | 0.200 | 0.150 |
| 进了决赛但输掉 | 0.185 | 0.100 |

决赛败局的构成高度单一：**DA 37 例里 30 例的金标决赛者来自 `coverage`，而 35 例的冠军来自 `commit`**（MCR 15/20 与 19/20）。逐例看，约一半是真错（`commit` 把注押在另一个家族：gold `Keloidal scleroderma` 答 `Nephrogenic Systemic Fibrosis`、gold `trigeminal schwannoma` 答 `Chordoma`），另一半是 §14 那个偏置的又一次显影——`Primary CNS Lymphoma`、`Limited Systemic Sclerosis`、`Hepatic Metastasis of Melanoma` 这些**更具体且临床上更接近的答案被判为不中，而 `Lymphoma`、`Scleroderma`、`Melanoma` 判中**。`coverage` 取向恰好在批量生产被该口径奖励的欠specified 标签，这也解释了 da_concept 为什么单独显著上升 5.5pp。

各取向的边际贡献（`stance_only_gold` = 只有该取向提名了金标的比例）：

| 取向 | DA 单独宽度 | DA 独家金标 | MCR 单独宽度 | MCR 独家金标 | 出任决赛者 | 夺冠 |
|---|---:|---:|---:|---:|---:|---:|
| commit | 2.31 | 0.080 | 2.08 | 0.050 | 1.01 / 1.00 | 0.225 / 0.220 |
| coverage | 2.31 | **0.185** | 2.17 | **0.110** | 0.91 / 0.96 | 0.145 / 0.120 |
| mechanism | 1.25 | 0.085 | 1.11 | 0.035 | 0.69 / 0.66 | 0.200 / 0.200 |

三个取向都在付回自己那次调用的钱（独家金标 0.035–0.185），没有一个可以删。`mechanism` 只在 0.66–0.69 的病例里被派出决赛者，但夺冠率 0.20，与 `commit` 相当。

### 16.5 两条确定性补丁都失败了，与 §5 一致

冠军按提名取向数分层后，准确率差异极大：**三取向一致提名的冠军 DA 0.354 / MCR 0.324，只有单取向提名的冠军 0.156 / 0.083**，而后者占 22–24% 的病例。但把它当决策信号用是无效的：

| 离线换选规则（零新增调用） | DA 净变化 | MCR 净变化 |
|---|---:|---:|
| 家族级共识（末词聚族）换选 | −1 例 | +2 例 |
| 单取向冠军 → 三取向一致候选 | −1 例 | ±0 例 |
| 单取向冠军 → 任何提名更多的候选 | −3 例 | +2 例 |

金标候选的家族共识度（2.43）甚至略低于冠军（2.52）。**「共识度高则准确率高」是案例难度的混淆，不是可用的判别信号**——这与 §5–6 的结论一致：这两条确定性换选规则在当前池上拿不到净益。原报告据此把“拆分决赛”列为下一项检验；最新 E4/E5/E9 证据说明，仍可改变 evidence integration、typed admission、requested-object projection 与候选拓扑，故不能再说转化率“只能”由决策轮次撬动。

### 16.6 小结（已被 §17 的预留 development 切片部分修正）

`MultiStance` 在首个 development 切片上以 5.2 次调用、9 个候选把历史口径召回抬到 DA 0.625 / MCR 0.470，并在 da_concept 上对 `Collapse3c` 取得 +5.5pp（p=0.013）。**这一条没有在预留 development 切片复现**，详见 §17.1；历史口径的召回增益本身复现了。

## 17. 预留 development 切片复现：历史召回增益与转化损失相消

`d2_heldout200b` / `mcr_200b` 上跑满 `MultiStance`（n=400，5.13–5.17 calls），七方法齐全对照。

### 17.1 §16.3 的 da_concept 增益没有在预留切片复现

| 切片 | Collapse3c concept | MultiStance concept | 检验 |
|---|---:|---:|:--|
| DA200（dev，配置在此选出） | 0.1850 | 0.2400 | 3-14，**p=0.013** |
| **DA200b（预留 development）** | 0.2150 | 0.2250 | 6-8，p=0.791 |
| MCR200（dev） | 0.2150 | 0.2200 | 6-7，p=1.000 |
| **MCR200b（预留 development）** | 0.2300 | 0.2200 | — |

+5.5pp 在预留切片上缩到 +1.0pp。逐项看，缺口的来源不是 `MultiStance` 在 dev 上偏高（0.240 → 0.225），而是 `Collapse3c` 在 dev 上偏低（0.185 → 0.215）。合并 n=400 仍显著（9-22，p=0.029），但那份显著性由配置被选中的那一半样本驱动，不应作为结论。

预留切片上的其余对照：DA200b task `MultiStance` 0.6150 低于 `Collapse3c` 的 0.6550（26-18，p=0.291）；MCR200b task 两者并列 0.2950，为七方法历史表中最高；`MultiStance` 在 DA200b concept 上对 Forest（p=0.029）与 IMPC（p=0.024）仍显著为负。这些都是内部 development、旧端点下的描述，不是外部能力确认。

### 17.2 复现的是两个分量，而不是它们的乘积

| | DA 首切片 | DA 预留切片 | MCR 首切片 | MCR 预留切片 |
|---|---:|---:|---:|---:|
| MultiStance 池召回 | 0.625 | **0.610** | 0.470 | **0.475** |
| MultiStance conv\|both | 0.384 | **0.369** | 0.468 | **0.463** |
| Collapse3c 池召回 | 0.385 | 0.400 | 0.390 | 0.360 |
| Collapse3c conv\|both | 0.481 | 0.537 | 0.551 | 0.639 |

在 legacy-chain 口径下，召回与转化率两个分量在两个 development 切片稳定到小数点后两位。**这支持 `MultiStance` 的宽池确有覆盖增益、同时伴随条件转化损失**；但两者都依赖旧 `dc.any_match`，且并非 external replication。E2 根级 clinical-complete 与 79 臂迁移后的解释见 §17.5。

### 17.3 历史描述性拟合与新的因果边界：存在候选干扰，但不存在通用宽度定律

历史分析把全部 14 个臂（我们的 11 个 + Lite / Forest / IMPC；v0 无候选池记录）在各自可用切片上的平均 raw-pool width 与 `dc.any_match` 条件转化率放在一起回归（`diag_width_conversion.py`）。原数值保留如下：

| 数据集 | historical legacy-chain arm-level OLS | R² | naive p | 相关 |
|---|---|---:|---:|---|
| DA | conv = 0.736 − **0.0469**×width | 0.584 | 0.0015 | corr(width, conv) = −0.764 |
| MCR | conv = 0.820 − **0.0453**×width | 0.522 | 0.0035 | corr(width, conv) = −0.722 |

这两条线只描述观测宽度约 3.9–9.1 内的历史臂级均值。它们有五个不能通过“调整系数”修复的限制：

1. `conv = dc.any_match(champion,gold) / dc.any_match(pool,gold)` 的 numerator/denominator 都是 legacy-chain/片段匹配，不是 clinical-complete；DA 中绝大多数命中是 fragment surface。
2. 14 个点共享病例、缓存、生成器和 selector，且混合 n=200/n=400 与不同切片；普通 OLS 把相关臂当独立样本，故表中的 `p` 不是病例聚类、架构聚类或外部确认后的推断。
3. 条件分母随扩池改变：新暴露病例通常更难，`conv` 下降可以同时包含病例构成变化和同病例候选干扰。截距在 width=0 无解释，区间外外推还会得到不可能的负概率。
4. OLS 是条件均值线，不是 upper envelope；没有做 frontier/quantile 建模，逻辑上不能把它称为 selector 上限。
5. 两条近似相等的 pooled slope 掩盖 benchmark、candidate type、pool topology、证据质量与 selector 的交互。旧 arm-level `corr(recall,top1)` 未显著，只能写成“n=14 时未检出相关”，不能写成“recall 根本不预测 Top-1”。

新的证据把“数值巧合”与“可复现机制”分开了：

- **E5 给出局部因果复现。** [`E5_candidate_interference/REPORT.md`](../mechanism_v2/results/E5_candidate_interference/REPORT.md) 冻结共享候选文本、ID、相对顺序和 selector payload，并保证 base width-4 pool 已含 reference。在九个 E5 臂均成功服务的同一批 162 例上，model-panel clinical-complete 从 base4 的 118/162（72.84%）降至 width8 的 89/162（54.94%）：−17.90pp/四个新增候选，即 **−4.48pp/新增候选**，与旧 pooled 斜率量级接近。这是“在这一构造、这一 selector、reference 已暴露时增加候选会干扰选择”的证据，不是普适系数。
- **异质性是主结果而非噪声。** 同一 joint-common-served 面板中，DA width-4→8 为 −11.49pp（−2.87pp/候选），MCR 为 −25.33pp（−6.33pp/候选）；类型梯度则为 synonym +4.32pp、component −0.62pp、unrelated −4.32pp、parent −7.41pp、sibling −11.73pp。旧 safe-exact 轨迹进一步显示 DA 主要是共享候选重排，MCR 主要是新增 plausible disease 直接夺冠。synonym/component 构造仍有 relation-label 误分，故具体类型系数只是敏感性；但 raw width 明显只是候选语义拓扑的代理量。
- **ITA 不能全归因 membership。** 模型面板迁移中 base4 served 200/200，而 width6/8 仅 166/164；修复哨兵上限后的 ITA complete 为 74.5%→50.5%→44.5%，混合了 candidate treatment 与 differential service。common-served 才是局部 membership sensitivity，部署估计仍应保留 ITA failure cost。逐类型共同服务分析更直接证明非单调：sibling −11.52pp，而 synonym complete +4.85pp、C∪P +6.67pp（独立 typed-5 Holm `q=.02954`），component 约零。
- **model-panel 仍有假阴性边界。** 修复后的 1,173 个隐藏 E2 sentinel 上，三 reviewer 的 complete recall 为 62.16%/77.03%/81.08%，聚合 complete accuracy 为 97.70%；面板误差不会把模型多数票变成人类 root truth。E5 的大幅、同向宽度结果强化机制结论，但类型级精细系数和 clinical-complete 发生率仍需 human-root full-pool adjudication。
- **E4 反证“conversion 是 width 的函数”。** [`E4_fixed_pool_crossover/REPORT.md`](../mechanism_v2/results/E4_fixed_pool_crossover/REPORT.md) 在同一冻结 pool/证据状态上仅换 selector，模型面板 complete 从 evidence-count 的 7.75% 变为 e7 15.25%、Forest/pairwise 17.25%。Forest 对 e7 本身未在 complete 的 Holm 家族中确认，但同宽度下 9.5pp 的 control→Forest 差异已经证明证据整合可移动 conversion。
- **E9 反证“更宽必然净亏”。** [`E9_view_independence/REPORT.md`](../mechanism_v2/results/E9_view_independence/REPORT.md) 中真实多视图相对 single-anchor 的 model-panel complete 为 +3.25pp（16 gain/3 loss，Holm `q=.01328`），相对 duplicate 为 +3.50pp（17/3，`q=.01031`）。有独有对象/证据的扩展可以取得净增益，重复或低边际候选则不能。

所以旧 `top1 = recall(w) × conv(w)` 盈亏线只可作为历史 legacy-chain 条件下的探索性预算计算；它不能推出固定 `k≈5`、coverage/conversion 必然不可兼得，或 selector 已到上限。当前更合适的估计对象是：

`P(clinical-complete Top-1 | complete candidate exposed) = f(qualified width, candidate topology/type, unique evidence, requested object, order/permutation, selector, benchmark family)`。

### 17.4 历史同宽度残差：DA legacy-chain surface 差异，不是临床能力差距

对上面的拟合取残差，按「我们的臂 / 基线」分组：

| 数据集 | 我们的臂 | 基线 | Mann-Whitney |
|---|---:|---:|:--|
| DA | −0.024 | **+0.089** | **p=0.0055** |
| MCR | +0.003 | −0.011 | p=0.769 |

在这份历史 OLS 内，DA 上基线的平均残差比我们的臂高 11.3pp，MCR 未检出分组差异。结合 §14（DA concept 的得分 95% 以上来自片段匹配、200 例里 exact 命中只有 1–4 例），它最一致的解释仍是「基线更常停在能拿片段分的粗标签上」。但该检验同样把相关臂当独立点，且没有 clinical-complete pool census；因此它只能作为 legacy surface sensitivity，不能叫同宽度临床能力差距，也不能用于校正 §17.3 的斜率。

### 17.5 结论修订

- **历史覆盖增益成立，能力“召回已解决”不成立。** `MultiStance` 以 5.2 次调用、约 9 个候选把 legacy-chain pool recall 提到 DA 0.618 / MCR 0.472，两个 development 切片方向一致；但旧 matcher 不能证明 clinical-complete candidate exposure，79 臂迁移又只审 Top-1，故不能宣布临床召回问题已解决。
- **候选干扰成立，固定斜率不成立。** E5 证明 reference 已暴露时，盲目加入候选会造成直接 capture 与共享候选重排；局部 model-panel common-served 下降约 −4.48pp/候选。但 E4 的同池 selector 改善和 E9 的真实多视图净增益说明 conversion 并非 width 单变量函数。正确结论是停止 flat fixed-k fill，而不是停止候选扩展或宣布 universal sweet spot。
- **E2 根审计显示宽覆盖没有形成净 clinical-complete 优势。** `Collapse3c` 为 122/800（15.25%），`MultiStance` 为 121/800（15.12%）；两者是 21 rescue/22 loss，差异远小于确认性要求。`Collapse3c` 应保留为 specificity-retention reference，`MultiStance` 应保留为覆盖/干扰机制臂，二者都不是已确认的总体 winner。
- **默认决策改为 Lite-like，而非 `Collapse3c`。** 当前安全路径是两次独立 proposal + 一次冻结 pool comparator；选择 Lite-like 是因为其简单、可审计、served 稳定，而复杂替代品尚未证明净益，并不是因为 Lite 的 clinical-complete 最高。下一版把 `Collapse3c` 的 specificity retention、safe identity、typed requested object 和 unique-evidence admission 融入该 comparator。
- **范式修订应精确到被否定的接口。** 应退役的是无类型、无证据门控、为填满 `k` 而扩张的平坦主池；最终一次冻结候选比较器仍是可保留部件。更宽 residual coverage ledger 与小型 evidence-qualified main frontier 可以并存，候选凭独有原文证据、对象层级和反证进入主比较，而不是凭 slot。

## 18. 拆开决赛（`MSplit`）：预注册验收未通过，并意外测出运行间噪声底

按当时的历史解释，§17.3 把主要损失定位到决策侧，§16.5 又排除了两条确定性补丁，因此本报告选择 `MSplit` 检验“一次调用内锦标赛是否是问题”。它把锦标赛拆成两次独立调用：第一次只做每个取向提名一名决赛者（且明确告知它不选冠军、被它丢掉的候选后面看不到），第二次只做决赛——先点出真正能区分决赛者的发现，逐一写出每位决赛者解释了哪些、解释不了哪些，再定冠军。预算 6 次调用（gap lane 触发时 7），实测 6.18。最新证据下，这是一项具体实现检验，不再称“剩下的唯一杠杆”。

**历史预注册验收**（在运行前写进 `run_aphhm_c_multistance_split.sh`）：在同样约 9 宽的池上，legacy-chain conv 必须比 §17.3 的描述性拟合线高出比单次调用版本多 0.10 以上，即 DA conv ≥ 0.477、MCR conv ≥ 0.566。该阈值仍可判定 `MSplit` 是否达到当时承诺的工程效果，但不能把拟合线反向认证为科学上限。

### 18.1 结果：未通过，且方向是反的

| 臂 | calls | 宽度 | 池召回 | conv | 拟合线 | 残差 | top-1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| MultiStance（一次调用） | 5.20 | 9.06 | 0.625 | **0.384** | 0.311 | **+0.073** | 0.240 |
| **MSplit（两次调用）** | 6.18 | 8.97 | 0.600 | 0.358 | 0.315 | +0.043 | 0.215 |
| MultiStance（DA 验收线） | — | — | — | ≥0.477 | — | ≥+0.16 | — |
| MultiStance（MCR） | 5.20 | 8.80 | 0.470 | **0.468** | 0.421 | **+0.047** | 0.220 |
| **MSplit（MCR）** | 6.14 | 8.90 | 0.490 | 0.408 | 0.417 | −0.009 | 0.200 |
| MSplit（MCR 验收线） | — | — | — | ≥0.566 | — | ≥+0.15 | — |

不是差一点，是差了一个数量级且符号相反：多花一次调用之后转化率反而下降。任务级上 `MSplit` 的 mcr_task 掉到 0.2200，对 `MultiStance` 的两次独立运行分别是 12-2（p=0.013）与 12-2（p=0.013）——**同一个显著回退被两个独立对照复现，这一条不是噪声。**

### 18.2 机制：孤立的组内赛比嵌在同一次调用里更差

把可召回病例的损失按轮次拆开：

| | MultiStance | MSplit |
|---|---:|---:|
| DA 组内赛就没提名金标 | 0.200 | 0.200 |
| DA 进决赛但输掉 | 0.185 | 0.185 |
| MCR 组内赛就没提名金标 | 0.150 | **0.205** |
| MCR 进决赛但输掉 | 0.100 | **0.080** |

专门的决赛调用确实把决赛败局压下去了（MCR 0.100 → 0.080），但提名轮在失去跨组语境之后变差得更多（0.150 → 0.205），净效果为负。**在单次调用里，模型是先看到全部三组再落笔提名的；拆开之后提名轮只能就组论组，而「这个候选值不值得进决赛」本来就依赖于对手是谁。** 决赛轮的信息优势换不回提名轮的语境损失。

### 18.3 顺带测出的运行间噪声底：DA concept 的复现标准差约 4pp

`MSplit` 与 `MultiStance` 的生成阶段配置逐字相同，但候选池并不相同，于是补跑了一次真正的同配置重复 `MultiStance-r2`（全新缓存，其余一切不变）。**在 `temperature=0` 下生成并不可复现：**

| | DA | MCR |
|---|---:|---:|
| 两次重复的候选池 Jaccard | 0.600 | 0.618 |
| 候选池完全相同的病例 | 0.050 | 0.070 |
| 冠军相同的病例 | 0.680 | 0.750 |

两次重复的头部指标：

| 指标 | MultiStance | MultiStance-r2 | 差 | 检验 |
|---|---:|---:|---:|:--|
| da_task | 0.6200 | 0.6250 | +0.005 | 17-18，p=1.000 |
| **da_concept** | 0.2400 | 0.2000 | **−0.040** | 13-5，p=0.096 |
| mcr_task | 0.2700 | 0.2700 | 0.000 | 6-6，p=1.000 |
| mcr_concept | 0.2200 | 0.2250 | +0.005 | 4-5，p=1.000 |

**三个指标在 n=200 上稳定到 0.5pp 以内，唯独 da_concept 在两次完全相同的运行之间摆了 4.0pp（p=0.096，几乎达到显著）。**

这条测量有两个后果，都必须写进结论：

1. **§16.3 的 da_concept +5.5pp（p=0.013）落在该指标自身的运行间噪声量级内。** §17.1 把它的未复现归因于「配置在 dev 上选出」，那个解释不完整——更直接的解释是这个指标在 n=200 上分辨不了 5pp 以下的差异。两次重复本身就给出 4pp 的摆动。
2. **本报告中所有不共用 LLM 缓存的臂间 da_concept 比较，若差值小于约 5pp，都不应作为结论。** 共用缓存的那些消融（§5–6 的 `+sel`/`+wide`/`+rich`/`+clean` 共用 C1–C4 输出）不受影响，它们的差值按构造是无噪的。§15 与 §17 中对 Forest / IMPC / MAC 的 da_concept 显著为负（差值 6–10pp、p≤0.03）仍然成立，因为它们越过了这条噪声线。

为什么只有 da_concept 这么不稳？与 §14.1 一致：该指标 95% 以上的得分来自片段匹配，而片段是否命中对标签措辞的微小变化极其敏感（`Lymphoma` 命中、`Primary CNS Lymphoma` 不命中）；生成阶段每次重采样都会改写一部分标签措辞，于是噪声被这个口径放大。MCR 的官方 LLM judge 对同样的措辞变化不敏感，所以 mcr_task 在两次重复之间一例不差。

### 18.4 结论修正：`MSplit` 失败，不构成范式上限

预注册判据明确否定了这个 `MSplit` 实现：多花一次调用后，legacy-chain conversion 与 MCR task 均未达到阈值，且 MCR 提名阶段因失去跨组语境而显著回退。可以写的是“把当前锦标赛机械拆成孤立提名 + 决赛没有价值”，不能写成“所有候选比较器都受两条 OLS 直线封顶”。

把旧上限主张撤回有三项直接理由：

1. §17.3 的 OLS 是历史、相关臂级的条件均值，不是 upper envelope，也不是 clinical-complete estimand；`MSplit` 在同一旧指标下失败不能把描述线变成因果界。
2. E4 在候选宽度完全固定时，证据整合/selector 可移动 model-panel clinical-complete；所以 selector 仍有可改进空间，只是 evidence-count、当前 e7 和这个 MSplit 不是答案。
3. E9 已显示真实独有 view 能在扩展候选/证据状态时取得净 complete 增益；主动取证是可能路径之一，但不是越线的唯一逻辑路径。

因此“必须修改范式”的精确版本是：**退役 flat、untyped、fixed-k、one-shot list ranking 作为唯一状态；保留一次冻结池 comparator，并在其前加入 safe identity、requested-object projection、typed candidate、unique-evidence admission，以及 residual coverage ledger / evidence-qualified main frontier 的两层状态。** selector 应做 permutation-aware 的病例特异比较，候选删除必须绑定同对象、同 episode 的更强反证。是否需要主动获取新证据由缺失 discriminator 触发，而不是因为旧 OLS 被误称为上限。

## 19. 下一步（按信息量排序）

79 臂迁移已经关闭 **Top-1 model-panel endpoint naming** 缺口，却没有关闭 clinical pool exposure、human-root ownership 或外部泛化缺口。下一步不应继续围绕旧直线微调 coefficient，而应改变 estimand 与实验设计。

1. **先补 full-pool clinical relation census，再谈新的 conversion 系数。** 79 臂迁移的统计单位是 arm-case Top-1；它既不覆盖旧 14 臂的完整候选池，也没有为每个 pool candidate 提供 clinical-complete/compatible-partial relation，因而旧回归所需的 clinical pool exposure 分母不存在。可选择对冻结旧池做盲法 full-pool adjudication，或执行一个规模更小但预注册完整的新嵌套池实验；在此之前禁止把 79 臂 Top-1 率除以 safe/legacy pool recall 来制造“clinical conversion”。
2. **用 human-root 复核 E5 的局部面板结论。** 新实验应保证 base pool 暴露 clinical-complete reference，而不只是 safe-exact；按 true synonym/parent/sibling/component/unrelated 分层随机加项，并随机候选位置/排列。主分析报告 ITA 与 common-served，使用病例聚类或病例随机效应模型，检验 family×type×width 交互和非线性；不能只拟合 `a−b×width`。模型面板约 −4.48pp/候选是优先复核的局部锚，不是待直接写入正文的 universal coefficient。
3. **实现 Lite-like + specificity-retention 的下一版，而不是复活 MSplit。** 两次 proposal 相互独立；registry 仅 exact/frozen synonym 合并；候选输出 type、requested-object、独有 raw span、strongest counterevidence；主 frontier 不固定填 `k`，其余进入 append-only coverage ledger；第三次调用在冻结 payload 上做 completeness-first、permutation-aware comparator。
4. **把 E4/E9 变成组合式可证伪实验。** 固定同一 pool、证据和 selector 分别改变 candidate membership、candidate-unique evidence 与 view provenance，至少重复若干候选排列。目标是分开估计直接 capture、共享候选 context reorder、evidence rescue、schema/service failure，而不是再把它们压成 width 一个变量。
5. **建立真正未触碰的外部确认集。** 当前完整 800 例都属于 development。若要发表“优于基线”或给出稳定临床能力排序，应在冻结 architecture、prompt、provider policy 与统计方案之后增加未参与开发的新病例/数据集；仅把当前 n=400 扩到 n=1000 不能消除重复开发偏倚。
6. **正式退役 DA `concept` 作为能力判据。** §18.3 的约 4pp run-to-run 波动与 §14 的片段奖励共同说明它最多是 legacy surface sensitivity。主端点用 root clinical-complete；compatible-partial/C∪P、safe-exact、legacy-chain、DA task 和 MCR task 分栏报告，不互相改名。复合 gold 若需自动分析，应另设 component/scope coverage，而不是延续 substring 二值命中。
7. **fresh task replay 与临床迁移严格解耦。** 其完成覆盖以 [`ALL_ARM_ENDPOINT_MIGRATION/REPORT.md`](../mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION/REPORT.md) 最新 manifest 为准；无论缓存是否最终补齐，DA mapper 与 MCR judge 都必须分族报告，非随机 partial cache 不作配对推断，也不能补足 full-pool clinical relation 缺口。
8. **停止无结构的 prompt/固定宽度 arms，而不是停止所有生成研究。** 新臂只有在检验上述 admission、对象投影、证据唯一性、排列鲁棒性或 residual-ledger 机制时才有信息量。原设计 §10.1 的 `2^3` 因子表已不足以回答这些新 estimand，不应按旧定义机械补跑。

## 20. 产物

- 实现：`src/agentclinic_tree_dx/aphhm_c.py`、`scripts/paper/run_aphhm_c.py`、`scripts/paper/test_aphhm_c_unit.py`（13 项结构性测试）
- prompt：`src/agentclinic_tree_dx/prompts/aphhm_c_{fact_ledger,axis_contract,batched_concepts,batched_concepts_v2,batched_concepts_noaxis,batched_concepts_evid,batched_concepts_evid_wide,batched_concepts_commit,complement,global_matrix,adjudicator}.txt`、多取向用 `aphhm_c_stance_{coverage,mechanism,nomination}.txt` 与 `aphhm_c_final_adjudicator.txt`、五个消融用 `aphhm_c_frontier_selector{,_rich,_clean,_candev,_tournament}.txt`、离线审计用 `aphhm_c_label_audit.txt`
- 运行脚本：`analysis/backbone_v1/run_aphhm_c_pilot200.sh`、`run_aphhm_c_selector200.sh`、`run_aphhm_c_selranks.sh`、`run_aphhm_c_width.sh`、`run_aphhm_c_noaxis.sh`、`run_aphhm_c_candev.sh`、`run_aphhm_c_collapse3w.sh`、`run_aphhm_c_collapse3c.sh`、`run_aphhm_c_collapse3c_200b.sh`、`run_aphhm_c_multistance.sh`、`run_aphhm_c_multistance_200b.sh`、`run_aphhm_c_multistance_split.sh`
- 评估：`analysis/backbone_v1/eval_aphhm_c.py` → `mosaic_eval/aphhm_c_pilot200.json`；`audit_concept_purity.py` → `mosaic_eval/concept_purity.json`；`diag_slot_efficiency.py` → `mosaic_eval/slot_efficiency.json`；`diag_da_conversion_failures.py` → `mosaic_eval/da_conversion_failures.json`；`diag_da_match_bias.py` → `mosaic_eval/da_match_bias.json`；`eval_aphhm_c_holdout.py` → `mosaic_eval/aphhm_c_holdout.json`；`diag_stance_marginals.py` → `mosaic_eval/stance_marginals.json`；`diag_width_conversion.py` → `mosaic_eval/width_conversion.json`
- 逐例轨迹：`logs/backbone_v1/{diagnosisarena,diagnosisarena_heldout,medcasereasoning,medcasereasoning_v2}/aphhm_c_{v1,sel_v1,wide_v1,rich_v1,clean_v1,k10_v1,k6_v1,k4_v1,nocond_v1,noaxis_v1,candev_v1,collapse3_v1,collapse3w_v1,collapse3c_v1,multistance_v1,multistance_r2,msplit_v1}/case_stages/`

全部 17 个 APHHM-C 臂 × 400 例的口径一致结果都在 `aphhm_c_pilot200.json` 的 `leaderboard` 与 `mcnemar_all_pairs`（1200 组配对检验）中。
