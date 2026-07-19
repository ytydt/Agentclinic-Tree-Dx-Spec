# TALP-Bundler 管线重设计规范

> **版本**: v1.0  
> **日期**: 2026-05-20  
> **前置文档**: `TALP_PIPELINE_IMPLEMENTATION_STATUS.md`, `STATIC_QA_DELIBERATION_DESIGN.md`  
> **适用范围**: `static_diagnosis_qa` 模式下的 TALP + FrontierCoverageBundler 管线

---

## 一、问题总结

经过系统性分析，当前 TALP-Bundler 管线存在以下相互关联的结构性缺陷：

### 1.1 `target_branches` 为平坦列表，丢失方向信息

**现状**：`target_branches: ["B1", "B2"]` 只回答"影响谁"，不回答"怎么影响"。  
**后果**：FrontierCoverageBundler 无法区分"正向覆盖 B2"和"附带反驳 B2"，导致 Phase 1.5 反证检测和 Phase 2 覆盖审计的语义模糊。

### 1.2 `primary_function` 同时承载方向和动机，语义过载

**现状**：`primary_function` 的四个枚举值（support/falsify/separate/safety_check）试图同时表达影响方向和认知动机。  
**后果**：
- LLM 系统性地将鉴别动作标为 "support"（日志中 60%+ 的多分支候选）
- Phase 1.5 检测 `primary_function == "falsify"` 几乎无法匹配任何候选
- `safety_check` 动机无法从方向信息推导，证明 `primary_function` 不可完全淘汰

### 1.3 `falsification_value` 定义模糊且实践中退化为噪声

**现状**：定义为"if result is negative, ability to disconfirm the leading branch"。  
**后果**：
- "阴性结果"过于狭窄——BCR-ABL 阳性同样不利于 de novo AML
- 反驳目标（"leading branch"）未被显式指定——从 B3 的视角生成的候选，其 falsification_value 相对于谁？
- LLM 实际赋值为 0.05-0.1 的噪声值

### 1.4 TALP 候选池与 Bundler 需求严重不协调

**现状**：TALP 提示词要求"每分支至少 1 个候选"，LLM 通常恰好生成 1 个。  
**后果**：
- Phase 1 消耗全部候选后，Phase 1.5 和 Phase 2 的候选池为空
- Phase 1.5 反证保障从未触发（无 `falsify` 候选可用）
- Phase 2 跨分支补充从未触发（无剩余候选）
- 整个多阶段 bundle 构建退化为"每分支选最高分候选"的简单排序

### 1.5 每分支 1 个动作无法同时满足正反两个认知需求

**现状**：Phase 1 的 `break` 语句在选到第一个候选后停止。  
**后果**：每个分支只能获得正向验证或自我否定中的一种，永远无法两全。在 static QA 模式下（所有惩罚项为 0），这是对零成本分析资源的人为浪费。

### 1.6 `selected_primary_action` 是单动作架构的残留物

**现状**：TALP 返回 `selected_primary_action`，controller 在 bundle 为空时将其作为 fallback。  
**后果**：在正常运行中从未被使用，但移除需处理 `candidate_leaves_ranked` 为空列表的边界情况。

---

## 二、重设计方案

### 2.1 `target_branches` 从列表改为方向字典

**旧**：
```json
"target_branches": ["B1", "B2", "B3"]
```

**新**：
```json
"target_branches": {
  "B1": "support",
  "B2": "against",
  "B3": "neutral"
}
```

每个受影响分支独立标注**预期影响方向**：
- `"support"`: 预期结果有利于该分支
- `"against"`: 预期结果不利于该分支
- `"neutral"`: 该分支受影响但方向不确定

**与 EvidenceAnnotator 的 `branch_effects` 形成事前/事后对称**：

| 阶段 | 字段 | 值域 |
|------|------|------|
| 事前（TALP 预测） | `target_branches` | `support` / `against` / `neutral` |
| 事后（Annotator 观测） | `branch_effects` | `strong_for` / `moderate_for` / `weak_for` / `neutral` / `weak_against` / `moderate_against` / `strong_against` |

**对 LLM 生成质量的影响**：字典格式不仅是数据结构的优化，也降低了 LLM 生成出错的概率。旧任务要求 LLM 同时做两个判断——(1) 从四个枚举值中选一个全局标签 (2) 列出所有受影响分支——两个判断之间的一致性不受结构约束，导致系统性语义倒挂（60%+ 的多分支候选被错误标为 "support"）。新任务只需对每个 frontier 分支做一个三选一判断（support / against / neutral），这是一个更简单、更局部的决策——LLM 在逐项填写结构化字段时比在需要全局一致性推理时表现更好。

### 2.2 `primary_function` 保留但职责收窄

`primary_function` 不再承载方向信息（方向由字典表达），只承载**不可从方向推导的认知动机**：

| 值 | 含义 | 典型场景 | 能否从字典推导 |
|---|------|---------|-------------|
| `confirm` | 验证性检查——寻求支持某假设的证据 | 常规诊断流程 | 可推导（branch_id 方向为 support） |
| `challenge` | 挑战性检查——试图动摇某假设 | 自我否定 / 反确认偏差 | 可推导（branch_id 方向为 against） |
| `differentiate` | 鉴别性检查——区分竞争假设 | 鉴别诊断 | 可推导（mixed 方向） |
| `safety_ensure` | 安全排查——排除低概率高危诊断 | 防灾难遗漏 | **不可推导**——需结合 danger 信息 |

**Bundler 的消费方式**：`safety_ensure` 标签影响 `_infer_coverage_mode` 的审计报告；其他三个值仅用于日志和调试。核心逻辑改为直接读取 `target_branches` 字典方向。

### 2.2b 三个评分指标的区别与在新设计中的角色

`LeafScore` 公式中包含三个信息论指标。它们测量不同维度的诊断价值，在新设计中各自的消费方式如下：

| | ExpectedInformationGain | FalsificationValue | ActionSeparationValue |
|---|---|---|---|
| **回答的问题** | "执行此动作后，对**单分支**的不确定性能降低多少？" | "如果结果对 branch_id 不利，能多大程度**动摇**该分支的后验？" | "此动作能在多大程度上**拉开**两个竞争分支的概率差距？" |
| **关注对象** | 单分支不确定性 | 单分支的脆弱性（challenge 候选） | 竞争分支间的可区分度 |
| **信息论语义** | 近似 KL 散度——当前后验与执行后预期后验的差异 | 非对称——仅衡量对 branch_id 不利结果的冲击力度 | 对称——区分任一方向均计入 |
| **对称性** | 双向（阳/阴性结果均计入） | 单向（仅不利结果） | 双向 |
| **Bundler 消费方式** | `_passes_gates()` 硬门槛（`min_marginal_ig_threshold`） | 通过 `total_score` 间接影响排名；仅 challenge 候选非零 | Phase 3 跨分支鉴别补充的选择标准 |
| **典型 target_branches** | 通常 1 个分支 | 通常 branch_id 自身（against） | 通常 2+ 个分支 |
| **临床类比** | 检查的总诊断效率 | 检查的排除能力（如 D-dimer 阴性排除 PE） | 鉴别试验（如 ANA 区分 SLE vs RA） |

**新设计中的变化**：
- `ExpectedInformationGain`：不变，仍为 `_passes_gates` 的硬门槛
- `FalsificationValue`：语义修正（见 §2.3），反驳目标从"leading branch"变为"branch_id 自身"，仅 challenge 候选非零
- `ActionSeparationValue`：不变，仍驱动 Phase 3

### 2.3 `falsification_value` 语义修正

**旧定义**：
> Ability to disconfirm the current leading branch if result is negative (0-1)

**新定义**：
> 如果分析结果对 `branch_id` 不利（无论结论是正面还是反面），能多大程度动摇 `branch_id` 的后验概率。仅在 challenge 候选中非零。(0-1)

关键变更：
- 反驳目标从"leading branch"变为"branch_id 自身"——每个 challenge 候选挑战的是自己归属的分支
- "阴性结果"变为"对 branch_id 不利的结果"——涵盖阳性和阴性两种可能

### 2.4 TALP 提示词：每分支 2 个候选（confirm + challenge）

**旧指令**：
> For EACH live branch generate at least one candidate analytic step.

**新指令**：
> 对每个 frontier 分支，生成**恰好 2 个**候选动作：
>
> (a) **confirm 候选**（`primary_function: "confirm"`）  
>     分析证据中**最支持**该分支的发现。  
>     `target_branches: { branch_id: "support", ... }`
>
> (b) **challenge 候选**（`primary_function: "challenge"`）  
>     分析证据中**最不利于**该分支的发现。  
>     `target_branches: { branch_id: "against", ... }`
>
> 如果你认为某分支无任何不利证据，将 challenge 候选的  
> `expected_information_gain` 设为 0.0（Bundler 会自动过滤）。
>
> 对于 `danger >= 0.7` 的分支，如果该分支后验 < 0.15，  
> 将其 confirm 候选的 `primary_function` 改为 `"safety_ensure"`。

**候选池大小变化**：4 分支 × 2 = 8 候选 → Phase 1 消耗 4，Phase 1b 消耗 3-4，Phase 2 有余量。

### 2.5 FrontierCoverageBundler：双通道 Phase 1

**旧结构**：
```
Phase 0: 终止短路
Phase 1: 每分支选 1 个最高分候选
Phase 1.5: 反证保障（依赖 primary_function == "falsify"）
Phase 2: 跨分支补充
Phase 3: 排序
```

**新结构**：
```
Phase 0:  终止短路（不变）
Phase 1:  confirm 通道 — 每分支选 target_branches[bid] == "support" 的最高分候选
Phase 1b: challenge 通道 — 每分支选 target_branches[bid] == "against" 的最高分候选
Phase 2:  方向多样性检查 — 若 leader 无任何 "against" 覆盖，构造性注入
Phase 3:  跨分支鉴别补充（action_separation_value 驱动，不变）
Phase 4:  排序（不变）
```

#### Phase 1 详细逻辑

```python
for branch_id in state.frontier:
    branch = state.branches.get(branch_id)
    if branch is None or branch.status not in ("live", "reopened"):
        continue
    for candidate in candidate_leaves:
        if candidate.branch_id != branch_id:
            continue
        tb = candidate.target_branches
        if not isinstance(tb, dict) or tb.get(branch_id) != "support":
            continue
        if not _passes_gates(candidate, bundle, content_set, config, min_ig):
            continue
        confirm_covered[branch_id] = candidate
        bundle.append(candidate)
        content_set.add(_normalize(candidate.content))
        break
```

#### Phase 1b 详细逻辑

```python
for branch_id in state.frontier:
    branch = state.branches.get(branch_id)
    if branch is None or branch.status not in ("live", "reopened"):
        continue
    for candidate in candidate_leaves:
        if candidate.branch_id != branch_id:
            continue
        tb = candidate.target_branches
        if not isinstance(tb, dict) or tb.get(branch_id) != "against":
            continue
        if not _passes_gates(candidate, bundle, content_set, config, min_ig):
            continue
        challenge_covered[branch_id] = candidate
        bundle.append(candidate)
        content_set.add(_normalize(candidate.content))
        break
```

#### Phase 2：方向多样性检查（替代旧 Phase 1.5）

```python
leader = max(live_branches, key=lambda b: b.posterior)
if leader.posterior >= 0.3:
    has_leader_challenge = leader.id in challenge_covered
    if not has_leader_challenge:
        # 候选池中也找不到 → 构造性注入
        synthetic = CandidateLeaf(
            leaf_id=f"{leader.id}::synthetic_challenge",
            branch_id=leader.id,
            leaf_type="ANALYZE_VIGNETTE",
            content=(
                f"What evidence in the vignette is MOST INCONSISTENT with "
                f"{leader.label}? Identify the single strongest finding that "
                f"argues against this diagnosis."
            ),
            target_branches={leader.id: "against"},
            primary_function="challenge",
            expected_information_gain=0.4,
            falsification_value=0.5,
            # 其他字段使用默认值
        )
        bundle.append(synthetic)
```

**设计理由**：
- 阈值从 0.5 降至 0.3——更早启动挑战机制
- 不再依赖 `primary_function == "falsify"` 标签——直接检查字典方向
- 构造性注入作为最后防线——确保即使 TALP 生成的所有候选都是 support 方向，leader 仍会被挑战

### 2.6 移除 `selected_primary_action`

**变更**：TALP 提示词中移除 `selected_primary_action` 字段。  
**Controller 中的 fallback 修改**：

```python
# 旧
if not bundle:
    bundle = [_action_dict_to_leaf(selected_action)]

# 新
if not bundle and candidate_leaves:
    bundle = [candidate_leaves[0]]
elif not bundle:
    # candidate_leaves 也为空 — 异常情况，注入诊断探测动作
    bundle = [CandidateLeaf(
        leaf_id="fallback::probe",
        branch_id=state.frontier[0] if state.frontier else "unknown",
        leaf_type="ANALYZE_VIGNETTE",
        content="Summarize all available evidence and identify which branch best fits.",
        target_branches={bid: "neutral" for bid in state.frontier},
        primary_function="differentiate",
        expected_information_gain=0.3,
        # ...
    )]
```

### 2.7 Bundle 大小估算

| 组件 | 4 分支 | 6 分支 |
|------|--------|--------|
| Phase 1（confirm） | 4 | 6 |
| Phase 1b（challenge） | 3-4（EIG=0 的被过滤） | 4-6 |
| Phase 2（构造性注入） | 0-1 | 0-1 |
| Phase 3（鉴别补充） | 0-2 | 0-2 |
| **总计** | **7-11** | **10-15** |

**LLM 调用数不变**：所有 ANALYZE_VIGNETTE 执行为 dict 返回（无 LLM），EvidenceAnnotator 仍为 1 次批量调用。

---

## 三、修订后的 TALP JSON Schema

```json
{
  "candidate_leaves_ranked": [
    {
      "branch_id": "B1",
      "type": "ANALYZE_VIGNETTE",
      "content": "分析性问题",
      "score": 0.85,
      "expected_information_gain": 0.7,
      "safety_value": 0.0,
      "action_separation_value": 0.6,
      "falsification_value": 0.0,
      "expected_cost": 0.0,
      "expected_delay": 0.0,
      "invasiveness": 0.0,
      "target_branches": {
        "B1": "support",
        "B2": "against",
        "B3": "neutral"
      },
      "primary_function": "confirm",
      "bundle_independence": 1.0,
      "result_dependency": false,
      "redundancy_group": "",
      "urgency": "routine",
      "why": "..."
    },
    {
      "branch_id": "B1",
      "type": "ANALYZE_VIGNETTE",
      "content": "什么证据与 B1 最不一致？",
      "score": 0.65,
      "expected_information_gain": 0.5,
      "safety_value": 0.0,
      "action_separation_value": 0.3,
      "falsification_value": 0.7,
      "expected_cost": 0.0,
      "expected_delay": 0.0,
      "invasiveness": 0.0,
      "target_branches": {
        "B1": "against",
        "B2": "support"
      },
      "primary_function": "challenge",
      "bundle_independence": 1.0,
      "result_dependency": false,
      "redundancy_group": "",
      "urgency": "routine",
      "why": "self-challenge for confirmation bias prevention"
    }
  ]
}
```

**删除的字段**：`selected_primary_action`  
**保留但语义变更的字段**：`target_branches`（列表 → 字典）、`primary_function`（枚举值变更）、`falsification_value`（反驳目标变更）

---

## 四、修订后的 CandidateLeaf 数据结构

```python
@dataclass
class CandidateLeaf:
    leaf_id: str
    branch_id: str
    leaf_type: str
    content: str
    expected_information_gain: float
    expected_cost: float
    expected_delay: float
    safety_value: float
    action_separation_value: float
    total_score: float

    # ── 方向与动机（v2 redesign）──
    # 每个受影响分支的预期影响方向：
    #   {"B1": "support", "B2": "against", "B3": "neutral"}
    target_branches: dict[str, str] = field(default_factory=dict)
    # 认知动机：confirm | challenge | differentiate | safety_ensure
    primary_function: str = "confirm"
    # 对 branch_id 的最大不利冲击力（仅 challenge 候选非零）(0-1)
    falsification_value: float = 0.0

    # ── 调度与约束 ──
    invasiveness: float = 0.0
    urgency: str = "routine"
    redundancy_group: str = ""
    bundle_independence: float = 1.0
    result_dependency: bool = False
    why: str = ""
```

**字段设计原理总表**：以下 6 个字段各自编码不同的维度，互不冗余：

| 字段 | 回答什么 | 维度 | 可否从其他字段推导 |
|------|---------|------|-----------------|
| `branch_id` | 为哪个 frontier 分支生成此候选 | 归属 | — |
| `target_branches` (dict) | 对各分支影响什么方向 | 方向（事前预测） | — |
| `primary_function` | 为什么选这个动作 | 认知动机 | 部分可推导（confirm/challenge/differentiate 可从方向推导），但 `safety_ensure` **不可推导**——需结合 danger 信息 |
| `expected_information_gain` | 总不确定性能降低多少 | 双向信息量 | — |
| `falsification_value` | 反面结果的决定性冲击力 | 单向冲击力度 | **不可从方向字典推导**——同为 `against` 的不同动作冲击力可以天差地别（0.2 vs 0.9），取决于临床检查的特异性和敏感性 |
| `action_separation_value` | 能多大程度拉开竞争分支差距 | 鉴别分辨率 | — |

**兼容性**：`target_branches` 类型从 `list[str]` 变为 `dict[str, str]`。所有消费 `target_branches` 的代码需要更新。

---

## 五、修订后的 TALP 提示词

```
Role: TemporaryAnalyticLeafPlanner

You are reasoning over a FIXED clinical vignette (no real patient interaction). All
evidence is pre-given in the case text. Your task is to generate structured analytic
candidates for each live branch, then let the downstream bundler select the final set.

Action types available:
- ANALYZE_VIGNETTE : analyse how specific evidence bears on a branch
- DIAGNOSIS_READY  : declare the differential resolved when evidence is conclusive

Instructions:

1. For EACH live branch in state.frontier, generate EXACTLY 2 candidates:

   (a) A CONFIRM candidate — analyse the evidence that BEST SUPPORTS this branch.
       Set target_branches[branch_id] = "support".
       Set primary_function = "confirm".
       Set falsification_value = 0.0.

   (b) A CHALLENGE candidate — analyse the evidence that is MOST INCONSISTENT
       with this branch. This is a self-challenge: you are looking for reasons
       why this branch might be WRONG, not why it is right.
       Set target_branches[branch_id] = "against".
       Set primary_function = "challenge".
       Set falsification_value = estimated probability displacement if the
       inconsistency is confirmed (0.0–1.0).

   If you cannot identify any inconsistent evidence for a branch, set the
   challenge candidate's content to:
   "No contradicting evidence identified for [branch label]; all available
   findings are consistent."
   and set expected_information_gain = 0.0 (Bundler will automatically filter it).

   EXCEPTION: for branches with danger >= 0.7 AND posterior < 0.15, replace
   the confirm candidate with a SAFETY_ENSURE candidate:
       Set primary_function = "safety_ensure".
       This candidate should analyse whether any evidence RULES OUT this
       dangerous diagnosis — failing to do so is a safety gap.

2. For EACH candidate, fill target_branches as a dictionary mapping EVERY
   affected branch to its expected impact direction:
     "support"  — the analysis result is expected to favor this branch
     "against"  — the analysis result is expected to disfavor this branch
     "neutral"  — the branch is affected but direction is uncertain

   The directions of different branches CAN and often SHOULD differ for the
   same candidate. Example: an analysis showing that subacute onset favors CML
   should have target_branches = {"B1(AML)": "against", "B2(CML)": "support"}.

3. Score each candidate (all components 0–1):
     LeafScore = ExpectedInformationGain
               + SafetyValue
               + ActionSeparationValue
               + FalsificationValue
   (CostPenalty / DelayPenalty / InvasivenessPenalty = 0 for analytic steps)

4. Content should be a precise, branch-specific question about the vignette
   evidence. Do NOT write generic questions that apply to all branches.
   Good: "Does the subacute onset over days with constitutional symptoms
          argue against de novo AML in favor of a chronic process?"
   Bad:  "Analyze the evidence for this branch."

5. Set bundle_independence = 1.0 and result_dependency = false for all
   analytic steps (they are independent since evidence is fixed).

6. Once one branch achieves clear dominance (posterior > 0.75 and no
   dangerous alternative), use DIAGNOSIS_READY as the top-ranked candidate.

Return strict JSON only, no markdown:
{
  "candidate_leaves_ranked": [
    {
      "branch_id": "B1",
      "type": "ANALYZE_VIGNETTE",
      "content": "precise analytic question",
      "score": 0.0,
      "expected_information_gain": 0.0,
      "safety_value": 0.0,
      "action_separation_value": 0.0,
      "falsification_value": 0.0,
      "expected_cost": 0.0,
      "expected_delay": 0.0,
      "invasiveness": 0.0,
      "target_branches": {"B1": "support", "B2": "against"},
      "primary_function": "confirm",
      "bundle_independence": 1.0,
      "result_dependency": false,
      "redundancy_group": "",
      "urgency": "routine",
      "why": "one-line rationale"
    }
  ]
}
```

---

## 六、修订后的 FrontierCoverageBundler 算法

```python
def build_bundle(candidate_leaves, state, config):
    if not candidate_leaves:
        return [], {}

    # Phase 0: 终止短路
    if candidate_leaves[0].leaf_type == "DIAGNOSIS_READY":
        return [candidate_leaves[0]], {}

    min_ig = config.min_marginal_ig_threshold
    bundle = []
    content_set = set()
    confirm_covered = {}
    challenge_covered = {}

    # Phase 1: confirm 通道
    for branch_id in state.frontier:
        branch = state.branches.get(branch_id)
        if branch is None or branch.status not in ("live", "reopened"):
            continue
        for candidate in candidate_leaves:
            if candidate.branch_id != branch_id:
                continue
            tb = candidate.target_branches
            if not isinstance(tb, dict) or tb.get(branch_id) != "support":
                continue
            if not _passes_gates(candidate, bundle, content_set, config, min_ig):
                continue
            confirm_covered[branch_id] = candidate
            bundle.append(candidate)
            content_set.add(_normalize(candidate.content))
            break

    # Phase 1b: challenge 通道
    for branch_id in state.frontier:
        branch = state.branches.get(branch_id)
        if branch is None or branch.status not in ("live", "reopened"):
            continue
        for candidate in candidate_leaves:
            if candidate.branch_id != branch_id:
                continue
            tb = candidate.target_branches
            if not isinstance(tb, dict) or tb.get(branch_id) != "against":
                continue
            if not _passes_gates(candidate, bundle, content_set, config, min_ig):
                continue
            challenge_covered[branch_id] = candidate
            bundle.append(candidate)
            content_set.add(_normalize(candidate.content))
            break

    # Phase 2: 方向多样性检查（替代旧 Phase 1.5）
    live_branches = [
        b for b in state.branches.values()
        if b.status in ("live", "reopened")
    ]
    if live_branches:
        leader = max(live_branches, key=lambda b: b.posterior)
        if leader.posterior >= 0.3 and leader.id not in challenge_covered:
            # 尝试从候选池中找任何对 leader 为 against 的候选
            for candidate in candidate_leaves:
                if candidate in bundle:
                    continue
                tb = candidate.target_branches
                if isinstance(tb, dict) and tb.get(leader.id) == "against":
                    if _passes_gates(candidate, bundle, content_set, config, min_ig):
                        bundle.append(candidate)
                        content_set.add(_normalize(candidate.content))
                        challenge_covered[leader.id] = candidate
                        break
            # 仍然没有 → 构造性注入
            if leader.id not in challenge_covered:
                synthetic = _build_synthetic_challenge(leader)
                bundle.append(synthetic)

    # Phase 3: 跨分支鉴别补充（不变）
    sep_threshold = config.min_separation_value_for_supplement
    sorted_by_sep = sorted(
        candidate_leaves,
        key=lambda c: c.action_separation_value,
        reverse=True,
    )
    for candidate in sorted_by_sep:
        if candidate in bundle:
            continue
        if candidate.action_separation_value < sep_threshold:
            break
        if not _passes_gates(candidate, bundle, content_set, config, min_ig):
            continue
        bundle.append(candidate)
        content_set.add(_normalize(candidate.content))

    # Phase 4: 排序
    bundle.sort(key=lambda a: a.expected_delay)

    # 审计报告
    branch_coverage = _build_coverage_audit(
        state, confirm_covered, challenge_covered, candidate_leaves, min_ig
    )
    return bundle, branch_coverage
```

---

## 七、覆盖审计报告增强

旧审计只区分 `covered` / `deferred`。新审计为每个分支分别报告 confirm 和 challenge 覆盖：

```python
def _build_coverage_audit(state, confirm_covered, challenge_covered, candidates, min_ig):
    audit = {}
    for branch_id in state.frontier:
        branch = state.branches.get(branch_id)
        if branch is None:
            continue
        audit[branch_id] = {
            "confirm_status": "covered" if branch_id in confirm_covered else "deferred",
            "challenge_status": "covered" if branch_id in challenge_covered else "deferred",
            "confirm_content": confirm_covered[branch_id].content if branch_id in confirm_covered else None,
            "challenge_content": challenge_covered[branch_id].content if branch_id in challenge_covered else None,
            "confirm_deferral_reason": None if branch_id in confirm_covered else _deferral_reason(branch_id, state, candidates, min_ig, "support"),
            "challenge_deferral_reason": None if branch_id in challenge_covered else _deferral_reason(branch_id, state, candidates, min_ig, "against"),
        }
    return audit
```

---

## 八、`_passes_gates` 的变更

`_is_redundant` 需要考虑同分支的 confirm 和 challenge 候选**不应被互相判为冗余**（它们内容词汇相似但认知方向相反）。

新增 gate：如果两个候选的 `branch_id` 相同但 `target_branches[branch_id]` 方向相反，豁免冗余检查。

```python
def _is_redundant(candidate, bundle, content_set, threshold):
    norm_c = _normalize(candidate.content)

    if candidate.redundancy_group:
        if any(b.redundancy_group == candidate.redundancy_group for b in bundle if b.redundancy_group):
            return True

    for existing in bundle:
        # 同分支反方向豁免
        if (existing.branch_id == candidate.branch_id
            and isinstance(existing.target_branches, dict)
            and isinstance(candidate.target_branches, dict)):
            own_dir_existing = existing.target_branches.get(existing.branch_id)
            own_dir_candidate = candidate.target_branches.get(candidate.branch_id)
            if own_dir_existing and own_dir_candidate and own_dir_existing != own_dir_candidate:
                continue  # 方向相反，不检查冗余

    for existing_norm in content_set:
        if _jaccard(norm_c, existing_norm) > threshold:
            return True
    return False
```

---

## 九、Controller 变更清单

| 位置 | 变更 |
|------|------|
| `plan_temporary_leaves` | 解析 `target_branches` 为 dict；移除 `selected_primary_action` 返回值 |
| `run` 主循环 | 移除 `selected_action` 变量及 consensus override 逻辑 |
| `run` bundle fallback | 从 `candidate_leaves[0]` 或构造性 fallback 获取 |
| `_normalize_static_qa_action` | 不变 |
| `_dispatch_env_call` | 不变 |
| `annotate_evidence_bundle` | 不变（bundle 更大但路径相同） |
| `group_correlated_evidence` | 不变（更大 bundle 时降级仍有效） |

---

## 十、修改文件索引

| 文件 | 修改内容 |
|------|---------|
| `src/agentclinic_tree_dx/state.py` | `CandidateLeaf.target_branches` 类型变更；注释更新 |
| `src/agentclinic_tree_dx/prompts/temporary_analytic_leaf_planner.txt` | 完整重写 |
| `src/agentclinic_tree_dx/action_bundler.py` | Phase 1/1b/2/3/4 重构；`_is_redundant` 方向豁免；覆盖审计增强 |
| `src/agentclinic_tree_dx/controller.py` | 移除 `selected_primary_action`；更新 `plan_temporary_leaves` 解析；更新 fallback |
| `src/agentclinic_tree_dx/config.py` | 新增 `leader_challenge_threshold: float = 0.3` |
| `tests/test_action_bundle.py` | 更新测试用例适配新 target_branches 格式 |
| `tests/test_static_qa_mode.py` | 更新 mock responses 适配新 schema |

---

## 十一、临床规范依据

本重设计的核心变更——**每分支同时生成 confirm 和 challenge 候选**——是 SNAPPS 框架 Step 3 的直接实现：

> *"Learners discuss why the patient presentation **supports or refutes EACH** differential diagnosis."*  
> — Wolpaw et al. (2003), *Academic Medicine, 78*(9), 893–898.

"自我否定"（每个分支挑战自己）优于"挑战首选分支"（旧 Phase 1.5 的策略）：

1. **临床鉴别诊断的基本规范**：对每个鉴别假设，医生都需要同时评估 for 和 against 证据——不是只挑战最可能的那个。旧设计将反证目标固定在 leader 上，违反了这一规范
2. **确认偏差的机制更精确**：确认偏差不仅发生在首选分支上，也发生在每个已获得初步支持的分支上。如果 B3 在 Turn 1 被 support 后没有被 challenge，它的概率会稳定在一个可能偏高的水平。自我否定覆盖所有分支的偏差风险
3. **信息增益更高**：N 个分支各自做 1 次自我否定 = N 个独立的反证检查（边际信息增益不递减）。而 N 个分支都去挑战首选 B1 = 对 B1 的冗余攻击（边际信息增益急剧递减）
4. **与双过程理论一致**：System 2 的作用不是攻击 System 1 的结论，而是对每个假设做结构化正反评估

引导式反思（guided reflection）文献支持将正反评估作为标准化流程：

> *"Deliberate reflection is effective particularly in nonstraightforward diagnostic tasks."*  
> — Mamede & Schmidt (2022), *PubMed 35771936*

---

## 十二、向后兼容与回滚计划

1. 修改前备份所有受影响文件到 `backups/pre_redesign_20260520/`
2. `target_branches` 解析代码同时支持 list 和 dict 格式（渐进迁移）
3. `config.py` 新增 `use_dual_channel_bundler: bool = True` 开关，设为 False 时回退到旧 Phase 1 逻辑
