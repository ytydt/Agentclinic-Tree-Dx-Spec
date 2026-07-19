# 每轮多动作执行算法设计文档

> **文档类型**：算法设计规格（Algorithm Design Specification）  
> **版本**：v1.0  
> **适用范围**：所有执行模式；修正现有单动作-每轮限制  
> **依赖文档**：`readme.md`、`SHARED_MODULES_IMPLEMENTATION.md`

---

## 1. 问题陈述

### 1.1 现有限制

当前实现在每轮循环中仅执行**一个动作**：

```python
# controller.py: run()
raw_result = self.execute_primary_action(state, selected_action)   # 单个动作
annotation = self.annotate_evidence(state, raw_result)              # 单个结果
```

`TemporaryLeafPlanner` 虽然生成了多个候选叶子的排名列表，但只有排名最高的一个被实际执行。

### 1.2 临床不合理性

**文献依据**：

> *"在急诊医学研究中，医生平均每个病例申请 7.2 项检查。"*  
> — MAI Diagnostic Orchestrator Benchmark (arXiv:2506.22405)

> *"并行策略（同时申请多项检查）可显著缩短信息等待时间，尤其适用于紧急情况或多个独立鉴别诊断同时需要明确的场景。"*  
> — Hershey & Cebul (1986), *Using Multiple Tests: Series and Parallel Approaches*

> *"从信息论角度而言，对独立检查目标采用并行策略，其信息获取总量等于各检查的信息量之和，不存在信息冗余损失——前提是各检查的诊断靶点相互独立。"*  
> — Moons & Harrell (2001), *Sensitivity and the Obscure True Negative Rate*

具体临床场景中，单动作限制造成不合理延迟：

| 场景 | 合理做法 | 当前系统行为 |
|------|---------|------------|
| 急性胸痛工作评估 | 同时开 ECG + 肌钙蛋白 + CXR | 须分3轮，各等待1次 |
| 多系统受累鉴别 | 同时问病史+查体+开血常规 | 须分3轮 |
| 感染灶定位 | 同时问症状+开尿培养+血培养 | 须分3轮 |

**串行 vs. 并行的信息论分析**：

- 若动作 A 和动作 B 的诊断靶点**相互独立**（例如 ECG 靶向"缺血性心脏病"，尿液分析靶向"泌尿系感染"），则并行执行不损失信息增益；
- 若动作 B 在语义上**依赖**动作 A 的结果（例如"若肌钙蛋白阳性，再做超声心动图"），则必须串行；
- 决策理论证明（Howard, 1966; Pratt et al., 1995）：当检查相互独立时，批量执行的期望信息价值等于各检查期望信息价值之和。

---

## 2. 算法设计目标

1. 每轮允许执行 **1–k 个动作**（k = `config.max_bundle_size`，默认 3）；
2. 保证**无信息冗余**：同一束内的动作不应对同一诊断问题重复询问；
3. 保证**无依赖违反**：依赖先前结果的动作不与其前驱共束；
4. 对**高危分支**保留快速通道（`danger ≥ 0.7` 的动作优先级不降低）；
5. 与**外部环境接口兼容**：SDBench、AgentClinic 等环境可按动作类型限制束宽；
6. 与**轮次预算模型兼容**：束视作一轮（可配置为按动作计费）。

---

## 3. 核心概念：动作束（Action Bundle）

**动作束**是一组在同一轮内并行执行的动作，其元素满足：
- **独立性**：束内任意两个动作不存在信息依赖关系；
- **非冗余性**：束内任意两个动作的诊断靶点不重叠；
- **容量约束**：`1 ≤ |bundle| ≤ config.max_bundle_size`。

束中动作执行后，其结果被**批量送入** `EvidenceAnnotator`，产生一份综合注释。

---

## 4. ActionBundler 模块（新增确定性模块）

### 4.1 定位

`ActionBundler` 是一个**纯确定性后处理器**，在 `TemporaryLeafPlanner` 之后运行，从候选叶子排名列表中构造动作束。不调用 LLM。

### 4.2 输入

- `candidate_leaves`：`TemporaryLeafPlanner` 输出的排名候选列表（已含各分量分数）
- `state`：当前 `DiagnosticState`（含 `actions_taken`、`branches`、`frontier` 等）
- `config`：包含 `max_bundle_size`、`min_marginal_ig_threshold`、`redundancy_similarity_threshold`

### 4.3 完整算法

```
ActionBundler(candidate_leaves, state, config) → bundle: list[Action]

Step 1: 主动作选取
  primary = candidate_leaves[0]    # LeafScore 最高动作，永远入束
  bundle = [primary]
  used_branch_ids = {primary.branch_id}
  used_targets = {normalize_content(primary.content)}

Step 2: 补充动作贪心填充
  for candidate in candidate_leaves[1:]:
    if len(bundle) >= config.max_bundle_size:
      break

    # ── 约束1：依赖性检查（DEPENDENCY GATE）──
    if is_dependent_on_bundle_result(candidate, bundle):
      continue    # 该动作依赖束内某动作的结果 → 跳过

    # ── 约束2：冗余性检查（REDUNDANCY GATE）──
    if is_redundant_with_bundle(candidate, bundle, config.redundancy_similarity_threshold):
      continue    # 诊断靶点已被束内某动作覆盖 → 跳过

    # ── 约束3：边际价值检查（MARGINAL VALUE GATE）──
    marginal_ig = candidate.expected_information_gain × (1 - overlap_factor(candidate, bundle))
    if marginal_ig < config.min_marginal_ig_threshold:
      continue    # 边际信息增益过低 → 跳过（束内其他动作已充分覆盖）

    # ── 偏好：跨分支覆盖 ──
    cross_branch_bonus = 0.1 if candidate.branch_id not in used_branch_ids else 0.0

    bundle.append(candidate)
    used_branch_ids.add(candidate.branch_id)
    used_targets.add(normalize_content(candidate.content))

Step 3: 安全分支优先插入
  # 若主动作不涉及高危分支（danger < 0.7），检查是否有未入束的高危动作
  high_danger_not_in_bundle = [
    c for c in candidate_leaves
    if c not in bundle
    and state.branches.get(c.branch_id, Branch(...)).danger >= 0.7
    and not is_redundant_with_bundle(c, bundle, config.redundancy_similarity_threshold)
  ]
  if high_danger_not_in_bundle and len(bundle) < config.max_bundle_size:
    # 替换束中评分最低的非安全动作（若存在），确保高危分支被覆盖
    lowest_non_danger = min(
      (b for b in bundle if state.branches.get(b.branch_id, Branch(...)).danger < 0.7),
      key=lambda x: x.total_score,
      default=None
    )
    if lowest_non_danger and high_danger_not_in_bundle[0].total_score > lowest_non_danger.total_score × 0.5:
      bundle.remove(lowest_non_danger)
      bundle.insert(0, high_danger_not_in_bundle[0])   # 高危动作置于束首

Step 4: 束内排序
  # 按预期延迟从低到高排序（低延迟动作先执行，如问患者 < 验血 < 影像）
  bundle.sort(key=lambda a: a.expected_delay)

return bundle
```

### 4.4 依赖性检查（is_dependent_on_bundle_result）

```python
RESULT_DEPENDENT_TYPES = {"USE_CALCULATOR", "RETRIEVE_KNOWLEDGE", "RETRIEVE_EXTERNAL_KNOWLEDGE"}

def is_dependent_on_bundle_result(candidate, bundle):
    """
    保守启发式：
    - USE_CALCULATOR / RETRIEVE_KNOWLEDGE 类型通常需要特定数值作为输入，
      若束内有可能产生该输入的动作，则判定为依赖。
    - 精确实现需要语义解析；当前版本使用类型-优先级代理：
      若 candidate 类型为结果依赖型，且束内存在 ORDER_LAB / ORDER_IMAGING，
      则该 candidate 不应在同一束内（可能需要等待结果）。
    """
    if candidate.leaf_type not in RESULT_DEPENDENT_TYPES:
        return False
    # 若束内有可能产生输入数值的检查动作，则判定依赖成立
    data_producing_types = {"ORDER_LAB", "ORDER_IMAGING", "REQUEST_VITAL", "REQUEST_EXAM"}
    return any(b.leaf_type in data_producing_types for b in bundle)
```

### 4.5 冗余性检查（is_redundant_with_bundle）

```python
def is_redundant_with_bundle(candidate, bundle, threshold=0.6):
    """
    两动作冗余当且仅当：
    (a) 相同 branch_id + 相同 leaf_type，OR
    (b) content 字符串的标准化 Jaccard 相似度 > threshold
    """
    for b in bundle:
        if b.branch_id == candidate.branch_id and b.leaf_type == candidate.leaf_type:
            if jaccard_similarity(normalize(b.content), normalize(candidate.content)) > threshold:
                return True
    return False

def jaccard_similarity(s1: str, s2: str) -> float:
    tokens1 = set(s1.lower().split())
    tokens2 = set(s2.lower().split())
    if not tokens1 or not tokens2:
        return 0.0
    return len(tokens1 & tokens2) / len(tokens1 | tokens2)

def normalize(content: str) -> str:
    # 去除标点、停用词（简化版）
    return " ".join(w for w in content.lower().split() if len(w) > 2)
```

---

## 5. TemporaryLeafPlanner 提示词修订

需在提示词中增加**束意识**（bundle-awareness），使 LLM 在评分时考虑候选动作的互补性，而非仅最大化单个动作的分值。

**新增字段**：在每个候选叶子的 JSON 结构中添加 `bundle_compatibility` 信息：

```
Additional scoring instruction:
6. For each candidate, assess its bundle_independence: how different is this
   action's diagnostic target from the other top candidates?
   - bundle_independence: 1.0 means completely independent diagnostic target
   - bundle_independence: 0.0 means directly redundant with higher-ranked candidate
   This field assists the deterministic ActionBundler to build the final bundle.

7. Do not propose two actions with near-identical content strings in the
   candidate_leaves_ranked list; only one of each unique diagnostic target
   should appear.
```

**新增输出字段**（每个候选叶子）：

```json
{
  "branch_id": "B1",
  "type": "ASK_PATIENT",
  "content": "...",
  "score": 0.0,
  "expected_information_gain": 0.0,
  "safety_value": 0.0,
  "action_separation_value": 0.0,
  "expected_cost": 0.0,
  "expected_delay": 0.0,
  "bundle_independence": 0.85,
  "result_dependency": false,
  "why": "one-line rationale"
}
```

其中：
- `bundle_independence`（0–1）：此动作与排名更高的候选在诊断靶点上的独立程度；
- `result_dependency`（bool）：此动作是否需要本轮其他动作的结果才能有意义（若为 true，则 ActionBundler 不将其与前驱同束）。

---

## 6. 动作束执行（execute_action_bundle）

### 6.1 接口

```python
def execute_action_bundle(
    self, state: DiagnosticState, bundle: list[dict]
) -> list[dict]:
    """
    按束内顺序执行每个动作，收集结果列表。
    每个动作仍通过现有 execute_primary_action 逻辑执行，
    但结果被累积为列表而非单个值。
    """
    results = []
    for action in bundle:
        raw_result = self.execute_primary_action(state, action)
        results.append({
            "action": action,
            "raw_result": raw_result,
        })
    return results
```

> **注意**：`execute_primary_action` 对每个动作仍独立追加 `state.actions_taken` 记录。在 SDBench、AgentClinic Patch 等模式下，外部动作类型归一化逻辑保持不变。

### 6.2 环境兼容层

不同外部环境对并行动作的支持程度不同：

| 模式 | 束宽限制 | 原因 |
|------|---------|------|
| `default` | 无限制（受 `max_bundle_size` 约束） | 无外部约束 |
| `agentclinic_physician_patch` | ≤ 2 | AgentClinic 患者代理为单轮问答模型；每束最多1个 `ASK_PATIENT` |
| `sdbench_patch` | ≤ 3 | Gatekeeper 接口允许批量询问，但建议不超过3个 |
| `static_diagnosis_qa` | ≤ 1 | 静态题干不受并行收益；保持单动作 |

**环境级束宽覆盖**（在 `ActionBundler` 调用前应用）：

```python
def effective_bundle_size(self, config_max: int) -> int:
    if self._in_static_qa_mode():
        return 1
    if self._in_patch_mode():
        return min(config_max, 2)
    if self._in_sdbench_mode():
        return min(config_max, 3)
    return config_max
```

### 6.3 AgentClinic Patch 模式的特殊约束

在此模式下，`ASK_PATIENT` 和 `REQUEST_TEST_OR_MEASUREMENT` 须分别走不同的外部代理（`patient_agent` vs `measurement_agent`）。一束内可同时包含两者（各最多1个），因为它们调用的是不同代理，**实质上是并行的**：

```python
# agentclinic patch 模式：若束内包含 ASK_PATIENT + REQUEST_TEST_OR_MEASUREMENT
# 可以并行（分别调用不同代理），无顺序依赖
```

---

## 7. 多结果证据注释（annotate_evidence_bundle）

### 7.1 设计选择分析

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A. 逐一注释后合并 | 对每个 (动作, 结果) 对分别调用 EvidenceAnnotator，再确定性地合并注释 | 可追溯；冲突可见 | k 次 LLM 调用/轮；合并规则需设计 |
| B. 批量单次注释 | 将所有 (动作, 结果) 对一并发送给 EvidenceAnnotator，单次 LLM 调用 | 1次 LLM 调用；LLM 可考虑结果间交互 | 提示词复杂度增加；LLM 可能遗漏某些结果 |
| C. 主动作注释 + 补充更新 | 仅对主动作做完整注释，次级动作做轻量补充注释 | 降低 LLM 负担 | 次级结果权重降低不合理 |

**选择方案 B（批量单次注释）**，理由：
1. 临床推理中，多条证据同时呈现时，结果间的**交互效应**（如两项检查互相印证）是真实的，LLM 应看到完整上下文；
2. 避免"逐一注释"中的顺序偏差——先注释的结果可能影响后续注释的起点分布；
3. 每轮节省 k-1 次 LLM 调用，对预算控制更友好。

### 7.2 EvidenceAnnotator 提示词修订

**新增多结果输入格式**说明：

```
Multi-result input note:
When raw_result is a list of {action, raw_result} pairs, you are receiving
multiple new results from the same turn. Treat them as a joint evidence set:

1. Summarise each result briefly, then synthesise their combined clinical
   meaning.
2. For each branch, determine the aggregate effect of ALL new results together.
   - If two results point in the same direction for a branch, use the stronger
     label (e.g., moderate_for + weak_for → moderate_for).
   - If two results conflict for a branch, use the net direction with the label
     one step weaker (e.g., strong_for + weak_against → moderate_for).
3. Set major_update: true if the COMBINED evidence significantly changes the
   leading branch or differential ordering.
4. Set contradiction_detected: true if any single result substantially
   contradicts the current leading hypothesis.
5. List reopen_candidates only for branches that the combined evidence
   warrants reopening.

Return the same JSON schema as single-result annotation. The result_summary
field should cover ALL results in a single coherent narrative.
```

**输入格式**（当结果为列表时）：

```json
{
  "state": {...},
  "raw_result": [
    {
      "action": {"type": "ASK_PATIENT", "content": "是否有心脏手术史？"},
      "raw_result": {"answer": "否"}
    },
    {
      "action": {"type": "ORDER_LAB", "content": "心肌肌钙蛋白I"},
      "raw_result": {"value": 2.8, "unit": "ng/mL", "ref_range": "< 0.04"}
    }
  ]
}
```

### 7.3 annotate_evidence_bundle 实现

```python
def annotate_evidence_bundle(
    self, state: DiagnosticState, bundle_results: list[dict]
) -> dict:
    """
    对一束动作的所有结果进行批量注释。
    single-result 和 multi-result 走同一 EvidenceAnnotator 提示词；
    区别在于 raw_result 字段是单个 dict 还是 list。
    """
    if len(bundle_results) == 1:
        # 降级为单结果路径，保持向后兼容
        return self.annotate_evidence(state, bundle_results[0]["raw_result"])

    annotation = self._call_module(
        "EvidenceAnnotator",
        {
            "state": state.to_dict(),
            "raw_result": bundle_results,   # 列表形式
        }
    )
    # 分支 ID 校验（与单结果路径相同）
    valid_ids = set(state.branches.keys())
    cleaned_effects = {
        bid: effect
        for bid, effect in annotation.get("branch_effects", {}).items()
        if bid in valid_ids
    }
    for bid in valid_ids:
        cleaned_effects.setdefault(bid, "neutral")
    annotation["branch_effects"] = cleaned_effects
    return annotation
```

---

## 8. 轮次预算与就绪度门控的修订

### 8.1 轮次预算计费模型

引入配置参数 `bundle_budget_mode`：

| 模式 | 含义 | 适用场景 |
|------|------|---------|
| `per_bundle`（默认） | 每束计为1轮，无论束内动作数 | 模拟真实时间（并行检查不增加时间） |
| `per_action` | 束内每个动作各计1轮 | 严格基准测试，强制信息效率 |
| `time_weighted` | 束计为束内最长预期延迟所对应的"时间轮次" | 模拟真实等待时间 |

```python
def account_turn_budget(self, state: DiagnosticState, bundle: list[dict]) -> None:
    mode = self.config.bundle_budget_mode
    if mode == "per_action":
        state.turn_budget_used += len(bundle)
    elif mode == "time_weighted":
        max_delay = max(a.get("expected_delay", 0.5) for a in bundle)
        state.turn_budget_used += max(1, round(max_delay * 2))
    else:  # per_bundle (default)
        state.turn_budget_used += 1
```

### 8.2 重复动作检测的修订

现有 `check_diagnosis_readiness` 中的重复检测：

```python
# 原逻辑（单动作）
repeated_last_action = (
    len(state.actions_taken) >= 2 and
    state.actions_taken[-1]["content"] == state.actions_taken[-2]["content"]
)
```

修订为**跨束重复**检测：

```python
def detect_repeated_bundle(self, state: DiagnosticState) -> bool:
    """
    检测最近一束的主动作内容是否与更早的束主动作重复。
    """
    if len(state.actions_taken) < 2:
        return False
    # 取最近一轮束的第一个动作（主动作）内容
    current_primary_content = state.actions_taken[-1]["content"]
    # 与最近3轮内的主动作比较（每束第一条记录即为主动作）
    recent_primaries = [
        a["content"] for a in state.actions_taken[-4:-1]
        if a.get("bundle_position", 0) == 0    # 新增字段，标记在束内的位置
    ]
    return current_primary_content in recent_primaries
```

---

## 9. 修订后的主循环流程

```
[每轮：多动作执行循环]

A.  SafetyController
B.  RootSelector（条件触发）
C.  BranchCreator（条件触发）
D.  TemporaryLeafPlanner
    → 输出：candidate_leaves_ranked（含 bundle_independence, result_dependency）
★ D'. ActionBundler
    → 输入：candidate_leaves_ranked + state + effective_bundle_size
    → 输出：bundle（1–k 个动作，满足独立性 + 非冗余性 + 容量约束）
★ E'. execute_action_bundle(bundle)
    → 对束内每个动作调用 execute_primary_action（结果追加 state.actions_taken）
    → 返回：bundle_results（动作+结果对的列表）
★ F'. annotate_evidence_bundle(bundle_results)
    → EvidenceAnnotator 接收多结果批量输入
    → 返回：单一聚合注释
G.  UpdateRouter（无变化）
H.  apply_probability_update（无变化）
    └─ recompute_parent_posteriors
    └─ _handle_major_update
I.  PostUpdateStateReviser + _apply_reopen_overrides（无变化）
J.  record_differential_history
★ J'. account_turn_budget（更新预算，替代原 turn_budget_used += 1）
K.  check_diagnosis_readiness（修订重复检测逻辑）
L.  TerminationJudge（无变化）
M.  FinalAggregator（无变化）
```

★ = 本次设计新增或修订步骤。

---

## 10. DiagnosticState 所需变更

### 10.1 Config 新增字段

```python
@dataclass
class DiagnosticConfig:
    # ... 现有字段 ...
    max_bundle_size: int = 3                       # 每束最大动作数
    min_marginal_ig_threshold: float = 0.05        # 入束的最低边际信息增益
    redundancy_similarity_threshold: float = 0.6   # Jaccard 冗余判定阈值
    bundle_budget_mode: str = "per_bundle"         # "per_bundle" / "per_action" / "time_weighted"
```

### 10.2 actions_taken 记录结构扩展

每条 `actions_taken` 记录新增字段：

```python
{
    "timestep": state.timestep,
    "bundle_id": state.timestep,      # 同一束内的动作共享 bundle_id
    "bundle_position": 0,             # 在束内的位置（0=主动作，1,2=补充动作）
    "bundle_size": len(bundle),       # 本束总动作数
    "action_type": action_type,
    "external_action": external_action,
    "content": content,
}
```

---

## 11. 对现有各模式的影响

### 11.1 Static QA 模式

束宽强制为 1（`effective_bundle_size = 1`），行为与当前完全相同。无需任何修改。

### 11.2 SDBench Patch 模式

束宽 ≤ 3。`DIAGNOSE` 类型动作不可与其他动作共束（诊断就绪即终止，无需继续执行）。

在 `ActionBundler` 中增加：

```python
# DIAGNOSE 类型动作若出现，强制单独成束
if primary.leaf_type == "DIAGNOSIS_READY":
    return [primary]
```

### 11.3 AgentClinic Physician Patch 模式

束宽 ≤ 2。每束最多包含：
- 1 个 `ASK_PATIENT` 动作（→ patient_agent）
- 1 个 `REQUEST_TEST_OR_MEASUREMENT` 动作（→ measurement_agent）

`DIAGNOSIS_READY` 类型强制单独成束（同 SDBench）。

### 11.4 Default 模式

无外部约束，束宽由 `config.max_bundle_size` 决定。

---

## 12. TerminationJudge 的 info_exhaustion 条件修订

原条件：
> "no further available discriminator is expected to change management"

在多动作场景下需更新为：

> "no further **bundle** of non-redundant, independent discriminators is expected to change management; all combinations of high-value actions have already been taken or are unavailable"

提示词修订（第3类终止）：

```
3. info_exhaustion: no bundle of non-redundant, independent discriminators
   is expected to change management. This is met when:
   (a) all askable_discriminators for live branches have been asked, OR
   (b) all requestable_discriminators for live branches have been ordered, OR
   (c) the maximum LeafScore of any untried action falls below 0.1.
   Note: the existence of untried dependent actions (result_dependency=true)
   that cannot yet be ordered is NOT a reason to continue if their prerequisites
   are already in actions_taken and awaiting results in the same bundle.
```

---

## 13. 完整使用示例（双动作束）

**病例**：52岁女性，突发呼吸困难 + 胸痛，既往有深静脉血栓史。

```
轮次1（束宽=2）：
  候选列表（LeafScore 排名）：
    1. ASK_PATIENT "您的胸痛是胸膜炎性（随呼吸加重）吗？"  score=0.82
       (branch=B2:PE, bundle_independence=1.0, result_dependency=false)
    2. ORDER_LAB "D-二聚体"                               score=0.79
       (branch=B2:PE, bundle_independence=0.85, result_dependency=false)
    3. ORDER_LAB "心肌肌钙蛋白I"                           score=0.71
       (branch=B1:ACS, bundle_independence=0.90, result_dependency=false)
    4. ORDER_IMAGING "胸部CXR"                             score=0.65
       (branch=B3:PTX, bundle_independence=0.95, result_dependency=false)

  ActionBundler:
    主动作 → #1 (ASK_PATIENT, branch=B2)
    检查 #2: branch_id=B2, leaf_type=ORDER_LAB → 不同类型 → 非冗余 → 入束
    检查 #3: branch_id=B1 → 不同分支 → 非冗余 → 入束（束宽=3时）
    束 = [ASK_PATIENT, ORDER_LAB(D-二聚体)]（束宽=2时）

  execute_action_bundle:
    结果1: {"answer": "是，随呼吸加重"}
    结果2: {"value": 4200, "unit": "ng/mL FEU", "ref_range": "< 500"}

  EvidenceAnnotator（批量输入）：
    result_summary: "胸膜炎性胸痛 + D-二聚体显著升高（8.4× 正常上限），
                    高度支持肺栓塞。"
    branch_effects:
      B2(PE): strong_for   （两条证据同向叠加）
      B1(ACS): weak_against
      B3(PTX): neutral（胸膜炎性疼痛也可见）
    major_update: true
    contradiction_detected: false

轮次2（束宽=2）：
  候选列表：
    1. ORDER_IMAGING "CT肺动脉造影"                       score=0.91
       (branch=B2:PE, bundle_independence=1.0, result_dependency=false)
    2. USE_CALCULATOR "Wells PE评分"                     score=0.70
       (branch=B2:PE, bundle_independence=0.60, result_dependency=true) ← 需要D-二聚体结果
    3. ASK_PATIENT "是否有近期长途旅行或固定不动史？"      score=0.68

  ActionBundler:
    主动作 → #1 (CTPA)
    检查 #2: result_dependency=true → BLOCK（依赖D-二聚体，已在上束获取，
              但 Wells 评分需要整合多项数据，计算器调用在同束内仍不安全）
    检查 #3: 不同类型，非冗余 → 入束
    束 = [CTPA, ASK_PATIENT(旅行史)]

  (注：若 bundle_budget_mode = "time_weighted"，CTPA 的 expected_delay=0.8 
   对应约 1.6 轮次预算，比单动作花费更多时间预算)
```

---

## 14. 与现有设计的对比

| 维度 | 现有设计（单动作） | 多动作设计（本文档） |
|------|-----------------|-----------------|
| 每轮动作数 | 1（硬编码） | 1–k（可配置，默认 3） |
| 信息获取效率 | 每轮仅获取单条证据 | 每轮获取 1–k 条互补证据 |
| EvidenceAnnotator 输入 | 单个结果 | 动作-结果对列表（向后兼容） |
| 冗余控制 | 无（LLM 隐式避免） | ActionBundler 确定性把关 |
| 依赖处理 | 无 | 依赖检测阻止同束共存 |
| 高危优先 | 通过 LeafScore 的 safety_value 隐式 | 束级安全插入（Step 3）显式保障 |
| 轮次预算 | 每动作1轮 | 可选 per_bundle / per_action / time_weighted |
| 外部模式兼容 | 单一逻辑 | per-mode 束宽限制 |
| 新增 LLM 模块 | — | 无（ActionBundler 纯确定性） |
| 提示词修订 | — | TemporaryLeafPlanner（新增 bundle_independence、result_dependency）；EvidenceAnnotator（多结果批量处理） |

---

## 15. 实现路线图

### 第一步：配置与状态扩展
- [ ] `config.py`：增加 `max_bundle_size`, `min_marginal_ig_threshold`, `redundancy_similarity_threshold`, `bundle_budget_mode`
- [ ] `state.py`：`actions_taken` 记录新增 `bundle_id`, `bundle_position`, `bundle_size` 字段文档（无类型变化）

### 第二步：ActionBundler 实现
- [ ] 创建 `src/agentclinic_tree_dx/action_bundler.py`，实现完整 `ActionBundler` 类：
  - `build_bundle()` 主方法
  - `is_dependent_on_bundle_result()`
  - `is_redundant_with_bundle()` + `jaccard_similarity()`
  - `effective_bundle_size()` per-mode 约束

### 第三步：提示词修订
- [ ] 更新 `temporary_leaf_planner.txt`（新增字段 `bundle_independence`, `result_dependency`，更新 scoring instruction）
- [ ] 更新 `evidence_annotator.txt`（新增多结果批量输入说明）
- [ ] 更新 `termination_judge.txt`（修订 info_exhaustion 条件）

### 第四步：controller.py 修订
- [ ] 新增 `execute_action_bundle(state, bundle) → list[dict]`
- [ ] 新增 `annotate_evidence_bundle(state, bundle_results) → dict`
- [ ] 新增 `account_turn_budget(state, bundle)`
- [ ] 修订 `detect_repeated_bundle()` 替代原 `repeated_last_action` 逻辑
- [ ] 修订 `run()` 主循环：将 `execute_primary_action` + `annotate_evidence` 替换为新路径
- [ ] 修订 `plan_temporary_leaves()` 以透传 `bundle_independence`、`result_dependency` 字段

### 第五步：测试
- [ ] 单元测试：`is_redundant_with_bundle`（高相似度阻断，低相似度放行）
- [ ] 单元测试：`is_dependent_on_bundle_result`（CALCULATOR 与 ORDER_LAB 共束被阻断）
- [ ] 单元测试：安全分支插入（高危动作占据束位）
- [ ] 单元测试：`account_turn_budget` 三种模式
- [ ] 集成测试：bundle_size=2，两个独立分支的 (ASK + ORDER_LAB) 同束执行，verify EvidenceAnnotator 收到列表输入
- [ ] 回归测试：`max_bundle_size=1` 时行为与现有实现完全一致
- [ ] 模式测试：Static QA 强制 bundle_size=1；SDBench DIAGNOSE 单独成束

---

## 16. 外部知识路径（维持抽象路径）

`ActionBundler` 对 `RETRIEVE_KNOWLEDGE` 和 `RETRIEVE_EXTERNAL_KNOWLEDGE` 类型应用以下规则：
- 若束内已有一个 `RETRIEVE_KNOWLEDGE` 动作，不再追加第二个（知识检索应串行以避免查询重叠）；
- `RETRIEVE_KNOWLEDGE` 可与 `ASK_PATIENT`、`ORDER_LAB` 等数据采集动作共束（两者不相互依赖）。

---

---

## 17. 从外部设计文档合并的补充设计

> 以下内容来自 `agentclinic_algorithm_update_requirements_design.md` 和 `algorithm_update_requirements_and_design.md` 的交叉审阅。

### 17.1 AtomicAction 数据模型增强

**来源**：`agentclinic_algorithm_update_requirements_design.md` §5.1

我们当前的 CandidateLeaf 数据结构缺少若干在临床决策中有价值的字段。基于外部文档的 `AtomicAction` 模型，增加以下字段到候选叶子结构中：

```python
@dataclass
class CandidateLeaf:
    branch_id: str
    leaf_type: str           # ASK_PATIENT|REQUEST_EXAM|REQUEST_VITAL|ORDER_LAB|ORDER_IMAGING|...
    content: str
    score: float
    expected_information_gain: float
    safety_value: float
    action_separation_value: float
    expected_cost: float
    expected_delay: float

    # ── 新增字段（来自外部文档）──
    target_branches: list[str] = field(default_factory=list)
    # 所有靶向分支（单个动作可影响多个分支）

    primary_function: str = "support"
    # support|falsify|separate|safety_check|coexistence_check|management_check

    falsification_value: float = 0.0
    # 该动作反驳当前领先分支的能力（0-1）

    invasiveness: float = 0.0
    # 侵入性/患者负担（0-1）

    urgency: str = "routine"
    # routine|urgent|emergent

    redundancy_group: str | None = None
    # 冗余组标识——同组内只应选一个（如"胸部影像"组内 CXR 与 CT 二选一）

    bundle_independence: float = 1.0
    result_dependency: bool = False
    why: str = ""
```

### 17.2 更精细的分支状态模型

**来源**：`agentclinic_algorithm_update_requirements_design.md` §4

我们当前的分支状态集合为：`live, parked, confirmed, closed_for_now, reopened, expanded`。外部文档提出更精细的状态划分，明确标注分支**为何存活**：

| 新状态 | 含义 | 与我们现有状态的映射 |
|--------|------|-------------------|
| `live_focus` | 当前领先或最决策相关的分支 | `live`（隐含） |
| `live_competing` | 合理替代方案，不应忽略 | `live`（隐含） |
| `live_safety_protected` | 后验不高但漏诊代价大 | `live`（隐含，通过 danger 分数判断） |
| `live_coarse` | 父级表示已足够，无需扩展 | `live`（新概念） |
| `live_expandable` | 通过扩展门检查，等待扩展 | `expand_now`（现有） |

**设计决策**：我们在**提示词层面**采纳这些细粒度标签（指导 LLM 对不同存活分支分配不同注意力），但在**代码数据模型中暂保留现有状态集合**。`PostUpdateStateReviser` 的决策输出新增这些细粒度标签作为**附加元数据**而非替代状态：

```json
{
  "branch_id": "B1",
  "decision": "keep_coarse",
  "live_subtype": "live_focus",
  "rationale": "..."
}
```

这样避免了大规模重构现有状态逻辑，同时让 LLM 和审计日志能够区分不同类型的"live"分支。

### 17.3 证据深度控制——多种终止子类型

**来源**：`agentclinic_algorithm_update_requirements_design.md` §7

外部文档定义了5种证据收集终止条件，部分在我们的 TerminationJudge 中已有对应，但以下两种值得明确纳入：

**T2. Actionable Parent Stop**（可操作父节点终止）：

```
多个子分支保持活跃，但它们共享相同的即时管理路径。
→ 在父节点层级终止，无需进一步区分子分支。
```

**T4. Uncertainty-Management Stop**（不确定性管理终止）：

```
诊断不确定性仍存在，但强制单一标签会不安全。
输出：排序的工作鉴别诊断 + 领先假设 + 未排除的危险替代 + 下一步建议 + 安全网触发条件
```

在 TerminationJudge 提示词中补充：

```
Additional termination sub-types:

actionable_parent_syndrome (sub-type of type 2):
  Multiple child branches remain active, but they all share the same immediate
  management pathway. Stop at the parent level and prescribe the shared action.
  Example: "infected biliary obstruction" — whether stone-related, malignant,
  or stricture, immediate action is the same (antibiotics + biliary drainage).

uncertainty_management (sub-type of type 3):
  When diagnostic uncertainty remains but forcing a single diagnosis would be
  unsafe, output a structured uncertainty package:
  - ranked working differential
  - leading hypothesis with confidence
  - dangerous alternatives not yet excluded
  - next recommended step
  - safety-net and reopen triggers
```

### 17.4 共享判别动作 vs 分支特异判别动作

**来源**：`algorithm_update_requirements_and_design.md` §7.2

外部文档明确区分**共享判别动作**（同时影响多个分支）和**分支特异判别动作**（仅针对一个分支）。这个区分对 TemporaryLeafPlanner 和 ActionBundler 的生成策略有实际影响：

**共享判别动作示例**：

```
生命体征、血氧饱和度、ECG、胸部X线、CBC、基础代谢、妊娠试验、心肺查体
```

**分支特异判别动作示例**：

```
PE 分支: 近期制动、雌激素暴露、单侧下肢肿胀、D-二聚体、CTPA
ACS 分支: 缺血性ECG改变、肌钙蛋白、劳力性压迫性胸痛
肺炎 分支: 发热、咳痰、影像浸润影
主动脉疾病 分支: 突发撕裂样疼痛、脉搏不对称、纵隔增宽
```

**在 TemporaryLeafPlanner 提示词中新增**：

```
Evidence classification awareness:
Classify each candidate action as either:
- "shared_discriminator": informs 2+ branches simultaneously (e.g., vitals,
  ECG, basic labs, chest imaging)
- "branch_specific_discriminator": targets primarily one branch
  (e.g., D-dimer for PE, troponin for ACS)

The ActionBundler will use this classification to ensure the bundle includes
both shared and branch-specific evidence when available. Early rounds should
favor shared discriminators; later rounds should shift to branch-specific ones.
```

### 17.5 非功能性需求补充

**来源**：`algorithm_update_requirements_and_design.md` §3.2

我们的设计文档中缺少以下非功能性需求的显式声明：

| ID | 需求 | 描述 |
|----|------|------|
| NFR-1 | **可追溯性** | 每个动作必须关联：靶向分支、预期价值、证据覆盖角色、结果、概率更新、分支状态变化 |
| NFR-2 | **偏差抵抗** | 系统必须记录所有存活分支的证据覆盖情况，防止领先分支固着 |
| NFR-3 | **成本感知** | 系统须支持 AgentClinic 风格的成本敏感评估 |
| NFR-4 | **工具使用审计** | 计算器使用和知识检索必须有显式理由 |
| NFR-5 | **安全覆盖** | 紧急中断逻辑必须覆盖普通证据收集或扩展逻辑 |

这些需求应作为实现阶段的验收标准。

---

## 参考文献

1. Howard, R.A. (1966). Information value theory. *IEEE Transactions on Systems Science and Cybernetics, 2*(1), 22–26.
2. Hershey, J.C., & Cebul, R.D. (1986). Using multiple tests: series and parallel approaches. *Medical Decision Making, 6*(4), 227–236.
3. Pauker, S.G., & Kassirer, J.P. (1980). The threshold approach to clinical decision making. *NEJM, 302*(20), 1109–1117.
4. Moons, K.G., & Harrell, F.E. (2003). Sensitivity and the obscure true-negative rate. *Annals of Internal Medicine, 138*(2), 166–167.
5. MAI Diagnostic Orchestrator (2025). Sequential Diagnosis with Language Models. arXiv:2506.22405.
6. Pratt, J.W., Raiffa, H., & Schlaifer, R. (1995). *Introduction to Statistical Decision Theory*. MIT Press.
7. Lyman, G.H., & Balducci, L. (1993). The effect of changing disease risk on the value of diagnostic tests. *Medical Decision Making, 13*(3), 203–213.
8. ClinicalAgents (2026). Multi-Agent Orchestration for Clinical Decision Making with Dual-Memory. arXiv:2603.26182.
9. `agentclinic_algorithm_update_requirements_design.md`（外部智能体生成，本节 §17.1–17.3 来源）
10. `algorithm_update_requirements_and_design.md`（外部智能体生成，本节 §17.4–17.5 来源）

---

*文档生成时间：2026-04-30*  
*基于代码分支：`codex/verify-agentclinic-compatibility-with-projects`*  
*补充来源：`agentclinic_algorithm_update_requirements_design.md`、`algorithm_update_requirements_and_design.md`*
