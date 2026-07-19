# Agentic RAG 控制机制参考手册

> **版本**: v1.0 | **日期**: 2026-05-22
> **定位**: 作为 `EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md`（知识层方案）的**后备解决方案库**——当外部知识层构建受阻（数据源不可用、覆盖不足、集成成本过高）时，可从本文档中选取纯架构层面的 Agentic 控制机制，独立改善系统表现。
>
> **核心观点**: Agentic 控制机制与外部知识层是**正交**的两个改进维度。前者解决"如何更好地使用知识"，后者解决"知识本身的来源"。即使没有外部知识层，P0 优先级的 Agentic 机制仍可显著降低证据锚定和鉴别遗漏。

---

## 一、Agentic RAG 的七种通用控制机制

> 来源：Agentic RAG Survey (arXiv 2501.09136), SoK (arXiv 2603.07379), Self-RAG (ICLR 2024), CRAG (2024), CtrlA (ACL 2025), MemR3 (NeurIPS 2025), PAR²-RAG (2025)

### 1.1 Adaptive Retrieval Decision（自适应检索决策）

**控制的问题**：是否需要检索——不是每次都检索，而是先判断 LLM 自身知识是否足够。

**实现方式**：
- **Self-RAG**：训练特殊 `[Retrieve]` token，让模型自主决定何时触发检索
- **CtrlA**：通过 LLM 内部表征的"诚实度/置信度方向"判断是否需要外部知识
- **Adaptive RAG**：用分类器评估查询复杂度——简单查询直接回答，复杂查询多步检索

**我们的现状**：不存在。TALP 每轮固定生成候选动作，从未判断"是否需要外部知识辅助"。

**可借鉴方式**（优先级 P2）：在知识层集成后，Controller 在调用知识检索前增加轻量判断——如果当前分支对的鉴别特征已在 DxS 索引中完全覆盖且已分析完毕，跳过知识检索。可减少不必要的 token 开销。

---

### 1.2 Query Routing（查询路由）

**控制的问题**：检索哪个来源——根据查询类型将请求路由到最合适的数据源。

**实现方式**：
- **Single-Agent Router**：一个协调 agent 分析查询后选择 SQL / 语义搜索 / Web / 推荐系统
- **Hierarchical RAG**：顶层 agent 评估查询复杂度后将子任务委派给专科 agent

**我们的现状**：不存在。所有知识层（DxS / UMLS / LR Cache / RAG）尚未实现，更无路由。

**可借鉴方式**（优先级 P1）：已在知识层方案中设计为"层间协作流程"——Layer 0 (DxS 差集) → Layer 1 (UMLS) → Layer 2 (LR Cache) → Layer 3 (RAG) 的升级路由。在 `DxFeatureRetriever` 和 `LRRetriever` 中内嵌路由逻辑。

---

### 1.3 Corrective Retrieval（纠正性检索）

**控制的问题**：检索到的内容质量够吗？如果不够怎么办？

**实现方式**：
- **CRAG**：由 5 个 agent 组成——Context Retrieval → Relevance Evaluation → Query Refinement → External Knowledge Retrieval → Response Synthesis。评估低于阈值则重写查询 + 补充检索
- **Self-correcting Agentic GraphRAG**：retrieve-evaluate-refine 循环

**我们的现状**：部分存在但很弱。EvidenceAnnotator 评估证据对分支的影响，但不评估 TALP 候选动作本身的质量。如果 TALP 生成的候选全部引用同一个证据（"35% blasts"），无机制检测并纠正。

**可借鉴方式**（优先级 P0）：
```
当前流程:
  TALP 生成候选 → Bundler 筛选 → 执行 → Annotator 评估
                                    ↓
                              （无反馈循环）

改进后:
  TALP 生成候选 → CandidateQualityJudge → 通过? → Bundler → 执行
                         ↓ 不通过
                  识别问题（如证据过度重复）
                         ↓
                  注入 discriminator_hints
                         ↓
                  TALP 重新生成（带 hints）
```

**独立实现方案**（无需知识层）：`CandidateQualityJudge` 可仅基于统计规则实现：
- 规则 1：如果 >50% 候选引用同一证据项 → 判定"证据锚定"，拒绝并要求 TALP 重生成
- 规则 2：如果所有候选的 `target_branches` 都指向同一分支 → 判定"分支覆盖不足"
- 规则 3：如果候选内容与 `actions_taken` 中已执行动作的语义相似度 >0.8 → 判定"重复动作"

---

### 1.4 Evidence Sufficiency Judge（证据充分性判断）

**控制的问题**：已收集的证据足够做出诊断了吗？还需要继续？

**实现方式**：
- **SEMA-RAG E-Agent**：每轮检索后预测 `(sufficiency_flag, gap_description, next_queries)`
- **MemR3**：维护 global evidence-gap tracker，透明追踪"已有/缺失"
- **PAR²-RAG**：breadth-first anchoring → evidence sufficiency control → depth-first commitment

**我们的现状**：TerminationJudge 判断是否终止诊断，但只是二元决策（继续/终止），不分析"缺少什么"。

**可借鉴方式**（优先级 P0）：

**独立实现方案**（无需知识层）：增加 `EvidenceSufficiencyCheck` 模块，在每轮 Annotator 之后调用：
```python
class EvidenceSufficiencyCheck:
    """分析当前证据覆盖的缺口，输出反馈给下一轮 TALP。"""
    
    def check(self, state) -> dict:
        # 输入：当前分支列表、已分析证据、vignette 全部证据
        # 输出：
        return {
            "sufficient": False,
            "coverage": 0.42,       # 已分析证据 / 全部可用证据
            "gaps": [
                "E4 (weight loss) 与 E11 (visual acuity loss) 未被任何动作分析",
                "分支 B1.2 CML-BC 缺少挑战性证据",
                "当前 5 轮中 3 轮引用了 E17 (35% blasts)——该证据已充分利用"
            ],
            "suggested_focus": [
                "优先分析 E4, E11, E13 等未使用证据",
                "生成针对 B1.2 vs B1.1 的鉴别性候选"
            ]
        }
```

此模块的 `gaps` 和 `suggested_focus` 直接注入下一轮 TALP 的 prompt，替代当前的固定模板。即使没有 DxS 索引，纯粹基于"已用/未用证据追踪"也能显著改善证据利用率。

---

### 1.5 Reflection / Self-Critique（反思/自我批评）

**控制的问题**：我的推理过程和输出有没有问题？

**实现方式**：
- **Self-RAG**：生成 critique tokens（`[IsRel]`、`[IsSup]`、`[IsUse]`）评估相关性、支持性、有用性
- **CRITIC**：agent 对自己的输出进行自我批评，然后修正
- **Reflexion**：从失败尝试中提取经验教训，存入记忆用于后续

**我们的现状**：EvidenceAnnotator 对执行结果做"反思"（评估证据影响），但 TALP 自身无反思——不知道"我上一轮的候选中 86% 引用了同一证据"。

**可借鉴方式**（优先级 P1）：

**独立实现方案 A——TALP 内部 self-critique**：
在 TALP prompt 末尾追加自审查指令：
```
Before finalizing candidates, perform a SELF-CHECK:
1. Count how many candidates reference E17 (blasts). If >2, replace excess with
   candidates analyzing OTHER evidence items.
2. Verify that at least 1 candidate targets the SECOND-ranked branch, not just
   the leader.
3. Ensure challenge candidates propose SPECIFIC alternative explanations, not
   generic "No contradicting evidence identified".
```

**独立实现方案 B——跨轮 Reflexion 记忆**：
在 Controller 中维护一个滚动的 `reflexion_memory`：
```python
reflexion_memory = []
# 每轮 Annotator 后追加
if annotator_result.evidence_already_saturated:
    reflexion_memory.append(
        f"Round {round}: E17 (35% blasts) has been analyzed 3 times. "
        f"Its discriminative value is exhausted. Do NOT generate candidates "
        f"referencing this evidence again."
    )
# 注入下一轮 TALP prompt
talp_payload["reflexion_notes"] = reflexion_memory[-3:]  # 保留最近 3 条
```

---

### 1.6 Query Decomposition / Planning（查询分解/规划）

**控制的问题**：复杂查询如何拆解为子步骤？

**实现方式**：
- **SEMA-RAG I-Agent**：将问题映射为 `(clinical_intent, entities, constraints, initial_query)` 四元组
- **Deep-DxSearch**：5 种动作模式的序列规划
- **PAR²-RAG**：breadth-first anchoring → depth-first refinement 两阶段

**我们的现状**：已较好实现。BranchCreator → TALP → Bundler Phase 1/1b/2 本身就是分层规划。

**可借鉴方式**（优先级 P3）：可在 VignetteParser 阶段增加临床 Schema 四元组提取。

---

### 1.7 Multi-Agent Collaboration（多 Agent 协作）

**控制的问题**：不同类型的任务由谁负责？如何协调？

**实现方式**：
- **SEMA-RAG**：3 agent（Interpreter / Explorer / Arbiter）
- **MEDDxAgent**：DDxDriver + History-taking + Knowledge Retrieval + Diagnosis Strategy
- **KG4Diagnosis**：GP Agent → Specialist Agent 层级

**我们的现状**：已天然实现（BranchCreator / TALP / Bundler / EvidenceAnnotator / TerminationJudge / AnswerMapper）。

**可借鉴方式**（优先级 P3）：强化每个模块 prompt 中的角色边界声明。

---

## 二、文档中六个临床 Agentic 系统的逐一解析

### 2.1 MedKGI（NeurIPS 2024）—— KG 约束 + 信息增益引导

#### Agentic 控制架构

```
患者主诉 → [实体提取 & KG 对齐] → 诊断子图 G_sub
                                      │
                ┌─────────────────────┤
                │                     │
                ▼                     ▼
    信息增益计算 IG(s)        后验概率更新 P(D|S_pos, S_neg)
    选择 IG 最大的症状             贝叶斯更新
                │                     │
                ▼                     ▼
    生成自然语言提问 ────────→ 患者回复 → OSCE 记录更新
                                      │
                                      ▼
                              终止? (熵 < 阈值)
                              是 → 输出诊断
                              否 → 循环
```

#### 三个控制点

| 控制点 | 机制 | 公式 |
|--------|------|------|
| **候选约束** | 仅允许询问 KG 子图 `G_sub` 中存在的症状节点 | `G_sub = ∪{Di} ∪ N(Di)`, 候选 ∈ `V_sub \ S_observed` |
| **最优选择** | 选择信息增益最大的症状 | `IG(s) = H(D) - [P(s)·H(D|s) + P(¬s)·H(D|¬s)]` |
| **后验更新** | 贝叶斯条件更新 | `P(Di|S) = P(S|Di)·P(Di) / ΣP(S|Dj)·P(Dj)` |
| **终止决策** | 诊断熵低于阈值或达最大轮数 | `H(D) < ε` 或 `t = T_max` |

#### 可借鉴之处

| 机制 | 映射到我们的模块 | 具体方案 | 知识层依赖 |
|------|---------------|---------|:--------:|
| KG 子图约束 | TALP 候选范围 | 用 DxS 差集或 UMLS 子图约束 TALP 只生成涉及未检查鉴别表型的候选 | 需要 Layer 0/1 |
| IG 精确计算 | Bundler 的 `ExpectedInformationGain` | 从 LLM 估计改为基于差集的精确 IG 计算 | 需要 Layer 0 |
| 贝叶斯后验 | `updater.py` 的 `ordinal_update` | 从固定乘法权重改为条件概率 + 贝叶斯更新 | **无需** |
| **IG 简化版（无需知识层）** | TALP + Bundler | 仅基于"该候选覆盖的分支数 × 每分支当前不确定度"做近似 IG 排序 | **无需** |

---

### 2.2 Deep-DxSearch（arXiv 2508.15746, 2025）—— RL 端到端动作策略

#### Agentic 控制架构

```
患者临床表现 P
        │
        ▼
┌─ LLM Agent (策略 π_θ) ─────────────────────┐
│                                              │
│  选择动作类型 α ∈ {reason, lookup,           │
│                     match, search, diagnose} │
│  生成文本规格 τ                               │
│                                              │
│  a_t = (α_t, τ_t)                           │
└──────────────┬───────────────────────────────┘
               │
      ┌────────┼────────┐
      │        │        │
  α=reason  α=lookup  α=match   α=search    α=diagnose
  (内部推理)  (查指南)  (匹配病例)  (文献检索)   (输出诊断)
      │        │        │          │              │
      └────────┼────────┘          │              │
               │                   │              │
               ▼                   ▼              ▼
        环境反馈 f_t          环境反馈 f_t      终止
               │                   │
               └─────────┬─────────┘
                         │
                  4 维奖励: Rwd(format, retrieval, reasoning, accuracy)
                         │
                    PPO 策略更新
```

#### 五个控制点

| 控制点 | 机制 | 特色 |
|--------|------|------|
| **动作类型选择** | Agent 在 5 种动作中自主选择 | 不固定顺序，自由交替 |
| **查询内容生成** | Agent 生成每种动作的文本规格 | 如 lookup 的疾病名、search 的关键词 |
| **检索-推理交替** | 不预设流程，agent 自由编排 | RL 训练后涌现出有效策略 |
| **终止决策** | Agent 自主决定何时输出 `<diagnose>` | 避免过早/过晚终止 |
| **RL 奖励塑造** | 4 维奖励联合优化 | 格式 + 检索质量 + 推理组织 + 诊断准确 |

#### 可借鉴之处

| 机制 | 映射到我们的模块 | 具体方案 | 知识层依赖 |
|------|---------------|---------|:--------:|
| 多种动作类型 | TALP | 扩展为 `{analyze, lookup_guideline, compare_branches}` 多类型候选 | 需要 Layer 0 |
| 自由交替 | Controller 主循环 | 允许某些轮次执行"回顾性推理"（不收集新证据，而是重新评估已有证据） | **无需** |
| **4 维评估分解（无需知识层）** | 评估体系 | 将诊断准确率拆分为：分支覆盖率 + 证据多样性 + 标签校准度 + 最终准确率 | **无需** |

---

### 2.3 SEMA-RAG（arXiv 2605.17101, 2026）—— 任务解耦 + 充分性自演进

#### Agentic 控制架构

```
输入问题 Q
    │
    ▼
┌─ I-Agent (Interpreter) ─────────────────────┐
│  输出: Q' = (intent, entities, constraints,  │
│              initial_query)                   │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌─ E-Agent (Explorer) ─────────────────────────┐
│  初始查询 q_init → TopK 检索 → 累积证据 C_t  │
│                                               │
│  每轮: E-Agent 判断 →                        │
│    s_t = 1 (sufficient) → 终止，传给 A-Agent │
│    s_t = 0 (insufficient) →                  │
│      输出 gap_description g_t                │
│      生成 next_queries Q_{t+1}               │
│      → 继续检索                              │
│                                               │
│  终止条件: s_t=1 或 t=T_max 或 Q_{t+1}=∅    │
└──────────────┬───────────────────────────────┘
               │ 收敛证据集 C*
               ▼
┌─ A-Agent (Arbiter) ──────────────────────────┐
│  去重 → 识别矛盾 → 组织支持/反对证据        │
│  → 结构化报告 R → 基于 R 选择答案            │
└──────────────────────────────────────────────┘
```

#### 三个控制点

| 控制点 | 机制 | 公式/逻辑 |
|--------|------|----------|
| **临床 Schema 结构化** | I-Agent 将问题映射为四元组 | `Q' = (o_int, o_ent, o_cons, q_init)` |
| **充分性驱动循环** | E-Agent 每轮输出 `(s_t, g_t, Q_{t+1})` | `s_t ∈ {0,1}`; `s_t=0` → 继续; `s_t=1` → 终止 |
| **证据裁决** | A-Agent 生成结构化报告后选答案 | 去重 + 矛盾识别 + 支持/反对组织 |

#### 可借鉴之处

| 机制 | 映射到我们的模块 | 具体方案 | 知识层依赖 |
|------|---------------|---------|:--------:|
| **E-Agent 充分性标志** | TALP + TerminationJudge | 每轮后增加 `EvidenceSufficiencyCheck`，gap 输出注入下一轮 TALP | **无需** |
| **gap → 新查询生成** | TALP 下一轮输入 | gap="未检查 basophilia" → TALP prompt 显式要求生成关于此的候选 | **无需** |
| I-Agent 四元组 | VignetteParser | 增加 `{主诉, 关键发现, 约束条件, 时间线}` 结构化提取 | **无需** |
| A-Agent 裁决报告 | EvidenceAnnotator | 强化为"支持/反对/矛盾"结构化报告（已部分实现 per_action_effects） | **无需** |

---

### 2.4 Self-correcting Agentic GraphRAG（Frontiers in Medicine 2025）

#### Agentic 控制架构

```
查询 → [Retrieve] 图遍历检索
            │
            ▼
       [Evaluate] Agent 评估检索质量
            │
      ┌─────┴─────┐
    通过          不通过
      │             │
      ▼             ▼
   生成答案    [Refine] 优化图搜索策略
                    │
                    └─→ 重新 Retrieve
```

**达成指标**：Faithfulness 0.94, Context Recall 0.92, Answer Relevancy 0.91

#### 可借鉴之处

| 机制 | 映射到我们的模块 | 具体方案 | 知识层依赖 |
|------|---------------|---------|:--------:|
| **Evaluate 环节** | Bundler 之后 | `BundleQualityEvaluator`：检查 bundle 证据重复率、分支覆盖率 | **无需** |
| **Refine 环节** | TALP 重生成 | 低质量 bundle 触发 TALP 带 hints 重生成，而非执行低质量 bundle | **无需** |

---

### 2.5 MedRAG（arXiv 2502.04413, 2025）—— KG 增强的层次化检索

#### Agentic 控制架构

```
临床表现 → 层次化诊断 KG 检索
               │
         ┌─────┼─────┐
         │     │     │
      疾病层  症状层  检查层
         │     │     │
         └─────┼─────┘
               │
               ▼
         动态 KG-EHR 联合检索
         (KG 提供鉴别关键差异 + EHR 提供相似病例)
               │
               ▼
         LLM 综合推理 → 诊断
```

#### 可借鉴之处

| 机制 | 映射到我们的模块 | 具体方案 | 知识层依赖 |
|------|---------------|---------|:--------:|
| 鉴别关键差异标注 | DxDiscriminatorIndex | DxS 差集 + LR 权重标注 | 需要 Layer 0+2 |
| **层次化组织思想（无需知识层）** | 证据内部组织 | 将 vignette 证据按"症状/体征/检验/影像"分层，TALP 每层至少选 1 个证据 | **无需** |

---

### 2.6 MedGraphRAG（ACL 2025）—— Triple Graph + U-Retrieval

#### Agentic 控制架构

```
用户文档 ─────────────── Triple Graph ─────────────── 权威来源
    │                        │                           │
    │    ┌─── U-Retrieval ───┤                           │
    │    │                   │                           │
    │    ▼                   ▼                           │
    │  自底向上:          自顶向下:                       │
    │  精确节点索引       全局一致性精炼                   │
    │    │                   │                           │
    │    └─────────┬─────────┘                           │
    │              ▼                                     │
    └──────── 综合生成 ──────────────────────────────────┘
```

#### 可借鉴之处

| 机制 | 映射到我们的模块 | 具体方案 | 知识层依赖 |
|------|---------------|---------|:--------:|
| **U-Retrieval 双向思想（无需知识层）** | TALP 候选生成 | 自底向上：从 vignette 未用证据出发找对应分支；自顶向下：从分支差异出发找对应证据 | **无需** |

---

## 三、适配性评估矩阵

### 3.1 按控制机制维度

```
                  检索决策    查询路由    纠正性循环   充分性判断   反思/自批评   规划/分解
                 "是否检索"  "检索哪里"  "质量够吗"   "够了吗"    "我对吗"     "拆子步骤"
─────────────────────────────────────────────────────────────────────────────────────
MedKGI              -        KG子图         -       IG→熵阈值      -        KG子图约束
Deep-DxSearch     RL学习      5种动作        -       RL→diagnose   RL奖励      reason
SEMA-RAG            -        dense       E-Agent    E-Agent       A-Agent     I-Agent
Self-corr.GRAG      -        图遍历      Refine     Evaluate        -           -
MedRAG              -        KG+EHR         -           -           -       层次化KG
MedGraphRAG         -       U-Retrieval     -           -           -      Triple Graph
─────────────────────────────────────────────────────────────────────────────────────
我们当前              ✗          ✗           ✗      TermJudge     Annotator   Branch+TALP
                                                    (仅二元)      (仅证据)      (已有)
```

### 3.2 按对我们的优先级排列

| 优先级 | 来源系统 | 具体机制 | 我们借鉴什么 | 需要知识层? | 实现难度 |
|:------:|---------|---------|------------|:--------:|:------:|
| **P0** | SEMA-RAG | E-Agent 充分性标志 + gap → 新查询 | `EvidenceSufficiencyCheck` 模块，gap 输出注入 TALP | **否** | 低 |
| **P0** | CRAG / Self-corr. GRAG | 纠正性循环 | `CandidateQualityJudge`，低质量触发重生成 | **否** | 低 |
| **P0** | MedKGI | IG 约束选择 | DxS 差集约束 TALP 候选范围 + 精确 IG 排序 | 需 Layer 0 | 低 |
| **P1** | MedKGI | 贝叶斯后验更新 | `ordinal_update` → 贝叶斯更新 | **否** | 低 |
| **P1** | Self-RAG / Reflexion | 反思 + 跨轮记忆 | TALP self-check + `reflexion_memory` 滚动注入 | **否** | 低 |
| **P1** | Self-corr. GRAG | retrieve-evaluate-refine | `BundleQualityEvaluator` | **否** | 中 |
| **P2** | Deep-DxSearch | 多类型动作 + 自由交替 | TALP 多动作类型；Controller 允许"回顾性推理"轮 | 部分 | 中 |
| **P2** | SEMA-RAG | I-Agent 临床 Schema | VignetteParser 增加四元组结构化 | **否** | 低 |
| **P3** | MedGraphRAG | U-Retrieval 双向 | TALP 自底向上 + 自顶向下双向候选生成 | **否** | 低 |
| **P3** | Deep-DxSearch | 4 维评估分解 | 分支覆盖率 + 证据多样性 + 标签校准度 + 准确率 | **否** | 低 |

---

## 四、无需知识层即可实施的独立改进方案

以下方案**完全不依赖外部知识层**，可在当前代码基础上独立实施：

### 4.1 EvidenceSufficiencyCheck（来自 SEMA-RAG E-Agent）

**改动位置**：Controller 主循环，每轮 Annotator 之后、下一轮 TALP 之前

**输入**：`state.branches`, `state.evidence_records`, `state.vignette_evidence_items`

**输出**：`{sufficient, coverage, gaps, suggested_focus}`

**注入方式**：`suggested_focus` 直接写入下一轮 TALP payload 的新字段 `evidence_gaps`

**prompt 修改**（TALP）：
```
When evidence_gaps is provided, you MUST:
1. Generate at least 2 candidates that analyze evidence items mentioned in the gaps
2. Do NOT generate candidates that re-analyze evidence items listed as "already saturated"
3. Prioritize gaps marked as "high priority" over general candidates
```

### 4.2 CandidateQualityJudge（来自 CRAG Relevance Evaluation）

**改动位置**：Controller 主循环，TALP 生成候选之后、Bundler 之前

**规则（无需 LLM 调用）**：
```python
def judge_candidate_quality(candidates, actions_taken):
    evidence_counter = Counter()
    for c in candidates:
        for evidence_ref in extract_evidence_refs(c.content):
            evidence_counter[evidence_ref] += 1
    
    # 规则 1: 证据锚定检测
    max_ref = evidence_counter.most_common(1)
    if max_ref and max_ref[0][1] > len(candidates) * 0.5:
        return {"pass": False, "reason": f"evidence_anchoring:{max_ref[0][0]}"}
    
    # 规则 2: 分支覆盖检测
    targeted_branches = set()
    for c in candidates:
        targeted_branches.update(c.target_branches.keys())
    if len(targeted_branches) < 2:
        return {"pass": False, "reason": "single_branch_coverage"}
    
    # 规则 3: 与已执行动作的重复检测
    for c in candidates:
        for past in actions_taken:
            if semantic_similarity(c.content, past.content) > 0.85:
                return {"pass": False, "reason": f"duplicate_action:{past.id}"}
    
    return {"pass": True}
```

**不通过时的处理**：
1. 将 `reason` 翻译为 TALP 的约束指令
2. 重新调用 TALP（最多 1 次重试，防止循环）

### 4.3 Reflexion Memory（来自 Reflexion + Self-RAG）

**改动位置**：Controller，维护一个滚动列表 `state.reflexion_notes`

**追加时机**：每轮 Annotator 完成后

**追加内容**：
```python
# 证据饱和检测
for evidence_id, count in evidence_usage_counter.items():
    if count >= 3:
        state.reflexion_notes.append(
            f"Evidence {evidence_id} has been analyzed {count} times. "
            f"Its discriminative value is exhausted. Generate candidates "
            f"focusing on OTHER unused evidence."
        )

# 标签偏差检测
for branch_id, labels in branch_label_history.items():
    if all(l in ("moderate_for", "weak_for") for l in labels[-3:]):
        state.reflexion_notes.append(
            f"Branch {branch_id} has received only moderate/weak labels "
            f"for 3 consecutive rounds. Consider generating a STRONG "
            f"challenge or support candidate for this branch."
        )
```

**注入方式**：TALP payload 中追加 `reflexion_notes` 字段（保留最近 5 条）。

### 4.4 贝叶斯后验更新（来自 MedKGI）

**改动位置**：`updater.py`

**核心变更**：
```python
def bayesian_update(posteriors, branch_effects):
    """从 ordinal 乘法改为 odds-space 贝叶斯更新。"""
    # 将 ordinal labels 映射为 LR 近似值
    LR_MAP = {
        "strong_for": 5.0, "moderate_for": 2.0, "weak_for": 1.2,
        "neutral": 1.0,
        "weak_against": 0.8, "moderate_against": 0.5, "strong_against": 0.2,
    }
    for branch_id, label in branch_effects.items():
        lr = LR_MAP.get(label, 1.0)
        # odds-space 更新
        prior_odds = posteriors[branch_id] / (1 - posteriors[branch_id] + 1e-9)
        posterior_odds = prior_odds * lr
        posteriors[branch_id] = posterior_odds / (1 + posterior_odds)
    # 归一化
    total = sum(posteriors.values())
    for k in posteriors:
        posteriors[k] /= total
    return posteriors
```

---

## 五、实施路线图

```
Week 0 (1-2 天)
├── 4.3 Reflexion Memory（最小改动，仅 Controller + TALP prompt）
└── 4.4 贝叶斯后验更新（仅 updater.py）

Week 1 (3-5 天)
├── 4.1 EvidenceSufficiencyCheck（新模块 + Controller 集成 + TALP prompt）
└── 4.2 CandidateQualityJudge（新模块 + Controller 集成）

Week 1 末: 冒烟测试验证以上 4 项改进的联合效果

Week 2+ (与知识层 Phase 1 并行)
├── MedKGI 式 IG 约束（需要 DxS 差集索引）
└── 多类型动作（如 lookup_guideline）
```

---

## 六、参考文献

1. Singh et al. "Agentic RAG: A Survey on Agentic RAG." arXiv 2501.09136, 2025.
2. SoK: Agentic RAG Taxonomy. arXiv 2603.07379, 2026.
3. Asai et al. "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection." ICLR 2024.
4. Yan et al. "Corrective Retrieval Augmented Generation." arXiv 2401.15884, 2024.
5. CtrlA: Adaptive RAG via Inherent Control. ACL Findings 2025.
6. MemR3: Memory Retrieval via Reflective Reasoning. NeurIPS 2025.
7. PAR²-RAG: Anchoring and Refinement RAG. OpenReview 2025.
8. MedKGI. "Iterative Differential Diagnosis with Medical Knowledge Graphs." NeurIPS 2024 Workshop. arXiv 2512.24181.
9. Deep-DxSearch. "End-to-End Agentic RAG System Training for Traceable Diagnostic Reasoning." arXiv 2508.15746, 2025.
10. SEMA-RAG. "Self-Evolving Multi-Agent RAG Framework for Medical Reasoning." arXiv 2605.17101, 2026.
11. Self-correcting Agentic Graph RAG for Clinical Decision Support in Hepatology. Frontiers in Medicine, 2025.
12. MedRAG. "Enhancing RAG with Knowledge Graph-Elicited Reasoning for Healthcare Copilot." arXiv 2502.04413, 2025.
13. MedGraphRAG. "Medical Graph RAG: Towards Safe Medical LLM via Graph RAG." ACL 2025. arXiv 2408.04187.
14. Shinn et al. "Reflexion: Language Agents with Verbal Reinforcement Learning." NeurIPS 2023.
15. Gou et al. "CRITIC: LLMs Can Self-Correct with Tool-Interactive Critiquing." ICLR 2024.
16. RAG-Gym. "Systematic Optimization of Language Agents for RAG." arXiv 2502.13957, 2025.
