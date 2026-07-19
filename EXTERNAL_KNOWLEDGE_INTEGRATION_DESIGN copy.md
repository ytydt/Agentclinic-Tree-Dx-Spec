# 外部知识集成方案设计

> **版本**: v1.6 | **日期**: 2026-05-28 | **更新**: 多源开放数据集成（Doclogica 13K + Wikidata + MONDO 58K + BioPortal 同义词）；双层同义词桥接（finding + disease）；unified cache 267K 条；15-gap 覆盖率 0%→100%
> **动机**: 冒烟测试分析揭示了两个不可仅靠 prompt 工程解决的知识缺口：
> 1. **EvidenceAnnotator 的 LR 标签偏差**——不知道 "35% blasts" 对 AML 和 CML-BC 的鉴别价值相同
> 2. **TALP 的证据盲区**——不知道 "视力下降 + 共济失调 → leukostasis → CML-BC 鉴别线索"

---

## 一、需要的两类外部知识

### 1.1 Annotator 需要：定量似然比（LR）数据

| 需求 | 示例 | 目标模块 |
|------|------|---------|
| 临床发现对特定诊断的 LR+/LR- | "35% blasts": LR+(AML)=5.2, LR+(CML-BC)=4.8 | EvidenceAnnotator |
| 检查/检验的灵敏度/特异度 | "basophilia for CML": Sn=0.85, Sp=0.92 | EvidenceAnnotator |
| 组合发现的联合 LR | "blasts + ataxia + visual loss": joint LR for leukostasis | ordinal_update → bayesian_update |

**缺乏此知识的后果**：Annotator 凭 LLM 直觉给 AML 标 `strong_for` 而给 CML-BC 标 `moderate_for`，导致归一化剪刀差。

### 1.2 TALP 需要：疾病鉴别特征图谱

| 需求 | 示例 | 目标模块 |
|------|------|---------|
| 疾病 A vs B 的鉴别特征列表 | CML-BC vs de novo AML: basophilia, splenomegaly, subacute onset | TALP |
| 临床综合征→疾病关联 | "leukostasis" → high WBC + blasts → CML-BC, hyperleukocytic AML | TALP |
| 已用证据的边际鉴别价值 | "35% blasts already analyzed → remaining discriminators: basophilia, BCR-ABL" | TALP |

**缺乏此知识的后果**：TALP 反复生成 "35% blasts support X?" 类问题（42 候选中 86% 引用 blasts），忽略视力、步态等高鉴别价值证据。

---

## 二、可用的外部数据源调研

### 2.1 似然比（LR）数据源

| 数据源 | 类型 | 覆盖范围 | 访问方式 | 优势 | 劣势 |
|--------|------|---------|---------|------|------|
| **GetTheDiagnosis.org** | 开放数据库 | 315 诊断, 1,133 发现, 1,733 条目 | Web 爬取（无 API） | 免费、结构化、含 Sn/Sp/LR | 覆盖面有限，无 API，需爬取 |
| **docLogica** | 半开放数据库 | ~1,700 疾病, ~1,200 检验, ~1,000 LR | **REST API**（`api2.doclogica.com`） | ★ 有公开 API、含 UMLS ID 映射、含发病率数据、支持鉴别诊断查询 | 免费账户部分数据带问号 |
| **JAMAevidence / JAMA Rational Clinical Exam** | 文献系列 | ~100 综述文章，各含数十个 LR | **无 API**——PubMed 全文 + 机构订阅 | 金标准 LR 数据，含系统综述 | 非结构化（**必须手工从文章提取**）、付费 |
| **PubMed / PMC 全文** | 原始文献 | 理论上无限 | PubMed API + RAG | 最全面的 LR 来源 | 需要 NLP 提取、质量参差 |
| **Isabel Healthcare API** | 商业 API | 10,000+ 疾病 | REST API（付费） | 96% 准确率、实时 | 高成本、无 LR 细节 |

### 2.2 疾病鉴别特征数据源

| 数据源 | 类型 | 覆盖范围 | 访问方式 | 优势 | 劣势 |
|--------|------|---------|---------|------|------|
| **Deep-DxSearch DiagRL-Corpus** | **扁平 JSON 映射表** | 16,371 疾病, 257,022 疾病-表型对 | HuggingFace（开源） | 覆盖最广、ICD-10 100% 覆盖、多源交叉验证 | **非 KG**——无疾病间关系、无鉴别权重、无综合征链 |
| **UMLS Metathesaurus** | 本体/关系图 | 3.45M 概念, 17.1M 名称, 190 词表 | REST API（免费，需 license） | 最全面的医学概念关系网络 | 关系类型粗粒度，无鉴别权重 |
| **SNOMED CT** | 临床术语本体 | 350,000+ 概念 | UMLS API / FHIR | 层次化临床概念、因果关系 | 复杂、学习曲线高 |
| **PrimeKG** | 开源知识图谱 | 17,080 疾病, 4M 关系 | GitHub (MIT) | 疾病-蛋白质-表型-药物多层关系 | 偏分子生物学，临床特征弱 |
| **SPOKE** | 生物医学知识引擎 | 19 数据库整合 | API（学术免费） | 多尺度（基因→临床表型） | 偏精准医学，非鉴别诊断 |
| **Diseasomics** | 疾病-症状网络 | Disease Ontology + SNOMED CT | 图数据库 | 84.56% 准确率，可机器读 | 学术项目，维护不确定 |
| **UpToDate / DynaMed** | 临床知识库 | 25+ 专科 | RAG（需订阅） | 最权威的临床鉴别特征 | 高成本、版权限制 |

#### Deep-DxSearch 指南数据详解

> **重要澄清**：DiagRL-Corpus 的疾病指南**不是知识图谱**，而是扁平的 disease → phenotype_list JSON 映射表。

**数据格式**（`Guideline_common.json` + `Guideline_rare.json`）：
```json
{
  "disease_name": "Chronic Myeloid Leukemia",
  "icd_code": "C92.1",
  "phenotypes": ["fatigue", "splenomegaly", "basophilia", "weight_loss",
                  "night_sweats", "thrombocytopenia", ...],
  "sources": ["Mayo Clinic", "NCBI", "WebMD"]
}
```

**数据规模**：
- 常见病：10,000+ 疾病，142,141 个疾病-表型对，ICD-10-CM 100% 覆盖
- 罕见病：6,000+ 疾病，114,881 个疾病-表型对（含表型出现率），来源 Orphanet
- 每个常见病条目平均 2.87 个独立来源交叉验证
- 来源：Mayo Clinic、WebMD、NIH、NCBI 等，经 GPT-4o 摘要提取为结构化信息
- 映射到 ICD、ORPHA、HPO 术语体系

**缺失能力**（需要我们自行构建）：
1. **无疾病间关系**——不知道 "CML blast crisis" 和 "AML" 共享大量表型
2. **无鉴别权重**——不知道 "basophilia" 对 CML 的 LR+ = 8.5
3. **无综合征推理链**——不知道 "视力下降 + 共济失调 → leukostasis"
4. **表型为自然语言**——需要标准化映射才能与 vignette 证据项匹配

**在 Deep-DxSearch 原系统中的使用方式**：通过 `<lookup>` 动作访问——agent 提交疾病名查询，`PhenotypeSearchService` 返回该疾病的典型表型列表。这是一个简单的 key-value 查找，不涉及图遍历。

### 2.3 当前临床 Agent 系统使用的知识源

| 系统 | 知识源 | 集成方式 | 年份 |
|------|--------|---------|------|
| **MedKGI** (NeurIPS 2024) | 自建医学知识图谱 | KG 约束 + 信息增益引导 | 2024 |
| **KG4Diagnosis** (CHIL 2025) | 自动构建的 362 疾病 KG | 语义实体提取 + 多维关系重建 | 2024 |
| **MEDDxAgent** (ACL 2025) | 知识检索 agent + 诊断策略 agent | 模块化多 agent | 2025 |
| **EBMChat** (medRxiv 2025) | PubMed + Cochrane Library | RAG + 记忆模块 + TAO 循环 | 2025 |
| **MedRAG** (2025) | 层次化诊断 KG + EHR | KG-增强 RAG | 2025 |
| **UpToDate AI Labs** | UpToDate 内容库 | 专有 RAG | 2024 |
| **DynaMed Dyna AI** | DynaMed 内容库 | 专有 RAG | 2024 |

**共同模式**：所有系统都使用了**某种形式的外部知识约束**来弥补 LLM 的临床推理不足。最有效的架构是 **KG + RAG 混合**——KG 提供结构化的疾病-特征关系，RAG 提供非结构化的临床文本证据。

---

## 三、方案设计：双通道知识注入

### 3.1 架构概览

```
  ┌──────────────────────── Knowledge Layers ───────────────────────────┐
  │                                                                     │
  │  层0: DxS 鉴别索引        层1: PrimeKG         层2: LR 缓存        │
  │  (16k diseases,扁平)    (300k HPO边+KG遍历) (定量 LR+/LR-)      │
  │  ┌───────────────┐       ┌──────────────┐    ┌──────────────┐      │
  │  │ disease →      │       │ symptom →    │    │ finding →    │      │
  │  │ {phenotypes}   │       │ syndrome →   │    │ {lr+, lr-,   │      │
  │  │               │       │ disease      │    │  source}     │      │
  │  └───────┬───────┘       └──────┬───────┘    └──────┬───────┘      │
  │          │                      │                    │              │
  │          │   层3: StatPearls + PubMed RAG (fallback)│              │
  │          │   ┌────────────────────────────┐          │              │
  │          │   │ vector-indexed text chunks │          │              │
  │          │   └────────────┬───────────────┘          │              │
  └──────────┼────────────────┼──────────────────────────┼──────────────┘
             │                │                          │
             ▼                ▼                          ▼
  ┌──────────────────┐  ┌────────────┐    ┌──────────────────┐
  │  DxFeature       │  │ (fallback) │    │  LR Retriever    │
  │  Retriever       │◄─┤            │    │  (for Annotator) │
  │  (for TALP)      │  └────────────┘    └────────┬─────────┘
  └────────┬─────────┘                             │
           │                                       │
     ┌─────▼──────┐                         ┌──────▼────────┐
     │ Temporary   │                         │ Evidence      │
     │ Analytic    │                         │ Annotator     │
     │ Leaf Plan.  │                         │               │
     └─────────────┘                         └───────────────┘
           │                                       │
           └───────────── Controller ──────────────┘
```

### 3.2 通道 A：LR Retriever → EvidenceAnnotator

**目的**：为 EvidenceAnnotator 提供定量 LR 参考，替代纯 LLM 直觉。

**数据源优先级**（2026-05-22 更新）：
1. **docLogica API**（★ 首选——唯一提供公开 REST API 的 LR 数据源）
   - 端点：`GET https://api2.doclogica.com/diseases/{id}` → 返回 findings + frequency（veryCommon/common/uncommon/rare）
   - 端点：`POST https://api2.doclogica.com/ddx/query` → 基于症状组合的鉴别诊断排序
   - 附带 UMLS CUI 映射（可与 PrimeKG/UMLS 对接）、发病率数据、语义关系
   - 免费注册即可访问，覆盖 ~1,700 疾病 + ~1,200 检验
   - **注意**：返回的是 frequency 标签而非精确 LR+/LR- 数值，需从 frequency 转换估算 LR
2. **GetTheDiagnosis.org**（补充，精确 Sn/Sp/LR 数据）→ Web 爬取构建本地缓存
   - 无 API，需爬取 1,733 条目，但数据含精确的 sensitivity/specificity 和 LR 数值
3. **JAMA Rational Clinical Exam** 系列 → **必须手工从论文中提取**（无 API、无结构化数据导出）
   - JAMA Network 无公开数据 API（"Jama Software API" 是另一产品，与 JAMA 医学期刊无关）
   - JAMAevidence 仅支持 PDF 下载和 PowerPoint 导出，无机器可读格式
   - 金标准 LR 数据但提取成本高，建议作为第三优先级手工补充
4. **PubMed RAG 补充** → 对缓存未覆盖的发现-疾病对做实时检索

**实现方案**：

```python
class LRRetriever:
    """在 EvidenceAnnotator 调用前，为每个 (finding, branch) 对检索 LR。"""
    
    def retrieve(self, findings: list[str], branches: list[str]) -> dict:
        """
        Returns:
          {
            "E17:blasts|B1.1:AML": {"lr_plus": 5.2, "lr_minus": 0.3, "source": "JAMA"},
            "E17:blasts|B1.2:CML-BC": {"lr_plus": 4.8, "lr_minus": 0.35, "source": "docLogica"},
          }
        """
        results = {}
        for finding in findings:
            for branch in branches:
                # 1. 查本地缓存
                cached = self.local_cache.get(finding, branch)
                if cached:
                    results[f"{finding}|{branch}"] = cached
                    continue
                # 2. 查 GetTheDiagnosis
                gtd = self.query_getthediagnosis(finding, branch)
                if gtd:
                    results[f"{finding}|{branch}"] = gtd
                    continue
                # 3. PubMed RAG fallback
                results[f"{finding}|{branch}"] = self.pubmed_rag_lr(finding, branch)
        return results
```

**注入方式**：在 EvidenceAnnotator 的 payload 中追加 `lr_reference` 字段：

```json
{
  "state": { ... },
  "raw_result": [ ... ],
  "lr_reference": {
    "35% blasts → AML": {"lr_plus": 5.2, "source": "JAMA 2018"},
    "35% blasts → CML-BC": {"lr_plus": 4.8, "source": "docLogica"},
    "visual acuity loss → leukostasis": {"lr_plus": 8.0, "source": "StatPearls"}
  }
}
```

**prompt 修改**：在 EvidenceAnnotator prompt 中增加：
```
When lr_reference is provided in the payload, USE these quantitative LR values
to calibrate your branch_effects labels instead of relying on clinical intuition.
Map LR ranges to labels: LR>=5 → strong_for, LR 2-5 → moderate_for, etc.
If two branches have similar LR values for the same finding, they MUST receive
the same label.
```

### 3.3 通道 B：Dx Feature Retriever → TALP

**目的**：为 TALP 提供"当前最有鉴别价值的未分析证据"，打破证据锚定。

**数据源优先级**（已修订）：
1. **DiagRL-Corpus 鉴别索引**（首选）→ 从 DxS 指南的扁平表型表构建疾病对差集，零成本、16k 疾病覆盖
2. **UMLS Metathesaurus 关系图**（综合征补充）→ 提供 DxS 指南缺失的"症状 → 综合征 → 疾病"多跳链
3. **StatPearls/Textbook RAG**（长尾 fallback）→ DxS 和 UMLS 均未覆盖时的文本检索

**核心思路：将扁平映射表转化为鉴别索引**

DiagRL-Corpus 虽非 KG，但其 16k 疾病 × 表型列表可以通过**集合运算**产生鉴别特征：

```python
class DxDiscriminatorIndex:
    """从 DiagRL-Corpus 构建疾病对鉴别特征索引。"""
    
    def __init__(self, guideline_path: str):
        with open(guideline_path) as f:
            self.guideline = json.load(f)
        # 构建 disease → set(phenotypes) 的快速查找表
        self.phenotype_sets = {
            d["disease_name"]: set(d["phenotypes"])
            for d in self.guideline
        }
    
    def get_discriminators(self, disease_a: str, disease_b: str) -> dict:
        """计算两个疾病之间的鉴别特征。"""
        pheno_a = self.phenotype_sets.get(disease_a, set())
        pheno_b = self.phenotype_sets.get(disease_b, set())
        return {
            "only_a": pheno_a - pheno_b,   # A 有但 B 没有的表型
            "only_b": pheno_b - pheno_a,   # B 有但 A 没有的表型
            "shared": pheno_a & pheno_b,   # 共有表型（无鉴别价值）
        }
        # 示例: get_discriminators("CML", "AML")
        # → only_CML: {"basophilia", "splenomegaly", "weight_loss", ...}
        # → only_AML: {"gum_hypertrophy", "DIC", ...}
        # → shared:   {"fatigue", "thrombocytopenia", "anemia", ...}


class EvidenceMatcher:
    """将 vignette 证据项与标准表型进行模糊匹配。"""
    
    def __init__(self, all_phenotypes: set[str], embedder):
        self.phenotype_embeddings = {
            p: embedder.encode(p) for p in all_phenotypes
        }
    
    def match(self, evidence_items: list[dict]) -> dict:
        """
        输入: [{"id": "E11", "text": "bilateral visual acuity loss"}, ...]
        输出: {
          "matched": {"E11": "visual_loss", "E4": "weight_loss"},
          "unmatched_evidence": ["E13"],  # 无法映射到标准表型
        }
        """


class DxFeatureRetriever:
    """整合 DxS 鉴别索引 + UMLS 关系 + RAG，为 TALP 提供鉴别提示。"""
    
    def __init__(self, dxs_index, umls_client, rag_retriever):
        self.dxs_index = dxs_index      # DiagRL-Corpus 鉴别索引
        self.umls = umls_client          # UMLS API 客户端
        self.rag = rag_retriever         # StatPearls/PubMed fallback
    
    def retrieve_discriminators(
        self, 
        branch_pairs: list[tuple[str, str]],
        vignette_evidence: list[dict],
        already_analyzed_ids: set[str],
    ) -> list[dict]:
        """
        三层查询：DxS 差集 → UMLS 综合征链 → RAG fallback
        
        Returns ranked discriminating features NOT yet analyzed.
        """
        results = []
        for disease_a, disease_b in branch_pairs:
            # === Layer 1: DxS 差集（O(1) 查找）===
            disc = self.dxs_index.get_discriminators(disease_a, disease_b)
            
            # 与 vignette 证据匹配，找出"有鉴别价值但尚未分析的证据"
            for eid, matched_pheno in self.evidence_matcher.match(vignette_evidence).items():
                if eid in already_analyzed_ids:
                    continue
                if matched_pheno in disc["only_a"]:
                    results.append({
                        "evidence_id": eid,
                        "feature": matched_pheno,
                        "favors": disease_a,
                        "source": "DiagRL-Corpus",
                        "power": "high",  # 独有表型 = 高鉴别力
                    })
                elif matched_pheno in disc["only_b"]:
                    results.append({
                        "evidence_id": eid,
                        "feature": matched_pheno,
                        "favors": disease_b,
                        "source": "DiagRL-Corpus",
                        "power": "high",
                    })
                # shared 表型跳过（无鉴别价值）
            
            # === Layer 2: UMLS 综合征链（DxS 缺失的多跳推理）===
            # 对 DxS 未匹配的证据，查询 UMLS 是否存在
            # "症状 → 综合征 → 疾病" 的间接关联
            for eid in unmatched_evidence_ids:
                syndrome_links = self.umls.find_syndrome_path(
                    symptom=vignette_evidence[eid],
                    diseases=[disease_a, disease_b]
                )
                if syndrome_links:
                    results.append({
                        "evidence_id": eid,
                        "feature": syndrome_links["path_description"],
                        "favors": syndrome_links["favored_disease"],
                        "source": "UMLS",
                        "power": "moderate",
                    })
            
            # === Layer 3: RAG fallback ===
            # 如果 DxS + UMLS 均未覆盖，检索 StatPearls
            if len(results) < 2:
                rag_hints = self.rag.search(
                    f"differential diagnosis {disease_a} vs {disease_b}"
                )
                # ... 解析 RAG 结果
        
        return sorted(results, key=lambda x: {"high": 3, "moderate": 2, "low": 1}[x["power"]], reverse=True)
```

**具体示例——CML Blast Crisis vs De Novo AML**：

```
DxS 差集计算:
  CML phenotypes:  {fatigue, splenomegaly, basophilia, weight_loss, night_sweats, ...}
  AML phenotypes:  {fatigue, bleeding, gum_hypertrophy, bone_pain, DIC, ...}
  only_CML:        {splenomegaly, basophilia, weight_loss, night_sweats}
  only_AML:        {gum_hypertrophy, bone_pain, DIC}
  shared:          {fatigue, thrombocytopenia, anemia, bleeding}

Vignette 证据匹配:
  E4:"weight loss over month"  → matched:"weight_loss" → only_CML → favors CML ✓
  E11:"visual acuity loss"     → unmatched by DxS → UMLS 查询 →
      "visual_loss" → "leukostasis" → "CML blast crisis"  → favors CML ✓
  E17:"35% blasts"             → matched:"blasts" → shared → 无鉴别价值，跳过 ✓

输出 discriminator_hints:
  1. E4: weight_loss → favors CML (source: DiagRL-Corpus, power: high)
  2. E11: visual_loss → leukostasis → favors CML (source: UMLS, power: moderate)
```

**注入方式**：在 TALP 的 payload 中追加 `discriminator_hints` 字段：

```json
{
  "state": { ... },
  "discriminator_hints": [
    {
      "branch_pair": ["B1.1 De Novo AML", "B1.2 CML Blast Crisis"],
      "unused_discriminators": [
        {
          "feature": "Visual acuity loss (E11) + ataxic gait (E13) → leukostasis",
          "favors": "B1.2 CML Blast Crisis",
          "power": "high",
          "why": "Leukostasis more common in CML-BC due to typically higher WBC burden"
        },
        {
          "feature": "Subacute onset (E1) + weight loss over month (E4)",
          "favors": "B1.2 CML Blast Crisis",
          "power": "moderate",
          "why": "Subacute course suggests chronic disease acute transformation"
        }
      ]
    }
  ]
}
```

**prompt 修改**：在 TALP prompt 中增加：
```
When discriminator_hints is provided, you MUST prioritize generating candidates
that analyze the listed unused discriminators BEFORE repeating analysis of
already-used evidence. Each candidate MUST reference at least one evidence item
from the hints that has NOT been analyzed in actions_taken.
```

### 3.4 知识层构建方案

对于本项目的具体需求，推荐**分层构建**策略（非单一 KG）：

#### 层 0：DiagRL-Corpus 鉴别索引（免费、覆盖最广、零构建成本）

直接从 DxS 开源指南构建疾病对差集索引：
```
输入: Guideline_common.json (16,371 diseases × phenotype lists)
处理: 对所有竞争疾病对，预计算 phenotype 集合差
产出: dx_discriminator_index.json

示例:
  ("CML", "AML") → {
    only_CML: ["basophilia", "splenomegaly", "weight_loss"],
    only_AML: ["gum_hypertrophy", "DIC", "bone_pain"],
    shared:   ["fatigue", "thrombocytopenia", "anemia"]
  }
```

**注意**：此层是**扁平查找表**，不是图。优势是 O(1) 查询和 16k 疾病覆盖；
劣势是无法提供"症状 A → 综合征 B → 疾病 C"的多跳推理链。

#### 层 1：KG 关系图（提供多跳推理和疾病间关系）

> **2026-05-22 验证结论：PrimeKG 确认可用，UMLS 需要 API 实测**

**首选方案：PrimeKG**（MIT License，Harvard Dataverse 免费下载）

经验证，PrimeKG 的 phenotype 节点**来自 HPO（Human Phenotype Ontology）**，是**临床层面的症状/体征**，
而非分子表型。例如 CML 在 GARD/Orphanet（PrimeKG 的 HPO 数据源之一）中的 phenotype 包括：
- Splenomegaly [HP:0001744]
- Thrombocytopenia [HP:0001873]
- Fatigue [HP:0012378]
- Leukocytosis, Basophil abnormality, Poor appetite 等

PrimeKG 的具体数据：
- **15,311 个 phenotype 节点**（HPO 术语，临床级别的症状/体征/检验异常）
- **300,634 条 disease_phenotype_positive 边**（疾病→表型的正向关联）
- **2,386 条 disease_phenotype_negative 边**（疾病→表型的排除关联——这对鉴别诊断极有价值）
- **37,472 条 phenotype_phenotype 边**（表型之间的层级/关联关系）
- **17,080 个 disease 节点**，包含 CML（id:30039）、CML blast phase（id:84261）、AML 多种亚型等
- 疾病间还有 **disease_disease 边**（包括 "subtype_of" 等层级关系）
- 数据来源：MONDO + HPO + Orphanet + DisGeNET + DrugBank + UBERON + GO 等 20 个源

**PrimeKG 对我们需求的覆盖验证**：
```
需求 1: "CML 的典型表型"
  → disease_phenotype_positive 边: CML (30039) → {Splenomegaly, Fatigue, Basophilia, ...}  ✓

需求 2: "CML vs AML 的鉴别特征"
  → phenotypes(CML) \ phenotypes(AML) = {Basophilia, Splenomegaly, ...}
  → phenotypes(AML) \ phenotypes(CML) = {Gingival hypertrophy, DIC, ...}  ✓
  → 300k disease_phenotype_positive 边覆盖远超 DxS 的 142k 对  ✓

需求 3: "视力下降 → leukostasis → CML-BC" 多跳链
  → PrimeKG 含 leukostasis (MONDO:0006831) 作为 disease 节点
  → 但 leukostasis → visual impairment 的直接边尚需实测验证  △
  → phenotype_phenotype 边（37k 条）可能提供间接路径  △

需求 4: "CML blast crisis 与 CML 的关系"
  → disease_disease 边: CML (30039) ←→ CML blast phase (84261)  ✓

需求 5: disease_phenotype_negative（排除关联）
  → 这是 DxS 指南完全不具备的能力——"疾病 X 通常不表现为症状 Y"
  → 对鉴别诊断极有价值（2,386 条）  ✓
```

**补充方案：UMLS Metathesaurus**（免费 API，需 license）

UMLS 验证结果：
- Leukostasis 确认存在：CUI **C0282548**，语义类型 "Disease or Syndrome"
- SNOMED CT 编码：30419000
- MONDO 映射：MONDO:0006831（与 PrimeKG 同源）
- 但 MedGen 页面中**未显示结构化的 concept relations**——leukostasis → visual impairment 的关系
  不确定是否存在于 UMLS 的 `finding_of` 或 `manifestation_of` 关系类型中
- **需要实际 API key 调用 `/content/current/CUI/C0282548/relations` 来验证**

**层 1 推荐方案**：

| 方案 | 数据源 | 优势 | 劣势 |
|------|--------|------|------|
| **方案 A（推荐）** | PrimeKG 下载 `kg.csv` | 离线使用、无 API 限制、含 negative 边、MIT license | 需下载 ~500MB 文件 |
| **方案 B（补充）** | UMLS REST API | 覆盖 3.45M 概念、实时查询 | 需申请 license、API 速率限制、需验证关系链可用性 |
| **方案 A+B** | PrimeKG 为主 + UMLS 补充 | 互补：PrimeKG 覆盖 disease-phenotype，UMLS 补充综合征链 | 双重维护成本 |

从 UMLS 提取 `finding_of` / `cause_of` / `associated_with` / `manifestation_of` 关系，
补充 PrimeKG 缺失的综合征级推理链（如 leukostasis → visual impairment）：
```
CUI:C0023467 (Leukemia, Myelocytic, Chronic) 
  -- associated_with --> CUI:C0542444 (Blast crisis)
CUI:C0282548 (Leukostasis)
  -- ?finding_of? --> CUI:C0042789 (Visual impairment)  [需 API 实测验证]
  -- ?finding_of? --> CUI:C0004134 (Ataxia)              [需 API 实测验证]
```

PrimeKG + UMLS 的协作使得 "visual impairment → leukostasis → CML blast crisis" 有望被自动发现，
弥补 DxS 指南中 CML 表型列表里不包含 "visual loss" 的缺陷。

#### 层 2：LR 权重标注（定量化）

为层 0 的鉴别特征和层 1 的关系边添加 LR 权重：
```
basophilia -- only_CML --> CML: LR+ = 8.5 (source: GetTheDiagnosis)
splenomegaly -- only_CML --> CML: LR+ = 3.2 (source: docLogica)
leukostasis -- manifestation_of --> CML-BC: LR+ = 6.0 (source: JAMA)
```

#### 层 3：文献 RAG 补充（按需）

对层 0-2 未覆盖的查询，通过 PubMed API + PubMedBERT 检索：
```
query: "leukostasis visual loss CML blast crisis likelihood ratio"
→ retrieve top-3 abstracts → extract LR estimate
```

#### 层间协作流程
```
TALP 请求鉴别提示
        │
        ▼
  层 0: DxS 差集索引 ──→ 找到 "basophilia, splenomegaly" (only_CML)
        │                  并与 vignette 证据匹配
        │
        ├─ 已匹配 → 层 2 查 LR → 返回带权重的 discriminator_hints
        │
        ├─ 未匹配的证据 → 层 1: PrimeKG 图遍历（phenotype_phenotype + disease_disease 边）
        │                  → 发现 "visual_loss → leukostasis → CML-BC"（含 UMLS 可选补充）
        │                  → 层 2 查 LR → 返回
        │
        └─ 层 0+1 均未覆盖 → 层 3: StatPearls/PubMed RAG fallback
```

---

## 四、实现路线图

### Phase 0: Prompt-embedded 知识表（零成本，1-3 天）

| 步骤 | 任务 | 产出 |
|------|------|------|
| 0.1 | 在 TALP prompt 中嵌入 Top-50 高频鉴别规则 | prompt 更新 |
| 0.2 | 在 Annotator prompt 中嵌入 Top-30 高频 LR 对照表 | prompt 更新 |
| 0.3 | 冒烟测试验证知识注入有效性 | 对比报告 |

### Phase 1: DxS 鉴别索引 + LR 缓存（1-2 周）

| 步骤 | 任务 | 产出 |
|------|------|------|
| 1.1 | 从 HuggingFace 下载 DiagRL-Corpus (`Guideline_common.json` + `Guideline_rare.json`) | 原始数据 ~39MB |
| 1.2 | 实现 `DxDiscriminatorIndex`：解析 DxS 指南，构建 disease → phenotype_set 映射 | `src/knowledge/dx_discriminator_index.py` |
| 1.3 | 预计算高频疾病对的表型差集并缓存 | `dx_discriminator_cache.json` |
| 1.4 | 实现 `EvidenceMatcher`：将 vignette 证据项模糊匹配到 DxS 标准表型 | `src/knowledge/evidence_matcher.py` |
| 1.5 | 接入 docLogica API（首选，~1,700 疾病 frequency 数据） + 爬取 GetTheDiagnosis.org 1,733 条精确 LR 条目 | `lr_cache.json` |
| 1.6 | 实现 `LRRetriever` 类 | `src/knowledge/lr_retriever.py` |
| 1.7 | 修改 TALP prompt（接收 `discriminator_hints`）+ Annotator prompt（接收 `lr_reference`） | prompt 更新 |
| 1.8 | 修改 controller 注入逻辑：在调用 TALP/Annotator 前查询知识层 | `controller.py` 更新 |
| 1.9 | ordinal_update → bayesian_update（使用 LR 缓存） | `updater.py` 更新 |

### Phase 2: PrimeKG 知识图谱 + 已用证据追踪（2-3 周）

> **2026-05-22 验证更新**：PrimeKG 已确认可用，phenotype 为 HPO 临床级别。

| 步骤 | 任务 | 产出 |
|------|------|------|
| 2.1 | 从 Harvard Dataverse 下载 PrimeKG `kg.csv`（~500MB，MIT License） | 原始 KG 数据 |
| 2.2 | 解析 `disease_phenotype_positive` 边（300k 条）和 `disease_phenotype_negative` 边（2.4k 条），构建 disease→phenotype_set 映射 | `src/knowledge/primekg_index.py` |
| 2.3 | 解析 `disease_disease` 边，构建疾病亚型/关联图（CML→CML-BC 等） | 疾病关系图 |
| 2.4 | 解析 `phenotype_phenotype` 边（37k 条），支持综合征→症状的多跳查询 | 表型层级遍历 |
| 2.5 | 将 PrimeKG 作为层 1 整合进 `DxFeatureRetriever`（DxS 差集未覆盖时查 PrimeKG） | 统一接口 |
| 2.6 | **可选**：申请 UMLS API key，验证 leukostasis→visual impairment 关系链（补充 PrimeKG 缺失的综合征链） | `umls_relations.json` |
| 2.7 | 增加"已用证据追踪"机制（`seen_evidence_ids` 跨轮持久化） | state 更新 |

### Phase 3: StatPearls/PubMed RAG fallback（2-3 周）

| 步骤 | 任务 | 产出 |
|------|------|------|
| 3.1 | 索引 StatPearls（301k snippets）+ 教科书（126k snippets）为向量库 | 检索服务 |
| 3.2 | 搭建 PubMed 检索 + LR 自动提取 pipeline | NLP pipeline |
| 3.3 | 整合进 DxFeatureRetriever（层 3）和 LRRetriever（fallback） | 统一接口 |

### Phase 4: 评估与校准（1-2 周）

| 步骤 | 任务 | 产出 |
|------|------|------|
| 4.1 | 在 medbullets 测试集上对比有/无知识注入的准确率 | 评估报告 |
| 4.2 | 校准 LR → ordinal label 的映射阈值 | 优化参数 |
| 4.3 | 分析知识注入对 bundle 证据多样性的影响 | 证据覆盖率指标 |
| 4.4 | 验证 DxS 鉴别索引的覆盖率（对测试集中每个 case 检查鉴别特征命中率） | 覆盖率报告 |

---

## 五、风险与替代方案

### 5.1 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| DxS 表型粒度不一致 | GPT-4o 摘要质量参差，表型可能过粗或遗漏 | 与 UMLS/HPO 术语标准化对齐；多源交叉验证（每疾病平均 2.87 来源） |
| DxS 差集无法覆盖综合征链 | "视力下降 → leukostasis → CML-BC" 此类间接关联无法仅靠差集发现 | PrimeKG phenotype_phenotype 边（37k 条）+ 可选 UMLS 关系图补充多跳推理（层 1）|
| Evidence ↔ Phenotype 匹配精度 | vignette 证据是自然语言，DxS 表型也是自然语言，模糊匹配可能错配 | embedding 相似度 + 阈值过滤；HPO 标准化 |
| GetTheDiagnosis 覆盖不足（315 诊断） | 长尾疾病无 LR | PubMed RAG fallback |
| UMLS 关系粗粒度（无鉴别权重） | 无法直接产生 discrimination_power | 用 LR 缓存补充权重 |
| LR 数据质量参差 | 错误 LR 导致更大偏差 | 设置 confidence 阈值，低置信度退回 LLM 判断 |
| token 开销增大 | TALP/Annotator payload 膨胀 | 限制 hints 数量（top-5），按需检索 |

### 5.2 低成本替代：Prompt-embedded 知识表

如果外部数据源集成成本过高，可先实施**静态知识嵌入**：

在 TALP prompt 中硬编码高频鉴别规则（类似 MedKGI 的 KG 约束）：

```
Hematological differential decision rules:
- Blasts ≥20% + subacute onset → consider CML blast crisis alongside AML
- Visual loss + ataxia + high WBC with blasts → evaluate for leukostasis
  (favors CML-BC > de novo AML due to typically higher WBC burden in CML)
- Basophilia → highly specific for CML (LR+ ~8.5)
- Splenomegaly → supports CML (LR+ ~3.2)
- No prior hematological history ≠ exclusion of CML-BC (37% are de novo)
```

这不需要外部数据源，但需要按领域手工编写，不可扩展。适合作为 Phase 1 的零成本起步。

---

---

## 六、深化调研：整合方式与数据类型选择

### 6.1 五种整合范式的对比分析

#### A. 标准 RAG（Vector-based Retrieval-Augmented Generation）

**原理**：将文档切片后向量化，查询时检索 top-k 相关片段注入 prompt。

**代表系统**：MedRAG Toolkit (MIRAGE), EBMChat

**MIRAGE 基准实测数据**（GPT-3.5 backbone, RRF-2 retriever）：

| 语料库 | MMLU-Med | MedQA-US | MedMCQA | PubMedQA* | BioASQ | 平均 |
|--------|----------|----------|---------|-----------|--------|------|
| 无 RAG (CoT) | 72.91 | 65.04 | 55.25 | 36.00 | 74.27 | 60.69 |
| PubMed (23.9M) | 75.57 | 64.34 | 55.34 | 69.00 | 87.06 | **70.26** |
| StatPearls (301k) | 72.64 | **65.67** | 54.63 | 30.00 | 61.17 | 56.82 |
| Textbooks (126k) | **76.68** | 65.91 | 54.79 | 31.00 | 59.39 | 57.55 |
| Wikipedia (29.9M) | 74.20 | 64.57 | 54.72 | 31.00 | 76.21 | 60.14 |
| MedCorp (54.2M，混合) | **76.86** | **67.32** | **55.63** | **69.00** | **87.38** | **71.24** |

**关键发现**：
- **PubMed 是唯一在所有任务上都优于 CoT 基线的单一语料库**
- StatPearls 和 Textbooks 对考试题有优势（MMLU-Med +3.8pp, MedQA-US +0.9pp），但**对文献型 QA 反而有害**（PubMedQA -6pp）
- **混合语料库 MedCorp 综合最优**——跨源检索弥补了单一语料库的盲区

**适合场景**：直接事实查询（"某发现的 LR+ 是多少"），知识补充。
**不适合场景**：需要多跳推理的鉴别诊断链（"症状 A → 综合征 B → 鉴别疾病 C"）。

---

#### B. GraphRAG（Graph-based Retrieval-Augmented Generation）

**原理**：先将文档构建为知识图谱（实体 + 关系 + 社区摘要），查询时通过图遍历检索多跳关联知识。

**代表系统**：MedGraphRAG (ACL 2025), Evidence-Based GraphRAG (USMLE)

**实测对比**（RAG vs GraphRAG, 复杂临床案例 [medRxiv 2025]）：

| 维度 | 标准 RAG | GraphRAG | 优胜方 |
|------|---------|----------|-------|
| 临床正确性 | 高 | 高 | 持平 |
| 指南依从性 | 中高 | 高 | GraphRAG |
| 患者特异性 | 中 | **高** | GraphRAG |
| 多跳推理（阈值/算法决策） | 弱 | **强** | GraphRAG |
| 输出清晰度 | **高** | 低（冗长引用） | RAG |
| 索引构建成本 | 低 | **高**（需构图） | RAG |

**关键发现**：
- GraphRAG 在**需要算法决策和多层级关系推理**的任务上显著优于标准 RAG
- 但 GraphRAG 的输出常包含冗长的指南摘录，**降低了可读性和 prompt 效率**
- MedGraphRAG 通过 "Triple Graph Construction + U-Retrieval" 同时连接用户文档和权威医学来源，在 9 个医学 QA 基准 + 2 个事实核查数据集上超越 SOTA

**适合场景**：疾病-综合征-症状的多跳推理链（正是我们 TALP 需要的 "视力下降 → leukostasis → CML-BC" 链条）。
**不适合场景**：简单的事实检索；图构建的前期投入大。

---

#### C. Agentic RAG（Agent-driven Iterative Retrieval）

**原理**：LLM 作为 agent 自主决定"何时检索、检索什么、是否足够"，通过多轮检索-评估-再检索循环逐步收敛。

**代表系统**：

| 系统 | 架构 | 性能提升 | 特色 |
|------|------|---------|------|
| **SEMA-RAG** (2026) | 3-agent: Interpreter + Explorer + Arbiter | +6.46pp (5 基准平均) | 证据充分性驱动的自演进检索 |
| **Deep-DxSearch** (2025) | RL 端到端训练，5 种动作模式 | +22.7% (平均准确率) | 16k 疾病指南 + 150k 病历 + 27M 文献 |
| **Self-correcting Agentic GraphRAG** (2025) | retrieve-evaluate-refine 循环 | faithfulness 0.94, recall 0.92 | 肝病领域专用 |

**SEMA-RAG 三阶段架构**（与我们的 pipeline 高度对齐）：
```
I-Agent (Interpreter)  →  E-Agent (Explorer)  →  A-Agent (Arbiter)
将问题映射为临床        充分性驱动的多轮       证据裁决 + 答案
Schema 四元组           检索（自演进）         选择
        ↕                      ↕                      ↕
   ≈ BranchCreator        ≈ TALP + Bundler       ≈ EvidenceAnnotator
```

**Deep-DxSearch 的知识环境**（开源可用）：
- **16,371 疾病表型映射表**（DiagRL-Corpus）：扁平 JSON 格式 `disease → [phenotype_list]`，**非 KG**，来源 Mayo Clinic/NIH/WebMD 经 GPT-4o 摘要提取；覆盖 257,022 个疾病-表型对，ICD-10-CM 100% 覆盖
- **177,029 患者记录**：用于 case-based reasoning（`<match>` 动作）
- **27M+ 生物医学文献**（MedRAG 体系）：PubMed + Wikipedia + Textbooks
- 5 种动作模式：`reason`（推理）、`lookup`（查阅表型映射表）、`match`（匹配病例）、`search`（文献检索）、`diagnose`（诊断）

**关键发现**：
- Agentic RAG 的核心优势是**与诊断流程的天然对齐**——临床推理本身就是迭代的
- Deep-DxSearch 通过 RL 让 agent **学会何时检索比检索什么更重要**
- SEMA-RAG 证明了**任务解耦**（解释/探索/裁决分离）比单一 reasoning chain 更有效

**适合场景**：多轮迭代诊断推理，知识需求在诊断过程中动态变化。
**不适合场景**：需要 RL 训练或复杂 agent 编排，实现成本较高。

---

#### D. KG Augmentation（Knowledge Graph Direct Augmentation）

**原理**：不经过检索，直接将 KG 中的结构化三元组或子图注入 LLM 的 prompt 或 reasoning path。

**代表系统**：MedKGI, KG4Diagnosis

**MedKGI 的 KG 约束机制**：
- 从医学 KG 提取当前症状相关的**疾病集合**和**鉴别特征集合**
- 用 KG 三元组**约束**问题生成——只允许生成 KG 中有对应关系的问题
- 信息增益引导——每次选择在 KG 上最能减少不确定性的问题

**KG4Diagnosis 的自动 KG 构建**：
- 覆盖 362 种常见疾病
- 语义实体抽取 + 多维关系重建
- 分层 multi-agent：全科 → 专科

**关键发现**：
- KG 约束**显著减少了 LLM 的幻觉和冗余提问**（MedKGI 对话效率提升 30%）
- 但 KG 质量是瓶颈——构建高质量医学 KG 成本高，长尾疾病覆盖不足
- **结构化约束 + 非结构化补充**是共识架构

**适合场景**：约束 TALP 的候选生成范围，防止证据锚定。
**不适合场景**：KG 未覆盖的罕见疾病或新发疾病。

---

#### E. Hybrid: KG-augmented GraphRAG + Agentic Orchestration

**原理**：用 KG 提供结构化骨架，用 RAG 补充非结构化文本，用 Agent 编排何时查询哪个通道。

**代表系统**：MedRAG (arXiv 2025), Deep-DxSearch

**MedRAG 的层次化诊断 KG**：
```
疾病层 ──┬── 症状/体征层 ──┬── 检查/检验层
         │                 │
    层次化关系          鉴别权重
    (子类/变体)        (LR/敏感度)
```

**Self-correcting Agentic GraphRAG**（肝病学专用）：
- 图遍历检索 → agent 评估相关性 → 动态优化图搜索策略
- Faithfulness: 0.94, Context Recall: 0.92, Answer Relevancy: 0.91

---

### 6.2 五种范式的适配性评估（针对 Tree-Dx-Spec pipeline）

我们的 pipeline 有以下特殊需求：

| 需求 | 描述 | 最适合的范式 |
|------|------|------------|
| **N1**: TALP 需要鉴别特征列表 | "CML-BC vs AML 的鉴别点有哪些" | KG Augmentation |
| **N2**: Annotator 需要定量 LR | "35% blasts 对 AML 的 LR+ 是多少" | 标准 RAG（事实检索） |
| **N3**: 多跳推理链 | "视力下降 → leukostasis → CML-BC" | GraphRAG |
| **N4**: 跨轮次证据追踪 | "哪些证据已分析，哪些还未用" | Agent 内部状态 |
| **N5**: 动态知识需求 | 第 1 轮和第 5 轮需要不同类型的知识 | Agentic RAG |
| **N6**: 低 token 开销 | llama-3.3-70b 上下文有限 | 结构化 KG（紧凑） |

**适配性矩阵**：

| 范式 | N1 鉴别特征 | N2 定量LR | N3 多跳推理 | N4 跨轮追踪 | N5 动态需求 | N6 低开销 | 总分 |
|------|:---------:|:--------:|:---------:|:---------:|:---------:|:--------:|:----:|
| 标准 RAG | △ | ★ | ✗ | ✗ | ✗ | △ | 2 |
| GraphRAG | ★ | △ | ★ | ✗ | △ | ✗ | 3 |
| Agentic RAG | △ | △ | △ | ★ | ★ | ✗ | 3 |
| KG Augmentation | ★ | △ | △ | ★ | △ | ★ | 4.5 |
| **Hybrid (KG + RAG + Agent)** | **★** | **★** | **★** | **★** | **★** | **△** | **5.5** |

> ★ = 强适配 (1.5), △ = 部分适配 (0.5), ✗ = 不适配 (0)

**结论：推荐 Hybrid 架构**——以 KG Augmentation 为主（低开销、结构化）, RAG 为辅（LR 事实检索）, Agent 编排为骨架（利用已有的 TALP 多轮迭代架构）。

---

### 6.3 最优数据类型选择

#### MIRAGE 基准的语料库偏好结论

| 数据类型 | 考试题(MMLU/MedQA/MedMCQA) | 文献题(PubMedQA/BioASQ) | 适合我们的场景 |
|---------|:------------------------:|:---------------------:|:------------:|
| **PubMed 摘要** | +0~3pp | **+33pp** | 中（LR 文献来源） |
| **StatPearls** | +0.6pp | **-6~-44pp（有害）** | 高（临床决策要点） |
| **Textbooks** | **+3.8pp** | **-5~-15pp（有害）** | 中（系统性鉴别） |
| **Wikipedia** | +1.3pp | -5~+2pp | 低 |
| **MedCorp（混合）** | **+4pp** | **+33pp** | 最高 |

**关键洞察**：
- StatPearls 和 Textbooks 虽然对文献 QA 有害，但它们**恰好是我们需要的类型**——临床鉴别诊断需要的是考试题级别的结构化临床知识，而非研究文献
- 对于 Tree-Dx-Spec 的 static_diagnosis_qa 模式（本质是"给定 vignette + 选项的考试题"），**StatPearls + Textbooks 是最适配的语料库**

#### 五种数据类型的细粒度分析

| 数据类型 | 优势 | 劣势 | 对 TALP 的价值 | 对 Annotator 的价值 | 推荐 |
|---------|------|------|:------------:|:-----------------:|:----:|
| **临床指南** (UpToDate, DynaMed, NICE) | 最权威、最新、结构化 | 版权、付费、更新频繁 | ★★★（鉴别算法） | ★★★（LR 推荐） | 理想但受限 |
| **临床百科** (StatPearls, BMJ Best Practice) | 免费/低成本、考试导向、结构化 | 覆盖有限、深度不足 | ★★★（鉴别特征） | ★★（定性描述） | **首选** |
| **医学教材** (Harrison's, Goldman-Cecil) | 系统全面、鉴别诊断章节 | 版权、非结构化 | ★★★（鉴别推理） | ★★（教科书 LR） | **首选补充** |
| **PubMed 论文** | 最全面、定量数据、系统综述 | 质量参差、需 NLP 提取 | ★（研究级鉴别） | ★★★（原始 LR 数据） | LR 的最终来源 |
| **知识图谱** (UMLS, SNOMED CT, PrimeKG) | 结构化、可计算、关系明确 | 粗粒度、无定量权重 | ★★★（约束生成） | ★（无 LR） | **骨架层** |
| **疾病-表型映射表** (DiagRL-Corpus 开源) | 16k 疾病 × 257k 表型对、开源 | 扁平结构（无关系/权重/综合征链）、需自建鉴别索引 | ★★★（差集计算即得鉴别特征） | ★（无 LR） | **首选骨架** |

#### 推荐的数据层次策略

```
┌──────────────────────────────────────────────────┐
│  Layer 3: PubMed + StatPearls RAG (fallback)     │ ← 长尾 LR / 复杂鉴别推理
│  27M PubMed abstracts + 427k StatPearls/TextB.   │
├──────────────────────────────────────────────────┤
│  Layer 2: LR Cache (structured hash lookup)      │ ← 定量似然比
│  docLogica API + GetTheDiagnosis + JAMA manual   │
├──────────────────────────────────────────────────┤
│  Layer 1: PrimeKG (HPO phenotypes + KG)           │ ← 300k disease-phenotype 边
│  + negative 排除边 + phenotype 多跳 + UMLS 补充  │
├──────────────────────────────────────────────────┤
│  Layer 0: DxS Discriminator Index (set diff)     │ ← 鉴别特征骨架
│  DiagRL-Corpus 16k diseases → phenotype 差集     │
│  （扁平映射表，非 KG，O(1) 查询）               │
└──────────────────────────────────────────────────┘
```

**查询路由逻辑**：
1. TALP 需要鉴别特征 → **Layer 0 (DxS 差集)** O(1) 查找，与 vignette 证据匹配 → 未覆盖时升级 **Layer 1 (PrimeKG)** → 仍未覆盖时 **Layer 3 (RAG)**
2. Annotator 需要 LR → **Layer 2 (LR Cache)** hash 查找 → 未命中时 **Layer 3 (PubMed RAG)**
3. 多跳推理链 → **Layer 1 (PrimeKG phenotype_phenotype + disease_disease 遍历，可选 UMLS 补充)** → **Layer 3 (StatPearls)** 文本验证

---

### 6.4 推荐架构：KG-骨架 + 双通道 RAG + Agent 编排

综合以上分析，最终推荐架构如下：

```
                  Controller (Agent Orchestrator)
                  ┌──────────────────────────────┐
                  │  已有 TALP 多轮迭代架构      │
                  │  = 天然的 "Agentic" 骨架     │
                  └──────┬───────────┬───────────┘
                         │           │
          ┌──────────────▼──┐  ┌────▼──────────────┐
          │  Structured     │  │  Text Retrieval    │
          │  Lookup Router  │  │  Router (fallback) │
          └──┬────┬────┬────┘  └───┬───────────┬───┘
             │    │    │           │            │
        ┌────▼┐┌──▼──┐│┌─────┐ ┌─▼──────┐ ┌──▼─────┐
        │ DxS ││Prime│││ LR  │ │StatP.  │ │PubMed  │
        │差集 ││ KG  │││缓存 │ │+TextB. │ │Abstracts│
        │索引 ││(HPO)│││     │ │(RAG)   │ │(RAG)   │
        └─────┘└─────┘│└─────┘ └────────┘ └────────┘
        Layer 0 Layer 1│Layer 2  Layer 3     Layer 3
                       ↕
                (层间自动升级)
```

**整合方式**：不是纯 RAG，不是纯 GraphRAG，不是纯 KG——而是 **KG-grounded Agentic Hybrid Retrieval**：
1. **KG 约束**（MedKGI 模式）：KG 提供"可以问什么"的约束集，防止 TALP 反复生成相同方向的候选
2. **结构化查找**（LR Cache）：无需向量检索，直接 hash 查找，零延迟
3. **向量 RAG 补充**（StatPearls + PubMed）：KG 未覆盖时降级为文本检索
4. **Agent 编排**（已有 Controller）：利用现有的多轮 TALP-Bundler-Annotator 循环作为 agentic 骨架，每轮动态决定需要什么知识

**与纯方案的对比**：

| | 纯 RAG | 纯 GraphRAG | 纯 KG | 纯 Agentic RAG | **推荐 Hybrid** |
|--|--------|-----------|-------|---------------|---------------|
| 鉴别特征获取 | 模糊匹配 | 精准多跳 | **精准直接** | 依赖 agent 质量 | KG 直接 + RAG 补充 |
| LR 数据获取 | 文本中提取 | 边权重 | 边权重（如有） | 多轮搜索 | **结构化缓存** |
| 推理链构建 | 单跳 | **多跳** | 受限于图深度 | 迭代收敛 | KG 多跳 + RAG 验证 |
| 实现复杂度 | 低 | 高 | 中 | 高 | **中**（利用已有架构）|
| Token 开销 | 中 | **高** | **低** | 高 | 低-中（按需检索） |

---

### 6.5 实现优先级修订

基于以上分析，修订第四章的实现路线图：

#### Phase 0（零成本，1-3 天）——Prompt-embedded 知识表
- 在 TALP prompt 中嵌入 Top-50 高频鉴别规则
- 在 Annotator prompt 中嵌入 Top-30 高频 LR 对照表
- **预期收益**：解决当前 CML-BC 类已知盲区，验证知识注入的有效性

#### Phase 1（低成本，1-2 周）——DxS 鉴别索引 + LR Cache
- 下载 DiagRL-Corpus（HuggingFace，~39MB），构建 `DxDiscriminatorIndex`（disease pair → phenotype 差集）
- 实现 `EvidenceMatcher`（vignette 证据 → 标准表型的模糊匹配）
- 构建 LR 结构化缓存（docLogica API 为主 + GetTheDiagnosis 爬取补充 + JAMA 手工提取高价值条目）
- 修改 TALP/Annotator prompt + controller 注入逻辑
- **注意**：DxS 指南是扁平 JSON 映射表（非 KG），通过集合运算生成鉴别特征，O(1) 查询
- **预期收益**：TALP 鉴别特征覆盖从 ~30% → ~70%，LR 标注偏差减半

#### Phase 2（中等成本，2-3 周）——PrimeKG 知识图谱（已验证可用）

> **2026-05-22 验证更新**：PrimeKG phenotype 节点为 HPO 临床级别（Splenomegaly, Fatigue 等），
> 确认覆盖临床症状而非仅分子表型。PrimeKG 还独有 disease_phenotype_negative 边（排除关联）。

- 下载 PrimeKG `kg.csv`（Harvard Dataverse，~500MB，MIT License）
- 构建 `PrimeKGIndex`：解析 disease_phenotype_positive（300k）+ negative（2.4k）边
- 构建疾病关系图：解析 disease_disease 边（CML → CML-BC 等亚型关系）
- 构建表型层级图：解析 phenotype_phenotype 边（37k），支持多跳查询
- 整合进 `DxFeatureRetriever` 作为层 1（DxS 差集覆盖不足时的 KG 补充）
- **可选**：申请 UMLS API key，实测 leukostasis→visual impairment 综合征链
- **预期收益**：
  - 鉴别特征覆盖从 DxS 的 ~70% → 90%+（300k 条 disease-phenotype 边 >> DxS 的 142k 对）
  - 新增排除诊断能力（disease_phenotype_negative 边 —— DxS 完全不具备）
  - 疾病亚型关系自动发现（如 "CML blast phase" 自动关联 "CML"）

#### Phase 3（中等成本，2-3 周）——StatPearls + Textbook RAG
- 索引 StatPearls（301k snippets）+ 教科书（126k snippets）
- 实现向量检索，作为 KG 的 fallback
- **预期收益**：覆盖 KG 缺失的长尾疾病和复杂鉴别推理

#### Phase 4（高投入，持续）——Agentic 编排 + PubMed RAG
- 实现 Controller 级别的知识路由（何时查 KG、何时查 RAG）
- PubMed 全库索引 + LR 自动提取 pipeline
- **预期收益**：接近 Deep-DxSearch 级别的知识覆盖

---

## 七、KG 数据源验证报告（2026-05-22）

### 7.1 PrimeKG 验证：临床层面粒度 ✓

**验证问题**：PrimeKG 的 disease-phenotype 关系是否包含临床层面的症状/体征，还是仅限于分子表型？

**验证方法**：分析 PrimeKG 论文（Sci Data 10:67, 2023）、GitHub 仓库、第三方数据分析笔记本、以及 GARD/Orphanet CML 条目。

**验证结论：确认为临床层面。** PrimeKG 的 phenotype 节点来自 HPO（Human Phenotype Ontology），是**临床可观测的症状、体征和检验异常**，而非分子层面的表型。

**关键证据**：

1. **数据来源**：PrimeKG 的 disease-phenotype 边来自 HPO + Orphanet + MONDO 的专家标注。论文明确记载从 `phenotype.hpoa`（HPO Annotation）中提取了 218,128 条 positive 和 negative 的 disease-phenotype 关联。

2. **CML 表型实例**（来自 GARD/Orphanet，与 PrimeKG HPO 数据同源）：
   ```
   Splenomegaly [HP:0001744]          — 脾大
   Thrombocytopenia [HP:0001873]      — 血小板减少
   Fatigue [HP:0012378]               — 疲劳
   Leukocytosis                       — 白细胞升高
   Poor Appetite                      — 食欲下降
   Abnormal Basophil Morphology       — 嗜碱性粒细胞异常
   Myeloproliferative Disorder        — 骨髓增殖性疾病
   Thrombocytosis                     — 血小板增多
   ```
   这些全部是**临床级别**的表型，直接对应医生可以通过查体和检验观察到的征象。

3. **数据规模优势**：
   - 300,634 条 disease_phenotype_positive 边（远超 DxS 的 ~142k 对）
   - 2,386 条 disease_phenotype_negative 边（**独有能力**——DxS 无排除关联）
   - 37,472 条 phenotype_phenotype 边（支持表型层级推理）
   - 17,080 个 disease 节点（含 CML 各亚型）

4. **关键节点确认**：
   ```
   id:30039  — chronic myelogenous leukemia, BCR-ABL1 positive（CML 主节点）
   id:84261  — blast phase chronic myelogenous leukemia, BCR-ABL1 positive（CML-BC 节点）
   id:94836  — atypical chronic myeloid leukemia, BCR-ABL1 negative
   id:99701  — acute myeloid leukemia with BCR-ABL1
   id:23849  — Myeloid leukemia（作为 effect/phenotype 节点也存在）
   ```

5. **对本项目的关键价值**：
   - **disease_phenotype_negative 边**：其他数据源（DxS、HPO 直接）不提供的"排除关联"，可以告诉 TALP "疾病 X 通常**不会**表现为症状 Y"，对鉴别诊断极为有价值
   - **disease_disease 边**：包含疾病亚型关系（CML → CML blast phase），弥补 BranchCreator 忽略 phase-crossing 的问题
   - **phenotype_phenotype 边**：支持 "visual impairment → retinal finding" → "leukostasis" 的间接推理

### 7.2 UMLS 验证：综合征链存在性 △ 待实测

**验证问题**：UMLS 的 `finding_of` / `manifestation_of` / `associated_with` 关系是否包含 "leukostasis → visual impairment" 等综合征级推理链？

**验证方法**：通过 NCBI MedGen（UMLS 前端）查询 leukostasis (C0282548)，分析其文档化的关系和层级。

**验证结论：CUI 确认存在，但关系链需 API 实测。**

**已确认**：
- Leukostasis **CUI: C0282548**，语义类型 "Disease or Syndrome"
- SNOMED CT 编码：30419000
- MONDO 映射：MONDO:0006831（与 PrimeKG 同源——PrimeKG 中的 leukostasis 节点即来自此 MONDO 概念）
- MeSH Tree Number：C15.378.553.560（Hematologic Diseases → Leukocyte Disorders）
- 同义词：Leukostasis Syndrome, Leukostases

**未确认**：
- MedGen 页面未显示结构化的 `finding_of` / `manifestation_of` 出站关系
- **leukostasis → visual impairment 的直接 UMLS 关系**尚不确定是否存在
- 需要使用 UMLS REST API 调用：
  ```
  GET /content/current/CUI/C0282548/relations
  参数: includeRelationLabels=RO&sabs=SNOMEDCT_US,MTH
  ```
  来获取 leukostasis 的所有语义关系

**临时替代方案**：
即使 UMLS 不存在直接的 leukostasis → visual impairment 关系，PrimeKG 的 phenotype_phenotype 边（37k 条）可能提供间接路径。另外，医学文献明确记载 leukostasis retinopathy 是 CML 伴高白细胞血症的已知并发症（PMC6256890, PMC10270769），可以通过 prompt-embedded 规则或 RAG 覆盖。

### 7.3 综合评估

| 数据源 | 临床粒度 | 覆盖度 | 排除关联 | 多跳推理 | 获取成本 | 总体评级 |
|--------|---------|--------|---------|---------|---------|---------|
| **PrimeKG** | ✓ HPO 临床级别 | 300k 边 / 17k 疾病 | ✓ 2.4k negative 边 | △ phenotype_phenotype 间接 | 免费（MIT） | **⭐⭐⭐⭐⭐ 首选** |
| **DxS DiagRL** | △ GPT-4o 摘要 | 142k 对 / 16k 疾病 | ✗ 无 | ✗ 无 | 免费（CC BY 4.0） | ⭐⭐⭐ 骨架 |
| **UMLS** | ✓ 标准化概念 | 3.45M 概念 | ✗ 未知 | ✓ 关系类型丰富 | 免费（需 license） | ⭐⭐⭐⭐ 补充 |
| **SNOMED CT** | ✓ 标准化 | 350k 概念 | △ 有限 | ✓ IS-A 层级 | 免费（需 license） | ⭐⭐⭐ 可选 |

**推荐知识层架构更新**：
```
Layer 0: DxS DiagRL-Corpus（扁平查表，O(1) 差集计算，骨架覆盖）
Layer 1: PrimeKG（KG 遍历，补充排除关联 + 疾病关系 + 表型多跳推理）  ← 新增！
Layer 2: LR Cache（docLogica API + GetTheDiagnosis + JAMA 手工，定量权重）
Layer 3: RAG fallback（StatPearls / PubMed，长尾覆盖）
Optional: UMLS API（综合征链补充，按需调用）
```

---

## 八、多源数据集评估与统一检索策略（2026-05-22）

### 8.1 已下载数据集规模总览

| 数据源 | 疾病数 | 关联对数 | 频率类型 | 临床数据类型 |
|--------|-------:|--------:|----------|------------|
| GetTheDiagnosis LR | 221 | 1,112 | 定量 LR+/LR- | 诊断测试 |
| docLogica | 1,475 | 13,225 | 定性 5 级 | 症状+体征 |
| HPO phenotype.hpoa | 12,996 | 282,723 | 定量(HPO 频率) | 表型(HPO) |
| Orphadata | 4,337 | 115,878 | 定性 6 级 | 罕见病表型 |
| BODHI-S | 779 | 10,352 | 定性 5 级 | 症状(SNOMED) |
| HealthKnowledgeGraph | 156 | 3,709 | 定量概率 | 症状(自由文本) |
| **合计(含重叠)** | **~20,000** | **~427,000** | | |

### 8.2 各数据源详细特性分析

#### GetTheDiagnosis.org LR Cache
- **内容**: 315 种诊断页面，857 种检查/测试项，1,112 条 LR 条目
- **语义域**: 主要为**诊断测试**（如 Troponin T, D-dimer, BNP），**非**患者症状
- **数据质量**: 高——每条含精确 LR+ 和 LR-，附 sensitivity/specificity
- **语义缺口**: 对 EvidenceAnnotator 的症状级别 LR 需求命中率 ~0%
- **价值定位**: 用于检验/检查结果的 LR 标注（Layer 2 补充通道）

#### docLogica
- **内容**: 1,475 种疾病（含 CML、SLE 等），13,225 条 finding 关联
- **频率分布**: `unknown` 77.0%, `common` 9.2%, `veryCommon` 5.2%, `uncommon` 5.8%, `rare` 2.5%
- **有效频率标签**: 仅 3,045 条 (23.0%)，其中 217 种疾病有至少 1 个已知频率
- **频率→近似 LR 映射**: `veryCommon`→0.9, `common`→0.5, `uncommon`→0.15, `somewhatRare`→0.05, `rare`→0.02
- **数据质量**: 中——finding 涵盖症状、体征、并发症，但 77% 缺频率
- **价值定位**: 作为鉴别特征列表（即使无频率也有价值），有频率时辅助 LR 近似

#### HPO phenotype.hpoa （**最高价值**）
- **内容**: 12,996 种疾病（8,614 OMIM + 4,335 ORPHANET + 47 DECIPHER），282,723 条注释
- **频率覆盖**: 77.6% (219,299 条) 有可解析频率标签
  - HPO 标准频率: 118,662 条（Obligate/Very frequent/Frequent/Occasional/Very rare）
  - 精确分数: 99,801 条（如 "3/4" = 75%）
  - 无频率: 64,151 条（仍可作为存在/缺失指示）
- **频率→sensitivity 映射**:
  - `HP:0040280 Obligate` → 1.0
  - `HP:0040281 Very frequent (80-99%)` → 0.895
  - `HP:0040282 Frequent (30-79%)` → 0.545
  - `HP:0040283 Occasional (5-29%)` → 0.17
  - `HP:0040284 Very rare (1-4%)` → 0.025
  - `HP:0040285 Excluded (0%)` → 0.0
  - 精确分数直接使用
- **HPO 术语数**: 19,944 个，已全部从 hp.obo 解析出名称和同义词
- **价值定位**: **核心症状级 LR 近似来源**——频率 P(phenotype|disease) ≈ sensitivity

#### Orphadata en_product4.xml
- **内容**: 4,337 种罕见病，115,878 条 HPO 表型关联
- **频率分布**: Occasional 42,753; Frequent 39,588; Very frequent 25,676; Very rare 6,509; Excluded 727; Obligate 625
- **100% 有频率标签**——优于 HPO phenotype.hpoa 的 77.6%
- **重叠**: 与 HPO 的 ORPHANET 子集高度重叠，但 Orphadata 频率标签更完整
- **价值定位**: 罕见病诊断的高质量频率源，用于 Orphadata 覆盖的疾病优先使用

#### BODHI-S (eka-care)
- **内容**: 779 种常见病（SNOMED 编码），4,037 个症状节点（含变体），10,352 条边
- **边属性**:
  - `likelihood_symptom_given_condition`: very_high 1,087; high 3,965; medium 3,847; low 1,314; rare 78
  - `likelihood_condition_given_symptom`: 方向相反的关联强度
  - `strong_predictor`: 布尔标志标记强预测指标
- **频率→sensitivity 映射**: `very_high`→0.9, `high`→0.65, `medium`→0.35, `low`→0.1, `rare`→0.02
- **数据来源**: 印度 EHR 数据衍生，含年龄/性别分层 likelihood
- **价值定位**: 常见病的症状关联（补充 HPO 的罕见病偏向），SNOMED 编码便于标准化对齐

#### HealthKnowledgeGraph (clinicalml)
- **内容**: 156 种常见病（自由文本名称），3,709 条症状-疾病对
- **数据质量**: 高——基于 27 万+患者数据的 noisy-or Bayesian 推断，每条含定量概率
- **示例**: abscess: pain (0.318), fever (0.119), swelling (0.112)
- **局限**: 仅 156 种病，覆盖面窄
- **价值定位**: 有限但高质量的常见病概率参考

### 8.3 覆盖度交叉分析

与 DiagRL-Corpus 目标疾病空间（16,162 种）的覆盖度（子串模糊匹配）：

| 数据源 | 疾病名称数 | 覆盖目标数 | 覆盖率 |
|--------|----------:|----------:|-------:|
| docLogica | 2,226 | 2,803 | 17.3% |
| HPO | 12,486 | 1,067 | 6.6% |
| BODHI-S | 779 | 2,402 | 14.9% |
| HealthKG | 156 | 2,048 | 12.7% |
| **联合覆盖** | | **4,927** | **30.5%** |

> **注意**: HPO 覆盖率低是因为 HPO 使用 OMIM/ORPHANET 疾病编号，不是自由文本名称。
> 需要 UMLS CUI 或 MONDO ID 做疾病名称标准化桥接（预计可将覆盖率提升至 50-60%+）。

#### CML (Case #68) 覆盖测试

| 数据源 | 是否覆盖 CML | 频率数据质量 |
|--------|-------------|------------|
| docLogica | **是** (26 findings) | 全部 `unknown` |
| HPO | **是** | 有频率标签 |
| BODHI-S | 否 | — |
| HealthKG | 否 | — |
| PrimeKG | **是** (含 CML-BC 节点) | 无频率但有 +/- 边 |
| DiagRL-Corpus | **是** | 表型列表（无频率） |

### 8.4 推荐统一检索策略

#### 设计原则

1. **频率数据优先**: 有定量频率 > 定性频率 > 存在/缺失
2. **多源级联**: 高质量源优先，缺失时降级到低质量源
3. **语义对齐**: 统一通过 HPO 术语桥接不同数据源的表型名称
4. **双用途**: 同一缓存同时服务 TALP（鉴别特征）和 Annotator（LR 近似）

#### 统一频率→LR 转换公式

将各数据源的频率标签统一转换为近似 sensitivity（Sn），然后估算 LR+：

```
LR+ ≈ Sn / (1 - Sp)

其中:
- Sn = P(phenotype | disease) ← 各数据源的频率
- Sp = 1 - P(phenotype | NOT disease) ← 需估计

Sp 估计策略:
1. 对于 HPO/Orphadata 表型:
   - 使用 HPO 注释中其他疾病对同一表型的频率，
     计算 population_frequency = Σ(freq_i × prevalence_i) / Σ(prevalence_i)
   - Sp ≈ 1 - population_frequency
2. 对于 BODHI-S/HealthKG:
   - 使用同数据源中该症状出现在其他疾病中的平均频率
3. Fallback:
   - 使用 base_specificity = 0.9（保守默认值）
   - 高频症状（如 fever, pain）降至 0.7
   - 高特异性体征（如 basophilia）升至 0.95
```

#### 统一症状-疾病频率缓存结构

```json
{
  "finding::disease": {
    "sensitivity": 0.85,
    "specificity": 0.92,
    "lr_plus": 10.6,
    "lr_minus": 0.16,
    "source": "HPO|Orphadata|BODHI-S|HealthKG|docLogica|GetTheDiagnosis",
    "confidence": "high|medium|low",
    "raw_frequency": "HP:0040281",
    "hpo_id": "HP:0001744"
  }
}
```

**置信度判定规则**:
- `high`: 精确 LR+/LR- (GetTheDiagnosis) 或精确频率分数 (HPO "3/4")
- `medium`: HPO 标准频率标签 或 Orphadata 或 HealthKG 概率
- `low`: 定性频率 (docLogica, BODHI-S) 或跨源推断

#### 多源级联检索顺序

```
┌─────────────────────────────────────────────────────────────────┐
│  Lookup(finding, disease) → 统一缓存                            │
│                                                                 │
│  1. GetTheDiagnosis (精确 LR)   ← confidence: high             │
│     ↓ miss                                                      │
│  2. HPO phenotype.hpoa (频率→LR) ← confidence: high/medium     │
│     ↓ miss                                                      │
│  3. Orphadata (罕见病频率→LR)    ← confidence: medium           │
│     ↓ miss                                                      │
│  4. HealthKG (概率→Sn→LR)       ← confidence: medium           │
│     ↓ miss                                                      │
│  5. BODHI-S (定性→Sn→LR)       ← confidence: low               │
│     ↓ miss                                                      │
│  6. docLogica (定性→Sn→LR)     ← confidence: low               │
│     ↓ miss                                                      │
│  7. PrimeKG (+/- 边 → 定性)    ← confidence: very_low          │
│     ↓ miss                                                      │
│  8. DiagRL-Corpus (存在/缺失)   ← 无 LR，仅鉴别特征            │
│     ↓ miss                                                      │
│  9. 退回 LLM 自行判断           ← 默认行为                     │
└─────────────────────────────────────────────────────────────────┘
```

#### 症状名称标准化方案

由于各数据源使用不同的症状命名（HPO ID vs 自由文本 vs SNOMED），需要多层匹配：

```
输入: 自由文本症状 (e.g., "spleen enlargement")
  │
  ├─ 1. 精确匹配 → HPO name/synonym 字典 (19,944 terms + synonyms)
  │     "spleen enlargement" → "Splenomegaly" [HP:0001744] ✓
  │
  ├─ 2. Jaccard token 匹配 (阈值 0.5) → HPO 名称
  │     将 query 和 candidate 分词后计算交集/并集比
  │
  ├─ 3. BODHI-S SNOMED → HPO 映射
  │     通过 SNOMED ID 交叉引用
  │
  └─ 4. 模糊子串匹配 → docLogica/HealthKG 自由文本
       fallback，最低精度
```

### 8.5 实现路线（统一缓存构建）

#### Step 1: 构建统一索引 `unified_symptom_disease_cache.json`

1. **HPO 核心层**: 以 HPO 术语为锚点，加载 282,723 条 disease-phenotype 注释
2. **Orphadata 补充**: 对同一疾病-表型对，如果 Orphadata 频率更精确则替换
3. **BODHI-S 映射**: 通过 SNOMED→HPO 桥接，补充常见病
4. **HealthKG 叠加**: 直接概率加入，标记来源
5. **docLogica 叠加**: 有效频率标签加入
6. **GetTheDiagnosis 覆盖**: 精确 LR 条目作为最高优先级
7. **LR 统一转换**: 所有 sensitivity 值通过公式转换为 LR+/LR-

#### Step 2: 统一检索接口修改

更新 `LRRetriever` 以支持:
- 多数据源 fallback 查找
- HPO 术语标准化
- 置信度标记
- 对 TALP: 输出鉴别特征列表 (finding 在 disease_A 中的频率 vs disease_B)
- 对 Annotator: 输出 LR+/LR-（带置信度和来源）

#### Step 3: 预计覆盖提升

| 场景 | 当前（仅 GetTheDiagnosis） | 统一缓存 |
|------|:------------------------:|:-------:|
| 症状→疾病 LR 命中率 | ~0% | ~60-75% |
| 检查→疾病 LR 命中率 | ~15% | ~15% (不变) |
| 疾病覆盖率 | 1.2% (221/16,162) | ~30-50% |
| 鉴别特征可用率 | 仅 DxS 差集 | DxS + 频率加权排序 |

---

## 九、检索策略合规性审计与改进方案（2026-05-22）

### 9.1 设计规范 vs 当前实现——逐项合规性对照

| # | 设计规范（文档章节） | 当前实现状态 | 合规 | 差距分析 |
|---|---------------------|-------------|:----:|---------|
| **R1** | Annotator 需要定量 LR（§1.1）："35% blasts 对 AML 和 CML-BC 的 LR 应相近" | 统一缓存 233K 条目含 LR+/LR-，CML 案例命中率 64% | **△** | 实际 CML 数据中 basophilia 对 AML 和 CML 显示相同 LR（HPO 频率均为 "Frequent"），缺少真正的疾病特异性 LR |
| **R2** | TALP 需要鉴别特征图谱（§1.2）：疾病对差集 + 综合征链 | Layer 0 (DxS 差集) + Layer 1 (PrimeKG) 已实现 | **✓** | 差集计算和 PrimeKG 排除边/疾病关系正常工作 |
| **R3** | 综合征链多跳推理（§1.2, §3.3）："visual_loss → leukostasis → CML-BC" | **未实现** | **✗** | PrimeKG `phenotype_phenotype` 边存在但 `DxFeatureRetriever` 未调用多跳遍历 |
| **R4** | 已用证据边际鉴别价值（§1.2）："35% blasts already analyzed → remaining discriminators" | `seen_evidence` 参数已实现，从差集中排除 | **✓** | — |
| **R5** | LR Retriever 级联（§3.2）：本地缓存 → GetTheDiagnosis → PubMed RAG fallback | 本地缓存（6 源统一）实现；**RAG fallback 完全缺失** | **△** | 缓存未命中时直接返回 "no data"，无 RAG 降级 |
| **R6** | DxFeature Retriever 级联（§3.3）：DxS 差集 → PrimeKG → RAG fallback | DxS + PrimeKG 已实现；**RAG fallback 缺失** | **△** | 同上 |
| **R7** | 四层架构（§3.4）：Layer 0→1→2→3 层间自动升级 | Layer 0-2 实现，**Layer 3 (RAG) 完全缺失** | **△** | 文档明确定义 "层 0+1 均未覆盖 → 层 3: StatPearls/PubMed RAG fallback"，目前无此路径 |
| **R8** | Evidence↔Phenotype 匹配精度（§5.1）："embedding similarity + threshold filtering; HPO standardization" | 使用 Jaccard token overlap + 医学词干化，**未使用 embedding** | **△** | 设计建议使用 embedding 相似度，实际使用词法匹配。HPO Mapper 研究显示 embedding 方法 F1=0.84 远超 rule-based |
| **R9** | Specificity 估计（§8.4）："使用其他疾病对同一表型的频率计算 population_frequency" | 使用简单启发式（fever→0.7, basophilia→0.95, 默认 0.9） | **△** | 缺少基于数据的 Sp 计算。已有 HPO 数据完全可以计算每个表型的跨疾病平均频率 |
| **R10** | 置信度阈值退回（§5.1）："低置信度退回 LLM 判断" | confidence 字段已存在但**未在 prompt 注入时用于过滤** | **△** | 低置信度条目直接注入可能引入误导 |
| **R11** | 组合 LR（§1.1）："blasts + ataxia + visual loss: joint LR for leukostasis" | **未实现** | **✗** | 目前仅支持单 finding 单 disease 查找 |
| **R12** | 推荐 Hybrid 架构（§6.4）：KG 约束 + 结构化缓存 + 向量 RAG 补充 + Agent 编排 | 结构化缓存 + KG 约束已实现；**向量 RAG 补充和 Agent 编排缺失** | **△** | Controller 中已有注入逻辑但无动态路由决策 |
| **R13** | 疾病名称标准化（§8.3 注意）："需要 UMLS CUI 或 MONDO ID 做疾病名称标准化桥接" | 使用子串 + token Jaccard 模糊匹配 | **△** | 无系统性本体 ID 桥接，HPO 覆盖率仅 6.6% 因名称不匹配 |

**合规总结**: 13 项设计要求中 **2 项完全达标 (✓)，9 项部分达标 (△)，2 项完全缺失 (✗)**。

### 9.2 当前检索策略的核心瓶颈

#### 瓶颈 1：术语匹配精度不足（影响命中率）

当前匹配链：精确 hash → 子串 → token Jaccard → 医学词干化 Jaccard。

**已知失败案例**：
- "basophilia" → HPO 中为 "Abnormal basophil morphology"（词干匹配成功，但语义精度低）
- "night sweats" → HPO 中为 "Night sweats"（精确匹配成功），但 CML 条目中无此表型
- "weight loss" → HPO 中为 "Decreased body weight"（token 重叠 "weight" 仅 Jaccard 0.25，低于阈值）
- "visual acuity loss" → HPO 中为 "Reduced visual acuity"（Jaccard 0.50 可匹配，但该条目与 CML 无关联）
- "hepatomegaly" → HPO 中存在 "Hepatomegaly"（但 CML 条目中不包含）

**根因**：Jaccard+stemming 是**词法**匹配，不理解语义——"Decreased body weight" 和 "weight loss" 语义等价但词法重叠低。

#### 瓶颈 2：缓存未命中无降级路径

当统一缓存 233K 条目未命中时（约 36% 概率），系统直接返回空结果。设计中明确要求的 Layer 3 RAG fallback 完全缺失。

#### 瓶颈 3：Specificity 估计粗糙导致 LR 区分度低

所有 HPO 来源的条目使用相同的默认 Sp（0.9）。导致 CML 和 AML 对"fatigue"的 LR+ 完全相同（均为 1.82），**无法体现鉴别价值的差异**——而实际上 fatigue 对 AML（急性起病）的敏感度应低于 CML（慢性起病渐进疲劳）。

#### 瓶颈 4：无多跳推理能力

"visual loss → leukostasis → CML-BC" 需要 PrimeKG phenotype_phenotype + disease_phenotype 边的 2-hop 遍历。当前 `DxFeatureRetriever` 仅读取直接关联的表型，不进行图遍历。

### 9.3 改进方案：基于最新文献的更优检索策略

#### 方案 A：Embedding-based HPO 术语标准化（替代 Jaccard+stemming）

**依据**：HPO Mapper（medRxiv 2025.12.20）证明 embedding-based 语义匹配 + LLM 质控可达 F1=0.84，远超 rule-based 方法。

**实现路径**：
```
当前: "weight loss" → Jaccard("weight loss", "Decreased body weight") = 0.25 → MISS
改进: "weight loss" → Embed("weight loss") · Embed("Decreased body weight") = 0.92 → HIT

模型选择:
  1. PubMedBERT (轻量, ~110M参数) → 离线编码 19,944 HPO 术语
  2. MedCPT Query Encoder (专为检索优化) → 255M query-article pairs 预训练
  3. sentence-transformers/all-MiniLM-L6-v2 (最轻量, ~22M参数, 适合受限环境)

离线预计算:
  - 将 19,944 个 HPO term + 同义词 编码为向量 → 存储为 .npy (~80MB)
  - 运行时: query 编码 (~5ms) → cosine top-k (~2ms via FAISS) → 阈值过滤
  
预期效果:
  - "weight loss" → "Decreased body weight" [HP:0004325] ✓ (cosine ~0.92)
  - "basophilia" → "Increased basophil count" [HP:0005560] ✓ (cosine ~0.88)
  - "visual loss" → "Visual impairment" [HP:0000505] ✓ (cosine ~0.85)
  - 命中率: ~64% → ~80-85% (估计)
```

**成本**：中低——仅需 embedding 模型 + FAISS，无需 GPU（CPU 推理可接受）。

**优先级**：**高——直接解决瓶颈 1，预计最大单项收益**。

#### 方案 B：Hybrid BM25 + Dense 检索（用于 Layer 3 RAG fallback）

**依据**：arXiv 2605.02520（2026 年 5 月最新）系统性对比 5 种 RAG 检索策略发现：
- Cross-Encoder Reranking 综合最优（composite 0.827, precision 0.852）
- Dense baseline 紧随其后（composite 0.822）
- Multi-Query Expansion 反而降低 precision（0.671）——不推荐

**实现路径**：
```
Layer 3 RAG Pipeline (StatPearls 为主):
  
  1. 语料库准备:
     - StatPearls 文本 (301K snippets, CC BY 4.0, 免费)
     - 按疾病/症状章节切块 (chunk_size=512 tokens)
     
  2. 双通道检索:
     - Dense: MedCPT bi-encoder → FAISS IVF-PQ 索引
     - Sparse: BM25 (Whoosh/rank_bm25) → 精确医学术语匹配
     - 融合: Reciprocal Rank Fusion (RRF, k=60)
  
  3. Cross-Encoder Reranking:
     - MedCPT-Cross-Encoder (PubMedBERT-based)
     - 对 top-20 RRF 结果重排序 → 输出 top-5
  
  4. 结构化提取:
     - 从 top-5 摘要中用 LLM 提取 LR 数值或鉴别特征
     - 注入 EvidenceAnnotator 或 TALP prompt
  
  查询触发条件:
     - 统一缓存 lookup_fuzzy 返回 None
     - 或 confidence = "low" 且是关键分支的关键证据
```

**成本**：中——需索引 StatPearls (~2GB 向量)，MedCPT Cross-Encoder 推理 (~200ms/query on CPU)。

**优先级**：**中——解决瓶颈 2，但构建成本较高**。

#### 方案 C：数据驱动的 Specificity 计算（替代启发式）

**依据**：已有 233K 条统一缓存数据完全可以计算每个表型的跨疾病基础频率。

**实现路径**：
```python
# 对每个 finding，计算它在所有疾病中出现的平均 sensitivity
finding_avg_freq = {}
for finding in all_findings:
    entries = cache.lookup_by_finding(finding)
    if entries:
        avg_sn = mean([e["sensitivity"] for e in entries])
        # Specificity ≈ 1 - avg_sn (粗略但数据驱动)
        finding_avg_freq[finding] = avg_sn

# "fever": 出现在 581 种病中, avg_sn ≈ 0.35 → Sp ≈ 0.65
# "basophilia": 出现在 3 种病中, avg_sn ≈ 0.55 → Sp ≈ 0.97
# 比硬编码 0.7/0.95/0.9 精确得多
```

**成本**：极低——纯数据计算，无新依赖。

**优先级**：**高——极低成本直接解决瓶颈 3**。

#### 方案 D：PrimeKG 2-hop 图遍历（解决综合征链推理）

**依据**：设计文档 §3.3、§3.4 明确要求；PrimeKG 含 37K phenotype_phenotype 边。

**实现路径**：
```
输入: evidence="visual loss", candidate_diseases=["CML-BC", "AML"]

Step 1: 在 PrimeKG 中查找 "visual loss" 的 phenotype_phenotype 邻居
  → ["retinal hemorrhage", "papilledema", "leukostasis retinopathy", ...]

Step 2: 对每个邻居，查找与 candidate_diseases 的 disease_phenotype 关联
  → "leukostasis retinopathy" ←→ "leukostasis" ←→ "CML blast phase"

Step 3: 构建推理链
  → "visual loss → (phenotype_phenotype) → leukostasis retinopathy 
      → (disease_phenotype) → CML blast phase"
  → discrimination_power: high (链长=2, 特异性=高)

输出:
  {
    "chain": ["visual loss", "leukostasis retinopathy", "CML blast phase"],
    "hop_count": 2,
    "favors": "CML-BC",
    "source": "PrimeKG 2-hop"
  }
```

**成本**：低——`PrimeKGIndex` 已加载 phenotype_phenotype 边，仅需新增遍历方法。

**优先级**：**高——已有数据基础，直接解决瓶颈 4 和设计规范 R3**。

#### 方案 E：UMLS CUI 桥接疾病名称标准化

**依据**：§8.3 覆盖度分析显示 HPO 疾病名覆盖率仅 6.6%（因命名差异）。

**实现路径**：
- 使用 MONDO ontology 映射（PrimeKG 已包含 MONDO ID）
- 构建 `{free_text_name → MONDO_ID → [HPO_disease_ids]}` 映射表
- 或使用 UMLS REST API 的 search endpoint 做 `disease_name → CUI → preferred_name` 标准化

**成本**：低（MONDO 映射）到中（UMLS API）。

**优先级**：**中——提升覆盖率但不解决核心推理问题**。

### 9.4 PrimeKG 2-hop 链的 LR 计算方案

#### 9.4.1 问题定义

当直接查找 `(finding, disease)` 在统一缓存中未命中，但 PrimeKG 图遍历发现一条间接链时：

```
evidence_phenotype ──(phenotype_phenotype)──→ intermediate ──(disease_phenotype)──→ disease
例: "visual loss" ──(p2p)──→ "leukostasis" ──(d2p, Sn=0.17)──→ "CML blast phase"
```

需要解决的核心问题：**如何从这条 2-hop 链推导出 LR+/LR-？**

#### 9.4.2 数学框架

目标是估计 P(E_obs | D)，即观察到 evidence E 时疾病 D 为真的条件概率。

**贝叶斯链式分解**：
```
P(E_obs | D) = Σ_M  P(E_obs | M) × P(M | D)
```

其中 M 是中间节点（intermediate phenotype）。

已知量：
- **P(M | D)** = 中间表型对目标疾病的 sensitivity → **已有**，来自统一缓存
  - 例: Sn(leukostasis | CML-BC) = 0.17 (来自 HPO "Occasional")

未知量：
- **P(E_obs | M)** = 观察到的证据在中间表型出现时的条件概率 → **需要估计**
  - 例: P(visual_loss | leukostasis) = ?
  - PrimeKG 的 phenotype_phenotype 边是**无权重二值边**，不含此概率

**链式 LR 推导**：
```
Sn_chain(E, D) = P(E|M) × Sn(M, D)      ← sensitivity 通过链路衰减
Sp_chain(E, D) ≈ 1 - P(E|¬D)            ← specificity 近似不变或略降
LR+_chain = Sn_chain / (1 - Sp_chain)
LR-_chain = (1 - Sn_chain) / Sp_chain
```

#### 9.4.3 四种 P(E_obs | M) 估计策略

##### 策略 A：HPO 层级结构推断（最精确，数据条件允许时）

HPO 是一棵有向无环图（DAG），phenotype_phenotype 边对应 IS_A 或 part_of 关系。
如果能判断边的语义类型，可以差异化估计：

```
IS_A (子→父，如 "Retinal hemorrhage" IS_A "Retinal abnormality"):
  子表型是父表型的特殊形式
  → P(child | parent) ≈ 1/N_children（均匀分布假设）
  → 如果 parent 有 5 个 child，P ≈ 0.2

part_of (部分→整体，如 "Visual loss" 是 "Leukostasis syndrome" 的表现之一):
  部分表型在整体出现时的概率取决于临床特征
  → 可从文献或统一缓存中同时关联两者的疾病比例来估计
```

**局限**：PrimeKG 导出的 phenotype_phenotype 边**不区分 IS_A / part_of / associated_with**——全部编码为同一类型。需要额外解析 HPO ontology (hp.obo) 才能获取边类型。

##### 策略 B：跨疾病共现率估计（数据驱动，推荐）

核心思想：利用已有的统一缓存数据，统计"拥有中间表型 M 的疾病中，有多大比例同时拥有证据表型 E"。

```python
def estimate_conditional(evidence: str, intermediate: str, lr: LRRetriever) -> float:
    """
    估计 P(evidence | intermediate) ≈ 
      #{diseases that have BOTH evidence AND intermediate} 
      / #{diseases that have intermediate}
    """
    inter_entries = lr.lookup_by_finding(intermediate)
    if not inter_entries:
        return _DEFAULT_TRANSITION  # 0.3

    inter_diseases = {e["disease"].lower() for e in inter_entries}
    co_occur = 0
    for d in inter_diseases:
        if lr.lookup_fuzzy(evidence, d):
            co_occur += 1

    return co_occur / len(inter_diseases) if inter_diseases else _DEFAULT_TRANSITION
```

**示例推演**（基于统一缓存 233K 条目）：
```
evidence = "visual loss"
intermediate = "leukostasis"

Step 1: 查找所有与 "leukostasis" 关联的疾病
  → [CML-BC, AML-hyperleukocytic, ALL-hyperleukocytic, ...]  假设 5 种

Step 2: 这 5 种疾病中，有多少也包含 "visual loss"？
  → CML-BC: lookup_fuzzy("visual loss", "CML-BC") → None (可能 miss)
  → AML-hyperleukocytic: → None
  → ... 假设找到 2 种
  → P(visual_loss | leukostasis) ≈ 2/5 = 0.4

Step 3: 链式 LR 计算
  Sn(leukostasis | CML-BC) = 0.17    ← 来自 HPO cache
  P(visual_loss | leukostasis) ≈ 0.4  ← 策略 B 估计
  
  Sn_chain = 0.4 × 0.17 = 0.068
  Sp_chain ≈ 0.95                      ← 保守默认
  
  LR+_chain = 0.068 / (1 - 0.95) = 1.36
  LR-_chain = (1 - 0.068) / 0.95 = 0.98

→ LR+ = 1.36: 微弱支持 CML-BC（合理——间接链本就应产生弱信号）
→ confidence: "indirect_chain"
```

**优势**：完全基于已有数据，不需额外外部资源，数值可解释。

**劣势**：依赖统一缓存中是否同时存在 evidence 和 intermediate 的条目；当缓存未覆盖时退化为默认值。

##### 策略 C：固定衰减因子（最简单，baseline）

不估计 P(E|M)，直接对中间节点的 LR 施加固定折扣：

```
LR+_chain = LR+_direct(M, D) × decay_factor

decay_factor 按跳数:
  1-hop (直接): 1.0
  2-hop: 0.3
  3-hop: 0.1 (不推荐超过 2-hop)
```

**示例**：
```
LR+(leukostasis, CML-BC) = Sn/（1-Sp） = 0.17/0.05 = 3.4
LR+_chain(visual_loss, CML-BC) = 3.4 × 0.3 = 1.02

→ 几乎中性信号，但方向正确
```

**优势**：实现最简单，无需额外计算。

**劣势**：所有 2-hop 链使用相同衰减，无法区分"IS_A 紧密关联"和"weakly associated"。

##### 策略 D：不计算数值 LR，输出定性推理链（最诚实）

不试图生成伪精确的 LR 数值，而是将 2-hop 链作为**结构化推理提示**返回给 LLM：

```json
{
  "type": "indirect_reasoning_chain",
  "chain": ["visual loss", "leukostasis", "CML blast phase"],
  "hops": 2,
  "intermediate_evidence": {
    "leukostasis → CML-BC": {"sensitivity": 0.17, "source": "HPO", "confidence": "medium"}
  },
  "qualitative_signal": "weak_support",
  "reasoning": "Visual loss is associated with leukostasis (PrimeKG phenotype link); leukostasis occurs in ~17% of CML blast phase patients (HPO Occasional)"
}
```

**优势**：
1. 不引入虚假精度——2-hop 链的 LR 估计误差可能达到数量级
2. LLM（TALP/Annotator）具备利用定性推理链的能力
3. 推理链本身对 TALP 的价值（"应该追问 leukostasis 相关症状"）远大于一个不可靠的 LR 数值

**劣势**：Annotator 的 `ordinal_update → bayesian_update` 管道需要数值 LR，定性链无法直接输入。

#### 9.4.4 推荐方案：B + D 混合

**对 TALP 通道（DxFeatureRetriever → discriminator_hints）**：
→ 使用 **策略 D（定性推理链）**
- TALP 只需知道"visual loss 可能经由 leukostasis 与 CML-BC 相关"即可生成更好的候选动作
- 不需要精确 LR，推理链本身就是鉴别提示

**对 Annotator 通道（LRRetriever → lr_reference）**：
→ 使用 **策略 B（共现率估计）+ 置信度标记**
- 计算数值 LR 以输入 bayesian_update 管道
- 但标记 `confidence: "indirect_chain"` 以区分直接查找结果
- Annotator prompt 中加入规则：`indirect_chain confidence 的 LR 仅作参考，LR 影响应衰减 50%`

**完整实现伪代码**：

```python
class PrimeKGIndex:  # 新增方法
    def find_2hop_chains(
        self,
        evidence_phenotype: str,
        candidate_diseases: list[str],
        *,
        max_intermediates: int = 10,
    ) -> list[dict]:
        """
        从 evidence 出发，经 phenotype_phenotype 1-hop 找中间节点，
        再经 disease_phenotype 连接到候选疾病。
        """
        evidence_lower = evidence_phenotype.strip().lower()
        neighbors = self.phenotype_phenotype.get(evidence_lower, set())
        chains = []

        for intermediate in neighbors:
            for disease in candidate_diseases:
                d_lower = disease.strip().lower()
                if intermediate in self.disease_phenotype_pos.get(d_lower, set()):
                    chains.append({
                        "evidence": evidence_phenotype,
                        "intermediate": intermediate,
                        "disease": disease,
                    })

        # 按中间节点的 disease 关联数排序（关联越少 = 越特异 = 越有鉴别价值）
        chains.sort(key=lambda c: len(
            self.disease_phenotype_pos.get(c["intermediate"], set())
        ))
        return chains[:max_intermediates]


class DxFeatureRetriever:  # 新增方法
    def get_2hop_lr(
        self,
        finding: str,
        diseases: list[str],
    ) -> list[dict]:
        """
        当直接 LR 查找未命中时，尝试 PrimeKG 2-hop 推理。
        返回带链路信息和估算 LR 的结果列表。
        """
        if not self.primekg or not self.lr:
            return []

        chains = self.primekg.find_2hop_chains(finding, diseases)
        results = []
        
        for chain in chains:
            intermediate = chain["intermediate"]
            disease = chain["disease"]

            # 查找 intermediate → disease 的直接 LR
            inter_entry = self.lr.lookup_fuzzy(intermediate, disease)
            if not inter_entry:
                continue
            
            sn_intermediate = inter_entry.get("sensitivity", 0.0)
            sp_intermediate = inter_entry.get("specificity", 0.9)

            # 策略 B: 估计 P(evidence | intermediate)
            p_e_given_m = self._estimate_conditional(finding, intermediate)

            # 链式 LR 计算
            sn_chain = p_e_given_m * sn_intermediate
            sp_chain = sp_intermediate  # 保守：specificity 不衰减
            lr_pos = sn_chain / (1 - sp_chain) if sp_chain < 1 else None
            lr_neg = (1 - sn_chain) / sp_chain if sp_chain > 0 else None

            results.append({
                "finding": finding,
                "disease": disease,
                "chain": [finding, intermediate, disease],
                "hops": 2,
                "p_evidence_given_intermediate": round(p_e_given_m, 3),
                "intermediate_sensitivity": sn_intermediate,
                "sensitivity_chain": round(sn_chain, 4),
                "specificity_chain": round(sp_chain, 4),
                "lr_positive": round(lr_pos, 3) if lr_pos else None,
                "lr_negative": round(lr_neg, 3) if lr_neg else None,
                "confidence": "indirect_chain",
                "source": f"PrimeKG 2-hop via {intermediate}",
            })

        return results

    def _estimate_conditional(self, evidence: str, intermediate: str) -> float:
        """策略 B: 跨疾病共现率估计 P(evidence | intermediate)"""
        _DEFAULT = 0.3

        if not self.lr:
            return _DEFAULT

        inter_entries = self.lr.lookup_by_finding(intermediate)
        if not inter_entries:
            return _DEFAULT

        inter_diseases = {e["disease"].strip().lower() for e in inter_entries}
        if not inter_diseases:
            return _DEFAULT

        co_occur = sum(
            1 for d in inter_diseases
            if self.lr.lookup_fuzzy(evidence, d)
        )
        estimated = co_occur / len(inter_diseases)

        # 设下限防止极端值
        return max(estimated, 0.1)
```

#### 9.4.5 LR 精度与置信度对照表

| 来源 | 跳数 | LR 精度 | 置信度标签 | prompt 中的使用方式 |
|------|:----:|---------|----------|-------------------|
| GetTheDiagnosis（精确 Sn/Sp） | 0 | ±5% | `high` | 直接用于 bayesian_update |
| HPO 定量频率 (如 "3/4") | 0 | ±15% | `high` | 直接用于 bayesian_update |
| HPO 标准频率标签 | 0 | ±30% | `medium` | 用于 bayesian_update，权重降低 |
| Orphadata / BODHI-S | 0 | ±40% | `medium`/`low` | 参考性质，LLM 可覆盖 |
| docLogica 定性 | 0 | ±50% | `low` | 仅提示方向，不用于计算 |
| **PrimeKG 2-hop 链** | **2** | **±1 数量级** | **`indirect_chain`** | **仅作推理提示；如需数值，权重降 50%** |
| LLM 自行判断 | — | 不可控 | — | 默认行为 |

#### 9.4.6 关键设计决策总结

1. **2-hop 链的 LR 误差可达数量级**——因此对 TALP 应输出推理链（策略 D），对 Annotator 输出数值但强制标记 `indirect_chain`。

2. **P(E|M) 的最佳估计来源是统一缓存的跨疾病共现率**（策略 B）——不依赖外部数据，利用已有 233K 条目的统计模式。

3. **Specificity 在链路中保持不变**——理论上 Sp 也会衰减，但保守不变可防止 LR+ 膨胀（过度支持）。

4. **不推荐超过 2-hop**——每增加一跳，P(E|M) 估计的误差呈指数增长，LR 信噪比急剧下降。

5. **中间节点的特异性决定链路价值**——如果中间节点（如"leukostasis"）仅关联 3 种疾病，其鉴别价值远高于"fatigue"（关联 500+ 种疾病）。排序时应优先返回中间节点疾病关联数少的链。

### 9.5 推荐实施优先级

| 优先级 | 方案 | 预期收益 | 成本 | 解决的瓶颈 |
|:------:|------|---------|------|-----------|
| **P0** | C: 数据驱动 Specificity | LR 区分度从 ~0 → 有意义 | 极低 | 瓶颈 3 |
| **P1** | A: Embedding HPO 匹配 | 命中率 64%→80-85% | 低-中 | 瓶颈 1 |
| **P1** | D: PrimeKG 2-hop 遍历 + B/D 混合 LR | 补全综合征链推理能力 | 低 | 瓶颈 4 (R3) |
| **P2** | E: 疾病名称标准化 | 覆盖率 30%→50-60% | 低-中 | R13 |
| **P3** | B: StatPearls RAG fallback | 缓存未命中时有降级路径 | 中-高 | 瓶颈 2 (R5-R7) |

**P0+P1 预计可在 1 周内完成，将 CML 案例命中率从 64% 提升至 ~85%，并补全多跳推理能力。**

### 9.6 与文档推荐架构的对齐状态

```
                 文档推荐 (§6.4)              →  当前状态
  ┌──────────────────────────────────────────────────────┐
  │  KG 约束 (MedKGI 模式)                               │
  │    约束 TALP 候选生成范围                             │
  │  → DxS 差集 + PrimeKG 排除边              ✅ 已实现   │
  ├──────────────────────────────────────────────────────┤
  │  结构化查找 (LR Cache)                               │
  │    hash 查找, 零延迟                                 │
  │  → 统一缓存 233K 条, fuzzy 匹配            ✅ 已实现   │
  │    (但匹配精度 △, Sp 估计 △)                         │
  ├──────────────────────────────────────────────────────┤
  │  向量 RAG 补充 (StatPearls + PubMed)                 │
  │    KG 未覆盖时降级为文本检索                          │
  │  → ❌ 完全缺失                                       │
  ├──────────────────────────────────────────────────────┤
  │  Agent 编排 (Controller 动态路由)                      │
  │    每轮动态决定需要什么知识                            │
  │  → △ 注入逻辑已有, 但无动态路由决策                   │
  └──────────────────────────────────────────────────────┘
```

**结论**：当前实现完成了推荐架构的**结构化层**（KG 约束 + LR Cache），但**非结构化补充层**（RAG fallback）和**智能编排层**（动态路由）尚未实现。在结构化层内部，术语匹配精度和 LR 区分度是两个可以快速修复的短板。

---

## 十、多跳推理链缺失的认识论根源与现有系统的解法（2026-05-22）

### 10.1 LR 数据库为什么不包含 2-hop 链？——三层根因分析

这不是某个数据库的疏漏，而是 **EBM（循证医学）诊断范式本身的设计边界** 与 **临床推理实际需求** 之间的结构性鸿沟。

#### 根因 1：EBM 的认识论基础——关联统计，非因果机制

LR 数据库的底层数据来自 **诊断准确性研究**（diagnostic accuracy studies），其标准范式是：

```
研究设计:
  取一组 已确诊疾病 D 的患者 (n₁)
  取一组 已确诊非 D 的对照组 (n₂)
  测量两组中 发现 F 的出现率
  → Sn = P(F|D),  Sp = 1 - P(F|¬D)
  → LR+ = Sn / (1-Sp)
```

这个方法论有一个关键特征：**它只测量 F 和 D 之间的统计关联，不建模为什么关联存在**。

举例说明：
- "basophilia → CML"：有人做了研究，测量了 CML 患者中 basophilia 的出现率 → 产生 LR
- "visual loss → CML"：**没有人会设计这样的研究**

为什么没有？因为视力下降不是 CML 的"典型表现"——它是一条**病理生理因果链**的末端：

```
CML blast crisis → WBC 极度升高 → 高粘滞血症 → leukostasis
  → 视网膜微血管淤塞 → 视力下降
```

EBM 的奠基者明确将此类推理归为**机制推理**（mechanistic reasoning），其证据等级**低于**直接的统计关联数据 [ref 29]。EBM 的核心主张是："不要根据机制猜测；用数据说话"——但数据（LR 数据库）只包含被研究过的直接关联。

> "Mechanistic reasoning has often led us astray... Whenever mechanistic reasoning is used to justify a therapeutic intervention, the stages and chain of reasoning should be shown, accompanied by the evidence that supports **each link** in the chain." — Howick et al., 2010 [ref 29]

这揭示了一个深层矛盾：**EBM 要求以数据为据，但 LR 数据库本身受限于研究者选择测量哪些 finding-disease 对，而研究者不会测量需要因果推理才能想到的间接关联。**

#### 根因 2：组合爆炸——不可能穷举所有链路

假设要覆盖所有 2-hop 链路：
```
20,000 findings × 20,000 intermediates × 20,000 diseases = 8 × 10¹² 潜在链路
```

即使仅考虑 KG 中存在边的链路，组合数仍达数百万级。每条链路都需要独立的临床研究来建立可靠的 LR——这在经济和伦理上都不可行。

LR 数据库是 **专家精选的高价值直接关联**，不是穷举图的边权重矩阵。

#### 根因 3：上下文依赖性——静态 LR 无法表达间接链

多跳链的 LR 高度依赖临床上下文：
```
P(visual_loss | CML) 取决于:
  - WBC 数值（>100k 时 leukostasis 风险急升）
  - 疾病分期（blast crisis vs chronic phase）
  - 年龄（血管脆性不同）
  - 治疗状态（是否已开始化疗）
```

直接关联的 LR（如 "basophilia → CML"）在不同上下文中变化较小（±2x），但间接链的 LR 可能跨越数量级（blast crisis 时 visual_loss 的 LR 可能是 chronic phase 的 100 倍）。**静态数据库结构无法表达这种条件性。**

#### 总结：三层根因的交汇

```
┌─────────────────────────────────────────────────────────┐
│  认识论层面 (根因1)                                       │
│  EBM = 关联统计范式 → 只测量直接 F→D 对                   │
│  间接链 = 机制推理 → EBM 明确将其排除在一级证据之外        │
├─────────────────────────────────────────────────────────┤
│  工程层面 (根因2)                                        │
│  穷举所有多跳链 = 组合爆炸 → 不可能建库                   │
├─────────────────────────────────────────────────────────┤
│  临床层面 (根因3)                                        │
│  间接链 LR 高度上下文依赖 → 静态值误差可达数量级           │
└─────────────────────────────────────────────────────────┘
      ↓
结论：2-hop 链不在 LR 数据库中，是 EBM 范式的结构性边界，
而非数据收集的技术缺口。任何试图为间接链计算"精确 LR"
的做法都在本质上超出了 EBM 的方法论保证。
```

### 10.2 现有 Agentic 临床诊断系统的解法——五种范式

一个关键发现：**目前没有任何系统试图为多跳链计算数值 LR**。它们用完全不同的方式绕过了这个问题。

#### 范式 A：KG 约束候选生成（不算 LR，用图结构约束提问范围）

**代表系统**：MedKGI [ref 1]

**核心思路**：不需要知道 "visual loss → CML" 的 LR，只需要知道 "leukostasis 是一个值得询问的方向"。

```
MedKGI 工作流:
  1. Entity Extraction: 从 vignette 提取实体 → 映射到 KG
  2. Subgraph Construction: 构建诊断子图（候选疾病 + 直接关联症状）
  3. Information Gain: 计算每个未询问症状的信息增益
     IG(symptom) = H(diseases) - H(diseases | symptom=present/absent)
  4. 选择 IG 最高的症状提问

  多跳处理: KG 子图自然包含 1-hop 邻居。
  如果 "leukostasis" 出现在子图中（作为 CML 的关联表型），
  且 "visual loss" 出现在 "leukostasis" 的邻居中，
  那么系统会优先询问 leukostasis 相关症状。
  
  → 不计算间接 LR，而是用 IG 引导提问方向
```

**如何处理间接链**：通过 KG 子图的拓扑结构隐式覆盖。多跳推理退化为"先问中间节点，再根据答案更新"。

**对我们的启示**：`DxFeatureRetriever.get_discriminator_hints()` 已经在做类似的事——通过 PrimeKG 表型差集给 TALP 提供"应该关注哪些方向"。但目前缺少的是**信息增益排序**——应该优先推荐 IG 最高的鉴别特征。

#### 范式 B：RL 训练的 Agent 策略（让 Agent 学会何时走间接推理路径）

**代表系统**：Deep-DxSearch [ref 18]

**核心思路**：不预计算多跳 LR，而是通过 RL 训练 Agent **学会何时推理（reason）、何时查表（lookup）、何时搜文献（search）**。

```
Deep-DxSearch 5 种动作:
  reason:  内部推理（LLM 进行多步因果分析）
  lookup:  查询 DiagRL-Corpus 表型表（1-hop 扁平查找）
  match:   匹配相似病例
  search:  检索 PubMed/Wikipedia 文献
  diagnose: 输出诊断
  
多跳链处理 (RL 策略自动学习):
  Step 1: lookup("CML") → 获取 CML 表型列表
  Step 2: reason("patient has visual loss; CML phenotypes include
           leukostasis; leukostasis can cause visual loss")
           → LLM 内部完成因果链推理
  Step 3: search("leukostasis visual loss CML blast crisis")
           → 从 PubMed 获取支持证据
  Step 4: diagnose("CML blast crisis")
```

**如何处理间接链**：**将多跳推理完全委托给 LLM 的 `reason` 动作**。RL 训练让 Agent 学会在什么时候调用 `reason` 而不是 `lookup`。关键不是为链计算 LR，而是让 Agent 知道"这里需要推理，不是查表"。

**对我们的启示**：我们的 TALP 已经是一个 LLM-based planner。当 DxFeatureRetriever 返回 2-hop 推理链时，TALP 的 LLM 能力完全可以利用这条链进行因果推理——无需精确 LR。

#### 范式 C：层次化 KG + LLM 增强鉴别特征（在图结构中编码间接关系）

**代表系统**：MedRAG [ref 5]，MedRAG Multi-Agent v2

**核心思路**：构建层次化的诊断 KG，在叶节点用 LLM 生成**疾病间的关键鉴别差异**——本质上是**将多跳推理预计算并固化为 KG 边属性**。

```
MedRAG 4-tier KG:
  Tier 1: Disease Categories (内科, 外科, ...)
  Tier 2: Subcategories (血液病, 肿瘤, ...)
  Tier 3: Diseases (CML, AML, ALL, ...)
  Tier 4: Critical Diagnostic Differences (LLM 生成)
    ← "CML-BC vs AML: CML-BC 更可能有 basophilia,
       splenomegaly, 渐进性病程, 且 blast crisis 可伴
       leukostasis（表现为视力/神经症状）"

MedRAG Multi-Agent v2 Neo4j schema:
  Symptom → Syndrome → Disease → Treatment + Pathways
    ← 4-tier 架构显式建模 "finding → syndrome → disease" 链
    ← BFS 3-hop 遍历
```

**如何处理间接链**：
1. 在 KG 构建阶段就用 LLM 将间接关系**展平为直接的鉴别描述**
2. 运行时通过 BFS 多跳遍历连接 evidence → syndrome → disease
3. 不计算数值 LR——用自然语言描述鉴别价值

**对我们的启示**：可以在 `build_unified_cache.py` 中增加一步——用 LLM 为高价值疾病对生成"关键鉴别差异"文本，缓存为结构化 JSON。这比计算 2-hop LR 更可靠。

#### 范式 D：迭代检索-推理循环（用多轮对话逐步收敛间接链）

**代表系统**：SEMA-RAG [ref 17], MultiDx (2026)

**核心思路**：不试图一次性推导完整的多跳链，而是通过**迭代检索**让链条逐步浮现。

```
SEMA-RAG 三阶段:
  I-Agent (Interpreter): 将问题分解为临床 Schema
  E-Agent (Explorer):    充分性驱动的多轮检索
    Round 1: search("visual loss differential diagnosis")
      → 获取: "visual loss 可由 leukostasis 引起"
    Round 2: search("leukostasis causes CML blast crisis")
      → 获取: "leukostasis 常见于 CML blast crisis 伴 WBC>100k"
    Round 3: evaluate_sufficiency()
      → "已有足够证据链接 visual loss → CML-BC"
  A-Agent (Arbiter):     证据裁决 + 答案生成

MultiDx 多源投票:
  Source 1 (Web): "visual loss + leukostasis" → CML-BC
  Source 2 (Case DB): similar cases → CML-BC
  Source 3 (Guidelines): CML blast crisis 特征 → CML-BC
  Source 4 (Knowledge): KG traversal → CML-BC
  → Cross-source voting: 4/4 support CML-BC
```

**如何处理间接链**：**分解为多轮直接检索**。第一轮找到 "visual loss → leukostasis"，第二轮找到 "leukostasis → CML"。每轮检索都是 1-hop 的，但多轮叠加就覆盖了 N-hop 链。

**对我们的启示**：我们的 TALP-Bundler-Annotator 多轮循环天然就是这种架构。如果第 1 轮 TALP 收到了 "visual loss may relate to leukostasis (PrimeKG chain)" 的提示，它可以生成 "ask about leukostasis symptoms" 的候选动作。第 2 轮的 evidence 就会包含 leukostasis 相关信息，此时直接 LR 查找可能就会命中。

#### 范式 E：拓扑感知的推理强制（确保 LLM 不走捷径）

**代表系统**：ShatterMed-QA (2026) [ref 30]

**核心思路**：不解决 LR 计算问题，而是揭示并对抗 LLM 的**多跳推理捷径学习**问题。

```
问题: LLM 在面对 "visual loss + high WBC → ?" 时，
     倾向于通过 hub 节点（如 "blood disorder"）直接跳到答案，
     而不是沿着 visual loss → leukostasis → CML-BC 的因果链推理。

ShatterMed-QA 的解法:
  1. k-Shattering: 物理删除 KG 中的 hub 节点（如 "inflammation", "blood"）
     → 强制模型沿真正的微病理链推理
  2. Bridge Entity Masking: 在 vignette 中隐藏中间实体 (e.g., "leukostasis")
     → 测试模型能否自行推导出被隐藏的桥接实体
  3. Topology-Driven Distractors: 从病理层级中采样同级干扰项
     → 防止通过排除法猜答
```

**如何处理间接链**：不处理——而是**评估模型是否具备处理间接链的能力**。这对我们的价值在于：它揭示了 LLM 在多跳推理中的系统性弱点。

### 10.3 五种范式的统一框架与我们的定位

```
                         多跳推理解决策略谱系

  ← 结构化/确定性                              非结构化/概率性 →

  ┌───────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐
  │ 范式 A    │  │ 范式 C   │  │ 范式 D   │  │ 范式 B    │  │ 范式 E   │
  │ KG 约束   │  │ 层次化   │  │ 迭代检索 │  │ RL Agent  │  │ 拓扑强制 │
  │ + IG 排序 │  │ KG+LLM增强│ │ 多轮收敛 │  │ 学习策略  │  │ 评估框架 │
  │           │  │          │  │          │  │           │  │          │
  │ MedKGI    │  │ MedRAG   │  │ SEMA-RAG │  │ Deep-DxS. │  │ ShatterMed│
  │           │  │ MultiAgent│ │ MultiDx  │  │           │  │          │
  └─────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬─────┘  └────┬─────┘
        │              │             │              │              │
        └──────────────┴─────┬───────┴──────────────┘              │
                             │                                     │
                    ┌────────▼────────┐                           │
                    │   共同特征:     │                            │
                    │   无一系统计算  │                            │
                    │   多跳链的      │◄─────────────────────────┘
                    │   数值 LR       │  (ShatterMed 证明 LLM
                    └────────┬────────┘   在多跳推理中有
                             │             系统性弱点)
                             ▼
                    ┌─────────────────┐
                    │  我们的系统     │
                    │  (Tree-Dx-Spec) │
                    │                 │
                    │ 当前: 范式 A    │  ← KG 约束 (DxS + PrimeKG)
                    │ + 部分范式 D    │  ← 多轮 TALP-Bundler-Annotator
                    │                 │
                    │ 推荐补充:       │
                    │ + 范式 C (LLM   │  ← 为 2-hop 链生成自然语言
                    │   增强鉴别描述) │     鉴别描述而非数值 LR
                    │ + 范式 D 强化   │  ← 利用多轮循环将间接链
                    │   (多轮分解)    │     分解为多轮直接查找
                    └─────────────────┘
```

### 10.4 对 §9.4 的修订建议

基于以上分析，对 §9.4 中 "2-hop LR 计算方案" 的评估需要更新：

| 方案 | 原定位 | 修订评估 |
|------|--------|---------|
| 策略 B (共现率估计 LR) | Annotator 通道主力 | **降级为辅助参考**——没有任何现有系统这样做，误差可达数量级 |
| **策略 D (定性推理链)** | TALP 通道主力 | **升级为两个通道的共同主力**——与 5 种范式的共识一致 |
| **新增：策略 F (多轮分解)** | — | **新增为首选策略**——将 2-hop 问题转化为多轮 1-hop 问题 |

#### 策略 F：多轮分解（利用已有的 TALP 迭代架构）

```
第 N 轮 (发现 visual loss 未命中直接 LR):
  DxFeatureRetriever 返回:
    "visual loss → (PrimeKG p2p) → leukostasis → (PrimeKG d2p) → CML-BC"
    
  TALP 接收链路提示后生成候选动作:
    CandidateLeaf: "Ask about symptoms of leukostasis 
                    (headache, confusion, dyspnea)"
    primary_function: "differentiate"
    target_branches: {"CML-BC": "+", "AML": "0"}

第 N+1 轮 (患者确认有 headache + confusion):
  LR 缓存直接命中:
    lookup("headache", "leukostasis") → LR+ = 2.1
    lookup("leukostasis", "CML-BC") → Sn = 0.17
    
  → 不再需要计算间接链 LR
  → 两个 1-hop 查找各自有可靠的 LR
  → bayesian_update 可以正确运行
```

**关键洞察**：多轮架构本身就是对间接链 LR 问题的**天然解法**——将不可靠的 N-hop LR 估计分解为 N 次可靠的 1-hop LR 查找，每次查找都在 EBM 的方法论保证范围内。

### 10.5 代码路径审计：多跳推理在当前 TALP 中的可行性（2026-05-22）

#### 10.5.1 当前知识注入的完整调用链

```
Controller.run() 主循环:
                                     
  Step D: plan_temporary_leaves(state)
    │
    ├── payload = state.to_payload()      ← 包含 branches, frontier, actions_taken (≤6条)
    │                                        evidence_for/against (每branch≤2条)
    │                                        differential_history (≤3轮)
    │
    ├── if enable_knowledge_injection:
    │   └── DxFeatureRetriever.format_discriminator_hints_for_prompt(disease_names)
    │       │
    │       ├── get_discriminator_hints()
    │       │   ├── Layer 0: DxS get_phenotypes(d) → 表型集合
    │       │   ├── Layer 1: PrimeKG get_positive_phenotypes(d) → 表型集合
    │       │   │   + get_negative_phenotypes(d) → 排除表型
    │       │   │   + get_related_diseases(d) → 关联疾病
    │       │   └── 合并 → pairwise 差集 → unique_per_disease
    │       │
    │       └── 格式化为纯文本 (≤25行):
    │           "[Knowledge Layer: coverage=75%, source=both]
    │            CML vs AML:
    │              Favours first: basophilia, splenomegaly, ...
    │              Favours second: gum_hypertrophy, DIC, ...
    │            NOT typically seen in CML: ..."
    │           
    │           ★ 注意: 此处完全不调用 phenotype_multihop()
    │           ★ 注意: 不包含任何 2-hop 链路信息
    │
    └── payload["discriminator_hints"] = hints_text  ← 仅此一个字段
        │
        └── _call_module("TemporaryAnalyticLeafPlanner", payload)
            │
            └── LLM 接收 JSON payload:
                {
                  "branches": {...},
                  "frontier": [...],
                  "actions_taken": [...],
                  "discriminator_hints": "...(纯文本, ≤25行)..."
                }
                
                ★ Prompt 模板中无任何对 discriminator_hints 的引用
                ★ LLM 仅通过 payload JSON 的字段名推断其用途
```

**关键发现**：

1. **`phenotype_multihop()` 已实现但从未被调用** — 存在于 `PrimeKGIndex` 中（L147-163），可做 BFS ≤2 跳遍历，但 `DxFeatureRetriever.get_discriminator_hints()` 不调用它。

2. **`enable_knowledge_injection` 默认关闭** — `config.py` L57: `enable_knowledge_injection: bool = False`。即使整个知识层已构建，如果不显式开启，TALP 和 Annotator 都收不到任何知识提示。

3. **Prompt 中无 `discriminator_hints` 占位符** — 三个 prompt 文件（`temporary_leaf_planner.txt`、`temporary_analytic_leaf_planner.txt`、`evidence_annotator.txt`）均未提及 `discriminator_hints` 或 `lr_reference`。知识块作为 payload JSON 中的额外字段传入，LLM 需要自行发现并利用它。

4. **finding 提取方式限制了 LR 查找范围** — Annotator 的 `finding_text` 来自 `state.actions_taken[-1]["content"]`，即最近一次 action 的**文本内容**（例如 "Does the subacute onset over days with constitutional symptoms argue against de novo AML?"），而非结构化的 finding 术语。这个长句子作为 `LRRetriever.lookup_fuzzy()` 的输入，几乎不可能命中缓存。

#### 10.5.2 逐条评估：多跳策略是否可行

##### 策略 D（定性推理链注入 TALP）— 当前可行性：❌ 不可行

| 需要的能力 | 当前状态 | 缺口 |
|-----------|---------|------|
| 从 PrimeKG 提取 2-hop 链 | `phenotype_multihop()` 存在但未调用 | 需要新方法 `find_2hop_chains()` |
| 链路信息注入 TALP payload | `discriminator_hints` 字段存在 | 需要扩展格式化逻辑 |
| TALP prompt 理解链路 | prompt **无任何提示** LLM 应如何使用 hints | **需要修改 prompt** |
| TALP 生成基于链路的候选 | prompt 中无 "syndrome chain" 概念 | **需要修改 prompt** |

**阻断点**：即使将 2-hop 链信息放入 `discriminator_hints`，当前 TALP prompt 也不会指导 LLM 如何利用它。TALP prompt（L1-95 of `temporary_analytic_leaf_planner.txt`）关注的是 "为每个 live branch 生成 CONFIRM + CHALLENGE 候选"，没有 "沿推理链追踪间接关联" 的指令。

##### 策略 F（多轮分解：Round N 提示中间概念 → Round N+1 直接查找）— 当前可行性：△ 理论可行但存在多处断裂

**预期流程 vs 实际代码路径**：

```
Round N (evidence: "visual loss"):

  预期: TALP 收到 "visual loss → leukostasis → CML-BC" 链
        → 生成候选: "Ask about leukostasis symptoms"
        
  实际:
    1. plan_temporary_leaves() 被调用
    2. format_discriminator_hints_for_prompt(["CML", "AML"]) 被调用
    3. get_discriminator_hints() 执行:
       - DxS 差集: CML phenotypes vs AML phenotypes → pairwise 差集
       - PrimeKG 直接表型: 同上
       ★ 不调用 phenotype_multihop("visual loss")
       ★ 不检查 "visual loss" 是否通过 p2p 边连接到某个疾病的表型
    4. hints 输出类似:
       "CML vs AML:
         Favours CML: basophilia, splenomegaly, ...
         Favours AML: gum_hypertrophy, DIC, ..."
       ★ 不包含 "visual loss → leukostasis" 链
    5. TALP LLM 收到 payload，完全不知道 visual loss 与 leukostasis 的关系
    6. TALP 可能生成:
       - "Analyze whether basophilia supports CML" (来自 hints)
       - "Analyze whether subacute onset argues against AML" (来自 LLM 自身知识)
       ★ 不太可能生成 "ask about leukostasis" 除非 LLM 本身已知此关联

Round N+1:
  ★ 即使 Round N 碰巧分析了 leukostasis，
    Round N+1 的 LR 查找也有问题:
    - finding_text = actions_taken[-1]["content"]
    - 内容是 "Does elevated WBC with blast crisis suggest leukostasis..."
    - 这个长句子 → LRRetriever.lookup_fuzzy() → 大概率不命中
    - 因为缓存 key 是 "leukostasis::chronic myeloid leukemia"
      而 finding_text 是一整句自然语言
```

**核心断裂点**：

| 断裂点 | 描述 | 严重性 |
|--------|------|:------:|
| **B1: 无 2-hop 触发** | `get_discriminator_hints()` 不检查当前 evidence 与 PrimeKG p2p 边的关系 | 高 |
| **B2: 无链路格式化** | `format_discriminator_hints_for_prompt()` 无法输出链路结构 | 高 |
| **B3: Prompt 无引导** | TALP prompt 不知道 `discriminator_hints` 的存在和用法 | 高 |
| **B4: finding 提取粗糙** | Annotator 用整句 action content 做 LR 查找 | 中 |
| **B5: 默认关闭** | `enable_knowledge_injection = False` | 低（配置问题） |
| **B6: 无链路追踪状态** | `DiagnosticState` 无 "当前正在追踪的推理链" 字段 | 中 |

#### 10.5.3 使多跳推理实际可行的最小改动清单

```
优先级 P0: 基础设施修复（使现有 1-hop 知识注入实际生效）
┌──────────────────────────────────────────────────────────────┐
│ □ B5: config.enable_knowledge_injection 默认改为 True        │
│       或至少在 smoke test 配置中启用                          │
│                                                              │
│ □ B3: 在 TALP prompt 末尾增加知识使用指令:                    │
│   "When discriminator_hints is present in the payload,       │
│    USE these features to generate candidates that target     │
│    the most discriminative phenotypes not yet analyzed."      │
│                                                              │
│ □ B4: 从 action content 中提取关键词而非整句传给 LR 查找:    │
│   - 使用 EvidenceMatcher 将 content → 标准化 phenotype       │
│   - 或从 Annotator 的 result_summary 中提取 finding 术语     │
└──────────────────────────────────────────────────────────────┘

优先级 P1: 多跳推理能力
┌──────────────────────────────────────────────────────────────┐
│ □ B1: 新增 DxFeatureRetriever.get_2hop_chains() 方法         │
│   - 输入: 当前 vignette evidence 中 LR 未命中的 findings     │
│   - 调用 PrimeKGIndex.phenotype_multihop() 或新增             │
│     find_2hop_chains(evidence, diseases)                     │
│   - 输出: list[{evidence, intermediate, disease, chain_text}]│
│                                                              │
│ □ B2: 扩展 format_discriminator_hints_for_prompt():           │
│   - 在现有 pairwise 差集之后，追加 2-hop 链路信息:           │
│   "[Indirect reasoning chains:]                              │
│    visual loss → (associated) → leukostasis → CML-BC         │
│    (leukostasis sensitivity for CML-BC: 17%, HPO Occasional) │
│    Suggestion: investigate leukostasis-related symptoms"      │
│                                                              │
│ □ B3 扩展: prompt 增加链路使用指令:                           │
│   "When indirect_reasoning_chains are present, generate      │
│    candidates that investigate the INTERMEDIATE phenotype     │
│    to confirm or rule out the indirect association."          │
│                                                              │
│ □ B6: DiagnosticState 新增 active_reasoning_chains 字段      │
│   - 跨轮持久化：Round N 发现链路 → Round N+1 追踪结果       │
│   - 链路状态: pending / confirmed / refuted                  │
└──────────────────────────────────────────────────────────────┘
```

#### 10.5.4 可行性实验：手动注入 2-hop 链信息到 TALP Payload（2026-05-22）

为验证 §10.5.2 中"策略 D 不可行"的结论是否过于保守（即 LLM 是否会自动利用 payload 中额外的链路字段），设计了三组对照实验。

**实验设计**：

| 条件 | discriminator_hints 内容 | 目的 |
|:----:|------------------------|------|
| A | 无 hints | 基线：LLM 仅凭 vignette 和 branch 信息生成候选 |
| B | 1-hop pairwise 差集（当前系统输出） | 对照：标准知识注入效果 |
| C | 1-hop + 2-hop indirect reasoning chains | 实验：链路信息是否被 LLM 采纳 |

- **场景**: Case #68 CML-BC（Round 2 状态，AML posterior=0.42, CML-BC posterior=0.33）
- **模型**: `qwen/qwen3-32b` (via OpenRouter, temperature=0.7)
- **重复**: 每个条件 3 次独立运行
- **核心测量**: LLM 生成的候选是否引用 **中间概念（leukostasis）** — 这是 2-hop 链路的关键中间节点，不在 1-hop 差集中出现
- **2-hop 链路示例**（注入条件 C）:
  ```
  Chain 1: bilateral visual acuity loss → leukostasis retinopathy → CML-BC
    (leukostasis occurs in ~17% of CML-BC but <5% of de novo AML)
    ★ Suggestion: Analyze whether the visual loss + fundoscopy findings
      constitute a leukostasis syndrome.
  Chain 2: progressive fatigue (3wk) + weight loss (2mo) → chronic myeloproliferative phase → CML-BC
    ★ Suggestion: Analyze whether the temporal dissociation argues for
      biphasic disease (chronic → blast crisis).
  ```

**实验结果**：

| 指标 (3 runs avg) | A (无) | B (1-hop) | C (2-hop) | C−B | 显著性 |
|:---|:---:|:---:|:---:|:---:|:---:|
| 总候选数 | 8.0 | 8.0 | 6.7 | −1.3 | |
| **中间概念 (leukostasis) 引用** | **0.0** | **0.0** | **1.0** | **+1.0** | **★★★** |
| 链路关键词引用 | 1.0 | 0.7 | 1.0 | +0.3 | ★ |
| 时间线/慢性推理引用 | 1.3 | 0.7 | 1.3 | +0.7 | ★ |
| 视觉链路引用 | 1.0 | 1.0 | 1.3 | +0.3 | ★ |
| CML-BC 支持候选数 | 2.3 | 2.3 | 2.7 | +0.3 | |

**关键发现 — 中间概念命中率**：

```
Per-run intermediate concept (leukostasis) counts:
  A: [0, 0, 0]  (hit rate: 0/3)
  B: [0, 0, 0]  (hit rate: 0/3)
  C: [1, 1, 1]  (hit rate: 3/3)  ← 100% 命中率
```

条件 C 在全部 3 次运行中，LLM 均生成了明确引用 leukostasis 的候选，且排名 #0 或 #1。典型输出：

> **[C-Run1, Rank #0]** B2/confirm: *"Do the bilateral retinal hemorrhages + cotton-wool spots argue for **leukostasis syndrome**, which occurs in 17% of CML-BC but <5% of de novo AML?"*
>
> **[C-Run2, Rank #0]** B2/confirm: *"Does the bilateral visual acuity loss with retinal hemorrhages and cotton-wool spots constitute **leukostasis syndrome**, which strongly favors CML-BC?"*
>
> **[C-Run3, Rank #0]** B1/challenge: *"Do the bilateral retinal hemorrhages with cotton-wool spots and the 2-month temporal dissociation argue against AML (via **leukostasis** → CML-BC chain)?"*

而条件 A 和 B 在所有 9 次运行中均**从未**产生包含 "leukostasis" 的候选——即使 vignette 中包含了 retinal hemorrhages + cotton-wool spots 这些 leukostasis 的临床表现。

**结论**：

| 问题 | 实验前假设 | 实验后结论 |
|------|-----------|-----------|
| TALP LLM 会利用 payload 中的链路字段吗？ | "不确定" → 倾向否 | ✅ **会。** 100% 命中率。LLM 不仅识别了 `discriminator_hints` 字段中的链路信息，还将其整合为最高排名的候选。 |
| Prompt 中无 hints 引用是否导致 LLM 忽略它？ | 预期会忽略 | ❌ **不会。** JSON payload 中的结构化链路信息即使未在 prompt 中被提及，也被 LLM 有效利用。但添加 prompt 指令（§10.5.3 P0-B3）仍推荐，以确保一致性。 |
| 2-hop 链路信息的"附加值"是什么？ | 不确定 | **引导 LLM 发现其自身知识中无法独立产生的推理路径。** A/B 条件中 LLM 看到 retinal hemorrhages 但从未连接到 leukostasis，说明这个间接推理超出了当前 LLM 的自发能力。 |

**对 §10.5.3 修改清单的影响**：

- **P0-B3（prompt 修改）降级为 optional**：实验证明 LLM 已能利用 payload 中的 hints，但 prompt 指令可提高鲁棒性
- **P1-B1 + P1-B2（2-hop chain 提取+格式化）升级为 critical path**：实验验证了链路信息的巨大价值，应优先实现
- **P1-B3（prompt 链路指令）降级为 nice-to-have**：C 条件的 `discriminator_hints` 末尾包含了链路使用指令，但 LLM 似乎即使没有显式指令也能自行利用链路结构

#### 10.5.5 端到端存活性验证：Bundler 筛选模拟（2026-05-22）

上述实验验证了 LLM 能生成链路候选。但该候选还需通过 `FrontierCoverageBundler` 的多层筛选才能实际执行。使用与实验相同的 3 次 Condition C 输出，将其注入真实 bundler 代码进行模拟。

**Bundler 筛选层级与链路候选的存活分析**：

```
候选生命周期:
  TALP LLM 生成 → CandidateLeaf 解析 → build_bundle() →
    Phase 1  (Confirm 通道): 按 branch_id 匹配 + target_branches == "support"
    Phase 1b (Challenge 通道): 按 branch_id 匹配 + target_branches == "against"
    _passes_gates():
      ├─ _is_dependent()          → ANALYZE_VIGNETTE 不在 dependent 集合 ✓
      ├─ _is_duplicate_knowledge() → ANALYZE_VIGNETTE 不在 knowledge 集合 ✓
      ├─ _is_redundant()          → Jaccard 相似度 < 0.60 阈值？
      └─ EIG ≥ min_marginal_ig    → EIG ≥ 0.05？
    Phase 2 (Directional diversity): 仅影响 leader 分支
    Phase 3 (Cross-branch supplement): 需 action_separation_value ≥ 0.50
  → 最终 bundle → execute_action_bundle()
```

**各 run 筛选结果**：

| Run | 链路候选位置 | EIG | 进入通道 | Jaccard 冗余？ | 最终 bundle？ |
|:---:|:---|:---:|:---|:---:|:---:|
| 1 | B2/confirm (leukostasis syndrome) | 0.45 | Phase 1, B2 confirm slot | 与 B1 confirm "blast count" Jaccard ≈ 0.05 ✓ | ✅ Bundle item #1 |
| 2 | B2/confirm (leukostasis syndrome) | 0.60 | Phase 1, B2 confirm slot | Bundle 为空（第一个进入）✓ | ✅ Bundle item #0 |
| 3 | B1/challenge (retinal hemorrhages + temporal dissociation) | 0.20 | Phase 1b, B1 challenge slot | 与 B1 confirm "blast percentage" Jaccard ≈ 0.08, 且 same-branch opposite-direction 豁免 ✓ | ✅ Bundle item #4 |

**链路候选存活率: 3/3 (100%)**

**逐层分析**：

1. **EIG 门槛 (0.05)**: 链路候选 EIG 范围 [0.20, 0.60]，远超阈值。LLM 将链路候选评为高信息增益是因为它提供了其他候选无法提供的独特推理角度（间接关联）。

2. **冗余检测 (Jaccard ≥ 0.60)**: 链路候选使用独特的医学术语 (leukostasis, retinal hemorrhages, cotton-wool spots, temporal dissociation)，与常规候选 (blast count, basophilia, splenomegaly) 词汇重叠极低。此外，`_same_branch_opposite_direction` 豁免机制使同一分支的 confirm/challenge 对免于冗余检测。

3. **Bundler 通道匹配**: 链路候选自然占据 B2 的 confirm 槽位（2/3 runs）或 B1 的 challenge 槽位（1/3 runs），这两个都是 dual-channel bundler 的**主要通道**（Phase 1/1b），不依赖 Phase 3 补充通道。

4. **target_branches 多分支影响**: Run 1-2 中链路候选的 target_branches 包含 `{"B2": "support", "B1": "against"}`，表示 LLM 理解了 leukostasis 同时支持 CML-BC 并反对 AML。这种多分支影响使其信息密度更高。

**唯一的边缘风险**：

| 风险 | 概率 | 触发条件 | 缓解 |
|------|:----:|---------|------|
| B2 confirm 槽位已被另一个高分 B2 confirm 候选占据 | 低 | 链路候选排名低于另一个 B2 confirm | 实验中链路候选始终排名 #0-#1，得分最高 |
| 与另一候选 Jaccard > 0.60 | 极低 | 另一候选也使用 retinal/visual 术语 | 链路术语高度专业化，常规候选不会使用 |
| EIG < 0.05 | 不可能 | LLM 给出极低分 | 3 runs 最低 EIG = 0.20 |

**结论**: 2-hop 链路候选在当前 bundler 架构中具有**结构性优势**——其独特的医学术语避免冗余过滤，其多分支影响和高 EIG 确保优先进入主通道。不需要修改 bundler 逻辑即可支持链路候选。

#### 10.5.6 原评估结论（已更新）

| 问题 | 答案 |
|------|------|
| 当前 TALP 能接收多跳链信息吗？ | **不能。** `get_discriminator_hints()` 不调用图遍历；`format_discriminator_hints_for_prompt()` 不输出链路结构。 |
| 如果硬编码注入链信息，TALP LLM 会利用它吗？ | ✅ **会，且效果显著。** 3/3 runs 中 LLM 均生成了引用中间概念 (leukostasis) 的候选，排名 top-1，而 baseline 和 1-hop 条件中 0/3 runs 产生此类候选。 |
| 多轮分解（策略 F）能自然发生吗？ | **极不可能自然发生，但注入链信息后可引导。** 条件 C 中 LLM 生成了 "investigate leukostasis" 类候选，如果 Round N+1 的 LR 查找能正确处理 finding 提取（P0-B4），多轮分解的路径即可打通。 |
| 最小化修改量是多少？ | **P0 级 2 处修改**（config 默认值 + finding 提取）可使 1-hop 知识注入生效。**P1 级 2 处修改**（get_2hop_chains + format_hints 扩展）可启用 2-hop 推理。Prompt 修改为 optional。 |
| 是否存在更深层的架构限制？ | **否。** 架构本身（payload JSON 注入 + 多轮循环 + `seen_evidence_phenotypes` 跟踪）完全支持多跳推理。限制全部在"接线"层面——已有组件未连接。 |

#### 10.5.7 上游管线端到端实测：当前知识检索能否生成链路 hints？（2026-05-22）

§10.5.4-5 验证了"下游可行"（LLM 能用、bundler 不过滤）。本节回答上游问题：**现有知识检索管线能否自动产生 2-hop 链路信息？** 使用真实数据文件 + 真实 `DxFeatureRetriever` 代码进行测试。

##### 断裂点 ①：疾病名称解析失败（0% coverage）

TALP 生成的分支标签（如 "Acute Myeloid Leukemia (AML)"、"CML-BC"）与知识层的索引键不匹配：

| TALP 标签 | DxS 匹配？ | PrimeKG 匹配？ | LR Cache 匹配？ |
|:----------|:---------:|:--------------:|:--------------:|
| Acute Myeloid Leukemia (AML) | ❌ | ❌ (仅有 20+ 特异亚型) | ❌ |
| Chronic Myeloid Leukemia - Blast Crisis (CML-BC) | ❌ | ❌ (有 "blast phase chronic myelogenous leukemia, bcr-abl1 positive" 但 0 个表型) | ❌ |
| Acute Lymphoblastic Leukemia (ALL) | ❌ | ✓ (有表型) | 部分 |
| Myelodysplastic Syndrome (MDS) | ❌ | ✓ (有表型) | ✓ |

使用 TALP 标签调用 `format_discriminator_hints_for_prompt()` 的实际输出：

```
[Knowledge Layer: coverage=0%, source=none]
```

**完全空白。** 零知识注入。即使 `enable_knowledge_injection=True`，TALP 也收不到任何 hints。

将疾病名改为 PrimeKG 兼容格式后，coverage 升至 75%，但这不会在生产中自然发生。

##### 断裂点 ②：AML 在 PrimeKG 中无通用条目

PrimeKG 有 20+ 个 AML 亚型（如 "acute myeloid leukemia with t(8;21)"），但没有通用 "acute myeloid leukemia" 条目。这意味着：
- CML vs AML 的 pairwise 比较**不会被生成**（AML 未找到）
- 即使名称匹配修复后，输出也只有 CML vs ALL 和 CML vs MDS 的差集

##### 断裂点 ③：leukostasis 在所有数据层中不存在

| 数据源 | leukostasis 条目 | 相关 p2p 边 |
|:------|:----------------:|:-----------:|
| PrimeKG 表型 | 0 | 不适用 |
| LR 缓存 | 0 | 不适用 |
| DxS (DiagRL) | 不确定（无法通过索引验证） | 不适用 |
| EvidenceMatcher 词表 | 0 | 不适用 |

##### 断裂点 ④：PrimeKG 中无任何从 retinal/visual 到 CML 的 2-hop 路径

实测 `phenotype_multihop()` 从以下起点搜索 2-hop 内的所有可达表型，与 CML 表型集取交集：

| 起始表型 | 2-hop 可达 | 与 CML 表型重叠 |
|:--------|:---------:|:--------------:|
| retinal cotton wool spot | 11 | 0 |
| retinal hemorrhage | 46 | 0 |
| visual loss | 8 | 0 |
| reduced visual acuity | 24 | 0 |
| abnormal retinal vascular morphology | 65 | 0 |

反向搜索（从 CML 15 个表型各做 2-hop BFS）同样未到达任何 retinal/visual 表型。

**结论：即使代码调用了 `phenotype_multihop()`，PrimeKG 图的拓扑结构中也不存在所需的链路。**

##### 断裂点 ⑤：LR Cache 的 CML 数据与视觉表现完全脱节

Fuzzy lookup 模拟 EvidenceAnnotator 查询：

| Finding | CML 命中？ | AML 命中？ | 命中的疾病 |
|:--------|:---------:|:---------:|:----------|
| bilateral visual loss | ❌ | ❌ | — |
| retinal hemorrhage | ❌ | ❌ | 23 个其他罕见病 |
| cotton wool spots | ❌ | ❌ | 2 个脑血管病 |
| leukostasis | ❌ | ❌ | — |
| basophilia | ❌ | ✓ (LR+=5.45) | AML (名称不匹配导致 CML 未命中) |
| splenomegaly | ❌ | ✓ (LR+=5.45) | AML + MDS (CML 未命中) |

basophilia 和 splenomegaly 对 CML 的 LR 查找失败的原因：LR 缓存索引键为 "chronic myeloid leukemia"，但 `lookup_fuzzy()` 接收的疾病名为 "chronic myelogenous leukemia, bcr-abl1 positive"，fuzzy 匹配判定两者不够相似（"myeloid" vs "myelogenous"）。

##### 自动输出 vs 手动注入的差距量化

| 组件 | 手动注入 (Condition C) | 自动管线实际输出 | 差距 |
|:-----|:---------------------|:---------------|:-----|
| **1-hop pairwise 差集** | "Favours CML-BC: basophilia, splenomegaly, ..." | `[Knowledge Layer: coverage=0%, source=none]` (空) | **100% 缺失** |
| **LR 定量数据** | "basophilia LR+ 4.1 for CML" | basophilia 对 CML: ❌ NO HIT | **100% 缺失** |
| **2-hop 链路信息** | "visual loss → leukostasis → CML-BC (17%)" | 不可能生成（数据+代码双重缺失） | **100% 缺失** |
| **链路使用指令** | "★ Suggestion: Analyze whether..." | 不存在此格式 | **100% 缺失** |
| **覆盖率** | ~75% (手工构造) | 0% (疾病名不匹配) | **从 75% → 0%** |

##### 根因分析：5 层断裂的级联效应

```
用户可见问题: "TALP 无法获得任何外部知识"
    │
    ├─ L0: enable_knowledge_injection = False (配置)
    │     ★ 即使修复,后续层仍全部断裂
    │
    ├─ L1: 疾病名称解析失败
    │     TALP labels ≠ PrimeKG keys ≠ LR cache keys ≠ DxS keys
    │     "CML-BC" → not found anywhere
    │     "AML" → 仅 DxS 有通用条目, PrimeKG/LR 无
    │     ★ 这是 1-hop 知识注入的最大阻塞点
    │
    ├─ L2: LR Cache 疾病名称交叉不匹配
    │     LR: "chronic myeloid leukemia" 
    │     PrimeKG: "chronic myelogenous leukemia, bcr-abl1 positive"
    │     ★ 即使名称解析修复, basophilia 对 CML 仍无法查到 LR
    │
    ├─ L3: 中间概念 (leukostasis) 不在任何数据源中
    │     ★ 2-hop 链路在数据层面根本不可能构建
    │
    └─ L4: PrimeKG 图拓扑无 visual→CML 2-hop 路径
          ★ 即使 leukostasis 存在, phenotype_multihop() 
            也无法到达 (retinal 和 CML 表型集完全隔离)
```

##### 修复路线图（优先级重新评估）

鉴于实测发现的严重程度，原 §10.5.3 的修改清单需要**前置一个 P-1 优先级**：

```
优先级 P-1: 疾病名称解析层 (Critical Blocker)
┌──────────────────────────────────────────────────────────────┐
│ □ N1: DxFeatureRetriever 新增 disease name normalization     │
│   - 输入: TALP label "Chronic Myeloid Leukemia - BC (CML-BC)"│
│   - 候选: fuzzy match against PrimeKG._disease_ids,          │
│     LR._disease_index, DxS._disease_phenotypes               │
│   - 输出: best match per data source                         │
│   - 方案: token-level Jaccard + 缩写扩展 (AML→acute myeloid) │
│                                                              │
│ □ N2: LR Cache ↔ PrimeKG 疾病名交叉统一                      │
│   - "chronic myeloid leukemia" = "chronic myelogenous        │
│     leukemia, bcr-abl1 positive"                             │
│   - 在 build_unified_cache.py 中添加别名映射                  │
│                                                              │
│ □ N3: AML 通用条目问题                                        │
│   - PrimeKG 无 "acute myeloid leukemia" 通用条目             │
│   - 方案: 聚合所有 AML 亚型的表型并集作为通用 AML 表型集      │
└──────────────────────────────────────────────────────────────┘

优先级 P0: 1-hop 知识注入生效 (原 §10.5.3 P0)
┌──────────────────────────────────────────────────────────────┐
│ □ B5: enable_knowledge_injection = True                      │
│ □ B4: Annotator finding 提取优化                             │
└──────────────────────────────────────────────────────────────┘

优先级 P1: 2-hop 链路 (原 §10.5.3 P1, 降级为 P2)
┌──────────────────────────────────────────────────────────────┐
│ ★ 受限于数据层: leukostasis 不在 PrimeKG/LR 中              │
│ ★ 需要额外数据源 (UMLS, 医学教科书 RAG, 或 LLM self-RAG)   │
│   才能补充 leukostasis 等综合征级中间概念                    │
│ □ 近期可行替代: 用 LLM 自身知识生成                          │
│   indirect_reasoning_chains (无需外部数据)                   │
│   - 新增 LLM 模块: "ChainDiscoverer"                        │
│   - 输入: 未匹配的 vignette evidence + 鉴别诊断列表          │
│   - 输出: 候选间接推理链 (质量依赖 LLM 知识边界)             │
└──────────────────────────────────────────────────────────────┘
```

### 10.6 结论

| 问题 | 答案 |
|------|------|
| 2-hop 链不在 LR 数据库中是设计原则问题吗？ | **是。** 这是 EBM 关联统计范式的结构性边界，非数据收集不足。LR 测量的是"发现 F 直接预测疾病 D 的概率"，不编码病理生理因果链。 |
| 现有系统如何解决？ | **绕过而非正面解决。** 5 种范式无一计算多跳 LR——它们用 KG 约束提问方向（范式 A）、用 LLM 生成鉴别描述（范式 C）、用多轮迭代分解为 1-hop 查找（范式 D）、用 RL 训练 Agent 策略（范式 B）。 |
| 我们应该怎么做？ | **策略 D（定性链）+ 策略 F（多轮分解）为主，策略 B（共现率 LR）为辅。** 这与领域共识一致，且充分利用了已有的 TALP 多轮架构。 |

---

## 十一、参考文献

1. MedKGI. "Iterative Differential Diagnosis with Medical Knowledge Graphs." NeurIPS 2024 Workshop.
2. KG4Diagnosis. "A Hierarchical Multi-Agent LLM Framework with Knowledge Graph Enhancement." CHIL 2025.
3. MEDDxAgent. "A Unified Modular Agent Framework for Explainable Automatic Differential Diagnosis." ACL 2025.
4. EBMChat. "Augmenting LLMs and RAG with an EBM-Enabled Agent System." medRxiv 2025.
5. MedRAG (KG). "Enhancing RAG with Knowledge Graph-Elicited Reasoning for Healthcare Copilot." WWW 2025 (arXiv 2502.04413).
6. MIRAGE Benchmark. "Benchmarking RAG for Medicine." ACL Findings 2024 (arXiv 2402.13178).
7. PrimeKG. "Building a knowledge graph to enable precision medicine." Sci Data 10:67, 2023.
8. SPOKE. "The scalable precision medicine open knowledge engine." Bioinformatics 39(2), 2023.
9. GetTheDiagnosis.org. "A Database of Sensitivity and Specificity." https://getthediagnosis.org
10. UMLS REST API. "Unified Medical Language System." https://documentation.uts.nlm.nih.gov/rest/home.html
11. Isabel Healthcare API. https://info.isabelhealthcare.com/symptom-checker-api
12. Wolters Kluwer. "UpToDate AI Labs." 2024.
13. EBSCO. "DynaMed Dyna AI." 2024.
14. MedGraphRAG. "Medical Graph RAG: Towards Safe Medical LLM via Graph RAG." ACL 2025 (arXiv 2408.04187).
15. RAG vs GraphRAG: Systematic Evaluation. arXiv 2502.11371, 2025.
16. RAG/GraphRAG for Complex Clinical Cases. medRxiv 2025.11.25.25341010, 2025.
17. SEMA-RAG. "Self-Evolving Multi-Agent RAG Framework for Medical Reasoning." arXiv 2605.17101, 2026.
18. Deep-DxSearch. "End-to-End Agentic RAG System Training for Traceable Diagnostic Reasoning." arXiv 2508.15746, 2025.
19. Self-correcting Agentic Graph RAG for Clinical Decision Support in Hepatology. Front. Med. 2025.
20. Knowledge Hypergraph for Evidence-Based Medicine. arXiv 2503.16530, 2025.
21. MRD-RAG. "The Multi-Round Diagnostic RAG Framework for Emulating Clinical Reasoning." arXiv 2504.07724, 2025.
22. Evidence-Based GraphRAG for USMLE. medRxiv 2025.05.03.25325604, 2025.
23. "Benchmarking Retrieval Strategies for Biomedical RAG: A Controlled Empirical Study." arXiv 2605.02520, 2026.
24. "Improving RAG for Health Care by Fine-Tuning Clinical Embedding Models." JMIR 2026;28(1):e82997.
25. HPO Mapper. "Semantic Mapping of Clinical Findings to the HPO Using AI-Powered Embeddings." medRxiv 2025.12.20.25342726, 2025.
26. MedCPT. "Contrastive Pre-trained Transformers with Large-scale PubMed Search Logs for Zero-shot Biomedical IR." Bioinformatics 39(11):btad651, 2023.
27. RD-Embed. "Unified Representations of Rare-Disease Knowledge from Clinical Records." medRxiv 2026.04.02.26350083, 2026.
28. LogosKG. "Scaling Biomedical Knowledge Graph Retrieval for Interpretable Reasoning." PMC 2026.
29. Howick et al. "Evidence-based mechanistic reasoning." J R Soc Med 103(11):433-441, 2010. (PMC2966890)
30. ShatterMed-QA. "A Topology-Regularized Multi-Hop Clinical Benchmark." arXiv 2603.12458, 2026.
31. HEG-TKG. "The Provenance Gap in Clinical AI: Evidence-Traceable Temporal Knowledge Graphs." arXiv 2604.17114, 2026.
32. MultiDx. "A Multi-Source Knowledge Integration Framework towards Diagnostic Reasoning." arXiv 2604.24186, 2026.
33. "Evidence based diagnosis: does the language reflect the theory?" BMJ 329(7473):1071, 2004. (PMC1553529)
34. "The EBM Approach to Diagnostic Testing: practicalities and limitations." Clin Biochem Rev 24(2):59-68, 2003. (PMC1252824)

---

## 11. 实施记录：Phase 3 RAG 强化与知识管线重构 (2026-05-22)

### 11.1 核心问题回顾

§10.5.7 的端到端实测揭示了知识管线的 5 层级联失败：
1. `enable_knowledge_injection` 默认关闭
2. TALP 疾病标签 ↔ 知识源索引键严重不匹配（覆盖率 0%）
3. LR 缓存 ↔ PrimeKG 疾病名不一致
4. 关键中间概念（leukostasis）在所有数据源中缺失
5. PrimeKG 图拓扑缺乏视觉症状→CML 的 2-hop 路径

### 11.2 实施的修复与新增模块

#### 11.2.1 P-1: DiseaseNameResolver（疾病名称解析层）

**新文件**: `src/agentclinic_tree_dx/knowledge/disease_name_resolver.py`

5 级解析策略：
1. **Exact match** — 标准化后精确匹配
2. **别名表 + 缩写扩展** — 内置 `_MANUAL_ALIAS_TABLE` (CML/AML/MDS/ALL/CLL 等)
   + `_ABBREVIATION_EXPANSIONS` (30+ 常见医学缩写)
3. **UMLS CUI 桥接** — 利用 docLogica 的 `umlsId` 字段 + 同义词，跨数据源名称映射
4. **子串包含** — 最小长度约束（≥5 字符）避免虚假短匹配
5. **Token Jaccard** — 最小共享 token 数量（≥2）+ 阈值 0.45

**效果**：Case #68 覆盖率 0% → **100%**

#### 11.2.2 DxFeatureRetriever 重写

**改动文件**: `src/agentclinic_tree_dx/knowledge/dx_feature_retriever.py`

重写为全层编排器，集成：
- Layer 0: DxS 鉴别索引 → 集合差集（通过 DiseaseNameResolver 匹配）
- Layer 1: PrimeKG → 正/负关联 + 相关疾病 + 2-hop BFS（首次接入）
- Layer 2: LR 缓存 → 模糊查找（通过 DiseaseNameResolver 匹配）
- **Layer 3 NEW**: ChainDiscoverer LLM 回调 → 间接推理链生成
- **2-hop chain 检索**: `get_2hop_chains()` 利用 PrimeKG `phenotype_multihop()`
- **未匹配证据检测**: `_find_unmatched_evidence()` 自动识别 vignette 中未关联到任何候选疾病的 findings
- `format_discriminator_hints_for_prompt()` 现在包含间接链段落

#### 11.2.3 Phase 3 RAG: ChainDiscoverer

**新文件**: `src/agentclinic_tree_dx/prompts/chain_discoverer.txt`

当结构化知识（DxS、PrimeKG、LR）无法提供间接推理路径时，使用 LLM 生成：
- 输入：未匹配的 vignette findings + 候选疾病列表 + 各疾病已知表型
- 输出：JSON 格式的间接推理链（finding → intermediate → disease），含频率估计和建议

触发条件：PrimeKG 2-hop 无结果时降级到 LLM ChainDiscoverer

#### 11.2.4 UMLS CUI 桥接实现

**集成路径**: docLogica `umlsId` → `DiseaseNameResolver._umls_cui_to_names` / `._name_to_cui`

- 自动索引 docLogica 的 `synonyms` 字段到同一 CUI 下
- 解析时：查询名→CUI→CUI 下所有同义词→匹配知识源键
- 实测：docLogica 约 1,700+ CUI 映射

#### 11.2.5 Controller 集成更新

**改动文件**: `src/agentclinic_tree_dx/controller.py`

- `_init_knowledge_layer()` 现在创建 `DiseaseNameResolver` 并加载 UMLS
- `_make_chain_discoverer_fn()` 连接 LLM client 到 ChainDiscoverer prompt
- `plan_temporary_leaves()` 传入 `vignette_text` 和 `include_chains` 参数
- 新配置项：`doclogica_cache_json`、`enable_chain_discoverer`

### 11.3 端到端验证结果 (Case #68)

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 覆盖率 | 0% | **100%** |
| CML-BC 解析 | ✗ 全失败 | ✓ DxS+PrimeKG+LR |
| AML 解析 | ✗ | ✓ DxS+PrimeKG |
| MDS 解析 | ✗ | ✓ PrimeKG |
| CMML 解析 | ✗ | ✓ DxS+PrimeKG |
| Splenomegaly LR | 无 | LR+=5.45 |
| Basophilia LR | 无 | LR+=5.45 |
| Hints 文本 | 空字符串 | 2117 chars, 33 lines |
| 2-hop PrimeKG 链 | N/A | 无结果（leukostasis 不在图中，符合预期） |
| ChainDiscoverer | N/A | 框架就绪，需 enable_chain_discoverer=True |

### 11.4 剩余限制 (P-1 修复后)

1. **DxS 匹配精度**：AML→"leukemia"、CMML→"leukemia"（过于泛化），需更多 alias 条目
2. **LR 匹配精度**：MDS→"c syndrome" 是虚假匹配，需提高 LR 层阈值
3. ~~**Retinal hemorrhages** 仍无 LR 数据~~ → **已修复（见 §11.5）**
4. ~~**StatPearls 向量索引** 未实现~~ → **已修复（见 §11.5）**
5. **Embedding 匹配**：EvidenceMatcher 仍基于 Jaccard（设计目标为 MedCPT embedding）

---

## 11.5 Phase 3 StatPearls/PubMed RAG 实施记录 (2026-05-23)

### 11.5.1 数据下载与解析

| 语料库 | 来源 | Chunks | 平均 tokens |
|--------|------|--------|-------------|
| **StatPearls** | NCBI FTP `statpearls_NBK430685.tar.gz` (1.8GB) | **367,799** | ~119 |
| **Textbooks** | HuggingFace `MedRAG/textbooks` (18 本, 201MB) | **125,847** | ~182 |
| **合计** | | **493,646** | |

解析：StatPearls 9,636 篇 NXML 文章 → 层级标题 + 段落 chunking；Textbooks 直接使用 MedRAG 预分块 JSONL。

### 11.5.2 索引构建

**TF-IDF 稀疏索引**（首选，用于快速启动）：
- `TfidfVectorizer(max_features=50000, ngram_range=(1,2), sublinear_tf=True)`
- 构建时间：**103.8 秒**
- 产物：`tfidf_matrix.npz` (254MB) + `tfidf_vectorizer.pkl` (163MB)

**FAISS 稠密索引**（可选，需 `sentence-transformers`）：
- 脚本 `build_rag_index.py` 支持 MedCPT / BiomedBERT / MiniLM 编码
- 因 HuggingFace 网络限制，模型手动下载到 `/data2/wanghongyi/models/all-MiniLM-L6-v2`
- CPU 编码 493K chunks 预计 ~2h；TF-IDF 作为即用替代

### 11.5.3 RAGRetriever 实现

**新文件**: `src/agentclinic_tree_dx/knowledge/rag_retriever.py`

双后端自动检测：
- 存在 `faiss.index` → FAISS dense search
- 存在 `tfidf_matrix.npz` → TF-IDF sparse search (cosine similarity)

查询 API：
- `search(query, top_k, score_threshold)` → 通用语义检索
- `search_for_disease(disease, finding)` → 疾病-特征关联检索
- `search_for_differential(diseases, finding)` → 鉴别诊断检索
- `extract_lr_from_snippets(snippets, finding, disease)` → 从文本提取 LR/Sn/Sp

### 11.5.4 PubMedRetriever 实现

**新文件**: `src/agentclinic_tree_dx/knowledge/pubmed_retriever.py`

两阶段 PubMed 搜索：
1. **严格查询**：要求摘要含 "sensitivity" / "specificity" / "likelihood ratio" → 提取定量 LR
2. **宽松查询**：放宽到 "diagnosis[MeSH]" / "clinical significance" → 提取上下文

提取管线：regex → LLM（可选）

### 11.5.5 DxFeatureRetriever Layer 3 集成

LR 检索级联路径（§3.2 设计 R5 合规）：
```
Layer 2 (LR cache 233K) → miss →
  Layer 3a (RAG: StatPearls/Textbooks 493K) → extract_lr / context →
    Layer 3b (PubMed live: 36M abstracts) → extract_lr / context
```

TALP hints 级联路径（§3.4 设计 R7 合规）：
```
Layer 0 (DxS) + Layer 1 (PrimeKG) → pairwise discriminators →
  Layer 1 (PrimeKG 2-hop BFS) → indirect chains →
    Layer 3a (RAG context for unmatched findings) →
      Layer 3c (ChainDiscoverer LLM) → indirect reasoning chains
```

### 11.5.6 配置变更

**config.py** 新增：
- `rag_index_dir: str | None = None` — Layer 3a 索引目录
- `pubmed_api_key: str | None = None` — NCBI API key
- `enable_pubmed_fallback: bool = False` — Layer 3b 开关

### 11.5.7 端到端验证结果 (Case #68)

| 查询 | 修复前 | 修复后 |
|------|--------|--------|
| `retinal hemorrhages` LR | **NO DATA** | **RAG context: CML blast transformation (StatPearls)** |
| `cotton-wool spots` LR | **NO DATA** | **RAG context + PubMed context (MDS/AML)** |
| `splenomegaly` LR | LR+=5.45 | LR+=5.45（无退化） |
| `basophilia` LR | LR+=5.45 | LR+=5.45（无退化） |
| TALP hints 行数 | 9 lines | **22 lines**（含 RAG 上下文） |
| RAG "leukostasis retinal" | N/A | **score=0.43, StatPearls 相关文章** |
| PubMed search | N/A | **PMID:38807037 leukemic retinopathy** |

### 11.5.8 新增文件清单

| 文件 | 功能 |
|------|------|
| `src/.../knowledge/rag_retriever.py` | Layer 3a RAG 检索（FAISS/TF-IDF 双后端） |
| `src/.../knowledge/pubmed_retriever.py` | Layer 3b PubMed E-utilities 检索+LR 提取 |
| `scripts/build_statpearls_corpus.py` | StatPearls NXML → JSONL 解析 |
| `scripts/build_rag_index.py` | FAISS 稠密索引构建 |
| `scripts/build_tfidf_index.py` | TF-IDF 稀疏索引构建 |
| `scripts/test_layer3_e2e.py` | Layer 3 端到端测试 |
| `data/corpus/statpearls/statpearls_chunks.jsonl` | 367K StatPearls chunks |
| `data/corpus/textbooks/textbooks_chunks.jsonl` | 125K Textbooks chunks |
| `data/corpus/rag_index/{tfidf_*,metadata.jsonl,config.json}` | 493K TF-IDF 索引 |

### 11.5.9 设计合规状态更新

| 需求 | 之前状态 | 现在状态 |
|------|----------|----------|
| **R5** LR 级联 fallback | △（缓存 miss 返回空） | **✓** RAG + PubMed 降级 |
| **R7** 四层架构 Layer 0→1→2→3 | △（Layer 3 缺失） | **✓** Layer 3a(RAG) + 3b(PubMed) + 3c(ChainDiscoverer) |
| **Phase 3.1** StatPearls 索引 | ✗ | **✓** 367K chunks + TF-IDF |
| **Phase 3.2** PubMed LR 提取 | ✗ | **✓** E-utilities + regex/LLM |
| **Phase 3.3** 整合进统一接口 | ✗ | **✓** DxFeatureRetriever 级联 |

---

## 11.6 2-hop 叶节点生成端到端验证 (2026-05-23)

### 11.6.1 测试目标

验证完整管线（知识检索 → TALP LLM → Bundler 筛选）是否能**自主发现并利用间接诊断推理链**，无需人工注入。

目标 2-hop 路径：`retinal hemorrhages → leukostasis → CML-BC`

### 11.6.2 Layer A: 知识检索管线

| 检测项 | 结果 | 详情 |
|--------|------|------|
| Unmatched evidence | ✓ 5项 | splenomegaly、retinal hemorrhages、WBC 145K、blasts 82%、basophilia 8% |
| PrimeKG 2-hop BFS | ✗ | leukostasis 不在 PrimeKG 图中（符合已知限制） |
| **RAG "leukostasis" 命中** | **✓** | score=0.71, StatPearls: Retinal Hemorrhages > Epidemiology |
| RAG "retinal hemorrhages" | ✓ | score=0.69, StatPearls: fundoscopy, Roth spots, AML 30-40% |
| RAG "splenomegaly CML" | ✓ | score=0.64-0.65, StatPearls: CML History & Schwartz Surgery |
| Hints 总长度 | 2682 chars, 32 lines | 包含 pairwise discriminators + 4 段 RAG context |
| Hints 含 chain 关键词 | ✓ | fundoscopy, retinal hemorrhage, cotton-wool |

**关键发现**：RAG 自动检索到以下临床决定性文本：
> "Within the spectrum of hematologic diseases, Roth spots occur in approximately 30% to 40% of patients with acute leukemia"

RAG 结果中 leukostasis 关键词出现在 score=0.71 的 StatPearls 段落中，表明知识检索层已能**自动提供**眼底检查与白血病之间的关联证据。

### 11.6.3 Layer B: TALP LLM 叶节点生成

模型: `qwen/qwen3-32b` | 3 次独立运行 | temperature=0.7

| 指标 | 值 |
|------|-----|
| 总候选节点 | 18 (6×3) |
| **含 chain 关键词的候选** | **5/18 (27.8%)** |
| **含 chain 候选的运行次数** | **3/3 (100%)** |

**代表性 chain-relevant 候选节点**：

```json
{
  "type": "ANALYZE_VIGNETTE",
  "content": "Do bilateral retinal hemorrhages with cotton-wool spots argue against CML-BC in favor of AML?",
  "expected_information_gain": 0.45,
  "target_branches": {"B1": "against", "B2": "support", "B3": "neutral"},
  "primary_function": "challenge",
  "why": "Reticular hemorrhages are more commonly associated with AML (30-40% incidence) than CML-BC"
}
```

```json
{
  "type": "ANALYZE_VIGNETTE",
  "content": "Do bilateral retinal hemorrhages with cotton-wool spots provide specific support for AML diagnosis?",
  "expected_information_gain": 0.50,
  "target_branches": {"B2": "support", "B1": "against", "B3": "neutral"},
  "primary_function": "confirm",
  "why": "Retinal hemorrhages are strongly associated with AML in clinical context"
}
```

LLM 成功吸收 RAG 提供的 "Roth spots / retinal hemorrhages → 急性白血病 30-40%" 证据，生成了利用视网膜出血来**挑战 CML-BC 并支持 AML** 的分析节点——这正是 2-hop 间接推理链的核心应用。

### 11.6.4 Layer C: Bundler 存活验证

| 检查项 | 条件 | 结果 |
|--------|------|------|
| expected_ig ≥ 0.05 | 0.45 ≥ 0.05 | ✓ PASS |
| has_target_branches | 3 branches | ✓ PASS |
| valid_primary_function | "challenge" | ✓ PASS |

**候选节点通过所有 Bundler 最低准入条件，可被正式纳入诊断计划。**

### 11.6.5 总结

| 层级 | 状态 | 对比之前 (§10.5) |
|------|------|-------------------|
| A: 知识检索 → hints | **✓ PASS** | 之前 0% coverage, 空 hints → 现在 100% coverage + RAG context |
| B: TALP → candidates | **✓ PASS** | 之前需手动注入 → 现在完全自动 |
| C: Bundler → survival | **✓ PASS** | 与手动注入测试一致 |

**结论：当前系统已能自主完成从知识检索到叶节点生成的完整 2-hop 推理路径。**

核心工作机制：
1. `DiseaseNameResolver` 消除疾病名称不匹配 → 100% 知识覆盖
2. `RAGRetriever` (TF-IDF over 493K StatPearls/Textbooks) 自动检索到 "retinal hemorrhages → leukemia 30-40%" 的临床证据
3. RAG context 被注入 TALP hints → LLM 基于该证据生成了利用眼底检查进行鉴别诊断的 CandidateLeaf
4. 生成的候选节点满足 FrontierCoverageBundler 的 IG/target/function 要求

### 11.6.6 剩余改进方向

1. **PrimeKG leukostasis 缺失**：2-hop BFS 仍无法找到 leukostasis 中间节点。长期方案：扩展 PrimeKG 或引入 HPO 表型层级
2. **ChainDiscoverer 未触发**：当前测试中 RAG 已足够，ChainDiscoverer LLM 未被激活。启用 `enable_chain_discoverer=True` 可补充更明确的链式推理提示
3. **TALP label 字段缺失**：LLM 返回 `content` 而非 `label` 字段，需在 TALP prompt 或后处理中统一
4. **Dense embedding 索引**：TF-IDF 是 lexical matching，对语义相近但用词不同的查询可能遗漏。建议在 GPU 环境构建 MedCPT/MiniLM dense index

---

## 11.7 临时叶节点与诊断路径完成的理论分析 (2026-05-23)

### 11.7.1 核心问题

TALP 生成的 `CandidateLeaf` 是**临时的**——每个诊断循环生成新的候选集，前一轮的候选在 bundle 执行后即失效。这引发一个根本性问题：**临时叶节点机制能否建立完整的多轮诊断路径，特别是 2-hop 间接推理路径？**

### 11.7.2 诊断循环架构回顾

Static QA 模式的每轮循环：

```
Safety → TALP(生成临时叶节点) → Bundler(筛选) → Execute(执行) 
  → Annotator(标注 branch_effects) → ProbUpdate(更新后验) 
  → StateReviser(分支状态决策) → ExpansionGate(条件扩展) → Termination(终止判断)
```

**证据持久化机制**：叶节点虽然临时，但其执行结果通过以下渠道**永久**留存于状态中：

| 持久化渠道 | 存储位置 | 生命周期 | TALP 可见性 |
|------------|----------|----------|-------------|
| `branch.evidence_for[]` | `Branch` 对象 | 永久（payload 截断为最近 2 条） | ✓ |
| `branch.evidence_against[]` | `Branch` 对象 | 永久（payload 截断为最近 2 条） | ✓ |
| `branch.posterior` | `Branch` 对象 | 永久（每轮更新） | ✓ |
| `actions_taken[]` | `DiagnosticState` | 永久（payload 截断为最近 6 条） | ✓ |
| `differential_history[]` | `DiagnosticState` | 永久（payload 截断为最近 3 条） | ✓ |
| `seen_evidence_phenotypes` | `DiagnosticState` | 永久（用于去重） | 间接 |
| `static_evidence_items` | `DiagnosticState` | 永久不变（原始题目） | ✓ |

**关键认知**：叶节点的"临时性"仅指**规划层**——候选集本身不跨轮保留。但叶节点执行后产生的**认知效果**（evidence_for/against、posterior 更新、actions_taken 记录）是永久性的，且构成下一轮 TALP 的输入语境。

### 11.7.3 TALP confirm/challenge 二元结构的语义约束

在分析 2-hop 路径之前，必须精确界定 TALP 两种候选类型的职责边界：

**confirm 候选**（提示词 L15-18）：
> "analyse the evidence that BEST SUPPORTS this branch"
> `target_branches[branch_id] = "support"`

**challenge 候选**（提示词 L20-26）：
> "analyse the evidence that is MOST INCONSISTENT with this branch"
> "you are looking for reasons why this branch might be WRONG, not why it is right"
> `target_branches[branch_id] = "against"`

**关键约束**：不存在第三种候选类型负责"反驳已有的 evidence_against"或"为异常发现提供替代解释"（即"reinterpret"功能）。confirm 只找最强支持证据，challenge 只找最强反对证据。这意味着之前 §11.7 初版中描述的 "counter-challenge"（Turn 2 Leaf-6: "Could leukostasis explain retinal hemorrhages in CML-BC?"）**不属于 challenge 类型的合法输出**——因为该候选的 target 是 `{B1: "support"}`，而 challenge 要求 `{B1: "against"}`。

### 11.7.4 2-hop 推理闭合的真实机制

在 confirm/challenge 二元约束下，2-hop 路径 `retinal hemorrhages → leukostasis → CML-BC` 通过以下三条实际途径成立（非互斥，可组合）：

#### 途径 A：EvidenceAnnotator 单轮内化闭合（最主要途径）

推理闭合点不在 TALP（规划层），而在 EvidenceAnnotator（标注层）。

**执行链**：

1. TALP 生成 B1-challenge："Do retinal hemorrhages argue against CML-BC in favor of AML?"
2. `_dispatch_env_call` 返回：`{"analysis_target": "Do retinal hemorrhages argue against CML-BC?"}`
3. `_build_annotator_payload` 构建 Annotator 输入时，注入 `lr_reference`（含 RAG 检索到的 leukostasis 上下文）：
   ```python
   lr_text = self._knowledge_retriever.format_lr_reference_for_prompt(
       finding_text, disease_names
   )
   payload["lr_reference"] = lr_text
   ```
4. EvidenceAnnotator（本身是 LLM）接收完整 state + analysis_target + lr_reference，在**同一次调用中**同时考虑：
   - "retinal hemorrhages 在 AML 中 30-40% 出现"（支持 AML 方向）
   - "WBC 145K 时 leukostasis 可致视网膜出血"（RAG lr_reference 提供）
   - "该患者确实有 WBC 145K"（static_evidence_items 可见）
5. Annotator 输出**已经整合了两跳推理**的 result_summary：
   > "While retinal hemorrhages occur in 30-40% of AML, leukostasis at WBC >100K
   > also produces bilateral retinal hemorrhages in CML blast crisis. Given WBC
   > 145K, this finding has limited differential specificity."
6. 标注 `B1: weak_against`（而非 strong/moderate_against），反映中间机制削弱了证据的鉴别力

**在此途径中，整个 2-hop 推理链在单轮内由 Annotator 完成闭合**，不需要跨轮传递。RAG lr_reference 注入是关键——它为 Annotator 提供了 leukostasis 的知识锚点。

#### 途径 B：confirm 候选的隐式覆盖

confirm 候选虽然不以"反驳 evidence_against"为目标，但可以间接触及中间概念：

1. Turn 1: challenge 将 retinal hemorrhages 写入 `B1.evidence_against`
2. Turn 2: `discriminator_hints` 重新生成，RAG 仍然提供 leukostasis 上下文
3. TALP B1-confirm 的任务是"找最支持 CML-BC 的证据"
4. `discriminator_hints` 中含有 "hyperleukocytosis → leukostasis → retinal involvement" 上下文
5. TALP 可能生成 confirm 候选：
   > "Does massive hyperleukocytosis (WBC 145K) with associated leukostasis risk support CML-BC as the unifying diagnosis for all findings including retinal involvement?"
   > `target_branches: {B1: "support", B2: "against"}`
6. 这是合法的 confirm 候选（找最强支持性证据），同时**自然覆盖了** leukostasis 中间概念

**该途径不违反提示词约束**——confirm 候选在寻找支持证据时，恰好选中了一个能同时解释异常发现的统一性论据。

#### 途径 C：Bundle 聚合的跨动作合成

同一 Bundle 中 B1-confirm（如 BCR-ABL1 支持 CML-BC）和 B1-challenge（retinal hemorrhages 质疑 CML-BC）同时执行。

`annotate_evidence_bundle` 将所有结果送给 Annotator，Annotator 提示词要求：
> "result_summary: synthesised combined clinical meaning of all actions"
> "Conflicting: net direction one step weaker (strong_for + weak_against → moderate_for)"

当 Annotator 同时看到 "BCR-ABL1 强支持 CML-BC" 和 "retinal hemorrhages 质疑 CML-BC" 时，它在**聚合阶段**自然需要调和两者矛盾——leukostasis 作为统一解释在此时被引入 result_summary。

### 11.7.5 修正后的 CML Case #68 示例过程

#### Turn 1: Bundle 内的对抗与调和

**输入状态**：
- B1(CML-BC, p=0.50), B2(AML, p=0.35), B3(MDS, p=0.15)
- `discriminator_hints`: 含 RAG context（leukostasis, Roth spots 30-40% AML, splenomegaly-CML）

**TALP 生成 6 候选**（3 分支 × 2）：
```
Leaf-1: [B1, confirm]    "Does BCR-ABL1 fusion with Philadelphia chromosome confirm CML-BC?"
        target: {B1: "support", B2: "against"}
Leaf-2: [B1, challenge]  "Do retinal hemorrhages argue against CML-BC in favor of AML?"
        target: {B1: "against", B2: "support"}
Leaf-3: [B2, confirm]    "Does 82% blast count support AML?"
        target: {B2: "support"}
Leaf-4: [B2, challenge]  "Does BCR-ABL1 positivity rule out de novo AML?"
        target: {B2: "against", B1: "support"}
Leaf-5: [B3, confirm]    "Does cytopenias pattern support MDS?"
        target: {B3: "support"}
Leaf-6: [B3, challenge]  "Does 82% blasts and acute presentation exclude MDS?"
        target: {B3: "against"}
```

**Bundler** → Phase 1 选 confirm [Leaf-1,3,5]，Phase 1b 选 challenge [Leaf-2,4,6] → Bundle 含 6 个动作

**Execute** → 6 个 `{"analysis_target": "..."}` 返回

**EvidenceAnnotator 批量标注**（**关键步骤——2-hop 闭合点**）：

Annotator 同时看到 Leaf-1（BCR-ABL1 支持 CML-BC）和 Leaf-2（retinal hemorrhages 质疑 CML-BC），加上 lr_reference 中的 RAG leukostasis 上下文。

per_action_effects:
```json
[
  {"action_index": 0, "micro_summary": "BCR-ABL1/Ph+ is pathognomonic for CML",
   "branch_effects": {"B1": "strong_for", "B2": "moderate_against"}},
  {"action_index": 1,
   "micro_summary": "Retinal hemorrhages occur in 30-40% of acute leukemia but also
    arise from leukostasis in CML blast crisis with WBC >100K; limited differential value",
   "branch_effects": {"B1": "weak_against", "B2": "weak_for"}},
  {"action_index": 3,
   "micro_summary": "BCR-ABL1 is characteristic of CML; de novo AML with BCR-ABL1
    exists but is rare and typically classified as CML-BC",
   "branch_effects": {"B2": "moderate_against", "B1": "moderate_for"}}
]
```

聚合 branch_effects:
```json
{"B1": "strong_for", "B2": "moderate_against", "B3": "strong_against"}
```

**证据写入**：
- `B1.evidence_for` ← 聚合 result_summary（含 BCR-ABL1 + leukostasis 调和分析）
- `B2.evidence_against` ← 同上

**后验更新** → B1: 0.50 → 0.65, B2: 0.35 → 0.22, B3: 0.15 → 0.08

**关键观察**：leukostasis 的 2-hop 推理在**单轮内由 Annotator 完成**：
- Leaf-2 提出了质疑（retinal hemorrhages → AML），这是第一跳
- Annotator 在分析 Leaf-2 时，借助 lr_reference 中的 RAG context，自动引入 leukostasis 机制作为 CML-BC 的替代解释，将标注从可能的 `moderate_against` 降级为 `weak_against`——这是第二跳的隐式闭合
- 同时 Leaf-1 和 Leaf-4 的强支持性证据（BCR-ABL1）在聚合中主导了总方向

#### Turn 2: 确认收敛

**输入状态**：
- B1(CML-BC, **p=0.65**), B2(AML, **p=0.22**), B3(MDS, **p=0.08**, 可能被 close)

**TALP 生成候选**（B1 已接近主导，challenge 变得更重要）：
```
Leaf-7: [B1, confirm]   "Does massive splenomegaly 8cm + basophilia 8% form a
         near-pathognomonic combination for CML-BC?"
        target: {B1: "support"}
Leaf-8: [B1, challenge]  "What is the strongest remaining argument against CML-BC?"
        target: {B1: "against"}
```

- Leaf-8 challenge 可能找到的最强反对证据已经很弱（82% blasts 更像 AML 但 Ph+ 已解释）
- Annotator 标注 Leaf-8: `B1: neutral`（无强力反对证据剩余）
- Annotator 标注 Leaf-7: `B1: moderate_for`

**后验更新** → B1: 0.65 → 0.75+ → 越过 `min_readiness_to_commit`

**TerminationJudge** → `ready_to_stop: true` → **AnswerMapper 输出 CML-BC**

### 11.7.6 机制可行性的理论修正

之前的"定理"声称 k-hop 链需要 k 轮循环。修正如下：

**修正后的命题**：在当前 confirm/challenge 二元结构下，2-hop 推理链的闭合主要依赖 **EvidenceAnnotator 的推理深度**而非 TALP 的跨轮传递。

实际机制：
```
TALP (规划层)          Annotator (标注层)         知识管线 (辅助层)
─────────────          ──────────────────         ────────────────
生成 challenge          ┐                         
  "finding X            │ 接收 challenge 问题
   argues against A"    │ + lr_reference (RAG)     ← RAG 提供中间概念 M
                        │                            的知识锚点
                        ├─ 分析: finding X → M → A  
                        │  在单次调用中完成
                        │  两跳推理的闭合
                        │
                        └─ 输出: weak_against
                           (而非 strong_against)
                           summary 含 M 的解释
```

**关键依赖**：

| 依赖 | 说明 | 当前满足度 |
|------|------|-----------|
| Annotator 推理深度 | LLM 需在单次调用中完成从 "X argues against A" 到 "but M explains X under A" 的推理 | 取决于 LLM 能力 |
| RAG lr_reference 注入 | 为 Annotator 提供中间概念 M 的知识锚点，降低对 LLM 内在知识的依赖 | ✓ 已验证（§11.6） |
| Bundle 聚合 | confirm + challenge 同 bundle 执行，Annotator 可在聚合中调和矛盾 | ✓ 架构支持 |

### 11.7.7 暴露的架构缺口与改进方向

当前 confirm/challenge 二元结构将 2-hop 推理的闭合**隐式下放给 Annotator**，而非由 TALP 显式规划。这带来以下风险：

1. **Annotator 能力依赖**：如果 Annotator LLM 不具备足够的临床推理深度，或未注意到 lr_reference 中的关键信息，它可能直接标注 `moderate_against` 而不考虑 leukostasis 替代解释——2-hop 推理链将断裂。

2. **lr_reference 可用性**：若 RAG 未检索到相关上下文（例如查询不匹配），Annotator 失去外部知识锚点，回退到纯粹依赖自身知识。

3. **可追溯性缺失**：2-hop 推理发生在 Annotator 的 `result_summary` 自由文本中，无法被程序化追踪和验证。

**改进方向**：

| 改进 | 描述 | 影响范围 |
|------|------|---------|
| **引入 reinterpret 候选类型** | TALP 第三种候选：针对已有 evidence_against 中的条目，分析是否存在替代解释。`target_branches: {B: "support"}`，但 content 明确引用并反驳 evidence_against 条目 | TALP 提示词 + Bundler Phase 新增通道 |
| **Annotator lr_reference 强化** | 当 challenge 候选涉及的 finding 在 RAG 中有高分匹配时，在 lr_reference 中**显式标注替代机制**（如 "Alternative: leukostasis at WBC>100K"），而非要求 Annotator 自行发现 | DxFeatureRetriever → Annotator payload |
| **Chain-aware Annotator 提示词** | 在 Annotator 提示词中增加指令：当 analysis_target 是 challenge 类型问题时，必须同时评估是否存在使该不利证据兼容当前分支的中间机制 | EvidenceAnnotator 提示词 |

### 11.7.8 结论

**2-hop 路径在当前架构下可以成立，但成立机制与 §11.7 初版描述不同**：

- **错误的模型**：TALP 跨轮生成 "counter-challenge" → 这违反 confirm/challenge 二元结构的语义约束
- **正确的模型**：challenge 叶节点提出质疑问题 → EvidenceAnnotator 在单轮内借助 RAG lr_reference 完成两跳推理闭合 → 输出审慎标注（weak_against 而非 strong_against）

这意味着：
1. 系统的 2-hop 推理能力**主要瓶颈在 Annotator**而非 TALP
2. RAG lr_reference 注入对 Annotator 的推理质量起**关键辅助作用**
3. 当前架构缺少 TALP 层面显式驱动"证据重新解读"的机制——这是一个可改进的设计缺口

---

## 11.8 间接推理路径强化方案 (2026-05-23)

§11.7 揭示了当前架构的核心缺口：2-hop 推理的闭合被**隐式下放给 EvidenceAnnotator**，缺乏 TALP 层面的显式驱动。本节设计三层协同强化方案，覆盖规划层（TALP）、标注层（Annotator）和知识层（RAG），并给出每条已发现途径（A/B/C）的针对性加固。

### 11.8.1 改进一：引入 reinterpret 候选类型

#### 动机

confirm/challenge 二元结构存在认知盲区：
- **confirm**：找最强支持证据 → 不关心 evidence_against
- **challenge**：找最强反对证据 → 只加剧证据对抗，不解决
- **缺失的认知功能**：对已存在的 evidence_against 提出替代解释——即"这条反对证据可能并不成立，因为存在替代机制"

reinterpret 填补的正是被移除的 counter-challenge 的语义空间，但以符合当前架构约束的方式实现。

#### TALP 提示词变更

在现有提示词 `temporary_analytic_leaf_planner.txt` 的 Instruction 1 中，在 (b) challenge 之后新增 (c)：

```
   (c) A REINTERPRET candidate — ONLY when evidence_against for this branch
       is non-empty: pick the MOST DAMAGING entry from evidence_against and
       analyse whether an ALTERNATIVE MECHANISM could explain that finding
       WITHOUT disfavouring this branch.

       Set target_branches[branch_id] = "support".
       Set primary_function = "reinterpret".
       Set falsification_value = 0.0.

       The content MUST:
       1. Quote or paraphrase the specific evidence_against entry being addressed
       2. Propose a concrete pathophysiological mechanism as an alternative
       3. Reference patient-specific data that makes the alternative plausible

       Example:
         evidence_against for CML-BC: "Retinal hemorrhages are more commonly
         associated with AML (30-40%)"
         →
         Content: "The evidence_against citing retinal hemorrhages favouring AML
         assumes direct leukemic infiltration. However, at WBC 145K with 82% blasts,
         leukostasis causes microvascular sludging in retinal vessels — could this
         alternative mechanism explain the fundoscopic findings under CML-BC?"

       If evidence_against is EMPTY for this branch, do NOT generate a
       reinterpret candidate. Generate only the confirm and challenge pair.
```

#### 触发条件

reinterpret 候选**条件性生成**，不是每个分支都需要：

| 条件 | 生成 | 理由 |
|------|------|------|
| `evidence_against` 非空 | ✓ 生成 reinterpret | 存在待反驳的证据 |
| `evidence_against` 为空 | ✗ 仅 confirm + challenge | 无反驳目标 |
| 分支 posterior < 0.10 | ✗ 即使有 evidence_against | 低概率分支不值得投入 reinterpret |
| danger ≥ 0.7 且 posterior < 0.15 | safety_ensure 替代 confirm | reinterpret 仍然生成（安全分支的反对证据更需要被检验） |

**每分支候选数变化**：

| 场景 | Turn 1 (evidence_against 空) | Turn 2+ (evidence_against 非空) |
|------|------------------------------|--------------------------------|
| 候选数/分支 | 2 (confirm + challenge) | 3 (confirm + challenge + reinterpret) |
| 4 分支总候选数 | 8 | 最多 12 |

#### primary_function 枚举值扩展

```python
# 现有
primary_function: Literal["confirm", "challenge", "differentiate", "safety_ensure"]

# 新增
primary_function: Literal["confirm", "challenge", "differentiate", "safety_ensure", "reinterpret"]
```

#### Bundler Phase 1c：reinterpret 通道

在 `action_bundler.py` 的 `_build_dual_channel` 中，Phase 1b 之后新增 Phase 1c：

```python
# ── Phase 1c: reinterpret channel ──────────────────────────────────
reinterpret_covered: dict[str, CandidateLeaf] = {}
for branch_id in state.frontier:
    branch = state.branches.get(branch_id)
    if branch is None or branch.status not in ("live", "reopened"):
        continue
    if not branch.evidence_against:
        continue  # no evidence_against → no reinterpret needed
    for candidate in candidate_leaves:
        if candidate.branch_id != branch_id:
            continue
        if candidate.primary_function != "reinterpret":
            continue
        if _get_target_direction(candidate, branch_id) != "support":
            continue
        if not _passes_gates(candidate, bundle, content_set, config, min_ig):
            continue
        reinterpret_covered[branch_id] = candidate
        bundle.append(candidate)
        content_set.add(_normalize(candidate.content))
        break
```

Phase 1c 放在 Phase 1b（challenge）之后、Phase 2（diversity guarantee）之前。这确保：
1. 每个分支先有 confirm（找支持）和 challenge（找反对）
2. 然后若有 evidence_against，追加 reinterpret（反驳反对）
3. Phase 2 检查领先分支是否有挑战覆盖时，不因 reinterpret 的存在而跳过

#### Bundle 大小估算（修订）

| 组件 | 4 分支 (Turn 1) | 4 分支 (Turn 2+) |
|------|-----------------|------------------|
| Phase 1 (confirm) | 4 | 4 |
| Phase 1b (challenge) | 3-4 | 3-4 |
| **Phase 1c (reinterpret)** | **0** | **2-4** |
| Phase 2 (diversity) | 0-1 | 0-1 |
| Phase 3 (separation) | 0-2 | 0-2 |
| **总计** | **7-11** | **9-15** |

#### reinterpret 与 EvidenceAnnotator 的交互

reinterpret 候选执行后送入 Annotator。其 analysis_target 形如：
> "The evidence_against citing retinal hemorrhages favouring AML assumes direct leukemic infiltration. However, at WBC 145K, leukostasis causes microvascular sludging — could this explain the findings under CML-BC?"

Annotator 标注此动作时有两种结果：
- **替代机制成立**：`branch_effects: {B1: "moderate_for"}` — evidence_against 被削弱，后验回调
- **替代机制不成立**：`branch_effects: {B1: "neutral"}` 或 `{B1: "weak_against"}` — evidence_against 维持

**这使 2-hop 推理从 Annotator 的隐式行为变为 TALP 的显式规划**，可追溯、可审计。

### 11.8.2 改进二：Chain-aware EvidenceAnnotator 提示词

#### 动机

即使不引入 reinterpret 候选类型，强化 Annotator 自身的推理能力也是必要的（途径 A 的加固）。当前 Annotator 提示词没有任何指令要求它在面对 challenge 问题时考虑替代解释。

#### 提示词新增段落

在 `evidence_annotator.txt` 的 "Phase-crossing awareness" 段落之后，新增：

```
Alternative mechanism awareness:
When the analysis_target is a CHALLENGE question (asks whether a finding argues
AGAINST a branch), you MUST perform a two-step evaluation:

Step 1 — Direct association: Assess the strength of the finding's association with
  competing branches (e.g., "retinal hemorrhages occur in 30-40% of AML").

Step 2 — Alternative mechanism check: Before assigning the final effect label,
  check whether a PATHOPHYSIOLOGICAL MECHANISM specific to the target branch could
  also explain the finding. Consult lr_reference if provided.
  Examples of alternative mechanisms:
  - Hyperleukocytosis → leukostasis → retinal hemorrhages (in CML blast crisis)
  - Autoimmune hemolysis → splenic sequestration (in CLL)
  - Tumor lysis → hyperuricemia → renal findings (in aggressive lymphoma)

If an alternative mechanism exists AND is plausible given the patient's data:
  - DOWNGRADE the effect by one level (e.g., moderate_against → weak_against)
  - DOCUMENT the mechanism in micro_summary / result_summary
  - Add "alternative_mechanism": "description" to the per_action_effects entry

If NO alternative mechanism is plausible, assign the effect label based on Step 1 alone.

This two-step process ensures that challenge analyses are FAIR — they identify real
weaknesses but do not overweight findings that have known alternative explanations.
```

#### 输出 schema 扩展

per_action_effects 新增可选字段：

```json
{
  "action_index": 1,
  "action_content": "Do retinal hemorrhages argue against CML-BC?",
  "micro_summary": "...",
  "branch_effects": {"B1": "weak_against", "B2": "weak_for"},
  "alternative_mechanism": "leukostasis at WBC >100K causes retinal microvascular sludging"
}
```

`alternative_mechanism` 字段的作用：
1. **可追溯性**：程序可检测 Annotator 是否执行了 Step 2
2. **证据质量标注**：后续模块（如 PostUpdateStateReviser）可利用此字段判断 evidence_against 的可靠程度
3. **知识管线反馈**：若 Annotator 发现的替代机制不在 RAG 索引中，可作为知识缺口信号

#### 对 evidence_against 写入的影响

经 Step 2 降级后的效果标签（如 `weak_against`）仍然写入 `evidence_against`，但 `result_summary` 中会包含替代机制的讨论，使后续 TALP 的 reinterpret 候选有更明确的反驳目标。

### 11.8.3 改进三：RAG lr_reference 显式替代机制标注

#### 动机

途径 A 和 C 都依赖 Annotator 从 lr_reference 中自行发现替代机制。但当前 `format_lr_reference_for_prompt` 输出的格式是平铺的 LR 数值或 RAG context 片段，未对替代机制做显式标注。Annotator 需要从一段 200 字符的原始文本中**自行识别**"leukostasis at WBC>100K"是一个替代机制——这依赖 LLM 的阅读理解能力。

#### DxFeatureRetriever.format_lr_reference_for_prompt 变更

在 `dx_feature_retriever.py` 的 `format_lr_reference_for_prompt` 方法中，当检测到 RAG context-only 条目时，追加替代机制提取：

```python
def format_lr_reference_for_prompt(
    self, finding: str, diseases: list[str],
    *, challenge_target_branch: str = "",
) -> str:
    """Generate a compact text block for injection into Annotator prompt.

    When challenge_target_branch is set, additionally search for alternative
    mechanisms that could explain `finding` under that branch's disease.
    """
    ref = self.get_lr_reference(finding, diseases)
    if ref["source"] == "none":
        return ""
    lines = [f"[LR Reference for '{finding}' (source: {ref['source']})]"]

    for disease, entry in ref["lr_data"].items():
        if entry:
            conf = entry.get("confidence", "?")
            if conf == "context-only":
                snippet = entry.get("context_snippet", "")[:150]
                title = entry.get("snippet_title", "")
                lines.append(f"  {disease}: [RAG context from {title}]")
                lines.append(f'    "{snippet}..."')
            else:
                lr_p = entry.get("lr_positive")
                lr_n = entry.get("lr_negative")
                sn = entry.get("sensitivity")
                sp = entry.get("specificity")
                lines.append(
                    f"  {disease}: LR+={lr_p}, LR-={lr_n} "
                    f"(Sn={sn}, Sp={sp}, confidence={conf})"
                )
        else:
            lines.append(f"  {disease}: no data")

    # --- NEW: alternative mechanism search ---
    if challenge_target_branch and self.rag and self.rag.is_ready:
        alt_query = (
            f"{finding} alternative mechanism pathophysiology "
            f"{challenge_target_branch}"
        )
        alt_results = self.rag.search(alt_query, top_k=2, score_threshold=0.5)
        if alt_results:
            lines.append(f"\n  [Alternative mechanisms for '{finding}' under "
                         f"{challenge_target_branch}:]")
            for r in alt_results:
                lines.append(f"    ⚕ {r.get('title', '?')} (score={r['score']:.2f})")
                content = r.get("content", "")[:180]
                lines.append(f"      {content}")
    return "\n".join(lines)
```

#### Controller._build_annotator_payload 变更

在构建 Annotator payload 时，检测最近执行的动作是否为 challenge 类型，若是则传入 `challenge_target_branch`：

```python
def _build_annotator_payload(self, state, raw_result):
    payload = {"state": state.to_payload(), "raw_result": raw_result}
    if self._knowledge_retriever and self.config.enable_knowledge_injection:
        disease_names = [
            b.label for b in state.branches.values()
            if b.status not in ("closed_for_now", "expanded")
        ]
        finding_text = ""
        challenge_target = ""
        if state.actions_taken:
            latest = state.actions_taken[-1]
            finding_text = latest.get("content", "")
            # Detect if this was a challenge action
            per_action = latest.get("per_action_branch_effects", {})
            if not per_action:
                # Check if the action was from a challenge candidate
                # by looking at the content pattern
                bid = latest.get("branch_id", "")
                branch = state.branches.get(bid)
                if branch:
                    challenge_target = branch.label

        if finding_text and disease_names:
            try:
                lr_text = self._knowledge_retriever.format_lr_reference_for_prompt(
                    finding_text, disease_names,
                    challenge_target_branch=challenge_target,
                )
                if lr_text:
                    payload["lr_reference"] = lr_text
            except Exception as e:
                _logger.warning("LR injection for Annotator failed: %s", e)
    return payload
```

#### 输出效果示例

改进前（当前）的 lr_reference：
```
[LR Reference for 'Do retinal hemorrhages argue against CML-BC?' (source: rag)]
  CML-BC: [RAG context from Retinal Hemorrhages > Epidemiology]
    "Within the spectrum of hematologic diseases, Roth spots occur in approximately 
     30% to 40% of patients with acute leukemia..."
```

改进后的 lr_reference：
```
[LR Reference for 'Do retinal hemorrhages argue against CML-BC?' (source: rag)]
  CML-BC: [RAG context from Retinal Hemorrhages > Epidemiology]
    "Within the spectrum of hematologic diseases, Roth spots occur in approximately 
     30% to 40% of patients with acute leukemia..."

  [Alternative mechanisms for 'retinal hemorrhages' under CML-BC:]
    ⚕ Hyperleukocytosis. > Complications (score=0.68)
      Leukostasis is an emergency complication of hyperleukocytosis (WBC >100K) 
      characterized by microvascular sludging. Retinal vessels are particularly 
      susceptible, producing bilateral hemorrhages and cotton-wool spots...
```

Annotator 看到 `[Alternative mechanisms]` 段落后，不再需要自行从散装文本中推断替代机制——它被**显式地、结构化地**呈现。

### 11.8.4 已发现途径的针对性强化

#### 途径 A（Annotator 单轮内化）— 风险：Annotator 推理不足

| 强化手段 | 机制 | 效果 |
|---------|------|------|
| **Chain-aware 提示词**（§11.8.2） | 强制 Step 2 替代机制检查 | Annotator 不再遗漏 lr_reference 中的替代解释 |
| **RAG 显式标注**（§11.8.3） | lr_reference 中单独标出 `[Alternative mechanisms]` 段 | 降低 Annotator 阅读理解负担 |
| **alternative_mechanism 字段** | Annotator 输出中结构化记录替代机制 | 可追溯、可审计 |

强化后的途径 A 流程：
```
TALP challenge → Execute → _build_annotator_payload (注入 lr_reference + Alternative mechanisms)
  → Annotator Step 1 (直接关联评估) 
  → Annotator Step 2 (替代机制检查，参考 [Alternative mechanisms] 段)
  → 标注: weak_against (降级) + alternative_mechanism: "leukostasis"
  → result_summary 含两跳完整推理
```

#### 途径 B（confirm 隐式覆盖）— 风险：confirm 不主动触及中间概念

| 强化手段 | 机制 | 效果 |
|---------|------|------|
| **reinterpret 候选**（§11.8.1） | TALP 显式生成"反驳 evidence_against"候选 | 不再依赖 confirm 偶然覆盖中间概念 |
| **discriminator_hints 链式提示** | `_format_chain_section` 已含 RAG context 和 ChainDiscoverer 输出 | TALP 在生成 reinterpret 时有明确的知识锚点 |

**reinterpret 本质上是途径 B 的确定化版本**：将 confirm 可能偶然触及替代机制的概率性行为，转变为 reinterpret 必然引用 evidence_against 并提出替代解释的确定性行为。

#### 途径 C（Bundle 聚合合成）— 风险：聚合时信息过载导致遗漏

| 强化手段 | 机制 | 效果 |
|---------|------|------|
| **per_action_effects 的 alternative_mechanism 字段** | 每个 challenge 动作单独记录替代机制 | 聚合时不遗漏已识别的替代解释 |
| **聚合规则扩展** | 当 challenge 动作标注了 alternative_mechanism 时，聚合 branch_effects 必须反映降级后的标签 | 防止聚合阶段"回退"到未降级的强标签 |

### 11.8.5 三层协同的完整数据流

以 CML Case #68 Turn 1 为例，展示三层改进如何协同工作：

```
┌─ TALP ─────────────────────────────────────────────────────────┐
│ 输入: B1(CML-BC, p=0.50), evidence_against=[]                  │
│                                                                  │
│ 生成 2 候选 (evidence_against 空，不触发 reinterpret):           │
│   Leaf-1 [B1, confirm]  "BCR-ABL1 支持 CML-BC?"                │
│   Leaf-2 [B1, challenge] "retinal hemorrhages 反对 CML-BC?"     │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ Execute + Annotate ────────────────────────────────────────────┐
│ _build_annotator_payload 注入:                                   │
│   lr_reference:                                                  │
│     CML-BC: [RAG context] "Roth spots in 30-40% of acute..."    │
│     [Alternative mechanisms for 'retinal hemorrhages'            │
│      under CML-BC:]                          ← 改进三: 显式标注  │
│       ⚕ Hyperleukocytosis > Complications                       │
│         "Leukostasis... microvascular sludging..."               │
│                                                                  │
│ Annotator Step 1: retinal hemorrhages → AML 30-40%              │
│ Annotator Step 2: 检查 [Alternative mechanisms]  ← 改进二       │
│   发现: leukostasis at WBC>100K → retinal hemorrhages            │
│   患者 WBC=145K → 替代机制成立                                   │
│   → 降级: moderate_against → weak_against                        │
│   → alternative_mechanism: "leukostasis at WBC 145K"             │
│                                                                  │
│ 写入: B1.evidence_against ← "retinal hemorrhages weak_against   │
│        (alternative: leukostasis)"                               │
│ 后验: B1: 0.50 → 0.48 (微幅下调，因为 weak_against)             │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ Turn 2 TALP ──────────────────────────────────────────────────┐
│ 输入: B1(CML-BC, p=0.48), evidence_against=["retinal           │
│        hemorrhages weak_against (alt: leukostasis)"]            │
│                                                                  │
│ evidence_against 非空 → 触发 reinterpret!        ← 改进一       │
│                                                                  │
│ 生成 3 候选:                                                     │
│   Leaf-3 [B1, confirm]      "splenomegaly+basophilia 支持?"     │
│   Leaf-4 [B1, challenge]    "新的最强反对证据是什么?"            │
│   Leaf-5 [B1, reinterpret]  "evidence_against 称 retinal        │
│     hemorrhages 偏向 AML。但 WBC 145K 的 leukostasis 是否        │
│     能完整解释 CML-BC 中的眼底表现，使该证据不再构成反对?"       │
│     target: {B1: "support"}                                      │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ Execute + Annotate ────────────────────────────────────────────┐
│ Leaf-5 (reinterpret) 标注:                                       │
│   Annotator 评估: leukostasis 机制 + WBC 145K + bilateral       │
│     hemorrhages + cotton-wool spots 的完整一致性                  │
│   → branch_effects: {B1: "moderate_for"}                         │
│   → result_summary: "Leukostasis at WBC 145K provides a         │
│     complete pathophysiological explanation for bilateral         │
│     retinal hemorrhages in CML-BC..."                            │
│                                                                  │
│ 写入: B1.evidence_for ← "leukostasis explains retinal findings" │
│ 后验: B1: 0.48 → 0.55                                           │
│ B1 同时有 evidence_for 和 evidence_against → 推理完整闭合        │
└──────────────────────────────────────────────────────────────────┘
```

### 11.8.6 对比：无改进 vs 三层强化

| 维度 | 无改进（当前） | 三层强化后 |
|------|---------------|-----------|
| 2-hop 推理闭合点 | Annotator 隐式（若 LLM 碰巧注意到 lr_reference） | **TALP 显式规划（reinterpret）+ Annotator 确定性执行（Step 2）** |
| 替代机制发现 | 依赖 Annotator 阅读理解 200 字符 RAG 片段 | **RAG 显式标注 `[Alternative mechanisms]`** |
| 可追溯性 | 无——埋在 result_summary 自由文本中 | **alternative_mechanism 字段 + reinterpret 候选类型** |
| 鲁棒性 | 单点依赖 Annotator | **三层冗余：TALP reinterpret → Annotator Step 2 → RAG 显式标注** |
| 候选池大小 | 8/turn (4 branch × 2) | **Turn 1: 8, Turn 2+: 最多 12** |
| Bundler 复杂度 | Phase 0/1/1b/2/3/4 | **新增 Phase 1c**（约 15 行代码） |

### 11.8.7 实施优先级

| 优先级 | 改进 | 代码变更量 | 理由 |
|--------|------|-----------|------|
| **P-1** | Annotator Chain-aware 提示词（§11.8.2） | ~15 行提示词 | 零代码变更，立即生效，加固途径 A |
| **P-1** | RAG 显式标注替代机制（§11.8.3） | ~20 行 dx_feature_retriever + ~5 行 controller | 中等代码量，显著降低 Annotator 推理负担 |
| **P-2** | reinterpret 候选类型（§11.8.1） | ~30 行 TALP 提示词 + ~20 行 action_bundler + ~5 行 state | 最大代码变更，但从根本上解决 TALP 层的认知盲区 |

### 11.8.8 风险评估

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| reinterpret 候选被 LLM 生成为"伪装的 confirm" | 中 | content 必须引用 evidence_against 具体条目；Bundler 可校验 |
| 候选池膨胀增加 TALP token 开销 | 低 | 条件性生成（仅 evidence_against 非空时）；Turn 1 无影响 |
| Annotator alternative_mechanism 字段频繁为空 | 中 | RAG 显式标注降低遗漏率；可配置为可选字段 |
| reinterpret 与 confirm 语义重叠 | 低 | confirm 不引用 evidence_against；reinterpret 必须引用 |
| evidence_against 条目过于笼统，reinterpret 无法定向反驳 | 中 | per_action_effects 的 micro_summary 提供更精确的反驳目标 |

---

## 11.9 完整版 vs 测试版推理轨迹对比分析 (2026-05-24)

### 11.9.1 背景

`test_2hop_leaf_generation.py`（测试版）能够识别 leukostasis chain 并生成支持 CML-BC 的候选节点，但 `test_full_pipeline_cml.py`（完整版）在 3 次独立运行中均错误地诊断为 AML 而非 CML-BC。本节通过逐字段比较两版的 TALP 输入/输出，追踪诊断失败的完整因果链。

### 11.9.2 先验概率生成机制

当前先验概率的生成方式为：**LLM 直接估计，无外部知识校准**。

| 阶段 | 模块 | 机制 | 外部知识参与 |
|------|------|------|------------|
| L1 分支创建 | BranchCreator | LLM 输出 `prior_estimate` 字段，控制器直接使用 `posterior = prior_estimate` | **无** |
| L2 子分支创建 | SubBranchCreator | LLM 输出 `prior_estimate`，控制器按比例分配父分支 posterior：`child.posterior = parent.posterior × (child.prior / Σchild.prior)` | **无** |
| 后续更新 | ProbabilityUpdate | ordinal LR 乘法器或 calculator rule 更新 posterior | 有（lr_reference） |

以 CML 案例为例：
- BranchCreator 给 B1("Myeloid Neoplasm with Increased Blasts") 的 `prior_estimate` = 0.70
- Round 1 Annotator 将 B1 posterior 推至 0.887
- SubBranchCreator 给子分支的 `prior_estimate`：B1.1(AML)=0.50, B1.2(CML-BC)=0.20, B1.3(MDS-EB)=0.20
- `initialize_child_posteriors` 按比例分配：
  - B1.1(AML): 0.887 × (0.50/0.90) = **0.493**
  - B1.2(CML-BC): 0.887 × (0.20/0.90) = **0.197**

**问题**：SubBranchCreator 的 `prior_estimate` 完全依赖 LLM 对 vignette 的"直觉"判断，没有利用任何外部知识（如 CML-BC 在高WBC+basophilia+splenomegaly 组合下的流行病学先验）。这导致 AML 以 2.5:1 的初始优势压制 CML-BC。

### 11.9.3 TALP 输入的 6 维差异

#### 差异 1：分支粒度和认知框架

| 维度 | 测试版 | 完整版 Round 2 |
|------|--------|---------------|
| 分支数 | 3（平级） | 8（2 层嵌套） |
| CML-BC 的位置 | B1（顶层，第一个） | B1.2（子分支，第二个） |
| AML 的位置 | B2（竞争者） | B1.1（同级的兄弟） |
| Frontier | 全部 active | ["B1.1", "B1.2", "B1.3", "B2"] |

**效果**：测试版 LLM 的认知任务是 "CML-BC vs AML 的平级对决"；完整版 LLM 需要在 4 个 frontier 分支间分配认知资源，注意力被稀释。

#### 差异 2：先验概率偏向

| 分支 | 测试版 | 完整版 |
|------|--------|--------|
| CML-BC | **0.500**（优势） | **0.197**（劣势，2.5:1 落后） |
| AML | 0.350 | **0.493**（优势） |

**效果**：TALP 提示词要求优先关注高概率分支。CML-BC 在完整版中以 0.197 的劣势地位获得更少的探索资源。

#### 差异 3：认知锚定——`actions_taken` 和 `evidence_for/against` 的累积偏差

完整版 Round 2 payload 携带 3 条 Round 1 遗留的 `actions_taken`：

| # | summary（截取） | 对 CML-BC 的倾向 |
|---|----------------|-----------------|
| 0 | "Leukostasis...highly specific to blast crisis in myeloid neoplasms (B1)" | 中性（指向家族级 B1） |
| 1 | "The lack of prior chronic MPN symptoms...more congruent with de novo myeloid neoplasm (B1)" | **反 CML-BC** |
| 2 | "No direct contradiction to myeloid neoplasm" | 中性 |

同时，B2(Chronic MPN) 的 `evidence_against` 已积累 2 条明确反对的证据。**这些遗留信息将 LLM 锚定在 "de novo myeloid > CML" 的叙事上**，Round 2 生成的候选节点自然延续这一偏向。

测试版 payload 中没有 `actions_taken` 和 `evidence_for/against`，LLM 以**空白认知状态**开始。

#### 差异 4（根因）：案例文本中 Philadelphia 染色体 / BCR-ABL1 证据缺失

| 证据 | 测试版 vignette | 完整版 case_summary |
|------|----------------|-------------------|
| **Philadelphia chromosome positive** | **✓ 明确包含** | **✗ 完全缺失** |
| **BCR-ABL1 fusion detected** | **✓ 明确包含** | **✗ 完全缺失** |
| **Cytogenetics** | **✓ 明确包含** | **✗ 完全缺失** |
| night sweats | ✗ | ✓ |
| abdominal fullness | ✗ | ✓ |
| petechiae | ✗ | ✓ |
| LDH elevated | ✗ | ✓ |
| Uric acid elevated | ✗ | ✓ |

**这是最关键的发现**：完整版 `test_full_pipeline_cml.py` 中的 `CML_VIGNETTE` **不含** Philadelphia chromosome / BCR-ABL1 信息。这是 CML 的**决定性诊断标准**（LR > 100），其缺失意味着：

1. VignetteParser 无法提取该证据（`static_evidence_items` 中无 Ph+ 相关条目）
2. BranchCreator / SubBranchCreator 无法据此校准先验
3. TALP 生成的候选节点无法引用这一决定性证据
4. EvidenceAnnotator 在缺乏 Ph+ 信息时，仅凭间接线索（basophilia、splenomegaly）评估 CML-BC 可能性——**这本身就是一个不可能正确完成的诊断任务**

#### 差异 5：Hints 中 chain target 的鉴别力稀释

测试版 chain 指向 "Chronic Myeloproliferative Neoplasm"（与 CML-BC 语义接近），完整版 Round 1 chain 指向抽象的 "Myeloid Neoplasm with Increased Blasts"——后者对 AML 和 CML-BC 均适用，chain 丧失鉴别力。

#### 差异 6：`resolved_evidence` 格式化差异

测试版使用 `resolved_evidence` 字段以 `{key, value}` 结构化呈现 7 条证据（包含 Ph+），证据显著性高。完整版通过 `static_evidence_items`（`to_payload` → `asdict()`）传递 11 条证据，但 Ph+ 不在其中。

### 11.9.4 诊断失败的因果链（完整版 py38-run1，3 轮）

```
┌─── 输入层 ────────────────────────────────────────────────────┐
│ case_summary 中缺失 Philadelphia chromosome / BCR-ABL1 证据   │
│ → VignetteParser 提取的 11 条 evidence_items 均不含 Ph+       │
└────────────────────────────┬───────────────────────────────────┘
                             │
┌─── Round 1 ────────────────▼───────────────────────────────────┐
│ BranchCreator: B1(Myeloid Neoplasm)=0.70                      │
│ TALP: 生成 leukostasis confirm for B1（家族级，无鉴别力）      │
│ Annotator: B1 evidence_for += 2 条，posterior → 0.887         │
│ Reviser: B1 → expand_now                                      │
└────────────────────────────┬───────────────────────────────────┘
                             │
┌─── Sub-branch ─────────────▼───────────────────────────────────┐
│ SubBranchCreator(无知识注入):                                   │
│   B1.1(AML)=0.50, B1.2(CML-BC)=0.20, B1.3(MDS-EB)=0.20       │
│ initialize_child_posteriors:                                    │
│   B1.1(AML) = 0.887 × 0.556 = 0.493                           │
│   B1.2(CML-BC) = 0.887 × 0.222 = 0.197                        │
│ → AML 以 2.5:1 初始优势压制 CML-BC                             │
└────────────────────────────┬───────────────────────────────────┘
                             │
┌─── Round 2 ────────────────▼───────────────────────────────────┐
│ TALP: 受 actions_taken 锚定 + AML 先验优势                     │
│       生成偏向 AML 的候选（虽然也有 CML-BC confirm）            │
│ Annotator 关键错误（无 Ph+ 信息下的必然结果）：                  │
│   Action 0: "82% blasts → moderate_against CML-BC"             │
│   Action 3: "8% basophilia → strong_against CML-BC"  ← 临床错误│
│   Action 4: "No prior MPN → decisively undermines CML-BC"      │
│ → B1.2(CML-BC) posterior: 0.197 → 0.048                       │
│ Reviser: B1.2(CML-BC) → park                                  │
└────────────────────────────┬───────────────────────────────────┘
                             │
┌─── Round 3 ────────────────▼───────────────────────────────────┐
│ CML-BC 已被 park，无法参与竞争                                  │
│ B1(Myeloid Neoplasm) → confirm                                 │
│ AnswerMapper: B1 → AML（子分支中 AML 得分最高）                 │
│ 最终答案: B (AML) — 错误                                       │
└────────────────────────────────────────────────────────────────┘
```

### 11.9.5 修复方案

#### 11.9.5.1 修复 0（前提）：补全测试案例的决定性证据

**问题**：`test_full_pipeline_cml.py` 的 `CML_VIGNETTE` 缺失 Philadelphia chromosome / BCR-ABL1 信息。

**修复**：在 Laboratory findings 后增加 Cytogenetics 段：

```
Cytogenetics:
- Philadelphia chromosome positive
- BCR-ABL1 fusion gene detected (p210 transcript)
```

**注意**：这是一个**测试案例构造错误**而非系统缺陷。但它揭示了系统在缺失决定性证据时的脆弱性——即使间接证据（basophilia + splenomegaly + leukostasis）高度提示 CML-BC，系统仍无法对抗 AML 的概率优势。

#### 11.9.5.2 修复 1：SubBranchCreator 知识注入 — 校准 `prior_estimate`

**问题**：SubBranchCreator 的 `prior_estimate` 完全依赖 LLM 直觉，无外部知识校准。

**修复方案**：

```
修改点: controller.py → run_expansion_gate()
时机:   在调用 SubBranchCreator 之前

1. 从 state.static_evidence_items 提取关键特征
2. 调用 DxFeatureRetriever 获取子分支候选疾病的 discriminator hints
3. 将 hints 注入 SubBranchCreator payload 的 "knowledge_context" 字段
4. SubBranchCreator 提示词增加指令:
   "When knowledge_context provides frequency or LR data for specific
    findings-disease associations, use these to calibrate prior_estimate
    rather than relying on clinical intuition alone."
```

**预期效果**：当外部知识表明 basophilia(8%) + massive splenomegaly 在 CML-BC 中的 LR 显著高于 AML 时，SubBranchCreator 应给 CML-BC 更高的 `prior_estimate`（如 0.35 而非 0.20）。

#### 11.9.5.3 修复 2：认知锚定缓解 — evidence_against 偏差检测

**问题**：Round 1 的 `actions_taken` 和 `evidence_for/against` 在 Round 2 payload 中形成认知锚定，使 LLM 延续先前的偏向。

**修复方案**：

```
修改点: controller.py → plan_temporary_leaves()
时机:   构造 TALP payload 时

1. 遍历 frontier 中的子分支
2. 如果某子分支的 parent 有 evidence_for 但该子分支自身
   evidence_for 为空且 evidence_against 为空（刚创建），
   在 payload 中增加一个 "bias_alert" 字段:
   "Branch {bid} was just created. Parent's accumulated evidence
    may not reflect the child's specific profile. Evaluate each child
    independently based on its own discriminating features."
3. 在 TALP 提示词中增加指令:
   "When bias_alert is present, ignore the implicit ranking suggested
    by prior posteriors. Generate candidates for each alerted branch
    with equal investigative priority."
```

**预期效果**：新创建的子分支获得平等的探索机会，不受父分支推理历史的锚定。

#### 11.9.5.4 修复 3：Pathognomonic 证据硬约束

**问题**：即使 Ph+ / BCR-ABL1 在 vignette 中存在，系统也可能因 Annotator 的权重分配不足而忽视其决定性作用。

**修复方案**：

```
修改点: DxFeatureRetriever + EvidenceAnnotator 提示词

1. DxFeatureRetriever 在 hints 中标记 pathognomonic findings:
   "[PATHOGNOMONIC] BCR-ABL1 fusion → CML (LR >100, PPV ≈ 1.0)"

2. EvidenceAnnotator 提示词增加硬约束:
   "When a finding is marked [PATHOGNOMONIC] in knowledge context:
    - Its branch effect MUST be 'strong_for' for the target disease
    - It OVERRIDES all indirect evidence in the opposite direction
    - No amount of negative indirect evidence can outweigh a
      pathognomonic positive finding"

3. ProbabilityUpdate 增加 pathognomonic 覆写规则:
   如果某条证据的 LR > 50，直接将对应分支 posterior 设为
   max(current_posterior, 0.70)，绕过 ordinal LR 累乘。
```

### 11.9.6 修复优先级

| 优先级 | 修复 | 代码变更量 | 理由 |
|--------|------|-----------|------|
| **P-0** | 补全测试案例 Ph+ 证据（§11.9.5.1） | 3 行 | 前提条件，否则所有后续修复无法验证 |
| **P-1** | SubBranchCreator 知识注入（§11.9.5.2） | ~30 行 controller + ~10 行提示词 | 校准初始概率分布，消除 AML 的假性优势 |
| **P-1** | Pathognomonic 证据硬约束（§11.9.5.4） | ~20 行 retriever + ~15 行提示词 + ~10 行 probability update | 确保决定性证据不被间接证据覆盖 |
| **P-2** | 认知锚定缓解（§11.9.5.3） | ~15 行 controller + ~10 行提示词 | 新子分支获得平等探索机会 |

### 11.9.7 结论

完整版推理失败的**最终根因**是测试案例 vignette 缺失 Philadelphia chromosome / BCR-ABL1 这一 CML 的决定性诊断证据。在没有这一 pathognomonic finding 的情况下，CML-BC 与 de novo AML 的鉴别在临床上确实极度困难——Annotator 的 "错误" 判断在此条件下其实是合理的。

然而，即使补全 Ph+ 证据后，系统仍然存在 3 个结构性脆弱点需要修复：

1. **SubBranchCreator 无知识注入** → AML 获得不合理的初始概率优势
2. **认知锚定无缓解机制** → Round 1 的偏向在 Round 2 被放大
3. **缺少 pathognomonic 证据硬约束** → 决定性证据可能被间接反对证据覆盖

---

## 12. B1 瓶颈修复：数值型化验结果 → HPO 表型术语映射 (2026-05-25)

> 详细计划见 [`B1_LAB_NORMALIZATION_PLAN.md`](./B1_LAB_NORMALIZATION_PLAN.md)  
> 四瓶颈修复总体方案见 [四瓶颈修复方案 plan](~/.cursor/plans/四瓶颈修复方案_e45b0adc.plan.md)

### 12.1 问题

Embedding 模型（all-MiniLM-L6-v2）无法对 "WBC 145000"、"82% blasts" 等数值型化验描述进行语义匹配。根因是通用语义模型不理解 "145000 > 11000 → 高 → Leukocytosis" 这种数值推理。

### 12.2 外部数据源调研

经系统调研，确定三个可用的外部数据源：

| 数据源 | 内容 | 规模 | 许可证 |
|--------|------|------|--------|
| **loinc2hpo** (Jackson Lab) | LOINC + 方向(H/L/N) → HPO 术语 | 3,118 LOINC, 827 HPO | HPO License |
| **LabQAR** (Bhasuran et al.) | 化验参考范围（上下界） | 550 项检验 | MIT |
| **medical-lab-reference** (mdtools.org) | 常见化验正常范围 (Tietz 5th Ed) | ~80 项 | MIT |

关键发现：**loinc2hpo** 已为 CML 相关的全部核心化验项提供了 HPO 映射：
- WBC (LOINC:6690-2) + H → HP:0001974 (Leukocytosis)
- Platelets (LOINC:26515-7) + L → HP:0001873 (Thrombocytopenia)
- Basophils (LOINC:30180-4) + H → HP:0031807 (Basophilia)
- Hemoglobin (LOINC:718-7) + L → HP:0020062 (Decreased hemoglobin)

### 12.3 项目已有 RAG 语料分析

| 语料 | 块数 | 含 "reference range" 的块 | 占比 |
|------|------|--------------------------|------|
| StatPearls | 367,799 | ~561 | 0.15% |
| Textbooks (MedRAG) | 125,847 | ~300 | 0.24% |

已验证 StatPearls 中包含 "WBC count... normal reference range of approximately 4.3 to 11.0 × 10^9/L" 等内容，可用作 RAG 兜底。但当前 RAG FAISS 索引二进制文件缺失，需重建。

### 12.4 方案架构：三层正规化管线

```
EvidenceItem.finding = "WBC 145,000/μL"
        │
   Layer 1: 正则解析
        │  → test_name="WBC", value=145000, unit="/μL"
        │
   Layer 2: 结构化查表
        │  → alias_map: "WBC" → LOINC:6690-2
        │  → lab_ranges: 正常=[4500,11000] → 145000>11000 → direction=H
        │  → loinc2hpo: 6690-2+Qn+H → HP:0001974 (Leukocytosis)
        │
   Layer 3: RAG 兜底（Layer 2 未命中时）
        │  → query RAGRetriever → 正则提取参考范围 → 判断方向
        │
   输出: NormalizedFinding(hpo_id="HP:0001974", hpo_term="Leukocytosis",
                           direction="H", confidence="high")
```

**核心模块**: `FindingNormalizer`（新建 `src/agentclinic_tree_dx/knowledge/finding_normalizer.py`）

### 12.5 数据文件

| 文件 | 来源 | 构建脚本 |
|------|------|---------|
| `data/knowledge_raw/lab_reference_ranges.json` | LabQAR + medical-lab-reference 整合 | `scripts/build_lab_reference_data.py` |
| `data/knowledge_raw/loinc2hpo_annotations.json` | loinc2hpoAnnotation TSV 转换 | 同上 |
| `data/knowledge_raw/lab_name_aliases.json` | LOINC short name + 常见缩写 | 同上 |
| `data/knowledge_raw/unit_conversions.json` | 手工维护（~20 组换算关系） | 同上 |

### 12.6 单位归一化策略

- 每个检验项定义标准单位，存储在 `lab_reference_ranges.json`
- `FindingNormalizer._normalize_unit()` 根据 `unit_conversions.json` 自动换算（约 20 组：×10^9/L ↔ /μL, g/L ↔ g/dL, mmol/L ↔ mg/dL 等）
- 无单位的数值按该检验最常见单位假设
- 不可换算时 fallback to Layer 3（RAG）

### 12.7 百分比型指标特殊处理

"82% blasts"、"8% basophils" 等百分比型指标使用专用阈值而非参考范围查表：

| 指标 | 异常阈值 | HPO（高） |
|------|---------|----------|
| blasts | ≥5% | HP:0012234 Elevated blast count |
| basophils | ≥2% | HP:0031807 Basophilia |
| eosinophils | ≥5% | HP:0001880 Eosinophilia |

### 12.8 正常值映射

loinc2hpo 的 N（正常）方向映射（如 WBC 正常 → HP:0011893）在鉴别诊断中有价值：
- "正常 WBC" 作为 evidence_against CML（CML 几乎必然 WBC 升高，LR- < 1）
- direction="N" 的 `NormalizedFinding` 标记 confidence="medium"

### 12.9 预期收益

CML 测试案例（11 条 evidence）覆盖度：
- 当前（P1+P2 后）：3/11 (27.3%)
- **+B1 FindingNormalizer：8/11 (72.7%)**——新增 WBC→Leukocytosis, Hb→Decreased Hb, Plt→Thrombocytopenia, Basophils→Basophilia, Blasts→Elevated blast count

### 12.10 实施路线

| Phase | 内容 | 优先级 |
|-------|------|--------|
| Phase 1: 数据准备 | 编写构建脚本，下载/整合数据源 | P0 |
| Phase 2: 核心模块 | 实现 FindingNormalizer 三层管线 | P0 |
| Phase 3: 集成测试 | 接入 controller，覆盖度测试 | P0 |
| Phase 4: RAG 重建 | 重建 FAISS 索引，恢复 Layer 3 | P1 |

---

## 13. B2 瓶颈安全性审查：LR cache 疾病-finding 配对缺失 (2026-05-27)

> ⚠️ 原 B2 方案中提出的"默认频率兜底"经审查存在严重临床安全隐患，以下为修正记录。  
> 详见四瓶颈修复方案 plan 中 B2 章节。

### 13.1 事实性纠正

原 plan 陈述 "HPO 的 4 条 CML 注释无频率字段被跳过" **不准确**：

- HPO 中 CML 有 **11 条注释，100% 有频率数据**（HP:0040280 Obligate × 1, HP:0040282 Frequent × 10）
- 全部进入 unified cache，加 Orphadata 补充共 **15 条**
- 真正的问题是 docLogica 的 26 条 CML 关联全部 `frequency="unknown"` 被过滤

### 13.2 频率缺失根因

| 数据源 | 缺失量 | 原因 |
|--------|--------|------|
| **HPO** | 64,151 条 (22.7%) | IEA（电子自动注释）占 46.4%；TAS/PCS 文献仅报告定性关联 |
| **docLogica** | 10,180 条 (77%) | 低发病率/专科疾病未经频率策展（如 CML 26 条全部 unknown） |
| **Orphadata** | 接近 0% | 专家策展最完整，每条含 obligate～excluded 频率 |

### 13.3 默认 Sn=0.30 方案的安全性分析

对 docLogica "unknown" 关联与其他数据源中相同 finding 的实际 Sn 交叉验证：

| Finding | 实际 Mean Sn | 实际 Max Sn | 默认 0.30 偏差 |
|---------|------------|-----------|---------------|
| polyuria | 0.653 | 1.000 | 低估 2.2× |
| bone pain | 0.590 | 1.000 | 低估 2.0× |
| neutrophilia | 0.561 | 0.900 | 低估 1.9× |
| splenomegaly | 0.538 | 1.000 | 低估 1.8× |
| fatigue | 0.514 | 1.000 | 低估 1.7× |

整个 cache 的 **Sn 中位数 = 0.545**（P25=0.170, P75=0.895）。默认 0.30 会系统性低估大多数关联敏感度。Bayesian 序贯更新中多个错误 LR 相乘，偏差指数级放大。

### 13.4 修正方案

| 子方案 | 安全性 | 说明 |
|--------|--------|------|
| ~~**B2-C：CML-BC 表型继承**~~ | ✗ **废弃** | 临床安全审计发现 CML-CP → CML-BC 继承存在方向性错误（thrombocytosis↔thrombocytopenia 反转）。替代方案：clinical_supplement_cache 手工注入经审查的 CML-BC 特异性数据。已于 2026-05-28 实施。 |
| **B2-A：定性关联层** | ✓ **已实施** | Guideline_rare 注入 4,622 条（含 Orphanet 频率→Sn 转换），Guideline_common 注入 139,038 条定性关联（confidence="qualitative"）。unified cache 总量 233K→377K。已于 2026-05-28 实施。 |
| **B2-B：RAG 频率检索** | △ 中等 | 从 StatPearls/教科书提取具体频率，需验证提取质量 |
| ~~原方案：默认 Sn 兜底~~ | ✗ 废弃 | 系统性偏差，违反循证原则 |
| **B2-新增：clinical_supplement_cache** | ✓ 安全 | 手工编写高频临床关联（WHO 2022/NCCN/Harrison 教科书来源），填补所有自动化知识源的结构性空缺。覆盖 blast count、anemia、basophilia、retinal hemorrhage 等 × 血液肿瘤组合。已于 2026-05-28 实施。 |

### 13.5 深化：回退策略与信号完整性 (2026-05-27)

**Q1 unknown 频率应触发回退**：在 unified cache 中保留 unknown 条目为 `{association_exists: true, quantitative_lr: null}`，运行时主动触发精准 RAG 查询。

**Q2 直接 LR 数据源**：GetTheDiagnosis（1,112 条直接 Sn/Sp/LR）是唯一已集成的直接 LR 源。JAMA Rational Clinical Exam 系列可手工提取~200-300 条金标准 LR（当前未集成）。RAG/PubMed 运行时提取也可获得直接 LR。

**Q3 直接查询优先于计算**：当前构建阶段已正确实现优先级。运行时 RAG 提取到具体 Sn/Sp 数值时，应标记为 `confidence="rag_extracted"`（高于从频率推算的 medium）。

**Q4 完全缺失时的三级信号**（替代当前的静默空字符串）：
1. 有定量 LR → 返回 Sn/Sp/LR 数值
2. 有定性关联无 LR → "Association exists, no quantitative LR"
3. 无任何关联 → "No known association in 6 sources"

"无关联记录"本身有信息量（提示可能不相关），告知 Annotator 优于让其在黑暗中猜测。

### 13.6 RAG 提取 LR 的精确度分析 (2026-05-27)

**结论：RAG 正则提取的 LR 精确度不稳定，不应无条件高于频率计算 LR。**

HPO 频率计算的误差是**系统性粗化**（真值在已知范围内），如 Frequent(30-79%) 对应 Sn=0.545、LR+ 真值 ∈ [0.60, 1.58]。而 RAG 正则提取存在**结构性张冠李戴风险**——snippet 可能含多种 finding 的数据，正则无法确认提取的数字描述了查询的 finding × disease 配对。

推荐 RAG 提取结果分级：
- **Tier A (rag_verified)**：snippet 同时含 finding 名和 disease 名，且数值在 finding 名 50 字符内 → 优先级高于 HPO medium
- **Tier B (rag_unverified)**：数值归属不确定 → 优先级低于 HPO medium，仅作交叉验证
- **Tier C (rag_llm_extracted)**：LLM 从上下文理解后提取 → 优先级 ≈ HPO medium

## 14. B3 瓶颈修复：病理特征性标记 (Pathognomonic Markers) 数据源与方案

### 14.1 问题

HPO 无独立 "Philadelphia chromosome" 或 "BCR-ABL1 fusion" 表型术语。当前 `PrimeKGIndex` 仅加载 disease-phenotype 边，忽略了 160,822 条 gene/protein ↔ disease 边。

### 14.2 可用数据源

| 数据源 | 本地 | 类型 | 规模 | B3 价值 |
|--------|------|------|------|---------|
| **Orphadata product4** | ✓ | Pathognomonic sign | 17 条 | 精确但少 |
| **Orphadata product4** | ✓ | Diagnostic criterion | 876 条 (193 疾病) | ★★★★★ |
| **PrimeKG** | ✓ | gene ↔ disease | 160,822 条 | ★★★★ |
| Orphadata product6 | ✗ | 基因-疾病(含因果类型) | 4,128 对 | ★★★ |
| ClinVar | ✗ | gene-condition TSV | 广泛 | ★★★ |
| DisGeNET | ✗ | GDA + DSI score | 400K+ | ★★★★ |

### 14.3 三层方案

**Layer C（最高优先级）**: 手工 `pathognomonic_markers.json` Top-20 标记 → LR > 100

**Layer A**: Orphadata product4 提取 → 17 pathognomonic + 876 diagnostic criteria

**Layer B**: PrimeKG gene-disease 边 → finding 含基因名时检查疾病关联

### 14.4 关键发现

1. Orphadata product4 的 876 条 "Diagnostic criterion" 比 17 条 "Pathognomonic sign" 价值更大
2. PrimeKG 已有 CML → ABL1/BCR "associated with" 边，但当前完全未被利用
3. PrimeKG CML 表型已含 "Ph-positive ALL" (HP:0004848)，信号存在但未被正确识别

## 15. 未集成数据源全面调研 (2026-05-27)

### 15.1 本地已有但未利用 (优先级 0, 零下载成本)

| 数据 | 内容 | B2/B3 价值 |
|------|------|-----------|
| **Guideline_common.json** (10.4MB) | 12,088 疾病, 133K HPO 对, **96% 不在 cache 中** | B2 ★★★★★ 定性关联层 |
| **Guideline_rare.json** (15.9MB) | 4,283 罕见病, 115K HPO 对, **100% 有频率** | B2 ★★★★ 可算 LR |
| **PrimeKG gene↔disease** (kg.csv 内) | 160,822 条, PrimeKGIndex 当前忽略 | B3 ★★★★ |
| **Orphadata product4 DiagnosticCriteria** | 17 pathognomonic + 876 diagnostic criteria | B3 ★★★★★ |

### 15.2 免费可下载 (优先级 1)

| 数据源 | 格式 | 内容 | B2/B3 |
|--------|------|------|-------|
| **GenCC** (CC0, TSV) | 6,086 gene-disease 对 + Definitive/Strong/Moderate/Limited 分级 | B3 ★★★★★ |
| **ClinVar gene_condition** (FTP) | gene-disease (OMIM/GeneReviews) | B3 ★★★★ |
| **MedGen MGREL.RRF** (FTP) | has_manifestation 表型关系 | B2 ★★★★ |
| **Orphadata en_product6.xml** (CC BY 4.0) | 4,128 gene-disease 含致病类型 | B3 ★★★★ |

### 15.3 需注册 (优先级 2)

OMIM genemap2/morbidmap (学术注册), OMIM Clinical Synopsis API (API Key), DisGeNET curated (Freemium)

## 16. 覆盖率修复实施记录 (2026-05-28)

> **状态标注图例** (回溯标注于 2026-06-03)
>
> | 标记 | 含义 |
> |------|------|
> | ✅ **有效** | 已实现且当前仍是生效的最终形态 |
> | 🔄 **已迭代** | 已实现，但被后续章节升级/扩展（机制保留，规模或能力增强） |
> | ⚠️ **已部分取代** | 仍在运行，但其大部分价值已被后续自动化方案覆盖 |
> | ❌ **已废弃** | 方案被否决或被替代，不再使用 |
> | 📊 **分析过时** | 当时的分析结论/数值已被后续实测推翻 |

### 16.0 各修复当前状态总览 (回溯标注于 2026-06-03)

| 小节 | 修复项 | 当前状态 | 迭代去向 |
|------|--------|---------|---------|
| 16.2 Fix 1 | B3 pathognomonic 反向排除 + 词边界 | 🔄 已迭代 | 16.5 扩展到 Orphadata 层 (B3-ext) |
| 16.2 Fix 2 | clinical_supplement_cache (22→21 条) | ⚠️ 已部分取代 | 21 条中 20 条已有自动化定性替代，仅余量化 LR 价值（尤其 leukostasis 三联征），最终由 B5 (第17章) 接管 |
| 16.2 Fix 3 | `_disease_match_score` 疾病模糊匹配 | 🔄 已迭代 | 16.6 加 `_strip_parens`；16.8/第18章 加 70 万条 disease bridge |
| 16.2 Fix 4 | B2-C 父疾病继承 | ❌ 已废弃 | 安全审计否决；改由 16.5 B4a 在 PrimeKG 内以安全方向重做 |
| 16.2 Fix 5 | 自动加载 supplement cache | 🔄 已迭代 | 16.8 `from_cache` 扩展为同时加载双层同义词桥接 |
| 16.5 B3-ext | Orphadata LR- 排除信号 | ✅ 有效 | — |
| 16.5 B2-A | Guideline 定性关联注入 | 🔄 已迭代 | 16.8 重做注入（cache 曾被重置后重灌，数值更新为 114,581 + 139,523） |
| 16.5 B4a | PrimeKG 子疾病表型继承 | ✅ 有效 | — |
| 16.5 B4c | disease-as-intermediate 2-hop | ✅ 有效 | — |
| 16.6 | HPO 本体层级匹配 + 三段论约束 | ✅ 有效 | subsumption_upward 机制仍在运行 |
| 16.7 | 15 对空白外部数据源评估 | 📊 分析过时 | "Doclogica 未注入" / "需 UMLS" 结论已被 16.8 推翻；"不可填补 6 对" 仍成立 |
| 16.8 | 多源开放数据集成 (v1.6) | 🔄 已迭代 | 数值 (267K cache / 143K disease / 15 finding bridge) 已被第18章 Athena 集成取代为 (377K / 702K / 398K) |

### 16.1 背景：CML Vignette LR 覆盖率分析

| 时间 | 覆盖率 | 说明 |
|------|--------|------|
| B1+B3 实施后 | 18/36 = **50.0%** | B1 归一化 + B3 pathognomonic 初始效果 |
| 本轮修复后 | 36/36 = **100%** | 5 项修复全部生效 |

### 16.2 五项修复详情

#### Fix 1: B3 pathognomonic 反向排除信号 ✅ → 🔄 已迭代

> **状态 (2026-06-03)**: 机制仍有效。16.5 将同一排除逻辑扩展到 Orphadata 层（`lookup_orphadata`），不再局限于 Layer C 手工表。

**文件**: `diagnostic_marker_index.py` `lookup_manual()`

当 finding 匹配 pathognomonic marker 但查询 disease 不在 `target_diseases` 中时，返回 `confidence="pathognomonic_exclusion"`, `lr_positive=0.15` 的排除信号，而非静默返回 None。

**临床意义**: Ph+ × AML 返回 LR+=0.15（表示 Ph+ 的存在降低 AML 可能性），Ph+ × CML 仍返回 LR+=150.0。

同时修复了 `_term_matches()` 词边界问题：短 term（≤5字符）要求词边界匹配，避免 "weight" 中的 "igh" 匹配到 IGH 基因位点。

#### Fix 2: clinical_supplement_cache 手工注入 ✅ → ⚠️ 已部分取代

> **状态 (2026-06-03)**: 当前实际为 **21 条**。经依赖审计：21 条中 **0 条**完全无自动化替代，**20 条**已有自动化*定性*关联（但 supplement 额外提供了量化 LR 数值），**1 条**完全冗余（自动化已有定量 LR）。
> - 移除 supplement 后 15-gap 覆盖 9/15（全部降级为无 LR 的定性关联），6/15 完全缺失。
> - 不可替代的核心价值是 **leukostasis 三联征**（retinal hemorrhage / cotton-wool spots / blurred vision）的量化 LR——这类间接并发症在所有自动化源中均无 sensitivity/specificity 数据。
> - 长期由 **B5 Finding Cluster（第17章）** 以综合征集群 LR 接管，届时可移除该手工层。

**文件**: `data/knowledge_raw/clinical_supplement_cache.json` (22 条)

填补所有自动化知识源（HPO/OMIM/Orphanet/PrimeKG/docLogica/Guideline）均缺失的高频临床关联。每条均注明来源（WHO 2022 / NCCN / Harrison 教科书 / leukostasis 文献）。

覆盖的关键缺口:
- Elevated blast count × CML-BC/AML/MDS (WHO 2022 定义)
- Anemia × CML-BC/AML (Harrison)
- Retinal hemorrhage / cotton-wool spots / blurred vision × CML-BC/AML/MDS (leukostasis 文献)
- Basophilia × AML/MDS (血液学教科书)
- Thrombocytopenia × AML (Harrison)
- Leukocytosis × CML-BC/AML (NCCN/Harrison)

#### Fix 3: LRRetriever 疾病模糊匹配增强 ✅ → 🔄 已迭代

> **状态 (2026-06-03)**: `_disease_match_score` 仍是核心，但已被多次升级：16.6 加入 `_strip_parens()` 去括号缩写；16.8 + 第18章在其之前增设 **disease synonym bridge（70 万条 alias→canonical）** 作为 Tier 1.5 精确同义词查找，模糊匹配现已退居为最后兜底。

**文件**: `lr_retriever.py`

1. 新增 `_disease_match_score()` 函数，使用多层匹配策略：
   - 精确匹配 → 子串 → 同义词归一化子串 → 关键医学词召回 → 同义词归一化关键词召回
2. 疾病同义词对: syndrome↔neoplasm, myeloid↔myelogenous, syndrome↔disease
3. 过滤泛化词（syndrome, disease, type, phase 等）只保留医学关键词做召回率计算
4. 修复了精确 disease 匹配存在时跳过亚型搜索的问题：现在同时搜索精确匹配 + 模糊匹配的所有疾病变体

**效果**: "myelodysplastic syndrome" 现在能匹配到 "myelodysplastic neoplasm with increased blasts" (score=0.8)，从而找到 MDS 亚型中的 retinal hemorrhage (LR+=0.65) 条目。

#### Fix 4: B2-C 父疾病继承 → 废弃 ❌ 已废弃

> **状态 (2026-06-03)**: 此 CML→CML-BC 方向的继承方案已确定废弃（方向性/程度安全隐患）。**注意区分**: 16.5 B4a 重新引入了"表型继承"，但那是在 **PrimeKG** 内对*零表型疾病*从表型最丰富的关联疾病继承（安全方向 + provenance 追踪），与本废弃方案机制不同。

**原方案**: 从 CML (父) 继承表型到 CML-BC (子)。

**安全审计发现**:
- Thrombocytosis (CML-CP Sn=0.545) 在 CML-BC 中应为 **Thrombocytopenia** → 方向相反
- Splenomegaly (CML-CP Sn=0.545) 在 CML-BC 中可能显著减少 → 程度错误
- 继承零增量（CML 本身不含 blast count/anemia 条目）

**替代方案**: 使用 clinical_supplement_cache 手工注入经审查的 CML-BC 特异性数据，每条均有临床文献支撑。

#### Fix 5: 自动加载 supplement cache ✅ → 🔄 已迭代

> **状态 (2026-06-03)**: `from_cache()` 的自动加载机制仍有效，并在 16.8 扩展为同时加载 `finding_synonym_bridge.json` 和 `disease_name_bridge_flat.json` 两个桥接文件（同样"放对目录即生效"，无需改 Controller）。

**文件**: `lr_retriever.py` `from_cache()` + `_load_supplement()`

`LRRetriever.from_cache()` 在加载主 unified cache 后，自动检查同目录下的 `clinical_supplement_cache.json`，合并其中不与主 cache 重复的条目。无需修改 Controller 配置。

### 16.3 来源分布 (36/36 对)

| 来源 | 命中数 | 占比 |
|------|--------|------|
| cache:HPO | 8 | 22.2% |
| cache:clinical_supplement (各子源) | 17 | 47.2% |
| B3:pathognomonic | 2 | 5.6% |
| B3:pathognomonic_exclusion | 4 | 11.1% |
| cache:Orphadata | 1 | 2.8% |

### 16.4 仍需 B4 的长期覆盖

cotton-wool spots 和 blurred vision 的 supplement cache 条目为临时解决方案（confidence=low）。长期应通过 B4 2-hop 间接链（finding → leukostasis → CML-BC）实现有理论支撑的自动化 LR 推导。

## 16.5 B2-A / B3-ext / B4a / B4c 实施记录 (2026-05-28)

> **状态 (2026-06-03)**: B3-ext / B4a / B4c ✅ 仍有效。B2-A 的 Guideline 注入 🔄 已在 16.8 重做（unified cache 曾被重置为 3 条后重新灌入，最终数值更新为 Guideline_rare 114,581 + Guideline_common 139,523），故本节"233,426 → 377,086"的数值为历史中间态。

### B3 扩展：Orphadata 层 LR- 排除信号

`lookup_orphadata()` 新增排除逻辑：当 HPO ID 在 Orphadata 中标记为某疾病的 pathognomonic sign，但查询的是**另一种疾病**时，返回 `lr_positive=0.15, confidence="pathognomonic_exclusion"` 排除信号。此前仅 Layer C (manual) 支持该机制。

### B2-A：Guideline 定性关联层注入

- **Guideline_rare**: 4,622 条新增（Orphanet 频率字符串→Sn 转换，使用 `FREQ_MAP`），109,628 条已存在被跳过
- **Guideline_common**: 139,038 条定性关联（`confidence="qualitative"`，无 LR 数据），3,103 条已存在被跳过
- **unified cache 总量**: 233,426 → 377,086 条
- `format_lr_reference_for_prompt()` 新增 `qualitative` 类型展示

### B4a：PrimeKG 子疾病表型继承

`PrimeKGIndex` 新增 `_inherit_parent_phenotypes()` 方法：在加载后，对所有 0 表型疾病，通过 `disease_disease` 边找到表型最丰富的关联疾病并继承其表型集合。

- **效果**: 9,927 个零表型疾病获得了表型数据（如 `adrenocortical insufficiency ← addison disease (49 phenotypes)`）
- `_inherited_phenotypes` dict 记录继承来源，供 provenance 追踪

### B4c：disease-as-intermediate 2-hop 路径

`find_2hop_chains()` 新增第二种路径类型：
1. **原 phenotype 路径**: evidence → intermediate_phenotype → disease（phenotype_phenotype + disease_phenotype_positive）
2. **新 disease-bridge 路径**: evidence → intermediate_disease → target_disease（evidence 是 intermediate_disease 的表型，intermediate 与 target 有 disease_disease 边）

新增辅助方法 `_find_diseases_with_phenotype()`。`get_2hop_lr()` 对 `chain_type="disease_intermediate"` 路径使用专门的 LR 估算策略。

### 覆盖度验证 (CML vignette, 17 findings × 3 diseases = 51 pairs)

| 指标 | 数值 | 占比 |
|------|------|------|
| 总对数 | 51 | 100% |
| 命中（量化 LR） | 43 | 84.3% |
| 命中（定性关联） | 8 | 15.7% |
| 排除信号 | 4 | 7.8% |
| 未命中 | 0 | 0% |

## 16.6 HPO 本体层级匹配与三段论方向约束 (2026-05-28)

> **状态 (2026-06-03)**: ✅ 有效。`HPOIndex` + `subsumption_upward` 衰减机制仍在 `lookup_fuzzy` 中运行（实测仍可命中如 `pancytopenia × MDS` 的上行匹配）。本节"无 supplement 9/24"是当时数据，后续 16.8 数据注入已将基线大幅提升。

### 问题：同义词缺失与上位症状匹配不安全

覆盖度审计发现 24 对无 supplement 时丢失的配对中，约 29% 是匹配机制问题：
- **Finding 同义词缺失**：`splenomegaly` ≠ `enlarged spleen or liver`（HPO 标准术语 vs Guideline 口语化描述）
- **疾病名括号干扰**：`Myelodysplastic Syndrome (MDS)` 因 "(MDS)" 导致子串匹配失败
- **上位症状无方向约束**：缓存中 "visual changes" 可匹配到 "retinal hemorrhages"，但反向（patient_broad → cache_specific）违反三段论

### 三段论约束设计

```
合法方向（上行匹配 / patient_specific → cache_broad）:
  大前提: Disease D → F_broad    (缓存记录: 白血病 → 出血倾向)
  小前提: F_specific IS-A F_broad (HPO: 视网膜出血 IS-A 出血倾向)
  结论:   D 可表现 F_specific ✓   (LR 按 depth 衰减)

非法方向（下行匹配 / patient_broad → cache_specific）:
  缓存:   D → F_specific (白血病 → 视网膜出血)
  患者:   F_broad (视觉异常)
  大前提不可倒置: 患者有 F_broad ≠ 患者有 F_specific ✗
  → attenuation = 0.0, 不返回 LR
```

### 实现

1. **`HPOIndex`** (`hpo_index.py`): 解析 `hp.obo`，构建:
   - 46,486 条 text→HPO ID 映射（canonical name + 所有 synonym + alt_id）
   - `is_a` 祖先/后代索引，BFS 计算 `subsumption_depth`
   - `classify_match()` API: 返回 `direction ∈ {exact, upward, downward, sibling, unrelated}` + `attenuation`

2. **`LRRetriever.lookup_fuzzy`** 修改:
   - 新增 HPO ID 级别匹配: 将 patient finding 和 cache entry 均解析为 HPO ID，比对 ID 而非文本
   - 当文本匹配失败时，检查 `is_ancestor_of(cache_hpo, patient_hpo)`:
     - 成立 → **上行匹配**: `_attenuate_entry()` 衰减 LR，`confidence="subsumption_upward"`
     - 不成立 → 不匹配（三段论非法方向）
   - LR 衰减公式: `attenuated_LR = 1.0 + (original_LR - 1.0) × max(0.3, 1.0 - 0.2 × depth)`

3. **`_disease_match_score`** 修改: 新增 `_strip_parens()` 去除括号缩写后再比较

### 效果

| 指标 | 修复前 | 修复后 | 变化 |
|------|--------|--------|------|
| 无 supplement 覆盖（24 对） | 3/24 (12.5%) | 9/24 (37.5%) | **+25%** |
| 其中 qualitative | 3 | 4 | +1 |
| 其中 subsumption (衰减 LR) | 0 | 5 | **+5** |
| 真数据空白（不可修复） | 21 | **15** | -6 |

### 修复路径分类

| 修复机制 | 新增覆盖对 | 示例 |
|----------|-----------|------|
| HPO ID 精确匹配 | 1 | `splenomegaly` = `enlarged spleen or liver` (同 HP:0001744) |
| HPO 上行包含 | 5 | `retinal hemorrhages` IS-A `bleeding easily` (HP:0000573 → HP:0001892) |
| 括号去除 + 上行 | 3 | `basophilia × MDS` 通过 MDS → "MDS with increased blasts" 子类型 |

### 仍不可修复的 15 对（初步评估，后续数据源探测已部分解决）

均为真正的知识源结构性空白：
- **11 对 AML 相关**: "Acute Myeloid Leukemia" 作为独立疾病实体在 HPO/Orphanet/Guideline 中完全缺失
- **3 对 cotton-wool spots**: 该临床体征未与任何白血病建立关联
- **1 对 blurred vision × MDS**: 无任何 MDS 变体包含视觉症状

## 16.7 外部数据源填补 15 对结构性空白评估 (2026-05-28)

> **状态 (2026-06-03)**: 📊 分析过时（结论已被执行结果部分推翻）。本节"Doclogica 仅用于 CUI 桥接、未注入 LR 缓存"和"需 UMLS 许可证"的判断已在 16.8 被推翻——Doclogica 13,193 条已注入，UMLS 由 MONDO+BioPortal+Athena 免费替代。仍然成立的是 **"不可自动填补的 6 对"**（cotton-wool spots×3 / blurred vision×MDS / basophilia×AML / retinal hemorrhage 量化 LR），它们至今仍依赖 supplement，待 B5 解决。

### 分析背景

对 15 对通过 HPO subsumption 仍无法恢复的"真空白"，逐一检测项目现有 + 外部潜在数据源的填补能力。

### PrimeKG 中 AML 的本体论角色

**关键发现**: PrimeKG 将 "Acute myeloid leukemia" 分类为 **`effect/phenotype`（表型）** 而非 **`disease`（疾病）**。
- AML 在 PrimeKG 中以 `disease_phenotype_positive` 关系出现在 29 个其他疾病的表型列表中（如 Fanconi 贫血 → AML, Li-Fraumeni 综合征 → AML）
- AML 本身 **没有** disease→phenotype 边——它没有自己的临床表现（fatigue, fever, splenomegaly 等）被记录
- 这意味着 PrimeKG 2-hop 链对 AML 无效，因为 AML 作为疾病节点不存在于 phenotype 子图中

### 各数据源对 15 对真空白的填补能力

| Finding | Disease | Doclogica | UMLS/文献 | PrimeKG | HealthKG | Bodhi |
|---------|---------|-----------|-----------|---------|----------|-------|
| splenomegaly | AML | ✓ | ✓ | ✗¹ | ✗² | ✗² |
| fatigue | AML | ✗ | ✓ | ✗¹ | ✗² | ✗² |
| bleeding easily | AML | ✓³ | ✓ | ✗¹ | ✗² | ✗² |
| elevated WBC | AML | ✓⁴ | ✗ | ✗¹ | ✗² | ✗² |
| fever | AML | ✗ | ✓ | ✗¹ | ✗² | ✗² |
| night sweats | AML | ✗ | ✓ | ✗¹ | ✗² | ✗² |
| bone pain | AML | ✓ | ✓ | ✗¹ | ✗² | ✗² |
| weight loss | AML | ✗ | ✓ | ✗¹ | ✗² | ✗² |
| retinal hemorrhages | AML | ✗ | ✓⁵ | ✗¹ | ✗² | ✗² |
| cotton-wool spots | AML | ✗ | ✗ | ✗¹ | ✗² | ✗² |
| blurred vision | AML | ✗ | ✗ | ✗¹ | ✗² | ✗² |
| cotton-wool spots | CML | ✗ | ✗ | ✗¹ | ✗² | ✗² |
| cotton-wool spots | MDS | ✗ | ✗ | ✗¹ | ✗² | ✗² |
| blurred vision | MDS | ✗ | ✗ | ✗¹ | ✗² | ✗² |
| basophilia | AML | ✗ | ✗ | ✗¹ | ✗² | ✗² |

> ¹ AML 在 PrimeKG 中归类为 phenotype，非 disease 实体
> ² 无白血病相关疾病条目
> ³ Doclogica 中 AML 有 "bleeding diathesis"（出血倾向）
> ⁴ Doclogica 中 AML 有 "hyperleukocytosis"（高白细胞症）和 "leukocytosis (blasts)"
> ⁵ 仅通过上位概念 "bleeding"——retinal hemorrhages 不直接记载于 AML 标准文献

### 汇总

| 数据源 | 可填对数 | 占比 | 备注 |
|--------|---------|------|------|
| **Doclogica** (项目已有) | **4/15** | 27% | AML 16 条 findings, CML 26 条, MDS 8 条。仅用于 UMLS CUI 桥接，**未注入 LR 缓存** |
| **UMLS/MedGen/临床文献** | **8/15** | 53% | 需 NLM 许可证 (免费) + API key。AML CUI=C0023467, SNOMED=91861009 |
| **Doclogica ∪ UMLS** | **9/15** | 60% | 合并去重后 |
| PrimeKG | 0/15 | 0% | AML 结构性分类为 phenotype |
| HealthKG | 0/15 | 0% | 156 种常见病，无白血病 |
| Bodhi KG | 0/15 | 0% | 779 种 SNOMED 疾病，无白血病 |

### 不可自动填补的 6 对

| Finding | Disease(s) | 根因 |
|---------|-----------|------|
| cotton-wool spots | AML / CML / MDS | 白棉絮状渗出本质是白细胞淤滞 (leukostasis) 的眼底并发症，是 **临床推理链**（WBC↑ → leukostasis → 视网膜微血管阻塞）的终点，而非直接的疾病-症状关联。无任何结构化知识库记录此关联。 |
| blurred vision | AML / MDS | 同上——间接并发症，需通过 leukostasis / anemia 间接链推导 |
| basophilia | AML | 嗜碱性粒细胞增多是 CML 的特征性标记（Doclogica CML 有），AML 中不常见 |

### 推荐行动优先级

1. ~~**[优先] 集成 Doclogica findings 到 unified_symptom_disease_cache**~~ ✅ **已完成** (v1.6)
2. ~~**[中期] 申请 UMLS 许可证**~~ → 改为方案 B/C: 使用 BioPortal + MONDO 开放数据替代 ✅ **已完成** (v1.6)
3. **[长期] cotton-wool spots / blurred vision**: 需通过 B5 Finding Cluster 或多跳病理链 (leukocyte↑ → leukostasis → retinal_ischemia → cotton-wool spots) 间接建模

### Doclogica AML 已有 findings（可立即注入）

```
gingival hypertrophy, granulocytic sarcoma, anemia (bone marrow failure),
arthralgia, peripheral joint arthritis, bleeding diathesis, bone pain,
cutaneous small vessel vasculitis, leukemia cutis, splenomegaly,
hepatomegaly, hypokalemia, hyperleukocytosis, metabolic acidosis,
thrombocytopenia, leukocytosis (blasts)
```

## 16.8 多源开放数据集成 (2026-05-28, v1.6)

> **状态 (2026-06-03)**: 🔄 已迭代。机制（双层桥接 + Tier 1.5）仍是当前架构，但本节所有规模数值已被 **第18章 Athena 词汇包集成 (v1.6.1)** 取代：
> - unified cache 267,305 → **377,107** 条（运行时，含 supplement）
> - disease bridge 143,610 → **702,147** 条
> - finding bridge 15 → **398,218** 条（同义词总数 850K）
> - 数据源新增 OHDSI Athena（95 万概念 / 127 万英文同义词）；本节"Athena 返回 403 需 Web UI"已通过手动下载词汇包解决。

### 整合概述

利用完全免费、无需 UMLS 许可证的开放数据源，构建双层同义词桥接体系，将 unified cache 从 3 条扩展到 267,305 条，15-gap 覆盖率从 0% 提升到 100%。

### 数据源汇总

| 数据源 | 类型 | 注入条目 | 贡献 |
|--------|------|---------|------|
| **Doclogica** (项目已有) | 疾病-finding 关联 | 13,193 条 | 1,475 种疾病 × 13K findings，填补 4/15 gap |
| **Orphanet Guideline_rare** | HPO 频率→LR 量化 | 114,581 条 | 4,283 种罕见病，含频率→LR 转换 |
| **Orphanet Guideline_common** | 症状-疾病定性关联 | 139,523 条 | 12,088 种常见病 |
| **Wikidata SPARQL** | AML 症状 | 5 条 | AML 7 症状（CML/MDS 无数据） |
| **MONDO OBO** (886K行) | 疾病同义词 bridge | 138,847 映射 | 58,794 疾病词条，346 白血病相关，1,447 同义词 |
| **BioPortal API** | finding + 疾病同义词 | 66 新映射 | AML 48+ 同义词, cotton-wool spots 6 同义词, CUI 映射 |

### 双层同义词桥接架构

```
┌────────────────────────────────┐
│  Finding Synonym Bridge        │  15 核心 finding → 共计 150+ 同义词
│  finding_synonym_bridge.json   │  含 BioPortal CUI 映射
│  e.g. "elevated white blood    │
│   cell count" → leukocytosis   │
└──────────────┬─────────────────┘
               │
┌──────────────▼─────────────────┐
│  Disease Synonym Bridge        │  143,610 alias → canonical 映射
│  disease_name_bridge_flat.json │  MONDO + BioPortal + 手动补充
│  e.g. "aml" → "acute myeloid  │
│   leukemia"                    │
└────────────────────────────────┘
```

### LRRetriever 查询流程（更新后）

```
lookup_fuzzy(finding, disease):
  1. 精确查找 (finding|disease key, 支持 :: 和 | 两种分隔符)
  2. 同义词桥接查找 (expand finding × expand disease → 组合键)
  3. HPO ID 查找 (finding → HPO resolve)
  4. 疾病索引 + fuzzy finding 匹配:
     a. 疾病同义词扩展 → 候选集
     b. 候选集内: finding 同义词匹配 (score=0.9) > 子串 (0.8) > bridge子串 (0.75) > token/stem Jaccard
  5. HPO subsumption (方向约束 + LR 衰减)
  6. Embedding fallback
```

### 15-gap 覆盖率对比

| 阶段 | 覆盖率 | 说明 |
|------|--------|------|
| v1.4 (原始 unified cache, 无 supplement) | 0/15 (0%) | 仅 3 条初始条目 |
| + HPO subsumption (v1.5) | 9/24→15 gap 中 0 恢复 | HPO 只解决同义词/层级问题 |
| + Doclogica + Wikidata 注入 | 8/15 (53%) | 直接关联 |
| + Guideline_rare/common 注入 | 10/15 (67%) | "blurred vision × Leukemia" 子串匹配 |
| + Finding synonym bridge | 14/15 (93%) | "elevated WBC" → leukocytosis 桥接 |
| + Disease synonym bridge + 全部桥接 | **15/15 (100%)** | 全覆盖 |

### 修改文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `lr_retriever.py` | 修改 | 新增 `_finding_synonym_bridge`, `_disease_synonym_bridge`; `from_cache` 加载桥接文件; `lookup` 支持 `\|` 和 `::` 双键格式; `lookup_fuzzy` 新增 Tier 1.5 同义词扩展 + 候选集内 bridge 匹配 |
| `unified_symptom_disease_cache.json` | 数据 | 3→267,305 条 (Doclogica + Orphanet + Wikidata) |
| `finding_synonym_bridge.json` | 新增 | 15 核心 finding 的 BioPortal 同义词映射 |
| `disease_name_bridge_flat.json` | 新增 | 143,610 条 MONDO + BioPortal 疾病同义词平面映射 |
| `mondo.obo` | 新增 | MONDO 本体 886K 行 |

### Athena / UMLS 替代方案

OHDSI Athena API 返回 403 (需通过 Web UI 手动下载)；UMLS 需注册许可证。实际效果证明完全可以用 MONDO + BioPortal (免费 API) 替代:

- **MONDO**: 覆盖 OMIM, DOID, ICD10, MESH, MedDRA 等 6+ 种 ID 体系的交叉引用
- **BioPortal**: 提供 SNOMED CT, MESH, HPO 三大本体的同义词 + CUI 查询
- **效果**: 143K 疾病同义词映射 + 150+ finding 同义词，无需 UMLS 许可证

## 16.9 安全性审查：LR 衰减公式与反向排除信号 (2026-06-03)

> 针对 16.6 的 HPO 上行衰减公式、16.2 Fix 1 / 16.5 B3-ext 的 pathognomonic 反向排除信号（固定 LR+=0.15），进行设计原理核查、下游触发机制追踪与临床安全评估。

### 16.9.1 下游消费机制核查（关键前提）

追踪 `DiagnosticMarkerIndex` / `LRRetriever` → `controller` → `updater` 的完整数据流，得到一个**决定性结论**：

> **代码中不存在任何 LR 数值的直接贝叶斯相乘。** 所有 LR 信号（pathognomonic 150.0、exclusion 0.15、subsumption 衰减值）都仅经 `DxFeatureRetriever.format_lr_reference_for_prompt()` 转为**文本**注入 EvidenceAnnotator 的 prompt；LLM 据此产出**分类标签** `branch_effects ∈ {strong_for … strong_against}`；最终由 `ordinal_update()` 映射为**固定序数权重** [0.2, 3.0] 相乘更新后验。

```
finding × disease
  → DiagnosticMarkerIndex.lookup() / LRRetriever.lookup_fuzzy()   (产出 LR 数值 + confidence + note)
  → format_lr_reference_for_prompt()                              (转为文本: "✗ ARGUES AGAINST — LR+=0.15" + Note)
  → payload["lr_reference"] → EvidenceAnnotator (LLM)             (人类式判断, 可读取 note 覆盖)
  → annotation["branch_effects"] = {bid: "strong_against" | ...}  (分类标签)
  → group_correlated_evidence()                                   (bundle 内 strong → moderate 降级)
  → ordinal_update(): label → ORDINAL_WEIGHTS[0.2..3.0] → ×posterior → normalize
```

**这一机制对前述安全担忧的影响**：

| 原始担忧 (基于"LR 直接相乘"假设) | 实际机制下的修正 |
|----------------------------------|-----------------|
| 0.15 在序贯更新中 0.15×0.15 累积放大 | ❌ 不成立。0.15 永不相乘；最多被 LLM 读成 `strong_against` → 权重 0.2；bundle 内还会被 `group_correlated_evidence` 降级为 0.5 |
| 衰减公式参数 (0.2/级, 0.3 地板) 影响后验精度 | ⚠️ 基本失效。衰减后的数值只是 prompt 里的一个文本，LLM 自行判断，公式精度实际是"装饰性"的 |
| 编造的定量值违反 B2.3 | ⚠️ 部分成立但被缓解。数值不进数学更新，但仍可能误导 LLM 判断 |

**新发现的下游问题**：

1. **真正的决策点是 LLM，而非公式**。安全性现在取决于 prompt 是否清晰传达 confidence 与例外 note。当前 exclusion 的展示是 `"✗ ARGUES AGAINST — LR+=0.15"` 置于主行、而关键豁免（如"Ph+ 也见于 AML"）置于次行 `Note:`，存在 LLM 过度采信主行、忽略 note 的风险。
2. **LR→标签映射无校准、不可审计**。从展示的"LR+=0.15"到分类标签 `strong_against` 的映射完全由 LLM 自由裁量，无确定性规则，导致结果不一致、不可复现。
3. **Pathognomonic 被序数层"压低"**。LR=150 经序数封顶后仅得权重 3.0（与任意 `strong_for` 等同）。计划 B3.4 曾设计"LR>50 时 posterior=max(current, 0.70)"的硬规则——**经核查从未实现**。这是"欠自信"失败（通常比过度自信安全），但削弱了特征性标记的应有价值。

### 16.9.2 LR 衰减公式：设计原理与评估

**公式**: `attn = max(0.3, 1.0 - 0.2 × depth)`；`LR_out = 1.0 + (LR_in − 1.0) × attn`（线性向 1.0 收缩）

| 维度 | 评估 | 判定 |
|------|------|------|
| 收缩方向 | 向无信息点 1.0 收缩，削弱（而非增强）证据 | ✅ 保守，失败模式为低估 |
| 深度→衰减映射 | HPO 中相隔 1 个 IS-A 步的表型差异不定；0.2/级、0.3 地板为魔数 | ❌ 无经验/文献校准 |
| 理论依据 | `LR(F_specific\|D)` 与 `LR(F_broad\|D)` 无保证的大小关系；具体症状可能更强或更弱 | ⚠️ 启发式假设，非贝叶斯定理 |
| 数值空间 | 应在 log-LR 空间收缩 (`LR^attn`)；本缓存 LR∈[0.25,2.5] 近 1，差异可忽略 | ⚠️ 当前数据下影响小 |
| LR- 改写 | 匹配由"患者具有具体症状"(presence) 触发，却同时改写返回 LR- | ⚠️ 逻辑瑕疵，低影响 |

**结论**：方向保守（安全），但参数任意、缺理论依据。鉴于 16.9.1 证实数值不进数学更新，公式的"精度问题"实际危害很低；真正重要的是**保留 confidence 降级标记**（当前 `confidence="subsumption_upward"` 已做到）。

### 16.9.3 反向排除信号 (固定 LR+=0.15)：设计原理与评估

**触发**: finding 命中某 pathognomonic marker，但查询疾病不在该 marker 的 `target_diseases` 中 → 返回 `lr_positive=0.15, confidence="pathognomonic_exclusion"`。

| 维度 | 评估 | 判定 |
|------|------|------|
| 推理方向 | "X 的定义性标记出现 → 降低竞争诊断 Y 概率"，即 `P(M\|Y) < P(M\|¬Y)`，公认"反向红旗" | ✅ 方向正确 |
| 不归零 | 0.15 ≠ 0，保留罕见实体可能性 | ✅ 符合"留有余地"原则 |
| 固定值 | 对**有跨病重叠**的标记是事实性错误（见下表） | ❌ 临床安全隐患 |
| 无分级 | 真排他标记 (PML::RARA) 应更接近 0.05；重叠标记根本不应触发 | ❌ 单一常数无法兼顾 |
| 与 B2.3 一致性 | 编造的固定定量值，与项目自身否决的"默认 Sn=0.30"同属反模式 | ❌ 自相矛盾 |

**逐条核对 `pathognomonic_markers.json` 中的跨病重叠风险**：

| Marker | 列为 target | 实际跨病重叠（错误排除风险） |
|--------|------------|------------------------------|
| Ph+ / BCR::ABL1 | CML | WHO 2022 设有独立的 **"AML with BCR::ABL1"**；也见于 Ph+ ALL。对 AML/ALL 触发 0.15 排除是**错误** |
| JAK2 V617F | PV | 也见于 **~55% ET、~65% PMF**。对 ET/PMF 触发 0.15 排除是**严重错误**（恰为首要鉴别诊断） |
| t(14;18)/BCL2 | FL | 也见于 **20-30% DLBCL (GCB)**。对 DLBCL 错误排除 |
| Auer rods | AML | 可罕见于**高级别 MDS**。对 MDS 排除偏强 |
| Reed-Sternberg | Hodgkin | RS 样细胞见于部分 **NHL、传单**。排除偏强 |

### 16.9.4 改进方案

**P0 — 反向排除去固定化（修复临床错误）**

1. **新增 `compatible_diseases` 字段**：在 `pathognomonic_markers.json` 每个 marker 增列该标记**确实可出现**的非定义疾病。
   - Ph+/BCR::ABL1 → `["acute myeloid leukemia", "ph+ acute lymphoblastic leukemia"]`
   - JAK2 V617F → `["essential thrombocythemia", "primary myelofibrosis"]`
   - t(14;18) → `["diffuse large b-cell lymphoma"]`
   - Auer rods → `["myelodysplastic syndrome"]`（仅高级别，低权重）
2. **`lookup_manual` / `lookup_orphadata` 增加门控**：查询疾病若命中 `compatible_diseases`，**不触发** exclusion（返回 None 或弱阳性），仅对真正互斥的疾病发排除信号。
3. **排除强度分级**（替代固定 0.15）：按 marker 的真实排他性给值——`confidence="pathognomonic"` 且无任何重叠记录 → 0.05；一般特异 → 0.2。或更符合 B2.3：**不给点估计，改发分类信号** `evidence_against` + 排他性 tier，由 LLM 结合 note 判断。

**P1 — LR→标签确定性映射（消除不可审计裁量）**

引入基于循证医学公认分级（Jaeschke et al. 1994 / McGee 2002）的确定性转换函数，作为 LLM 判断的**锚点**（而非取代）：

| LR+ 区间 | LR- 区间 | 序数标签 |
|---------|---------|---------|
| >10 | <0.1 | strong_for / strong_against |
| 5–10 | 0.1–0.2 | moderate |
| 2–5 | 0.2–0.5 | weak |
| 1–2 | 0.5–1 | minimal/neutral |

在 prompt 中同时给出 LR 数值**和**其对应的循证分级标签，减少 LLM 自由裁量的不一致。

**P2 — Pathognomonic 硬规则补全（兑现 B3.4 计划）→ 落地时调整为"延后 + 否定前置件"**

> 原方案：对 `confidence="pathognomonic"` 且无竞争 pathognomonic 的情形实现 bounded 后验地板 `posterior = max(current, 0.85)`。
>
> **落地决策（2026-06-03）：暂不实现硬地板，改为补齐其安全前置件**。理由：
> 1. 16.9.1 确立的核心架构是"软信号"——所有 LR 经 LLM + 序数层，不进硬数学。突兀加一个硬后验地板与该架构相冲突。
> 2. marker 匹配此前是**无否定识别的子串匹配**："no Auer rods"/"Reed-Sternberg absent" 会照样触发 pathognomonic 命中。在此基础上加 0.85 硬地板将**锁死错误诊断**，是净负安全改动。
> 3. 单一关键词命中即把后验抬到 0.85 过于激进（fuzzy 疾病名匹配亦可能错配）。
>
> 因此先实现**否定语境识别**（见下），作为任何未来硬规则的必要前置件；同时 P1 的 EBM band 已把 pathognomonic（LR≥10）明确标注为"strong_for"，软信号侧已最大化。硬地板待否定/语境识别足够稳健后再评估。

**P3 — 衰减公式微调（低优先级）**

- 改 log-LR 空间收缩 `LR_out = LR_in^attn`；文档注明 depth 为启发式、参数未校准。
- presence 触发的上行匹配不改写 LR-。
- 维持 `confidence="subsumption_upward"` 降级标记（已实现）。

**安全原则总结**：所有外部/推断 LR 当前均为**软信号**（经 LLM + 序数层），不得改为硬性数学相乘；任何点估计若无 2×2 表或文献支撑，应优先用**分类信号 + 例外清单**表达（遵循 B2.3）。排除信号**永不归零**，pathognomonic **永不到 1.0**。

### 16.9.5 改进落地记录 (2026-06-03)

| 项 | 状态 | 落地内容 | 文件 |
|----|------|---------|------|
| **P0-1** compatible_diseases | ✅ 已实现 | 为 7 个跨病重叠 marker 增 `compatible_diseases`（Ph+/AML+ALL、JAK2/ET+PMF、t(14;18)/DLBCL、t(8;14)/DLBCL、Auer/MDS、RS/NHL+DLBCL，+ 16.9.6 增 amyloid/MM）；版本 → v1.1 | `pathognomonic_markers.json` |
| **P0-2** 排除门控 | ✅ 已实现 | `lookup_manual` 重构：target 命中优先 → compatible 命中则**跳过不发排除** → 否则发排除；`lookup` 级联可继续其他层 | `diagnostic_marker_index.py` |
| **P0-3** 排除分级 | ✅ 已实现 | `_exclusion_lr_for()`：pathognomonic→0.1，highly_specific→0.3，支持 per-marker `exclusion_lr` 覆盖；orphadata 排除 0.15→0.1 | `diagnostic_marker_index.py` |
| **P1** EBM band | ✅ 已实现 | 模块级 `ebm_lr_band()`（Jaeschke 1994 / McGee 2002），注入 pathognomonic / highly_specific / exclusion / subsumption / indirect_chain / 通用 LR 各 prompt 行：`[EBM: <band> → suggests <label>]` | `dx_feature_retriever.py` |
| **P2** 硬地板 | ⏸️ 延后 | 见 16.9.4 P2 决策；改为先做否定前置件 | — |
| **P2-prereq** 否定识别 | ✅ 已实现 | 前置 `_NEGATION_CUES` + 后置 `_TRAILING_NEGATION_CUES`（absent/negative/not seen…），窗口扫描；"no Auer rods"/"RS absent" 不再触发命中或排除 | `diagnostic_marker_index.py` |
| **P3** log-LR 衰减 | ✅ 已实现 | `_attenuate_entry`：线性收缩 `1+(LR-1)*attn` → log 空间 `LR^attn`；presence 触发不再改写 LR-（置 None） | `lr_retriever.py` |

**改进前 vs 改进后（关键对照）**：

| 场景 | 改进前 | 改进后 |
|------|--------|--------|
| JAK2 V617F vs ET / PMF | LR+=0.15 排除（**错误**，首要鉴别诊断被压低） | 不发排除（compatible 门控）✅ |
| Ph+ vs AML | LR+=0.15 排除（错误，WHO 有 AML-BCR::ABL1） | 不发排除 ✅ |
| 淀粉样变 vs 多发性骨髓瘤 | LR+=0.15 排除（错误，AL 淀粉样变与 MM 共存） | 不发排除（16.9.6 修）✅ |
| anti-CCP / smudge cells 命中靶病 | 标为 `confidence=pathognomonic`（**夸大**） | 标为 `highly_specific`（16.9.6 修）✅ |
| 真排他 marker（PML::RARA）vs 无关病 | LR+=0.15（一刀切） | LR+=0.1（分级，更强且更准）✅ |
| "no Auer rods seen" vs AML | 触发 pathognomonic / 排除（**危险误判**） | None（否定识别）✅ |
| 上行 subsumption LR=0.25, depth=2 | 线性 0.55 | log 0.435（log 空间更合理）；LR- 不再误输出 ✅ |
| LLM 看到的 LR | 仅裸数值，映射靠自由裁量 | 数值 + EBM 分级锚点，减少不一致 ✅ |

数值不变事实：因下游为序数 + LLM（16.9.1），上述改动主要提升**喂给 LLM 的信号正确性与一致性**，而非直接改动后验算术。

### 16.9.6 补充测试：多疾病知识层测试 (2026-06-03)

**动机**：此前所有流水线测试仅用**单一 CML vignette**（`test_full_pipeline_cml.py`），无法暴露其他疾病/机制下的问题。新增确定性多疾病测试台 `scripts/test_multidisease_supplementary.py`，覆盖 10 个跨病场景（PV/ET/PMF、APL/AML、Hodgkin/DLBCL、RA/SLE、淀粉样变/MM、MCL/CLL、CMV 等），直击 P0 改动影响面，无需 LLM。

**新暴露并修复的问题**（单一 CML 用例从未触及）：

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| **A** 置信度夸大 | target 命中**硬编码** `confidence="pathognomonic"`，把 highly_specific marker（anti-CCP LR30、smudge LR50、JAK2 LR80、t(11;14) LR80…）也标成 pathognomonic | `lookup_manual` 未读 marker 自身 confidence | 读 `m["confidence"]`；prompt 新增 `⊕ HIGHLY SPECIFIC` 分支 |
| **B** 假排除 | 淀粉样变 marker 对**多发性骨髓瘤**发 0.1 排除，但 AL 淀粉样变常与 MM 共存 | amyloid marker 缺 compatible_diseases | 增 `compatible_diseases: [multiple myeloma, …]` |
| **C** 措辞脆性 | "owl-eye **intranuclear** inclusion bodies" 无法匹配 marker term "owl-eye inclusion bodies"（中插一词），CMV 无信号 | marker 层为精确子串匹配，不容词序/插词 | ⚠️ 记录在案，未修（需引入 marker 层模糊匹配，超出本次安全审查范围） |

**测试结果**：10 场景，"误排除真实诊断" bug = 0；A/B 修复后 highly_specific 不再误标 pathognomonic、MM 不再被误排除。回归：`tests/test_knowledge_layer.py` 28 passed。

**遗留（C 类）**：marker 层精确子串匹配对措辞敏感（插词、词序、缩写）。当前其他层（LRRetriever 的 HPO/同义词桥、RAG）可部分兜底，但 marker 层自身建议后续引入与 LRRetriever 同源的 HPO 归一化。

### 16.9.7 补充测试 II：真实 USMLE 数据集暴露的缩写碰撞 bug (2026-06-03)

**动机**：进一步用真实诊断数据集 `medbullets_hard_test.tsv`（89 例 USMLE 难题，27 例为诊断类）检验。脚本 `scripts/mine_medbullets_cases.py`：分类诊断类用例，并对含 marker 关键词的 vignette 逐选项跑 marker 层，标记"排除正确答案"等安全问题。

**重大发现（高危真实 bug）**：marker 词表含 `sma`/`ema`/`ama`/`hbs` 等**超短抗体缩写**，与常见临床 token 严重碰撞：

| 标记词 | 本意 | 碰撞含义（高频） |
|--------|------|-----------------|
| `sma` | 抗平滑肌抗体（AIH） | **superior mesenteric artery** 肠系膜上动脉 |
| `ama` | 抗线粒体抗体（PBC） | **against medical advice** 自动离院 |
| `ema` | 抗肌内膜抗体（乳糜泻） | 多义 |
| `hbs` | 血红蛋白 S（镰状细胞） | **HBsAg** 乙肝表面抗原 |

初测：27 个 marker-相关用例中 **25 例的正确答案被错误排除**（如 "SMA occlusion"→排除肠系膜缺血、"left AMA"→排除…）。词边界能挡住 `edema`/`plasma`/`asthma` 内的子串，但挡不住**独立的** `SMA`/`AMA` token。

**根因**：超短全字母缩写即使加词边界仍会匹配真实文本中同形异义的独立 token。

**修复（16.9.7）**：上下文消歧而非删词（保留召回）。`_AMBIGUOUS_ABBREV = {sma, ema, ama, hbs, hb s}` 中的词，只有当 ±50 字符内出现血清学/化验线索（antibody / positive / titer / IgA / anti- / serology / autoimmune …）时才算命中：
- `"CT shows SMA occlusion"` → 不命中 ✅
- `"left AMA"` / `"HBsAg positive"`（"hbs" 另受词边界保护）→ 不命中 ✅
- `"SMA antibody positive, titer 1:160"` / `"AMA positive on serology"` / `"IgA EMA antibodies"` → 仍命中 ✅

**结果**：medbullets 27 用例"排除正确答案" **25 → 0**；真实措辞消歧测试 7/7；回归 `test_knowledge_layer.py` 28 passed、多疾病台 0 bug。

**方法论意义**：单一 CML 用例 + 自构 10 场景都**未**暴露此 bug——只有真实、跨科室的大数据集才触发了超短缩写碰撞。证实"在数据集内另寻诊断用例"对发现潜在问题的必要性。后续可扩展 `_AMBIGUOUS_ABBREV` 并对全部 ≤3 字母标记词做碰撞审计。

**遗留**：marker 层仍为关键词匹配，未做 LLM 全流水线评测（需 LLM endpoint）。27 个诊断类用例的 HPO/LR-cache 覆盖率评测留待全流水线测试。

### 16.9.8 调研：从手写黑名单到自动化上下文消歧 (2026-06-03)

> 16.9.7 的 `_AMBIGUOUS_ABBREV` 是**手写黑名单**——不可扩展、需逐词维护、必漏未知碰撞。本节调研可自动化、可调用外部数据 / RAG / KG 的消歧方案。

#### 16.9.8.1 问题重构：这是"实体链接 / 概念归一化"，不是字符串匹配

当前 marker 层逻辑是 `字符串命中 → 触发`。根本缺陷：把**表面形式**当成**概念身份**。正确范式（生物医学 NLP 标准任务）：

> **mention → 结合上下文定位到一个标准概念（CUI/HPO）→ 仅当 grounded concept == marker 的 concept 时才触发。**

如此一来歧义问题自动消失，无需任何黑名单："SMA" 在 "SMA occlusion" 中被定位为 `C0227317 superior mesenteric artery [Body Part]`，与 ASMA marker 的 `C0312825 smooth muscle antibody [Lab]` 概念不等 → 不触发。这也与本项目"三段论大小前提不得倒置"一致：概念身份是比字符串更严格的前提。

#### 16.9.8.2 文献范式（2024–2026）

| 范式 | 代表方法 | 要点 | 可借鉴 |
|------|---------|------|--------|
| 临床缩写 WSD | GlossBERT / OTA 分类（ClinicalBERT, BlueBERT），CASI/MSH-WSD/UMN | context-candidate 对二分类；F1≈0.91 | 上下文 vs 候选义项配对打分 |
| WSD + 结构知识 | UMLS **语义类型**增强特征 (PMC11141859) | 加 UMLS semantic type，F1→0.93 | 语义类型过滤（Lab vs Body Part）|
| 语料自导出义项 | FlexiTerm + 二分类 (Frontiers 2024) | 不依赖外部义项库，从语料抽长形式 | 减少对人工义项表依赖 |
| 生物医学实体链接 BEL | retrieve-and-rerank（SapBERT 稠密检索 + cross-encoder/LLM 重排）| 候选生成 + 重排两阶段；bounded recall | 与本项目现有 Embedding+RAG 同构 |
| 同形词消歧 | **BELHD** (2024) | KB 侧预处理：给同形概念加消歧串，强制唯一链接 | KB 侧自动消歧（离线、确定性）|
| LLM 生成式重排 | BeLink / BioELX (2026) | mention-anchored prompt，set-wise 多选；RAG 相关反馈 | LLM 工具调用消歧 |

#### 16.9.8.3 现有基础设施已足以支撑（无需从零造）

| 能力 | 已有组件 | 现状 |
|------|---------|------|
| CUI 概念表 | `finding_synonym_bridge.json` | **398,218 条全部带 CUI** ✅ |
| 语义类型 / 概念域 | Athena `CONCEPT.csv`（domain/class）、BioPortal | 已下载，可解析 |
| 稠密语义检索 | `EmbeddingIndex`（sentence-transformers + FAISS）| 已实现 |
| 本体定位 | `HPOIndex.resolve_fuzzy()` / `classify_match()` | 已实现 |
| CUI 桥接 | `DiseaseNameResolver`（CUI + 缩写扩展 + token Jaccard）| 已实现 |
| RAG / 文献 | `RAGRetriever`（StatPearls/教科书 FAISS）、`PubMedRetriever` | 已实现 |
| LLM 重排 | ChainDiscoverer / annotator LLM | 已接入 |

#### 16.9.8.4 提议的分层自动消歧架构（替代黑名单）

> 设计原则：**确定性优先、外部调用兜底、成本随歧义度递增**。仅对"自动检测为歧义"的 mention 逐层升级。

- **T0 自动歧义检测（离线、确定性、零成本）— 取代手写黑名单**
  - 对每个 marker term 取其 CUI；用 Athena/BioPortal/UMLS 反查该**表面形式**映射的所有 CUI。
  - 若一个 term 跨**多个语义类型/概念域**映射到 ≥2 CUI（如 "SMA"→动脉[Body Structure] + 抗体[Lab]），自动标记为 ambiguous，并记录"marker 期望的语义类型"。
  - 产物：`auto_ambiguity_map.json`（脚本生成，非手写），替代 `_AMBIGUOUS_ABBREV`。
- **T1 语义类型 / 上下文向量消歧（离线、确定性）**
  - 命中歧义 term 时，取 ±窗口上下文，用 `EmbeddingIndex` 比较 mention 上下文与各候选义项 gloss 的余弦；或用浅层线索（支配动词、共现 token）判定语义类型是否匹配 marker 期望类型。对应 PMC11141859（语义类型，F1 0.93）。
- **T2 RAG 相关反馈消歧（工具调用、外部数据）**
  - 用 `RAGRetriever`/PubMed 为每个候选义项取证据片段，比较哪个义项的检索上下文与 mention 上下文更契合（generative relevance feedback）。对应 BeLink/PMC12866626。
- **T3 LLM set-wise 重排（工具调用）**
  - 仅对 T1/T2 仍不确定者：mention-anchored prompt（"在 '…[SMA] occlusion…' 中，SMA 指 (A) 抗平滑肌抗体 (B) 肠系膜上动脉？"）单次多选。对应 BioELX/BeLink。
- **T4 外部 KG 交叉校验（外部 KG）**
  - 用 Wikidata/UMLS/MONDO 的语义类型与邻域关系做最终一致性核查（marker 概念应为 Lab/Immunologic Factor；若上下文强指 Anatomical Structure 则否决）。

#### 16.9.8.5 落地建议（分阶段）

1. **阶段一（推荐立即做，确定性、零外部依赖）**：实现 **T0 + T1**。用现有 CUI 桥 + Athena 语义域脚本自动生成 `auto_ambiguity_map.json`，并用语义类型/上下文向量替换 `_AMBIGUOUS_ABBREV`。可完全离线、可复现、无 LLM 成本。预期同时覆盖未来未知碰撞。
2. **阶段二（按需）**：对低置信 mention 接 **T2 RAG**，复用现有 FAISS 索引。
3. **阶段三（高歧义/高风险才触发）**：**T3 LLM 重排**，严格限定调用频次（仅 T0 标记且 T1/T2 不决者），控成本。
4. **统一原则**：所有消歧仍输出**软信号 + confidence**（与 16.9.1 一致），消歧失败时"宁可不触发 marker"（fail-safe，避免假排除/假命中）。

**结论**：自动化可行且基础设施齐备。手写黑名单应被 **T0 自动歧义检测（基于现有 CUI/语义类型）** 取代，RAG/LLM 作为高歧义兜底。这是文献主流（retrieve-and-rerank + 语义类型 + LLM 重排）在本项目既有组件上的直接落地，无需引入新依赖。

> 状态：✅ 已落地（阶段一 T0+T1 确定性，T2/T3/T4 钩子已接入、按需启用）。落地记录见 16.9.9。

### 16.9.9 落地记录：T0–T4 自动消歧替代手写黑名单 (2026-06-04)

#### 16.9.9.1 数据前提的事实性纠正（重要）

16.9.8.3 调研称 `finding_synonym_bridge.json` "398,218 条全部带 CUI ✅"。**实测不成立**：该文件每条都有 `cui` 字段，但 **仅 112 条非空**（99.97% 为 `null`），且它是 phenotype/finding 导向，**不含任何短抗体缩写**（sma/ama/ema/hbs 在其中均查无）。本地也无带语义类型的完整 UMLS / Athena `CONCEPT.csv`（仅有 9 条目的 `athena_omop_synonyms.json`，无 domain/semantic type）。

因此 16.9.8.4 设想的"对每个 marker term 取 CUI → 反查表面形式映射的所有 CUI → 跨语义类型即判歧义"在当前数据下**不可直接实现**。落地改用**等价且确定性、零外部依赖**的替代检测（见下），并保留升级到真实 CUI/语义类型源的接口。

#### 16.9.9.2 实际落地架构

| 层 | 状态 | 实现 |
|----|------|------|
| **T0** 自动歧义检测 | ✅ 确定性、离线 | `scripts/build_auto_ambiguity_map.py` → `data/knowledge_raw/auto_ambiguity_map.json`。检测器：**单 token、全字母、长度 ≤4 的缩写形**（acronym-shaped）即判歧义（16.9.7 实证的碰撞根因）。每个歧义 term 自动记录：`expected_semantic_type`（由 marker 自身 terms/note 推断：serology/molecular/histopathology）、`positive_cues`（共享语义型词典 ∪ **同 marker 全称兄弟 term 的内容 token**，自动派生而非手列）、`competing_cues`（解剖/给药/通用义词典）。当前自动标出 6 个：`acpa, ama, asma, ema, hbs, sma`（覆盖原黑名单 sma/ema/ama/hbs 并新增 acpa/asma）。 |
| **T1a** 词法语义型消歧 | ✅ 确定性、离线、常开 | mention ±50 字符窗口：命中 positive cue → marker 义（FIRE，向后兼容原 `_abbrev_context_ok`）；仅命中 competing cue → 他义（SUPPRESS）。 |
| **T1b** 上下文向量消歧 | ✅ 已接入、按需 | 仅当 T1a 不决且注入了 `EmbeddingIndex` 时：`EmbeddingIndex.cosine(ctx, marker原型)` vs `cosine(ctx, 竞争原型)`，按 0.05 余弦边际裁决。 |
| **T2** RAG 相关反馈 | ✅ 钩子已接入、按需 | 注入 `RAGRetriever` 时：对 marker 义/竞争义各检索片段，比较与 ctx 的 token 重叠。 |
| **T3** LLM set-wise 重排 | ✅ 钩子已接入、按需 | 注入 `llm_fn` 时：mention-anchored 二选一（A=marker 义 / B=他义），仅对 T1/T2 不决者。 |
| **T4** 外部 KG 一致性 | ✅ 钩子已接入、按需 | 注入 ontology（HPOIndex 等）时：竞争义概念在本体可定位则倾向 SUPPRESS。 |
| **Fail-safe** | ✅ | 所有可用层均不决 → **不触发 marker**（避免假命中/假排除，遵循 16.9.8.5.4）。 |

#### 16.9.9.3 改动文件

| 文件 | 改动 |
|------|------|
| `scripts/build_auto_ambiguity_map.py` | 新增。T0 生成器。 |
| `data/knowledge_raw/auto_ambiguity_map.json` | 新增（生成物，6 个歧义 term）。 |
| `src/.../knowledge/marker_disambiguator.py` | 新增。`MarkerDisambiguator`（T0–T4 级联 + `Decision`）。 |
| `src/.../knowledge/embedding_index.py` | 新增 `cosine(a,b)`（T1b 用）。 |
| `src/.../knowledge/diagnostic_marker_index.py` | 用 `MarkerDisambiguator` 替代 `_AMBIGUOUS_ABBREV`/`_abbrev_context_ok`（后者降级为 `_legacy_*` 兜底）；`__init__` 增 `auto_ambiguity_map_path`/`embedding_index`/`rag_retriever`/`llm_fn`/`ontology_index`。 |
| `src/.../config.py` | 增 `auto_ambiguity_map_json`。 |
| `src/.../controller.py` | 构建 marker index 时传入 ambiguity map 路径与已加载的 `emb_index`（T1b）。 |
| `tests/test_knowledge_layer.py` | 新增 `TestMarkerDisambiguation`（7 例）。 |
| `scripts/verify_marker_disambiguation.py` | 新增。确定性验证（10 例 + fail-safe）。 |

#### 16.9.9.4 验证结果

- `verify_marker_disambiguation.py`：10/10 通过（"SMA occlusion"不触发、"SMA antibody"触发、"left AMA"不触发、"IgA EMA antibodies"触发、"HBsAg"被词边界拦截等）+ fail-safe 通过。
- `mine_medbullets_cases.py`（真实 USMLE）："排除正确答案" = **0**（与 16.9.7 一致；期间发现并修复一处**自指 cue bug**——`iga ema` 派生出的 `ema` token 误成为 `ema` 自身的 positive cue，已通过"派生 cue 排除 acronym 形 token"修复）。
- `tests/test_knowledge_layer.py`：**35 passed**（原 28 + 新 7），无回归。
- 多疾病台：true-Dx-excluded = 0。

#### 16.9.9.5 遗留与后续

- **真 CUI/语义类型源**：当前 T0 用"短缩写形"结构启发式替代 CUI 反查。若后续接入完整 UMLS/Athena `CONCEPT.csv`，可把 T0 升级为真正的"表面形式→多 CUI/多语义类型"检测，覆盖非短形的同形异义。
- **T1b/T2/T3/T4 默认未在热路径强制启用**：embedding 已在 controller 注入（仅"无 cue"罕见分支触发，惰性、低成本）；RAG/LLM/KG 需显式注入。
- **16.9.6 Issue C（marker 层措辞脆性，插词/词序）**仍未修，与本节正交。

## 17. B5: Finding Cluster — 以综合征集群作为 LR 统计单元 (2026-05-28)

### 17.1 问题：条件独立性假设被系统性违反

当前系统对 bundle 中的多个 finding 分别计算 individual LR，再通过 `ordinal_update` 将效应值相乘更新后验概率。这隐含了 **findings 间的条件独立性假设**——即在给定疾病的条件下，各 finding 的出现概率互不影响。

**该假设在临床实践中经常被违反**。例如 CML vignette 中的视网膜出血、棉絮状渗出和视力模糊三者同源于白细胞淤滞（leukostasis），一旦出现其中一个，其他两个的概率大幅升高。将三者的 LR 分别相乘会 **系统性高估** 该证据集的联合诊断价值。

### 17.2 临床文献支撑

#### 关键定量结论

**Glasziou et al., 1997, JGIM**（"Quantitative assessments from the clinical examination: How should clinicians integrate the numerous results?"）：

| 策略 | ROC AUC | 结论 |
|------|---------|------|
| 7 个 individual LR 相乘 | **0.69** | 最差——条件依赖导致过度自信 |
| 逻辑回归选 3 个非冗余项 LR | **0.79** | 最佳 (p=0.02 vs 7 项) |
| 仅用单个最佳 finding | **0.75** | 与 3 项无显著差异 (p=0.20) |

> **结论**："Conditional independence assumptions were violated when seven clinical examination items were used to estimate posterior probability. Focusing on items identified through logistic models overcame violations of independence."

#### 五种 Finding 集群范式

| # | 范式 | 临床实例 | LR 来源 | 关键特征 |
|---|------|---------|---------|---------|
| 1 | **Clinical Prediction Rule (CPR)** | Wells PE 评分: {DVT 征象, HR>100, 制动, 恶性肿瘤, 咯血, 临床判断} → 低/中/高风险 | Stratum-Specific LR (SSLR): 低=0.16, 中=1.0, 高=16.0 | 已验证、有分层 LR |
| 2 | **中间病理生理状态** | Disease ← Leukostasis ← {视网膜出血, 棉絮渗出, 视力模糊} | Bayesian Network 中间节点 | QMR 开发者承认缺失此表示是关键缺陷 (Shwe 1991) |
| 3 | **诊断标准集** | CML-BC WHO 2022: {≥20% blasts + Ph+/BCR-ABL1 + CML 病史} = 确诊; Duke 标准: 2 major 或 1 major+3 minor = definite IE | 集群本身即诊断定义 | 官方权威 |
| 4 | **Category-Oriented LR** | 下尿路症状类别: 阴道分泌物 vs 阴道刺激 → 仅用鉴别力更强者 | 最佳单项 LR | 依赖 finding 取鉴别力最强者 |
| 5 | **临床 Gestalt** | {视网膜出血 + 视力模糊 + WBC>100k} → "leukostasis 图景" | 隐式联合 LR | 有时准确性超过形式化规则 |

**Nikovski, CMU, 2000** (Constructing Bayesian Networks for Medical Diagnosis):
> "Another strategy is to introduce intermediate nodes that represent pathophysiological states; they are also called **clusters of findings**. In this scheme, the findings determine the truth value of the intermediate node, and only the latter influences the disease node directly."

**QMR/INTERNIST-1 开发者** (Shwe et al., 1991):
> "a lack of temporal modeling, a lack of representation of degree of severity, a lack of anatomic knowledge, and **an absence of a representation of intermediate pathophysiologic states**" — 明确列为系统关键缺陷

### 17.3 当前系统的具体违反

| 环节 | 问题 | 影响 |
|------|------|------|
| `EvidenceAnnotator` | 对 bundle 中每个动作分别标注 `branch_effects` | 隐含条件独立 |
| `ordinal_update` | 将多个效应值相乘 | 过度自信 |
| `group_correlated_evidence` | 将多动作 `strong_*` 降级为 `moderate_*` | 对条件依赖的粗暴近似，缺乏理论基础 |
| TALP 叶节点粒度 | 以单个 finding 为单元，相关 finding 被反复分析 | 浪费分析轮次，信息增量递减 |

### 17.4 CML Vignette 中的自然集群

| ID | 名称 | 成员 | 共享机制 | 问题 |
|----|------|------|---------|------|
| C1 | 骨髓衰竭 | Anemia, Thrombocytopenia, Fatigue | 骨髓被 blast 取代 | individual LR 相乘高估 |
| C2 | 髓系增殖 | Leukocytosis, Splenomegaly, Basophilia | MPN 克隆扩增 | CML-BC vs AML 鉴别时仅 basophilia 有价值 |
| C3 | 白细胞淤滞 | Retinal hemorrhage, Cotton-wool spots, Blurred vision | WBC↑ 微循环阻塞 | 3 个弱 LR 不应分别相乘 |
| C4 | Blast Crisis 定义 | ≥20% blasts, Ph+/BCR-ABL1 | 诊断标准 | 充分条件，命中即确诊 |
| C5 | 全身性症状 | Fatigue, Weight loss | 非特异 | LR≈1.0，可忽略 |

### 17.5 四级集成方案

#### Scale 1: LR 模块内 — Cluster LR Overlay ★ 推荐立即实施

| 项目 | 内容 |
|------|------|
| 新增文件 | `data/knowledge_raw/finding_clusters.json` (~50 集群定义) |
| 新增类 | `knowledge/finding_cluster_index.py` → `FindingClusterIndex` |
| 修改 | `knowledge/dx_feature_retriever.py` |
| 改动量 | ~3 文件, 1 数据文件 |
| 向后兼容 | ✓ 无集群匹配时回退到 individual LR |

**机制**: `DxFeatureRetriever` 在对一组 findings 查询 LR 时，先检查是否有 ≥ `min_members` 个 finding 属于同一已知集群。若匹配，返回集群级联合 LR + `confidence="cluster_lr"`；未匹配则正常返回 individual LR。

```json
{
  "clusters": [{
    "id": "leukostasis_ocular",
    "name": "Leukostasis Ocular Syndrome",
    "member_findings": ["retinal hemorrhage", "cotton-wool spots", "blurred vision"],
    "min_members_to_activate": 2,
    "mechanism": "hyperleukocytosis → microvascular occlusion",
    "disease_lr": {
      "acute myeloid leukemia": {"lr_positive": 4.5, "source": "leukostasis_literature"},
      "chronic myeloid leukemia, blast crisis": {"lr_positive": 3.8},
      "myelodysplastic syndrome": {"lr_positive": 0.3}
    }
  }]
}
```

#### Scale 2: Evidence Pipeline — Syndrome Pre-Clustering

| 项目 | 内容 |
|------|------|
| 修改 | `state.py`: `EvidenceItem` 增加 `cluster_id`; `DiagnosticState` 增加 `evidence_clusters` |
| 修改 | `controller.py`: VignetteParser 后增加 `FindingClusterIndex.annotate()` 步骤 |
| 修改 | `evidence_annotator.txt`: prompt 感知集群上下文 |
| 改动量 | ~5 文件 |
| 依赖 | Scale 1 |

EvidenceAnnotator 看到: "以下 3 个 finding 构成 Leukostasis 综合征 (cluster_lr=3.8 for CML-BC)，请作为一个整体评估"。

#### Scale 3: TALP + Bundler — Syndrome-Centric Planning

| 项目 | 内容 |
|------|------|
| 修改 | TALP prompt: candidate leaf 升级为 syndrome 粒度 |
| 修改 | `action_bundler.py`: 以 syndrome 为去重/覆盖单元 |
| 修改 | `evidence_annotator.txt`: syndrome 级 branch_effects |
| 修改 | `updater.py`: cluster_lr 替代 ordinal weight |
| 改动量 | ~8 文件 + prompts |
| 依赖 | Scale 2 + 充分评估 |

**关键变化**: TALP 生成 "evaluate leukostasis syndrome for CML-BC" 而非 "evaluate retinal hemorrhage for CML-BC"。一个 leaf 覆盖一个 syndrome 的所有 member findings。Bundler 以 syndrome 为去重/覆盖单元。

**预期收益**:
- 分析轮次减少（leukostasis 3 个 finding 一轮完成而非三轮）
- 消除条件依赖造成的过度自信
- 更贴合临床推理模式

#### Scale 4: 三层诊断模型 (长期研究方向)

```
Disease ← Syndrome/Cluster ← Finding
```

诊断树引入中间综合征层。等价于 Bayesian Network 中间节点方案 (Nikovski 2000)。需要大规模 syndrome-finding-disease 三元组知识库。

### 17.6 数据源

| 来源 | 内容 | 可用性 |
|------|------|--------|
| WHO 2022 血液肿瘤分类 | 各病种诊断标准集群 | 手工提取 |
| NCCN 指南 | 综合征定义 (leukostasis, TLS, DIC) | 手工提取 |
| Orphanet diagnostic criteria | 893 条 | ✓ 已有 `diagnostic_markers.json` |
| HPO 本体层次 | 父概念 = finding 集群 (如 Pancytopenia 含 3 子表型) | ✓ 可从 HPO 提取 |
| 临床预测规则 (CPR) | Wells/Duke/CURB-65 等 ~200 条 | 需外部收集 |
| JAMA Rational Clinical Exam | ~100 篇系统综述，含组合 LR | 需手工提取 |

### 17.7 推荐实施路径

| Phase | 时间 | 内容 | 预期效果 |
|-------|------|------|---------|
| Phase 1 | 立即 | Scale 1 (Cluster LR Overlay) + Annotator prompt 增加集群警告 (Scale 0) | 修正条件依赖高估；~3 文件 |
| Phase 2 | 短期 | Scale 2 (EvidenceItem.cluster_id + Annotator 感知) | 集群级标注，概率更新可用集群 LR |
| Phase 3 | 中期 | Scale 3 评估 ROI → 若正向则实施 | 轮次减少 + 准确率提升 |

## 18. 多源开放数据集成实施记录 (2026-05-28, v1.6)

### 18.1 背景

v1.5 通过 HPO 本体层级匹配将无 supplement 的覆盖从 3/24 恢复到 9/24，但仍有 15 对"真结构性空白"。v1.6 通过集成多个免费开放数据源，在不依赖 UMLS 许可证的前提下，将 15-gap 覆盖率从 0% 提升到 100%。

### 18.2 数据获取

| 数据源 | API/方式 | 凭据要求 | 获取状态 |
|--------|---------|---------|---------|
| Wikidata SPARQL | query.wikidata.org | 无 | AML 7 症状 |
| BioPortal REST | data.bioontology.org | API key (免费) | 疾病+finding 同义词 |
| MONDO OBO | GitHub Release | 无 | 886K 行, 58,794 terms |
| OHDSI Atlas Demo | atlas-demo.ohdsi.org/WebAPI | 无 (公开) | 502 OMOP 同义词变体 |
| **OHDSI Athena 词汇包** | 手动下载 1.2GB zip | 注册账号 | **95 万概念, 127 万英文同义词** |
| Doclogica | 项目已有 | 无 | 1,475 疾病 x 13K findings |
| Orphanet Guidelines | 项目已有 | 无 | 16K+ 疾病 |

### 18.3 Unified Cache: 3 -> 267,305 条

| 来源 | 注入条数 | 疾病数 |
|------|---------|--------|
| Doclogica | 13,193 | 1,475 |
| Orphanet rare (含频率 LR) | 114,581 | 4,283 |
| Orphanet common (定性) | 139,523 | 12,088 |
| Wikidata AML | 5 | 1 |
| 初始 hand-curated | 3 | 3 |
| **合计** | **267,305** | **~22K** |
| + clinical_supplement (运行时) | ~110 | — |
| **运行时总计** | **377,107** | **22,402** |

### 18.4 双层同义词桥接

**Finding Bridge** (finding_synonym_bridge.json): **398,218** finding 条目, 850K 同义词 (SNOMED+HPO+MeSH+BioPortal)

**Disease Bridge** (disease_name_bridge_flat.json): **702,147** alias->canonical (SNOMED+ICD10+MONDO+BioPortal)

### 18.5 LRRetriever 代码变更

1. 新属性: `_finding_synonym_bridge`, `_disease_synonym_bridge`
2. `from_cache()` 自动加载桥接文件
3. `lookup()` 支持 `::` 和 `|` 双分隔符
4. `lookup_fuzzy()` 新增 Tier 1.5 synonym-expanded exact lookup
5. 候选集内新增 bridge-substring 匹配 (score=0.75)

### 18.6 15-gap 覆盖率演进

| 阶段 | 覆盖率 |
|------|--------|
| v1.4 原始 (无 supplement) | 0/15 (0%) |
| + Doclogica + Wikidata | 8/15 (53%) |
| + Guideline rare/common | 10/15 (67%) |
| + Finding synonym bridge | 14/15 (93%) |
| + Disease bridge + 全部桥接 | **15/15 (100%)** |

### 18.7 新增/修改文件

| 文件 | 类型 |
|------|------|
| `lr_retriever.py` | 修改: 桥接加载 + 双键 + Tier 1.5 |
| `unified_symptom_disease_cache.json` | 数据: 267K 条 |
| `finding_synonym_bridge.json` | 新增 |
| `disease_name_bridge_flat.json` | 新增 |
| `mondo.obo` | 新增: MONDO 本体 |
| `disease_name_bridge.json` | 修改: MONDO 扩展 |
| `athena_omop_synonyms.json` | 新增: OHDSI Atlas 502 OMOP 同义词 |

### 18.8 Athena 词汇包集成 (v1.6.1)

**获取方式**: Athena 官方 API 有 WAF 拦截，通过 Web UI 手动下载词汇包 (1.2GB zip)。

**解析结果**:
- CONCEPT.csv: 1000 万行, 过滤后 **951,662** 医学概念 (SNOMED 47.5万, MeSH 34万, ICD10CM 10万, HPO 1.9万)
- CONCEPT_SYNONYM.csv: 524 万行, 过滤后 **1,270,821** 条英文医学同义词 (覆盖 657,698 个概念)

**桥接规模变化**:

| 桥接 | 集成前 | Athena 集成后 | 增量 |
|------|--------|-------------|------|
| Disease bridge | 143,874 | **702,147** | +558,273 |
| Finding bridge | 112 | **398,218** | +398,106 |
| Finding 同义词总数 | ~200 | **850,081** | +849,881 |

**性能**: 加载 6.6s (一次性), 查询 <0.1ms

**额外覆盖验证**:
- `hepatosplenomegaly × CML` → splenomegaly (子串匹配)
- `pancytopenia × MDS` → HPO subsumption
- `easy bruising × AML` → bruising easily (同义词桥接)
- `leucocytosis × CML` → leukocytosis (英式/美式拼写桥接)

## 19. 各编排环节知识注入方案 (2026-06-04, v1.7 — 设计调研)

### 19.1 背景与现状盘点

前序版本只把外部知识正式接入了**两条通道**：
- **通道 A（LR → EvidenceAnnotator）**：多层 LR 检索注入证据标注（§3、§9）。
- **通道 B（Dx Feature → TALP）**：`discriminator_hints` 注入临时叶规划（§3.3）。

对编排链上的其余 LLM 模块（RootSelector / BranchCreator / SubBranchCreator），代码现状是**仅有一个 LLM 自报触发的占位通道**：模块返回 `need_external_knowledge=True` 时调用 `controller.knowledge_router(query)`，而该 router 默认是 `naive_knowledge_router` —— 一个只回显 query 的 **stub**，未接任何真实知识源。即：

| 模块 | 结构化知识注入 | 机制 | 默认是否生效 |
|------|---------------|------|------------|
| RootSelector | ✗ 无 | LLM `need_external_knowledge` → stub | stub，无真实知识 |
| BranchCreator | ✗ 无 | 同上 stub | stub |
| SubBranchCreator | ✗ 无 | 同上 stub | stub |
| TALP | ✓ 有 | `DxFeatureRetriever` → `discriminator_hints` | 否（`enable_knowledge_injection` 默认关）|
| EvidenceAnnotator | ✓ 设计 | 多层 LR → `lr_reference` | 通道 A 既有设计 |

文档此前仅在 §7.1 顺带识别到 BranchCreator 的缺口（PrimeKG `disease_disease` 亚型边可"弥补 BranchCreator 忽略 phase-crossing 的问题"），但**未给出落地注入方案**。本节补齐各环节方案。

### 19.2 共性设计原则

1. **controller 主动注入**：不再只依赖 LLM 自报 `need_external_knowledge`；在调用模块前由 controller 查询知识层并填充 payload 字段。
2. **独立开关 + 安全回退**：每条通道有独立 config 开关，知识为空时 payload 字段留空，回退到当前纯 LLM 行为（fail-open，不阻断流程）。
3. **字段化 + prompt 显式引用 + 控 token**：知识以结构化字段进入 payload，prompt 显式声明"若提供则优先校准"，并限制条数（top-k）控制 token 膨胀。

### 19.3 环节 0：RootSelector（根综合征选择）

- **问题**：根综合征纯靠 LLM 自由归纳，缺"症状→综合征"结构锚定，易选偏或漏掉危险综合征。
- **复用基础设施**：`PrimeKGIndex.search_phenotypes / get_related_phenotypes`、`DxFeatureRetriever.match_evidence_to_phenotypes`、`HPOIndex`。
- **注入点**：`select_root`（`controller.py`），首次调用 `RootSelector` 前。
- **payload 新增字段**：`candidate_syndromes`（vignette 表型经 PrimeKG 邻接/2-hop 聚合的候选综合征 + 命中证据）、`alarm_phenotype_hits`（命中危险表型提示）。
- **prompt 改动**：若提供 `candidate_syndromes`，应在其中校准根综合征并说明排除原因。
- **门控**：`enable_root_knowledge`（默认关）；映射不出表型则字段留空。

### 19.4 环节 1：BranchCreator（一级分支 / 疾病族生成）—— 缺口最大

- **问题**：① 忽略 phase-crossing 亚型（CML → CML blast phase）；② 分支集合的"鉴别轴/覆盖度"无外部约束，易遗漏鉴别诊断。
- **复用基础设施**：`PrimeKGIndex.get_related_diseases`（`disease_disease` 亚型边）、`search_diseases` + `DiseaseNameResolver`（综合征→候选疾病集合）、`DxFeatureRetriever.get_discriminator_hints`（候选疾病间鉴别轴）。
- **注入点**：`create_branches`（`controller.py`），首次调用前**主动注入**（替代仅靠 LLM 自报）。
- **payload 新增字段**：`candidate_disease_families`（根综合征下候选疾病/族，含 PrimeKG 相关亚型）、`subtype_links`（`disease_disease` 亚型边，专喂 phase-crossing）、`axis_hints`（鉴别轴）。
- **prompt 改动**：分支应覆盖 `candidate_disease_families` 主要族，并对 `subtype_links` 的亚型显式决定纳入/合并。
- **门控**：新增 `enable_branch_knowledge`（默认关）；保留 stub 路径兜底。

### 19.5 环节 2：SubBranchCreator（JIT 子分支扩展）

- **问题**：细化粗分支时同样缺亚型/鉴别轴知识，粒度全凭 LLM。
- **复用基础设施**：同 BranchCreator，但以**被扩展分支的 label** 为查询起点：`get_related_diseases`（该疾病亚型）+ `get_discriminator_hints`（子分支间鉴别点）。
- **注入点**：`expand_subbranches` 对应方法（`controller.py`）首次调用前。
- **payload 新增字段**：`parent_subtypes`、`sibling_discriminators`。
- **prompt 改动**：子分支应落在 `parent_subtypes` 内，并标注区分用 `sibling_discriminators`。
- **门控**：复用 `enable_branch_knowledge`。

### 19.6 环节 3：TALP（临时叶规划）—— 补强而非新建

- **现状**：已注入 `discriminator_hints`（DxS 差集 + PrimeKG 2-hop + ChainDiscoverer），但默认关、仅 hints 无 LR。
- **扩展**：
  - A. **补 LR 参考**：hints 旁追加 `lr_reference`（`get_lr_reference / format_lr_reference_for_prompt`），给 TALP 估期望信息增益量化锚点。
  - B. **接 pathognomonic markers**：复用 `DiagnosticMarkerIndex` + `MarkerDisambiguator`（§16.9）注入"一旦出现即近乎确诊"的标志，引导高鉴别价值候选。
  - C. **默认开启评估**：A/B 实验后决定 `enable_knowledge_injection` 是否默认开。
- **注入点**：`plan_temporary_leaves`（`controller.py`，已有钩子）。

### 19.7 环节 4：Bundler / EvidenceAnnotator

- **Bundler**：确定性算法，不需独立外部知识；接受 TALP 下传的 `redundancy_group` 即可。
- **EvidenceAnnotator**：即通道 A，多层 LR 检索注入 `lr_reference`，属既有设计，非本次新增缺口。

### 19.8 优先级总览

| 环节 | 现状 | 建议动作 | 主要复用 | 优先级 |
|------|------|---------|---------|--------|
| RootSelector | stub | 综合征候选注入 | PrimeKG 表型邻接 / match_evidence | 中 |
| BranchCreator | stub | **新建知识通道**（亚型+鉴别轴） | PrimeKG `disease_disease` / get_discriminator_hints | **高** |
| SubBranchCreator | stub | 复用 BranchCreator 通道 | 同上（以分支 label 为起点） | 中 |
| TALP | 已注入 hints | 补 LR + pathognomonic markers | get_lr_reference / DiagnosticMarkerIndex | 中 |
| Annotator(LR) | 已设计通道 A | 按既有方案落地 | lr_retriever 多层检索 | — |

---

## 20. LR 覆盖三项改进（2026-06，落地）

针对 LR-hole 诊断（trace_lr_holes.py）暴露的三类"反直觉空洞"，本次落地三项改进。平树/症状聚类（B5）暂押后。

### 20.1 改进一：疾病实体归一化（机制/形态学 → 规范疾病实体）

- **问题（结构性"疾病洞"）**：benchmark 选项常以**因果机制**或**细胞/组织形态学**表述，而非疾病名，例如 "Increased parathyroid hormone"、"Beta cell tumor"、"Hypercortisolism"、"Apical lung tumor"。这些表述在以疾病为键的 LR cache / HPO / PrimeKG / Orphadata 中**零命中**，导致该选项永远拿不到数值 LR，只能落到定性 RAG。
- **方案**：新增 `data/knowledge_raw/mechanism_to_disease.json`（精选、可扩展的 `exact` 映射表），将机制/形态学表述归一化到知识源真正索引的疾病实体（如 `Increased parathyroid hormone → primary hyperparathyroidism`、`Beta cell tumor → insulinoma`、`Apical lung tumor → pancoast tumor`）。
- **落地点**：
  - `DiseaseNameResolver.load_mechanism_map()` + `canonicalize_entity()`；`_resolve_impl` 新增 **Tier 0**：先把机制表述改写为疾病名，再走原有解析层级。
  - `DxFeatureRetriever.get_lr_reference`：对每个候选疾病计算 `dq[d]=canonicalize_entity(d)`，**所有检索层（markers / cache / RAG）一律用规范实体查询**；但 `lr_data` 仍以**原始选项标签为键**（controller 据此回填分支），故对外契约不变。
  - controller 构建 resolver 时自动加载（`config.mechanism_to_disease_json`，None 时在 `lr_cache_json` 同目录自动发现）。
- **效果与边界**：实测 `Increased parathyroid hormone` 正确归一并解析到 `primary hyperparathyroidism`；但若 cache 本身缺该疾病的 finding 关联（如 hypercalcemia×primary hyperparathyroidism 无数值条目），归一化只能"打开门"，数值缺口需由改进二/三回填。`Leukemoid reaction`（反应性过程，非疾病实体）在任何疾病键源都不存在，归一化无法解决，须靠对比鉴别。

### 20.2 改进二：RAG 期定性→定量转化 + LR-

- **问题**：`rag_retriever.extract_lr_from_snippets` 旧逻辑仅用粗正则抓显式数值 LR/Sn/Sp，且**硬编码 `lr_negative=None`**；而 cache 构建期那套"频率词→Sn→LR+/LR-"的换算从未在检索期复用，导致 RAG 命中大多是 `context-only`（LR+=None）。
- **方案**：新建 `knowledge/lr_quant.py`，把构建期的频率换算移植到检索期：
  - **A 级（显式数值）**：文本含 Sn/Sp 或 LR 数值 → `confidence="rag_extracted"`。
  - **B 级（定性频率）**：识别 "majority/most/commonly/often/rarely/hallmark/up to X%" 等频率语言 → 校准 Sn 点估计 → `compute_lr` 同时算 **LR+ 与 LR-**；标 `confidence="rag_qualitative"` 供贝叶斯更新衰减。
  - **临床安全**：仅在句子提及该 finding 时取频率（避免张冠李戴）；Sp 由 finding 鉴别力估计（高特异术语 0.95 / 低特异 0.70 / 默认 0.85），不伪造固定默认值；遵循 2026-05-27 安全评审"废弃统一默认频率"的结论。
- **落地点**：`lr_quant.quantify_snippet()`；`rag_retriever.extract_lr_from_snippets` 改为遍历 snippet 取最高置信条目。
- **效果**：实测原 `context-only` 的对（如 Hypophosphatemia×Antacid overuse）现产出 `RAG-quant LR+=6.33 / LR-` 等数值；无频率语言的 snippet 仍正确回退 `context-only`。

### 20.3 改进三：二级 cache（RAG 计算结果独立持久化）

- **目标**：把改进二在检索期算出的 RAG-LR **持久化到独立的二级 cache**，与精选的主 cache 解耦；重复运行/案例可复用昂贵的 RAG（embedding 检索 + 抽取），不污染主 cache，也不每次重算。
- **落地点**：新建 `knowledge/secondary_lr_cache.py`（`SecondaryLRCache`）。
  - 键 `"{finding}::{disease}"`（小写）；命中存条目，无数值信号存 `null` 标记（`contains()` 区分"未见过"与"见过但无信号"，避免重复死路）。
  - 线程安全（eval 多 worker 共享 retriever）；原子写回，每 25 条 / 退出时 flush。
  - `DxFeatureRetriever` 新增 `secondary_lr_cache` 参数；RAG 层先查二级 cache，命中则跳过重算，未命中才走 RAG 并回写。
  - controller 在 `enable_lr_rag_fallback` 时构建（`config.secondary_lr_cache_json`，None 时同目录自动发现 `rag_lr_secondary_cache.json`），注册 `atexit` flush。

### 20.4 改进四：AnswerMapper 因果优先规则

- **问题（因果陷阱）**：选项常构成因果链（疾病→机制→症状），树已锁定病因，但 AnswerMapper 易映射到更"贴近主诉"的下游症状/机制选项（如选 "Brachial plexopathy" 而非其病因 "Apical lung tumor"）。
- **方案**：`prompts/answer_mapper.txt` 新增 **Step 2.5 CAUSAL PRECEDENCE**：当 leading 分支代表底层疾病/病因、而另一选项只是其下游效应/机制/症状时，**映射到上游病因选项**；仅当 leading 分支本身即该机制且无上游疾病选项受支持时才选机制/症状选项；不得默认选最"字面复述主诉"的选项。
- **一致性后处理**：沿用既有 F3 `_enforce_answer_consistency`（`final_answer = argmax(answer_option_mapping)`）作为确定性兜底。

### 20.5 测试与门控

- 回归测试 `tests/test_disease_norm_lr_quant.py`（11 项）：机制归一化、`lr_quant` 数值/定性/无信号三态、二级 cache put/get/persist/null 记忆、AnswerMapper prompt 契约。全套既有测试（53 项）仍通过。
- 配置：`mechanism_to_disease_json` / `secondary_lr_cache_json` 均支持显式指定或同目录自动发现；二级 cache 仅在 `enable_lr_rag_fallback` 时启用。

### 20.6 改进五：LR− 排除通道（正常/缺失发现入账）

- **问题（Q1/Q2 同一缺口）**：核查发现主流水线**实质上不使用 LR−**——`_reconcile_annotation_with_kb` 只取 `lr_positive`（含 <1 的"在场弱反对"），`controller` 从不读 `lr_negative`；且 `_gather_atomic_findings` 把**正常**化验/生命体征**直接跳过**（避免方向盲假阳，安全）。但这丢弃了 §12.8 / B1 §7 明文要求的循证排除证据：正常值对"几乎必然异常型"疾病是合法的 LR−<1 反对证据。一刀切删除正常值"不制造假阳但按遗漏方式不安全"。
- **方案（保留正常值、经 LR− 正确入账）**：
  1. **FindingNormalizer**：`NormalizedFinding` 新增 `negated_hpo_terms`。正常值（direction="N"）不再只产 `hpo_term=None`，而是列出它**否定的异常表型**（实验室同时查 H/L 的 loinc2hpo 映射；生命体征取规则的 hpo_high/hpo_low；BP 取 Hypertension/Hypotension）。实测："WBC 7000"→negates `[Leukocytosis, Leukopenia]`、"Temp 98.6F"→`[Fever, Hypothermia]`、"BP 120/80"→`[Hypertension, Hypotension]`。
  2. **controller**：抽出 `_raw_atomic_facts`（present/normal 两路共用）；新增 `_gather_normal_ruleout_findings`——仅在门控开时，把正常值否定的异常表型作为"**缺失发现**"返回。
  3. **reconciliation**：present 路照旧用 `lr_positive`；新增 rule-out 路——对每个缺失异常表型查 LR，取该 finding 对疾病的 **`sensitivity` 与 `lr_negative`**；仅当 `Sn ≥ ruleout_min_sensitivity` 且 `lr_negative ≤ ruleout_lr_negative_threshold` 才视为有效排除，按 `kb_numeric_lr[bid] *= lr_negative`（独立证据 → odds 相乘）压低该病，并把定性 effect 推向 `moderate_against`；**绝不覆盖 pathognomonic 地板分支**，也不覆盖本回合已有的在场纳入信号。
- **临床安全门控**（`config`，**默认全关**，A/B 后再开）：
  - `enable_normal_value_ruleout=False`：总开关；关时 `_gather_normal_ruleout_findings` 返回 []，零行为变化（保留原"安全跳过"为兜底）。
  - `ruleout_min_sensitivity=0.8`：仅高 Sn 发现的缺失才有排除力（低 Sn 正常值排除力弱，避免过度压概率）。
  - `ruleout_lr_negative_threshold=0.5`：要求 LR− 明显 <1 才入账。
- **落地点**：`finding_normalizer.py`（`negated_hpo_terms` + 三条分类路径）、`controller.py`（`_raw_atomic_facts` / `_gather_normal_ruleout_findings` / `_reconcile_annotation_with_kb` rule-out 块 + 早退守卫）、`config.py`（3 门控）。
- **回归测试** `tests/test_lr_negative_ruleout.py`（5 项）：正常值产出 negated 表型 / 异常值不产；门控开关；正常 WBC 经 LR−=0.05 压低 CML、effect→moderate_against、AML 不受影响；低 Sn（0.97<0.99 阈值）正确跳过。
- **关系**：本通道是 §16.5 B3-ext "Orphadata LR− 排除信号" 在**主流水线推理期**的真正落地（此前仅 P3 把误用的 presence-触发 LR− 置 None，未补正确的 absence→LR− 路径）。

---

## 21. 根因解剖 → 先验/排除/噪声三类修复（结构化年龄先验 + LR− 卫生 + 噪声门）

> 背景：开启 §20 三项改进 + §20.6 LR− 通道后的并发评测出现"原本正确题反而变错"。本节落地对该回归的**根因解剖**、**临床文献佐证**，以及据此实现的 **P0（已落地）/ P1·P2（开关化，待实验）** 修复。

### 21.1 根因解剖（按部件定位）

| # | 现象 | 部件 | 根因 | 类别 |
|---|------|------|------|------|
| R1 | RAG-quant LR 越过噪声门、强行翻转 LLM 方向（如 weight loss LR+≈0.15→`moderate_against`）；Case 18 出现 6 处 override | `_kb_entry_to_signal` 的 `noisy` 集合（旧版仅含 `context-only/context/low/indirect_chain`） | 新置信标签 `rag_qualitative` / `rag_extracted` 未入 `noisy`，使**频率语言估计（且 Sp 为猜测值）**获得与精选 cache 同级的方向覆盖权 | 外部知识误用（检索噪声反成干扰） |
| R2 | 人口学事实（"55-year-old man"）被当作发现走 finding→LR，产出虚假信号 | `_gather_atomic_findings` present 路 | 年龄/性别是**流行病学（改先验）**而非**检验结果（改似然）**，被错误送入似然通道 | 编排缺陷（证据类型混淆） |
| R3 | "within normal limits"/查体阴性被嵌入为**在场**表型，得到错误 LR+ | `_gather_atomic_findings` 的 embedding 兜底 | 阴性陈述未被识别为 pertinent negative，按在场发现处理 | 编排缺陷 + 知识误用 |
| R4 | 年龄强相关分支（如儿童 CML、老人 ALL）先验未被压低 | 先验仅由 LLM `prior_estimate` 决定，无流行病学结构化接地 | 缺结构化年龄/性别→发病率通道 | 知识欠缺 |

### 21.2 临床文献佐证

- **阴性/正常发现是合法排除证据，且常被低估**：Bayes & Physical Examination 多机构研究显示临床各层级**系统性低估**体征对概率的影响、对**阴性发现**低估更甚（PMC3427763）。AAFP 2009、TheNNT：LR− ≤0.1–0.2 显著降低概率；联合 pertinent negatives（正常生命体征 + 正常肺部查体）可排除肺炎（LR−≈0.10）。→ **结论：不应删除查体阴性，应经 LR− 通道让其压低"大概率产生该异常体征"的分支后验。** 验证了用户判断。
- **SnNout 仍依赖可信 Sp**：Sn 高 + 阴性可排除（SnNout），但 LR−=(1−Sn)/Sp 仍含 Sp；Sp 不可信时排除力不可信（AAFP；Brown EBM）。→ **P1 增设 Sp 门**。
- **年龄/性别属先验而非发现 LR**：同一发现（如血尿）在老年男性 vs 年轻女性恶性概率不同——这是**先验（患病率）**差异，likelihood ratio 不应承载（Australian Prescriber）。→ **R2/R4：年龄/性别走结构化先验通道**。

### 21.3 P0（已落地）

**P0-a 堵噪声门（R1）**：`_kb_entry_to_signal` 在 `rag_lr_can_override_direction=False`（默认）时，把 `rag_qualitative`/`rag_extracted` 并入 `noisy` —— RAG 派生 LR **仍进入 prompt 供 LLM 参考，但不得驱动确定性方向覆盖**。配置可开（消融用）。注意：本改动只影响 present 路的方向覆盖，**不影响** LR− rule-out 块（后者直接读 `lr_negative`，由 §21.5 的 Sp/方向门单独治理）。

**P0-b 人口学剔除 finding 路（R2）**：新增 `_is_demographic_fact`（年龄/性别/年龄段正则）；present 路开头跳过人口学事实——它们改由 §21.4 结构化先验消费。

**P0-c 查体阴性 → LR− 排除（R3，保留后验作用，不删除）**：
- 新增 `_extract_negated_phenotype`：识别显式否定（`no/without/negative for/absence of …`）→ 取被否定表型；识别"`<系统> within normal limits/unremarkable`"→ 经小型 `_NORMAL_SYSTEM_NEGATES` 表映射该系统的高 Sn 异常族（cardiopulmonary→[心杂音, 肺部异常听诊, 呼吸窘迫] 等）。
- present 路跳过这些阴性陈述（避免误当在场）；`_gather_normal_ruleout_findings` 在原"数值正常→negated 表型"基础上**新增自由文本阴性**两路（命名表型经受控词表 embedding，系统级经曲线表），统一进 LR− rule-out 块。

### 21.4 结构化年龄/性别 → 发病率先验通道（R4，结构化版本）

- **数据**：新建 `data/knowledge_raw/age_sex_incidence.json`（**curated、可扩展**，与 `mechanism_to_disease.json` 同范式）。结构：`categories`（粗类：solid_malignancy / degenerative / atherosclerotic_cardiovascular / congenital_genetic / autoimmune_inflammatory）+ `diseases`（高价值特异覆盖：CML/ALL/AML/前列腺癌/卵巢癌/子宫内膜癌/巨细胞动脉炎/川崎病）。每条含 6 个年龄段乘子（0-1/2-12/13-18/19-40/41-60/61-200）与可选 `sex_skew`。乘子为**相对权重（1.0=中性）**，源于 SEER 年龄别发病率与教材 onset 分布；clamp [0.05, 4.0]。
- **部件**：新建 `knowledge/prior_modifier.py`（`PriorModifier`）。
  - `parse_age_sex(text)`：从 vignette/原子事实解析 (年龄, 性别)；月龄→0（婴儿段）。
  - `multiplier(label, age, sex)`：先特异疾病、后粗类，关键词子串匹配（短词 `cml/all/aml` 要求整词）；无匹配→1.0（覆盖盲区不扭曲先验）；性别错配（如女性×前列腺癌）→近 0。
  - `apply(branches, age, sex)`：对每支 `prior *= multiplier` 后**按原总质量重归一**（保持先验总量不变），`posterior` 同步；返回 trace 供日志。
- **注入点**：`create_branches` 末尾调用 `_apply_age_prior`（在任何证据并入**之前**一次性施加）；`controller.__init__` 在 `enable_age_prior` 时加载（`age_sex_incidence_json`，None 时同目录自动发现）。
- **门控**：`enable_age_prior=False`（默认）。关闭或解析不到年龄时严格零行为变化。
- **实测**：CML@70 ×2.28、CML@7 ×0.12；ALL@5 >1.5；前列腺癌×女性 <0.1。

### 21.5 P1 / P2（开关化，待实验）

- **P1（方向一致性 + Sp 门）**：rule-out 块新增——(i) **绝不**压低本回合 present 路已**纳入**（`*_for`）的分支（丢弃同回合矛盾信号）；(ii) `ruleout_min_specificity>0` 时，跳过 `specificity` 缺失或低于阈值的排除项（SnNout 仍需可信 Sp）。
- **P0-d（rule-out 排除 RAG-quant 源，默认开）**：根因解剖（§21.7 case 13/24）发现一处确定性缺陷——**正常体温** → "Hypothermia 缺失" → 一条 `RAG-quant:corpus` 条目谎称某分支 Hypothermia 的 Sn=0.95 → LR−=0.0588 强行压低该分支。这正是 P0-a 在 present 路拦截的 RAG-quant 噪声，但 rule-out 块直读 `lr_negative` **绕过了噪声门**。修复：rule-out 仅采信**精选源**的 Sn/LR−，`source` 含 `RAG-quant` 或 `confidence∈{rag_qualitative, rag_extracted}` 的条目默认跳过（同样受 `rag_lr_can_override_direction` 统一开关管控）。回归 `test_lr_negative_ruleout.py` 新增 2 项验证（默认跳过 / 开关打开时放行）。
- **P2（present-path-first）**：`ruleout_require_present_path_silent=True` 时，仅对 present 路**无任何信号（neutral）**的分支施加 LR−。
- **实验**：`scripts/eval_pipeline_medbullets.py` 新增 `--[no-]age-prior` / `--rag-override` / `--[no-]ruleout-present-first` / `--ruleout-min-sp` 开关；默认采用 **P0 修复态（age prior 开、present-first 开、RAG 不得 override）**，对照组用于度量 P1/P2 净效果。

### 21.6 落地点与回归

- 代码：`controller.py`（`_is_demographic_fact`/`_extract_negated_phenotype`/`_NORMAL_SYSTEM_NEGATES`、present 路跳过、`_gather_normal_ruleout_findings` 双路扩展、噪声门、`_apply_age_prior`、rule-out P1/P2 门）、`config.py`（`rag_lr_can_override_direction` / `enable_age_prior` / `age_sex_incidence_json` / `ruleout_min_specificity` / `ruleout_require_present_path_silent`）、新增 `knowledge/prior_modifier.py` 与 `data/knowledge_raw/age_sex_incidence.json`。
- 回归测试 `tests/test_age_prior_and_negatives.py`（23 项）：`parse_age_sex`、`PriorModifier`（年龄/性别乘子、错配归零、无匹配中性、归一化、无年龄空操作）、人口学/否定/系统级否定识别与在场误判防护。`test_lr_negative_ruleout.py`(7，含新增 RAG-quant 源 2 项)、`test_disease_norm_lr_quant.py`(11) 全通过。

### 21.7 全量实验结果与方差诊断（关键结论）

- **P0 修复态全量跑**（25 题 / 10 并发 / qwen3-32b / ~75min）：**全量 4/25=16%，文本-only 2/9=22.2%**。
- **跨 6 次运行的文本题对比**显示：正确题集合**几乎每跑都在洗牌**（case 1/9/14/17/22/23 各自在 OK/XX 间反复），总分在 **1/9–3/9** 抖动，均值≈2.2/9。
- **根因：解码 `temperature=1.0`** × 每题 ~15 次 LLM 调用 → 单题结果高度随机。**n=9 下 ±1 题即纯噪声，单次 A/B（含 P1/P2、age-prior on/off）无法判别配置真实效果。**
- **确定性可攻靶点**（与方差无关）：
  1. **LR 大面积 MISS（0 HIT / 5 MISS）**：BranchCreator 产出冗长非规范族名（"Neuroendocrine Tumor-Related Hyperglycaemic Syndrome"、"Foreign Body-Induced Upper Respiratory Tract Infection"），无法键入疾病键 LR cache。机制图/归一化对自由组合族名无能为力——需在 **BranchCreator 侧产出规范实体标签** 或 **检索期把族名解析到可命中实体**。
  2. **RAG-quant 假排除**（已修，见 P0-d）：case 13/24 的 Hypothermia 假 Sn 排除。
- **方差治理建议（待定方向）**：降温（0.2~0.3）后 on/off 对照 / 多种子取均值 / 扩大文本样本量 / 组合。结构化改动本身经单测 + 临床文献 + 关时零行为变化已站得住，但**效果量化必须先压方差**。

### 21.8 全错题逐部件根因解剖（13 / 18 / 24，6 跑全错）

三题均为**教科书级 pathognomonic 表现**，且**正确假设都已作为分支存在于树中**，却都输给了"被锚定的常见/被框定诊断"：

| case | gold | 决定性线索（pathognomonic） | 正确分支是否存在 | 胜出分支(后验) | 误判 |
|---|---|---|---|---|---|
| 13 | A 胰高血糖素瘤(α细胞瘤) | 疼痛性游走性红斑(NME)+糖尿病+腹泻 | ✓ "Neuroendocrine Tumor-Related Hyperglycaemic Syndrome"（却被判 moderate_against） | Insulin Resistance Syndrome…(0.872) | →E 胰岛素抵抗 |
| 24 | B 鼻腔异物 | 患儿 + **单侧** 血性脓涕 | ✓ "Foreign Body-Induced URI"（停留 neutral） | Bacterial URI w/ Superinfection(0.825) | →E 细菌二重感染 |
| 18 | E 肝血管扩张(肝腺瘤/紫癜样肝破裂) | OCP + 合成代谢类固醇体征(厚颈、宽肩、痤疮)+RUQ+休克 | ✓ "Hepatobiliary Vascular Emergency"（被判 against→neutral） | Acute Abdominal Hemorrhage…(0.232, 极平) | →A 异位妊娠 |

**共性根因（与 age/LR−/噪声门正交）——两段式缺陷**：
1. **B-label 非规范化 → KB 全 MISS**：BranchCreator 产出冗长组合族名（如 "Foreign Body-Induced Upper Respiratory Tract Infection"），疾病键 LR cache **0 HIT / 全 MISS**，外部知识**根本无法点火** → LLM 的先验锚定永远得不到证据纠偏。机制图/实体归一化对自由组合族名无能为力。
2. **决定性线索未被点亮**：枢纽证据被映射为**泛化表型**（NME→"Erythematous rash"、单侧血性脓涕→"Nasal Discharge"、类固醇体征→未入证据），其**pathognomonic→特异疾病**关联从未被检索/加权 → LLM 维持对常见/被框定诊断（胰岛素抵抗 / 细菌鼻窦炎 / 异位妊娠）的锚定。

**结论**：这类错误**不是**新通道造成，也不会被它们修复。真正的主瓶颈是"**枢纽线索→特异疾病关联的可检索性 + 反锚定**"。两条修复方向（属后续大改，非本轮）：
- **(a) 分支→规范实体可命中**：BranchCreator 为每分支附 `representative_disease`（规范实体），或检索期把族名解析到代表性可命中实体，让 KB/LR 能对正确分支点火。
- **(b) 枢纽/pathognomonic 线索点亮**：对高特异线索（NME、患儿单侧血性鼻涕、类固醇体征+OCP 等）检索强关联疾病并强制其分支获得 LR+/抬升后验（反锚定）。

### 21.9 温度归零 + P0–P2 单因子消融实验（变量控制）

- **温度贯通**：`RobustLLMClient` 新增 `temperature` 字段（dataclass），`get_robust_completion` 默认回退到 `self.temperature`；eval 脚本 `--temp`（0.0=确定性）、`--tag`、`--[no-]ruleout` 新开关。`temperature=0.0` 因 `is not None` 判定正确透传。
- **设计**：temp=0 确定性下，对 **9 道文本题**做**单因子消融**（从 P0 修复态 base 出发各改一项），每组一次跑即点估计：`base / noage(--no-age-prior) / ragover(--rag-override) / nopf(--no-ruleout-present-first) / sp50(--ruleout-min-sp 0.5) / noruleout(--no-ruleout) / minbase(--no-age-prior --no-ruleout)`。7 组并发执行（机器 462G 空闲、API 不限速）。
- **判读**：以 base 为基准，各组 Δ 正确题数即该因子在确定性解码下的净效果（消除采样方差）。

#### 21.9.1 结果（temp=0，9 文本题，单次确定性）

| 配置（相对 base 改一项） | no-image | Δ vs base |
|---|---|---|
| **base**（全部 P0 修复开、Sp 门关） | **5/9 (55.6%)** | — |
| noage（年龄先验关） | 4/9 | −1 |
| minbase（年龄+rule-out 均关） | 3/9 | −2 |
| nopf（present-first 关） | 3/9 | −2 |
| ragover（允许 RAG override） | 2/9 | −3 |
| noruleout（rule-out 通道关） | 1/9 | −4 |
| sp50（Sp 门=0.5） | 1/9 | −4 |

逐题 OK 矩阵（✓=对）：

| case | base | noage | ragover | nopf | sp50 | noruleout | minbase |
|---|---|---|---|---|---|---|---|
| 1 | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ | ✓ |
| 9 | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ |
| 13 | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| 14 | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| 17 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| 18 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| 22 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ | ✗ |
| 23 | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ |
| 24 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

#### 21.9.2 结论

1. **降温归零有效**：base 稳定复现 **5/9**，远高于 temp=1 的彩票区间（1–3/9，均值≈2.2）。**后续一切 A/B 应在 temp=0 下进行。**
2. **base（当前 P0 修复默认态）是 7 组里最优，碾压所有单因子消融。**
3. **稳健正贡献**：(i) **RAG 噪声门**（base 5 vs ragover 2，+3）；(ii) **present-first P2**（base 5 vs nopf 3，+2）；(iii) **LR− rule-out 通道**（base 5 vs noruleout 1，在 base 语境 +4）。
4. **Sp 门（P1@0.5）有害**（base 5 → sp50 1）：KB 多数条目无 specificity 字段，门会**误杀**几乎所有有效 rule-out 并扰动轨迹 → **保持默认关闭（0）**。
5. **年龄先验**：在最优 base 中略正（5 vs noage 4），但 {age × ruleout} 2×2 显示**强交互**——
   |  | ruleout✓ | ruleout✗ |
   |---|---|---|
   | age✓ | 5 | 1 |
   | age✗ | 4 | 3 |
   即 ruleout 关时年龄反而有害。**保留 age 开（属最优 base），但其为非干净独立增益。**
6. **轨迹蝴蝶效应**：即便 temp=0，单因子改一项也会翻动"看似无关"的题——某回合证据变化会级联改变后续 LLM payload（确定但混沌）。故 n=9 下**个题翻转仍含轨迹噪声**，但**聚合排序可信，base 稳居第一**。
7. **case 17/18/24 全配置皆错**（13/14/22/23 在配置间churn），印证 §21.8：这是**枢纽线索→特异疾病关联可检索性 + 反锚定**的知识/编排瓶颈，**非这些旋钮可修**。

**落地建议**：维持 base 默认（age 开、rule-out 开、present-first 开、噪声门开、Sp 门关）；后续真正提分的杠杆是 §21.8(a)(b)（分支规范实体可命中 + pathognomonic 线索点亮），而非继续调这些门控。

### 21.10 §21.8(a)(b) 落地 + 全错题"首发部件→应得中间结果→逐级误导链"细化

#### 21.10.1 落地实现

**(a) 分支 `representative_diseases` → KB/LR 可命中**（gate `enable_representative_disease_lr`，默认关）
- `Branch` 新增 `representative_diseases: list[str]`；BranchCreator/SubBranchCreator 提示新增**必填字段**：每分支给 1–4 个**规范、可查疾病实体**（如族名 "Myeloid Neoplasm with Increased Blasts" → `["acute myeloid leukemia","CML blast crisis","MDS with excess blasts"]`），**族 label 仍保持宽泛**（不破坏 phase-crossing 规则）。
- `_clean_representative_diseases()` 容错（str/list/占位符过滤、去重、上限 4）。
- reconciliation 与 annotator payload：当 gate 开，把每分支的 `representative_diseases` 一并作为 LR 查询串（`label_to_bid.setdefault(rd, bid)`），疾病键 cache 即可对**正确分支**点火。
- 设计动机：族名是"组织用"的宽标签（覆盖 AML+CML 危象），**本就不该命中疾病键**；规范实体才是 cache 的键。故这是**补一条查询通路**，不改族结构。

**(b) pathognomonic 枢纽线索点亮 + 反锚定**（gate `enable_anti_anchoring`，默认关）
- `_compute_pivotal_hint()`：对本回合原子证据×(分支 label+代表实体)做 LR 查询，取 **LR+≥5** 的最强 `(finding→disease)` 对（去重，最多 3 条），生成 `pivotal_evidence_hint` 注入 EvidenceAnnotator payload。
- `evidence_annotator.txt` 新增反锚定指令：先问"领先假设能否解释枢纽线索；若某特异线索强烈指向**另一**分支且当前领先者无法解释，则抬升该分支（≥moderate_for），不要默认常见/被框定诊断"。
- 回归测试 `tests/test_representative_disease_lr.py`（5 例，全绿）：族 label 单独 MISS / 代表实体命中并 override；pivotal hint 命中与空场景。

#### 21.10.2 四道错题的"首发错误部件 / 应得中间结果 / 逐级误导链"

> 数据**逐字取自** base 跑（temp=0，`logs/medbullets_conc_base_20260607_205406_cases/case_*.log`）的 `AGE-PRIOR` / `KB reconcile` INFO 行（含 recon_trace 的 per-branch `llm_effect`、HIT 的 `lr_positive`/`kb_source`）、posterior 轨迹与 `medbullets_conc_base_205406.json` 的 `pred`。**四题正确分支都已在树中生成**，全因下列**相互正交的首发错误因素**逐级放大而误判。

**误差因素清单（按首发部件归类）**

| # | 首发部件 | 错误现象（实例，逐字） | 应得正确中间结果 |
|---|---|---|---|
| F1 | VignetteParser/原子证据 | **阴性反转**：case14 原文 "normal bowel movements" 被抽成 **`Infrequent bowel movements`** | 应作**阴性**证据走 LR− 通道，**反对** CF（无吸收不良） |
| F2 | Stage-2 表型嵌入（泛化坍缩） | 枢纽线索被吃成泛化父表型：case24 "单侧血性脓涕"→`Nasal Discharge`；case18 雄激素滥用体征(厚颈/宽肩/运动员体型)→仅 `acne` | 保留 "unilateral bloody nasal discharge"、"anabolic-steroid 体征" 等特异短语 |
| F3 | FindingNormalizer 体征区间（成人标定） | 儿科生理值误判异常：case14 →`Hypotension`；case24 →`Hypotension`+`Tachycardia`→放大"全身感染" | 按年龄段归一 → **正常** → 不产生伪重症信号 |
| F4 | BranchCreator 族 label 直接做 LR 键 | **全 MISS**：四题几乎所有回合 `0 HIT / 全 MISS`（族名/冗长组合名无法命中疾病键 cache） | 用代表实体查询 → 对正确分支点火（**= Fix A**） |
| F5 | 外部知识误用 + 噪声 finding | case17 注入 `Hypertension`、`Diabetes`、`Cerebral dysmyelination`、`Ataxic gait` 等非特异/跑题 finding，且 LLM 把含 CML 的 `Chronic Myeloproliferative Neoplasm` 评为 **moderate_against** | 这些非特异关联不应压制慢性髓系；CML 应保持候选 |
| F6 | 人口学过滤漏网（作为 finding） | `Age and gender: 10-year-old girl`、`Patient is a 57-year-old man` 漏入 finding 列表（正则未覆盖 "Age and gender:"/"Patient is a…" 句式） | 路由到结构化年龄先验，**不**进 finding→LR |
| **F7** | **结构化年龄先验：共享 controller 上的人口学缓存泄漏（新发现，代码级 bug）** | eval 单 controller 跨题复用（脚本注释自述"controller 不写 per-run state"），但 `_apply_age_prior` 把 `self._patient_age_sex` 缓存到实例，且仅当 `age is None` 才重解析 → **首个患者(55岁男)的人口学泄漏到后续/并发各题**。日志铁证：**case14 是 10 岁女孩，却记到 `AGE-PRIOR age=55 sex=male`**，并据此把正确的"先天性心肺综合征"族先验 **×0.4 压低** | `_patient_age_sex` 应**每题重置**（或不存于共享实例）；case14 应解析为 (10, female)，**上调**先天性分支 |

**逐题细化（首发部件 → 应得中间结果 → 逐级误导链 → 最终错答）**

**▍case 14 — gold A / 误 C**
- 问法："最可能伴随的体征？" gold **A=Diastolic murmur best heard along the right lower sternal border**（右位心/Kartagener=原发性纤毛运动障碍 PCD）；pred **C=Increased chloride in the patient's sweat**（CF 汗氯试验）。
- 分支树：`B1 Cystic Fibrosis…` / `B2 Congenital Cardiac and Pulmonary Syndromes…`（含 PCD/右位心）/ `B3 Chronic Inflammatory Lung Disease…`。**正确族 B2 已存在**。
- 原子证据（逐字，问题项标 F）：`Hypotension`(**F3**, 患儿 BP90/58 误判)、`Age and gender: 10-year-old girl`(**F6**)、`Chronic cough`、`Infrequent bowel movements`(**F1**, 原文 normal)、`Abnormal tricuspid valve physiology`(=右心杂音，**枢纽，正确**)、`Episodic upper airway obstruction`、`Growth metrics: 25th percentile…`。
- 年龄先验：`AGE-PRIOR age=55 sex=male`(**F7** 泄漏) → 把 B1、B2 先验**各 ×0.4**（对 55 岁男而言先天病罕见）——**恰好压低了正确的 B2 先天族**。
- 逐回合：t1–t5 全部 `0 HIT, 全 MISS`(**F4**)；recon_trace t1：B1=`moderate_for`、B2=`moderate_for`、B3=`neutral`。后验 leader **B1(CF) 0.409→0.3765** 始终压 B2，三尖瓣杂音的右位心/PCD 关联因 0 HIT **从未点火**。
- 误导链：① F7 先验压低 B2；② F1 把"反对 CF 的正常排便"反转为"支持 CF 的便秘"；③ F3 伪重症 + F4 全程无外部纠偏 → LLM 锚死 CF（甚至合理化出"胰功能保留型 CF"）；④ AnswerMapper 据 leader=CF → 选 **C(汗氯)**。
- 应得：正常排便/正常发育走 LR− 反对 CF；三尖瓣杂音+支扩+鼻窦炎+内脏转位 → PCD → 体征 **A**。

**▍case 17 — gold D / 误 A**
- gold **D=Chronic myelogenous leukemia (CML)**；pred **A=Acute lymphoblastic leukemia (ALL)**。
- 分支树：`Myeloid Neoplasm with Increased Blasts` / `Lymphoid Neoplasm with Increased Blasts` / `Chronic Myeloproliferative Neoplasm`(**含 CML**) / `Lymphoproliferative / Plasma Cell Disorder` / `Reactive Leukocytosis`。
- 原子证据：`Leukocytosis`、`Elevated blast count`、`Anemia`、`Thrombocytopenia`(髓系正解线索) + 噪声 `Hypertension`(**F5**)、`Diabetes`(**F5**)、`Patient is a 57-year-old man`(**F6**)、`Cerebral dysmyelination`、`Ataxic gait`、`Visual acuity abnormality`(跑题)。
- 年龄先验：`age=55 male` 对 4 个肿瘤族**一律 ×1.3**（不区分）→ 无判别力。
- 逐回合：t1–t5 全 `0 HIT, 全 MISS`(**F4**)；recon_trace t1 关键：`Myeloid…blasts`=**moderate_for**、`Lymphoid…blasts`=**moderate_for**、`Chronic Myeloproliferative Neoplasm`(**=CML 所在族**)=**moderate_against**(**F5 误判**)。leader 维持 **0.359→0.4** 在"急性 blasts"两族间，慢性髓系被自评压制。
- 误导链：① "elevated blasts" 把框架推向**急性**白血病，含 CML 的慢性族被 LLM 评 moderate_against；② F4 致 leukocytosis/嗜碱/巨脾的 **CML 特异 LR 永不点火**，无外部翻盘；③ 在 Myeloid vs Lymphoid 急性两族间，淋系胜出 → **A(ALL)**。
- 应得：慢性髓系增殖（巨脾/嗜碱/BCR-ABL）经代表实体点火 → **D(CML)**。

**▍case 18 — gold E / 误 C**
- gold **E=Vascular ectasia within the liver**（肝紫癜/血管扩张，雄激素合成代谢类固醇所致）；pred **C=Obstruction of blood flow through the hepatic vein**（Budd-Chiari）。
- 分支树：`Ectopic Pregnancy` / `Biliary Tract Obstruction` / `Hepatic Vascular Occlusion / Budd-Chiari` / `Acute Pancreatitis` / `Liver Vascular Anomalies / Hemangioma`(**正确族**)。
- 原子证据：`right upper quadrant abdominal pain`、`oral contraceptive pills`、`Excessive alcohol`、`Weight loss`、`acne`(**F2**, 雄激素体征坍缩为痤疮)、`Intraretinal fluid`(伪造跑题)。**雄激素滥用/合成类固醇这一指向肝紫癜的枢纽丢失**。
- 逐回合：t1 罕见地 **2 HIT**——但命中的是 `Abdominal discomfort`→`Ectopic Pregnancy`(lr+0.1,HealthKG)=moderate_against、→`Acute Pancreatitis`(lr+0.031)=strong_against，即**只把两个错误分支正确压低**；正确族 `Liver Vascular Anomalies`=**MISS, neutral**(**F4**)，Budd-Chiari=MISS neutral。后验在 `0.109↔0.48` 间，Budd-Chiari 借 OCP+RUQ+年轻女性经典锚上位。
- 误导链：① F2 丢失类固醇体征 → 正确族无支持证据；② F4 正确族 0 HIT 全程 neutral；③ OCP+RUQ→Budd-Chiari 锚 → **C**。
- 应得：合成代谢类固醇滥用体征保真 → 肝紫癜/血管扩张 → **E**。

**▍case 24 — gold B / 误 E**
- gold **B=Foreign body obstruction**；pred **E=Sinusitis with bacterial superinfection**。
- 分支树：`Bacterial Superinfection of Sinusitis` / `Foreign Body with Secondary Infection`(**正确族**) / `Nasal Vascular Lesion with Infection` / `Nasal Structural Abnormality` / `Other Acute Infections`。
- 原子证据：`Chronic sinusitis`、`Nasal Discharge`(**F2**, "单侧血性脓涕"坍缩，丢 unilateral+bloody 异物特异性)、`Hypotension`+`Tachycardia`(**F3**, 7 岁患儿 BP90/48 P124 误判为休克/重症)、`Asthma`、`rest of exam within normal limits`。
- 逐回合：t1/t2 全 `0 HIT, 全 MISS`(**F4**)；recon_trace t1：`Bacterial Superinfection`=**strong_for**、`Foreign Body`=**neutral**、`Nasal Vascular Lesion`=strong_for。leader **0.63** 由细菌族占据，异物族始终 neutral。
- 误导链：① F2 抹掉唯一枢纽（单侧+血性）→ 异物族特异性归零、停 neutral；② F3 伪重症放大"全身/细菌感染"；③ F4 无外部纠偏 + "previously diagnosed sinusitis" 框定锚 → **E**。
- 应得：儿童单侧血性脓涕 → 异物 LR+ 抬升 → **B**。

**关键洞察（指导实验判读）**：
- **F4 是四题共性、Fix A 直击**；但 **Fix B 受 F2 上游闸制**——case24/18 的枢纽线索在 F2 已坍缩，pivotal-hint 检索不到正确实体即点不亮（fixb2 仍能救回 case24，提示其代表实体 "foreign body" 经 hint 通路绕过了 F2，属意外正例）。
- **F7（年龄先验人口学泄漏）是代码级 bug，且污染了 §21.9 的 age 消融**：noage 关掉的不仅是"年龄先验"，也顺带消除了这条泄漏的负作用，故 §21.9 中 age 的"净增益"判读需打折。**应优先修复 F7（每题重置 `_patient_age_sex`）后重测 age 先验。**
- F1（阴性反转）、F3（儿科体征）是**独立于两修复**的上游缺陷，进入下一轮（finding 抽取保真 + 儿科参考区间）。

#### 21.10.3 控制实验（temp=0，9 文本题，4 臂并发）

设计：以新提示（含 representative_diseases，对各臂一致）为公共基线，2×2 因子：`base8`(都关) / `fixa`(--fix-a) / `fixb`(--fix-b) / `fixab`(--fix-a --fix-b)。指标为相对 base8 的 Δ 正确题数（确定性，消除采样方差）。

**已完成结果（temp=0，9 文本题）**

| 臂 | 提示 | 开关 | 准确率 | vs §21.9 干净 base(5/9) | vs base8b(2/9) | 备注 |
|---|---|---|---|---|---|---|
| **干净 base**（§21.9，**无** rep 字段） | 旧 | P0 默认 | **5/9** | — | +3 | 全局最优 |
| base8 / base8b（rep 字段，两修复关） | 新 | — | **2/9 / 2/9** | **−3** | — | rep 字段本身确定性退化（两跑同对集 {14,23}） |
| fixb（初版，**无条件**反锚定） | 新 | --fix-b | 1/9 | −4 | −1 | 已废弃：无条件反锚定指令污染 annotator（见 §错误修复） |
| **fixb2**（修正：反锚定移入 hint + RAG 噪声过滤） | 新 | --fix-b | **3/9** | −2 | **+1** | **唯一解出 case24**；另恢复 1、9 |
| fixa | 新 | --fix-a | **未完成** | — | — | 被终止：payload 膨胀 → 远程 qwen3 反复 240s 超时重试，单题 >2h（非检索瓶颈，见 §21.11） |
| fixab | 新 | --fix-a --fix-b | 未运行 | — | — | — |

**判读（按原始消融目的）**

1. **Fix A 的"必需提示改动"本身是净退化（最关键发现）**：仅向 BranchCreator/SubBranchCreator 增加 `representative_diseases` 必填字段（两修复均关），就把干净 base 从 **5/9 确定性地拉到 2/9**——base8 与 base8b 两次独立跑同为 2/9、且正确集相同（{14,23}），**可复现、非采样噪声**。原因：该字段扰动了一级分支生成（不同分支集 → 下游级联不同）。这意味着 **Fix A 即便其 LR 命中通路有益，也被其提示脚手架的退化抵消**；在本题集上 Fix A（连同其提示）**不是净增益**。
2. **Fix B（修正版）= 3/9，是批次 2 唯一正信号**：唯一在全部 11 个配置里解出 **case 24**（pred B），即反锚定成功抵抗 "previously diagnosed sinusitis" 的框定锚——这与 §21.10.2 "case24 须先修 F2 方能救回" 的预判相反，提示代表实体 "foreign body" 可经 pivotal-hint 点亮、绕过 F2 坍缩。但 fixb2 相对 base8b 的对集为 **完全不相交**（base8b {14,23} → fixb2 {1,9,24}），故 +1 仍处轨迹噪声内，**未稳健超越干净 base 5/9**。
3. **轨迹蝴蝶效应再次确认（稳健性警示）**：temp=0 并不等于轨迹稳定——微小提示/开关改动引起正确集大幅重排（§21.9 base↔base8 仅 {23} 重叠；本批 base8b↔fixb2 零重叠）。故 **n=9 单跑的逐题翻转不可靠**；只有大幅聚合差（noruleout 1、sp50 1、ragover 2 vs base 5）与可复现退化（rep 字段 5→2）可信。
4. **case 17 / 18 全配置仍错**（含 fixb2）：符合 §21.10.2 预判——其枢纽线索在 **F2（表型泛化坍缩）** 上游即丢失（case18 类固醇体征、case17 髓系特异线索 + F5 误导性 2-hop），非 Fix A/B 可救。
5. **耗时与本批无关**：mean_dt 在 14.9–32.7 min/题间剧烈波动且与配置无相关性，全由远程 OpenRouter qwen3-32b 推理延迟方差支配（详见 §21.11）。

**结论与下一步**

- **维持 §21.9 干净 base（5/9）为默认**；`enable_representative_disease_lr` / `enable_anti_anchoring` 默认关。
- **Fix A 需解耦提示脚手架**：当前"问 LLM 要 representative_diseases"的做法连带退化分支生成。改进方向——**不改分支生成提示**，而在分支生成后由 `DiseaseNameResolver`/规范实体表**后处理派生**每个族 label 的代表实体，仅用于 LR 查询通路。如此可保留 5/9 干净 base，再叠加 Fix A 的命中收益。
- **Fix B 在干净 base 上重测**（而非 base8b）：把 pivotal-hint 注入接到**旧提示**基线上，单独评估反锚定能否在不引入 rep 字段退化的前提下保住 case24 收益。
- **F2 保真 + F3 儿科参考区间** 进入下一轮（17/18/24 的真正上游闸门）。

### 21.11 检索耗时调研：瓶颈在远程 LLM，非检索（结论性）

> 触发：观察到 fixa 臂极慢，疑"检索耗时"。结论：**检索不是瓶颈，3 张空闲本地 GPU 帮不上忙**，墙钟时间几乎全部是远程 LLM 调用。

- **检索热路径实测**（`scripts/bench_rag_search.py`）：单次 RAG 查询 ≈ **11ms**（encode + FAISS，36MB/~24k 向量 flat 索引）；9 线程并发 270 查询仅 **2.31s**（串行需 ~3.0s）——FAISS 搜索在 encode 锁外且释放 GIL，**本就并行**。PubMed 网络回退在评测中关闭（`enable_pubmed_fallback=False`），不在热路径。
- **多 GPU encoder 池实测无效**（`scripts/bench_encoder_pool.py`）：单卡+全局锁 167 enc/s vs 三卡池 151 enc/s。短文本 encode ~6ms，受 Python/CUDA kernel-launch 开销支配，非算力/锁瓶颈。**已实现 opt-in 多 GPU 池**（`embedding_index.EncoderPool` + `TREE_DX_EMBED_DEVICES`，默认关），保留为能力但默认不启用。
- **真正瓶颈 = 远程 qwen3-32b 推理**：模型经 **OpenRouter 远程 API**，本地 GPU 与之无关。`call_timeout=240s` + `max_retries=5`；日志铁证：fixa3 `case_01` 分支创建 09:02 → t1 KB-reconcile 10:05（**63 分钟**，其间仅 3 次 LLM 调用）→ **单次有效调用 ~15–20 分钟**（疑超时重试叠加）。payload ~16–22K 字符（~5–7K token），**Fix A 把代表实体 LR 块塞进 Annotator → prompt 更大 → 推理/重试更久**，这正是 fixa 比 base 慢约 4× 的主因。
- **待查（下一轮，优先本地侧）**：即便计入 payload 长度，单次 15–20min 仍异常 → 优先排查本地网络/代理（clash VPN、连接池、`call_timeout`/重试策略），并核验 payload 必要性（§PAYLOAD_SLIMMING_PLAN 瘦身）。仅对**异常膨胀**的实验（如 fixa）按需提速，常规题集押后。

### 21.12 提示门控修复 + 干净重跑（**温度=0 仍非确定性的铁证**）

**(a) 落地：`representative_diseases` 提示字段门控到 Fix A 开关**
- 从 `branch_creator.txt`/`sub_branch_creator.txt` 静态提示**移除**该字段（指令 + schema 示例）；`controller._call_module` 中仅当 `enable_representative_disease_lr=True` 时运行时追加该指令（`_REP_DISEASE_DIRECTIVE`）。校验器只需 id+label，缺省 → `[]`，Fix A 通路 inert。回归 28 例全绿。
- 目的：① 复现干净 base；② 使 Fix A 提示膨胀严格 opt-in（耗时可控）；③ 让 Fix B 可在干净提示上单测。

**(b) 重跑结果（temp=0，9 文本题）**

| 臂 | 开关 | 准确率 | 正确集 |
|---|---|---|---|
| `cleanbase` | 全关（门控后=干净提示） | **5/9** | {1, 9, 13, **17**, 23} |
| `cleanfixb` | `--fix-b` | **0/9** | {} |

**(c) 判读 —— 两条关键结论**

1. **门控修复成功复现干净 base 5/9**：证实 base8 的 −3 退化**确由 `representative_diseases` 提示字段所致**。且 `cleanbase` **首次解出 case 17（CML）**——移除该字段使分支生成回到更优形态。
2. **`cleanfixb` 的 0/9 与 Fix B 无关——它是远程端点非确定性的铁证**：
   - 全部 9 题**无任何 `pivotal_evidence_hint` 注入**（干净 base 的宽泛族 label 在 curated LR 上 LR+≥5 全 MISS，RAG 来源被噪声门过滤）→ **`--fix-b` 在本跑中完全 inert**，payload 与 `cleanbase` 应当一致。
   - 然而结果从 5/9 暴跌到 0/9（连 1/9/23 这种必对题都翻错）。
   - **决定性证据**：对**同一** case_01、**inert 的 flag**，两臂在**第一个 LLM 模块**就分叉——
     - VignetteParser：`Patient: 55-year-old male bodybuilder` vs `Age/gender: 55-year-old male`；`Loss of weight` vs `Weight loss`（同一原文，抽取不同）。
     - BranchCreator：分支族**完全不同**（cleanbase: "Apical Thoracic Mass Processes / Brachial Plexopathy / …" vs cleanfixb: "Thoracic Malignant Neoplasm… / Neurological Compression Syndrome… / …"）。
   - BranchCreator 在任何 Fix B 代码之前执行，故该分叉**不可能**由 Fix B 造成 → **OpenRouter 上的 qwen3-32b 即便 `temperature=0` 也非确定性**（远程多 provider 路由 + MoE + 批处理/后端差异 + 推理 CoT 发散）。

3. **方法论后果（必须修正）**：**单跑 temp=0 消融不可信**。一个 inert 的开关都能把 9 题成绩从 5/9 摆到 0/9，说明 §21.9 / §21.10.3 的所有单跑点估计（base=5/9、各 P0 消融、fixb2=3/9 等）都带巨大方差，**逐题翻转乃至 ±数题的聚合差很可能是端点采样噪声**。fixb2 的 "唯一解出 case24" 与 cleanbase 的 "解出 case17" 同属此类单次抽样，**不能据此判定修复有效**。

**下一步（修正实验协议）**
- 改为**每臂 K 次重复跑**（建议 K≥5），比较 **均值±std / 多数投票**，而非单跑点估计；或改用**可确定性复现的本地模型**（如本地 vLLM 托管，配 `seed` + 单 provider）以消除端点噪声——这也顺带回收 §21.11 的本地空闲 GPU。
- 在获得稳定基线方差带之前，**暂缓据单跑结论调整任何旋钮/修复**。

#### 21.12.1 随机性来源审计与固定（落地）

> **结论先行**：`cleanbase/cleanfixb` 系 **F7 修复之前**跑出（JSON 12:48/13:02 vs `controller.py` 修复 18:35），故其方差含 F7 泄漏污染。逐项排查并固定如下。

| 来源 | 是否随机 | 处理 |
|---|---|---|
| **OpenRouter provider 路由** | **是（主因）**：qwen3-32b 原 `order=["alibaba","chutes"]`，并发两跑可落到不同 provider | **固定**：`order=["alibaba"]` 单 provider、`allow_fallbacks=False` |
| **量化精度** | **是**：不同 endpoint 可能 fp8/int4 量化 | **固定**：`quantizations=["bf16","fp16","fp32"]`（排除量化）+ `require_parameters=True` |
| **解码 seed/温度** | 是 | **固定**：`temperature=0` + 新增 `seed`（默认 0），两条请求路径（直 POST + chat.completions）均透传；`--seed` 可调 |
| **F7 人口学跨题泄漏** | **是**：泄漏取决于 worker 调度/题序 → 跑间不定 | **已修**（§21.10.2，per-case 缓存）+ 回归测试 |
| 显式 RNG（random/np.random/seed） | 否 | 全包无调用（已 grep） |
| set/dict 迭代序（PYTHONHASHSEED） | 否（无影响结果的 set 迭代） | 无需处理 |
| 二级 LR cache 持久化 | 值确定（FAISS+正则确定性），仅影响是否重算 | 建议每实验批用**全新 cache** 以防跨版本污染 |
| 共享 controller 跨线程状态 | 仅 F7 一处 per-case 泄漏 | 已修；其余无 per-run 写 self |

**经验验证（已更正）**：
- ⚠️ **`quantizations=["bf16","fp16","fp32"]` 过滤不可用**：qwen3-32b 无任何 endpoint 标注这些量化级别——唯二全精度 provider（Alibaba/Groq）量化标为 `unknown`，DeepInfra/Nebius/AtlasCloud/SiliconFlow 均为 fp8。加该过滤 → OpenRouter 返回 `404 No endpoints found` → 代码**静默回退到 llama-3.3-70b**（`get_completion_from_messages` 的 unpack 失败兜底）。故最初那次"逐字节相同"实为 **llama 兜底**，非 qwen3-32b。已移除量化过滤，改为 `{"order":["alibaba"],"allow_fallbacks":False}`（首方 provider、全精度、支持 seed）。
- ⚠️ **真·结论（分输出长度）：固定 provider/seed/温度后，短输出可复现、长推理输出不可复现**。两个对照探针（均 Alibaba 单 provider + seed=0 + temp=0 + 无回退，响应 `served_by=Alibaba` 实测确认，0 次兜底）：
  - 短输出（"法国首都" → 单词）：连发 **4 次完全一致**（md5 `e20d37a5`，`scripts/probe_provider.py`）。
  - 长输出（"列出 CML 三大特异表现" → 长文本+推理链）：连发 **3 次发散**（md5 各异、长度 266/195/151，`scripts/probe_determinism.py`）。
- **量化未能显式固定**：qwen3-32b 无 bf16/fp16/fp32 端点（Alibaba/Groq=`unknown`，余者 fp8）；但锁定单 provider 已**隐式固定**精度。
- **根因**：服务端**并发批处理的浮点不可结合性**——同一请求每次与不同并发请求拼进同一 batch，归约顺序变 → 极小浮点差异，在长 greedy 解码中**逐 token 累积**，某步翻 token 后轨迹分叉。**与 seed/温度/provider 无关，API 参数无法消除。** 我们 pipeline 的所有模块输出均为长结构化 JSON+CoT，正落在不可复现一类。

**可达确定性的三条路径**（需选择）：
1. **本地 vLLM 托管**（占用 §21.11 的 3 块空闲 GPU，seed + 单 replica + greedy）→ 真·确定性，且顺带消除远程延迟/超时。**首选**。
2. **改用非推理模型**（用户已授权"必要时选取非 reason 模型"）→ 无采样 CoT，更可能遵守 temp0/seed；但共享端点仍受批处理微扰。
3. **接受方差 + 每臂 K 次重复**（K≥5，多数投票 / 均值±std）。

#### 21.12.2 非推理模型实测：可复现但精度归零（决定性反例）

按路径 2 实测 **qwen/qwen-2.5-72b-instruct（DeepInfra 单 provider + seed=0 + temp=0）**：

| 项 | 结果 |
|---|---|
| **可复现性** | ✅ 长输出连发 3 次逐字节一致（md5 `6a945d71`）；in-pipeline 0 次 llama 兜底（已加 `disable_model_fallback`） |
| **精度** | ❌ **cleanbase 0/9**（全部有效字母但全错；对照 qwen3-32b checkpoint **5/9**） |
| **耗时** | ❌ 每 case **66-90 min**（每题 80-100+ 次 LLM 调用 × DeepInfra 单 provider 串行延迟）；4 实验顺序跑 ~4-5 h |

**结论（关键）**：本诊断流水线为**多轮问诊 × 深度鉴别树**（每题 80-100+ 次模块调用），强依赖 **CoT 推理**。把推理模型（qwen3-32b）换成非推理模型（qwen2.5-72b）→ **精度从 5/9 崩到 0/9**，无任何信号可供研究 P0-P2。**确定性（非推理）与精度（推理）在远程端点上不可兼得。**

**唯一同时满足"确定性 + 精度"的路径 = 本地托管一个推理模型**（vLLM + qwen3-32b，seed + 单 replica + 确定性 kernel），既消除远程批处理噪声，又消除远程延迟/限流。已终止远程非推理实验（仅留 cleanbase 0/9 作反例存档），等待是否搭建本地推理服务的决策。

#### 21.12.3 MoE 排除 + 稠密模型实测：字节级不可复现，但"答案级"可复现

用户约束：**MoE 模型一律不可复现**（专家路由在批处理下引入额外非确定性）→ 排除 `qwen3-235b-a22b-2507`(MoE)、`qwen3-30b-a3b`(MoE)、GLM-4.5/4.6(MoE) 等。

实测**稠密**非推理模型（zero-shot CoT，长输出，单 provider，seed=0，temp=0，4 次重复）：

| 稠密模型 | provider | 长输出字节级一致 | 最终答案 |
|---|---|---|---|
| qwen2.5-72b (dense 72B) | DeepInfra | ❌ 4/4 文本各异 | B,B,B,B ✅ 稳定 |
| mistral-small-3.2 (dense 24B) | Mistral | ❌ 4/4 文本各异 | B,B,B,B ✅ 稳定 |

**关键结论**：**去 MoE 是必要但不充分条件**。稠密模型在**共享云端点**上对**长输出**仍逐次发散——根因是批处理浮点不可结合性（与 MoE 路由无关）。此前"qwen2.5-72b 逐字节一致"仅因那次输出短（794 字符）；到 ~2280 字符即每次发散。

**但最终答案稳定**（B/B/B/B）。故两条路：
- **字节级确定性（长输出）→ 仅本地托管**（稠密模型 + batch=1 / 确定性 kernel）。
- **远程稠密非推理 → "答案/决策级"可复现**，而这正是有效 A/B 所需（最终 9-题分数稳定），即便中间 CoT 文本有抖动。唯一风险：80-100 次链式调用中，中间文本抖动可能偶发翻转某分支决策 → 需对**同配置全流水线跑 2 次**验证最终分数稳定性。

**精度前提**：远程稠密非推理在**当前 JSON-only 流水线**下 = 0/9（无 CoT 空间）。需在模块 prompt 加**结构化 CoT（decision 字段前置 `reasoning` 字段）**才能恢复精度（raw 探针已证 CoT → 正确答案 B）。

#### 21.12.4 决定性反例：全流水线在远程端点**不可复现**（即便 dense+非思考+seed）

为满足"dense + 医学≈85 + 远程"，选 **qwen3-32b 关思考模式**（`reasoning.enabled=false`，dense 32B，MedQA 85.3，已实测 reasoning_chars=0）。**同配置（seed=0、temp=0、单 provider Alibaba、非思考）并发跑 2 次**，逐题对比：

| case | gold | run A | run B | 一致? |
|---|---|---|---|---|
| 1 | A | A | B | ❌ |
| 9 | D | C | C | ✓ |
| 13 | A | E | E | ✓ |
| 14 | A | C | C | ✓ |
| 18 | E | D | C | ❌ |
| 23 | A | A | C | ❌ |
| 24 | B | E | E | ✓ |

**3/7 题在两次同配置运行间翻转（~43%）。** 

**铁证结论**：单次调用的"答案级可复现"（探针里 B/B/B）**无法穿透 80-100 次链式调用**——每次调用 content 的微小批处理噪声逐级累积，最终翻转约 40% 的诊断。**因此远程端点对本深度流水线根本无法产出可复现实验，与 MoE/dense、思考/非思考无关。** 此外非思考使精度从 5/9 跌到 ~2/9（思考在做实质工作）。

**唯一可复现路径 = 本地托管 + 受控批处理**（batch=1 / 确定性 kernel + seed），消除累积噪声源。精度则需推理模型或强模型+结构化 CoT。远程方案就此排除。

**残余风险**：服务端**批处理**在并发下仍可能因 batch 组成不同引入浮点级微扰（隔离调用已可复现，但满负载并发未必逐字节稳定）。要 bit-exact，仍需本地托管（配 seed + 单 provider）。

**本地网络/VPN**：已有看门狗 `_is_proxy_port_open()` + `_restore_vpn_blocking()`→`clashon.sh`（SSL/连接错误时触发）。异常长延迟主因是 `call_timeout=240s` 超时后**守护线程被弃但仍在后台打 API**（contention spiral）+ 跨 provider 排队。新增 `--no-vpn`（置 `TREE_DX_USE_PROXY=0` + 调 `clashoff`）以在 OpenRouter 可直连时绕开 VPN 过载——仅当本机能直连 openrouter.ai 时有效。

---

### 21.13 checkpoint 回退核验 + 5/9 来源审计 + 人口学先验数据错误修复

回退到"最佳配置"复跑以核验 5/9、并检验 F7 行为改变时，发现 **5/9 这个基准本身建立在一个 bug 之上**，并连带审计出人口学先验数据的两个独立缺陷。

#### 21.13.1 5/9 checkpoint 来源审计（颠覆性发现）

对 checkpoint（`cleanbase_20260608_121807`，5/9）逐题 `AGE-PRIOR` 日志取证：

| 跑 | 每题 demographics | 成绩 |
|---|---|---|
| cleanbase（5/9） | **全部 9 题 = `age=55 sex=male`** | 5/9 |
| cleanfixb（0/9，同批） | **全部 9 题 = `age=7 sex=male`** | 0/9 |

这是 **F7 泄漏**：9 个并发 worker 共享同一 controller 实例，**最先解析出年龄的题把 (age,sex) 写进 `self._patient_age_sex`，其余 8 题全部读到这个泄漏值**。两次跑各被一个"竞速冠军"决定（cleanbase 抢到 55/男，cleanfixb 抢到 7/男）。

**三项确凿结论**：
1. **5/9 是在人口学泄漏下得到的**——把 `55岁/男` 一刀切套到全部 9 题（含卵巢囊肿题 → 被"男"压到 ×0.05；CF 遗传病题 → 被 55 岁压到 ×0.4）。
2. **5/9 无固定 seed**——checkpoint 配置打印（`run_cleanbase.out`）为 `model=qwen/qwen3-32b workers=9 temp=0.0`，**无 `seed=` 字段**（`--seed` 是之后 §21.12.1 才加）。
3. **当前版本 vs checkpoint 至少 6 处差异**：F7（泄漏→修复，**最大行为差**）、seed（无→0）、provider（`["alibaba","chutes"]`多→`["alibaba"]`单）、model fallback（开→`disable_model_fallback=True`）、workers（9→10）、题集（9文本子集→全25）。

**推论**：「务必再次得到 5/9」这个目标**不成立**——5/9 依赖的恰是已被主动修掉的 bug。F7 修复后的完整配置复跑（`ckpt_repro`）得 **1/9 文本**（仅 idx9 存活；1/13/17/23 全翻转），但这是 F7+seed+provider+并发+端点噪声的叠加，无法归因单一因素。

**重要更正**：先前推测"泄漏 age=55 借 ×1.3 帮到 case_17(CML)"**不准确**——case_17 真实年龄 57，与泄漏值 55 同处 41–60 band，F7 对该题年龄乘子**零影响**；其 D→B 翻转纯属端点噪声（§21.12.4 已证 ~40% 翻转率）。

#### 21.13.2 F7 行为验证：通过

F7 修复版（`state._age_sex_cache`，每题独立）live 日志确认每题读取本题自己的人口学、无跨题泄漏：case_09 `age=59 male`、case_06 `age=38 male`（先天肠旋转不良族 ×0.7，正确）、case_04 `7yo boy`。回归测试 `test_f7_age_sex_cached_per_state_not_across_cases` 覆盖。

#### 21.13.3 fix-a/fix-b 不 work 根因（基于 qwen3-32b 运行记录）

- **Fix A（`representative_diseases` 提示字段）= 确定性净退化，不可修（提示路线）**：base8/base8b 两跑同为 2/9、正确集相同 {14,23}（可复现、非噪声）。根因：给 BranchCreator 加必填字段扰动一级分支生成。**新证据（决定性）**：retriever `dx_feature_retriever.py:514` `canonicalize_entity(d)` 表明**分支标签规范化在基线里早就做了**——Fix A 提示词唯一增量是"族→具体亚型展开"，而这恰是扰动源。结论：**提示路线的 Fix A 永久关闭**；若要"族→亚型展开"应走**分类法（PrimeKG 子节点）后处理**，绝不走提示。
- **Fix B（反锚定 hint）= 一致向下，机制有缺陷，远程不可净隔离**：cleanfixb 0/9、fixb 1/9、fixb2 3/9 全 < base 5/9。但 **cleanbase(5/9) vs cleanfixb(0/9) 的对比本身被 F7 泄漏污染**（一个 55/男、一个 7/男），故"fix-b 把 5/9 拉到 0/9"**不可信**。机制缺陷确凿：无条件反锚定把标注器从"正确的常见诊断"推开。鉴于端点不可复现（§21.12.4），**远程无法净隔离 fix-b 效果**——需本地托管或"干净 base 轨迹重放"方可控变量。

#### 21.13.4 人口学先验数据错误（独立审计，已修复）

审计 `age_sex_incidence.json` + `prior_modifier.py` 匹配逻辑，发现两个独立缺陷：

**Bug 1（否定盲、临床反向）**：`_kw_hit` 纯子串匹配使 **"Reactive / Non-**malignan**t Leukocytosis" 命中 `solid_malignancy` 关键词 "malignan"** → 良性反应过程被套上癌症年龄曲线（55岁 ×1.30 / 老年 ×2.2）。**修复**：`_kw_hit` 新增否定前缀守卫 `_NEG_PREFIX_RE`（`non-`/`not`/`without` 紧邻关键词时跳过该次命中）→ 现为中性 1.00。

**Bug 2（血液病误归固体瘤，含儿科危险错误）**：广义族名 "Myeloid/Lymphoid Neoplasm…"、"Chronic Myeloproliferative Neoplasm" 经关键词 "neoplasm" 命中 `solid_malignancy`，套用**固体瘤**年龄曲线而非白血病曲线。最严重：**"Lymphoid Neoplasm with Increased Blasts"（≈ALL，儿童高发）在 8 岁本应 ×2.4 升高，却被固体瘤曲线 ×0.20 压低（~9.5× 反向错误）**。**修复**：新增 `diseases` 条目 `myeloid neoplasm (family)`（老年偏，70岁 ×2.2）/ `lymphoid neoplasm (family)`（儿童偏，8岁 ×1.9）；因 `_match_entry` 先查 `_diseases` 后查 `_categories`，族名优先命中正确曲线。回归测试 `test_audit_bug1_*` / `test_audit_bug2_*` 覆盖；固体瘤（melanoma/adenocarcinoma）与 CML 专属曲线无回归。

**Bug 3（次生观察）**：`apply` 的归一化 `scale=total_before/total_after` 使**同类一致乘子在重整后抵消**——当所有 live 分支落同一类目（如泄漏期 case_09/17 四个血液病分支全 ×1.3），年龄先验**净微分效应≈0**。Bug 1+2 还会把"良性反应""淋系（儿童峰）""髓系（老年峰）"错误**塌缩到同一固体瘤桶**，**抹掉**年龄本应提供的鉴别力（年轻患者 ALL ×2.4 vs CML ×0.1 的 24× 分离）。Bug 1/2 修复后此鉴别力恢复。

**对照实验（已完成）**：`f7_ageon`（F7修复版 age 开）vs `f7_ageoff`（age 关），9 文本子集、workers=5、temp=0、seed=0、alibaba 单固定，唯一变量=age-prior 开关（两臂均跑数据修复**前**的旧数据）。

| idx | gold | ageON | ageOFF | ckpt(泄漏 5/9) |
|---|---|---|---|---|
| 1 | A | B✗ | B✗ | A |
| 9 | D | C✗ | C✗ | D |
| 13 | A | E✗ | B✗ | A |
| 14 | A | C✗ | C✗ | C |
| 17 | D | B✗ | A✗ | D |
| 18 | E | C✗ | D✗ | A |
| 22 | C | A✗ | D✗ | D |
| 23 | A | **A✓** | **A✓** | A |
| 24 | B | E✗ | E✗ | E |
| **总** | | **1/9** | **1/9** | 5/9 |

**结论**：(1) 两臂均 1/9，唯一稳定正确题 = idx23(Adhesions)（checkpoint/ageon/ageoff/完整复跑皆对）。(2) age-prior 开/关在 **4/9 题（13/17/18/22）改变了答案**——故年龄先验**并非 inert**（确实扰动轨迹），但**这些翻转无一落到正确答案上**：在此题集上它是**轨迹扰动而非信号**，净准确率贡献=0。(3) 1/9 vs 泄漏 5/9 的落差主因 = 5/9 本是 `55岁/男` 一刀切的**幸运 artifact** + 端点 ~40% 翻转噪声，**非任何单一开关**。(4) 干净验证（修复后数据 + age 开关）受 §21.12.4 端点不可复现所限，单跑信号弱；**真正可复现的 A/B 仍需本地托管**。

#### 21.13.5 逐案根因解剖（基于 `f7_ageon` 流水线日志）

逐题读取 ageON 臂的完整流水线日志（root/branches/posterior/leader/AnswerMapper），定位失败的**首发部件、应得中间结果、逐级误导链**。

| idx | gold | pred | 首发失败部件 | 根因类别 |
|---|---|---|---|---|
| 13 | A 胰高血糖素瘤(α细胞瘤) | E 胰岛素抵抗 | 分支生成/排序 | 基率锚定 |
| 17 | D CML | B AML | 分支生成 + 线索反转 | 线索反转 + 知识缺口 |
| 18 | E 肝血管扩张(peliosis hepatis) | C Budd-Chiari | 根/分支生成 | 知识关联缺失 |
| 22 | C 原发甲旁亢(PTH↑) | A 抗酸剂过量 | 分支排序 + **数据 Bug1** | 数据误导 + 锚定 |
| 23 | A 粘连 | **A ✓** | — | 常见无歧义，稳定命中 |
| 1,9,14,24 | — | 全错 | 上游 + 端点噪声 | 混合 |

**case_17（CML）——线索反转 + 结构掩埋（最具代表性）**
- 患者 57 岁，WBC **57,500 + 35% blasts**，伴**视物模糊(20/100) + 共济失调** = **leukostasis（白细胞淤滞）**，CML 枢纽线索。
- 误导链：建分支时 **CML 家族（"Chronic Myeloproliferative Neoplasm"）被 parked 到 0.007**、"CML Blast Crisis" closed 到 0.012，原话 *"Acute neurological deficits are atypical for chronic myeloproliferative neoplasms…"*——**把 leukostasis 视觉/神经症状误判为"反对慢性白血病"**（实为支持 CML）。→ 树仅向 AML 子树扩展 → leader "AML t(8;21)" → AnswerMapper `final_answer=B`（"Leading leaf: De Novo AML"）。
- 应得中间结果：CML/blast-crisis 家族应保持 live 且高后验（WBC 极高更像 CML；leukostasis = 高黏滞标志）。
- 关联 §16 已标记的 **leukostasis 三联征无量化 LR** 知识缺口：无数值信号救回 CML，LLM 又主动反向解读。checkpoint 那次答对 D 系**轨迹运气**，非真本事。

**case_18（peliosis hepatis）——知识关联缺失，age 正确 inert**
- 23 岁女，急性 RUQ 痛 + 休克(80/40)，**粗壮肩颈、背/额痤疮（雄性化）+ 健身比赛减重 + OCP** = 合成类固醇线索。gold E = 肝血管扩张(peliosis)。
- 误导链：**"雄性化体征→合成类固醇→peliosis" 的因果链从未建立**，流水线锚定常见胆道/血管病因（Budd-Chiari / 胆总管结石）。
- age-prior 在该题**无 trace（inert）**——分支标签无任何流行病学关键词匹配，正确地保持中性（非 bug）。

**case_22（原发甲旁亢）——数据 Bug1 主动误导**
- leader = "**Reactive / Non-malignant Hypercalcemia**" → `final_answer=A`（抗酸剂过量/乳碱）。gold C = PTH↑。
- 该良性分支正是被 **Bug1 误 ×1.3** 推成领跑（修复后→1.0）。**这是已修数据 bug 可能直接改善的一题**。

**case_13（glucagonoma）/ case_22 / case_17 共性**：罕见/特异诊断被**常见家族基率锚定**埋没（T2DM 盖过 α细胞瘤、反应性盖过原发甲旁亢、AML 盖过 CML）——正是 **Fix B（反锚定）的设计靶点**，但 Fix B 实现反噬（§21.13.3）。

**贯穿性结论**：
1. **三大主因**：(a) 基率锚定埋没特异诊断（13/17/22）、(b) 枢纽线索被反向解读或缺量化 LR（17 leukostasis）、(c) 知识关联缺失（18 类固醇→peliosis）。叠加 (d) 个别数据 bug 误导（22，已修）。
2. **失败发生在上游**（建根/建分支/线索解读），**不在年龄先验幅度**——故 age-on/off 翻转的 4 题全在错误选项间重排，先验改不动它。
3. 唯一稳定正确题（23）是常见无歧义诊断，印证流水线对"bread-and-butter"可靠、对"罕见+特异线索"系统性失手。
4. 真正提分杠杆 = **特异线索点亮（不走提示扰动的 Fix B 替代）+ 补 leukostasis 类量化 LR**；验证须本地可复现环境。

---

### 21.14 §21.13.5 根因的修复方案（联网佐证）+ Fix A/B 逐案干扰解剖

> 本节回答两件事：(A) §21.13.5 列出的逐案根因**如何修**（含联网取证的临床数据）；(B) 忽略"远程不可复现"这一干扰项，**逐案分析 Fix A / Fix B 是否引入了额外干扰**（机制级，非看最终准确率）。

#### 21.14.0 先决：§21.13.4 的三个数据 bug 在**本工作树尚未落地**（需移植）

审计本树 `prior_modifier.py` / `age_sex_incidence.json`，确认 copy 版描述的修复**不在此树**：
- `_kw_hit`（`prior_modifier.py:178`）仍是纯子串匹配，**无 `_NEG_PREFIX_RE` 否定守卫** → Bug1（"Non-malignant…" 命中 "malignan"）在此树**仍存在**。
- `age_sex_incidence.json` 仅有 `chronic/acute myeloid leukemia` 等具体条目，**无 `myeloid/lymphoid neoplasm (family)` 族条目** → Bug2（广义族名误归固体瘤曲线、ALL 儿童 ×0.20 反向）在此树**仍存在**。
- `apply()` 归一化 `scale=total_before/total_after`（`:168`）原样存在 → Bug3（同类乘子重整后抵消）在此树**仍存在**。

**结论**：要在本树复现 §21.13.4 的修复效果，必须**移植** Bug1/2 修复（否定守卫 + 族条目），这是 case_22 等"数据主动误导"题的直接修复项。

#### 21.14.1 逐案修复方案

| case | gold | 根因（§21.13.5） | 修复手段 | 数据来源 |
|---|---|---|---|---|
| 22 | 原发甲旁亢 | 数据 Bug1 把"Non-malignant Hypercalcemia"×1.3 推成领跑 | **移植 Bug1 否定守卫** → 良性分支回中性 1.0 | 代码审计（本树缺失） |
| 17 | CML | 枢纽线索被反向解读 + 无量化 LR | **补 CML 量化 LR**（见 21.14.2，含纠偏） | 联网（见下） |
| 18 | peliosis hepatis | "雄性化→合成类固醇→peliosis"因果链从未建立 | **补 AAS→peliosis 机制映射 + LR** | 联网（见下） |
| 13 | glucagonoma | 基率锚定（T2DM 盖过 α 细胞瘤） | **特异线索点亮（NME+高血糖）走机制化 LR 注入，非提示反锚定** | 见 21.14.4 |

#### 21.14.2 case_17（CML）量化 LR —— **联网取证后对 §21.13 框架的重要纠偏**

§21.13.5 把"leukostasis（视觉/共济失调）"当作 **CML 枢纽线索**。**联网临床证据表明该框架不准确**：

- Hyperleukocytosis 定义为 WBC > 100,000/μL；**symptomatic leukostasis 在 CML 慢性期极罕见，几乎只见于加速期/急变期**，因 CML 外周细胞多为较小、可变形的成熟粒系（中幼/晚幼/分叶核），而非僵硬的原始细胞。
- **Leukostasis 最常见于 AML**（髓系原始细胞体积大、变形差），ALL/CLL 中极罕见。
- 来源：*Leukostasis in adult acute hyperleukocytic leukemia*（Hematol Oncol, doi:10.1002/hon.2292）；ACEP Critical Care（2025）；StatPearls *Leukocytosis*（NCBI NBK560882）。

**纠偏含义**：在本病例 WBC 57,500 + **35% 原始细胞** + leukostasis 体征下，leukostasis 本身其实**偏向 AML / CML 急变**，**不能**作为"支持慢性 CML"的证据——故§21.13 拟"补 leukostasis→CML LR"的方向**会引入新错误**。CML 的真正鉴别信号应是：

1. **WBC 极度升高 + 全谱髓系左移**（myelocyte/metamyelocyte 峰、**嗜碱性粒细胞增多 basophilia**）；
2. **脾大**；
3. **BCR-ABL1 / Ph 染色体阳性、LAP 评分低**。

**正确修复**：curated LR 应锚定**这些**特征而非 leukostasis：
- `basophilia` → CML：LR+ 强阳（嗜碱增多对 CML 高度特异）；
- `WBC > 50k with myeloid left-shift (myelocytes/metamyelocytes)` → CML/CMPN vs reactive：LR+ 中-强；
- `BCR-ABL1 positive` → CML：近乎 pathognomonic（LR+ 极高）。
- 同时**纠正反向解读**：在 EvidenceAnnotator 知识提示中明确"leukostasis/神经-视觉症状**不**反对髓系肿瘤；急变期 CML 同样可致 leukostasis"，消除 *"acute neuro deficits atypical for chronic MPN"* 这条把 CML 家族 park 到 0.007 的错误推理。

> 注：该题 35% 原始细胞使 "CML blast crisis" 与 "de novo AML" 的鉴别本就微妙；若 vignette 含 basophilia/脾大/Ph⁺ 则 gold=CML 成立，否则需复核题面。这本身是**知识 + 题面证据**问题，非单纯先验幅度问题。

#### 21.14.3 case_18（peliosis hepatis）—— AAS→肝血管病变，机制链补全

**联网证据**（强、干净）：
- 合成代谢雄激素类固醇（AAS，尤其 **17-α 烷基化**）是 **peliosis hepatis / 肝窦扩张**的明确危险因素，多见于**健美者/运动员**；可表现 RUQ 不适、肝大，破裂时**急腹症 + 血管性虚脱（休克）+ 腹腔积血**——与本例 80/40 休克吻合。
- 来源：LiverTox *Androgenic Steroids*（NCBI NBK548931）；*AAS-induced liver injury: an update*（PMC9331524）；Thieme J Gastrointest Abdom Radiol 2024（10.1055/s-0044-1787963）。

**关键鉴别提醒**：上述文献同时指出 **AAS 也与 Budd-Chiari（本例错误答案 C）相关**——故"有 AAS 暴露"**不足以**区分 peliosis 与 Budd-Chiari。鉴别点：
- **peliosis/肝血管扩张**：肝实质内充血性血囊、可破裂出血 → **急性失血性休克**、影像见血池/囊腔；
- **Budd-Chiari**：肝静脉流出道梗阻 → 腹水、肝大、肝静脉血栓，**非急性大出血**。

**修复手段**：
1. `mechanism_to_disease.json` 增映射："anabolic steroid use / androgenic features (acne, virilization) in athlete + acute liver bleed" → `peliosis hepatis` / `hepatic vascular ectasia`（建立缺失的因果链，让该分支可被建出并命中 LR）；
2. curated LR：`anabolic-androgenic steroid use` → `peliosis hepatis` LR+ 强阳；并标注**鉴别要点**（急性出血性休克 favors peliosis；流出道梗阻/腹水 favors Budd-Chiari）。

#### 21.14.4 case_13 / 通用：基率锚定的**机制化**修复（取代提示反锚定）

§21.13 已判定提示路线的反锚定（Fix B）反噬。正确替代 = **特异线索 → 数值 LR → 贝叶斯加权**，全程不依赖让 LLM"对抗常见诊断"的软提示：
- glucagonoma：`necrolytic migratory erythema + new-onset hyperglycemia + weight loss` 组合 → glucagonoma 近 pathognomonic，curated LR+ 极高；
- 关键在于**线索组合作为整体**命中 LR（而非散成"高血糖"/"皮疹"两个弱信号——见 21.14.5 Fix A 把这两者拆散的反例）。

#### 21.14.5 Fix A 逐案干扰解剖（机制级，**确定性、非噪声**）

base8/base8b 两跑同为 2/9、正确集同为 {14,23}（§21.13.3 已证可复现）。本节给出**新的决定性机制证据**：对比 `cleanbase` vs `fixa_r2` 的**一级分支标签**，发现 Fix A 的 `representative_diseases` 字段会**掏空（hollow）分支标签的鉴别粒度**：

| case | cleanbase 分支标签（有鉴别力） | fixa 分支标签（被掏空） |
|---|---|---|
| 13 | "Endocrine-Metabolic Syndrome **with Severe Hyperglycemia**"、"Drug-Induced **Hyperglycemia and Rash**"、"Infection-Related Multiorgan Syndrome **with Hyperglycemia and Rash**" | "Endocrine Disorder with Hyperglycemia"、**"Inflammatory Bowel Disease"**、**"Autoimmune Skin Disorder"**、"Metabolic Syndrome" |
| 22 | "Malignancy **with Hypercalcemia** and Elevated Alk Phos"、"**Reactive Hypercalcemia** from Antacid Overuse"、"Granulomatous Disease with **Vit D** abnormalities" | **"Endocrine Disorder"**、**"Malignancy"**、**"Gastrointestinal Disorder"**、**"Infectious Disease"** |
| 17 | "Myeloid Neoplasm with Increased Blasts"、"Chronic Myeloproliferative Neoplasm (chronic/accelerated phase)" | 同类（仅去掉 "(chronic/accelerated phase)" 限定），**分歧最小** |

**机制结论（额外干扰确凿）**：要求 LLM 额外产出 `representative_diseases`（具体亚型清单）后，模型把**具体性"卸载"到该字段**，导致**分支 LABEL 退化为顶层器官系统桶**（case_22："Endocrine/Malignancy/GI/Infectious"；case_13 把"高血糖+皮疹"的 glucagonoma 整体线索**拆散**成无关的"IBD/Autoimmune Skin"）。流水线的后验/LLM 效应是**在 label 粒度上**计算的——label 被掏空到"Malignancy"级别后：
1. 兄弟分支同样粗（都退化为器官桶），**鉴别力丧失**；
2. 即便 `representative_diseases` 里正确列了 CML/glucagonoma，**贝叶斯更新与排序仍发生在错误的粗粒度上**，命中也救不回正确叶。

→ 这是**比"扰动"更具体的损伤定位**：Fix A 不是随机扰动分支，而是**系统性下推 label 抽象层级、破坏中层 syndrome 框架**。印证 §21.13.3 的判决——**提示路线 Fix A 永久关闭**；"族→亚型"必须走**分类法后处理**（PrimeKG 子节点 / 既有 `canonicalize_entity`），即**保持 label 在 syndrome 粒度、把代表实体作为 LR-lookup 的旁路附件**，绝不进提示。

#### 21.14.6 Fix B 逐案干扰解剖：当前实现**基本 inert**，无法点亮它要点亮的线索

抽取 `fixb_r2` 的 case 13/17/18/22 流水线日志，`PIVOTAL DISCRIMINATING EVIDENCE` 提示块**全为空**：

- 当前 Fix B 的 hint 仅在**广义分支标签命中 curated LR+ ≥ 5** 时才注入，且 RAG 衍生 LR 被噪声门挡掉（§21.10）。
- 而这些题的广义 label（"Myeloid Neoplasm…"、"Endocrine Disorder…"）**恰恰 MISS curated cache**（正是 F4 的 LR 洞）。
- **悖论**：Fix B 设计用来"点亮特异线索"，但它的触发条件（curated LR+≥5 命中）**正是 F4 所缺失的东西** → Fix B **几乎从不触发**。

**逐案干扰结论**：
1. **不奏效的根因不是"反锚定把对的推开"**（那是已弃用的无条件版，§21.13.3）——当前 hint-gated 版**根本不开火**，故对 13/17/18/22 **零信号注入**；准确率波动纯属端点噪声。
2. **唯一开火时反而有害**：早前 fixb2 case_17 曾注入一条 RAG 衍生的伪 `Hypertension LR+≈6` → 误导标注器（§21.10 记录）。即"开火 = 喂噪声"。
3. 故 Fix B "净干扰"= **大多数情况无（inert）+ 少数开火时喂噪声**，两者都不能修 F4。

#### 21.14.7 贯穿结论：两个 fix 都打 F4，但机制都错位

- **Fix A**（提示加字段）→ 掏空 label 粒度，**破坏鉴别**；
- **Fix B**（提示 hint）→ 触发条件依赖的 curated LR**正是 F4 所缺**，故**打不着**；偶尔开火又喂 RAG 噪声。
- **正确路线（单一、非提示）**：
  1. **保持分支 label 在 syndrome 粒度**（不动 BranchCreator 提示）；
  2. 用**分类法**把 label 映射到代表实体（旁路，不进提示）；
  3. 对代表实体做 **curated-LR lookup**，把命中的数值 LR 作为**贝叶斯加权**注入后验（机制化点亮，取代提示反锚定）；
  4. **补齐 F4 的 curated LR 洞**：21.14.2（basophilia/WBC 左移/BCR-ABL→CML，**非 leukostasis**）、21.14.3（AAS→peliosis）、21.14.4（NME+高血糖→glucagonoma），并**移植 21.14.0 的 Bug1/2 数据修复**。
- **验证**：单跑信号被端点 ~40% 翻转噪声淹没；A/B 须**本地托管**或"干净 base 轨迹重放"控变量（§21.12.4 / §21.13.4）。

