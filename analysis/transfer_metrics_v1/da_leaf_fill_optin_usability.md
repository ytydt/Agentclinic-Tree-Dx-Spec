# 标准协议「补叶」相关机制：默认 OFF × 低伤害可用性评估

状态：调研笔记（非正式 claim）  
日期：2026-07-26  
锚点：DiagnosisArena `compat_parallel` 正式主表 **@1=0.72 / @2=0.78**  
范围：标准 DA harness 周边（含 opt-in）；不含已硬编码开启的建树/生成补叶

---

## 0. 先钉死：什么已经默认 ON（不在「OFF 候选」里）

| 机制 | 作用 | 状态 |
|------|------|------|
| 建树 `recall_hints_gap`（含 L1 `branch_recall_gap_fill`） | 建轴时召回补洞 | **ON**（staged 硬编码） |
| Annotate **Config A** `l2_recall_gap_fill` | L2 生成后一次召回补子叶（真加树叶） | **ON**（`diagnosisarena_l2_pipeline` 硬编码） |

→ 标准路径**已经有**生成期补叶；本次评估的是 **额外、默认 OFF** 的补叶/扩覆盖机制。

---

## 1. 候选池总表（默认 OFF）

| ID | 是否真补叶 | 改什么 | DA 默认 | 门控 | 额外伤害 | 可用性裁定 |
|----|:----------:|--------|---------|------|----------|------------|
| **Approach A** 同义修绑 | **否**（只修绑） | option→已有叶 | OFF | frozen+live **PASS** | **低**（伤害 2 / 救援 12） | **唯一可推荐启用的 OFF 机制** |
| **R2** 全树叶注入 + typed | **是**（进 ranking） | ranking 叶集 | OFF | **REJECT** | **高** Δ@1=−0.30 | **不可用** |
| **I1** 受限注入 + typed | **是**（≤5） | ranking 叶集 | OFF | **REJECT** | **高** Δ@1=−0.33 | **不可用** |
| AdaptiveSubdivide / deepen | 伪 L3 | ranking | 非默认 | subdivide **REJECT** | Δ@1=−0.08 | **不可用** |
| R4/R5 Track C 外诊名→hints | 间接（重建树） | 树 | OFF | live **REJECT** | 未起效 / 禁默认 | **不可用（生产）** |
| L2 targeted gapfill 脚本族 | **是**（离线加叶） | 树副本 | 不进 harness | research_only | **无 DA @1/@2** | **研究可用；DA 未接线** |
| Transfer `compat_then_pad` | 否（评测 pad） | 开放列表 | 开放评测可选 | Acc 不伤 | **低**（Acc Δ=0） | **仅开放指标；非 DA 补叶** |

---

## 2. 「额外伤害较低」筛选后的可用性

### 2.1 Approach A（`--synonym-bind-repair`）— **可用候选 #1**

| 项 | 内容 |
|----|------|
| 补叶？ | **不补**。只对空 `matched_leaf_ids` 做同义/桥接回填 |
| 证据 | live all100：**0.81/0.93**；vs 本跑 compat Δ@1=**+0.10**、Δ@2=**+0.15**；救援 12 / 伤害 2 |
| 避害关键 | **不重跑 typed、不扩叶集**（避开 R2/I1 的 H3 秩扰动） |
| 可用性 | harness **已挂旗标**；`default_candidate=true`；**DA 生产默认仍 off**（需显式 enable） |
| Transfer | `compat_synonym` 栈 **已开** |
| 局限 | 不解决「树上真没有金标叶」；对 OX 开放 R 的 C 类覆盖洞 **无效** |
| 建议 | DA 主表若要涨 @1/@2：**优先讨论 enable Approach A**；与补叶正交 |

证据：`analysis/l1_recall_failure_v1/improvement_gates.md` · `smoke_synonym_bind_live/`

### 2.2 R2 / I1 注入 — **低伤害假设已证伪**

| | R2 全树 | I1 受限 |
|--|---------|---------|
| mean_extra | ~16 | ~3.3 |
| typed @1 | **0.42** | **0.42**（Pilot） |
| Δ@1 vs compat | **−0.30** | **−0.33** |

压叶不能消 typed 重绑伤害。事后 rematch「变好」属 **I5 伪增益**，禁止写主表。  
→ **标准协议下不可用。**

### 2.3 Track C（R4/R5）— **上界有、live 无**

外源诊断名注入 hints 后重建：上界偶发 PASS，ABSENT live mapper **0/0**。  
→ **保持 OFF**；禁止当默认补叶。

### 2.4 L2 targeted gapfill（hybrid / gates / global_reassign）— **研究可用、协议未接入**

| 项 | 内容 |
|----|------|
| 做什么 | 在冻结树副本上 **定向生成缺失 L2 叶**（真补叶） |
| 默认 | **不在** DA staged / compat harness |
| 已有结果 | MedBullets 小队列（n≈17）research_only；例：`gold_l2_coverage` 可到 ~0.88，`actual_top2`~0.59（`logs/l2_targeted_gapfill_global_reassign_v1`） |
| DA option@k | **无** all100 compat 对照 |
| OX 叠加烟测 | 标准管线 opt-in `--targeted-l2-gapfill`；`ox_seq24` live：**mapper@1 持平 0.875**，开放 μF1 +0.9pp，**仅 1/24 例加叶**（Config A 已补大部分）→ 见 `ox_seq24_targeted_gapfill_smoke.md` |
| 伤害 | 结构门控（parent/semantic）旨在控脏叶；OX24 见 mapper@2 −4pp（小样本） |
| 建议 | **可用性 = 研究轨**；默认 OFF；若要进标准协议，需按 C 类缺失分层抽样 + DA @1 门控 |

### 2.5 开放评测 pad（勿与 R2 注入混名）

`compat_then_pad_posterior`：不改树/不改 mapper；开放列表 pad 到 K。  
MCR Acc@1 持平、any-hit↑；OX μF1 略升。  
→ **开放指标可用**；**不是** DA 补叶机制。

---

## 3. 未完成但文档指向的「可能低伤害」缺口

I1 报告明确下一步：**避免 typed 全量重绑 / 冻结 map**（I2 护栏，**未做**）。  
即：若存在「只往 ranking 追加叶 + **冻结** option_maps 再 rematch」变体，伤害曲线未知——**当前无可用实现与数字**，不能当低伤害补叶启用。

---

## 4. 总裁定（可用性）

```
标准协议里「默认 OFF」且与补叶/覆盖相关的机制
├─ 已证低伤害可启用 ── Approach A（修绑，非补叶）★
├─ 已证高伤害禁用 ── R2 全树注入、I1 受限+typed、subdivide
├─ live 无效禁用 ── Track C 外诊名注入
├─ 研究可用未接线 ── targeted L2 gapfill（真补叶；缺 DA/OX 主表门控）
└─ 评测侧可用 ── compat_then_pad（开放列表；非 harness 补叶）
```

**回答你的问题**：  
在「补叶 + 默认 OFF + 额外伤害低」的交集里，**目前没有已过 DA 主表门控的真补叶机制**。  
- 唯一 **OFF 且低伤害、可立刻讨论启用** 的是 **Approach A（不补叶）**。  
- 真补叶要么 **已在 Config A / recall_hints_gap 默认开着**，要么是 **R2/I1（高伤害 REJECT）**，要么是 **targeted gapfill（有代码与小样本，未进标准协议）**。

---

## 5. 若目标是抬 OX 开放 Recall（对照先前审计）

| 缺口类型 | OFF 机制能否帮 | 推荐 |
|----------|----------------|------|
| D 排序截断 | Approach A ✗；R2 注入会伤 mapper | 加大 K / 重排；非补叶 |
| C 真缺失 | Approach A ✗；targeted gapfill ** theoretically ✓** | 开 OX 限量子集 targeted 实验 |
| B 粒度 | Approach A 部分（仅闭集绑） | 评测父⊇子协议或生成伞名叶 |

产物交叉：`ox_recall_low_rootcause_audit.md` · `improvement_gates.md` · `r2_harm_rootcause.md`
