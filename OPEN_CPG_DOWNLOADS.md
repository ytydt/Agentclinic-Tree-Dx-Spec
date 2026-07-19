结论：**DynaMed、UpToDate、BMJ Best Practice 都不应通过爬虫/批量抓网页/破解离线 App 缓存来本地化**。可行路径只有官方 API、内容授权或机构集成；若受限，建议改用开放 CPG + 本体/KG + StatPearls + **已购 Merck 19e PDF**（内部 RAG）等替代语料。

## 三大商业库如何合规本地化

| 来源 | 是否可直接批量下载 | 合规路径 | 备注 |
|---|---:|---|---|
| **DynaMed** | 否，除非授权 | EBSCO **MedsAPI / Product Content API**，OAuth2，需 DynaMed 订阅与开发者权限 | 官方文档提到 Product Content API 可取 article JSON，也支持 offline caching 场景，但取决于合同 |
| **UpToDate** | 标准订阅下否 | Wolters Kluwer **UpToDate Digital Architect / Connect APIs**，企业合同 + subscription key | 面向 EHR / 数字平台嵌入；普通账号不能批量下载内容 |
| **BMJ Best Practice** | 标准订阅下否 | BMJ content licensing / syndication / EHR integration / HL7 Infobutton / search widget | App 可离线阅读，但不等于允许抽取本地语料库；大规模复用需 BMJ/CCC 授权 |

不要做：
- 登录后批量爬网页。
- 抽取移动 App 离线包。
- 共享机构账号批量抓取。
- 将全文导入本地 RAG 后供多人使用，除非合同明确允许。

如果拿到授权，建议本地化格式：

```text
vendor_id
title
section_path
content_html / content_text
last_reviewed
last_updated
evidence_grade
guideline_links
icd10 / snomed / mesh / umls tags
license_scope
retrieved_at
```

并做增量更新、访问审计、授权范围隔离。

## 如果访问受限：替代 CPG 来源

### 1. 首选开放/半开放指南库

| 来源 | 获取方式 | 适合替代的信息 |
|---|---|---|
| **NICE Guidance** | NICE syndication API，需申请 API key；网页/PDF 公开 | 英国高质量 CPG、诊疗路径、诊断/管理建议 |
| **WHO Guidelines / WHO SMART Guidelines** | WHO 官网、部分结构化 SMART Guidelines | 全球公共卫生、感染病、母婴、慢病、资源受限场景 |
| **CDC Guidelines** | 官网、MMWR、API/RSS/网页 | 感染病、疫苗、公共卫生、暴露处理 |
| **USPSTF** | 官网公开建议 | 筛查、预防、风险分层 |
| **ECRI Guidelines Trust** | 检索/索引为主 | 找指南来源与元数据，不一定提供全文 API |
| **PubMed / Europe PMC** | E-utilities，publication type: Practice Guideline / Guideline / Consensus | 批量发现指南文献、摘要、DOI、PMID |

### 2. 专科协会指南

这些通常比 DynaMed/UpToDate 更接近原始 CPG，可按专科批量建索引。

| 专科 | 推荐来源 | 可替代内容 |
|---|---|---|
| 心血管 | **ACC/AHA**, **ESC** | 胸痛、ACS、心衰、瓣膜病、心律失常 |
| 感染病 | **IDSA**, CDC, WHO | 抗感染、肺炎、尿路感染、败血症、HIV |
| 肿瘤 | **NCCN API**（需 AccessKey/授权）, **ASCO**, **ESMO** | 肿瘤诊断分期、治疗路径、red flags |
| 肾脏 | **KDIGO** | AKI、CKD、电解质、肾小球病 |
| 呼吸 | **GOLD**, **GINA**, ATS/ERS | COPD、哮喘、间质肺病、肺栓塞相关指南 |
| 内分泌/代谢 | **ADA Standards of Care**, Endocrine Society | 糖尿病、高钙、甲状腺、肾上腺 |
| 风湿 | **ACR**, EULAR | 关节炎、血管炎、自免疾病 |
| 神经 | **AAN** | 卒中后、癫痫、头痛、神经肌肉 |
| 妇产 | **ACOG**, RCOG | 妊娠、异位妊娠、产科急症 |
| 放射/检查 | **ACR Appropriateness Criteria** | 影像检查选择、症状到检查路径 |
| 血液 | ASH, BSH | 贫血、白细胞异常、凝血、血液肿瘤 |

### 3. 开放临床综述/点-of-care 替代

| 来源 | 获取方式 | 用途 |
|---|---|---|
| **StatPearls / NCBI Bookshelf** | 公开网页；MedRAG/statpearls 已有分段语料 | 疾病概览、鉴别诊断、评估、治疗，适合 RAG |
| **Merck Manual 19e（已购 PDF）** | 本地 PDF（`build_merck_manual_corpus.py`） | Approach/DDx 症状路径（内部 RAG only，§1.9） |
| **Merck Manual Professional（在线）** | 网页公开，注意许可 | 仅 metadata/链接；**勿爬取正文** |
| **MedlinePlus** | NIH，结构稳定 | 患者向但质量可靠，可抽症状/检查/疾病关系 |
| **AAFP articles** | 部分公开 | 初级 care 诊断流程、常见病 |
| **BMJ/NEJM/JAMA open articles** | 只用开放许可部分 | 高质量综述，但版权需逐篇确认 |

## 对你这个项目的建议组合

如果目标是“综合征根节点 → 一级分支 → 防漏正确分支”，不需要完整复制 UpToDate/DynaMed。更合适的是建三层本地语料：

### A. CPG 原文索引层
用于权威建议、诊疗路径、can’t-miss：

- NICE
- WHO
- CDC
- IDSA
- ACC/AHA/ESC
- ADA/KDIGO/GOLD/GINA/ACR/ACOG/AAN/ASCO/ESMO 等协会指南
- ACR Appropriateness Criteria

### B. Point-of-care 综述层
用于 differential diagnosis、evaluation、clinical features：

- StatPearls
- Merck Manual 19e（已购 PDF，`data/corpus/merck/`；在线 Professional 版仅链接）
- MedlinePlus
- AAFP 公开综述

### C. 结构化知识层
用于自动 coverage / disease→domain 投影：

- HPO/HPOA
- MONDO / Disease Ontology
- SNOMED CT（如有许可）
- UMLS（如有 UMLS license）
- PrimeKG
- Monarch
- SemMedDB / SemRep
- LOINC

## 实操路线

1. **不要先追商业库全文**。先抓开放 CPG + StatPearls + 已购 Merck 19e PDF，足够支撑 schema/coverage 研究。
2. 用 PubMed E-utilities 建 `guideline_index`：筛 `Practice Guideline`, `Guideline`, `Consensus Development Conference`。
3. 对每篇指南/章节抽取：
   - `condition`
   - `clinical presentation`
   - `differential diagnosis`
   - `red flags / urgent referral`
   - `recommended tests`
   - `management pathway`
   - `evidence grade`
4. 用 UMLS/SNOMED/HPO/MONDO 标准化实体。
5. 本地只存开放许可全文；受限内容只存 metadata/link，不存全文。
6. 若后续确需 DynaMed/UpToDate/BMJ，走企业授权，明确：
   - 是否允许 bulk content ingest；
   - 是否允许 RAG/LLM use；
   - 是否允许 derivative structured database；
   - 是否允许多人访问；
   - 更新/删除义务。

一句话：**商业库用官方授权 API；无授权时，用 NICE/WHO/CDC/专科协会指南 + StatPearls + 已购 Merck 19e PDF + HPO/MONDO/PrimeKG 组合，能更合规且更适合结构化 BranchCreator 知识库。**

## 「症状入口 + DDx 段」资源的开放许可现实（2026-06-24 核实，重要）

为「综合征→L1 分支→防漏」目标最想要的是**按症状组织、含显式鉴别诊断段**的 point-of-care 资源。实测后多数闭源或限制复用，**特此澄清以免误用**（详见 `CPG_RAG_EXTRACTION.md` §13.2）：

| 源 | 结构契合度 | 许可现实 | 处置 |
|---|---|---|---|
| **NICE CKS**（cks.nice.org.uk，370 主题/~1000 场景） | 极高（assessment·diagnosis·referral·DDx） | **非开放**：IP 属 **Agilio Software**，**不在 NICE 开放内容许可内**，**不走 syndication API**；仅 NHS/学生免费，大学/商业须 Agilio 授权 | **排除**（≠ NICE 开放指南，勿混淆） |
| **AAFP**（American Family Physician） | 高（"Differential diagnosis of…"） | 全文版权保留，复用需付费授权 | **排除/需授权** |
| **Merck Manual 19e（已购 PDF）** | 高（352 章 TOC + **23** Approach 章） | 用户已购，内部 RAG only | **`scripts/build_merck_manual_corpus.py`** → `data/corpus/merck/`（**9,629** chunks）；见 [`CPG_RAG_EXTRACTION.md`](CPG_RAG_EXTRACTION.md) §1.9 |
| **Merck Manual Professional（在线）** | 高（"Approach to the patient with…"） | 免费阅读，但 reuse/posting/入库须书面许可 | 当前 `msd_child__` 仅作 metadata/链接，**勿爬取在线正文** |
| **WikEM**（OpenEM Foundation） | 中高（急诊 can't-miss） | **CC BY-SA 3.0**，但附 **AI/ML 使用限制条款**（训练/微调/评测） | 检索复用须署名 + ShareAlike，AI/ML 用途先法务确认 |
| **StatPearls / 开放教科书 / NICE 开放指南 / WHO / CDC / PMC-OA 综述** | 中–高 | ✅ 开放可整库 | **覆盖保证主力**（见 §13.2–13.3） |

**结论**：开放许可下不存在可整库镜像的「BMJ-BP 式症状→DDx」资源；覆盖保证 = 开放源集成 + 症状入口子集挖掘 + KG/本体覆盖审计 + curated can't-miss 下界（`CPG_RAG_EXTRACTION.md` §13）。

# Open CPG Download Notes

本文件记录**可公开获取**的 Clinical Practice Guideline (CPG) 本地镜像方式、扩展抓取流程与最新下载结果。商业源（DynaMed、UpToDate、BMJ Best Practice）未镜像。**NCCN** 已通过注册账号下载 Navigator 清单 PDF，存于 `data/cpg/restricted/nccn/`（受限、不入 git）。

## 当前产物（2026-06-24：Merck 19e + DDx 三源合并）

### 三层语料总览

| 层 | 路径 | 用途 | 规模（当前） |
|---|---|---|---:|
| **A. 开放 CPG 原文** | `data/cpg/raw/` + `manifest_latest.jsonl` | 权威建议、诊疗路径 | **2037** 条 ok / 2041 总，~463 MB+ raw |
| **A′. 指南发现索引** | `data/cpg/api/*_latest.jsonl` | PMID/PMC/DOI 元数据，按需拉全文 | PubMed **320** + Europe PMC **1000** |
| **A″. NCCN 受限 PDF** | `data/cpg/restricted/nccn/` | 肿瘤 CPG（个人账号/EULA） | **92** PDF，~171 MB |
| **B. 点-of-care** | `data/poc/medlineplus/processed/` | 症状/疾病患者向摘要 | **2029** 主题 chunks，~11 MB |
| **B′. StatPearls** | `data/corpus/statpearls/` | 疾病综述 RAG（独立语料） | **367,799** 段，~4.4 GB |
| **B″. Merck 19e（已购 PDF）** | `data/corpus/merck/` | Approach/DDx RAG（**内部 only**，禁止再分发） | **9,629** chunks / **353** 章 / **23** Approach |
| **C. CPG DDx chunks（合并）** | `data/cpg/processed/cpg_chunks.jsonl` | WikEM + PMC-OA + manifest + Merck | **360,234**（`--useful-only`） |
| **C′. Manifest CPG chunks** | `data/cpg/processed/manifest_cpg_chunks.jsonl` | NICE + 协会 HTML（§1.5.3） | **39,091** useful / **3,196** 篇（**198** bot_gate 跳过） |
| **C″. Bot-gate 审计** | `data/cpg/eval/manifest_bot_gate_report.json` | PubMed/PMC 浏览器校验页清单 | **198** 条（2.09% 镜像） |

### 开放 CPG 镜像指标

| 指标 | 开放 CPG | NCCN 受限 | 点-of-care / API |
|---|---:|---:|---:|
| 种子主条目 | **2024**（70 手工 + **1954** 派生，含 NICE **133**） | — | — |
| manifest 条目（含附件） | **2041** | **92** | MedlinePlus **2029** chunks |
| 下载成功 | **2037 / 2041** | **92 / 92** | XML 3 文件 + chunks 已解析 |
| API 元数据索引 | — | — | PubMed **320** + Europe PMC **1000** |

**本批新增派生**（相对 1202 条基线，+713）：

| 前缀 / 来源 | 新增 | 说明 |
|---|---:|---|
| `acc_aha_pm__` | **246** | PubMed ACC/AHA 指南（2010–2026，优先 PMC 全文） |
| `esc_epmc__` | **150** | Europe PMC：*Eur Heart J*「ESC Guidelines」 |
| `ash_ba_epmc__` | **120** | Europe PMC：*Blood Advances* ASH 指南 |
| `ssc_epmc__` | **80** | Europe PMC：*Crit Care Med* SSC/SCCM |
| `ssc_pm__` | **76** | PubMed Surviving Sepsis / SCCM 指南 |
| `sccm_child__` | **38** | SCCM 官网指南 hub 子页 |

**种子派生构成**（`open_cpg_seed.json`，全量 Top 15）：

| 前缀 / 来源 | 条数 | 说明 |
|---|---:|---|
| `acr_ac__` | 278 | ACR Appropriateness Criteria |
| `acog_child__` | 337 | ACOG sitemap |
| `acc_aha_pm__` | 246 | ACC/AHA PubMed/PMC |
| `esc_epmc__` | 150 | ESC *Eur Heart J* PMC |
| `ash_ba_epmc__` | 120 | ASH *Blood Advances* PMC |
| `idsa_child__` | 100 | IDSA A–Z |
| `aan_pm__` | 88 | AAN PubMed |
| `ssc_epmc__` | 80 | SSC/SCCM Crit Care Med PMC |
| `ssc_pm__` | 76 | SSC/SCCM PubMed |
| `rcog_child__` | 71 | RCOG Green-top |
| `endocrine_pm__` | 51 | Endocrine Society PubMed |
| `sccm_child__` | 38 | SCCM 官网单篇 |
| `eular_child__` | 42 | EULAR |
| `ash_sub__` | 25 | ASH topic 子页 |
| `msd_child__` | 31 | MSD Manual |

**manifest 按来源 Top 10**（`status == ok`）：ACOG 339、ACR 300、**ACC/AHA 248**、IDSA 105、**ASH 156**、AAN 90、**ESC 153**、**SSC/SCCM 196**、RCOG 72、Endocrine 65。

核心路径：

| 用途 | 路径 / 脚本 |
|---|---|
| 开放 CPG 下载 | `scripts/download_open_cpg.py`（`--skip-existing`、`--insecure`） |
| HTML 索引 → seed | `scripts/expand_open_cpg_seed.py` |
| API 一键管道 | `scripts/run_cpg_api_pipeline.py` |
| 手 curated 扩展 | `data/cpg/open_cpg_seed_expansion.json` |
| POC 索引 seed | `data/cpg/open_poc_seed.json` |
| API 派生 seed | `data/cpg/open_cpg_api_seed.json`（ESMO sitemap） |
| 合并后种子 | `data/cpg/open_cpg_seed.json` |
| 开放 manifest | `data/cpg/manifest_latest.jsonl` |
| PubMed 指南索引 | `data/cpg/api/pubmed_guideline_index_latest.jsonl` |
| Europe PMC 索引 | `data/cpg/api/europepmc_guideline_index_latest.jsonl` |
| MedlinePlus 批量 | `scripts/download_medlineplus_bulk.py` → `data/poc/medlineplus/raw/` |
| MedlinePlus 解析 | `scripts/parse_medlineplus_topics.py` → `data/poc/medlineplus/processed/` |
| NCCN PDF | `scripts/download_nccn_navigator_pdfs.py` |
| NCCN manifest | `data/cpg/restricted/nccn/manifest_latest.jsonl` |
| StatPearls（独立） | `data/corpus/statpearls/statpearls_chunks.jsonl` |

`manifest_latest.jsonl` 每行是一条 JSON，字段包括 `id`、`parent_id`、`source`、`title`、`url`、`clinical_area`、`access`、`status`、`sha256`、`raw_path`、`text_path`。下游索引应**以 manifest 为入口**。

## 已镜像来源（按学会/机构）

### 首批（15 个主条目，仍保留）

- **CDC/MMWR**：阿片类镇痛处方指南
- **CDC**：STI 2021（页面 + 全 PDF）；HIV Nexus 指南索引
- **USPSTF**：A/B 推荐总表
- **NICE**：脓毒症 NG51、疑似癌症 NG12、胸痛 CG95、头痛 CG150
- **IDSA/ATS**：成人 CAP（页面 + 路径/摘要 PDF）
- **IDSA/SHEA**：C. difficile 2021
- **WHO**：成人高血压（页面 + PDF）；0–59 天婴儿严重细菌感染（页面 + PDF）
- **KDIGO**：CKD 2024、AKI 2012（页面 + PDF/摘要）
- **ACR**：Appropriateness Criteria 总索引

### 扩展批次新增（2026-06-22 索引派生 + API）

| 来源 | 新增内容 | 约条数 |
|---|---|---:|
| **ACR** | Appropriateness Criteria **全部** Narrative + 风湿 CPG 页 + CMS 4 条 | 278 + 16 |
| **IDSA** | A–Z Practice Guidelines 全文页 | ~100 |
| **RCOG** | Green-top 指南全文页 | 71 |
| **EULAR** | Annals Rheum Dis 推荐（含 PMC 回退） | 42 |
| **ATS** | site.thoracic.org 声明与 implementation tools | 23 |
| **ESMO** | Nuxt sitemap API 临床指南页 | 24 |
| **MSD Manual** | Health Topics 专科目录 + 首页深链 | 31 |
| **ASH** | CPG hub **10** + topic 子页 **25** | 35 |
| **Endocrine Society** | 专科分类 **12** + PubMed 指南 **51** | 63 |
| **ACOG** | sitemap：PB/CO/Practice Advisory 等 | **337** |
| **AAN** | PubMed Corporate Author 指南 | **88** |
| **ACC/AHA** | PubMed 2010–2026 + PMC 映射 | **246** |
| **ESC** | Europe PMC *Eur Heart J*「ESC Guidelines」 | **150** |
| **ASH Blood Advances** | Europe PMC ASH 指南 | **120** |
| **SSC/SCCM** | SCCM hub **38** + Europe PMC **80** + PubMed **76** | 194 |
| **GOLD / GINA** | COPD 2026、哮喘 2024 PDF | 3 |
| **ACC/AHA / ESC** | ACS PMC 全文、心衰 PMC 全文 | 2 |
| **CDC** | 脓毒症、PrEP/HIV 子链、STI 等 | ~15 |
| **USPSTF** | A/B 总索引 + 10 条 hand-curated 筛查 | 11 |
| **NICE** | 公开 HTML 推荐章节 **126** + 首批 hand-curated **7** | **133**（manifest **132 ok** / 1 error） |
| **NICE Syndication API** | 凭据已注册；全库 bulk 待 **API-Key 激活** | 见 §NICE |
| **PubMed / Europe PMC** | 指南 metadata 索引（API，非 HTML 镜像） | 1320 |
| **MedlinePlus** | XML 批量 + 主题 chunks 解析 | 2029 |

## 索引页扩展机制

推荐完整重跑顺序：

```bash
# 1) API 索引 + MedlinePlus 解析 + ESMO seed
python scripts/run_cpg_api_pipeline.py --download-esmo

# 2) 从已下载 HTML 索引派生子链 + 合并 seed
python scripts/expand_open_cpg_seed.py

# 3) 增量下载（跳过已有 raw）
python scripts/download_open_cpg.py --timeout 90 --skip-existing --insecure --sleep 0.35
```

`expand_open_cpg_seed.py` 合并来源：

- `open_cpg_seed_expansion.json`（hand-curated）
- `open_poc_seed.json`（StatPearls/MSD/AAFP/MedlinePlus 索引）
- `open_cpg_api_seed.json`（ESMO sitemap，由 `build_esmo_api_seed.py` 生成）
- `open_cpg_nice_public_seed.json`（NICE 公开 Recommendations 章节，由 `extract_nice_public_chapters.py` 生成）
- `open_cpg_nice_seed.json`（NICE Syndication API 索引派生，由 `build_nice_api_seed.py` 生成；需 API-Key）
- 本地 HTML 索引派生（CDC HIV、ACR AC、IDSA A–Z 等）
- 在线抓取（RCOG green-top、ATS statements hub、MSD health-topics）
- **ACOG sitemap**（`sitemap.xml` → PB/CO 等 337 篇）
- **PubMed Corporate Author**（Endocrine 51、AAN 88、**ACC/AHA 246**、**SSC 76**）
- **Europe PMC**（**ESC 150**、**ASH Blood Advances 120**、**SSC 80**）
- **SCCM 官网 hub**（**38** 篇指南页）
- **ASH hub 深链**（VTE/SCD 等 25 个 topic 子页）

| 索引页 / 数据源 | 派生内容 | 条数 |
|---|---|---:|
| ACR Appropriateness | 全部 Narrative | 278 |
| ACOG sitemap | PB/CO/Advisory/Consensus 等 | 337 |
| IDSA A–Z | Practice Guideline 页 | ~100 |
| ACC/AHA PubMed | Corporate Author 2010–2026 | 246 |
| ESC Europe PMC | Eur Heart J ESC Guidelines | 150 |
| ASH Blood Advances | Europe PMC | 120 |
| AAN PubMed | Corporate Author 指南 | 88 |
| SSC Europe PMC | Crit Care Med | 80 |
| SSC PubMed | Surviving Sepsis / SCCM | 76 |
| SCCM hub | 官网子页 | 38 |
| RCOG Green-top | 在线清单 | 71 |
| Endocrine PubMed | Corporate Author 指南 | 51 |
| EULAR Recommendations | BMJ 链接（失败时 PMC 回退） | 42 |
| MSD Health Topics | 专科目录 | 31 |
| ASH hub 子页 | VTE/SCD/ALL 等 topic | 25 |
| ESMO Sitemap | 临床 CPG 页（API） | 24 |
| **NICE 公开章节** | NG/CG/QS Recommendations 等（`nice_pub__*`） | **126** |
| ATS Statements Hub | implementation tools | 23 |
| ACR Rheumatology | 风湿 CPG 页 | 16 |
| Endocrine Society | 专科分类 | 12 |
| ASH Guidelines | CPG hub | 10 |
| CDC HIV Index | 段落级子链 | 8 |

注意：

- 派生 ID 前缀：`acr_ac__`、`acog_child__`、`aan_pm__`、`endocrine_pm__`、`ash_sub__` 等；重复运行会先剥离旧派生项再重建。
- RCOG / AAFP 需 `--insecure`（本环境 TLS 链问题）。
- **ACOG** 页面为 SPA，但 sitemap URL 可稳定镜像摘要/正文片段。
- **AAN** 官网 `GetGuidelineContent` 对自动化 403；本批改用 **PubMed metadata**。
- **Endocrine** 分类页为动态列表；单篇指南经 **PubMed Corporate Author** 派生；OUP/JCEM 直链易 **403**。
- `download_open_cpg.py` 写入 manifest 时会**按 id 合并**历史条目，增量 run 不会覆盖全量。

## API 抓取管道（2026-06-22）

一键运行（推荐）：

```bash
python scripts/run_cpg_api_pipeline.py --download-esmo
python scripts/run_cpg_api_pipeline.py --download-esmo --pubmed-max 1000 --epmc-max 5000
```

分步脚本：

| 脚本 | 数据源 | 产物 |
|---|---|---|
| `build_pubmed_guideline_index.py` | [PubMed E-utilities](https://eutils.ncbi.nlm.nih.gov/) | `data/cpg/api/pubmed_guideline_index_latest.jsonl` |
| `build_europepmc_guideline_index.py` | [Europe PMC REST](https://europepmc.org/RestfulWebService) | `data/cpg/api/europepmc_guideline_index_latest.jsonl` |
| `build_esmo_api_seed.py` | ESMO Nuxt sitemap | `data/cpg/open_cpg_api_seed.json` → 合并进 seed |
| `parse_medlineplus_topics.py` | 已下载 MedlinePlus XML | `data/poc/medlineplus/processed/medlineplus_topic_chunks_latest.jsonl` |
| `fetch_nice_syndication_index.py` | NICE Syndication API | `data/cpg/api/nice_syndication_index_latest.jsonl` |
| `build_nice_api_seed.py` | 上项索引 | `data/cpg/open_cpg_nice_seed.json` |
| `crawl_nice_published_ddx.py` | NICE 已发布列表 + **侧边栏全章节**（**canonical，无手工表**） | `data/cpg/open_cpg_nice_ddx_seed.json` |
| `audit_manifest_bot_gate.py` | manifest PubMed/PMC 浏览器校验页 | `data/cpg/eval/manifest_bot_gate_report.json`（§1.5.3.2） |
| `build_manifest_cpg_chunks.py` | manifest HTML/text 切 chunk | `data/cpg/processed/manifest_cpg_chunks.jsonl` |
| `build_cpg_chunks.py` | 多源合并 useful chunks | `data/cpg/processed/cpg_chunks.jsonl` |
| `extract_nice_public_chapters.py` | NICE 公开 HTML（**legacy curated**，非自动化路径） | `data/cpg/open_cpg_nice_public_seed.json` |
| `download_nice_syndication.py` | Syndication API 正文 | `data/cpg/raw/nice/`、`text/nice/` |

环境变量（可选）：

- `NCBI_API_KEY` / `PUBMED_EMAIL`：提高 PubMed 速率上限
- `NICE_API_KEY`：NICE Syndication **API-Key**（HTTP 头 `API-Key`；**不是**注册 JSON 里的 `client_id`）
- `NICE_CREDENTIALS_JSON`：注册文件路径（默认 `/data3/wanghongyi/Shanghai Jiao Tong University.json`）；可在 JSON 根或 `registrations.production` 下添加 `"api_key": "..."` 字段

### NICE Syndication 凭据与批量下载（2026-06-22）

**凭据文件**（勿提交 git）：`/data3/wanghongyi/Shanghai Jiao Tong University.json`

| 字段 | 说明 |
|---|---|
| `registrations.production.client_id` / `client_secret` | 应用注册元数据（OAuth `client_secret_post`） |
| **`api_key`**（待填入） | Syndication 实际访问密钥，来自 [api.nice.org.uk/account](https://api.nice.org.uk/account) |

**重要**：NICE Syndication 使用静态 **`API-Key` HTTP 头**，不是 OAuth bearer。注册 JSON 中的 `client_id`/`client_secret` **不能**直接作为 API-Key（实测 401）。流程：

1. 在 NICE 账户页接受 licence 条款；
2. 复制账户页显示的 **API key**；
3. 任选其一：`export NICE_API_KEY=...`，或在凭据 JSON 增加 `"api_key": "..."`；
4. 验证：`python scripts/fetch_nice_syndication_index.py --verify-only`；
5. 全库索引：`python scripts/fetch_nice_syndication_index.py --max-depth 3`；
6. 生成 seed + 下载：`python scripts/run_cpg_api_pipeline.py --skip-pubmed --skip-europepmc --skip-esmo --skip-medlineplus --download-nice`。

**NICE 公开 HTML（canonical 自动化路径，无需 API-Key）**：

设计原则见 [`CPG_RAG_EXTRACTION.md`](CPG_RAG_EXTRACTION.md) §1.3：**不依赖** `extract_nice_public_chapters.py` 内 curated 表或 `open_cpg_seed_expansion.json` 中的 NICE 条目。

```bash
# 从 published 列表解析 NG/CG/DG/SC，stacked-nav 侧边栏全章节（排除 research/committee/update）
python scripts/crawl_nice_published_ddx.py --use-cache-list --all-sidebar --download

python scripts/expand_open_cpg_seed.py
python scripts/download_open_cpg.py --timeout 90 --skip-existing --insecure --sleep 0.35
```

当前 **`nice_ddx__*` 1320 章**（303 指南，manifest **1320 ok**）；`nice_pub__*`（126 条 curated）为历史语料，新 run 以 `nice_ddx__*` 为准。

API 索引层为**发现用元数据**（PMID/DOI/PMC 链接）；全文镜像仍走 `download_open_cpg.py` 或 Europe PMC→PMC 回退（见 EULAR 429 处理）。

## 重跑方式

```bash
python scripts/download_open_cpg.py
python scripts/download_open_cpg.py --limit 5
python scripts/download_open_cpg.py --sleep 2 --timeout 60
python scripts/download_open_cpg.py --timeout 90 --skip-existing --insecure --sleep 0.35
```

脚本行为：

- 读取 `data/cpg/open_cpg_seed.json`。
- 对每个主条目和 `attachments` **显式**下载，不做无边界爬虫。
- 保存原始响应到 `data/cpg/raw/<source>/`。
- 对 HTML 抽取可见文本到 `data/cpg/text/<source>/`。
- 对 `public_pdf` 校验 payload 以 `%PDF` 开头；若已安装 `pypdf`，同步生成 PDF 文本层。
- 生成带时间戳的 `summary_*.json` 与 `manifest_*.jsonl`；`manifest_latest.jsonl` **合并**历史条目（按 `id` 去重）。

## 新增来源规则

优先编辑 `data/cpg/open_cpg_seed_expansion.json`，再运行 `expand_open_cpg_seed.py`。字段示例：

```json
{
  "id": "source_topic_year",
  "source": "SOURCE",
  "title": "Human readable title",
  "url": "https://official.example/guideline",
  "clinical_area": ["domain", "syndrome"],
  "access": "public_html",
  "parent_id": "optional_index_id",
  "attachments": [
    {
      "id": "full_pdf",
      "title": "Full guideline PDF",
      "url": "https://official.example/full.pdf",
      "access": "public_pdf"
    }
  ]
}
```

**可加入**：官方公开网页/PDF、政府/学会公开资料、PMC 等明确开放的 NIH 镜像。

**不可加入**：需登录或订阅的全文、tokenized session URL、版权不明的第三方转载 PDF、用个人账号批量爬取的受限内容。

## NCCN 受限镜像（Navigator + 全库缺口，已完成）

[NCCN Guidelines Navigator](https://www.nccn.org/guidelines/nccn-guidelines-navigator) **41 份** Navigator 指南 + 全库 category_1–4 相对 Navigator **额外 51 份**（如 Melanoma、CML、Pain、Screening 等），合计 **92 份** 主 PDF，已通过注册账号登录后批量下载（`physician_gls/pdf/*.pdf`，排除 Evidence Blocks / Framework 变体）。

| 指标 | 数值 |
|---|---:|
| 来源 | Navigator 页 + `category_1`–`category_4` 全库 |
| 下载脚本 | `scripts/download_nccn_navigator_pdfs.py` |
| 产物目录 | `data/cpg/restricted/nccn/raw/`、`text/` |
| manifest | `data/cpg/restricted/nccn/manifest_latest.jsonl`（合并两次 run，92 条） |
| 成功 | **92 / 92** |
| 总体积 | ~171 MB |

重跑方式（**凭证仅通过环境变量传入，勿写入仓库**）：

```bash
export NCCN_USERNAME='your@email'
export NCCN_PASSWORD='...'
# Navigator 41 条
python scripts/download_nccn_navigator_pdfs.py --scope navigator --sleep 0.8
# 全库中 Navigator 未覆盖的条目（增量）
python scripts/download_nccn_navigator_pdfs.py --scope missing-full --skip-existing --sleep 0.8
# 全库 ~92 条（从头）
python scripts/download_nccn_navigator_pdfs.py --scope full --skip-existing --sleep 0.8
```

`--skip-existing` 时 `manifest_latest.jsonl` 会与历史条目**合并**（按 `id` 去重），避免增量 run 覆盖 Navigator 批次。

**合规提醒**：

- 内容受 [NCCN EULA](https://www.nccn.org/home/end-user-license-agreement) 约束，仅限个人注册账号范围内的查看/研究使用，**不得再分发或用于多人 RAG 服务**。
- `data/cpg/restricted/` 已加入 `.gitignore`，PDF 不会进入 git。
- 若需 API/企业集成，仍应走 [NCCN Developer API](https://www.nccn.org/developer-api)（见 `scripts/download_nccn_licensed.py`）。

### 与开放 CPG 镜像的关系

- 开放 CPG（CDC/NICE/WHO 等）仍在 `data/cpg/raw/`，manifest 在 `data/cpg/manifest_latest.jsonl`。
- NCCN 为**独立受限层**，下游索引时必须标注 `license_note: restricted_login_pdf`，并与开放语料分层存储。

## §2 专科协会指南 — 入库状态（2026-06-22 最新）

对照上文「### 2. 专科协会指南」。图例：**✅ 已较完整**｜**⚠️ 部分**｜**❌ 未入库**｜**🔐 需注册/API**

| 专科 | 来源 | 状态 | 已入库 | 剩余缺口 |
|---|---|:---:|---|---|
| **心血管** | ACC/AHA | ✅ | **248** 条（246 PubMed/PMC + ACS 2025 全文） | JACC 非 OA 全文仍缺 |
| | ESC | ✅ | **153** 条（150 *Eur Heart J* PMC + 心衰索引/全文） | escardio.org SPA 子页 |
| **感染病** | CDC / WHO | ✅ | ~15 CDC + 3 WHO（含 PDF） | 部分 stacks.cdc.gov 403 |
| | IDSA | ✅ | **~105** 条（A–Z 全文页 + CAP/C.diff/UTI/SST/AMR） | 个别页面更新滞后 |
| **肿瘤** | NCCN | ✅🔐 | **92** PDF（受限层） | Developer API AccessKey |
| | ESMO | ⚠️ | 索引 + **24** sitemap 页 | topic 子页、PDF 未全量 |
| | ASCO | ❌ | — | 未加 seed |
| **肾脏** | KDIGO | ✅ | CKD/AKI 页 + PDF | — |
| **呼吸** | GOLD / GINA | ✅ | 2026/2024 PDF | — |
| | ATS | ⚠️ | 索引 + **23** 声明/tools | ERS 未加；ATS/ERS 联合全文不全 |
| **内分泌** | ADA | ⚠️ | Standards of Care 索引 | 全卷 PDF 需订阅 |
| | Endocrine Society | ✅ | 索引 + **12** 专科分类 + **51** PubMed 指南 | OUP/JCEM 403 |
| **风湿** | ACR | ✅ | **300** 条（278 AC Narrative + 16 风湿 + 索引） | — |
| | EULAR | ✅ | **43** 条（BMJ/PMC 镜像） | 429 时需 PMC 回退 |
| **神经** | AAN | ⚠️ | 索引 + **88** PubMed 指南 metadata | 官网全文 403 |
| **妇产** | ACOG | ✅ | sitemap **337** 篇 PB/CO/Advisory 等 | 部分为摘要层 |
| | RCOG | ✅ | 索引 + **71** Green-top 页 | — |
| **放射** | ACR AC | ✅ | 见 ACR 300 条 | — |
| **血液** | ASH | ✅ | hub **35** + **120** Blood Advances PMC | ashpublications.org 403 时走 PMC |
| | BSH | ❌ | — | 未加 seed |
| **急危重症** | SSC/SCCM | ✅ | **196** 条（38 SCCM 页 + 80/76 PMC/PubMed + Sepsis 2026） | — |
| **预防** | USPSTF | ⚠️ | 总索引 + 10 条 hand-curated | 动态总表未全量 |
| **综合** | NICE | ✅/⚠️ | **133** 条（**126** 公开 Recommendations 章节 + 7 首批）；Syndication 全库 🔐 待 API-Key |

### §2 汇总

| 类别 | 来源 |
|---|---|
| **✅ 较完整** | CDC、WHO、KDIGO、GOLD、GINA、**IDSA**、**ACR**、**ACR AC**、**RCOG**、**EULAR**、**ACOG**、**ACC/AHA**、**ESC**、**ASH**、**SSC/SCCM**、**NICE**（公开 HTML 章节）、NCCN（受限） |
| **⚠️ 部分** | ESMO、ATS、ADA、Endocrine、AAN、USPSTF、**NICE Syndication 全库**（凭据已注册，待 API-Key 激活） |
| **❌ 未入库** | **ASCO**、**BSH**、**ERS** |
| **🔐 需 API key** | NCCN Developer API、NICE Syndication API |

## §3 开放临床综述 / 点-of-care — 入库状态（2026-06-22 最新）

| 来源 | 状态 | 已入库 | 剩余缺口 |
|---|:---:|---|---|
| **MedlinePlus** | ✅ | XML 3 文件 + **2029** 主题 chunks | 症状→疾病关系结构化可再深化 |
| **PubMed / Europe PMC** | ✅ | API 索引 **1320** 条 metadata | 可按 PMC OA 选择性全文入库 |
| **MSD Manual** | ⚠️ | 索引 + **31** 专科/深链页 | 数千疾病条目未逐条 |
| **ESMO** | ⚠️ | 24 页（见 §2） | SPA 子 topic |
| **StatPearls** | ⚠️ | CPG 层 Bookshelf 索引；语料在 `data/corpus/statpearls/`（367k 段） | 未并入 `data/cpg/manifest` |
| **AAFP** | ⚠️ | Clinical Recommendations 索引（`--insecure`） | SPA，单篇未展开 |
| **BMJ/NEJM/JAMA OA** | ❌ | — | 需逐篇许可 |

### §3 汇总

| 类别 | 说明 |
|---|---|
| **✅ 已批量** | MedlinePlus chunks、PubMed/Europe PMC 指南索引 |
| **⚠️ 部分** | MSD、StatPearls（独立 corpus）、AAFP、ESMO |
| **❌ 未开始** | BMJ/NEJM/JAMA 开放文章逐篇索引 |

### 点-of-care 重跑

```bash
python scripts/download_medlineplus_bulk.py
python scripts/parse_medlineplus_topics.py
python scripts/run_cpg_api_pipeline.py --skip-esmo --skip-nice
python scripts/download_open_cpg.py --skip-existing --insecure
```

## 已知抓取限制

| 来源 | 现象 | 处理 |
|---|---|---|
| **stacks.cdc.gov** | 部分环境 403；本次批次多数 HTML 元数据页可下 | 失败时改用 CDC/MMWR 或 hivnexus 公开 PDF/HTM |
| **clinicalinfo.hiv.gov** | 自动化请求易 403 | 保留 CDC HIV 索引中的 MMWR/stacks 可访问子链 |
| **JACC / AHA Journals / diabetesjournals** | 403 | ACS 改用 PMC 全文；ADA 用 professional.diabetes.org 索引 |
| **RCOG / AAFP** | 本环境 TLS 链校验失败 | 使用 `download_open_cpg.py --insecure` |
| **ard.bmj.com（EULAR）** | 批量抓取易 **429 Too Many Requests** | 失败条目改抓 **PMC/PubMed**（Europe PMC API 解析） |
| **academic.oup.com（Endocrine/JCEM）** | 自动化请求 **403** | 改用 PubMed metadata；有 PMC 时再拉全文 |
| **aan.com GetGuidelineContent** | 自动化 **403** / 空壳页 | 改用 PubMed Corporate Author 索引 |
| **acc.org / escardio.org** | 指南列表为 SPA | ACC 走 PubMed；ESC 走 Europe PMC *Eur Heart J* |
| **acog.org SPA** | 列表页无静态子链 | 改用 **sitemap.xml** 派生 337 篇 |
| **ashpublications.org** | 部分 403 | 优先 Europe PMC *Blood Advances* PMC 全文 |
| **ADA 全卷 PDF** | 官方 CDN 签名 URL 会过期 | 仅镜像索引页；全文 PDF 需机构订阅或逐篇开放 PDF |
| **USPSTF 总表** | 前端动态加载，静态 HTML 几乎无子链 | 已 hand-curated 10 条高频 recommendation URL |

## 商业与受限源（DynaMed / UpToDate / BMJ）

不应直接批量抓取网页。可行路径：机构合同 → 供应商 API / bulk export / FHIR 嵌入 → 明确 RAG 与再分发许可。无授权时继续使用本仓库已镜像的开放 CPG + StatPearls + **已购 Merck 19e PDF**（`data/corpus/merck/`）+ HPO/MONDO/PrimeKG（见上文「对你这个项目的建议组合」）。

## 下游使用建议

当前仓库含**三层可审计语料**（开放 HTML/PDF 镜像、API 发现索引、POC chunks），还不等于可直接驱动 `mandatory_coverage` 的 curated KB。建议：

1. **全文层**：过滤 `data/cpg/manifest_latest.jsonl` 中 `status == "ok"`（当前 **2037** 条，含 NICE **132**）。
2. **发现层**：用 `data/cpg/api/pubmed_guideline_index_latest.jsonl` / `europepmc_guideline_index_latest.jsonl` 按专科/期刊补漏，优先 `is_open_access == "Y"` 或含 `pmcid` 的条目。
3. **POC 层**：`data/poc/medlineplus/processed/` 与 `data/corpus/statpearls/` **独立 corpus**（标注不同 `license_note` / `source_tier`）；**勿**默认并入 `cpg_chunks`（MedlinePlus 评测 Recall@10 −2%，见 §1.5.3.1）。
4. **DDx 症状入口层**：`data/cpg/processed/cpg_chunks.jsonl`（WikEM + PMC-OA + manifest + Merck）；manifest 子集见 `manifest_cpg_chunks.jsonl`。
5. 对 `text_path` 非空内容做章节切分，优先 recommendation / differential / red flags / investigations；**先**跑 `python scripts/audit_manifest_bot_gate.py` 识别 NCBI 浏览器校验页（§1.5.3.2），chunk 管道会自动剔除。
6. 写入/刷新 `cpg_chunks.jsonl`：`python scripts/build_manifest_cpg_chunks.py --useful-only` → `python scripts/build_cpg_chunks.py --useful-only`。
7. NCCN 受限 PDF 单独标注 `restricted_login_pdf`，不与开放语料混用。
8. 索引：`python scripts/build_tfidf_index.py` / `build_rag_index.py`（已含 Merck corpus；`cpg_chunks` 合入见 IMP-31）。

**RAG 提取方案**（PDF/HTML 解析、切分、索引、结构化抽取）见 [`CPG_RAG_EXTRACTION.md`](CPG_RAG_EXTRACTION.md)（§1.3 自动化路径、§1.4 数据结构调研结论）。

**分支知识自动化实施入档**（MECE / mandatory_coverage / 与 CPG 集成 Phase 排期）见 [`BRANCH_KNOWLEDGE_IMPLEMENTATION_PLAN.md`](BRANCH_KNOWLEDGE_IMPLEMENTATION_PLAN.md)。

## 后续扩展建议（未实施）

| 优先级 | 任务 | 脚本 / 条件 |
|---|---|---|
| — | ~~Merck Manual 19e PDF 切分入库~~ | **已完成**：`build_merck_manual_corpus.py` → `data/corpus/merck/`（§1.9） |
| 高 | NICE Syndication 全库 bulk | 凭据：`/data3/wanghongyi/Shanghai Jiao Tong University.json`；激活后 `NICE_API_KEY` + `fetch_nice_syndication_index.py` |
| 高 | Europe PMC OA 条目选择性 PMC 全文入库 | 从 `europepmc_guideline_index_latest.jsonl` 筛 `is_open_access` |
| 高 | **198 篇 bot_blocked 补拉全文** | 清单：`manifest_bot_gate_report.json`；Europe PMC / BioC / 协会 publisher（**非**重跑同 PubMed URL） |
| 中 | MedlinePlus 并入 `cpg_chunks` | **禁止**（评测 Recall@10 −2%，0/50 仅 MedlinePlus 命中；保留 POC 层；ablation 才 `--include-medlineplus`） |
| 中 | PubMed 摘要层并入 RAG | **禁止**（`content_tier=abstract_only` 已由 `--useful-only` 剔除；全文缺 DDx/推荐块，Europe PMC 0% PMCID） |
| 中 | ASCO / BSH / ERS seed + 索引派生 | 编辑 `open_cpg_seed_expansion.json` |
| 低 | ADA / AAFP SPA 子页 | 需 headless 或官方 API |
| 低 | BMJ/NEJM/JAMA 开放文章索引 | 逐篇许可 + metadata 索引 |
| 低 | StatPearls 与 `data/cpg/manifest` 统一 | 保持 `data/corpus/statpearls/` 分层或写 cross-ref manifest |

针对「综合征→L1 分支防漏」目标，PMC-OA **不应整库抓取**（约 300 万+ OA 篇，噪声极大），而应抓取**定向筛选后的「症状入口 + DDx 组织」子集**。下面分「有效数据是什么」和「从什么入口抓」两层说明。

---

## PMC-OA 抓取指引

> **BioC API 文档**：[BioC API for PMC Open Access](https://www.ncbi.nlm.nih.gov/research/bionlp/APIs/BioC-PMC/)（NLM BioNLP；仅 **PMC OA 子集** + Author Manuscript Collection）。与 Europe PMC `fullTextXML` 同为结构化全文入口，passage 级 `section_type` / `type`（`title_1`、`paragraph` 等）便于 IMP-50 chunk 切分。Bulk：[BioC-PMC FTP](https://ftp.ncbi.nlm.nih.gov/pub/wilbur/BioC-PMC)。

---

## 一、需要抓取的有效数据是什么？

### 1. 文章级：只收「综合征/症状入口型」OA 综述

| 维度 | 要收 | 不要收 |
|---|---|---|
| **组织方式** | 标题/结构以**症状/综合征 S** 为起点，正文含 DDx/评估/红旗段 | 以**已确诊疾病 X** 为中心的管理/治疗指南（ACC/AHA、ESC 等，**已在 manifest**） |
| **文献类型** | Review、Systematic Review、Clinical Education、Continuing Medical Education | 原始研究、病例报告、方法学、meta 方法论文 |
| **标题模式** | `"approach to"` / `"differential diagnosis of"` / `"evaluation of"` / `"causes of"` / `"workup of"` / `"clinical approach"` | 单病种治疗路径、手术/介入共识 |
| **许可** | **PMC Open Access 子集**（`isOpenAccess=Y` 且可拉 JATS/XML 全文） | 仅有 PubMed 摘要、无 PMCID 的条目 |
| **语言** | 英文临床综述 | 非临床、兽医、纯基础 |

这类文章的结构最接近 CKS/AAFP/BMJ-BP 的「Approach to the patient with X」，是 IMP-50 的核心目标。

### 2. 全文内：只收对 BranchCreator 有用的语义块

从 JATS XML（优先）或去噪 HTML 中切出：

| 语义块 | 对应下游字段 | 优先级 |
|---|---|---|
| **Differential diagnosis / Causes / Etiology** | `mandatory_coverage` 候选域、`candidate_entities` | **P0** |
| **Red flags / Can't miss / Urgent / Emergency referral** | `cant_miss` | **P0** |
| **Initial evaluation / Diagnostic approach / Workup / Recommended tests** | 检查路径、实体富集 | **P1** |
| **Clinical presentation / History / Physical exam** | 证据对齐、query 扩展 | P2 |
| **Management / Treatment / Prognosis** | 一般不用于 L1 轴划分 | **排除或降权** |
| **References / Methods / Supplementary** | 噪声 | **排除** |

每块 chunk 应带：

```json
{
  "entry_type": "syndrome_entry",
  "chunk_type": "differential | red_flag | evaluation | background",
  "content_tier": "full_text",
  "section_path": "Approach to Hypercalcemia > Differential Diagnosis",
  "syndrome_anchor": "hypercalcemia",
  "license_note": "pmc_oa_cc_by",
  "pmid": "...",
  "pmcid": "PMC...",
  "citation_span": "..."
}
```

### 3. 索引层：必须存的元数据字段

`pmc_oa_ddx_index.jsonl`（发现层，IMP-50 交付物）建议字段：

| 字段 | 用途 |
|---|---|
| `pmid`, `pmcid`, `doi` | 去重、溯源 |
| `title` | 检索 + 从标题抽 `syndrome_anchor` |
| `journal`, `pub_year` | 专科过滤、时效 |
| `pub_type` | 确认 Review 等 |
| `is_open_access`, `license` | **合规门**（CC BY / CC BY-NC 等） |
| `query_matched` | 记录命中哪条发现 query |
| `syndrome_keywords` | 从标题解析出的根节点候选 |
| `has_pmc_fulltext` | 是否可拉 XML |
| `url` | `https://pmc.ncbi.nlm.nih.gov/articles/{PMCID}/` |

**不要**在发现层就抓全文；先筛 metadata，再对 `has_pmc_fulltext=true` 批量拉 XML。

---

## 二、应从什么入口抓取？

建议 **两阶段管道**：发现（Discovery）→ 全文（Full-text），与现有 `build_pubmed_guideline_index.py` / `build_europepmc_guideline_index.py` 模式一致，但 **query 不同**。

```
┌─ 阶段 A：发现（metadata index）────────────────────────────┐
│  PubMed E-utilities esearch  ──┐                            │
│  Europe PMC REST search       ──┼→ pmc_oa_ddx_index.jsonl  │
│  （同一套 DDx query，结果合并去重）│                          │
└────────────────────────────────┘                            │
                              ↓ 筛 isOpenAccess=Y + pmcid    │
┌─ 阶段 B：全文（structured text）────────────────────────────┐
│  Europe PMC fullTextXML（JATS，章节树清晰）                  │
│  或 NCBI BioC API（passage 级，含 license / section_type）   │
│  或 NCBI efetch db=pmc（JATS 备选）                         │
│  → 按 <sec> 或 BioC passage 切 chunk → syndrome_entry 索引  │
└─────────────────────────────────────────────────────────────┘
```

### 入口 1：PubMed E-utilities（发现层，主入口之一）

- **URL**：`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi`
- **已有脚本模式**：`scripts/build_pubmed_guideline_index.py`（当前 query 是 `Practice Guideline[PT]`，需**另建** DDx 专用脚本）
- **推荐 query 模板**（每条单独跑，合并去重）：

```text
("approach to"[Title] OR "differential diagnosis of"[Title] OR "evaluation of"[Title] OR "causes of"[Title] OR "workup of"[Title])
AND (Review[PT] OR "Systematic Review"[PT])
AND ("open access"[Filter] OR free full text[sb])
AND english[lang]
```

- **后续**：`esummary` 取 title/journal/pubtype；用 `elink dbfrom=pubmed db=pmc` 拿 PMCID
- **环境**：`NCBI_API_KEY` + `PUBMED_EMAIL`（项目已支持）

### 入口 2：Europe PMC REST Search（发现层，主入口之二）

- **URL**：`https://www.ebi.ac.uk/europepmc/webservices/rest/search`
- **已有脚本模式**：`scripts/build_europepmc_guideline_index.py`
- **推荐 query**（Europe PMC 语法）：

```text
(TITLE:"approach to" OR TITLE:"differential diagnosis" OR TITLE:"evaluation of" OR TITLE:"causes of")
AND (PUB_TYPE:"review" OR PUB_TYPE:"systematic review")
AND OPEN_ACCESS:Y
AND HAS_FT:Y
AND SRC:MED
```

- **优势**：一次返回 `pmid`、`pmcid`、`isOpenAccess`、`journalTitle`，比 PubMed 少一步 elink
- **cursorMark 分页**：现有脚本已支持

### 入口 3：Europe PMC fullTextXML（全文层，JATS 首选）

- **URL**：`https://www.ebi.ac.uk/europepmc/webservices/rest/{PMCID}/fullTextXML`
- **为何首选（JATS）**：返回 **JATS/NLM XML**，`<sec><title>` 可直接映射 `section_path`，章节树最完整
- **限制**：仅 **Open Access 子集**可返回 XML；非 OA 只给 metadata

### 入口 4：NCBI BioC API for PMC OA（全文层，**passage 切分友好**）

- **文档**：[BioC API for PMC Open Access](https://www.ncbi.nlm.nih.gov/research/bionlp/APIs/BioC-PMC/)
- **单篇 URL 模板**：

```text
https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_{json|xml}/{PMID|PMCID}/{unicode|ascii}
```

- **示例**（JSON + PMCID）：

```text
https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/PMC1790863/unicode
```

- **响应结构**：`BioCCollection → documents[] → passages[]`；每 passage 含 `text`、`infons.type`（`title_1` / `paragraph` / `table` …）、`infons.section_type`；document 级 `infons.license`（如 `CC BY`、`CC BY-NC-ND`）——**合规门可直接读 license 字段**。
- **适用场景**：
  - 与 Europe PMC XML **二选一或互为校验**（同一 PMC OA 子集）；
  - 希望 **passage 级**批量切 chunk、避免 HTML 导航噪声；
  - 有 API key 时仍无需 key（公开 REST）；遵守 NCBI 频率礼貌即可。
- **Bulk**：`ftp://ftp.ncbi.nlm.nih.gov/pub/wilbur/BioC-PMC`（规模化二期；起步仍建议先 discovery index 再按 PMCID 拉单篇）。
- **注意**：BioC 与 JATS 一样，**仅覆盖 PMC OA / Author Manuscript 子集**（见 [OA file list](https://www.ncbi.nlm.nih.gov/pmc/tools/openftlist/)）；非 OA 条目须跳过或仅保留 metadata。

### 入口 5：NCBI efetch db=pmc（全文层，JATS 备选）

- **URL**：`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id=PMCxxxxx&retmode=xml`
- 与 Europe PMC XML 格式基本一致；适合已有 `NCBI_API_KEY` 的批量拉取

### 入口 6：Europe PMC OA 批量（离线大规模，非首选起步）

| 方式 | 入口 | 适用 |
|---|---|---|
| **FTP 批量** | `https://europepmc.org/downloads`（OA subset，JATS+PDF，周更） | 离线建全库后再本地筛 DDx 标题 |
| **OAI-PMH** | `https://europepmc.org/oai.cgi?verb=ListRecords&metadataPrefix=pmc&set=pmc-open` | 合规 bulk harvest metadata+全文 |

**不建议起步就用**：300 万+ 篇全量下载后再筛，成本高；应先走入口 1+2 定向发现（预计数千～数万篇），再对命中条目拉 XML。

### 入口 7：不要用或仅作兜底

| 入口 | 原因 |
|---|---|
| PubMed 摘要页 HTML（`pubmed.ncbi.nlm.nih.gov/{pmid}/`） | 无 DDx 正文，项目 manifest 里已有大量 `public_html_index` 摘要层——**正是 §1.5 指出的结构缺陷** |
| `download_open_cpg.py` 直接抓 PMC HTML 页 | 可用但噪声大（PMC 导航壳）；JATS 更优 |
| 全库 OA FTP 无 query 过滤 | 噪声比、存储成本不可接受 |

---

## 三、与现有 CPG 管道的关系

当前仓库里 PMC 相关数据**有两条线**，不要混淆：

| 已有 | 用途 | IMP-50 新线 |
|---|---|---|
| `europepmc_guideline_index`（`PRACTICE GUIDELINE[PT]`） | **疾病管理型** CPG 发现 | 不重复 |
| manifest 中 `acc_aha_pm__` / `esc_epmc__` 等 | 专科**指南**全文镜像 | 不重复 |
| **新建** `pmc_oa_ddx_index.jsonl` | — | **症状入口型 DDx 综述**发现 |
| chunk 进 RAG 时 `entry_type=syndrome_entry` | — | 与 `chunk_type=differential` 一起 boost |

现有 `build_europepmc_guideline_index.py` 可**复用框架**（cursor 分页、jsonl 输出），只需换 query 和输出文件名；全文拉取是**新增步骤**（当前脚本只做 metadata）。

---

## 四、推荐抓取优先级（实操顺序）

1. **Europe PMC REST** + 上述 DDx query → `pmc_oa_ddx_index.jsonl`（最快验证规模与 OA 比例）
2. 对 index 中 `pmcid != null && is_open_access == Y` 批量拉全文：**Europe PMC `fullTextXML`** 或 **BioC API `BioC_json/{PMCID}/unicode`**（推荐二选一；BioC 便于 passage 切分 + 读 `license`）
3. 按 JATS `<sec>` 或 BioC `passages[].infons` 切 chunk（`Differential Diagnosis` / `Red Flags` / `Evaluation` 等）
4. 写入统一 schema（`entry_type=syndrome_entry`，`content_tier=full_text`），并入 TF-IDF/FAISS 索引
5. PubMed E-utilities 作**补漏**（Europe PMC 未收录的 OA 条目）

**合规要点**：只入库 PMC **Open Access 子集**；每条 chunk 保留 `license`/`license_note`；CC BY-NC 条目若用于 RAG 检索一般可接受，但衍生结构化 KB 发布前需按许可标注。

---

## 五、一句话总结

**有效数据** = PMC-OA 子集中、标题/结构以「症状/综合征」为入口、含 DDx/红旗/初始评估段的**临床综述全文章节**（不是摘要、不是疾病管理指南）。

**抓取入口** = 发现用 **Europe PMC REST Search**（`OPEN_ACCESS:Y HAS_FT:Y` + DDx 标题 query）+ **PubMed esearch 补漏**；全文用 **Europe PMC `/{PMCID}/fullTextXML`**（JATS 章节树）或 **[BioC API](https://www.ncbi.nlm.nih.gov/research/bionlp/APIs/BioC-PMC/) `BioC_json/{PMCID}/unicode`**（passage + license）；bulk BioC-PMC FTP / Europe PMC OAI 仅作规模化二期。

### 已实现脚本与命令

**阶段 A — 发现层**（Europe PMC 6 条 DDx query，可选 PubMed 补漏）：

```bash
python scripts/build_pmc_oa_ddx_index.py --sleep 0.25
# 可选 PubMed 补漏（需 PUBMED_EMAIL / NCBI_API_KEY）
python scripts/build_pmc_oa_ddx_index.py --pubmed --pubmed-max 2000 --sleep 0.34
```

输出：`data/cpg/api/pmc_oa_ddx_index_latest.jsonl`

**阶段 B — BioC 全文 + chunk**：

```bash
python scripts/fetch_pmc_bioc.py --skip-existing --sleep 0.35
# 试跑：python scripts/fetch_pmc_bioc.py --limit 20 --sleep 0.35
```

输出：

| 路径 | 内容 |
|---|---|
| `data/cpg/raw/pmc_oa/bioc-{pmcid}.json` | BioC JSON 原文 |
| `data/cpg/text/pmc_oa/pmc-oa-ddx-{pmcid}.txt` | 去 passage 拼接的纯文本 |
| `data/cpg/processed/pmc_oa_ddx_chunks.jsonl` | DDx/红旗/评估语义块 |
| `data/cpg/manifest_latest.jsonl` | 合并 article 级 manifest 行 |

共享逻辑：`scripts/pmc_oa_ddx_common.py`（query 模板、BioC passage→chunk、syndrome anchor 解析）。

结构调研结论（发现层假阳性、推荐 RAG 子集 2421 篇、IMP-35 门控）见 [`CPG_RAG_EXTRACTION.md`](CPG_RAG_EXTRACTION.md) **§1.6**。

---

## WikEM 抓取指引

> **许可**：CC BY-SA 3.0（OpenEM Foundation）；站点附 **AI/ML 使用限制**——**禁止**用于模型训练/微调/评测；**RAG 运行时检索**一般可接受，须署名 + ShareAlike。详见 [`CPG_RAG_EXTRACTION.md`](CPG_RAG_EXTRACTION.md) §1.7。

### 有效数据

| 要收 | 不要收 |
|---|---|
| `Category:Symptoms` 英文主条目（Chief complaint / 症状入口） | 翻译子页（`/es`…）、体重模板、纯治疗/文档页 |
| `Differential Diagnosis` / `Evaluation` / `Workup` / Red flags 段 | `Management`、`References`、`See Also` |
| DDx 列表中的 wiki 链接实体 | ML 训练语料 |

### 入口

- **MediaWiki API**：`https://www.wikem.org/w/api.php`
- **发现**：`list=categorymembers&cmtitle=Category:Symptoms`
- **全文**：`action=parse&prop=text|sections`

### 已实现脚本

```bash
# 发现 + 全文 + chunk + cant_miss JSON
python scripts/crawl_wikem_syndrome.py --skip-existing --sleep 0.35

# 仅发现层
python scripts/crawl_wikem_syndrome.py --discover-only
```

| 路径 | 内容 |
|---|---|
| `data/cpg/api/wikem_syndrome_index_latest.jsonl` | 症状页 index |
| `data/cpg/raw/wikem/{slug}.html` | 原始 HTML |
| `data/cpg/text/wikem/wikem-{slug}.txt` | 抽取 plain text |
| `data/cpg/processed/wikem_ddx_chunks.jsonl` | DDx/评估 chunk |
| `data/knowledge_raw/cant_miss_by_syndrome_wikem.json` | IMP-56 WikEM 接地 |
| `data/cpg/manifest_latest.jsonl` | 合并 manifest 行 |

**实测（2026-06-24）**：163 症状页 → **1,053** chunks（148 页含 DDx/评估/红旗段）→ `cant_miss_by_syndrome_wikem.json`（3,835 cant_miss 链接）。解析须适配 MediaWiki `mw-headline` DOM 与 DDx 模板子节继承。

**结构调研结论**（Category 噪声、geriatrics 漏切、IMP-35 门控、推荐 RAG 子集）见 [`CPG_RAG_EXTRACTION.md`](CPG_RAG_EXTRACTION.md) **§1.7.4–1.7.5**；**检索完备性**与 2026-06-24 切分/门控修复见 **§1.8**。