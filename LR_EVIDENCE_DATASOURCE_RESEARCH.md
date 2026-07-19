# LR 计算 / 证据选择 / 证据标注协同 — 数据源调研

> **调研日期**：2026-07-07  
> **触发问题**：当前 LR 计算和证据选择依赖哪些数据源？证据标注器如何利用 LLM 和外部知识协同？错误 LR 主要源于数据源还是 LLM？新增 CPG / Case report 能否弥补缺陷？  
> **方法**：代码走查（`dx_feature_retriever` / `controller` / `lr_quant` / `finding_normalizer` 等）+ 阅读外部方案 [`构建临床诊断kg_20260702_2110.md`](构建临床诊断kg_20260702_2110.md) + 联网检索 MedKGI / Dual-Inf / NICE RAG grounding 等最新研究。  
> **来源会话**：`d6e23c24-82b3-4786-a36b-03356b21f410`（transcript 行 4323–4337）。  
> **后续深化**：量化探针 + 9 题实证 + 算法缺陷 A1–A14 见 [`EVIDENCE_ANNOTATION_LR_DEFECTS_RESEARCH.md`](EVIDENCE_ANNOTATION_LR_DEFECTS_RESEARCH.md)。

---

## 0. 原始调研问题

> 当前 LR 计算和证据选择依赖哪些数据源？证据标注器如何利用 LLM 和外部知识协同工作？协同流程是什么样的？LLM 在标注时产生的错误 LR，其问题主要源于数据源提供的错误知识还是 LLM 本身的问题？当前 CPG 和 Case report 数据已经新增，可能可以弥补之前在证据选择和 LR 标定使用的数据源的缺陷吗？可能缓解 LLM 无法正确标注的问题吗？另外，查阅互联网并阅读 `构建临床诊断kg_20260702_2110.md` 这个外部方案，借鉴这些资源，进行详细调研。

---

## 1. LR 计算与证据选择依赖的数据源

LR 查找是一条**分层级联**，从确定性高的手工/结构化源到不确定的文本检索源逐级回退（`dx_feature_retriever.py:491` 的 `get_lr_reference`）：

| 层级 | 数据源 | 文件 / 索引 | 性质 |
|---|---|---|---|
| **Layer 0**（最高优先） | pathognomonic / 诊断标志物 / 基因关联 | `pathognomonic_markers.json`（手工策展 ~24 条）、`diagnostic_markers.json`（Orphadata 派生）、PrimeKG 基因边 | 高可信、有 LR+ 注释 |
| **Layer 2**（主力） | 统一症状-疾病频率缓存 | `unified_symptom_disease_cache.json` | 由 GetTheDiagnosis（精确 LR±）、HPO、Orphadata、HealthKG、BODHI、docLogica 合并（`build_unified_cache.py`） |
| **Layer 2 辅助** | 同义桥 / HPO 本体 / 嵌入兜底 | `finding_synonym_bridge.json`、`disease_name_bridge_flat.json`、`hp.obo` + `hpo_embeddings.npy`、SNOMED 三件套 | 模糊匹配、上位衰减、同概念提升 |
| **数值归一化** | 化验/生命体征参考范围 | `lab_reference_ranges.json`、`loinc2hpo_annotations.json`、`unit_conversions.json`（`finding_normalizer.py`） | 数值→方向感知 HPO 术语；正常值产出 `negated_hpo_terms` 供 LR− 通道 |
| **Layer 3a**（可选，**默认关**） | RAG 检索 + 定量抽取 | `rag_index`（StatPearls + Textbooks，FAISS）+ `rag_lr_secondary_cache*.json` | 文本片段 → `lr_quant.quantify_snippet` 现算 Sn/Sp/LR |
| **Layer 3b**（可选） | PubMed 兜底 | 在线 NCBI E-utilities | 同上 |
| **Layer 2-hop** | PrimeKG 链式条件概率 | `kg.csv` | 间接推断 |

**关键配置**：

- 主 pipeline 默认 `enable_lr_rag_fallback=False`（`config.py:82`）——只走 marker 表 + unified cache + 2-hop，不做文本检索抽取；评测脚本可显式打开 RAG。
- `age_sex_incidence.json` 走**先验修正**（`PriorModifier`），**不进** finding→LR 通道。
- `rag_lr_can_override_direction=False`（`config.py:373`，默认）——RAG 来源 LR 只能作 prompt 参考，**不能**覆盖 LLM 方向、不进 rule-out。

### 1.1 各模块职责速查

| 模块 | 路径 | 职责 |
|---|---|---|
| `DxFeatureRetriever.get_lr_reference` | `knowledge/dx_feature_retriever.py:491` | LR 级联入口 |
| `format_lr_reference_for_prompt` | 同上 | 渲染 prompt 可读 LR 参考行 |
| `LRRetriever.lookup_fuzzy` | `knowledge/lr_retriever.py` | unified cache 模糊/嵌入匹配 |
| `quantify_snippet` / `purify_entry` | `knowledge/lr_quant.py` | RAG 文本→Sn/Sp/LR；provenance 净化 |
| `FindingNormalizer` | `knowledge/finding_normalizer.py` | 数值化验→方向感知 HPO |
| `SecondaryLRCache` | `knowledge/secondary_lr_cache.py` | RAG 二级缓存持久化 |
| `DiagnosticMarkerIndex` | `knowledge/diagnostic_marker_index.py` | Layer 0 marker 表 |

### 1.2 CPG / Case report 与 LR 路径的关系（现状）

| 索引 | 当前用途 | 是否进入 LR 路径 |
|---|---|---|
| `cpg_index` | `GuidelineBranchSource` — **分支创建召回**（默认 OFF） | **否** |
| `case_report_index` | `CaseReportBranchSource` — **分支创建召回**（默认 OFF） | **否** |
| `rag_index_dir` | StatPearls + Textbooks（+ 部分 CPG chunk） | **是**（Layer 3a，默认关） |

CPG chunk 已按 `differential` / `red_flag` / `evaluation` / `diagnostic` 分类（`build_cpg_chunks.py`），但**只存文本，未抽取结构化 Sn/Sp/LR**。

---

## 2. 证据标注器：LLM + 外部知识协同流程

每一轮证据的完整协同流程（`controller.py`）：

```
证据文本
 └─ _raw_atomic_facts (2428)              取本轮结构化证据 / 结果摘要
 └─ _gather_atomic_findings (2527)        FindingNormalizer 归一化 + 嵌入匹配表型；跳过人口学/否定句
     ↓ atomic findings
 └─ _build_annotator_payload (2183)      对每个 finding 调 format_lr_reference_for_prompt
     ↓                                      → 注入 lr_reference（≤4000 字）
     ↓                                      → 可选 pivotal_evidence_hint（LR+≥5，2265）
 └─ EvidenceAnnotator (LLM)              prompts/evidence_annotator.txt
     ↓                                      → branch_effects 七档定性
 └─ _reconcile_annotation_with_kb (2676)  再查 KB → _kb_entry_to_signal
     ↓                                      → 高置信 KB 覆盖 LLM 方向
     ↓                                      → 产出 branch_lr / pathognomonic floor
 └─ apply_probability_update (3018)      bayesian_lr_update 或 ordinal_update
                                           (+ enable_discrimination_gate 冻结全弱轮)
```

**分工**：

- **LLM**：语义判断「这条证据支持/反对哪个分支、强度多少」。
- **外部知识**：
  - **(a) 注入锚点**（LLM 之前）——降低 LLM 自创 LR 的空间；
  - **(b) 事后机械纠偏**（LLM 之后）——方向覆盖 + 数值 LR + LR− rule-out。

**七档定性标签 ↔ EBM LR 区间**（prompt 约定）：

| 标签 | 近似 LR 区间 |
|---|---|
| `strong_for` | LR+ ≥ 5 |
| `moderate_for` | LR+ 2–5 |
| `weak_for` | LR+ 1–2 |
| `neutral` | ~1 |
| `weak_against` | LR− 0.5–1 |
| `moderate_against` | LR− 0.2–0.5 |
| `strong_against` | LR− ≤ 0.2 |

---

## 3. 错误 LR 的根因：数据源 vs LLM

**结论：两者都有，但代码中的防护绝大多数针对「数据源侧错误」，说明历史上主要问题源在数据源，而非 LLM 幻觉。**

### 3.1 数据源侧（防护最重）

| 缺陷模式 | 机制 | 典型后果 |
|---|---|---|
| **伪造特异度** | cache/RAG 抽取时若只有 Sn 没有 Sp，默认填 `_DEFAULT_SP=0.85`（`lr_quant.py:67`） | 低 Sn × 伪造 0.85 → **虚假强排除 LR**（头号 bug，`lr_quant.py:79-85`） |
| **百分比抓错** | `pct` 通道抓关键词范围内**任意百分比**（常是死亡率/患病率/样本量）误当敏感度 | 伪 LR+ / LR− |
| **频率→LR 伪标定** | Orphadata 等只有频率标签（`phrase:frequent_low` 等）被硬映射到 LR 桶 | 43% 缓存条目无真实 Sn/Sp（见深化报告 §3） |

> **⚠️ 2026-07-08 修订（重要）**：上表「频率→LR 伪标定」的定性需**收窄**。根因不在频率数据本身，而在 `build_unified_cache.build_entry` 把频率当 `sensitivity` 再补默认 `Sp=0.85`。按 **LIRICAL 范式**（`LR(h|D)=P(h|D)/背景频率`，分母用跨疾病背景而非伪 Sp）重算，本地 `phenotype.hpoa` 的 264,245 条频率记录（80.1% 带显式频率）就是**合法表型 LR**（Kayser-Fleischer→Wilson LR≈3434 已实测）。详见 [`LR_QUANT_FEASIBILITY_VERDICT.md`](LR_QUANT_FEASIBILITY_VERDICT.md) §8。故 §7 中"频率桶降级为 context-only"应改为"按 LIRICAL 范式重算为表型 LR"。
| **非临床 finding 量化** | 人口学/正常体检/非特异症状被 `quantify_snippet` 强行算 LR | case 17 类「Age: 57 years → LR−=0.012」灾难 |

**已有防护（均为数据源质量补丁）**：

- `neutralize_entry` — 把伪造排除 clamp 到 [0.5, 2.0]
- `purify_entry` — 剥离无 `explicit:` 依据的数值（`lr_quant.py:166`）
- 正则解析 hardening + controller LR 注入 `continue`（单条 bad finding 不再拖垮整轮）

detox 实验曾「扰动脆弱平衡反而 −13.3pp」，说明启发式源本身噪声极大（二级缓存仅 ~0.13% 是显式依据）。

### 3.2 LLM 侧（次要，已有纠偏机制）

- **方向标反**（如把某升高标志物标成支持错误分支）、**锚定常见诊断**。
- 靠 `enable_kb_direction_reconciliation` 事后覆盖 + anti-anchoring 中性提示纠偏。
- 联网研究印证：LLM 做「从疾病反推代表症状 / 给证据定强度」时，**对内部医学知识的依赖使其易受严重幻觉影响**：
  - **Dual-Inf**（Nature）：把 backward-inference 的幻觉列为主要失败源；
  - **MedKGI**：把「弱知识锚定导致幻觉内容」列为 LLM 诊断三大缺陷之首。

### 3.3 判断

错误 LR **主要源于数据源提供的错误/伪造知识**（尤其 unified cache 与 RAG 抽取里的伪造特异度和 pct 误读）；LLM 方向性错误是**次要**且已有纠偏机制。这也解释了为什么默认关掉 RAG fallback——那条路引入的噪声常大于收益。

---

## 4. 新增 CPG / Case report 能否弥补？

**结论：目前它们完全没有接入 LR/证据标注路径；即使接入也不能直接解决定量 LR 问题，反而可能重蹈覆辙——但用对方式可以带来实质增益。**

### 4.1 能弥补的部分

| 缺口 | CPG / Case report 可提供的 | 预期增益 |
|---|---|---|
| **证据选择 / 召回** | CPG `red_flag` / `differential` chunk；case report 的确诊-鉴别对 | 显著证据画像、长尾召回（RareArena 实验已证召回层有效） |
| **鉴别依据缺失** | 带方向的「支持/排除/红旗」关系 | 减少 LLM 方向标反（定性锚点） |
| **分支覆盖** | `GuidelineBranchSource` / `CaseReportBranchSource` | 防漏关键 L1 方向（与 LR 路径独立） |

### 4.2 不能直接解决的部分

| 风险 | 原因 |
|---|---|
| **定量 LR 标定** | `extract_lr_from_snippets` → `quantify_snippet` 是**索引无关**的；指向 CPG/case report 会遇到完全相同的伪造 Sp / pct 误读 |
| **Case report 量化** | 单个病例报告的频率描述**不具备群体统计意义**；直接量化成 LR 会制造更多伪证据 |
| **faithfulness ≠ LR 正确性** | NICE RAG 把 faithfulness 从 43% 提到 99.5%，提升的是「忠实于来源文本」，**不等于**提升定量 LR 的正确性 |

### 4.3 间接帮助 LLM 误标

若把 CPG 的鉴别/红旗 chunk 作为**定性方向锚点**（而非定量 LR）注入 prompt，能减少 LLM 方向标反——与 RAG grounding 研究一致（放射指南 RAG 把幻觉从「routinely」降到 3/79）。

---

## 5. 借鉴外部方案与联网研究

外部 KG 方案（[`构建临床诊断kg_20260702_2110.md`](构建临床诊断kg_20260702_2110.md)）与最新论文高度收敛于同一批设计原则：

### 5.1 把「共现」和「鉴别依据」分开建模

外部文档 §1、§5 第四层明确警告：**临床 KG 最危险的错误是把共现关系误当诊断依据**——这正是 unified cache 伪造特异度问题的本质。

应建 `finding_discriminates_for/against`、`red_flag_for`、`diagnostic_criterion` 这类**带方向的鉴别边**，而不是频率共现。CPG/case report 新语料恰好适合抽这类边。

### 5.2 provenance + 证据分级是强制项

外部文档 §5 第五层：每条 LR/鉴别关系应带来源、证据等级、抽取模型、人工审核状态。

本项目 `provenance` 字段已有（`explicit:*` / `pct:*` / `phrase:*`），建议做**硬门控**：

> **只有 `explicit:`（真实报告的 Sn+Sp）才允许进数值 LR 通道；其余降级为定性方向锚点。**

这其实就是 `purify_entry` 的思路，建议设为默认。

### 5.3 salience filtering（显著证据画像）

外部文档 §6：给每个 finding 打 6 标签（`episode_related` / `new_or_changed` / `severity` / `specificity` / `explained_by_background` / `diagnostic_role`），把慢性基础病异常值降权为 background/noise。

本项目已有 `is_nondiscriminative_finding` 雏形，但只覆盖人口学/正常值，可扩展到「慢性基线异常」。

### 5.4 KG 锚定 + 信息增益（而非自由生成 LR）

MedKGI / medIKAL / Dual-Inf 的共识：

- 让 KG 约束推理到已验证本体；
- 用**双向验证**（正推诊断→反推症状→核验）替代让 LLM 直接给 LR。

本项目的 `_reconcile_annotation_with_kb` 已是雏形，可借鉴 Dual-Inf 的「反推代表症状再核验」加强方向纠偏，用 medIKAL 的「KG 交叉验证提高对 LLM 幻觉的容错」。

### 5.5 联网研究要点

| 来源 | 核心启示 | 对本项目的映射 |
|---|---|---|
| **MedKGI** | PrimeKG + information gain 迭代鉴别；弱 KG 锚定→幻觉 | 分支 KB recall hints / syndrome axis |
| **Dual-Inf**（Nature） | backward-inference 幻觉是主失败源 | `_reconcile` 双向核验 |
| **medIKAL** | KG 交叉验证提高对 LLM 幻觉容错 | KB 覆盖 LLM 方向 |
| **NICE RAG grounding** | faithfulness 43%→99.5% | CPG 作定性锚点，非定量 LR |
| **GARMLE-G**（arXiv 2506.21615） | 直接检索权威指南、不依赖模型生成 | GuidelineBranchSource 范式 |
| **RAG DDx** | 主诊断 54%→78%，≥1 正确鉴别 92%→98% | 召回层 A/B 已验证方向 |

---

## 6. 一句话建议

新增的 CPG/case report 应作为**定性鉴别证据层**（抽 `discriminates_for/against`、`red_flag` 带 provenance 的边，注入 prompt 做方向锚定）接入证据标注，而**不要**当作定量 LR 源直接喂 `quantify_snippet`。

定量 LR 通道应收紧到只信 `explicit:` 依据。这样能弥补「证据选择/鉴别依据缺失」和「LLM 方向标反」，但「精确 LR 数值标定」仍需依赖 GetTheDiagnosis 这类真实统计源，不能指望从叙述性文本里可靠地算出来。

---

## 7. 建议改造方向（概要，待单独方案）

| 优先级 | 改造项 | 说明 |
|---|---|---|
| **P0** | provenance 硬门控默认开启 | `purify_entry` 生产默认；~~`orphanet_rare` 频率桶降级为 context-only~~ → **改：频率桶按 LIRICAL 范式重算为表型 LR**（见 [`LR_QUANT_FEASIBILITY_VERDICT.md`](LR_QUANT_FEASIBILITY_VERDICT.md) §8.5） |
| **P0** | pathognomonic 语义判定 | LR+ ≥ 阈值 → posterior floor，不限于 `confidence=="pathognomonic"` |
| **P1** | CPG 定性鉴别层 | 从 `differential`/`red_flag` chunk 抽方向边 → 注入 `lr_reference` 旁路 |
| **P1** | 常见综合征 discriminative markers 补库 | LAP→leukemoid、ESR→thyroiditis 等（探针 5/21 MISS） |
| **P2** | salience filtering 扩展 | 慢性基线异常降权 |
| **P2** | Dual-Inf 式双向核验 | reconcile 阶段反推代表症状 |

> 若需 CPG/case-report 接入证据标注的**具体改造方案**（接口、数据结构、评测指标），可在此基础上另起 `CPG_EVIDENCE_ANNOTATION_INTEGRATION_PLAN.md`。

---

## 8. 相关文档索引

| 文档 | 关系 |
|---|---|
| [`EVIDENCE_ANNOTATION_LR_DEFECTS_RESEARCH.md`](EVIDENCE_ANNOTATION_LR_DEFECTS_RESEARCH.md) | **深化版**：21 探针量化 + A1–A14 算法缺陷 + 9 题实证 |
| [`构建临床诊断kg_20260702_2110.md`](构建临床诊断kg_20260702_2110.md) | 外部 KG 五层架构与 syndrome→L1 设计 |
| [`EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md`](EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md) | B2 LR 通道、§26 错误 LR 溯源、§31 CPG 强制分支源 |
| [`CPG_RAG_EXTRACTION.md`](CPG_RAG_EXTRACTION.md) | CPG chunk 分类、NICE 整合、§13 防漏增强 |
| [`GRAPHRAG_MULTISOURCE_FEASIBILITY_RESEARCH.md`](GRAPHRAG_MULTISOURCE_FEASIBILITY_RESEARCH.md) | 多源 GraphRAG 可行性 |
| [`RESIDUAL_MISS_ROOTCAUSE_AND_MECE.md`](RESIDUAL_MISS_ROOTCAUSE_AND_MECE.md) | §13b LR 解析修复、§14 recall hints |
| `scripts/probe_lr_annotation_defects.py` | LR 探针（缓存臂 + `--rag` 臂） |

---

*本文档由会话 `d6e23c24` 第 4337 轮助手回复入档整理，2026-07-08。*
