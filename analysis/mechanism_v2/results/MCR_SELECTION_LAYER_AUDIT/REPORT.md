# MCR_SELECTION_LAYER_AUDIT — 冻结 payload 里还剩多少可提取信号

日期 2026-08-21 · 零在线调用 · 复现 `python3 analysis/mechanism_v2/mcr_selection_layer_audit.py`

## 起因

`MCR_SELECTOR_TRUNCATION_V1` 返回 NO_GO 之后，有三个后继干预被先后提出：

1. 换候选集（用 APHHM 非选项泄露版 L2 列表作候选，看转化是否改善）；
2. 改比较器判据（翻转 tournament prompt 第 24–25 行的 family-vs-subtype 默认方向）；
3. 重排 payload（用一个真实分数替代任意的生成序）。

本审计在花任何在线调用之前，用冻结日志把这三条逐一验掉，并定位真正的约束层。

队列与 `MCR_SELECTOR_TRUNCATION_V1` 一致：池内可达的 **167/400** 例（registry 至少含一个被临床 panel 判为 `complete_equivalent` 的标签），dev = mcr_v1 + mcr_v2（73），holdout = mcr_200b（94）。这是选择层唯一可能获益的切片。

## Q1 63 例损失的构成：不是粒度退让

| 冻结冠军关系 | 例数 |
|---|---|
| `complete_equivalent` | 104 |
| `not_equivalent` | 25 |
| `conflicting_subtype_or_scope` | 17 |
| `manifestation_or_related` | 13 |
| `partial_parent_or_component` | **8** |

主导失败模式是**放着 shortlist 里的精确匹配不选、去选一个临床上不同的同族兄弟**，而非退到父类：

| gold | 池内完整标签 | 冻结冠军 | 关系 |
|---|---|---|---|
| Leiomyosarcoma | Leiomyosarcoma | Malignant solitary fibrous tumor | `not_equivalent` |
| mucormycosis | Mucormycosis | Blastomycosis | `not_equivalent` |
| Schwannoma | Schwannoma | Ganglion cyst | `not_equivalent` |
| Fibrous dysplasia | Fibrous Dysplasia | Juvenile Ossifying Fibroma | `conflicting_subtype_or_scope` |
| Contrast-induced encephalopathy | Contrast-induced encephalopathy | Hypoxic-ischemic encephalopathy | `conflicting_subtype_or_scope` |

**结论：干预 2 作废。** family-vs-subtype 规则最多覆盖 8/63；这些是需要决定性证据（组织学、影像、培养）才能分开的鉴别，不是粒度政策问题。

## Q2 证据是反向的：比较器是照 prompt 正确执行的

在 63 例损失里，对比正确候选（C）与被选中冠军（W）在 payload 中携带的证据：

| | C（正确） | W（冠军） |
|---|---|---|
| `for` span 均数 | 2.29 | **3.84** |
| C 的 `for` 更少 | **48/63** | — |
| 带 `against` | **42/63** | 28/63 |
| C 有 `against` 而 W 没有 | 21/63 | — |
| payload 位置均值 | 2.97 | **0.70** |
| C 位置更靠后 | **55/63** | — |

tournament prompt 的判据是"权衡 `for` 与 `against`；带强 `against` 的候选通常是错的；偏好能解释最多决定性发现的候选"。正确候选系统性地带着**更少的支持证据和更多的反对证据**进来——比较器给出错误答案，是**忠实执行了一份被污染的输入**。缺陷在选择器上游的逐候选证据分配。

## Q3 比较器相对"取第一个"只值 +11 例

同一 payload 上三种决策规则：

| 规则 | complete（167 例） | 成本 |
|---|---|---|
| 比较器（1 次 LLM 调用） | **104** (62.3%) | 167 次调用 |
| 盲取 payload 位置 0 | **93** (55.7%) | 零 |
| 盲取 `for` span 最多者 | 59 (35.3%) | 零 |

比较器与位置 0 的选择一致率为 **130/167 = 77.8%**。首个完整标签的位置分布高度集中在头部：pos 0 有 93 例，pos 0–2 累计 136/167（81.4%）。

两点读数：整个 LLM 比较步骤的边际价值是 **+11 例**；而它显著优于按证据数量选（59），说明比较器并没有单纯跟随证据体量，它确实在读 vignette——只是被证据偏置拖住。

## Q4 生成序已经是最优的可得排序

multistance 臂的 `enable_matrix=False`，因此 registry 上每个概念的 `score` 恒为 0.0，`ledger_rank` 退化为 `concept_id` 生成序。这一度看起来是"排序信息被浪费了"。实测相反——把 8 个可从冻结 payload 计算的排序与生成序对比（选择只在 dev 上做）：

| 排序 | dev top1 | dev top3 | holdout top1 | holdout top3 |
|---|---|---|---|---|
| **gen_order（现状）** | **39** | **60** | **54** | **76** |
| specificity_desc | 33 | 59 | 40 | 72 |
| stance_desc | 28 | 52 | 41 | 69 |
| stance_then_specificity | 27 | 52 | 39 | 64 |
| specificity_then_stance | 27 | 56 | 35 | 68 |
| for_desc | 23 | 49 | 36 | 68 |
| for_minus_against_desc | 23 | 49 | 37 | 64 |
| specificity_no_against_gen | 22 | 50 | 30 | 56 |
| no_against_first | 21 | 46 | 34 | 52 |

生成序在 dev 与 holdout 上同时胜过全部替代排序。生成器把最有把握的猜测放在第一位，这是个真实的置信排序；而基于证据计数的排序最差，与 Q2 一致。

**结论：干预 3 作废。** 冻结 payload 里没有比生成序更好的无 oracle 排序，重排只会掉点。这也解释了截断为什么近似中性——截断保留的正是排序最好的头部候选。

## 换候选集（干预 1）：另有独立证据否掉

不需要绕道 APHHM L2 就能做干净的换池对照，因为 Collapse3c 本身是 APHHM-C 臂，证据契约一致且池标签 100% 有临床判定。MCR 全 400 例：

| | 池宽 | 池内可达 complete | 冠军 complete | 给定可达的转化率 |
|---|---|---|---|---|
| multistance | 8.75 | 167/400 | 104/400 | 62.3% |
| collapse3c | 5.24 | 154/400 | 107/400 | 69.5% |

池内可达性 2×2：两池都可达 145，**仅 multistance 可达 22**，**仅 collapse3c 可达 9**，都不可达 224。换池净可达性 **−13**，两池并集天花板 176（比 multistance 单独只多 9）。Collapse3c 的全部优势在转化率，不在候选质量。

至于 APHHM L2 这条具体路线，另有三个独立阻碍：

- **证据契约为空。** 冻结树 1831 个 L2 branch 与标注树 3060 个 branch 的 `evidence_for`/`evidence_against` 全部为空，只有 `posterior`。选择器 payload 的每个候选是 `{label, for, against}`，喂 L2 等于喂裸标签，对照会退化成"抽掉证据"的效应（E4 已测得证据整合在同一池上值约 +9.5pp），无法回答候选质量问题。`p5_audit` 里确有逐候选证据，但那是外部文献块（`source: CPG`，`chunk_id: pmc_oa_ddx__…`）挂在粗家族标签上，250 条 effect 中 243 条为 `neutral`/`unknown`。
- **队列只有 100 例。** 非选项泄露的 `aphhm_clean_v1` 仅存在于 mcr_v1；mcr_v2 只有泄露版 `compat_synonym_v1`，mcr_200b 没有 classic L2。
- **80% 标签无临床判定。** 冻结树 1445/1812 未判定，覆盖率随 posterior 名次从 53% 衰减到 23%；标注树好些（56% 未判定）但仍需新裁决。而其池内完整下界（冻结 31/100、标注 34/100）与 multistance 在同一 100 例上的 30/100 持平。

## 综合：约束在证据分配层

选择层的可提取信号已接近榨干：**93 例免费**（取第一个），**104 例已实现**（比较器），而剩余 63 例所需的信息**不在 payload 里**——正确候选携带的证据本身弱于错误对手（Q2），所以任何对给定 payload 的重新加权、重排、截断都无法把它们捞回来。这与三次实验结果自洽：截断中性（NO_GO）、重排掉点（Q4）、换池净负（−13）。

唯一尚未被否掉的假设是**逐候选证据分配质量**：生成器在提出正确诊断时，给它写了稀薄的支持与显式的反对。这是 MCR 的绑定约束，也是下一个该测的层。

> **追记（2026-08-21）：该假设也已被否，MCR 选择层项目结束。**
> [`MCR_EVIDENCE_SYMMETRY_GATE_V1`](../MCR_EVIDENCE_SYMMETRY_GATE/REPORT.md) 证实不对称主要是
> 写法产物（PASS），但 [`MCR_EVIDENCE_REASSIGNMENT_V1`](../MCR_EVIDENCE_REASSIGNMENT/REPORT.md)
> 用去偏置后的证据重跑选择器得到 **−6 例**（p = 0.362），且 `sym_shuffle − shuffle_only` = −1
> （p = 1.000），触发预注册的否证形态。
>
> 该实验同时更正本报告 Q3 的一处解读：77.8% 的位置 0 顺从率**不是**朴素的位置偏好。定种打乱
> payload 顺序后，冠军落在位置 0 的比例掉到 **30/167 = 18.0%**——比较器并未退化成"仍取第一个"，
> 而是按内容与生成序达成一致；毁掉该顺序要付 **−11 例**（p = 0.043 名义、Holm 0.130）的代价。
> 由此 Q4"生成序已是最优可得排序"从离线推断升级为在线实测。
>
> 综合读数：生成器写给自己最有信心的候选的那份"膨胀"证据，膨胀正**因为**它更有信心，而这份
> 信心是真信息——次序性偏置同时是一条**置信通道**。选择器输入空间的四个维度（候选集来源 −13、
> 名单宽度 −2/−5、payload 顺序 −11、逐候选证据 −6）全部为中性或更差，冻结配置处于局部最优。
> MCR 的剩余头寸在**生成层**，不在选择层或证据格式层。

## 对既有文档的影响

- `MCR_SELECTOR_TRUNCATION/REPORT.md` 的机制诊断（"比较器对截断不敏感、变动时退向更粗的父类"）在方向上成立，但本审计给出更准的定位：退向父类只占 8/63，主导模式是同族误判，且根因在证据分配而非比较器判断。
- `CLINICAL_RESCORE/REPORT.md` §5 记录的 63 例选择层缺口数值不变，机制归因应更新为证据分配层。
