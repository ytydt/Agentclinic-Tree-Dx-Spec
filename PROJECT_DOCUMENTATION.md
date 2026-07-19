# agentclinic-tree-dx 项目开发文档

> 本文档面向接手该项目的后续开发者，以当前实际代码实现状态为基准，描述项目的架构、模块、外部集成方式及尚未完成的工作。

---

## 目录

1. [项目背景与目标](#1-项目背景与目标)
2. [仓库结构](#2-仓库结构)
3. [算法设计概述](#3-算法设计概述)
4. [核心状态模型](#4-核心状态模型)
5. [控制器主循环](#5-控制器主循环)
6. [执行模式](#6-执行模式)
7. [各核心模块说明](#7-各核心模块说明)
8. [提示词系统](#8-提示词系统)
9. [LLM 客户端](#9-llm-客户端)
10. [外部项目集成](#10-外部项目集成)
    - [AgentClinic 集成](#101-agentclinic-集成)
    - [SDBench 集成](#102-sdbench-集成)
11. [适配器层（Adapters）](#11-适配器层adapters)
12. [工具路由模块](#12-工具路由模块)
13. [测试体系](#13-测试体系)
14. [安装与运行](#14-安装与运行)
15. [当前实现状态与差距分析](#15-当前实现状态与差距分析)
16. [后续开发指引](#16-后续开发指引)

---

## 1. 项目背景与目标

### 1.1 学术背景

本项目的核心算法思路来源于《面向视频问答的组合式推理技术研究 v3(1).pdf》中提出的树推理方法——通过**自顶向下的递归分解**加**自底向上的聚合**，维护可追踪的推理路径。该方法被迁移并适配到临床诊断领域。

参考文件：
- `面向视频问答的组合式推理技术研究v3(1).pdf`
- `tree-reasoning-in-diagnosis_20260412_0732.json`

### 1.2 项目定位

本项目是一个**基准测试专用**的原型诊断推理系统，不面向真实患者部署。其核心能力包括：

1. 在部分可观测条件下维护诊断推理树；
2. 决策每轮应执行的动作（问诊、检查、检验、影像、计算器、知识检索、终止）；
3. 每轮获取新证据后更新分支概率；
4. 在合适的置信度下停止推理；
5. 输出下列四种诊断结论之一：
   - 主导诊断（single leading diagnosis）
   - 可指导管理的父综合征（actionable parent syndrome）
   - 共存诊断（coexisting diagnoses）
   - 带后续检查计划的工作鉴别诊断（ranked working differential）

### 1.3 支持的基准任务

| 基准类型 | 上游项目 | 对应执行模式 |
|---------|---------|------------|
| 交互式诊断（医生扮演） | [AgentClinic](https://github.com/SamuelSchmidgall/AgentClinic.git) | `agentclinic_physician_patch` |
| 交互式诊断（Gatekeeper 接口） | [Open-MAI-Dx-Orchestrator (SDBench)](https://github.com/The-Swarm-Corporation/Open-MAI-Dx-Orchestrator) | `sdbench_patch` |
| 静态选择题式诊断（MedQA 风格） | 无需上游 | `static_diagnosis_qa` |

---

## 2. 仓库结构

```
agentclinic-tree-dx/
├── pyproject.toml                          # 项目配置，依赖 openai>=1.40.0
├── readme.md                               # 主规格文档（最完整版）
├── agentclinic_tree_dx_spec.md             # AgentClinic 树诊断规格（与 readme 高度重叠）
├── sdbench_tree_dx_spec.md                 # SDBench 模式专用规格
├── sdbench_tree_dx_scaffold_continuation.md# SDBench 脚手架示例代码片段
├── sdbench_upstream_setup.md               # SDBench 上游接入说明（安装 + 接口）
├── agentclinic_upstream_setup.md           # AgentClinic 上游接入说明（安装 + 接口）
├── agentclinic_patch_development_documentation.md  # AgentClinic Physician Patch 需求文档
├── sdbench_diagnostic_algorithm_patch_dev_doc.md   # 标准算法→补丁算法迁移说明
├── static_diagnosis_qa_mode_spec.md        # 静态 QA 模式规格（第1部分）
├── static_diagnosis_qa_mode_spec_part_2.md # 静态 QA 规格第2部分
├── static_diagnosis_qa_mode_spec_part_3.md # 静态 QA 规格第3部分
├── static_diagnosis_qa_mode_spec_part_4.md # 静态 QA 规格第4部分
├── static_diagnosis_qa_mode_spec_part_5.md # 静态 QA 规格第5部分
├── static_diagnosis_qa_patch_spec.md       # 静态 QA 与交互算法的增量规格
│
├── src/agentclinic_tree_dx/                # 主包源码
│   ├── __init__.py
│   ├── config.py                           # ControllerConfig 配置类
│   ├── state.py                            # 所有状态数据类
│   ├── controller.py                       # 核心控制器（主循环）
│   ├── prompting.py                        # 提示词加载映射
│   ├── llm_client.py                       # OpenAI LLM 客户端
│   ├── update_router.py                    # 更新方法路由器
│   ├── updater.py                          # 概率更新器（序数更新）
│   ├── branch_manager.py                   # 分支管理模块封装
│   ├── leaf_planner.py                     # 临时叶子规划模块封装
│   ├── executor.py                         # 动作执行模块封装
│   ├── aggregator.py                       # 最终聚合模块封装
│   ├── safety.py                           # 安全筛查模块封装
│   ├── root_selector.py                    # 根节点选择模块封装
│   ├── termination.py                      # 终止判断模块封装
│   ├── evidence_annotator.py               # 证据注释模块封装
│   ├── state_reviser.py                    # 状态修订模块封装
│   ├── prompts/                            # 提示词文件（.txt）
│   │   ├── safety_controller.txt
│   │   ├── root_selector.txt
│   │   ├── branch_creator.txt
│   │   ├── temporary_leaf_planner.txt
│   │   ├── evidence_annotator.txt
│   │   ├── post_update_state_reviser.txt
│   │   ├── termination_judge.txt
│   │   ├── final_aggregator.txt
│   │   ├── hypothesis.txt                  # SDBench/Static QA 辩论角色
│   │   ├── test_chooser.txt
│   │   ├── challenger.txt
│   │   ├── stewardship.txt
│   │   ├── checklist.txt
│   │   ├── consensus.txt
│   │   ├── final_diagnosis_emitter.txt     # SDBench 专用
│   │   ├── vignette_parser.txt             # Static QA 专用
│   │   ├── answer_mapper.txt               # Static QA 专用
│   │   ├── evidence_allocator.txt          # Static QA 专用
│   │   ├── reasoning_economy_auditor.txt   # Static QA 专用
│   │   ├── temporary_analytic_leaf_planner.txt  # Static QA 专用
│   │   └── tool_use_gate.txt               # Static QA 专用
│   ├── adapters/
│   │   ├── agentclinic_env.py              # AgentClinic 环境适配器
│   │   ├── sdbench_env.py                  # SDBench 环境适配器
│   │   ├── static_qa_env.py                # 静态 QA 环境适配器
│   │   └── mock_env.py                     # 测试用 Mock 适配器
│   └── tools/
│       ├── calculator_router.py            # 计算器路由（占位实现）
│       └── knowledge_router.py             # 知识检索路由（占位实现）
│
└── tests/
    ├── test_state.py
    ├── test_controller.py
    ├── test_update_router.py
    ├── test_agentclinic_env.py
    ├── test_sdbench_mode.py
    ├── test_static_qa_mode.py
    ├── test_llm_path.py
    └── test_patch_mode.py
```

---

## 3. 算法设计概述

### 3.1 两阶段主循环

控制器每轮按"规划 → 同化"两个阶段执行：

**规划阶段（Planning Phase）**

| 步骤 | 描述 |
|-----|------|
| A. 安全筛查 | 检测是否需要紧急干预，若是则优先执行急救动作 |
| B. 根节点选择/修订 | 确定当前综合征级别的组织性问题 |
| C. 分支创建/修订 | 生成竞争假设分支，维护活跃前沿 |
| D. 辩论（部分模式） | SDBench/Static QA 模式下执行多角色辩论 |
| E. 临时叶子规划 | 为活跃分支分配候选下一步判别动作，全局排序，选择一个主动作 |

**同化阶段（Assimilation Phase）**

| 步骤 | 描述 |
|-----|------|
| F. 执行主动作 | 调用外部环境获取新证据 |
| G. 证据注释 | LLM 将原始结果转换为结构化分支相关证据 |
| H. 更新路由 | 确定性地选择更新方法（计算器 / 规则 / 序数） |
| I. 概率更新 | 更新分支后验概率 |
| J. 状态修订 | 对各分支执行展开/停泊/关闭/确认/重开决策 |
| K. 终止检查 | 判断是否应停止推理树扩展 |
| L. 最终聚合 | 若停止则生成面向基准的输出 |

### 3.2 分支生命周期

每个分支（Branch）处于以下状态之一：

| 状态 | 含义 |
|-----|------|
| `live` | 当前活跃，可参与下一轮判别 |
| `parked` | 暂时搁置，但保留以备后用 |
| `closed_for_now` | 低于测试阈值，当前不再追踪 |
| `confirmed` | 后验概率已足够高，已确认 |
| `reopened` | 因新证据矛盾或先前结果被重新解读而重新激活 |

### 3.3 更新方法策略

LLM **只负责注释证据**，不决定更新方法。更新方法由确定性策略路由器选择：

```python
def choose_update_method(annotation: dict) -> str:
    if annotation.get("calculator_applicable", False):
        return "calculator"
    if annotation.get("formal_rule_available", False):
        return "rule_based"
    return "ordinal"
```

> **当前状态**：三个分支在 `apply_probability_update` 中均实际执行的是序数更新（ordinal update），calculator 和 rule_based 路径均为占位实现。

---

## 4. 核心状态模型

状态模型定义在 `src/agentclinic_tree_dx/state.py`。

### 4.1 DiagnosticState（诊断状态）

系统的核心全局状态，贯穿整个控制器生命周期：

| 字段 | 类型 | 说明 |
|-----|------|------|
| `case_id` | str | 案例标识 |
| `timestep` | int | 当前轮次 |
| `case_summary` | str | 案例摘要（每轮从环境获取） |
| `root` | RootNode \| None | 当前根节点（综合征级别） |
| `branches` | dict[str, Branch] | 所有分支（含各状态） |
| `frontier` | list[str] | 当前活跃分支 ID 列表 |
| `other_mass` | float | 活跃前沿之外分支的概率总质量 |
| `candidate_leaves` | list[CandidateLeaf] | 当前轮候选叶子动作 |
| `actions_taken` | list[dict] | 历史动作记录 |
| `differential_history` | list[dict] | 每轮分支后验概率历史 |
| `deliberation` | DeliberationState | 辩论状态（SDBench/Static QA） |
| `interrupt` | InterruptState | 紧急中断状态 |
| `termination` | TerminationState | 终止状态 |
| `turn_budget_used` | int | 已用轮次（Patch 模式） |
| `estimated_remaining_value` | float | 估算剩余信息价值 |
| `diagnosis_readiness_score` | float | 诊断就绪度评分 |
| `benchmark_output_ready` | bool | 基准输出是否就绪 |
| `static_vignette` | str | 静态 QA 文本（Static QA 模式） |
| `static_question` | str | 静态 QA 问题 |
| `static_options` | list[str] | 静态 QA 选项列表 |
| `static_evidence_items` | list[EvidenceItem] | 静态 QA 已解析证据项 |
| `tool_use_log` | list[dict] | 工具调用日志（Static QA） |

### 4.2 Branch（分支）

表示一个竞争性诊断假设：

| 字段 | 说明 |
|-----|------|
| `id` | 分支唯一标识 |
| `label` | 假设名称 |
| `status` | 生命周期状态 |
| `prior` / `posterior` | 先验 / 后验概率 |
| `danger` | 危险程度（0-1），影响"不可漏诊"判断 |
| `actionability` | 可操作性分数 |
| `explanatory_coverage` | 解释覆盖率 |
| `expand_score` | 展开得分 |
| `evidence_for` / `evidence_against` | 支持/反对该分支的证据 |
| `askable_discriminators` | 可通过问诊获取的判别器（Patch 模式扩展） |
| `requestable_discriminators` | 可通过检查/检验获取的判别器 |
| `turn_cost_to_refine` | 精化该分支所需轮次成本 |
| `diagnosis_commitment_gain` | 确认该分支对诊断就绪度的提升 |

### 4.3 CandidateLeaf（候选叶子）

临时叶子规划阶段产生的候选下一步动作：

| 字段 | 说明 |
|-----|------|
| `leaf_type` | 动作类型（见下方动作空间） |
| `content` | 动作内容描述 |
| `expected_information_gain` | 期望信息增益 |
| `expected_cost` | 期望成本 |
| `total_score` | 综合评分 |

### 4.4 DeliberationState（辩论状态）

仅在 SDBench 和 Static QA 模式下使用：

| 字段 | 对应辩论角色 |
|-----|------------|
| `hypothesis_analysis` | Hypothesis（假设分析） |
| `test_chooser_analysis` | TestChooser / EvidenceAllocator |
| `challenger_analysis` | Challenger（挑战者） |
| `stewardship_analysis` | Stewardship / ReasoningEconomyAuditor |
| `checklist_analysis` | Checklist（清单核查） |
| `consensus_action` | Consensus（共识动作，最终被执行） |

---

## 5. 控制器主循环

控制器实现在 `src/agentclinic_tree_dx/controller.py`，类名 `AgentClinicTreeController`。

### 5.1 初始化参数

```python
AgentClinicTreeController(
    env,                   # 环境适配器（必填）
    llm=None,              # OpenAILLMClient 实例，若不提供则使用 env.call_module()
    calculator_router=None,# 计算器路由，默认 naive_calculator_router（占位）
    knowledge_router=None, # 知识路由，默认 naive_knowledge_router（占位）
    config=None,           # ControllerConfig 实例，默认使用默认配置
)
```

### 5.2 配置项（ControllerConfig）

| 字段 | 默认值 | 说明 |
|-----|--------|------|
| `execution_mode` | `"default"` | 执行模式（见第6节） |
| `test_threshold` | `0.05` | 分支测试阈值（低于此值可关闭） |
| `commit_threshold` | `0.75` | 分支确认阈值 |
| `max_live_frontier` | `4` | 最大活跃前沿宽度 |
| `max_turn_budget` | `None` | 最大轮次预算（Patch/SDBench/Static QA 模式强制） |
| `min_readiness_to_commit` | `0.75` | 诊断就绪度最低阈值 |
| `allow_external_knowledge` | `True` | 是否允许外部知识检索 |
| `allow_calculator` | `True` | 是否允许计算器 |
| `allow_notebook` | `False` | 是否允许笔记本工具 |

### 5.3 模块调用机制

控制器内部统一使用 `_call_module(module_name, payload)` 调用各阶段模块：

- 若初始化时提供了 `llm`：加载对应提示词文件，调用 OpenAI API，返回 JSON；
- 若未提供 `llm`：调用 `env.call_module(module_name, payload)`，用于确定性测试（注入 mock 响应）。

### 5.4 模式判断方法

| 方法 | 返回 True 的条件 |
|-----|----------------|
| `_in_patch_mode()` | `execution_mode == "agentclinic_physician_patch"` |
| `_in_sdbench_mode()` | `execution_mode == "sdbench_patch"` |
| `_in_static_qa_mode()` | `execution_mode == "static_diagnosis_qa"` |

---

## 6. 执行模式

### 6.1 default 模式

最基础的交互式诊断模式，无特定基准约束。每轮执行完整的规划-同化流程，由 `TerminationJudge` 模块决定何时停止。

**输出格式**：`FinalAggregator` 模块的标准 JSON 输出。

### 6.2 agentclinic_physician_patch 模式

对接 AgentClinic 基准平台的医生扮演模式。主要特性：

- **动作空间收窄**：映射到 `ASK_PATIENT`、`REQUEST_TEST_OR_MEASUREMENT`、`USE_NOTEBOOK`（需开启）、`RETRIEVE_EXTERNAL_KNOWLEDGE`（需开启）、`DIAGNOSIS_READY`；
- **诊断就绪度门控**：只有当 `leader.posterior >= min_readiness_to_commit` 且不存在危险备选假设和高价值判别动作时，才允许提交诊断；
- **轮次预算**：超过 `max_turn_budget` 时强制停止；
- **输出格式**：
  ```json
  {
    "internal_reasoning_state": {...},
    "benchmark_output": "Diagnosis Ready: <diagnosis>"
  }
  ```

### 6.3 sdbench_patch 模式

对接 Open-MAI-Dx-Orchestrator（SDBench）Gatekeeper 接口。主要特性：

- **动作空间**：映射到 `ASK`、`TEST`、`DIAGNOSE` 三类 SDBench 原生动作；
- **Top-3 前沿限制**：活跃分支上限为 3（而非 default 模式的 4）；
- **多角色辩论**：每轮在叶子规划之前执行 6 角色辩论（Hypothesis、TestChooser、Challenger、Stewardship、Checklist、Consensus），共识动作覆盖叶子规划器的选择；
- **最终诊断发射**：使用 `FinalDiagnosisEmitter` 生成单一诊断字符串，并调用 `env.submit_diagnosis()` 提交；
- **输出格式**：
  ```json
  {
    "diagnosis": "...",
    "submission": {...},
    "internal_reasoning_state": {...}
  }
  ```

### 6.4 static_diagnosis_qa 模式

处理静态选择题式诊断任务（MedQA、NEJM 等）。主要特性：

- **无需外部环境**：第一轮通过 `VignetteParser` 解析整个案例文本，提取证据项、问题和选项；
- **无需患者/测量智能体**：所有"动作"都是对已解析证据的内部分析（`ANALYZE_VIGNETTE`、`SELECT_OPTION`）；
- **辩论角色**：使用 `EvidenceAllocator`（替代 TestChooser）和 `ReasoningEconomyAuditor`（替代 Stewardship）；
- **工具门控**：使用 `ToolUseGate` 模块在执行计算器/知识检索前做基准纯洁性检验；
- **叶子规划器**：使用 `TemporaryAnalyticLeafPlanner`（替代 `TemporaryLeafPlanner`）；
- **输出格式**：
  ```json
  {
    "final_answer": "A",
    "answer_option_mapping": {...},
    "internal_reasoning_state": {...}
  }
  ```

---

## 7. 各核心模块说明

### 7.1 SafetyController（安全筛查）

**提示词文件**：`prompts/safety_controller.txt`

**职责**：检查是否存在需要立即干预的紧急情况（如气道受损、休克、严重出血等）。

**输入**：当前 `DiagnosticState` 序列化字典

**输出 JSON 示例**：
```json
{
  "interrupt_active": false,
  "reason": "stable",
  "required_actions": [],
  "why_not_interrupt_if_false": ["no instability signs"]
}
```

**控制器行为**：若 `interrupt_active=true`，执行紧急动作后检查 `env.patient_still_unstable()`，若仍不稳定则跳过本轮后续步骤。

### 7.2 RootSelector（根节点选择）

**提示词文件**：`prompts/root_selector.txt`

**职责**：从当前可用信息中选择最佳综合征级别的组织性问题作为推理树的根节点。

**约束**：
- 不得以单一孤立化验值作为根节点；
- 优先选择综合征级别的表述；
- 若提出外部知识请求且 `allow_external_knowledge=True`，控制器会调用知识路由并重新调用本模块。

**输出 JSON 示例**：
```json
{
  "root_label": "acute chest pain syndrome",
  "time_course": "hours",
  "supporting_facts": ["substernal pain", "radiation to left arm"],
  "excluded_root_candidates": ["isolated troponin elevation"],
  "need_external_knowledge": false,
  "knowledge_query_if_needed": "",
  "confidence": 0.7
}
```

### 7.3 BranchCreator（分支创建）

**提示词文件**：`prompts/branch_creator.txt`

**职责**：在当前根节点下生成竞争性假设分支。

**约束**：默认 2-4 个活跃分支；若存在高危情况，至少包含一个"不可漏诊"分支。

**输出 JSON 示例**：
```json
{
  "branches": [
    {"id": "B1", "label": "ACS", "status": "live", "prior_estimate": 0.5, "danger": 0.8},
    {"id": "B2", "label": "GERD", "status": "live", "prior_estimate": 0.5, "danger": 0.1}
  ],
  "frontier": ["B1", "B2"],
  "need_external_knowledge": false,
  "knowledge_query_if_needed": ""
}
```

### 7.4 TemporaryLeafPlanner（临时叶子规划）

**提示词文件**：`prompts/temporary_leaf_planner.txt`（交互模式），`prompts/temporary_analytic_leaf_planner.txt`（Static QA 模式）

**职责**：为当前活跃分支生成候选判别动作，全局排序后**选出且仅选出一个**主动作。

**候选动作类型**：`ASK_PATIENT`、`REQUEST_EXAM`、`REQUEST_VITAL`、`ORDER_LAB`、`ORDER_IMAGING`、`USE_CALCULATOR`、`RETRIEVE_KNOWLEDGE`

**评分公式**：
```
LeafScore(L) = ExpectedInformationGain(L) + SafetyValue(L) + ActionSeparationValue(L)
             - CostPenalty(L) - DelayPenalty(L)
```

### 7.5 EvidenceAnnotator（证据注释）

**提示词文件**：`prompts/evidence_annotator.txt`

**职责**：将原始动作结果转换为结构化的分支相关证据。

**重要约束**：LLM 在此阶段**只能注释证据**，不得直接修改分支状态或选择更新数学方法。

**输出 JSON 示例**：
```json
{
  "result_summary": "pain radiates to left arm",
  "major_update": true,
  "calculator_applicable": false,
  "formal_rule_available": false,
  "branch_effects": {
    "B1": "strong_for",
    "B2": "moderate_against"
  },
  "contradiction_detected": false,
  "reopen_candidates": []
}
```

`branch_effects` 可取值：`strong_for`、`moderate_for`、`weak_for`、`neutral`、`weak_against`、`moderate_against`、`strong_against`

### 7.6 UpdateRouter（更新路由）

**源文件**：`src/agentclinic_tree_dx/update_router.py`

**职责**：根据证据注释确定性地选择概率更新方法（无 LLM 调用）。

> **当前状态**：虽然路由逻辑已实现，但 `apply_probability_update` 在三条路径下均实际执行序数更新。

### 7.7 Updater（概率更新器）

**源文件**：`src/agentclinic_tree_dx/updater.py`

**已实现**：序数更新（ordinal update），对应权重表：

```python
ORDINAL_WEIGHTS = {
    "strong_for": 3.0,
    "moderate_for": 1.8,
    "weak_for": 1.2,
    "neutral": 1.0,
    "weak_against": 0.8,
    "moderate_against": 0.5,
    "strong_against": 0.2,
}
```

更新逻辑：`new_posterior = normalize(prior * weight)`

**未实现**：calculator_update、rule_based_update

### 7.8 PostUpdateStateReviser（后更新状态修订）

**提示词文件**：`prompts/post_update_state_reviser.txt`

**职责**：在概率更新完成后，对每个分支做结构性状态转移决策。

**可选决策**：`expand_now`、`keep_coarse`、`park`、`close_for_now`、`confirm`、`reopen`

**控制器行为**：根据决策更新分支 `status` 字段，并重建 `state.frontier` 列表。

### 7.9 TerminationJudge（终止判断）

**提示词文件**：`prompts/termination_judge.txt`

**职责**：判断是否应停止推理树的扩展。

**五种终止类型**：
1. `confirmation`：一个分支已被足够确认
2. `actionable_parent`：多个子分支未解决，但共用同一管理路径
3. `info_exhaustion`：没有更多可期待改变管理决策的判别信息
4. `working_differential`：显式的不确定性管理是正确终点
5. `emergency_override`：紧急干预覆盖进一步扩展

### 7.10 FinalAggregator / FinalDiagnosisEmitter / AnswerMapper（最终聚合）

- **default / agentclinic_physician_patch 模式**：调用 `FinalAggregator`，输出标准诊断 JSON（含 `final_mode`、`ranked_differential` 等）；若设置了 moderator_agent，还会附加 `moderator_review`；
- **sdbench_patch 模式**：调用 `FinalDiagnosisEmitter`，输出单一诊断字符串，并提交给 Gatekeeper；
- **static_diagnosis_qa 模式**：调用 `AnswerMapper`，从分支状态映射到最佳选项，输出 `final_answer`。

### 7.11 辩论模块（SDBench 和 Static QA 模式专用）

每轮在叶子规划前执行，顺序为：

| 模式 | 角色顺序 |
|-----|---------|
| SDBench | Hypothesis → TestChooser → Challenger → Stewardship → Checklist → Consensus |
| Static QA | Hypothesis → EvidenceAllocator → Challenger → ReasoningEconomyAuditor → Checklist → Consensus |

`Consensus` 模块的输出会覆盖叶子规划器选择的动作（若存在共识动作）。

---

## 8. 提示词系统

提示词文件存放在 `src/agentclinic_tree_dx/prompts/` 目录，每个模块对应一个 `.txt` 文件。

**加载机制**（`prompting.py`）：

```python
PROMPT_FILE_BY_MODULE = {
    "SafetyController": "safety_controller.txt",
    "RootSelector": "root_selector.txt",
    # ...共 22 个映射
}

def load_module_prompt(module_name: str) -> str:
    file_name = PROMPT_FILE_BY_MODULE[module_name]
    prompts_dir = Path(__file__).resolve().parent / "prompts"
    return (prompts_dir / file_name).read_text(encoding="utf-8").strip()
```

**调用方式**：每次模块调用时，提示词作为 `system` 角色消息传入，`payload` 的 JSON 序列化内容作为 `user` 角色消息传入，要求 LLM 严格输出 JSON。

---

## 9. LLM 客户端

**源文件**：`src/agentclinic_tree_dx/llm_client.py`

**实现**：`OpenAILLMClient`，基于 OpenAI Responses API（`client.responses.create`），使用 `json_object` 格式确保输出为合法 JSON。

**默认模型**：`gpt-4.1-mini`

**使用前提**：环境变量中需设置 `OPENAI_API_KEY`。

**调用示例**：
```python
from agentclinic_tree_dx.llm_client import OpenAILLMClient
llm = OpenAILLMClient(model="gpt-4.1-mini")
# 在控制器初始化时传入
controller = AgentClinicTreeController(env=env, llm=llm)
```

**与 Mock 环境的区别**：若控制器初始化时**不**传入 `llm`，则所有模块调用都走 `env.call_module()`，需要在环境的 `module_responses` 字典中注入确定性响应。这是测试时的常用方式。

---

## 10. 外部项目集成

### 10.1 AgentClinic 集成

**上游项目**：https://github.com/SamuelSchmidgall/AgentClinic.git

**本项目角色**：作为"医生智能体（Doctor Agent）"与 AgentClinic 的患者智能体（Patient Agent）和测量智能体（Measurement Agent）交互。

**接口兼容性**：

`AgentClinicEnv` 同时支持两套接口：

| 操作 | 本项目原生接口 | AgentClinic 上游接口 |
|-----|--------------|-------------------|
| 向患者提问 | `answer_question(question)` | `inference_patient(question)` |
| 执行测量/检验 | `perform_test(test_type, request)` | `inference_measurement(request)` |

**快速接入步骤**：

```bash
# 1. 克隆两个仓库
git clone https://github.com/SamuelSchmidgall/AgentClinic.git

# 2. 创建共享虚拟环境
python -m venv .venv && source .venv/bin/activate

# 3. 安装依赖
pip install -r AgentClinic/requirements.txt
pip install -e ./agentclinic-tree-dx

# 4. 设置 PYTHONPATH
export PYTHONPATH="$PYTHONPATH:$PWD/AgentClinic"
```

**集成代码示例**：

```python
from agentclinic import ScenarioLoaderMedQA, PatientAgent, MeasurementAgent
from agentclinic_tree_dx.adapters.agentclinic_env import AgentClinicEnv
from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.llm_client import OpenAILLMClient
from agentclinic_tree_dx.state import DiagnosticState

# 加载 AgentClinic 场景和智能体
loader = ScenarioLoaderMedQA()
scenario = loader.get_scenario(id=0)
patient = PatientAgent(scenario=scenario, backend_str="gpt4o")
measurement = MeasurementAgent(scenario=scenario, backend_str="gpt4o")

# 创建环境适配器
env = AgentClinicEnv(
    case_id="agentclinic-medqa-0",
    initial_summary="Interactive AgentClinic case.",
    patient_agent=patient,
    tester_agent=measurement,
)

# 运行控制器
controller = AgentClinicTreeController(
    env=env,
    llm=OpenAILLMClient(model="gpt-4.1-mini"),
    config=ControllerConfig(execution_mode="agentclinic_physician_patch"),
)
result = controller.run(DiagnosticState(case_id="agentclinic-medqa-0"))
print(result["benchmark_output"])  # "Diagnosis Ready: <diagnosis>"
```

### 10.2 SDBench 集成

**上游项目**：https://github.com/The-Swarm-Corporation/Open-MAI-Dx-Orchestrator

**本项目角色**：通过 Gatekeeper 接口（ASK/TEST/DIAGNOSE）与 SDBench 基准平台交互。

**Gatekeeper 接口支持**：

`SDbenchEnv` 支持以下接口变体（自动探测）：

| 操作 | 首选接口 | 备选接口 |
|-----|---------|---------|
| 获取案例摘要 | `get_case_abstract()` | `get_initial_case_info()` / `initial_case_info` |
| 提问 | `ask(question)` | `ask_question(question)` |
| 请求检验 | `test(name)` | `order_test(name)` |
| 提交诊断 | `diagnose(diagnosis)` | `submit_diagnosis(diagnosis)` |

**快速接入步骤**：

```bash
pip install mai-dx
pip install -e .
```

**直接接入（Gatekeeper 方法存在时）**：

```python
from agentclinic_tree_dx.adapters.sdbench_env import SDbenchEnv
from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.llm_client import OpenAILLMClient
from agentclinic_tree_dx.state import DiagnosticState

gatekeeper = your_upstream_gatekeeper_object  # 需要提供 ask/test/diagnose 方法
env = SDbenchEnv(case_id="sdbench-case-1", gatekeeper=gatekeeper)

controller = AgentClinicTreeController(
    env=env,
    llm=OpenAILLMClient(),
    config=ControllerConfig(execution_mode="sdbench_patch"),
)
result = controller.run(DiagnosticState(case_id="sdbench-case-1"))
print(result["diagnosis"])
```

**若只有独立的患者/测量智能体**，使用 `GatekeeperFacade` 适配：

```python
class GatekeeperFacade:
    def __init__(self, case_abstract, patient_agent, measurement_agent, diagnosis_submitter):
        self._case_abstract = case_abstract
        self.patient_agent = patient_agent
        self.measurement_agent = measurement_agent
        self.diagnosis_submitter = diagnosis_submitter

    def get_case_abstract(self):
        return self._case_abstract

    def ask(self, question: str):
        return self.patient_agent.answer(question)

    def test(self, test_name_or_panel: str):
        return self.measurement_agent.run(test_name_or_panel)

    def diagnose(self, diagnosis: str):
        return self.diagnosis_submitter.submit(diagnosis)
```

**接口名称不匹配时**，使用可调用钩子（无需包装类）：

```python
env = SDbenchEnv(
    case_id="sdbench-case-1",
    gatekeeper=your_gatekeeper_object,
    case_summary_getter=lambda gk: gk.summary_text,
    ask_fn=lambda gk, q: gk.query(q),
    test_fn=lambda gk, t: gk.run_test(t),
    diagnose_fn=lambda gk, dx: gk.finalize(dx),
)
```

---

## 11. 适配器层（Adapters）

### 11.1 AgentClinicEnv

**源文件**：`src/agentclinic_tree_dx/adapters/agentclinic_env.py`

面向 AgentClinic 基准的环境适配器。需要注入 `patient_agent`（提供 `answer_question` 或 `inference_patient`）和 `tester_agent`（提供 `perform_test` 或 `inference_measurement`）。`moderator_agent` 可选，用于对最终输出进行审核。

### 11.2 SDbenchEnv

**源文件**：`src/agentclinic_tree_dx/adapters/sdbench_env.py`

面向 SDBench Gatekeeper 接口的环境适配器。支持多种接口命名变体和可调用钩子。

### 11.3 StaticQAEnv

**源文件**：`src/agentclinic_tree_dx/adapters/static_qa_env.py`

面向静态选择题任务的环境适配器。需要在构造时提供 `vignette`（案例文本）、`question`（问题）和 `options`（选项列表）。无需患者/测量智能体。

### 11.4 MockAgentClinicEnv

**源文件**：`src/agentclinic_tree_dx/adapters/mock_env.py`

测试专用 Mock 适配器。通过 `module_responses` 字典注入各模块的确定性响应（可为固定字典或可调用函数）。所有 `ask_patient`、`request_exam` 等调用均记录在内部列表中，便于测试断言。

---

## 12. 工具路由模块

### 12.1 calculator_router

**源文件**：`src/agentclinic_tree_dx/tools/calculator_router.py`

**当前状态**：占位实现（`naive_calculator_router`），接收内容字符串和状态，返回空字典或固定响应，不执行实际计算。

**规格要求**（待实现）：
- 解析计算请求（如 Wells Score、CURB-65 等临床评分）
- 从当前状态提取所需输入变量
- 执行计算并返回结构化结果

### 12.2 knowledge_router

**源文件**：`src/agentclinic_tree_dx/tools/knowledge_router.py`

**当前状态**：占位实现（`naive_knowledge_router`），直接返回空结果，不执行实际检索。

**规格要求**（待实现）：
- 接收知识检索查询字符串
- 查询外部医学知识库（如 UpToDate、PubMed 摘要等）
- 返回结构化知识文本

---

## 13. 测试体系

测试位于 `tests/` 目录，使用 pytest 框架。运行方式：

```bash
# 安装项目（开发模式）
pip install -e .

# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_controller.py -v
```

| 测试文件 | 覆盖内容 |
|---------|---------|
| `test_state.py` | 状态数据类的基本构造和序列化 |
| `test_controller.py` | 控制器端到端主循环（使用 Mock 环境） |
| `test_update_router.py` | 更新路由策略选择逻辑 |
| `test_agentclinic_env.py` | AgentClinicEnv 适配器接口兼容性 |
| `test_sdbench_mode.py` | SDBench 模式动作映射和辩论流程 |
| `test_static_qa_mode.py` | Static QA 模式文本解析和答案映射 |
| `test_llm_path.py` | LLM 客户端路径（通常需要真实 API 密钥） |
| `test_patch_mode.py` | AgentClinic Physician Patch 模式就绪度门控逻辑 |

---

## 14. 安装与运行

### 14.1 安装

```bash
# 克隆项目
git clone <this-repo-url>
cd agentclinic-tree-dx

# 创建虚拟环境（Python 3.10+）
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或 .venv\Scripts\activate  # Windows

# 安装项目
pip install -e .

# 设置 OpenAI API Key
export OPENAI_API_KEY="sk-..."
```

### 14.2 最小运行示例（Mock 环境）

```python
from agentclinic_tree_dx.adapters.mock_env import MockAgentClinicEnv
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import DiagnosticState

# 注入确定性响应
module_responses = {
    "SafetyController": {"interrupt_active": False, "reason": "stable", "required_actions": []},
    "RootSelector": {
        "root_label": "acute chest pain syndrome",
        "time_course": "hours",
        "supporting_facts": ["substernal pain"],
        "excluded_root_candidates": [],
        "confidence": 0.7,
        "need_external_knowledge": False,
    },
    # ... 其余模块响应
    "FinalAggregator": {
        "final_mode": "ranked_working_differential",
        "leading_diagnosis_or_parent": "acute coronary syndrome",
        # ...
    }
}

env = MockAgentClinicEnv(module_responses=module_responses)
controller = AgentClinicTreeController(env=env)
result = controller.run(DiagnosticState(case_id="demo"))
```

### 14.3 LLM 驱动运行示例

```python
from agentclinic_tree_dx.adapters.mock_env import MockAgentClinicEnv
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.llm_client import OpenAILLMClient
from agentclinic_tree_dx.state import DiagnosticState

env = MockAgentClinicEnv(module_responses={})
llm = OpenAILLMClient(model="gpt-4.1-mini")
controller = AgentClinicTreeController(env=env, llm=llm)
result = controller.run(DiagnosticState(case_id="demo"))
```

---

## 15. 当前实现状态与差距分析

### 15.1 已完整实现

| 功能 | 文件 |
|-----|------|
| 核心状态数据类（含扩展字段） | `state.py` |
| 控制器主循环（四种模式） | `controller.py` |
| 序数概率更新器 | `updater.py` |
| 更新路由策略（逻辑层） | `update_router.py` |
| AgentClinic 环境适配器（含双接口兼容） | `adapters/agentclinic_env.py` |
| SDBench 环境适配器（含接口变体探测） | `adapters/sdbench_env.py` |
| 静态 QA 环境适配器 | `adapters/static_qa_env.py` |
| Mock 环境适配器（测试用） | `adapters/mock_env.py` |
| LLM 客户端（OpenAI Responses API） | `llm_client.py` |
| 提示词加载映射（22 个模块） | `prompting.py` |
| 提示词文件（21 个 .txt） | `prompts/` |
| 动作类型规范化（三种模式） | `controller.py` |
| 诊断就绪度门控（Patch 模式） | `controller.py` |
| SDBench Top-3 前沿限制 | `controller.py` |
| SDBench 多角色辩论流程 | `controller.py` |
| Static QA 文本解析 + 答案映射流程 | `controller.py` |
| 轮次预算强制终止 | `controller.py` |
| 分支差异历史记录 | `controller.py` |
| pytest 测试集（8个测试文件） | `tests/` |

### 15.2 已实现框架但内容为占位（Placeholder）

| 功能 | 状态说明 |
|-----|---------|
| calculator 更新路径 | 路由逻辑已实现，但 `apply_probability_update` 中 calculator 分支仍走序数更新 |
| rule_based 更新路径 | 同上，rule_based 分支也走序数更新 |
| `naive_calculator_router` | 返回空结果，不执行实际临床评分计算 |
| `naive_knowledge_router` | 返回空结果，不执行实际知识检索 |
| 各个薄封装模块 | `branch_manager.py`、`leaf_planner.py`、`executor.py` 等多为薄封装，实际逻辑在控制器和提示词中 |

### 15.3 规格文档中定义但代码中尚未实现

| 功能 | 所在规格 | 优先级建议 |
|-----|---------|----------|
| 祖先节点概率重新计算（major_update=True 时） | `readme.md` §9.8 | 高 |
| 分支重开触发机制（非通过 LLM，而是条件检测） | `readme.md` §9.8 | 高 |
| 计算器真实实现（Wells Score、CURB-65 等） | `readme.md` §6, §9.4 | 中 |
| 知识检索真实实现 | `readme.md` §6 | 中 |
| 多层级分支树（目前仅有一层 ROOT→Branch） | `readme.md` §4.1 | 中 |
| AgentClinic 评估完整对接（评分上报） | `agentclinic_patch_development_documentation.md` | 中 |
| SDBench 评估完整对接（评分上报） | `sdbench_tree_dx_spec.md` | 中 |
| 回归测试套件（代表性案例） | `readme.md` §13, Milestone 4 | 低 |
| 追踪日志（trace logging） | `readme.md` §13, Milestone 3 | 低 |

### 15.4 仓库结构差异

规格文档中描述的部分目录/文件在当前代码库中**不存在**：

- `docs/spec.md`、`docs/prompt_contracts.md`、`docs/json_schemas.md`
- `tests/test_branch_revision.py`、`tests/test_interrupts.py`
- `tests/fixtures/`
- 根目录级别的 `requirements.txt`（当前依赖由 `pyproject.toml` 管理）

---

## 16. 后续开发指引

### 16.1 优先级排序建议

**第一优先级（核心算法完整性）**：

1. **实现真实的 calculator_update 和 rule_based_update**：目前这两条路径是死代码，需要在 `updater.py` 中实现 Bayes 更新或临床规则应用，并在 `apply_probability_update` 中正确分发。

2. **实现 major_update 时的祖先重计算**：在 `annotation["major_update"] = True` 时，当前代码没有触发额外的祖先节点概率修订。需要在 `revise_branch_states` 之后增加 `recompute_ancestors` 逻辑。

3. **实现分支重开的条件检测**：目前分支重开完全依赖 `PostUpdateStateReviser` 模块的 LLM 判断，缺少如规格中所述的确定性规则（如 `annotation["reopen_candidates"]` 非空时触发重开）。

**第二优先级（工具与评估）**：

4. **实现知识路由器**：接入医学知识 API（如 PubMed Entrez、UpToDate 接口），使 `RETRIEVE_KNOWLEDGE` 动作真正有效。

5. **实现计算器路由器**：实现常用临床评分（Well's DVT、CURB-65、HEART Score 等），使 `USE_CALCULATOR` 动作真正有效。

6. **完整端到端对接 AgentClinic 和 SDBench 基准**：按照 `agentclinic_upstream_setup.md` 和 `sdbench_upstream_setup.md` 完成完整的运行和评分流程验证。

**第三优先级（工程质量）**：

7. **补充测试**：增加 `test_branch_revision.py`（多种状态转移组合）、`test_interrupts.py`（紧急中断流程）。

8. **追踪日志**：在控制器每个阶段的关键决策点添加结构化日志（至少记录：使用的更新方法、分支状态转移、终止类型）。

9. **多层级分支树支持**：目前分支树只有 ROOT → Level-1 分支，规格允许进一步向下展开子分支（`expand_now` 时创建子分支）。

### 16.2 关键代码位置速查

| 想修改的功能 | 对应文件 | 关键行 |
|------------|---------|--------|
| 概率更新逻辑 | `updater.py` | 全文件 |
| 概率更新调用分发 | `controller.py` | `apply_probability_update()` |
| 模式判断与分支逻辑 | `controller.py` | `run()` 主循环 |
| 动作类型到外部接口映射 | `controller.py` | `execute_primary_action()` |
| 诊断就绪度门控逻辑 | `controller.py` | `check_diagnosis_readiness()` |
| 各模块的 LLM 提示词 | `prompts/*.txt` | 各文件 |
| LLM 调用参数（模型、格式） | `llm_client.py` | `call_module()` |
| AgentClinic 接口适配 | `adapters/agentclinic_env.py` | `ask_patient()`, `_run_measurement()` |
| SDBench 接口适配 | `adapters/sdbench_env.py` | `ask_gatekeeper()`, `request_test()`, `submit_diagnosis()` |
| 计算器实现 | `tools/calculator_router.py` | 全文件（待实现） |
| 知识检索实现 | `tools/knowledge_router.py` | 全文件（待实现） |

### 16.3 开发里程碑对照

| 里程碑 | 内容 | 当前状态 |
|-------|------|---------|
| M1：基础框架 | 状态模型、控制器骨架、Mock 环境、提示词接口、序数更新 | **已完成** |
| M2：算法完整性 | 计算器路由、知识路由、中断控制器、重开逻辑、祖先重计算 | **部分完成**（中断控制器已完成，其余待实现） |
| M3：基准对接 | AgentClinic/SDBench 适配器、提示词调优、追踪日志、评估工具 | **部分完成**（适配器已完成，日志和评估待完善） |
| M4：评估与消融 | 代表性案例回归测试、失效模式分析、停止策略消融 | **未开始** |

---

*文档生成时间：2026-04-28*  
*基于代码分支：`codex/verify-agentclinic-compatibility-with-projects`*
