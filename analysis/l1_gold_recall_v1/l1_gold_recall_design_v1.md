# L1 金标召回：方案设计 v1

**根因**：[`l1_gold_recall_rootcause.md`](l1_gold_recall_rootcause.md)  
**迁移卡**：[`external_l1_recall_transfer_cards.md`](external_l1_recall_transfer_cards.md)  
**默认**：只从 Track B 选整合主轨；Track C 分列探索。与 compat_parallel / L1-Calib-B12 **解耦**（召回在树构建或 L1 冻结前 / 评测绑定层）。

---

## Track B — 封闭主轨（推荐默认）

### B1. MapperBind-Repair（P0）

| 项 | 内容 |
|----|------|
| 目标 | 降低假 `L1_MISS`；抬 AutoCoverage 至接近 TreeParentPresent |
| 做法 | （1）`relation=equivalent/related` 强制尝试叶 ID 回填；（2）空 `matched_leaf_ids` 时对树叶做规范化字符串/嵌入近邻；（3）禁止高置信 `unrelated` 在存在近精确叶时无抽检通过 |
| 不改 | 推理路径、L1 后验、生产默认开关可先仅审计层重算 |
| 成功像 | 18 例 UNBIND 中大部分 AutoCoverage→1；option @k 可能连带上升 |
| 风险 | 过宽绑定抬假阳性 option；须保留 typed 冲突护栏 |

### B2. Leaf→Parent 评测父集（P0，审计协议 bump）

| 项 | 内容 |
|----|------|
| 目标 | 协议层 `TreeParentPresent` / 改进 AutoCoverage 定义 |
| 做法 | 金标文本与**全部树叶**近义匹配 → 取 L1 祖先为可接受父（不依赖 mapper） |
| 角色 | 度量修复；可与 B1 并行；**推理仍禁金标** |
| 成功像 | 报告双列：旧 AutoCoverage vs 叶反推 coverage |

### B3. AxisGapFill-lite（P2）

| 项 | 内容 |
|----|------|
| 目标 | 补 mandatory 空域（`branch_recall_gap_fill`） |
| 预期 | 对 18 例假 MISS **基本无效**；对真缺父 **有限**（若缺父不在 mandatory 表则无用） |
| 角色 | 小消融；非默认 |

### B4. 强制轴极注入（P2，针对已知综合征）

| 项 | 内容 |
|----|------|
| 目标 | 对反复轴错位病种注入固定 L1 极 |
| 范围 | 仅配置表白名单；禁止金标驱动 |

**默认推荐整合顺序**：先 **B2（度量）** 与 **B1（映射）** 烟测；B3/B4 仅当盲法确认仍有 `TREE_PARENT_ABSENT` 堆积时启用。

---

## Track C — 开放扩族（探索）

### C1. i-MedRAG-style Family Hypothesize（高潜力环路）

1. 建树前：vignette → 多轮 follow-up 检索（共享 KB）。  
2. 抽取疾病/家族假设列表（召回导向）。  
3. **归一**：映射到现有 L1 标签或创建新 L1 节点；失败丢弃。  
4. 再进入常规 BranchCreator / BFS。  
5. 分列成本（rounds×queries×retrieve）。

**适用**：case 67、231 类轴错位；**不对**全量 100 无门控开启。

### C2. MAC/Dual 病名并集 → 家族对齐

- 多角色或 forward 列表 → 并集 → 同 C1 归一。  
- REJECT：整段多医生嵌建树作生产默认。

### C3. OpenRegen（与上轮一致）

- 允许提议新家族名；归一失败丢弃；禁止与封闭排序混报。

**Track C REJECT 为默认生产路径的理由**：本批 90% 缺口非真缺父；开放扩族成本高、MECE 风险大、归因难。

---

## 非目标（本设计明确不做）

- 把 B12 / SupportRerank 当 coverage 修复。  
- 推理时读金标选家族。  
- 用官方私有 MedRAG 语料替换共享 KB 作可比主表。

---

## 与烟测规格的接口

见 [`l1_gold_recall_smoke_spec.md`](l1_gold_recall_smoke_spec.md)：映射修复臂与扩族臂 **分列**；主终点用拆分后的 TreeParentPresent / L1CandidateRecall（协议 bump 后）。

产出完成：本文件。
