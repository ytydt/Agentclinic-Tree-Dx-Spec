# 顽固漏检根因诊断 + MECE 重构论证

> 范围:分支创建第一阶段(L1 家族召回)。针对策展评测集 **14 常见 + 8 罕见/难**
> 上"引入 case_report/CPG 语料几乎无增益"的现象,定位残余漏检的真实根因,
> 并论证"用自动 MECE 分支生成保证 L1 不漏检"这一重构方向。
>
> 所有数字来自可复现脚本:
> - `scripts/eval_salient_case_report_ab.py`(14/8,arms: llm/cpg_dual/cr_dual/union/union_all)
> - `scripts/eval_llm_ddx_rarearena.py`(RareArena 真长尾 n=80,留一 + 金标 token 剥离)

---

## 0. 一句话结论

**8/14 上"语料无增益"不是纯 RAG 到顶,而是残余漏检基本都是流水线缺陷
(实体抽取 / 实体排序 / 评估匹配)与个别语料构成缺口,不是"检索够不着"。**
因此:
- 靠**扩数据源**最多救回 ~1 例(leukemoid),收益最低;
- **实体侧修复**(SNOMED 头词/同义扩展 + 去泛化偏置排序)命中大多数排序型漏检;
- **L1 不漏检的正解是结构性的**:让 LLM 生成 **MECE 且穷尽**的一级分区,金标永远有可达分支,与"是否预先召回到那个具体叶子"解耦;语料价值转移到 **L2/L3 长尾叶子富集**(真长尾上 case-report 46% > LLM 30%,这才是可辩护的创新点)。

---

## 1. 逐例根因(顽固漏检)

per-case best-rank(None=该臂未命中),LLM=`meta-llama/llama-3.3-70b-instruct`:

| 例 | 综合征帧 | 金标(接受任一) | llm | cpg | cr | 根因归类 |
|---|---|---|---|---|---|---|
| **lower_gi_bleeding** | lower GI bleeding | angiodysplasia / angioectasia | 2 | None | None | **实体抽取缺口 + 实体排序埋没** |
| **c9_leukemoid** | leukocytosis | leukemoid / reactive | 6 | None | None | **语料构成缺口**(库内几乎无该条目) |
| **c1_pancoast** | focal limb neuro deficit | pancoast / superior sulcus / compressive | 1 | None | None | **词面 chunk 可达性 + 语料稀薄**(pancoast 仅 1 chunk) |
| **c23_adhesions** | bowel obstruction | adhesion(s) | None* | None | None | **评估匹配假阴**(词形变体) |

\* c23 的 LLM 输出里实际含 `Abdominal adhesions` / `Adhesional bowel obstruction`,
只是 `adhesional ≠ adhesion` 使子集 token 匹配假阴(见 §4-B)。

其余 common 例的 cr=None(pleural_effusion / cushing / macrocytic)是
**case-report 语料对常见病天然稀疏**,预期内、非缺陷。

---

## 2. 冒烟证据:angiodysplasia 的完整链路(排序型漏检的样板)

把 `angiodysplasia` 加入 vocab 后逐段追踪同一 query "lower gastrointestinal bleeding":

| 阶段 | 结果 | 判定 |
|---|---|---|
| **chunk 检索** | 含 angiodysplasia 的 DDx 片段排 **rank 7**(综合征查询) | ✓ 正常 |
| **实体抽取** | 入 vocab 后 spotter 从该片段抽出 `{angiodysplasia, colorectal cancer, diverticular disease, aortoenteric fistula, ...}` | ✓ 正常(前提:在 vocab) |
| **实体排序** | 进召回字典但**排第 49**(score 0.0119),被 `hypotension`/`erosive esophagitis` 等高频泛化词淹没 → top-40 截断 | ✗ 埋没 |

**结论:chunk 排序没问题;卡在(a)实体不在 vocab → 抽不出;(b)抽出后被频次求和的泛化共现词埋没。**
这正好把"排序根因"切成**实体识别缺口**与**实体聚合排序缺陷**两块,并排除"chunk 排序问题"和"纯 RAG 检索到顶"。

---

## 3. spotter 词表:是 SNOMED 派生,不是手写(可扩展性 OK)

`build_disorder_vocab`(`knowledge/guideline_branch_source.py`)的实际来源:

- 输入 `snomed_concepts.json`:**137,342 概念**(disorder 94,702 / finding 37,471 / morphologic 5,169)。
- 取每个 `tag=="disorder"` 概念的 `preferred` + `synonyms`,小写、长度门限 `min_len=5`,去掉 `_GENERIC` 泛化词。
- 即 **spotter 词表 = SNOMED disorder 术语表**,非人工编写 → 可随 KG 扩展,合用性良好。

**但存在粒度错配缺口(可修、且仍是 SNOMED 派生):**

| 金标裸词 | SNOMED 是否有 | vocab 里实际是什么 | 裸词能否被 spot |
|---|---|---|---|
| angiodysplasia | 有(`Angiodysplasia of intestine` 等 5 条) | 复合名 `angiodysplasia of intestine` | ✗(裸 `angiodysplasia` 匹配不上复合 n-gram) |
| pancoast | 有(`Pancoast tumor` / `Pancoast's syndrome`) | `pancoast tumor` / `superior sulcus tumor` | ✓(但语料仅 1 chunk) |
| leukemoid | 有(`Leukemoid reaction` 56478004 等 5 条) | `leukemoid reaction`(复合,✓) | ✓(但语料几乎无 chunk) |
| peliosis | 有(`Peliosis hepatis` 等) | `peliosis hepatis` | 部分 |

**修法(不引入手写答案):** 从 SNOMED disorder 名派生**头词/短同义**别名(如
`Angiodysplasia of intestine → angiodysplasia`),补进 spotter 词表。这是词表工程,
沿用 KG 来源、可自动化,不是策展答案。

---

## 4. 对四条假设的裁定 + 用户两点质疑的证实

### A. 扩数据源 / 修预处理(已定位为预处理 bug,已修复)
- `c9_leukemoid`:SNOMED 有该病、Merck 手册也有类白血病反应,**但旧 CPG 索引 203,830 chunk 中仅 1 条含 "leukemoid"**(还是播散性结核综述的评估段)。
- **根因不是"没下载",是预处理分类 bug**(用户判断属实):Merck 里"类白反应 vs CML"的
  鉴别内容位于 `Chapter 117. Leukemias > … > Diagnosis` 子段。`merck_manual_common.py`
  的 `classify_chunk_type` 中,`sub in DDX_SUBSECTIONS` 分支把 `diagnosis` 归为
  `"other"`(其后 `if sub == "diagnosis": return "evaluation"` 是**永不可达的死代码**,
  被前一分支遮蔽)→ `build_cpg_chunks --useful-only` 丢弃 `disease_entry` 的
  `other/background` chunk → 索引里这些 DDx 段全部丢失。
- **修复**(`scripts/merck_manual_common.py`):`diagnosis → evaluation`、
  `specific/other disorders → differential`(消除死代码)。重跑
  `build_merck_manual_corpus --chunk-only → build_cpg_chunks --useful-only →
  build_cpg_tfidf_index`。效果:
  - Merck `differential` chunk 37 → 136;索引总量 203,830 → **205,115**。
  - leukemoid 可用 chunk 进库(Merck 的 CML-Diagnosis / specific-disorders 段)。
  - **c9_leukemoid CPG 召回:None(缺席)→ rank 21(在库)**。
- 仍差临门一脚:rank 21 卡在 hit@20 外,被 `tuberculosis/CKD/ulcerative colitis` 等
  泛化词压住 → **交棒给 D-entity(去泛化实体排序)**。即预处理修复把"数据缺口"消成
  了"实体排序问题",两个根因边界清晰。
- 语料覆盖仍不均(`angiodysplasia` 57 / `peliosis` 18 / `pancoast` 1 chunk),但那些
  是 chunk 数量,不再是分类 bug。

### B. 评估匹配假阴(便宜、应先修)
- `c23_adhesions`:LLM 生成 `Abdominal adhesions`,金标接受 `adhesions`,
  `{adhesions} ⊆ {abdominal, adhesions}` **本应命中**;但同批 LLM 另一次只吐
  `Adhesional bowel obstruction`,`adhesional ≠ adhesion` 使子集匹配假阴。
- → **family matcher 需词形归一(stemming)**,先还原真实指标再谈漏检数。

### C. 纯 RAG 天花板 / 新架构(证据不支持)
- 片段大多检得到(angiodysplasia rank 7),瓶颈在下游抽取+排序。
  GraphRAG/新检索架构解决不了 vocab 粒度与实体聚合排序。**非当前瓶颈。**

### D. spotter 固定词表(用户质疑)—— 见 §3
- 是 SNOMED 派生非手写,扩展性 OK;真问题是**复合名 vs 裸头词的粒度**,可自动修。

---

## 5. 语料的真实价值定位(不是 L1,是长尾 L2/L3)

在 board-classic 的 14/8 集合上,LLM 本就覆盖(common 12/14、rare 6/8),
语料无法体现 L1-家族召回增益。但在**真长尾**上语料是刚需:

RareArena Orphanet,n=80,留一 + 金标 token 剥离(两臂公平,防泄漏),recall@20:

| arm | recall@20 | 独占救回 |
|---|---|---|
| llm | 24/80 (30%) | 10 |
| cpg_dual | 2/80 (2%) | 0 |
| cr_dual | **37/80 (46%)** | **23** |
| **union_all(cpg∪cr∪llm)** | **48/80 (60%)** | — |

**创新叙事应改为:可验证的自动 MECE 分支生成(保证 L1 完备) + 长尾叶子检索富集
(L2/L3,LLM 弱、语料强),而不是用 RAG 去救 L1 召回。**

---

## 6. MECE 重构:L1 不漏检是结构性保证,不是叶子检索问题

**核心论点:只要 L1 分区 MECE 且 collectively exhaustive,金标永远有可达分支。**
验证——所有顽固漏检的金标都能落进一个自然的 MECE 一级域:

| 漏检金标 | 自然 MECE 一级域 |
|---|---|
| adhesions | 机械性/梗阻性(vs 炎症/血管/肿瘤) |
| leukemoid reaction | 反应性/继发性(vs 克隆性/肿瘤性) |
| angiodysplasia | 血管/结构性来源(vs 炎症/肿瘤/憩室) |
| pancoast tumor | 肿瘤/压迫性(vs 血管/脱髓鞘/代谢) |

即:**具体叶子是否被预先召回,与"金标是否可达"解耦**。若 LLM 生成阶段
自动满足 MECE(而非依赖手工 `syndrome_axis_map.json`),且带**可验证穷尽性**,
则 phase-1 的召回/互斥/可分目标直接达成,语料退居 L2/L3 富集辅助位。

**这要求一个 MECE 穷尽性校验器**(阶段 C 原型):给定 LLM 生成的 L1 分区,
校验 (1) 互斥(分支间无重叠)(2) 穷尽(该综合征的已知病因空间被覆盖,留
"其他/未分类"兜底)(3) 金标可投影到某分支。用 8/14 验证:每个金标是否都落进
生成分区的某个域。

---

## 7. 行动顺序(用户拍板 A→B→C)

- **A(本文)**:根因固化。✅
- **B**:`family matcher` 加 **Porter 词形归一(fixpoint)**,对称作用于金标与候选。✅
  - 关键修复:`adhesional/adhesions/adhesion → adh`、`obstructive/obstruction → obstruct`。
  - 重算 8/14(`meta-llama/llama-3.3-70b-instruct`,stemmed matcher):

  | arm | common14 hit@20 | rare8 hit@20 |
  |---|---|---|
  | llm | 12/14 | 7/8(↑ from 6:救回 c23_adhesions) |
  | union(cpg∪cr) | 10/14 | 5/8 |
  | **union_all** | **12/14(miss 0)** | **7/8(miss 1)** |

  - **"到底漏几例"澄清**:四入口并集在 common **0 漏**;rare 残 1,且该 1 例随 LLM 采样波动
    (LLM 非确定),**不是硬语料缺口**。检索-only 的残差(common 1、rare 3)才是真正的
    流水线缺陷(angiodysplasia 抽取、leukemoid 语料缺口、pancoast 可达性)。
  - 结论:matcher 假阴此前**虚增了 1 例"顽固漏检"**;修正后 8/14 上的召回问题基本被
    LLM+语料并集吸收,残余落到 §4-A/§2 的可控修复项。
- **C**:MECE 穷尽性校验器原型(`scripts/eval_mece_l1_reachability.py`),8/14 验证 L1 可达性。✅ 见 §8。

后续可选(方向已认可,非本轮):针对性补 leukemoid 等真缺口条目、MECE 校验器补严。

---

## 9. D-entity 实测:中性/负面(诚实记录,已默认关闭)

实现了两项(均 opt-in,默认关,`test_dual_entrance_case_reports.py` 10/10 不回归):
1. **SNOMED 头词别名**(`build_disorder_vocab(head_aliases=True)`):从复合名派生裸头词
   ("Angiodysplasia of intestine" → "angiodysplasia"),+8,787 别名。
2. **去泛化特异性重排**(`GuidelineBranchSource(degeneric_rerank=True)`):按检索器 TF-IDF
   idf 给实体聚合分乘特异性因子(rare 词上调、泛化词下调),在截断前生效。
   实测因子:`angiodysplasia`=1.01、`hypotension`=0.71、`tuberculosis`=0.67。

**结果(逐配置,cpg_dual/cr_dual hit@20):**

| 配置 | COMMON cpg | COMMON cr | RARE cpg | RARE cr | RareArena n=80 cr |
|---|---|---|---|---|---|
| base | 8/14 | 8/14 | 3/8 | 5/8 | 37/80 (46%) |
| head only | 8/14 | **6/14** | 3/8 | 4/8 | — |
| head+degen | **7/14** | 8/14 | 3/8 | 5/8 | 37/80 (46%) |

**判定:净收益 ≈ 0,甚至轻负。** 8,787 个头词别名引入 spotting 噪声,挤掉了部分 common
金标(cr 8→6);RareArena 长尾完全不变。

**但产出一个更精确的诊断(修正 §2 的初判):** angiodysplasia 在**综合征单入口** legacy
路径上其实排 **rank 13–19(本就接近/进 @20)**;真正把它压到 **rank 37** 的是
**双入口 RRF 与弱 salient("hematochezia in older adult")的融合稀释** + `max_candidates=40`
截断。即残余漏检的机制是**融合质量(弱 salient 淹没强综合征信号)**,不是"实体不在 vocab"
也不是"实体排序泛化偏置"。→ 下一步应调**融合**(salient 质量门控 / 动态入口权重 / 提高
截断额度),而非继续加词表或重排。已把 head/degen 留作 opt-in,默认关。

---

## 8. MECE L1 可达性实证(阶段 C 关键结果)

`scripts/eval_mece_l1_reachability.py`,防泄漏协议:
1. **GENERATE**:LLM 仅凭 {综合征, salient} 生成 5-9 个互斥 L1 家族 + 显式兜底
   "other/less-common causes",**不看金标、不用手工 axis 表**。
2. **JUDGE**:另一次 LLM 调用把金标病名指派到唯一分支索引(或 -1)。

结果(generator+judge = `meta-llama/llama-3.3-70b-instruct`):

| 集合 | reachable(落进**非兜底**具体分支) | reachable(任意分支含兜底) |
|---|---|---|
| COMMON (14) | **14/14** | 14/14 |
| RARE/HARD (8) | **8/8** | 8/8 |
| **合计 (22)** | **22/22** | 22/22 |

每例都生成了显式兜底分支,且**所有金标都落进了一个具体(非兜底)MECE 家族**:
- angiodysplasia → `vascular/structural`
- leukemoid → `neoplastic/proliferative`
- pancoast → `neoplastic/compressive`
- adhesions → `adhesive/intussusceptive`

**这是本轮最强的结论:**
- **叶子检索 recall@20**:union_all 在 rare 上 7/8(且残 1 随 LLM 采样波动)。
- **L1 结构可达性**:22/22——**每个金标都有可达的一级分支**。

即:把 phase-1 目标从"预先召回到具体叶子"改为"生成 MECE+穷尽的 L1 分区",
**L1 不漏检从一个检索难题变成一个可达成、可验证的结构性属性**。语料/检索层的
价值随之明确转移到 **L2/L3 长尾叶子富集**(RareArena 上 cr 46% > llm 30%)。

**caveat(下一步该补的严谨性,非本轮):**
1. 本原型只验证了"金标可投影到某分支",**尚未量化互斥性违背**(同一病能否被指派
   进≥2 分支)与**穷尽性缺口**(是否有病因空间的分支缺失)。需加一个"MECE 违背率"
   指标:对每个分区枚举一组已知病因,检查重叠/遗漏。
2. generator 与 judge 用同一模型,judge 可能对自己的分区过度自信 → 应换**独立模型**
   做 judge,或引入人工抽检。
3. n=22 且是 board-classic;应在 RareArena 长尾上重跑,确认长尾金标同样 L1 可达。

---

## 8b. D-mece 补严:换指标(互斥违背/穷尽缺口)+ 独立 judge + RareArena 长尾

上面三条 caveat 全部落地。`scripts/eval_mece_l1_reachability.py` 重写:generator 与
**judge/probe 换成独立模型**(Llama-3.3-70B 生成、**Qwen-2.5-72B 独立评判**);新增
**probe 群体**(每例独立生成 6 个具体病,不看分区),在其上量化两项 MECE 质量:
- **互斥违背率** = probe 被指派进 **>1 个非兜底分支**的比例(重叠);
- **穷尽性缺口** = probe **无法落进任何非兜底分支**(只落兜底/无)的比例(病因空间遗漏)。

新增 `--rarearena N` 用长尾病例(金标=真实诊断)复跑。结果(n=32:common14+rare8+RareArena10):

| 集合 | 金标可达(具体) | 互斥违背率 | 穷尽性缺口 |
|---|---|---|---|
| COMMON (14) | 13/14 | 9/78 (12%) | 8/78 (10%) |
| RARE/HARD (8) | 8/8 | **18/48 (38%)** | 2/48 (4%) |
| RareArena 长尾 (10) | 9/10 | 13/60 (22%) | 2/60 (3%) |
| **合计 (32)** | **30/32** | **40/186 (22%)** | 12/186 (6%) |

**关键修正与新结论:**
1. **自评高估了可达性。** 上一版 generator 自评给 22/22;换独立 Qwen judge 后
   **30/32**——common 的 `acute_pancreatitis` 金标无法被指派进 Llama 生成的任一分支,
   1 例 RareArena 只落兜底。即"L1 可达性"并非饱和,**自评存在乐观偏置**。
2. **互斥性才是真正的短板,且随长尾恶化。** 整体互斥违背 22%,**rare/hard 高达 38%**
   (`c18_peliosis` 5/6、`c23_adhesions` 4/6、`c9_leukemoid` 3/6 的 probe 同时落进多个
   分支)。这给了 D-mece 一个**有区分度、非饱和的改进靶点**:降低分区重叠(尤其长尾)。
3. **穷尽性缺口较小(6%)**,主要在 `macrocytic_anemia`(3/6)。
4. 方法学上,"可达性"单指标不足以比较分区质量(易饱和且受自评偏置);应以
   **互斥违背率 + 穷尽性缺口 + 独立 judge** 为主指标。这正是你说的"需要其他 criteria"。

---

## 9. D-fusion:融合稀释是残余漏检的实际瓶颈(实测,已落地为可配置)

§8 的 D-entity 诊断指向"融合稀释":弱 salient 在等权 RRF 下把综合征-强金标压出 @20。
本节把它做成可调旋钮并**在大样本上判定**(不只 14/8)。`GuidelineBranchSource.recall` /
`CaseReportBranchSource.recall` 新增三参数:`finding_entrance_weight`(finding 入口 RRF
权重)、`rrf_k`、`salient_gate`(用检索器 idf 丢弃非判别性 salient)。

**RareArena n=80(长尾,确定性,无 LLM):**

| 配置 | cr_dual@20 |
|---|---|
| base(w1.0) | 37/80 |
| gate / w0.5 / w0.5+gate / w0.3 / k10 | **38/80** |

**14/8(默认生产 vocab,head_aliases=False):**

| 配置 | COMMON cpg / cr | RARE cpg / cr |
|---|---|---|
| base(w1.0) | 8 / 8 | 4 / 5 |
| **w0.5** | **9** / 8 | 4 / 5 |
| gate | 7 / 7 | 4 / 4 |
| w0.5+gate | 7 / 7 | 4 / 4 |

**结论:**
1. **`finding_entrance_weight=0.5` 是干净小赢**:COMMON cpg 8→9(把被弱 salient 淹掉的
   综合征-强金标提回 @20)、RareArena 37→38,**其余全部不回归**。**证实了融合稀释诊断。**
2. **`salient_gate`(idf 丢弃)净负**(COMMON 8→7、RARE 5→4):idf 判别过于粗暴,会误杀
   有用 finding。**不采用。**
3. `rrf_k`、SNOMED 头词别名对结果无正向作用。
4. 绝对增益很小(±1 例)——因为 finding 入口同时也**真救了**另一些例(Pancoast 类),
   不能直接砍。净效应是"轻正、无回归"。这也解释了为何残余漏检"顽固":单一旋钮到顶了。

**落地:** 新增 `Config.salient_finding_entrance_weight`(默认 1.0 保持确定性),controller
两处 `recall_for_branches` 调用已接入;置 0.5 即启用上面实测更优的融合。`test_dual_entrance_case_reports.py` 10/10 不回归。

---

## 10. 互斥违背根因深挖:主因是"分类轴混用"(axis mixing)

对 §8b 的 overlap 用 `--dump-overlaps` 导出每个重叠 probe 落进的分支标签(n=36,含
RareArena 14),聚合"系统性同时命中的标签对":

| 次数 | 重叠标签对(非正交) |
|---|---|
| 6× | Genetic/congenital × Vascular/structural anomalies |
| 4× | Hepatobiliary/pancreatic × Neoplastic/compressive |
| 3× | Infectious × Pulmonary |
| 3× | Other systemic × Toxic/Metabolic |
| 2× | Traumatic × Vascular/structural |
| 2× | Neoplastic/proliferative × Primary hematologic |
| 2× | Infectious × Inflammatory/Autoimmune |
| 2× | Cardiovascular × Pulmonary |

**根因判定:重叠几乎全部来自"缺少单一分类基准(fundamentum divisionis)"——LLM 把
不同轴的桶并列**:
- **解剖轴 × 机制轴**(最系统):`Hepatobiliary/pancreatic`(解剖)与 `Neoplastic`(机制)
  并列 → 胰腺肿瘤两边都进;`Infectious`/`Traumatic`(病因)× `Pulmonary`(解剖)同理。
- **病因轴 × 机制轴**:`Genetic/congenital` × `Vascular/structural`(结构异常常本就是先天),
  `Neoplastic/proliferative` × `primary hematologic`(白血病既是肿瘤又是血液)。

即**违背不是"scope 措辞模糊",而是分区维度不统一**。→ 修法明确:强制**单轴分区**
(一次只用 机制 / 解剖 / 病理过程 之一),而非混合桶。在 `eval_mece_l1_reachability.py`
加 `--gen-mode single`(显式单一 fundamentum divisionis 的生成 prompt)。

**mixed-vs-single A/B(n=36:common14+rare8+RareArena14,同一独立 probe 集,Qwen 独立 judge):**

| 生成模式 | 金标可达(具体) | 互斥违背率 | 穷尽性缺口 |
|---|---|---|---|
| mixed(原) | 29/36 | 59/272 (**21%**) | 17/272 (6%) |
| **single(单轴)** | **34/36** | 40/272 (**14%**) | 21/272 (7%) |

**结论(根因确认 + 修法有效):**
1. 强制单一分类基准把**互斥违背 21%→14%**(−7pp,相对降约 1/3),证实"轴混用"就是主因。
2. 顺带把**金标可达性 29→34**(更干净的分区反而更好安放金标),穷尽缺口基本不变(噪声)。
3. 这是一个**可落地到生成阶段的、有区分度的 MECE 改进**:BranchCreator 的分区 prompt 应
   加"单一 fundamentum divisionis"约束。互斥性(而非可达性)才是长尾上真正待优化的维度。
   (17 次 qwen provider 抖动加了少量噪声,但方向一致且幅度明确。)

---

## 11. 生产落地 + 分支创建阶段核验(C 表落地 + B 表全开 + LLM 撤换)

**落地清单:**
- **C 表(单轴 MECE)写进生产 prompt**:`prompts/branch_creator.txt` 新增
  "MANDATORY SINGLE-AXIS RULE",要求所有同级分支来自同一 fundamentum divisionis,并给出
  解剖×机制混用的反例。(此前只在评测脚本验证,现进入实际分支生成。)
- **B 表全开(核验配置)**:`enable_case_report_branch_source` + `enable_cpg_branch_source`
  + `enable_llm_ddx_branch_entrance` + `enable_branch_knowledge`,`salient_finding_entrance_weight=0.5`,
  CPG 入口指向重建后的 `data/corpus/cpg_index`(D-data Merck 修复)。
- **骨干 LLM 撤换**:`eval_pipeline_medbullets.py --model` 默认 `qwen/qwen3-32b` →
  **`meta-llama/llama-3.3-70b-instruct`**(qwen3 基座更强但此前协议/窗口表现不佳,暂撤,
  待 llama 验证可用后再验 qwen3)。

**分支创建阶段核验**(`scripts/eval_branch_creation_medbullets.py`,只跑 `select_root →
create_branches` 就停,LLM judge 判金标是否落进某个非兜底一级家族):

| 集合 | clean L1 覆盖(金标进非兜底家族) | reachable(含兜底) |
|---|---|---|
| medbullets 难题 text-only 诊断题(n=9) | **9/9** | 9/9 |

每题的分区都是**单轴、干净**,金标全部命中具体家族(节选):

| 题 | 金标 | 命中家族 |
|---|---|---|
| Pancoast | Apical lung tumor | Compressive Plexopathy or Apical Mass |
| 类白反应 | Leukemoid reaction | Reactive / Non-malignant Leukocytosis(D-data 修复受益) |
| 肝血管扩张 | Vascular ectasia within the liver | Hepatic / Hepatobiliary Vascular Disorder |
| 肠粘连 | Adhesions | Mechanical Obstruction |
| 甲旁亢 | Increased parathyroid hormone | PTH-mediated Hypercalcemia |

**关键结论:在落地配置下,分支创建阶段对这批难题实现 L1 无漏检(9/9)。** 即生产端剩余
的准确率问题**不在分支创建**(一级方向已完备且 MECE),而在**下游**(叶子规划 / 证据获取 /
承诺判定)。这把调试焦点从"分支是否漏方向"明确转移到下游推理链。
(单次 llama temp=1.0 运行;覆盖信号无歧义,若需稳健性可多次复跑取一致率。回归:
`test_branch_knowledge / test_dual_entrance_case_reports / test_controller` 共 19/19 通过。)

## 12. 手工策展依赖审计:手写 axis map 非 load-bearing,可移除(可扩展性)

用户要求:**必须移除手工策展依赖;若存在必需的手工依赖,视为可扩展性缺陷**。为此把分支
创建阶段的 axis 来源做成三档对照(`scripts/eval_branch_creation_medbullets.py --branch-mode`),
在同一批 9 题上比 clean L1 覆盖:

| branch-mode | axis/domain 来源 | 手工策展? | clean L1 覆盖 | 说明 |
|---|---|---|---|---|
| `handmap` | `syndrome_axis_map.json`(手写)+ B 表四入口 | **是** | 9/9 | §11 落地配置 |
| `auto_kb` | SNOMED 定义属性 + LR 缓存派生(`KBAxisMap`) | 否 | **8/9** | taxonomy 轴产出无关域(如把臂丛病变分到"碳水代谢紊乱"),case 0 漏 |
| `pure_llm` | 无任何 axis map、无 B 表:单轴 prompt 独立生成 | **否** | **9/9** | 与 handmap 持平,零策展 |

**结论:手写 `syndrome_axis_map.json`(及 `syndrome_override_seeds.json` 兜底种子)对 L1 覆盖
不是 load-bearing。** `pure_llm` 单轴 prompt 在完全不读任何手工 MECE/axis 文件的情况下达到
与 handmap 相同的 9/9,而 KB 自动派生(`auto_kb`)反而更差(taxonomy 轴质量不稳,产生 8/9)。
因此把生产分支路径设为 **pure_llm(`enable_branch_knowledge=False`,默认值)** 即可**移除该手工
策展依赖且无覆盖损失**——这是本次审计对"可扩展性缺陷"的直接消解。

> 注:`pathognomonic_markers.json / diagnostic_markers.json / age_sex_incidence.json / LR 缓存`
> 等在 pure_llm 下仅作**下游知识注入且 fail-open**(缺失不影响流程),且多为脚本自动构建
> (`build_diagnostic_markers.py` 等),不属于"必需的手工 MECE 策展"。真正的手写 MECE 文件
> (axis map / 种子)已被证明可下线。

## 13. (2) 下游失分定位:漏检不在分支创建,在**证据环节的后验塌缩**

新建 `scripts/eval_downstream_trace_medbullets.py`:跑**真实完整生产 controller**(select_root →
branches → 证据环 → AnswerMapper),对每题从最终 state 抽取金标一级家族的**后验轨迹**并归因失分
阶段。**分支路径用 pure_llm**(§12 证明的零策展、9/9 覆盖路径),所以任何失分都是下游造成。

工程隔离:每题一个**独立子进程**(各自 GIL),否则单题的 CPU 死循环会因 GIL 饿死其余线程
(初版线程池 9 题全 TIMEOUT 即此因);并**关闭二级 LR 缓存**(9 进程共享一个 JSON → 反复全量
重写 + 写竞争,`faulthandler` 自转储定位到 `secondary_lr_cache._flush_locked`)。

**8 题跑通(case 22 甲旁亢单题 CPU 死循环命中已知 runaway,超时丢弃),归因分布:**

| 失分阶段 | 题数 | 含义 |
|---|---|---|
| **证据环后验塌缩**(EVIDENCE_COLLAPSE / PRIOR_STARVED) | **7** | 金标家族**存在且早期竞争**(early_rank 多为 1~2),随证据轮次**被单调压到垫底**,错误家族胜出 |
| L1_MISS | 1 | case 14 金标答案是"胸骨右下缘舒张期杂音"这类**体征描述而非病名**,judge 无法映射到家族(benchmark 答案格式伪缺失,非真漏方向) |

**逐题后验轨迹(金标家族,按轮次)——全是单调塌缩:**

| 题 | 金标 | 家族 early_rank | 家族后验轨迹 | 最终名次 | 胜出(错误)家族 |
|---|---|---|---|---|---|
| 1 Pancoast | Apical lung tumor | **1** | 0.643→0.465→0.491→0.168→0.102 | 2 | Neuropathic 0.573 |
| 9 类白反应 | Leukemoid reaction | 2 | 0.262→0.263→0.195→0.139→0.052 | 3 | Myeloid Neoplasm 0.498 |
| 13 胰高血糖素瘤 | Alpha cell tumor | 2 | 0.292→0.31→0.144→0.109→0.024 | 3 | Autoimmune 0.179 |
| 17 CML | Chronic myelogenous leukemia | 2 | 0.157→0.09→0.06→0.03→0.018 | 2 | Myeloid w/ Blasts 0.611 |
| 18 肝血管扩张 | Vascular ectasia | 5 | 0.115→0.143→0.38→**0.534**→0.02 | 5 | 末轮**全家族塌到≈0**,AnswerMapper 全 0 → 默认 A |
| 23 肠粘连 | Adhesions | 2 | 0.25→0.162→0.13→0.093→0.029 | 3 | Infectious GI 0.127 |
| 24 鼻腔异物 | Foreign body obstruction | 2 | 0.16→0.038→0.028→0.017→0.01 | 3 | Inflammatory 0.064 |

**关键结论(回答 (2)):**
1. **失分环节明确在证据环的概率更新,不在分支创建。** 8 题里 7 题金标家族**都在场且开局竞争
   力靠前**,却被证据轮次**系统性压到垫底**——这是 `annotate_evidence_bundle → apply_probability_
   update` 把质量持续搬离正确家族,而非"没生成正确方向"。分支创建 9/9(§11)与下游 0/8 的落差
   全部归属下游。
2. **case 18 是最尖锐的样本:** 正确家族一度以 0.534 领跑,末轮被打到 0.02 且**所有家族后验一起
   塌到≈0**,AnswerMapper 拿到全 0 映射只能默认输出 A。指向末轮证据更新/归一化(或规则排除)
   存在**灾难性反向刷分**。
3. **发现两个下游 bug(证据链质量污染源):**
   - `LR injection for Annotator failed: could not convert string to float: '.'`(case 9/13/14/17
     命中):LR 参考数值解析 bug(`dx_feature_retriever`/`lr_retriever`),使 LR 注入被丢弃 → 证据
     权重失真。
   - 二级 LR 缓存在多进程/高并发下 `_flush_locked` 全量重写造成 CPU 停滞(本次通过关闭缓存规避;
     生产并发下建议改增量写或每命名空间独立文件)。
4. **下一步应聚焦:** 证据标注→后验更新的**方向与幅度**(为何正确家族被持续 down-weight)、末轮
   塌缩防护、以及上面两个解析/缓存 bug。分支创建、MECE、检索入口已不是瓶颈。

(harness:`scripts/eval_downstream_trace_medbullets.py`;结果:`logs/downstream_hard9.json` +
`logs/downstream_retry3.json`。llama-3.3-70b,pure-LLM 分支路径,单次运行。)

## 13b. 后验 down-weight 根因锁定 + 两处修复(LR 解析 bug + 判别门控)

回答 §13(4)遗留的核心问题:**为什么正确家族被持续 down-weight?** 用一次**无 LLM 的受控模拟**
把机制从 LLM 噪声里剥离出来,再用真实 A/B 验证。

### 根因 A(数学层,主因):softmax 归一化的"稀释性 down-weight"

`updater.ordinal_update` 每轮做 `posterior_i × weight(label_i)` 后**全局重归一化**。受控模拟(5 家族,
金标开局 0.30 并列第一,此后每轮只有**某一个 distractor** 拿到 `weak_for`(×1.2)、其余全 `neutral`):

```
turn   GOLD   DistA   DistB   DistC   Other
   0   0.300  0.250   0.200   0.150   0.100
   5   0.244  0.293   0.235   0.147   0.081     ← GOLD 从并列第一被挤到第二
```

**金标从头到尾没有拿到过一次 `against`**,仅因归一化,"别人涨→我被动缩水"。真实病例里非特异
主诉(发热/腹痛/乏力)极多,标注器只会给被"框定"的 distractor 一个 `weak_for`、给宽泛的正确家族
`neutral`,于是 5 轮累积成单调塌缩——正是 §13 观察到的 early_rank 1~2 → 末轮垫底。

### 修复 1(低风险,已默认生效):LR 参考数值解析 bug

`lr_quant._SN_RE/_SP_RE` 用 `([\d.]+)` 贪婪吞标点,"sensitivity of ." → `'.'` → `float('.')` 抛错
(即 §13 的 `could not convert string to float: '.'`)。且 controller 里 Annotator 的 LR 注入循环
**`except: break`**——一个坏 finding 直接**丢掉该轮剩余全部 LR 证据**。两处同修:

- `lr_quant`:正则改 `(\d+(?:\.\d+)?)`(与 §27.4 `_LR_RE` 同款),`float()` 全部 try/except 兜底 → 坏
  token 退化为"无数值",不再抛错。
- `controller` LR 注入循环:`break → continue`,坏条目跳过、不再牺牲整块证据。
- 回归:`test_lr_detox / test_lr_negative_ruleout / test_disease_norm_lr_quant / …` 共 **34/34**;
  受控解析测试 `float('.')`、`LR+=0.86.` 等全部不再崩。

### 修复 2(默认 OFF,零回归):判别门控 `enable_discrimination_gate`

针对根因 A:**整轮都非判别性**(所有 label ∈ {neutral, weak_for, weak_against};数值 LR 全落
`[1/1.5,1.5]`)时**冻结后验**、不做归一化搬运;**只要该轮有 ≥1 个 moderate/strong 标签,就照常
全量更新**(含其 weak 标签)。同一模拟下 GOLD 稳在 0.300 不塌,而一次 `strong_for` 仍照常把
distractor 0.25→0.50。落点:`updater.{ordinal_update,bayesian_lr_update,calculator_update}` 加
`gate` 参数,`controller.apply_probability_update` 读 `config.enable_discrimination_gate`。默认 OFF
= 字节级等价旧路径。单测 `tests/test_discrimination_gate.py` **7/7**。

### 真实 A/B(4 题 collapse 子集,pure_llm,均含 LR 修复;baseline vs `--gate`)

| 题 | 金标家族后验轨迹 baseline | 轨迹 gate | 读数 |
|---|---|---|---|
| 13 胰高血糖素瘤 | 0.833→0.206→**0.0**→0.314→0.281 | 0.335→0.362→0.521→**0.539**→0.418 | 门控**消除了塌到 0**,金标家族全程 rank1 |
| 23 肠粘连 | 0.203→0.307→0.274→0.34→0.309 | 0.346→0.463→0.317→0.381→**0.503** | 门控把金标家族后验抬得更高、稳居 rank1 |
| 18 肝血管扩张 | 0.182→…→0.004(饿死) | 0.4→0.286→0.136→0.108→0.07 | 起点更高但仍衰减:该题有**真判别性反向证据**,门控**正确地不去动它** |
| 24 鼻腔异物 | 0.184→…→0.024(饿死) | 0.169→…→0.019 | 同上,残余饿死 |

**结论(诚实):**
1. **根因 A 被证实且被门控控制住**:门控把 case13 金标家族从"塌到 0.0"救成"全程 rank1、峰值 0.539",
   case23 从 0.34 抬到 0.503。**机制层修复有效、可复现**(模拟 + 真实轨迹一致)。
2. **门控没有立刻抬升端到端准确率**(gate 0/4 vs base 1/4),但这**不是门控回归**,而是它把失分从
   "家族丢失"**推进到了下游的两类更靠后缺陷**,后者现在成为主瓶颈:
   - **MAP_FAIL(答案映射,新主因)**:case13/23 金标**家族已 rank1、后验最高**,AnswerMapper 却在
     **正确家族内选错具体选项**——case23 金标"Adhesions(粘连)"与干扰项"Twisting of the bowel
     (肠扭转)"**同属机械梗阻家族**,映射器选了肠扭转;case13"Alpha cell tumor"与"Insulin resistance"
     同属内分泌家族。**这是叶层/选项判别问题,不是家族后验问题,门控管不到。**
   - **真判别性反向证据**(case18/24):金标家族确有 moderate/strong 反向标注,门控按设计不干预 →
     属于"标注方向"问题(见下一步)。
   - 注:n=4 且 AnswerMapper 本身随机(base 与 gate 两次同样金标家族 rank1,却分别映射到 A/E),
     故 4 题的 0/4 vs 1/4 差异**落在映射器噪声内**,不能据此判定门控优劣。
3. **下一步真正的杠杆(已被本次 A/B 前移暴露)**:
   (a) **AnswerMapper / 叶层判别**——正确家族内区分具体病因(粘连 vs 扭转、alpha 细胞瘤 vs 胰岛素
       抵抗),这是当前最大失分源;
   (b) **标注方向**——case18/24 的反向 moderate/strong 是否合理(标注器是否被 framing 带偏);
   (c) 残余 **CPU-runaway**(case17/22 仍超时,LR 模糊匹配深层 bug)。

门控与 LR 修复均已落地;LR 修复默认生效(纯修 bug),门控 `enable_discrimination_gate` 默认 OFF,
建议在更大样本 + 修好 AnswerMapper 叶层判别后再评估是否设默认。
(harness:`--gate`;结果 `logs/downstream_gate5.json` vs `logs/downstream_base4.json`。)

## 14. KB 集成通路重构:解耦"分区定义"与"实体召回"(§32 recall-hints)

**问题(用户指出):** 生产端"知识集成介入后的轴生成/投影后处理"沿用手工策展时代方法。
读码确认根因——`_build_branch_candidates` 把**两件本可分离的事耦合**成一条通路:

1. **分区定义**:`axis_map.domain_names(entry)` → 变成 `mandatory_coverage`,`_BRANCH_
   KNOWLEDGE_DIRECTIVE` 命令 LLM"每个 domain 出一个 L1 分支、不得丢弃"。于是 **L1 分区被
   axis_map 支配**——hand map(不可扩展)或 KBAxisMap(SNOMED taxonomy 分组质量差:臂丛病变
   →"碳水代谢紊乱 (taxonomy)"等无关域,§12 实测 8/9 < pure_llm 9/9)。把 LLM 锚到坏分区**有害**。
2. **实体投影**:`recall_for_branches → axis_map.project_entity`(member_keywords 子串最长匹配)。
   任何**没子串命中种子域**的召回病名被直接丢弃(`guideline_branch_source.py` L403-404)。对 KB 域,
   member_keywords≈种子病名 token,**新召回的长尾病名大多投影失败被丢**——把入口本应带来的长尾召回
   几乎全部浪费,幸存的又只强化已经坏了的桶。

**净效果:** `auto_kb + B 表`(四路并发)= 把 LLM 锚到坏分区 + 喂投影残缺的实体 → **反不如
pure_llm**。而 RareArena 证明 `recall()` 层(未投影)确实能捞回长尾罕见病 @20 —— **召回是好的,
坏的是"分区+投影"的耦合**。

**重构(§32,新增 `branch_kb_recall_hints`):解耦。** LLM 独占单轴 MECE 分区(已证 9/9,**不注入
mandatory_coverage、不需要任何 axis_map**);4 入口(case-report ∪ CPG ∪ LLM-DDx)召回经 RRF 融合成
**一个扁平 ranked `candidate_diseases` 提示表**(非分区、非强制)注入,指令改为"用提示补全你自己
分区的可达性"。KB 由此变成**严格增量**:只能扩召回,永远不能强加坏分区或丢掉 LLM 的好分区,且
**零手工策展**。`_build_branch_candidates` 里新模式优先短路,`auto_axis_kb`/`enable_mandatory_kb_
branches` 在此模式下被取代。

**分支创建 A/B(9 题 text-only,llama-3.3-70b,`eval_branch_creation_medbullets.py --branch-mode`):**

| 模式 | 手工策展 | 分区来源 | 长尾召回 | clean L1 | 说明 |
|---|---|---|---|---|---|
| pure_llm | 否 | LLM 自建 | 无 | 9/9* | *case3 为 judge 伪命中(金标是"胸骨右下缘舒张期杂音"体征串) |
| auto_kb(耦合) | 否 | KB taxonomy | 投影后残缺 | **8/9** | case0 臂丛病变被分到"碳水代谢紊乱"等无关域 → 漏 |
| **recall_hints(§32 解耦)** | **否** | **LLM 自建** | **扁平全量注入** | **8/9** | 唯一 miss = case3 同一体征串伪缺失(与 pure_llm 同源噪声),**不回归** |

**关键证据(解耦既不伤分区、又真加召回):**
- recall_hints **修复了 auto_kb 漏的 case0**:分区是干净单轴(Neoplastic/Vascular/Inflammatory/
  Traumatic/Other),金标→Neoplastic **CLEAN**;且提示表里赫然含 **"Pancoast tumor"、"Brachial plexus
  tumor"、"Cervical spine tumor"**(金标 Apical lung tumor 就是 Pancoast)。
- 提示表反复**把金标本身或近邻捞进候选**:case4 含 "Chronic Myeloid Leukemia"(金标 CML)、case5 含
  "Hepatic Vein Thrombosis"(金标肝血管扩张,血管类)、case8 含 "Foreign body obstruction"(金标原词)。
  这正是耦合投影此前**丢弃**的长尾召回价值。
- 即 recall_hints 在 L1 覆盖上**≈ pure_llm(差异仅一例 judge 噪声)、且明显优于耦合 auto_kb**,同时
  把长尾召回安全地注回。回归:`test_branch_knowledge / test_dual_entrance_case_reports /
  test_controller` 共 **19/19 通过**。

**结论与建议:** 用户的判断成立——旧集成通路的"轴生成/投影"确是手工策展遗留耦合,叠加四路并发反
伤。§32 解耦模式在保住 LLM 最优分区的前提下把 KB 召回变成零策展的安全增量,是"既接入 KB 又不伤"
的正确通路。默认仍 OFF(`branch_kb_recall_hints`),建议后续做两件事再定默认:(1) RareArena 长尾上
跑"提示注入 → LLM 分区 → 金标可达性"的大样本 A/B(现有 `eval_llm_ddx_rarearena.py` 已证 union 召回
@20 增益,缺的是"注入后 LLM 分区是否真覆盖"这一段);(2) 可选的 Phase-B——生成后把未被任何家族覆盖
的高分召回作为缺口自动补一枝(比旧 `enable_mandatory_kb_branches` 更稳,因为补的是"召回实体缺口"
而非"KB 域")。

(harness:`scripts/eval_branch_creation_medbullets.py --branch-mode recall_hints`;结果
`logs/branchgen_rh.json`。代码:`config.branch_kb_recall_hints` + `controller._build_recall_hints`
+ `_BRANCH_RECALL_HINTS_DIRECTIVE`。)

### 14b. RareArena 长尾大样本 A/B:注入不回归,家族级判定已近饱和(补做上文建议 (1))

补上"注入后 LLM 分区是否真覆盖金标"这一段。新 harness `eval_recall_hints_rarearena.py`:
40 例 RareArena、**留一法**(case-report 入口排除本案自身报告,防泄漏)、金标 token 从 presentation
剥离;**同一 root 复用**(KB 不影响选根 → 公平且省算力),仅 `create_branches` 一处分 arm;judge 把
金标病名指派到某个生成家族(或 -1),CLEAN = 落在**非残余**家族。

| arm | clean | reachable | 说明 |
|---|---|---|---|
| pure_llm(无提示) | 38/40 (95%) | 38/40 (95%) | LLM 独建分区 |
| **recall_hints(注入)** | 37/40 (92%) | **39/40 (97%)** | reachable 反超 pure |
| — | — | — | RESCUE=1、REGRESS=2 |

- **不回归的实质结论**:两 arm 差异全部落在**跨越广域家族边界**的判定抖动上,而非真覆盖丢失。
  逐例看 3 个 discordant:
  - **TTP(rescue)**:pure 建了一套"胰岛素/低血糖"轴(跑偏,金标无家可归 miss);hints 建"内分泌/
    感染/毒代/神经/其它"→ 金标落 "Other Causes" **reachable**。提示把分区从跑偏拉回。
  - **Wilson / pPNET(regress)**:两 arm **都 reachable**,只是 hints 版把金标判进了残余 "Other" 而非
    某个具名家族 → clean/非 clean 的**判定阈值抖动**,不是漏检(reachable 均命中)。
- **饱和效应**:RareArena 金标多为罕见"实体",但家族级 MECE 分区(肿瘤/血管/炎症/感染/代谢…)对二者
  几乎都可达(95–97%),**家族级判定已近天花板**,难以放大提示增益——提示的价值在 §14 已由"金标近邻
  病名(Pancoast/CML/异物)反复进候选表"直接证实,此处大样本进一步证**注入不伤害 reachable**。

(harness:`scripts/eval_recall_hints_rarearena.py --n 40`;结果 `logs/recall_hints_ra_n40.json`。)

### 14c. Phase-B:召回驱动的 MECE 缺口自动补枝(实现上文建议 (2),默认 OFF)

比旧 `enable_mandatory_kb_branches` 更稳:补的是**"召回实体缺口"**而非"KB 域"。在 recall-hints 分区
生成后,一次 LLM 指派 pass 判定 top-K 召回候选各自能否归入某个家族;**若有高分候选一个家族都进不去**,
发**一次**纠偏 re-call 让 LLM 加宽/新增一个家族(保持同一单轴 MECE,不得建病名分支)。守卫:**仅当
修复后家族数不缩水才接受**(坏 re-call 永不回归);fail-open → 原分区。开关
`config.branch_recall_gap_fill`(需 `branch_kb_recall_hints`),默认 OFF。

- 8/14 难题 `--branch-mode recall_hints_gap` 全跑:**clean 9/9、reachable 9/9**(9 例分区本就无缺口 →
  无 re-call 触发,证明"无缺口不打扰"的空操作路径正确)。
- 单测 `tests/test_recall_gap_fill.py` **6/6**:开关 OFF/非 recall-hints 空操作、全覆盖不触发、
  修复不缩水才接受、缩水则拒绝、负号索引解析(含字符串 "-1")。

(代码:`controller._gap_fill_branches` + `_recall_gap_uncovered`;prompt 追加
`uncovered_candidates` 指令分支;harness `--branch-mode recall_hints_gap`。)

## 14. B 表全开(4 路并集)vs pure-LLM 的下游 A/B:不伤害,反而净正向(但有代价)

问题:按"最佳配置测试程序"(B 表全开=`enable_branch_knowledge + case_report + cpg +
llm_ddx` 四入口并集 + 手写 axis map)跑完整下游,是否伤害性能?给 `eval_downstream_trace_
medbullets.py` 加 `--branch-mode {pure_llm,btable}`,在**同一批难题**上做下游 A/B。

**6 例两配置都跑通的难题上:**

| 题 | 金标 | pure-LLM(零策展) | B 表全开(4 路并集) |
|---|---|---|---|
| 1 Pancoast | Apical lung tumor | XX 塌缩 r2 | **OK ✅** r2 |
| 13 胰高血糖素瘤 | Alpha cell tumor | XX 塌缩 r3 | XX 塌缩 **r2** |
| 14 舒张期杂音 | (体征描述,非病名) | XX judge 伪缺失 | XX 饿死 r5 |
| 18 肝血管扩张 | Vascular ectasia | XX 塌缩 r5 | XX 塌缩 **r2** |
| 23 肠粘连 | Adhesions | XX 塌缩 r3 | **OK ✅** r1 |
| 24 鼻腔异物 | Foreign body | XX 饿死 r3 | XX 饿死 **r2** |
| **准确率** | | **0/6** | **2/6** |

另:case 9、17 在 B 表下**超时丢弃**(pure-LLM 下可跑完)。

**结论:**
1. **准确率不但不受损,反而净正向**:B 表 2/6 > pure-LLM 0/6,且把正确家族最终名次从 r3/r5
   普遍拉到 r2。KB 锚定 + 4 路并集给 BranchCreator 更强候选,救回 Pancoast、肠粘连。
2. **可扩展性代价**:B 表"最佳配置"= handmap,**重新引入手写 `syndrome_axis_map.json` 依赖**
   (§12);对不在手写表里的综合征 fail-open 退回 pure-LLM,增益不保证外推。
3. **算力/鲁棒性代价 + 混淆项**:B 表更重(LLM-DDx 第 4 入口 + 更多检索 + 更长 prompt),
   使 case 9/17 命中已知 CPU-runaway 超时;且本次 B 表把下游 `rag_index_dir` 一并换成
   `cpg_index`(现设计下 CPG 分支源与下游 RAG 共用索引),故 2/6 增益可能部分来自换索引而非
   并集本身。
4. **两条路的准确率天花板都被同一下游 bug 压着**(正确家族被证据环持续 down-weight,§13),
   修那个才是真正杠杆。

决策:要最高分 → B 表全开(接受手工依赖 + 更重);要可扩展零策展且覆盖不输 → pure-LLM 默认。
(小样本 6 例、单次运行,方向可信不宜当终值。harness:`--branch-mode btable`;结果
`logs/downstream_btable8.json`。)
