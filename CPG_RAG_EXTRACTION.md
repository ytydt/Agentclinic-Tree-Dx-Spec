# CPG / 非结构化临床语料的 RAG 提取方案

本文档调研**如何从 PDF、HTML、PubMed 摘要等复杂非结构化 CPG 语料中，用 RAG 提取 BranchCreator / mandatory_coverage 所需信息**。与 [`OPEN_CPG_DOWNLOADS.md`](OPEN_CPG_DOWNLOADS.md)（镜像与合规）和 [`EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md`](EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md)（Layer 0–3 架构）衔接。

---

## 1. 问题与目标

### 1.1 现状

截至 2026-06-24，开放 CPG 镜像约 **9200+** 条可审计条目（含 PMC-OA **5869**、WikEM **163**）；NICE 公开 HTML **`nice_ddx__*` 1320 章**（303 指南）已入库；PMC-OA DDx 综述 **87,976** chunks（推荐 RAG 子集 **2,421** 篇，§1.6）；WikEM **1,053** chunks（§1.7）。Syndication 全库待 API-Key。

| 形态 | 约占比 | 典型来源 | 文本质量 |
|---|---:|---|---|
| HTML 全文 | ~71% | IDSA、ACOG、SCCM、ASH 官网 | 中–高（已有 `text_path`） |
| HTML 索引 / PubMed 摘要 | ~28% | ACC/AHA、AAN、Endocrine `*_pm__` | 低–中（常仅 abstract） |
| PDF | ~15 条附件 | GOLD/GINA、WHO、CDC、KDIGO | 中（`pypdf` 线性抽取，表格易乱） |
| 已结构化 chunks | 2029 主题 | MedlinePlus | 高（段落级 JSONL） |
| 独立 RAG 语料 | 367k 段 | StatPearls（`data/corpus/statpearls/`） | 高（NXML 段落切分） |

**关键缺口**：`data/cpg/processed/cpg_chunks.jsonl` **尚未实现**；现有 Layer 3 RAG（`RAGRetriever`）只索引 StatPearls + Textbooks，**未纳入 CPG 镜像**。

### 1.2 提取目标（面向 Tree-Dx-Spec）

RAG 在这里不是「把整篇指南塞进 prompt」，而是从非结构化原文中**按需召回片段**，再**结构化抽取**为下游 KB 字段。与本项目最相关的字段包括（见 `SYNDROME_TO_L1_BRANCH_KNOWLEDGE_RESEARCH.md`）：

| 字段 | 用途 | 典型 CPG 章节 |
|---|---|---|
| `mandatory_coverage` / 鉴别域 | L1 分支防漏 | Differential diagnosis、Evaluation、Syndrome workup |
| `cant_miss` / red flags | 急症分支 | Urgent referral、When to hospitalize |
| `recommended_tests` | 检查路径 | Diagnostic workup、Initial assessment |
| `management_pathway` | 治疗/处置线索 | Recommendations、Treatment algorithm |
| `evidence_grade` | 置信度标注 | Class I/II/III、GRADE、Level A/B/C |
| LR / Sn / Sp（可选） | EvidenceAnnotator | 含数字或定性频率的句子 |

### 1.3 NICE 整合原则：全自动化、零手工文件依赖

**设计约束**：NICE 进入 BranchCreator / mandatory_coverage 的路径必须是**可重复、可增量、无需维护 curated 列表**的管道。下列文件/步骤**不是** NICE 的长期数据源：

| 非目标（legacy / 其他来源用） | 原因 |
|---|---|
| `extract_nice_public_chapters.py` 内 `CURATED` 表 | 固定 25 条 URL，扩展需人工改代码 |
| `open_cpg_seed_expansion.json` 中 NICE 条目 | 手 curated 扩展，不可规模化 |
| 运行时依赖 `syndrome_axis_map.json` 预映射 NICE 专科 | 轴图是 BranchCreator 契约，不是 CPG 发现层 |

**canonical 自动化路径**（无 API-Key 与有 API-Key 二选一，可并存去重）：

```text
┌─ 路径 A（公开 HTML，当前主力）────────────────────────────────────────┐
│ nice.org.uk/guidance/published 分页列表                                 │
│   → crawl_nice_published_ddx.py --use-cache-list --all-sidebar        │
│   → open_cpg_nice_ddx_seed.json（1320 章 / 303 NG·CG·DG·SC）          │
│   → download_open_cpg.py → manifest + text_path                       │
└───────────────────────────────────────────────────────────────────────┘
┌─ 路径 B（Syndication API，API-Key 激活后）────────────────────────────┐
│ fetch_nice_syndication_index.py → build_nice_api_seed.py              │
│   → download_nice_syndication.py → manifest + text_path               │
└───────────────────────────────────────────────────────────────────────┘
        ↓ 二者 manifest 合并（按 id / url 去重）
┌─ RAG 层（待建，全自动）───────────────────────────────────────────────┐
│ build_cpg_chunks.py                                                   │
│   · 读 manifest_latest.jsonl（status=ok, text_path 非空）              │
│   · section_path ← seed.title 或「{guidance_title} > {chapter}」       │
│   · clinical_area ← nice_published_list_latest.json 标题/类型启发式    │
│   · chunk_type ← 章节 slug 规则（Recommendations / symptom-organised…）│
│ build_tfidf_index.py / build_rag_index.py（corpus=cpg）               │
│ GuidelineBranchSource / BranchPayloadBuilder                          │
│   · query 由 syndrome + vignette 动态生成，不按手工 map 过滤 NICE      │
└───────────────────────────────────────────────────────────────────────┘
```

**自动化元数据**：指南主条目不写入单独 seed 行；chunk 阶段从 `nice_published_list_latest.json` 解析 `{ref, title, url}` 填入 `parent_manifest_id` / `section_path` 前缀，**等价于「按主条目组织」**，无需 `nice_guidance_*` 父 seed。

**与 UnionAxisMap 的分工**：NICE RAG 产出 **generated** 的 `mandatory_coverage` 候选；`syndrome_axis_map.json` / override seeds 仍为 **curated 下界与轴契约**，不由 NICE 管道维护。

### 1.4 NICE 数据结构调研结论（2026-06-23）

本节归档 NICE 公开 HTML 镜像的**字段结构**、**章节内容分布**、**综合征起点 RAG 可行性**及**集成阻塞项**；与 §1.3 自动化路径衔接。交叉引用：[`OPEN_CPG_DOWNLOADS.md`](OPEN_CPG_DOWNLOADS.md) NICE 小节、[`EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md`](EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md) §31.13.13 / §31.14。

#### 1.4.1 Seed 与 Manifest 字段（`nice_ddx__*`）

每条章节为**独立可下载条目**；逻辑上归属指南主条目，但**不写入** `nice_guidance_{ref}` 父 seed 行。

| 字段 | 示例 | 说明 |
|---|---|---|
| `id` | `nice_ddx__cg95__recommendations` | `{prefix}__{ref}__{slugify(chapter_slug)}`，≤120 字符 |
| `parent_id` | `nice_guidance_cg95` | 逻辑父键；chunk 阶段用 published 列表补全标题/URL |
| `nice_ref` | `cg95` | 指南编号（NG/CG/DG/SC） |
| `chapter_slug` | `Recommendations` / `overview` | 侧边栏 slug；`overview` 为 landing 页 |
| `title` | `{guidance_title} — {chapter_title}` | 含完整指南名 + 章节名，供检索与 `section_path` |
| `url` | `…/guidance/cg95/chapter/Recommendations` | 章节 canonical URL |
| `clinical_area` | `["nice","guideline","differential_diagnosis"]` | **当前过粗**；`build_cpg_chunks.py` 应从 `nice_published_list_latest.json` 推导专科标签 |
| `access` | `public_html` | 无 API-Key |

Manifest 在 seed 基础上增加：`status`、`sha256`、`raw_path`、`text_path`（如 `data/cpg/text/nice/nice-ddx-cg95-recommendations.txt`）、`bytes`。磁盘为**扁平目录**，按 `{ref}-{slug}` 文件名前缀区分指南；**按主条目组织**在 chunk 元数据层完成，非目录层级。

**规模（`--all-sidebar`，2026-06-23）**：**1320** 章节 / **303** 指南；manifest **1320 ok**。历史 `nice_pub__*`（126 条 curated）与 `open_cpg_seed` 中旧 `nice_ddx__*` 条目可能并存，新 run 以 `open_cpg_nice_ddx_seed.json` 为准。

#### 1.4.2 章节内容分布（鉴别信息载体）

| 章节类型 | 约占比 | 鉴别信息密度 | RAG 优先级 |
|---|---:|---|---|
| `Recommendations` | ~280/1320 | **高**（~74% 含 consider/refer/exclude/suspected 等词） | **P0** |
| 按症状/体征组织（如 NG12 `Recommended actions organised by symptom…`） | 少数 | **极高**（症状群→转诊/鉴别） | **P0** |
| `Context` / `Rationale-and-impact` | ~350 | 中–低（背景与证据 rationale） | P1 |
| `overview` / `Introduction` | ~340 | 低（scope、更新摘要） | P2 |

**结论**：鉴别诊断信息**并非**仅存在于 Overview；**Recommendations 及症状组织章节**是 mandatory_coverage / cant_miss 的主载体。旧版 DDx 关键词过滤（311 章）会漏掉大量 Recommendations，已由 `--all-sidebar` 取代。

#### 1.4.3 综合征 / 症状群起点 RAG：可行性判断

| 阶段 | 状态 | 说明 |
|---|---|---|
| 镜像 + 正文 | ✅ | 1320 章均有 `text_path` |
| `cpg_chunks.jsonl` | ❌ | 未切分、未打 `chunk_type` |
| CPG 向量/稀疏索引 | ❌ | `RAGRetriever` 仍仅 StatPearls + 教科书 |
| 运行时检索 NICE | ❌ | **当前无法**从综合征 query 召回 NICE 片段 |
| 管道接通后 | ✅ 预期可行 | 动态 query（§5.4）+ Recommendations chunk + 抽取带 citation |

**与 StatPearls 的分工不变**：NICE = 权威推荐与转诊阈值；StatPearls = 综述式鉴别描述。NG12 类指南是「症状群→鉴别/转诊」的**最强正例**。

#### 1.4.4 集成阻塞项（待 Phase 3 消除）

1. **`GuidelineBranchSource` on-topic 门控与章节标题不匹配**（`guideline_branch_source.py`；**全 CPG 源共有**，见 §1.5.4）：过滤要求 title 含 `Differential Diagnosis|Etiology|Causes|Evaluation`，或 title 与 syndrome token 重叠。NICE 及 IDSA/ACOG 等 chunk 标题多为指南名或 `Recommendations`，**易被丢弃**。修复方向：并入 CPG 索引后改按 `chunk_type` 或源别章节 slug 白名单。任务 ID：**IMP-35**。
2. **HTML 导航噪声**：NICE / ACOG / PubMed·PMC 等可见文本常含面包屑、Cookie、Skip to content（§3.1、§1.5.1）；`build_cpg_chunks.py` 应分源做 main-content 裁剪。
3. **`clinical_area` 未与专科/综合征轴关联**：检索后需用 `syndrome_axis_map` 或 query-time 专科启发式降噪声，**不由 NICE seed 手工维护**。

### 1.5 其他 CPG 数据源结构清查（2026-06-23）

对 `open_cpg_seed.json`（3441 条）与 `manifest_latest.jsonl`（3453 ok）的实测清查。**结论：NICE 的多章节 + 悬空 `parent_id` 是特有模式；更普遍的问题是全库共有的 RAG 门控、HTML 噪声、摘要层与页内切分需求。**

#### 1.5.1 问题类型 × 数据源矩阵

| 结构 / RAG 问题 | NICE | 官网 HTML 派生（IDSA/ACOG/SCCM/ACR/RCOG…） | PubMed/Europe PMC 派生（ACC/AHA/AAN/ESC/Endocrine/ASH…） |
|---|---|---|---|
| **悬空 `parent_id`（父行不在 seed）** | ✅ **303** 个 `nice_guidance_*` | ❌ 均有 `*_index` 主条目在 seed | ❌ 均有 `*_guidelines_index` |
| **URL 级多章节** | ✅ 1320 章（`--all-sidebar`） | ❌ 0 条 `/chapter/` URL；**一指南一页** | ❌ 单 PMID/PMC 页 |
| **页内章节切分需求** | 中（已 URL 分章，Recommendations 仍长） | **高**（IDSA 中位 ~8.7kB，37% >20kB 单页） | 高（PMC 全文）；摘要层 **不适用** |
| **`content_tier: abstract_only`** | 低 | 低（ACOG 几乎全页 ~25kB） | **高**（ACC/AHA **~24%** 摘要/metadata；AAN/Endocrine 类似） |
| **HTML 导航/Cookie 噪声** | 高（100% 抽样） | 高（ACOG/ASH/RCOG）；IDSA/ACR 较低 | 高（PubMed/PMC 壳） |
| **title 含 DDx/Evaluation section 名** | **~0.4%**（6/1548） | **~0%**（IDSA 0/105） | **~0–4%** |
| **`GuidelineBranchSource` on-topic 门控** | ⚠️ 误滤 Recommendations | ⚠️ **同样误滤**（标题为指南名非 section） | ⚠️ 同上；且摘要层无 DDx 正文 |
| **`clinical_area` 过粗** | ✅ 仅 3 个泛化 tag | ⚠️ 多数 1–2 tag（如 `["obstetrics","gynecology"]`） | ⚠️ 常仅 1 tag |
| **手工 curated 依赖** | legacy `nice_pub__*` / expansion 4 条 | `open_cpg_seed_expansion.json` 部分（USPSTF 11 等） | 低（API 索引自动派生） |

#### 1.5.2 分源要点

**IDSA / SCCM / ACOG / ACR（HTML 索引派生）**

- 结构：`{org}_index` 主条目 **在 seed 内** + `{org}_child__*` 子链（100–337 条/索引）；`parent_id` 可解析。
- 与 NICE 差异：**无 URL 章节**；鉴别/推荐内容在同一 HTML 页的 `Recommendations` / `Diagnosis` 等 **H2/H3** 下，须 `build_cpg_chunks.py` 做**页内标题切分**，不能照搬 NICE 的 URL-chapter 逻辑。
- ACOG：多为完整 HTML 页（中位 ~25kB），但 Cookie 横幅污染严重。

**ACC/AHA / AAN / ESC / Endocrine / ASH（PubMed/Europe PMC 派生）**

- 结构：`{org}_pm__` / `{org}_epmc__` + 索引页；811 条派生中 **~63%** 为 `public_html_index`（PubMed 摘要页）。
- **摘要层风险**：ACC/AHA 248 ok 中约 60 条 text <5kB（摘要/metadata）；**不宜**用于 mandatory_coverage 抽取，chunk 须标 `content_tier: abstract_only` 并在检索时过滤（§4.3）。
- 有 PMC 全文者（如 ESC 67、ACC/AHA 33）质量接近 IDSA，但仍需去 PubMed/PMC 导航壳。

**ACR Appropriateness Criteria**

- 278 条 narrative HTML，结构较干净（导航噪声低），**全文可用**；标题 rarely 含 “differential diagnosis”，同样依赖 IMP-35 门控修复 + 页内切分。

**手工 / 半自动源（非规模化）**

- `open_cpg_seed_expansion.json`（51 条）：GOLD/GINA PDF、USPSTF 10+1、NICE 4、CDC/ESC 等——**其他来源的补充入口**，与 NICE §1.3 自动化原则同类，不应作为主力 DDx 管道。
- USPSTF/ADA/AAFP：多为**仅索引**、子链未全量展开（见 `OPEN_CPG_DOWNLOADS.md` 覆盖表）。

#### 1.5.3 对 `build_cpg_chunks.py` 的分源策略（**已实施**，2026-06-24）

脚本：`scripts/cpg_manifest_common.py` + `scripts/build_manifest_cpg_chunks.py` → `data/cpg/processed/manifest_cpg_chunks.jsonl`，由 `build_cpg_chunks.py` 合并。

| 源类型 | 切分单元 | 必填 metadata | 实测（`--useful-only`） |
|---|---|---|---:|
| NICE `nice_ddx__*` | HTML `article.recommendation` + `div.section` | `parent_ref`、`chapter_slug`、`chunk_type` | **29,391** chunks |
| IDSA/ACOG/SCCM/ACR/RCOG HTML | `<main>`/`<article>` + 页内 h2–h4 | `content_tier: full_text`；剔除 nav/cookie/hub | **~6.7k** chunks |
| PubMed 摘要 | abstract 段 | `content_tier: abstract_only`；**useful-only 排除** | 摘要层不入 useful 合并 |
| PMC 指南镜像 HTML | `#main-content` 章节 | `content_tier: full_text` | ACC/AHA/ESC 等 **~2.3k** |
| PDF 附件 | 线性 text 按标题切 | 同 society HTML | CDC/GOLD/GINA 等 |

**结构缺陷修复**：

- **索引/着陆页过滤**：A–Z List、Syndication API、方法学页等 **23+** 条跳过（`INDEX_TITLE_RE` / `is_hub_text`）。
- **NICE 主内容抽取**：优先 raw HTML `div.chapter`，不用带面包屑的 `text_path`。
- **PubMed 摘要层**：`abstract_only` 在 `--useful-only` 合并时剔除，避免噪声召回。
- **NCBI 浏览器校验页剔除**（2026-06-25）：`is_browser_gate_text()` / `manifest_has_bot_gate()` 识别 `Checking your browser before accessing pubmed…` 拦截页；`build_manifest_cpg_chunks.py` 记 `skip_reasons["bot_gate"]`；`build_cpg_chunks.py` 合并兜底。审计：`scripts/audit_manifest_bot_gate.py` → `data/cpg/eval/manifest_bot_gate_report.json`。
- **IMP-35 对齐**：chunk 写入 `chunk_type` / `entry_type` / `content_tier`，不依赖 StatPearls 式 section 标题。

**全量规模（2026-06-25）**：manifest 处理 **3,200** 篇（**198** 篇 `bot_gate` 跳过）→ **39,091** useful chunks；合并后 `cpg_chunks.jsonl` **360,234** 条（含 WikEM + PMC-OA + Merck + manifest；**不含** MedlinePlus）。

#### 1.5.3.2 NCBI 浏览器校验页（bot_gate，2026-06-25）

`download_open_cpg.py` 批量拉 PubMed/PMC HTML 时，NCBI reCAPTCHA 拦截页（约 **171 字节**）曾被误存为 `text_path`。典型文案：*Checking your browser before accessing pubmed.ncbi.nlm.nih.gov …*。

| 层 | 实测 | 处置 |
|---|---|---|
| manifest 原始镜像 | **198 / 9,483** 文件（**2.09%**） | 报告见 `data/cpg/eval/manifest_bot_gate_report.json`；可选 `--annotate-manifest` 写 `download_quality: bot_blocked` |
| 按来源（原始层） | SSC/SCCM **63**、ACC/AHA **60**、AAN **31**、Endocrine **27**、ESC **11**、ASH **5**、EULAR **1** | 均为 `*_pm` / `*_epmc` PubMed·PMC 镜像前缀 |
| manifest useful chunks | 剔除前 **18** poison chunk → 剔除后 **0** | `skip_reasons["bot_gate"]: 198`；`cpg_chunks` **360,234**（−18） |
| 其他源（NICE/WikEM/PMC-OA BioC/Merck/MedlinePlus） | **0** | 不受此问题影响 |

**实现**：`cpg_manifest_common.is_browser_gate_text()`、`manifest_has_bot_gate()`；`scripts/audit_manifest_bot_gate.py`。

**待办**：198 篇须 Europe PMC / BioC / 协会 publisher 补拉全文（非重跑 `download_open_cpg.py` 同 URL）。

#### 1.5.3.1 有害操作（评测结论，勿默认启用）

`scripts/eval_abstract_fulltext_recall.py`（50 条 WikEM 综合征 query，TF-IDF Recall@10）结论：**以下两项视为有害，禁止作为默认管道**。

| 操作 | 实测 | 处置 |
|---|---|---|
| **MedlinePlus 并入 `cpg_chunks`** | Recall@10 **60%→58%（−2%）**；**0/50** 出现「仅 MedlinePlus 命中」 | 保留 `data/poc/medlineplus/` POC 层；合并仅 ablation 用 `--include-medlineplus` |
| **PubMed `abstract_only` 摘要层入 RAG 正文** | 协会源 Recall@10 +2%，但配对全文 DDx 短语约为摘要 **5×**；513 篇仅摘要库存 Europe PMC **PMCID 0%** | `--useful-only` 已剔除；补全文应走协会 publisher HTML/PDF，**非** Europe PMC |

报告：`data/cpg/eval/abstract_fulltext_recall_report.json`。

#### 1.5.4 共用集成阻塞项（非 NICE 独有）

1. **IMP-35** 影响**全部** CPG 源：现行 on-topic 门控按 StatPearls `{Article} > Differential Diagnosis` 标题设计，对「指南全名 — Recommendations」、PMC-OA/WikEM `Clinical Features` 等**普遍不适用**；并入 `cpg_chunks` 后改按 `chunk_type` + `entry_type` 门控。
2. **CPG 未入索引**（§1.1）：所有源当前均不可被综合征 query 召回。
3. **`clinical_area` enrichment**：各源均需在 chunk 阶段从 title/MeSH/索引 metadata 自动推导，而非扩手工 map。

#### 1.5.5 增量源结构对照（PMC-OA §1.6 / WikEM §1.7）

| 结构 / RAG 问题 | PMC-OA | WikEM |
|---|---|---|
| 发现层假阳性 | **高**（55% 无 syndrome anchor） | **低–中**（**15/163** 无 useful chunk；Category 含 hub） |
| 全文可用性 | 高（BioC）；13 篇失败 | 高（163/163 parse 成功） |
| 页内 DDx 载体 | BioC `title_1/2` | Template **h3** + wiki 表 |
| 专科变体 | 独立 OA 文章 | `(geriatrics)` 等 **章节名非标** → 漏 chunk |
| 推荐 RAG 核心 | **2,421** 篇 | **148** 页 |
| cant_miss | 须正文抽取 | **3,835** wiki 链指（待 UMLS 归一） |
| 共用阻塞 | IMP-35、`build_cpg_chunks.py` 未接入 | 同左 |

### 1.6 PMC-OA DDx 综述结构调研结论（2026-06-24）

本节归档 IMP-50 全量抓取（`build_pmc_oa_ddx_index.py` + `fetch_pmc_bioc.py`）后的**实测结构**与 RAG 可用性子集。交叉引用：[`OPEN_CPG_DOWNLOADS.md`](OPEN_CPG_DOWNLOADS.md) § PMC-OA 抓取指引。

#### 1.6.1 规模（2026-06-24 实测）

| 层 | 数量 | 说明 |
|---|---:|---|
| 发现 index | **5,950** | Europe PMC 6 条 DDx 标题 query |
| 有 PMCID 全文 | **5,882** | `has_pmc_fulltext=true` |
| BioC 成功入库 | **5,869** | 13 篇 API 失败 |
| DDx chunks | **87,976** | `pmc_oa_ddx_chunks.jsonl` |

#### 1.6.2 与 NICE / PubMed 摘要层的结构差异

| 维度 | NICE | PubMed 派生 | **PMC-OA** |
|---|---|---|---|
| 多 URL 章节 | ✅ 1320 章 | ❌ | ❌ 一 PMCID 一篇 |
| 摘要层风险 | 低 | **高**（~63% 仅摘要） | **低**（BioC 全文） |
| HTML 导航噪声 | 高 | 高 | **低**（BioC passage） |
| 页内章节 | URL 已分章 | 须 HTML 切分 | **较好**（BioC `title_1/2`） |
| 发现层精度 | 较高（侧边栏筛） | 中 | **偏低**（标题 query 偏宽） |

**结论**：PMC-OA **不存在** NICE 式多章节/Recommendations 载体问题，也**不像** ACC/AHA 镜像那样大量缺正文；主要风险在**发现 query 假阳性**与**全库共有 IMP-35 门控**。

#### 1.6.3 发现层与 chunk 质量（实测）

| 指标 | 数量 | 占比 |
|---|---:|---:|
| 无 `syndrome_keywords`（标题非症状入口） | 3,275 | 55% |
| 无 differential/red_flag/evaluation chunk | 423 篇 | 7.4% |
| 有 anchor **且** 有 DDx/红旗/评估 chunk（**推荐 RAG 核心**） | **2,421** 篇 | ~41% |
| 上述核心子集 useful chunks | ~46,506 | — |
| IMP-35 标题门控粗算误滤率 | ~90.6% | 须改读 `chunk_type` |

典型假阳性标题：*"How Tobacco Smoke Causes Disease"*、*"Evaluation and Treatment of Dyslipidemia"*、Patient Version 癌症页。

chunk 层缺口：`syndrome_anchor` 未写入 chunk（仅 index 有 `syndrome_keywords`）；`clinical_area` 过粗。

#### 1.6.4 集成建议

1. **检索子集**：优先 `syndrome_keywords` 非空且 `useful_chunks≥1` 的 **~2,421** 篇，非全库 5,950。
2. **IMP-35**：PMC-OA chunk 已带 `chunk_type`，门控应读该字段而非 section 标题字面。
3. **可选过滤**：index 阶段增加最小 useful-chunk 阈值；chunk 阶段补 `syndrome_anchor`。
4. **`parent_id=pmc_oa_ddx_index`** 悬空（与 NICE 同类，非阻塞）。

#### 1.6.5 抓取状态

脚本已实施：`scripts/build_pmc_oa_ddx_index.py`、`scripts/fetch_pmc_bioc.py`、`scripts/pmc_oa_ddx_common.py`。命令见 `OPEN_CPG_DOWNLOADS.md` § PMC-OA。

### 1.7 WikEM 数据结构调研结论（2026-06-24）

WikEM（CC BY-SA 3.0，附 AI/ML 限制）为**急诊症状入口 + DDx 表**的开放源，对应 IMP-56 cant_miss 与 syndrome_entry RAG。脚本：`scripts/crawl_wikem_syndrome.py`。

#### 1.7.1 有效数据是什么

| 要收 | 不要收 |
|---|---|
| `Category:Symptoms` 下**英文主条目**（腹痛、胸痛、AMS 等） | 翻译页（`/es`、`/fr`…）、体重模板页、纯管理/药理条目 |
| 章节：`Differential Diagnosis`、`Evaluation/Workup`、`Red flags` / can't-miss 段 | `Management`、`References`、`See Also`、计算器细节 |
| DDx 表内 **wiki 链接实体**（→ cant_miss 候选） | 用于模型训练/微调/评测（站点 AI/ML 条款禁止） |

#### 1.7.2 结构特点

- **一症状一页**，MediaWiki `parse` API 返回章节树；DDx 常嵌 **Template**（如 `Template:DDX_RUQ`），展开后在 HTML 中仍为可抽取列表。
- **无 URL 多章节**；**无摘要层**；导航噪声低于 NICE HTML。
- chunk 已打 `entry_type=syndrome_entry`、`syndrome_anchor=页面标题`；同样受 **IMP-35** 影响（若按标题字面门控会误滤 `Clinical Features` 等）。
- 许可：**RAG 检索可用**，须署名 + ShareAlike；**禁止**用于 ML 训练/微调/评测。

#### 1.7.3 交付物与实测规模（2026-06-24）

| 层 | 数量 | 说明 |
|---|---:|---|
| 发现 index | **163** | `Category:Symptoms` 去重后（剔除 `/en` 重复页） |
| 全文入库 | **163** | MediaWiki `parse` API |
| DDx chunks | **1,053** | differential 为主，含 evaluation / red_flag |
| 有 useful chunk 的症状页 | **148** | 15 页仅 background/other（如纯索引页 `Visual diagnosis (main)`） |
| cant_miss 实体链接 | **3,835** | 跨页 wiki 链接；见 `cant_miss_by_syndrome_wikem.json` |

**结构注意**：WikEM 使用 Translate 扩展，HTML 中 `<h2><span class="mw-headline" id="…">`（id 在 span 上）；DDx 内容常嵌于 **Template 展开的 h3 子节**（如 RUQ/RLQ 表），须按 heading 树继承 `chunk_type`，不能仅依赖 API 顶层 `sections`。

| 路径 | 内容 |
|---|---|
| `data/cpg/api/wikem_syndrome_index_latest.jsonl` | 发现层（Category:Symptoms） |
| `data/cpg/processed/wikem_ddx_chunks.jsonl` | DDx/评估/红旗 chunk |
| `data/knowledge_raw/cant_miss_by_syndrome_wikem.json` | 症状→cant_miss 实体（wiki 链接 + provenance） |

命令见 [`OPEN_CPG_DOWNLOADS.md`](OPEN_CPG_DOWNLOADS.md) § WikEM 抓取指引。

#### 1.7.4 结构问题清查（2026-06-24 实测）

对 `wikem_syndrome_index_latest.jsonl`（163 条）、`wikem_ddx_chunks.jsonl`（1,053 chunks）、`cant_miss_by_syndrome_wikem.json` 的实测清查。**结论：WikEM 不存在 NICE 式多 URL 章节或 PubMed 摘要层问题；主要风险在 Category 发现噪声、变体页章节命名、以及全库共有 IMP-35 门控。**

##### 与 NICE / PMC-OA 的差异

| 维度 | NICE | PMC-OA | **WikEM** |
|---|---|---|---|
| 多 URL 章节 | ✅ 1320 章 | ❌ 一 PMCID 一篇 | ❌ 一症状一页 |
| 摘要层 / 缺正文 | 低 | 低（BioC） | **无**（API 全文） |
| HTML 导航噪声 | 高 | 低（BioC） | **低–中**（Translate 标签已剥离；TOC 不入 chunk） |
| 症状入口精度 | 较高 | 偏低（55% 无 anchor） | **较高**（163 页均 `Category:Symptoms`） |
| DDx 载体 | Recommendations 章 | BioC passage | **Template 展开 h3 表 + wiki 链接** |
| `syndrome_anchor` | 须从标题/父指南推 | 仅 index 有 | **chunk 级齐全** |
| 许可 | 开放 HTML | PMC-OA | **CC BY-SA + AI/ML 限制** |

##### 问题类型 × 实测

| 结构 / RAG 问题 | WikEM 实测 | 严重度 |
|---|---|---|
| **悬空 `parent_id`**（`wikem_syndrome_index` 无 seed 父行） | ✅ 163 条均有 | 低（与 NICE/PMC-OA 同类，chunk 阶段可补） |
| **发现层假阳性** | ⚠️ **15/163** 无 useful chunk：`*(main)` 索引 hub（3）、部位诊断 hub（`Ear/Elbow/Foot diagnoses`）、非症状条目（`Depression`、`Insomnia`、`Acute pain management` 等） | 中 |
| **变体页章节命名** | ⚠️ **15** 页 `useful_chunks=0`：`(geriatrics)` 用 `Elderly` 节而非 `Differential Diagnosis`（如 Abdominal pain geriatrics **含 MI/缺血等 DDx 链接但未入 chunk**）；部分 stub 仅链到主条目 | **高**（漏 clinically useful 变体） |
| **Template 子节依赖** | ⚠️ 顶层 API `sections` 仅 8 节，DDx 表在 h3（RUQ/RLQ…）；**须 heading 树继承 `chunk_type`**（已实现） | 高（未实现时 0 chunk） |
| **MediaWiki DOM** | ⚠️ `id` 在 `<span class="mw-headline">` 非 `<h2>`；首版 parser 因此 **0 chunk** | 已修复 |
| **IMP-35 标题门控** | ⚠️ ~**81%** chunk 的 section 字面不含 `Differential Diagnosis/Causes/Evaluation`（`Clinical Features`、`RUQ Pain` 等） | 高（须改读 `chunk_type`） |
| **cant_miss 覆盖** | ⚠️ **139/163** 症状有 wiki 链接实体；**24** 页空（多为 geriatrics stub / 索引 hub） | 中 |
| **短 fragment chunk** | ⚠️ **81** 条 differential chunk &lt;120 字符（Translate 壳、`Differential Diagnosis` 空壳节） | 中（检索噪声） |
| **纯 prose DDx 无链接** | ⚠️ **39** 条 differential chunk 无 `wiki_links` | 低 |
| **`clinical_area` 过粗** | ⚠️ 仅 `wikem/emergency_medicine/syndrome_entry` | 低 |

##### 典型假阳性 / 漏抽取样例

| 类型 | 样例 | 说明 |
|---|---|---|
| 索引 hub | `Diagnoses by body part (main)`、`Visual diagnosis (main)` | Category:Symptoms 下的**目录页**，非单症状 DDx |
| 非症状条目 | `Acute pain management`、`Depression`、`Weight loss` | 管理/慢病页，非 chief complaint 入口 |
| 变体漏抽取 | `Abdominal pain (geriatrics)` | `Elderly` 节含 MI、SBO、appendicitis 等，但无显式 DDx 标题 → **当前 0 chunk** |
| 有效正例 | `Abdominal pain` | 17 chunks，139 cant_miss 链接，h3 区位 DDx 表完整 |

#### 1.7.5 集成建议

1. **推荐 RAG 子集**：**148** 页（`useful_chunks≥1`），非全库 163；索引 hub 与确认 stub 可降权或排除。
2. **变体页增强（待实现）**：对 `(geriatrics)` / `(peds)` 页，将 `Elderly`、`Pediatric` 等节启发式标为 `differential`；或 fallback 链到主条目 DDx。
3. **IMP-35**：WikEM chunk 已带 `chunk_type` + `syndrome_anchor`，门控**必须**读这两字段。
4. **cant_miss（IMP-56）**：`cant_miss_by_syndrome_wikem.json` 可用；geriatrics 变体需补抽取或手工 alias 到主条目。
5. **许可**：RAG 检索 + cant_miss 接地可接受；**禁止**入库语料用于模型训练/微调/评测。

#### 1.7.6 与 §1.5 矩阵的补充行

| 结构 / RAG 问题 | WikEM |
|---|---|
| 悬空 `parent_id` | ✅ `wikem_syndrome_index` |
| URL 级多章节 | ❌ |
| 页内章节切分 | **高**（Template h3 + heading 继承） |
| `content_tier: abstract_only` | **无** |
| HTML 噪声 | 低–中 |
| title 含 DDx section 名 | **~83%** 抽样有显式 DDx 节；**实际 DDx 表多在 h3** |
| IMP-35 误滤 | ⚠️ ~81% |
| 发现层精度 | 中（Category 含 hub/非症状 **~9%** 无效页） |

---

### 1.8 症状群入口检索完备性调研（2026-06-24）

**问题**：当前 chunk 拆分 + top-k 检索能否保证（假设源内信息完整）综合征 query 召回**完整 DDx**？

**结论：不能保证**；chunk 策略设计目标是**按需召回片段**，不是保留「篇级 DDx 闭包」。在 2026-06-24 修复前存在**漏切**（WikEM geriatrics、PMC 子节）与**误过滤**（IMP-35 标题门控 ~81–90%）；修复后**单篇内召回**显著改善，但**跨 chunk 完备性**仍依赖检索层扩展。

#### 1.8.1 两层缺口（修复前）

| 层 | 问题 | 后果 |
|---|---|---|
| **切分/过滤** | WikEM `(geriatrics)` 的 `Elderly` 节未标 differential；PMC 仅看当前节名、80 字阈值；IMP-35 只认 StatPearls 式 section 标题 | 源内有 DDx 但未入库或被门控丢弃 |
| **检索** | top-k 单 query；无同 `source_id` 扩展；CPG 未入 RAG 索引 | 单篇 DDx 拆多块时无法一次收齐 |

#### 1.8.2 已实施修复（2026-06-24）

| 组件 | 改动 |
|---|---|
| `wikem_common.py` | `Elderly`/变体节 → differential；Translate 壳剥离；wiki 链指列表降 min_len；发现层剔除 `(main)`/`* diagnoses` hub |
| `pmc_oa_ddx_common.py` | 按 **section_stack 全路径** 判断 DDx 树；列表式 passage 降 min_len；chunk 写入 `syndrome_anchor` |
| `cpg_chunk_gate.py` + `guideline_branch_source.py` | **IMP-35**：优先 `chunk_type` / `entry_type=syndrome_entry` / `syndrome_anchor` |
| `rag_retriever.py` | 检索结果携带 chunk 元数据；`expand_ddx_siblings()` **篇内 DDx 闭包扩展**（⚠️ 代码已实现，但**实时索引缺 `chunk_type`/`source_id` 字段，运行时空转**，须待 IMP-31 重建写入元数据后生效——见 §1.10.2） |
| `build_cpg_chunks.py` | 合并 WikEM + PMC-OA + manifest + Merck → `cpg_chunks.jsonl` |
| `build_manifest_cpg_chunks.py` | manifest NICE/协会 HTML → `manifest_cpg_chunks.jsonl`（§1.5.3；含 bot_gate 剔除） |
| `audit_manifest_bot_gate.py` | 扫描 manifest 浏览器校验页 → `data/cpg/eval/manifest_bot_gate_report.json`（§1.5.3.2） |
| `rechunk_pmc_oa.py` | 离线自 BioC 重切（无需重拉网络） |
| `build_merck_manual_corpus.py` | 已购 Merck 19e PDF → `data/corpus/merck/`（§1.9） |

**修复后规模（实测）**：

| 源 | 修复前 | 修复后 |
|---|---:|---:|
| WikEM 发现 index | 163 | **147**（剔除 16 hub） |
| WikEM useful 页 | 148 | **137**（warnings 10） |
| WikEM chunks | 1,053 | **1,055** |
| PMC-OA chunks | 87,976 | **317,710**（放宽 DDx 树内保留；⚠️ 实测 `--useful-only` 几乎未削减 PMC，仍 317,710 全入，见 §1.10.4） |
| Merck 19e chunks | — | **9,629**（353 章；**23** Approach 章 → **1,284** `syndrome_entry`） |
| Manifest CPG（NICE + 协会 HTML） | — | **39,091** useful（**3,196** 篇；NICE **29,391**；**198** 篇 bot_gate 跳过） |
| `cpg_chunks.jsonl`（`--useful-only` 五源合并） | — | **360,234**（WikEM 1,055 + PMC-OA 317,710 + manifest 39,091 + Merck 2,378） |

#### 1.8.3 仍不能保证「完整 DDx」的原因

1. **top-k 上限**：WikEM 腹痛等页仍有 10+ DDx 子块，单次 query 未必全进 top-k（靠 `expand_ddx_siblings` 缓解）。
2. **PMC 发现层假阳性/子集**：全库 317k chunks 仍含非症状入口；推荐 `--pmc-require-anchor` 子集入索引。
3. **NICE / 官网 HTML**：尚未切 chunk，未纳入 `cpg_chunks.jsonl`。
4. **评测尺子未建**：`eval_coverage_oracle.py`（IMP-54）待量化「源内 DDx 实体集 vs 检索 union recall」。

#### 1.8.4 推荐运行时策略（篇级 DDx 闭包）

```text
症状 query → top-k 命中任 chunk
         → expand_ddx_siblings(source_id)  # 拉齐同篇 differential/red_flag/evaluation
         → snippet_on_topic (chunk_type 门控)
         → 抽取 mandatory_coverage / cant_miss
```

命令：

```bash
python scripts/crawl_wikem_syndrome.py --skip-existing --sleep 0.35
python scripts/rechunk_pmc_oa.py
python scripts/audit_manifest_bot_gate.py          # 可选：--annotate-manifest
python scripts/build_manifest_cpg_chunks.py --useful-only
python scripts/build_merck_manual_corpus.py --chunk-only   # 已有 extracted.txt 时仅重切
python scripts/build_cpg_chunks.py --useful-only
python scripts/build_cpg_chunks.py --useful-only --pmc-require-anchor  # 推荐 RAG 子集
python scripts/build_tfidf_index.py   # ⚠️ 脚本已列 Merck，但**实时索引（5-23 FAISS）尚未重建，当前仅 StatPearls+Textbooks**；须重跑方含 Merck，且 cpg_chunks 合入仍 IMP-31 待办（见 §1.10.1）
python scripts/build_rag_index.py     # 同上（FAISS 稠密索引；重建即触发 ~32 万级向量重编码，见 §1.10.4）
```

### 1.9 Merck Manual 19e（已购 PDF）结构调研与 RAG 管道（2026-06-24）

**许可边界**：MSD 在线 Professional 版禁止批量爬取/入库；本项目使用**用户已购买的第 19 版整册 PDF**（`/data3/wanghongyi/...pdf`），仅**内部 RAG**，`manifest.json` 标 `purchased_19e_internal_rag_only` / `redistribution: prohibited`。

**PDF 格式特征（CHM→PDF，4114 页）**：

| 特征 | 说明 |
|---|---|
| 前置页 | 1–2 空白；3–~52 为点线目录（TOC）；正文自 **~第 63 页**（Chapter 1） |
| 章节 | TOC 解析 **352 章**；页眉/页脚重复 `Chapter N. Title` |
| 疾病章 | 条目 Title Case 标题 → `Introduction` / `Symptoms and Signs` / `Diagnosis` / `Treatment` … |
| Approach 章 | 标题含 **`approach to`**（23 章）→ `entry_type=syndrome_entry`；条目如 `Chest Pain`、`Chronic and Recurrent Abdominal Pain`；小节含 `History:` / `Physical examination:` / `Testing:` |
| 抽取噪声 | 交叉引用 `see p.\n123` 断行、表格/图注行、希腊字母拆行 — `merck_manual_common.clean_page_text` 归一化 |

**切分策略**（`scripts/merck_manual_common.py`）：

- 目录解析 → 章节 canonical title；正文按 `Chapter N.` 切章。
- **疾病章**：仅当下一行是标准小节名时才切条目（避免 Nutrition 等散文章把每句误当条目）。
- **Approach 章**：Title Case 短标题（≤85 字、无句号）识别 complaint 条目。
- chunk 字段对齐 CPG 管道：`id`、`section_path`、`content`、`chunk_type`、`entry_type`、`source=Merck-Manual-19e`。

**交付物**：

```bash
python scripts/build_merck_manual_corpus.py          # 全量提取+切分 → data/corpus/merck/
python scripts/build_merck_manual_corpus.py --chunk-only  # 仅重切已有 extracted.txt
python scripts/build_cpg_chunks.py --useful-only     # 合并 WikEM + PMC-OA + Merck
python scripts/build_tfidf_index.py                  # StatPearls + Textbooks + Merck
```

| 文件 | 用途 |
|---|---|
| `data/corpus/merck/merck_manual_19e_extracted.txt` | 带 `===PAGE:N===` 标记的纯文本 |
| `data/corpus/merck/merck_manual_19e_toc.json` | 352 章 TOC |
| `data/corpus/merck/merck_manual_19e_chunks.jsonl` | RAG snippets |
| `data/corpus/merck/manifest.json` | 溯源与许可 |

**实测规模（2026-06-24 全量提取）**：

| 指标 | 数值 |
|---|---:|
| 提取页码 | 63–4114 |
| 解析章节 | 353 |
| 总 chunks | **9,629** |
| Approach 章 | **23** |
| `syndrome_entry` chunks | **1,284** |
| `chunk_type=differential` | 37 |
| 合并进 `cpg_chunks.jsonl`（`--useful-only`） | **2,378** |

**RAG 价值**：23 章 Approach 是**已购授权**下最接近 BMJ「症状入口 + DDx」的语料；与 WikEM/PMC-OA 互补（Merck 覆盖全科、PMC 深综述、WikEM 急诊 can't-miss）。

---

### 1.10 核验与更正（2026-06-25，实测 + 孤立实验）

> 对 §1.6–1.9 结论与 §13/§14 规划做了一次磁盘实测 + 孤立检索实验复核。**最重要的更正：三源（PMC/WikEM/Merck）已在 chunk/文件层就绪，但运行时 RAG 索引完全未含它们——所有新源当前对运行时检索零贡献**。以下逐项给出证据。

#### 1.10.1 【关键更正】实时 RAG 索引未含任何新源（Merck/WikEM/PMC 全缺）

**实测**：`data/corpus/rag_index/` 实际加载的是 **2026-05-23 构建的 FAISS（MiniLM-L6）索引**，`config.json` `sources=["statpearls","textbooks"]`，`ntotal=493646`。按 id 前缀统计：367,799 StatPearls（`_pN`）+ ~126k Textbooks（`InternalMed_Harrison`…）= 493,646，**无 Merck / WikEM / PMC**（`grep wikem|pmc_oa|syndrome_entry` = 0）。

**与文档冲突点**：§1.8.2 与 §1.9 命令注释 `build_tfidf_index.py # StatPearls + Textbooks + Merck` 暗示 Merck 已入索引——**实为脚本已列入但索引从未重建**（脚本改于 6-24，索引产物停留在 5-23）。即便 TF-IDF 产物（`tfidf_matrix.npz`，5-23）也早于 Merck 构建。

**结论**：§1.6–1.9 的全部抓取/切分成果 + §1.8.2 的「修复」目前**运行时不可达**；**IMP-31（索引重建）是唯一解锁前提**，非「待办优化项」而是「卡点」。

#### 1.10.2 【更正】`expand_ddx_siblings` 与 IMP-35 门控在实时索引上空转

**孤立实验**（`RAGRetriever('data/corpus/rag_index')`，查询 `abdominal pain / hypercalcemia / approach to jaundice`，各 top-8）：

| 观测 | 结果 |
|---|---|
| 返回源 | 仅 StatPearls（`_pN`）+ Textbooks（`InternalMed_Harrison`），无新源 |
| `chunk_type` | **全部 None**（实时索引元数据仅 `id/title/content/article_id/tokens`） |
| `source_id` | 全部空 |
| `expand_ddx_siblings` | 8 → 8（**新增 0**） |

**更正**：§1.8.2 将 `expand_ddx_siblings`/IMP-35 列为「已实施修复」**代码层属实**，但因实时索引缺 `chunk_type`/`source_id` 字段，**运行时完全不生效**。须在 §1.8.2 标注「依赖 IMP-31 重建（含元数据字段）后方生效」。IMP-31 重建时**必须写入** `source_id/chunk_type/entry_type/syndrome_anchor/license_note`（`_hit_from_meta` 已读取这些键）。

#### 1.10.3 【澄清】NICE 1548 + 协会 HTML（~3000 份）尚未进 cpg_chunks

**实测**：`build_cpg_chunks.py` 的 `SOURCES` 仅 WikEM/PMC/Merck 三个文件；manifest 中 **NICE 1548、ACOG 339、ACR 300、ACC/AHA 248、IDSA 105、ESC/ASH/AAN…** 等 ~3000 份 HTML 指南**均未切 chunk**。尽管 §1.4（NICE 1320 章）、§1.5 对其结构做了深入调研，IMP-30 当前**仅覆盖三症状源**。

**抽样质量**（未整合源 text_path）：NICE 首行命中条为 *"NICE Syndication API（registration required)"* 着陆页；IDSA 首条为 *"A–Z List"* 索引页；ACOG 首条为 *"Clinical Consensus Methodology"* 方法学页（含 Cookie 噪声）。即这些源**含大量索引/着陆/方法学页**，须经 §1.5.3 分源页内切分 + main-content 抽取后方可用。**排期上「先症状源、后协会 HTML」合理**，但文档须明确 NICE/协会 HTML **当前不在 cpg_chunks 也不在索引**。

#### 1.10.4 【数据质量】cpg_chunks 组成偏噪，`--useful-only` 未实际过滤 PMC

**实测 `cpg_chunks.jsonl`（321,143）**：

| 维度 | 数值 |
|---|---|
| `chunk_type=other`（低价值） | 99,306（**30.9%**） |
| `chunk_type=evaluation/differential/red_flag` | 130,756 / 87,008 / 3,838 |
| content `<120` 字符（碎片） | 28,265（**8.8%**） |
| `entry_type=syndrome_entry` | 320,049（99.7%） |

PMC-OA 单源 317,710：useful（diff/red/eval）218,687，其中 ≥120 字符 198,996（跨 5,437 篇）。**`--useful-only` 几乎未削减 PMC**（合并后仍 317,710 全入），与命令注释暗示的「筛选」不符。

**优化建议（基于组成分析）**：IMP-31 入索引应取 **useful ∧ ≥120 字符子集（≈200k）**，或 `--pmc-require-anchor` 子集，而非 321k 全量——后者使 ~31% `other` + 8.8% 碎片稀释检索，并使 FAISS 需多编码 ~32 万条 MiniLM 向量（显著算力）。**完整 recall A/B 待 IMP-31 重建 + IMP-54 评测尺子**；此处仅依据组成给出子集化方向。

#### 1.10.5 【更正】PMC `syndrome_anchor` = 标题原文，非归一化综合征；「2,421 症状入口核心」偏乐观

**实测**：5,765 篇 PMC 的 `syndrome_anchor` 几乎一一对应文章标题（distinct anchor 5,717 ≈ distinct article 5,765）。其中含明确非临床假阳性（*"IoT Cloud Platforms"*、*"Machine Learning … Credit Risk"*、*"Digital Twin … Transportation"*），明确非临床约 **1–2%**（不算严重污染）；但仅 ~36% 标题含显式临床/症状词，**约 63% 标题无显式临床或症状 token**——多为**疾病入口综述**而非症状入口。

**更正**：§1.6.3「推荐 RAG 核心 2,421 篇」的判据是「anchor 非空 ∧ useful chunk」，而 anchor=标题恒非空，故该指标**高估可用症状入口产出**。应改判据为「标题/anchor 经**临床实体归一（IMP-58）**命中症状/综合征概念」。这进一步印证 §14.3（实体归一）与 §14.4（综合征 crosswalk）的必要性——`syndrome_anchor` 不能直接当综合征键用。

#### 1.10.6 对既有规划的影响（修订优先级再确认）

上述更正**不推翻** §13/§14 的方向，但**强化** IMP-31 的卡点地位并细化其规格：

1. **IMP-31（P0 卡点）**：重建索引时①并入 cpg_chunks 的 **useful∧≥120 子集**；②**写入 chunk 元数据字段**（否则 §1.8.2 闭包/门控继续空转）；③评估 32 万级向量的 FAISS 重编码成本，必要时先 TF-IDF 验证再上稠密。
2. **IMP-58/59 前移**：因 `syndrome_anchor`=标题不可直接用，归一/别名是「PMC 真正可用」的前提，应与 IMP-31 并行。
3. **IMP-30 补全**：NICE/协会 HTML 切 chunk 仍是独立待办（§1.5.3），不要因「已抓取镜像」误判为已整合。
4. **新源边际价值须先证后投**（规划最优性提醒）：同一孤立实验中，**现有 StatPearls+Textbooks 索引对多数综合征已给出可用 DDx 块**——如 `hypercalcemia` 命中 *Hypercalcemia of Malignancy > Differential Diagnosis*、*Hyperparathyroidism > Differential Diagnosis*；`jaundice` 命中 *Evaluation of Jaundice in Adults*。故新源（尤其 32 万级 PMC）相对现有索引的**边际召回增益尚未证明**。建议次序：先用 **IMP-54 oracle 评测**在「现有索引 vs +useful 子集」上量化边际 recall，再决定是否承担 32 万级稠密重编码——避免在未证增益前过度投入全量 PMC 索引。

---

```text
┌─────────────┐   ┌──────────────┐   ┌─────────────┐   ┌──────────────┐   ┌─────────────────┐
│ 1. Ingest   │ → │ 2. Parse     │ → │ 3. Chunk    │ → │ 4. Index     │ → │ 5. Retrieve +   │
│ manifest    │   │ 格式归一化    │   │ 语义单元切分 │   │ 向量/稀疏索引 │   │ Extract         │
└─────────────┘   └──────────────┘   └─────────────┘   └──────────────┘   └─────────────────┘
     已有              部分已有            待建              可复用              可复用+扩展
```

**设计原则**：

1. **Manifest 为唯一入口**：每条 chunk 必须能追溯到 `manifest.id`、`sha256`、`license_note`。
2. **先归一化再切分**：PDF/HTML/PubMed 先变成带章节路径的 plain text 或 Markdown-like 结构。
3. **检索与抽取分离**：RAG 只负责召回；结构化字段用规则 + 小模型/LLM 在**短上下文**上抽取。
4. **分层语料**：CPG 原文（权威）与 StatPearls/MedlinePlus（综述）分 index 或分 `source_tier` 字段，避免患者向摘要覆盖指南推荐强度。

---

## 3. 各格式解析策略

### 3.1 HTML（~1364 条）

**现状**：`scripts/download_open_cpg.py` 用 `VisibleTextExtractor` 做可见文本抽取，结果在 `data/cpg/text/<source>/`。

**局限**：

- 导航栏、登录壳（AAN、ACC SPA）污染正文；
- **NICE 公开 HTML**（`nice-ddx-*`）：`VisibleTextExtractor` 常保留 `stacked-nav` 面包屑（`You are here: Home NICE Guidance…`），稀释 TF-IDF/embedding 信号——`build_cpg_chunks.py` 应对 NICE 源优先 main-content 抽取（§1.4.4）；
- 列表/表格结构丢失；
- ACOG 等多为摘要层，非全文。

**改进建议**（按优先级）：

| 手段 | 适用 | 说明 |
|---|---|---|
| 主内容区启发式 | 大多数学会站 | 优先 `<main>`、`<article>`、`.content`；剔除 nav/footer |
| 站点模板 | IDSA、SCCM、ACOG | 针对已下载 HTML 统计 DOM 模式，写轻量 extractor |
| Readability / trafilatura | 通用 fallback | 比裸 `HTMLParser` 更少噪声 |
| 保留 URL + 标题 | 全部 | 即使正文差，metadata 仍可支撑「发现层」检索 |

### 3.2 PDF（~15 附件 + NCCN 受限层）

**现状**：`pypdf` 按页线性抽取，页间插入 `--- page N ---` 标记。

**局限**：

- 双栏排版导致行序错乱；
- 表格、流程图、推荐分级表常不可读；
- 扫描版 PDF 无 OCR 则几乎无文本。

**改进建议**：

| 层级 | 工具 | 成本 | 适用 |
|---|---|---|---|
| L0 | `pypdf`（已有） | 低 | 文字型 PDF、先跑通管道 |
| L1 | **pdfplumber** / PyMuPDF | 中 | 简单表格、保留坐标 |
| L2 | **GROBID**（TEI XML） | 中高 | 期刊型指南（PMC PDF、Eur Heart J） |
| L3 | **Marker** / Nougat / OCR | 高 | 扫描件、复杂版式 |

**推荐策略**：对 manifest 中 `access == public_pdf` 或 PMC 全文优先跑 GROBID；失败回退 `pypdf`。

### 3.3 PubMed / Europe PMC 摘要页（~535 条 `public_html_index`）

**现状**：URL 多为 `pubmed.ncbi.nlm.nih.gov/{pmid}/` 或 PMC 全文。

**策略**：

- **有 PMC 全文**（ACC/AHA、ESC、ASH、SSC 等 `*_pm__` / `*_epmc__`）：索引 PMC HTML/PDF，**不要只索引摘要页**。
- **仅摘要**：chunk 标注 `content_tier: abstract_only`；可用于实体发现，**不用于**强推荐抽取。
- **补全**：从 `data/cpg/api/*_guideline_index_latest.jsonl` 按 PMID 批量拉 OA 全文（Europe PMC OA API）。

### 3.4 已结构化源（直接并入）

| 源 | 路径 | 接入方式 |
|---|---|---|
| MedlinePlus | `data/poc/medlineplus/processed/medlineplus_topic_chunks_latest.jsonl` | 字段已齐；**POC 仅**，禁止默认并入 `cpg_chunks`（Recall@10 −2%，§1.5.3.1） |
| StatPearls | `data/corpus/statpearls/statpearls_chunks.jsonl` | 已有 367k 段，保持独立 corpus 或 `source_tier: review` |
| NCCN 受限 | `data/cpg/restricted/nccn/` | 仅本地研究账号；chunk 必须 `license_note: restricted_login_pdf`，**不与开放 index 混用** |

---

## 4. 指南专用切分（Chunking）

StatPearls 按 **段落 + 章节标题** 切分（`build_statpearls_corpus.py`）。CPG 需要**保留临床语义单元**，建议：

### 4.1 切分单元

1. **Recommendation 块**（最高优先级）：编号推荐句、Class/Level 标记。
2. **章节**：Introduction / Diagnosis / Management / Special populations。
3. **表格行**（若解析成功）：检验 → 适应证 → 证据等级。
4. **Fallback**：512–1024 token 滑动窗口，overlap 64–128，带 `section_path` 前缀。

### 4.2 章节检测启发式

对 plain text 匹配：

```text
^(Recommendations?|Summary of recommendations|Diagnostic|Management|Treatment|Definition)
^\d+(\.\d+)*\s+[A-Z]
^(Class [I|II|III]|Level [A|B|C]|GRADE)
```

HTML 源优先用 `<h1>`–`<h4>` 构建 `section_path`（与 StatPearls 的 `title: "Article > Section"` 对齐）。

### 4.3 统一 Chunk Schema（建议）

写入 `data/cpg/processed/cpg_chunks.jsonl`，每行示例：

```json
{
  "id": "acc_aha_acs_2025_pmc__rec_12",
  "source_id": "acc_aha_acs_2025_pmc",
  "source": "ACC/AHA",
  "parent_manifest_id": "acc_aha_acs_2025_pmc",
  "section_path": "Acute Coronary Syndromes > Recommendations > Antiplatelet Therapy",
  "chunk_type": "recommendation",
  "title": "2025 ACC/AHA Guideline for ACS",
  "content": "...",
  "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12907536/",
  "clinical_area": ["cardiology", "ACS"],
  "sha256": "...",
  "license_note": "open_pmc",
  "content_tier": "full_text",
  "tokens": 420
}
```

**字段说明**：

- `chunk_type`: `recommendation` | `diagnostic` | `differential` | `red_flag` | `background` | `table` | `other`
- `content_tier`: `full_text` | `abstract_only` | `index_page`
- `license_note`: 与 manifest 一致，下游 RAG 必须过滤

### 4.4 建议脚本（待实现）

```text
scripts/build_cpg_chunks.py      # manifest + WikEM + PMC-OA + Merck → cpg_chunks.jsonl（默认不含 MedlinePlus / abstract_only）
scripts/build_cpg_rag_index.py   # 合并 cpg_chunks → FAISS/TF-IDF（MedlinePlus 仅 ablation，见 §1.5.3.1）
```

`build_cpg_chunks.py` 应：

1. 读 `manifest_latest.jsonl`，过滤 `status == ok` 且 `text_path` 非空；
2. 按 `access` / 扩展名选择 parser；
3. 输出 chunk + 统计（recommendation 块占比、空 chunk 率）。

---

## 5. 索引与检索

### 5.1 复用现有 Layer 3 基础设施

项目已实现（`src/agentclinic_tree_dx/knowledge/rag_retriever.py`）：

- **TF-IDF**（`scripts/build_tfidf_index.py`）：493k 文档，~100s 构建，**无 GPU 依赖**，适合迭代。
- **FAISS 稠密**（`scripts/build_rag_index.py`）：MedCPT / BiomedBERT / MiniLM。
- **查询 API**：`search()`、`search_for_disease()`、`search_for_differential()`、`extract_lr_from_snippets()`。

### 5.2 CPG 索引方案

**方案 A（推荐起步）**：**多 corpus 合并索引 + metadata 过滤**

```text
data/corpus/rag_index/
  metadata.jsonl    # StatPearls + textbooks + cpg_chunks（不含 MedlinePlus / abstract_only）
  config.json       # sources: ["statpearls","textbooks","cpg"]
  tfidf_matrix.npz  # 或 faiss.index
```

每条 metadata 增加：

```json
{
  "corpus": "cpg",
  "source_tier": "guideline",
  "chunk_type": "recommendation",
  "clinical_area": ["cardiology"]
}
```

检索时：

```python
# 伪代码
retriever.search(
    query=f"{syndrome} differential diagnosis red flags",
    top_k=20,
    filter={"source_tier": "guideline", "chunk_type": ["recommendation", "differential", "red_flag"]},
)
```

**方案 B**：**独立 CPG 索引**（`data/cpg/rag_index/`），BranchKnowledge 管道专用；StatPearls 仍作 Layer 3 fallback。隔离清晰，但需维护双索引。

### 5.3 混合检索（Hybrid RAG）

指南文献含大量**标准术语**（ICD、检验名、Class I），建议：

| 通道 | 作用 |
|---|---|
| **Sparse（BM25/TF-IDF）** | 精确匹配指南术语、缩写、推荐编号 |
| **Dense（MedCPT）** | 语义匹配「综合征 + 鉴别域」 |
| **融合** | RRF（k=60）或 weighted sum |

与 `EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md` §Layer 3 设计一致；CPG 并入后 sparse 通道权重可适当提高。

### 5.4 查询构造（面向 mandatory_coverage）

针对综合征根节点 \(S\) 与证据 \(E\)，建议**多 query 模板**（分别检索后去重）：

```text
Q1: "{S} differential diagnosis causes"
Q2: "{S} red flags urgent referral emergency"
Q3: "{S} initial diagnostic evaluation tests"
Q4: "{E} {S} clinical presentation guideline"
```

对每条命中 chunk，用 `clinical_area` / `source` 与 `syndrome_axis_map` 做**专科过滤**，减少无关专科指南噪声（如用「leukocytosis」误召肿瘤 CPG）。

---

## 6. 从 RAG 片段到结构化字段

RAG 输出的是**文本片段**；结构化抽取应**短上下文、强 schema**。

### 6.1 两阶段模式

```text
Retrieve (top-k chunks, ~2–8k tokens)
    ↓
Compress（可选：LLM 逐 chunk 一句话摘要 + 来源）
    ↓
Extract（JSON schema 填充）
    ↓
Validate（UMLS/MONDO 实体链接、证据等级格式、license 检查）
    ↓
Write KB / payload.branch_knowledge
```

### 6.2 抽取 Schema 示例

```json
{
  "syndrome_query": "pancytopenia with blasts",
  "mandatory_domains": [
    {"domain_label": "Acute leukemia", "rationale": "...", "citations": ["acc_aha_pm__..."]},
    {"domain_label": "MDS / bone marrow failure", "rationale": "...", "citations": ["ash_ba_epmc__..."]}
  ],
  "cant_miss": [
    {"condition": "Acute promyelocytic leukemia", "trigger": "DIC, severe coagulopathy", "citation": "..."}
  ],
  "recommended_tests": ["peripheral smear", "bone marrow biopsy", "cytogenetics"],
  "evidence_grades": [{"statement": "...", "grade": "Class I", "source_id": "..."}]
}
```

### 6.3 抽取手段对比

| 方法 | 优点 | 缺点 | 适用 |
|---|---|---|---|
| **规则 + 正则** | 快、可审计 | 覆盖有限 | Class I/II、编号推荐 |
| **LLM + JSON schema** | 灵活 | 幻觉、需 citation 约束 | mandatory_coverage、cant_miss |
| **检索增强抽取** | 每字段带 citation | 两次 LLM 调用 | 生产 KB |
| **专用 IE 模型** | 稳定 | 需标注数据 | 规模化后 |

**防幻觉约束**（必须）：

- 抽取结果每条陈述绑定 `citation: chunk_id`；
- LLM prompt 要求「仅使用 Context 中的句子；无法找到则填 null」；
- 后验：抽取 span 与 chunk 做 substring / fuzzy match。

### 6.4 与现有 LR 提取衔接

`RAGRetriever.extract_lr_from_snippets()` 已通过 `lr_quant.quantify_snippet` 从 StatPearls 抽 LR。CPG chunk 接入后**同一函数可复用**，但需注意：

- 指南中 LR 数字少于教科书；
- 更多 **Class/Level** 定性证据，应映射到 `confidence: rag_qualitative` 而非伪造 LR。

---

## 7. 与 BranchCreator 知识管道的集成

当前设计（`SYNDROME_TO_L1_BRANCH_KNOWLEDGE_RESEARCH.md`）：

```text
syndrome + vignette evidence
  → _build_branch_candidates (T1/T2 结构化 KB)
  → payload.branch_knowledge { mandatory_coverage, cant_miss, ... }
  → BranchCreator LLM
```

**CPG RAG 建议插入点**：

```text
T1/T2 结构化 KB（LR cache、PrimeKG、markers）
        ↓ miss / low coverage
T3a  CPG RAG（本方案：指南 chunk 检索 + 域/ cant_miss 抽取）
        ↓
T3b  StatPearls RAG（现有 Layer 3，综述/鉴别描述）
        ↓
T3c  PubMed live（可选，见 pubmed_retriever.py）
```

**模式 A（软锚定）兼容**：CPG 抽取结果写入 `branch_knowledge.mandatory_coverage` 时保持**域粒度**（broad family），不把「急性髓系白血病」直接当 L1 label。

---

## 8. 质量与评估

### 8.1 管道指标

| 指标 | 目标 | 测量 |
|---|---|---|
| 可切分率 | >90% 有 text 的 manifest 产出 ≥1 chunk | build 日志 |
| Recommendation 召回 | 全文指南中 ≥60% 含 `chunk_type=recommendation` | 抽样人工 |
| 检索 MRR@10 | 综合征 query 命中相关专科指南 | 50 条标注 query |
| 抽取 citation 合法率 | >95% citation 可定位到 chunk | 自动校验 |
| mandatory_coverage 命中率 | 金标域 ∈ 抽取域 | 9-case / MedBullets 子集 |

### 8.2 已知风险

| 风险 | 缓解 |
|---|---|
| PDF 表格乱码 | GROBID / 跳过大 table chunk |
| 摘要当全文用 | `content_tier` 过滤 |
| 版权 | manifest `license_note` + 禁止混用 NCCN 受限 |
| 索引污染（导航 HTML） | 主内容抽取 + 最小长度阈值 |
| LLM 幻觉推荐 | citation 强制 + 人工 spot check |

---

## 9. 实施路线图

### Phase 0 — 最小可行（1–2 天）

- [x] `scripts/build_cpg_chunks.py`：五源合并（WikEM + PMC-OA + manifest + Merck）；`--useful-only` 排除 `abstract_only`；合并阶段剔除 bot_gate
- [x] NCBI 浏览器校验页剔除（§1.5.3.2）：`audit_manifest_bot_gate.py` + `is_browser_gate_text()`
- [x] ~~合并 MedlinePlus~~ → **有害，禁止默认**（§1.5.3.1；保留 POC 层）
- [ ] 扩展 `build_tfidf_index.py` 读取 `cpg_chunks.jsonl`
- [ ] 手工 spot check 20 条（IDSA、SCCM、ESC PMC）

### Phase 1 — 检索验证（3–5 天）

- [ ] 50 条综合征 query 标注集 + MRR 评测脚本
- [ ] Hybrid（TF-IDF + 可选 FAISS）+ `clinical_area` 过滤
- [ ] `BranchPayloadBuilder` 原型：RAG → LLM 抽 `mandatory_coverage`（带 citation）

### Phase 2 — PDF / 全文增强（1–2 周）

- [ ] GROBID 批处理 PMC PDF
- [ ] Europe PMC OA 补全摘要-only 条目
- [ ] `chunk_type` 分类器（规则或轻量模型）

### Phase 3 — 生产 KB（持续）

- [ ] 与 `_build_branch_candidates` 集成（T3a 层）
- [ ] 增量更新：manifest `sha256` 变化 → 只重建受影响 chunk
- [ ] 人工 curated 覆盖层（高 stakes 综合征）

---

## 10. 命令速查（当前仓库）

```bash
# 已有：StatPearls / TF-IDF RAG
python scripts/build_statpearls_corpus.py
python scripts/build_tfidf_index.py
# 或
python scripts/build_rag_index.py --model ncbi/MedCPT-Article-Encoder

# 已有：CPG 镜像
python scripts/expand_open_cpg_seed.py
python scripts/download_open_cpg.py --skip-existing --insecure --sleep 0.35

# 已有：MedlinePlus chunks
python scripts/download_medlineplus_bulk.py
python scripts/parse_medlineplus_topics.py

# CPG chunk 管道（§1.5.3）
python scripts/audit_manifest_bot_gate.py          # 报告 → data/cpg/eval/manifest_bot_gate_report.json
python scripts/build_manifest_cpg_chunks.py --useful-only
python scripts/build_cpg_chunks.py --useful-only

# 待建：CPG RAG 索引
# python scripts/build_cpg_rag_index.py

# NICE Syndication（需 NICE_API_KEY；凭据见 OPEN_CPG_DOWNLOADS.md §NICE）
# export NICE_API_KEY=...
# python scripts/fetch_nice_syndication_index.py --credentials-json "/data3/wanghongyi/Shanghai Jiao Tong University.json"
# python scripts/build_nice_api_seed.py
# python scripts/run_cpg_api_pipeline.py --skip-pubmed --skip-europepmc --skip-esmo --skip-medlineplus --download-nice

# NICE 公开 HTML（canonical，无需 API-Key）
python scripts/crawl_nice_published_ddx.py --use-cache-list --all-sidebar --download
# legacy curated（勿用于 NICE 自动化路径）：
# python scripts/extract_nice_public_chapters.py
```

---

## 11. 参考文献与外部实践

| 主题 | 参考 |
|---|---|
| 医学 RAG 评测 | MedRAG、MIRAGE benchmark |
| 指南结构化 | WHO SMART Guidelines、NICE syndication JSON |
| PDF 学术解析 | GROBID、PMC JATS/NLM XML |
| 混合检索 | RRF (Cormack et al.)；MedCPT bi-encoder |
| 本项目 Layer 3 | `EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md` §11.5、§23 |
| 分支 KB 字段 | `SYNDROME_TO_L1_BRANCH_KNOWLEDGE_RESEARCH.md` |

---

## 12. 结论

1. **镜像已完成，结构化未开始**：1912 条 CPG 大多有 `text_path`，但尚未进入 RAG 索引；**首要任务是 `cpg_chunks` 管道**。
2. **不要指望单次 RAG 读 PDF**：解析（PDF/HTML）→ 章节切分 → 索引 → 检索 → **独立结构化抽取**，五步缺一不可。
3. **优先全文、标注 tier**：PMC/官网 HTML > PubMed 摘要；抽取 mandatory_coverage 时过滤 `abstract_only`。
4. **复用现有 Layer 3**：扩展 `metadata.jsonl` 与 `RAGRetriever` 即可，无需重写检索栈。
5. **与 StatPearls 分工**：CPG = 权威推荐与分级；StatPearls = 鉴别描述与症状路径；MedlinePlus 保留 POC、**不**进统一 CPG 索引；合并索引时用 `source_tier` 区分，且排除 `abstract_only`。

下一步实现建议从 **`scripts/build_cpg_chunks.py` + TF-IDF 索引扩展** 开始，用 9-case benchmark 验证「综合征 → mandatory_coverage 域」是否因 CPG 而提升召回。

**实施入档**：与本仓库分支知识自动化（pathognomonic / mechanism_to_disease / MECE / UnionAxisMap）的统一 Phase 排期、TODO 索引与验收指标见 [`BRANCH_KNOWLEDGE_IMPLEMENTATION_PLAN.md`](BRANCH_KNOWLEDGE_IMPLEMENTATION_PLAN.md)（§4 Phase 3 = 本文 Phase 0–3 对齐项）。NICE 字段结构、章节 DDx 分布与 RAG 集成阻塞项见 **§1.4**。

---

## 13. 面向「防漏关键方向」的整合增强（2026-06-24 续研）

> **目标重述**：在**无 BMJ Best Practice / UpToDate / DynaMed** 等商业「approach-to-symptom」库的前提下，由综合征（根节点）+ 证据稳健生成少数 L1 分支，并用外部知识库**保证正确诊断所在方向不被遗漏**。本节是对 §1–§12 的补强，聚焦四个此前未充分展开的薄弱面：**①数据源的开放许可现实、②CPG 在管道中的正确角色、③面向召回的检索、④覆盖保证（而非平均检索质量）的评测与运行时门**。

### 13.1 关键再定位：CPG 是「覆盖审计器 / 实体富集器」，不是「轴定义器」

CPG 文献（NICE 指南、IDSA、ACC/AHA、ESC…）的组织方式是**「已确诊疾病 X 如何评估/治疗/转诊」**，而非**「面对综合征 S 有哪些鉴别方向」**。一篇 ACS 指南告诉你 ACS 怎么管理，却**不枚举「胸痛」的 DDx 轴**。因此：

- **L1 分类轴 + MECE 域**（`l1_classification_axis` / `mandatory_coverage`）应主要由 **curated `syndrome_axis_map` + LLM-axis（UnionAxisMap A∪C）** 决定；
- **CPG RAG 的最佳产出**是：① `cant_miss` / red-flag / 转诊阈值（指南的强项），② 每个域下的 `candidate_entities`（疾病实体富集），③ 证据分级（Class/Level）。
- **闭环缺口**：CPG 抽出的是**具体疾病/红旗实体**，仍需经 `disease→domain` 投影（MONDO/SNOMED 祖先 + curated overrides，见 `SYNDROME_TO_L1_BRANCH_KNOWLEDGE_RESEARCH.md` §11.5）归位到 MECE 域，并由**覆盖审计**判定是否已被 `mandatory_coverage` 覆盖。

> **设计含义**：不要期望从 CPG「读出」分类轴；应让 CPG 作 **path-B coverage auditor**（SYNDROME §11.4）——检索到的高召回实体若投影不进任何 mandatory 域，则产出 `schema_gap` 并注入 residual 域，**绝不静默丢弃**。

### 13.2 开放许可现实清查（决定可用源边界，2026-06-24 核实）

最理想的「症状/综合征入口 + 显式 DDx 段」point-of-care 资源**几乎全部闭源或限制复用**。实测结论：

| 源 | 结构是否「症状入口 + DDx 段」 | 开放复用许可 | 对本项目可用性 |
|---|---|---|---|
| BMJ Best Practice / UpToDate / DynaMed | ✅ 黄金标准 | ❌ 商业，需企业授权 | **排除**（§OPEN_CPG_DOWNLOADS 已述） |
| **NICE CKS**（370 主题 / ~1000 场景，含 assessment·diagnosis·referral） | ✅ **最贴合目标** | ❌ **非开放**：IP 属 Agilio Software，**不在 NICE 开放内容许可内**，不走 syndication API；仅 NHS/学生免费，大学/商业需 Agilio 授权 | **排除/需授权**（易被误当 NICE 开放数据，特此澄清） |
| **AAFP**（"Diagnostic approach to…" / "Differential diagnosis of…"） | ✅ 强 | ❌ 全文版权保留，复用需付费授权 | **排除/需授权** |
| **Merck Manual Professional**（"Approach to the patient with…"） | ✅ 强 | ⚠️ 免费**阅读**，但 reuse/posting/入库需书面许可 | **在线不入库**（`msd_child__` 仅 metadata）；**已购 19e PDF 可内用 RAG**（§1.9，`Merck-Manual-19e`） |
| **WikEM**（EM 鉴别 + can't-miss） | ✅（急诊向） | ⚠️ **CC BY-SA 3.0**，但站点附 **AI/ML 使用限制条款**（训练/微调/评测） | **检索可用、需署名 + ShareAlike；AI/ML 条款需法务确认**（RAG 检索≠模型训练，学术非商业较稳妥） |
| **StatPearls**（含 "Differential Diagnosis" 段） | ✅ 部分 | ✅ 开放（MedRAG/NXML） | **已在库**（367,799 段） |
| 开放教科书语料 | ✅ "Approach to" 章 | ✅ | **已在库**（Textbooks corpus） |
| **NICE 开放指南**（NG/CG/DG） | ⚠️ 多为疾病/管理组织；**NG12/CG95/「fever in under 5s」类症状指南是例外** | ✅ 开放内容许可 | **已在库**（1320 章） |
| **WHO / CDC** | ⚠️ 部分症状路径 | ✅（US-gov / WHO 开放） | 已部分在库 |
| **PMC Open Access 综述**（"approach to X" / "differential diagnosis of X" / "evaluation of X"[ti]） | ✅✅ **直接 DDx 组织** | ✅ **PMC-OA 子集开放** | **新机会，见 §13.3** |
| Wikipedia / WikiDoc | ⚠️ 不稳定 | ✅ CC BY-SA | 兜底发现层 |

> **战略结论**：开放许可下**不存在可整库镜像的「BMJ-BP 式症状→DDx」资源**；覆盖保证**不能靠单源**，必须 = **开放源集成 + 症状入口子集挖掘 + KG/本体覆盖审计 + curated can't-miss 下界**。这把目标从「找到那一个库」改写为「用多源拼出覆盖，并用审计证明无漏」。

### 13.3 在已镜像/开放语料中挖掘「症状入口 + DDx 组织」子集

与其期待新库，不如**在现有开放语料里筛出真正 DDx 组织的片段**，建 `syndrome_entry` 子索引并优先检索：

1. **NICE 症状指南**：NG12（suspected cancer，按症状/部位组织）、CG95（chest pain）、fever in under 5s、headache、CKS-外的 NG 系列——§1.4.2 已证 `Recommendations` + 「按症状组织」章是 mandatory_coverage/cant_miss 主载体。
2. **StatPearls `Differential Diagnosis` / `Evaluation` 段**：已在库，按 section 标题打 `chunk_type=differential`。
3. **PMC Open Access 综述定向采集（新增，详见 [`OPEN_CPG_DOWNLOADS.md`](OPEN_CPG_DOWNLOADS.md) PMC-OA 抓取指引）**：Europe PMC / PubMed 发现层 query 标题含 `"approach to"` / `"differential diagnosis of"` / `"evaluation of"` / `"causes of"` 的 OA 综述；全文优先 **Europe PMC `fullTextXML`（JATS）** 或 **[BioC API for PMC OA](https://www.ncbi.nlm.nih.gov/research/bionlp/APIs/BioC-PMC/)**（`BioC_json/{PMCID}/unicode`，passage 含 `section_type` + document 级 `license`）。是 CKS/AAFP/BMJ 的合规替身。交付 `pmc_oa_ddx_index.jsonl`（IMP-50，**已实施**）。
4. **Merck Manual 19e（已购 PDF，§1.9）**：23 章 `approach to …` → `entry_type=syndrome_entry`；`scripts/build_merck_manual_corpus.py` → `data/corpus/merck/merck_manual_19e_chunks.jsonl`（**9,629** chunks，内部 RAG only，禁止再分发）。
5. **WikEM**（CC BY-SA，急诊 can't-miss）：`wikem_ddx_chunks.jsonl`（**1,055** useful chunks，§1.7）。
6. **子索引标记**：chunk 增 `entry_type: syndrome_entry | disease_entry`；检索 mandatory_coverage 时对 `syndrome_entry` 加权（boost），降低「疾病管理」噪声。

**面向覆盖的 query 扇出**（替换/补充 §5.4 的 Q1–Q4，强制跨轴召回，避免只命中显著轴）：

```text
按 syndrome S 与 UnionAxisMap 给出的候选轴逐一发问：
  Qmech : "{S} differential diagnosis by mechanism / etiology causes"
  Qanat : "{S} anatomical / organ-based differential"
  Qurg  : "{S} red flags can't miss emergency must not miss"
  Qwork : "{S} initial diagnostic evaluation approach workup"
  Qsymptom-entry: "approach to {S}" / "differential diagnosis of {S}"   ← 命中 §13.3 子集
对每路 top-k 检索后合并去重 → 喂覆盖审计（§13.5）。
```

### 13.4 面向召回的检索增强（grounded）

「防漏」是**召回**问题，不是平均精度问题。文献支持的两阶段法（CMIRB / AutoMIR 等医学 IR 工作）：

| 阶段 | 手段 | 对召回的作用 | 备注/代价 |
|---|---|---|---|
| 召回 | **Hybrid：BM25/TF-IDF（术语/缩写/推荐编号）+ MedCPT dense（PubMed 检索日志预训练）**，高 `top_k`（如 50–100） | 广撒网，先把正确域片段纳入候选 | 已有 Layer 3 基础设施（§5.1），仅需 corpus=cpg |
| 重排 | **MedCPT cross-encoder**（或 BGE-reranker）对候选精排 | 在不牺牲召回前提下提精度，确认临床相关 | 单独 reranker，开销可控 |
| 查询扩展 | **HyDE / Query2Doc**：LLM 生成「假想 DDx 文档」再嵌入检索 | 弥合「短综合征 query ↔ 复杂指南正文」语义鸿沟，**专治低召回**（HyDE 文档明示适用低 Recall + 域外语料） | ⚠️ 防幻觉：仅用于覆盖召回，**不**用于数值/实体精确字段；HyDE 约 8 次 LLM 调用，成本高 |
| 进阶 | **SL-HyDE**（自学习，无需标注；CMIRB 上 NDCG@10 较 HyDE +4.9%）、**CHR 对比假设检索**（同时生成「目标假设」与「貌似合理但错的 mimic 假设」，相减抑制 hard-negative DDx） | 减少「貌似合理但错误」的鉴别项污染候选 | 二期可选；CHR 较 HyDE token 成本低约 9.7× |

**落地建议**：起步只加 **MedCPT dense + cross-encoder 重排 + 跨轴 query 扇出**（确定性、低风险、对召回增益直接）；HyDE 作为**低置信兜底**（当 hybrid 的 query-doc 相似度低于阈值时才触发），并强制 cross-encoder 后验 + citation 接地，规避幻觉。

### 13.5 覆盖保证：oracle-union 评测 + 缺口归因（而非只测 MRR）

§8.1 的 MRR@10 衡量「检索好不好」，但目标是「会不会漏」。补两类专测：

1. **`eval_coverage_oracle.py`（新增，IMP-54）**：对 9-case + MedBullets 子集，取**所有源并集**检索结果，判定 `gold_entity` 的 L1 域是否出现在任一源召回中。报告：
   - **oracle-union gold-domain recall**（理论上界——能不能漏；若上界都不足，说明缺源，不是缺检索）；
   - **逐源边际贡献**（去掉某源后 recall 降多少 → 决定优先补哪类源）；
   - **缺口归因**（漏的 case 属于：无任何源覆盖 / 有覆盖但检索没召回 / 召回了但投影失败）。
2. **运行时实体→域可达性门（IMP-55）**：检索/抽取得到的高召回实体，经 `disease→domain`（MONDO/SNOMED 祖先 + PrimeKG + curated overrides）投影；**若投影不进任何 mandatory 域**：先试最近域，否则**注入 `residual / other-critical` 域并标 provenance**，确保 LLM 不能把正确方向删掉（呼应 §31.13 硬约束 2「覆盖永不低于基线」、SYNDROME §4.3 Step 5）。

> 二者合一即「防漏」的可证明机制：oracle-union 给上界，可达性门给运行时下界。
>
> **branch-gen 六层展开（A–F 成因表、与 Step 0–3 对照、解锁序 vs 诊断序）**：**§17.2.1**。

### 13.6 专设 can't-miss 层（不依赖概率检索）

危险方向**不能**靠 top-k 排序保证（低概率但致命者会被挤掉）。建 curated `data/knowledge_raw/cant_miss_by_syndrome.json`（IMP-56），来源**仅限可复用开放源**：

- **WikEM**（CC BY-SA，急诊「can't miss」列表；需署名 + ShareAlike，AI/ML 条款先法务确认）；
- **NICE 开放指南的转诊/疑癌标准**（NG12 等，开放许可）；
- **CDC / WHO** 急症阈值；
- LLM 起草 + **逐条 citation 接地核验**（§6.3 防幻觉约束），人工抽检合入。

该层作为 `mandatory_coverage` 的**硬下界**：无论检索结果如何，综合征命中即强制注入对应 can't-miss 域。

### 13.7 主动学习闭环（benchmark/log → 缺口 → 候选种子）

复用 SYNDROME §11.8：case log 中 `gold wrong / branch missing / LR MISS / uncovered gold entity` → 归因到层（§13.5 缺口归因）→ 自动起草 `schema_gap_report` + 候选 projection override / can't-miss 条目，进人工审核队列。把「漏」转成可持续修复的 PR 流，而非一次性手写。

### 13.8 新增数据源与任务清单（接入 IMP-* 编号）

| ID | 任务 | 交付物 | 许可/风险 | 关联 |
|---|---|---|---|---|
| **IMP-50** | PMC-OA「approach-to / differential-diagnosis-of」综述定向采集 | `data/cpg/api/pmc_oa_ddx_index_latest.jsonl` + `data/cpg/processed/pmc_oa_ddx_chunks.jsonl` | PMC-OA 开放 | §1.6、§13.3；**已实施**（index 5950 / BioC 5869 / chunks 87976；推荐 RAG 核心 **2421** 篇） |
| **IMP-51** | `entry_type`（syndrome_entry/disease_entry）标记 + 子索引 boost | `build_cpg_chunks.py` 字段 + 检索权重 | — | §13.3；WikEM/PMC/Merck **已标记**，检索 boost **待办** |
| **IMP-52** | 跨轴 query 扇出（Qmech/Qanat/Qurg/Qwork/Qsymptom-entry） | `BranchPayloadBuilder` 查询层 | — | §13.4、§5.4 |
| **IMP-53** | MedCPT dense + cross-encoder 重排（HyDE 低置信兜底，带防幻觉门） | `RAGRetriever` 重排路径 | HyDE 成本/幻觉 | §13.4 |
| **IMP-54** | `eval_coverage_oracle.py`：oracle-union recall + 边际贡献 + 缺口归因 | 评测脚本 + 报告 | — | §13.5、§8 |
| **IMP-55** | 运行时实体→域可达性门 + residual 域注入 | `controller._build_branch_candidates` | — | §13.1/13.5、§31.13 约束2 |
| **IMP-56** | `cant_miss_by_syndrome.json`（WikEM/NICE/CDC 接地 + 抽检） | curated JSON + provenance | WikEM CC BY-SA + AI/ML 条款 | §1.7、§13.6；WikEM 部分 **`cant_miss_by_syndrome_wikem.json` 已自动化** |

> **优先级**：IMP-54（先量上界，决定是否缺源）→ IMP-55（运行时防漏门，立竿见影）→ IMP-50/51（补症状入口源）→ IMP-52/53（检索增强）→ IMP-56（can't-miss 下界）。其中 **IMP-54/55 不依赖新数据**，可与 §1.1 的 `build_cpg_chunks.py` 并行先行。

### 13.9 与许可红线一致的「不要做」清单

- ❌ 不爬取 / 不入库 **CKS、AAFP、Merck 在线版、BMJ BP、UpToDate、DynaMed** 全文作为 RAG 复用语料（仅可存 metadata/链接或走授权 API）；**已购 Merck 19e PDF 除外**（内部 RAG，禁止再分发，见 §1.9）；
- ❌ 不把 **WikEM** 内容用于**模型训练/微调/评测**（其 AI/ML 条款），检索复用须署名 + ShareAlike 并先确认；
- ✅ 可整库用：**StatPearls、开放教科书、NICE 开放指南、WHO/CDC、PMC-OA 综述**——覆盖保证主要依赖这五类 + 本体/KG 审计。

---

## 14. 三源抓取完成后的整合前沿（2026-06-25 续研）

> **背景**：PMC-OA（5,869 篇 / 317,710 chunks）、WikEM（147 页 / 1,055 chunks / 3,835 cant_miss 链接）、Merck 19e（9,629 chunks / 23 Approach 章）均已抓取、切分、修复（§1.6–1.9、§1.8.2）。**前沿已从「获取/解析」转移到「融合 + 索引 + 覆盖证明」**。本节针对「综合征→L1 分支防漏」目标，补 §13 之后**真正未落地**的五处空白，按对目标的杠杆排序。

### 14.0 现状定位（2026-06-25 实测核对）

| 维度 | 状态 | 证据 |
|---|---|---|
| 三源抓取 + 切分 | ✅ 完成 | §1.6–1.9 |
| 切分/门控修复（IMP-35、expand_ddx_siblings） | ✅ 完成 | `rag_retriever.expand_ddx_siblings()` 已实现；`cpg_chunk_gate.py` 读 `chunk_type` |
| **WikEM + PMC-OA 进入 RAG 索引** | ❌ **未落地** | `build_tfidf_index.py` 仅 load `statpearls/textbooks/merck`；`cpg_chunks.jsonl`（含 WikEM/PMC）**不在索引** |
| 跨源 DDx 融合 / 实体归一 | ❌ 未设计 | 无 `cant_miss_by_syndrome.json`（仅 `_wikem`）、无统一 DDx union |
| 综合征别名 crosswalk（root↔源 anchor） | ❌ 缺失 | `data/knowledge_raw/` 无 syndrome alias 表 |
| 覆盖评测尺子（IMP-54） | ❌ 待建 | §1.8.3 |

> **核心判断**：症状入口源已就位，但**两个新源（WikEM/PMC-OA）运行时不可检索**——这是当前一切召回增益的**前置卡点**，应把 IMP-31 从「索引扩展」升级为 **P0 解锁项**。否则 IMP-52/53/54 无法在新源上生效。

### 14.1 解锁卡点：把 `cpg_chunks` 真正并入索引（IMP-31，升 P0）

**问题**：`build_tfidf_index.py::load_chunks()` 硬编码三个 corpus 文件，**未读 `data/cpg/processed/cpg_chunks.jsonl`**。WikEM 1,055 + PMC-OA 317,710 已切好却查不到。

**最小落地**：

1. `load_chunks()` 增读 `cpg_chunks.jsonl`（或 `--useful-only --pmc-require-anchor` 子集，避免 317k 全量稀释）；
2. `config.json` `sources` 追加 `["cpg_wikem","cpg_pmc_oa","nice"]`，并为每 chunk 保留 `source_id / chunk_type / entry_type / syndrome_anchor / license_note`（检索后过滤与 boost 依赖这些字段，§13.3/§1.8.4）；
3. FAISS 路径（`build_rag_index.py`）同步；
4. 验收：综合征 query（如 "abdominal pain differential"）能召回 WikEM/PMC chunk，且 `expand_ddx_siblings` 可拉同篇闭包。

> 该项一旦完成，§13 的所有检索增益（query 扇出、重排、覆盖审计）才有数据可作用。

### 14.2 跨源 DDx 融合与一致性投票（IMP-57，新增）

现已有 **5 个重叠的症状入口源**（WikEM、PMC-OA、Merck、StatPearls、NICE），同一综合征会得到**粒度/同义/重叠各异**的 DDx 列表。当前无「按综合征聚合 + 去重 + 置信分级」的设计——而这正是 `mandatory_coverage` 与 `candidate_entities` 的直接上游。

**方案**：离线对每个 `syndrome_anchor` 聚合各源 DDx 实体 → 归一（§14.3）→ 去重 → **一致性投票打分**：

```text
entity_confidence(S, e) =
    Σ_source  w_source · 1[e ∈ DDx_source(S)]
  + cant_miss_bonus(e)            # WikEM/NICE red-flag 命中
  - single_source_penalty
分层：
  ≥2 源一致 + (Merck/NICE 等权威源之一)  → high  → 进 mandatory 候选
  单权威源 或 多弱源                      → medium → candidate_entities
  仅单弱源 / 仅 PMC 长尾                   → low    → 仅提示，不进 mandatory
```

复用 SYNDROME §11.10 既有打分骨架（text_ddx / ontology / phenotype / kg / runtime gap）；新增的是**「源间一致性」作为显式信号**——多源同现的鉴别方向漏掉风险最低，应优先保覆盖。产物：`data/knowledge_raw/ddx_union_by_syndrome.json`（generated，带 per-entity provenance）。

### 14.3 实体归一层：DDx mention → 规范概念（IMP-58，新增）

跨源融合、去重、`disease→domain` 投影、cant_miss 下界**全部依赖**把自由文本实体串（WikEM 3,835 个 wiki 链接、PMC/Merck DDx 短语）归一到规范 ID。文档目前仅标「待 UMLS 归一」，未定工具/流程。

**调研选型（2026-06-25）**：

| 工具 | 机制 | 适用 | 代价 |
|---|---|---|---|
| **scispaCy `umls`/`mesh` linker** | char-3gram 近邻（~3M UMLS 概念） | **推荐基线**：易集成、文档完善、本地无网络 | 精度中（字面匹配） |
| **QuickUMLS** | CPMerge 近似匹配 | 与 MetaMap 近似 recall、更快 | 需 UMLS 安装 |
| **SapBERT / BioEL** | 上下文向量 | 高精度难例 | 重，需模型 |
| **+ LLM 消歧层** | 候选 → LLM 选 | 给上述任一 +10~16 F1（文献） | 额外 LLM 调用 |

**落地建议**：以 **scispaCy UMLS linker 作基线**把实体串映射到 CUI（→ MONDO/SNOMED xref），对**模糊/多候选**项加 **LLM 消歧**（仅这部分，控成本）；输出 `entity_norm_cache.json`（mention→CUI/MONDO + 置信）。这一层是 §14.2 去重与 §13.5 可达性门（IMP-55）的公共前置。

> **注**：归一只用于**对齐与覆盖判定**，不改变 chunk 原文；检索仍走原始文本（保留同义召回）。

### 14.4 综合征词表 crosswalk：root label ↔ 源 anchor（IMP-59，新增）

**召回隐患**：RootSelector 输出的根标签（如 `AMS`）须能词面/语义命中各源 anchor 词表——WikEM chief complaint（`Altered mental status`）、Merck Approach 章标题（`Confusion and Delirium`）、PMC 标题综合征。三套词表**互不对齐**，纯词面 query 扇出（§13.3）会漏召回。

**方案**：建 `data/knowledge_raw/syndrome_alias_map.json`，把规范综合征 id ↔ {root 别名, WikEM anchor, Merck anchor, PMC 标题词, UMLS/SNOMED 同义词}。来源：① 各源已有的 `syndrome_anchor` 字段（自动收集）；② UMLS/SNOMED 同义词扩展；③ embedding 聚类发现近义（SYNDROME §11.2 路径 E）。检索前用该表把 root 归一并扩展为多别名 query，**直接提高症状入口召回**。

### 14.5 用源本身自举覆盖评测 silver-standard（强化 IMP-54）

IMP-54 需要 case→gold_entity→gold_domain 金标，纯手工标注成本高。**新机会**：三源对一个综合征的**跨源 DDx 并集（§14.2）即可作 silver-standard「期望 DDx 闭包」**：

- **召回上界量化**：检索 union 是否覆盖该 silver 闭包 → 直接得 oracle-union recall，而非只看 9-case 手工金标；
- **disease→domain 投影候选自举**：silver 闭包内实体经归一 + 本体祖先即生成 `disease_domain_projection.generated.json` 候选（SYNDROME §11.12 Phase 1），人工只审 diff；
- **缺口归因**：silver 内但任何源都没检索到 = 检索缺陷；silver 都没有 = 缺源（指引补哪类源）。

这把「金标从零标注」降级为「审核源自举的 diff」，与文档既定的「curated = reviewed generated」原则一致。

### 14.6 分支数量控制与排序：保覆盖但不爆炸

目标要「**几个**初步方向」。多源融合后实体数膨胀，若全提为分支会违反 SYNDROME §8.1（L1 控制在 3–7）且稀释后续 LR。建议：

- **mandatory floor**（cant_miss + ≥2 源一致域）**必保**；
- 其余按 **跨源频次 + 患病率先验**（年龄/性别人口学，复用既有 demographic prior）排序，取 top 形成 ranked optional；
- 过宽域延后到 L2（SYNDROME §4.3 软约束），避免 VINDICATE 式过覆盖（§9.3）。

### 14.7 轴冲突子分裂信号：从 CPG/Merck 抽取（服务目标第二要求）

目标第二条要求「**轴不能错**」——正确诊断不得落入与关键证据相反方向 LR 的分支（既往 CML vs blast crisis、分期子轴化问题）。Merck/PMC Approach 章与 NICE 常显式描述**子分层**（acute vs chronic、reactive vs neoplastic、compensated vs decompensated）。可从这些章节抽取 **sub-axis 提示**，喂给「分期子轴化」逻辑：当某子族症状 LR 与母族相反时，提示 BranchCreator 将其分裂为独立分支。这是 CPG 对**轴正确性**（而非仅覆盖）的增量贡献，此前 §13 未覆盖。

### 14.8 任务清单与修订优先级

| ID | 任务 | 交付物 | 状态 | 关联 |
|---|---|---|---|---|
| **IMP-31**（升 **P0**） | `cpg_chunks`（WikEM/PMC-OA）并入 TF-IDF/FAISS 索引 + 保留 chunk 元数据 | 改 `build_tfidf_index.py` / `build_rag_index.py` | **解锁卡点** | §14.1 |
| **IMP-57** | 跨源 DDx 融合 + 一致性投票 | `ddx_union_by_syndrome.json` | 新增 | §14.2、SYNDROME §11.10 |
| **IMP-58** | 实体归一层（scispaCy UMLS + LLM 消歧） | `entity_norm_cache.json` | 新增 | §14.3 |
| **IMP-59** | 综合征别名 crosswalk | `syndrome_alias_map.json` | 新增 | §14.4 |
| **IMP-54+** | oracle 覆盖评测（用 §14.5 silver 自举） | `eval_coverage_oracle.py` | 强化 | §13.5、§14.5 |
| **IMP-60** | CPG/Merck sub-axis 提示抽取（轴正确性） | sub-axis 候选 | 新增 | §14.7 |

> **修订实操顺序**：**IMP-31（解锁，索引）→ IMP-58（归一，公共前置）→ IMP-57（融合）→ IMP-54+（用融合自举评测）→ IMP-59（别名召回）→ IMP-55（可达性门）→ IMP-60（轴正确性）**。IMP-31 不做，后续皆悬空。

---

## 15. 混合管道 vs 纯 CPG 管道：设计与孤立实验（2026-06-25）

> 目标（用户规格）：在**无任何手工 curated 分支文件**参与（仅 `mechanism_to_disease.json` 用于 gold 归一，且其本身应由本体自动化）的条件下，评估两条管道「创建出覆盖正确答案家族（无整族缺失）且轴正确（无反向 LR 兄弟污染）的分支」的能力，并保证 **CPG 数据源不空转**。综合征根节点由 **LLM 抽取**（RootSelector 代理），不读 `syndrome_axis_map.json`。

### 15.1 前置：专用 CPG 索引（让 CPG 真正生效）

实时 `rag_index` 不含任何 CPG（§1.10.1），故先建**独立** CPG 索引（不动实时索引）：`scripts/build_cpg_tfidf_index.py` → `data/corpus/cpg_index/`。

- 输入 `cpg_chunks.jsonl`（**360,234**，含 manifest HTML 源 39,091：NICE 29,391 / ACR 1,876 / IDSA 1,222…，以 `recommendation` 为主；**198** 篇 bot_gate 已剔除，见 §1.5.3.2）。
- 过滤：`chunk_type∈{differential,red_flag,evaluation,recommendation}` ∧ `len≥120` ∧ 去浏览器检查/Cookie 噪声页 ∧ sha256 去重 → **203,830 useful**（弃 99,926 other + 22,215 短 + 17 噪声 + 34,264 重复）。
- 索引文本 = `section_path + content + wiki_links`（WikEM 的 `wiki_links` 是现成 DDx 实体列表，提升召回）。
- 元数据保留 `source_id/chunk_type/entry_type/syndrome_anchor` → **`expand_ddx_siblings`/`cpg_chunk_gate` 在此索引上真正触发**（实测 `abdominal pain` 闭包 8→213，`hypercalcemia` 8→119；§1.10.2 的空转问题在此被解决）。实验中对闭包设 +60 上限，防 PMC 巨文章淹没候选池。

> **逐步处理细节**（raw chunk → 检索 → snippet → LLM payload → 后处理）见 **§20 全链路备忘**。

### 15.2 两条管道设计（`scripts/eval_cpg_branch_pipeline.py`）

| 管道 | 流程 | 是否用 CPG | 是否用 LLM |
|---|---|---|---|
| `orig`（基线） | `GuidelineBranchSource(rag_index).recall` → `KBAxisMap.partition_from_candidates` → 投影 | 否（CPG 空转，仅作参照） | 仅综合征抽取 |
| **`cpg_llm`（纯 CPG）** | `GuidelineBranchSource(cpg_index).build_branch_knowledge_llm`（方案A）：LLM 在 CPG DDx 片段上**直接产出单轴 MECE 域 + 实体 + mandatory**，绕过 SNOMED 分区墙 | **是（203k CPG）** | 是（综合征 + 方案A） |
| **`hybrid`（混合）** | `cpg_index.recall_llm`（GARMLE-G② 接地抽取）∪ `rag_index.recall` → 合并候选 → `KBAxisMap.partition_from_candidates` → 投影 | **是** | 是（综合征 + GARMLE-G②） |

**curated-free 校验**：根节点经 LLM 抽取；分区/域由 RAG+LLM 生成，无 `syndrome_axis_map.json` / `syndrome_override_seeds.json` / `auto_axis_cache.json` 参与；仅 `mechanism_to_disease.json` 用于 gold 归一（待 IMP-58 本体自动化）。

### 15.3 孤立实验结果（N=9 文本诊断题，medbullets_hard；上游用 u29_full 日志）

| 管道 | L1 覆盖 | L1 轴-OK | L2 覆盖 | L2 轴-OK | gold 家族**由 CPG 召回** |
|---|---:|---:|---:|---:|---:|
| `orig`（CPG 空转） | 2/9 (22%) | 2/2 | 2/9 | 2/2 | 0/9 |
| **`cpg_llm`（纯 CPG / 方案A）** | **5/9 (56%)** | **5/5** | **5/9** | **5/5** | 5/9 |
| `hybrid`（CPG∪orig→SNOMED 分区） | 3/9 (33%) | 3/3 | 3/9 | 3/3 | **6/9** |

逐例（HIT=覆盖）：`cpg_llm` 命中 1(pancoast→Neoplastic)、17(CML→Myeloid Lineage Neoplasms)、18(peliosis→Hepatic and Vascular Pathology)、22(PHPT→PTH-related hypercalcemia)、24(异物→Nasal Foreign Body)；miss 9/13/23（+14 为体征措辞，见下）。

### 15.4 关键发现（实验支撑）

1. **CPG 不空转，且实质提升召回**：CPG 片段在 **9/9** 例被检索；gold 家族**由 CPG 召回 5–6/9**（orig 为 0/9）。`expand_ddx_siblings`/门控在 CPG 索引上确认生效。**满足"CPG 必须发挥实效"的硬要求**。
2. **纯 CPG 管道（方案A）最优**：L1 覆盖 56%（orig 的 2.5×），且**轴正确率 5/5=100%**。其优势来自 LLM 直接构建临床命名的 MECE 域（"PTH-related hypercalcemia"/"Myeloid Lineage Neoplasms"），而非 SNOMED 分类名。
3. **混合管道反而劣于纯 CPG（33% < 56%）——重大发现**：hybrid 召回 gold 最多（6/9）却覆盖最低（3/9）。根因：hybrid 把 CPG 召回喂回 `partition_from_candidates`（**SNOMED is_a 分区墙**，§1.10/§31.13.10），即使 gold 已在候选集仍投影失败（cases 9/13/24 召回但被分区丢弃）。**这定量证明：瓶颈是分区而非召回；让 LLM 直接建分区（方案A）才能把召回兑现为覆盖，把召回路由回 SNOMED 分区会浪费它**。
4. **失败模式是「整族缺失/覆盖」，非「轴错误」**：所有被覆盖案例 L1/L2 轴均 100% OK，未观察到反向 LR 兄弟污染。L1==L2（sub-axis 拆分未改变结果）说明在当前 9 例粒度上，深层轴污染尚未暴露——需构造 gold 子族与兄弟存在反向 LR 的案例（如 CML 慢性 vs 急变）才能压力测试 L2，建议作为 IMP-60 的评测扩充。
5. **残余 miss 的可归因来源**：① case 14 gold 是体征措辞（"diastolic murmur…"）非疾病实体，`mechanism_to_disease.json` 缺此映射 → 归一缺口（IMP-58）；② case 23(adhesions)、13(glucagonoma) 的 LLM 综合征抽取偏弱（→"nausea and vomiting"/"hyperglycemia"），根节点质量直接拖累下游 → 提示**纯 CPG 管道对 RootSelector 质量敏感**，需更稳的综合征抽取或多综合征候选并查。剔除体征措辞后，疾病-gold 上纯 CPG 有效覆盖 5/8=63%。

### 15.5 自动 curate 文件质量与可扩展性结论

- **方案A（纯 CPG）可作为 `auto_axis_cache.json` / override 种子的自动起草器**：它在无任何 curated 输入下产出轴+MECE 域+实体+mandatory，轴 100% 正确、覆盖 56%，质量足以作为"机器起草 + 人工抽检"的草稿（对应 TODO-GL-19 `draft_override_seeds.py`）。建议草稿先经 §15.4(5) 的归一/根节点增强，再人工核验。
- **不要走 hybrid 的"召回→SNOMED 分区"路径做 curate 起草**：实验证明该路径浪费召回。混合管道若要用，应改为"**CPG 方案A 产分区 + orig 召回仅作 mandatory 下界补充**"（即让 LLM 分区为主，原管道候选只用于"防漏"注入残差域），而非把两者候选都灌进 SNOMED 分区。

### 15.6 待办（实验驱动）

- **IMP-31 仍是前置**：本实验用独立 `cpg_index` 绕开了实时索引缺失；生产环境仍需把 CPG 并入主检索（或让 controller 支持双索引路由）。
- **IMP-58（归一）+ 更稳 RootSelector**：直接拉升纯 CPG 覆盖（解 case 14/23/13）。
- **L2 压力集**：构造"母族正确但子族反向 LR"案例（CML 慢性/急变、CHF 收缩/舒张等），用 split=True 真正考核 sub-axis 防污染（IMP-60）。
- **混合管道重构**：改为"LLM 分区为主 + 原管道候选作 mandatory 下界"，再测是否能在保持方案A 覆盖的同时进一步防漏。

### 15.7 与 §31.13.17「StatPearls+Textbooks+LLM=75%」的同口径对照（2026-06-25）

> 用户问：之前 §31.13.17 含 StatPearls+Textbooks+LLM（方案A）的结果（**覆盖 75%**）是否更佳？该管线能否额外帮助？答案需在**同口径**（curated-free，综合征用 LLM 抽取，N 一致）下测，因为 §31.13.17 的 75% **用了手工 `syndrome_axis_map.json` 取综合征标签**（curated），与本任务"无 curated"前提不一致。

新增两臂同口径实测（curated-free LLM 抽根，qwen3-32b@T=0，闭包/门控均生效）：

| 臂（方案A，LLM 抽根） | L1 覆盖 (N=9) | L1 覆盖 (N=8，排除体征 case14) | 轴-OK | 覆盖案例 |
|---|---:|---:|---:|---|
| `sp_llm`（StatPearls+Textbooks 索引） | 4/9 (44%) | **4/8 (50%)** | 4/4 | 1,17,22,24 |
| `cpg_llm`（CPG 索引） | 5/9 (56%) | **5/8 (62%)** | 5/5 | 1,17,**18**,22,24 |
| `union_llm`（CPG ∪ StatPearls 片段） | 5/9 (56%) | **5/8 (62%)** | 5/5 | 1,17,18,22,24 |

**对用户两问的实证回答：**

1. **"之前 75% 是否更佳？"——否，那是 curated 注入的假象。** §31.13.17 的 StatPearls+方案A=75%(6/8) **依赖手工 map 提供干净综合征标签**；一旦换成本任务要求的 curated-free LLM 抽根，**同一 StatPearls+方案A 跌到 50%(4/8)**。这 **75%→50%(≈2 例)** 的落差，恰好量化了那个被算作"全自动"的 curated 根节点的真实贡献——即 §31.13.17「75% 全自动」**名不副实，实为半自动**（综合征根来自 curated）。**应更正 §31.13.17 结论**：方案A 在真正 curated-free 下覆盖约 50%（StatPearls）/62%（CPG），而非 75%。

2. **"StatPearls 管线能否额外帮助 CPG？"——在本 9 题集上没有。** `union_llm`（把 StatPearls/Textbooks 片段并入 CPG 一起喂 方案A）覆盖 = **5/8，与 CPG 单独完全相同**，覆盖案例集一字不差（1,17,18,22,24），**零额外案例**。反而 CPG 单独已覆盖 StatPearls 漏掉的 **case18（peliosis/肝血管病变**——PMC 肝病综述+Merck 提供了 StatPearls 缺的肝窦/血管扩张内容）。即在此集上 **CPG 覆盖 ⊇ StatPearls 覆盖**，StatPearls 无边际增益；且 union 还把 case17 CML 的域命名劣化为"Acute Myeloid Leukemia (AML)"（CPG 单独为更准的"Myeloid Lineage Neoplasms"），提示盲目并源可能稀释 LLM 的分区命名质量。

3. **共同短板与真正杠杆**：两个语料都漏的 **case 9(leukemoid)/13(glucagonoma)/23(adhesions)** 是 LLM 抽根/轴框定问题（→"nausea and vomiting"等弱根），**非语料缺失**——故"换/加语料"对这三例无用，真正杠杆是 **更稳的 RootSelector + 实体归一（IMP-58）**。

**结论**：在 curated-free 前提下，**纯 CPG（方案A）是当前最佳单管线（62%）**；StatPearls/Textbooks 既不更佳（50%），叠加后也无额外帮助（仍 62%）。若要超过 62%，方向是 **RootSelector/归一增强 + 方案C 式极小 curated 兜底（A∪C）**，而非引入或叠加 StatPearls 语料。N=9 样本小，结论限于此基准集，但 CPG⊇StatPearls 的覆盖包含关系方向明确。

---

## 16. 数据源差异化检索算法：缺陷验证 + 设计 + 证明（2026-06-25）

> **用户命题**：各数据集「最合适的组织方式」各不相同（§1.5.3、§1.4–§1.9）；在这些差异化最佳组织下，**统一化检索方法会损害综合征入口召回**。本节先**实验验证该负面影响并定位缺陷**，再**设计差异化检索算法并实验证明其克服缺陷、提升召回**。脚本：`scripts/eval_differentiated_retrieval.py`；报告：`data/cpg/eval/differentiated_retrieval_report.json`。

### 16.1 前提：各源「综合征入口」组织方式互不相同

| 源 | 入口载体 | 关键字段 | 中位正文长 | 最佳检索假设 |
|---|---|---|---:|---|
| **WikEM** | chief-complaint 页 | `syndrome_anchor`=主诉 + `wiki_links`=**显式 DDx 实体列表** | 321 | 综合征名 match anchor/wiki_links（术语精确） |
| **Merck 19e** | `Approach to …` 章 | `entry_type=syndrome_entry` + `section_path` | 707 | "approach to {S}" match 章标题 |
| **NICE** | recommendation 编号块 | `chunk_type=recommendation`（95%）、标题=指南名 | 1,596 | chunk_type 过滤 + 指南名 anchor（标题无综合征词） |
| **PMC-OA** | 综述全文（**占库 88%**） | `syndrome_anchor`=**论文标题原文**、prose | 617 | dense / 标题 anchor（~63% 标题无显式临床词） |
| **协会**（ACC/AHA/IDSA/ESC…） | 长篇疾病管理 prose | `chunk_type=recommendation/evaluation` | ~2,000 | chunk_type + 指南名 anchor |

→ 同一个「综合征入口」在 WikEM 是**实体列表**、在 Merck 是**Approach 章标题**、在 NICE 是 **recommendation 块**、在 PMC 是**论文标题**。无单一文本场/查询模板能同时最优匹配。

### 16.2 实验设置

- **语料**：`cpg_chunks.jsonl` 的 useful∧≥120 子集，**295,041** chunk（PMC 289,741 = **98%**，即生产实况的源失衡）。
- **Query 集（干净综合征入口）**：WikEM anchor **138** 个主诉 + Merck Approach 章 **23** 个 complaint。
- **Gold**：该综合征自身的入口 chunk（同 anchor / 同 Approach 章）；WikEM 另取 `wiki_links` 并集为 **gold DDx 实体集**。
- **指标**：entry Recall@10（top-10 含 ≥1 入口 chunk）、首个 gold 排名中位、DDx 实体覆盖@10、top-10 中 PMC 占比。
- **臂 A 统一**：单一 TF-IDF（文本=`section_path+content+wiki_links`），单模板 `approach to {S} differential diagnosis evaluation`。
- **臂 B 差异化**：见 §16.4。

### 16.3 缺陷验证（统一检索的负面影响）

| Query 集 | 臂 | Recall@10 | DDx 实体覆盖@10 | top-10 PMC 占比 |
|---|---|---:|---:|---:|
| WikEM (138) | **统一** | **0.659** | 0.283 | **0.51** |
| Merck (23) | **统一** | 0.913 | — | 0.21 |

**定位到四类具体缺陷（均有实测证据）：**

1. **候选淹没（candidate flooding）**：PMC 占库 88%，单综合征词在 PMC prose 中的绝对竞争 chunk 数巨大——`pain` **8,982** 个、`acute` 8,912、`abdominal` 2,813、`fever` 1,800、即便 `diarrhea` 也 1,198。这些 prose chunk 在统一池里与 WikEM **唯一一条**简短入口 chunk 抢 top-10 名额 → top-10 有 **51%** 被 PMC 占据。
2. **入口被埋（entry burial）**：138 例中统一检索 **47 例失败**；这些入口 chunk 其实存在，但真实排名中位 = **第 38 名**（被约 35 条 PMC prose 压在上面），**8 例**甚至跌出 top-200。例：`acute diarrhea` 入口在第 **108** 名（95 条 PMC 在其上）、`acute dyspnea` 第 115 名。
3. **查询模板错配**：单模板 `approach to {S} differential diagnosis` 适配 Merck/PMC 标题，但 NICE recommendation 块标题是**指南名**（无 "differential" 无综合征词）、协会 prose 同理 → 这些源的入口对该模板**先天低分**。
4. **anchor 语义混淆**：统一把 PMC 的「论文标题 anchor」与 WikEM 的「主诉 anchor」同等对待；前者 ~63% 无临床词、噪声高，拉低 anchor 通道的判别力。

> 注：原始草稿曾用「跨语料 IDF 对比」佐证，但 IDF 随语料规模 N 缩放、跨库不可比；已更正为**文档频率分数 + 绝对竞争 chunk 数 + 真实埋深**三项可比证据（见报告 `defect_candidate_flooding` / `defect_entry_burial`）。

### 16.4 差异化检索算法设计

针对 §16.3 四缺陷，逐一对症：

| 组件 | 机制 | 克服的缺陷 |
|---|---|---|
| **① 分源子索引** | 每源（wikem/merck/nice/society/pmc）建独立 TF-IDF，检索时各自取 top-k | **①候选淹没**：少数高价值源不再与 88% PMC 在同一池竞争名额 |
| **② 源级字段加权** | 入库文本按源结构加权（重复=权重）：WikEM `section_path×3+anchor×2+wiki_links×3`；Merck/NICE `section_path×2`；PMC `anchor×2`；协会纯 content | **②入口被埋/③模板错配**：把各源真正承载入口语义的字段提权 |
| **③ 源级查询路由** | 每源用专属 query 形：WikEM=`{S}`；Merck=`approach to {S}`；NICE=`{S} assessment diagnosis recommendations`；协会=`{S} diagnosis evaluation`；PMC=`differential diagnosis of {S} causes` | **③查询模板错配** |
| **④ RRF 融合** | 各源 rank list 用 Reciprocal Rank Fusion（k=60）合并，**按名次而非原始分**，消除跨源 TF-IDF 分数尺度不可比 | **①淹没 / 跨源分数不可比** |
| **⑤ 入口 boost** | 融合后对 `entry_type=syndrome_entry`、anchor-token 命中、section_path 含综合征词的 chunk 加权重排 | **④anchor 语义混淆**：让真入口 chunk 上浮，弱化 PMC 标题 anchor 噪声 |

**伪代码**：

```text
diff_retrieve(S, k):
  for src in {wikem, merck, nice, society, pmc}:
      q = query_form[src](S)                 # ③ 源级查询路由
      rl[src] = sub_index[src].search(q, k)  # ① 分源子索引（②字段加权已在建索引时固化）
  fused = RRF([rl[src] for src], k_const=60) # ④ 名次融合
  return rerank(fused, boost=entry_type/anchor/section_path)[:k]  # ⑤ 入口 boost
```

### 16.5 证明：差异化检索克服缺陷并提升召回

同一 query 集、同一 gold、同一 corpus（PMC 88%）下对照：

| Query 集 | 指标 | 统一 | **差异化** | 增益 |
|---|---|---:|---:|---:|
| WikEM (138) | **entry Recall@10** | 0.659 | **0.993** | **+33.4pp** |
| WikEM (138) | 首个 gold 排名中位 | 2 | **1** | — |
| WikEM (138) | **DDx 实体覆盖@10** | 0.283 | **0.533** | **+25.0pp（≈1.9×）** |
| WikEM (138) | top-10 PMC 占比 | 0.51 | **0.26** | 淹没减半 |
| Merck (23) | entry Recall@10 | 0.913 | **1.000** | +8.7pp |

**逐缺陷对应证明**：
- 缺陷①淹没 → ④分源+RRF：PMC 占 top-10 由 51%→26%，给入口让出名额；
- 缺陷②埋深（中位第 38 名）→ ①分源：WikEM 入口在自身 897 文档池里稳居前列，Recall 66%→99.3%；
- 缺陷③模板错配 → ③查询路由：NICE/协会/PMC 各按其结构发问，不再被单模板压分；
- 缺陷④anchor 混淆 → ⑤boost：真入口（entry_type/anchor 命中）上浮，DDx 实体覆盖近翻倍。

**对照公允性说明**：差异化为每源保留独立名额，本身即「防淹没」的算法贡献；其增益不是凭空给 WikEM 配额，而是**把被 88% PMC 挤掉的高价值少数源入口重新纳入候选并按名次公平融合**——这正是「防漏」目标所需。

### 16.6 落地路径（接 IMP-31，新增 IMP-61）

当前差异化检索器在 `scripts/eval_differentiated_retrieval.py` 中作**参考实现 + 实验证明**。生产化：

| ID | 任务 | 说明 |
|---|---|---|
| **IMP-31**（前置） | 重建索引并写入 `source/source_id/chunk_type/entry_type/syndrome_anchor/wiki_links` 元数据 | 分源路由/字段加权/boost 全依赖这些字段（§1.10.2） |
| **IMP-61**（新增） | `DifferentiatedCPGRetriever`：分源子索引 + 源级 query 路由 + RRF 融合 + 入口 boost；封装为 `RAGRetriever` 兼容接口供 `GuidelineBranchSource` 调用 | §16.4 设计；起步 TF-IDF，后续 PMC 通道可换 MedCPT dense（§13.4） |

**与既有结论一致性**：§16 不与 §15 矛盾——§15 证明「CPG 方案A 把召回兑现为覆盖」，§16 证明「**先用差异化检索把各源入口召回上来**」是其前置；二者串联即「差异化召回 → 方案A 分区/抽取」。差异化检索亦是 §13.4「面向召回的检索增强」在**源失衡**这一具体缺陷上的落地。

---

## 17. Branch 生成阶段 RAG 低召回：排查清单 + 诊断实验（2026-06-25）

> **范围**：仅 **Branch 生成**链路——`综合征/症状群入口 → query → 检索 DDx 片段 → 篇内闭包 → 门控 → spotting/LLM 抽取 → 候选疾病族`。成功判据：**金标准疾病族是否进入候选族集**（尚未进入 SNOMED 分区/覆盖投影）。
>
> **缺口归因总览**：§13.5 三类缺口 → **§17.2 决策树** → **§17.2.1 六层全景（A–F）**；缺陷 ID 清单 → §17.3–§17.4；原调研 B1–B11 对照 → §17.4.2。**§17 缺陷 ID → 改哪个参数/IMP** → **§19.0.8 表 D**；参数详解 → **§19.0.8**。
>
> **脚本**：`scripts/eval_branch_rag_recall_diagnosis.py`  
> **报告**：`data/cpg/eval/branch_rag_recall_diagnosis.json`  
> **诊断设定**：综合征标签取自 **手工 map**（隔离 RAG/spotting，不混入 RootSelector 误差）；N=8（排除体征 gold case14）。

### 17.1 本节目的与适用范围（备忘录定位）

**目的**：为后续 branch 生成迭代提供**可复原、可逐项勾选**的低召回排查备忘录——每条缺陷含：机制说明、在 pipeline 中的位置、如何验证、已知实测状态、推荐修复与 IMP 编号。

**范围（仅 Branch 生成 RAG 召回）**：

```text
[输入] 综合征/症状群 S（RootSelector 或 hand map）
   ↓
[1] Query 构造          GuidelineBranchSource.recall() 内 4–5 条 query
   ↓
[2] 向量/稀疏检索       RAGRetriever.search()  → top_k hits
   ↓
[3] 篇内 DDx 闭包       expand_ddx_siblings(source_id)  → 同篇 differential/evaluation
   ↓
[4] On-topic 门控       cpg_chunk_gate.snippet_on_topic()
   ↓
[5] 疾病族 spotting     _spot() n-gram × SNOMED disorder vocab
   ↓                    或 recall_llm() / build_branch_knowledge_llm()
[6] 候选族排序截断      max_candidates=40
   ↓
[7] （下游，本节不测） KBAxisMap.partition / 方案A LLM 分区 → gold→domain 覆盖
```

**本节成功判据（branch-gen 召回）**：金标准疾病族是否进入 **[5] 输出的候选族 dict**（`GuidelineBranchSource.recall()` 或等价 LLM 抽取）。**不**包含 [7] 分区/覆盖（见 §15/§31.13）。

**关键代码锚点**：

| 组件 | 路径 |
|---|---|
| 召回主逻辑 | `src/agentclinic_tree_dx/knowledge/guideline_branch_source.py` |
| 检索器 | `src/agentclinic_tree_dx/knowledge/rag_retriever.py` |
| 门控 | `src/agentclinic_tree_dx/knowledge/cpg_chunk_gate.py` |
| 孤立评测 | `scripts/eval_branch_creator_isolated.py` |
| CPG 管道评测 | `scripts/eval_cpg_branch_pipeline.py` |
| **本节诊断脚本** | `scripts/eval_branch_rag_recall_diagnosis.py` |
| 数据源上界（§18） | `scripts/eval_cpg_oracle_recall.py` |

**评测基准**：medbullets_hard 文本诊断 **9 题**，本节多数实验 **N=8**（排除 case14：gold 为纯体征措辞 `"diastolic murmur…"`，非疾病实体，归一/spotting 口径不同）。

**两套综合征标签（诊断时必须区分，不可混读）**：

| 设定 | 来源 | 用途 |
|---|---|---|
| **hand 标签** | `syndrome_axis_map.json` → `SyndromeAxisMap.match()` | **隔离 RAG/spotting**（§17 诊断默认） |
| **curated-free 标签** | LLM RootSelector  surrogate | 端到端可扩展性（§15）；c23 常弱化为 "nausea and vomiting" |

**索引现状（2026-06-25）**：

| 索引路径 | 后端 | 文档数 | 生产是否可达 | 备注 |
|---|---|---:|---|---|
| `data/corpus/rag_index/` | FAISS IndexIVFPQ + MiniLM-L6 | 493,646 | ✅ 是 | 仅 StatPearls+Textbooks；config 无 CPG |
| `data/corpus/cpg_index/` | TF-IDF | 203,830 | ❌ 否（独立实验索引） | useful 子集；含完整 chunk 元数据 |
| `cpg_chunks.jsonl` | 文件层 | 360,252 | ❌ 未入主索引 | IMP-31 待重建 |

---

### 17.2 缺口归因框架（决策树，IMP-54 对齐）

对每个漏召回 case，**按序**判定属于哪一层（勿跳步）：

```text
Step 0  数据源上界（§18 oracle entry+closure）
        └─ gold 不在任何入口→闭包内？ → 【缺源 / 切分 / 入口匹配】→ 补源或改 chunk/alias
        └─ 在闭包内？ → 继续 Step 1（说明数据足，问题在检索/抽取）

Step 1  片段层：合并 _retrieve_snippets 文本是否含 gold 家族词？
        └─ 否 → 【B 检索未召回】→ 查 §17.3 Part A/B 检索类缺陷
        └─ 是 → 继续 Step 2

Step 2  候选层：recall() 候选 dict 是否含 gold 家族（方案B 实体级匹配）？
        └─ 否 → 【C 检索到但未抽出（spotting 损失）】→ §17.3 C* / §17.4 L*
        └─ 是 → 继续 Step 3

Step 3  覆盖层：project_entity(gold, entry) 是否为非空 domain？
        └─ 否 → 【D 分区/投影失败】→ 方案A / IMP-55（§15，非本节 RAG 召回）

Step 4  轴层：axis_direction_ok 是否 FAIL？
        └─ 是 → 【轴污染】→ split_variants / IMP-60（§15 L2）
```

**与 §18 的关系**：§18 实测 **entry+closure 上界 = 8/8 (100%)** → 对本基准 **Step 0 恒为「数据可达」**；当前 50–87.5% 召回差距 = Step 1–2 工程损耗（38–50pp），**不是缺数据源**。

**完整六层清单（成因→方案→现状）**：见 **§17.2.1**（与 §13.5 IMP-54 三类缺口、§17.3 A/B/C/D 缺陷 ID 对照）。

---

### 17.2.1 六层缺口归因全景（A–F，branch-gen 专节，2026-06-26 入档）

> **来源**：项目内现有研究汇总（§13.5 / §14 / §15 / §17 / §18 / §23.11 / EXTERNAL §8.3·§11.2·§断裂点①）；按 **branch 创建算法**（`GuidelineBranchSource.recall()` → 候选族集）组织。
>
> **与 §13.5 三类缺口的对齐**（`eval_coverage_oracle.py`，IMP-54，**待建**）：对每个漏 case，先取**所有源并集** oracle 检索，再归因——
>
> | IMP-54 缺口类型 | 本框架层 | §17.2 Step | 典型误判 |
> |---|---|---|---|
> | **无任何源覆盖** | **A** 工程/索引 | Step 0 失败 | 误加检索算法 |
> | **有覆盖但检索/抽取未召回** | **B** 检索机制 + **C₂** spotting（Step 2） | Step 1–2 | 误补数据源 |
> | **召回了但投影/覆盖失败** | **F** 分区墙（+ **D** 命名导致伪投影失败） | Step 3 | 误当作「召回低」 |
> | **（横切）度量低估** | **E** 度量假象 | — | 误报「真漏」 |
> | **（旁路，非 branch-gen RAG）** | **C₁** 可达≠可排序（LR cache） | — | 与 branch-gen spotting 混淆 |

**核心判断（一句话）**：当前「召回偏低」在不同位置根因不同——实测反复指向 **①索引/元数据未解锁（IMP-31，A 层）**、**②检索后 spotting/拥挤（B+C₂ 层，§17.5）**、**③分区/归一/排序墙（D/F/C₁ 层）**、**④度量低估（E 层）**；**而非「语料里没有 gold」**（§18 entry+closure **8/8=100%**）。排查应 **先跑 oracle 定缺口类型**（§18 已证 Step 0；IMP-54 待补 union 边际 + recall@k），再决定补源 / 补检索 / 补分区归一。

#### A. 工程/索引层（数据未进检索——**当前最大卡点**）

| 成因 | 解决方案 | 现状 / 证据 | §17.3 |
|---|---|---|---|
| **新源未进实时索引**：`build_tfidf_index.py` 仅 load statpearls/textbooks；`cpg_chunks`（WikEM/PMC/Merck/NICE）运行时不可查 | 索引重建并入 `cpg_chunks`（`--useful-only --pmc-require-anchor` 子集） | **IMP-31 P0 未落地**；生产 FAISS 493k 仅 StatPearls+Textbooks（§1.10.1、§14.1） | **A1** |
| **chunk 元数据缺失 → 闭包/门控空转**：无 `chunk_type/source_id`，`expand_ddx_siblings`/`cpg_chunk_gate` 加 0 | 重建写入 `source_id/chunk_type/entry_type/syndrome_anchor` | 代码已实现；**孤立实验 8→8（+0）**（§1.10.2）；待 IMP-31 生效 | **A2** |
| **语料稀释**：cpg_chunks 31% `other`、8.8% <120 字符 | 入索引取 `useful∧≥120` 子集（≈200k） | §15.1 独立 `cpg_index`（203,830）已验证；生产未用 | **A3** |
| **NICE/协会 HTML 以 recommendation 为主** | 作 mandatory 审计/上下文，非主 DDx 召回 | differential 仅 80/39k chunk | **A4** |
| **浏览器/Cookie 噪声页** | 抓取层 NOISE 过滤 | cpg_index 已滤 17 条 | **A5** |

#### B. 检索/召回机制层（「有覆盖但没召回」——Step 1）

| 成因 | 解决方案（§13.4） | 现状 / 证据 | §17.3 / L* |
|---|---|---|---|
| **单轴 query 只命中显著轴**，漏其他鉴别方向 | **跨轴 query 扇出**：Qmech/Qanat/Qurg/Qwork/Qsymptom-entry，多路 top-k 合并 | **IMP-52 待办** | **B1** |
| **短综合征 query ↔ 复杂指南正文语义鸿沟** | **HyDE/Query2Doc**；进阶 **SL-HyDE/CHR**（抑制 mimic DDx） | IMP-53 规划；HyDE **仅低置信兜底**+防幻觉门 | **B2**, **L6/L7** |
| **稀疏/稠密单独召回不足** | **Hybrid BM25/TF-IDF + MedCPT dense**，top_k 50–100 + **cross-encoder 重排** | IMP-53 / §9.4 方案B **待办**；生产 FAISS=MiniLM | **B2**, **L1/L2** |
| **top-k 漏同篇多 DDx 子块** | **`expand_ddx_siblings` 篇内闭包** | 已实现；cpg_index **8→213**（§15.1）；生产索引无元数据→**不触发** | **B3**, **L3** |
| **统一池 PMC 淹没**（`pain` PMC 8982 vs WikEM 897） | **IMP-61 差异化检索** | §16.5 WikEM Recall@10 **0.659→0.993** | **B7**, **L9** |
| **ANN nprobe / IVFPQ 近似** | nprobe sweep / IVFFlat | **§17.5.2 已跑**：默认 nprobe=32，@k=30 **非主因** | **B8**, **L8** |
| **score_threshold 误杀** | 召回阶段 threshold=0 | **§17.5.3**：轻微（-2 hits） | **B9** |
| **query 词面/eponym 鸿沟**（Pancoast↔limb deficit） | IMP-59 alias + pathognomonic 直提 | c1 **四臂全漏**（§19.3④）；需非检索通道 | **B5**, **L4** |

#### C. 可达≠可排序（排序/特异性瓶颈——**LR 旁路，branch-gen 需知**）

> **定位**：本节 **C₁** 描述 **Layer 2 LR unified_cache 反向检索**（EXTERNAL §23.11.2），**不是** `GuidelineBranchSource.recall()` 主路径；但同一 gold 在 branch-gen 也会因 **flat spotting + top-40 拥挤**（§17.3 **C4/C5**）呈现类似「可达但排不进候选」——机制不同、症状相似，排查时勿混读。

| 成因 | 解决方案 | 现状 / 证据 |
|---|---|---|
| 金标准 **flat 反向检索可达 78%（7/9）**，但名次 **69–491**（池 2000–3000）→ **recall@20=0/9** | 放弃单一 LR-cache 反向检索；**分层多通道候选**，`mandatory_coverage` 取并集（召回优先） | EXTERNAL §23.11.2 **硬实证** |
| **IDF 特异性加权抬不动**（gold 走「泛化发现」，被几千病共享） | 族级聚合后再排序（§23.12 T2） | 个体可达、族级才可排 |
| **佐证过滤（≥2 条）反杀召回**（unified_cache 对 gold 平均 ≤1 条连接） | 佐证作加分非硬门槛；或换 curated 通道 | 过滤后 recall **2/9** |
| **pathognomonic / diagnostic_markers 直提** | `pathognomonic_markers.json` 接入 branch-gen 候选层 | §23.11.3 **可提名 5/9**（glucagonoma/CML/peliosis 等）；**branch-gen 未接入**（**D3**, **L13**） |

#### D. 实体/命名归一（「召回了但词面不匹配」——Step 2 部分 + 投影前置）

| 成因 | 解决方案 | 现状 / 证据 | 映射 |
|---|---|---|---|
| **疾病名解析失败 → 0% coverage**（TALP 标签 ↔ 知识源键不匹配） | `DiseaseNameResolver` 规范化（CUI + 缩写 + token Jaccard） | **已落地**；case#68 **0%→100%**（EXTERNAL **断裂点①** / §11.2.1 P-1） | **C1** 前置 |
| **HPO 疾病名覆盖仅 6.6%**（命名差异） | **UMLS CUI / MONDO ID 桥接** | §9.4 **方案E** / EXTERNAL **R13** **待办** | IMP-58 |
| **PMC `syndrome_anchor`=标题原文**，非归一综合征 | scispaCy UMLS linker + LLM 消歧 | **IMP-58 P0 待办**；~63% 标题无显式临床词（§1.10.5） | **A2** 延伸 |
| **root label ↔ 源 anchor 词面不一致** | **`syndrome_alias_map.json`** | **IMP-59 待办** | **B5** |
| **症状术语 Jaccard 匹配弱** | **embedding-based HPO 归一**（替代 Jaccard+stemming） | §9.4 **方案A** **待办** | — |

#### E. 度量假象（不是真低，是尺子低估——横切层）

| 成因 | 解决方案 | 现状 / 证据 |
|---|---|---|
| `GOLD_FAMILY_TOKENS` **token 子集匹配**：惩罚精确实体、奖励泛化名——c9 给 `infectious mononucleosis`（临床正确）判 MISS，给泛化 `leukemia` 反而命中 | **度量修正（方案B / TODO-GL-10）**：实体级/嵌入相似 + 前缀词干放松 | **✅ 已落地**；GUIDELINE Recall@K **50%→75%**（§31.13.17、§17.3 **C8**） |
| 无法区分「真漏 vs 度量低估 vs 排序埋没」 | **IMP-54** `eval_coverage_oracle.py`：oracle-union 上界 + recall@k 曲线 | §18 entry+closure **已跑**；union 边际 + 全曲线 **待建**（§17.4.2 **B11**） |

#### F. 召回≠覆盖：投影/分区墙（下游 Step 3——**常被并入「召回低」误判**）

| 成因 | 解决方案 | 现状 / 证据 |
|---|---|---|
| gold **已进候选**（hybrid **6/9**、cpg_det **5/9**），但 **SNOMED `is_a` 投影失败**（adhesions/peliosis/foreign body 等机制/解剖措辞）→ coverage 仍 MISS | ① **方案A**（LLM 直接建 MECE 分区）绕墙（§15.3）；② **IMP-55** 运行时实体→域可达性门 + residual 注入；③ **IMP-56** can't-miss 硬下界 | §15.4 跨源再确认；**墙在分区，不在召回** |
| LLM 轴框定错误（c9 按谱系切轴无 reactive 桶） | override / 轴模板 prompt | §31.13.17 方案A 2 miss |
| 低概率致命方向被 top-k 挤掉 | IMP-56 `cant_miss_by_syndrome.json` | WikEM 部分 **`cant_miss_by_syndrome_wikem.json` 已自动化** |

#### 落地优先级（两套次序，勿混读）

| 次序 | 适用场景 | 推荐链 |
|---|---|---|
| **解锁序**（研究/IMP-54 前置，§13.8·§14.5） | 新源已切但未进索引；需先证「有没有覆盖」 | **IMP-31**（解锁索引+元数据）→ **IMP-58**（实体归一）→ **IMP-54**（量上界、定缺口类型）→ **IMP-55**（运行时防漏门）→ **IMP-52/53**（扇出+混合+重排）→ **IMP-56**（can't-miss 下界） |
| **诊断修复序**（§18 已证数据足，§17.5 漏斗已定位瓶颈） | 独立 `cpg_index` 实验轨；spotting 50% 为主因 | **IMP-63**（解耦 k + MMR + recall_llm）→ **IMP-61**（差异化检索）→ **IMP-31**（生产兑现）→ IMP-58/59 → IMP-53/52 → IMP-54 CI（§17.7） |

> **IMP-54/55 不依赖新数据**，可与 IMP-31 并行；但 **IMP-31 不做则闭包/门控/CPG 源在生产零贡献**（§14.0）。

#### A–F ↔ §17.2 决策树速查

```text
A 层失败？ → Step 0 oracle 非 100% → 补源/切分/IMP-31
A 通过、Step 1 失败？ → B 层 → §17.3 B* / §17.4 L*
Step 1 通过、Step 2 失败？ → B 层 spotting 子环节 + D 层命名 → §17.3 C* / IMP-58/59/63
Step 2 通过、Step 3 失败？ → F 层 → 方案A / IMP-55（§15，非 RAG 召回）
E 层？ → 先确认方案B 度量后再判「真漏」
C₁ 层？ → 仅 LR cache / pathognomonic 直提通道；branch-gen 主径见 C4/C5
```

---

### 17.3 可能缺陷排查清单 — Part A（项目内已识别）

> 格式：**ID | 机制 | 典型症状 | 如何验证 | 方案 | 状态 | 实测**

#### A 类：源 / 索引 / 元数据（Step 0 之前）

| ID | 缺陷 | 机制 | 如何验证 | 方案 | 状态 | 实测 |
|---|---|---|---|---|---|---|
| **A1** | **新 CPG 源未进生产索引** | `build_tfidf_index.py` 仅 load statpearls/textbooks/merck；`cpg_chunks` 360k 不可查 | `grep -c wikem data/corpus/rag_index/metadata.jsonl` → 0；config.sources 无 cpg | **IMP-31** 重建；或 controller 双索引路由 | **未落地** | §1.10.1 |
| **A2** | **chunk 元数据缺失 → 闭包/门控空转** | 生产 metadata 仅 id/title/content/article_id/tokens；无 source_id/chunk_type | 检索后 `chunk_type` 全 None；expand 8→8 | IMP-31 **必须写入** 元数据字段 | 代码有、**索引无** | §1.10.2 孤立实验 |
| **A3** | **语料稀释（other + PMC 88%）** | 321k 中 31% chunk_type=other；合并池 PMC 占 88% | `cpg_chunks` 按 source/chunk_type 统计 | useful 子集；**IMP-61** 分源 RRF | 部分 | §1.10.4；§16.3 |
| **A4** | **NICE/协会 HTML 以 recommendation 为主** | manifest 39k chunk 中 differential 仅 80；非 DDx 主载体 | `manifest_cpg_chunks.jsonl` chunk_type 分布 | 作疾病上下文+mandatory 审计，非主 DDx 召回 | 已认知 | §17 续研 |
| **A5** | **浏览器/Cookie 噪声页** | AAN 等 manifest 首块为 Cloudflare 检查页 | `NOISE` regex 过滤；build_cpg_tfidf_index 弃 17 条 | 抓取层过滤 + sha256 去重 | cpg_index 已滤 | build_cpg_tfidf_index.py |

#### B 类：Query / 检索排序（Step 1）

| ID | 缺陷 | 机制 | 如何验证 | 方案 | 状态 | 实测 |
|---|---|---|---|---|---|---|
| **B1** | **单模板 query** | 仅 "differential diagnosis of {S}" + "causes/etiology"；漏 red-flag / anatomical / workup 轴 | 对比 IMP-52 五路 query 并集 recall | **IMP-52** Qmech/Qanat/Qurg/Qwork/Qsymptom-entry | 待办 | §13.4 |
| **B2** | **稀疏-only / 无 dense** | 生产 FAISS=MiniLM；cpg 实验=TF-IDF；无语义近邻 | 同 query A/B：TF-IDF vs MedCPT | **IMP-53** hybrid BM25+MedCPT | 待办 | — |
| **B3** | **top_k 过小漏同篇 DDx** | 单篇 10+ DDx 子块，k=8 不全 | recall@k 曲线 k=8,16,30,50 | expand_ddx_siblings + 提高 k | cpg_index **闭包生效** | §15.1：8→213 |
| **B4** | **门控误滤** | StatPearls 假设 title 含 `> Differential`；NICE 多为 Recommendations | 统计 snippet_on_topic 前后 hit 数 | IMP-35 已改 chunk_type/entry_type；NICE 需分源门控 | 代码有；生产索引无字段 | §31.13.13 |
| **B5** | **综合征 query 与 corpus 词面不一致** | hand 标签 "focal limb neuro deficit" ↔ 语料 "Pancoast"/"superior sulcus" | oracle c1：124 入口块 0 direct，closure 靠 PMC sibling | IMP-59 alias crosswalk；GARMLE-G① context query | 部分 | §18.2 c1 |
| **B6** | **GARMLE-G① ctx-query 噪声** | 把整段 vignette 拼进 query 引入 off-topic 片段 | `--garmle` 臂 vs 确定性 recall 对比 | 仅 colloquial+短 feature 子集，非全文 300 字 | 实测曾**回退** | §31.13.14 |
| **B7** | **统一检索源淹没** | PMC 占 88%；`pain` 在 PMC 8982 chunk 竞争 | §16 WikEM Recall@10 0.659 vs 0.993 | **IMP-61** 差异化检索 | 实验证明 | §16.5 |
| **B8** | **ANN nprobe / IVFPQ 近似** | 默认 nprobe=32；PQ 压缩二次近似 | `eval_branch_rag_recall_diagnosis.py` nprobe sweep | nprobe≥4（小 k）；IVFFlat+RFlat 精排 | **本基准非主因** | §17.5.2 |
| **B9** | **score_threshold 误杀** | search(threshold=0.1) 过滤低分 hit | B10 threshold 0/0.1/0.3 对比 | 召回阶段 threshold=0 | 轻微 | §17.5.3 |
| **B10** | **RootSelector 弱标签** | LLM 抽 "nausea" 替代 "bowel obstruction" | hand vs LLM 标签 A/B | 更稳 RootSelector；多候选 syndrome 并查 | §15 证 75%→50% | §15.7 |

#### C 类：Spotting / 抽取（Step 2，branch-gen **独有**）

| ID | 缺陷 | 机制 | 如何验证 | 方案 | 状态 | 实测 |
|---|---|---|---|---|---|---|
| **C1** | **SNOMED n-gram spotter vocab 缺口** | `_spot()` 最长 5-gram 匹配 disorder vocab；机制名/eponym 不在 vocab | 片段含 gold 词但不在 SNOMED disorder | 扩 vocab + IMP-58 UMLS linker | 部分 | c13 glucagonoma |
| **C2** | **min_len=5 / 多词约束** | 短 disease token 漏 spot | 人工查 spotter 对短词 | 降 min_len 或 UMLS 链接 | 待评估 | — |
| **C3** | **_GENERIC_NAMES 误杀** | 过宽族名被滤 | 查 recall 日志是否滤掉 gold 上位词 | 白名单机制名→具体病 | 部分 | mechanism_to_disease |
| **C4** | **max_candidates=40 + 噪声淹没** | 多片段累加 w 分；高频无关病（urticaria/MI）占满 40 槽；**闭包灌池放大** | top_cands 与 gold 对比 | **IMP-63**：闭包→grounding（移出池）+ **IMP-64 本体归族**族层竞争 | **✅ 落地+证实**（§19.6） | §17.5.1；§19.6 |
| **C5** | **top_k↑ 损害 spotting** | k=30 检索更好但 spot 更差 | tfidf k=8 vs k=30 对比 | 检索/抽取 **解耦 k**（`retrieve_k/extract_k`） | **已落地（参数化）；⚠️ MMR-trim 对确定性 spotter 有害（§19.6#4）** | 75%→50%；§19.6 |
| **C6** | **未用 WikEM wiki_links** | WikEM chunk 带结构化 DDx 实体列表，spotter 未直读 | 查 wikem hit 的 wiki_links 字段 | 结构化直抽 mandatory 候选 | 已落地；本基准零增益（§17.5.6） | §16.1 |
| **C7** | **GARMLE-G② LLM 抽取未默认启用** | recall_llm 存在但 recall() 默认走 spotter | `extractor=spotter+llm` 臂对比 | IMP-63 `extractor='spotter+llm'` 合并 recall_llm | **✅ 落地；A5 最大杠杆（0.704→0.768，L1tgt 0.929）** | §31.13.15；§19.6#6 |
| **C8** | **度量 token 子集低估** | `_gold_family_match` 旧版惩罚精确实体 | 方案B 修正前后 Recall 50%→75% | **方案B 已落地** | ✅ | §31.13.17 |

#### D 类：分区 / 覆盖（Step 3–4，记录备查，非 RAG 召回）

| ID | 缺陷 | 机制 | 验证 | 方案 | 实测 |
|---|---|---|---|---|---|
| **D1** | SNOMED is_a 分区墙 | 候选有 gold 但 project_entity=None | oracle recall + partition | 方案A LLM MECE | hybrid 6/9 召回→3/9 覆盖 |
| **D2** | LLM 轴框定错误 | c9 按谱系切轴无 reactive 桶 | 方案A 逐例 domain 名 | override / 轴模板 prompt | §31.13.17 A 的 2 miss |
| **D3** | 可达≠可排序（LR cache） | 金标准 reachable 78% 但 recall@20=0 | §23.11.2 反向检索 | 分层候选 + pathognomonic 直提 | EXTERNAL §23.11 |

---

### 17.4 可能缺陷排查清单 — Part B（文献 / 通用 RAG，branch-gen 特化）

> 外部依据：Snorkel RAG failure modes (2024)；JMIR Med Inform 2026 e94241（clinical embedding benchmark）；MedCPT (Bioinformatics 2023)；RAG-Fusion (arXiv 2402.03367)；MMLF NAACL 2025；FAISS FAQ (IVFPQ)；Parent-child / Late chunking (arXiv 2409.04701, 2602.16974)。

| ID | 缺陷 | 为何专咬 branch-gen | 如何验证 | 方案 | 优先级 | 项目状态 |
|---|---|---|---|---|---|---|
| **L1** | **嵌入训练目标≠检索** | BioBERT/MLM 各向异性 >0.90；MiniLM 通用 | 同 query MedCPT vs MiniLM recall@30 | MedCPT / BioLORD | P1 | 未做 A/B |
| **L2** | **Query-Document 非对称** | 短 syndrome query vs 长 guideline 正文 | MedCPT Query+Article 双编码器 | MedCPT 双塔 | P1 | 未落地 |
| **L3** | **上下文碎片化** | DDx 列表切散到多 chunk；单 chunk 无完整列表 | entry-direct vs entry+closure（§18） | parent-child / late chunking / auto-merge | P1 | 闭包部分替代 |
| **L4** | **Query 欠定 / 词汇鸿沟** | lay vs technical；eponym（Pancoast↔limb deficit） | 多 query RRF 是否抬升 c1 | RAG-Fusion + IMP-59 alias | P1 | c1 仍漏 |
| **L5** | **Hard-negative 挤占 top-k** | 常见病 chunk 语义近但 DDx 错 | top-k 源组成 + MMR 前后 | MMR / 按 source 去重 | P1 | CPG c9 见 urticaria |
| **L6** | **HyDE 语义鸿沟** | 短 query 与 corpus 分布偏移 | 低置信时 HyDE A/B | HyDE 仅作低置信兜底 + 接地 | P2 | §13.4 规划 |
| **L7** | **SL-HyDE / CHR mimic 抑制** | 貌似合理错误 DDx 污染候选 | CHR vs baseline 候选纯度 | 二期 IMP-53 进阶 | P3 | 未做 |
| **L8** | **IVFPQ 双重近似** | nprobe + PQ 压缩； rare 邻居丢失 | nprobe sweep + IVFFlat 对照 | nprobe↑ / RFlat / IVFFlat | P2 | §17.5.2 非主因 |
| **L9** | **IDF 术语污染** | 泛化 symptom  term 在 PMC 海量出现 | §16 IDF(`pain`) PMC 8982 vs WikEM 897 | 分源 IDF / 差异化检索 | P0 | §16.3 缺陷① |
| **L10** | **多跳综合征链** | 单跳 query 够不到间接 gold 族 | 2-hop PrimeKG / 迭代检索 | KG 桥接 + 中间概念 | P2 | EXTERNAL §4a |
| **L11** | **Can't-miss 靠排序不可靠** | 低概率致命方向被 top-k 挤掉 | 无检索时 mandatory 是否仍漏 | IMP-56 cant_miss 硬层 | P1 | WikEM 部分自动 |
| **L12** | **重排后多查询增益消失** | RAG-Fusion 在强 reranker 后 NDCG 增益→0 | 先 RRF 召回再 cross-encoder | 两阶段：广召回→精排→抽取 | P1 | RAG-Fusion README caveat |
| **L13** | **长尾/罕见 gold 语料与嵌入欠表征** | peliosis/glucagonoma 在 corpus 稀疏；嵌入空间不可分 | Orphanet 补源 A/B；pathognomonic 直提 recall | Orphanet + **pathognomonic_markers 接入 branch-gen** | P1 | §23.11.3 可提名 5/9；**branch-gen 未接入**（原调研 **B8**） |

**branch-gen 特有问题（通用 RAG 文档较少强调）**：

1. **检索对象不是「答案段落」而是「DDx 实体集合」**——MRR@10 高仍可能 0 候选族（实体未 spot）。
2. **成功需「入口块→同篇鉴别块」关联**（§18 c1）——parent-document / closure 是必需件，非可选优化。
3. **多源组织互异**（§16.1）——统一 embedding 空间假设不成立，需分源路由。

---

### 17.4.1 原调研 Part A 简列（2026-06-25 文献+项目综述，入档索引）

> 下列为 branch-gen 阶段**项目内已纳入**的成因速查（原调研 Part A「简列不展开」）；细节见 §13/§17.3/§23/§31.13 各节。

| 主题 | IMP / 锚点 | 作用环节 | 状态 |
|---|---|---|---|
| 跨轴 query 扇出 | **IMP-52** | Query 构造 [1] | 待办 |
| Hybrid + cross-encoder 重排 | **IMP-53** | 检索 [2] | 待办 |
| HyDE / SL-HyDE / CHR | IMP-53 进阶 | 检索 [2] 低置信兜底 | 规划 |
| 篇内 DDx 闭包 | `expand_ddx_siblings` / **IMP-31** | 闭包 [3] | **已落地**（§19） |
| 度量修正（token→实体级） | 方案B / TODO-GL-10 | 评测尺子 | ✅ |
| 实体归一 | **IMP-58** | spotting/融合 | 待办 |
| 综合征别名 crosswalk | **IMP-59** | Query [1] | 待办 |
| SNOMED 分区墙 | 方案A / IMP-55 | 下游 [7]（非 RAG 召回） | §15 实锤 |
| 可达≠可排序 | §23.11.2 | LR 反向检索 | 已证；branch-gen 另径 |

---

### 17.4.2 原调研 Part B（B1–B11）入档对照 — **必读：ID 不可混读**

> **⚠️ 命名冲突（易误判）**：本节 **「原调研 B*」**（2026-06-25 外部文献综述）与 **§17.3 的 A/B/C/D 类 ID**、**§17.5 诊断实验代号** 是**三套编号**：
>
> | 代号 | 含义 | 示例 |
> |---|---|---|
> | **原调研 B6** | spotting/抽取损失（branch-gen **独有**子环节） | → 映射 **C4/C7** + 实验 **§17.5.1「漏斗 B6」** |
> | **§17.3 B6** | GARMLE-G① ctx-query **噪声**（完全不同） | 实测曾回退 |
> | **§17.5.1「B6 漏斗」** | 诊断**实验名**（retrieved vs spotted 拆分） | 非 §17.3 缺陷 ID |
> | **原调研 B3** | FAISS nprobe 泄漏 | → §17.3 **B8** + 实验 **§17.5.2「B3 nprobe」** |
> | **原调研 B10** | 相似度/阈值口径 | → 实验 **§17.5.3「B10 口径」**（≠ §17.3 B10 RootSelector） |

**召回链路**（每环均为潜在丢分点）：

```text
综合征标签 → query 构造 → 检索 DDx/etiology 片段 → 篇内闭包 → on-topic 门控
  → spotting/LLM 抽取疾病族 → 候选族集
成功判据：金标准疾病族是否进入候选族集（不含 SNOMED 分区/覆盖）
```

#### 原调研 B1–B11 完整对照表

| 原ID | 成因（摘要） | 为何专咬 branch-gen | 方案 | §17 映射 | 入档/实测状态 |
|---|---|---|---|---|---|
| **B1** | 嵌入器领域/训练目标不匹配；MiniLM 通用；CPG 实验纯 TF-IDF | 短 query↔长指南需语义近邻 | MedCPT / BioLORD 替换 MiniLM | **L1** + §17.3 **B2** + IMP-53 | **未做 A/B**；文献 JMIR 2026 e94241 已引 |
| **B2** | Query–Document 非对称编码 | 综合征 query vs 指南正文不在同一空间 | MedCPT 双塔（Query+Article） | **L2** + IMP-53 | 未落地 |
| **B3** | ANN IVFPQ **nprobe 泄漏**（初判 nprobe=1） | FAISS 默认近似丢近邻 | 调 nprobe / IVFFlat / RFlat | **§17.3 B8** + **L8**；实验 **§17.5.2** | **已跑**；**更正**：生产默认 **nprobe=32**，@k=30 **非瓶颈** |
| **B4** | 上下文碎片化；DDx 列表切散 | 单 chunk 无完整 DDx 列表 | parent-child / late chunking / auto-merge | **L3** | 闭包部分替代；无 parent-child 结构 |
| **B5** | Query 欠定；eponym/缩写鸿沟 | Pancoast↔limb deficit | RAG-Fusion + IMP-59 alias | **L4** + §17.3 **B5** | c1 仍漏（§19.3④ 机制通道） |
| **B6** | **spotting 抽取损失**（检索到但未抽出） | **branch-gen 独有**；QA-RAG 无此步 | `recall_llm` 兜底；扩 vocab/同义 | **C1–C7**；实验 **§17.5.1 漏斗**、**§17.5.6** | **已跑+跟进**；CPG extraction_loss=3/8→经 resolver **5–6/8**；瓶颈 **C4 非 C1** |
| **B7** | hard-negative / 常见病挤占 top-k | 挤掉低频 gold 族 | MMR / 按 source 去重 | **L5** + **L9** + C4 | **§17.5.6** PMC ~90% top-k；闭包灌池 **§19.5.2** 实锤 |
| **B8** | **长尾/罕见 gold** 语料与嵌入欠表征 | peliosis/glucagonoma 稀疏 | Orphanet；**pathognomonic 直提** | **L13**（本节补录）+ **D3** + §17.7 P1 | pathognomonic **§23.11.3 可提名 5/9**；**branch-gen 候选层未接入** |
| **B9** | 多跳/间接综合征链 | 单跳 query 够不到 gold | PrimeKG 桥接；迭代检索 | **L10** | 未做 |
| **B10** | 打分/阈值/度量口径错配 | 误杀或权重方向反 | 核对 metric/threshold/w 方向 | 实验 **§17.5.3**（≠ §17.3 B10） | **已跑**；L2 方向正确；threshold **轻微** |
| **B11** | **评测尺子缺失**（N 小、无 recall@k、无上界） | 无法分「真漏 vs 度量低估 vs 排序埋没」 | IMP-54 oracle + recall@k CI | **IMP-54/62** + **§18 oracle** + **§19.5** | **部分落地**（见下） |

#### 原调研 B11 / B6 / B8 入档明细（用户关切项）

**B6（spotting 抽取）— 已入档，但分散在三处，此处合并：**

| 维度 | 入档位置 | 结论 |
|---|---|---|
| 排查原因定义 | **§17.3 C 类**（C1–C8）；**§17.4.2 上表** | branch-gen **独有**；「retrieved≠spotted」 |
| 诊断实验 | **§17.5.1**（漏斗）；**§17.5.6**（C1/C4/C6/B4/L5 跟进） | CPG 3/8 抽取损失；**C4 拥挤 > C1 vocab** |
| 修复路线 | **IMP-63**（§17.7 P0）；**§19.5.2**（闭包勿灌 40 槽） | recall_llm + MMR + 解耦 k |
| 脚本 | `eval_branch_rag_recall_diagnosis.py`；`eval_branch_diag_followup.py` | 报告 `branch_rag_recall_diagnosis.json` |

**B8（长尾罕见 + pathognomonic）— 部分入档，缺口已补 L13：**

| 维度 | 入档位置 | 缺口 |
|---|---|---|
| pathognomonic 直提 | **D3**、§17.7 P1、§19.3④（c1 机制通道） | **未接入** `GuidelineBranchSource.recall()` 主路径 |
| Orphanet 补源 | **L13**（本节补录） | 未实施 |
| 嵌入 rare 不可分 | **L1/L13** 交叉 | MedCPT A/B 未跑 |

**B11（评测尺子）— 部分入档，分项状态：**

| 尺子 | 脚本/节 | 状态 |
|---|---|---|
| 数据源上界（entry+closure） | **§18** `eval_cpg_oracle_recall.py` | ✅ **8/8=100%** |
| 检索 vs spotting 漏斗 | **§17.5.1** IMP-62 | ✅ N=8 hand 标签 |
| nprobe / 口径 / top_k | **§17.5.2–17.5.4** | ✅ |
| recall@k 全曲线（493k IVFPQ rare） | IMP-54；§17.5.3「未测」 | ❌ **待 IMP-54** |
| `eval_coverage_oracle.py`（oracle-union + 逐源边际） | §13.5 / IMP-54 | ❌ **待建**（§18 为 entry+closure，非 union 边际） |
| 扩样 + L2/轴可分性 | **§19.5** `eval_branch_multilevel.py` | ✅ n=14；区分度 0.395 |
| N=8 小样本局限 | **§17.5.6**、§19.5.4 | ✅ 已记录 |

#### 原调研「立即可查四项」— 执行状态（2026-06-26）

| 原建议 | 对应原ID | 执行 | 结论 |
|---|---|---|---|
| FAISS nprobe 量化 | B3 | **§17.5.2** | 默认 nprobe=32；@k=30 **非主因** |
| 相似度/阈值口径 | B10 | **§17.5.3** | L2 方向正确；**非主因** |
| 检索 vs spotting 拆分 | B6 | **§17.5.1** + **§17.5.6** | CPG 瓶颈在 **spotting/C4** |
| MedCPT 编码器 A/B | B1/B2 | Playbook **E4** | **待跑** |

---

### 17.5 已执行诊断实验（2026-06-25，可复现）

**命令**：

```bash
PYTHONPATH=src python scripts/eval_branch_rag_recall_diagnosis.py --index both
# 报告 → data/cpg/eval/branch_rag_recall_diagnosis.json
# 日志 → logs/branch_rag_recall_diagnosis.log（若 tee）
```

**设定**：hand 综合征标签；`GuidelineBranchSource(top_k=30, max_candidates=40)`；cpg_index 闭包 cap +60。

#### 17.5.1 漏斗 B6：检索层 vs spotting 层（核心实验）

> **实验代号说明**：此处 **「漏斗 B6」** = 诊断实验名（retrieved vs spotted 拆分），对应**原调研 Part B 的 B6（spotting 抽取损失）**；**≠** §17.3 缺陷 **B6**（GARMLE-G① ctx-query 噪声）。

| 索引 | 片段含 gold | 候选含 gold | 抽取损失 | 双漏 | 解读 |
|---|---:|---:|---:|---:|---|
| rag_index (FAISS MiniLM, 493k) | 6/8 (75%) | 6/8 (75%) | **0** | c1,c13 | 瓶颈=**纯检索** |
| cpg_index (TF-IDF, 204k) | 7/8 (87.5%) | 4/8 (50%) | **3** | c1 | 瓶颈=**spotting** |

**逐例明细（cpg_index）**：

| idx | gold | syndrome (hand) | 检索 | spot | bucket | n_snip | top-5 候选（spotter 产出） |
|---:|---|---|:---:|:---:|---|---:|---|
| 1 | pancoast tumor | focal limb neuro deficit | ✗ | ✗ | neither | 24 | IBD, stroke, dementia, patella alta, PPA |
| 9 | leukemoid reaction | leukocytosis | ✓ | ✗ | **retrieved_not_spotted** | 24 | urticaria, MI, intellectual disability, MM, … |
| 13 | glucagonoma | hyperglycemia with skin | ✓ | ✗ | **retrieved_not_spotted** | 24 | urticaria, gastric cancer, MI, … |
| 17 | CML | leukocytosis | ✓ | ✓ | both | 24 | urticaria, MI, …（含 CML 通路） |
| 18 | peliosis (liver) | acute abdomen shock | ✓ | ✗ | **retrieved_not_spotted** | 24 | urticaria, vomiting, ectopic pregnancy, … |
| 22 | PHPT | hypercalcemia | ✓ | ✓ | both | 24 | GERD, asthma, HF, pneumonia, metastases |
| 23 | adhesions | bowel obstruction | ✓ | ✓ | both | 24 | vomiting, LBO, nausea, … |
| 24 | foreign body | unilateral nasal discharge | ✓ | ✓ | both | 24 | foreign body, pulsatile tinnitus, … |

**rag_index 对照（同设定）**：c1/c13 **双漏**；c9/c17/c18/c22/c23/c24 双命中。c13 在 rag 连片段都无 gold（StatPearls 缺 glucagonoma 上下文），cpg 片段有但 spotter 仍失败。

#### 17.5.2 诊断 B3：FAISS nprobe 全矩阵（rag_index）

> **实验代号说明**：此处 **「诊断 B3」** = 原调研 Part B **B3（nprobe 泄漏）** 的验证实验；**≠** §17.3 缺陷 **B3**（top_k 过小漏同篇 DDx）。

索引：`IndexIVFPQ`，metric=**L2**，**默认 nprobe=32**（非 1）。

**k=30（与 recall 默认一致）**：

| nprobe | 片段含 gold | spotting 含 gold |
|---:|---:|---:|
| 1 | 6/8 | 6/8 |
| 4 | 6/8 | 6/8 |
| 16 | 6/8 | 6/8 |
| 64 | 6/8 | 6/8 |
| 128 | 6/8 | 6/8 |
| 256 | 6/8 | 6/8 |

**k=8**：

| nprobe | 片段含 gold | spotting 含 gold | 抽取损失 |
|---:|---:|---:|---:|
| 1 | 5/8 | 5/8 | 0 |
| 4 | 6/8 | 5/8 | 1 |
| 16 | 6/8 | 4/8 | 2 |
| 64 | 6/8 | 5/8 | 1 |

**结论**：@k=30 **nprobe 不是瓶颈**；@k=8 小 k 部署时 **nprobe≥4** 且注意 nprobe↑ 时 spotting@8 可能反降（更多噪声片段进入 spotter，与 C5 一致）。

#### 17.5.3 诊断 B10：FAISS 度量 / 阈值 / ANN 口径（rag_index）

> **实验代号说明**：此处 **「诊断 B10」** = 原调研 Part B **B10（相似度/阈值口径）** 的验证实验；**≠** §17.3 缺陷 **B10**（RootSelector 弱标签）。

| 检查项 | 结果 |
|---|---|
| FAISS metric | **L2**（距离越小越相似） |
| 默认 nprobe | 32 |
| `w=1/(1+score)` | L2 下小距离→大 w，**方向正确** |
| 5k 子样本 brute top10 vs Flat top10 | **overlap=10/10** |
| threshold 0.0→0.3（case9 leukocytosis） | 30→28 hits（**-2，轻微**） |
| threshold（case1/c13） | 无变化 |

**未测 / 待 IMP-54**：全库 493k IVFPQ 对 rare entity 的 recall@k 曲线；PQ 压缩在 nprobe=nlist 时仍 <100% recall（FAISS FAQ）。

#### 17.5.4 CPG TF-IDF top_k 敏感性（C5 实证）

| top_k | 片段含 gold | spotting 含 gold | Δ spot |
|---:|---:|---:|---|
| 8 | 5/8 (62.5%) | **6/8 (75%)** | — |
| 30 | **7/8 (87.5%)** | **4/8 (50%)** | **−25pp** |

→ **禁止**用单一 top_k 同时服务检索与 spotting；推荐：**retrieve_k=50 → 门控/MMR → extract_k=15**。

#### 17.5.5 与 §18 Oracle 上界对照

| 指标 | 数值 | 含义 |
|---|---:|---|
| entry+closure 上界 | **8/8 (100%)** | 数据+闭包可达 |
| cpg spotting | 4/8 (50%) | 工程损耗 **−50pp** |
| cpg 片段检索 | 7/8 (87.5%) | 距上界 **−12.5pp** |
| §15 cpg_llm 覆盖 (curated-free) | 5/8 (62.5%) | 含分区损耗 |

#### 17.5.6 C1 / C6 / B4 / L5 补充诊断（2026-06-26，`eval_branch_diag_followup.py`）

补齐 §17.3/§17.4 中此前未实测的开放项；cpg_index，hand 标签，经**权威 `run_b6_split` 路径**（含 resolver 扩展）。

| 诊断 | 结论 | 证据 | 影响/动作 |
|---|---|---|---|
| **C1 spotter vocab 缺口** | **证伪——非瓶颈** | 8/8 gold 家族**均在** SNOMED disorder vocab（含 c1 `…carcinoid tumor of lung`、c13 `islet cell tumor`、c17 `chronic myeloid leukemia`） | **不需扩 vocab**；spotting 失败属 C4 而非 C1 |
| **C4 n-gram/cap 拥挤** | **确认为 spotting 瓶颈** | c13/c18：gold 既在片段又在 vocab，仍未进候选（被高频噪声挤出 40 槽 / 表面形未 n-gram 命中） | **IMP-63（P0）**：recall_llm + MMR + 解耦 k |
| **C6 WikEM wiki_links 注入** | **零增益（N=8）** | spotted 0.625（on）= 0.625（off）；`recovered_by_wiki=[]`；retrieved 0.875 不变 | 机制已落地、保留；**本基准无实效**，更正此前"显式 DDx 直用有益"的隐含预期 |
| **B4 on-topic 门控误滤** | **非问题** | 8/8 case 门控 pass-rate = **220/220 (100%)**，未滤掉任何片段 | cpg_index 上**去优先级**；NICE 分源门控仍待生产索引验证 |
| **L5/L9 PMC 淹没 spotter** | **确认** | top-k 源组成 **~90% PMC**（c1 207/220、c9 200/220、c22 215/220）；少数源仅个位~20 槽 | **IMP-61 UNION + MMR**（§19.3②：纯等权 RRF 有害，须 UNION） |

**对 §17.5.1 基线的更正**：§17.5.1 记录 cpg spotting 4/8(50%)，**系 resolver 机制扩展落地前的旧值**；当前经 resolver（leukocytosis→CML 等）spotting 已升至 **5–6/8（62.5–75%）**。

**小样本不稳定性（直接动机 → §19 重做）**：c18 peliosis 在不同进程间 spotting 命中在 5/8↔6/8 间抖动（TF-IDF 打分并列 + 候选边界 + 40 槽截断），c13 稳定漏。**N=8、且仅评 L1 家族宽匹配，区分度与稳定性均不足**——印证需纳入 L2/L3 + 扩样（§19 重做）。

**净结论（修复优先级再聚焦）**：spotting 瓶颈是 **C4（拥挤/表面形），非 C1（vocab）**；门控 B4 无碍；PMC 淹没（L5/L9）实锤。**vocab 扩充与 wiki_links 直抽不在关键路径**。

> **§19.6 更正**：本节曾提"IMP-61 UNION 降噪为正解"——**已证伪**。UNION/等权 RRF 在 n=14 上均稀释 PMC 主干而**有害**（0.235）；C4 的正解是 **IMP-63 闭包移出候选池 + IMP-64 本体归族（族层竞争）+ C7 LLM 抽取**，而非差异化检索降噪。详见 §19.6#1/#3/#5。

---

### 17.6 后续诊断 Playbook（迭代时按此执行）

**每次改检索/抽取代码后**：

1. **跑漏斗诊断**  
   `python scripts/eval_branch_rag_recall_diagnosis.py --index both`  
   关注：`extraction_loss`、`retrieved_not_spotted` 是否下降。

2. **跑 Oracle 上界（防误补源）**  
   `python scripts/eval_cpg_oracle_recall.py`  
   若 entry+closure 仍 100%，**不要**优先加数据源。

3. **分轨评测（hand vs LLM 标签）**  
   - hand 标签 → 纯 RAG/spotting 回归  
   - LLM 标签 → `eval_cpg_branch_pipeline.py` 端到端

4. **新增 case 时扩充**  
   - `GOLD_FAMILY_TOKENS`（eval_branch_creator_isolated.py）  
   - oracle 脚本 syndrome anchor 表  
   - 记录 entry-direct vs closure 是否仍 100%

5. **单缺陷 A/B 矩阵（建议顺序）**  
   | 实验 | 变量 | 成功信号 |
   |---|---|---|
   | E1 | IMP-61 差异化 vs 统一 TF-IDF | WikEM 式入口 recall↑；cpg spotting↑ |
   | E2 | IMP-63 recall_llm 兜底 vs 纯 spotter | extraction_loss 3→0 |
   | E3 | retrieve_k=50 + MMR vs k=30 flat | 检索≥7/8 且 spotting≥6/8 |
   | E4 | MedCPT vs MiniLM（同 nprobe） | c1/c13 检索层↑ |
   | E5 | IMP-59 alias + pathognomonic 直提 | c1 pancoast 检索↑ |

**勿用作唯一指标**：MRR@10（不反映实体族是否进候选）；单跑 token 子集 Recall（方案B 已修正）。

---

### 17.7 当前阶段修复优先级（诊断驱动，2026-06-25）

> **与 §17.2.1 解锁序的关系**：本节为 **§18 已证数据足 + §17.5 漏斗已定位** 后的**诊断修复序**；若生产索引仍无 CPG（A 层未解锁），须并行推进 **IMP-31**（见 §17.2.1「解锁序」）。

| 优先级 | 动作 | 针对缺陷 | 预期收益 | 实测（§19.6） |
|---|---|---|---|---|
| **✅ 落地** | **IMP-63** 闭包→grounding（移出候选池）+ `extractor=spotter+llm` | C4,C5,C7 | 隔离闭包噪声 + LLM 兜底 | **A5 0.768（L1tgt 0.929）；闭包方差消除** |
| **✅ 落地** | **IMP-64** 本体反向归族（覆盖增广） | C4,§21.5 | 族层竞争、贴合诊断树 | **轴可分 0.571→0.643；综合持平** |
| ⚠️ 落地但**弃用** | **IMP-61** UNION/RRF 接入 recall | A3,B7,L9 | （原期）降噪 | **0.235，PMC 稀释有害；仅留 §16 入口场景** |
| ⚠️ 落地**待数据** | **IMP-60** 轴极注入 | 轴可分性 | 双极保证 | **本评测集 cant_miss 源未覆盖 → 无效，需扩源** |
| **P0** | **IMP-31** 生产索引+元数据 | A1,A2 | 闭包/门控在生产生效 | 未落地 |
| **P1** | IMP-58/59 归一+eponym | B5,C1,c1 | 机制名/eponym 可达（c1） | 未落地 |
| **P1** | pathognomonic_markers 接入候选层 | D3,L5 | c1/c13 直提 | 未落地 |
| **P2** | IMP-53 MedCPT hybrid | B2,L1,L2 | 语义召回 | 未落地 |
| **P2** | IMP-52 跨轴扇出 | B1 | 多轴 DDx 不漏 | 未落地 |
| **P2** | IMP-54/62 常驻 recall@k CI | B8,L8 | 防回归 | `eval_branch_confounder_matrix.py` 已常驻 |

---

### 17.8 任务编号（IMP-62/63 与 §16/§18 衔接）

| ID | 任务 | 交付物 | 状态（§19.6） | 依据 |
|---|---|---|---|---|
| **IMP-63** | spotting 路径重构（闭包→grounding + spotter+llm，参数化） | `guideline_branch_source.py` `_recall_v2` | **✅ 已落地**（A5=0.768；方差消除） | C4,C5,C7 |
| **IMP-64** | 本体反向归族（is_a 覆盖增广，族层竞争） | `guideline_branch_source.py` `_rollup_candidates` | **✅ 已落地**（轴可分 0.571→0.643） | §21.5 |
| **IMP-61** | 差异化检索器（含 `fusion='union'`） | `DifferentiatedCPGRetriever` | ⚠️ 落地但**主路径弃用**（PMC 稀释 0.235） | §16；B7,L9 |
| **IMP-60** | 强制轴极注入（cant_miss 双极） | `guideline_branch_source.py` `_inject_axis_poles` | ⚠️ 落地**待扩 cant_miss 源**（本集无效） | §14.7,§19.5 |
| **IMP-62** | 漏斗诊断常驻化 + 混杂矩阵 | `eval_branch_rag_recall_diagnosis.py`、`eval_branch_confounder_matrix.py`（含 **multilevel_hard / mece / mece_hard**） | ✅ 常驻 | §17.5、§19.6、**§19.8** |
| **IMP-31** | CPG 并入生产索引+元数据 | 改 build_tfidf/rag_index | ❌ 未落地（P0 解锁卡点） | A1,A2 |
| **IMP-58/59** | 实体归一 + syndrome alias/eponym | entity_norm + crosswalk | ❌ 未落地（P0：c1 唯一出路） | B5,C1 |
| **IMP-54** | oracle-union + recall@k 曲线 | `eval_coverage_oracle.py` | ❌ 未落地 | §17.2 Step 0–3 |

**三节关系（勿混读）**：

- **§16**：统一检索为何损害入口召回 → **差异化检索算法**（WikEM 138 query 实证）。
- **§17**：branch-gen **候选族召回**漏斗 → spotting 瓶颈为 **C4 拥挤**；**§19.6 已落地 IMP-63/64** 修复（闭包移出池 + LLM 抽取 + 本体归族）。
- **§18**：数据源 **100% 闭包可达** → 瓶颈不在缺源，在 IMP-31/63 工程兑现。
- **§19.6**：混杂受控重评 → 证实"闭包灌池有害（C4）非闭包本身"、LLM 抽取（C7）为最大杠杆、UNION/MMR-trim 弃用。

**串联路径（§19.6 后更新）**：`§18 证数据足 → §17/IMP-63 闭包移出池+LLM 抽取（✅）→ §21/IMP-64 本体归族提轴可分（✅）→ IMP-58+eponym 补 c1（待）→ §15 方案A 把候选兑现为覆盖`。

**全链路逐步细节**（raw chunk → LLM payload、各 arm 消费方式、spotting 术语）：**§20**。

---

### 17.9 尚待落地缺陷清单（2026-06-26 汇总，§19.6 后）

> **读法**：本表汇总 §17.3（A/B/C/D）+ §17.4（L1–L13）全部缺陷的**当前落地状态**，按"是否仍待落地"分三组。**✅ 已落地/已证非瓶颈/下游**的项不再阻塞 branch-gen 召回；**🔴 P0 / 🟡 P1 / ⚪ P2** 为**尚待落地**的真实缺口。

#### A. 🔴 P0 — 仍阻塞、最高优先

| 缺陷 | ID | 现状 | 阻塞影响 | 下一步 |
|---|---|---|---|---|
| **新 CPG 源未进生产索引**（A1） | IMP-31 | ❌ 生产 `rag_index` 仅 StatPearls+Textbooks | **所有 CPG 源（WikEM/Merck/PMC/NICE）在生产零贡献**；§19.6 全部成果跑在独立 `cpg_index`，未进生产 | 重建 FAISS/TF-IDF，写入 `source_id/chunk_type/entry_type/syndrome_anchor` |
| **chunk 元数据缺失**（A2） | IMP-31 | ❌ 生产 metadata 无 `chunk_type/source_id` | 闭包/门控/grounding 在生产空转 | 同上（IMP-31 必带元数据） |
| **c1 机制/eponym 鸿沟**（B5/L4） | IMP-58+eponym | ❌ 未落地 | 四检索臂皆漏 c1（Pancoast↔臂痛/Horner）；**唯一非检索出路** | scispaCy UMLS linker + eponym/机制直提名通道 |

#### B. 🟡 P1 — 应落地、非阻塞主链

| 缺陷 | ID | 现状 | 说明 |
|---|---|---|---|
| **轴极注入数据缺口** | IMP-60 | ⚠️ 代码落地，**cant_miss 源未覆盖 lab/endocrine 综合征** | §19.6#7：`cant_miss_by_syndrome_wikem.json` 用症状类目 id，与 hypercalcemia/cushing 等 token 不重叠 → 实测无效。**须扩 can't-miss 源**（lab/内分泌综合征）才能激活 |
| **单模板 query**（B1） | IMP-52 | ❌ 未落地 | 仅 "differential/causes of {S}"，漏 red-flag/anatomical/workup 轴；跨轴 5 路 query 扇出 |
| **综合征别名 crosswalk**（B5/L4） | IMP-59 | ❌ 未落地 | root↔WikEM/Merck/PMC anchor + UMLS 同义；c1 部分 |
| **长尾 + pathognomonic 未接入 branch-gen**（B8/L13/D3） | IMP-53(Orphanet)/pathognomonic | ❌ branch-gen 候选层未接入 | §23.11.3 可提名 5/9，但 `pathognomonic_markers` 仅在 LR 通道，未进 `recall()` 候选层（c1/c13 直提） |
| **稀疏-only 无 dense / 编码器不匹配**（B2/L1/L2） | IMP-53 MedCPT | ❌ 未做 A/B | cpg 实验纯 TF-IDF；MedCPT 双塔语义召回未验证 |
| **can't-miss 靠排序不可靠**（L11） | IMP-56 | 🟡 WikEM 部分自动 | 低概率致命方向被 top-k 挤掉；需硬下界层（与 IMP-60 同源） |
| **重排后多查询增益消失**（L12） | 两阶段广召回→精排 | ❌ 未做 | RAG-Fusion 在强 reranker 后增益→0；先广召回再 cross-encoder |

#### C. ⚪ P2 — 长尾/低杠杆

| 缺陷 | ID | 现状 |
|---|---|---|
| 跨轴扇出深化（B1） | IMP-52 进阶 | 未做 |
| HyDE / SL-HyDE / CHR 低置信兜底（L6/L7） | IMP-53 进阶 | 未做 |
| 多跳综合征链（B9/L10） | PrimeKG 2-hop | 未做 |
| IVFPQ recall@k 全曲线（B8/L8） | IMP-54 | 非主因，待 CI |
| spotter `min_len`/短词漏 spot（C2） | UMLS linker | 待评估（IMP-58 顺带） |
| oracle-union + 逐源边际（B11） | IMP-54 | 待建（§18 为 entry+closure，非 union） |

#### D. ✅ 已闭环（不再阻塞 branch-gen 召回）

| 项 | 结论 | 出处 |
|---|---|---|
| **C4 候选池拥挤 / 闭包灌池** | ✅ IMP-63 闭包→grounding 修复（含方差） | §19.6#1,2 |
| **C5 解耦 retrieve/extract k** | ✅ 参数化；⚠️ MMR-trim 对确定性 spotter 有害（仅用于 LLM grounding） | §19.6#4 |
| **C7 LLM 抽取未默认** | ✅ `extractor=spotter+llm`（最大杠杆，L1tgt 0.929） | §19.6#6 |
| **本体归族 / 轴可分性** | ✅ IMP-64 覆盖增广（0.571→0.643） | §19.6#3 |
| **C1 spotter vocab 缺口** | ✅ 证伪——非瓶颈（gold 均在 vocab） | §17.5.6 |
| **C6 WikEM wiki_links** | ✅ 已落地；本基准零增益 | §17.5.6 |
| **B3/B8 nprobe / IVFPQ** | ✅ 已跑——@k=30 非主因 | §17.5.2 |
| **B4 on-topic 门控** | ✅ 非问题（pass 100%） | §17.5.6 |
| **B6/L5/L9 PMC 淹没 + 等权 RRF/UNION** | ✅ 差异化主路径**弃用**（PMC 稀释有害）；unified+grounding 为正解 | §19.3②、§19.6#5 |
| **C8 度量 token 子集低估** | ✅ 方案B 已修正 | §31.13.17 |
| **B10 度量/阈值口径** | ✅ 已跑——方向正确、threshold 轻微 | §17.5.3 |
| D1/D2/D3 SNOMED 分区墙/轴框定/LR 可达≠可排序 | ➡️ 下游覆盖问题（§15 方案A/IMP-55），**非 branch-gen 召回** | §17.3 D 类 |

**一句话现状**：branch-gen **召回/抽取层**的核心缺陷（C4/C5/C7 + 轴可分性）已由 **IMP-63/64 闭环**；**真正剩余的 P0 是 IMP-31（生产索引落地）与 IMP-58（c1 机制鸿沟）**——前者决定上述成果能否在生产生效，后者是唯一无法靠检索解决的 case。

---

## 18. Oracle 上界核验：全 CPG 源「入口→篇内闭包」是否可达金标准（2026-06-25）

> **核验问题**（用户）：当前数据源中，与**根节点综合征/症状群入口**相关联的条目里，是否含有正确答案相关的鉴别信息，支持正确分支生成？目的：**检索质量拉满**时最高能达到的召回率（上界）。
>
> **关键约束**（用户修正）：**不只统计 StatPearls，须统计所有 CPG 源**；且各源结构不同（§16.1）——有些源检索到的是**入口块**，须从入口块**关联到真正的鉴别信息**。
>
> **脚本**：`scripts/eval_cpg_oracle_recall.py`　**报告**：`data/cpg/eval/cpg_oracle_recall.json`

### 18.1 方法：不排序、只查「可达性」（区别于 §17 的检索器实测）

§17 量化的是**当前检索器**召回；本节量化**数据源理论上界**——把检索质量视为完美，三层逐级放宽：

| 层级 | 定义 | 含义 |
|---|---|---|
| **entry-direct** | gold 出现在**入口块本身**文本 | 最严：单 chunk 自带答案 |
| **entry+closure** | gold 出现在入口块**同 `source_id` 全篇闭包**（含 WikEM `wiki_links` DDx 列表） | **现实上界**：检索命中入口后做篇内闭包扩展即可达 |
| **full-corpus** | gold 在任意 CPG chunk 出现 | 绝对下界（不要求与入口关联） |

**多源结构感知**（§16.1）：入口匹配同时扫 `syndrome_anchor`（PMC=标题 / WikEM=主诉）、`section_path`/`title`（NICE/协会/Merck=指南章节名，**无 anchor**）；闭包按 `source_id` 聚合同篇全部 chunk，把"入口块"关联到承载真正鉴别信息的 sibling chunk。综合征锚词含 **US/UK 双拼写**（NICE 用 `-aemia/-oedema/tumour`）。N=8（排除体征 gold case14）。

### 18.2 实测结果（360,234 chunks 全扫）

| 层级 | 召回 | 说明 |
|---|---:|---|
| entry-direct | **7/8 = 88%** | 唯一 miss：c1 Pancoast |
| **entry+closure** | **8/8 = 100%** | **现实上界** |
| full-corpus | 8/8 = 100% | 绝对下界（含宽匹配假阳，仅参考） |

**逐例（closure 命中源 = 真正承载鉴别信息的源）**：

| idx | gold | 入口块数 | 入口文章数 | entry-direct | closure 命中源 |
|---:|---|---:|---:|:---:|---|
| 1 | Pancoast | 124 | 7 | **✗** | **PMC-OA** |
| 9 | leukemoid | 14 | 4 | ✓ | PMC-OA |
| 13 | glucagonoma | 141 | 20 | ✓ | PMC-OA |
| 17 | CML | 188 | 11 | ✓ | ASH, Merck, PMC-OA |
| 18 | peliosis | 254 | 23 | ✓ | Merck, PMC-OA, WikEM |
| 22 | PHPT | 149 | 8 | ✓ | Merck, NICE, PMC-OA |
| 23 | adhesions | 230 | 12 | ✓ | Merck, NICE, PMC-OA |
| 24 | foreign body | 10 | 3 | ✓ | Merck, WikEM |

### 18.3 核心结论

1. **数据源充分性已坐实：全 CPG 源「入口→篇内闭包」上界 = 100%（8/8）。** 每个 case 的金标准鉴别信息都能从其综合征入口经同篇闭包到达——**不存在"整族数据缺失"**。
2. **c1 是"入口块需关联到鉴别信息"的活证据**：其 124 个入口块**没有一个**直接提到 Pancoast，但 PMC 同篇 sibling chunk 提到——正印证用户判断（"有些源检索到的是入口块，需从入口块关联到真正的鉴别信息"）。**篇内闭包（`expand_ddx_siblings`）不是可选优化，而是召回必需件**。
3. **瓶颈定性确认在工程而非数据**：上界 100% vs §15 实测 56–62%（CPG+方案A）/ §17 检索层 75–87.5%、spotting 层 50% ⇒ **38–50pp 的差距全部是检索排序 + spotting 抽取的工程损耗**，应由 IMP-61（差异化检索）+ IMP-63（spotting 重构 + 闭包扩展生产化）+ IMP-31（元数据解锁闭包）兑现，而非继续补数据源。
4. **多源互补性**：closure 命中以 **PMC-OA 为主干**（覆盖全部 8 例），Merck/WikEM/NICE/ASH 提供高密度结构化补充（c17/c22/c23/c24 由 Merck/NICE/WikEM 命中）——支持 §16 差异化检索"为少数高价值源保留名额"的必要性。

### 18.4 可信度与局限

- **closure 命中源收敛可信**（PMC/Merck/WikEM/NICE/ASH）；**full-corpus 的"全源命中"含宽匹配假阳**——`adhesions`/`foreign body`/`leukemia` 这类常见词 gold 在无关指南里也出现，故 full-corpus 仅作绝对下界，不用于源归因。
- 综合征锚词为**核验用途**手工设定（含 c1 `shoulder/arm pain`、c18 `abdominal pain` 等较泛词，入口块数偏大），仅用于度量上界、不进入生产路径；主管道仍 curated-free（LLM RootSelector，§15）。
- N=8 小样本，上界结论待 IMP-54 扩样复核；但"数据足、瓶颈在检索/spotting"的定性与 §17 漏斗诊断**互相印证、方向一致**。

## 19. 落地 IMP-31 闭包 + IMP-61 差异化检索 + 新方法验证（2026-06-26）

> **目标**（用户）：落地 IMP-31（篇内闭包生产化）+ IMP-61/§16（数据集特异检索）；**若二者仍无法实现"入口块→信息块关联"与"利用散落多块的鉴别信息"，则设计新方法**。
>
> **产物**：
> - `RAGRetriever.expand_ddx_siblings`（升级）：`source_id` 倒排索引（O(hits) 而非 O(corpus)）+ WikEM `wiki_links` 合成 DDx 块注入。
> - `DifferentiatedCPGRetriever`（IMP-61）：分源子索引 + 源级 query 路由 + RRF 融合 + 入口 boost；`RAGRetriever` 兼容接口。建索引脚本 `scripts/build_differentiated_cpg_index.py`（输出 `data/corpus/cpg_diff_index/`，5 桶 295k 行）。
> - `AnchorAugmentedRetriever`（**新方法**）：锚点/章节结构化入口选择 **UNION** 基检索（保 PMC 主干），再接闭包。
> - 验证脚本 `scripts/eval_diff_retriever_validation.py`，报告 `data/cpg/eval/diff_retriever_validation.json`。

### 19.0 阅读指南：术语、指标与实验臂代号

> **本节结构**：§19.1–§19.4 = 首批验证（9 题 rare，臂代号 **S/D**）；§19.5 = 多级重做（14 题 common，臂代号 **unified/…**）；§19.6 = 混杂受控重评（**A** 臂，落地 IMP-63/64/60）；**§19.7 = 表 C 待办项落地 + Hybrid/全栈 LLM 补跑**（新增 **A6–A12** 臂）；**§19.8 = 8 题难病四大指标 + MECE 全矩阵补跑**（2026-06-27）。**权威结论**：检索/闭包/rollup/LLM → **§19.6**；表 C（fanout/提名/硬层/MedCPT）→ **§19.7**；**难病集 hComp / MECE₈** → **§19.8**；**生产选型** → **§19.0.6b 末段速查**（14 题 LLM 有效 Comp 仍以 **gnn-llm A9l=0.812** 为准）。
>
> **速查入口**：参数改哪个旋钮、对应 §17 哪条缺陷 → **§19.0.8 表 D**；参数完整说明 → **§19.0.8 表 A–C**；IMP 怎么配 → **§19.0.8 表 E**；**新增臂代号怎么读** → **§19.0.6b**。

#### 19.0.1 三个平面：chunk / 疾病实体 / 族（读臂代号前必看）

branch-gen RAG 实验里，**三个计数对象不可混读**（详见 §21.1）：

| 平面 | 计量对象 | 典型参数 | 作用 |
|---|---|---|---|
| **检索平面（chunk）** | 检索返回的 **文本块** 数 | `top_k=30`；闭包后可扩至 200+ | 决定 `_spot()` / LLM 能看到哪些 prose |
| **抽取平面（疾病实体）** | spotter/LLM 产出的 **具体病名** 数 | `max_candidates=40` | 决定哪些疾病进入候选 dict |
| **分区平面（族/域）** | MECE **L1 分支族** | 方案A 或 SNOMED 分区 | BranchCreator 最终分支结构 |

**40 ≠ 40 个 chunk**：`max_candidates=40` 是 **40 个疾病实体**，不是 40 个检索块。闭包把 sibling chunk **灌进 spotter 可见文本**时，每个块又可 `_spot()` 出多个病名 → 常见病（MI、urticaria）在多块重复累加分 → **挤掉 rare gold**（§21.3 C4）。

#### 19.0.2 闭包三种模式：灌候选池 vs grounding vs 关闭

**闭包（`expand_ddx_siblings`）**：检索命中某篇指南的**入口块**后，把**同篇**（同 `source_id`）内所有 differential/evaluation 等 sibling 块，以及 WikEM 的 `wiki_links` 合成块，一并拉入上下文。

| 模式 | 代码参数 | 闭包块去哪？ | 对 spotter 候选池的影响 | 典型用途 |
|---|---|---|---|---|
| **灌候选池**（legacy） | `closure_mode='pool'`（默认）或旧路径 S1/D* | 与 top-k 检索块**合并**，全部进 `_spot()` | sibling 引入更多常见病实体 → **40 槽拥挤**（C4）；§19.5 常见病 mandatory 覆盖下降 | §19.2 S1、§19.5 unified-closure、A0_legacy |
| **grounding**（IMP-63） | `closure_mode='grounding'` | **只**进 `_retrieve_snippets`（≤24 条 excerpt），**不进** `_spot()` 的 snippet 集合 | spotter 候选池**不受闭包 sibling 污染**；闭包仍可供 **LLM 抽取**（`recall_llm` / 方案A） | A1_grounding、推荐生产配置 |
| **关闭** | `closure_mode='off'` 或 `expand_ddx_siblings=identity` | 无 sibling 扩展 | 仅 top-k 原始检索块参与 spot | S0、A0b_noclosure |

```text
                    ┌─ 灌候选池 (pool) ─────────────────────────────┐
检索 top_k=30 ──→   │  + expand_ddx_siblings (+60~80 sibling)      │
                    │         ↓ 全部合并                            │
                    │    _spot(title+content)  →  scored{病名:w}   │
                    │         ↓ 累加 + 截断                        │
                    │    max_candidates=40  ← C4 拥挤发生在这里     │
                    └──────────────────────────────────────────────┘

                    ┌─ grounding (IMP-63) ──────────────────────────┐
检索 top_k=50 ──→   │  spotter 池：仅原始 top-k 块（无 sibling）    │
                    │         ↓                                     │
                    │    _spot() → max_candidates=40（无闭包噪声）   │
                    │                                               │
                    │  并行：闭包 sibling → _retrieve_snippets       │
                    │         ↓ ≤24×400 字                          │
                    │    recall_llm / 方案A（LLM 读 excerpt 抽 DDx） │
                    └──────────────────────────────────────────────┘
```

**为何 §19.5 说「闭包有害」而 §19.6 又说「闭包无害」？**  
§19.5 测的是 **灌候选池**（pool）；§19.6 证实 harmful 的是 **灌池这一用法**，不是闭包本身——改为 **grounding** 后指标与「完全关闭闭包」相同（0.702），且 LLM 臂（A5）仍能吃到闭包 enrich 的 excerpt。

#### 19.0.3 指标速查（各表列名含义）

| 列名 | 全称 | 含义 | 成功信号 |
|---|---|---|---|
| **retrieved / ret** | 片段层召回 | 合并 `_retrieve_snippets` 文本中**是否含 gold 词**（检索+闭包是否"摸到"答案） | 高 = 检索层 OK |
| **spotted / spot** | 候选层召回 | `recall()` 输出的候选 dict **是否含 gold 族**（方案B 实体级匹配） | 高 = 抽取层 OK |
| **extr_loss / xloss** | 抽取损失 | retrieved=✓ 但 spotted=✗ 的 case 数（**检索到了但没抽出来**） | 越低越好 |
| **L1tgt** | L1 target 召回 | 正确诊断所在 **L1 族** 是否在候选中 | §19.5/§19.6 |
| **L1mnd** | L1 mandatory 覆盖 | can't-miss L1 族被召回的比例（均值） | 衡量"整族缺失"风险 |
| **轴可分 / AxisSep** | 轴极可分性 | `axis_pair` 中**两个相反轴极是否都被召回** | 双极皆有才能正确切轴 |
| **L2 / L2sub** | L2 子族召回 | 在 L2 query 下正确**子族**是否被召回 | §19.5 深度指标 |
| **Comp / 综合** | 综合分 | (L1tgt + L1mnd + 轴可分 + L2) / 4 | 跨臂排序用 |
| **hComp / hL1*** | 8 题难病多级 | 同 Comp，评测集 `branch_recall_eval_set_hard.json`（idx 1/9/13/17/18/22/23/24） | §19.8 |
| **MECE₁₄ / MECE₈** | MECE 域投影覆盖 | flat 40 名经 `project_entity`→L1 域，统计 `mece_map_coverage` 等（`eval_mece_arm`） | **≠ L1tgt**；§19.8 |
| **R / S / RS / --** | 逐例漏斗 | R=仅检索达；S=仅候选含；RS=双命中；--=双漏 | §19.2 逐例表 |

#### 19.0.4 实验臂代号与完整配置（§19.2：S/D 臂，N=8 rare）

脚本：`eval_diff_retriever_validation.py`　索引：`cpg_index`（统一 TF-IDF）　标签：**hand** 综合征

| 代号 | 检索器 | 闭包 | 闭包去向 | `GuidelineBranchSource` 要点 | 主要验证 §17 缺陷 | 对照目的 |
|---|---|---|---|---|---|---|
| **S0** `unified_noclosure` | `RAGRetriever(cpg_index)` | ❌ 关（`expand=identity`） | — | `top_k=30`，legacy `recall()` | C5 基线 | 基线：无 sibling 扩展 |
| **S1** `unified_closure` | 同上 | ✅ 开（cap +80 sibling） | **灌候选池** | 同上 + `expand_ddx_siblings` | **C4** 灌池 | 测闭包对 spotter 的增益/伤害 |
| **D1** `differentiated_closure` | `DifferentiatedCPGRetriever`（5 桶 TF-IDF） | ✅ 开 | **灌候选池** | 融合 = **等权 RRF**（按名次） | **B7/L9** PMC 稀释 | 测分源检索是否优于 unified |
| **D2** `anchor_union_closure` | `AnchorAugmentedRetriever(RAGRetriever)` | ✅ 开 | **灌候选池** | 基检索 **UNION** 锚点匹配块 | B5/L4 入口选择 | 测结构化入口选择 |

#### 19.0.5 实验臂代号与完整配置（§19.5：多级臂，N=14 common）

脚本：`eval_branch_multilevel.py`　索引：`cpg_index`　抽取：**确定性 spotter only**（无 LLM）

| 代号 | 对应 §19.2 | 闭包 | 闭包去向 | 主要验证 §17 缺陷 | 备注 |
|---|---|---|---|---|---|
| **unified_noclosure** | ≈ S0 | ❌ | — | C5 基线 | §19.5 最佳臂（0.702） |
| **unified_closure** | ≈ S1 | ✅ | **灌候选池** | **C4** mandatory↓ | mandatory 覆盖下降 |
| **anchor_union_closure** | ≈ D2 | ✅ | **灌候选池** | C4 + B5 | 仍受闭包灌池拖累 |
| **differentiated_closure** | ≈ D1 | ✅ | **灌候选池** | **B7/L9** | PMC 稀释，最差（0.307） |

#### 19.0.6 实验臂代号与完整配置（§19.6：A 臂，累积消融）

脚本：`eval_branch_confounder_matrix.py`　环境：**gnn-llm**（sklearn 1.4.1；**§19.8** 本机补跑 LLM 失效见 caveat）　评测：**14 题 ML + 8 题漏斗 + 8 题 ML（hard）+ MECE（14/8）**

| 代号 | 检索器 | 闭包去向 | 在上一臂基础上 **增量** | IMP | 主要验证 §17 缺陷 |
|---|---|---|---|---|---|
| **A0_legacy** | unified TF-IDF | **灌候选池** | 旧 `recall()` 默认路径（= §19.2 S1 逻辑） | — | **C4** + 方差 |
| **A0b_noclosure** | unified TF-IDF | ❌ 关 | 无 sibling | — | C5 对照 |
| **A1_grounding** | unified TF-IDF | **grounding** | `closure_mode='grounding'` | **IMP-63** | **C4 修复** |
| **A1m_mmrtrim** | unified TF-IDF | grounding + **MMR trim** | +`retrieve_k=50, extract_k=15, mmr_lambda=0.7` | 诊断 | C5/L5（**证伪**） |
| **A2_rollup** | unified TF-IDF | grounding | +`rollup_mode='family+orphan'`, `taxonomy=KBAxisMap` | **IMP-64** | C4 族层 + 轴可分 |
| **A3_union** | **DifferentiatedCPGRetriever(fusion='union')** | grounding + rollup | 检索器换为分源 UNION | **IMP-61** | B7/L9（**证伪**） |
| **A4_poles** | 同 A3 | 同 A3 | +`inject_poles=True`, `cant_miss=wikem` | **IMP-60** | L11（源缺口无效） |
| **A4u_poles_unified** | unified TF-IDF | grounding + rollup | +轴极注入（unified 基） | IMP-60 | L11 诊断 |
| **A5_llm** | unified TF-IDF | grounding + rollup + poles | +`extractor='spotter+llm'`, qwen3-32b | **IMP-63/C7** | **C7** + C4 |
| **A5h_llm** | **HybridCPGRetriever** | grounding + rollup + poles | 同 A5 + LLM，检索换 Hybrid | IMP-53+C7 | Hybrid 对 A5 路径增益 |
| **A6_fanout** | unified TF-IDF | grounding | +`query_mode='fanout'`（五路 facet 查询） | **IMP-52** | B1（**证伪**） |
| **A7_nominate** | unified TF-IDF | grounding | +`nominate=True`, `pathognomonic` | **IMP-58** | C1/c1 机制鸿沟 |
| **A8_hardmiss** | unified TF-IDF | grounding + rollup + poles | +`cant_miss_hard=True` | **IMP-56** | L11 硬层 |
| **A9_tableC_all** | unified TF-IDF | grounding + rollup + poles | A8 + fanout + 提名（**含 fanout，有害**） | 表C 联合 | 证伪 fanout 拖累 |
| **A9b_no_fanout** | unified TF-IDF | grounding + rollup + poles | A8 + 提名（**去 fanout**） | 表C 联合 | 确定性联合对照 |
| **A10_hybrid** | **HybridCPGRetriever** | grounding | 检索换 Hybrid（= A1 基） | **IMP-53** | B2/L1/L2 词面鸿沟 |
| **A11_hybrid_nom** | HybridCPGRetriever | grounding + rollup | A10 + 提名 + 硬层 | IMP-53+58 | **确定性最佳 0.723** |
| **A9l_tableC_llm** | unified TF-IDF | grounding + rollup + poles | +提名+硬层+`spotter+llm`（**无 fanout**） | 表C+C7 | **综合最佳 0.812** |
| **A11_llm** | HybridCPGRetriever | grounding + rollup | A11 + `spotter+llm`（**无 poles**） | IMP-53+58+C7 | Hybrid+LLM **0.783** |
| **A12_hybrid_fullstack_llm** | HybridCPGRetriever | grounding + rollup + poles | A9l 配置 + Hybrid 检索 | IMP-53+表C+C7 | L2 **0.857**（与 A11_llm 并列） |

**累积关系（§19.6 主线）**：A0b → A1（+grounding）→ A2（+rollup）→ A5（+LLM）；A3/A4 为**替换检索器**的独立对照，不叠加在 A2 之上。

**表 C / Hybrid 线（§19.7，非严格累积）**：在 **A1_grounding** 基线上**各开一项**（A6/A7/A8）或**联合**（A9/A9b）；检索换 Hybrid 后重跑（A10→A11）；再叠 LLM 得全栈臂（A5h / A9l / A11_llm / A12）。读数时勿把 A12 当作 A2 的下一行累积——它是「A9l 全栈 + Hybrid 检索」的**交叉组合**。

#### 19.0.6b 新增实验臂阅读指南（§19.7：表 C + Hybrid + 全栈 LLM）

> **为何需要本节？** §19.6 落地 IMP-63/64/60 后，§17.9 **表 C** 仍有多项「未参数化」改进（fanout 查询、机制提名、can't-miss 硬层、MedCPT 双塔）可能干扰结论。§19.7 在 **A1_grounding** 基线上**单独隔离**每项，再跑 **Hybrid** 与 **全栈+LLM** 补全实验；脚本仍为 `eval_branch_confounder_matrix.py`，需 `--llm` 才跑含 LLM 的臂。

##### （1）代号怎么读：数字段含义

| 前缀/模式 | 含义 | 示例 |
|---|---|---|
| **A6–A8** | 表 C **单因子**隔离臂（每次只比 A1 多开**一个**旋钮） | A7 = 只开提名 |
| **A9 / A9b** | 表 C **确定性联合**（rollup+poles+硬层+提名；A9 多 fanout，A9b 去掉） | A9b_no_fanout |
| **A10–A11** | **IMP-53**：检索器从 unified TF-IDF 换为 **HybridCPGRetriever** | A11 = A10 + 提名 + rollup + 硬层 |
| **A5h** | **A5 的 Hybrid 版**（rollup+poles+LLM，**无**提名/硬层） | 对比「Hybrid 是否帮 A5 路径」 |
| **A9l** | **unified 全栈 + LLM**（A9b 确定性栈 + `spotter+llm`） | 平面 L1 / 综合最优 |
| **A11_llm / A12** | **Hybrid 全栈 + LLM**；A12 = A9l + Hybrid；A11_llm = A11 + LLM（**无 poles**） | L2 深度 / 语义检索 |

##### （2）「全栈」具体指哪些旋钮全开？

文档里的 **全栈（full stack）** 指在 **A1_grounding**（闭包→grounding，不进 spotter 池）之上，**同时启用**下列生产向改进（**明确不含 fanout**）：

| 旋钮 | 参数 | 作用（一句话） |
|---|---|---|
| 本体归族 | `rollup_mode='family+orphan'`, `taxonomy=KBAxisMap` | IMP-64：40 槽在**族层**竞争，提轴可分 |
| 轴极注入 | `inject_poles=True`, `cant_miss=…` | IMP-60：can't-miss 轴极软注入（依赖 cant_miss 源） |
| can't-miss 硬层 | `cant_miss_hard=True` | IMP-56：注入/提名实体**穿透** max_candidates 裁剪 |
| 机制/标志物提名 | `nominate=True`, `pathognomonic=[…]` | IMP-58：上下文机制措辞→**直提名**疾病实体 |
| LLM 抽取 | `extractor='spotter+llm'`, qwen3-32b | C7：grounding excerpt 上 **grounded** 补抽 |
| ~~五路 fanout~~ | ~~`query_mode='fanout'`~~ | IMP-52：**已证伪，全栈不含** |

**检索器二选一**（这是全栈臂之间最核心的差别）：

| 检索器 | 类 | 编码方式 | 用于哪条全栈臂 |
|---|---|---|---|
| **unified** | `RAGRetriever(cpg_index)` | 仅 TF-IDF 稀疏 | **A9l** |
| **Hybrid** | `HybridCPGRetriever(cpg_index, cpg_medcpt_index)` | TF-IDF **并联** MedCPT dense，RRF 融合 | **A11_llm、A12** |

MedCPT **不是替换** TF-IDF，而是**第二检索塔**；闭包、`expand_ddx_siblings` 仍由 sparse 侧 metadata 驱动。

##### （3）新增臂完整配置对照（复制粘贴级）

环境：`gnn-llm`；LLM：`qwen/qwen3-32b @ T=0`；闭包 cap=80；评测：ML n=14 + 漏斗 n=8 + **hard ML n=8 + MECE**（§19.8）。

> **数据双轨（勿混读）**：下表 **Comp** 来自 **gnn-llm 2026-06-26** 专跑（LLM 有效）。`branch_confounder_matrix.json` 经 **2026-06-27 全矩阵合并**后，JSON 内 A9l 等 LLM 臂可能显示 **0.699**（本机 `openai.OpenAI` 缺失）——**不得以之替换下表 A9l=0.812**。8 题 **hComp / MECE₈** 以 **§19.8** 为准。

| 臂 | 检索器 | closure | rollup | poles | hard | nominate | fanout | extractor | **Comp** | 选型提示 |
|---|---|---|---|---|---|---|---|---:|---|
| A1_grounding | unified | grounding | off | off | off | off | off | spotter | 0.702 | §19.6 确定性基线 |
| A6_fanout | unified | grounding | off | off | off | off | **on** | spotter | 0.693 | **勿开** |
| A7_nominate | unified | grounding | off | off | off | **on** | off | spotter | 0.707 | 机制鸿沟补漏 |
| A8_hardmiss | unified | grounding | on | on | **on** | off | off | spotter | 0.699 | K=40 上≈中性保险 |
| A9b_no_fanout | unified | grounding | on | on | on | on | off | spotter | 0.699 | 确定性联合（无 LLM） |
| A10_hybrid | **Hybrid** | grounding | off | off | off | off | off | spotter | 0.719 | 仅换检索器 |
| A11_hybrid_nom | Hybrid | grounding | on | off | on | on | off | spotter | **0.723** | **确定性最佳** |
| A5h_llm | Hybrid | grounding | on | on | off | off | off | spotter+llm | 0.756 | Hybrid 版 A5 |
| **A9l** | unified | grounding | on | on | on | on | off | spotter+llm | **0.812** | **综合 / L1tgt 首选** |
| A11_llm | Hybrid | grounding | on | off | on | on | off | spotter+llm | 0.783 | Hybrid+LLM，**L2=0.857** |
| A12 | Hybrid | grounding | on | on | on | on | off | spotter+llm | 0.778 | 文档「Hybrid 全栈」；略逊于 A11_llm |

> **A9l 修正说明**：首版 A9l 误开 `query_mode='fanout'`，测得 Comp=**0.766**、轴可分=0.571；去掉 fanout 后 Comp=**0.812**、轴可分=**0.714**。读旧日志时勿与修正版混淆。

##### （4）生产选型速查（读表用）

```text
  目标                     推荐臂          检索器              关键 Comp / L2
  ─────────────────────────────────────────────────────────────────────
  综合分 / L1tgt 最高      A9l            unified TF-IDF      0.812 / L2 0.786
  L2 子族 / 语义近邻       A11_llm        Hybrid (MedCPT)     0.783 / L2 0.857
  纯确定性、无 LLM         A11            Hybrid              0.723 / hComp 0.656 (§19.8)
  仅验证 MedCPT 检索增益   A10 vs A1      Hybrid vs unified   +0.017 Comp
  仅验证机制提名           A7 vs A1       unified             漏斗 xloss 1→0
  勿用                     A6 / A9(含fanout)                  有害
```

**与 §19.6 旧结论的关系**：§19.6 说「带 LLM 最佳 = A5（0.768）」仍成立于 **未叠表 C** 的路径；叠提名+硬层+去 fanout 后 **A9l（0.812）** 为新上限；Hybrid 全栈 **未超过** unified 全栈的综合分，但在 **L2** 上与 A11_llm 并列最高（0.857）。

##### （5）跑数命令备忘

```bash
# 确定性表 C 隔离 + Hybrid（无 LLM）
PYTHONPATH=src python scripts/eval_branch_confounder_matrix.py \
  --arms A1_grounding,A6_fanout,A7_nominate,A8_hardmiss,A9b_no_fanout,A10_hybrid,A11_hybrid_nom

# 全栈 LLM 补跑（需 VPN + qwen）
PYTHONPATH=src python scripts/eval_branch_confounder_matrix.py --llm \
  --arms A5h_llm,A9l_tableC_llm,A11_llm,A12_hybrid_fullstack_llm

# 全矩阵（除 A0_legacy）：8 题四大指标 + MECE（§19.8）
PYTHONPATH=src python scripts/eval_branch_confounder_matrix.py --llm \
  --exclude-arms A0_legacy
```

部分 `--arms` 跑数会**合并**写入 `data/cpg/eval/branch_confounder_matrix.json`（保留已有臂，只更新本次跑的）。**归档**：`data/cpg/eval/archive/2026-06-27_hard_mece/`。

#### 19.0.7 其他高频术语

| 术语 | 含义 |
|---|---|
| **B6 漏斗** | retrieved vs spotted 拆分实验（§17.5.1）；**≠** §17.3 缺陷 B6（ctx-query 噪声） |
| **hand 标签** | 综合征来自 `syndrome_axis_map.json` 手工 map，隔离 RAG/spotting，不混入 RootSelector 误差 |
| **curated-free 标签** | LLM RootSelector  surrogate 抽综合征（§15）；c23 常弱化为 "nausea" |
| **grounding excerpt** | `_retrieve_snippets` 产出的 ≤24 条 prose 摘要（每条 ≤400 字），供 LLM ** grounded 抽取** |
| **spotter** | `_spot()`：最长 5-gram 匹配 SNOMED disorder vocab，**确定性、无 LLM** |
| **recall_llm / C7** | GARMLE-G②：LLM 从 grounding excerpt 中抽 DDx 实体列表，与 spotter 结果合并 |
| **覆盖增广 rollup** | IMP-64：仅 `len(scored)>40` 时对全量 spotted key 做 SNOMED `is_a` 分组（2–70% 覆盖，≤6 超族）；flat top-40 **超族零成员** 时从 40 名外取 **1 名具体病** 替换 **末尾 ≤5 槽**（`n_reserve=min(缺席族数,K//8)`）；**不用族名**替换具体名；≤40 时不生效。**规格**：`BRANCH_GENERATION_PHASE_REPORT.md` **§2.9.1** |
| **UNION（检索融合）** | 各源桶各取 top-N，取**并集**再排序（vs 等权 RRF 按名次融合） |
| **方差源（closure-pool）** | `expand_ddx_siblings` 用 Python `set` 迭代 sibling → 入池顺序受 `PYTHONHASHSEED` 影响 + 40 槽截断 → A0_legacy 跨跑 0.54–0.65 抖动 |
| **nominate / 提名** | IMP-58：`nominate=True` 时对 `{syndrome}{syn}{context}` 做 `pathognomonic_markers.json` + `mechanism_to_disease.json` **子串匹配**（非 LLM）；命中以 **≥0.6×max(spot)** 写入 `recall()` scored；`cant_miss_hard` 强制回 top-40。**消费**：实验 flat 40 名；生产另经 controller T1 marker→按域。**规格**：`BRANCH_GENERATION_PHASE_REPORT.md` **§2.9.2** |
| **cant_miss_hard / 硬层** | IMP-56：`cant_miss_hard=True` 时，被注入或提名的 mandatory 实体在 `max_candidates` 截断后**强制回填**，防静默挤出 |
| **query_mode=fanout** | IMP-52：在 DDx/etiology 查询外追加 mechanism/anatomy/urgency/workup/symptom 五路 facet；§19.7 **证伪**（A6 有害），全栈**默认关闭** |
| **HybridCPGRetriever** | IMP-53：`RAGRetriever`(TF-IDF) **并联** MedCPT FAISS（`cpg_medcpt_index`），查询用 `MedCPT-Query-Encoder`，结果 **RRF 融合**；接口与 unified 兼容，可 drop-in |
| **全栈 / full stack** | 见 **§19.0.6b(2)**：grounding + rollup + poles + hard + nominate + spotter+llm，**不含 fanout**；检索器分 unified（A9l）与 Hybrid（A11_llm/A12） |
| **A9l 修正** | 首版误含 fanout（Comp 0.766）；现行定义已去 fanout（Comp **0.812**）——读数时对照 §19.0.6b(3) 脚注 |

#### 19.0.8 参数 ↔ §17 缺陷 ↔ 改进方案（主速查表）

> **用法**：左列 = `GuidelineBranchSource` / 检索器可配参数；**针对缺陷** = §17.3（A/B/C/D）+ §17.4（L*）；**改进方案** = 具体改什么、怎么配；**§19 验证** = 哪条臂/哪节有实测。**默认/legacy** = 旧路径（A0_legacy），**推荐** = §19.6.3 生产配置。

##### 表 A — 检索与闭包参数

| 参数 | 默认值（legacy） | 针对 §17 缺陷 | 缺陷机制（一句话） | 改进方案（具体做什么） | §19 验证 |
|---|---|---|---|---|---|
| **`top_k`** | `30` | B3, C5 | 单 k 同时服务检索与 spotter；k↑ 检索↑ 但 spot↓ | 保持 spotter 用 `top_k=30`；广检索改用 **`retrieve_k=50`**（与 spotter 解耦，见下行） | §17.5.4：k=30 spot 50% < k=8 75% |
| **`retrieve_k`** | `=top_k` | B3, C5, L3 | 检索广度不足则漏同篇 DDx；但与 extract 共用 k 时 C5 互斥 | IMP-63：单独拉高检索广度（50），**不**增大 spotter 可见块数 | A1m 用 50；spotter 池仍 30 逻辑 |
| **`extract_k`** | `None`（不裁剪） | C5, L5 | 意图：spotter 前 MMR 裁到 15 块，减噪声 | ⚠️ **对确定性 spotter 有害**（mandatory/轴可分需广度）→ **仅用于 LLM grounding 路径**，spotter 池**不设 extract_k** | A1m：0.702→0.376 |
| **`closure_mode`** | `'pool'` | **C4**, L3, L5, L9 | pool：sibling 灌 spotter → 40 槽常见病挤 rare gold | **`'grounding'`**：sibling **只**进 `_retrieve_snippets` 供 LLM；spotter **只吃** top-k 原始块 | A1=0.702；A0_legacy 0.54–0.65 不稳 |
| **`closure_mode='off'`** | — | C4（回避） | 完全不要 sibling → 丢失 rare 散落 gold（§18 c1 需闭包） | 仅作对照（S0/A0b）；**生产不用**——grounding 更优（保留闭包给 LLM） | A0b=S1 grounding 指标 |
| **`expand_ddx_siblings` cap** | +60~80 | B3, L3 | 无闭包则入口块内 DDx 列表切散、单 chunk 不全 | 闭包本身保留（IMP-31）；**去向**由 `closure_mode` 控制，非关闭包 | §18：entry+closure 100% |
| **检索器：unified TF-IDF** | `RAGRetriever(cpg_index)` | B7, L9 | PMC 占 88%，统一 IDF 下 WikEM 入口被淹 | **生产主路径仍用 unified**（§19.6#5：换检索器更差） | A1/A2/A5 最佳 |
| **检索器：DifferentiatedCPG** | `fusion='rrf'` 或 `'union'` | B7, L9, A3 | 分源 IDF 防 PMC 污染；但替换 unified 会稀释 PMC 主干 | §16 WikEM **入口 Recall** 场景按需启用；**主 recall 路径弃用**（RRF 与 UNION 均 0.24–0.42） | D1/A3 harmful |
| **检索器：AnchorAugmented** | UNION 锚点块 | B5, L4 | TF-IDF 排不到入口块；§18 上界靠 anchor 选篇 | 作**少数源入口**补充；§19.6 仍低于 unified+grounding | D2：0.618 |

##### 表 B — 抽取与候选参数

| 参数 | 默认值（legacy） | 针对 §17 缺陷 | 缺陷机制（一句话） | 改进方案（具体做什么） | §19 验证 |
|---|---|---|---|---|---|
| **`max_candidates`** | `40` | **C4** | 40 个**疾病实体**槽；flat 竞争，常见病累加 w 占满 | ① `closure_mode=grounding` 减灌池噪声；② **`rollup_mode`** 族层覆盖增广；③ **`extractor=spotter+llm`** 补漏抽 | §21.3；A5 L1tgt 0.929 |
| **`extractor`** | `'spotter'` | **C7**, C1, C4 | 仅 n-gram `_spot()`：机制名/eponym/表面形漏抽 | **`'spotter+llm'`**：spotter 产 broad 候选 + `recall_llm` 从 grounding excerpt ** grounded 补抽**，合并进同一 dict | **A5 最大杠杆** 0.768 |
| **`extractor='llm'`** | — | C7 | 纯 LLM，无 spotter 广度 | 不推荐单独使用；spotter+llm 并集更稳 | — |
| **`mmr_lambda`** | `None` | L5, C4 | MMR 意图：snippet 去重、降 PMC 重复 | spotter 池：**不设**（A1m 有害）；LLM `_retrieve_snippets` 内部可未来加 MMR | A1m 证伪 |
| **`resolver`** | `DiseaseNameResolver` | C1, C3, B5 | 机制措辞→具体病；宽族→成员（CML 等） | 保持开启；**c1 eponym 鸿沟仍需 IMP-58**（resolver 不够） | c17 经 resolver 命中 |
| **`rollup_mode`** | `'off'` | **C4**, D1, 轴可分 | flat 40 槽挤掉不同 is_a 族；轴极只召回单侧 | **`'family+orphan'`**：is_a **覆盖增广**——保 flat 强 hit，为否则整族缺失的族留 ~12% 槽；orphan 单独成族 | A2：轴可分 0.643 |
| **`taxonomy`** | `None` | D1, §21.5 | SNOMED 分区墙在下游；召回层需族层竞争 | 注入 **`KBAxisMap`**，调用 `_taxonomy_groups()` | A2 rollup |
| **`inject_poles`** | `False` | L11, IMP-60, 轴可分 | can't-miss 低概率轴极被 top-40 挤掉 | `True` + **`cant_miss`** 字典：缺一侧轴极时注入 can't-miss 实体（0.6×max 分） | A4u≡A2（**源未覆盖**） |
| **`cant_miss`** | `{}` | L11, IMP-56/60 | 同上；需 syndrome→实体列表 | 加载 `cant_miss_by_syndrome*.json`；**须扩 lab/endocrine 综合征** | WikEM 症状 id 不匹配本评测集 |

##### 表 C — 索引 / 元数据 / 未参数化项（§17 A 类 & 待办 IMP）

| 对象 | 针对 §17 缺陷 | 改进方案 | 状态 | §19 能否验证 |
|---|---|---|---|---|
| **生产 `rag_index` 含 CPG** | **A1, A2** | IMP-31 重建索引 + 写入 `source_id/chunk_type/entry_type/syndrome_anchor` | 🟡 实验底座已足；**生产索引**待重建 | 否（实验 `cpg_index` 元数据已完整，§19.7.4 核验） |
| **`wiki_links` 合成块** | C6 | IMP-31 闭包内 `_wiki_links_hit` | ✅ 落地；本基准零增益 | S0–D2 均无差 |
| **`snippet_on_topic` 门控** | B4 | IMP-35 `chunk_type/entry_type` | ✅ 非瓶颈 | §17.5.6 pass 100% |
| **IMP-52 五路 query** | B1 | `query_mode="fanout"`：Qmech/Qanat/Qurg/Qwork/Qsymptom 并集 | ✅ 落地；**轻度有害**默认关 | **A6=0.693<A1=0.702**（§19.7.2） |
| **IMP-53 MedCPT hybrid** | B2, L1, L2 | MedCPT dense 塔 + sparse RRF（`HybridCPGRetriever`） | ✅ **落地+验证（正收益）** | **A10=0.719>A1=0.702；轴可分/L2/漏斗全升（§19.7.2）** |
| **IMP-58/59 实体归一+alias** | **C1, B5, L4, c1** | `nominate=True`：机制/形态/族 + eponym + pathognomonic **直提名** | ✅ **落地（机制+标志物通道）**；UMLS linker 增量 | **A7 漏斗 xloss 1→0、综合最佳 0.707** |
| **IMP-56 can't-miss 硬层** | L11 | `cant_miss_hard=True`：穿透 `max_candidates` 裁剪 | ✅ 落地；n=14 中性安全网 | A8≈A4u（K=40 罕咬） |
| **pathognomonic 接入 recall** | L13, D3, c1/c13 | `nominate` 内并入 `pathognomonic_markers` 触发→target_diseases | ✅ 落地（并入 IMP-58 通道） | 见 A7（xloss→0） |

##### 表 D — §17 缺陷 ID → 参数/臂 反向速查（「这个 bug 改哪个旋钮？」）

| 缺陷 ID | 典型症状 / case | 首选改进（参数或臂） | 备选 / 未证实 | §19 实测结论 |
|---|---|---|---|---|
| **A1/A2** | 生产查不到 WikEM/PMC；闭包 8→8 | **IMP-31** 重建生产索引 | — | 实验轨 `cpg_index` 已有效 |
| **A3** | PMC 88% 语料稀释 | useful 子集；**不**靠 IMP-61 替换 unified | 分源索引仅 §16 入口场景 | A3_union 有害 |
| **B1** | 单 query 漏 red-flag/workup 轴 | ~~IMP-52 `query_mode=fanout`~~ | — | **A6 证伪：轻度有害，默认关** |
| **B2/L1/L2** | 语义近邻 miss | **IMP-53 `HybridCPGRetriever`**（sparse+MedCPT RRF，已落地） | — | **A10：轴可分0.643/L2 0.714/漏斗xloss0** |
| **B3/L3** | 同篇 DDx 切散 | `expand_ddx_siblings` + **`closure_mode=grounding`** | `retrieve_k↑` | 闭包 100% 上界 |
| **B4** | 门控误滤 DDx 块 | IMP-35（**已非瓶颈**） | — | pass 100% |
| **B5/L4/c1** | Pancoast↔limb deficit 词面鸿沟 | **IMP-58 `nominate=True`**（机制+pathognomonic 直提名，**已落地**） | IMP-59 UMLS linker 增量 | **A7 漏斗 xloss 1→0** |
| **B6**（§17.3） | ctx-query 引噪声 | **禁用**全文 vignette query | colloquial 短 feature | 曾回退 |
| **B7/L9** | PMC 淹没 top-k ~90% | **unified+grounding**（不弃 PMC 主干） | ~~IMP-61 替换~~ | 差异化有害 |
| **B8/L8** | FAISS nprobe 丢近邻 | nprobe≥4 | — | **非主因** @k=30 |
| **B10** | LLM 综合征标签弱 | hand 标签隔离评测；稳 RootSelector | — | §15 75%→50% |
| **C1** | 机制名不在 vocab | **IMP-58 `nominate=True`**（已落地，A7） | 扩 vocab | **C1 证伪为瓶颈；提名补机制鸿沟** |
| **C2** | 短病名漏 spot | IMP-58 UMLS | 降 min_len | 待评估 |
| **C3** | 宽族名被 `_GENERIC_NAMES` 滤 | mechanism_to_disease 白名单 | resolver | 部分 |
| **C4** | urticaria/MI 占满 40 槽；闭包加重 | **`closure_mode=grounding`** + **`rollup_mode=family+orphan`** + **`extractor=spotter+llm`** | ~~MMR trim spotter~~ | **✅ A1/A2/A5** |
| **C5** | k=30 检索好 spot 差 | **`retrieve_k` 与 spotter 解耦**；spotter **不** extract_k trim | MMR 仅 grounding | A1m 证伪 trim |
| **C6** | WikEM 结构化 DDx 未直读 | `_wiki_links_hit`（已落地） | — | 零增益 N=8 |
| **C7** | 片段有 gold 候选无 | **`extractor='spotter+llm'`** | recall_llm 单独 | **A5 +6.4pp** |
| **C8** | 评测低估实体 recall | 方案B 实体级匹配（已落地） | — | ✅ |
| **D1/D2** | 候选有 gold 但分区失败 / 轴错 | 方案A LLM MECE（§15）；非 recall 参数 | IMP-55 | 下游 |
| **D3/L13** | pathognomonic 未进候选 | **`nominate=True` 并入 pathognomonic**（已落地） | — | A7 xloss→0 |
| **L5** | hard-negative 挤 top-k | grounding 减 spotter 池噪声；**不用** spotter MMR | IMP-61 | A1m 有害 |
| **L11/轴可分** | 只召回单轴极 | **`inject_poles=True`** + **`cant_miss_hard=True`**（IMP-56 已落地）+ 扩 cant_miss 源 | — | A4 无效（源缺口）；A8 硬层 K=40 罕咬 |

##### 表 E — IMP 编号 → 参数组合（复制粘贴级生产草图）

| IMP | 启用的参数组合 | 针对缺陷 | §19 最佳臂 |
|---|---|---|---|
| **IMP-31 闭包** | `expand_ddx_siblings` + `wiki_links`；配合 **`closure_mode='grounding'`** | B3, L3, A2 | 闭包机制保留；去向由 IMP-63 定 |
| **IMP-63** | `closure_mode='grounding'`；可选 `retrieve_k=50`；**`extractor='spotter+llm'`** | **C4, C5, C7** | A1（确定性）/ **A5（+LLM）** |
| **IMP-64** | `taxonomy=KBAxisMap`, `rollup_mode='family+orphan'` | **C4**, 轴可分 | **A2**（轴可分 0.643） |
| **IMP-60** | `inject_poles=True`, `cant_miss={...}` | L11, 轴可分 | A4u（待 cant_miss 扩源） |
| **IMP-61** | `DifferentiatedCPGRetriever(fusion='union'|'rrf')` | B7, L9（§16 子场景） | **主路径弃用** A3=0.235 |
| **IMP-58/59** | **`nominate=True`, `pathognomonic=[...]`**（机制/形态/族 + pathognomonic 直提名）；UMLS linker 待增量 | **B5, C1, c1, L4** | **A7：漏斗 xloss 1→0、综合 0.707 最佳** |
| **IMP-52** | `query_mode="fanout"`（默认 legacy） | B1 | **A6 证伪：轻度有害（−0.9pp），生产不开** |
| **IMP-56** | `cant_miss_hard=True`（配合 inject_poles） | L11 | A8≈A4u（K=40 罕咬；保险层） |
| **IMP-53** | `HybridCPGRetriever(cpg_index, cpg_medcpt_index)`（sparse+MedCPT dense RRF；闭包委托 sparse） | B2, L1, L2 | **A10=0.719（轴可分/L2/漏斗全升）；A11 联合=0.723 确定性最佳** |
| **IMP-31 生产索引** | 重建 `rag_index` + 元数据（实验底座 `cpg_index` 已完整） | **A1, A2** | §19 不受影响；生产基建 P0 |

**推荐生产调用（§19.6.3 展开）**：

```python
GuidelineBranchSource(
    RAGRetriever("data/corpus/cpg_index"),  # 待 IMP-31 换生产索引
    vocab,
    resolver=resolver,
    top_k=30,                    # spotter 可见原始检索块数
    retrieve_k=50,               # 可选：广检索（仅影响 grounding 路径取块）
    closure_mode="grounding",    # IMP-63：闭包不进 spotter 池 → 修 C4 + 方差
    taxonomy=kb_axis_map,        # IMP-64
    rollup_mode="family+orphan", # IMP-64：族层覆盖增广 → 轴可分 +7pp
    extractor="spotter+llm",     # IMP-63/C7 → L1tgt 0.929
    llm_client=llm,
    inject_poles=True,           # IMP-60（需 cant_miss 源覆盖目标综合征）
    cant_miss=cant_miss_map,
)
# 明确不用：extract_k/mmr_lambda 裁 spotter；DifferentiatedCPG 替 unified；closure_mode='pool'
```

##### 表 F — 实验臂 → 打开了哪些参数（与表 D 对照读）

| 臂 | closure_mode | rollup | extractor | 检索器 | 主要验证的 §17 缺陷 |
|---|---|---|---|---|---|
| S0 / A0b | off | off | spotter | unified | 基线；C5 对照 |
| S1 / A0_legacy | **pool** | off | spotter | unified | **C4 灌池** + 方差 |
| A1_grounding | **grounding** | off | spotter | unified | **C4 修复** |
| A1m_mmrtrim | grounding + trim | off | spotter | unified | C5/L5（**证伪** trim） |
| A2_rollup | grounding | **family+orphan** | spotter | unified | C4 族层 + **轴可分** |
| A3_union | grounding | rollup | spotter | **differentiated** | B7/L9（**证伪** 替 unified） |
| A5_llm | grounding | rollup | **spotter+llm** | unified | **C7** + C4 |
| A5h_llm | grounding | rollup | spotter+llm | **hybrid** | IMP-53 + C7 |
| A6_fanout | grounding | off | spotter | unified | B1（**证伪**） |
| A7_nominate | grounding | off | spotter | unified | IMP-58 机制提名 |
| A8_hardmiss | grounding | rollup | spotter | unified | IMP-56 硬层 |
| A10_hybrid | grounding | off | spotter | **hybrid** | IMP-53 B2/L2 |
| A11_hybrid_nom | grounding | rollup | spotter | hybrid | 确定性最佳 |
| A9l | grounding | rollup | spotter+llm | unified | **综合最佳** |
| A11_llm | grounding | rollup | spotter+llm | hybrid | L2 最佳 |
| A12 | grounding | rollup | spotter+llm | hybrid | Hybrid 全栈 |

---

### 19.1 落地内容

| 部件 | 机制 | 对应需求 |
|---|---|---|
| **闭包升级（IMP-31）** | 命中块 → 同 `source_id` sibling 块（倒排查表）+ 每个含 `wiki_links` 的块合成"Differential includes: …"块喂给 spotter | 入口块→篇内散落鉴别信息；WikEM 显式 DDx 列表直用（**注：§17.5.6 C6 实测本基准零增益，机制保留待更大样本/WikEM 入口为主的场景验证**） |
| **DifferentiatedCPGRetriever（IMP-61）** | wikem/merck/nice/pmc/society 各自 TF-IDF（隔离 IDF）→ 源级 query → RRF（按名次）→ 入口 boost | §16 防 PMC 淹没、提升少数源入口召回 |
| **AnchorAugmentedRetriever（新方法）** | 从 query 解析 syndrome+`clinical features:` 上下文 → 与 `syndrome_anchor`/`section_path` token 重叠选入口块 → **并入**基检索结果 → 闭包 | §18 上界靠"锚点选入口文章"达成，非 TF-IDF 排序；UNION 保证召回 ≥ base |

### 19.2 验证结果（hand 综合征标签，B6 漏斗，N=8）

> **臂代号配置**：见 **§19.0.4**（S0/S1/D1/D2 完整对照表）。**指标列含义**：见 **§19.0.3**。

| 臂 | retrieved（检索+闭包达 gold） | spotted（候选含 gold） | extr_loss | neither |
|---|---:|---:|---:|---:|
| S0 unified，**无闭包** | 0.875 | 0.75 | 1 | 1 |
| S1 unified，**有闭包** | 0.875 | 0.75 | 1 | 1 |
| **D1 差异化，有闭包** | **0.75** | **0.625** | 1 | 2 |
| **D2 锚点UNION，有闭包（新方法）** | **0.875** | 0.75 | 1 | 1 |

逐例 retrieved/spotted（R=检索达、S=候选含）：

| idx | gold | S0 | S1 | D1 | D2 |
|---:|---|:--:|:--:|:--:|:--:|
| 1 | pancoast | -- | -- | -- | -- |
| 9 | leukemoid | RS | RS | RS | RS |
| 13 | glucagonoma | R- | R- | -- | R- |
| 17 | CML | RS | RS | RS | RS |
| 18 | peliosis | RS | RS | R- | RS |
| 22 | PHPT | RS | RS | RS | RS |
| 23 | adhesions | RS | RS | RS | RS |
| 24 | foreign body | RS | RS | RS | RS |

### 19.3 核心发现（带证据，含对前述规划的更正）

1. **闭包（IMP-31）正确但"入口检索受限"——本基准零增益。** S0≡S1：闭包只能扩展**已被检索到的文章**；唯一漏检 c1 的 gold 文章根本未进 top-k，闭包无从触及。⇒ **更正 §18 结论③的隐含期望**：闭包是必需件，但**单靠闭包不足以兑现 §18 的 100% 上界**，因为上界依赖"按锚点选入口文章"而非 TF-IDF query 排序。
2. **纯差异化检索（IMP-61，D1）反而有害（0.875→0.75）。** 等权 RRF 稀释了 §18 证明承载全部 8 例 gold 的 **PMC 主干**，使 c13/c18 由 R 跌为漏检。⇒ **更正 §16/§17 的优先级假设**：§16 的增益是在 **WikEM/Merck 入口召回**这一指标上（897 query 基准），**不可外推**到"gold 多在 PMC prose"的本基准；IMP-61 须改为 **UNION 形态**（保 PMC 主干 + 补少数源入口），而非替换式等权 RRF。
3. **新方法（AnchorAugmented，D2）安全有效但不解 c1。** UNION 设计使 retrieved 恢复到 0.875（修复 D1 的回退），无回归；但 c1 仍漏——因为 c1 的呈现（"右臂/手无力"）**无任何表层词**能匹配 Pancoast/superior-sulcus 锚点。§18 之所以达 c1，**纯因手工 curated 锚词**（含 pancoast/Horner），生产 curated-free 下不可得。
4. **c1 是机制/eponym 鸿沟，非检索方法问题。** 任何检索臂都无法召回（4/4 臂 `--`）。需要 **IMP-58 实体归一 + eponym/pathognomonic 直提名**（臂+手无力+Horner→臂丛→肺尖肿瘤）这一**非检索**通道。
5. **c13 是 spotting 抽取损失。** 全检索臂 `R-`（片段含 glucagonoma 但 n-gram spotter 未抽出）⇒ **IMP-63（P0）** spotting 重构。

### 19.4 结论：curated-free 召回天花板与剩余杠杆

- **检索可达上界（curated-free）= 7/8**（仅 c1 不可被任何检索器召回）；**spotting 后 = 6/8**（c13 抽取损失）。
- **两个剩余缺口均非检索问题**：
  - **c1 → IMP-58 + eponym/机制直提名（P0）**：检索/闭包/差异化/锚点 UNION 四法皆无效，唯一出路是机制桥接。
  - **c13 → IMP-63 spotting 重构（P0）**：检索已达，损失在 n-gram 抽取层。
- **IMP-61 修订**：采纳 **D2（锚点 UNION）形态**为生产路径（无回归、含结构化入口选择）；弃用 D1 等权替换式（PMC 稀释有害）。差异化分源子索引仍保留供少数源入口场景（§16 WikEM 基准）按需启用。

> ⚠️ **§19.6 再更正（最终）**：本节"采纳 D2 锚点 UNION 为生产路径"的结论基于 9 题 L1 漏斗。在 14 题多级度量（§19.5/§19.6）下，**anchor-union（0.571–0.618）与 differentiated-UNION（0.235）均低于 unified+grounding（0.702）**。**最终生产路径 = unified 检索 + IMP-63 闭包→grounding + IMP-64 本体归族 + C7 LLM 抽取**；所有差异化/UNION 形态**退出主 recall 路径**，仅留 §16 WikEM-入口子场景按需启用。
- **IMP-31 闭包**：已生产化（倒排 + wiki_links 注入），保留为所有检索臂的后处理必需件；其价值在"入口文章被选中后"兑现，故须与"锚点入口选择（D2）"或"机制直提名（c1）"配合才形成完整链路。

### 19.5 多级分支评测重做：增区分度 + L2 + 轴可分性（2026-06-26）

> **臂代号配置**：见 **§19.0.5**（与 §19.2 S/D 臂的对应关系）。**闭包模式**：本节全部臂均为 **灌候选池**（§19.0.2），故 unified-closure 会触发 C4 拥挤。

> **动机**（用户）：9 题**一级分支**样本量过低、宽匹配饱和——§19.2 中 S0/S1/D2 **完全一致**（0.875/0.75），无法区分检索器优劣。**改造实验**：纳入 **二级（L2）分支**与**轴极可分性**，并新增 **14 个人工综合征样本**。
>
> **评测集**：`data/cpg/eval/branch_recall_eval_set.json`（14 综合征，教科书级 DDx 树：PTH 轴/容量轴/Light 标准/铁蛋白/FENa/RAIU/ACTH 轴/肾素-醛固酮/胆红素结合）。每例标注：`l1_mandatory`（can't-miss L1 族）、`l1_target`（正确诊断所属族）、`l2_gold`（target 下正确子族）、`axis_pair`（一对**相反轴极**，须双双召回才能正确切轴）。
>
> **脚本**：`scripts/eval_branch_multilevel.py`　**报告**：`data/cpg/eval/branch_multilevel.json`
>
> **指标**：L1 target 召回 / L1 mandatory 覆盖 / **轴可分性**（双极皆召回）/ L2 子族召回 / 综合分。

#### 19.5.1 结果（n=14，cpg_index，确定性 spotter）

| 臂 | L1 target | L1 mandatory | **轴可分性** | L2 子族 | **综合分** |
|---|---:|---:|---:|---:|---:|
| **unified 无闭包** | 0.857 | 0.738 | 0.571 | 0.643 | **0.702** |
| unified 有闭包 | 0.786 | 0.613 | 0.500 | 0.500 | 0.600 |
| anchor-union 有闭包 | 0.857 | 0.613 | 0.500 | 0.500 | 0.618 |
| **differentiated 有闭包** | 0.286 | 0.440 | 0.214 | 0.286 | **0.307** |

**区分度**：综合分跨臂极差 **0.395**（DISCRIMINATING）——重做达成目标，9 题的"零区分"被打破。臂序：**unified-noclosure 0.702 > anchor-union 0.618 > unified-closure 0.600 ≫ differentiated 0.307**。

> ⚠️ **环境更正（§19.6 发现）**：本表的 closure/differentiated 数值系 **base env（sklearn 0.23.2）反序列化告警下**所得。改用 **`gnn-llm`（sklearn 1.4.1.post1，匹配索引构建版本）** 后基线为 unified-closure **0.634**、anchor **0.571**、differentiated **0.424**（见 `baseline_A0_multilevel.json`）。**unified-noclosure 0.702 两环境一致**（cpg_index 路径稳定）；差异仅在含闭包/差异化臂。结论方向不变，但**重评一律以 `gnn-llm` 为准**。

#### 19.5.2 关键新发现（9 题不可见）

1. **篇内闭包在常见综合征上有害（0.702→0.600）。** 逐例（`n_cand1=40` 两臂均饱和）：闭包使 **7/14** case 的 L1 mandatory 覆盖**下降、0 例上升**（hypercalcemia 0.75→0.25、pleural 1.0→0.5、hyperthyroidism 1.0→0.5、microcytic 1.0→0.75、lower-GI 0.5→0.25）。机制：本节所有臂均用 **灌候选池** 模式（§19.0.2）—— sibling 块与 top-k 合并后全部 `_spot()`，常见病在多块重复累加分 → 挤掉 can't-miss 族（**C4 拥挤实锤**）。
   - ⇒ **正解 = IMP-63**：改为 **grounding 模式**——闭包 sibling 只进 `_retrieve_snippets` 供 LLM，**不进** spotter 的 40 槽候选池（§19.6 证实有效）。
2. **differentiated 等权 RRF 严重有害（0.307）**，在 n=14 上**复现并放大** §19.3② 结论（PMC 主干稀释）——**确定弃用**等权替换式。
3. **anchor-union 修复差异化回退**（0.307→0.618）但仍受闭包拥挤拖累，低于 unified-noclosure。
4. **轴可分性是独立短板**：最佳臂仅 **0.571**——过半综合征只召回**单一轴极**（如只召回 hypovolemic 漏 hypervolemic、只召回 transudate 漏 exudate），下游无法正确切轴 → **轴污染风险**。⇒ 需 **IMP-60 sub-axis 提取 + 强制轴极注入**（cant_miss 双极）。

#### 19.5.3 对 §19.2 结论的更正与修订建议

- **更正**："闭包零增益、安全无回归"（§19.3①③，基于 9 题 L1）在更敏感的 14 题多级度量下**不成立**：闭包**实际有害于常见病 mandatory 覆盖**（候选池拥挤）。9 题因 rare-gold + 宽匹配而掩盖了该效应。
- **修订生产配置**：spotting 默认路径应为 **unified 检索（不灌闭包到候选池）**；闭包与差异化仅在**独立通道**服务"rare 散落 gold（grounding→LLM 抽取）"与"少数源入口（anchor-union）"，由 IMP-63 编排 cap-aware 融合。
- **IMP-63 升级为最高优先**：不仅修 spotting 抽取损失（§17），更要**隔离闭包噪声**对候选池的污染（本节）。

> ✅ **已落地+证实（§19.6）**：IMP-63 `closure_mode='grounding'` 经实验证实把闭包移出候选池后**完全复现** unified-noclosure 的 0.702，且**保留闭包供 LLM 抽取**（优于此处"默认关闭闭包"的临时建议）。本节 #1 的"闭包有害"已精确化为"闭包**灌候选池**有害（C4）"，且 closure-pool 旧路径还被证实为 **方差源**（set 迭代序 + 40 槽截断）。详见 **§19.6**。

#### 19.5.4 局限

- token 子集匹配（非语义）、确定性 spotter（未走 recall_llm）、cpg_index TF-IDF；人工样本为教科书 DDx 树（作者标注，轴极取公认判据）。
- n=14 仍非大样本，但**区分度已足以排序检索/抽取策略**；rare-disease 9 题（§17/§19.1）与常见病 14 题（本节）**互补**：前者暴露"入口检索/机制鸿沟"，后者暴露"候选池拥挤/轴可分性"。两套并用为后续 IMP-63 落地的回归基准。

---

### 19.6 混杂因素受控重评：落地 IMP-63/64/61/60 后 A/B 矩阵（2026-06-26）

> **一句话结论**：§19/§19.5 跑在未修复旧路径上，结论被混杂污染。落地修复后重评得：**最佳 = A5（spotter+LLM，综合 0.768 / L1tgt 0.929）；确定性最佳 = A2（本体归族，轴可分 0.643）**。「闭包有害」精确化为「闭包**灌候选池**有害（C4）」，改为 **grounding 模式**（§19.0.2）即复现 0.702 且消除方差；**LLM 抽取（C7）是最大杠杆**；**UNION/RRF 与 MMR-trim 弃用**。
>
> **臂代号配置**：见 **§19.0.6**（A0–A5 累积消融表）。**闭包 grounding vs 灌池**：见 **§19.0.2** 示意图。

> **动机**（用户）：§17 大量缺陷未落地修复，且 §19.2/§19.5 实验本身跑在 **未修复的 `recall()` 旧路径**上（C4 40槽拥挤、C5 单一 k、L5/L9 PMC 淹没、C7 仅确定性 spotter），故"闭包有害 / 臂序"等结论**被混杂污染**，须先落地修复再重评。
>
> **落地**（均参数化、保留旧路径 → A0 可复现）：
> - **IMP-63**：`GuidelineBranchSource` 新增 `retrieve_k/extract_k/mmr_lambda/closure_mode/extractor`。`closure_mode='grounding'` 把闭包**移出 spotter 候选池**（只喂 grounding/LLM 通道）；`extractor='spotter+llm'` 合并 `recall_llm`。
> - **IMP-64**：`closure_mode` + `rollup_mode='family+orphan'`，经 `KBAxisMap._taxonomy_groups()` 把 hit 实体**反向归 is_a 族**，以**覆盖增广**（保强 flat hit + 为否则整族缺失的族保留少量槽位）在**族层**竞争 40 槽（§21.5）。
> - **IMP-61 UNION**：`DifferentiatedCPGRetriever(fusion='union')`（各桶 top-N 取并集，弃等权 RRF）。
> - **IMP-60**：`inject_poles=True` + `cant_miss` 注入缺失轴极的 can't-miss 实体。
>
> **脚本**：`scripts/eval_branch_confounder_matrix.py`　**报告**：`branch_confounder_matrix{_det,_a5}.json`
> **环境（关键）**：必须用 **`gnn-llm`**（sklearn 1.4.1.post1，匹配索引构建版本）；base env（sklearn 0.23.2）**反序列化告警会污染 cpg_diff_index 结果**（A0 基线在两环境差 ~6pp）。

#### 19.6.1 矩阵结果（ML n=14 多级 + CPG 漏斗 n=8；累积消融）

> 各臂**完整配置**见 **§19.0.6**；下表「配置」列仅摘要增量。

| 臂 | 配置（相对上一行的增量） | L1tgt | L1mnd | **轴可分** | L2 | **综合** | ret | spot | xloss |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **A0_legacy** | 旧 recall + 闭包灌**候选池**（=§19 路径） | 0.57–0.79 | 0.58–0.69 | 0.43–0.50 | 0.571 | **0.54–0.65** | 0.875 | 0.63–0.75 | 1–2 |
| **A0b_noclosure** | 闭包全关（=§19.5"最佳"） | 0.857 | 0.738 | 0.571 | 0.643 | **0.702** | 0.875 | 0.75 | 1 |
| **A1_grounding** | **IMP-63**：闭包→grounding（移出候选池） | 0.857 | 0.738 | 0.571 | 0.643 | **0.702** | 0.875 | 0.75 | 1 |
| A1m_mmrtrim | +高 k 检索 + MMR/extract_k=15 trim（**诊断**） | 0.357 | 0.363 | 0.214 | 0.571 | **0.376** | 0.875 | 0.50 | 3 |
| **A2_rollup** | **IMP-64**：本体反向归族（覆盖增广） | 0.786 | 0.744 | **0.643** | 0.643 | **0.704** | 0.875 | 0.75 | 1 |
| A3_union | **IMP-61 UNION** 检索器替换 | 0.143 | 0.298 | 0.071 | 0.429 | **0.235** | 0.75 | 0.50 | 2 |
| A4_poles | +IMP-60 轴极注入（union 基） | 0.143 | 0.298 | 0.071 | 0.429 | **0.235** | 0.75 | 0.50 | 2 |
| A4u_poles_unified | IMP-60 轴极注入（unified 基） | 0.786 | 0.744 | 0.643 | 0.643 | **0.704** | 0.875 | 0.75 | 1 |
| **A5_llm** | **IMP-63 C7**：spotter+`recall_llm`（qwen3-32b） | **0.929** | **0.786** | 0.643 | **0.714** | **0.768** | 0.875 | 0.75 | 1 |

#### 19.6.2 逐改进结论（混杂受控后，重derive §19.5 结论）

1. **「闭包有害」被更正为「闭包**灌候选池**有害」（C4 实锤）。** `A1_grounding`（闭包→grounding）**完全复现** `A0b_noclosure` 的 0.702，而 `A0_legacy`（闭包灌池）只有 0.54–0.65。⇒ 闭包**本身无害**；§19.5.2#1 的处方（IMP-63 把闭包移出候选池）**经实验证实有效**，且 grounding 模式**保留闭包供 LLM 抽取**（A5 受益）——优于 §19.5 临时建议的"默认关闭闭包"。
2. **旧 closure-pool 路径还**不确定**（方差源）。** `A0_legacy` 跨进程在 0.54↔0.65 抖动，根因：`expand_ddx_siblings` 的 `source_id` 用 **set 迭代序**（受 PYTHONHASHSEED 影响）+ 40 槽截断 → sibling 入池顺序不定。grounding 模式（无闭包入池）**稳定**。⇒ 这是用户长期关切的 BranchCreator 方差的一个**确定根因**，IMP-63 grounding 模式一并消除。
3. **本体反向归族（IMP-64）提升轴可分性 0.571→0.643（§19.5 的独立短板），综合分持平（0.704）。** 价值在**结构/轴**（更贴合诊断树 L1=MECE 族）而非提升 flat 召回；覆盖增广实现**严格非回归**（早期"族分纯重排"版本曾把常见族灌高、挤掉 rare gold，已废弃）。注意 is_a 有时**跨临床轴归并**（primary vs secondary 甲旁亢为 is_a 兄弟却是相反 L1 极），故归族**不能整体替换** flat，仅作覆盖增广。
4. **MMR/extract_k=15 trim 在确定性 spotter 上有害（0.702→0.376，漏斗 0.75→0.50）。** ⇒ **更正 §17.5.4 的外推**：该节"k 小 spotting 好"是**单 gold 噪声拥挤**场景；多族**广度**指标（mandatory/轴可分）需要**多 snippet**，激进裁剪会饿死广度。trim 仅宜用于**喂 LLM 的 grounding**（`_retrieve_snippets` 已 cap 24），**不应**裁剪确定性 spotter 池。
5. **IMP-61 UNION 仍有害（0.235）。** 在 n=14 上**再次复现** §19.3②/§19.5.2#2：差异化检索（无论等权 RRF 还是 UNION）都稀释承载 gold 的 PMC 主干，retrieved 跌 0.875→0.75。⇒ **生产仍用 unified**；差异化仅留作 §16 WikEM-入口场景按需启用，**不接入主 recall 路径**。
6. **LLM grounded 抽取（C7）是最大单一杠杆（0.704→0.768，L1tgt 0.857→0.929）。** `recall_llm` 合并把确定性 spotter 漏抽的 gold 族大量找回 ⇒ **确认 §19 问题(d)**：§19.2/§19.5 的低分**相当程度源于"仅用确定性 spotter"这一 C7 混杂**，而非检索/数据不足。
7. **IMP-60 轴极注入在本评测集上**无效**（A4u≡A2）。** 非代码问题，而是 **`cant_miss_by_syndrome_wikem.json` 用 WikEM 症状类目 id（abdominal-pain 等），与本评测集的化验/内分泌综合征（hypercalcemia/cushing）token 不重叠** → 查不到注入项。⇒ IMP-60 已落地参数化，但**需扩 can't-miss 源覆盖**（lab/endocrine 综合征）才可实测，列为后续数据缺口。

#### 19.6.3 推荐生产配置（基于矩阵）

```
# 平面 L1 / 综合最优（A9l = 0.812）：unified TF-IDF + 全栈 + LLM
GuidelineBranchSource(
    RAGRetriever("data/corpus/cpg_index"),
    vocab, resolver=resolver,
    closure_mode="grounding", taxonomy=KBAxisMap, rollup_mode="family+orphan",
    extractor="spotter+llm", llm_client=llm,
    nominate=True, pathognomonic=markers,
    inject_poles=True, cant_miss=cant_miss_map, cant_miss_hard=True)
# L2 深度最优（A12 = L2 0.857）：将检索器换为 HybridCPGRetriever(cpg_index, cpg_medcpt_index)
# 勿开 query_mode="fanout"；勿用 differentiated UNION/RRF；勿 MMR-trim spotter 池
```

- **确定性最佳 = A11（0.723）**；**带 LLM 综合最佳 = A9l（0.812，unified 全栈）**；**L2 最佳 = A12（0.857，Hybrid 全栈）**。
- **§19.5/§19.6 臂序更正（含 §19.7 补跑）**：`A9l(0.812) > A12(0.778) > A5h(0.756) > A11(0.723) ≈ A1(0.702) ≫ fanout/UNION/MMR-trim`。
- 两套评测（rare 9 题 + 常见 14 题）+ 漏斗 n=8 现为 IMP-63/64 回归基准；矩阵脚本 `eval_branch_confounder_matrix.py` 常驻。**2026-06-27** 起另输出 **8 题四大指标 + MECE**（§19.8）。

### 19.7 表 C 待办项落地 + 单独/联合验证（IMP-52 / IMP-56 / IMP-58 / IMP-53；2026-06-26）

> **阅读入口**：新增臂代号、全栈定义、Hybrid vs unified、生产选型 → **§19.0.6b**（本节为实验记录与结论展开）。

> **动机**：§17.9 表 C 列出的「索引/元数据/未参数化项」尚未落地，**可能对 §19 A 臂结论形成干扰**。本节把可即时落地者**参数化进 `GuidelineBranchSource`**（保留旧路径），在 A1_grounding 基线上**单独隔离**每项（A6/A7/A8），并**联合**（A9）评测其与已落地 IMP-63/64/60 的交互；不可即时验证者（生产索引重建、MedCPT 编码）核验底座充分性后**记依据推迟/异步**。

#### 19.7.1 落地项与参数（新增旋钮，默认保持 legacy）

| 表 C 项 | IMP | 新参数 | 语义 | 知识源（无金标准泄漏） |
|---|---|---|---|---|
| 五路 query | **IMP-52** | `query_mode="fanout"` | 在 DDx/etiology 查询外追加 Qmech/Qanat/Qurg/Qwork/Qsymptom 五个正交 facet 查询 | 仅查询模板，无外部表 |
| 实体归一+eponym+pathognomonic 接入 | **IMP-58**(+L13/D3) | `nominate=True`, `pathognomonic=[...]` | 扫描临床上下文中的**机制/形态措辞**(`mechanism_to_disease`)、**宽族关键词**与 **pathognomonic 触发词** → **直接提名**蕴含的疾病实体进候选池 | `mechanism_to_disease.json`（拟自动化）+ `pathognomonic_markers.json`（WHO/教材源） |
| can't-miss 硬层 | **IMP-56** | `cant_miss_hard=True` | 保证注入的 can't-miss / 提名实体**穿透 `max_candidates` 裁剪**（vs IMP-60 软地板可被挤出） | 同 IMP-60（cant_miss 字典） |

新增 `DiseaseNameResolver.nominate_from_text()`：自由文本→机制/族蕴含实体的**反向**提名（与 `expand_to_entities` 单标签互补）。烟测：`apical lung tumor, horner` → `pancoast tumor`；`hypercortisolism` → `cushing syndrome`；`catecholamine excess` → `pheochromocytoma`；`chronic myeloproliferative` → CML/PV/ET/PMF。

#### 19.7.2 隔离 + 联合矩阵结果（ML n=14 + 漏斗 n=8；A1_grounding 基线）

> **8 题 hComp / MECE₈** 见 **§19.8**（2026-06-27 全矩阵补跑）。下表 **Comp / 漏斗** 为 **gnn-llm 2026-06-26** LLM 有效跑数。

| 臂 | 增量配置 | L1tgt | L1mnd | 轴可分 | L2 | **综合** | ret | spot | xloss |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **A1_grounding** | 基线（IMP-63 grounding） | 0.857 | 0.738 | 0.571 | 0.643 | **0.702** | 0.875 | 0.75 | 1 |
| A6_fanout | +IMP-52 五路 query | 0.857 | 0.702 | 0.571 | 0.643 | **0.693** | 0.875 | 0.75 | 1 |
| **A7_nominate** | +IMP-58+pathognomonic 提名 | 0.857 | **0.756** | 0.571 | 0.643 | **0.707** | 0.875 | **1.0** | **0** |
| A8_hardmiss | +IMP-56 硬层（A4u 基：rollup+poles） | 0.786 | 0.726 | **0.643** | 0.643 | **0.699** | 0.875 | 0.75 | 1 |
| A9_tableC_all | A4u+硬层+**fanout**+提名（全叠） | 0.786 | 0.702 | 0.571 | 0.643 | **0.676** | 0.875 | 1.0 | 0 |
| **A9b_no_fanout** | A4u+硬层+提名（**去 fanout**） | 0.786 | 0.726 | **0.643** | 0.643 | **0.699** | 0.875 | 1.0 | 0 |
| **A10_hybrid** | **IMP-53** sparse+MedCPT dense RRF（A1 基） | 0.786 | 0.732 | **0.643** | **0.714** | **0.719** | 0.875 | **0.875** | **0** |
| **A11_hybrid_nom** | IMP-53 + 提名 + rollup + 硬层（**确定性最佳**） | 0.786 | 0.75 | **0.643** | **0.714** | **0.723** | 0.875 | **1.0** | **0** |
| **A5h_llm** | Hybrid + A5（rollup+poles+LLM，无提名） | 0.857 | 0.738 | **0.643** | **0.786** | **0.756** | 0.875 | 0.875 | **0** |
| **A9l_tableC_llm** | unified 全栈+LLM（**去 fanout 修正版**） | **0.929** | **0.821** | **0.714** | **0.786** | **0.812** | 0.875 | **1.0** | **0** |
| **A12_hybrid_fullstack_llm** | **文档推荐真·全栈**：Hybrid+提名+硬层+poles+LLM | 0.857 | 0.756 | 0.643 | **0.857** | **0.778** | 0.875 | **1.0** | **0** |
| **A11_llm** | Hybrid + A11 + LLM（无 poles） | 0.857 | **0.774** | 0.643 | **0.857** | **0.783** | 0.875 | **1.0** | **0** |
| ~~A9l（旧，含 fanout）~~ | 同上但误开 `query_mode=fanout` | 0.929 | 0.78 | 0.571 | 0.786 | 0.766 | 0.875 | 1.0 | 0 |

#### 19.7.3 逐项结论

1. **IMP-58 提名（A7）是表 C 唯一明确正收益项。** 漏斗 **xloss 1→0、spotted 0.75→1.0**（机制措辞蕴含的 gold 实体本不在 DDx 片段里，靠检索无法找回——这正是 §17 c1 Pancoast / c13 的「机制鸿沟」），L1mnd 0.738→0.756，综合 0.702→**0.707**（全臂最佳），且 L1tgt/轴可分**无回归**。⇒ **推荐纳入生产**。这也**更正了表 C/表 D 对 C1/c1 的旧判**：c1 不必等 scispaCy UMLS linker，**机制表+pathognomonic 直提名已能补**（UMLS linker 退为增量）。
2. **IMP-52 五路 query（A6）轻度有害。** L1mnd 0.738→0.702、综合 −0.9pp，无召回增益。机制同 MMR/UNION：本 TF-IDF 底座 + on-topic 门控已捕获 DDx 主簇，正交 facet 反而引入跨主题噪声块稀释 mandatory。**A9（含 fanout）0.676 < A9b（去 fanout）0.699 复证**。⇒ 参数化保留但**默认关闭，生产不推荐**。
3. **IMP-56 硬层（A8）在 n=14 上≈中性但是廉价安全网。** `max_candidates=40` 在 14 题候选规模下**很少咬到**，故硬层无可见增减；轴可分 0.643 的增益来自 **poles（A4u）本身**而非硬层。价值在**生产更大候选池**时防止 mandatory 族被静默挤出。⇒ 作为**零成本保险**保留。
4. **IMP-53 MedCPT hybrid（A10）是表 C 第二个明确正收益项，且修对了它瞄准的缺陷。** sparse+dense RRF 把**轴可分 0.571→0.643、L2 子族 0.643→0.714、漏斗 spotted 0.75→0.875（xloss 1→0）**，综合 0.702→**0.719**。dense 塔召回的正是 sparse 因**词面鸿沟（B2/L1/L2）漏掉的语义近邻 gold chunk**——与设计意图吻合。代价是 L1tgt 0.857→0.786（RRF 重排把个别表面词命中的 L1 target 降位），但广度/深度全面提升，**净综合为正**。⇒ **推荐纳入生产主检索**（与 §19.6#5 弃用的 differentiated UNION/RRF 不同：hybrid **不替换** sparse，而是**并联**dense 补漏，故不稀释 PMC 主干）。
5. **联合最优（2026-06-26 补跑 A5h/A9l/A12 后修订）。**
   - **综合分最高 = A9l（unified TF-IDF 全栈+LLM，已去 fanout）= 0.812**（旧版误开 fanout 仅 0.766；去 fanout 后轴可分 0.571→**0.714**、L1mnd 0.78→**0.821**，+4.6pp 综合）。⇒ **fanout 对 LLM 全栈同样有害**，A9l 定义已修正为默认 `query_mode=legacy`。
   - **L2 子族最高 = A11_llm / A12 = 0.857**（并列）。Hybrid+LLM 路径上 **A11_llm（0.783）略优于 A12（0.778）**——poles 注入在 Hybrid+LLM 组合上**无额外增益**（与 §19.6 IMP-60 cant_miss 源缺口一致）。
   - **Hybrid 全栈若必须用**：优先 **A11_llm**（Hybrid+提名+rollup+hardmiss+LLM，**不加 poles**），而非 A12。
   - **A5h_llm**（Hybrid+A5，无提名）= 0.756，略高于旧 A5_llm unified（0.750），轴可分/L2/漏斗均优于 unified A5。
   - 确定性栈不变：**A11 = 0.723**。
   - **生产分场景推荐**：① 重 L1tgt/L1mnd/综合 → **A9l 配置**（unified + grounding + rollup + poles + nominate + hardmiss + spotter+llm，**不开 fanout、暂不用 Hybrid**）；② 重 L2 深度 → **A12 配置**（+ HybridCPGRetriever）；③ 纯确定性 → **A11**（+ Hybrid）。
6. **去 fanout 的联合（A9b 0.699）仍优于含 fanout 的 A9（0.676）**，复证 IMP-52 在任何组合下均为负贡献；A9l 旧版含 fanout 的 0.766 亦低于修正版 0.812。

#### 19.7.4 不可即时验证项的底座核验与处置

- **IMP-31 生产 `rag_index` 含 CPG（A1/A2）**：核验确认 **§19 实验底座 `cpg_index` 元数据完整**（`source_id/article_id/source/entry_type/chunk_type/section_path/clinical_area` 齐全，203830 chunk），故 **IMP-31 缺陷不干扰任何 §19 A 臂**——表 C「§19 能否验证=否」属实。生产 `rag_index`（493646 向量）仍仅 statpearls+textbooks、无 CPG/无元数据字段，属**端到端生产管道缺口**（与本评测正交），列为独立 P0 基建（重建 FAISS IVFPQ 编码 ~70 万 chunk）。
- **IMP-53 MedCPT 双塔（B2/L1/L2）——✅ 已完整落地并验证**：`scripts/build_medcpt_cpg_index.py` 用 `ncbi/MedCPT-Article-Encoder` 对 cpg 语料（与 sparse 索引**行对齐**）做 dense 编码（CLS 768d 点积，分片断点续跑），GPU(cuda:2) ~76 rows/s，45min 完成 203830 向量 → `data/corpus/cpg_medcpt_index`（`embeddings.npy` 626MB + FAISS `IndexFlatIP`）。`HybridCPGRetriever`（`hybrid_cpg_retriever.py`）封装 sparse `RAGRetriever` + MedCPT dense FAISS（`ncbi/MedCPT-Query-Encoder` 编码 query），**RRF 融合**，闭包委托 sparse，接口与 `RAGRetriever` 兼容（drop-in）。矩阵实测见 §19.7.2/19.7.3#4：**A10 轴可分+L2+漏斗全面提升，综合 0.719；A11 联合提名达确定性最佳 0.723**。

### 19.8 8 题难病四大指标 + MECE 全矩阵补跑（2026-06-27）

> **动机**：§19.6/§19.7 矩阵在 **14 题常见集** 上 Comp 区分度已足，但 **8 题 rare hand 标签** 此前仅评 **漏斗**（retrieved/spotted/xloss），未与 14 题对齐 **L1tgt/L1mnd/轴可分/L2** 四级指标；亦缺 **MECE 域投影** 尺子（`syndrome_axis_map` 域 vs flat 40 名候选）。本节补跑 **§19 全实验臂**（**跳过 A0_legacy**），并归档。

#### 19.8.1 跑数设置与 caveat

| 项 | 内容 |
|---|---|
| **命令** | `PYTHONPATH=src python scripts/eval_branch_confounder_matrix.py --llm --exclude-arms A0_legacy` |
| **完成** | 2026-06-27T18:42Z；19 臂；`generated_at` 写入 `branch_confounder_matrix.json` |
| **标注** | 8 题：`data/cpg/eval/branch_recall_eval_set_hard.json`（含 L2 / mandatory / axis_pair / `syndrome_map_id`） |
| **脚本扩展** | `eval_branch_multilevel.eval_mece_arm()` → 矩阵每臂输出 `multilevel_hard`、`mece`、`mece_hard` |
| **归档** | `data/cpg/eval/archive/2026-06-27_hard_mece/`（JSON + log + hard 标注 + README） |
| **⚠️ LLM 环境** | 本机 `openai` 包无 `OpenAI` 类 → **A5/A5h/A9l/A11_llm/A12 的 spotter+llm 补抽全部失败**（日志大量 `module 'openai' has no attribute 'OpenAI'`）。带 LLM 臂 **14 题 Comp 不可读**（如 A9l **0.699**）；**hComp / MECE / 确定性臂 / 漏斗** 仍有效。**14 题 LLM 有效 Comp 仍以 gnn-llm §19.7.2 为准**（A9l **0.812**）。 |

#### 19.8.2 8 题难病多级 + MECE₈（节选）

| 臂 | hL1tgt | hL1mnd | h轴可分 | hL2 | **hComp** | **MECE₈** | spot | xloss |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **A11_hybrid_nom** / A11_llm / A12 | 0.875 | 0.750 | 0.643 | 0.714 | **0.656** | **0.688** | 1.0 | 0 |
| A9l_tableC_llm / A9b_no_fanout | 0.875 | 0.688 | 0.643 | 0.643 | 0.622 | 0.594 | 1.0 | 0 |
| **A7_nominate** | 0.875 | 0.688 | 0.571 | 0.643 | 0.583 | 0.562 | 1.0 | 0 |
| A10_hybrid | 0.875 | 0.688 | 0.643 | 0.714 | 0.398 | 0.688 | 0.875 | 0 |
| **A1_grounding** | 0.750 | 0.625 | 0.571 | 0.643 | **0.372** | 0.469 | 0.75 | 1 |
| A2_rollup / A5_llm | 0.750 | 0.625 | 0.643 | 0.643 | 0.411 | 0.500 | 0.75 | 1 |
| A6_fanout | 0.875 | 0.688 | 0.571 | 0.643 | 0.398 | 0.594 | 0.75 | 1 |
| A3_union | 0.143 | 0.375 | 0.071 | 0.429 | 0.247 | 0.302 | 0.5 | 2 |

**MECE₁₄（同跑，勿与 L1tgt 混读）**：A1 **0.125**、A7 **0.143**、A11 **0.119**；`mece_gold_domain_recall` 在 14 题上 **≈0**——flat 40 名多为具体病名，**token 家族 L1tgt 可高** 但 **投影进手工 MECE 域仍低**。

#### 19.8.3 结论（与 §19.7 互补）

1. **常见 vs 难病落差**：A1 **Comp 0.702 → hComp 0.372**（−33pp）。mandatory/轴在刁钻集仍是主瓶颈；**漏斗 spot 6/8→8/8**（A7/A11）说明提名+硬层修 **候选层**，不自动抬 **L1 投影分**。
2. **8 题确定性最佳 = A11_hybrid_nom（hComp 0.656）**；与 A11_llm/A12 **同分** 因本跑 LLM 未生效。相对 A1，A7 提名 **hComp +21pp**、漏斗 **xloss 1→0**（复证 §19.7.3#1）。
3. **A7 逐例**：c1/c13/c17/c18/c22/c24 L1tgt 命中；**c9/c23 仍漏**（c23 adhesions 等机制/解剖措辞投影仍弱）。
4. **MECE₈ 最高 = A11（0.688）**，与 hComp 排序一致；MECE 尺子适合看 **「候选能否投回 syndrome 域」**，与 **recall token 匹配** 分轨（§17.1 / §6.19）。
5. **后续**：在 **gnn-llm** 环境仅重跑 LLM 臂并 **merge JSON**，可保留本节 hard/MECE/确定性结果，恢复 A9l **14 题 0.812** 与 **8 题 hComp** 的同文件对照。

**交叉引用**：阶段报告 **`BRANCH_GENERATION_PHASE_REPORT.md` §7.4、§14.0.1 表 4**（交流版同表）。

---

## 20. Raw chunk → LLM payload 全链路 + 实验消费备忘（2026-06-26）

> **定位**：§15 讲「各 arm 测什么、结果如何」；§17 讲「召回漏斗与缺陷排查」。本节补全中间缺失的**逐步处理细节**——从磁盘上的 raw chunk 到 LLM 实际收到的 JSON payload，以及 LLM 产出如何被下游使用。**迭代 IMP-63/64 或改检索/抽取代码时，先对照本节逐步核对。**
>
> **主线**：实验主路径 **`cpg_llm`**（纯 CPG + 方案A）；`hybrid` / `union_llm` / `cpg_det` 在相应步骤标注差异。
>
> **关键代码**：`scripts/build_cpg_tfidf_index.py` → `RAGRetriever` → `GuidelineBranchSource` → `scripts/eval_cpg_branch_pipeline.py` → `RobustLLMClient.call_module`

### 20.1 总览：离线 vs 在线

```text
【离线 — 实验前一次性】
  HTML/PDF/NXML 原文
    → build_cpg_chunks / manifest 切分
    → cpg_chunks.jsonl（360k+ 条）
    → build_cpg_tfidf_index.py 过滤 + TF-IDF
    → data/corpus/cpg_index/（203,830 useful）

【在线 — 每个 case】
  vignette / case_summary
    → [LLM-1] RootSelectorSurrogate → syndrome 字符串
    → 4–5 条检索 query → TF-IDF top_k=30
    → expand_ddx_siblings（+60 cap）→ 门控 → 去重截断
    → ≤24 条 snippet 字符串
    → [LLM-2] BranchKnowledgeBuilder（方案A）或 GuidelineDDxExtractor（GARMLE-G②）
    → branch_knowledge entry → project_entity 评测
```

**核心事实**：LLM **从不直接读 CPG 库**；只读经检索、闭包、门控、硬截断后的 **prose excerpt 列表**。

---

### 20.2 阶段 0：Raw 语料 → `cpg_chunks.jsonl`（离线）

**脚本**：`build_cpg_chunks.py` + `build_manifest_cpg_chunks.py`（分源策略见 §1.5.3）。

| 步骤 | 操作 | 产出字段 |
|---|---|---|
| 0.1 | 读本地 HTML/PDF/NXML；去导航/Cookie 噪声 | `content`, `url`, `source` |
| 0.2 | 按源切 chunk（NICE 按 URL 章；IDSA 按 H2/H3；PMC 按段落） | `section_path`, `title` |
| 0.3 | 章节 slug → DDx 语义标签 | `chunk_type`（differential / red_flag / evaluation / recommendation） |
| 0.4 | 标记综合征入口页 | `syndrome_anchor`, `entry_type` |
| 0.5 | WikEM 解析 wiki 链接 | `wiki_links: ["MI", "SBO", …]` |
| 0.6 | 聚合同篇 | `source_id`, `article_id` |

**单条 chunk 逻辑形态**（示例）：

```json
{
  "source": "WikEM",
  "source_id": "wikem_syndrome__abdominal-pain-geriatrics",
  "chunk_type": "differential",
  "syndrome_anchor": "Abdominal pain (geriatrics)",
  "content": "Elderly … MI, dissection, mesenteric ischemia …",
  "wiki_links": ["MI", "aortic dissection", "SBO", "…"]
}
```

全库约 **360,234** 条；实验索引只用 useful 子集（§15.1）。

---

### 20.3 阶段 1：Chunk 库 → 实验索引 `cpg_index/`（离线）

**脚本**：`scripts/build_cpg_tfidf_index.py`

**1.1 过滤**（203,830 / 360k 保留）：

- `chunk_type ∈ {differential, red_flag, evaluation, recommendation}`
- `len(content) ≥ 120`
- 非 Cloudflare/Cookie 噪声页；sha256 去重

**1.2 构造检索文本**（wiki_links 文本化拼入，提升 DDx 实体 TF-IDF 命中）：

```python
index_text = f"{section_path or title} {content} {' '.join(wiki_links)}"
```

**1.3 向量化**：`TfidfVectorizer`（80k features, (1,2)-gram）→ `tfidf_matrix.npz` + `metadata.jsonl`（**完整元数据保留**，供闭包/门控）。

此阶段 **无 LLM**。

---

### 20.4 阶段 2：实验 case 输入

**脚本**：`eval_cpg_branch_pipeline.py --arms cpg_llm --llm`

| 输入 | 来源 | 是否进 LLM |
|---|---|---|
| vignette / `text` | u29_full 日志 `case_summary` | LLM-1 全量（≤1500 字）；检索 query 用前 300 字 |
| `gold` | medbullets 正确答案 + `mechanism_to_disease.json` 归一 | **否**（仅评测） |
| CPG 索引 | `data/corpus/cpg_index/`（TF-IDF，203k） | 经检索间接进入 |

加载：`GuidelineBranchSource(RAGRetriever(cpg_index), snomed_vocab, resolver)`；默认 `top_k=30`, `max_candidates=40`。

---

### 20.5 阶段 3：LLM-1 — 抽 presenting syndrome（在碰 CPG 之前）

**函数**：`extract_syndrome_llm(vignette[:1500], llm)`  
**Module**：`RootSelectorSurrogate`  
**模型**：`qwen/qwen3-32b @ T=0`

| 角色 | 内容 |
|---|---|
| system | ≤8 词命名 presenting syndrome，不要诊断 |
| user payload | `{"vignette": "<case_summary 前1500字>"}` |
| 期望 JSON | `{"syndrome": "leukocytosis"}` |

**curated-free**：不读 `syndrome_axis_map.json`。输出 `syn` 驱动后续全部检索 query（弱根如 `"nausea and vomiting"` 会直接拖累下游，§15.7）。

---

### 20.6 阶段 4–8：确定性检索 → snippet 列表（`_retrieve_snippets`）

与 `recall()` **同源检索+门控**，但**不做 spotting**，只产出 LLM grounding 字符串。

#### 20.6.1 构造 query（4–5 条，无 LLM）

```text
1. differential diagnosis of {syn}
2. causes and etiology of {syn}
3. approach to {colloquial}                    # _colloquial() 去 jargon 后，若 ≠ syn
4. differential diagnosis of {syn}. clinical features: {context[:300]}
```

`context` = 完整 case_summary；仅 **300 字**拼入第 4 条（GARMLE-G① context query）。

#### 20.6.2 TF-IDF 检索（每条 query 独立）

```python
hits = retriever.search(q, top_k=30, score_threshold=0.0)
```

每条 query → top **30** hit；5 条 query 合计最多 ~150 hit（含重复）。hit 含**完整** `content`（此时尚未截断）及 `source_id/chunk_type/...` 元数据。

#### 20.6.3 篇内 DDx 闭包 `expand_ddx_siblings`

实验脚本 cap **+60**（`eval_cpg_branch_pipeline.make_gsource`）：

1. **WikEM 合成块**：`"Differential diagnosis includes: MI; aortic dissection; …"`（来自 metadata `wiki_links`）
2. **同 `source_id` sibling 块**：倒排索引 O(hits) 拉齐同篇全部 useful chunk

闭包把「入口块命中」扩展为「同篇散落 DDx」（§18 c1/Pancoast 必需件）；但若直接灌 spotter 候选池会拥挤（§19.5.2）。

#### 20.6.4 On-topic 门控 `snippet_on_topic`

保留：`chunk_type ∈ useful`；或 `syndrome_entry` 且 anchor 重叠；或 title/section_path 含 DDx 词且与 syndrome token 重叠。被滤块 **不进 LLM**。

#### 20.6.5 去重 + 格式化 + 硬上限（**主要信息损失点**）

```python
snippet = f"[{title[:70]}] {content[:400]}"
return out[:24]
```

| 保留 | 丢弃 |
|---|---|
| 标题前 70 字 + 正文前 400 字 | 正文 401 字以后（长 DDx 列表后半） |
| 最多 **24** 条 snippet | 第 25 条及以后 |
| — | `wiki_links` 数组（仅见 prose 或合成句） |
| — | `source`, `url`, `score`, `clinical_area` 等元数据 |

`union_llm` 例外：CPG snippets + StatPearls snippets 拼接后 **[:36]**。

---

### 20.7 阶段 9：LLM-2 payload 组装（`call_module`）

```python
messages = [
  {"role": "system", "content": prompt_text},
  {"role": "user", "content":
      f"Module: {module_name}\nReturn strict JSON only, no markdown.\n"
      f"Payload:\n{json.dumps(payload)}"}
]
```

#### 20.7.1 方案A — `build_branch_knowledge_llm`（`cpg_llm` / `union_llm`）

**Module**：`BranchKnowledgeBuilder`

**Payload**：

```json
{
  "presenting_syndrome": "hypercalcemia",
  "reference_excerpts": [
    "[Merck Manual > Hypercalcemia > Causes] Primary hyperparathyroidism …",
    "[PMC-OA review > Differential diagnosis] …",
    "… ≤24（union 36）条 …"
  ]
}
```

**LLM 一次调用完成四件事**（不分步）：

1. 选 **单一分类轴**（etiology / anatomy / mechanism / morphology / lineage）
2. 划 **3–6 个 MECE 域**
3. 每域列 **具体疾病实体**（必须 grounded in excerpts）
4. 标 **mandatory=true** 的 can't-miss 域

**期望输出**：

```json
{
  "axis": "etiology",
  "domains": [
    {"name": "PTH-related hypercalcemia",
     "entities": ["primary hyperparathyroidism", "…"],
     "mandatory": true}
  ]
}
```

**缓存**：命中 `auto_axis_cache_cpg.json[syndrome]` → 跳过 LLM-2。

#### 20.7.2 GARMLE-G② — `recall_llm`（`hybrid` 的 CPG 侧）

**Module**：`GuidelineDDxExtractor`  
**同一套** `_retrieve_snippets`（≤24 条）  
**任务**：仅 flat 疾病列表 `{"families": ["disease1", …]}`，**不定轴、不分族**  
**下游**：与 StatPearls 确定性 `recall()` 合并 → `KBAxisMap.partition_from_candidates`（SNOMED 分区墙，§15.4）

---

### 20.8 阶段 10：LLM 输出后处理（无 LLM）

`build_branch_knowledge_llm` 内：

| 步骤 | 操作 |
|---|---|
| 10.1 | 解析 JSON；失败 → `_empty_entry()` |
| 10.2 | 滤 `_GENERIC_NAMES`（infection、neoplasm 等） |
| 10.3 | `DiseaseNameResolver.expand_to_entities()` 机械展开宽泛族 |
| 10.4 | `_domain_to_entry_domain()` → `member_keywords` + `_entities` |
| 10.5 | 组装 `branch_knowledge` entry（与 `SyndromeAxisMap` 契约一致） |
| 10.6 | 写 `auto_axis_cache_cpg.json` |

实验脚本额外：`_attach_l2(entry)` → `KBAxisMap._split_variants()` 生成 L2 子轴。

**方案A 绕开 SNOMED 分区**：entry 直接用于 `SyndromeAxisMap.project_entity(gold, entry)`。

---

### 20.9 各实验 arm 的 LLM 消费对照

| Arm | LLM 调用次数 | 读 CPG 的方式 | snippet 上限 | LLM-2 任务 | 下游 |
|---|---:|---|---:|---|---|
| `orig` | 1（仅 syndrome） | 不读 CPG | — | — | SNOMED 分区 |
| `cpg_det` | 1（仅 syndrome） | 不读；spotter 吃全文 | — | — | SNOMED 分区 |
| **`cpg_llm`** | **2** | 方案A excerpts | **24** | 定轴+分族+实体+mandatory | 直接投影 |
| `union_llm` | 2 | CPG∪SP excerpts | **36** | 同上 | 直接投影 |
| `hybrid` | 2 | recall_llm excerpts | 24 | flat 实体列表 | SNOMED 分区 |
| `sp_llm` | 2 | 不读 CPG（StatPearls） | 24 | 方案A | 直接投影 |

**口径提醒**：`max_candidates=40` 是 **spotter/recall_llm 的疾病实体数**，不是 chunk 数；方案A **不经过** top-40 实体池。

---

### 20.10 「spot / spotting」术语备忘

**spotting** = 从已检索片段文本中 **识别具体疾病名** 并写入候选 dict 的过程（branch-gen **独有**子环节，QA-RAG 无此步）。

**两层诊断口径**（§17 / `eval_branch_rag_recall_diagnosis.py`）：

| 层 | 名称 | 判据 |
|---|---|---|
| 检索层 | retrieved | 合并 snippet 文本含 gold 家族词 |
| 抽取层 | spotted | `recall()` 候选 dict keys 含 gold（方案B 实体匹配） |

**`_spot()` 机制**（`guideline_branch_source.py`）：最长优先 5-gram × SNOMED disorder vocab 词面匹配；**非** LLM。

**决定能否 spot 到 gold 的主要因素**：

1. **词表/词面**：是否在 SNOMED vocab；eponym/机制名 verbatim 不匹配则 miss（C1）
2. **片段是否进 spotting 输入**：检索/门控/闭包（Step 1）
3. **后处理过滤**：综合征自指、`_GENERIC_NAMES` 黑名单
4. **排序截断**：多片段 `scored[dz]+=w` 累加 → `max_candidates=40` 噪声淹没（C4）；k↑ 伤 spotting（C5）

语料以 **具体病名** 为主、同综合征下具体病极多 → flat spot + top-40 **极易淹没** rare gold（§17.5.1 c9/c13/c18）。

---

### 20.11 信息漏斗（数量级）

```text
360,234 raw chunks
  → 203,830 进 cpg_index
  → ~5 queries × top_k=30 ≈ 150 hit（含重复）
  → expand +60 cap → 200+ 块
  → snippet_on_topic → 几十块
  → 去重 + [:24] → 24 块 × 400 字 ≈ 10k 字符
  → JSON payload + system prompt → 一次 LLM-2 调用
```

**LLM 从未看到**：完整索引、chunk 元数据表、闭包后未进 top-24 的块、400 字后的 DDx 枚举、金标准/评测标签。

**实验刻意未做**： grounding 核验门（TODO-GL-16）；`wiki_links` 结构化直喂；分批 map-reduce LLM；IMP-61 差异化检索（实验用统一 TF-IDF）。

---

### 20.12 与相关章节交叉引用

| 想了解… | 见 |
|---|---|
| 各 arm 实验结果与 curated-free 口径 | §15 |
| 召回漏斗、spotting 损失、nprobe | §17 |
| **六层缺口归因全景（A–F）+ 落地双序** | **§17.2.1** |
| **原调研 Part B（B1–B11）对照与 ID 说明** | **§17.4.2** |
| 数据源 100% 闭包上界 | §18 |
| 闭包/差异化/锚点 UNION 落地与更正 | §19 |
| **具体病名淹没、参数口径、结构化 DDx 演进** | **§21** |
| IMP-63 改什么 | §17.7；闭包隔离见 §19.5.2 |
| IMP-64 结构化 DDx 索引（规划） | §14.3、§17.3 C6、§21.6 |

**IMP-63 改造锚点**（对照本节逐步改）：

- 检索：`retrieve_k=50`（广召回）
- 抽取通道：门控/MMR 后 **仅 top-15 高质量块** → `recall_llm` 或结构化直抽
- **禁止** raw 闭包 + n-gram spotter 直接灌 `max_candidates=40` 池（§19.5.2 拥挤实锤）

---

## 21. Branch-gen 口径澄清：具体病名淹没、参数边界与结构化 DDx 演进（2026-06-26）

> **定位**：本节整理 branch 生成阶段若干**易混口径**与**结构性质因**——为何语料以具体病名为主却要在 L1 族层竞争、pipeline 中 `top_k` / snippet 上限 / `max_candidates` 各指什么、flat spotting 如何淹没 gold、LLM 能否一次吃尽所有 chunk，以及「离线结构化 DDx → 本体 rollup → 诊断树」是否与现有 IMP 同构。与 **§20**（逐步处理链）互补：§20 讲「怎么做」，本节讲「为何如此设计 / 为何会失败」。
>
> **依据**：§17.5.1 抽取损失实测、§17.5.4 top_k 敏感性、§19.5.2 候选池拥挤、§15.4 SNOMED 分区墙、`guideline_branch_source.py` / `auto_axis.py` 代码行为。

### 21.1 关键口径：`40` / `30` / `24` 不可混读

讨论 branch-gen RAG 时，「top-40」「hit@40」常与「检索块数」混为一谈。**当前 pipeline 中各参数含义严格不同**：

| 参数 | 代码位置 | 计量对象 | 实验默认值 | 服务环节 |
|---|---|---|---:|---|
| **`top_k`** | `GuidelineBranchSource._top_k`；`RAGRetriever.search()` | 单次 query 检索返回的 **chunk 数**（闭包后可扩至 200+） | **30** | 检索排序 |
| **`_retrieve_snippets` 上限** | `guideline_branch_source.py` `out[:24]` | 喂给 LLM 的 **snippet 条数**（union 臂 **36**） | **24** | LLM grounding |
| **每 snippet 截断** | `content[:400]` | 单条 excerpt 字符上限 | **400** | LLM grounding |
| **`max_candidates`** | `GuidelineBranchSource._max_candidates`；`recall()` / `recall_llm()` | spotting / LLM 抽取后保留的 **疾病实体数**（dict keys） | **40** | 候选族排序截断 |

**结论（须牢记）**：

- **`max_candidates=40` = 40 个疾病候选实体，不是 40 个 chunk。**
- **方案A（`cpg_llm`）不经过 top-40 实体池**：LLM 直接产出 `branch_knowledge`（轴 + 域 + 实体），与 spotter 的 40 槽无关（§20.9）。
- **LLM 实际 grounding 规模**：约 **24 × 400 ≈ 9.6k 字符** prose excerpt，**不是**闭包后 200+ 块全文，**更不是** 40 chunk。

```text
检索平面（chunk）          抽取平面（disease entity）         分区平面（domain/族）
top_k=30 × ~5 queries  →  _spot / recall_llm  →  max_candidates=40  →  方案A 或 SNOMED 分区
     ↑                          ↑                           ↑
  §20.6.2                   §20.10 / §17.3 C*            §15 / KBAxisMap
```

---

### 21.2 语料形态：具体病名为主，L1 目标为族/域

**观察（与数据源抽样一致）**：CPG/指南 DDx 块在原文中列举的是**具体疾病实体**，而非 BranchCreator 契约所需的 **3–7 个 L1 域/族**。

| 源 | 典型形态 | 示例 |
|---|---|---|
| WikEM | 结构化链接 + 散文 | `wiki_links: ["MI", "aortic dissection", "SBO", …]` |
| PMC / 协会 HTML | 散文式 DDx 枚举 | `nephrolithiasis, renal abscess, urosepsis, …` |
| StatPearls | 章节 `> Differential Diagnosis` | 正文逐条列具体病 |

**BranchCreator 契约**（SYNDROME §8.1）：L1 需 **MECE 域/族**，不是 200 个 flat 具体病名。

**当前默认路径（`recall()` / spotter）** 在两者之间的桥接方式为：

```text
具体病名（语料）
  → _spot() 词面命中 SNOMED disorder
  → 多 snippet 累加权重 w
  → top-40 疾病实体 dict
  → （下游）KBAxisMap.partition / 方案A LLM 再聚成族
```

**常见误解**：「族名被族名淹没」。实测机制是 **「具体病名在 flat 实体池里互相竞争，罕见 gold 具体病被高频噪声具体病挤出 top-40」**（§17.5.1：c9 leukemoid 片段含 gold，top-5 候选为 urticaria/MI/…）。

项目内 **`KBAxisMap._taxonomy_groups()`**（`auto_axis.py`）已具备「具体 concept → is_a 上位概念成族」逻辑，但默认 spotter 路径 **未先做 rollup**，而是在实体平面直接竞争；且 SNOMED rollup 对 adhesions/peliosis/foreign body 等仍存在投影墙（§15.4）。

---

### 21.3 flat spotting + `max_candidates=40` 的淹没机制

同一 presenting syndrome 下，语料可关联的**具体病数量极大**（闭包后 8→213 chunk，每块 `_spot()` 又可命中多个实体）。在 **不加族层聚合** 的前提下：

| 现象 | 机制 | 后果 |
|---|---|---|
| 常见病跨篇重复 | MI、urticaria、infection 等在多块出现 → `scored[dz] += w` 累加高 | 占满 40 槽 |
| 罕见 gold 单次出现 | leukemoid、peliosis、glucagonoma 仅 1–2 块提及 → 分数低 | **挤出 top-40** |
| 词面/度量不一致 | 语料写 eponym/机制名，vocab 认 SNOMED 标准名 | 检索层有、spot 层无（C1，§17.5.1） |
| top_k 增大 | 更多噪声 chunk 进入 spotter（§17.5.4） | 检索↑、spotting↓（87.5%→50%） |
| 闭包灌候选池 | sibling 块引入更多常见病实体（§19.5.2） | 7/14 常见病 mandatory 覆盖下降 |

**与 §17 诊断漏斗的对应**：上述属于 **Step 2「检索到但未抽出」（C 类）** 的结构根因之一，而非 Step 0 缺源（§18 闭包上界 100%）。

---

### 21.4 LLM 一次性消费 snippet 的能力边界

**方案A / GARMLE-G②** 均通过 `_retrieve_snippets` 将 CPG 压缩为 ≤24（union 36）条 excerpt 后 **单次 LLM 调用**（§20.7）。

| 维度 | 评估 | 依据 |
|---|---|---|
| 上下文长度 | 24×400 字对 32k 模型通常可装下 | §20.11 数量级 |
| 中部信息利用 | 长而杂的 excerpt 列表存在「中间丢失」风险 | 通用 RAG 经验 |
| 噪声 vs 增益 | **多 chunk 已证实有害**：k=30 时 spotting 50% < k=8 时 75% | §17.5.4 |
| 方案A 分工 | LLM 同时做抽取+分族+MECE，优于纯 spotter，但对 eponym 鸿沟（c1）仍弱 | §15.7、§19.3④ |

**设计结论**：

- **不应假设**「一次 LLM 读取闭包后 200+ chunk 全量原文 → 输出完整诊断树」为可靠主路径。
- **更稳架构**：**先结构化/聚合（族层）→ 必要时小上下文 LLM 定轴/处理 orphan**（§21.5），而非持续增大 `top_k` 或 snippet 上限。

---

### 21.5 结构化 DDx 改造方向（IMP-64 规划，与现有 IMP 同构）

**问题陈述**：在「语料 = 具体病名、目标 = L1 族、竞争 = flat top-40 实体」三角下，在线 n-gram spotter 结构性弱势；仅调 spotter 参数无法根治（§19.5.2、§17.3 C4/C5）。

**目标架构**——将 branch-gen 从：

```text
检索 prose → 在线 n-gram spot → flat top-40 实体 → 再分区
```

演进为：

```text
离线/半离线 per-chunk DDx 结构化
  → 在线按综合征 union 实体集（非重新 spot prose）
  → 本体 rollup 成族（+ 孤儿走方案A）
  → 直接输出 branch_knowledge 形诊断树
```

**与已有 IMP / 代码的对齐**：

| 改造步骤 | 已有 / 规划 | 章节 |
|---|---|---|
| chunk 内抽 DDx 实体 | WikEM `wiki_links` 直读；`_spot()`；`recall_llm` | §16.1、§17.3 C6 |
| 医学 NER + 归一 | **IMP-58** scispaCy UMLS → CUI/MONDO | §14.3 |
| 多源实体并集 | **IMP-57** `ddx_union_by_syndrome.json` | §14.2 |
| is_a 向上聚类成族 | `KBAxisMap._taxonomy_groups()` | `auto_axis.py` |
| LLM 定轴 MECE 输出树 | **方案A** `build_branch_knowledge_llm` | §15、§20.7 |

#### 21.5.1 建议的分层算法（演进，非一步替换）

**离线**（对每个 chunk）：

1. `chunk_type=differential` 或含 `wiki_links` → **直读结构化列表**（零 NER 成本）
2. 否则 → section-aware NER（scispaCy / QuickUMLS）→ mention + span
3. **IMP-58** 归一 → CUI / MONDO / SNOMED concept
4. 写入 `ddx_entities_by_chunk.jsonl`：`{source_id, syndrome_anchor, entities[], provenance}`

**在线**（给定综合征 S）：

1. 检索命中入口文章（IMP-61b 锚点 UNION + IMP-31 闭包，§19）
2. 从预提取表 **union 实体**（按 source 加权、跨源一致 boost），**而非**对 prose 重新 spot
3. **Rollup**：具体 concept → is_a 选「覆盖 2–70% 候选的最 specific 祖先」→ L1 域
4. **孤儿实体**（adhesions / foreign body 等 is_a 挂不住）→ 方案A 小 prompt 或 mechanism 轴
5. **mandatory** = cant_miss + ≥2 源一致（§14.6）→ 输出 `branch_knowledge` 契约

**相对 flat spotter 的优势**：

1. 竞争发生在 **族层**，而非 200+ 具体病 flat 排序
2. WikEM / 列表型 DDx **绕过 spotter**，gold 不易被 urticaria 等重复常见病挤掉
3. LLM 输入可变为 **「已抽取实体表 + 少量 provenance」**，降低 24 块 prose 上限压力

#### 21.5.2 已知风险（项目已部分验证）

| 风险 | 说明 | 缓解 |
|---|---|---|
| 纯 NER ≠ DDx 抽取 | 须区分「鉴别列表中的病」vs「正文合并症」 | `chunk_type`、章节标题、列表格式、轻量句法 |
| 缩写 / 俗称 | WikEM `MI`、`SBO` 等 | IMP-58 + 缩写表 |
| SNOMED rollup 墙 | adhesions/peliosis 等投影失败 | rollup 失败集走方案A（§15.4） |
| 轴选择 | 同一批病可多轴 MECE 切法 | LLM 或 `SyndromeAxisMap` 定轴，不能单靠 is_a |
| 离线成本 | 36 万 chunk 全量 NER | 批处理；优先 WikEM / 显式 DDx 高价值子集 |

**输出形态**：`build_branch_knowledge_llm` 产出的 `branch_knowledge` **可直接作诊断树**；改进点在于 **树节点应由「结构化实体 rollup + 多源投票」生成**，而非 LLM 从 24 段 prose 同时猜实体与分区。

---

### 21.6 与现有 IMP 的演进顺序（非二选一）

| 阶段 | 动作 | 针对问题 | ID |
|---|---|---|---|
| **✅ 已落地** | 闭包**移出候选池**→grounding；`recall_llm` 合并兜底（**非** MMR-trim 确定性 spotter，§19.6#4） | 抽取损失、候选拥挤、方差 | **IMP-63**（§19.6） |
| **✅ 已落地** | `_taxonomy_groups` is_a 反向归族（**覆盖增广**，在线 spotted 实体层） | 族层竞争、轴可分性 | **IMP-64**（§19.6，轴可分 +7pp） |
| **中期 P1** | WikEM `wiki_links` + DDx 列表 parser 直抽 | 零成本结构化子集 | C6 / §17.3 |
| **中期 P1** | IMP-58 归一 + 按 `source_id` 预聚合 | 具体病 → 规范 ID | **IMP-58** |
| **中期 P2** | 离线 NER 索引 + 在线 union（替 prose 重 spot） | §21.5 完整离线版（在线归族已落地） | **IMP-64+**（离线扩展） |
| **轴 / 孤儿** | 方案A 仅对 rollup 失败集 / 定 axis | SNOMED 墙 | 方案A、§15.4 |

不必在「继续修 spotter」与「全面结构化」之间二选一：**IMP-63 解燃眉之急（已落地）；IMP-64 在线归族已落地（覆盖增广版，提轴可分性），离线 NER 索引版为后续结构化主干**。

> **§19.6 实测要点**：①归族**不能整体替换** flat 排序（is_a 会把 primary/secondary 等**相反 L1 轴极**归为兄弟，整体替换会塌缩该区分），故采**覆盖增广**（保强 flat hit + 仅为否则整族缺失的族保留少量槽）；②归族价值在**轴可分性/结构**（0.571→0.643）而非 flat 召回（持平）；③LLM grounded 抽取（C7）才是最大 flat 召回杠杆（L1tgt 0.929）。

---

### 21.7 本节结论（备忘）

1. **语料以具体病名为主、同综合征下具体病极多** → flat spot + `max_candidates=40` **结构性易淹没** rare gold（§17.5.1、§19.5.2）。
2. **`40` = 疾病候选实体数，不是 chunk 数**；LLM grounding 实际约 **24 snippet × 400 字**，且 **增大 chunk 数已证有害**（§17.5.4）。
3. **「NER → 归一 → 本体 rollup → 诊断树」为正确演进方向**，与 IMP-57/58、§14、`_taxonomy_groups`、方案A **同构**；宜作为 IMP-63 之后的主干（**IMP-64**），而非抛弃检索。
4. **关键增量**：离线 per-chunk DDx 结构化索引 + 在线按文章 union + **族层聚合**；LLM 角色从「读大量 prose 同时猜实体与分区」降级为「定轴 / 消歧 / 处理 is_a orphan」。
