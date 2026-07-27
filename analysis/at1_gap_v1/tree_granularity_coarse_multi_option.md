# 阶段 2c-Coarse：单叶多选项过粗

**表**：`coarse_leaf_audit.tsv`  
**审核包**：`audit_packets/{case_id}.json`  
**Agent 审核表**：`granularity_audit_sheet.jsonl`

## 1. 自动检出

| 范围 | 自动 coarse 阳性 |
|------|-----------------:|
| A 集（@2∧¬@1） | **10/19** |
| 定义 | ≥2 选项的 matched leaves 相交，且含 gold 字母 |

## 2. Cursor-Agent 审核结果（A 集 coarse 自动阳性 10 例）

| verdict | n | case_id |
|---------|--:|---------|
| `coarse_leaf_multi_option`（通过） | **7** | 29, 90, 117, 151, 163, 186, 205 |
| `mapper_overmerge` | 1 | 59 |
| `reject` | 2 | 120, 177 |

- Agent 通过率：7/10  
- 其中 `needs_l3=true`：7（与通过集一致）  
- 细分概念上界：若过粗叶下按选项可分轴生成 L3 且 gold 子叶独占，则上述 7 例具备 **@1 恢复上界**（文案计数，未真跑生成）。

## 3. 典型模式

1. **解剖/部位轴过粗**（90 caruncular vs amelanotic melanoma）  
2. **药物/诱因轴过粗**（205 methimazole vs drug-induced ANCA）  
3. **分子实体下表型过粗**（163 FIP1L1-PDGFRA）  
4. **假阳性**：选项为上下位同绑（120）或 gold 为 `complication_of`（177）→ 不是 L3 亚型细分能单独解决

## 4. 设计含义

- Coarse 通过占比（7/19≈37% of A）→ 融合方案 **必须**含 `AdaptiveSubdivideUnderL2`。  
- **禁止**把 support 重排当作 Coarse 的唯一对策。  
- 与 Fine 可共存；验收须分列。

产出：本文件 + `coarse_leaf_audit.tsv` + 审核表。
