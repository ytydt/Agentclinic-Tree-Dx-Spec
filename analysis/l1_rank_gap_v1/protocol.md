# L1 排序缺口调研：指标与数据契约

**状态**：阶段 A 锁定  
**决策**：1C 双口径漏斗 / 2C⊃B 双轨外部机制 / 3A 本轮只交付文档与审计（不实现、不跑新臂）  
**队列**：DiagnosisArena `d2_seq100_v1`（pilot24 + remain76）  
**日志锚点**：
- `logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/{case_results,mapper/projections}`
- `logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/{case_results,mapper/projections}`
- 病例元数据：`logs/diagnosisarena_d2_m01_v1/normalized_cases.json`

---

## 1. 决策锁定

| 题 | 选择 | 含义 |
|----|------|------|
| 主口径 | **1C** | gold-L1 家族命中 + `L1-prior-only` option 代理 + 过程层分解 |
| 借鉴范围 | **2C（保留 B）** | Track B = 改选择/更新 + 冻结后封闭重排（默认整合主轨）；Track C = 多医生 L1 / 开放扩族等（非作弊且有潜力即可入档，分列） |
| 交付 | **3A** | 调研、根因、设计、烟测规格；不改生产默认、不跑 Pilot/all100 新臂 |

---

## 2. 双口径漏斗定义

### 2.1 家族级（主终点）

对每例构造 **可接受 gold-L1 父集** \(P^\star\)（见 §3），再取 `l1_posteriors` 按 posterior 降序得到家族序 \(R_{L1}=(f_1,\ldots,f_m)\)。

| 指标 | 定义 |
|------|------|
| **family @1** | \(P^\star\cap\{f_1\}\neq\emptyset\) |
| **family @2** | \(P^\star\cap\{f_1,f_2\}\neq\emptyset\) |
| **family MRR** | \(\max\{1/k:f_k\in P^\star\}\)，若 \(P^\star\) 与 \(R_{L1}\) 无交则为 0 |
| **L1 coverage** | \(P^\star\cap\{f_1,\ldots,f_m\}\neq\emptyset\)（有可接受父在候选集中，不论秩） |
| **L1_MISS** | 无 coverage（对齐论文漏斗：无可接受 gold parent 进入 L1 候选） |
| **L1_HIT_MISRANK** | coverage 成立但 family @2 失败 |

17 例 BFS 上的 SELECT@ / gold-parent Top-1 数字 **只作机制假说，不进本队列主表**。

### 2.2 下游 option 代理（衔接指标）

沿用 at1_gap 2b：`L1-prior-only` = 按 L1 后验序、每家族取 joint 中最先出现的代表叶，再与 mapper 金标叶投影做 option @1/@2/MRR。  
官方 mapper（L2-joint）option 指标并列报告，用于对照「家族序弱」vs「叶序+映射强」。

### 2.3 过程分解（归因层）

在现有 annotate 落盘字段上可自动报告：

- `preset`、`compiler_rules_injected`、`n_selected` / `selected_budget`、`stop_reason`、`selected_fact_ids`
- 本轮 **无** 完整 DIRECTION/RULE-OUT 逐步轨迹落盘 → SELECT/DIRECTION 细标签仅能做 **抽样人工/半自动**；全量以 stop_reason + coverage/misrank 代理

分层桶（每例唯一主标签，优先级自上而下）：

1. `L1_MISS`  
2. `L1_HIT_MISRANK`（有 coverage，非 @2）  
3. `L1_OK_OPTION_MISS`（family @2 且 option `L1-prior-only` @1 失败）  
4. `L1_OK_OPTION_HIT`（family @2 且 option proxy @1 成功）  
5. `UNLABELED`（缺投影/缺后验）

---

## 3. 可接受 gold-L1 父集 \(P^\star\)（本轮自动规则）

本轮采用 **可复现自动规则**（非完整盲法临床审核）。审核备注：若后续人工盲法修订父集，须 bump 协议版本并重算主表。

**规则 `v1_auto_parent`**：

1. 取 mapper 金标选项的 `matched_leaf_ids` ∪ `clone_leaf_ids`。  
2. 在 `final_ranking_labels`（及必要时树叶）上查找这些叶的 `parent`，并入 \(P^\star\)。  
3. 若金标叶未匹配：用金标选项文本 / `gold_diagnosis` 与各 L1 `label` 做 `labels_synonymish` 启发式匹配，命中的 L1 id 并入 \(P^\star\)（记 `parent_source=label_synonym`）。  
4. 若仍空：记 `L1_MISS` 且 `parent_source=none`（coverage 失败；可能是映射失败而非排序失败）。

**诚实披露**：同一疾病可合法挂多个近义 L1（如多条「心脏转移」家族）；自动规则把 mapper 克隆叶的多个 parent 都视为可接受，会使 family @k **偏乐观**。人工审核应收紧到临床互斥轴上的最少父集。

---

## 4. 作弊边界

| 阶段 | 可读金标？ |
|------|------------|
| 审计 / 指标计算 | 是 |
| 推理、选臂、门控、重排 | **否** |
| 正式报告 | 禁止金标条件 G2 / 金标选臂数字 |

---

## 5. 产出清单（A–G）

| 文件 | 阶段 |
|------|------|
| 本文件 `protocol.md` | A |
| `l1_family_metrics.tsv` / `l1_rank_gap_audit.md` / `l1_family_summary.json` | B |
| `ours_l1_ranking_mechanism_card.md` | C |
| `external_l1_transfer_cards.md` | D |
| `l1_related_work_transfer.md` | E |
| `l1_weakness_rootcause.md` / `l1_improvement_design_v1.md` | F |
| `l1_improvement_smoke_spec.md` | G |
| `audit_l1_rank_gap.py` | 审计脚本（只读日志） |

---

## 6. 中期分流（阶段 B 后）

- 若 family @1 已高而 option 代理仍弱 → 优先代表叶/映射，收缩纯 L1 重排优先级。  
- 若 family @1 低或 `L1_HIT_MISRANK` 占比高 → 强化 Track B/C 的 L1 算子设计。
