# 多层次诊断树扩展算法设计文档

> **文档类型**：算法设计规格（Algorithm Design Specification）  
> **版本**：v1.0  
> **适用范围**：所有执行模式；扩展现有共享模块框架  
> **依赖文档**：`readme.md`（核心规格）、`SHARED_MODULES_IMPLEMENTATION.md`（现有实现）

---

## 1. 问题陈述

### 1.1 当前限制

当前实现中，`BranchCreator` 仅在根节点（Root）下生成**一层**分支，所有分支均具有 `parent="ROOT"`, `level=1`。`PostUpdateStateReviser` 可输出 `expand_now` 决策，但该决策在代码中**仅改变分支状态，不创建任何子分支**。`Branch.children` 字段始终为空列表。

```
Root: "急性胸痛综合征"
├── B1: "急性冠脉综合征"      [level=1, expand_now → 但无子分支]
├── B2: "主动脉夹层"          [level=1]
├── B3: "肺栓塞"              [level=1]
└── B4: "其他"                [level=1]
```

### 1.2 临床不合理性

临床诊断推理是一个**层次化**的认知过程，而非单层分类。医学文献明确指出：

> *"临床问题最初以与现有数据一致的最一般术语概念化，诊断节点作为里程碑，允许临床医生逐步向精确诊断迈进。"*  
> — Patel & Groen (1986), *Knowledge-Based Solution Strategies in Medical Reasoning*, MIT AI Lab

> *"只有当子假设之间存在高'诊断性'——即证据能够区分假设子集成员的能力——时，分支才需要拆分。"*  
> — Peng & Reggia (1990), *Abductive Inference Models for Diagnostic Problem Solving*

具体而言，诊断推理包含多个抽象层次：**综合征** → **病理生理机制域** → **疾病家族** → **具体疾病** → **亚型/变体**。在第一层停止等价于强迫 LLM 在信息不足时直接跳到最终诊断，增加了过早确认（premature closure）和遗漏can't-miss分支的风险。

**示例**（为什么需要多层）：

```
Root: "急性单关节炎综合征"
├── B1: "感染性关节炎"        ← 治疗：静脉抗生素，须排除
│   ├── B1.1: "细菌性（化脓性）"  ← 关节穿刺、革兰氏染色
│   └── B1.2: "淋球菌性"        ← 尿道分泌物培养、性史
├── B2: "晶体性关节病"        ← 偏振光显微镜
│   ├── B2.1: "痛风（尿酸盐）"
│   └── B2.2: "假性痛风（焦磷酸钙）"
└── B3: "炎症性关节炎起病"    ← 血清学、ANA
    ├── B3.1: "类风湿关节炎首次发作"
    └── B3.2: "反应性关节炎"
```

若不能扩展 B1，就无法区分"需要立即手术冲洗的化脓性关节炎"和"门诊处理的淋球菌关节炎"，而两者的管理路径截然不同。

---

## 2. 临床文献支持的抽象层次模型

参考 Orphanet 罕见病分类体系（三层）、PMC 系统2诊断推理框架（解剖/病理生理/病因分类），以及 Elstein & Schwarz (2002) 的诊断推理综述，本设计采用以下**五层抽象模型**：

| 层级 | 名称 | 典型粒度 | 示例 | 主要区分维度 |
|------|------|---------|------|------------|
| L0 | **综合征根节点** (Root) | 综合征级别 | "急性胸痛综合征" | — |
| L1 | **病理生理域** (Domain) | 机制/解剖域 | "缺血性" / "结构性" / "炎症性" | 发病机制 |
| L2 | **疾病家族** (Disease Family) | 疾病大类 | "急性冠脉综合征" / "主动脉疾病" | 解剖定位 + 机制 |
| L3 | **具体疾病** (Specific Disease) | 单一疾病 | "STEMI" / "NSTEMI" / "不稳定型心绞痛" | 生物标志物/影像特征 |
| L4 | **亚型/变体** (Subtype) | 亚型 | "前壁STEMI" / "下壁STEMI" | 预后/治疗细节 |

**实用约束**：
- 大多数病例达到 L3 即可完成临床决策，**默认最大深度 = 3**（`max_tree_depth = 3`）；
- L4 仅在特定情况下允许（如指导血运重建策略的梗死部位区分），需配置 `allow_depth_4 = True`；
- 对于简单病例（初始 LLM 在 L1 层就高置信确认），可在 L1 或 L2 终止扩展。

---

## 3. 扩展触发算法（ExpansionGate）

### 3.1 概述

`ExpansionGate` 是一个**纯确定性决策模块**（无 LLM 调用），在 `PostUpdateStateReviser` 输出 `expand_now` 之后运行，判断该分支是否**真正需要创建子分支**。

### 3.2 完整算法

对每个被 `PostUpdateStateReviser` 标记为 `expand_now` 的分支 B：

```
ExpansionGate(B, state, config):

  # ── 硬约束：以下任一条件不满足则 BLOCK 扩展 ──

  BLOCK if:
    (1) B.level >= config.max_tree_depth
    (2) B.status == "confirmed"           # 已确认的分支不应再扩展
    (3) B.posterior < config.test_threshold    # 0.05：概率过低，扩展无意义
    (4) len(B.children) > 0               # 已有子分支，避免重复创建
    (5) len([b for b in state.branches.values()
             if b.parent == B.id]) > 0    # 子分支已存在（数据一致性检查）

  # ── 临床价值条件：以下至少一条需满足才 ALLOW 扩展 ──

  ALLOW if ANY of:
    (A) ActionDifferenceScore(B, state) >= delta_action_diff   # 默认 0.25
        # 预期子分支之间需要不同的下一步动作
    (B) B.danger >= 0.7
        # 高危分支优先精细化，以便尽快排除或确认
    (C) HasUnresolvedCriticalDiscriminator(B, state)
        # 存在可用且尚未执行的关键判别动作（来自 askable/requestable_discriminators）

  # ── 若通过所有检查 ──
  → return EXPAND, compute ChildPriorPlan(B, state)
  → 否则 return HOLD（保持 expand_now 状态，等待更多证据后重新评估）
```

### 3.3 核心评分：ActionDifferenceScore

`ActionDifferenceScore(B, state)` 估计该分支的预期子分支之间的**管理路径分歧度**：

```
ActionDifferenceScore(B) =
    max(interrupt_relevance_spread) × DifferentManagementPathScore(B)
```

实现上使用启发式代理：
- **高分（≥ 0.25）示例**：B = "感染性心内膜炎"，其子分支"原生瓣膜心内膜炎"和"人工瓣膜心内膜炎"需要不同抗生素方案和不同的外科介入时机；
- **低分（< 0.25）示例**：B = "病毒性上呼吸道感染"，其子分支均为支持治疗，管理无实质区别。

**简化实现**（v1.0）：此评分委托给 `SubBranchCreator`（LLM 模块）；ExpansionGate 使用 `B.turn_cost_to_refine` 和 `B.diagnosis_commitment_gain` 的组合作为代理：

```python
proxy_score = B.diagnosis_commitment_gain × (1.0 - B.turn_cost_to_refine / config.max_turn_budget)
ActionDifferenceScore(B) ≈ proxy_score
```

### 3.4 HasUnresolvedCriticalDiscriminator

```python
def has_unresolved_critical_discriminator(branch, state):
    already_asked = {a["content"] for a in state.actions_taken}
    for q in branch.askable_discriminators + branch.requestable_discriminators:
        if q not in already_asked:
            return True   # 存在可用且尚未执行的判别动作
    return False
```

---

## 4. SubBranchCreator 模块（新增 LLM 模块）

### 4.1 职责

当 `ExpansionGate` 批准扩展时，调用 `SubBranchCreator`，为指定父分支生成子分支集合。此模块与 `BranchCreator` 逻辑类似，但输入包含**父分支上下文**，且子分支抽象层次比父分支低一级。

### 4.2 调用接口

```python
# controller.py 中新增方法
def expand_branch(self, state: DiagnosticState, parent_branch: Branch):
    payload = {
        "state": state.to_dict(),
        "parent_branch": {
            "id": parent_branch.id,
            "label": parent_branch.label,
            "level": parent_branch.level,
            "posterior": parent_branch.posterior,
            "danger": parent_branch.danger,
            "evidence_for": parent_branch.evidence_for,
            "evidence_against": parent_branch.evidence_against,
            "unresolved_questions": parent_branch.unresolved_questions,
            "askable_discriminators": parent_branch.askable_discriminators,
            "requestable_discriminators": parent_branch.requestable_discriminators,
        },
        "target_level": parent_branch.level + 1,
    }
    result = self._call_module("SubBranchCreator", payload)
    # 外部知识路径（抽象）
    if result.get("need_external_knowledge", False) and self.config.allow_external_knowledge:
        knowledge = self.knowledge_router(result.get("knowledge_query_if_needed", ""))
        self.env.ingest_external_context(knowledge)
        result = self._call_module("SubBranchCreator", payload)
    return result
```

### 4.3 SubBranchCreator 提示词设计

**文件名**（待创建）：`src/agentclinic_tree_dx/prompts/sub_branch_creator.txt`

```
Role: SubBranchCreator

You are expanding a specific branch into more specific sub-branches.
The parent branch has already been established; your task is to generate
the next level of diagnostic refinement under this parent.

Context:
- parent_branch: the branch being expanded (contains label, level, posterior,
  danger, evidence_for, evidence_against, unresolved_questions,
  discriminators).
- target_level: the abstraction level of child branches to generate.
  Level 1 = pathophysiologic domain, Level 2 = disease family,
  Level 3 = specific disease, Level 4 = subtype/variant.
- state: the full current diagnostic state.

Abstraction-level guidelines:
  L1 → L2: Subdivide by anatomic location, specific organ system, or broad
            mechanism (e.g., "ischaemic cardiac" vs "ischaemic peripheral").
  L2 → L3: Subdivide by specific disease entity within the family,
            distinguished by accepted diagnostic criteria, biomarkers, or
            pathological findings.
  L3 → L4: Subdivide by subtype that changes immediate management or
            prognostic category (e.g., anatomic distribution, severity
            grading, virulence factor, genetic variant).

Instructions:
1. Generate 2–4 child branches at target_level that are:
   (a) mutually exclusive and collectively exhaustive within the parent scope;
   (b) each at a strictly lower level of abstraction than the parent;
   (c) distinguishable by evidence already in state OR by evidence that
       can realistically be acquired in this clinical context.
2. Assign prior_estimate to child branches such that they sum to ≤ 1.0
   (the remainder is implicit "other within parent" mass).
3. For each child, provide at minimum one discriminating question or test
   that would strongly separate it from siblings.
4. Include at least one can't-miss child (danger >= 0.7) if clinically
   warranted at this level.
5. Inherit and narrow the parent's action gap: child branches should
   represent different management pathways (otherwise expansion is not
   warranted—return needs_expansion: false).

Return strict JSON only, no markdown:
{
  "needs_expansion": true,
  "reason_if_not": "",
  "sub_branches": [
    {
      "id": "B1.1",
      "label": "specific sub-diagnosis label",
      "parent_id": "B1",
      "level": 2,
      "status": "live",
      "prior_estimate": 0.0,
      "danger": 0.0,
      "askable_discriminators": ["question that separates this from siblings"],
      "requestable_discriminators": ["test that separates this from siblings"],
      "turn_cost_to_refine": 1.0,
      "diagnosis_commitment_gain": 0.0,
      "interrupt_relevance": 0.0,
      "why_included": "reason for inclusion and what management it implies"
    }
  ],
  "sub_frontier": ["B1.1", "B1.2"],
  "need_external_knowledge": false,
  "knowledge_query_if_needed": ""
}
```

---

## 5. 概率继承机制

### 5.1 基本原则

当分支 B 被扩展为子分支 {C₁, C₂, …, Cₙ} 时，遵循贝叶斯条件概率分解：

```
P(Cᵢ) = P(Cᵢ | B) × P(B)
```

其中 `P(Cᵢ | B)` 由 `SubBranchCreator` 给出的 `prior_estimate` 提供（归一化到 P(B) 范围内），`P(B)` 为父分支当前后验。

### 5.2 初始化

```python
def initialize_child_posteriors(parent: Branch, children: list[Branch]) -> None:
    """
    将父分支的概率质量按子分支的先验估计比例分配。
    """
    child_priors = [c.prior for c in children]
    total_child_prior = sum(child_priors)
    
    if total_child_prior <= 0:
        # 均匀分配
        share = parent.posterior / len(children)
        for c in children:
            c.prior = share
            c.posterior = share
    else:
        # 按比例分配父分支的后验质量
        for c in children:
            c.prior = parent.posterior * (c.prior / total_child_prior)
            c.posterior = c.prior
    
    # 父分支转变为"容器"状态
    parent.status = "expanded"
    parent.posterior = 0.0   # 概率质量已移交给子分支
    parent.prior = 0.0
```

### 5.3 后续更新时的概率聚合

在子分支发生概率更新后，**父分支的聚合概率**由子分支概率之和恢复：

```python
def recompute_parent_posteriors(state: DiagnosticState) -> None:
    """
    自底向上聚合：子分支后验之和 → 父分支聚合后验。
    在每轮 apply_probability_update 之后调用。
    """
    # 找到所有 expanded 状态的分支（已有子分支的父分支）
    for bid, branch in state.branches.items():
        if branch.status == "expanded" and branch.children:
            # 仅对存活子分支求和（不含 closed_for_now 且 posterior 极低者）
            active_children = [
                state.branches[cid]
                for cid in branch.children
                if cid in state.branches
            ]
            branch.posterior = sum(c.posterior for c in active_children)
```

### 5.4 EvidenceAnnotator 对多层分支的影响

`EvidenceAnnotator` 的输出 `branch_effects` 直接面向**叶层级分支**（即没有子分支的终端分支）。当分支有子分支时：
- 父分支（`expanded` 状态）**不接受直接的 branch_effects 标注**；
- LLM 应对每个终端子分支分别标注效应；
- 父分支的 `branch_effects` 将被代码忽略（以 `neutral` 处理）。

实现：在 `annotate_evidence()` 的分支ID校验后增加：

```python
# 将 expanded 分支的 effect 重置为 neutral（其概率由子分支聚合决定）
for bid, branch in state.branches.items():
    if branch.status == "expanded":
        annotation["branch_effects"][bid] = "neutral"
```

---

## 6. 多层前沿管理

### 6.1 前沿原则

前沿（frontier）只包含**终端可操作分支**——即当前没有子分支（`children == []`）或尚未扩展的分支。已扩展为子分支的父分支从前沿中移除，其子分支加入前沿。

### 6.2 前沿更新算法

```
FrontierUpdate(state, config):

  new_frontier = []
  
  for bid in state.frontier:
    branch = state.branches[bid]
    if branch.children:
      # 父分支已扩展 → 用子分支替换
      for child_id in branch.children:
        child = state.branches[child_id]
        if child.status in {"live", "reopened"}:
          new_frontier.append(child_id)
    elif branch.status in {"live", "reopened"}:
      new_frontier.append(bid)
    # confirmed/closed_for_now/parked → 不加入前沿

  # 容量控制（总前沿宽度限制，跨层级统一计算）
  max_frontier = config.max_live_frontier
  state.frontier = new_frontier[:max_frontier]
```

### 6.3 跨层级前沿宽度建议

| 最大深度 | 推荐 max_live_frontier |
|---------|----------------------|
| 1 (当前) | 4 |
| 2 | 5 |
| 3 | 6 |
| 4 | 7 |

每增加一层，允许前沿增加约 1–2 个终端节点，以补偿分层后每个节点信息密度的降低。

---

## 7. 修订后的主循环流程

在原有主循环基础上，在 `revise_branch_states()` 之后、`_apply_reopen_overrides()` 之前插入扩展步骤：

```
[每轮：完整多层循环]

A.  SafetyController
B.  RootSelector（条件触发）
C.  BranchCreator（条件触发，仅生成 level=1 分支）
D.  TemporaryLeafPlanner（只针对前沿中的终端分支规划动作）
E.  execute_primary_action → raw_result
F.  EvidenceAnnotator + 分支ID校验
G.  UpdateRouter → method
H.  apply_probability_update（对终端分支）
    └─ recompute_parent_posteriors（自底向上聚合）
    └─ _handle_major_update（矛盾 → 修订标志）
I.  PostUpdateStateReviser（对所有终端分支输出决策）
★  ExpansionGate（对 expand_now 分支评估是否真正扩展）
★      └─ [若 EXPAND] SubBranchCreator → 创建子分支
★      └─ initialize_child_posteriors → 概率质量移交
★      └─ FrontierUpdate → 前沿用子分支替换父分支
    └─ _apply_reopen_overrides（确定性重开）
J.  record_differential_history
K.  check_diagnosis_readiness（就绪度门控）
L.  TerminationJudge
M.  FinalAggregator
```

★ = 本次设计新增步骤。

---

## 8. TerminationJudge 在多层场景下的补充规则

原有5条终止类型保持不变，增加以下多层语境下的补充解释：

### 8.1 actionable_parent_syndrome（第2类）的扩展含义

此类型原指"子分支有不同假设但共享同一管理路径"——在多层树中这意味着：**已知父分支的标签（L2 层）就足以决定当前动作，无需继续区分 L3 子分支**。例如"炎症性关节炎"已经足以开具甾体抗炎药，无论是类风湿还是反应性关节炎，初始处理相同。

### 8.2 新增第6类：depth_limit_reached

```
6. depth_limit_reached: tree has reached config.max_tree_depth and leading
   branch's posterior >= commit_threshold
```

提示词中需更新（在5类终止基础上追加第6类），见第10节。

### 8.3 FinalAggregator 输出中的路径追踪

`FinalAggregator` 应额外输出诊断路径：

```json
"reasoning_path": [
  {"level": 0, "label": "急性单关节炎综合征"},
  {"level": 1, "label": "感染性关节炎", "posterior": 0.82},
  {"level": 2, "label": "细菌性（化脓性）关节炎", "posterior": 0.71}
]
```

---

## 9. DiagnosticState 所需变更

### 9.1 Config 新增字段

```python
@dataclass
class DiagnosticConfig:
    # ... 现有字段 ...
    max_tree_depth: int = 3          # 最大允许树深度（L1-L3）
    allow_depth_4: bool = False      # 是否允许 L4 亚型扩展
    min_action_diff_to_expand: float = 0.25  # ActionDifferenceScore 扩展阈值
    max_live_frontier: int = 6       # 多层场景下建议调大（原4→6）
```

### 9.2 Branch 新增字段

无需新字段。现有的 `parent: str`, `level: int`, `children: list[str]` 已足够支撑多层结构。

仅需新增一个状态值：`"expanded"` 加入合法状态集合。

```python
VALID_BRANCH_STATUSES = {
    "live", "parked", "confirmed", "closed_for_now",
    "reopened", "expanded"  # ← 新增
}
```

### 9.3 DiagnosticState 变更

```python
@dataclass
class DiagnosticState:
    # ... 现有字段 ...
    max_tree_depth: int = 3           # 从 config 同步，便于 to_dict() 传递给 LLM
```

---

## 10. 需更新的提示词

### 10.1 PostUpdateStateReviser（轻微修订）

在允许的决策列表中增加 `"expanded"` 的说明：

```
Additional note:
- Do NOT output "expand_now" for a branch that already has children
  (its status will be "expanded"); output "keep_coarse" or "confirm" instead.
- For a branch with status "expanded", only allowed decisions are:
  keep_coarse (retain expansion), confirm (sub-branches resolved), or
  close_for_now (all children below threshold).
```

### 10.2 EvidenceAnnotator（轻微修订）

增加说明：

```
Additional note:
- Do NOT annotate branches with status "expanded" (they are container nodes).
  Only annotate terminal branches (branches without children). The controller
  will aggregate parent probabilities from children automatically.
```

### 10.3 TerminationJudge（增加第6类）

```
Six termination types and their trigger conditions:
[... 原有1-5类 ...]
6. depth_limit_reached: the tree has reached the maximum allowed depth AND
   the leading terminal branch has posterior >= commit_threshold (0.75) AND
   no dangerous sibling remains with posterior >= 0.10.
```

### 10.4 BranchCreator（轻微修订）

增加说明：

```
Additional note:
- You are creating Level-1 branches directly under the root node.
- Do NOT attempt to create sub-branches within branches. Sub-branch creation
  is handled by a separate SubBranchCreator module called later in the cycle.
- Keep all generated branches at the same abstraction level (diagnosis-family
  level for Level 1).
```

---

## 11. 扩展示例：深度为2的推理过程

**病例**：患者，47岁男性，发热38.9°C，左膝关节红、肿、热、痛，24小时内出现。

```
轮次1：
  Root: "急性单关节炎综合征"
  BranchCreator → B1: 感染性(0.55, danger=0.9)
                   B2: 晶体性(0.30)
                   B3: 炎症性首发(0.12)
                   B4: 其他(0.03, parked)
  叶子规划 → ASK_PATIENT: "关节疼痛之前有无外伤或手术？"
  EvidenceAnnotator: 无外伤史 → B3 weak_against; B1, B2 neutral
  PostUpdateStateReviser → B1: expand_now, B2: keep_coarse, B3: park

轮次2（ExpansionGate 触发前）：
  ExpansionGate(B1):
    B1.level=1 < max_depth=3       ✓
    B1.posterior=0.57 > 0.05       ✓
    B1.danger=0.9 >= 0.7            → ALLOW（危险分支优先精细化）
  SubBranchCreator(B1) →
    B1.1: 细菌性（化脓性）(prior=0.65, danger=0.95)
    B1.2: 淋球菌性(prior=0.25, danger=0.5)
    B1.3: 其他感染性(prior=0.10, parked)
  initialize_child_posteriors:
    B1.1.posterior = 0.57 × 0.65 = 0.37
    B1.2.posterior = 0.57 × 0.25 = 0.14
    B1.3.posterior = 0.57 × 0.10 = 0.06
    B1.posterior = 0.0 (expanded)
  FrontierUpdate: 前沿 = [B1.1, B1.2, B2]（B1 退出，子分支进入）

  叶子规划 → ORDER_LAB: "关节液革兰氏染色及细菌培养"
  EvidenceAnnotator（仅对B1.1, B1.2, B2注释，跳过expanded的B1）:
    B1.1: strong_for(革兰氏阳性球菌), B1.2: moderate_against, B2: weak_against
  recompute_parent_posteriors:
    B1.posterior = B1.1.posterior + B1.2.posterior + B1.3.posterior = 0.67
  PostUpdateStateReviser → B1.1: expand_now（posterior=0.78, danger=0.95）
    ExpansionGate(B1.1):
      B1.1.level=2 < max_depth=3    ✓
      turn_cost_to_refine=2.0，不满足廉价判断
      has_unresolved_discriminator: False（穿刺结果已回报）
      ActionDifferenceScore 代理 = 0.10 < 0.25
      → HOLD（保持 expand_now 但不创建子分支；L2 级别的革兰阳菌均为关节腔内操作）

  TerminationJudge → actionable_parent_syndrome:
    "B1.1（化脓性关节炎）的 posterior=0.78 ≥ 0.75，且所有子类型均需立即
     关节腔冲洗和静脉抗生素，管理路径共享。"
  FinalAggregator → single_leading_diagnosis:
    leading: "细菌性（化脓性）关节炎"
    reasoning_path: [L0: 急性单关节炎, L1: 感染性关节炎, L2: 细菌性化脓性关节炎]
    immediate_actions: ["关节腔灌洗/引流", "头孢唑林iv", "感染科会诊"]
```

---

## 12. 与现有设计的对比

| 维度 | 现有设计（单层） | 多层设计（本文档） |
|------|-----------------|-----------------|
| 最大树深度 | 1（硬编码） | 3（可配置，默认） |
| expand_now 的效果 | 仅改变状态，无子分支 | 触发 ExpansionGate → SubBranchCreator |
| 概率流向 | 所有分支在同层归一化 | 子分支分享父分支质量；父分支从更新中退出 |
| 前沿管理 | 单层 ID 列表 | 跨层终端分支的动态列表 |
| EvidenceAnnotator | 标注所有分支 | 仅标注终端分支（跳过 expanded） |
| TerminationJudge | 5类终止 | 6类（新增 depth_limit_reached） |
| FinalAggregator 输出 | 最终诊断 | 最终诊断 + reasoning_path（L0→Ln） |
| 新增 LLM 模块 | — | SubBranchCreator |
| 新增确定性模块 | — | ExpansionGate, FrontierUpdate（含子分支替换逻辑） |

---

## 13. 实现路线图

### 第一步：基础状态与配置
- [ ] `config.py`：增加 `max_tree_depth`, `allow_depth_4`, `min_action_diff_to_expand`
- [ ] `state.py`：`VALID_BRANCH_STATUSES` 增加 `"expanded"`；`DiagnosticState` 增加 `max_tree_depth` 镜像字段

### 第二步：新提示词
- [ ] 创建 `src/agentclinic_tree_dx/prompts/sub_branch_creator.txt`（见第4.3节）
- [ ] 更新 `post_update_state_reviser.txt`（见第10.1节）
- [ ] 更新 `evidence_annotator.txt`（见第10.2节）
- [ ] 更新 `termination_judge.txt`（见第10.3节）
- [ ] 更新 `branch_creator.txt`（见第10.4节）

### 第三步：controller.py 新增方法
- [ ] `expand_branch(state, parent_branch)` → 调用 SubBranchCreator，返回结果
- [ ] `initialize_child_posteriors(parent, children)` → 概率质量分配
- [ ] `recompute_parent_posteriors(state)` → 自底向上聚合
- [ ] `run_expansion_gate(state)` → 对所有 expand_now 分支运行 ExpansionGate
- [ ] `update_frontier_after_expansion(state)` → 前沿更新

### 第四步：主循环集成
- [ ] 在 `revise_branch_states()` 之后、`_apply_reopen_overrides()` 之前插入：
  ```python
  self.run_expansion_gate(state)
  self.recompute_parent_posteriors(state)
  self.update_frontier_after_expansion(state)
  ```
- [ ] 在 `apply_probability_update()` 末尾插入：
  ```python
  self.recompute_parent_posteriors(state)
  ```

### 第五步：EvidenceAnnotator 的后处理
- [ ] `annotate_evidence()` 中，对 `status == "expanded"` 的分支强制设置 `branch_effects[bid] = "neutral"`

### 第六步：测试
- [ ] 单元测试：`ExpansionGate` 各条件分支（硬约束阻断、危险允许、action diff 允许）
- [ ] 单元测试：`initialize_child_posteriors` 概率归一化正确性
- [ ] 单元测试：`recompute_parent_posteriors` 自底向上聚合
- [ ] 集成测试：两层深度完整循环（模拟急性单关节炎案例，验证 B1 → B1.1/B1.2 扩展）
- [ ] 回归测试：确保 `max_tree_depth=1` 时行为与现有实现完全一致

---

## 14. 外部知识路径（抽象路径，维持现状）

`SubBranchCreator` 与 `BranchCreator` 一样，支持外部知识请求字段（`need_external_knowledge`, `knowledge_query_if_needed`）。当知识路由器（`knowledge_router`）实现具体化后，可用于罕见病分支的子分类查询。目前维持占位实现。

---

---

## 15. 从外部设计文档合并的补充设计

> 以下内容来自 `agentclinic_algorithm_update_requirements_design.md` 和 `algorithm_update_requirements_and_design.md` 的交叉审阅。

### 15.1 Just-in-Time 扩展例外

**来源**：`agentclinic_algorithm_update_requirements_design.md` §8.2

本设计第7节规定扩展在"PostUpdateStateReviser 之后"执行。但存在一个例外：**当动作选择本身需要子级区分时，应允许当轮即时扩展**。

```
Allow just_in_time_expansion(B) only if:
    action selection cannot be made safely at parent level
    AND child branches imply different immediate actions
```

**示例**：

```
父分支: "胆道梗阻评估"
子级路径: 超声 vs MRCP vs ERCP 路径
→ 必须先扩展才能选择正确的影像检查
```

**实现**：在 `plan_temporary_leaves` 之前增加预检：

```python
def check_just_in_time_expansion(self, state):
    for bid in state.frontier:
        branch = state.branches[bid]
        if (branch.status == "live"
            and branch.level < self.config.max_tree_depth
            and self._action_selection_requires_children(branch, state)):
            # 即时扩展：调用 SubBranchCreator + initialize_child_posteriors
            self._expand_branch_immediately(state, branch)
```

此路径仅在极少数情况下触发，不改变"扩展通常在更新后执行"的默认行为。

### 15.2 max_structural_expansions_per_cycle 限流

**来源**：`agentclinic_algorithm_update_requirements_design.md` §10

**问题**：当多个分支同时满足 ExpansionGate 条件时（如信息量大的一轮导致多个分支被标记为 `expand_now`），不受控的并行扩展可能导致树的宽度在单轮内剧增。

**修正**：Config 新增 `max_structural_expansions_per_cycle`：

```python
max_structural_expansions_per_cycle: int = 2
# 默认每轮最多扩展 2 个分支
# K = 1 用于常规病例
# K = 2 用于复杂或高风险病例
# 仅在紧急或矛盾覆盖下允许临时超出
```

**在 `run_expansion_gate` 中的应用**：

```python
def run_expansion_gate(self, state):
    eligible = []
    for bid, branch in state.branches.items():
        if branch.status == "expand_now" and self._passes_expansion_gate(branch, state):
            branch.expand_score = self._compute_expansion_score(branch, state)
            eligible.append(branch)

    # 按 expand_score 降序排列，只取前 K 个
    eligible.sort(key=lambda b: b.expand_score, reverse=True)
    selected = eligible[:self.config.max_structural_expansions_per_cycle]

    for branch in selected:
        self.expand_branch(state, branch)
```

### 15.3 Coexistence Check 作为扩展触发条件

**来源**：`agentclinic_algorithm_update_requirements_design.md` §9.2 Priority E

**问题**：我们的 ExpansionGate 临床价值条件（§3.2 ALLOW 条件）包含 `ActionDifferenceScore`、`danger`、`HasUnresolvedCriticalDiscriminator`，但遗漏了**共存性检查**——当证据模式提示可能有多个诊断共存时，扩展有助于揭示这一点。

**修正**：在 ALLOW 条件中新增第 (D) 条：

```
ALLOW if ANY of:
  (A) ActionDifferenceScore(B, state) >= delta_action_diff
  (B) B.danger >= 0.7
  (C) HasUnresolvedCriticalDiscriminator(B, state)
  (D) CoexistenceSuspected(B, state)   ← 新增
      # 当该分支的证据模式与另一个存活分支的证据模式互不矛盾，
      # 且两者的后验之和 > 0.80，可能暗示多诊断共存。
      # 扩展可帮助确认或排除共存假设。
```

### 15.4 classification_axis 和 level_role 元数据

**来源**：`agentclinic_algorithm_update_requirements_design.md` §11、§15.2

我们的 SubBranchCreator 提示词（§4.3）目前只要求 `level` 字段。外部文档要求每个扩展决策附带结构化的分类轴标注，以提高可追溯性。

**修正**：SubBranchCreator 输出 JSON 新增两个字段：

```json
{
  "sub_branches": [
    {
      "id": "B1.1",
      "label": "...",
      "level": 2,
      "level_role": "disease_class",
      "classification_axis": "mechanism",
      ...
    }
  ]
}
```

**level_role 取值**：`"domain"` / `"family"` / `"disease_class"` / `"specific_disease"` / `"subtype_or_management_variant"`

**classification_axis 取值**：`"anatomy"` / `"mechanism"` / `"urgency"` / `"management_pathway"` / `"test_pathway"` / `"etiology"` / `"risk_context"` / `"severity"` / `"other"`

SubBranchCreator 提示词追加：

```
6. For each child branch, annotate:
   - level_role: what role this branch plays in the diagnostic hierarchy
     (domain / family / disease_class / specific_disease /
      subtype_or_management_variant)
   - classification_axis: what axis was used to distinguish this child
     from its siblings
     (anatomy / mechanism / urgency / management_pathway / test_pathway /
      etiology / risk_context / severity / other)
```

### 15.5 灵活分类轴——非固定本体论

**来源**：`algorithm_update_requirements_and_design.md` §2.4, `agentclinic_algorithm_update_requirements_design.md` §11.2

外部文档明确强调：**层级角色是默认指导而非固定本体论**。分类轴应根据根节点的临床问题动态选择。

> *"Branch levels have typical functions, not rigid universal categories."*

我们的五层模型（§2）已有此意图，但措辞不够明确。追加以下约束说明到第2节（抽象层次模型）：

**追加说明**：

上表中的"主要区分维度"列仅为**默认指导**。实际分类轴应由当前临床问题决定：
- **胸痛**根节点：L1 可能按**病理生理机制**分（缺血性/血栓栓塞/结构性）；
- **休克**根节点：L1 可能按**血流动力学类型**分（分布性/心源性/梗阻性/低血容量）；
- **黄疸**根节点：L1 可能按**解剖位置**分（肝前/肝细胞/胆汁淤积性）；
- **神经功能缺损**根节点：L1 可能按**时间病程**分（急性/亚急性/慢性）。

同一棵树的不同分支甚至可以使用不同的分类轴——只要同级兄弟节点的分类轴一致即可（Valid split criteria 第1条：同级分支处于可比的抽象层次）。

### 15.6 扩展示例补充——来自外部文档的临床场景

**来源**：`agentclinic_algorithm_update_requirements_design.md` §11.4

**黄疸案例**（与我们第11节的急性单关节炎案例互补）：

```
Level 0: 成人黄疸综合征
Level 1: 肝前性 / 肝细胞性 / 胆汁淤积-梗阻性
  分类轴 = anatomy (解剖位置)
Level 2 (under 胆汁淤积-梗阻性):
  肝内胆汁淤积 / 肝外梗阻
  分类轴 = anatomy (梗阻位置)
Level 3 (under 肝外梗阻):
  胆总管结石 / 恶性肿瘤 / 狭窄 / 其他
  分类轴 = etiology (病因)
Level 4 (under 胆总管结石):
  源控制紧急性 / 病因特异性管理
  分类轴 = management_pathway
```

**休克案例**：

```
Level 0: 未分化休克
Level 1: 分布性 / 心源性 / 梗阻性 / 低血容量
  分类轴 = mechanism (血流动力学机制)
Level 2 (under 分布性):
  脓毒症 / 过敏反应
  分类轴 = etiology
Level 3 (under 脓毒症):
  感染源 / 特定病原体
  分类轴 = anatomy + etiology
```

---

## 参考文献

1. Patel, V.L., & Groen, G.J. (1986). Knowledge-based solution strategies in medical reasoning. *Cognitive Science, 10*(1), 91–116.
2. Peng, Y., & Reggia, J.A. (1990). *Abductive Inference Models for Diagnostic Problem Solving*. Springer.
3. Elstein, A.S., & Schwarz, A. (2002). Clinical problem solving and diagnostic decision making: selective review of the cognitive literature. *BMJ, 324*(7339), 729–732.
4. Bowen, J.L. (2006). Educational strategies to promote clinical diagnostic reasoning. *NEJM, 355*(21), 2217–2225.
5. Orphanet (2012). Orphanet Nomenclature and Classification of Rare Diseases. INSERM.
6. Croskerry, P. (2002). Achieving quality in clinical decision making: cognitive strategies and detection of bias. *Academic Emergency Medicine, 9*(11), 1184–1204.
7. Redelmeier, D.A., et al. (2001). Problems for clinical judgement: introducing cognitive psychology as one more basic science. *CMAJ, 164*(3), 358–360.
8. Lucas, P.J.F. (1996). *A Theory of Diagnosis as Hypothesis Refinement*. Utrecht University Technical Report CS-1996-42.
9. Stern, S.D.C., Cifu, A.S., & Altkorn, D. (2019). *Symptom to Diagnosis: An Evidence-Based Guide* (4th ed.). McGraw-Hill.
10. `agentclinic_algorithm_update_requirements_design.md`（外部智能体生成，本节 §15.1–15.6 来源）
11. `algorithm_update_requirements_and_design.md`（外部智能体生成，本节 §15.5 来源）

---

*文档生成时间：2026-04-30*  
*基于代码分支：`codex/verify-agentclinic-compatibility-with-projects`*  
*补充来源：`agentclinic_algorithm_update_requirements_design.md`、`algorithm_update_requirements_and_design.md`*
