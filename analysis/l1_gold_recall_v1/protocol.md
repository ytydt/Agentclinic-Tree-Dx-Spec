# L1 金标召回调研：协议与术语（`l1_gold_recall_v1`）

**状态**：阶段 A 锁定  
**队列**：DiagnosisArena `d2_seq100_v1`（100 例）  
**与上轮区别**：[`../l1_rank_gap_v1/`](../l1_rank_gap_v1/) 专攻 **排序**（B12 Pilot REJECT）；本协议专攻 **召回 / coverage**，禁止把排序臂结论直接当作召回结论。  
**交付边界**：调研 + 根因 + 设计 + 烟测规格；**不实现**、不改生产默认、本轮不跑数。

---

## 1. 决策锁定

| 项 | 选择 |
|----|------|
| 主口径 | **双漏斗拆分**：自动 `family_coverage=0.80` 只作起点 |
| 必须拆开 | 「mapper / 叶绑定失败」vs「树上无可用金标父 / 父未进入 L1 候选」 |
| 外部借鉴 | Track **B** 封闭补召回（主轨）+ Track **C** 开放扩族（探索，含 i-MedRAG/MAC/Dual） |

**现象锚点**（[`../l1_rank_gap_v1/l1_rank_gap_audit.md`](../l1_rank_gap_v1/l1_rank_gap_audit.md)）：全量自动 coverage **0.80**；`L1_MISS` **20** 例且 `parent_source=none`，与 mapper @2=0 高度重叠——**尚不能**写成「根本没有 L1 分支」。

---

## 2. 三层指标（审计可读金标；推理不读）

| 层 | 名称 | 定义 | 本轮角色 |
|----|------|------|----------|
| 1 | **AutoCoverage** | `v1_auto_parent` 下可接受父 ∈ `l1_posteriors` 集合 | 现报 **0.80**；起点，非终裁 |
| 2 | **TreeParentPresent** | 盲法/半自动：金标诊断是否存在至少一个临床可接受 L1 父挂在**该例树**上（不论是否进后验 Top 集） | 拆假 MISS 的关键层 |
| 3 | **L1CandidateRecall** | 可接受父 ∈ 运行时 L1 候选 / 后验支持集 | 真·召回终点（协议 bump 后） |

审计阶段可读金标与树标签；任何推理臂 / 选臂 **禁止**读评测金标（同论文执行计划作弊边界）。

---

## 3. 召回漏斗标签（每例唯一，优先序）

自上而下赋唯一桶：

1. **`MAPPER_UNBIND`**：树上存在临床可接受父（及/或金标近义叶），但 `v1_auto_parent` 因 mapper 叶未绑定 / 关系过严 / 同义启发式失败而记 `parent_source=none` → **假 AutoCoverage MISS**。  
2. **`TREE_PARENT_ABSENT`**：该例树上不存在可接受 L1 父（轴错位或金标轴未建族）→ **真缺父**。  
3. **`PARENT_NOT_IN_L1_SET`**：可接受父在树上，但未进入运行时 `l1_posteriors` / L1 候选支持集 → **真·候选召回失败**。  
4. **`L1_PRESENT_OK`**：AutoCoverage 与半自动父判定均成功（本审计的 20 例 MISS 中不应出现）。

中期分流：

- 主因 **`MAPPER_UNBIND`** → 召回扩族设计 **降优先**；转映射修复 / 叶生成 / 绑定。  
- 主因 **`TREE_PARENT_ABSENT` / `PARENT_NOT_IN_L1_SET`** → 强化 Track B/C 的 L1 扩召回。

---

## 4. 与论文执行计划对齐

对齐 [`PAPER_EXPERIMENT_EXECUTION_PLAN.md`](../../PAPER_EXPERIMENT_EXECUTION_PLAN.md) §13：

| 论文术语 | 本协议 |
|----------|--------|
| `L1 parent coverage` | 意图上 ≈ **TreeParentPresent ∧ L1CandidateRecall**；现产数字多为 **AutoCoverage**（`v1_auto_parent`） |
| 漏斗 `L1_MISS` | 论文：没有可接受 gold parent；本轮进一步拆成上表四桶，避免把映射失败写成召回失败 |
| `clean parent coverage` | 接近盲法 **TreeParentPresent**（本轮用半自动全量 20 例代理；完整盲法可 bump） |

**禁止**：用 AutoCoverage 单独宣称「系统缺少 L1 分支」或「召回只有 80%」。

---

## 5. 数据锚点

| 用途 | 路径 |
|------|------|
| AutoCoverage / `L1_MISS` 列表 | `analysis/l1_rank_gap_v1/l1_family_metrics.tsv` |
| case / mapper / tree | `logs/.../downstream_top2_w12_v1/` 与 `pipeline_remaining76_v1/annotate/` |
| 产出根 | `analysis/l1_gold_recall_v1/` |

---

## 6. 完成定义（本调研）

`analysis/l1_gold_recall_v1/` 下 A–G 齐备；用一句话钉死 80% 缺口主因属于哪一类；Track B 有可实现方案；Track C 含 i-MedRAG/MAC/Dual 迁移或 REJECT 理由。
