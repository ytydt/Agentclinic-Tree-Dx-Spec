# 冒烟测试 Postmortem：medbullets-68 (CML) 误诊根因分析与修复

> **版本**: v1.0
> **日期**: 2026-05-20
> **案例**: medbullets-68（57 岁男性，WBC 57,500 伴 35% blasts）
> **正确答案**: D — Chronic Myelogenous Leukemia (CML blast crisis)
> **系统答案**: B — Acute Myelogenous Leukemia
> **模型**: meta-llama/llama-3.3-70b-instruct

---

## 一、误诊事件概述

系统运行 5 轮，执行 29 个 ANALYZE_VIGNETTE 动作，最终以 B1.1 (ALL, posterior=0.312) 和 B1.2 (AML, posterior=0.234) 为领先候选。B2 (Chronic Myeloproliferative Neoplasm) 在 Turn 2 后被关闭 (posterior=0.037)，最终衰减至 0.003。AnswerMapper 选择了 B (AML)。

正确诊断 D (CML) 在整个推理过程中**从未被作为独立候选认真评估**。

---

## 二、L1 分支设计分析

### 2.1 当前 L1 分支

| 分支 | 标签 | Prior | Danger |
|------|------|-------|--------|
| B1 | Acute Leukemia | 0.40 | 0.8 |
| B2 | Chronic Myeloproliferative Neoplasm | 0.20 | 0.4 |
| B3 | Lymphoproliferative Disorder | 0.10 | 0.3 |
| B4 | Reactive Leukocytosis | 0.10 | 0.1 |

### 2.2 问题：acute/chronic 二分法遗失了"慢性疾病急性转化"

L1 分支以 **疾病时间属性**（acute vs chronic）作为首要分类轴。这在大多数情况下是合理的，因为 L1 分支的设计原则是"诊断家族级别"（diagnosis-family level），不宜过细。

但本案例暴露了一个根本性缺陷：**CML blast crisis 是一种慢性疾病的急性表现**。它在细胞学上（≥20% blasts）看起来像急性白血病，但在分子遗传学上（BCR-ABL1/Philadelphia 染色体）是慢性骨髓增殖性肿瘤。这种"跨时间属性"的疾病实体在 acute/chronic 二分法中没有自然的归属位置。

### 2.3 此案例的理想 L1 分支

根据 WHO-HAEM5（2022）和 ICC 分类框架，白血病的首要分类轴应当是**细胞系（lineage）+ 遗传学驱动因子**，而非仅凭时间属性：

| 分支 | 标签 | 覆盖范围 | 关键鉴别 |
|------|------|---------|---------|
| B1 | Myeloid Neoplasm with Increased Blasts | De novo AML, MDS-EB, CML-BP (myeloid) | 骨髓形态、免疫表型、BCR-ABL |
| B2 | Lymphoid Neoplasm with Increased Blasts | ALL, lymphoblastic lymphoma | 淋巴系标记物、TdT |
| B3 | Chronic Myeloproliferative Neoplasm (without blast transformation) | CML-CP, PV, ET, PMF | 骨髓活检、JAK2/BCR-ABL |
| B4 | Lymphoproliferative Disorder / Plasma Cell Neoplasm | CLL, lymphoma, MM | 免疫球蛋白、淋巴结 |
| B5 | Reactive / Non-malignant | 白细胞反应、感染 | 感染标志物 |

**关键区别**：B1 的范围包含了 de novo AML **和** CML blast crisis，因为两者在首次就诊时的临床表现几乎不可区分（均为高 blast count + 全身症状）。鉴别需要 BCR-ABL 检测。这比当前设计的优势在于：

1. **CML blast crisis 不会因 L1 分类而被排除**——它作为 B1 的子分支（B1.x: CML blast crisis）自然存在
2. **B3 仅覆盖慢性期**，不会因 blast count 高而被不公正地压低
3. **分类轴从"时间属性"变为"细胞系+blast burden"**，与 WHO 2022 框架一致

### 2.4 但 L1 分支不宜过细——原则的平衡

L1 分支是"诊断家族级别"，目的是**快速缩小搜索空间**而非精确分型。以下原则需要平衡：

| 原则 | 当前设计 | 建议调整 |
|------|---------|---------|
| 互斥穷举 | ✅ 四分支覆盖完整 | ✅ 五分支覆盖更细 |
| 抽象层级一致 | ✅ 均为"家族级" | ✅ 仍为家族级 |
| 临床可操作性 | ⚠️ CML-BC 无归属 | ✅ 含 blast 的 MPN 归入 B1 |
| 分支数量适中 | ✅ 4 个 | ✅ 5 个（仍在 2-6 范围内） |
| 禁止跨层级混合 | ✅ | ✅ |

### 2.5 BranchCreator 原则调整建议

当前 BranchCreator prompt（第 22-39 行）已经包含了"temporal completeness rule"，并且明确指出 "A single high blast count does NOT by itself exclude a chronic disorder in blast crisis"。**问题不在于缺少规则，而在于规则的可操作性不足**。

**调整 1：将"时间属性分离"规则升级为"疾病阶段跨越"规则**

旧规则：
> "When the root node involves a process with both ACUTE and CHRONIC presentations, create SEPARATE branches for each major temporal category."

这个规则鼓励的是 acute/chronic 二分——恰恰是导致 CML-BC 无归属的原因。

新规则应当是：
> "When a disease family can present in multiple phases (e.g., chronic → accelerated → blast crisis), the **blast-bearing phase** should be classified with other blast-bearing entities (acute leukemia), NOT with its chronic-phase counterpart. The classification axis at L1 should prioritize **current clinical presentation pattern** (blast burden, cell lineage) over **underlying disease chronicity**."

**调整 2：在示例中显式包含 CML blast crisis 的归属**

旧示例：
> B2 "Chronic Myeloproliferative Neoplasm" (CML, PV, ET, PMF — chronic phase)

新示例应当明确 CML-BC 归入 B1：
> B1 "Myeloid Neoplasm with Increased Blasts" (de novo AML, CML blast crisis, MDS-EB)
> B2 "Chronic Myeloproliferative Neoplasm" (CML chronic/accelerated, PV, ET, PMF)

---

## 三、P0 修复：EvidenceAnnotator 信息坍缩

### 3.1 问题描述

`annotate_evidence_bundle` 对整个 bundle 的所有动作产生**一个** `result_summary` 和**一组** `branch_effects`，然后将同一个 summary 复制给 bundle 中的所有 action record。这意味着：

- 6 个不同的 confirm/challenge 问题 → 1 个笼统回答
- 双通道（confirm + challenge）在 TALP 和 Bundler 中正确生成，在标注阶段完全丢失
- Bundle 大小增加不产生额外信息价值

### 3.2 修复方案：逐动作 branch_effects + 聚合 summary

EvidenceAnnotator 的 prompt 修改为要求返回**逐动作的 branch_effects**（`per_action_effects`），同时保留聚合 summary 用于日志和 evidence_for/against 列表：

```json
{
  "result_summary": "aggregate plain language summary",
  "per_action_effects": [
    {
      "action_index": 0,
      "action_content": "Does 35% blasts support ALL?",
      "branch_effects": {"B1.1": "moderate_for", "B1.2": "weak_for"},
      "micro_summary": "35% blasts is consistent with both ALL and AML..."
    },
    {
      "action_index": 1,
      "action_content": "Can subacute onset argue against ALL?",
      "branch_effects": {"B1.1": "weak_against", "B1.2": "neutral"},
      "micro_summary": "Subacute onset is slightly atypical for ALL..."
    }
  ],
  "branch_effects": {"B1.1": "moderate_for", "B1.2": "weak_for"},
  "major_update": false,
  "contradiction_detected": false,
  "reopen_candidates": []
}
```

代码层面：
1. `annotate_evidence_bundle` 使用 `per_action_effects` 为每个 action record 写入**独立的** `result_summary`
2. 概率更新仍使用聚合 `branch_effects`（保持兼容性）
3. `_update_branch_evidence_lists` 使用每个 action 的独立 `micro_summary`

### 3.3 LLM 调用数影响

无变化——仍为 1 次 EvidenceAnnotator 调用/轮。只是 prompt 和 response 格式变更。

---

## 四、P1 修复：BranchCreator 慢性疾病急性转化指导

### 4.1 BranchCreator prompt 调整

在 "temporal completeness rule" 基础上增加 "phase-crossing rule"：

> **Phase-crossing rule**: When a disease can undergo phase transformation
> (e.g., CML chronic → blast crisis, follicular lymphoma → DLBCL transformation),
> the transformed/blast-bearing phase should be classified alongside other entities
> sharing that presentation pattern at L1:
>   - CML blast crisis → classify with "Myeloid Neoplasm with Blasts", NOT with "Chronic MPN"
>   - Richter transformation → classify with "Aggressive Lymphoma", NOT with "CLL"
>
> The L1 classification axis should prioritize CURRENT PRESENTATION PATTERN
> (blast burden, cell lineage, acuity) over UNDERLYING DISEASE CHRONICITY.

### 4.2 EvidenceAnnotator prompt 调整

增加对"疾病阶段跨越"的提示：

> When evaluating evidence against a branch that encompasses multiple disease phases
> (e.g., "Chronic Myeloproliferative Neoplasm" covering both chronic-phase CML and
> CML blast crisis), do NOT assign "against" solely because the presentation appears
> acute. High blast counts can occur in blast crisis of chronic diseases. Consider
> whether the branch label encompasses phase transformations before labeling effects.

---

## 五、认知问题 vs 知识缺陷分析

### 5.1 核心问题：CML blast crisis 被忽略是认知问题还是知识缺陷？

**结论：主要是认知/结构问题（约 70%），辅以知识应用问题（约 30%）。不是纯粹的知识缺失。**

#### 证据 1：LLM 具备 CML blast crisis 知识

BranchCreator prompt 第 37-39 行**已明确提到** blast crisis：
> "A single high blast count does NOT by itself exclude a chronic disorder
> in blast crisis — maintain both ACUTE and CHRONIC families until
> discriminating evidence is available."

LLM 读到了这个指令，但仍然：
- 将 B2 标为 "Chronic Myeloproliferative Neoplasm"（暗示慢性期）
- 给 B2 赋 danger=0.4（低于急性白血病的 0.8）
- 未在 why_included 中提及 blast crisis 可能性

这说明 LLM "知道" blast crisis 存在，但**没有将这个知识与当前病例的具体表现关联起来**。

#### 证据 2：EvidenceAnnotator 的推理路径暴露了锚定偏差

Turn 1 的 branch_effects：
- B1 (Acute Leukemia): `strong_for`
- B2 (Chronic MPN): `weak_against`

理由是 "35% blasts argues against Chronic Myeloproliferative Neoplasm"。这在慢性期 CML 是正确的，但 EvidenceAnnotator **被 B2 的标签锚定**——看到 "Chronic" 就认为高 blast count 反对它，没有考虑 blast crisis 是 CML 的自然进展阶段。

这是经典的**标签锚定偏差**（label anchoring bias）：分支标签中的 "Chronic" 字样引导了后续所有模块的推理方向。

#### 证据 3：信息坍缩阻断了纠错通道

即使 TALP 生成了针对 B2 的 challenge 候选（如"35% blasts 是否反对 CML?"），由于 EvidenceAnnotator 的信息坍缩，这个问题的答案被淹没在整个 bundle 的笼统 summary 中。系统**没有机会发现 "35% blasts 反对 CML" 这个结论是有争议的**。

#### 证据 4：结构性过早关闭

B2 的后验在 Turn 2 降至 0.037，低于 `test_threshold` (0.05)，触发 PostUpdateStateReviser 将其关闭。一旦关闭，B2 永远不会被扩展为包含 "CML blast crisis" 的子分支。这是**结构性过早关闭**——不是 LLM 有意排除 CML，而是概率更新机制在 CML 被充分评估之前就将其淘汰了。

### 5.2 认知问题的对抗机制

由于误诊的主要原因是认知/结构性的，以下机制针对认知偏差设计：

#### 机制 A：标签去偏化（Label Debiasing）

**问题**：分支标签中的时间属性词（"Chronic"/"Acute"）锚定了后续推理。
**方案**：BranchCreator 在生成分支时，标签中不应包含排他性时间属性。例如 "Myeloproliferative Neoplasm (all phases)" 而非 "Chronic Myeloproliferative Neoplasm"。

#### 机制 B：Phase-2 "Devil's Advocate" 扩展检查

**问题**：低概率分支在被扩展之前就被关闭。
**方案**：在 PostUpdateStateReviser 将分支标记为 `close_for_now` 之前，如果该分支的 `danger ≥ 0.4` 且尚未被扩展过，强制触发一次 "反事实检查"：

> "If this branch were expanded into sub-branches, could any sub-branch explain
> the current evidence better than the leading hypothesis? Specifically, consider
> whether a phase transformation (e.g., blast crisis) might match the
> evidence pattern."

这相当于在关闭分支前强制执行一次 SNAPPS Step 3 的反思。

#### 机制 C：EvidenceAnnotator 的"交叉标注"要求

**问题**：Annotator 对 B2 的评估没有考虑 blast crisis。
**方案**：在 EvidenceAnnotator prompt 中增加交叉标注规则：

> "When labeling a branch as 'against', explicitly consider and document
> whether a sub-entity within that branch family (e.g., blast crisis within
> CML, transformation within CLL) could explain the evidence. If so,
> downgrade the 'against' label to 'neutral' and add the sub-entity to
> reopen_candidates."

#### 机制 D：Bundler Phase 2 的"诊断选项守护"

**问题**：系统的 `static_options` 中包含 D (CML)，但推理过程从未将其与内部分支关联。
**方案**：在 static_diagnosis_qa 模式下，增加一个"选项覆盖审计"：Bundler 的 Phase 2 检查 `static_options` 中的每个选项是否被至少一个 frontier 分支覆盖。如果存在未覆盖的选项（如 D=CML），强制注入一个分析候选来评估该选项。

文献支持：
> Multi-agent frameworks using LLMs, including "devil's advocate" roles to correct
> confirmation and anchoring biases, improved diagnostic accuracy from 0% to 76%
> for top differential diagnoses. — Ke et al. (2024), JMIR 26(1):e59439

### 5.3 知识应用问题的补充机制

虽然不是纯知识缺失，但以下知识的显式引入可以改善 LLM 的推理质量：

#### 知识 A：CML blast crisis 的鉴别线索

以下临床线索可区分 CML blast crisis 与 de novo AML（来源：PMC5458010, PMC11545322）：

| 线索 | CML blast crisis | De novo AML |
|------|-----------------|-------------|
| **嗜碱性粒细胞增多** | 常见（高度特异性） | 罕见 |
| **脾脏肿大** | 常见且显著 | 少见或轻度 |
| **年龄** | 中位年龄 50-60 岁 | 双峰分布（儿童 + 老年） |
| **起病方式** | 亚急性（数周至数月） | 急性（数天至数周） |
| **WBC** | 通常 > 100,000（leukostasis 常见） | 可低可高 |
| **Philadelphia 染色体** | 阳性（定义性） | 偶见（de novo BCR-ABL+ AML） |
| **既往血液学异常** | 可能有慢性期病史 | 无 |

**引入方式**：在 BranchCreator 和 EvidenceAnnotator 的提示词中以"临床鉴别规则"形式嵌入。

#### 知识 B：WHO 2022 分类框架

> WHO-HAEM5 (2022) 和 ICC 均以**遗传学驱动因子**作为首要分类轴，superseding
> 形态学定义。BCR::ABL1 阳性的急性白血病表现可以是 CML blast crisis
> 或 de novo BCR-ABL1+ AML——鉴别需要核型分析和分子检测。
> — J Hematol Oncol 17, 61 (2024)

**引入方式**：BranchCreator prompt 中的分类示例应当引用 WHO 2022 框架。

#### 知识 C：Leukostasis 与高粘滞综合征

本案例中的视力下降 (20/100) 和共济失调步态是**高粘滞综合征/leukostasis** 的表现，这在 CML blast crisis（因极高 WBC 和 blast count）中比 de novo AML 更常见。

> Leukostasis is a medical emergency most commonly seen in acute leukemia with
> WBC > 100,000, but can occur at lower counts when blast percentage is high.
> Symptoms include visual changes, headache, and neurological deficits.
> — StatPearls: Leukocytosis (NBK560882)

**引入方式**：EvidenceAnnotator prompt 中以"临床关联规则"提示视力变化+高 WBC+blasts 的组合应提高 leukostasis 相关诊断（CML-BC, hyperleukocytic AML）的权重。

### 5.4 知识引入的来源与途径

| 知识类型 | 来源 | 引入途径 | 优先级 |
|---------|------|---------|--------|
| 疾病阶段跨越规则 | WHO-HAEM5, ICC 分类 | BranchCreator prompt 规则 | P1 |
| CML-BC vs de novo AML 鉴别线索 | PMC5458010, PMC11545322 | EvidenceAnnotator prompt 临床规则 | P2 |
| Leukostasis 临床关联 | StatPearls NBK560882 | EvidenceAnnotator prompt 关联规则 | P3 |
| 疾病转化通用模式 | 临床教科书 | BranchCreator "phase-crossing rule" | P1 |

---

## 六、修复实施清单

| # | 修复项 | 文件 | 优先级 | 状态 |
|---|--------|------|--------|------|
| 1 | EvidenceAnnotator prompt: per_action_effects 格式 | `evidence_annotator.txt` | P0 | ✅ 已实施 |
| 2 | Controller: `annotate_evidence_bundle` 解析 per_action_effects | `controller.py` | P0 | ✅ 已实施 |
| 3 | BranchCreator prompt: phase-crossing rule + 新示例 | `branch_creator.txt` | P1 | ✅ 已实施 |
| 4 | EvidenceAnnotator prompt: 疾病阶段跨越提示 | `evidence_annotator.txt` | P1 | ✅ 已实施 |
| 5 | SubBranchCreator prompt: phase-crossing sub-branch rule | `sub_branch_creator.txt` | P1 | ✅ 已实施 |
| 6 | frontier 去重 bug 修复 | `controller.py` | P3 | 待后续修复 |

---

## 七、参考文献

1. Pamuk GE, Ehrlich LA. "An Overview of Myeloid Blast-Phase Chronic Myeloid Leukemia." *Cancers (Basel)* 16(21):3615, 2024. [PMC11545322]
2. Huang Y et al. "A case report focusing on diagnosis and intervention of CML in blast crisis." *Front Oncol* 15:1711432, 2025.
3. Chen Z, Wang E. "'Chronic myelogenous leukemia in primary blast crisis' rather than 'de novo BCR-ABL1-positive acute myeloid leukemia'." *Cancer* 123(15):2912-2918, 2017. [PMC5458010]
4. Kim HJ et al. "A practical approach on the classifications of myeloid neoplasms and acute leukemia: WHO and ICC." *J Hematol Oncol* 17:61, 2024.
5. Croskerry P. "Premature Closure: Anchoring Bias, Occam's Error, Availability Bias." In: *Diagnosis and Treatment in Emergency Medicine.* Springer, 2018. pp 155-162.
6. Ke Y et al. "LLM-based multi-agent framework for improving diagnostic accuracy." *JMIR* 26(1):e59439, 2024.
7. Lambe G et al. "What causes delays in diagnosing blood cancers? A rapid review." *Primary Health Care Res Dev* 24:e12, 2023.
8. Stenzinger A et al. "Cognitive bias in clinical large language models." *npj Digital Medicine* 8:48, 2025.
9. Bond WF et al. "Cognitive Debiasing Strategies for the Emergency Department." *Ann Emerg Med* 71(1):87-96, 2018. [PMC6001502]
10. Arber DA et al. "Initial Diagnostic Work-Up of Acute Leukemia: ASCO Clinical Practice Guideline." *J Clin Oncol* 37(3):239-253, 2019. [PMC6338392]
