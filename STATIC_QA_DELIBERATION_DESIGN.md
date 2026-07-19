# Static QA 模式审议算法设计

> **文档类型**：算法设计规格（Algorithm Design Specification）  
> **版本**：v1.0  
> **适用范围**：`static_diagnosis_qa` 执行模式  
> **替换对象**：当前 `run_static_qa_deliberation()` 中的六模块审议循环

---

## 一、临床认知科学基础

### 1.1 双过程理论与诊断错误

诊断推理的双过程理论（Dual Process Theory）区分了两种认知模式：

- **System 1（直觉式）**：快速、自动、基于模式识别的推理
- **System 2（分析式）**：慢速、有意识、基于形式知识的推理

> *"Instructions encouraging clinicians to explicitly use both System 1 and System 2 strategies together can lead to consistent error rate reductions."*  
> — Croskerry (2009), Dual Processing and Diagnostic Errors, *Advances in Health Sciences Education*

关键发现是：两种系统**均可能出错**，错误的根源不在于系统类型本身，而在于**知识可及性不足**和**未经验证的初始假设被过早固化**。

> *"Errors derive from lack of access to appropriate knowledge rather than processing failures, and both System 1 and System 2 reasoning are equally prone to error."*  
> — Monteiro et al. (2024), Dual Process Models of Clinical Reasoning, *PubMed*

### 1.2 过早闭合（Premature Closure）

过早闭合是诊断错误中最常见的认知偏差，占误诊原因的三分之二以上：

> *"Premature closure is a cognitive error where clinicians fail to consider reasonable alternative diagnoses after forming an initial impression."*  
> — Graber et al. (2005), *Annals of Internal Medicine*; Schiff et al. (2009), *Archives of Internal Medicine*

预防过早闭合的核心策略是**强制考虑替代方案**（consider alternatives）：

> *"A powerful debiasing technique is continuously asking 'What else?' to maintain a broad differential diagnosis."*  
> — MDedge (2024), Diagnostic Challenges in Primary Care

### 1.3 有效性最高的干预：引导式反思

系统综述表明，在所有去偏差干预策略中，**引导式反思（guided reflection / deliberate reflection）** 的证据最为一致：

> *"Guided reflection emerged as the most consistently successful approach across multiple studies."*  
> — Lambe et al. (2016), Dual-process Cognitive Interventions to Enhance Diagnostic Reasoning, *BMJ Quality & Safety*

> *"Experimental evidence has supported the effectiveness of deliberate reflection in increasing physicians' diagnostic performance, particularly in nonstraightforward (complex) diagnostic tasks."*  
> — Mamede & Schmidt (2022), Deliberate Reflection and Clinical Reasoning, *PubMed*

引导式反思的核心机制是**激活并重组先验知识**——让推理者回头审视已有证据，检查是否存在被忽略的信号或与当前假设矛盾的线索。

### 1.4 诊断暂停（Diagnostic Timeout）

临床实践中已有结构化工具将上述原则制度化：

> **Diagnostic Timeout**：当诊断不确定性升高时，任何团队成员均可发起的结构化暂停。典型流程包含：  
> (1) 触发条件识别（症状不典型 / 客观数据不符 / 直觉警觉）  
> (2) 证据重新审查（支持/反对当前诊断的证据）  
> (3) 不可遗漏诊断列举（can't-miss diagnoses）  
> (4) 其他器官系统可能性评估  
> (5) 下一步行动计划  
> — Children's Hospital Colorado (2023), Diagnostic Time Out Algorithm; Rao & Ferris (2022), *Diagnosis*

### 1.5 SNAPPS 框架中的对比分析

SNAPPS（Summarize, Narrow, Analyze, Probe, Plan, Select）是临床推理教学中经循证验证的框架，其 Step 3 "Analyze" 明确要求：

> *"Learners discuss why the patient presentation supports or refutes EACH differential diagnosis."*  
> — Wolpaw et al. (2003), *Academic Medicine*

该步骤的关键是**逐个假设做证据正反对比**，而非仅论证领先假设。

### 1.6 多智能体 LLM 系统的实证

2024–2025 年多项研究证实，结构化多智能体辩论可显著提升 LLM 诊断准确率：

| 系统 | 方法 | 改进幅度 |
|------|------|---------|
| MAC（npj Digital Medicine, 2025） | 4 个医生智能体 + 1 个督导智能体 | 罕见病诊断准确率显著优于单模型 |
| Tree-of-Reasoning（arXiv, 2025） | 树结构推理路径 + 跨智能体交叉验证 | 复杂诊断一致性提升 |
| EVINCE（arXiv, 2024） | 探索-利用配对辩论 + 熵变化理论 | 诊断可靠性和鲁棒性改善 |
| MEDDxAgent（ACL, 2025） | 模块化框架 + 迭代患者档案精化 | 大小模型均 >10% 准确率提升 |

共同发现：有效的多智能体系统**不是简单投票**，而是通过**结构化角色分工和交叉验证**来减少单一推理路径的盲点。

---

## 二、对当前架构的诊断

### 2.1 当前架构的根本问题

当前审议循环存在三个与上述临床证据直接矛盾的结构性缺陷：

| 缺陷 | 违反的临床原则 |
|------|-------------|
| 6 模块中 5 个仅 3 行提示词，输出格式不可控 | 引导式反思要求**结构化**的反思框架，不可自由发挥 |
| Consensus 仅接收 Checklist 输出，忽略其他 4 个模块 | 等同于诊断暂停中仅做合规检查，跳过"证据重审"和"替代方案考虑" |
| 审议结果不影响行动选择（bundle 由 TALP 独立构建） | 反思若不改变后续行为则无临床价值——相当于"走过场" |

### 2.2 过度设计的领域

| 组件 | 过度原因 |
|------|---------|
| EvidenceAllocator | 静态模式下证据已完全可观测，选取顺序可由确定性优先级决定 |
| ReasoningEconomyAuditor | 其去冗余功能已被 `FrontierCoverageBundler._is_redundant` 确定性实现 |
| Checklist | 其合规检查已被 `FrontierCoverageBundler._passes_gates` 确定性实现 |
| Consensus 作为行动选择器 | 行动选择已由 TALP + FrontierCoverageBundler 处理 |

---

## 三、新审议算法设计

### 3.1 设计原则

基于上述文献综述，新审议算法遵循以下原则：

| # | 原则 | 来源 |
|---|------|------|
| P1 | 审议必须产生**结构化**输出，不允许自由格式 | Lambe et al. (2016): guided reflection 必须有明确框架 |
| P2 | 审议必须对**每个存活分支**做正反证据对比 | SNAPPS Step 3: analyze each differential |
| P3 | 审议必须强制产出**至少一个反驳动作建议** | Cognitive forcing: "What else could this be?" |
| P4 | 审议输出必须**注入**后续动作规划（TALP） | 反思不改变行为则无价值 |
| P5 | 审议应在**证据处理后**而非行动选择前执行 | Diagnostic timeout 在累积不确定性后触发 |
| P6 | 审议不参与概率计算或分支状态变更 | 数值更新是确定性算法的职责 |

### 3.2 模块精简

删除 6 个旧模块（Hypothesis, EvidenceAllocator, Challenger, ReasoningEconomyAuditor, Checklist, Consensus），替换为 **2 个结构化模块**：

```
旧审议循环 (6 个 LLM 调用):
  Hypothesis → EvidenceAllocator → Challenger →
  ReasoningEconomyAuditor → Checklist → Consensus

新审议循环 (2 个 LLM 调用):
  EvidenceSynthesizer → DiagnosticChallenger
```

### 3.3 新模块 1：EvidenceSynthesizer（证据综合器）

#### 临床对应

对应于 **SNAPPS Step 3 "Analyze"** 和**诊断暂停中的证据重新审查**。其核心功能是：给定当前所有已处理证据和分支状态，对每个存活分支做**正反证据清点**，并产出一个全局态势评估。

#### 触发时机

**不在每轮开始时触发**（旧设计的错误之处）。改为在以下条件之一满足时触发：

```
触发条件（任一满足即触发）:
  (a) state.timestep == 1（首轮结束后的初始综合）
  (b) annotation.major_update == true（证据重大变更后）
  (c) annotation.contradiction_detected == true（矛盾检测后）
  (d) 领先分支发生变更（上一轮的 leader != 本轮的 leader）
  (e) state.timestep == max_turn_budget - 1（倒数第二轮强制反思）
```

**依据**：诊断暂停不是每分钟执行一次的例行程序，而是在不确定性升高时触发。条件 (a)-(e) 对应于临床暂停的五类触发信号。

#### 输入

```json
{
  "branches": "state.to_payload() 中的分支状态（含 posterior、evidence_for/against）",
  "frontier": "当前活跃分支列表",
  "actions_taken": "最近 N 条动作记录（裁剪版）",
  "static_evidence_items": "完整的直接证据条目列表",
  "seen_evidence_ids": "已分析的证据条目 ID 集合"
}
```

#### 提示词设计

```
Role: EvidenceSynthesizer

You are performing a structured diagnostic reflection (diagnostic timeout)
on the current differential diagnosis. Your task is NOT to choose actions
or update probabilities. Your task is to ANALYZE the current evidence
pattern across all branches.

For EACH branch in the frontier, you must:
1. List the evidence items that SUPPORT this branch, with brief reasoning
2. List the evidence items that ARGUE AGAINST this branch, with brief reasoning
3. Identify the single MOST IMPORTANT unresolved question for this branch
4. Assess whether this branch has been UNDER-EXAMINED relative to others
   (coverage debt)

Then provide a global assessment:
5. Which branch currently has the WEAKEST evidentiary basis for its
   posterior probability? (This branch may be over- or under-estimated.)
6. Are there any UNEXPLAINED evidence items — findings in the vignette
   that are not adequately accounted for by ANY current branch?
7. Is the current leading branch's advantage based on STRONG discriminating
   evidence, or merely on the absence of contradicting evidence?
   (The distinction matters: absence of contradiction ≠ confirmation.)

CRITICAL RULE — evidence asymmetry detection:
If the leading branch has received substantially more analytical attention
(more actions_taken entries targeting it) than competing branches, flag
this as a potential confirmation bias risk.

Return strict JSON only, no markdown:
{
  "branch_assessments": [
    {
      "branch_id": "B1",
      "supporting_evidence": ["E16: 35% blasts consistent with acute leukemia"],
      "opposing_evidence": ["subacute onset atypical for de novo AML"],
      "key_unresolved": "BCR-ABL status to distinguish AML from CML blast crisis",
      "coverage_debt": false,
      "examination_count": 3
    }
  ],
  "global_assessment": {
    "weakest_evidential_basis": "B3",
    "unexplained_findings": ["mildly ataxic gait not fully explained by any branch"],
    "leading_branch_strength": "moderate — based on blast count but lacks
      cytogenetic confirmation",
    "confirmation_bias_risk": "low|moderate|high",
    "confidence_in_current_differential": 0.0
  }
}
```

#### 输出消费方式

EvidenceSynthesizer 的输出**直接注入 TALP 的上下文**：

```python
talp_payload = state.to_payload()
if synthesis is not None:
    talp_payload["deliberation_context"] = {
        "evidence_synthesis": synthesis,
        "challenger_flags": challenger_output,  # 见下
    }
```

TALP 提示词中增加对应指令：

```
If deliberation_context is provided:
- Prioritize generating candidates for branches flagged with coverage_debt=true
- For branches where confirmation_bias_risk is "high", ensure at least one
  candidate has primary_function="falsify"
- Address unexplained_findings by generating at least one candidate that
  explicitly tests whether those findings fit any current branch
```

### 3.4 新模块 2：DiagnosticChallenger（诊断质疑器）

#### 临床对应

对应于**认知强迫策略（Cognitive Forcing Strategy）** 中的"What else could this be?"以及**诊断暂停中的 can't-miss 检查**。

#### 触发时机

与 EvidenceSynthesizer **同步触发**（当 EvidenceSynthesizer 被调用时，DiagnosticChallenger 随后执行），接收 EvidenceSynthesizer 的输出作为上下文。

#### 输入

```json
{
  "state": "state.to_payload()",
  "evidence_synthesis": "EvidenceSynthesizer 的完整输出",
  "leading_branch": "当前后验最高的非 expanded 分支",
  "closed_branches": "status 为 closed_for_now 或 parked 的分支摘要"
}
```

#### 提示词设计

```
Role: DiagnosticChallenger

You are a diagnostic safety officer performing a cognitive forcing check.
Your sole purpose is to prevent premature closure by challenging the
current leading diagnosis.

You receive the EvidenceSynthesizer's analysis as context. Based on it:

1. LEADING BRANCH CHALLENGE:
   Construct the strongest possible argument AGAINST the current leading
   branch. Use specific evidence items. If the leading branch's advantage
   rests on "absence of contradiction" rather than "presence of strong
   discriminating evidence," say so explicitly.

2. OVERLOOKED ALTERNATIVE CHECK:
   Review all closed/parked branches. For each, state whether the closure
   reason still holds given ALL current evidence. If any closed branch
   should be reconsidered, list it with the specific evidence that
   warrants reopening.

3. CAN'T-MISS DIAGNOSIS CHECK:
   Are there any high-danger (danger ≥ 0.7) branches that have received
   insufficient analytical attention? If yes, this is a safety gap.

4. FALSIFICATION PRESCRIPTION:
   Propose exactly ONE specific analytical action that, if its result
   contradicts the leading branch, would most decisively shift the
   differential. This action should target the weakest point of the
   leading branch's evidence base.

5. ANCHORING RISK ASSESSMENT:
   Based on the evidence_synthesis's examination_count per branch, assess
   whether the reasoning process has been disproportionately focused on
   confirming the leading hypothesis.

Return strict JSON only, no markdown:
{
  "leading_branch_challenge": {
    "branch_id": "B1",
    "strongest_counterargument": "string",
    "evidence_basis": "strong_discriminating|absence_of_contradiction|mixed"
  },
  "reopen_recommendations": [
    {
      "branch_id": "B3",
      "reason": "string",
      "triggering_evidence": ["E-id"]
    }
  ],
  "safety_gaps": [
    {
      "branch_id": "B3",
      "danger": 0.9,
      "examination_deficit": "only 1 action targeted this branch vs 4 for leader"
    }
  ],
  "falsification_action": {
    "target_branch": "B1",
    "action_type": "ANALYZE_VIGNETTE",
    "content": "string",
    "expected_impact": "string"
  },
  "anchoring_risk": "low|moderate|high"
}
```

#### 输出消费方式

DiagnosticChallenger 的输出影响三个下游环节：

**1. 注入 TALP 上下文（同 EvidenceSynthesizer）**

TALP 在看到 `challenger_flags.falsification_action` 时，应确保候选列表中包含该动作或等效动作。

**2. 触发分支重开（确定性逻辑）**

```python
for rec in challenger_output.get("reopen_recommendations", []):
    bid = rec["branch_id"]
    if bid in state.branches and state.branches[bid].status in ("closed_for_now", "parked"):
        state.branches[bid].status = "reopened"
        if bid not in state.frontier:
            state.frontier.append(bid)
```

**3. 增强 FrontierCoverageBundler 的 Phase 1.5**

当 `anchoring_risk == "high"` 时，FrontierCoverageBundler 的 falsification guarantee 从"仅当 leader P ≥ 0.5 时触发"降低为"leader P ≥ 0.3 时触发"：

```python
falsify_threshold = 0.3 if anchoring_risk == "high" else 0.5
```

---

## 四、修订后的主循环结构

```
[Turn N]

A.  SafetyController
B.  RootSelector（条件触发）
C.  BranchCreator（条件触发）

    ┌─────────────────────────────────────────────────────┐
    │ 审议层（条件触发，非每轮执行）                         │
    │                                                       │
    │ 触发条件:                                             │
    │   timestep==1 OR major_update OR contradiction         │
    │   OR leader_changed OR final_turn_approaching          │
    │                                                       │
    │ EvidenceSynthesizer ← state + evidence_items          │
    │      ↓                                                 │
    │ DiagnosticChallenger ← state + evidence_synthesis      │
    │      ↓                                                 │
    │ 确定性分支重开（若有 reopen_recommendations）          │
    └─────────────────────────────────────────────────────┘
         ↓ deliberation_context 注入
D.  TALP ← state + deliberation_context（若存在）
D'. FrontierCoverageBundler ← candidate_leaves + anchoring_risk
E'. execute_action_bundle
F'. EvidenceAnnotator → annotation
G.  概率更新
H.  recompute_parent_posteriors
I.  PostUpdateStateReviser
J.  ExpansionGate + SubBranchCreator（条件触发）
K.  终止判断

    ┌─────────────────────────────────────────────────────┐
    │ 最终验证（仅在终止确定后执行）                        │
    │                                                       │
    │ 强制触发 EvidenceSynthesizer + DiagnosticChallenger    │
    │ 若 anchoring_risk == "high":                          │
    │   终止被否决，强制增加 1 轮反驳动作                   │
    └─────────────────────────────────────────────────────┘

L.  AnswerMapper → FinalAggregator
```

### 4.1 与旧循环的 LLM 调用数比较

| 场景 | 旧循环（每轮 6 次） | 新循环 |
|------|-------------------|--------|
| 普通轮（无触发） | 6 次 | 0 次 |
| 触发轮 | 6 次 | 2 次 |
| 5 轮运行（2 次触发） | 30 次 | 4 次 |
| **节省** | — | **87%** |

---

## 五、证据调度机制（替代 EvidenceAllocator）

### 5.1 确定性优先级队列

静态模式下，证据选取顺序由**确定性优先级函数**决定，不消耗 LLM 调用：

```python
def compute_evidence_priority(
    item: EvidenceItem,
    state: DiagnosticState,
) -> float:
    score = 0.0
    content = item.content.lower()

    # ── 临床显著性（异常值 > 正常值）──
    ABNORMAL_MARKERS = ["elevated", "decreased", "abnormal", "positive",
                        "blasts", "mass", "opacity", "enlargement"]
    NORMAL_MARKERS = ["normal", "unremarkable", "within normal", "negative"]

    if any(m in content for m in ABNORMAL_MARKERS):
        score += 3.0
    if any(m in content for m in NORMAL_MARKERS):
        score -= 1.0

    # ── 证据类型权重（客观 > 主观）──
    if any(k in content for k in ["count", "mg/dl", "meq/l", "mm^3", "g/dl", "%"]):
        score += 2.0  # 实验室定量数据
    elif any(k in content for k in ["exam", "physical", "gait", "acuity"]):
        score += 1.5  # 体格检查
    elif any(k in content for k in ["history", "presents", "complaint"]):
        score += 1.0  # 病史

    # ── 跨分支区分度（能影响多个 live 分支的证据优先）──
    for branch in state.branches.values():
        if branch.status not in ("live", "reopened"):
            continue
        for disc in branch.askable_discriminators + branch.requestable_discriminators:
            if _token_overlap(item.content, disc) > 0.3:
                score += 0.5

    return score
```

### 5.2 调度流程

```python
def schedule_evidence(state: DiagnosticState) -> list[str]:
    """返回尚未分析的证据 ID，按优先级降序排列。"""
    unseen = [
        item for item in state.static_evidence_items
        if item.id not in state.seen_evidence_ids
    ]
    ranked = sorted(unseen, key=lambda e: compute_evidence_priority(e, state), reverse=True)
    return [e.id for e in ranked]
```

TALP 在生成候选时参考 `scheduled_evidence_ids` 列表，优先为排在前面的证据条目生成分析动作。

---

## 六、终止前最终验证机制

### 6.1 临床依据

> *"Task-oriented checklists demonstrate greater error reduction than cognitive-process approaches."*  
> — Sibbald et al. (2022), Checklists to Reduce Diagnostic Error, *BMJ Open*

终止前强制执行一次审议（EvidenceSynthesizer + DiagnosticChallenger），等同于手术前的 "sign-out" 检查——在不可逆的决策点之前做最后审视。

### 6.2 机制

```python
def final_verification(self, state, synthesis, challenger_output):
    """终止确定后，强制执行最终验证。若发现高锚定风险，否决终止。"""

    if challenger_output.get("anchoring_risk") == "high":
        # 否决终止：强制增加 1 轮，执行 falsification_action
        state.termination = TerminationState(False, "continue",
            "Final verification detected high anchoring risk; "
            "forcing one falsification round before commitment.")
        forced_action = challenger_output["falsification_action"]
        return forced_action  # 由 controller 直接执行此动作

    # 检查 safety_gaps
    if challenger_output.get("safety_gaps"):
        for gap in challenger_output["safety_gaps"]:
            if gap.get("danger", 0) >= 0.8:
                state.termination = TerminationState(False, "continue",
                    f"Safety gap: high-danger branch {gap['branch_id']} "
                    f"under-examined. Forcing additional analysis.")
                return None  # 正常 TALP 流程，但 frontier 中该分支优先

    return None  # 终止被确认，进入 AnswerMapper
```

### 6.3 防止无限循环

最终验证**最多触发一次**。如果强制增加的反驳轮结束后仍然 `anchoring_risk == "high"`，第二次不再否决终止，直接输出答案（附带 `low_confidence` 标记）。

```python
if state._final_verification_count >= 1:
    # 已执行过一次最终验证，不再否决
    pass
else:
    state._final_verification_count = getattr(state, '_final_verification_count', 0) + 1
    # 执行验证逻辑
```

---

## 七、设计如何降低已知偏差

### 7.1 偏差-对策映射表

| 认知偏差 | 定义 | 新审议中的对策 | 对策的文献依据 |
|---------|------|-------------|-------------|
| **确认偏差** | 倾向于寻找支持初始假设的证据 | EvidenceSynthesizer 检测 `examination_count` 不均衡 → 触发 `confirmation_bias_risk` 标记 → TALP 为欠覆盖分支优先生成动作 | Mendel et al. (2011), *Psychological Medicine* |
| **过早闭合** | 在充分排除替代方案前固化诊断 | DiagnosticChallenger 强制产出 `falsification_action` + 终止前 `final_verification` 可否决提前终止 | Graber et al. (2005); Cognitive Forcing Strategies, Croskerry (2003) |
| **锚定偏差** | 过度依赖初始信息 | EvidenceSynthesizer 评估 `leading_branch_strength`（区分"强鉴别证据"vs"无矛盾即领先"）→ 弱基础时降低终止阈值 | Kahneman (1974); Diagnostic Timeout 框架 |
| **搜索满足** | 找到一个解释后停止搜索 | EvidenceSynthesizer 检测 `unexplained_findings`（未被任何分支解释的证据）→ TALP 为这些发现生成候选 | SNAPPS Step 3 逐假设分析 |
| **可得性偏差** | 更容易想起常见诊断 | DiagnosticChallenger 显式审查 `closed_branches`，检查低概率但高危分支是否被合理关闭 | Tversky & Kahneman (1973); "What else?" 策略 |

### 7.2 与 Case #68（CML）的改善预测

以 Case #68 为例，新审议循环预期在以下节点干预：

```
Turn 1 后（timestep==1 触发）:
  EvidenceSynthesizer:
    B1(AML) examination_count=2, B3(CML) examination_count=0
    → confirmation_bias_risk = "high"
    → unexplained_findings = ["subacute onset over several days atypical for de novo AML"]

  DiagnosticChallenger:
    → leading_branch_challenge:
      "B1(AML) advantage rests on blast count alone; subacute constitutional
       symptoms and visual changes are equally consistent with CML blast crisis"
      evidence_basis = "absence_of_contradiction"
    → falsification_action:
      "Analyze whether the subacute tempo (days of malaise, night sweats,
       weight loss over a month) better fits a chronic myeloproliferative
       disorder accelerating into blast crisis than a de novo acute leukemia"
    → anchoring_risk = "high"

结果: TALP 被强制为 B3(CML) 生成分析动作，而非继续为 B1(AML) 深入
```

在旧架构中，Hypothesis 仅复读先验概率，CML 分支（P=0.1）从未获得足够分析关注。

---

## 八、Config 新增参数

```python
@dataclass
class ControllerConfig:
    # ... 现有字段 ...

    # ── 审议参数 ──
    enable_deliberation: bool = True
    deliberation_on_major_update: bool = True
    deliberation_on_contradiction: bool = True
    deliberation_on_leader_change: bool = True
    deliberation_on_final_turn: bool = True
    max_final_verification_rounds: int = 1
    high_anchoring_falsify_threshold: float = 0.3
    normal_falsify_threshold: float = 0.5
```

---

## 九、与旧架构的差异对照

| 维度 | 旧审议循环 | 新审议循环 |
|------|----------|----------|
| 模块数量 | 6 个 LLM | 2 个 LLM |
| 触发时机 | 每轮固定运行 | 条件触发（5 种条件） |
| 提示词质量 | 5/6 仅 3 行 | 2/2 完整提示词 + JSON schema |
| 输出消费 | Consensus 仅看 Checklist → selected_action 被 bundle 覆盖 | 注入 TALP 上下文 + 确定性分支重开 + Bundler 阈值调节 |
| 证据选取 | EvidenceAllocator（3 行提示词 LLM 调用）| 确定性优先级队列（0 LLM） |
| 行动决策 | Consensus 选 1 个动作（被忽略）| 不参与行动选择（TALP + Bundler 负责）|
| 终止验证 | 无 | final_verification 可否决终止 |
| 对确认偏差的防护 | 无有效机制 | examination_count 不均衡检测 + 强制覆盖修正 |
| 每 5 轮 LLM 开销 | 30 次 | 4 次（节省 87%） |

---

## 参考文献

1. Croskerry P. (2003). Cognitive forcing strategies in clinical decisionmaking. *Annals of Emergency Medicine, 41*(1), 110–120.
2. Croskerry P. (2009). A universal model of diagnostic reasoning. *Academic Medicine, 84*(8), 1022–1028.
3. Croskerry P. (2009). Dual processing and diagnostic errors. *Advances in Health Sciences Education, 14*(S1), 37–49.
4. Graber ML, Franklin N, Gordon R. (2005). Diagnostic error in internal medicine. *Archives of Internal Medicine, 165*(13), 1493–1499.
5. Kahneman D, Tversky A. (1974). Judgment under uncertainty: Heuristics and biases. *Science, 185*(4157), 1124–1131.
6. Lambe KA, O'Reilly G, Kelly BD, Curristan S. (2016). Dual-process cognitive interventions to enhance diagnostic reasoning: a systematic review. *BMJ Quality & Safety, 25*(10), 808–820.
7. Mamede S, Schmidt HG. (2022). Deliberate reflection and clinical reasoning: Founding ideas and empirical findings. *PubMed 35771936*.
8. Mendel R, Traut-Mattausch E, Jonas E, et al. (2011). Confirmation bias: why psychiatrists stick to wrong preliminary diagnoses. *Psychological Medicine, 41*(12), 2651–2659.
9. Monteiro SD, et al. (2024). Dual process models of clinical reasoning: The central role of knowledge in diagnostic expertise. *PubMed 38825755*.
10. Rao S, Ferris TG. (2022). A pause in pediatrics: implementation of a pediatric diagnostic time-out. *Diagnosis, dx-2022-0010*.
11. Sibbald M, et al. (2022). Checklists to reduce diagnostic error: a systematic review using a human factors framework. *BMJ Open, 12*(4), e058219.
12. Wolpaw TM, Wolpaw DR, Papp KK. (2003). SNAPPS: a learner-centered model for outpatient education. *Academic Medicine, 78*(9), 893–898.
13. Multi-Agent Conversational LLMs for diagnosis. *npj Digital Medicine* (2025), 8, Article 154.
14. Tree-of-Reasoning. *arXiv:2508.03038* (2025).
15. EVINCE. *arXiv:2405.15808* (2024).
16. MEDDxAgent. *ACL 2025*, 2025.acl-long.677.
