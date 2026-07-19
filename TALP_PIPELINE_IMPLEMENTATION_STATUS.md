# Static QA 模式 TALP 流水线实现状态

> **生成时间**: 2026-05-19  
> **关联日志**: `logs/smoke_test_20260519_no_delib.log`（Case #68, CML, 无审议循环）  
> **关联代码**: `src/agentclinic_tree_dx/controller.py`

---

## 一、当前执行流程概览

审议循环（Hypothesis → EvidenceAllocator → Challenger → ReasoningEconomyAuditor → Checklist → Consensus）已在 `controller.py` 中关闭。当前 `static_diagnosis_qa` 模式的每一轮执行流程如下：

```
[一次性初始化] VignetteParser ── 仅 timestep == 1
     │
     ▼
┌─── Turn N 开始 ───────────────────────────────────────────────┐
│                                                                 │
│ A.  SafetyController                                            │
│ B.  RootSelector（仅当 root 为空或 root_revision_needed）      │
│ C.  BranchCreator（仅当无分支或根节点变更）                    │
│                                                                 │
│ D-pre. JIT Expansion（若存在 action_requires_children 的分支）  │
│        └─ recompute_parent_posteriors                           │
│                                                                 │
│ D.  TemporaryAnalyticLeafPlanner (TALP)                        │
│     └─ 返回 candidate_leaves_ranked + selected_primary_action   │
│                                                                 │
│ D'. FrontierCoverageBundler                                     │
│     └─ Phase 0/1/1.5/2/3 → bundle（确定性算法，非 LLM）       │
│     └─ fallback: 若 bundle 为空 → 用 selected_action 包装      │
│                                                                 │
│ E'. execute_action_bundle                                       │
│     └─ 逐个执行 bundle 中的动作（static QA: ANALYZE_VIGNETTE） │
│     └─ 每个动作追加 record 到 state.actions_taken               │
│                                                                 │
│ F'. EvidenceAnnotator                                           │
│     └─ 单个或批量标注，产出 branch_effects + result_summary     │
│                                                                 │
│ G.  group_correlated_evidence（确定性降级）                     │
│ G'. apply_probability_update（ordinal / rule_based / calculator）│
│                                                                 │
│ H.  recompute_parent_posteriors（扩展后的父聚合）               │
│                                                                 │
│ I.  PostUpdateStateReviser                                      │
│     └─ branch_decisions: confirm/close/park/reopen/expand_now   │
│                                                                 │
│ J.  ExpansionGate + SubBranchCreator（条件触发）                │
│     └─ recompute_parent_posteriors                              │
│     └─ update_frontier_after_expansion                          │
│                                                                 │
│ J'. _apply_reopen_overrides（确定性分支重开）                   │
│     record_differential_history                                 │
│     account_turn_budget                                         │
│                                                                 │
│ K.  check_diagnosis_readiness → 若就绪 → AnswerMapper → 结束   │
│ K'. TerminationJudge → 若终止 → AnswerMapper → 结束            │
│ K". turn_budget 耗尽 → AnswerMapper → 结束                     │
│                                                                 │
└─── Turn N 结束 ───────────────────────────────────────────────┘
```

---

## 二、模块调用序列实测（Case #68）

以下为 `smoke_test_20260519_no_delib.log` 中记录的 **21 次 LLM 调用**：

| # | 模块 | 轮次 | 功能 |
|---|------|------|------|
| 1 | VignetteParser | 初始化 | 解析原始题目为结构化证据项 |
| 2 | SafetyController | Turn 1 | 急性安全筛查 |
| 3 | RootSelector | Turn 1 | 综合征根节点选择（首次） |
| 4 | RootSelector | Turn 1 | 同上（外部知识重试，need_external_knowledge=true） |
| 5 | BranchCreator | Turn 1 | 创建 Level-1 鉴别分支（B1-B4） |
| 6 | **TALP** | Turn 1 | 为每个 frontier 分支生成候选分析动作 |
| 7 | EvidenceAnnotator | Turn 1 | 标注 bundle 执行结果，产出 branch_effects |
| 8 | PostUpdateStateReviser | Turn 1 | 分支状态决策（expand_now / close / keep） |
| 9 | SubBranchCreator | Turn 1 | 扩展 B1(Acute Leukemia) → B1.1-B1.4 |
| 10 | TerminationJudge | Turn 1 | 判断是否终止（continue） |
| 11 | SafetyController | Turn 2 | 急性安全筛查 |
| 12 | **TALP** | Turn 2 | 候选分析动作（基于更新后的 frontier） |
| 13 | EvidenceAnnotator | Turn 2 | 标注 |
| 14 | PostUpdateStateReviser | Turn 2 | 分支状态决策 |
| 15 | TerminationJudge | Turn 2 | 判断是否终止（continue） |
| 16 | SafetyController | Turn 3 | 急性安全筛查 |
| 17 | **TALP** | Turn 3 | 候选分析动作 |
| 18 | EvidenceAnnotator | Turn 3 | 标注 |
| 19 | PostUpdateStateReviser | Turn 3 | 分支状态决策 |
| 20 | TerminationJudge | Turn 3 | 判断终止（diagnosis readiness 已触发） |
| 21 | AnswerMapper | 终止 | 将 leading branch 映射到答案选项 |

**稳态轮的模块调用模式**（Turn 2 和 Turn 3 均为 5 次调用）：

```
Safety → TALP → EvidenceAnnotator → PostUpdateStateReviser → TerminationJudge
```

---

## 三、各关键模块的当前实现逻辑

### 3.1 TemporaryAnalyticLeafPlanner (TALP)

**代码位置**: `controller.py:365-405`  
**提示词**: `prompts/temporary_analytic_leaf_planner.txt`

#### 功能

TALP 是 static QA 模式下的候选动作生成器。它接收完整的 `state.to_payload()` 作为输入，为 frontier 中的每个活跃分支生成至少一个 `ANALYZE_VIGNETTE` 候选动作。

#### 输入

TALP 接收的 payload 是 `state.to_payload()` 的输出，包含：
- `branches`: 所有分支（活跃分支为完整状态，closed/parked 为精简 stub）
- `frontier`: 当前活跃分支 ID 列表
- `actions_taken`: 最近 6 条动作记录（已剥离 `raw_result` 和 `branch_coverage`）
- `static_evidence_items`: 完整的直接证据条目列表
- `static_options`: 答案选项列表（暴露给 TALP，**注意**：这是潜在的锚定风险来源）
- `differential_history`: 最近 3 轮的概率快照

#### 输出

```json
{
  "candidate_leaves_ranked": [
    {
      "branch_id": "B1",
      "type": "ANALYZE_VIGNETTE",
      "content": "精确的分析性问题",
      "score": 0.8,
      "expected_information_gain": 0.6,
      "safety_value": 0.1,
      "action_separation_value": 0.1,
      "falsification_value": 0.1,
      "target_branches": ["B1", "B2"],
      "primary_function": "support|falsify|separate|safety_check",
      "bundle_independence": 1.0,
      "result_dependency": false,
      "redundancy_group": "",
      "urgency": "routine",
      "why": "..."
    }
  ],
  "selected_primary_action": {
    "branch_id": "B1",
    "type": "ANALYZE_VIGNETTE",
    "content": "..."
  }
}
```

#### 当前行为观察（基于日志）

**Turn 1 TALP 输出**（4 个候选，对应 4 个 frontier 分支 B1-B4）：

| # | branch_id | function | score | target |
|---|-----------|----------|-------|--------|
| 1 | B1 (Acute Leukemia) | support | 0.8 | B1, B2 |
| 2 | B2 (Chronic Myeloproliferative) | separate | 0.7 | B1, B2 |
| 3 | B3 (Lymphoproliferative) | support | 0.5 | B3, B1 |
| 4 | B4 (Reactive Leukocytosis) | falsify | 0.4 | B4, B1 |

**问题分析**：
- 4 个候选中 3 个的 `target_branches` 都包含 B1，表明 TALP 已将注意力集中在领先分支
- B2 的候选内容是"区分 B1 和 B2"，但其 `primary_function` 是 "separate" 而非 "falsify B1"
- 没有任何候选试图反驳 B1 的领先地位

#### 评分公式

```
LeafScore = ExpectedInformationGain
          + SafetyValue
          + ActionSeparationValue
          + FalsificationValue
          - CostPenalty        (= 0, 静态模式)
          - DelayPenalty       (= 0, 静态模式)
          - InvasivenessPenalty (= 0, 静态模式)
```

在静态模式下，Cost/Delay/Invasiveness 恒为 0，因此评分简化为四个正向分量之和。

### 3.2 FrontierCoverageBundler

**代码位置**: `action_bundler.py`  
**类型**: 确定性算法（不调用 LLM）

#### 算法阶段

```
Phase 0: 短路 — 若 top 候选为 DIAGNOSIS_READY，直接返回
Phase 1: 强制覆盖 — 为 frontier 中每个活跃分支选择一个最高分代表动作
Phase 1.5: 反证保障 — 若 leader (P≥0.5) 无 falsify 动作，尝试插入一个
Phase 2: 补充 — 用 action_separation_value 高的跨分支动作填充
Phase 3: 排序 — 按 expected_delay 升序排列
```

#### 当前行为（基于日志）

Turn 1 的 4 个候选全部入选 bundle（因为每个分支各有一个代表），形成大小为 4 的 bundle。

**关键约束**：
- `_is_redundant`: Jaccard 相似度 > 0.60 则排除
- `_is_dependent`: 计算器/知识检索不能与数据产出动作同 bundle
- `_passes_gates`: 综合所有约束

#### 已知问题

1. **Phase 1.5 反证保障阈值过高**：leader P ≥ 0.5 才触发，而首轮 B1 先验仅 0.4，反证保障未生效
2. **无锚定检测**：Bundler 不检查 bundle 是否过度集中于某一分支
3. **选项暴露**：`static_options` 出现在 payload 中，可能影响 TALP 的分析角度

### 3.3 execute_action_bundle

**代码位置**: `controller.py:419-471`

#### 执行流程

```python
for action in bundle:
    action_dict = _leaf_to_action_dict(action)
    raw_result = _execute_single_action(state, action_dict, ...)
```

在 static QA 模式下，所有 `ANALYZE_VIGNETTE` 动作的 `_dispatch_env_call` 返回：

```json
{
  "analysis_target": "<TALP 生成的分析问题>",
  "evidence_items_ref": "see state.static_evidence_items",
  "question": "<原始问题>"
}
```

**关键特征**：这不是真正的"执行"——没有外部交互，仅将分析目标记录到 state 中。实际的推理发生在 EvidenceAnnotator 处理这些记录时。

### 3.4 EvidenceAnnotator

**代码位置**: `controller.py:625-694`  
**提示词**: `prompts/evidence_annotator.txt`

#### 功能

接收 `(state, raw_result)` 对，产出：
- `branch_effects`: 每个分支的证据效果（`strong_for` / `moderate_for` / `weak_for` / `neutral` / `weak_against` / `moderate_against` / `strong_against`）
- `result_summary`: 文本摘要
- `major_update`: 是否为重大更新
- `contradiction_detected`: 是否检测到矛盾
- `reopen_candidates`: 建议重开的分支列表

#### 当前行为

单个 bundle 结果时使用单条路径（`annotate_evidence`），多个时使用批量路径（`annotate_evidence_bundle`）。

**处理流程**：
1. 调用 LLM 获取标注结果
2. `_clean_annotation`: 验证 branch ID，强制 expanded 分支为 neutral
3. `_update_branch_evidence_lists`: 将 summary 追加到对应分支的 `evidence_for` / `evidence_against`
4. 当 bundle 大小 > 1 时，`group_correlated_evidence` 将 `strong_for/against` 降级为 `moderate_for/against`

### 3.5 概率更新

**代码位置**: `controller.py:741-768`, `updater.py`

#### 策略选择

`choose_update_method(annotation)` 根据标注中的 `calculator_applicable` 和 `formal_rule_available` 字段选择：
- `calculator`: 使用计算器结果的精确更新
- `rule_based`: 使用确定性规则的更新
- `ordinal`: 默认的序数更新（绝大多数情况）

#### ordinal_update

基于 `branch_effects` 的序数标签（strong/moderate/weak × for/against）执行固定幅度的概率调整，然后重新归一化。

### 3.6 PostUpdateStateReviser

**代码位置**: `controller.py:1003-1037`  
**提示词**: `prompts/post_update_state_reviser.txt`

#### 功能

接收更新后的 state，对每个分支做出决策：
- `confirm`: 分支被确认（高概率 + 充分证据）
- `close_for_now`: 分支被暂时关闭
- `park`: 分支被搁置
- `reopen`: 重新激活已关闭的分支
- `expand_now`: 标记为需要扩展（设置 `expand_score = 0.5`）
- `keep_coarse`: 保持当前状态

同时更新 `state.frontier`。

### 3.7 ExpansionGate + SubBranchCreator

**代码位置**: `controller.py:773-966`

#### ExpansionGate 条件（全部硬约束通过 + 至少一个 ALLOW 条件）

**硬约束**:
- `level < max_tree_depth`（默认 3）
- `status != confirmed`
- `posterior >= test_threshold`（0.05）
- 无现有子节点

**ALLOW 条件**（至少满足一个）:
- `ActionDifferenceScore >= min_action_diff_to_expand`（0.25）
- `danger >= 0.7`
- 存在未解决的 discriminator
- 怀疑共存诊断

#### SubBranchCreator

调用 LLM 为通过 ExpansionGate 的分支生成子分支。子节点的概率通过贝叶斯分解从父节点分配。父节点状态变为 `expanded`，概率归零。

### 3.8 check_diagnosis_readiness

**代码位置**: `controller.py:1086-1122`

#### 逻辑

```python
diagnosable = [b for b in branches if b.status != "expanded"]
leader = max(diagnosable, key=lambda b: b.posterior)
if leader.posterior >= min_readiness_to_commit:  # 默认 0.80
    return True  # 进入 AnswerMapper
```

**修复历史**：曾因未过滤 `expanded` 分支导致过早终止（Case #68 修复）。

### 3.9 AnswerMapper

**代码位置**: `controller.py:1148-1159`  
**提示词**: `prompts/answer_mapper.txt`

#### 功能

将 state 中的 leading branch 映射到答案选项，产出：
- `final_answer`: 选项字母（如 "B"）
- `answer_option_mapping`: 各选项的置信度分布

---

## 四、Token 管理机制：state.to_payload()

**代码位置**: `state.py:176-252`

`to_payload()` 是 `to_dict()` 的 token-efficient 版本，应用以下裁剪：

| 字段 | 裁剪方式 | 每轮节省量 |
|------|---------|-----------|
| `actions_taken` | 剥离 `raw_result` 和 `branch_coverage`；最多保留 6 条 | ~2,200 chars/turn |
| `branch.evidence_for/against` | 每个列表最多保留 2 条 | ~1,600 chars/turn |
| closed/parked 分支 | 替换为精简 stub（id, label, status, posterior, danger） | ~1,600 chars/turn |
| `deliberation` | 清空（当前已关闭，无影响） | ~500 chars/turn |
| `differential_history` | 最多 3 轮快照 | 累积控制 |
| `candidate_leaves` | 省略（不被下游消费） | 变量 |

**整体效果**：防止 payload 随轮次线性增长。实测 Turn 1 payload ≈ 4K tokens，Turn 3 payload ≈ 5K tokens（增速受控）。

---

## 五、当前流水线的已知缺陷

### 5.1 无反锚定机制

**症状**：Case #68 中 B1(Acute Leukemia) 从 Turn 1 起领先，B2(CML) 在 Turn 1 即被 close_for_now，后续从未重开。正确诊断 CML 从未获得足够分析关注。

**根因**：
- TALP 不接收任何"挑战领先分支"的信号
- FrontierCoverageBundler 的 Phase 1.5 反证保障在首轮不生效（leader P < 0.5）
- PostUpdateStateReviser 关闭 B2 后无自动反审机制

### 5.2 ANALYZE_VIGNETTE 的空执行

**症状**：`_dispatch_env_call` 对 `ANALYZE_VIGNETTE` 返回的仅是一个指向性记录（`analysis_target` + `evidence_items_ref`），不执行任何实际分析。

**影响**：所有分析推理实际由 EvidenceAnnotator 一个模块完成，EvidenceAnnotator 同时承担了"分析证据"和"标注效果"双重职责，超出其设计意图。

### 5.3 选项暴露

**症状**：`state.to_payload()` 将 `static_options`（答案选项列表）传递给 TALP 和 EvidenceAnnotator，可能引入锚定偏差。

**对比**：RootSelector 已通过 `_root_selector_payload()` 剥离选项，但其他模块未做此处理。

### 5.4 EvidenceAnnotator 过载

**症状**：在静态模式下，EvidenceAnnotator 需要在看到 `{"analysis_target": "Does X support Y?", "evidence_items_ref": "see state"}` 后：
1. 理解分析目标
2. 从 state 中的 `static_evidence_items` 中找到相关证据
3. 进行临床推理
4. 产出 branch_effects

步骤 2-3 本应由 ANALYZE_VIGNETTE 的"执行"完成，但当前该步骤为空操作。

### 5.5 bundle 大小与 annotator 输入不匹配

**症状**：Turn 1 产生 4 个 bundle 动作，但 `annotate_evidence_bundle` 在 `len(bundle_results) == 1` 时走单条路径。实际上 bundle 包含 4 个 action，但由于静态模式的特殊处理，所有 action 的 `raw_result` 结构相同（仅 `analysis_target` 不同），Annotator 需要在一次调用中处理 4 个不同的分析目标。

### 5.6 概率更新缺乏自反馈

**症状**：ordinal_update 对 `strong_for` 的固定增幅不考虑该分支已获得多少次 `strong_for`。已经领先的分支持续获得 `strong_for` 会导致概率过度集中。

---

## 六、与含审议循环运行的比较

| 指标 | 含审议循环（dx2 日志） | 无审议循环（当前） |
|------|---------------------|------------------|
| 总 LLM 调用 | ~61 次 | 21 次 |
| 运行轮数 | 5 轮 | 3 轮（第 3 轮 readiness 触发） |
| 运行时间 | ~120 秒 | ~42 秒 |
| 最终答案 | B (AML) ✗ | B (AML) ✗ |
| B2(CML) 最终后验 | 0.015（reopened） | 0.046（closed_for_now） |
| 审议循环对结果的影响 | 微弱（Consensus 被 bundle 覆盖） | N/A |

**关键发现**：关闭审议循环后答案未改变，确认了 `IMPLEMENTATION_STATUS.md` 中的分析——旧审议循环对最终结果几乎无影响，因为 Consensus 的 `selected_action` 在 static QA 模式下被 `build_bundle()` 的结果覆盖。

---

## 七、TALP 与 Bundler 之间的数据流

```
                     state.to_payload()
                           │
                           ▼
              ┌─────────────────────┐
              │ TALP (LLM)          │
              │                     │
              │ 输入:               │
              │   全部 branches     │
              │   frontier          │
              │   actions_taken[-6] │
              │   evidence_items    │
              │   static_options    │
              │                     │
              │ 输出:               │
              │   candidate_leaves  │
              │   selected_action   │
              └─────────┬───────────┘
                        │
                        ▼
              ┌─────────────────────┐
              │ FrontierCoverage    │
              │ Bundler (确定性)    │
              │                     │
              │ 输入:               │
              │   candidate_leaves  │
              │   state             │
              │   config            │
              │                     │
              │ Phase 1: 每分支选 1 │
              │ Phase 1.5: 反证     │
              │ Phase 2: 补充       │
              │ Phase 3: 排序       │
              │                     │
              │ 输出:               │
              │   bundle            │
              │   branch_coverage   │
              └─────────┬───────────┘
                        │
                        ▼
              ┌─────────────────────┐
              │ execute_action_     │
              │ bundle              │
              │                     │
              │ static QA:          │
              │ → {analysis_target, │
              │    evidence_ref,    │
              │    question}        │
              │ × bundle_size       │
              └─────────┬───────────┘
                        │
                        ▼
              ┌─────────────────────┐
              │ EvidenceAnnotator   │
              │ (LLM)              │
              │                     │
              │ 输入:               │
              │   state.to_payload()│
              │   bundle_results    │
              │                     │
              │ 输出:               │
              │   branch_effects    │
              │   result_summary    │
              │   major_update      │
              │   reopen_candidates │
              └─────────┬───────────┘
                        │
                        ▼
              ┌─────────────────────┐
              │ apply_probability_  │
              │ update (确定性)     │
              │                     │
              │ ordinal_update:     │
              │   效果标签 → 固定   │
              │   概率增减 → 归一化 │
              └─────────────────────┘
```

---

## 八、配置参数（当前值）

| 参数 | 值 | 作用 |
|------|---|------|
| `execution_mode` | `"static_diagnosis_qa"` | 启用静态模式 |
| `max_turn_budget` | 5 | 最大轮数 |
| `min_readiness_to_commit` | 0.80 | 触发诊断就绪的概率阈值 |
| `max_live_frontier` | 6 | 前沿最大分支数 |
| `max_tree_depth` | 3 | 最大树深度 |
| `min_marginal_ig_threshold` | 0.05 | bundle 候选最小信息增益 |
| `redundancy_similarity_threshold` | 0.60 | Jaccard 冗余阈值 |
| `min_separation_value_for_supplement` | 0.50 | Phase 2 补充动作最低分离值 |
| `bundle_budget_mode` | `"per_bundle"` | 每个 bundle 计 1 轮 |

---

## 九、修改记录

| 日期 | 修改 | 文件 |
|------|------|------|
| 2026-05-19 | 关闭 static QA 审议循环（`run_static_qa_deliberation` 调用和 consensus override） | `controller.py:80-83, 98-100` |
