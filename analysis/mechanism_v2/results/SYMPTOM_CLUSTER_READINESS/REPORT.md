# 症状集群证据能否上线测试：就绪度调研

> **历史状态说明（2026-08-25）：** 本文的“生成层是唯一还开着的路径”是 G1 前的就绪度结论；G1 已按原
> canonical-key identity gate 关闭该生成式干预。后续逐案审计又证明该 gate 不能解释成 clinical-complete
> recall，但并未挽救 G1 的高扰动/低命题增益实现。当前只支持另立的 candidate-blind、query-only fuzzy
> target-profile proposal 进入受控测试；typed-subgraph matcher 与 residual lane 尚未实测；见
> [`../../PHENOTYPE_SUBGRAPH_RETRIEVAL_ITERATION_REPORT.md`](../../PHENOTYPE_SUBGRAPH_RETRIEVAL_ITERATION_REPORT.md)。

**日期**: 2026-08-21
**性质**: 零调用调研（冻结产物 + 代码审查 + 知识资产盘点），无 LLM 调用、无 panel
**复现**: `python3 analysis/mechanism_v2/symptom_cluster_readiness.py` → `audit.json`
**队列**: `aphhm_c_multistance_v1`，400 例 MedCaseReasoning（4641 条 fact，3415 个带证据的候选）
**动因**: Auditing Evidence Use in Medical LLM Diagnosis (2607.20848) 主张诊断力来自 2–3 个症状构成的集群；`症状集群.md` 给出候选实现路径

---

## 0. 结论

**"集群"这个方向有真实信号，但它只能进生成层；作为证据重排上线已被本轮实测否证。**

第一版报告（§1–§4）做的是资产与能力盘点，第二版（§5–§9）执行了它推荐的探针并处理了
两个追加问题。合并后的结论有四条：

1. **A 类"冗余打包"已经实现且有全量数据，但打开它并不值。** `ObservedFact.correlation_group`
   在 400 例 4641/4641 条 fact 上全部被填充，`EvidenceLedger.score_concept` 已按组
   clip 去重。这机制在 **12 个 c4 家族臂上一直在跑**（并非普遍空转）；用冻结 `ledger.cells`
   做的零调用反事实显示：打包改变冠军的 36 例里，**打包 0 例完整、关打包 5 例完整**，
   4 个臂方向一致。空转只发生在 **collapse3c 家族 4 个 + multistance 家族 5 个**臂上，
   而 **forest / IMPC / mosaic 等 61 个臂连槽位都不存在**。

2. **步骤 0 探针已执行并被否证。** 把证据从 span 计数改写为相关组计数，转化率
   **0.355 → 0.307**（59 → 51），方向与"冗余膨胀"假设相反；全部混合策略均不超过
   生成序基线的 93。

3. **但集群信号在候选层是真的。** 按不同高特异性组数分桶，完整率
   **0.030 / 0.054 / 0.086 / 0.120**（0/1/2/3 组），单调上升 4 倍，量级正落在论文所说的
   2–3 区间。**起作用的是特异性而非多重性**——`n_high_groups`(76) 明显优于
   `n_groups`(51) 与 `n_spans`(59)。它无法转成排名收益，是因为生成序（0.560）已经
   吸收了这份信息。

4. **B 类"合取判别子"的查表与接地两条路都不通，且这是方法性失败。** SNOMED 综合征词典
   9028 条，对 4641 条 fact 的精确解析率 **0.11%**；HPO 精确接地 **3.8%**，表面的 75.2%
   是双向子串匹配的假象（"血沉 73 mm/h" → 类风湿关节炎）。这是实体链接方法落后所致，
   改进它是做 B 类的必要前提——但**不会让已被否证的重排路线复活**（§9）。

**因此唯一还开着的路是把集群放进生成层**：让生成器在提出候选时就指明支撑它的 2–3 个
特异性发现组合，并据此定置信度。这与本项目累积结论"MCR 的剩余头寸在生成层"收敛。

---

## 1. 两类"集群"必须分开处理

`症状集群.md` 区分了两种被混称为"集群"的结构，本仓库对二者的就绪度截然不同：

| | A 类：冗余打包 | B 类：合取判别子 |
|---|---|---|
| 语义 | 多条 finding 反映同一底层过程 | 组合本身才有判别意义 |
| 需要的操作 | **压制**（避免重复计数） | **上调**（组合分 > 分量和） |
| schema | `correlation_group` 就位 | 无槽位 |
| 数据 | 4641/4641 已填充 | 无 |
| 算法 | `score_concept` 已实现组内 clip | 无 |
| 在 multistance 中 | 空转（C4 跳过） | 不存在 |

关键点：**`correlation_group` 的方向与 B 类相反。** `aphhm_c_fact_ledger.txt` 的指示是
"groups facts that are the SAME underlying observation restated (e.g. an imaging
description and its impression)"，示例可见 case 109 的 G6 把头 CT、脑 MRI、复查 MRI 的
同一病灶归为一组。`GROUP_CLIP = 3` 是在**截断**组内叠加。所以现有机制不能直接充当
论文所指的判别单元，把它当作 B 类使用会得到符号相反的效果。

---

## 2. A 类：已建成但未通电

### 2.1 数据（Q1/Q2）

400 例、4641 条 fact、3625 个相关组，均 9.06 组/例。组规模分布：

| 组规模 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| 组数 | 2870 | 565 | 141 | 36 | 7 | 4 | 1 | 1 |

含 ≥2 条 fact 的组占 **20.8%**，规模 2–3 的组占 **19.5%**——与论文所述的 2–3 量级吻合，
但语义是冗余而非合取。

### 2.2 代码路径

```
ObservedFact.correlation_group          aphhm_c.py:159   字段
ObservedFact.group_key                  aphhm_c.py:166   回退到 fact_id
EvidenceLedger.score_concept            aphhm_c.py:711   按 group_key 聚合
  clipped = max(-GROUP_CLIP, min(GROUP_CLIP, raw))       GROUP_CLIP = 3
  rel = max(RELIABILITY_WEIGHT[...])                     组内取最高可靠性
test_correlation_group_clips_double_counting             单测保护
```

### 2.3 为什么它在 MCR 上没生效

```
self.enable_matrix = mode not in ("c4_selector_candev_nomatrix",
                                  "multistance", "multistance_split")   aphhm_c.py:844
...
stages["c4"] = {"skipped": True, "reason": f"mode={self.mode}"}         aphhm_c.py:1783
```

C4 被跳过 → 无 `EvidenceCell` → `score_concept` 找不到 admitted cell → 分数全为 0.0 →
`ledger_rank` 退化为 `concept_id`（生成序）。这与 `MCR_SELECTION_LAYER_AUDIT` 观察到的
"生成序已是最优离线排序信号"是同一个事实的两面：**multistance 根本没有证据打分层。**

### 2.4 重开证据层的成本

`_annotate_matrix` 按 fact 行分块，每块携带全部候选，`n_chunks = 2 if cells > 180 else 1`。
实测 fact/例 11.6、候选/例 8.75、cells/例 ≈ 101.6 < 180，故绝大多数病例 1 次调用。
**400 例约 400–500 次调用**，与已执行的截断实验（495）同量级，远低于证据重派（1801）。

---

## 3. B 类：查表与接地两条路都不通

### 3.1 命名复合体查表（Q3）

`knowledge/compound_finding.py` 是既有的"候选盲复合发现表示"实现（TALP 实验遗产）：
`atomize()` 做规则化原子拆分，`SyndromeResolver` 把复合文本解析为带 provenance 与
entailment 校验的 SNOMED 综合征，支持 legacy/atomic/syndrome/dual 四模式。它**未接入
`aphhm_c.py`**，只在 `probe_compound_findings.py`、`eval_talp_discrimination.py`（`--compound_mode`）
与测试中被引用。

按 `eval_talp_discrimination.py` 的构建方式（`snomed_term_index.json` 中含 "syndrome"
且 tag 为 disorder 的词条）得到 **9028 条**词典，在 4641 条 fact 上：

- 解析出综合征：**5/4641 = 0.11%**
- 5 例全部形如 `hepatorenal syndrome`、`irritable bowel syndrome`——vignette 直接写出了
  综合征名，等于零增益，且接近 `provisional_diagnosis` 应被隔离的情形

失败根因是 `SyndromeResolver.resolve` 用精确归一化字符串匹配（`self.entries.get(norm)`），
而 fact 是逐字叙述性 span。**复合体必须被发现，不能被查表。**

顺带一个反向信号：**32.9% 的 fact 在表层就可拆为 >1 个原子**（原子数 2 的 1158 条、
3 的 301 条）。这说明抽取层输出的"单条 finding"本身常已是复合体——集群工作的第一个
真实抓手可能是**拆分**而非**聚合**。

### 3.2 本体接地（Q4）

| 指标 | 值 |
|---|---|
| HPO 词条 / 同义词 | 19,389 / 46,486 |
| 精确接地 | 178/4641 = **3.8%** |
| 精确 + fuzzy | 3489/4641 = 75.2% |

**75.2% 不可信。** `resolve_fuzzy` 是双向子串匹配并返回字典迭代中的首个命中
（`hpo_index.py:114-123`）。12 例随机抽样（仅 fuzzy 命中者）中仅 1 例正确：

| fact span | fuzzy 结果 |
|---|---|
| no pallor, jaundice, or palpable peripheral lymphadenopathy | **All** (HP:0000001，根节点) |
| erythrocyte sedimentation rate of 73 mm/h | **Rheumatoid arthritis** |
| mild thrombocytosis (120 × 10^9/L) | **Myocardial infarction** |
| an adenosine deaminase of 23.8 U/L | **Myocardial infarction** |
| a 5 × 10 cm soft, fluctuant, non-tender mass ... right knee | **Right** |
| leftward septal deviation | **Left** |
| severe thrombocytopenia (platelet count, 1 × 10^9/L) | Thrombocytopenia ✓ |

`Rheumatoid arthritis` 反复出现是因为其同义词含两字符串 `ra`，它是
`Noncont**ra**st`、`e**ra**te` 等的子串。否定也被丢弃（`no ... lymphadenopathy` → 根节点）。

可用的替代资产存在但需新建：`hpo_embeddings.npy`(69 MB) + `hpo_embedding_metadata.json`
可支撑 RAG-HPO 式检索接地；`knowledge/finding_normalizer.py`(35 KB) 对实验室值与生命
体征有生产级解析（参考区间、单位换算、方向判定、HPO 查找）。但 fact 的两个最大 modality
是 **history(1420)** 与 **imaging(990)**，恰好都不在 `FindingNormalizer` 的覆盖范围内
（laboratory 仅 754、exam 1128）。

### 3.3 知识侧依赖边（Q5）

`phenotype.hpoa`：282,723 行、12,996 疾病、727 条 NOT（排除性）注释、218,572 行带 frequency。
质量可用，但**命名空间 100% 是 OMIM(166,574) + ORPHA(115,853) + DECIPHER(296)**——罕见病
与孟德尔病。

本队列 400 条 gold 中精确落入 hpoa 的只有 **66/400 = 16.5%**。MedCaseReasoning 的 gold
形如 `Liver metastasis from colon cancer`、`Tumor-induced osteomalacia`、`cryptococcoma`，
是获得性/肿瘤性/感染性诊断，HPOA 结构上不收录。**疾病条件化共现最多只能覆盖 1/6 队列。**

其余资产盘点：

| 资产 | 状态 | 对集群工作的价值 |
|---|---|---|
| `snomed_relations.json` (40 MB) | 在 | DUE TO / AFTER / finding site，可做机制与解剖依赖 |
| `primekg_index.py` | 代码在 | 需核对底层数据是否落地 |
| `mechanism_to_disease.json` | 仅 5 KB | 太小，不足以替代 DisMech |
| `lr_cache.json` + `rag_lr_secondary_cache.*` | 在 | 单 finding LR，非联合 LR |
| `pathognomonic_markers.json` / `diagnostic_markers.json` | 在 | 单 finding 高特异性标记 |
| DisMech / PhenoSS | **缺** | `症状集群.md` 重点依赖的两项均不在仓库 |

---

## 4. 立即可做的零调用探针（Q6）

这是本次调研最有价值的发现。把候选证据从 span 计数改写为**不同相关组计数**，全部前置
条件已具备：

| 指标 | 值 |
|---|---|
| 候选 support_span 总数 | 8102 |
| 可连接到某条 fact 的 span | 7932 = **97.9%** |
| 有证据的候选数 | 3415 |
| span 数/候选（均值） | 2.37 |
| 不同相关组数/候选（均值） | 1.95 |
| span 数 > 不同组数（含冗余重复计数）的候选 | 1104/3415 = **32.3%** |

连接方式是 span 与 fact `raw_span` 的子串重叠——两者都是 vignette 的逐字子串，所以
97.9% 的连接率是结构性的，不依赖任何模糊匹配。

**为什么这值得先做**：`MCR_SELECTION_LAYER_AUDIT` 已确认"证据数量与正确性呈反向关系"
（证据越多的候选越可能是错的）。若这个反常符号部分来自冗余膨胀——一个候选拿到 4 条
其实是同一观察复述的 span，看起来就比只有 2 条独立组证据的候选更强——那么按组去重后
符号可能翻转，从而给出一个此前不存在的可用离线排序信号。这个假设**零成本可证伪**。

注意这不与既有否证冲突。三次已执行的干预（截断、证据重派、候选质量）都在**不改变
证据计量单位**的前提下操作选择层输入；本探针改变的是计量单位本身。

---

## 5. 空转不是普遍现象：三档 regime（Q7）

对全部 82 个有冻结日志的 medcasereasoning 臂逐一检查（每臂取前 60 例），得到三档互不相同
的状态。**"打开开关即可获益"只对其中一档成立，而对另一档连开关都不存在。**

| regime | 臂数 | 判据 | 代表臂 |
|---|---|---|---|
| **live** 机制真在跑 | **12** | c4 存在，候选分数非 0 | `aphhm_c_v1`(c4)、`sel`/`wide`/`rich`/`clean`、`k4`/`k6`/`k10`、`candev`、`noaxis`、`nocond` |
| **inert** 有槽位有数据但空转 | **9** | facts 全带 `correlation_group`，但 c4 被跳过、分数全 0 | **collapse3c 家族 4 个**（`collapse3_v1`/`collapse3c_v1`/`collapse3c_r2`/`collapse3w_v1`，mode `c4_selector_candev_nomatrix`）+ **multistance 家族 5 个**（`multistance_v1`/`_r2`/`_contractfix`、`msplit_v1`/`_r2`） |
| **absent** 连槽位都没有 | **61** | 无 facts 层，无 `correlation_group` | **forest**（`compact_forest_v0/v1/v11`、`mosaic_forest_v1/_r2`）、**IMPC**（`mosaic_impc_v1/_r2`）、mosaic lite/adaptive4、以及全部 e*/r4/r5/r6/v0 探针臂 |

回答问题 1 的三个分支：

- **collapse3c 与 multistance 完全同病**。两者 mode 不同（`c4_selector_candev_nomatrix`
  vs `multistance`）但都在 `enable_matrix` 的排除表里，实测 c4 跳过 60/60、分数 0/313。
  对它们而言这是**一次开关翻转**的距离。
- **forest 与 IMPC 不是空转，是结构性缺失**。它们的 evidence 行只有
  `evidence_id / raw_span / polarity / epistemic_status / modality / reliability / source_view`，
  **没有 `correlation_group`，也没有 `specificity`**；`compact_forest` 更薄，只有
  `evidence_id / raw_span / source_view`。它们也没有 `EvidenceLedger`，候选带的是
  `score_logit` 而非 ledger 分数。所以对 forest/IMPC 而言这不是开关，而是
  **prompt + schema + 打分层三处改动**。
- **c4 家族 12 个臂里机制一直在跑**，这给了我们一个免费的自然实验来判定"打开它值不值"。

---

## 6. 打开它并不值：live 臂上的自然实验（Q8）

`c4` 与 `c4_selector_clean` 等 mode 中，`aphhm_c_v1`、`aphhm_c_v1_r2`、`noaxis`、`nocond`
不在 `SELECTOR_MODES` 内（`aphhm_c.py:823`），冠军就是 ledger argmax，没有 LLM 选择器介入。
因此用冻结的 `ledger.cells` 逐例精确重算 `score_concept`，比较**打包开 / 打包关**两种
argmax，就得到一个零调用的反事实。

保真校验：`registry[].score − 重算 total` 落在 `{0.0, 0.1, 0.125, 0.167, ...}` 这样的
小集合上（即 `axis_bias`），说明重算与冻结分数逐例吻合，不是近似。

| 臂 | clip 触顶组 | 分数被打包改变的候选 | 冠军翻转例 | 打包→完整 | 关打包→完整 | Δ |
|---|---|---|---|---|---|---|
| `aphhm_c_v1` | 472 | 364/1620 | 9 | 0 | 2 | **−2** |
| `aphhm_c_v1_r2` | 472 | 349/1628 | 15 | 0 | 0 | 0（5 例无判定） |
| `aphhm_c_noaxis_v1` | 184 | 161/1213 | 6 | 0 | 2 | **−2** |
| `aphhm_c_nocond_v1` | 171 | 138/1166 | 6 | 0 | 1 | **−1** |

三点读数：

1. **clip 确实在 binding**（472 组触顶），**22.5% 的候选分数被打包改变**——机制不是装饰。
2. **但冠军只在约 7% 的病例翻转**（9/200、15/200、6/200、6/200）。
3. **翻转的 36 例里，打包一次都没产出完整冠军，关掉打包产出了 5 例。** 方向在 4 个臂上
   一致，从未有一例偏向打包。

关于强度的诚实说明：36 例翻转、8 例无临床判定，样本很小；且 `aphhm_c_v1` 与 `_r2` 是
重复运行、`sel`/`wide`/`rich`/`clean` 与 `v1` 共享 C1/C4 阶段（472 与 364 完全相同），
因此有效独立观测只有 2–3 个，不能当作显著性结论。但**方向一致且从不为正**，足以否掉
"翻开关就有收益"这一预期。

**因此对 collapse3c/multistance 的建议是不要仅为这套机制翻开关**（虽然只需一次改动）；
对 forest/IMPC 更不建议投入三处改动去移植一个在 live 臂上不产生收益的机制。

---

## 7. 步骤 0 已执行：假设被否证（Q9）

按上一版报告的推荐执行了零调用探针：把候选证据从 span 计数改写为不同相关组计数，在
MCR 400 例（池内含完整标签的 166 例）上比较 top-1 临床完整数。

保真校验：`gen_order = 93`、`n_spans_desc = 59` 与 `MCR_SELECTION_LAYER_AUDIT` 记录的
"93 例免费（取第一个）"与"按证据数量选 = 59"逐数吻合。

| 排序信号 | top-1 完整 | 转化率 | Δ vs 生成序 |
|---|---|---|---|
| **`gen_order` 生成序（冻结基线）** | **93** | **0.560** | — |
| `n_high_groups_desc` 高特异性组数降序 | 76 | 0.458 | −17 |
| `n_spans_desc` span 数降序 | 59 | 0.355 | −34 |
| **`n_groups_desc` 不同相关组数降序** | **51** | **0.307** | **−42** |
| `n_groups_minus_against_desc` | 50 | 0.301 | −43 |
| `n_groups_asc`（反向） | 24 | 0.145 | −69 |
| `n_spans_asc`（反向） | 10 | 0.060 | −83 |

**核心结果：按相关组去重让信号变差（59 → 51），而不是变好。** 冗余膨胀假设被否证——
上一版报告推测"span 计数被同一观察的复述抬高，去重后符号会翻转"，实测方向相反。
同时反向排序远差于正向（10 与 24 vs 59 与 51），说明证据体量与正确性是**正相关**、
只是远弱于生成序；这与审计 Q2 不矛盾：Q2 的"证据反向"是**在 63 例损失内部**比较正确
候选与被选冠军，不是全局排序断言。

混合策略同样无一超过基线：

| 混合策略 | top-1 完整 |
|---|---|
| 生成序但跳到首个 `n_high_groups ≥ 1` | 92 |
| 生成序但跳到首个 `n_high_groups ≥ 2` | 82 |
| 生成序但跳到首个 `n_high_groups ≥ 3` | 87 |

### 7.1 但集群信号在候选层是真实的

排序层失败的同时，候选层出现干净的单调性：

| 不同高特异性组数 | 候选数 | 占比 | 完整率 |
|---|---|---|---|
| 0 | 1336 | 38.2% | **0.030** |
| 1 | 1496 | 42.7% | 0.054 |
| 2 | 557 | 15.9% | 0.086 |
| 3 | 92 | 2.6% | **0.120** |

从 0 到 3 完整率单调上升 **4 倍**。这在方向上支持论文的主张：**由特异性发现构成的组合
确实携带诊断信号，而且量级正落在 2–3 个的区间。** 起作用的是**特异性**而非**多重性**——
`n_high_groups`(76) 明显优于 `n_groups`(51) 与 `n_spans`(59)。

### 7.2 为什么这不能变成排名收益

生成序（0.560）已经编码了比任何证据派生信号更多的信息。生成器把最有把握的猜测放在
第一位，而这份把握本身就已经吸收了"该候选有几个特异性发现支持"。因此在**冻结 payload
上做任何后验重加权都是在用信息量更少的代理替换信息量更多的原信号**——这与截断
（NO_GO）、证据重派（−6）、换池（−13）三次已执行干预的形态完全一致。

**推论：若集群要产生价值，必须进入生成层——改变哪些候选被提出、以什么置信度提出——
而不是作为对冻结 payload 的后验重排。** 这与 `MCR_SELECTION_LAYER_AUDIT` 的结论
"MCR 的剩余头寸在生成层，不在选择层或证据格式层"收敛到同一处。

---

## 8. 修订后的实施顺序

上一版报告的步骤 0/1/2 已被本轮实测处理完毕，结论是全部**关闭**：

| 原步骤 | 状态 | 依据 |
|---|---|---|
| 0 组去重重排 | **否证** | Q9：59 → 51，方向与假设相反；混合策略无一超过 93 |
| 1 在 multistance/collapse3c 重开 C4 让打包生效 | **否证** | Q8：机制在 12 个 live 臂上真在跑，翻转 36 例中打包 0 完整、关打包 5 完整 |
| 2 拆分探针（`atomize` 后重抽证据） | **降级为低优先** | Q9 表明起作用的是特异性而非多重性；提高组分辨率只会强化已被否证的 `n_groups` 方向 |

剩下的路只有一条，而且它的形态和上一版的判断不同。**完整方案已另立文件**：
[`SYMPTOM_CLUSTER_GENERATION_PLAN.md`](../../SYMPTOM_CLUSTER_GENERATION_PLAN.md)，
其中含新增的立场分解诊断（Q11：coverage 每捞回一例耗 250.8 个候选、非 commit 立场的
边际召回仅 13 例）、G1 召回保全门的冻结队列（dev 67 例 × 2 臂 = 134 调用，零面板）、
以及三个候选干预中一个被直接放弃的理由。下表是其摘要：

| 步骤 | 内容 | 成本 | 前置 |
|---|---|---|---|
| **A** | **生成层集群**：在候选生成 prompt 里要求生成器指出"哪 2–3 个特异性发现的组合支撑该候选"，并据此给出置信度；集群作为**生成时**的推理约束而非事后重排 | 需预注册；量级同 stance 生成（每例数次调用） | Q9 单调性（0.030→0.120）已提供先验 |
| B | 可信本体接地（若 A 需要把集群对齐到本体）：走 RAG-HPO 式检索 + LLM 选择，替换现 3.8% 的字符串匹配 | 见 §9 三档评估 | 与 A 解耦，可独立验证 |

**不要再做冻结 payload 上的后验重排。** 截断（NO_GO）、证据重派（−6）、换池（−13）、
本轮组去重（−42）与打包开关（−5）已构成五次一致的否证：**该 payload 的可提取信号已榨干。**

---

## 9. 合取子失败是否源于实体链接失败

这是一个独立于上述否证的问题，答案是**部分成立，但不足以解释全部**。需要把两件事分开：

1. **`症状集群.md` 的查表路线失败，确实主要是实体链接失败。** §3.1 的 0.11% 与 §3.2 的
   3.8% 都是**方法性**失败而非数据性失败：`SyndromeResolver.resolve` 用精确归一化字符串
   匹配，`HPOIndex.resolve_fuzzy` 用双向子串 + 首个命中。这是 2010 年代前的做法，在叙述性
   span 上必然崩溃。SOTA 方案的评估见下节引用的调研结论。
2. **但 Q9 的否证不依赖实体链接。** 步骤 0 用的是仓库自己的 `correlation_group`
   （LLM 生成、97.9% 可连接），完全绕开了本体链接，仍然是 −42。同理 Q8 用的是冻结的
   `ledger.cells`，也不涉及链接。**所以"后验重排无效"这一结论对实体链接质量不敏感；
   实体链接是 B 类合取子能否被构造的瓶颈，不是重排失败的原因。**

结论：改进实体链接是**做 B 类合取子的必要前提**，但它不会让已被否证的重排路线复活。

### 9.1 SOTA 方案调研（文献）

完整调研见本节附录。要点：

- **直接 prompt 通用 LLM 做端到端链接是灾难性的**：GPT-4 在 COMETA 上 R@1 仅 40.3%，
  DeepSeek-R1 37.6%（转引自 PILOT arXiv:2608.04144 汇总的 LLM4BioEL 数字）；表型任务上
  GPT-4o-mini 直接 prompt 的 mention F1 在 BIOC-GS 上只有 2.66（AutoPCR arXiv:2507.19315）。
- **但"先检索候选、再让 LLM 选"很强**：BioBERT top-20 + GPT-4o 在 1,820 个 OMIM 表型
  术语上从 62% 提到 **85%**（Frontiers Digital Health 2025, `10.3389/fdgth.2025.1495040`）；
  RAG-HPO 在 112 篇病例报告 1,792 条标注上 **F1 0.78**（Genome Medicine 2025,
  `10.1186/s13073-025-01521-w`）；AutoPCR **零本体特定训练**，mention F1 平均排名第一，
  全部实验成本 <$1。
- **最接近本场景的期望锚点**：SNOMED CT Entity Linking Challenge（JAMIA 2025,
  `10.1093/jamia/ocaf104`，MIMIC-IV 出院记录）三名获奖方案 macro-IoU 仅
  **0.4202 / 0.4194 / 0.3777**，中位数 0.2572，且**冠军是纯字典法**。真实叙述性病历 →
  SNOMED 的 SOTA 本来就只有 0.42 量级，不应期待高分。
- **数值型 finding 有确定性正解**：`loinc2hpo`（npj Digital Medicine 2019,
  `10.1038/s41746-019-0110-4`）按 L/N/H 映射到带方向的 HPO（血钾偏高 → Hyperkalemia
  HP:0002153，正常值记为否定的 HP:0011042）。本仓库已有 `loinc2hpo_annotations.json`
  与生产级 `FindingNormalizer`，可拼成零调用零泄漏的确定性层。
- **否定应是独立一层而非链接目标**：`"no pallor, jaundice, or palpable peripheral
  lymphadenopathy"` 应产出 3 个概念 × polarity=absent，而不是链接到一个概念。SOTA 见
  arXiv:2503.17425（i2b2 2010 assertion，LLaMA-3.1-8B + LoRA 准确率 0.962），规则基线
  NegEx / ConText（`medspaCy`）。
- **未找到可核查指标的一档**：MedGemma 技术报告（arXiv:2507.05201）未报告任何实体链接 /
  概念标准化 benchmark；BioMistral、Llama-3-Med、GatorTron 在 BC5CDR / MedMentions / HPO
  类 benchmark 上的 SOTA 数字同样未找到可靠来源。**此处不做估算。**

### 9.2 在本队列上实测：三条"零成本修法"的真实效果

调研提出三条不需训练的修复。在 4641 条 fact 上实测后，**其中两条的预期需要下调**：

| 修法 | 调研预期 | 本队列实测 |
|---|---|---|
| 限制到 `Phenotypic abnormality` (HP:0000118) 子树 | 消灭 `All`/`Left`/`Right` 三类错误 | **对精确匹配是 no-op**：178 条精确命中**全部已在子树内**（子树外 0 条）。它只对子串回退有效——回退命中中 602/3311 = 18.2% 落在子树外，其中 280 条落到根节点 `HP:0000001` |
| 禁用短同义词 | 消灭 `ra` → Rheumatoid arthritis 一类 | **确认，且成本极低**：词表中长度 <4 的条目只有 **53/46,486**，却导致 **2346/3311 = 70.9%** 的回退命中 |
| 删除双向子串回退 | 去掉噪声源 | **确认，且这是三条里唯一真正起作用的**。删掉后覆盖率不下降，因为回退本身 12 抽样仅 1 例正确 |

**关键修正：这三条合起来并不能把 3.8% 抬高，它们只是把虚假的 75.2% 归零。** 由于精确命中
本已全在子树内、且回退整条要删，前两条基本被第三条吸收。**真正提高覆盖率必须上检索 +
LLM 选择层，那是有调用成本的。** 上一节的"零成本修复"措辞应按此理解：它修的是精度，
不是覆盖率。

### 9.3 modality 路由的硬约束

| modality 段 | 条数 | 占比 | 可行路径 |
|---|---|---|---|
| `laboratory` | 754 | 16.2% | **确定性层**：`FindingNormalizer` + `loinc2hpo`，零调用零泄漏 |
| `exam` | 1128 | 24.3% | 生命体征子集走确定性层，其余走 HPO 检索 |
| `history` + `imaging` + `treatment_response` | **2527** | **54.4%** | **必须走 SNOMED**——HPO 本体缺少影像学 finding 与病史事件概念 |

**超过一半的 span 根本不能用 HPO。** 这不是方法问题而是本体覆盖问题，任何以 HPO 为唯一
目标的方案上限都被这 54.4% 封住。

### 9.4 污染风险与可用性三档

泄漏只发生在"用 MedCaseReasoning 的病例做训练或调超参"时；在 i2b2、SympTEMIST、GSC+、
SNOMED Challenge 等外部语料上微调的公开 checkpoint 属于无泄漏。

| 档位 | 方案 | 本场景 |
|---|---|---|
| **零训练可用** | SapBERT / KRISSBERT 现成权重检索；AutoPCR；REAL（BioNLP 2024）；RAG-HPO；简化 retriever；字典法（FastHPOCR / KIRI 式）；NegEx / ConText；`loinc2hpo`；SimConcept 规则（IEEE JBHI 2015）；Borchert 式 LLM 简化（Database 2024, `baae067`） | **✅ 可用**，且能复用已有 `hpo_embeddings.npy` / `snomed_term_index.json` / `loinc2hpo_annotations.json` / `FindingNormalizer` |
| **仅需外部语料训练（无泄漏）** | ANGEL（arXiv:2408.16493）/ GenBioEL 的 UMLS 预训练权重；xMEN cross-encoder（JAMIA Open 2025）；PILOT reranker；BioELX；LLM4BioEL（需 token logits，闭源 API 不可用） | ⚠️ 技术可用但需 GPU 与数周工程量，边际收益不匹配 |
| **需本任务标注（有泄漏风险）** | ANGEL / GenBioEL 的数据集特定 fine-tune；PhenoBERT / PhenoTagger(++) 本体特定重训；SNOBERT 式 NER 微调；MITEL-UNIUD LoRA | **❌ 不可用**。测试集为 MedCaseReasoning（公开病例报告），在其上训练或调超参构成泄漏，预注册制下应排除 |

一条需标为**推测**的风险（未找到直接证据）：MedCaseReasoning 源自公开病例报告，通用 LLM
的预训练语料很可能已包含其源文献，因此"让 LLM 选概念"这一步本身可能受益于记忆。缓解
办法是只让 LLM 做"从检索出的 20 个候选中选一个或弃权"这类**受限判别**，不做开放生成——
受限判别对源文记忆的敏感度远低于自由生成。

### 9.5 若要做 B 类，最小流水线的形态

分五段，总调用量约 **700–1400 次**（落在既有预算量级内）：确定性层（0 调用，laboratory +
生命体征）→ 分解层（~250–400 调用，处理 32.9% 表层复合 span，同时输出 polarity）→
检索层（0 调用，复用 `hpo_embeddings.npy` 取 top-20，HPO 走 HP:0000118 子树，
history/imaging 路由 SNOMED）→ 选择层（~300–800 调用，从 top-20 选 1 或 `no_match`，
**允许弃权是精度关键**）→ 审计层（~100–200 调用抽样复核）。

保守对照臂：字典法强化 + KRISSBERT top-1 + 相似度阈值弃权，**零调用零训练完全可复现**
（依据：SNOMED Challenge 冠军为纯字典法，且 KRISSBERT 在 MIMIC 出院记录上 R@1 90.58%，
见 ClinicalNLP 2026 `2026.clinicalnlp-1.33`）。

期望校准：文献最高的 85%（Frontiers 2025）是在**已规范化的短表型短语**上取得的，而本队列
是长叙述；RAG-HPO 的 F1 0.78 里 **95.2% 的假阳性是目标项的上位祖先**，按精确 ID 判定会
显著更低。**因此"可信 top-1 接地率 45–65%"应记为推测而非文献结论**，且 §9.3 的 54.4%
非 HPO 段是其硬上限来源。

---

## 10. 本次调研未做的事

- 未做任何 LLM 调用，未动 panel
- 未修改 `aphhm_c.py` 或任何生产路径；`enable_matrix` 保持原状
- 未核对 `primekg_index.py` 的底层数据是否实际落地
- 未评估 `cceg_*` 子系统（claim/graph 检索）对依赖边的贡献
- 未在 DA 队列上重复本盘点（本报告数字全部来自 MCR 400 例）
- Q8 的 36 例翻转样本小、且 4 个臂间存在共享阶段，**不构成显著性结论**，只用于否掉
  "翻开关就有收益"的预期
- 未实现任何 SOTA 实体链接方案，只做了方案评估（§9 与附录）
