# OX C 类缺叶根因细化：KB vs LLM vs 其他

状态：审计结论（Config-A 感知 v2）  
日期：2026-07-26  
范围：taxonomy C 桶 **n=105**（`C_true_absent_*`）  
主证据：逐案 `annotate/cache/{id}/l2_llm_cache.json` + `case_results` ranking  
对照：`annotate/shared_trees`（taxonomy / 开放 posterior 评测用的叶宇宙）  
机器表：[`ox_c_leaf_absent_rootcause.json`](ox_c_leaf_absent_rootcause.json)

---

## 0. 总判（直接回答）

| 问题 | 答案 |
|------|------|
| **主要是 KB 缺失吗？** | **否。** 在可挖到的 Config A 热路径里，金标大量出现在 **LLM-DDx differentials** 与 **gap-assign 候选**中。 |
| **主要是 LLM 认知/生成缺陷吗？** | **是，第一主因（约 2/3）。** 入口已提名或 Creator 曾写出，但未稳定进入最终提交/短名单。 |
| **还有别的吗？** | **有：** (1) taxonomy「叶不在」混入了 **评测叶宇宙错误**；(2) 假朋友/伞名噪声；(3) 一小撮真入口池空洞或轴错位。 |

**一句话**：C 类不应再被讲成「知识库里没有这个病」；更准确是 **LLM 入口/生成与落叶/留树/进窗之间的断裂**，再叠加 **shared_trees≠Config A 树** 的审计污染。

---

## 1. 必须先钉死的产物陷阱

开放指标与原 taxonomy 的「全叶」来自：

`annotate/shared_trees` → 建树阶段写入的 L2  

而标准 annotate 的 Config A 会 **strip L2 后按 per_parent 重生成**，结果只活在内存 / `case_results.final_ranking_*`，**没有写回 shared_trees**。

| 证据 | 含义 |
|------|------|
| case4 ranking 含 `Meconium ileus`，shared_trees 叶集无 | taxonomy 标 C，实为 **假 C（产物错位）** |
| case7 cache 某次 Creator 写出 `Neuroleptic Malignant Syndrome`，shared_trees / ranking 短名单无 | 可能是真丢叶，或已在 Config A 全叶但未进短 ranking（与 D 类混淆） |

→ 下文 v2 已用 **Config A ranking + LLM cache** 重切；原「C≈22% 金标」里有一部分不是「Config A 没生成」。

---

## 2. v2 根因分布（n=105）

| 机制 | n | 占 C | 含义 |
|------|--:|-----:|------|
| **C2b** Creator 缓存曾写出金标，但不在 Config A 短 ranking | **47** | **44.8%** | LLM 生成过；最终未进提交窗（丢叶 **或** 全叶有但截断——缺持久化全树时二者难分） |
| **C2a** 入口/gap 见过金标，Creator 缓存从未写出 | **23** | **21.9%** | **硬 LLM 丢叶**（知而未写） |
| **C1** 入口未见中，偏轴错/空洞/非病名金标 | **15** | **14.3%** | 真覆盖洞或金标不可叶化 |
| **C0** 假朋友/伞名噪声 | **12** | **11.4%** | 不宜当「缺特异叶」 |
| **T_*** 假 C：金标其实在 Config A ranking | **8** | **7.6%** | taxonomy 叶宇宙错误 |

合并：

- **LLM 相关（C2\*）≈ 66.7%**
- **真池/轴问题（C1）≈ 14.3%**
- **假朋友 + 假 C（C0+T）≈ 19%**

严格桶 `C_true_absent_not_in_tree`（n=74）内同样是 **C2 主导**（C2b 34 + C2a 22）。

---

## 3. 机制拆解

### 3.1 C2a — 「知道」但 Creator 不写（最硬的 LLM 缺陷）

链路：`llm_ddx differentials` / parent-assign / `RecallGapAssign(index=-1)` → `L2RecallCreator` → 可选 gap_fill。

| case | gold | 证据 |
|------|------|------|
| 2 | tuberculosis | differentials 多次含 TB；gap `index=-1`；**无任何 sub_branch=TB** |
| 35 | fungal lung infection | ddx+gap uncovered；未落叶 |
| 55 | Cushing's syndrome | 同上 |

这不是 KB 空白：模型在入口任务里已提名，**子叶生成/修补未兑现**。

### 3.2 C2b — Creator 写过，但进不了最终短名单

| case | gold | cache sub_branch | ranking |
|------|------|------------------|---------|
| 7 | NMS | 有（某次 B1 扩叶） | 仅 Tardive Dyskinesia |
| 8 | DIC / PNH | 有 | 仅 HUS/TTP |
| 5 | lumbar spinal stenosis | 有 | 短名单无 |

可能解释（需持久化 Config A 全树才能分清）：

1. **生成后被后续 repair/覆盖丢掉** → 真缺叶（LLM/控制流）  
2. **仍在全叶上但 joint/后验没送进短窗** → 实为 **D 类截断**，被错误叶宇宙标成 C  

工程含义：先 **把 Config A 终态树落盘**，再谈补叶 ROI。

### 3.3 C1 — 入口池未见（更接近「召回洞」）

多为：

- 不可叶化金标：`various infectious diseases`、`a wide variety of infections`、药名列表（SSRIs/TCAs…）  
- 稀有/寄生虫名入口未提名：`Toxoplasma gondii`  
- 非特异：`dehydration` / `malnutrition`

这类 **才** 更像「召回/轴/金标形态」问题，而不是「KB 缺 tuberculosis 这种常见病」。

### 3.4 静态 KB 探针说明

本次 `DiseaseNameResolver` 经 `load_offline_resolver` **未挂上 LR/DxS 等源**（`resolve_all_sources` 恒空），case_report/CPG 空载时也无标签——**不能**用「resolver=空」反证 KB 真缺。  
反而 cache 里高比例 ddx/gap 命中，已足以否决「主因=KB 缺失」。

---

## 4. 与「补叶 / gapfill 烟测」的闭合

OX seq24 叠 targeted gapfill 几乎不加叶，与本审计一致：

- 许多「C」对 Config A 并非「候选池空」；  
- 错轴 / 短名单截断 / 假 C 都会让二次补叶 **打空**；  
- 真正该打的是 **Creator/gap_fill 兑现率（C2a）** 与 **终态树持久化后的 D/C 重切（C2b）**。

---

## 5. 建议优先级

1. **落盘 Config A 终态树**（annotate 写 `annotate/config_a_trees/`），重跑 taxonomy → 把假 C / 伪 C2b 剥离。  
2. **针对 C2a** 做 Creator/gap_fill 门控（uncovered 且 ddx 已提名 → 强制保留/再修）。  
   离线验证与控制器开关见 [`ox_c2a_force_emit.md`](ox_c2a_force_emit.md)（`l2_gap_force_emit_uncovered`）。
3. **不要**把主资源砸在「先扩 KB 救 C」；KB/CPG 最多服务 C1 长尾。  
4. C0 假朋友改走粒度/匹配协议，勿进补叶主表。

---

## 6. 产物

| 文件 | 内容 |
|------|------|
| [`ox_c_leaf_absent_rootcause.json`](ox_c_leaf_absent_rootcause.json) | v2 逐条标签 |
| [`audit_ox_c_leaf_absent_rootcause.py`](../../scripts/paper/audit_ox_c_leaf_absent_rootcause.py) | v1 挖 cache 脚本（可复跑） |
| 本文 | Config-A 感知裁定 |

**审计裁定**：C 类缺叶的主因是 **LLM 生成路径未兑现（入口已知 / 偶发写出但未进入最终短窗）**，不是 KB 大规模缺失；次因是轴/不可叶化金标与 taxonomy 叶宇宙错位。
