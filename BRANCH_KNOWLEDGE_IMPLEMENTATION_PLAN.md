# 分支知识自动化与 CPG-RAG 实施入档

**入档日期**：2026-06-22  
**状态**：已批准路线图（待按 Phase 逐项落地）  
**关联文档**：

| 文档 | 关系 |
|---|---|
| [`SYNDROME_TO_L1_BRANCH_KNOWLEDGE_RESEARCH.md`](SYNDROME_TO_L1_BRANCH_KNOWLEDGE_RESEARCH.md) | 临床 schema 与字段契约 |
| [`EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md`](EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md) §23、§31.13 | 架构与已落地模块 |
| [`CPG_RAG_EXTRACTION.md`](CPG_RAG_EXTRACTION.md) | CPG 语料→chunk→抽取管道 |
| [`OPEN_CPG_DOWNLOADS.md`](OPEN_CPG_DOWNLOADS.md) | 1912 条开放 CPG 镜像 |

---

## 1. 背景与目标

### 1.1 问题

Tree-Dx 分支创建阶段（BranchCreator）依赖四类知识产物，**默认路径以手工 curated 为主**，扩展新综合征/新专科时维护成本线性增长：

| 产物 | 路径 / 形态 | 当前规模 | 手工程度 |
|---|---|---:|---|
| 特征性标记 | `data/knowledge_raw/pathognomonic_markers.json` | 24 条 | **高**（metadata 明示 Hand-curated） |
| 机制→疾病映射 | `data/knowledge_raw/mechanism_to_disease.json` | ~47 exact + 9 family_expansions | **高**（保守扩展） |
| MECE 域框架 | 运行时 `branch_knowledge`（来自 `syndrome_axis_map.json` 等） | 11 syndrome id | **高**（含 benchmark 导向关键词） |
| 血液学 prompt 模板 | `prompts/branch_creator.txt` B1–B5 | 5 域静态示例 | **高**（prompt 正例） |

另有半自动层：`diagnostic_markers.json`（893 条，Orphadata，`scripts/build_diagnostic_markers.py`）。

### 1.1b 现状核验（2026-06-23，对当前仓库实测）

> 本计划与三份 CPG 文档来自并行分支；此处对关键数字与「已落地 / 待建」边界做一次实测校准，避免重做已完成工作。

**实测计数（一致，无需修正）**：

| 产物 | 文档值 | 实测 | 结论 |
|---|---|---|---|
| `syndrome_axis_map.json` | 11 syndrome id | 11（含 `undifferentiated`，即 10 临床 + 兜底） | 一致 |
| `mechanism_to_disease.json` | ~47 exact + 9 family | 47 exact + 9 family + 1 pattern | 一致 |
| `pathognomonic_markers.json` | 24 | 24 | 一致 |
| `syndrome_override_seeds.json` | C 源 | 7 综合征 | — |
| `diagnostic_markers.json` | 893 | 893 | 一致 |
| StatPearls chunks | 367k | 367,799 | 一致 |
| RAG `metadata.jsonl` 合并库 | 493k | 493,646（StatPearls+教科书） | 一致 |
| CPG manifest | 1912 条 ok / 1915 总 | ok=1912，total=1915 | 一致 |

**已落地（文档部分仍列为「待建」，实为已完成）**：

- `src/.../knowledge/union_axis.py`（`UnionAxisMap`）✅ 已存在。
- `config.py`：`union_axis_ac`、`branch_llm_axis_live`、`llm_axis_cache_json`、`override_seeds_json` ✅ 四字段已落地。
- `controller.py`：`_BRANCH_KNOWLEDGE_DIRECTIVE`（Mode A 软锚定）✅ 已接线，**仅当 payload 含 `branch_knowledge` 时追加**（OFF 路径与旧 prompt 字节一致）。
- `scripts/eval_pipeline_medbullets.py`：`--union-axis-ac` / `--branch-llm-axis-live` ✅ 已接线（IMP-13 仅剩「跑实验」）。
- `data/knowledge_raw/auto_axis_cache.json`：✅ 已 bootstrap **7 综合征**（leukocytosis、hypercalcemia、hyperglycemia_with_skin、bowel_obstruction、acute_abdomen_shock、focal_limb_neuro_deficit、unilateral_nasal_discharge），§31.13.18 已验证 8/8 gold-domain。IMP-10 状态：缓存已起步，剩余综合征批量回填 + 接地核验门（IMP-11）待办。
- `RAGRetriever`：`search` / `search_for_disease` / `search_for_differential` / `extract_lr_from_snippets` ✅ 均已存在（CPG_RAG_EXTRACTION §5.1、§6.4 引用准确）。

**确为待建（与文档一致）**：`build_cpg_chunks.py`、`mine_marker_gaps.py`、`mine_mechanism_map_gaps.py`、`draft_override_seeds.py`、`branch_payload_builder.py`、接地核验门（IMP-11/TODO-GL-16）。

### 1.2 目标

在不破坏临床安全与现有 `branch_knowledge` 契约的前提下，将维护模式从 **「逐条手写」** 转为 **「多源自动生成 + 接地核验 + 人工抽检合入 curated」**：

```text
generated candidates（广覆盖、可丢弃）
    → 接地核验 / 覆盖率评测
    → curated 合入（小而可靠、版本化）
    → runtime 消费（UnionAxisMap / _build_branch_candidates）
```

**硬约束**（与 §31.13 一致）：

1. 下游契约不变：`{l1_classification_axis, axis_rationale, mandatory_coverage, candidate_entities_by_domain, syndrome_matched}`。
2. 覆盖永不低于手工基线：A∪C 合并 + 手工 map fallback（`UnionAxisMap`）。
3. `mandatory_coverage` 取**域粒度**（broad family），禁止把具体疾病名当 L1 label。
4. 所有 generated 项带 `provenance` + `content_tier`；低 tier（如 abstract_only）不单独驱动 mandatory。

---

## 2. 四类产物：内容、消费点与自动化策略

### 2.1 `pathognomonic_markers.json`

**字段**：`terms`, `gene_symbols`, `target_diseases`, `compatible_diseases`, `lr_positive`/`lr_negative`, `confidence`, `source`, `note`。

**消费点**：

- `DiagnosticMarkerIndex`（Layer C，最高优先级）
- `_build_branch_candidates` T1 提名 → `candidate_entities_by_domain`
- EvidenceAnnotator pathognomonic floor / 反向排除

**自动化策略**：

| 步骤 | 脚本（待建/已有） | 输出 |
|---|---|---|
| Orphadata pathognomonic 候选 | 已有 `build_diagnostic_markers.py` | 初筛 HPO↔disease |
| 题库/日志 diff 挖洞 | 待建 `scripts/mine_marker_gaps.py` | `marker_candidates.jsonl` |
| CPG/教科书 LR 句抽取 | Phase 2+（见 §4） | 带 citation 的 LR 候选 |
| 人工 gate | review checklist | 合入 `pathognomonic_markers.json` v1.x |

**不可全自动**：`compatible_diseases`、LR 数值、描述性体征同义词（如 NME→glucagonoma）须人工或半自动审核。

### 2.2 `mechanism_to_disease.json`

**字段**：`exact`（机制/形态选项→cache 实体）、`family_expansions`（宽泛 L1 label→实体列表）、`patterns`（占位泛化）。

**消费点**：`DiseaseNameResolver`、`KBAxisMap` 召回、`expand_to_entities` 分类学展开。

**自动化策略**：

| 步骤 | 脚本（待建） | 输出 |
|---|---|---|
| 选项文本 vs LR cache 实体差集 | `scripts/mine_mechanism_map_gaps.py` | 候选 exact 映射 |
| SNOMED `associated_morphology` / `due_to` | `scripts/build_mechanism_map_from_snomed.py` | 候选映射（须 cache 存在性过滤） |
| CPG Etiology/Mechanism chunk | `BranchPayloadBuilder`（Phase 1） | mechanism→entity 对 |
| 人工 gate | 仅映射 cache 中已有实体 | 合入 JSON |

### 2.3 `branch_knowledge` MECE 框架

**非静态文件**——由 `controller._build_branch_candidates()` 注入 BranchCreator payload。

**默认数据源**：`data/knowledge_raw/syndrome_axis_map.json`（syndrome_keywords → axis → domains → member_keywords → split_variants）。

**已落地自动化路径**（config 切换，默认 OFF）：

| 模式 | Config | 模块 | 说明 |
|---|---|---|---|
| 手工 map | （默认） | `SyndromeAxisMap` | 10 综合征 + undifferentiated（共 11 id） |
| KB 自动轴 | `auto_axis_kb=True` | `KBAxisMap` | SNOMED 属性 + LR 召回；纯 SNOMED 对 mechanism 金标弱 |
| 指南 RAG 召回 | （`GuidelineBranchSource`） | StatPearls/教科书 TF-IDF | 确定性实体 spotting |
| LLM 轴缓存 | `union_axis_ac=True` | `UnionAxisMap` | A=LLM cache + C=override seeds + 手工 fallback |
| 热路径 LLM | `branch_llm_axis_live=True` | 同上 | 缺失综合征实时生成并写回 cache |
| CPG 层（规划） | T3a | `cpg_chunks` + 抽取 | 权威推荐与专科 DDx |

**推荐生产组合**：`enable_branch_knowledge` + `union_axis_ac` + 离线填充 `llm_axis_cache_json` + `override_seeds_json`。

### 2.4 BranchCreator B1–B5 模板

**位置**：`src/agentclinic_tree_dx/prompts/branch_creator.txt` L36–46。

**定位**：血液学场景（blasts 存在时）的**手工正例**；语义已镜像至 `syndrome_axis_map.leukocytosis` 与 `syndrome_override_seeds.leukocytosis`。

**演进**：

- Prompt **保留通用规则**（broad label、phase-crossing、can't-miss）。
- 专科 MECE 模板改为 **数据驱动注入**（`branch_knowledge.mandatory_coverage`），不在 prompt 中无限堆静态 B1–Bn。
- 有 `branch_knowledge` 时，controller 追加 `_BRANCH_KNOWLEDGE_DIRECTIVE`（`controller.py`），B1–B5 退化为 fallback 示例。

---

## 3. 目标架构

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ Layer 0 — 高精度小表（curated，人工 gate）                               │
│   pathognomonic_markers.json │ mechanism_to_disease.json              │
│   syndrome_override_seeds.json │ syndrome_axis_map.json（识别+兜底）     │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│ Layer 1 — 半自动构建（脚本 + 外部 KB）                                   │
│   build_diagnostic_markers.py │ build_snomed_knowledge.py               │
│   mine_*_gaps.py（待建）│ draft_override_seeds.py（待建）                │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│ Layer 2 — 运行时自动生成（确定性 hot path）                              │
│   GuidelineBranchSource │ KBAxisMap │ UnionAxisMap                      │
│   _build_branch_candidates → mandatory_coverage / entities_by_domain    │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│ Layer 3 — CPG / 全文 RAG（待建 cpg_chunks）                              │
│   manifest → build_cpg_chunks → TF-IDF/FAISS → BranchPayloadBuilder     │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
                    BranchCreator LLM（+ _enforce_mandatory_branches）
```

**curated vs generated 分工**（见 `SYNDROME_TO_L1_BRANCH_KNOWLEDGE_RESEARCH.md` §11.13）：

- **curated**：reviewed、版本化、高置信；runtime mandatory 的唯一权威来源。
- **generated**：广覆盖、带 provenance；低置信仅提示扩展，不进 mandatory。
- **UnionAxisMap**：C（curated seeds）为骨架，A（LLM cache）加性合并，手工 map 为 coverage 下界。

---

## 4. 分阶段实施路线图

### Phase 0 — 评测尺子与基线（3–5 天）【P0】

**目标**：任何自动化改动可回归；确立手工基线数字。

| ID | 任务 | 交付物 | 验收 |
|---|---|---|---|
| **IMP-00** | 固化 9-case + MedBullets 子集 gold-domain 标注 | `data/eval/branch_knowledge_gold.json` | 每 case：syndrome_id, gold_entity, gold_domain |
| **IMP-01** | 跑通隔离评测 harness | 已有 `scripts/eval_branch_creator_isolated.py` | HAND vs KB vs UNION 报告可复现 |
| **IMP-02** | 记录当前基线 | 本文件 §6 基线表 | gold-domain recall、axis error、mandatory 注入率 |

**命令**：

```bash
python scripts/eval_branch_creator_isolated.py   # HAND / auto_axis / 对比
python scripts/probe_axis_recall.py
python scripts/probe_branch_recall.py
```

### Phase 1 — UnionAxisMap 生产化 + 种子半自动（1–2 周）【P0】

**目标**：脱离逐 syndrome 扩 `syndrome_axis_map.json`；覆盖 ≥ 手工基线。

| ID | 任务 | 交付物 | 验收 |
|---|---|---|---|
| **IMP-10** | 离线批量生成 LLM axis cache | `data/knowledge_raw/auto_axis_cache.json` | 已 bootstrap 7 综合征 / 8/8 gold-domain（§31.13.18 已验证）；剩余综合征批量回填待办 |
| **IMP-11** | 接地核验门 | 改 `GuidelineBranchSource.build_branch_knowledge_llm` | 实体须逐字命中检索片段，否则丢弃（TODO-GL-16） |
| **IMP-12** | 种子自动起草脚本 | `scripts/draft_override_seeds.py` | 输出候选 JSON + provenance（TODO-GL-19） |
| **IMP-13** | 端到端实验 | `eval_pipeline_medbullets.py --union-axis-ac --branch-knowledge` | TODO-GL-13：方差与准确率 |
| **IMP-14** | 轴模板 prompt 增强 | prompt 注入顶层鉴别轴范式 | 修 c1/c9 轴框定（TODO-GL-20） |

**Config**：

```python
enable_branch_knowledge = True
union_axis_ac = True
llm_axis_cache_json = "data/knowledge_raw/auto_axis_cache.json"
override_seeds_json = "data/knowledge_raw/syndrome_override_seeds.json"
branch_llm_axis_live = False  # 生产默认关
```

### Phase 2 — 静态小表半自动扩展（1–2 周）【P1】

**目标**：降低 pathognomonic / mechanism 表的「挖洞式」手写。

| ID | 任务 | 交付物 | 验收 |
|---|---|---|---|
| **IMP-20** | marker 缺口挖掘 | `scripts/mine_marker_gaps.py` | 输出 case log 中未命中 T1 的体征列表 |
| **IMP-21** | mechanism 缺口挖掘 | `scripts/mine_mechanism_map_gaps.py` | 选项文本无 cache 命中 → 候选映射 |
| **IMP-22** | SNOMED morphology 候选 | `scripts/build_mechanism_map_from_snomed.py` | 仅保留 cache 存在实体 |
| **IMP-23** | 合入 review 流程 | `docs/MARKER_REVIEW_CHECKLIST.md`（可选） | 每条新 marker 有 source + compatible_diseases |

### Phase 3 — CPG chunk 管道（1–2 周）【P0/P1】

**目标**：1912 条开放 CPG 进入 RAG；专科 DDx 补强 StatPearls。

详见 [`CPG_RAG_EXTRACTION.md`](CPG_RAG_EXTRACTION.md) §9；与本计划对齐的 ID：

| ID | 任务 | 交付物 | 验收 |
|---|---|---|---|
| **IMP-30** | CPG 切分 | `build_manifest_cpg_chunks.py` + `build_cpg_chunks.py` + `audit_manifest_bot_gate.py` | **部分完成**：manifest **39,091** useful（**198** bot_gate 跳过）+ 三源合并 **360,234**；NICE syndication 待 API；198 篇待补拉全文 |
| **IMP-30b** | NICE 语料（镜像） | `crawl_nice_published_ddx.py --all-sidebar` → **1320 章 / 303 指南** manifest ok（**已完成**）；Syndication 全库待 API-Key | 公开 HTML 自动化路径见 CPG_RAG §1.3–§1.4 |
| **IMP-35** | NICE/CPG 召回门控 | 改 `GuidelineBranchSource`：`cpg_chunk_gate.snippet_on_topic`（`chunk_type` / `entry_type` / `syndrome_anchor`）+ `expand_ddx_siblings` | NICE/WikEM/PMC chunk 不被 StatPearls 标题门控误滤 |
| **IMP-31** | 索引扩展 | 改 `build_tfidf_index.py` / `build_rag_index.py` | ⚠️ **更正（2026-06-25 实测）**：实时索引仍是 5-23 FAISS（**仅 statpearls+textbooks**），**Merck/WikEM/PMC 全未入**（脚本列了 merck 但索引从未重建）；全部 **待办**，见 CPG §1.10.1 |
| **IMP-32** | 50 条 query 标注 + MRR | `scripts/eval_cpg_retrieval.py` | MRR@10 基线 |
| **IMP-33** | BranchPayloadBuilder 原型 | `knowledge/branch_payload_builder.py` | RAG→LLM 抽 mandatory_coverage + citation |
| **IMP-34** | 接入 T3a | `_build_branch_candidates` 可选 CPG 层 | 9-case mandatory 命中率提升 |

**命令**：

```bash
python scripts/audit_manifest_bot_gate.py          # 可选：--annotate-manifest
python scripts/build_manifest_cpg_chunks.py --useful-only
python scripts/build_merck_manual_corpus.py --chunk-only   # Merck 已提取时仅重切
python scripts/build_cpg_chunks.py --useful-only
python scripts/build_tfidf_index.py   # ⚠️ 实时索引尚未重建（5-23 仅 StatPearls+Textbooks，Merck 也未入）；重跑+并入 cpg_chunks 才解锁，见 CPG §1.10.1
python scripts/build_rag_index.py
# python scripts/eval_cpg_retrieval.py   # IMP-32 待建
```

### Phase 4 — PubMed / BODHI 兜底与闭环学习（2–4 周）【P2】

| ID | 任务 | 交付物 | 参考 |
|---|---|---|---|
| **IMP-40** | PubMed DDx 检索 | `PubMedRetriever.differential_families()` | TODO-GL-17 |
| **IMP-41** | BODHI 兄弟族下界 | mandatory floor 完整性 | TODO-GL-18 |
| **IMP-42** | schema 缺口报告 | `scripts/schema_gap_report.py` | case log → 自动 PR 候选 |
| **IMP-43** | disease→domain 投影自动生成 | `*.generated.json` | SYNDROME §11.12 Phase 1 |

### Phase 3.5 — 覆盖保证与召回增强（2026-06-24 续研，CPG §13）【P0/P1】

> 目标：在无 BMJ-BP/UpToDate/CKS 等闭源「症状→DDx」库下，用开放源集成 + 覆盖审计**证明并保证**关键方向不漏。许可红线见 `CPG_RAG_EXTRACTION.md` §13.2 / `OPEN_CPG_DOWNLOADS.md` 开放许可现实表。

| ID | 任务 | 交付物 | 优先级 | 参考 |
|---|---|---|---|---|
| **IMP-54** | `eval_coverage_oracle.py`：oracle-union gold-domain recall + 逐源边际贡献 + 缺口归因 | 评测脚本 + 报告 | **P0**（先量上界，不依赖新数据） | CPG §13.5 |
| **IMP-55** | 运行时实体→域可达性门 + residual 域注入（防 LLM 删正确方向） | `controller._build_branch_candidates` | **P0**（立竿见影，不依赖新数据） | CPG §13.1/13.5、§31.13 约束2 |
| **IMP-50** | PMC-OA「approach-to / differential-diagnosis-of」综述定向采集（CKS/AAFP/BMJ 的合规替身） | `pmc_oa_ddx_index.jsonl` + BioC/JATS chunk | P1 | CPG §13.3、`OPEN_CPG_DOWNLOADS.md` PMC-OA 指引；**已实施** |
| **IMP-51** | `entry_type`（syndrome_entry/disease_entry）标记 + 子索引 boost | `build_cpg_chunks.py` 字段 | P1 | CPG §13.3；WikEM/PMC/Merck **已标记**，检索 boost **待办** |
| **IMP-52**（**✅ 落地，证伪有害**） | 跨轴 query 扇出（mechanism/anatomy/urgency/workup/symptom-entry）= `query_mode="fanout"` | `guideline_branch_source.py` `_build_queries` | **完成但默认关**（§19.7：A6=0.693<A1=0.702，TF-IDF 底座下 facet 稀释 mandatory，无召回增益） | CPG §13.4、§19.7 |
| **IMP-53**（**✅ 落地+验证** 2026-06-26） | MedCPT dense 塔（`ncbi/MedCPT-Article-Encoder`，CLS 768d 点积，203830 向量）+ sparse **RRF hybrid**；语料**行对齐** `cpg_index`；闭包委托 sparse | `scripts/build_medcpt_cpg_index.py`（断点续跑）+ `hybrid_cpg_retriever.py`（drop-in） | **完成（正收益）**（§19.7：**A10 轴可分 0.571→0.643、L2 0.643→0.714、漏斗 xloss 1→0、综合 0.702→0.719**；A11 联合提名达确定性最佳 0.723。与 differentiated 不同：dense **并联**不替换 sparse，不稀释 PMC） | CPG §13.4、§19.7 |
| **IMP-56**（**✅ 落地，安全网**） | can't-miss **硬层** = `cant_miss_hard=True`：保证注入的 mandatory/提名实体穿透 `max_candidates` 裁剪（配合 IMP-60 inject_poles） | `guideline_branch_source.py` `_recall_v2` 硬切 | **完成**（§19.7：A8 在 n=14/K=40 罕咬→≈中性；生产更大候选池防静默挤出） | CPG §13.6、§19.7 |

### Phase 3.6 — 三源融合 + 索引解锁（2026-06-25 续研，CPG §14）【P0/P1】

> 背景：PMC-OA / WikEM / Merck 19e 已抓取切分（CPG §1.6–1.9），前沿转向**融合 + 索引 + 覆盖证明**。**IMP-31 是前置卡点**：WikEM/PMC-OA chunk 已切但未进 RAG 索引（`build_tfidf_index.py` 仅 statpearls/textbooks/merck），后续召回增益皆悬空于此。

| ID | 任务 | 交付物 | 优先级 | 参考 |
|---|---|---|---|---|
| **IMP-31**（升 **P0**） | `cpg_chunks`（WikEM/PMC-OA）并入 TF-IDF/FAISS 索引，保留 `source_id/chunk_type/entry_type/syndrome_anchor` | 改 `build_tfidf_index.py` / `build_rag_index.py` | **P0 解锁卡点** | CPG §14.1 |
| **IMP-31闭包**（**已落地** 2026-06-26） | `expand_ddx_siblings` 升级：`source_id` 倒排（O(hits)）+ WikEM `wiki_links` 合成 DDx 块注入 | 改 `rag_retriever.py` | **完成**（验证：入口检索受限，单靠闭包零增益，须配锚点入口选择/机制提名） | CPG §19.1/19.3① |
| **IMP-58**（**✅ 落地（机制+标志物通道）** 2026-06-26） | **`nominate=True`**：`pathognomonic_markers.json`（24 条 OR）+ `mechanism_to_disease.json`（exact key≥6 + family_expansions ≤12）对 `{syndrome}{syn}{context}` **子串匹配** → 具体病名以 **≥0.6×max(spot)** 写入 `recall()` scored；`cant_miss_hard` 时 forced 回 top-40。**消费**：链 A 实验 flat 40 名（A7/A9l）；链 B 生产 `controller` T1 marker→按域（**不**调 `recall(nominate)`）。**规格**：`BRANCH_GENERATION_PHASE_REPORT.md` **§2.9.2**、§6.10 | `guideline_branch_source.py` `_nominate_from_context` + `disease_name_resolver.py` | **完成**（§19.7：A7 xloss 1→0、spotted 0.75→1.0） | CPG §14.3、§19.7 |
| **IMP-57** | 跨源 DDx 融合 + 一致性投票（≥2 源→mandatory 候选） | `ddx_union_by_syndrome.json` | P1 | CPG §14.2、SYNDROME §11.10 |
| **IMP-59** | 综合征别名 crosswalk（root↔WikEM/Merck/PMC anchor + UMLS 同义） | `syndrome_alias_map.json` | P1 | CPG §14.4 |
| **IMP-60** | CPG/Merck sub-axis 提示抽取（服务轴正确性，分期子轴化） | sub-axis 候选 | P2 | CPG §14.7 |
| **IMP-61** | **数据源差异化检索器**（分源子索引 + 源级 query 路由 + RRF/**UNION** 融合 + 入口 boost），封装为 `RAGRetriever` 兼容接口 | `DifferentiatedCPGRetriever`（**已落地** 2026-06-26，含 `fusion='union'`）+ `scripts/build_differentiated_cpg_index.py` | ⚠️ **落地但弃用主路径**（§19.6：UNION 在 n=14 仍 0.235，PMC 稀释有害；仅留 §16 WikEM-入口场景按需启用） | CPG §16、§19.3②、§19.6#5 |
| **IMP-61b**（**已落地** 2026-06-26，**新方法**） | `AnchorAugmentedRetriever`：锚点/章节结构化入口选择 **UNION** 基检索（保 PMC 主干）→ 闭包；修复 IMP-61 等权稀释回退 | `anchor_entry_retriever.py` | **P1**（§19.2：D2 无回归=0.875；§18 上界靠锚点选入口而非 TF-IDF 排序） | CPG §19.1/19.3③ |
| **IMP-62** | Branch-gen **检索/抽取漏斗诊断**常驻脚本 + CI 报告（B6 拆分；含 nprobe/B10/top_k 矩阵） | `scripts/eval_branch_rag_recall_diagnosis.py` → `branch_rag_recall_diagnosis.json` | **P1**（已首跑；**完整排查备忘录 CPG §17.3–17.6**） | CPG §17 |
| **IMP-63**（**✅ 已落地** 2026-06-26） | CPG spotting 路径重构：参数化 `retrieve_k/extract_k/mmr_lambda/closure_mode/extractor`；**`closure_mode='grounding'` 把闭包移出候选池**（消除 C4 拥挤+set 序方差）；**`extractor='spotter+llm'` 合并 `recall_llm`**。**⚠️ MMR/extract_k-trim 实测对确定性 spotter 有害（饿死广度，§19.6#4），仅宜用于喂 LLM 的 grounding** | `guideline_branch_source.py`（`_recall_v2` 等） | **完成**（§19.6：grounding 复现 0.702 无方差；spotter+llm **A5=0.768，L1tgt 0.929** 最大杠杆） | CPG §17.7、§19.5、§19.6 |
| **IMP-64**（**✅ 已落地** 2026-06-26） | **本体反向归族**：仅 `len(scored)>40` 时对 **全量** spotted key 做 SNOMED `is_a` 分组（2–70% 覆盖，≤6 超族；`family+orphan` 孤儿单成员族）；flat top-40 **超族零成员** 时从 40 名外取 **1 名具体病** 替换 **末尾 ≤5 槽**（`n_reserve=min(缺席族数,K//8)`）；**不用族名**替换具体名。**消费**：仅 `recall()` ≤40 flat dict，不管 24 条 LLM 摘要。**规格**：`BRANCH_GENERATION_PHASE_REPORT.md` **§2.9.1**、§6.12 | `guideline_branch_source.py` `_rollup_candidates`（`rollup_mode`、`taxonomy` 注入） | **完成**（轴可分 0.571→0.643，综合持平） | CPG §21.5、§19.6#3 |
| **IMP-60**（**⚠️ 落地待数据**） | sub-axis 提取 **+ 强制轴极注入**（cant_miss 双极）：保证相反轴极双双进候选，避免单极召回→轴污染 | `guideline_branch_source.py` `_inject_axis_poles`（`inject_poles`/`cant_miss`） | 已落地参数化，但 **`cant_miss_by_syndrome_wikem.json`（症状类目 id）未覆盖本评测的 lab/endocrine 综合征 → 实测无效**；须扩 can't-miss 源 | CPG §14.7、§19.5、§19.6#7 |

**修订实操顺序**（按 §19.6/§19.7 混杂受控重评后的剩余杠杆排序）：IMP-31闭包（✅）→ **IMP-63 闭包→grounding + spotter+llm（✅，A5=0.768）** → **IMP-64 本体归族（✅，轴可分 0.643）** → **IMP-58 机制/标志物直提名（✅，A7 漏斗 xloss→0）** → **IMP-56 硬层（✅）** → **IMP-53 MedCPT hybrid（✅，A10=0.719；A11 确定性最佳 0.723）** → **扩 cant_miss 源激活 IMP-60** → IMP-31 生产索引重建（FAISS+元数据，端到端基建）→ …　**弃用**：IMP-52 fanout（§19.7 轻度有害）、differentiated UNION/RRF 接入主 recall（PMC 稀释）、spotter 池 MMR-trim（饿死广度）。

**§19.6 混杂受控重评（2026-06-26，`eval_branch_confounder_matrix.py`，gnn-llm 环境）**：§19.2/§19.5 跑在未修复旧 recall 上（C4/C5/C7 混杂）。落地 IMP-63/64/61/60（均参数化保旧路径）后 A/B 矩阵（ML n=14 + 漏斗 n=8）：臂序 **A5_llm 0.768（L1tgt 0.929）> A2_rollup 0.704（轴可分 0.643）≈ A1_grounding/A0b 0.702 ≫ A0_legacy 0.54–0.65（不稳）≫ MMR-trim 0.376 / UNION 0.235**。**重derive 结论**：①"闭包有害"→更正为"闭包**灌候选池**有害（C4）"，grounding 复现 0.702 且保闭包供 LLM；②旧 closure-pool 还是**方差源**（set 序+40槽）；③本体归族提**轴可分性**（§19.5 短板）；④**LLM grounded 抽取（C7）是最大 flat 召回杠杆**；⑤UNION/RRF 仍有害弃用；⑥MMR-trim 饿死广度（更正 §17.5.4 外推）；⑦IMP-60 因 cant_miss 源覆盖缺口在本集无效。

**§19 验证关键结论（2026-06-26，`eval_diff_retriever_validation.py`）**：curated-free 手工标签下，**检索可达上界 = 7/8**（c1 不可被任何检索器召回——机制/eponym 鸿沟）、**spotting 后 = 6/8**（c13 抽取损失）。⇒ ①闭包（IMP-31）正确但"入口检索受限"，本基准零增益（S0≡S1）；②纯差异化（IMP-61 等权 RRF）稀释 PMC 主干，有害（0.875→0.75）；③锚点 UNION（IMP-61b）无回归（0.875）；④两剩余缺口 **均非检索问题**：c1→IMP-58+eponym（P0）、c13→IMP-63（P0）。

**§19.5 多级分支重做（2026-06-26，`eval_branch_multilevel.py`，n=14 教科书综合征）**：9 题 L1-only 饱和无区分；新增 L2+轴可分性后**区分度达成**（综合分极差 0.395）。臂序 **unified-noclosure 0.702 > anchor-union 0.618 > unified-closure 0.600 ≫ differentiated 0.307**。**新发现**：①**闭包在常见综合征上有害**——灌入有界 40 槽候选池致 **7/14 case 的 L1 mandatory 覆盖下降、0 上升**（C4 拥挤实锤）⇒ IMP-63 须**隔离闭包噪声**（仅喂 grounding 通道）；②differentiated 等权 RRF n=14 复现有害（0.307）→ 弃用；③**轴可分性仅 0.571**（过半综合征只召回单轴极）⇒ IMP-60 强制轴极注入。**更正**：§19.3 "闭包安全无回归"在更敏感的多级度量下不成立。`§17.5.6` 补充诊断证：spotting 瓶颈是 **C4 拥挤非 C1 vocab**、wiki_links 零增益、门控 B4 无碍、PMC 淹没 top-k ~90%。

**IMP-61 依据（2026-06-25 实验，CPG §16）**：在 PMC 占库 88% 的源失衡实况下，统一 TF-IDF 检索使 WikEM 综合征入口 Recall@10 仅 0.659（47/138 失败，入口真实排名中位第 38、被 ~35 条 PMC prose 压住），定位四缺陷：候选淹没（`pain` 在 PMC 有 8,982 竞争 chunk）、入口被埋、查询模板错配、anchor 语义混淆。差异化检索（①分源子索引②源级字段加权③源级 query 路由④RRF 融合⑤入口 boost）将 Recall@10 提到 **0.993（+33.4pp）**、DDx 实体覆盖 0.283→0.533（×1.9）、top-10 PMC 占比 0.51→0.26。

**IMP-31 规格细化（2026-06-25 实测 + 孤立实验，CPG §1.10）**：①实时索引经实测仅 statpearls+textbooks（5-23 FAISS），Merck 亦未入——重建是**唯一解锁前提**，非优化项；②重建**必须写入** `source_id/chunk_type/entry_type/syndrome_anchor`，否则 `expand_ddx_siblings`/IMP-35 门控继续空转（孤立实验：实时索引这些字段全空，闭包 8→8 +0）；③入索引取 **useful∧≥120 字符子集（≈200k）** 而非 321k 全量（实测 31% `other`、8.8% 碎片，`--useful-only` 未实际削减 PMC）；④`syndrome_anchor`=标题原文（~63% 无显式临床词），故 **IMP-58 归一须与 IMP-31 并行**，PMC 才真正可用；⑤NICE/协会 HTML 仍未切 chunk（IMP-30 待补全）。

### Phase 5 — 持续运维

| 周期 | 动作 |
|---|---|
| CPG manifest 增量 | `sha256` 变化 → 只重建受影响 chunk |
| 新 benchmark case | 跑 IMP-01 → 缺口进 IMP-20/21/12 |
| curated 合入前 | domain recall + axis purity + smoke eval（SYNDROME §11.12 Phase 4） |

---

## 5. 文件与模块清单

### 5.1 已有（可直接用）

| 路径 | 用途 |
|---|---|
| `data/knowledge_raw/syndrome_axis_map.json` | 手工 MECE + 识别 keywords |
| `data/knowledge_raw/syndrome_override_seeds.json` | UnionAxisMap C 源 |
| `data/knowledge_raw/pathognomonic_markers.json` | Layer C markers |
| `data/knowledge_raw/mechanism_to_disease.json` | 机制/族展开 |
| `src/.../knowledge/auto_axis.py` | `KBAxisMap` |
| `src/.../knowledge/union_axis.py` | `UnionAxisMap` |
| `src/.../knowledge/guideline_branch_source.py` | RAG + `build_branch_knowledge_llm` |
| `src/.../controller.py` | `_build_branch_candidates`, `_enforce_mandatory_branches`, `_BRANCH_KNOWLEDGE_DIRECTIVE` |
| `data/knowledge_raw/auto_axis_cache.json` | A 源生成物（已 bootstrap 7 综合征，§31.13.18 验证 8/8；剩余回填待办） |
| `scripts/eval_branch_creator_isolated.py` | 隔离评测 |
| `scripts/crawl_nice_published_ddx.py` | NICE published 列表 + 侧边栏全章节（canonical，CPG_RAG §1.3） |
| `data/cpg/open_cpg_nice_ddx_seed.json` | NICE 1320 章节 seed |
| `data/cpg/api/nice_published_list_latest.json` | 指南主条目元数据（ref/title/url，chunk 阶段补 parent） |

### 5.2 待建 / legacy

| 路径 | Phase | 备注 |
|---|---|---|
| `scripts/extract_nice_public_chapters.py` | — | **legacy curated**；非 NICE 自动化路径（CPG_RAG §1.3） |
| `scripts/fetch_nice_syndication_index.py` | 1/3 | API-Key 激活后全库 |
| `scripts/build_nice_api_seed.py` | 1/3 | |
| `scripts/download_nice_syndication.py` | 3 | |
| `scripts/nice_credentials.py` | 1 | |
| `data/cpg/open_cpg_nice_public_seed.json` | — | legacy 126 条；新 run 以 `nice_ddx__*` 为准 |
| `scripts/mine_marker_gaps.py` | 2 | |
| `scripts/mine_mechanism_map_gaps.py` | 2 | |
| `scripts/draft_override_seeds.py` | 1 | |
| `scripts/eval_cpg_retrieval.py` | 3 | |
| `data/cpg/processed/cpg_chunks.jsonl` | 3 | |
| `knowledge/branch_payload_builder.py` | 3 | |

---

## 6. 基线与验收指标

### 6.1 分支知识（BranchCreator 隔离评测）

| 指标 | 手工 map 基线 | Union A∪C 目标 | 备注 |
|---|---|---|---|
| gold-domain recall | 8/8（§31.13.18） | ≥ 8/8 | 禁整族缺失 |
| axis error | 0 | 0 | gold 分支 LR 方向不得与关键证据相反 |
| mandatory 注入率 | 记录基线 | 不升高为佳 | 惰性 covered 判据见 §31.13.8 |
| 跨 run 分支集一致率 | 低（纯 LLM） | 高（KB 锚定） | `--branch-knowledge` |

### 6.2 CPG RAG（Phase 3 后）

| 指标 | 目标 |
|---|---|
| chunk 可切分率 | >90% |
| 检索 MRR@10 | 基线 + 迭代 |
| mandatory_coverage 命中率 | 9-case / MedBullets 子集提升 |
| citation 合法率 | >95% |

### 6.3 静态表扩展（Phase 2 后）

| 指标 | 目标 |
|---|---|
| T1 精确提名覆盖 | MedBullets 子集 pathognomonic  firing ↑ |
| LR hole 数 | `trace_lr_holes.py` 输出 ↓ |
| 误排除事件 | `compatible_diseases` 审计 0 回归 |

---

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| LLM 幻觉 DDx 域 | 接地核验门（IMP-11）；CPG citation 强制 |
| SNOMED 分区语义错误 | UnionAxisMap：不以纯 SNOMED 为唯一源 |
| abstract 当全文 | `content_tier` 过滤 |
| 过度 mechanism 映射 | 仅映射 cache 已有实体；人工抽检 |
| benchmark 过拟合 keywords | 识别层保留 hand map；分区层自动化 |
| 覆盖回退 | UnionAxisMap 手工 fallback；mandatory floor seeds |

---

## 8. TODO 索引（与 EXTERNAL 设计文档对齐）

| 本计划 ID | 设计文档 ID | 摘要 |
|---|---|---|
| IMP-11 | TODO-GL-16 | LLM 输出接地核验门 |
| IMP-12 | TODO-GL-19 | draft_override_seeds.py |
| IMP-14 | TODO-GL-20 | 轴模板 prompt |
| IMP-40 | TODO-GL-17 | PubMed differential_families |
| IMP-41 | TODO-GL-18 | BODHI 兄弟族下界 |
| IMP-13 | TODO-GL-13 | 端到端 union-axis 实验 |
| IMP-01 | TODO-AX-06 | 隔离评测 harness（已有，需固化数据集） |
| IMP-20/21 | TODO-BC-01 等 | family_expansions / marker 扩展 |

---

## 9. 结论与下一步

1. **四类产物不必全部追求「全自动 curated」**；正确分工是 curated 小表 + generated 广表 + Union 合并。
2. **近期最高 ROI**：Phase 0 尺子 → Phase 1 UnionAxisMap 生产化 → Phase 3 `build_cpg_chunks.py`（与 CPG 镜像规模匹配）。
3. **B1–B5 不需逐条自动化**；其语义已由 leukocytosis map/seeds 数据化，prompt 仅保留通用规则。
4. **单一入口文档**：本文件为实施入档；细节管道见 `CPG_RAG_EXTRACTION.md`，架构见 `EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md` §31.13。

**立即下一步**：

```bash
# 1. 基线评测
python scripts/eval_branch_creator_isolated.py

# 2. NICE Syndication（在账户页获取 API-Key 后）
export NICE_API_KEY='...'   # 或写入凭据 JSON 的 api_key 字段
python scripts/fetch_nice_syndication_index.py --verify-only
python scripts/fetch_nice_syndication_index.py --max-depth 3
python scripts/build_nice_api_seed.py
python scripts/run_cpg_api_pipeline.py --skip-pubmed --skip-europepmc --skip-esmo --skip-medlineplus --download-nice

# 3. 启动 Phase 3 最小可行
# 实现 scripts/build_cpg_chunks.py（见 CPG_RAG_EXTRACTION.md §5）
```

---

*本入档随 Phase 完成逐项勾选 IMP-* 任务并更新 §6 基线表。*
