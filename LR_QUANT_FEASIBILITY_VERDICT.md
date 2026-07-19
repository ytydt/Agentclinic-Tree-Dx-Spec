# 定量 LR 方案的根本可行性判定

> **判定日期**：2026-07-08
> **触发问题**：定量 LR 计算方案在根本上是否可行？必须有开放获取（或注册即得）的数据源支持。外部文档提及的源是否可行（下载实测）？联网调研更广泛的源。如确无可靠 LR 源，则以定性路为主题。
> **方法**：本地缓存实测 + 外部文档源逐一下载探测（GetTheDiagnosis / Cochrane DTA 已下载）+ 联网调研（JAMA RCE / Signs and Evidence / DiagBench / Cochrane API）。
> **前置**：`[LR_EVIDENCE_DATASOURCE_RESEARCH.md](LR_EVIDENCE_DATASOURCE_RESEARCH.md)`、`[EVIDENCE_ANNOTATION_LR_DEFECTS_RESEARCH.md](EVIDENCE_ANNOTATION_LR_DEFECTS_RESEARCH.md)`。
>
> **⚠️ 2026-07-08 二次修订**：新外部文档 `[构建临床诊断kg_20260708_0128.md](构建临床诊断kg_20260708_0128.md)` 引入 **LIRICAL 表型 LR 范式** 与 **分层 LR 语义**，对下面的"定量 LR 根本不可行"初判构成**实质修正**。§0–§6 为初判，**必须连同文件末 §8 一起读**——§8 是当前生效结论。

---

## 0. 一句话结论

**定量 LR 作为「覆盖任意 finding→disease 的主力机制」不可行**——开放世界里真实报告 Sn/Sp 的结构化数据只有 ~1–2k 条、且集中在**命名诊断试验**上，与标注器需要查询的开放症状/体征×疾病空间存在数量级鸿沟。

**可行的是**：把定量 LR 收缩成一个**薄的、高精度锚定层**（≈1–2k 条 GetTheDiagnosis 试验型 LR + 手工 pathognomonic 表），其余全部走**定性方向标签 + provenance 门控 + KB 方向纠偏**。→ **主题应转为定性路，定量 LR 仅作锚点。**

---

## 1. 本地缓存实测：真实 LR 占比 0.29%

`data/knowledge_raw/unified_symptom_disease_cache.json`（`entries` 键下 **377,086** 条）：


| 来源                  | 条数        | 占比        | 性质                   |
| ------------------- | --------- | --------- | -------------------- |
| HPO                 | 215,436   | 57.1%     | 疾病→表型**频率**标签，非诊断 LR |
| Guideline_common    | 139,038   | 36.9%     | 指南共现/频率              |
| Orphadata           | 5,705     | 1.5%      | 罕见病表型**频率桶**         |
| BODHI-S             | 4,630     | 1.2%      | 共现                   |
| Guideline_rare      | 4,622     | 1.2%      | 频率                   |
| HealthKG            | 3,688     | 1.0%      | 患者统计条件概率             |
| docLogica           | 2,855     | 0.8%      | UMLS 桥接              |
| **GetTheDiagnosis** | **1,112** | **0.29%** | **唯一真实报告 Sn+Sp 的源**  |


- **grounded（真实 Sn+Sp）：1,112 条 = 0.29%**。
- **频率桶伪 LR（HPO freq / Orphadata「Frequent/Occasional」/「n/m」）：≈110,833 条 = 29.4%**——这些是**患病率/共现频率**，被硬映射成 LR 桶，不是诊断准确度。
- 其余 ~70% 无任何数值 LR。

> 换言之，即便缓存有 37 万条，能支撑「真实统计学 LR」的只有那 0.29%。这与 `[EVIDENCE_ANNOTATION_LR_DEFECTS_RESEARCH.md](EVIDENCE_ANNOTATION_LR_DEFECTS_RESEARCH.md)` 的伪特异度/频率伪标定结论一致。

---

## 2. 外部/开放 LR 源逐一探测

### 2.1 GetTheDiagnosis.org —— 本项目 `build_unified_cache.py` 的 Source #1（已下载实测）

> **更正**：GetTheDiagnosis 来自本项目自己的 `build_unified_cache.py`（其代码注释 "Source 1"），**不是** `构建临床诊断kg_20260702_2110.md` 提出的源——外部文档全篇未提任何 Sn/Sp/LR 数据源（详见 §2.6）。

- 官网自述**全库仅 315 诊断 / 1,133 finding / 1,733 条**（Copyright 2008–2014）。
- 本地 `lr_cache.json` 已抓取 **1,112 条**（221 疾病 / 857 finding），**100% 带真实 Sn+Sp+LR±**，且已全部并入 unified cache。→ **这个源已经吃干榨净，不存在"还没接入"的增量。**
- 致命局限：
  1. **规模天花板极低**（<2k），且**试验/体检手法为主**（Thompson test、D-dimer、troponin…），不是开放症状空间。
  2. **众包、公众可编辑**，官方免责声明「不保证准确性」——质量方差大。
  3. 我们 9/21 探针词（basophilia、Kayser-Fleischer、Auer rods、necrolytic migratory erythema、Horner…）**命中 0**。它对长尾/病理征象几乎无覆盖。

### 2.2 Cochrane DTA Reference Dataset（已下载实测，Zenodo 1303259，43 MB，CC-BY-NC）

- 内容：**63 个 DTA 系统综述主题**（伤寒 RDT、D-dimer 排 PE、踝肱指数诊 PAD…），1,357 张 forest plot PNG + 一个 `data.xml`。
- 实测：`data.xml` 是 study 级抽取，Sn/Sp **大量埋在 forest-plot 图片和自由文本表格里**，没有干净的 `TP/FP/FN/TN` 键值对；结构化提取需重活。
- 局限：**疾病/问题主题只有 63 个**，比 GetTheDiagnosis 的疾病覆盖还窄；且 **CC-BY-NC（禁商用）**。适合做小规模高质量锚点，不能做广覆盖。

### 2.3 Signs and Evidence（在线，联网调研）

- **64 conditions / 193 signs / 47 tests** 的 LR 计算库——同样是**小规模、体征/试验为主**，且是在线计算器、**无批量下载**。

### 2.4 JAMA Rational Clinical Examination（联网调研）

- **症状/体征 LR 的黄金参考源**，但：~50+ 主题、**版权书/系列文章、无批量结构化数据**、需手工从文章逐条抽取。可作为**人工策展锚点**的权威依据，但不能规模化自动获取。

### 2.5 其它探测到的（均非广覆盖 LR 源）


| 源                                 | 是什么                       | 对定量 LR 的价值                           |
| --------------------------------- | ------------------------- | ------------------------------------ |
| Cochrane 官方 data package（2023.4+） | 每篇 DTA 综述的 2×2 表可下载       | 需 Cochrane Library 权限、DTA 综述仅数百篇、主题窄 |
| DiagBench（HuggingFace）            | 2,257 例**诊断轨迹** benchmark | 是评测集，**不是 LR 源**                     |
| diagcalc / EvalTest               | 从 2×2 表**算** LR 的工具       | 只是计算器，不提供数据                          |


### 2.6 外部文档 `构建临床诊断kg_20260702_2110.md` 提及的数据源（逐条核对，全部本地已有）

**关键事实：外部文档全篇未提任何 Sn/Sp/似然比数据源。** 全文 grep：`GetTheDiagnosis`=0 次；`似然比/敏感度.*特异度`=0 次；`LR+ / LR-` 仅出现 1 次（第 2664 行），且是作为「判断两个方向是否可分」的**定性指标之一**（与 IG、direction-specificity、coverage 并列），**不是**要去查一个 LR 数据库。

外部文档实际推荐的数据源全是**本体 / KG / CPG / 病例**类，我逐条核对——**全部本地已有原始文件，且没有一个提供定量 LR**：


| 外部文档推荐源                                      | 本地文件                                          | 提供什么                              | 有无定量 LR            |
| -------------------------------------------- | --------------------------------------------- | --------------------------------- | ------------------ |
| **HPO** phenotype.hpoa                       | `phenotype.hpoa`(35MB)                        | disease→表型 + **频率桶**(如 `4/4`)     | 无（频率≠LR）           |
| **HPO** 本体                                   | `hp.obo`(11MB)                                | 表型词表                              | 无                  |
| **Orphanet / HOOM / Orphadata**              | `orphadata_product4.xml`(48MB)、`product6.xml` | rare disease→HPO + **频率桶**        | 无（见下）              |
| **Mondo**                                    | `mondo.obo`(51MB)                             | 疾病 ID 归一化                         | 无                  |
| **PrimeKG**                                  | `kg.csv`(982MB)                               | disease–symptom/disease–disease 边 | 无（共现，无 Sn/Sp）      |
| **HealthKG**                                 | `healthkg.csv`                                | 患者统计条件概率                          | 无（P(sym            |
| **UMLS / SNOMED CT**                         | 需许可                                           | 术语归一化                             | 无（本就非 LR 源）        |
| **CPG / DDXPlus / DeepRare / PubCaseFinder** | —                                             | rule-in/rule-out、DDx、表型匹配         | 无（**定性**鉴别，非数值 LR） |


**Orphadata/HOOM 实测**（`orphadata_product4.xml`）：频率字段只有 **6 个离散桶**——
`Very frequent (99-80%)` 25,676 条、`Frequent (79-30%)` 39,588、`Occasional (29-5%)` 42,753、`Very rare (<4-1%)` 6,509、`Obligate (100%)` 625、`Excluded (0%)` 727。
这是 **P(finding│disease) 的患病频率**，**不是** LR——LR 需要同时有 Sn 和 Sp（还要 P(finding│¬disease)）。把这些桶硬映射成 LR，正是当前缓存里 29% 伪 LR 的来源，也是外部文档 §1/§5 自己警告的「共现≠诊断依据」陷阱。

（`phenotype.hpoa`/`orphadata` 里 grep 到的 "sensitivity/specificity" 全是疾病名噪声，如 *Hypersensitivity pneumonitis*、*Growth hormone insensitivity*，**没有一个是诊断准确度字段**。）

> **所以对"外部文档提及的 LR 数据源是否检测"这一问的直接回答：外部文档根本没提任何定量 LR 数据源；它推荐的 8 类源本地全部已有并已接入，全都是本体/频率/共现/定性鉴别，没有一个能产出真实 Sn/Sp/LR。外部方案本身走的就是"定性鉴别边 + KG 约束"路线，与本判定的结论一致。**

---

## 3. 为什么"从文本现算 LR"这条路也不成立

外部文档设想用 RAG 从 StatPearls/教材片段现抽 Sn/Sp（Layer 3a）。实测（`[EVIDENCE_ANNOTATION_LR_DEFECTS_RESEARCH.md](EVIDENCE_ANNOTATION_LR_DEFECTS_RESEARCH.md)` §3 + probe）已证：

- 叙述性文本极少同时报告 Sn **和** Sp → 触发 `_DEFAULT_SP=0.85` **伪造特异度** → 虚假强排除。
- `pct` 通道抓到的百分比常是患病率/死亡率/样本量，误当敏感度。
- 二级 RAG 缓存里带 `explicit:` 真实依据的仅 **~0.13%**；detox 实验一动就 −13.3pp，说明这条路信噪比极差。

> **结论：narrative→LR 的自动量化在根本上不可靠**，不是调参能救的。

---

## 4. 数量级鸿沟（可行性的核心矛盾）


|     | 供给（开放真实 LR）     | 需求（标注器查询空间）                |
| --- | --------------- | -------------------------- |
| 规模  | ~1–2k 条         | 开放 finding × 疾病，10⁴–10⁶ 量级 |
| 内容  | 命名诊断试验 / 部分体检手法 | 任意症状、体征、化验、影像、病理征象         |
| 长尾  | 几乎为 0           | 正是难题所在（罕见病、病理征象）           |


**供需错配是结构性的**：不存在一个开放/注册即得的源能把这个鸿沟填上。这就是"根本上不可行"的证据。

---

## 5. 判定与建议路线：定性为主，定量作锚

### 5.1 定量 LR —— 收缩为「锚定层」（Anchor，不做广覆盖）

- **只信 `explicit:` 依据**（真实报告的 Sn+Sp）进数值 LR 通道 → 就是把 `purify_entry` 设默认（`[LR_EVIDENCE_DATASOURCE_RESEARCH.md](LR_EVIDENCE_DATASOURCE_RESEARCH.md)` §5.2 P0）。
- 数值锚 = **GetTheDiagnosis 1,112 条 + 手工 pathognomonic 表**；命中即给 posterior floor / 强锚点，命中率低但精度高、无副作用。
- **频率桶（HPO/Orphadata）一律降级为 context-only 先验**，退出 finding→LR 数值通道。

### 5.2 定性路 —— 升为主题（覆盖其余 ~99.7%）

1. **七档方向标签**（`strong_for`…`strong_against`）作为主力，由 LLM 判定、KB 方向纠偏（`_reconcile_annotation_with_kb`）。
2. **CPG / Case report 抽「带方向的鉴别边」**（`discriminates_for/against`、`red_flag_for`、`diagnostic_criterion`）注入 prompt 做**方向锚定**，而非量化 LR（`[LR_EVIDENCE_DATASOURCE_RESEARCH.md](LR_EVIDENCE_DATASOURCE_RESEARCH.md)` §4.3/§5.1）。
3. **判别门控**（`enable_discrimination_gate`，已实现）冻结全弱轮，防定性证据被 renormalization 稀释掉正确家族。
4. **salience filtering** 把慢性基线异常降权为 background。

### 5.3 一句话路线

> **定量 LR 从「主力查询机制」降级为「≈1–2k 条高精度锚点」；证据标注主体转向"定性方向标签 + provenance 门控 + KB/CPG 方向纠偏"。** 这既符合开放数据的客观供给上限，也与 MedKGI / Dual-Inf / NICE-RAG grounding「用 KG 约束方向、不让 LLM 自由生成 LR」的共识一致。

---

## 6. 落到工程的最小动作（承接现有 P0/P1）


| 优先级    | 动作                                                                       | 依据      |
| ------ | ------------------------------------------------------------------------ | ------- |
| **P0** | `purify_entry` 默认开：非 `explicit:` 不进数值 LR 通道                              | §5.1    |
| **P0** | 频率桶（HPO/Orphadata pseudo-LR）降级为 context-only 先验                          | §1、§5.1 |
| **P1** | CPG/case-report 抽方向边 → prompt 定性锚点（不喂 `quantify_snippet`）                | §5.2    |
| **P1** | 常见综合征 discriminative marker 手工补库（探针 MISS：LAP→leukemoid、ESR→thyroiditis…） | probe   |
| **P2** | 关掉/严格门控 RAG narrative→LR（信噪比差）                                           | §3      |


> 定量锚点层不需要新数据采购——现有 1,112 条 GetTheDiagnosis 已足够；重点是**把它和伪 LR 隔离开**，别让 29% 的频率桶污染判决。

---

## 8. 二次修订（当前生效结论）：新外部文档带来的挑战与补充

> 依据：`[构建临床诊断kg_20260708_0128.md](构建临床诊断kg_20260708_0128.md)`（尤其 line 590 起的「症状→疾病 LR」章、line 1272 起的「成品 LR 工具」章、line 1627 起的「上下层级 LR」章）。以下均已**本地实测**。

### 8.1 修订后的一句话结论

**定量 LR 分裂为两个子空间，可行性不同，不能一刀切：**

1. **表型/HPO 编码的罕见病空间 —— 定量 LR 可行，且数据本地已齐。** 用 **LIRICAL 范式**（`LR(h|D)=P(h|D)/背景频率`）从我们已有的 `phenotype.hpoa` 现算，可得 **264,245 条**可计算的表型-LR 边（80.1% 带显式频率）。这是一条被 §0 初判**误杀**的真定量路径。
2. **常见 ED 综合征的 Sn/Sp 空间 —— 仍不可行**（§0–§6 成立）：真实 Sn/Sp 只有 ~1–2k 条、命名试验为主，缺口是结构性的。

**因此当前生效路线 = 三层：LIRICAL 表型 LR（罕见病/长尾）＋ GetTheDiagnosis+pathognomonic 数值锚（常见试验）＋ 定性方向标签（其余）。** 定性仍是覆盖面最大的层，但"定量根本不可行"这句话被推翻——它只对"常见综合征广覆盖"成立。

### 8.2 对 §0 判断的直接挑战：HPO 频率不是伪 LR，是**用错了方法**

- §1/§3 把 HPO/Orphadata 频率归为"43% 伪 LR"。**根因定位修正**：缺陷在 `build_unified_cache.py` 的 `build_entry(sensitivity=freq, ...)` —— 它把频率当 Sn、再补默认 `Sp=0.85` 去算 LR，分母是伪造的。
- LIRICAL 的正确用法：频率是 `P(h|D)`（分子），分母是该表型在**全库疾病**的背景频率 `P(h|¬D)≈P(h)`。同一批数据，方法对了就是合法 LR。
- **本地实测证据**（`phenotype.hpoa` 2026-02 版，12,974 疾病 / 11,514 HPO 词）：
  - Kayser-Fleischer 环 → Wilson 病 **LR≈3434**；铜代谢异常 → Wilson **LR≈6487**
  - café-au-lait 斑 → NF1 **LR≈1011**；腋窝雀斑 → NF1 **LR≈861**
- LIRICAL 原文：384 例罕见病 top-3 命中 **92.9%**、正确诊断平均后验 67.3%（AJHG 2020）。**方法学已验证**。

### 8.3 成品 LR 工具实测


| 工具/源                      | 本地状态                                                        | 是否真定量 LR         | 可行性判断                         |
| ------------------------- | ----------------------------------------------------------- | ---------------- | ----------------------------- |
| **LIRICAL / CAVaLRi**     | 依赖数据（`phenotype.hpoa`+`hp.obo`）已在本地；引擎 Java CLI，输出 JSON/TSV | **是**（表型 LR，`P(h | D)/P(h                        |
| **DDXPlus 经验 LR**         | `ddxplus_test.csv`（134,530 例）本地已有                           | 经验 LR，非文献真值      | 本地采样现算可得判别证据，但有"完美分隔"合成伪影（P(f |
| GetTheDiagnosis           | 本地 1,112 条                                                  | 是（真 Sn/Sp）       | 常见试验数值锚（§2.1，已吃尽）             |
| Cochrane DTA              | 已下载 43MB                                                    | 是但埋在图片           | 63 主题，太窄（§2.2）                |
| JAMA RCE / Signs&Evidence | 不可批量                                                        | 是                | 非开放（§2.3/2.4）                 |


### 8.4 最大概念补充：分层 LR 语义（三份文档此前均缺）

新文档 line 1627–2365 整章论证 —— 这不是数据问题，是**建模问题**，且直接命中我们已定位的 **MAP_FAIL 叶子鉴别瓶颈**（正确家族选对、但家族内选错具体病）：

1. **LR 绑定 `(target hypothesis, comparator set)`，不是疾病节点的固有属性。** 现缓存的 `finding::disease` 隐含"vs 全体其他病"的比较集、且无人群/场景 → 语义欠定。
2. **三类 LR 必须分开存**：类别级（路由）、叶子级（具体病 vs 非此病）、**同胞级**（`P(f|D_i)/P(f|C\D_i)`，类别内鉴别）。**同胞级正是叶子鉴别缺的那块。**
3. **父类 LR 不能继承/平均给子病**（发热→感染 LR=5，不等于发热→肺炎 LR=5）。
4. **避免重复计数**：父+子、祖裔 finding（腹痛/右下腹痛/McBurney）不能连乘。
5. **优先存 Sn/Sp/2×2 与类别内先验，而非只存 LR**（LR 是派生量，跨层聚合需要原始 likelihood）。
6. **两阶段推理**：大类路由 → 类别内同胞鉴别。与本项目 L1(MECE 分支)→L2 树结构天然对齐。

### 8.5 修订后的工程动作（覆盖/补充 §6）


| 优先级       | 动作                                                                            | 相对 §6 的变化               |
| --------- | ----------------------------------------------------------------------------- | ----------------------- |
| **P0（改）** | 频率桶**不要**一律降级为 context-only；改为**按 LIRICAL 范式重算为表型 LR**（`freq/背景频率`），进数值通道     | ⟵ 推翻 §5.1/§6 的"频率桶降级"结论 |
| **P0**    | 修 `build_unified_cache.build_entry`：频率源不再填 `sensitivity=freq + 默认 Sp`，改存 `P(h | D)` 并单独计算背景频率           |
| **P1**    | 罕见病/长尾分支集成 LIRICAL（或复刻其表型 LR 计算，数据本地已全）                                       | 新增                      |
| **P1**    | 证据边补 `comparator_set` / `context` 字段；LR 分类别级/叶子级/同胞级三型                        | 新增（§8.4）                |
| **P1**    | 为叶子鉴别补**同胞级 LR**（MAP_FAIL 直接对症）                                               | 新增，对症瓶颈                 |
| **P2**    | GetTheDiagnosis 数值锚保留；narrative→LR RAG 仍严格门控                                  | 沿用 §6                   |
| **P2**    | DDXPlus 仅作 benchmark，标注 synthetic，不进真值库                                       | 沿用                      |


### 8.6 与初判的关系

- §0–§6 **在"常见综合征广覆盖 Sn/Sp"范围内仍然成立**。
- 但"定量 LR 根本不可行、应整体转定性"这一**总判被 §8 收窄**：罕见病/表型空间有一条本地即可落地的定量 LR 路径（LIRICAL），且我们此前是因为**算法用错**（频率当 Sn+伪 Sp）才把它当成噪声丢弃的。
- 净效果：**定性仍是最大覆盖层，但定量不再"只有 1–2k 锚点"——罕见病侧多出 ~26 万条本地可算的表型 LR 边；同时暴露出比数据更关键的"分层 LR 语义"建模欠账。**

---

## 9. 三层落地前的隔离测试（LR 覆盖/质量，2026-07-08）

> 目标（用户要求）：在真正把三层结论写进生产前，先**隔离测试**——排除"证据选错/分支选错"的干扰（人工喂正确候选分支与关键鉴别证据），只问：三层栈能给多大比例的关键鉴别 finding 一个**可用的定量 LR**，以及来自哪一层。

- 脚本：`[scripts/eval_lr_coverage_isolated.py](scripts/eval_lr_coverage_isolated.py)`
- 人工数据：`[data/eval/lr_coverage_cases.json](data/eval/lr_coverage_cases.json)`（9 个 MedBullets 核心案例的叶层候选=正确+关键干扰，L1 家族沿用 `logs/branchgen_rh.json`；外加 3 个 RareArena 真长尾罕见病样例）
- 三层定义：**A** = 自包含 LIRICAL 表型 LR（本地 `phenotype.hpoa`+`hp.obo`，`LR=P(h|D)/P(h|¬D)`）；**B** = 生产锚点检索器 `get_lr_reference(fast)`（pathognomonic marker + `manual_highly_specific §22.3` + GetTheDiagnosis 真 Sn/Sp，**频率派生的伪 LR 不算 grounded**）；**C** = 定性方向标签（永远兜底，故不计入"定量覆盖"）。
- 两臂：`auto`（机器解析 finding→HPO、disease→OMIM）vs `hinted`（用人工 HPO/OMIM 提示）——两者相等即说明**映射不是瓶颈**，测的是数据覆盖本身。

### 9.1 结果


| 语料                      | n(关键 finding) | A LIRICAL  | B 锚点 grounded | **定量覆盖 A∪B**    | 仅定性兜底       |
| ----------------------- | ------------- | ---------- | ------------- | --------------- | ----------- |
| MedBullets（常见 ED/内科 dx） | 28            | 6/28 (21%) | 3/28 (10%)    | **8/28 (28%)**  | 20/28 (72%) |
| RareArena（罕见 Mendelian） | 11            | 9/11 (81%) | 1/11 (9%)     | **10/11 (90%)** | 1/11        |


`auto == hinted`（两语料全相等）→ **映射不是瓶颈**；缺口来自数据本身。

### 9.2 三层结论被数据证实

1. **LIRICAL（A 层）扛起长尾**：RareArena 81%（auto），并入 B 后 90%。这正是把频率桶按 LIRICAL 范式重算的收益兑现。
2. **常见 dx 定量天花板低**：即便三层齐上，MedBullets 定量覆盖仅 28%，**72% 必须落到定性 C 层**——与 §0–§6 初判一致。⇒ **三层分工是对的：定性仍是最大覆盖层，定量按语料分层补强。**
3. **伪 LR 缺陷现形（§8 根因的实证）**：MedBullets 上 B.any-numeric=8 但 grounded 仅 3（5 个是频率伪 LR）；RareArena 上 11/11 的缓存"数值"里 10 个是伪 LR。典型对比：**Kayser-Fleischer→Wilson，现缓存伪 LR 仅 11（Sn=0.53+伪 Sp=0.95），LIRICAL 重算 4679**——现路径把近病理征严重低估 ~400 倍。这就是 §8.5 P0"频率源改存 `P(h|D)` 并单独算背景频率"要修的东西。

### 9.3 隔离测试额外暴露的 LIRICAL 层缺陷（落地前需处理）

- **HPO 祖先传播缺失**：`cafe-au-lait spots`(HP:0000957) → NF1 返回 None，因为 NF1 疾病条目实际标注的是子术语 `Multiple cafe-au-lait spots`(HP:0007565)。LIRICAL 层需在查询时**向下/向上沿 `is_a` 传播**（把祖先 finding 匹配到疾病标注的具体子术语），否则叶子术语错配会假性丢覆盖。
- **常见/反应性诊断天然缺席 hpoa**：leukemoid reaction、adhesions、nasal foreign body、CML、peliosis hepatis 均不在 `phenotype.hpoa`（非 Mendelian）→ A 层必然 miss，只能靠 B（DTA 锚点）或 C。**这划清了 A 层的适用边界。**
- **常见判别性实验室值缺锚**：LAP、低磷、高钙(常见甲旁亢)、ALP 升高等在 A/B 均 miss——这些恰是 MedBullets 的决定性鉴别点，指向"补 GetTheDiagnosis/DTA 锚点 + 定性方向"的 P1/P2 工作。

### 9.4 落地判定

隔离测试**支持三层落地**，但落地顺序应为：先修 A 层根因与祖先传播（§8.5 P0 + 9.3），因为其收益最大且已被量化（长尾 81–90%、伪 LR 纠偏 ~400×）；常见 dx 侧以 B 锚点 + C 定性为主，不追求定量覆盖率。

### 9.5 落地候选依序执行 + 重测（隔离层，未进生产端，2026-07-08）

按 §9.4，两项候选在隔离测试脚本内依序实现并重测（生产 `EvidenceAnnotator` 未改）：

**候选 1 — HPO `is_a` 传播**（子代匹配 + subsumption 背景频率）

- `LiricalPhenotypeLR`：查询项 Q 若被疾病标注的**更具体子术语**满足即算命中（`P(h|D)` 取子代最大频率）；背景频率改用"标注 Q 或其任一子代的疾病占比"。
- 直接修好 `café-au-lait spots`(HP:0000957)→NF1：原返回 None（NF1 实际标 `Multiple cafe-au-lait spots` HP:0007565），现 LR=72。

**候选 2 — 比较集（同胞级）LR**（§8.4 核心建模洞见）

- `sibling_lr()`：`LR_sib = P(h|gold) / mean_i P(h|distractor_i)`，比较集用人工数据里的**关键干扰分支**（不是"vs 全体 13k 病"）。这正是 MAP_FAIL 叶子鉴别所缺的量。

**重测结果（对比 §9.1）**


| 语料         | A auto | A(祖先传播后)             | 同胞级可算 | 同胞级判别(≥2×) | 定量覆盖 A∪B        |
| ---------- | ------ | -------------------- | ----- | ---------- | --------------- |
| MedBullets | 21%    | 21%（非 Mendelian 无变化） | 21%   | 17%        | 28%（不变）         |
| RareArena  | 81%    | **90%**              | 90%   | **72%**    | **100%**（+10pp） |


同胞级 LR 的判别输出**临床上自洽**，且诚实地把共享征标为 `~tie`：

- `Lisch nodules→NF1` sibLR=900、`situs inversus→PCD` sibLR=170、`thromboembolism→homocystinuria` sibLR=500 → 强判别（正确）。
- `bronchiectasis→PCD` sibLR=0.3、`café-au-lait→NF1` sibLR=1.8、`ectopia lentis→homocystinuria` sibLR=1.7 → `**~tie`（不判别）**：这三个恰是与干扰分支（CF / Legius / Marfan）共享的征象，单看不足以鉴别——与临床一致（ectopia lentis 需方向"上/下"、café-au-lait 需计数/伴随征）。这说明同胞级 LR 能**如实暴露**"看似特异、实则跨同胞共享"的伪判别点，正对 MAP_FAIL。

**净结论**：候选 1 使长尾定量覆盖补满到 100%（隔离样本）；候选 2 为叶子鉴别提供了可算且自洽的判别信号（RareArena 72% 关键征可判别）。常见 dx 侧仍如 §9.4——A/同胞级天然不适用（非 Mendelian），靠 B 锚点 + C 定性。二者均已重测通过，**待批准后再接入生产 `EvidenceAnnotator*`*。

---

## 10. Backbone LLM 无知识约束的定性判别力 + 协作策略（2026-07-08）

> 用户要求：进一步验证，并单独测出 llama 自身（**无任何 LR/marker/KB 注入**）的定性判别准确率，用以设计协作策略。

- 脚本：`[scripts/eval_llm_qualitative_discrimination.py](scripts/eval_llm_qualitative_discrimination.py)`
- 同一批隔离数据（finding × 人工候选集），temp=0，问 LLM「该 finding 最支持哪个候选（或 -1 不判别）」，再与 §9 的 LR 裁决交叉列表。

### 10.1 LLM 单独判别准确率（挑对正确诊断）


| 语料             | n   | LLM correct     | abstain(-1) |
| -------------- | --- | --------------- | ----------- |
| MedBullets（常见） | 28  | **18/28 (64%)** | 1           |
| RareArena（罕见）  | 11  | **10/11 (90%)** | 0           |


### 10.2 协作地图（LLM 正确率 × LR 层裁决，核心发现）


| LR 桶        | n   | LLM correct      | 含义                                                                                                                 |
| ----------- | --- | ---------------- | ------------------------------------------------------------------------------------------------------------------ |
| **LR→gold** | 16  | **16/16 (100%)** | LR 能判别处，LLM 也全对 → LR 对"选择"是**冗余**（但仍提供可审计权重/后验幅度）                                                                  |
| **LR~tie**  | 3   | **1/3 (33%)**    | LR 判"共享/不判别"处，LLM **自信地选错同胞**（`bronchiectasis→CF` high、`ectopia lentis→Marfan` high）→ LR 在此**最有价值：当护栏否决 LLM 的伪判别** |
| **LR_none** | 20  | **11/20 (55%)**  | 定量不可能区（常见 dx），LLM 独木难支、仅略高于抛硬币 → 需 B 层 DTA 锚点 + 检索接地的定性推理                                                          |


### 10.3 三条协作策略（按 LR 桶路由）

1. **LR→gold 区（罕见/表型，两者一致）**：LLM 主导选择，LR 作**确认 + 校准后验幅度**（把定性方向变成可审计的数值权重）。边际收益在"幅度/可审计"，不在"改判"。
2. **LR~tie 区（同胞共享征）**：**LR/同胞级当护栏**。LLM 的失败模式是**过度自信的伪判别**（错的 2 个都标 high 置信）→ 注入 `~tie` 信号**冻结该 finding 的判别权重**、逼模型去找真正的鉴别点（如 ectopia lentis 的"上/下"方向、café-au-lait 计数）。这是 LR 层边际收益最高的区。
3. **LR_none 区（常见 dx，占 MedBullets 关键征多数）**：两层都无定量，LLM 独测仅 55%。典型错判：`hyperglycemia→T2DM`(漏 glucagonoma)、CML 系列→AML/CLL、`RUQ 痛/低血压→胆总管结石/胰腺炎`、`单侧血性鼻涕→鼻出血`。⇒ **纯自由回忆 LLM 在此不安全**，须靠：(a) 扩 GetTheDiagnosis/DTA 数值锚（B 层），(b) 用检索到的 case-report/CPG 片段**接地**定性推理（而非放任模型凭记忆）。

### 10.4 对总体判定的补充

- **LLM 的强项与 LR 的强项高度重叠**（LR→gold 区 100%）：所以 LR 的作用**不是替 LLM 做选择，而是**：① 罕见病侧给可审计的定量后验幅度；② **同胞共享征上当护栏，纠正 LLM 的过度自信**；这恰好对症 MAP_FAIL。
- **最危险的是 LR_none × LLM 错判**（常见 dx 的 confusable 叶子），这既非 LIRICAL 也非同胞级能覆盖 → 明确 B 层 DTA 锚点扩充与"检索接地定性"是下一优先级，而非继续堆表型 LR。
- 局限：temp=0 单次、样本 39 关键征、单一 backbone（llama-3.3-70b）。趋势清晰但绝对数需扩样本/多 backbone 复核。

### 10.5 稳定性 + 跨 backbone 复核（2026-07-08）

在同一隔离数据上再跑两组验证：


| 运行                          | MedBullets | RareArena | LR→gold          | **LR~tie**    | LR_none          |
| --------------------------- | ---------- | --------- | ---------------- | ------------- | ---------------- |
| llama temp0 单次（§10.1 基线）    | 64%        | 90%       | 16/16 (100%)     | **1/3 (33%)** | 11/20 (55%)      |
| llama reps3 temp0.4（稳定性）    | 57%        | 90%       | 15/16 (93%)      | **1/3 (33%)** | 10/20 (50%)      |
| qwen3-32b temp0（跨 backbone） | 53%(+7弃权)  | 90%       | 14/16 (87%,+2弃权) | **1/3 (33%)** | 10/20 (50%,+5弃权) |


**协作地图结构三次运行完全不变**（验证稳健）：

1. **LR~tie 桶 = 33%，三次全等**——护栏结论**铁证**。两个稳定错判 `bronchiectasis→CF`、`ectopia lentis→Marfan` 在所有 backbone 上都错；仅 `café-au-lait→NF1` 对（本可辩护）。⇒ **同胞共享征上 LLM 系统性失败，与 backbone 无关**，正是同胞级 LR 当护栏的价值点。
2. **LR_none 桶 ≈ 50%，三次全近**——常见 dx confusable 叶子是稳定的危险区，换 backbone 不改善。
3. **LR→gold 桶高位**——两者皆强、且一致。
4. **稳定性**：llama reps3 平均一致度 0.99（仅 1 项不稳），RareArena 1.00 → 单次 temp0 结论可信。
5. **backbone 气质差异（但不改结构）**：qwen3 弃权率高得多（MedBullets 7 vs 1–2）。在 ~tie/none 区**弃权其实是更正确的行为**（承认不判别，如 qwen3 对 ectopia lentis 弃权）；但它在 LR→gold 区也弃权丢 2 分。⇒ **协作策略应含"校准/弃权"维度**：鼓励 LLM 在低判别信号时弃权，再由 LR 层或检索接地补足，而非强行选择。

---

## 11. 改进的独立判别集：饿死型错误 + 深度分层（2026-07-08）

> 用户批评（成立）：§9 的覆盖集只标了 gold 方向的 ~24 条证据，从未测：(a) 干扰分支被误标高 LR → 正确分支在归一化中**饿死**；(b) 混杂证据把正确分支误 rule-out；(c) 该排除的干扰分支没排除；且无树深度分层。为此构造**独立**新集。

- 数据：`[data/eval/lr_discrimination_matrix.json](data/eval/lr_discrimination_matrix.json)`（独立于覆盖集）——9 案例、**46 条证据、131 个 (证据×分支) 期望效应格**（远超 24），每格标 `pathognomonic..rule_out` 8 级效应、深度（L1 家族路由 / leaf 叶层）、陷阱类型。
- 脚本：`[scripts/eval_lr_discrimination_matrix.py](scripts/eval_lr_discrimination_matrix.py)`。对比两引擎：`prod_today`（现生产 `get_lr_reference` 原样）与 `stack`（三层落地候选 = grounded-B ∪ LIRICAL-A）。四种饿死型错误分类计数。

### 11.1 总体结果（131 格）


| 引擎         | 饿死错误         | FALSE_HIGH_distractor | FALSE_RULEOUT_gold | MISSED_RULEOUT_distractor | MISSED_SUPPORT_gold |
| ---------- | ------------ | --------------------- | ------------------ | ------------------------- | ------------------- |
| prod_today | **37 (28%)** | 1                     | 1                  | 21                        | 14                  |
| stack（候选后） | **37 (28%)** | 1                     | 0                  | 21                        | 15                  |


**关键：三层落地候选几乎不动常见 dx 的饿死错误（37→37）**——它们补的是长尾**覆盖**（§9），而饿死错误主要是 **rule-out 缺失 + 否定词处理**，不在覆盖范畴。stack 仅靠"不使用错配的伪条目"消掉 1 个 FALSE_RULEOUT_gold。

### 11.2 深度分层（直接命中用户关切）


| 深度            | n   | prod 饿死      | stack 饿死     |
| ------------- | --- | ------------ | ------------ |
| L1 家族路由       | 57  | 2 (3%)       | 2 (3%)       |
| **leaf 叶层鉴别** | 74  | **35 (47%)** | **35 (47%)** |


**饿死错误 95% 集中在叶层**——正是 MAP_FAIL 所在。家族路由基本没问题，问题全在"家族内选具体病"。

### 11.3 两个被证实的"主动饿死"bug（否定词盲区）

1. **FALSE_HIGH 干扰分支**：`normal serum lipase → acute pancreatitis` 返回 **LR+=100**（GetTheDiagnosis）。实测 `normal / elevated / 裸 serum lipase` 三者**都**给 100——**检索器丢弃了 `normal/elevated` 限定词**，把"脂肪酶正常"（本应 rule-out 胰腺炎）当成强 rule-IN。⇒ 干扰分支 pancreatitis 被抬到 LR100 → peliosis 饿死。**正是用户设想的场景 (a)。**
2. **FALSE_RULEOUT 正确分支 + MISSED_RULEOUT 干扰分支（一条证据双错）**：`normal sweat chloride` → PCD 返回 **LR+=0**（HPO 伪频率，PCD 无此表型→freq0→LR0，误杀正确分支）；→ CF 返回 **LR+=2**（本应 rule-out CF，却给了正向 LR）。否定词盲区 + 伪频率叠加，**同时**误杀 gold 和放过 distractor。**正是场景 (b)+(c)。**

### 11.4 陷阱类型分析（stack）


| 陷阱                           | n   | 饿死率     | 解读                          |
| ---------------------------- | --- | ------- | --------------------------- |
| shared_high（共享高危征）           | 37  | **2%**  | 机器在共享征上基本保持中性、**不乱抬**——好    |
| confounder_correct（诱导误排正确分支） | 15  | **0%**  | 正确分支未被混杂证据误杀——好（否定词 bug 除外） |
| ruleout_distractor（应排除干扰）    | 35  | **54%** | 几乎无 rule-out 能力             |
| discriminator（干净判别点）         | 24  | **50%** | 半数判别点无数值支撑（MISSED_SUPPORT）  |
| pathognomonic                | 10  | 30%     | 部分近病理征仍 miss                |


### 11.5 工程含义（新增，优先于继续堆表型 LR）

- **P0（新，最高优先）— 否定/数值方向感知**：`get_lr_reference` 必须区分 `normal/elevated/absent` 限定词与裸术语（lipase-100 bug、sweat-chloride bug 都是它）。这是**当前正在制造饿死**的活体 bug，且与 backbone/覆盖无关。
- **P1（新）— 显式 rule-out/不相容通道**：21/35 应 rule-out 的干扰分支没被排除。频率型 LR **结构上无法表达**"某在场证据与某病不相容"（LAP 高↔CML、无原始细胞↔急性白血病、hCG 阴↔异位妊娠、situs inversus↔CF）。需要一个独立的不相容/rule-out 边类型，而非靠 LR<1。
- **优先级重排**：叶层（47% 饿死）> 家族路由（3%）。三层覆盖候选（§9）对**长尾覆盖**有效、对**常见 dx 饿死无效** → 下一步应是否定处理 + rule-out 通道，而非继续扩表型 LR。
- 好消息：shared_high(2%)/confounder(0%) 说明机器**不会主动乱抬共享征、也基本不误杀正确分支**（除否定 bug），饿死主要来自"该动的没动"（缺 rule-out/缺 support），修复方向明确。

---

*本文档由会话 `d6e23c24-82b3-4786-a36b-03356b21f410` 整理，2026-07-08；§8 为二次修订，§9 为三层落地前隔离测试，§10 为 LLM 定性判别+协作，§11 为饿死型独立判别集。下载物：`/tmp/dta_x/CL145_open_set_20181101/`（Cochrane DTA，可清理）。*