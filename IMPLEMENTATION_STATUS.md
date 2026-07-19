# 实现现状文档

> 本文档基于当前代码实际行为（不是设计规范）进行描述，目标是让读者无需阅读源码即可理解系统的真实执行逻辑。  
> 核心文件：`src/agentclinic_tree_dx/controller.py`、`state.py`、`action_bundler.py`、`prompts/*.txt`

---

## 目录

1. [执行模式](#1-执行模式)
2. [核心数据结构](#2-核心数据结构)
3. [主循环总体结构](#3-主循环总体结构)
4. [阶段详解](#4-阶段详解)
   - [4.1 首轮初始化（仅 Turn 1）](#41-首轮初始化仅-turn-1)
   - [4.2 每轮安全检查（Step A）](#42-每轮安全检查step-a)
   - [4.3 根节点选择（Step B）](#43-根节点选择step-b)
   - [4.4 L1 分支创建（Step C）](#44-l1-分支创建step-c)
   - [4.5 审议子循环（Step D-pre-0）](#45-审议子循环step-d-pre-0)
   - [4.6 即时展开（Step D-pre）](#46-即时展开step-d-pre)
   - [4.7 行动规划 TALP（Step D）](#47-行动规划-talpstep-d)
   - [4.8 动作覆盖与 bundle 构建（Step D'）](#48-动作覆盖与-bundle-构建step-d)
   - [4.9 bundle 执行（Step E'）](#49-bundle-执行step-e)
   - [4.10 证据标注（Step F'）](#410-证据标注step-f)
   - [4.11 概率更新（Step G）](#411-概率更新step-g)
   - [4.12 分支状态修订（Step I）](#412-分支状态修订step-i)
   - [4.13 结构性展开（Step J）](#413-结构性展开step-j)
   - [4.14 终止判断（Step K）](#414-终止判断step-k)
   - [4.15 最终聚合](#415-最终聚合)
5. [LLM 模块速览表](#5-llm-模块速览表)
6. [关键机制详解](#6-关键机制详解)
   - [6.1 state.to_payload() vs to_dict()](#61-statetopayload-vs-todict)
   - [6.2 Frontier 的语义](#62-frontier-的语义)
   - [6.3 概率更新三种路径](#63-概率更新三种路径)
   - [6.4 父节点后验聚合](#64-父节点后验聚合)
7. [已知架构问题](#7-已知架构问题)

---

## 1. 执行模式

`ControllerConfig.execution_mode` 决定整个流程的行为：

| 模式字符串 | 场景 | 动作类型 | 终止触发 |
|-----------|------|---------|---------|
| `static_diagnosis_qa` | 静态 MCQ（MedBullets 等） | `ANALYZE_VIGNETTE` / `SELECT_OPTION` / `DIAGNOSIS_READY` | `check_diagnosis_readiness` → `AnswerMapper` |
| `sdbench_patch` | SDBench 交互式问诊 | `ASK` / `TEST` / `DIAGNOSE` | `check_diagnosis_readiness` → `FinalDiagnosisEmitter` |
| `agentclinic_physician_patch` | AgentClinic 临床模拟 | `ASK_PATIENT` / `REQUEST_TEST_OR_MEASUREMENT` / `DIAGNOSIS_READY` | `check_diagnosis_readiness` → `FinalAggregator` |

> **动作类型映射**：TALP 输出的动作类型（如 `ORDER_LAB`）经 `_normalize_*_action()` 方法映射到各模式的合法动作集。静态 QA 模式将所有查询型动作统一映射为 `ANALYZE_VIGNETTE`。

---

## 2. 核心数据结构

### DiagnosticState（中央状态）

```python
@dataclass
class DiagnosticState:
    case_id: str
    timestep: int = 0                           # 当前轮次（Turn 编号）
    case_summary: str = ""                      # 当前用例完整描述（每轮从 env 刷新）
    root: RootNode | None = None                # 根节点（Turn 1 后初始化）
    branches: dict[str, Branch] = {}            # 所有分支（含所有层级）
    frontier: list[str] = []                    # 当前活跃分支 ID 列表
    other_mass: float = 0.0                     # 前三外分支的概率质量合计

    candidate_leaves: list[CandidateLeaf] = []  # TALP 产出的候选动作
    actions_taken: list[dict] = []              # 所有已执行动作记录
    differential_history: list[dict] = []       # 各轮后验概率快照
    deliberation: DeliberationState = ...       # 审议团本轮输出

    # Static QA 专用字段
    static_vignette: str = ""                   # VignetteParser 解析后的题干
    static_question: str = ""                   # 题目问句
    static_options: list[dict] = []             # 选项列表 [{id, description}]
    static_evidence_items: list[EvidenceItem] = []  # 从题干提取的独立证据条目
    answer_option_mapping: dict = {}            # AnswerMapper 输出的选项置信度

    # 控制字段
    turn_budget_used: int = 0
    max_turn_budget: int | None = None
    max_tree_depth: int = 3
    benchmark_output_ready: bool = False
    diagnosis_readiness_score: float = 0.0
    termination: TerminationState = ...
    interrupt: InterruptState = ...
```

### Branch（诊断分支）

```python
@dataclass
class Branch:
    id: str                         # 如 "B1", "B1.1"
    label: str                      # 诊断族标签
    parent: str                     # 父分支 ID（L1 为 "ROOT"）
    level: int                      # 层级：1=家族, 2=疾病类, 3=具体疾病, 4=亚型
    status: str                     # live / parked / closed_for_now / expanded / confirmed / reopened
    prior: float                    # 上轮后验（当轮先验）
    posterior: float                # 当轮后验（由 apply_probability_update 更新）
    danger: float                   # 高危标记（0-1；≥0.7 不轻易关闭）
    evidence_for: list[str]         # 支持该分支的证据摘要列表
    evidence_against: list[str]     # 反对该分支的证据摘要列表
    children: list[str]             # 子分支 ID 列表（展开后填充）
    # AgentClinic/SDBench 扩展字段
    askable_discriminators: list[str]
    requestable_discriminators: list[str]
    turn_cost_to_refine: float
    diagnosis_commitment_gain: float
    level_role: str                 # family / disease_class / specific_disease / subtype_or_management_variant
    classification_axis: str        # anatomy / mechanism / urgency / etiology / ...
```

> **`expanded` 状态的特殊含义**：当分支被展开为子分支后，`status` 变为 `expanded`，`posterior` 被置 0（由 `recompute_parent_posteriors` 自下而上聚合子节点）。`expanded` 节点不参与 `check_diagnosis_readiness` 的诊断就绪评估，也不参与 `EvidenceAnnotator` 的效果标注。

### CandidateLeaf（候选动作）

```python
@dataclass
class CandidateLeaf:
    leaf_id: str
    branch_id: str                  # 主要目标分支
    leaf_type: str                  # ANALYZE_VIGNETTE / ASK_PATIENT / ORDER_LAB / ...
    content: str                    # 动作内容（问题 / 检查项）
    total_score: float              # TALP 打分
    expected_information_gain: float
    expected_cost: float
    expected_delay: float
    safety_value: float
    action_separation_value: float
    falsification_value: float
    primary_function: str           # support / falsify / safety_check
    target_branches: list[str]      # 可覆盖的分支 ID 列表
    bundle_independence: float      # 与其他动作的独立性（0-1）
    invasiveness: float
```

---

## 3. 主循环总体结构

```
run(state)
│
├─ [Turn 1 only] 初始化：VignetteParser → parse_static_vignette
│
└─ while True:
    timestep += 1
    case_summary ← env.get_case_summary()
    │
    ├─ [Step A]   SafetyController → 安全检查 → 可能执行紧急动作
    ├─ [Step B]   RootSelector → 选/修订根节点（仅初次或 root_revision_needed 时）
    ├─ [Step C]   BranchCreator → 创建 L1 分支（仅初次或根节点变更时）
    │
    ├─ [Step D-pre-0] 审议子循环（每轮必跑）:
    │   ├─ Hypothesis → d.hypothesis_analysis         [3行提示，基本无效]
    │   ├─ EvidenceAllocator → d.test_chooser_analysis [3行提示，建议下一条证据]
    │   ├─ Challenger → d.challenger_analysis          [3行提示，质疑领先假设]
    │   ├─ ReasoningEconomyAuditor → d.stewardship_analysis [3行提示]
    │   ├─ Checklist → d.checklist_analysis            [3行提示，合规检查]
    │   └─ Consensus ← {state, deliberation: checklist_analysis}  ← 仅接收 Checklist
    │       → d.consensus_action: {action_type, content, reasoning}
    │
    ├─ [Step D-pre] check_just_in_time_expansion → 条件性触发 SubBranchCreator
    │
    ├─ [Step D]   TALP → candidate_leaves (打分排序列表) + selected_action (top-1)
    │
    ├─ [Step D' override] 若 consensus_action 存在:
    │   selected_action ← consensus_action  [覆盖 TALP top-1，但不影响 bundle]
    │
    ├─ [Step D' bundle] build_bundle(candidate_leaves):
    │   Phase 0: 若 top-1 为 DIAGNOSIS_READY → 直接返回单动作
    │   Phase 1: frontier 覆盖（每个 live 分支选一个代表动作）
    │   Phase 1.5: 领先分支（P≥0.5）强制插入 falsify 动作
    │   Phase 2: 跨分支补充（高 action_separation_value）
    │   Phase 3: 按 expected_delay 排序
    │   兜底: 若 bundle 为空 → bundle = [selected_action]  ← 此时 Consensus 生效
    │
    ├─ [Step E'] execute_action_bundle → 按顺序执行 bundle 中每个动作
    │   每个动作记录追加到 state.actions_taken
    │   static_qa: ANALYZE_VIGNETTE 返回 {analysis_target, evidence_items_ref}
    │
    ├─ [Step F'] annotate_evidence_bundle:
    │   单动作 → annotate_evidence (单次 EvidenceAnnotator 调用)
    │   多动作 → 单次 EvidenceAnnotator 调用处理全部结果
    │   输出: {result_summary, major_update, branch_effects: {bid: label}, ...}
    │   label ∈ {strong_for, moderate_for, weak_for, neutral, weak_against,
    │             moderate_against, strong_against}
    │   → update_evidence_lists: 将 result_summary 追加到 branch.evidence_for/against
    │
    ├─ [Step G] group_correlated_evidence: 多动作时降级 strong → moderate
    │   choose_update_method → apply_probability_update:
    │   ├─ calculator: calculator_update
    │   ├─ rule_based: rule_based_update
    │   └─ ordinal (默认): ordinal_update
    │   → 更新所有 branch.posterior
    │
    ├─ [Step H] recompute_parent_posteriors (expanded 节点底部向上聚合子节点 posterior 之和)
    │
    ├─ [Step I] PostUpdateStateReviser → branch_decisions:
    │   每个分支: expand_now / keep_coarse / park / close_for_now / confirm / reopen
    │   → revise_branch_states → 写入 branch.status
    │
    ├─ [Step J] run_expansion_gate:
    │   对每个新标记 expand_now 的分支 → expand_branch → SubBranchCreator
    │   → initialize_child_posteriors (按先验比例分配父节点 posterior)
    │   → 父节点 status=expanded, posterior=0
    │   recompute_parent_posteriors → update_frontier_after_expansion
    │   (frontier 中的 expanded 节点被其子节点替换)
    │
    ├─ [Step K] 终止检查:
    │   check_diagnosis_readiness:
    │   ├─ 筛选 status != "expanded" 的诊断叶节点
    │   ├─ 找最高后验 leader
    │   └─ leader.posterior ≥ min_readiness_to_commit (默认 0.75) → 触发终止
    │
    │   check_termination → TerminationJudge → ready_to_stop
    │
    │   turn_budget_used ≥ max_turn_budget → 强制终止
    │
    └─ final_aggregate → AnswerMapper / FinalDiagnosisEmitter / FinalAggregator
```

---

## 4. 阶段详解

### 4.1 首轮初始化（仅 Turn 1）

**触发条件**：`_in_static_qa_mode() and state.timestep == 1`

**执行内容**：

```
VignetteParser ← {raw_case: case_summary}
  输出: {vignette, question, options, evidence_items}
  → state.static_vignette  (题干文本)
  → state.static_question  (题目问句)
  → state.static_options   (选项 [{id, description}])
  → state.static_evidence_items  (结构化证据条目列表)
  → state.mode_policy = {benchmark_purity: true, allow_external_knowledge: ...}
```

鲁棒字段映射：代码依次尝试 `content` → `fact` → `description` → `item+value` → `text` 提取证据内容，避免 LLM 字段名不一致导致空白。

---

### 4.2 每轮安全检查（Step A）

```
SafetyController ← state.to_payload()
  输出: {interrupt_active, reason, required_actions}
  → state.interrupt
  若 interrupt_active: execute_emergent_actions → env.take_emergent_action(action)
  若 patient_still_unstable(): continue（跳过本轮后续步骤，进入下一轮）
```

---

### 4.3 根节点选择（Step B）

**触发条件**：`state.root is None` 或 `state.root_revision_needed`

```
_root_selector_payload(state):
  ← state.to_dict()（注意：此处用 to_dict 而非 to_payload）
  → 清空 static_options（防止答案选项污染根节点判断）
  → 正则替换 case_summary 中 "Options:" 之后的内容为占位符

RootSelector ← 净化后 payload
  输出: {root_label, time_course, confidence, supporting_facts,
         excluded_root_candidates, alarm_features}
  → state.root = RootNode(...)
  若 need_external_knowledge and allow_external_knowledge:
    → knowledge_router → env.ingest_external_context → 重新调用 RootSelector
```

---

### 4.4 L1 分支创建（Step C）

**触发条件**：`not state.branches` 或根节点变更

```
BranchCreator ← state.to_payload()
  输出: {branches: [...], frontier: [...], need_external_knowledge}
  每个 branch: {id, label, status, prior_estimate, danger, level_role,
                classification_axis, askable_discriminators,
                requestable_discriminators, turn_cost_to_refine,
                diagnosis_commitment_gain, interrupt_relevance, why_included}
  → 写入 state.branches（Branch 对象，posterior 初始化为 prior_estimate）
  → state.frontier = BranchCreator 建议的 frontier
```

**注意**：若 BranchCreator 建议 `need_external_knowledge`，当前代码**无额外处理**（与 RootSelector 不同，没有重试逻辑）。

---

### 4.5 审议子循环（Step D-pre-0）

在 `static_diagnosis_qa` 模式下执行 `run_static_qa_deliberation`：

```
全部 6 个模块均接收相同的 payload = state.to_payload()

1. Hypothesis ← payload
   输出: 任意格式（提示词 3 行，无 schema）→ d.hypothesis_analysis
   ⚠ 实际输出通常为分支置信度列表，复读先验概率，无证据分析

2. EvidenceAllocator ← payload
   输出: 任意格式（提示词 3 行，无 schema）→ d.test_chooser_analysis
   ⚠ 建议下一步应分析的证据，是动作规划，不是证据推理

3. Challenger ← payload
   输出: 任意格式（提示词 3 行，无 schema）→ d.challenger_analysis
   ⚠ 偶发返回 {"response": {...}} 嵌套 JSON，_extract_json_best_effort 失败时返回 {}

4. ReasoningEconomyAuditor ← payload
   输出: 任意格式（提示词 3 行，无 schema）→ d.stewardship_analysis
   ⚠ 偶发返回过短内容触发重试（最多 10 次）

5. Checklist ← payload
   输出: 任意格式（提示词 3 行，无 schema）→ d.checklist_analysis

6. Consensus ← {state: payload, deliberation: d.checklist_analysis}
   ⚠ 仅接收 Checklist 的输出，其他 4 个模块输出被忽略
   输出: {action_type, content, reasoning} → d.consensus_action
```

**Consensus 输出的 `consensus_action` 在后续 Step D' 中覆盖 TALP 的 `selected_action`，但不影响 bundle 内容（bundle 始终由 TALP 候选构建）。**

---

### 4.6 即时展开（Step D-pre）

`check_just_in_time_expansion`：在 TALP 之前，对 frontier 中满足以下条件的分支触发提前展开：

1. `branch.status in {"live", "reopened"}`
2. `branch.level < max_tree_depth`
3. `not branch.children`
4. `_action_selection_requires_children(branch)` = True

`_action_selection_requires_children` 条件（同时满足）：
- `branch.posterior >= commit_threshold * 0.5`（默认 ≥ 0.375）
- `branch.classification_axis in {"management_pathway", "test_pathway"}`
- 存在未使用的 discriminator

满足条件则立即调用 `expand_branch → SubBranchCreator`，并更新 frontier。

---

### 4.7 行动规划 TALP（Step D）

```
TemporaryAnalyticLeafPlanner (static_qa 模式) 或
TemporaryLeafPlanner (其他模式) ← state.to_payload()

输出: {candidate_leaves_ranked: [...]}
每个候选: {branch_id, type, content, score, expected_information_gain,
           safety_value, action_separation_value, falsification_value,
           expected_cost, expected_delay, invasiveness,
           target_branches, primary_function, bundle_independence}

→ 转换为 CandidateLeaf 对象列表
→ selected_action = candidate_leaves[0]（top-1 候选）
  若 candidate_leaves 为空: selected_action = {} (空动作)
```

---

### 4.8 动作覆盖与 bundle 构建（Step D'）

**覆盖逻辑（影响 `selected_action` 但不影响 bundle）**：
```python
if consensus_action:
    selected_action = consensus_action   # Consensus 单动作覆盖 TALP top-1
```

**build_bundle 四阶段算法**：

```
输入: candidate_leaves (TALP 输出), state.frontier, config

Phase 0: 若 candidate_leaves[0].leaf_type == "DIAGNOSIS_READY"
  → 立即返回 [candidate_leaves[0]]（单动作，短路所有后续）

Phase 1: 强制 frontier 覆盖
  对 frontier 中每个 live/reopened 分支:
    从 candidate_leaves 中找该分支的最高分候选（通过 _passes_gates）
    添加到 bundle（每分支最多 1 个代表动作）

Phase 1.5: 领先分支防确认偏差
  若 live 分支中最高 posterior 的领先分支 P ≥ 0.5，
  且 bundle 中没有针对该分支的 falsify 动作:
    → 从候选中插入一个 primary_function=="falsify" 的动作

Phase 2: 跨分支补充
  先补充尚未被覆盖的 frontier 分支（通过 target_branches 字段）
  再按 action_separation_value 排序，添加超过阈值的高分离度动作

Phase 3: 按 expected_delay 升序排序

兜底: 若 bundle 为空 → bundle = [_action_dict_to_leaf(selected_action)]
  此时 Consensus 的 consensus_action 才真正生效
```

**_passes_gates 检查**（任一失败则拒绝）：
1. `_is_dependent`：result-dependent 动作不与 data-producing 动作共 bundle
2. `_is_duplicate_knowledge_retrieval`：每个 bundle 最多 1 个知识检索动作
3. `_is_redundant`：Jaccard 相似度 > `redundancy_similarity_threshold`（内容重复）
4. `expected_information_gain < min_marginal_ig_threshold`（信息增益过低）

---

### 4.9 bundle 执行（Step E'）

```
execute_action_bundle: 顺序执行 bundle 中每个动作

每个动作:
  1. 确定 action_type 和 external_action（经模式适配器归一化）
  2. 追加到 state.actions_taken（含 bundle_id, bundle_position, bundle_size）
  3. _dispatch_env_call → 执行动作，获取 raw_result
  4. raw_result 回填到 actions_taken 最后一条记录

static_qa 模式的 ANALYZE_VIGNETTE 执行：
  raw_result = {
    "analysis_target": content,
    "evidence_items_ref": "see state.static_evidence_items",  # 不重复传完整证据
    "question": state.static_question,
  }
```

---

### 4.10 证据标注（Step F'）

```
annotate_evidence_bundle:
  单动作 → annotate_evidence: 单次 EvidenceAnnotator LLM 调用
  多动作 → 单次 EvidenceAnnotator 调用，raw_result 为整个 bundle_results 列表

EvidenceAnnotator ← {state: state.to_payload(), raw_result}
  输出: {result_summary, major_update, branch_effects: {bid: label},
         calculator_applicable, formal_rule_available,
         contradiction_detected, reopen_candidates}

标注规则:
  - expanded 分支不标注（自动跳过）
  - 必须标注所有 live 分支（包括非目标分支的 neutral 效果）

group_correlated_evidence:
  若 bundle_size > 1，将所有 strong_for/strong_against 降级为 moderate_*
  （防止多动作协同导致的双重计数）

update_evidence_lists:
  将 result_summary 追加到:
  ├─ "for" in label → branch.evidence_for
  └─ "against" in label → branch.evidence_against
```

---

### 4.11 概率更新（Step G）

```
choose_update_method(annotation):
  calculator_applicable=True → "calculator"
  formal_rule_available=True → "rule_based"
  else → "ordinal"（默认）

apply_probability_update(state, annotation, method):
  calculator: calculator_update(branches, annotation, calculator_result)
  rule_based: rule_based_update(branches, annotation)
  ordinal: ordinal_update(branches, annotation)  ← 最常用

更新: branch.prior = branch.posterior
      branch.posterior = new_value
```

**`ordinal_update` 核心逻辑（参考实现）**：基于 `branch_effects` 的有序标签（strong_for → +0.3, moderate_for → +0.15, weak_for → +0.05, neutral → 0, weak_against → -0.05, ...），对当前后验做加权调整并归一化，确保所有分支概率之和为 1。

---

### 4.12 分支状态修订（Step I）

```
PostUpdateStateReviser ← state.to_payload()
  输出: {branch_decisions: [{branch_id, decision, live_subtype, rationale}]}

decision → branch.status 映射:
  expand_now    → 标记待展开（Step J 处理）
  keep_coarse   → 保持当前 live 状态，不展开
  park          → status = "parked"
  close_for_now → status = "closed_for_now"
  confirm       → status = "confirmed"
  reopen        → status = "reopened"

约束:
  - 不对 posterior < test_threshold(0.05) 的 live 分支输出 expand_now
  - 不对 danger ≥ 0.7 的分支输出 close_for_now（除非 posterior < 0.01）
  - 不对已有子节点（status=="expanded"）的分支输出 expand_now
```

---

### 4.13 结构性展开（Step J）

```
run_expansion_gate:
  对 state.branches 中每个 status="expand_now" 的分支:
    1. _passes_expansion_gate 硬约束检查:
       - branch.level < effective_max_depth
       - status != "confirmed"
       - posterior >= test_threshold
       - no existing children
    2. expand_branch → SubBranchCreator

SubBranchCreator ← {state: state.to_payload(), parent_branch: {id, label, level,
                     posterior, danger, evidence_for, evidence_against,
                     unresolved_questions, discriminators}, target_level}
  输出: {needs_expansion, sub_branches: [...]}
  → 创建 Branch 对象并写入 state.branches
  → parent_branch.children 填入子节点 IDs

initialize_child_posteriors:
  total_prior = sum(child.prior for child in children)
  若 total_prior > 0:
    child.posterior = parent.posterior * (child.prior / total_prior)
  否则:
    child.posterior = parent.posterior / len(children)
  parent.status = "expanded"
  parent.posterior = 0.0   ← 置零，由 recompute_parent_posteriors 聚合

update_frontier_after_expansion:
  frontier 中的 expanded 节点替换为其 live/reopened 子节点
  截断至 max_live_frontier（默认 6）
```

---

### 4.14 终止判断（Step K）

**路径 1：`check_diagnosis_readiness`（主路径）**

```python
diagnosable = [b for b in state.branches.values() if b.status != "expanded"]
ranked = sorted(diagnosable, key=lambda b: b.posterior, reverse=True)
leader = ranked[0]
return leader.posterior >= config.min_readiness_to_commit  # 默认 0.75
```

触发时直接调用 `final_aggregate`，跳过 `TerminationJudge`。

**路径 2：`check_termination`（辅助路径）**

```
TerminationJudge ← state.to_payload()
  输出: {ready_to_stop, termination_type, reason}
  → state.termination
  若 ready_to_stop → final_aggregate
```

**路径 3：Turn budget（硬截止）**

```python
if turn_budget_used >= max_turn_budget:
    state.termination = TerminationState(True, "info_exhaustion", "turn budget reached")
    return final_aggregate(state)
```

---

### 4.15 最终聚合

| 模式 | 调用 | 输出 |
|------|------|------|
| `static_diagnosis_qa` | `AnswerMapper ← {state: to_payload(), options}` | `{final_answer, answer_option_mapping, internal_reasoning_state}` |
| `sdbench_patch` | `FinalDiagnosisEmitter ← {state: to_dict(), internal_reasoning_state}` | `{diagnosis, submission, internal_reasoning_state}` |
| 其他（含 patch） | `FinalAggregator ← state.to_dict()` | `{leading_diagnosis_or_parent, ...}` |

> `AnswerMapper` 接收的 `state` 是 `to_payload()`（裁剪版），但 `internal_reasoning_state` 返回的是 `to_dict()`（完整版）。

---

## 5. LLM 模块速览表

| 模块名 | 提示词行数 | 接收方 | 输出消费方 | 提示词质量 |
|-------|----------|-------|----------|----------|
| VignetteParser | 充分 | 原始题目文本 | parse_static_vignette | ✅ |
| SafetyController | 充分 | state.to_payload() | interrupt 字段 | ✅ |
| RootSelector | 67 行 | 净化后 payload | state.root | ✅ |
| BranchCreator | 79 行 | state.to_payload() | state.branches | ✅ |
| SubBranchCreator | 73 行 | {state, parent_branch, target_level} | state.branches (children) | ✅ |
| **Hypothesis** | **3 行** | state.to_payload() | d.hypothesis_analysis（被忽略） | ⚠️ |
| **EvidenceAllocator** | **3 行** | state.to_payload() | d.test_chooser_analysis（被忽略） | ⚠️ |
| **Challenger** | **3 行** | state.to_payload() | d.challenger_analysis（被忽略） | ⚠️ |
| **ReasoningEconomyAuditor** | **3 行** | state.to_payload() | d.stewardship_analysis（被忽略） | ⚠️ |
| **Checklist** | **3 行** | state.to_payload() | d.checklist_analysis → Consensus | ⚠️ |
| **Consensus** | **3 行** | {state, deliberation: checklist_analysis} | selected_action（兜底） | ⚠️ |
| TemporaryAnalyticLeafPlanner | 充分 | state.to_payload() | candidate_leaves（bundle 构建源） | ✅ |
| TemporaryLeafPlanner | 充分 | state.to_payload() | candidate_leaves（bundle 构建源） | ✅ |
| EvidenceAnnotator | 67 行 | {state, raw_result/bundle_results} | branch_effects → 概率更新 | ✅ |
| PostUpdateStateReviser | 63 行 | state.to_payload() | branch.status 变更 | ✅ |
| TerminationJudge | 充分 | state.to_payload() | state.termination | ✅ |
| AnswerMapper | 充分 | {state, options} | final_answer | ✅ |
| FinalAggregator | 充分 | state.to_dict() | 最终诊断输出 | ✅ |
| ToolUseGate | 充分 | {state, action_type, content} | 工具调用许可检查 | ✅ |

> **⚠️ 标记**：提示词仅 3 行，无 JSON schema，LLM 自由发挥输出格式，该模块输出在当前实现中实际无效或几乎无效。

---

## 6. 关键机制详解

### 6.1 state.to_payload() vs to_dict()

```
to_dict()    → 完整序列化，无裁剪，用于：
               - _root_selector_payload (然后再净化)
               - FinalAggregator
               - FinalDiagnosisEmitter
               - internal_reasoning_state 字段

to_payload() → 裁剪序列化，用于所有 LLM 推理调用：
               裁剪规则：
               ├─ actions_taken: 最近 6 条；去除 raw_result, branch_coverage
               ├─ branch.evidence_for/against: 各最多 2 条（保留最新）
               ├─ closed_for_now/parked 分支: 替换为最小 stub
               │   {id, label, level, status, posterior, danger,
               │    closure_reason, evidence_against[-1:]}
               ├─ deliberation: 清空为 {}
               ├─ differential_history: 最近 3 个快照
               └─ candidate_leaves: 完全移除
```

### 6.2 Frontier 的语义

`state.frontier` 是一个 **ID 列表**，代表当前轮次需要被覆盖的活跃分支。它是**异构多层级**的：

- 初始 frontier = BranchCreator 建议的 L1 分支 IDs
- 某 L1 分支被展开后：该 L1 从 frontier 移除，其 L2 子分支加入 frontier
- 因此在树有 2 层展开时，frontier 可能同时包含 L1（未展开）和 L2（已展开子节点）

**frontier 不等于"所有活跃分支"**：`closed_for_now`、`parked`、`confirmed` 的分支不在 frontier，但在 `state.branches` 中以 STUB 形式保留。

### 6.3 概率更新三种路径

```
EvidenceAnnotator 输出:
  calculator_applicable=True  → calculator_update（适用 Wells/CURB-65 等评分）
  formal_rule_available=True  → rule_based_update（适用显式诊断规则）
  else                        → ordinal_update（默认：有序标签 → 数值调整 → 归一化）
```

所有三条路径均保证更新后所有分支后验概率之和为 1。

### 6.4 父节点后验聚合

被展开的父节点 (`status="expanded"`) 的后验不由概率更新算法直接计算，而是通过 `recompute_parent_posteriors` 自下而上聚合：

```python
parent.posterior = sum(child.posterior for child in active_children)
```

该函数在三个位置被调用：
1. Step D-pre 即时展开后
2. Step G 概率更新后（Step H）
3. Step J 结构性展开后

---

## 7. 已知架构问题

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| A | **审议团与 TALP 双轨并行，决策不集成** | `run_static_qa_deliberation` + `plan_temporary_leaves` | 6 次审议 LLM 调用仅在 bundle 为空时生效，常态下无效 |
| B | **Consensus 仅接收 Checklist** | `run_static_qa_deliberation` L.356-358 | Hypothesis/EvidenceAllocator/Challenger/ReasoningEconomyAuditor 输出被丢弃，Consensus 的审议基础残缺 |
| C | **5 个审议模块提示词各仅 3 行无 schema** | `prompts/*.txt` | LLM 自由发挥格式，输出不可控；Challenger 偶发嵌套 JSON 解析失败 |
| D | **frontier 跨层级异构，概率不可比** | `update_frontier_after_expansion` | L1 分支（代表一个疾病家族）与 L2 子分支（代表具体疾病）同在 frontier，直接比较 posterior 导致误判 |
| E | **Consensus 输出的 `selected_action` 覆盖 TALP top-1 但不影响 bundle** | controller.py L.93-103 | 规范意图（审议驱动行动）与实现（bundle 独立构建）不一致 |
| F | **Challenger JSON 嵌套问题（遗留）** | Challenger 模块输出 | `{"response": {...}}` 被 `_extract_json_best_effort` 解析失败后回退为 `{}`，Challenger 实际上零输出 |
| G | **`_root_selector_payload` 使用 `to_dict()` 而非 `to_payload()`** | controller.py L.250 | 根节点选择时传入完整未裁剪 state，为初次调用时开销最大的单次 LLM 调用之一 |
