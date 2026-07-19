# 知识库源补充 · KG 结构改善 · 检索与 root 抽取优化：规划方案

**文档类型**：规划/设计（**仅入档，暂不改项目代码**）
**撰写日期**：2026-07-02
**服务目标**：优化 **Tree-Dx** 的 **一级分支生成（BranchCreator）** 与其上游 **根节点选择（RootSelector）**、下游 **证据检索**。
**输入依据**：
- 外部设计意见 `构建临床诊断kg_20260702_2110.md`（下称「外部案」）。
- 项目文档 `CPG_RAG_EXTRACTION.md`（尤其 §13/§14/§16/§17/§18/§19）、`BRANCH_GENERATION_PHASE_REPORT.md`、`BRANCH_KNOWLEDGE_IMPLEMENTATION_PLAN.md`（IMP 编号沿用，本文新增从 **IMP-65** 起）。
- 已落盘的成品 KG/索引工件盘点（见 §2）。
- 互联网补充检索（2026-07 前沿，见 §6）。

**两条硬约束（来自用户）**：
1. **本轮先出文档，不动项目代码**；数据源补充可执行。
2. **从模拟病案抽取 KG 时，凡本项目已有同源成品 KG 且合用者，优先复用成品**，不重复抽取。

---

## 0. 一页速览（TL;DR）

外部案的核心主张是：**不要把「综合征」当主检索入口**，而应改为
**「本次就诊问题表征 EL-PR + 显著证据画像」→ 候选疾病方向优先召回（candidate-first）→ 证据文档二阶段解释 → 疾病对鉴别证据**，并对基础病异常值做 **显著性过滤**，用 **多通道配额召回** 防止罕见/危急病被常见病挤出。

对照本项目现状：
- 我们 **已有** 绝大部分底座成品（PrimeKG `kg.csv`、HPO、Orphanet、SNOMED、BODHI、`unified_symptom_disease_cache`、`Guideline_common/rare.json`、CPG/PMC/WikEM/Merck chunks、TF-IDF/MedCPT/差异化三套索引、`cant_miss_by_syndrome_wikem.json`、疾病名/发现桥接表）。**无需重下 DDXPlus/MIMIC** 即可拼出外部案的多数层次。
- 我们 **缺** 的是：把这些散件组织成 **分层诊断 KG（问题表征层 → 方向本体层 → 疾病组/illness-script 层 → 鉴别证据层）**，以及 **显著性过滤** 与 **配额化候选优先召回** 的运行时装配。
- 外部案与本项目 §16/§19 的实验结论 **相互印证**（统一检索被 PMC 淹没、候选池拥挤、罕见病被挤出），也 **纠正** 了外部案「直接上等权差异化/UNION」的乐观：本项目 §19.5/§19.6 实测等权 UNION 在 n=14 常见综合征上有害（PMC 稀释），所以差异化必须走 **配额保护 + 入口 boost**，而非等权融合。

本文给出四块规划：**A 数据源补充（复用优先）**、**B 知识库结构改善（文本→分层 KG）**、**C 检索与 root 抽取优化**、**D 三条新思路**（区别于外部案与既有算法），并落为 **IMP-65…IMP-72** 的排期与评测口径。

---

## 1. 外部案要点提炼与取舍判断

外部案是一段多轮检索式研究，结论散落在若干轮。归纳其可执行主张，并标注本项目的采纳度：

| # | 外部案主张 | 本项目判断 | 采纳度 |
|---|---|---|---|
| E1 | **综合征不宜作主检索键**；主入口应为 **EL-PR（episode-level problem representation）+ 显著证据画像** | 与 §19 「弱根标签是主要失败模式之一」一致；但本项目 root 是 **syndrome-frame**（含时相+定位+开放病因），已比裸综合征强 | **部分采纳**：保留 syndrome-frame，但**追加结构化显著证据画像 SFP 作为并行检索键**（§7.C1） |
| E2 | **一阶段召回「候选疾病/方向」而非「证据文档」**；文档 RAG 放二阶段 | 与本项目「先召回候选族、再取证据」的树式流程天然吻合；但本项目一阶段目前仍主要靠文档检索出实体 | **采纳**：显式化 candidate-first + 方向本体（§7.C2、§5.B） |
| E3 | **一阶段方向须 MECE-like**：按 病理生理机制 / 解剖系统 / 时程 / 风险层 四正交分区；每方向配 rule-in/rule-out/test/competing 证据槽；用「方向×证据矩阵」保证可分性 | 与 §2.7「轴极」、§19.5「轴可分性 0.571 偏低」高度契合；本项目缺显式方向本体与证据矩阵 | **采纳**：作为 KG 的「方向本体层」+「鉴别证据层」（§5.B2/§5.B4） |
| E4 | **多通道配额召回**（chief-complaint / phenotype / lab / imaging / rare / cannot-miss / medication / schema），每通道独立 top-k 配额，罕见与危急通道 **绕过** 常见病竞争 | 与 §16 差异化、§19.6「等权 UNION 被 PMC 稀释有害」互补：**配额** 正是修复等权稀释的关键 | **采纳（升级）**：把 §16/§19 的差异化升级为 **配额化融合**（§7.C3、§8.D-N4） |
| E5 | **显著性过滤**：每个 finding 打 `episode_related / new_or_changed / severity / specificity / explained_by_background / diagnostic_role` 六标签；基础病异常值降权为 context，不作主病因强召回 | 直接回应「无关主病因的基础病异常值」问题；本项目 **尚无** 该层 | **采纳（重点）**：新增 **Salience Filter**（§7.C1、§8.D-N2） |
| E6 | **鉴别证据层**：`disease_pair → discriminating_feature / recommended_test / rule_in / rule_out / red_flag` | 本项目有 `pathognomonic_markers.json`、`diagnostic_markers.json`、`cant_miss_*`，但 **无 disease_pair 级** 结构 | **采纳**：从 CPG/PMC-DDx/Merck 文本抽取，复用现有 chunk（§5.B4） |
| E7 | 数据源：DDXPlus / MedRAG-DDXPlus KG / MIMIC-IV-Ext-DiReCT / PrimeKG / HPO / Orphanet HOOM / PubCaseFinder / RadGraph / EPFL Guidelines / NICE CKS；技术栈 FHIR+OMOP+SNOMED/UMLS/HPO/LOINC/RxNorm + scispaCy/MedCAT + Neo4j/pgvector + hybrid | 本项目 **已有** PrimeKG/HPO/Orphanet/SNOMED/CPG/Merck/WikEM/PMC；**未下** DDXPlus/MIMIC（且 MIMIC 需授信、DDXPlus 底层 KB 专有） | **选择性采纳**：优先复用已有；DDXPlus/MedRAG-KG 作 **可选** prototype 校验；MIMIC 因授权门槛暂缓（§4） |
| E8 | 一阶段输出 **结构化方向对象**（含 supporting/opposing evidence、missing discriminators、recall_channel、coverage_checks），而非 ranked disease list | 与树式分支的 payload 可对接；利于下游二级子分支与证据检索 | **采纳**：定义为 BranchCreator 的候选 schema（§5.B2 输出格式） |

**外部案未触及、但用户点名要做的**：**root 抽取策略**（§7.C1）——外部案讨论的是「检索入口」，未直接给 RootSelector 的工程改造；本项目的 root 抽取现状与改造见 §3、§7.C1。

---

## 2. 已有成品工件盘点（复用清单）

盘点结论：**底座数据与索引基本齐备**，缺的是「组织结构」与「运行时装配」。下表按外部案的层次映射本项目现有工件（路径均在 `data/`）。**标 ★ 者为可直接复用的成品 KG，禁止重复抽取。**

| 外部案层次 | 现有可复用成品 | 位置 | 复用方式 |
|---|---|---|---|
| disease–symptom / disease–disease backbone | ★ **PrimeKG** 边表（~8.1M 行） | `knowledge_raw/kg.csv` | 直接作方向本体归族与疾病组 backbone |
| 表型标准化 / 罕见病 | ★ **HPO** 本体 + `phenotype.hpoa`；★ **Orphanet** product4/6 | `knowledge_raw/hp.obo`、`phenotype.hpoa`、`orphadata_product4/6.xml` | phenotype→disease 召回通道 |
| 症状-疾病频率/LR | ★ **unified_symptom_disease_cache**（206MB）、`lr_cache.json`、BODHI 边 | `knowledge_raw/unified_symptom_disease_cache.json`、`lr_cache.json`、`bodhi_edges_present_in.csv` | 显著性/特异性打分、finding→disease 召回 |
| 疾病知识（common/rare） | ★ **Guideline_common.json / Guideline_rare.json**（DiagRL 风格 `{disease:{symptom_list,hpo_list,icd,source}}`） | `knowledge_raw/Guideline_*.json` | illness-script 层雏形，**优先复用**替代重抽 |
| 临床术语关系 | ★ **snomed_relations.json**（finding_site/due_to/interprets…）、`snomed_concepts.json`、`snomed_term_index.json` | `knowledge_raw/snomed_*.json` | 实体归一 + 方向本体 is_a 归族（IMP-64 已用） |
| 疾病/发现别名桥 | ★ `disease_name_bridge(_flat).json`、`finding_synonym_bridge.json`、`athena_omop_synonyms.json`、`auto_ambiguity_map.json` | `knowledge_raw/*.json` | 跨源 DDx mention 归一（IMP-58/59 基础） |
| CPG/DDx 证据文本 | **cpg_chunks.jsonl**（360k）、**pmc_oa_ddx_chunks.jsonl**（318k）、**wikem_ddx_chunks.jsonl**、Merck 19e chunks、WikEM syndrome index | `cpg/processed/*.jsonl`、`corpus/merck/*.jsonl`、`cpg/api/wikem_syndrome_index_latest.jsonl` | 鉴别证据层抽取原料（`entry_type/chunk_type/syndrome_anchor` 已标） |
| 检索索引 | TF-IDF `cpg_index`(203k)、MedCPT `cpg_medcpt_index`(203k×768)、差异化 `cpg_diff_index`(分源 295k)、StatPearls+Textbooks `rag_index`(493k) | `corpus/*_index/` | 直接复用为多通道底座 |
| cannot-miss / 机制 / 标志物 | `cant_miss_by_syndrome_wikem.json`、`mechanism_to_disease.json`、`pathognomonic_markers.json`、`diagnostic_markers.json` | `knowledge_raw/*.json` | cannot-miss 通道 + 机制直提名（IMP-56/58） |
| 综合征轴/域配置 | `syndrome_axis_map.json`(11)、`auto_axis_cache*.json`、`syndrome_override_seeds.json` | `knowledge_raw/*.json` | 方向本体层的人工/半自动种子 |
| 评测集 | `branch_recall_eval_set(_hard).json`、`branch_confounder_matrix*.json` | `cpg/eval/*.json` | 新指标（direction/cannot-miss/rare recall）复用扩展 |

**缺口（须新建或补齐）**：
- `healthkg.csv` **空文件**、`bodhi_s_triples.jsonl` 空占位——非阻断，可忽略或后补。
- **无独立分层诊断 KG**（`data/kg/` 不存在）——本文 §5 的核心产物。
- **无 disease_pair 级鉴别证据**、**无显著性标签层**、**无方向本体（MECE 分区）文件**。
- **未下** DDXPlus / MIMIC-IV-Ext-DiReCT / RadGraph（外部案推荐，但本项目场景下多为可选，见 §4）。

---

## 3. root 抽取现状（两份阶段文档未记载，用户点名）

**流程位置**：`临床病例 → RootSelector（选根） → BranchCreator（建一级分支） → 二级子分支 → 证据检索`。

**现状**（代码事实）：
- `controller.select_root()`（`controller.py:897–914`）+ prompt `prompts/root_selector.txt` 驱动，**纯 LLM 自由归纳**，产出 syndrome-frame 标签（如「Acute Syncope of Uncertain Aetiology with Uncharacterised ECG Abnormality」），带 `time_course / supporting_facts / excluded_root_candidates / alarm_features / confidence`。
- prompt 已内建：**证据分级**（ECG/影像/病理 Tier1 > 病史 Tier5）、**开放病因**（不过早锁死机制）、**竞争机制登记表**（excluded_root_candidates）、**神经定位规则**、**若干专科硬规则**（新生儿多系统→代谢/遗传高优先；运动后 AMS→低钠 vs 热射病双列）。
- **候选综合征约束（`candidate_syndromes` 由 PrimeKG/HPO 提供）在设计文档 §19.3 提出但未实现**；`need_external_knowledge` 分支多为 naive stub，无结构化 KG 注入。
- **无独立 root 准确率评测**：分支/RAG 评测普遍用 **hand syndrome 标签** 绕过 RootSelector（`eval_branch_rag_recall_diagnosis.py`、`eval_branch_creator_isolated.py`）；端到端才隐含覆盖，弱根标签（case 9/13/23）是已知失败源。

**判断**：现有 syndrome-frame 已相当接近外部案 EL-PR 的「主问题锚点 + 语义限定词」两类信息，但**缺三样**：(a) **显著阳性/阴性证据画像（SFP）** 的结构化并行表达；(b) **基础病异常值的显著性降权**；(c) **KG 锚定的候选综合征/方向约束 + 独立评测**。这三样正是 §7.C1 的改造重点。

---

## 4. 数据源补充策略（复用优先，可执行）

遵循用户约束「已有成品优先复用」。分三档：

### 4.1 已有，直接复用（不新增下载）
PrimeKG、HPO(+hpoa)、Orphanet(product4/6)、MONDO、SNOMED 关系/概念、BODHI、`unified_symptom_disease_cache`、`Guideline_common/rare`、CPG/PMC/WikEM/Merck chunks、三套索引、cant-miss/机制/标志物表、疾病名桥。→ 覆盖外部案的 backbone / 罕见病 / 症状-疾病 / 指南证据 / 术语标准化五层的绝大部分。

### 4.2 建议补充（低门槛、开放许可、边际收益明确）
| 源 | 用途 | 许可 | 优先级 | 备注 |
|---|---|---|---|---|
| **NICE CKS / Syndication 全库** | primary-care「presentation→DDx」方向补全 | 需 API-Key（项目已有凭据路径） | P1 | 承接 IMP-30/30b 未完成部分 |
| **198 篇 bot_blocked 全文补拉**（Europe PMC / BioC / 出版商） | 修复 §CPG bot-gate 缺口 | 开放 | P2 | 承接既有 TODO |
| **MedRAG 发布的 DDXPlus diagnostic KG（xlsx）** | 作 **prototype 校验**：`manifestation→candidate→DDx→distinguishing`；与我们自建方向本体做覆盖对照 | GitHub 可取；底层合成 | P2（可选） | **不作生产主源**；仅复用其成品 KG 做上界对照，符合「复用成品」原则 |

### 4.3 暂缓（门槛/收益不匹配）
- **MIMIC-IV-ED / -Note / -Ext-DiReCT**：需 PhysioNet 授信 + DUA，且本项目评测集是 medbullets/教科书综合征+罕见病，真实 EHR 分布收益在当前阶段不显著。**暂缓**，列为「临床级增强版本」备选。
- **RadGraph / RadGraph-XL**：影像结构化抽取，仅当引入影像文本病例时才需要。**暂缓**。
- UMLS/SNOMED CT 全量、LOINC/RxNorm：术语许可复杂；当前 `snomed_*`/`athena_omop_synonyms` 已够用。**按需**。

> **模拟病案抽取 KG 的复用红线**：若需从 medbullets/StatPearls/案例文本抽 disease–symptom / illness-script，**先查** `Guideline_common/rare.json`、`unified_symptom_disease_cache`、`lr_cache`、PrimeKG 是否已含该疾病条目；命中则复用，仅对**缺失条目**做增量 LLM 抽取并接地核验（IMP-11 门），避免重复造轮子。

---

## 5. Part B｜知识库结构改善：文本 → 分层诊断 KG

**目标产物**：新建 `data/kg/`（当前不存在），承载一张 **四层诊断 KG**，把散件（§2）与文本抽取（CPG/PMC/Merck）组织为可检索、可归族、可鉴别的结构。层次直接映射外部案 §7/§9 与本项目 §2.7 轴极、§19.5 轴可分性。

```text
Layer 0  证据/术语标准化层（复用现有桥接）
   finding/symptom/lab/imaging/disease  →  SNOMED/HPO/MONDO/PrimeKG id + 别名
        ↓
Layer 1  问题表征层 EL-PR / chief-problem 模板
   chief_problem(胸痛/呼吸困难/发热/腹痛/AMS/晕厥…) + semantic_qualifiers
        ↓
Layer 2  方向本体层（MECE-like，四正交分区）
   direction = {system, mechanism, time_course, risk_tier}
   + residual buckets（other/multisystem/iatrogenic/artifact…）
   + cannot-miss guardrails
        ↓
Layer 3  疾病组 / illness-script 层
   direction → disease_group → disease(illness_script: 流行病学/时程/关键征/检查)
        ↓
Layer 4  鉴别证据层
   disease_pair → {rule_in, rule_out, discriminating_test, red_flag}
   direction × evidence 矩阵（support/oppose/required/cannot-miss）
```

### 5.1 Layer 0：证据/术语标准化（复用为主）
- 直接用 `snomed_term_index.json` + `disease_name_bridge.json` + `finding_synonym_bridge.json` 做 mention→id 归一（IMP-58/59 已具雏形）。
- **新增**：`salience` 字段占位（见 §7.C1），供 Layer 1 消费。

### 5.2 Layer 1：问题表征层（半自建）
- 以 `syndrome_axis_map.json`(11) + WikEM syndrome index(147) + PMC/Merck 的 `syndrome_anchor` 为种子，抽取 **高频 chief-problem 模板**（外部案 Step1 清单：chest pain / dyspnea / fever / abdominal pain / headache / AMS / syncope / weakness / jaundice / edema / AKI / anemia / rash / seizure / back pain…）。
- 每模板挂 `semantic_qualifiers`（acute/subacute/chronic, focal/diffuse, exertional/pleuritic…）。
- **输出格式（BranchCreator 候选对象，采纳 E8）**：
```json
{
  "problem_representation": "acute hypoxemic dyspnea with tachycardia and clear CXR",
  "directions": [{
    "direction": "pulmonary vascular acute process",
    "coverage_role": "primary_candidate|competing|long_tail_guard|cannot_miss",
    "system": "pulmonary", "mechanism": "vascular",
    "time_course": "acute", "risk_tier": "cannot_miss",
    "supporting_evidence": ["hypoxemia","tachycardia","clear CXR"],
    "opposing_evidence": [],
    "missing_discriminators": ["CTPA","D-dimer context","leg US"],
    "candidate_disease_groups": ["pulmonary embolism spectrum"],
    "recall_channel": ["chief_problem","imaging_pattern","cannot_miss"]
  }],
  "coverage_checks": {"cannot_miss_present": true, "rare_channel_present": true,
                      "artifact_channel_present": true, "baseline_downweighted": true}
}
```

### 5.3 Layer 2：方向本体层（核心新建，复用 PrimeKG/SNOMED 归族）
- 每方向是 tuple `{system, mechanism, time_course, risk_tier}`（外部案四分区）；疾病可多标签，但每 episode 必须指定 **primary direction**（对应本项目「主分类轴」单轴原则，§2）。
- **归族复用**：用 PrimeKG `disease_disease` + SNOMED `is_a` 把疾病聚到 direction/disease_group（IMP-64 的本体反向归族已验证可提升轴可分性 0.571→0.643，此处系统化）。
- **残差桶 + cannot-miss guardrail**：残差桶保证完备性；cannot-miss 由 `cant_miss_by_syndrome_wikem.json` 扩展（当前只覆盖症状类，须补 lab/endocrine，呼应 IMP-60 未激活缺口）。

### 5.4 Layer 4：鉴别证据层（文本抽取，接地核验）
- 从 `pmc_oa_ddx_chunks`(318k, chunk_type=differential) + WikEM DDx + Merck「approach-to」章节抽取 `disease_pair → {rule_in/rule_out/test/red_flag}`。
- **抽取手段**：spotter+LLM grounded（IMP-63 已证为最大 flat 召回杠杆 A5=0.768），**实体须逐字命中片段**（IMP-11 门）+ citation。
- **direction×evidence 矩阵**：按 chief-problem 汇总，落为可用于「证据可分性」判据的稀疏矩阵（外部案 §4.1）。

> **复用红线再申**：Layer 3 illness-script 优先从 `Guideline_common/rare.json` + `unified_symptom_disease_cache` 直接投影；仅缺失疾病走增量抽取。

---

## 6. 互联网前沿补充（2026-07）与对本项目的启示

| 来源 | 结论 | 对本项目启示 |
|---|---|---|
| **When Does Retrieval Beat Direct LLM Diagnosis in Rare Disease**（BioNLP 2026, 10,382 例/7 基准） | 存在 **coverage 驱动的交叉点**：真金标在检索器 top-50 内（高覆盖）时本体检索占优；低覆盖时开放式 LLM 占优；加 LLM reranker 可补大部分差距；本体检索两大结构性失败＝**注释稀疏 + 表型同质** | 支持 **coverage-aware 路由**（§8.D-N3）：按病例可召回性动态在「检索召回」与「LLM/机制提名」间切换——与本项目 §19「c1 机制/eponym 鸿沟检索不可达」实测一致 |
| **DeepRare**（Nature 2025） | 三层 agent + 自反思闭环；case-searcher 把病例库编码为 **HPO 列表相似匹配**；带可溯证据链 | 我们已有 HPO/Orphanet：可低成本加一个 **HPO-profile 罕见病召回通道**（§7.C3 rare channel），复用 `hpo_symptom_disease.json` |
| **MedKGI / MedClarify**（2025–2026） | **信息增益（DEIG）** 选最具区分力的问题/检查；KG 约束防幻觉；OSCE 结构化状态跟踪 | 迁移到 **检索/分支**：用「期望区分力」选 **能最大程度分离当前候选方向的证据块/查询**（§8.D-N1），而非纯相似度——这是区别于外部案「配额」与既有「RRF hybrid」的新算子 |
| **AutoRD / GEN-KnowRD**（2024–2026） | ontology-enhanced LLM 从文本抽罕见病 KG；LLM 构建可复用、机器可读的结构化 RDK 层 | 支撑 §5.4 的「文本→鉴别证据层」抽取路线与接地核验；GEN-KnowRD 的「先约束候选空间再评估」印证 §7.C1 的 KG 锚定候选 |

---

## 7. Part C｜检索与 root 抽取优化

### C1. root 抽取：syndrome-frame + 显著证据画像（SFP）双表征 + KG 锚定候选
**问题**：现 root 为单一 LLM 文本标签，缺结构化证据画像与基础病降权，且无 KG 候选约束/独立评测。

**改造设计（分三步，均先文档定义）**：
1. **并行产出 SFP（Salient Findings Profile）**：在 RootSelector 阶段，除 syndrome-frame 文本外，产出结构化对象：
   ```json
   {"chief_problem":"...", "semantic_qualifiers":[...],
    "salient_positive":[...], "salient_negative":[...],
    "context_priors":[...], "background_abnormalities":[
      {"finding":"chronically_elevated_creatinine","status":"baseline_abnormality",
       "diagnostic_role":"context_modifier","retrieval_weight":"low_for_primary"}]}
   ```
2. **Salience Filter（显著性过滤，采纳 E5）**：对每个 finding 打六标签 `episode_related/new_or_changed/severity/specificity/explained_by_background/diagnostic_role`。判据：`显著证据 = abnormal ∧ new/changed ∧ temporally_aligned ∧ mechanistically_coherent ∧ severity_sufficient`。打分复用 `lr_cache`/`unified_symptom_disease_cache`（特异性/LR）+ SNOMED `due_to` 关系（机制一致性）。基础病异常值降为 context，不进主病因强召回。
3. **KG 锚定候选综合征（落地 §19.3 未实现项）**：用 SFP 的显著阳性 findings 经 HPO/PrimeKG 反查 `candidate_syndromes`，作为 **软约束** 注入 RootSelector prompt（不锁死，仅提示竞争机制），降低弱根标签率。
4. **独立评测**：新增 root 准确率口径（见 §9），不再一律用 hand 标签绕过。

### C2. Candidate-first 两阶段化（采纳 E2）
- **一阶段**：EL-PR/SFP → **方向本体层（Layer 2）** 召回 direction+disease_group（不排最终名次，保覆盖）。
- **二阶段**：对每个候选 direction/disease 做 **candidate-specific RAG**（文档检索取证），复用现有索引；再走 **Layer 4 疾病对鉴别证据**。
- 与现树式流程对接：一阶段=BranchCreator 的 L1 方向；二阶段=证据检索与 LR 调整。

### C3. 多通道配额召回（采纳 E4，修复 §19.6 等权稀释）
在现有索引之上装配 **8 通道**，每通道独立 top-k 配额，**罕见/cannot-miss 通道绕过常见病竞争**：

| 通道 | 复用工件 | 配额建议 |
|---|---|---|
| chief-problem / 常见 ED | `cpg_diff_index`(wikem/merck) + `syndrome_axis_map` | 20 |
| phenotype（HPO-SNOMED） | `hpo_symptom_disease.json` + `unified_cache` | 30 |
| lab-pattern | `unified_cache` / `lr_cache` | 15 |
| imaging-pattern | PMC/Merck 影像段（暂用文本） | 15 |
| **rare（HPO/Orphanet）** | `orphadata_*` + `Guideline_rare.json` + DeepRare 式 HPO 相似 | 25（独立索引） |
| **cannot-miss** | `cant_miss_by_syndrome_wikem.json`（须扩 lab/endocrine） | 15（强制保留） |
| medication/exposure | `mechanism_to_disease.json` + 药物史 | 10 |
| guideline-schema | `cpg_index` / PMC-DDx | 10 |

- **融合＝配额化 RRF/UNION**：先各通道 top-k 入池（保底），再统一 rerank。这修复了 §19.5/§19.6「等权 UNION 被 PMC 稀释、n=14 掉到 0.235/0.307」的问题——**问题不在差异化本身，而在等权无配额**。
- **多样性约束**：同一 pathophysiologic group ≤ N、每 organ system ≥ M、rare ≥ R、cannot-miss 强制（外部案 §3.3）。

### C4. Coverage-aware 路由（新，见 §8.D-N3）
按 BioNLP 2026 结论，估计本病例 **检索覆盖度**（金标在 top-50 概率的代理指标），低覆盖时切到 **LLM/机制直提名**（IMP-58 已有）与 rare-channel；高覆盖时以本体检索为主。

---

## 8. Part D｜三条新思路（区别于外部案与既有算法）

> 外部案 = 「配额 + 显著性过滤 + 分层 KG」；既有算法 = 「RRF hybrid（IMP-53）+ 差异化/锚点 UNION（IMP-61/61b）+ 机制提名（IMP-58）+ 本体归族（IMP-64）」。下述三条均不与之重复。

### D-N1. 区分力最大化检索（Discrimination-Maximizing Retrieval, DMR）
**思想**：把 MedKGI/MedClarify 的 **期望信息增益（DEIG）** 从「选下一个问题」迁移到 **「选召回块 / 构造查询」**。不再仅按「与病例相似」召回，而按「**该块/查询能最大程度分离当前候选方向**」召回。
- 形式：给定当前 direction 分布 `P(d)`，对候选块 `c` 估计 `IG(c) = H(P) − E[H(P | c)]`，用 Layer 4 的 direction×evidence 矩阵近似 `P(d|c)`。取 IG 高者进入二阶段取证。
- **与既有区别**：RRF/差异化解决「召回什么源」，DMR 解决「召回什么最能鉴别」；这是 **判别式检索目标**，此前项目/外部案均按相似度或配额，不按信息增益。
- **落点**：二阶段 candidate-specific RAG 的块排序、以及「missing_discriminators」的主动取证建议。

### D-N2. 显著性门控查询（Salience-Gated Query, SGQ）
**思想**：把 §7.C1 的显著性过滤 **前置到查询构造**——基础病异常值在 **进索引前** 就按 `retrieval_weight` 降权/剔除，避免噪声 finding 污染 top-k。
- 形式：查询 = `Σ w_i · term_i`，`w_i` 由 salience 六标签 + `lr_cache` 特异性联合决定；`explained_by_background=true ∧ new_or_changed=false` 的项 `w→0`（仅保留于 context/risk 通道）。
- **与既有区别**：项目现有查询构造（`_build_queries`、fanout IMP-52）不区分「主病因证据 vs 基础病噪声」；SGQ 显式建模用户提出的「无关主病因的基础病异常值」。

### D-N3. 覆盖度感知的检索/生成混合门（Coverage-Aware Gate, CAG）
**思想**：按 BioNLP 2026「coverage 交叉点」，**逐病例** 决定用检索召回还是 LLM/机制提名主导。
- 形式：训练/标定一个轻量 `coverage_score`（基于 SFP 命中索引的密度、罕见度、eponym 触发等），低于阈值→提升 rare-channel + IMP-58 机制提名权重并触发 LLM grounded nomination；高于阈值→本体检索主导。
- **与既有区别**：项目现固定管道；CAG 是 **自适应路由**，直接回应本项目 §19「c1 检索不可达（机制/eponym 鸿沟）」——对这类病例自动绕开注定失败的相似度检索。

---

## 9. 评测口径（新增，先定义后实现）
一阶段 **不看 top-1 准确率**，看覆盖类指标（外部案 §2.4 + 本项目 §19 对齐）：
- `direction_recall@K`（目标 ≥ 0.98）、`disease_group_recall@K`
- `critical_miss_recall@K`（目标 = 1.00）
- `rare_channel_recall@K`（**独立** 评估，防被常见病挤出）
- `coverage_by_organ_system` / `coverage_by_mechanism`（完备性）
- `axis_separability`（轴可分性，承接 §19.5 的 0.571 基线）
- **root 独立指标**：`root_frame_quality`（是否含 ≥2 类信息、是否开放病因、竞争机制登记完整度）、弱根标签率
- 回归集：`branch_recall_eval_set(_hard)` + medbullets + 罕见 8 题 + `cant_miss` 对抗集 + 基础病噪声对抗集。

---

## 10. 路线图与 IMP 编号（P0 优先、复用优先、暂不写码）

| IMP | 任务 | 依赖 | 优先级 | 复用 | 产物 |
|---|---|---|---|---|---|
| **IMP-65** | 定义并入档 **分层诊断 KG schema**（Layer0-4）+ `data/kg/` 目录规范 | — | **P0** | §2 全部工件 | 本文 §5 + schema.json 规范（文档） |
| **IMP-66** | **Salience Filter** 规格：六标签 + 打分（复用 lr_cache/unified/SNOMED due_to） | IMP-65 | **P0** | ★ 现有缓存 | 规格文档 + 标签枚举 |
| **IMP-67** | **RootSelector 双表征**：SFP 结构化输出 + KG 锚定 `candidate_syndromes`（落地 §19.3）+ root 独立评测口径 | IMP-66 | **P0** | HPO/PrimeKG | prompt/协议草案（不改码） |
| **IMP-68** | **方向本体层（Layer2）** 构建：四分区 tuple + PrimeKG/SNOMED 归族 + 残差桶 + cannot-miss 扩 lab/endocrine | IMP-65 | P1 | ★ PrimeKG/SNOMED/cant_miss | direction_ontology.json 规范 |
| **IMP-69** | **Layer4 鉴别证据抽取**：disease_pair→{rule_in/out/test/red_flag} + direction×evidence 矩阵（spotter+LLM grounded, IMP-11 门） | IMP-68 | P1 | ★ PMC-DDx/WikEM/Merck chunks | 抽取规格 + 矩阵格式 |
| **IMP-70** | **配额化多通道召回** 规格（8 通道+配额+多样性约束），修复等权稀释 | IMP-68 | P1 | ★ 三套索引/HPO/Orphanet | 融合算法伪码（文档） |
| **IMP-71（新）** | **DMR** 区分力最大化检索规格（DEIG 迁移到块/查询选择） | IMP-69 | P2 | Layer4 矩阵 | 算法规格 |
| **IMP-72（新）** | **CAG** 覆盖度感知门 + **SGQ** 显著性门控查询 规格 | IMP-66,70 | P2 | IMP-58/lr_cache | 算法规格 + 阈值标定方案 |
| （数据） | NICE Syndication 全库、198 篇 bot_blocked 补拉、（可选）MedRAG-DDXPlus KG 对照 | — | P1/P2 | — | 承接既有 TODO |

**实操顺序**：IMP-65（schema）→ IMP-66（salience）→ IMP-67（root 双表征，最大痛点）→ IMP-68/69（KG 结构）→ IMP-70（配额召回）→ IMP-71/72（新算子）。**本轮仅产出上述规格文档**；编码待用户放行。

---

## 11. 与既有结论的一致性与纠偏
- **一致**：外部案「统一检索淹没入口」＝本项目 §16 缺陷验证（WikEM Recall@10 0.659、PMC 占比 0.51）；外部案「候选池被常见病挤占」＝§2.6「候选池拥挤」实锤。
- **纠偏**：外部案倾向直接上「差异化/等权 UNION」；本项目 §19.5/§19.6 实测等权 UNION 在常见综合征上 **有害**（PMC 稀释，掉到 0.235/0.307）。→ 本方案坚持 **配额保护 + 入口 boost + candidate-first**，而非等权融合（§7.C3、§8.D-N4→并入 IMP-70）。
- **补强**：外部案未给 root 抽取工程；本方案以 §7.C1 双表征 + §3 现状为基础补齐，并新增 §8 三条判别式/自适应算子作为项目独有增量。

---

*（本文为规划入档，未改动任何项目代码；数据源补充与后续编码待用户确认放行。）*
