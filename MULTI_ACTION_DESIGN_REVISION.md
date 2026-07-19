# 每轮多动作设计修正备忘录

> **类型**：对 `MULTI_ACTION_PER_TURN_DESIGN.md`（v1.0）的修正  
> **版本**：v1.1  
> **修正原因**：原设计存在两处根本性错误，本文档予以纠正并给出替代方案

---

## 一、两处根本性错误的识别

### 错误1：基于模式的束宽限制缺乏依据

原设计第6节"环境兼容层"制定了如下规则：

> AgentClinic Patch ≤ 2；SDBench ≤ 3；Static QA = 1

**错误原因**：查阅适配器源码，接口层面**不存在任何调用次数约束**：

```python
# agentclinic_env.py — ask_patient / request_test_or_measurement 均为普通方法调用，无限制
def ask_patient(self, content: str) -> dict:
    result = self.patient_agent.answer_question(content)
    return result if isinstance(result, dict) else {"patient_answer": result}

# sdbench_env.py — ask_gatekeeper / request_test 同样可重复调用
def ask_gatekeeper(self, question: str) -> dict:
    result = self.gatekeeper.ask(question)
    return result if isinstance(result, dict) else {"answer": result}
```

`patient_agent`、`tester_agent`、`gatekeeper` 均为外部 Python 对象，对调用频次无任何机制约束。

上述限制不是工程约束，不是数据集规定，而是**完全人为设定**，不应出现在算法规格中。

---

### 错误2：LeafScore 贪心选取导致确认偏差

原设计的 `ActionBundler` 以主动作为起点，用贪心方式补充次级候选，实质上倾向于**持续强化当前领先分支**——因为领先分支的候选动作天然具有更高的 `LeafScore`（`safety_value` 更高，`action_separation_value` 更高）。

**文献依据**：

> *"确认偏差是临床推理中最常见的认知偏误。进行验证性信息检索（寻找支持初始诊断的证据）的临床医生比使用反驳性或均衡策略的临床医生，作出错误诊断的概率显著更高。"*  
> — Mendel et al. (2011), *Confirmation Bias: Why Psychiatrists Stick to Wrong Preliminary Diagnoses*, Psychological Medicine

> *"积极开放思维（AOT）风格——主动寻找反驳既有信念的证据——与更全面的检查过程和更多被考虑的鉴别诊断数量相关。"*  
> — Ramos et al. (2022), *Active Open-Minded Thinking and Diagnostic Reasoning*, PMC

当算法总是把最多预算分配给领先分支时，**领先分支的后验在每轮都被持续强化**，而竞争分支得不到充分探索，最终形成一个自我强化的错误路径：

```
轮次1: B1(后验0.55) → 为 B1 选最高分动作 → B1后验升至0.70
轮次2: B1(后验0.70) → 仍为 B1 选最高分动作 → B1后验升至0.82
轮次3: TerminationJudge: B1 posterior=0.82 ≥ 0.75 → 终止
→ B2、B3 从未被充分探索，即使其中一个才是真正诊断
```

---

## 二、修正方案

### 2.1 废除基于模式的束宽限制

不再设置任何模式特有的束宽上限。束大小由以下**内容驱动因素**决定：

1. 当前前沿（`state.frontier`）中的存活分支数量；
2. 每个存活分支的可用且尚未执行的高价值判别动作数量；
3. 信息价值阈值（`min_marginal_ig_threshold`）。

**唯一保留的结构性约束**：
- `DIAGNOSIS_READY` 类型动作（代表诊断就绪）**不可与任何其他动作共束**；该类型一旦出现于候选列表首位，则束退化为单动作束，立即终止本轮其余步骤。这不是因为外部环境限制，而是因为"宣布诊断"是一个**状态转移终止动作**，与信息采集动作语义不相容。

```python
def build_bundle(self, candidate_leaves, state, config):
    if candidate_leaves[0].leaf_type == "DIAGNOSIS_READY":
        return [candidate_leaves[0]]   # 终止动作单独成束
    # ... 正常束构建 ...
```

### 2.2 以"前沿覆盖束"替代"贪心补充束"

**核心原则**：每个存活分支（`state.frontier` 中的每个分支 ID）必须在束内拥有至少一个代表动作，除非该分支已无可用的高价值判别动作。

**新算法名称**：`FrontierCoverageBundler`（替换原 `ActionBundler`）

---

## 三、FrontierCoverageBundler 完整算法

```
FrontierCoverageBundler(candidate_leaves, state, config) → bundle: list[Action]

─── 前置检查 ──────────────────────────────────────────────────────────────
  if candidate_leaves[0].leaf_type == "DIAGNOSIS_READY":
    return [candidate_leaves[0]]   # 终止动作立即返回


─── Phase 1：强制分支覆盖（Mandatory Branch Coverage）────────────────────
  # 目标：为 frontier 中每个存活分支选出一个代表动作

  covered = {}             # branch_id → selected CandidateLeaf
  bundle = []
  bundle_content_set = set()

  for branch_id in state.frontier:
    branch = state.branches.get(branch_id)
    if branch is None or branch.status not in {"live", "reopened"}:
      continue

    # 在候选列表中，按 LeafScore 从高到低找到该分支的第一个合格动作
    for candidate in candidate_leaves:
      if candidate.branch_id != branch_id:
        continue

      # 约束A：依赖性门（同原设计，CALCULATOR 等不与数据采集动作共束）
      if is_dependent_on_bundle_result(candidate, bundle):
        continue

      # 约束B：冗余性门（内容 Jaccard 相似度 > threshold 则跳过）
      if is_redundant_with_bundle(candidate, bundle, bundle_content_set,
                                  config.redundancy_similarity_threshold):
        continue

      # 约束C：最低信息增益门
      if candidate.expected_information_gain < config.min_marginal_ig_threshold:
        break   # 该分支剩余候选按降序排列，后续更低，直接跳过该分支

      # 选中：此动作成为该分支的代表
      covered[branch_id] = candidate
      bundle.append(candidate)
      bundle_content_set.add(normalize_content(candidate.content))
      break   # 每分支只选一个代表动作


─── Phase 2：跨分支高价值补充（Optional Cross-Branch Supplement）──────────
  # 目标：添加 action_separation_value 高（能同时区分多个分支）的额外动作
  # 注意：此阶段是可选的，不强制执行

  for candidate in sorted(candidate_leaves, key=lambda x: -x.action_separation_value):
    if candidate in bundle:
      continue
    if candidate.action_separation_value < config.min_separation_value_for_supplement:
      break   # 降序排列，后续更低，提前退出

    # 同样须通过三个约束门
    if is_dependent_on_bundle_result(candidate, bundle):
      continue
    if is_redundant_with_bundle(candidate, bundle, bundle_content_set,
                                config.redundancy_similarity_threshold):
      continue
    if candidate.expected_information_gain < config.min_marginal_ig_threshold:
      continue

    bundle.append(candidate)
    bundle_content_set.add(normalize_content(candidate.content))


─── Phase 3：束内排序（按预期延迟升序）─────────────────────────────────
  bundle.sort(key=lambda a: a.expected_delay)

return bundle
```

### 算法说明

**Phase 1 的"强制覆盖"语义**：

覆盖失败（该分支无合格动作）的合理原因只有两种：
1. **信息耗尽**：该分支的所有判别动作已在 `actions_taken` 中（这意味着这个分支的探索已经完整，`TerminationJudge` 应将其标记为 `info_exhaustion`）；
2. **无价值判别动作**：该分支的所有候选动作信息增益均低于 `min_marginal_ig_threshold`（说明该分支的后验变化对当前状态影响可忽略，`PostUpdateStateReviser` 应将其 `park`）。

**Phase 2 的"补充"语义**：

跨分支判别动作（`action_separation_value` 高）能以一次动作同时影响多个分支的后验，是信息效率最高的动作类型。例如：
- "患者是否有注射毒品史？" 能同时对"感染性心内膜炎（B1↑）""HIV相关心肌病（B2↑）""普通心力衰竭（B3 neutral）"产生区分效果。

此类动作在 Phase 1 可能因为"不属于任何单一分支代表"而未被选入，Phase 2 给予补充机会。

---

## 四、修订后的 Config 参数

删除 `max_bundle_size`（人为上限），替换为以下参数：

```python
@dataclass
class DiagnosticConfig:
    # ... 现有字段 ...
    
    # ── 多动作束参数（替换 max_bundle_size）──
    min_marginal_ig_threshold: float = 0.05
    # 入束的最低预期信息增益（适用于 Phase 1 和 Phase 2）
    
    min_separation_value_for_supplement: float = 0.50
    # Phase 2 补充动作的最低跨分支区分度阈值
    
    redundancy_similarity_threshold: float = 0.60
    # Jaccard 冗余判定阈值（内容字符串）
    
    bundle_budget_mode: str = "per_bundle"
    # "per_bundle" / "per_action" / "time_weighted"
    
    # 废除的参数（不再使用）：
    # max_bundle_size: int  ← 删除
```

**理论上的束大小范围**：
- 最小：1（所有分支均无合格动作，仅保留主动作；或进入终止动作路径）
- 最大：`len(state.frontier) + N_supplement`，其中 N_supplement 取决于 Phase 2 补充动作数

在典型的 2–4 个存活分支场景下，实际束大小约为 2–5 个动作，与临床常见的并行检查规模一致。

---

## 五、对 TemporaryLeafPlanner 提示词的修订

在原版本基础上，将以下说明替换为：

**删除**（原第4条）：
> "Select exactly one primary action: the highest-scoring globally ranked candidate."

**替换为**：
```
4. Generate a sufficient diversity of candidates to cover ALL live branches in
   the current frontier. Specifically:
   - For each live branch in state.frontier, include at least one candidate
     discriminator that targets that branch specifically.
   - Do NOT concentrate all high-scoring candidates on the leading branch alone.
     The controller's ActionBundler will enforce branch-level coverage; your
     role is to ensure that per-branch candidates of adequate quality exist.
   - Rank candidates globally by LeafScore; the ActionBundler will select
     representatives per branch from this ranked list.

5. Do not propose an action with identical content to one already in the
   actions_taken history.

6. For each candidate, assess its bundle_independence and result_dependency:
   - bundle_independence: 1.0 = fully independent diagnostic target relative
     to other candidates in the list; 0.0 = redundant with a higher-ranked
     candidate.
   - result_dependency: true if this action logically requires the result of
     another action in this candidate list to be meaningful (e.g., a
     calculator call that needs a lab value not yet obtained).
```

**selected_primary_action 字段保留**（代表 Phase 1 中主分支代表动作），但语义从"全局最优单动作"变为"领先分支的代表动作"。

---

## 六、对 EvidenceAnnotator 提示词的补充说明

在多动作束场景下，`EvidenceAnnotator` 对**所有分支**的注释（包括非领先分支）至关重要。新增说明：

```
Cross-branch annotation requirement:
When raw_result is a list of results from different branches, ensure that
branch_effects includes annotations for EVERY live branch—not just the branch
that the primary action targeted.

This is critical to prevent confirmation bias: even if a result primarily
supports branch B1, you must still assess and report its effect on B2, B3, etc.
A result that is "neutral" for B2 is still informative (it means B2 remains
unaffected by this evidence). Do NOT leave any live branch without an effect
annotation.
```

---

## 七、与原设计的差异对照

| 维度 | v1.0（原设计） | v1.1（本修正） |
|------|--------------|--------------|
| 束宽限制依据 | 模式特定（人为） | 信息价值 + 前沿覆盖（内容驱动） |
| 束构建策略 | 贪心补充（主动作 + 次级填充） | 强制分支覆盖（Frontier Coverage） |
| 确认偏差风险 | 高（贪心偏向领先分支） | 低（每分支强制一个代表动作） |
| 模式束宽配置 | AgentClinic ≤ 2; SDBench ≤ 3; Static QA = 1 | 无模式约束（统一算法） |
| 唯一结构约束 | 模式级别硬限制 | DIAGNOSIS_READY 动作单独成束 |
| Config 参数 | `max_bundle_size` + 其余阈值 | 删除 `max_bundle_size`；新增 `min_separation_value_for_supplement` |
| 跨分支补充 | Phase 2 贪心（评分驱动） | Phase 2 高区分度优先（`action_separation_value`） |
| 最小束大小 | 1（主动作） | 1（终止动作或信息耗尽时） |

---

## 八、关于 Static QA 模式的特殊说明

Static QA 模式的信息结构与对话式模式有本质区别：题干已完整呈现所有信息，动作类型为 `ANALYZE_VIGNETTE` / `SELECT_OPTION`，不存在外部环境的"并行问询"概念。

但 `FrontierCoverageBundler` 在 Static QA 下仍然成立：
- 每个存活分支对应的 `ANALYZE_VIGNETTE` 动作内容不同（分析题干时关注不同的关键特征集合）；
- 强制为每个分支生成一个分析角度，有助于避免只从"领先诊断"视角分析题干；
- 实际束大小取决于候选列表中有多少个不冗余的分析角度。

因此 Static QA 模式**不需要**任何束宽特殊处理，`FrontierCoverageBundler` 统一适用。

---

## 九、更新后的实现路线图

删除原路线图中"第一步"里 `max_bundle_size` 的引入，以及所有 per-mode 束宽限制的相关代码。

**新增**：
- `config.py`：用 `min_separation_value_for_supplement` 替换 `max_bundle_size`
- `action_bundler.py`：实现类名改为 `FrontierCoverageBundler`，Phase 1 逻辑完全重写
- `temporary_leaf_planner.txt`：更新第4条指令（覆盖所有存活分支）
- `evidence_annotator.txt`：新增跨分支注释要求说明

其余实现步骤（controller.py 修订、budget 模型、测试）与原路线图一致，不变。

---

---

## 十、从外部设计文档合并的补充设计

> 以下内容来自 `agentclinic_algorithm_update_requirements_design.md` 和 `algorithm_update_requirements_and_design.md`（其他智能体助手生成）的交叉审阅，识别出本设计遗漏但具有独立价值的设计要素。

### 10.1 FalsificationValue——反驳价值（重要遗漏）

**问题**：我们的 `LeafScore` 公式为：

```
LeafScore(L) = ExpectedInformationGain + SafetyValue + ActionSeparationValue
             - CostPenalty - DelayPenalty
```

该公式**没有独立项来量化一个动作"反驳领先分支"的能力**。外部文档明确指出这是反确认偏差的核心机制：

> *"FalsificationValue: how much the action could disconfirm the current leading branch."*
> — `agentclinic_algorithm_update_requirements_design.md` §5.2

**修正**：在 LeafScore 公式中新增 `FalsificationValue` 分量：

```
LeafScore(L) = ExpectedInformationGain(L)
             + SafetyValue(L)
             + ActionSeparationValue(L)
             + FalsificationValue(L)         ← 新增
             - CostPenalty(L)
             - DelayPenalty(L)
             - InvasivenessPenalty(L)         ← 新增（来自外部文档）
```

**FalsificationValue 语义**（0–1）：该动作若结果为阴性/不符合预期，能多大程度上降低当前领先分支的后验。例如：
- 对"PE"领先分支执行 D-二聚体：若阴性则 PE 基本排除 → FalsificationValue 高；
- 对"PE"领先分支询问"是否有胸痛"：无论回答如何都不能有效排除 PE → FalsificationValue 低。

**提示词中新增字段**（每个候选叶子）：

```json
{
  "falsification_value": 0.0,
  "invasiveness": 0.0
}
```

### 10.2 target_branches 替换单一 branch_id

**问题**：当前 `CandidateLeaf` 使用单一 `branch_id: str`，暗示每个动作只为一个分支服务。但现实中许多动作同时影响多个分支（如生命体征检查影响所有分支，ECG 同时影响 ACS、PE、心包炎）。

**修正**：

```python
# 原始
@dataclass
class CandidateLeaf:
    branch_id: str          # 单一靶向
    ...

# 修订
@dataclass
class CandidateLeaf:
    branch_id: str          # 保留：主靶向分支（向后兼容）
    target_branches: list[str] = field(default_factory=list)  # 新增：所有靶向分支
    ...
```

- `branch_id` 保留用于向后兼容和 Phase 1 的分支代表选取；
- `target_branches` 用于计算 `action_separation_value` 和 Phase 2 的跨分支补充。

### 10.3 primary_function 枚举——结构化动作意图

**来源**：`agentclinic_algorithm_update_requirements_design.md` §5.1

每个候选动作增加一个结构化的功能标注：

```python
primary_function: str  # 取值之一：
# "support"             — 该动作预期支持其靶向分支
# "falsify"             — 该动作预期反驳其靶向分支
# "separate"            — 该动作区分两个或更多竞争分支
# "safety_check"        — 该动作保护高危分支不被遗漏
# "coexistence_check"   — 该动作评估多个诊断共存的可能性
# "management_check"    — 该动作确认管理路径而非诊断本身
```

**在 FrontierCoverageBundler 中的应用**：

Phase 1 选出的代表动作中，应确保**至少一个动作的 `primary_function` 为 `"falsify"`**（当存在后验 ≥ 0.5 的领先分支时）：

```
# Phase 1 后追加：领先分支反驳检查
if leading_branch.posterior >= 0.5:
    if not any(a.primary_function == "falsify"
               and leading_branch.id in a.target_branches
               for a in bundle):
        # 从候选列表中寻找一个针对领先分支的 falsify 动作
        falsifier = next(
            (c for c in candidate_leaves
             if c.primary_function == "falsify"
             and leading_branch.id in c.target_branches
             and c not in bundle
             and not is_redundant_with_bundle(c, bundle, ...)),
            None
        )
        if falsifier:
            bundle.append(falsifier)
```

### 10.4 显式分支覆盖审计映射

**来源**：`agentclinic_algorithm_update_requirements_design.md` §6

`FrontierCoverageBundler` 的返回值应包含一个**分支覆盖审计映射**，记录每个存活分支的覆盖状态和延迟原因：

```json
{
  "bundle": [...],
  "branch_coverage": {
    "B1": {
      "status": "covered",
      "selected_actions": ["A1", "A3"],
      "coverage_mode": "direct"
    },
    "B2": {
      "status": "covered",
      "selected_actions": ["A2"],
      "coverage_mode": "safety_sentinel"
    },
    "B3": {
      "status": "deferred",
      "selected_actions": [],
      "deferral_reason": "posterior 0.02 below testing threshold; parked with reopen trigger: fever > 38.5°C"
    }
  }
}
```

**覆盖模式**（来源：`algorithm_update_requirements_and_design.md` FR-3）：

| 模式 | 含义 |
|------|------|
| `direct` | 为该分支选择了专门的判别动作 |
| `shared` | 该分支被一个跨分支判别动作间接覆盖 |
| `safety_sentinel` | 该分支通过安全哨兵动作监测 |
| `already_covered` | 该分支已在本轮或近轮内被充分覆盖 |
| `justified_deferral` | 合理延迟，附原因 |

此映射写入 `state.actions_taken` 的同一束记录中，便于后续可追溯性审计（NFR-1, NFR-2）。

### 10.5 Coverage Debt Penalty——覆盖债务惩罚

**来源**：`algorithm_update_requirements_and_design.md` §8.3

```
if exists branch with coverage_status == not_covered:
    penalize additional evidence for already-covered leading branch
```

在 `FrontierCoverageBundler` 的 Phase 2 中具体化：

```python
# Phase 2 修订：若 Phase 1 后仍有未覆盖的存活分支，
# 则 Phase 2 优先填充这些分支的候选动作，而非为已覆盖分支追加补充动作
uncovered_branches = [
    bid for bid in state.frontier
    if bid not in covered and state.branches[bid].status in {"live", "reopened"}
]
if uncovered_branches:
    # 优先用 Phase 2 预算填补覆盖债务
    for bid in uncovered_branches:
        for candidate in candidate_leaves:
            if bid in candidate.target_branches and candidate not in bundle:
                if passes_all_gates(candidate, bundle, config):
                    bundle.append(candidate)
                    covered[bid] = candidate
                    break
```

### 10.6 Bundle Types 分类法

**来源**：`agentclinic_algorithm_update_requirements_design.md` §5.5

不同临床阶段对束的组成有不同预期。此分类法作为**提示词指导**（非硬约束）提供给 TemporaryLeafPlanner：

| 束类型 | 适用时机 | 典型组成 |
|--------|---------|---------|
| **病史束** | 信息稀疏的早期阶段 | 起病/时间线、症状性质、伴随症状、暴露/风险、药物、既往史 |
| **生命体征+查体束** | 多数急性病例早期 | HR/BP/RR/SpO2/T + 重点心肺/腹部/神经系统查体 |
| **基础实验室束** | 需广泛系统鉴别时 | CBC、CMP、（妊娠试验）、（尿液分析） |
| **分支特异束** | 特定分支成为主导时 | PE 评估束（D-dimer + CTPA）、ACS 评估束（ECG + troponin）等 |
| **紧急束** | 安全中断触发时 | 稳定化动作 + 紧急监测 + 紧急实验室 + 时间敏感治疗 |

提示词中新增（TemporaryLeafPlanner）：

```
Bundle phase awareness:
When generating candidates, consider the current diagnostic phase:
- Early (timestep 1-2): prefer history questions + vitals + exam (broad coverage)
- Mid (timestep 3-5): prefer branch-specific labs, imaging, calculators
- Late (timestep 6+): prefer confirmatory or falsifying tests for leading branches
Candidates should reflect the appropriate phase, not merely the branch
with the highest posterior.
```

### 10.7 CorrelatedEvidenceGrouper——关联证据分组

**来源**：`agentclinic_algorithm_update_requirements_design.md` §14.4

**问题**：当一束内包含多个对同一分支产生同向效果的动作时（如"肌钙蛋白升高" + "ECG 缺血性改变"均支持 ACS），简单的乘性更新会**重复计算**关联证据的效果——因为两项检查的诊断信息并非完全独立。

**修正**：在 `apply_probability_update` 之前增加 `CorrelatedEvidenceGrouper`：

```python
def group_correlated_evidence(annotation: dict, state: DiagnosticState) -> dict:
    """
    对 branch_effects 中的关联证据应用衰减因子。
    当同一束内多个动作对同一分支产生同向强效应时，
    后续同向效应的权重衰减。
    """
    effects = annotation["branch_effects"]
    # 统计每个分支收到的同向强效应计数
    for bid, effect in effects.items():
        if bid not in state.branches:
            continue
        # 若该分支在本束内已有 strong_for/strong_against，
        # 后续同向效应降级一档（strong → moderate）
        # 具体实现在 ordinal_update 的权重表中用衰减因子
        pass  # 详细实现见代码阶段
    return annotation
```

此模块为纯确定性逻辑，不调用 LLM。

---

## 参考文献（补充）

- Mendel R. et al. (2011). Confirmation bias: why psychiatrists stick to wrong preliminary diagnoses. *Psychological Medicine, 41*(12), 2651–2659.
- Ramos V. et al. (2022). Active open-minded thinking and diagnostic reasoning. PMC9755454.
- Peirce C.S. (1878). Deduction, induction, and hypothesis. *Popular Science Monthly, 13*, 470–482. （反驳性推理的哲学基础）
- Wason P.C. (1960). On the failure to eliminate hypotheses in a conceptual task. *Quarterly Journal of Experimental Psychology, 12*(3), 129–140. （"四卡任务"：验证性偏差的经典实验）
- `agentclinic_algorithm_update_requirements_design.md`（外部智能体生成，本节 §10.1–10.7 来源）
- `algorithm_update_requirements_and_design.md`（外部智能体生成，本节 §10.4–10.5 来源）

---

*文档生成时间：2026-04-30*  
*修正对象：`MULTI_ACTION_PER_TURN_DESIGN.md` v1.0 §4、§5、§6*  
*补充来源：`agentclinic_algorithm_update_requirements_design.md`、`algorithm_update_requirements_and_design.md`*
