# L1 金标召回：烟测规格（只出规格，本轮不跑数）

**设计**：[`l1_gold_recall_design_v1.md`](l1_gold_recall_design_v1.md)  
**协议**：[`protocol.md`](protocol.md)  
**状态**：**规格锁定；禁止在本调研轮次实现/跑 Pilot**

---

## 1. 目的

验证 Track B（映射/父集）与 Track C（扩族）对 **真·召回指标** 的效应，并与排序臂、compat 臂分列。

---

## 2. 臂定义（建议 ID）

| 臂 ID | 轨 | 描述 | 实现触达（将来） |
|-------|----|------|------------------|
| `R0-baseline` | — | 现网 annotate + `v1_auto_parent` | 已有日志即可重算 |
| `R1-parent-from-leaf` | B2 | 评测父集改为树叶近义→祖先；推理不变 | 审计脚本 bump |
| `R2-mapper-bind-repair` | B1 | 映射回填/近邻绑叶 | mapper 或后处理 |
| `R3-gapfill-lite` | B3 | `branch_recall_gap_fill=on` | config |
| `R4-imedrag-family` | C1 | 建树前 i-MedRAG 式假设 + 归一挂 L1 | 新管线钩子 |
| `R5-mac-union-family` | C2 | 多列表并集归一 | 新钩子 |

**硬规则**：R1/R2 与 R4/R5 **分列报告**；禁止平均成单一「召回臂」。

---

## 3. 终点与护栏

### 主终点（协议 bump 后至少报两列）

| 指标 | 定义 |
|------|------|
| AutoCoverage | 旧 `v1_auto_parent`（对照） |
| TreeParentPresent | 半自动/盲法可接受父在树上 |
| L1CandidateRecall | 可接受父 ∈ `l1_posteriors` |

对 `R1`：允许 AutoCoverage 定义切换，但须 **双列** 旧口径。

### 护栏

| 护栏 | 阈值建议 |
|------|----------|
| option @2（官方 mapper） | 相对 R0 下降 ≤ 0.02（全量）或 Pilot 双侧警示 |
| 成本 | R4/R5 须报 LLM calls / retrieve 次数；超过 R0×3 则默认不整合 |
| 金标泄漏 | 运行时 payload 禁金标字段（沿用 `assert_no_gold_leak`） |
| MECE | R4/R5 新 L1 须过归一；失败率写入审计 |

### 次终点

- 漏斗桶计数：`MAPPER_UNBIND` / `TREE_PARENT_ABSENT` / `PARENT_NOT_IN_L1_SET`  
- family @1/@2（覆盖子集）— **只作旁注**，不作召回成功判据  
- compat_parallel option @1 — 旁注联动，非召回主判据

---

## 4. 队列与阶段门

| 阶段 | n | 通过门（建议） |
|------|--:|----------------|
| Pilot24 | 24 | R1 或 R2：`MAPPER_UNBIND` 在自动 MISS 子集上降 ≥50% **或** AutoCoverage +≥0.08；option @2 护栏通过 |
| all100 | 100 | 确认 Pilot 方向；R4 仅在 `TREE_PARENT_ABSENT`≥1 的子集上单独报 |

**REJECT 例**

- R4 全量开启但 TreeParentPresent 不升、成本×3 → REJECT 默认整合。  
- R2 抬 AutoCoverage 但 option @2 大跌 → REJECT 或收紧绑定。  
- 任何臂读金标选族 → 硬 REJECT。

---

## 5. 明确不做（本规格轮）

- 不实现代码、不改生产默认。  
- 不跑 Pilot24 / all100。  
- 不把 L1-Calib-B12 并入本烟测。

---

## 6. 交付检查（将来实现轮）

- [ ] 臂开关与审计脚本版本写入 summary JSON  
- [ ] 双口径 coverage 表  
- [ ] 映射臂 vs 扩族臂分节  
- [ ] 成本前沿一行  

产出完成：本规格文件（调研轮结束）。
