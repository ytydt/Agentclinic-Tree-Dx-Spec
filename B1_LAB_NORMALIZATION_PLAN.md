# B1：数值型化验结果 → HPO 表型术语映射方案

> **版本**: v1.0 | **日期**: 2026-05-25  
> **问题**: Embedding 对 "WBC 145000"、"82% blasts" 等数值化验描述无法语义匹配到 "Leukocytosis"、"Elevated blast count"  
> **目标**: 将数值型化验结果自动映射为标准 HPO 术语，接入 LR cache 参与似然比计算

---

## 1. 问题分析

### 1.1 当前瓶颈

VignetteParser 提取的 evidence 中，数值型化验描述占比显著：

| 原始描述 | 期望 HPO 术语 | 当前匹配结果 |
|----------|-------------|-------------|
| WBC 145,000/μL | HP:0001974 Leukocytosis | ✗ Embedding 无法匹配 |
| 82% blasts | HP:0012234 Elevated blast count | ✗ 无语义相似性 |
| Hemoglobin 7.2 g/dL | HP:0020062 Decreased hemoglobin | ✗ 无法判断方向 |
| Platelet 45,000 | HP:0001873 Thrombocytopenia | ✗ 无法判断方向 |
| Basophils 8% | HP:0031807 Basophilia | ✗ 数值无语义 |

**根因**：Embedding 模型（all-MiniLM-L6-v2）为通用语义模型，不理解 "145000 > 11000 → 高" 这种数值推理。

### 1.2 为何不用纯 LLM 方案

| 因素 | LLM 方案 | 结构化方案 |
|------|---------|-----------|
| 延迟 | ~500ms/条（API 调用） | <1ms/条（查表） |
| 可靠性 | LLM 可能误判阈值 | 确定性规则 |
| 可审计性 | 黑盒 | 完全可追溯 |
| 成本 | Token 消耗 | 零增量成本 |
| 离线运行 | 需要 API | 完全离线 |

---

## 2. 外部数据源调研结果

### 2.1 核心数据源：loinc2hpo（Jackson Laboratory）

**仓库**: [TheJacksonLaboratory/loinc2hpoAnnotation](https://github.com/TheJacksonLaboratory/loinc2hpoAnnotation)

将 LOINC 检验代码 + 结果方向（H/L/N）映射到 HPO 术语的权威注释表。

| 指标 | 数值 |
|------|------|
| 总注释数 | 7,416 条 |
| 唯一 LOINC ID | 3,118 个 |
| 唯一 HPO 术语 | 827 个 |
| 定量（Qn）注释 | 6,116 条 |
| 许可证 | HPO License（学术免费） |

**CML 相关的关键映射**:

| 化验项 | LOINC | 方向 | HPO ID | HPO 术语 |
|--------|-------|------|--------|---------|
| WBC | 6690-2 | H | HP:0001974 | Leukocytosis |
| WBC | 6690-2 | L | HP:0001882 | Leukopenia |
| Platelets | 26515-7 | H | HP:0001894 | Thrombocytosis |
| Platelets | 26515-7 | L | HP:0001873 | Thrombocytopenia |
| Basophils | 30180-4 | H | HP:0031807 | Basophilia |
| Eosinophils | 711-2 | H | HP:0001880 | Eosinophilia |
| Hemoglobin | 718-7 | L | HP:0020062 | Decreased hemoglobin |
| Hemoglobin | 718-7 | H | HP:0020063 | Increased hemoglobin |
| Neutrophils | 26499-4 | H | HP:0011897 | Neutrophilia |
| Lymphocytes | 26478-8 | L | HP:0001888 | Lymphopenia |

**工作原理**: 给定 LOINC 代码和结果方向（H=高于正常/L=低于正常/N=正常），直接查表获得 HPO 术语。**loinc2hpo 不提供参考范围数值**，仅提供方向到 HPO 的映射，因此需要配合参考范围数据源才能从原始数值判断方向。

### 2.2 参考范围数据源

#### 数据源 A：LabQAR（MIT 许可）

**仓库**: [balubhasuran/LabQAR](https://github.com/balubhasuran/LabQAR)

| 指标 | 数值 |
|------|------|
| 检验项目数 | 550 |
| 数据格式 | JSON（set1_reference_range.json, set2_classification.json） |
| 内容 | SI 参考范围上下界、标本类型、性别/年龄分组 |
| 许可证 | MIT |
| 来源 | 手工策展，附 annotation guidelines |

**数据格式示例**:
```json
{
  "ID": 1,
  "Question": "For the lab test 'Acetaminophen' measuring in 'μmol/L' in Specimen 'Serum, plasma' for 'any gender' and 'any age group', what is the correct lower and upper bound range values in SI reference range?",
  "Answer": "70–200"
}
```

**局限**: 参考范围以 QA 格式存储，需解析提取结构化字段。

#### 数据源 B：medical-lab-reference（MIT 许可）

**仓库**: [computerdude11111/medical-lab-reference](https://github.com/computerdude11111/medical-lab-reference)

| 指标 | 数值 |
|------|------|
| 检验项目数 | ~80（覆盖常见化验） |
| 数据格式 | Markdown 表格（可结构化提取） |
| 分类 | Chemistry, Hematology, Coagulation, Liver, Thyroid, Iron, Lipid, Cardiac, Inflammatory |
| 许可证 | MIT |
| 权威来源 | Tietz Clinical Guide 5th Ed, KDIGO, AHA/ACC, Mayo Clinic Labs |

**已结构化的关键参考范围**:

| 检验项 | 正常范围 | 单位 |
|--------|---------|------|
| WBC | 4,500–11,000 | /μL |
| RBC (M/F) | 4.7–6.1 / 4.2–5.4 | million/μL |
| Hemoglobin (M/F) | 14–18 / 12–16 | g/dL |
| Hematocrit (M/F) | 42–52 / 37–47 | % |
| Platelets | 150,000–400,000 | /μL |
| MCV | 80–96 | fL |
| Sodium | 136–145 | mEq/L |
| Potassium | 3.5–5.0 | mEq/L |
| Creatinine (M/F) | 0.7–1.3 / 0.6–1.1 | mg/dL |
| Glucose (fasting) | 70–100 | mg/dL |

#### 数据源 C：LOINC 官方数据库

| 指标 | 数值 |
|------|------|
| LOINC 代码总数 | ~100,000 |
| 格式 | CSV（Loinc.csv, LoincTableCore.csv） |
| 内容 | 检验名称、组分、单位、量纲 |
| 许可证 | 免费注册下载 |

**用途**: 检验名称标准化 → LOINC 代码映射（不含参考范围）。

### 2.3 项目已有语料（RAG 兜底）

| 语料 | 块数 | 含参考范围的块 | 占比 |
|------|------|-------------|------|
| StatPearls | 367,799 | ~561 | 0.15% |
| Textbooks (MedRAG) | 125,847 | ~300 | 0.24% |
| **合计** | **493,646** | **~861** | **0.17%** |

**已验证内容示例**（StatPearls）：
- "The white blood cell (WBC) count... normal reference range of approximately 4.3 to 11.0 × 10^9/L"
- "Neutrophilia is defined as a higher neutrophil count in the blood than the normal reference range of absolute neutrophil count"

**当前问题**: RAG FAISS 索引二进制文件缺失，需重建。

---

## 3. 架构设计：三层正规化管线

### 3.1 整体流程

```
VignetteParser 输出的 EvidenceItem
  │
  │  finding = "WBC 145,000/μL"
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ Layer 1: 正则解析（FindingNormalizer._parse_lab）    │
│                                                     │
│ 正则模式匹配 → 提取:                                │
│   test_name = "WBC"                                 │
│   value     = 145000.0                              │
│   unit      = "/μL"                                 │
│                                                     │
│ 如果正则未命中 → 原样传递给 EmbeddingIndex           │
└─────────────────┬───────────────────────────────────┘
                  │ (test_name, value, unit)
                  ▼
┌─────────────────────────────────────────────────────┐
│ Layer 2: 结构化查表（FindingNormalizer._classify）   │
│                                                     │
│ Step 2a: test_name → 标准名 + LOINC 代码            │
│   "WBC" → alias_map → "Leukocytes" → LOINC:6690-2  │
│                                                     │
│ Step 2b: 单位归一化                                  │
│   value=145000, unit="/μL" → 145000 /μL             │
│   (如单位不匹配参考范围单位，执行换算)               │
│                                                     │
│ Step 2c: 查参考范围 → 判断方向                       │
│   lab_ranges["WBC"] = {low:4500, high:11000, ...}   │
│   145000 > 11000 → direction = "H"                  │
│                                                     │
│ Step 2d: loinc2hpo 查表                              │
│   LOINC:6690-2 + Qn + H → HP:0001974               │
│                                                     │
│ 如果 Step 2a~2d 任一步失败 → fallback to Layer 3    │
└─────────────────┬───────────────────────────────────┘
                  │ HPO term(s)
                  ▼
┌─────────────────────────────────────────────────────┐
│ Layer 3: RAG 兜底（FindingNormalizer._rag_lookup）   │
│                                                     │
│ query = "WBC 145000 reference range interpretation"  │
│ → RAGRetriever.search() → snippets                  │
│ → 正则提取参考范围 + 判断方向                        │
│ → loinc2hpo 或 HPO 术语直接匹配                     │
│                                                     │
│ 如果仍未命中 → 返回原始 finding（不做转换）          │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
输出: NormalizedFinding {
    original: "WBC 145,000/μL",
    hpo_term: "Leukocytosis",
    hpo_id:   "HP:0001974",
    direction: "H",
    confidence: "high",  // high=结构化查表, medium=RAG, low=未命中
    source: "loinc2hpo:6690-2"
}
```

### 3.2 模块设计

#### 3.2.1 新模块：`FindingNormalizer`

**文件**: `src/agentclinic_tree_dx/knowledge/finding_normalizer.py`

```python
class FindingNormalizer:
    """将数值型化验描述正规化为 HPO 表型术语."""

    def __init__(
        self,
        lab_ranges_path: Path,      # lab_reference_ranges.json
        loinc2hpo_path: Path,       # loinc2hpo_annotations.json
        alias_map_path: Path,       # lab_name_aliases.json
        unit_conversions_path: Path, # unit_conversions.json
        rag_retriever: RAGRetriever | None = None,
    ): ...

    def normalize(self, finding: str) -> NormalizedFinding | None:
        """主入口: 尝试将单条 finding 正规化."""
        ...

    def normalize_batch(self, findings: list[str]) -> list[NormalizedFinding | None]:
        """批量正规化."""
        ...

    def _parse_lab(self, text: str) -> LabParsed | None:
        """Layer 1: 正则提取 test_name + value + unit."""
        ...

    def _classify(self, parsed: LabParsed) -> NormalizedFinding | None:
        """Layer 2: 结构化查表判断方向 + loinc2hpo 映射."""
        ...

    def _rag_lookup(self, text: str, parsed: LabParsed | None) -> NormalizedFinding | None:
        """Layer 3: RAG 兜底."""
        ...
```

#### 3.2.2 数据结构

```python
@dataclass
class LabParsed:
    test_name: str      # "WBC"
    value: float        # 145000.0
    unit: str           # "/μL"
    original: str       # "WBC 145,000/μL"

@dataclass
class NormalizedFinding:
    original: str       # 原始 finding 文本
    hpo_term: str       # "Leukocytosis"
    hpo_id: str         # "HP:0001974"
    direction: str      # "H" / "L" / "N"
    confidence: str     # "high" / "medium" / "low"
    source: str         # "loinc2hpo:6690-2" / "rag:statpearls_xxx"
    test_name: str      # 标准化后的检验名
    value: float | None # 原始数值
    unit: str | None    # 原始单位
```

### 3.3 数据文件规划

#### 3.3.1 `data/knowledge_raw/lab_reference_ranges.json`

从 LabQAR + medical-lab-reference 整合构建：

```json
{
  "WBC": {
    "loinc_codes": ["6690-2", "26464-8"],
    "reference_ranges": [
      {
        "low": 4500,
        "high": 11000,
        "unit": "/μL",
        "gender": "any",
        "age": "adult",
        "source": "Tietz 5th Ed"
      }
    ],
    "aliases": ["white blood cell", "white blood cell count", "leukocytes", "leukocyte count"],
    "scale": "Qn"
  },
  "Hemoglobin": {
    "loinc_codes": ["718-7"],
    "reference_ranges": [
      {"low": 14.0, "high": 18.0, "unit": "g/dL", "gender": "male", "age": "adult", "source": "Tietz 5th Ed"},
      {"low": 12.0, "high": 16.0, "unit": "g/dL", "gender": "female", "age": "adult", "source": "Tietz 5th Ed"}
    ],
    "aliases": ["Hb", "Hgb", "hemoglobin level"],
    "scale": "Qn"
  }
}
```

#### 3.3.2 `data/knowledge_raw/loinc2hpo_annotations.json`

从 loinc2hpoAnnotation TSV 转换：

```json
{
  "6690-2": {
    "Qn": {
      "H": {"hpo_id": "HP:0001974", "hpo_term": "Leukocytosis"},
      "L": {"hpo_id": "HP:0001882", "hpo_term": "Leukopenia"},
      "N": {"hpo_id": "HP:0011893", "hpo_term": "Normal leukocyte count"}
    }
  },
  "26515-7": {
    "Qn": {
      "H": {"hpo_id": "HP:0001894", "hpo_term": "Thrombocytosis"},
      "L": {"hpo_id": "HP:0001873", "hpo_term": "Thrombocytopenia"},
      "N": {"hpo_id": "HP:0011873", "hpo_term": "Normal platelet count"}
    }
  }
}
```

#### 3.3.3 `data/knowledge_raw/lab_name_aliases.json`

检验名称别名映射表：

```json
{
  "WBC": ["white blood cell", "white blood cell count", "leukocytes", "wbc count", "white cell count"],
  "RBC": ["red blood cell", "red blood cell count", "erythrocytes", "rbc count"],
  "Hb": ["hemoglobin", "hgb", "hemoglobin level", "hb level"],
  "Plt": ["platelet", "platelets", "platelet count", "thrombocytes"],
  "BUN": ["blood urea nitrogen", "urea nitrogen"],
  "Cr": ["creatinine", "serum creatinine", "creat"],
  "Na": ["sodium", "serum sodium", "na+"],
  "K": ["potassium", "serum potassium", "k+"],
  "Glu": ["glucose", "blood glucose", "fasting glucose", "blood sugar"],
  "blasts": ["blast cells", "blast count", "blast percentage", "myeloblasts"]
}
```

#### 3.3.4 `data/knowledge_raw/unit_conversions.json`

常用单位换算：

```json
[
  {
    "test_group": "WBC",
    "conversions": [
      {"from": "×10^9/L", "to": "/μL", "factor": 1000},
      {"from": "×10^3/μL", "to": "/μL", "factor": 1000},
      {"from": "cells/mm3", "to": "/μL", "factor": 1}
    ]
  },
  {
    "test_group": "Hemoglobin",
    "conversions": [
      {"from": "g/L", "to": "g/dL", "factor": 0.1},
      {"from": "mmol/L", "to": "g/dL", "factor": 1.611}
    ]
  },
  {
    "test_group": "Platelets",
    "conversions": [
      {"from": "×10^9/L", "to": "/μL", "factor": 1000},
      {"from": "×10^3/μL", "to": "/μL", "factor": 1000}
    ]
  },
  {
    "test_group": "Glucose",
    "conversions": [
      {"from": "mmol/L", "to": "mg/dL", "factor": 18.018}
    ]
  },
  {
    "test_group": "Creatinine",
    "conversions": [
      {"from": "μmol/L", "to": "mg/dL", "factor": 0.01131}
    ]
  }
]
```

---

## 4. 正则解析规则（Layer 1）

### 4.1 核心正则模式

```python
PATTERNS = [
    # "WBC 145,000/μL"  "WBC: 145000 /uL"  "WBC = 145,000"
    r"(?P<name>[A-Za-z][A-Za-z0-9 /-]*?)\s*[:=]?\s*(?P<value>[\d,]+\.?\d*)\s*(?P<unit>[a-zA-Zμ/%°×^]+(?:/[a-zA-Zμ]+)?)?",

    # "82% blasts"  "8% basophils"
    r"(?P<value>\d+\.?\d*)\s*%\s*(?P<name>blasts?|basophils?|eosinophils?|neutrophils?|lymphocytes?|monocytes?|bands?|reticulocytes?)",

    # "hemoglobin of 7.2 g/dL"  "platelet count of 45000"
    r"(?P<name>[A-Za-z][A-Za-z ]+?)\s+(?:of|at|is|was|level)\s+(?P<value>[\d,]+\.?\d*)\s*(?P<unit>[a-zA-Zμ/%°×^]+(?:/[a-zA-Zμ]+)?)?",

    # "elevated WBC (145,000/μL)"  "low hemoglobin (7.2)"
    r"(?:elevated|increased|high|low|decreased|reduced)\s+(?P<name>[A-Za-z][A-Za-z ]*?)\s*\((?P<value>[\d,]+\.?\d*)\s*(?P<unit>[^\)]*?)?\)",
]
```

### 4.2 百分比型指标特殊处理

对于 "82% blasts"、"8% basophils" 等百分比型指标，不需要参考范围查表，而是使用专用阈值：

```json
{
  "blasts": {
    "threshold_high": 5,
    "unit": "%",
    "hpo_high": {"id": "HP:0012234", "term": "Elevated blast count"},
    "note": ">=20% defines acute leukemia per WHO"
  },
  "basophils": {
    "threshold_high": 2,
    "unit": "%",
    "hpo_high": {"id": "HP:0031807", "term": "Basophilia"}
  },
  "eosinophils": {
    "threshold_high": 5,
    "unit": "%",
    "hpo_high": {"id": "HP:0001880", "term": "Eosinophilia"}
  }
}
```

---

## 5. 集成点

### 5.1 插入位置

`FindingNormalizer` 在 `EvidenceMatcher` 之前调用，对所有 `EvidenceItem` 进行预处理：

```
VignetteParser
     │
     │  List[EvidenceItem]
     ▼
FindingNormalizer.normalize_batch()    ← 新增
     │
     │  List[EvidenceItem]（finding 可能被替换/增补）
     ▼
EvidenceMatcher.match_batch()
     │
     ▼
LRRetriever.lookup()
```

### 5.2 controller.py 修改

```python
# 在 _init_knowledge_layers() 中:
self._finding_normalizer = FindingNormalizer(
    lab_ranges_path=data_dir / "lab_reference_ranges.json",
    loinc2hpo_path=data_dir / "loinc2hpo_annotations.json",
    alias_map_path=data_dir / "lab_name_aliases.json",
    unit_conversions_path=data_dir / "unit_conversions.json",
    rag_retriever=self._rag_retriever,
)

# 在 evidence 处理流程中:
for item in evidence_items:
    normalized = self._finding_normalizer.normalize(item.finding)
    if normalized:
        item.normalized_hpo_id = normalized.hpo_id
        item.normalized_hpo_term = normalized.hpo_term
        item.finding_direction = normalized.direction
```

---

## 6. 构建脚本

### 6.1 `scripts/build_lab_reference_data.py`

自动化构建所有数据文件：

1. 下载 loinc2hpoAnnotation TSV → 转换为 `loinc2hpo_annotations.json`
2. 下载 LabQAR JSON → 解析提取结构化参考范围
3. 解析 medical-lab-reference Markdown → 补充常见检验范围
4. 合并去重 → 生成 `lab_reference_ranges.json`
5. 从 HPO OBO 文件解析 HPO term name → 补全 `loinc2hpo_annotations.json` 中的 `hpo_term` 字段
6. 生成 `lab_name_aliases.json`（从 LOINC short name + 常见缩写）
7. 生成 `unit_conversions.json`

### 6.2 `scripts/rebuild_rag_index.py`（可选）

重建 RAG FAISS 索引，恢复 Layer 3 兜底能力。

---

## 7. 正常值映射的价值

loinc2hpo 同时提供 N（正常）方向的 HPO 映射，例如：
- WBC 正常 → HP:0011893 Normal leukocyte count
- Platelets 正常 → HP:0011873 Normal platelet count

**正常值的映射在鉴别诊断中有重要价值**：
- "正常 WBC" 可以作为 **evidence_against** CML（CML 几乎必然 WBC 升高）
- 在 Bayesian 更新中，LR- < 1 的正常结果可以压低疾病概率

在实现中，当化验值落在正常范围内时，同样生成 `NormalizedFinding`（direction="N"），但 confidence 标记为 "medium"（因为正常也可能在疾病早期出现）。

---

## 8. 单位不同的解决方案

### 8.1 策略

1. **标准单位**：每个检验项定义一个标准单位（存储在 `lab_reference_ranges.json` 中）
2. **自动换算**：`FindingNormalizer._normalize_unit()` 根据 `unit_conversions.json` 自动转换
3. **无单位处理**：对于无单位的数值（如 "WBC 145000"），按该检验的最常见单位假设
4. **不可换算**：如单位不在换算表中，fallback to Layer 3（RAG）或跳过

### 8.2 实现逻辑

```python
def _normalize_unit(self, parsed: LabParsed, target_unit: str) -> float | None:
    if not parsed.unit or parsed.unit == target_unit:
        return parsed.value

    key = (parsed.unit, target_unit)
    if key in self._unit_conv_map:
        return parsed.value * self._unit_conv_map[key]

    # 尝试反向换算
    rev_key = (target_unit, parsed.unit)
    if rev_key in self._unit_conv_map:
        return parsed.value / self._unit_conv_map[rev_key]

    return None  # 无法换算
```

### 8.3 需覆盖的换算关系（约 20 组）

| 换算 | 系数 | 适用检验 |
|------|------|---------|
| ×10^9/L → /μL | ×1000 | WBC, Platelets, Neutrophils, etc. |
| ×10^3/μL → /μL | ×1000 | 同上 |
| cells/mm³ → /μL | ×1 | 同上 |
| g/L → g/dL | ×0.1 | Hemoglobin, Albumin |
| mmol/L → mg/dL | ×18.018 | Glucose |
| μmol/L → mg/dL | ×0.01131 | Creatinine |
| mmol/L → mEq/L | ×1 | Na, K, Cl (单价离子) |
| μmol/L → mg/dL | ×0.05848 | Bilirubin |
| pmol/L → pg/mL | ×1 | Free T3 |
| nmol/L → ng/dL | ×0.1 | Free T4 |

---

## 9. 实施路线图

### Phase 1：数据准备（优先级 P0）

| 步骤 | 任务 | 产物 | 预计耗时 |
|------|------|------|---------|
| 1a | 编写 `scripts/build_lab_reference_data.py` | 构建脚本 | 1h |
| 1b | 下载 loinc2hpoAnnotation TSV | 原始数据 | 5min |
| 1c | 整合 LabQAR + medical-lab-reference | `lab_reference_ranges.json` | 30min |
| 1d | 转换 loinc2hpo TSV → JSON | `loinc2hpo_annotations.json` | 15min |
| 1e | 构建别名表和单位换算表 | `lab_name_aliases.json`, `unit_conversions.json` | 30min |

### Phase 2：核心模块实现（优先级 P0）

| 步骤 | 任务 | 产物 | 预计耗时 |
|------|------|------|---------|
| 2a | 实现 `FindingNormalizer` 类 | `finding_normalizer.py` | 2h |
| 2b | 实现正则解析模式 | Layer 1 | 30min |
| 2c | 实现结构化查表 | Layer 2 | 1h |
| 2d | 实现 RAG 兜底 | Layer 3 | 30min |

### Phase 3：集成与测试（优先级 P0）

| 步骤 | 任务 | 产物 | 预计耗时 |
|------|------|------|---------|
| 3a | 集成到 controller.py | 流程接入 | 30min |
| 3b | 编写 CML 场景单元测试 | `test_finding_normalizer.py` | 1h |
| 3c | 更新 `test_lr_coverage.py` 增加 B1 指标 | 覆盖度报告 | 30min |

### Phase 4：RAG 索引重建（优先级 P1）

| 步骤 | 任务 | 产物 | 预计耗时 |
|------|------|------|---------|
| 4a | 重建 FAISS/TF-IDF 索引 | `faiss.index` 或 `tfidf_matrix.npz` | 30-60min |
| 4b | 验证 Layer 3 兜底功能 | 测试报告 | 30min |

---

## 10. 预期收益

### 10.1 覆盖度提升

以 CML 测试案例中的 11 条 evidence 为基准：

| 层 | 命中 | 示例 |
|----|------|------|
| 当前（P1+P2 后） | 3/11 (27.3%) | splenomegaly, fatigue, night sweats |
| + B1 FindingNormalizer | **+5** (72.7%) | WBC→Leukocytosis, Hb→Decreased Hb, Plt→Thrombocytopenia, Basophils→Basophilia, Blasts→Elevated blast count |
| + B3 Pathognomonic | **+1** (81.8%) | Ph+/BCR-ABL1 |

### 10.2 性能预期

| 操作 | 延迟 |
|------|------|
| 正则解析（Layer 1） | <0.1ms |
| 查表 + loinc2hpo（Layer 2） | <0.5ms |
| RAG 兜底（Layer 3） | ~50-200ms |
| **单条 finding 端到端** | **<1ms（L1+L2 命中）** |

---

## 11. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LabQAR 参考范围不全 | 罕见检验无法归一化 | RAG Layer 3 兜底 + 逐步手工补充 |
| 正则模式不覆盖复杂表述 | 漏判 | 保守策略：未匹配的原样传递给 Embedding |
| 百分比阈值因地区/指南不同 | 少量误判 | 使用保守阈值 + 可配置 |
| loinc2hpo 注释不含所有检验 | 部分 LOINC 无 HPO 映射 | 3118 LOINC 已覆盖绝大多数常见检验 |
| RAG 索引重建耗时 | Layer 3 暂不可用 | Layer 2 已覆盖核心场景；索引重建独立于核心开发 |

---

## 12. 落地状态（2026-06-05 补记）

### 12.1 发现的缺口

代码（`knowledge/finding_normalizer.py`）与数据（`data/knowledge_raw/lab_reference_ranges.json`、
`loinc2hpo_annotations.json`、`unit_conversions.json`）此前已实现并就位，`controller` 也按
`config.lab_reference_ranges_json && config.loinc2hpo_json` 条件构造 `FindingNormalizer`。
但核查发现：

1. **三条配置路径默认 `None`，且 `eval_pipeline_medbullets.py` 与所有 `scripts/`、`tests/` 均未传入** →
   `FindingNormalizer` 在**完整 pipeline 中从未被构造**（dormant）。
2. 即便构造，`match_evidence_to_phenotypes` 只把归一化得到的 HPO 术语**追加**为一个新候选键；
   而 `controller._gather_atomic_findings` 按"原始事实"取匹配（`matches.get(raw)`），
   **漏掉了归一化产出的 HPO 术语**——导致数值化验仍走方向盲的嵌入误映射
   （`Temperature 100°F → Cold skin temperature`、`Pulse 120/min → Absent pulse`、
   `Hemoglobin 10 g/dL → hemoglobin <5 g/dl`）。

### 12.2 修复（已落地）

1. **接线**：`eval_pipeline_medbullets.py` 与 `verify_evidence_extraction.py` 的 config
   传入 `lab_reference_ranges_json / loinc2hpo_json / unit_conversions_json`，激活 `FindingNormalizer`。
2. **接入提取**：`controller._gather_atomic_findings` 改为两阶段：
   - **Stage 1（确定性）**：每条原子事实先过 `FindingNormalizer.normalize()`；
     异常→取其 `hpo_term`（方向正确，如 `35% blasts → Elevated blast count`、
     `Hemoglobin 10 g/dL → Decreased hemoglobin`）；
     **正常值/无法判向→直接跳过**（不再把正常生命体征喂给嵌入器，杜绝伪异常表型）。
   - **Stage 2（嵌入）**：归一化未识别的定性 finding（如 `night sweats`、`splenomegaly`、
     `erythematous rash`）才走受控词表嵌入匹配；无映射时无损回退原文。
3. **回归**：`tests/test_payload_slimming.py::test_atomic_findings_use_normalizer_and_skip_normal_vitals`
   锁定"异常化验取 HPO 术语 / 正常生命体征跳过 / 定性 finding 走嵌入"三类行为。
