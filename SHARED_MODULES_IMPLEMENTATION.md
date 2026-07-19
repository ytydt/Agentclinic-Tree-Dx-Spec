# 共享模块实现算法详解

> 本文档描述此次更新后各共享模块（所有执行模式均使用）的完整实现逻辑，包括其所依赖提示词的完整内容，以及提示词与代码之间的协作关系。
>
> **共享模块**：指在 `default`、`agentclinic_physician_patch`、`sdbench_patch`、`static_diagnosis_qa` 四种模式中均被调用的模块，对应主循环中"规划阶段 A–D"和"同化阶段 F–L"的全部步骤。

---

## 控制器主循环概览

每轮执行顺序如下（`controller.py: run()`）：

```
[每轮开始]
 A. SafetyController          ← 安全筛查
 B. RootSelector              ← 根节点选择/修订（条件触发）
 C. BranchCreator             ← 分支创建（条件触发）
    （SDBench/Static QA 模式在此处插入辩论层）
 D. TemporaryLeafPlanner      ← 临时叶子规划
 E. execute_primary_action    ← 执行选定动作（无提示词）
 F. EvidenceAnnotator         ← 证据注释
 G. UpdateRouter              ← 更新方法路由（纯确定性，无提示词）
 H. apply_probability_update  ← 概率更新（纯算法，无提示词）
    └─ _handle_major_update   ← major update 后处理（纯算法）
 I. PostUpdateStateReviser    ← 分支状态修订
    └─ _apply_reopen_overrides← 确定性重开覆盖（纯算法）
 J. record_differential_history ← 历史记录（纯算法）
 K. check_diagnosis_readiness ← 就绪度门控（Patch/SDBench/Static QA，纯算法）
 L. TerminationJudge          ← 终止判断
 M. FinalAggregator / FinalDiagnosisEmitter / AnswerMapper ← 最终聚合
[循环结束]
```

---

## 阶段 A：SafetyController（安全筛查）

### 实现逻辑

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

控制器将当前完整状态序列化后发送给 LLM（经 `SafetyController` 提示词）。  
LLM 返回 JSON，控制器从中构造 `InterruptState` 对象写入 `state.interrupt`。

**若 `interrupt.active = True`**：
1. 调用 `execute_emergent_actions(state)` —— 将 `required_actions` 逐条追加到 `env.emergent_actions` 列表（注：实际外部执行依赖各环境适配器的 `take_emergent_action()` 实现）；
2. 检查 `env.patient_still_unstable()`，若仍不稳定则 `continue`（跳过本轮后续所有步骤，进入下一轮）；
3. 若已稳定，照常继续后续规划步骤。

### 所依赖提示词

**文件**：`src/agentclinic_tree_dx/prompts/safety_controller.txt`

```
Role: SafetyController

Inspect the current case state and determine whether immediate intervention must
occur before further diagnostic expansion.

Rules:
1. Check for universal instability markers: airway compromise, severe respiratory
   compromise, shock or major haemodynamic instability (hypotension, tachycardia
   with end-organ signs), severe altered mental status with instability,
   uncontrolled haemorrhage.
2. Check for time-critical syndrome patterns that require action before the
   differential is fully resolved (e.g., STEMI, stroke, tension pneumothorax,
   septic shock, meningitis with herniation risk).
3. If any instability criterion is met, set interrupt_active: true and list the
   required immediate actions.
4. If interrupt is inactive, explicitly state which universal instability criteria
   were assessed and why each is not met.
5. Do not retrieve external knowledge unless it would immediately alter emergency
   action without delaying stabilisation.

Return strict JSON only, no markdown:
{
  "interrupt_active": true,
  "reason": "brief clinical rationale",
  "required_actions": ["action 1", "action 2"],
  "why_not_interrupt_if_false": []
}
```

**提示词与代码的协作方式**：
- LLM 负责：识别具体临床紧急情况、给出必要动作列表；
- 代码负责：构造 `InterruptState`、触发 `execute_emergent_actions`、控制循环流程。

---

## 阶段 B：RootSelector（根节点选择与修订）

> **版本注记（2026-05-18）**：本模块经历了重大提示词重设计和代码加固，解决了原版的三类偏差——字面化主诉、单一机制锚定、选项污染。详见下文。

### 实现逻辑

**触发条件**（`controller.py: run()`）：
```python
root_needs_revision = state.root_revision_needed          # 由 _handle_major_update 设置
if state.root is None or root_needs_revision:
    state.root = self.select_root(state)
    state.root_revision_needed = False                    # 修订后清除标志

if not state.branches or root_needs_revision or self.env.root_changed_materially(state):
    state.branches, state.frontier = self.create_branches(state)
```

首次调用（`state.root is None`）或上一轮 `_handle_major_update` 设置了修订标志时触发。

**`select_root()` 完整逻辑**（含选项屏蔽）：
```python
def _root_selector_payload(self, state) -> dict:
    """构造 RootSelector 专用 payload，屏蔽 MCQ 答案选项以防锚定偏差。"""
    payload = state.to_dict()
    payload["static_options"] = []            # 隐藏答案选项
    # 从 case_summary 中删除 "Question:" / "Options:" 块
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
        alarm_features=result.get("alarm_features", []),   # ← 新字段
    )
```

**外部知识路径**（抽象）：当 LLM 请求外部知识时，调用 `knowledge_router`（当前为占位实现），将结果注入 `env.external_context` 后重新调用本模块。

**根节点修订触发机制**（`_handle_major_update`，见阶段 H）：
```
EvidenceAnnotator 返回 contradiction_detected=True
    → apply_probability_update 调用 _handle_major_update
    → state.root_revision_needed = True
    → 下一轮循环开始时 select_root() 被重新调用
```

**`RootNode` 数据结构**（`state.py`）：
```python
@dataclass
class RootNode:
    label: str
    time_course: str
    severity: str
    confidence: float
    supporting_facts: list[str] = field(default_factory=list)
    excluded_candidates: list[str] = field(default_factory=list)
    alarm_features: list[str] = field(default_factory=list)   # ← 新增：报警特征
```

### 设计原则（v2，2026-05-18）

根节点是**综合征框架（syndrome frame）**，不是诊断。其核心职责是：

1. **开放鉴别空间**：标签必须保留所有合理机制，不过早闭合。使用"Possible X or Y Aetiology"而非"Suspected X Aetiology"。
2. **主诉优先**：主诉/主要症状群必须出现在标签核心词中；图像/图形引用词只作后缀修饰，不替代主诉。
3. **竞争机制注册**：`excluded_root_candidates` 作为竞争机制注册表，记录所有被考虑但排名较低的机制——**不仅是被彻底排除的**，而是供 BranchCreator 生成分支的备选库。
4. **选项污染防护**：payload 中的 MCQ 答案列表在传入 RootSelector 前被裁剪，防止模型锚定到可见答案词。
5. **证据层级（加权，非覆盖）**：客观发现（ECG > 实验室 > 体检 > 生命体征）优先于主观病史，但病史不被丢弃——进入 `supporting_facts` 或 `alarm_features`。
6. **图像缺失信号**：`kind="image_reference"` 的证据项触发根标签加入"Uncharacterised ECG/Imaging Abnormality"修饰词，`confidence ≤ 0.5`。
7. **新生儿/婴儿多系统综合征规则**：6月龄以下婴儿出现黄疸、肝脾大、发育落后、白内障等两项及以上并存时，代谢/遗传病（先天性代谢病）**必须**被列为高优先级竞争机制，不得以"多系统性质"为由降低其排名（多系统受累在此年龄段恰是代谢病的支持证据，而非反驳证据）。
8. **运动后意识改变规则**：马拉松等高强度耐力运动后出现 AMS 时，**必须**同时列入两项竞争机制：(a) 运动相关低钠血症（EAH，过量低渗液摄入→稀释性低钠→脑水肿，治疗：等渗/高渗盐水）；(b) 劳力性热射病（EHS，散热失败→高热→细胞损伤，治疗：快速降温）。二者管理措施相反，不可混淆。根标签病因短语应保持开放（如"with Possible Hyponatraemic or Hyperthermic Aetiology"），`confidence ≤ 0.6`，直至血清钠测定结果已知。

### 所依赖提示词

**文件**：`src/agentclinic_tree_dx/prompts/root_selector.txt`（当前完整版见文件，此处摘录算法核心）

**根标签组合顺序**（Algorithm Step 4）：
```
[temporal pattern]
+ [PRIMARY presenting syndrome — chief complaint or dominant symptom cluster]
+ [aetiology phrase — OPEN: "of Uncertain Aetiology",
   "with Possible Cardiac or Vasovagal Aetiology";
   name 1–2 COMPETING mechanisms, NOT a single committed one,
   unless evidence is near-conclusive (≥0.85 confidence)]
+ [image-reference qualifier if a Figure is referenced]
```

**神经解剖定位规则**（通常适用，非绝对）：

| 体征模式 | 通常定位 |
|---------|---------|
| 同侧颅神经缺损 + 对侧肢体运动/感觉丧失 | 脑干或颈延交界 |
| 对侧面部 + 对侧肢体缺损 | 大脑半球 |
| 双侧下肢运动/感觉丧失 ± 膀胱 | 脊髓 |
| 单侧上肢 ± 肩痛 ± Horner + 顶叶危险因素 | 臂丛/肺尖（T1/C8） |

**提示词与代码的协作方式**：
- LLM 负责：综合征框架命名、竞争机制枚举、证据层级评估、知识检索请求；
- 代码负责：选项污染防护（`_root_selector_payload`）、`RootNode` 构造、`root_revision_needed` 标志消费。

**验证结果（2026-05-18）**：
- 精准测试（7 个跨系统案例）：7/7，三维检验（关键词 + 禁止词 + 竞争机制 ≥2）
- 广泛测试（20 个随机案例）：20/20（其中 #6、#44 在域规则修复后通过）
- 修复后全量回归（26 个去重案例）：26/26
- 累计：26/26（含 #6 新生儿半乳糖血症修复 + #44 马拉松低钠血症修复）

> **注意**：`need_root_revision` 字段由 LLM 生成但目前不被代码读取——代码修订触发由 `_handle_major_update` 基于 `contradiction_detected` 驱动。两套机制并行，LLM 端预留供未来扩展。

---

## 阶段 C：BranchCreator（分支创建）

### 实现逻辑

**触发条件**：`state.branches` 为空、`root_needs_revision` 为真、或 `env.root_changed_materially()` 返回真时触发。

**`create_branches()` 完整逻辑**：
```python
def create_branches(self, state):
    result = self._call_module("BranchCreator", state.to_dict())
    # 外部知识请求（抽象路径）
    if result.get("need_external_knowledge", False) and self.config.allow_external_knowledge:
        knowledge = self.knowledge_router(...)
        self.env.ingest_external_context(knowledge)
        result = self._call_module("BranchCreator", state.to_dict())

    branches = {}
    for b in result["branches"]:
        branches[b["id"]] = Branch(
            id=b["id"], label=b["label"],
            parent="ROOT", level=1,          # 当前仅支持单层树
            status=b.get("status", "live"),
            prior=b.get("prior_estimate", 0.0),
            posterior=b.get("prior_estimate", 0.0),   # 初始 prior = posterior
            danger=b.get("danger", 0.0),
            actionability=0.0,               # 未由 LLM 填充，留作后续扩展
            explanatory_coverage=0.0,        # 同上
            askable_discriminators=b.get("askable_discriminators", []),
            requestable_discriminators=b.get("requestable_discriminators", []),
            turn_cost_to_refine=b.get("turn_cost_to_refine", 0.0),
            diagnosis_commitment_gain=b.get("diagnosis_commitment_gain", 0.0),
            interrupt_relevance=b.get("interrupt_relevance", 0.0),
        )
    return branches, result.get("frontier", [])
```

**SDBench 模式后处理**（`initialize_sdbench_top3`，在 `create_branches` 之后立即调用）：
```python
def initialize_sdbench_top3(self, state):
    ranked = sorted(state.branches.values(), key=lambda b: b.posterior, reverse=True)
    state.frontier = [b.id for b in ranked[:3]]          # 强制截取前3
    state.other_mass = sum(b.posterior for b in ranked[3:])  # 压缩其余为 OTHER mass
```

### 所依赖提示词

**文件**：`src/agentclinic_tree_dx/prompts/branch_creator.txt`

```
Role: BranchCreator

Generate schema-level competing branches under the current root node.

Instructions:
- Keep all branches at the same abstraction level (e.g., all at diagnosis-family
  level, not mixed with specific diagnoses).
- Include at least one can't-miss branch (high danger score, even if low prior
  probability) whenever the clinical context warrants it.
- Apply the branch inclusion rule: keep branch B if ANY of the following hold:
    plausibility(B) > test_threshold (0.05)
    OR danger(B) >= 0.7
    OR B uniquely explains unresolved critical evidence
- Default frontier policy: 2-4 live branches, 1-2 parked branches, optional
  residual OTHER.
- For each branch, estimate the fields that allow the controller to score leaf
  actions:
    askable_discriminators: questions that could help separate this branch
    requestable_discriminators: tests or exams that could separate this branch
    turn_cost_to_refine: approximate number of turns needed to resolve this branch
    diagnosis_commitment_gain: how much confirming this branch would raise
                               diagnosis readiness (0-1)
    interrupt_relevance: how urgent this branch is if confirmed (0-1)
- External knowledge retrieval is permitted only if the diagnostic schema is
  unclear or rare.

Return strict JSON only, no markdown:
{
  "branches": [
    {
      "id": "B1",
      "label": "diagnosis family label",
      "status": "live",
      "prior_estimate": 0.0,
      "danger": 0.0,
      "askable_discriminators": ["question 1"],
      "requestable_discriminators": ["test 1"],
      "turn_cost_to_refine": 1.0,
      "diagnosis_commitment_gain": 0.0,
      "interrupt_relevance": 0.0,
      "why_included": "reason"
    }
  ],
  "frontier": ["B1", "B2"],
  "need_external_knowledge": false,
  "knowledge_query_if_needed": ""
}
```

**提示词与代码的协作方式**：
- LLM 负责：生成竞争分支、应用包含规则、估算各判别器字段；
- 代码负责：构造 `Branch` 对象（`parent="ROOT"`, `level=1`）、外部知识调用、SDBench 的 top-3 截取。

---

## 阶段 D：TemporaryLeafPlanner（临时叶子规划）

### 实现逻辑

```python
def plan_temporary_leaves(self, state):
    # Static QA 模式使用不同模块
    planner_module = ("TemporaryAnalyticLeafPlanner" if self._in_static_qa_mode()
                      else "TemporaryLeafPlanner")
    result = self._call_module(planner_module, state.to_dict())

    leaves = []
    for idx, x in enumerate(result["candidate_leaves_ranked"]):
        leaves.append(CandidateLeaf(
            leaf_id=f"{x['branch_id']}::{x['type']}::{idx}",
            branch_id=x["branch_id"], leaf_type=x["type"], content=x["content"],
            expected_information_gain=x.get("expected_information_gain", 0.0),
            expected_cost=x.get("expected_cost", 0.0),
            expected_delay=x.get("expected_delay", 0.0),
            safety_value=x.get("safety_value", 0.0),
            action_separation_value=x.get("action_separation_value", 0.0),
            total_score=x["score"],
        ))

    selected = result["selected_primary_action"]
    # SDBench 外部格式反映射（ASK/TEST/DIAGNOSE → 内部类型）
    if self._in_sdbench_mode() and selected["type"] in {"ASK", "TEST", "DIAGNOSE"}:
        mapping = {"ASK": "ASK_PATIENT", "TEST": "REQUEST_TEST_OR_MEASUREMENT",
                   "DIAGNOSE": "DIAGNOSIS_READY"}
        selected = {"type": mapping[selected["type"]], "content": selected["content"]}
    return leaves, selected
```

**`estimated_remaining_value` 更新**（`plan_temporary_leaves` 返回后立即调用）：
```python
def update_estimated_remaining_value(self, state):
    if not state.candidate_leaves:
        state.estimated_remaining_value = 0.0
        return
    state.estimated_remaining_value = max(
        (x.total_score for x in state.candidate_leaves), default=0.0
    )
```
取所有候选叶子中评分最高者作为"剩余信息价值"的代理估计，用于诊断就绪度门控（阶段 K）。

**共识动作覆盖**（SDBench 和 Static QA 模式）：
```python
if self._in_sdbench_mode() and state.deliberation.consensus_action:
    selected_action = state.deliberation.consensus_action
if self._in_static_qa_mode() and state.deliberation.consensus_action:
    selected_action = state.deliberation.consensus_action
```
当辩论层产生了共识动作时，叶子规划器的选择被覆盖。

### 所依赖提示词

**文件**：`src/agentclinic_tree_dx/prompts/temporary_leaf_planner.txt`

```
Role: TemporaryLeafPlanner

Generate candidate temporary leaves for the current live frontier and select
exactly one next action.

Candidate action types:
- ASK_PATIENT
- REQUEST_EXAM
- REQUEST_VITAL
- ORDER_LAB
- ORDER_IMAGING
- USE_CALCULATOR
- RETRIEVE_KNOWLEDGE

Instructions:
1. For each live branch, generate candidate discriminators that could separate it
   from competing live branches.
2. Score each candidate using this formula:
     LeafScore(L) = ExpectedInformationGain(L) + SafetyValue(L)
                  + ActionSeparationValue(L) - CostPenalty(L) - DelayPenalty(L)
   - ExpectedInformationGain: how much this action reduces uncertainty (0-1)
   - SafetyValue: bonus for actions that quickly rule out high-danger branches (0-1)
   - ActionSeparationValue: how well this action separates one branch from others
     (0-1)
   - CostPenalty: penalise high-cost, invasive, or risky actions (0-1)
   - DelayPenalty: penalise slow results (0-1)
3. Merge all branch-local candidates into one globally ranked list.
4. Select exactly one primary action: the highest-scoring globally ranked candidate.
5. Do not propose an action with identical content to one already in the
   actions_taken history.

Return strict JSON only, no markdown:
{
  "candidate_leaves_ranked": [
    {
      "branch_id": "B1",
      "type": "ASK_PATIENT",
      "content": "action content string",
      "score": 0.0,
      "expected_information_gain": 0.0,
      "safety_value": 0.0,
      "action_separation_value": 0.0,
      "expected_cost": 0.0,
      "expected_delay": 0.0,
      "why": "one-line rationale"
    }
  ],
  "selected_primary_action": {
    "branch_id": "B1",
    "type": "ASK_PATIENT",
    "content": "action content string"
  }
}
```

**提示词与代码的协作方式**：
- LLM 负责：为每个活跃分支生成候选、按 LeafScore 公式评分、全局排序、选出一个主动作；
- 代码负责：`CandidateLeaf` 对象构造、`estimated_remaining_value` 计算、SDBench 外部格式映射、共识动作覆盖。

---

## 阶段 F：EvidenceAnnotator（证据注释）

### 实现逻辑

```python
def annotate_evidence(self, state, raw_result):
    annotation = self._call_module(
        "EvidenceAnnotator",
        {"state": state.to_dict(), "raw_result": raw_result}
    )
    # ── 确定性后处理：分支 ID 校验 ──
    valid_ids = set(state.branches.keys())
    cleaned_effects = {
        bid: effect
        for bid, effect in annotation.get("branch_effects", {}).items()
        if bid in valid_ids                          # 过滤非法 ID
    }
    for bid in valid_ids:
        cleaned_effects.setdefault(bid, "neutral")  # 补全遗漏分支为 neutral
    annotation["branch_effects"] = cleaned_effects
    return annotation
```

**分支 ID 校验的作用**：防止 LLM 返回不存在的分支 ID（如 "B5" 而当前只有 B1-B3），或遗漏某个分支导致后续更新偏差。校验逻辑完全确定性，不依赖 LLM。

**输入**：`state.to_dict()`（含当前分支状态、动作历史、证据列表） + `raw_result`（外部环境返回的原始结果）。

### 所依赖提示词

**文件**：`src/agentclinic_tree_dx/prompts/evidence_annotator.txt`

```
Role: EvidenceAnnotator

Interpret the newly acquired result and summarise its effect on each branch in
the current differential.

Instructions:
- Summarise the result in plain clinical language.
- For every branch ID present in the current state, classify the effect using
  exactly one of these labels:
    strong_for       (LR+ >= 5, or clinically decisive support)
    moderate_for     (LR+ 2-5, or meaningful support)
    weak_for         (LR+ 1-2, or minor support)
    neutral          (does not materially change probability)
    weak_against     (LR- 0.5-1, or minor reduction)
    moderate_against (LR- 0.2-0.5, or meaningful reduction)
    strong_against   (LR- < 0.2, or clinically decisive exclusion)
- Set major_update: true if this result significantly changes the leading branch
  or the overall differential ordering.
- Set calculator_applicable: true only if a validated clinical scoring rule
  (e.g., Wells DVT/PE, CURB-65, HEART Score, TIMI) directly applies and
  sufficient inputs are available in the current state.
- Set formal_rule_available: true only if the benchmark or environment provides
  a formal interpretation rule that can be applied algorithmically.
- List any branch IDs in reopen_candidates that should be reopened if currently
  closed or parked. Use this when the result directly contradicts the reason
  those branches were closed.
- Set contradiction_detected: true if the result directly and substantially
  contradicts the current leading hypothesis.

Rules you must follow:
- Do NOT choose the update method.
- Do NOT revise branch states directly.
- Only annotate the evidence.
- Only include branch IDs that actually exist in the current state.

Return strict JSON only, no markdown:
{
  "result_summary": "plain language summary",
  "major_update": false,
  "calculator_applicable": false,
  "formal_rule_available": false,
  "branch_effects": {
    "B1": "strong_for"
  },
  "contradiction_detected": false,
  "reopen_candidates": []
}
```

**提示词与代码的协作方式**：
- LLM 负责：基于 LR 范围的效应分类、矛盾检测、计算器适用性判断、重开候选推荐；
- 代码负责：分支 ID 合法性校验（过滤非法 ID + 补全 neutral 默认值）；
- **LLM 被明确禁止**：直接选择更新方法或修改分支状态，这两件事分别在阶段 G、I 中确定性地完成。

---

## 阶段 G：UpdateRouter（更新方法路由）

### 实现逻辑

纯确定性逻辑，无 LLM 调用。

```python
# update_router.py
def choose_update_method(annotation: dict) -> str:
    if annotation.get("calculator_applicable", False):
        return "calculator"
    if annotation.get("formal_rule_available", False):
        return "rule_based"
    return "ordinal"
```

**优先级**：calculator > rule_based > ordinal（默认）。  
路由结果仅由 EvidenceAnnotator 的输出决定，与 LLM 在其他阶段的行为无关。

---

## 阶段 H：概率更新（apply_probability_update）

### 实现逻辑

```python
def apply_probability_update(
    self, state: DiagnosticState, annotation: dict, method: str
) -> None:
    if method == "calculator":
        # 调用 calculator_router（当前为抽象路径），结果存入 annotation 备用
        calculator_result = self.calculator_router(
            annotation.get("result_summary", ""), state
        )
        annotation["_calculator_result"] = calculator_result
        posteriors = calculator_update(state.branches, annotation, calculator_result)
    elif method == "rule_based":
        posteriors = rule_based_update(state.branches, annotation)
    else:
        posteriors = ordinal_update(state.branches, annotation)

    for bid, branch in state.branches.items():
        branch.prior = branch.posterior    # 旧 posterior 成为新 prior
        branch.posterior = posteriors[bid]

    if annotation.get("major_update", False):
        self._handle_major_update(state, annotation)
```

### 三条更新路径

**ordinal 路径**（`updater.py: ordinal_update`，当前唯一产生实质效果的路径）：

```python
ORDINAL_WEIGHTS = {
    "strong_for": 3.0,    "moderate_for": 1.8,  "weak_for": 1.2,
    "neutral": 1.0,
    "weak_against": 0.8,  "moderate_against": 0.5, "strong_against": 0.2,
}

def ordinal_update(branches, annotation, weights=None):
    weights = weights or ORDINAL_WEIGHTS
    raw = {}
    effects = annotation.get("branch_effects", {})
    for bid, branch in branches.items():
        label = effects.get(bid, "neutral")       # 已由代码补全，不会缺失
        weight = weights.get(label, 1.0)
        raw[bid] = max(branch.posterior, 1e-6) * weight   # 防零保护
    return normalize(raw)                         # 归一化

def normalize(raw_scores):
    total = sum(raw_scores.values())
    if total <= 0:
        n = len(raw_scores)
        return {k: 1.0/n for k in raw_scores} if n else {}
    return {k: v/total for k, v in raw_scores.items()}
```

**更新语义**：`new_posterior ∝ old_posterior × weight(effect_label)`，然后归一化。  
即每条新证据通过乘以对应权重后重新归一化，类似于简化的乘性贝叶斯更新。

**calculator 路径**（`updater.py: calculator_update`，抽象路径）：

```python
def calculator_update(branches, annotation, calculator_result=None):
    # 抽象路径：真实实现应从 calculator_result["branch_lr"] 提取 LR+/LR-
    # 并执行: posterior_odds = prior_odds * LR → posterior = odds/(1+odds)
    # 当前 fallback 到 ordinal_update
    return ordinal_update(branches, annotation)
```

**rule_based 路径**（`updater.py: rule_based_update`，抽象路径）：

```python
def rule_based_update(branches, annotation, rule_fn=None):
    # 抽象路径：真实实现由基准环境注入 rule_fn 可调用对象
    if rule_fn is not None:
        return rule_fn(branches, annotation)
    return ordinal_update(branches, annotation)
```

### _handle_major_update（major update 后处理）

```python
def _handle_major_update(self, state: DiagnosticState, annotation: dict) -> None:
    if annotation.get("contradiction_detected", False) and state.root is not None:
        state.root_revision_needed = True   # 下轮循环开始时触发 RootSelector 重新调用
```

当证据产生重大更新（`major_update=True`）且检测到矛盾时，设置根节点修订标志。这实现了规格中"major update → 考虑修订根节点"的要求。

---

## 阶段 I：PostUpdateStateReviser（后更新状态修订）

### 实现逻辑

**第一步：LLM 决策**（`revise_branch_states`）：
```python
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

    max_frontier = self.config.max_live_frontier            # 默认 4
    if self._in_sdbench_mode():
        max_frontier = min(max_frontier, 3)                 # SDBench 强制 ≤ 3
    state.frontier = new_frontier[:max_frontier]            # 截取前沿
```

**第二步：确定性重开覆盖**（`_apply_reopen_overrides`，在 `revise_branch_states` 之后调用）：
```python
def _apply_reopen_overrides(self, state: DiagnosticState, annotation: dict) -> None:
    max_frontier = self.config.max_live_frontier
    if self._in_sdbench_mode():
        max_frontier = min(max_frontier, 3)

    for bid in annotation.get("reopen_candidates", []):     # EvidenceAnnotator 的输出
        if bid not in state.branches:
            continue
        branch = state.branches[bid]
        if branch.status in {"closed_for_now", "parked"}:   # 仅覆盖关闭/停泊状态
            branch.status = "reopened"
            if bid not in state.frontier and len(state.frontier) < max_frontier:
                state.frontier.append(bid)
```

**两步设计的关键意图**：
- LLM（PostUpdateStateReviser）负责常规转移（expand/park/close/confirm）；
- 代码（`_apply_reopen_overrides`）负责**确定性覆盖**——当 EvidenceAnnotator 明确标记某分支应重开时，LLM 的关闭/停泊决策被强制撤销。
- 这保证了"证据驱动的重开"不依赖 LLM 在同一轮内的一致性。

### 所依赖提示词

**文件**：`src/agentclinic_tree_dx/prompts/post_update_state_reviser.txt`

```
Role: PostUpdateStateReviser

After probabilities have been updated, revise branch states for the next cycle.

Allowed decisions per branch:
- expand_now:    posterior above test_threshold, child branches imply different
                 actions, useful discriminator still exists
- keep_coarse:   live but no need to subdivide yet; refinement benefit is low
- park:          not currently dominant, still plausible enough to retain, low
                 immediate refinement value
- close_for_now: posterior below test_threshold AND no unresolved critical
                 evidence AND further pursuit would not change current management
- confirm:       posterior >= commit_threshold AND finer distinctions would not
                 change the current management decision
- reopen:        previously closed or parked; new evidence or contradiction
                 warrants revisiting

Thresholds to use:
- commit_threshold: 0.75  (use confirm if posterior >= 0.75)
- test_threshold:   0.05  (eligible for close_for_now if posterior < 0.05)

Safety override: never close_for_now a branch with danger >= 0.7 unless
posterior < 0.01.

ExpandScore heuristic (use to choose between expand_now and keep_coarse):
  ExpandScore(B) = RemainingUncertainty(B) x ExpectedActionDifference(B)
                 x SafetyWeight(B) - CostOfExpansion(B)
  Prefer expand_now when ExpandScore > 0.

Instructions:
- Produce exactly one decision for every branch ID currently in the state.
- This is the ONLY stage where structural branch-state transitions occur in a cycle.
- Use current posterior, danger, unresolved_questions, and evidence_for/against
  to justify each decision.

Return strict JSON only, no markdown:
{
  "branch_decisions": [
    {
      "branch_id": "B1",
      "decision": "expand_now",
      "rationale": "one-line justification"
    }
  ]
}
```

**提示词与代码的协作方式**：
- LLM 负责：对每个分支应用转移规则，输出含决策和理由的列表；
- 代码负责：状态转换执行、前沿列表重建（含前沿宽度限制）、事后确定性重开覆盖。

---

## 阶段 K：DiagnosisReadinessGate（诊断就绪度门控）

> 仅在 `agentclinic_physician_patch`、`sdbench_patch`、`static_diagnosis_qa` 三种模式下激活，`default` 模式跳过此阶段直接走 TerminationJudge。

### 实现逻辑

```python
def check_diagnosis_readiness(self, state: DiagnosticState) -> bool:
    if not state.branches:
        state.diagnosis_readiness_score = 0.0
        return False

    ranked = sorted(state.branches.values(), key=lambda b: b.posterior, reverse=True)
    leader = ranked[0]
    state.diagnosis_readiness_score = leader.posterior   # 写入状态供后续模块参考

    # 基础阈值检查（所有三种模式）
    if leader.posterior < self.config.min_readiness_to_commit:  # 默认 0.75
        return False

    # AgentClinic patch 模式的额外三重门控
    if self._in_patch_mode():
        dangerous_alternative_exists = any(
            b.id != leader.id and b.danger >= 0.7 and b.posterior >= 0.15
            for b in ranked
        )
        cheap_high_yield_exists = any(
            leaf.total_score >= 0.8 and leaf.expected_cost <= 0.2
            for leaf in state.candidate_leaves
        )
        repeated_last_action = (
            len(state.actions_taken) >= 2 and
            state.actions_taken[-1]["content"] == state.actions_taken[-2]["content"]
        )
        if dangerous_alternative_exists or cheap_high_yield_exists or repeated_last_action:
            return False

    return True
```

**就绪度判断逻辑**（AgentClinic Patch 模式，最严格）：

| 条件 | 含义 | 阻止提交 |
|------|------|---------|
| `leader.posterior < 0.75` | 领先分支还不够确定 | 是 |
| 危险备选存在（`danger≥0.7, posterior≥0.15`） | 仍有高危诊断未排除 | 是 |
| 廉价高价值动作存在（`score≥0.8, cost≤0.2`） | 还有低成本高收益的判别动作 | 是 |
| 最后两次动作内容相同 | 陷入重复循环 | 是 |

**SDBench 和 Static QA 模式**：只检查基础阈值 `leader.posterior >= min_readiness_to_commit`。

**无提示词**：此阶段为纯确定性算法逻辑。

---

## 阶段 L：TerminationJudge（终止判断）

### 实现逻辑

```python
def check_termination(self, state):
    result = self._call_module("TerminationJudge", state.to_dict())
    return TerminationState(
        ready_to_stop=result["ready_to_stop"],
        termination_type=result.get("termination_type", "continue"),
        reason=result["reason"],
    )
```

控制器仅在**就绪度门控未通过**时才调用此模块。

**轮次预算强制终止**（独立于 TerminationJudge）：
```python
if (self._in_patch_mode() or self._in_sdbench_mode() or self._in_static_qa_mode()) \
   and state.max_turn_budget and state.turn_budget_used >= state.max_turn_budget:
    state.termination = TerminationState(True, "info_exhaustion", "turn budget reached")
    return self.final_aggregate(state)
```
轮次耗尽时直接终止，不调用 TerminationJudge（避免在预算已耗尽时 LLM 仍建议继续）。

### 所依赖提示词

**文件**：`src/agentclinic_tree_dx/prompts/termination_judge.txt`

```
Role: TerminationJudge

Decide whether tree expansion should stop now.

Five termination types and their trigger conditions:
1. confirmation:         one branch has posterior >= 0.75 AND no dangerous
                         alternative (danger >= 0.7, posterior >= 0.10) remains
                         unresolved
2. actionable_parent:    multiple child branches remain unresolved but they ALL
                         share a single immediate management path; finer diagnosis
                         would not change the next action
3. info_exhaustion:      no further available discriminator is expected to change
                         management; all high-value actions have already been
                         taken or are unavailable
4. working_differential: residual uncertainty is irreducible with available tools;
                         explicit uncertainty management is the correct clinical
                         endpoint
5. emergency_override:   an urgent interrupt is active and further expansion
                         would delay required intervention

If none of these five conditions apply, return ready_to_stop: false with
termination_type: continue.

Return strict JSON only, no markdown:
{
  "ready_to_stop": false,
  "termination_type": "continue",
  "reason": "brief rationale",
  "if_continue_next_best_action_type": "ASK_PATIENT"
}
```

**提示词与代码的协作方式**：
- LLM 负责：对照5种类型的触发条件判断是否停止；
- 代码负责：构造 `TerminationState`、触发 `final_aggregate()`、独立处理轮次预算耗尽。

---

## 阶段 M：FinalAggregator（最终聚合）

### 实现逻辑

```python
def final_aggregate(self, state):
    # Static QA 模式：调用 AnswerMapper，映射为单一选项
    if self._in_static_qa_mode():
        mapped = self._call_module("AnswerMapper", {"state": state.to_dict(),
                                                     "options": state.static_options})
        return {"final_answer": mapped.get("final_answer", ""),
                "answer_option_mapping": ..., "internal_reasoning_state": ...}

    # SDBench 模式：调用 FinalDiagnosisEmitter，输出单一诊断字符串并提交
    if self._in_sdbench_mode():
        emitter = self._call_module("FinalDiagnosisEmitter", {...})
        diagnosis = emitter.get("final_diagnosis", "undetermined")
        submitted = self.env.submit_diagnosis(diagnosis)   # 提交给 Gatekeeper
        return {"diagnosis": diagnosis, "submission": submitted,
                "internal_reasoning_state": ...}

    # default / agentclinic_physician_patch 模式：调用 FinalAggregator
    final_output = self._call_module("FinalAggregator", state.to_dict())
    if hasattr(self.env, "review_with_moderator"):
        final_output["moderator_review"] = self.env.review_with_moderator(final_output, state)

    # AgentClinic patch 模式：包装为基准面向格式
    if self._in_patch_mode():
        diagnosis = final_output.get("leading_diagnosis_or_parent", "undetermined")
        return {"internal_reasoning_state": final_output,
                "benchmark_output": f"Diagnosis Ready: {diagnosis}"}
    return final_output
```

### 所依赖提示词（default / patch 模式）

**文件**：`src/agentclinic_tree_dx/prompts/final_aggregator.txt`

```
Role: FinalAggregator

Produce the final diagnostic output.

Select the appropriate output mode using these rules:
- single_leading_diagnosis:    one branch clearly dominates (posterior >= 0.75)
                               and is confirmed; certainty is sufficient for
                               direct clinical action
- actionable_parent_syndrome:  multiple child branches remain unresolved but
                               the parent syndrome determines the immediate
                               treatment; finer distinction is not yet needed
- coexisting_diagnoses:        more than one active branch is independently
                               clinically meaningful and compatible with the
                               evidence
- ranked_working_differential: residual uncertainty remains; false certainty
                               would be unsafe; output a ranked differential
                               plus next-step plan

Rules:
- Prefer single_leading_diagnosis only when the leading branch is clearly
  dominant and no dangerous alternative remains.
- Use actionable_parent_syndrome when child branches share the same immediate
  management pathway.
- Always include safety_net_or_reopen_triggers for parked or closed branches
  that could re-emerge with new evidence.
- recommended_next_tests_if_any should list any tests still warranted for
  prognostic or safety-netting purposes even after stopping.

Return strict JSON only, no markdown:
{
  "final_mode": "single_leading_diagnosis",
  "leading_diagnosis_or_parent": "diagnosis or parent syndrome label",
  "ranked_differential": ["diagnosis 1", "diagnosis 2"],
  "coexisting_processes": [],
  "supporting_evidence": ["key supporting finding"],
  "conflicting_evidence": [],
  "immediate_actions": ["action 1"],
  "recommended_next_tests_if_any": [],
  "safety_net_or_reopen_triggers": ["trigger condition"],
  "confidence": 0.0
}
```

**提示词与代码的协作方式**：
- LLM 负责：依据4种模式的选择规则输出结构化诊断结论；
- 代码负责：模式路由（default/patch/SDBench/Static QA）、moderator review 附加、patch 模式输出格式包装。

---

## 模块间数据流

```
state.to_dict()
    │
    ▼ (SafetyController)
InterruptState ──→ execute_emergent_actions [如激活]
    │
    ▼ (RootSelector) [首次 or root_revision_needed]
RootNode ──→ state.root
    │
    ▼ (BranchCreator) [首次 or root_needs_revision]
{Branch...} + frontier ──→ state.branches, state.frontier
    │
    ▼ (TemporaryLeafPlanner)
[CandidateLeaf...] + selected_action ──→ state.candidate_leaves
                                      + estimated_remaining_value
    │
    ▼ execute_primary_action → raw_result
    │
    ▼ (EvidenceAnnotator) + 分支ID校验
annotation {branch_effects, major_update, calculator_applicable,
            formal_rule_available, contradiction_detected, reopen_candidates}
    │
    ├── choose_update_method → method: "ordinal" | "calculator" | "rule_based"
    │
    ▼ apply_probability_update
branch.prior ← branch.posterior
branch.posterior ← normalize(prior × weight)
    │
    ├── [major_update=True] _handle_major_update
    │       └── [contradiction_detected=True] state.root_revision_needed = True
    │
    ▼ (PostUpdateStateReviser)
branch.status ← {confirm/close_for_now/park/expand_now/keep_coarse/reopen}
state.frontier ← [active branch ids]
    │
    ▼ _apply_reopen_overrides [确定性覆盖]
reopen_candidates 中 closed/parked 分支 → branch.status = "reopened"
    │
    ▼ record_differential_history
state.differential_history ← [{bid: posterior}]
    │
    ├── [Patch/SDBench/Static QA] check_diagnosis_readiness → [如通过] final_aggregate
    ▼
(TerminationJudge)
TerminationState {ready_to_stop, termination_type, reason}
    │
    └── [ready_to_stop=True] final_aggregate → 返回最终结果
```

---

## 各模块实现完整度一览

| 模块 | 提示词完整度 | 代码逻辑完整度 | 主要局限 |
|------|------------|--------------|---------|
| SafetyController | 含5条具体临床规则 | 中断触发和流程控制已完整 | `take_emergent_action` 依赖适配器实现 |
| RootSelector | 含3维算法和2条排除规则 | 修订触发（contradiction→flag）已完整 | 外部知识路径为占位；多轮修订测试未覆盖 |
| BranchCreator | 含包含规则和判别器字段规范 | 分支对象构造完整；SDBench top-3 截取已实现 | 仅单层树；`actionability`/`explanatory_coverage` 未填充 |
| TemporaryLeafPlanner | 含完整 LeafScore 公式 | 叶子对象构造和剩余价值估算完整 | 评分计算完全依赖 LLM，无代码层面的公式验证 |
| EvidenceAnnotator | 含7级效应标签和 LR 范围 | 分支ID校验和 neutral 补全已完整 | AgentClinic patch 额外字段（就绪度变化）未在提示词中要求 |
| UpdateRouter | 无提示词（纯确定性） | 三路路由逻辑正确 | — |
| ordinal_update | 无提示词（纯算法） | 乘性更新+归一化完整 | 简化的贝叶斯近似，非严格统计正确 |
| calculator_update | 无提示词（抽象路径） | 接口已定义；fallback 到 ordinal | 未实现真实 LR 贝叶斯更新 |
| rule_based_update | 无提示词（抽象路径） | 接口已定义；支持 rule_fn 注入 | 未提供任何内置规则 |
| _handle_major_update | 无提示词（纯算法） | 矛盾→root_revision 标志 | 未实现兄弟节点重评估 |
| PostUpdateStateReviser | 含阈值、安全覆盖、ExpandScore | 6种转移执行完整；前沿截取完整 | 阈值未从 config 动态传入提示词 |
| _apply_reopen_overrides | 无提示词（纯算法） | 确定性覆盖完整；frontier 容量检查 | — |
| DiagnosisReadinessGate | 无提示词（纯算法） | Patch 模式三重门控完整 | SDBench/Static QA 只检查基础阈值 |
| TerminationJudge | 含5种类型的触发条件 | 结构完整；与就绪度门控衔接正确 | 轮次预算终止独立于此模块（正确设计） |
| FinalAggregator | 含4种输出模式选择规则 | 4路分发完整；moderator review 附加 | 诊断字符串格式规范依赖 LLM |

---

*文档生成时间：2026-04-30*  
*基于代码分支：`codex/verify-agentclinic-compatibility-with-projects`*
