# 实现分析文档：各模式各模块简化实现、提示词依赖与完整版差距

> 本文档对各执行模式中每个模块的**当前实际实现逻辑**进行逐一分析，指出其依赖的提示词文件内容，并与规格文档（`readme.md`、`sdbench_tree_dx_spec.md`、`agentclinic_patch_development_documentation.md`、`static_diagnosis_qa_mode_spec*.md`）中定义的完整实现之间的差距。

---

## 阅读说明

- **当前实现**：描述代码库中现有的实际逻辑，包括 `controller.py` 中对应函数的真实行为。
- **所依赖提示词**：列出提示词文件路径与其当前全部内容（均极为简短）。
- **完整版要求**：规格文档中定义的该模块完整行为。
- **差距**：当前实现与完整版之间具体缺少什么。

---

## 第一部分：基础模块（所有模式共用）

---

### 模块 A：SafetyController（安全筛查）

#### 当前实现

```python
# controller.py: safety_screen()
def safety_screen(self, state):
    result = self._call_module("SafetyController", state.to_dict())
    return state.interrupt.__class__(
        active=result.get("interrupt_active", False),
        reason=result.get("reason", ""),
        required_actions=result.get("required_actions", []),
    )
```

```python
# safety.py（薄封装，当前未被控制器调用）
def run_safety_controller(env, state: DiagnosticState) -> dict:
    return env.call_module("SafetyController", state)
```

控制器调用 `_call_module("SafetyController", state.to_dict())`，LLM 返回结果后直接构造 `InterruptState`。若 `interrupt_active=True`，则调用 `execute_emergent_actions()`（将动作追加到 `env.emergent_actions` 列表），然后检查 `env.patient_still_unstable()`，若不稳定则跳过本轮剩余步骤。

**在各模式中的差异行为**：所有模式均调用此模块，但 SDBench 模式下"中断"不产生独立的对外基准动作——仅影响内部优先级排序（规格要求），而当前实现对此无区分处理。

#### 所依赖提示词

**文件**：`src/agentclinic_tree_dx/prompts/safety_controller.txt`

```
Role: SafetyController
Inspect the provided diagnostic state and return strict JSON with interrupt status.
Return keys: interrupt_active, reason, required_actions, why_not_interrupt_if_false.
```

**3行，仅指定角色名和输出 key 列表，无任何临床规则或判断准则。**

#### 完整版要求（readme.md §9.1）

完整版要求 LLM 检查以下具体情况并给出判断：
- 气道受损（airway compromise）
- 严重呼吸道受损
- 休克或主要血流动力学不稳定
- 严重意识改变伴不稳定
- 不可控出血
- 高度怀疑时间敏感综合征

在 AgentClinic 补丁模式中，规格还要求将"中断"重新解释为：优先获取最快决定性证据，或允许早期诊断承诺，而不是生成完整治疗方案。

在 SDBench 模式中，规格要求紧急情况**不**产生独立的对外干预动作，而是修改：分支优先级、对快速决定性检查的偏好、对早期承诺的容忍度。

#### 差距

| 差距项 | 说明 |
|--------|------|
| 临床规则缺失 | 提示词未列出任何具体的紧急情况触发条件，完全依赖 LLM 自由判断 |
| 模式感知缺失 | SafetyController 提示词不感知执行模式，SDBench 模式下不会将中断转化为"分支优先级调整"的内部指令 |
| `execute_emergent_actions()` 为空操作 | 该函数只是将动作追加到列表，不实际执行任何临床干预 |
| `patient_still_unstable()` 恒为 False | Mock/所有适配器默认返回 False，无法模拟真实不稳定情形 |

---

### 模块 B：RootSelector（根节点选择）

> **状态（2026-05-18）**：已完成重大重设计，原版差距均已修复。

#### 当前实现

```python
# controller.py: select_root() + _root_selector_payload()
def _root_selector_payload(self, state) -> dict:
    """屏蔽 MCQ 答案选项，防止选项污染根节点选择。"""
    payload = state.to_dict()
    payload["static_options"] = []
    import re
    if payload.get("case_summary"):
        payload["case_summary"] = re.sub(
            r"\n+(?:Question|Options)\s*:.*",
            "\n[Answer options redacted — use clinical findings only]",
            payload["case_summary"], flags=re.DOTALL | re.IGNORECASE,
        )
    return payload

def select_root(self, state):
    payload = self._root_selector_payload(state)
    result = self._call_module("RootSelector", payload)
    if result.get("need_external_knowledge", False) and self.config.allow_external_knowledge:
        knowledge = self.knowledge_router(result.get("knowledge_query_if_needed", ""))
        self.env.ingest_external_context(knowledge)
        result = self._call_module("RootSelector", payload)
    return RootNode(
        label=result.get("root_label", result.get("label", "Undifferentiated syndrome")),
        time_course=result.get("time_course", "unspecified"),
        severity="unspecified",
        confidence=result.get("confidence", 0.5),
        supporting_facts=result.get("supporting_facts", []),
        excluded_candidates=result.get("excluded_root_candidates", []),
        alarm_features=result.get("alarm_features", []),
    )
```

#### 所依赖提示词

**文件**：`src/agentclinic_tree_dx/prompts/root_selector.txt`

关键设计要点（详见文件全文）：

**标签构成顺序**：`[时间模式] + [主诉综合征] + [开放机制短语] + [图像缺失修饰词]`

**开放性原则**：机制短语必须保留竞争机制（"Possible Cardiac or Vasovagal Aetiology"），仅在置信度 ≥0.85 时才允许单一机制承诺。

**竞争机制注册表**：`excluded_root_candidates` 记录所有被考虑但排名较低的机制，供 BranchCreator 生成对应分支。

**证据层级**（加权优先，非强制覆盖）：
- Tier 1：ECG/影像/病理 → Tier 2：定义生理状态的实验室值 → Tier 3：体格检查 → Tier 4：生命体征模式 → Tier 5：患者病史

**图像缺失处理**：`kind="image_reference"` 证据 → 标签加入"with Uncharacterised ECG/Imaging Abnormality"，`confidence ≤ 0.5`。

**选项污染防护**：由 `_root_selector_payload()` 在代码层面强制执行，不依赖提示词约束。

#### 原差距修复状态

| 原差距项 | 修复方式 |
|---------|---------|
| 字面化主诉（"Acute Arm Weakness Syndrome"）| 明确禁止示例 + 标签构成顺序要求 |
| 单一机制锚定 | 机制短语要求列出竞争机制；"Uncertain Aetiology"为默认格式 |
| 选项污染 | `_root_selector_payload()` 裁剪 payload 中的 MCQ 选项 |
| 神经解剖过度确定 | 规则加"usually/most likely"限定，例外进入注册表 |
| `evidence OVERRIDE history` 绝对化 | 改为"carries higher weight"，病史保留至 supporting_facts |
| 禁用规则缺失 | 详细 FORBIDDEN 列表含反例 |
| 外部知识路由为占位 | 现状未变，仍为占位；`allow_external_knowledge` 默认关闭 |

#### 验证结果（2026-05-18，medbullets_hard_test）

- 精准测试 7 个案例（跨系统）：**7/7**，含三维检验（关键词 + 禁止词 + ≥2 竞争机制）
- 广泛随机测试 20 个案例：**20/20**
- 累计：**27/27**

---

### 模块 C：BranchCreator（分支创建）

#### 当前实现

```python
# controller.py: create_branches()
def create_branches(self, state):
    result = self._call_module("BranchCreator", state.to_dict())
    if result.get("need_external_knowledge", False) and self.config.allow_external_knowledge:
        knowledge = self.knowledge_router(result.get("knowledge_query_if_needed", ""))
        self.env.ingest_external_context(knowledge)
        result = self._call_module("BranchCreator", state.to_dict())
    branches = {}
    for b in result["branches"]:
        branches[b["id"]] = Branch(
            id=b["id"], label=b["label"], parent="ROOT", level=1,
            status=b.get("status", "live"),
            prior=b.get("prior_estimate", 0.0),
            posterior=b.get("prior_estimate", 0.0),
            danger=b.get("danger", 0.0),
            actionability=0.0, explanatory_coverage=0.0,
            askable_discriminators=b.get("askable_discriminators", []),
            requestable_discriminators=b.get("requestable_discriminators", []),
            turn_cost_to_refine=b.get("turn_cost_to_refine", 0.0),
            diagnosis_commitment_gain=b.get("diagnosis_commitment_gain", 0.0),
            interrupt_relevance=b.get("interrupt_relevance", 0.0),
        )
    return branches, result.get("frontier", [])
```

所有分支的 `parent="ROOT"`、`level=1`，仅创建**一层**分支树。`actionability` 和 `explanatory_coverage` 恒为 0.0（未由 LLM 填充）。SDBench 模式下，`create_branches()` 完成后还会调用 `initialize_sdbench_top3()`，强制将前沿截取至后验概率最高的 3 个分支。

#### 所依赖提示词

**文件**：`src/agentclinic_tree_dx/prompts/branch_creator.txt`

```
Role: BranchCreator
Generate same-level competing diagnostic branches for the current root.
Return strict JSON with keys branches, frontier, need_external_knowledge,
knowledge_query_if_needed.
```

**3行，无任何关于前沿策略、"不可漏诊"分支、抽象级别约束的指导。**

#### 完整版要求（readme.md §9.3）

完整版要求：
- 默认 2–4 个活跃分支 + 1–2 个停泊分支 + 可选残差 OTHER；
- 若 `plausibility(B) > test_threshold` 或 `danger(B)` 高 或 `B 唯一解释关键未解证据` 则保留分支；
- 需包含至少一个"不可漏诊"分支（若情况允许）；
- 仅在内部分支框架不稳定时才检索外部方案/指南。

SDBench 规格额外要求：精确输出 3 个活跃分支 + OTHER mass，且每个分支要说明 `why_included`。

#### 差距

| 差距项 | 说明 |
|--------|------|
| 分支包含规则缺失 | 提示词未提供"保留/排除"判断准则 |
| "不可漏诊"分支缺失 | 无指令要求包含高危分支 |
| 多层级分支树未实现 | 所有分支均为 level=1，无子分支展开 |
| `actionability`/`explanatory_coverage` 未填充 | 这两个字段恒为 0.0 |
| SDBench 的 OTHER mass 处理不完整 | `other_mass` 在 `initialize_sdbench_top3()` 中通过求和计算，但后续更新时未同步维护 |

---

### 模块 D：TemporaryLeafPlanner（临时叶子规划）

#### 当前实现

```python
# controller.py: plan_temporary_leaves()
def plan_temporary_leaves(self, state):
    planner_module = "TemporaryAnalyticLeafPlanner" if self._in_static_qa_mode() \
                     else "TemporaryLeafPlanner"
    result = self._call_module(planner_module, state.to_dict())
    leaves = []
    for idx, x in enumerate(result["candidate_leaves_ranked"]):
        leaves.append(CandidateLeaf(
            leaf_id=f"{x['branch_id']}::{x['type']}::{idx}",
            branch_id=x["branch_id"],
            leaf_type=x["type"],
            content=x["content"],
            expected_information_gain=x.get("expected_information_gain", 0.0),
            expected_cost=x.get("expected_cost", 0.0),
            expected_delay=x.get("expected_delay", 0.0),
            safety_value=x.get("safety_value", 0.0),
            action_separation_value=x.get("action_separation_value", 0.0),
            total_score=x["score"],
        ))
    selected = result["selected_primary_action"]
    # SDBench 模式：将 ASK/TEST/DIAGNOSE 反向映射为内部类型
    if self._in_sdbench_mode() and selected["type"] in {"ASK", "TEST", "DIAGNOSE"}:
        mapping = {"ASK": "ASK_PATIENT", "TEST": "REQUEST_TEST_OR_MEASUREMENT", 
                   "DIAGNOSE": "DIAGNOSIS_READY"}
        selected = {"type": mapping[selected["type"]], "content": selected["content"]}
    return leaves, selected
```

随后调用 `update_estimated_remaining_value()`，取 `candidate_leaves` 中 `total_score` 的最大值作为 `estimated_remaining_value`。在 SDBench 和 Static QA 模式下，若辩论产生了 `consensus_action`，会覆盖叶子规划器的选择。

#### 所依赖提示词

**文件**（交互模式）：`src/agentclinic_tree_dx/prompts/temporary_leaf_planner.txt`

```
Role: TemporaryLeafPlanner
Create ranked candidate leaves and choose exactly one primary next action.
Return strict JSON with keys candidate_leaves_ranked and selected_primary_action.
```

**文件**（Static QA 模式）：`src/agentclinic_tree_dx/prompts/temporary_analytic_leaf_planner.txt`

```
Role: TemporaryAnalyticLeafPlanner
Generate analytic temporary leaves over fixed evidence and pick one. Return strict JSON.
```

**两者均为 2–3 行，无评分公式、无动作类型约束、无全局排序算法。**

#### 完整版要求（readme.md §9.4）

完整版评分公式：
```
LeafScore(L) = ExpectedInformationGain(L) + SafetyValue(L) + ActionSeparationValue(L)
             - CostPenalty(L) - DelayPenalty(L)
```

AgentClinic 补丁模式的修订公式：
```
LeafScore = InfoGain + DiagnosisCommitmentValue + SafetyValue
           - TurnCost - TestCost - Delay - RedundancyPenalty
```

还要求：为每个活跃分支生成能将其与竞争分支分离的候选判别器，所有分支的候选合并为一个全局列表后排序，选出且仅选出一个主动作。

#### 差距

| 差距项 | 说明 |
|--------|------|
| 评分公式缺失 | 提示词无任何评分公式，评分完全由 LLM 自由决定 |
| 诊断承诺价值未建模 | AgentClinic patch 模式的 `DiagnosisCommitmentValue` 未纳入提示词 |
| 全局排序机制缺失 | 提示词无指令要求"合并所有分支的候选后全局排序" |
| 冗余惩罚缺失 | 未指导 LLM 识别和惩罚已执行或重复的动作 |
| `expected_information_gain` 等子字段 | LLM 输出通常不填充这些字段，控制器用 0.0 作为默认值 |

---

### 模块 E：Action Executor（动作执行）

#### 当前实现

`execute_primary_action()` 在控制器中直接实现（共约 100 行），分三层处理：

1. **模式标准化**：将内部动作类型映射为对外接口（SDBench: `ASK/TEST/DIAGNOSE`；AgentClinic patch: `ASK_PATIENT/REQUEST_TEST_OR_MEASUREMENT/...`；Static QA: `ANALYZE_VIGNETTE/SELECT_OPTION/DIAGNOSIS_READY`）；
2. **Static QA 工具门控**：若动作类型为 `USE_CALCULATOR` 或 `RETRIEVE_KNOWLEDGE`，先调用 `ToolUseGate` 模块，若返回 `allow=False` 则直接返回 `{"tool_blocked": True}`；
3. **分模式路由**：根据模式选择调用环境适配器的哪个方法（`ask_gatekeeper`、`ask_patient`、`request_test`、`order_lab` 等）。

`executor.py` 中只定义了 `ALLOWED_ACTIONS` 常量集合，不包含任何执行逻辑。

#### 所依赖提示词

动作执行本身无提示词。`ToolUseGate` 模块在 Static QA 模式下使用：

**文件**：`src/agentclinic_tree_dx/prompts/tool_use_gate.txt`

```
Role: ToolUseGate
Decide whether calculator/retrieval is allowed under static QA policy.
Return strict JSON: allow, reason, justification.
```

#### 完整版要求

规格要求"每轮只执行一个主动作"（已实现）。SDBench 规格还要求支持**问题批处理**（question batching）：一个 ASK 动作可以包含多个相关问题（以列表形式），且 ASK 和 TEST 内容不得混合在同一轮。

#### 差距

| 差距项 | 说明 |
|--------|------|
| 问题批处理未实现 | SDBench 规格要求 ASK 可包含多问题列表，当前实现只处理单一字符串内容 |
| 内部工具用于外部推理的分离 | 规格要求计算器/知识检索作为"内部推理支持"，不违反对外动作契约，当前代码无此层面的显式隔离 |
| `ToolUseGate` 提示词极简 | 无基准纯洁性规则细节 |

---

### 模块 F：EvidenceAnnotator（证据注释）

#### 当前实现

```python
# controller.py: annotate_evidence()
def annotate_evidence(self, state, raw_result):
    return self._call_module("EvidenceAnnotator", 
                             {"state": state.to_dict(), "raw_result": raw_result})
```

LLM 返回的 `annotation` 字典直接传给更新路由器。控制器不验证 `branch_effects` 中的 key 是否与当前 `state.branches` 的 key 匹配——若 LLM 返回了不存在的分支 ID，后续更新会静默跳过。

#### 所依赖提示词

**文件**：`src/agentclinic_tree_dx/prompts/evidence_annotator.txt`

```
Role: EvidenceAnnotator
Annotate evidence impact by branch without changing structure.
Return strict JSON with keys result_summary, major_update, calculator_applicable,
formal_rule_available, branch_effects, contradiction_detected, reopen_candidates.
```

**3行，无任何证据分类规则或效应强度定义。**

#### 完整版要求（readme.md §9.6）

完整版要求 LLM 明确：
- 总结结果；
- 分类每个分支的支持/反对关系；
- 检测矛盾；
- 检测共存可能性；
- 检测是否适用计算器或规则更新。

AgentClinic 补丁模式还要求额外说明：该结果是否应提升诊断就绪度、是否仍值得再进行一轮问诊/检查、是否产生足够强的矛盾以触发停泊分支重开。

#### 差距

| 差距项 | 说明 |
|--------|------|
| 效应强度定义缺失 | 提示词未解释各效应标签（`strong_for` 等）的含义 |
| AgentClinic patch 额外要求缺失 | 未要求 LLM 输出诊断就绪度变化或重开触发信号 |
| 分支 ID 合法性校验缺失 | 控制器不验证 LLM 返回的分支 ID 是否合法 |
| 矛盾触发重开机制缺失 | `reopen_candidates` 字段虽被收集，但在 `revise_branch_states()` 中完全由 LLM（PostUpdateStateReviser）决定，无基于 `reopen_candidates` 的确定性触发逻辑 |

---

### 模块 G：UpdateRouter（更新路由）

#### 当前实现

```python
# update_router.py
def choose_update_method(annotation: dict) -> str:
    if annotation.get("calculator_applicable", False):
        return "calculator"
    if annotation.get("formal_rule_available", False):
        return "rule_based"
    return "ordinal"
```

**路由逻辑本身已正确实现。**

```python
# controller.py: apply_probability_update()
def apply_probability_update(self, state, annotation, method):
    # Naive placeholder: calculator and rule paths are mapped to ordinal update.
    posteriors = ordinal_update(state.branches, annotation)
    for bid, branch in state.branches.items():
        branch.prior = branch.posterior
        branch.posterior = posteriors[bid]
```

**关键问题**：`apply_probability_update` 完全忽略了 `method` 参数，无论路由结果是什么，**三条路径均执行序数更新**。

#### 所依赖提示词

无提示词（纯确定性逻辑）。

#### 完整版要求（readme.md §9.7、§9.8）

- `calculator` 路径：需调用真实临床评分工具（Wells Score、CURB-65 等），利用计算结果（如 LR+/LR-）对分支概率进行贝叶斯更新；
- `rule_based` 路径：应用基准/环境编码的形式化解读逻辑；
- `major_update=True` 时：重新计算祖先节点，重新评估兄弟节点，若矛盾严重则考虑修订根节点。

#### 差距

| 差距项 | 说明 |
|--------|------|
| **calculator_update 为死代码** | 路由到 calculator 时仍走序数更新，计算器路由结果被完全忽略 |
| **rule_based_update 为死代码** | 同上 |
| `major_update` 处理缺失 | `annotation["major_update"]` 被收集但从未被利用，不触发任何额外逻辑 |
| 祖先重计算未实现 | 多层级树中的祖先节点概率传播逻辑缺失 |
| OTHER mass 未参与更新 | SDBench 模式下 `other_mass` 不随每轮更新而调整 |

---

### 模块 H：PostUpdateStateReviser（后更新状态修订）

#### 当前实现

```python
# controller.py: revise_branch_states()
def revise_branch_states(self, state):
    result = self._call_module("PostUpdateStateReviser", state.to_dict())
    new_frontier = []
    for d in result["branch_decisions"]:
        branch = state.branches[d["branch_id"]]
        decision = d["decision"]
        if decision == "confirm":
            branch.status = "confirmed"
        elif decision == "close_for_now":
            branch.status = "closed_for_now"
        elif decision == "park":
            branch.status = "parked"
        elif decision in {"reopen", "expand_now", "keep_coarse"}:
            branch.status = "reopened" if decision == "reopen" else "live"
            new_frontier.append(branch.id)
        else:
            branch.status = "live"
            new_frontier.append(branch.id)

    max_frontier = self.config.max_live_frontier
    if self._in_sdbench_mode():
        max_frontier = min(max_frontier, 3)
    state.frontier = new_frontier[:max_frontier]
```

#### 所依赖提示词

**文件**：`src/agentclinic_tree_dx/prompts/post_update_state_reviser.txt`

```
Role: PostUpdateStateReviser
Given updated state, choose branch structural decisions.
Return strict JSON with key branch_decisions.
```

**2行，无任何转移规则、阈值或评分公式。**

#### 完整版要求（readme.md §9.9）

完整版指定了严格的转移规则：
- **confirm**：`posterior >= commit_threshold` 且子分支细分不改变当前决策周期；
- **close_for_now**：`posterior < test_threshold` 且无唯一解释的关键未解证据且进一步追踪不影响当前管理；
- **park**：非当前主导、仍够可信、立即细化的期望价值低；
- **expand_now**：`ExpandScore(B) = RemainingUncertainty × ExpectedActionDifference × ExpectedInfoGain × SafetyWeight - CostOfExpansion > 0`。

AgentClinic 补丁规格还要求：向更窄前沿方向施加更强压力，更早停泊低价值分支。

#### 差距

| 差距项 | 说明 |
|--------|------|
| 转移阈值未传递给 LLM | 提示词未提供 `commit_threshold`、`test_threshold` 等配置值 |
| ExpandScore 公式缺失 | LLM 不知道 `expand_now` 的计算方式，完全自由裁量 |
| 重开的确定性触发缺失 | `annotation["reopen_candidates"]` 不作为确定性输入传递给此模块，重开决策完全由 LLM 主观判断 |
| 子分支创建逻辑缺失 | `expand_now` 决策后未创建子分支节点，树结构始终是一层 |

---

### 模块 I：TerminationJudge（终止判断）

#### 当前实现

```python
# controller.py: check_termination()
def check_termination(self, state):
    result = self._call_module("TerminationJudge", state.to_dict())
    return TerminationState(
        ready_to_stop=result["ready_to_stop"],
        termination_type=result.get("termination_type", "continue"),
        reason=result["reason"],
    )
```

**注意**：在 `check_termination()` 之前，控制器已先调用 `check_diagnosis_readiness()`（Patch/SDBench/Static QA 模式下），若就绪度门控通过则**直接返回**，不调用 `TerminationJudge`。仅在就绪度门控未通过时才走到 `TerminationJudge`。轮次预算耗尽时也直接停止，不调用 `TerminationJudge`。

#### 所依赖提示词

**文件**：`src/agentclinic_tree_dx/prompts/termination_judge.txt`

```
Role: TerminationJudge
Decide whether tree expansion should stop.
Return strict JSON with keys ready_to_stop, termination_type, reason,
if_continue_next_best_action_type.
```

**3行，无5种终止类型的触发条件描述。**

#### 完整版要求（readme.md §9.10）

完整版定义了5种明确终止类型及其触发条件：
1. `confirmation`：一个分支足够确认；
2. `actionable_parent`：多个子分支未解决但共用同一管理路径；
3. `info_exhaustion`：无进一步可用判别器能改变管理；
4. `working_differential`：显式不确定性管理是正确终点；
5. `emergency_override`：紧急干预覆盖进一步扩展。

SDBench 规格的终止判断更严格：基准面向输出必须是单一诊断字符串，而非广泛的管理计划。

#### 差距

| 差距项 | 说明 |
|--------|------|
| 5种终止类型的触发条件未在提示词中定义 | LLM 不知道各终止类型的具体触发标准 |
| `actionable_parent` 概念缺失 | 提示词未描述什么是"actionable parent syndrome"及其判断条件 |
| `check_diagnosis_readiness()` 与 `TerminationJudge` 的关系不清晰 | 就绪度门控在 Patch 模式下完全跳过了 TerminationJudge，功能存在重叠 |

---

### 模块 J：FinalAggregator / FinalDiagnosisEmitter / AnswerMapper（最终聚合）

#### 当前实现

```python
# controller.py: final_aggregate()
def final_aggregate(self, state):
    # Static QA 模式
    if self._in_static_qa_mode():
        mapped = self._call_module("AnswerMapper", {"state": state.to_dict(), 
                                                     "options": state.static_options})
        return {"final_answer": mapped.get("final_answer", ""),
                "answer_option_mapping": ..., "internal_reasoning_state": ...}
    
    # SDBench 模式
    if self._in_sdbench_mode():
        emitter = self._call_module("FinalDiagnosisEmitter", {"state": ..., 
                                                               "internal_reasoning_state": ...})
        diagnosis = emitter.get("final_diagnosis", "undetermined")
        submitted = self.env.submit_diagnosis(diagnosis)
        return {"diagnosis": diagnosis, "submission": submitted, 
                "internal_reasoning_state": ...}
    
    # default / agentclinic_physician_patch 模式
    final_output = self._call_module("FinalAggregator", state.to_dict())
    if hasattr(self.env, "review_with_moderator"):
        final_output["moderator_review"] = self.env.review_with_moderator(final_output, state)
    if self._in_patch_mode():
        diagnosis = final_output.get("leading_diagnosis_or_parent", "undetermined")
        return {"internal_reasoning_state": final_output,
                "benchmark_output": f"Diagnosis Ready: {diagnosis}"}
    return final_output
```

#### 所依赖提示词

**FinalAggregator**（`prompts/final_aggregator.txt`）：
```
Role: FinalAggregator
Produce final AgentClinic output payload.
Return strict JSON with final_mode and required final output fields.
```

**FinalDiagnosisEmitter**（`prompts/final_diagnosis_emitter.txt`）：
```
Role: FinalDiagnosisEmitter
Output exactly one final diagnosis string. Return strict JSON with final_diagnosis.
```

**AnswerMapper**（`prompts/answer_mapper.txt`）：
```
Role: AnswerMapper
Map internal diagnosis reasoning to a single benchmark answer option. Return strict JSON
with final_answer.
```

**三者均为 2 行，无输出模式选择规则或诊断字符串格式规范。**

#### 完整版要求

AgentClinic 补丁规格要求将最终聚合分为两层：
- `internal_final_aggregate()`：保留完整鉴别诊断、不确定性、支持/冲突证据；
- `render_agentclinic_output()`：仅输出基准评估兼容的单一诊断字符串。

FinalAggregator 的4种输出模式（`single_leading_diagnosis`、`actionable_parent`、`coexisting_diagnoses`、`ranked_working_differential`）的选择规则未在提示词中定义。

#### 差距

| 差距项 | 说明 |
|--------|------|
| 输出模式选择规则缺失 | 提示词未指导 LLM 何时选择 4 种输出模式中的哪一种 |
| 内/外层聚合分离未实现 | AgentClinic patch 规格要求的双层聚合在代码中被简化为单次调用后直接格式化输出 |
| 诊断字符串格式规范缺失 | `Diagnosis Ready: <diagnosis>` 格式在控制器中硬编码，未经 LLM 确认诊断名称是否符合基准评分期望格式 |

---

## 第二部分：模式专用模块

---

### 模块 K：辩论层（SDBench 模式专用）

#### 当前实现

```python
# controller.py: run_deliberation()
def run_deliberation(self, state: DiagnosticState) -> DeliberationState:
    d = DeliberationState()
    payload = state.to_dict()
    d.hypothesis_analysis   = self._call_module("Hypothesis", payload)
    d.test_chooser_analysis = self._call_module("TestChooser", payload)
    d.challenger_analysis   = self._call_module("Challenger", payload)
    d.stewardship_analysis  = self._call_module("Stewardship", payload)
    d.checklist_analysis    = self._call_module("Checklist", {
        "state": payload,
        "proposed_actions": d.test_chooser_analysis,
    })
    d.consensus_action = self._call_module("Consensus", {
        "state": payload,
        "deliberation": {
            "hypothesis": d.hypothesis_analysis,
            "test_chooser": d.test_chooser_analysis,
            "challenger": d.challenger_analysis,
            "stewardship": d.stewardship_analysis,
            "checklist": d.checklist_analysis,
        },
    })
    return d
```

6个角色依次调用，每次将整个 `state.to_dict()` 作为载荷，**早期角色的输出不作为后续角色（除 Checklist 和 Consensus 外）的显式输入**。

#### 所依赖提示词（6个文件）

| 角色 | 文件 | 完整内容 |
|------|------|---------|
| Hypothesis | `hypothesis.txt` | `Role: Hypothesis` / `Propose and refine differential hypotheses for current top-k branches. Return strict JSON.` |
| TestChooser | `test_chooser.txt` | `Role: TestChooser` / `Recommend high-value next ASK/TEST candidates for discrimination. Return strict JSON.` |
| Challenger | `challenger.txt` | `Role: Challenger` / `Critique overconfidence and identify contradictions/alternatives. Return strict JSON.` |
| Stewardship | `stewardship.txt` | `Role: Stewardship` / `Assess efficiency, urgency, and redundancy for next action. Return strict JSON.` |
| Checklist | `checklist.txt` | `Role: Checklist` / `Validate benchmark legality: only ASK/TEST/DIAGNOSE externally. Return strict JSON with valid/issues.` |
| Consensus | `consensus.txt` | `Role: Consensus` / `Choose exactly one benchmark-facing action. Return strict JSON: action_type, content, reasoning.` |

**所有 6 个提示词均为 2 行，无结构化输出 schema、无角色间协作规则。**

#### 完整版要求（sdbench_tree_dx_spec.md §8、§11）

SDBench 规格为每个角色定义了详细的 JSON 输出 schema 和操作规则：

**Hypothesis**：应输出 `{top3: [{branch_id, label, probability, rationale}], contradictory_evidence: [...]}`

**TestChooser**：应提出最多3个候选动作，每个标注目标分支 (`target_branches`)、动作类型 (`ASK/TEST`)、理由

**Challenger**：应输出 `{anchoring_risk, contradictions, reopen_candidates, falsification_action}`

**Stewardship**（baseline 模式）：不以金钱成本为否决条件，而是最小化冗余和浪费轮次；输出 `{redundant_candidates, preferred_low_waste_candidate, reason}`

**Checklist**：验证动作是否基准合法（仅 ASK/TEST/DIAGNOSE，禁止 ASK+TEST 混合，禁止重复）

**Consensus**：从前5个角色的输出中综合选择一个 `{action_type: "ASK|TEST|DIAGNOSE", content, reasoning}`

#### 差距

| 差距项 | 说明 |
|--------|------|
| 角色间信息流不完整 | Hypothesis、TestChooser、Challenger、Stewardship 调用时均只看 state，互相不知道其他角色的分析结论；只有 Checklist 和 Consensus 收到了前几个角色的输出 |
| 输出 schema 未在提示词中定义 | 各角色应输出的 JSON 结构未指定，LLM 可能输出不兼容格式 |
| `stagnation_detected` 未实现 | 规格中 `DeliberationState` 含 `stagnation_detected` 字段，当前 `DeliberationState` 无此字段 |
| 问题批处理未纳入 TestChooser | TestChooser 提示词未提及 ASK 可包含多个问题列表 |
| Stewardship 无基线成本关闭逻辑 | 提示词未明确说明"不以金钱成本为否决条件" |

---

### 模块 L：Static QA 辩论层（Static QA 模式专用）

#### 当前实现

```python
# controller.py: run_static_qa_deliberation()
def run_static_qa_deliberation(self, state: DiagnosticState) -> DeliberationState:
    d = DeliberationState()
    payload = state.to_dict()
    d.hypothesis_analysis   = self._call_module("Hypothesis", payload)
    d.test_chooser_analysis = self._call_module("EvidenceAllocator", payload)
    d.challenger_analysis   = self._call_module("Challenger", payload)
    d.stewardship_analysis  = self._call_module("ReasoningEconomyAuditor", payload)
    d.checklist_analysis    = self._call_module("Checklist", payload)
    d.consensus_action      = self._call_module("Consensus", {
        "state": payload,
        "deliberation": d.checklist_analysis,  # 注意：只传了 checklist 输出
    })
    return d
```

与 SDBench 辩论的关键区别：`Consensus` 的 `deliberation` 参数只包含 `checklist_analysis`，而不是全部5个角色的输出。

#### 所依赖提示词

| 角色 | 文件 | 完整内容 |
|------|------|---------|
| EvidenceAllocator | `evidence_allocator.txt` | `Role: EvidenceAllocator` / `Allocate next direct/derived/interpretive evidence operation from fixed vignette evidence. Return strict JSON.` |
| ReasoningEconomyAuditor | `reasoning_economy_auditor.txt` | `Role: ReasoningEconomyAuditor` / `Audit benchmark purity, avoid unnecessary cycles/tool use, and output strict JSON.` |

（Hypothesis、Challenger、Checklist、Consensus 与 SDBench 模式共用相同提示词文件）

#### 差距

| 差距项 | 说明 |
|--------|------|
| Consensus 信息输入严重不足 | Static QA 模式下 Consensus 只能看到 Checklist 输出，而 SDBench 模式下 Consensus 能看到所有 5 个角色的分析；这是代码 bug，可能是疏漏 |
| EvidenceAllocator 输出 schema 未定义 | 规格中未详细描述其输出格式，实现提示词也只有 2 行 |
| ReasoningEconomyAuditor 基准纯洁性规则缺失 | 提示词无具体的"基准纯洁性"判断标准 |

---

### 模块 M：VignetteParser（Static QA 模式专用）

#### 当前实现

```python
# controller.py: parse_static_vignette()
def parse_static_vignette(self, state: DiagnosticState) -> None:
    parsed = self._call_module("VignetteParser", {"raw_case": state.case_summary})
    state.static_vignette = parsed.get("vignette", state.case_summary)
    state.static_question = parsed.get("question", "")
    state.static_options  = parsed.get("options", [])
    state.static_evidence_items = [
        EvidenceItem(
            id=item.get("id", f"direct::{idx}"),
            kind=item.get("kind", "direct"),
            content=item.get("content") or item.get("fact", ""),
            source_ids=item.get("source_ids", []),
            independent=item.get("independent", True),
            branch_links=item.get("branch_links", {}),
            metadata=item.get("metadata", {}),
        )
        for idx, item in enumerate(parsed.get("evidence_items", []))
    ]
```

仅在 `timestep == 1` 时调用一次。`EvidenceItem` 中的 `kind`（`direct`/`derived`/`interpretive` 三类）由 LLM 自由分配。

#### 所依赖提示词

**文件**：`src/agentclinic_tree_dx/prompts/vignette_parser.txt`

```
Role: VignetteParser
Parse static vignette into structured evidence items, question stem, and options.
Return strict JSON.
```

**2行，无证据类型定义、无证据独立性处理规则。**

#### 完整版要求（static_diagnosis_qa_mode_spec.md 系列）

规格要求将证据分为三类并给出处理策略：
- **direct**（直接事实）：可直接使用；
- **derived**（推导性）：需要推理步骤才能使用；
- **interpretive**（解释性）：依赖上下文解读。

还要求处理证据间依赖关系（`source_ids` 字段）、独立性假设（`independent` 字段），以及将每条证据预先映射到相关分支（`branch_links`）。

#### 差距

| 差距项 | 说明 |
|--------|------|
| 证据类型分类规则缺失 | 提示词无 direct/derived/interpretive 三类的定义 |
| 证据独立性处理缺失 | `independent` 字段由 LLM 自由填充，无处理规则 |
| 证据-分支预映射缺失 | `branch_links` 字段在 VignetteParser 时被填充，但后续未在 EvidenceAnnotator 中利用 |

---

### 模块 N：DiagnosisReadinessGate（就绪度门控，Patch/SDBench/Static QA 专用）

#### 当前实现

```python
# controller.py: check_diagnosis_readiness()
def check_diagnosis_readiness(self, state: DiagnosticState) -> bool:
    if not state.branches:
        state.diagnosis_readiness_score = 0.0
        return False
    
    ranked = sorted(state.branches.values(), key=lambda b: b.posterior, reverse=True)
    leader = ranked[0]
    state.diagnosis_readiness_score = leader.posterior
    
    if leader.posterior < self.config.min_readiness_to_commit:
        return False
    
    if self._in_patch_mode():
        dangerous_alternative_exists = any(
            b.id != leader.id and b.danger >= 0.7 and b.posterior >= 0.15 for b in ranked
        )
        cheap_high_yield_exists = any(
            leaf.total_score >= 0.8 and leaf.expected_cost <= 0.2 for leaf in state.candidate_leaves
        )
        repeated_last_action = False
        if len(state.actions_taken) >= 2:
            repeated_last_action = (state.actions_taken[-1]["content"] == 
                                    state.actions_taken[-2]["content"])
        
        if dangerous_alternative_exists or cheap_high_yield_exists or repeated_last_action:
            return False
    
    return True
```

**唯一一个含有具体数值阈值的确定性非 LLM 逻辑模块。**

#### 所依赖提示词

无提示词（纯确定性逻辑）。

#### 完整版要求（agentclinic_patch_development_documentation.md §4.5）

规格要求：
1. 一个分支后验概率足够高，可进行基准承诺；
2. 不存在仍值得用廉价判别器排除的危险备选诊断；
3. 不存在仍然高价值低成本的动作（期望改变答案）；
4. 已准备好以预期的最终格式渲染诊断。

SDBench 模式和 Static QA 模式的门控条件与 Patch 模式的门控条件是否相同？**目前代码中 `_in_patch_mode()` 为真时才应用完整门控，其他两个模式只检查 `leader.posterior < min_readiness_to_commit`，跳过危险备选和廉价高价值判别器检查。**

#### 差距

| 差距项 | 说明 |
|--------|------|
| SDBench/Static QA 模式门控条件过宽 | 非 Patch 模式只检查后验概率阈值，不检查危险备选和廉价高价值动作 |
| 阈值硬编码 | `danger >= 0.7`、`posterior >= 0.15`、`total_score >= 0.8`、`expected_cost <= 0.2` 均为硬编码常量，未暴露在 `ControllerConfig` 中 |
| `cheap_high_yield_exists` 判断依赖 LLM 的 `expected_cost` | `expected_cost` 通常为 0.0（LLM 不填充），导致此条件实际上总是为 False |

---

## 第三部分：占位工具模块

---

### 模块 O：calculator_router（计算器路由）

#### 当前实现

```python
# tools/calculator_router.py
def naive_calculator_router(query: str, state: object | None = None) -> dict:
    return {
        "tool": "naive_calculator",
        "query": query,
        "result": "placeholder_score",
        "note": "Naive LLM-style placeholder used for calculator path.",
    }
```

返回固定占位字典，不解析 `query` 内容，不执行任何计算。

#### 完整版要求

规格要求：
1. 解析临床评分请求（如 "Wells Score for DVT"）；
2. 从 `state` 中提取所需输入变量；
3. 执行评分计算；
4. 返回数值结果及其对分支概率的影响（如 LR+ = 3.0 时对应的贝叶斯更新）。

#### 差距

整个模块为占位，**所有功能均未实现**。具体缺少：
- 评分类型解析器
- 状态字段提取器
- 评分计算引擎（Wells DVT、HEART Score、CURB-65 等）
- 贝叶斯更新计算（LR+ × prior odds）

---

### 模块 P：knowledge_router（知识路由）

#### 当前实现

```python
# tools/knowledge_router.py
def naive_knowledge_router(query: str) -> dict:
    return {
        "tool": "naive_knowledge_lookup",
        "query": query,
        "summary": "Placeholder external context from naive LLM interaction.",
    }
```

返回固定占位字典，不执行任何检索。

#### 完整版要求

规格要求在以下场景下提供有效知识检索：
- RootSelector 请求案例框架（`need_external_knowledge=True`）；
- BranchCreator 请求诊断方案/指南；
- 执行 `RETRIEVE_KNOWLEDGE` 动作时。

#### 差距

整个模块为占位，**所有功能均未实现**。具体缺少：
- 医学知识 API 接入（如 PubMed Entrez、UpToDate）
- 查询结构化（将自由文本查询转为 API 参数）
- 结果摘要生成
- 注入后上下文的利用机制（`env.external_context` 目前只存储数据，不影响后续 LLM 调用）

---

## 第四部分：跨模式综合差距汇总

| 维度 | 当前状态 | 完整版要求 |
|------|---------|----------|
| **提示词质量** | 全部 21 个提示词文件均为 2–3 行（角色名 + 输出 key 列表），无任何操作规则 | 规格文档为每个模块提供了数十行详细的角色说明、判断规则和 JSON schema |
| **概率更新路径** | 三条路径（calculator/rule_based/ordinal）均执行序数更新 | calculator 和 rule_based 路径应执行不同的数学逻辑 |
| **树的深度** | 最多一层（ROOT → Branch），无子分支展开 | expand_now 决策应能创建子分支，实现真正的递归分解 |
| **major_update 处理** | 完全被忽略 | 应触发祖先重计算、兄弟节点重评估、可能的根节点修订 |
| **重开机制** | 完全依赖 LLM（PostUpdateStateReviser）自由判断 | 应有基于 `reopen_candidates` 和 `contradiction_detected` 的确定性触发逻辑 |
| **根节点修订** | `root_changed_materially()` 恒返回 False，根节点不会被修订 | 应在新证据产生强烈矛盾时触发根节点修订 |
| **外部知识注入的利用** | `env.external_context` 仅存储，不影响后续 LLM 调用的上下文 | 注入的知识应被后续模块调用时实际传递给 LLM |
| **SDBench OTHER mass** | 初始化时计算，但后续更新不维护 | 每轮概率更新后应同步调整 OTHER mass |
| **问题批处理（SDBench）** | 仅支持单字符串 content，不支持问题列表 | SDBench ASK 动作应支持多问题列表 |
| **辩论角色间信息流** | 早期角色输出不作为后续角色的显式输入 | Challenger 应能看到 TestChooser 的提案，Stewardship 应能看到所有前置分析 |
| **工具模块** | calculator_router 和 knowledge_router 均为占位实现 | 应实现真实的临床评分计算和医学知识检索 |

---

*文档生成时间：2026-04-28*  
*基于代码分支：`codex/verify-agentclinic-compatibility-with-projects`*
