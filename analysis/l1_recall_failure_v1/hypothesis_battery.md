# 假设电池（先写后验）

**协议**：[`protocol.md`](protocol.md)  
**漏斗**：[`r2_harm_rootcause.md`](r2_harm_rootcause.md) · [`r2_harm_case_audit.tsv`](r2_harm_case_audit.tsv)  
**规则**：每条含陈述 / 预期证据 / 检验方法 / 通过则改进方向。漏斗跑完后在「后验」栏打钩或删改。

---

## R2 主轴（反害）

### H1 噪声叶稀释

| 项 | 内容 |
|----|------|
| **陈述** | 全树注入的非近邻叶扩大候选，拉低金标 option 秩 / Top-1。 |
| **预期证据** | mean `n_extra` 大；伤害桶 ≫ 救援桶；matched 叶 Jaccard 偏低。 |
| **检验** | `r2_harm_case_audit.tsv` 分层 + `n_extra` / Jaccard 分层均值。 |
| **通过则** | **I1 受限注入**（仅近义/高分叶）。 |
| **后验** | mean_extra=16.1；伤害 39 vs 救援 9；matched Jaccard≈0.18；harm 金标叶相对 ranking 新入率 0.77 → **支持**。I1 落地后 mean_extra=3.3 仍反害 → **必要非充分**（须配合避免全量 typed 重绑）。 |

### H2 关系翻转

| 项 | 内容 |
|----|------|
| **陈述** | 金标选项 `relation_type` 从 equivalent/subtype 翻成 unrelated（或反之），导致 joint 投影错位。 |
| **预期证据** | 伤害桶 `relation_changed=1` 率显著高于双对桶。 |
| **检验** | 比较 `compat_gold_relation` vs `typed_gold_relation`。 |
| **通过则** | **I2 绑定护栏**（高置信 unrelated 且近精确叶存在时抽检/冻结）。 |
| **后验** | harm 翻转率 0.36 < rescue 0.56；unbind 风格仅 2/39 → **不支持为反害主因**（I2 降优先）。 |

### H3 秩重排非绑定丢失

| 项 | 内容 |
|----|------|
| **陈述** | 金标仍有 matched 叶，但 `gold_option_rank` 变差（compat 叶序被打乱）。 |
| **预期证据** | harm 中 `matched_present_typed=1` 且 `rank_worsened=1`。 |
| **检验** | 漏斗字段 `harm_rank_worsened_with_match_n`。 |
| **通过则** | 护栏优先保秩 / 限制注入对 ranking 的扰动（与 I1 协同）。 |
| **后验** | **34/39** harm 有匹配但秩变差 → **强支持**（I1 限制注入扰动优先于 I2）。 |

### H4 仅 UNBIND 子集受益、全局平均受害

| 项 | 内容 |
|----|------|
| **陈述** | 注入对 MAPPER_UNBIND 子集可能救援，但对已正确绑定的多数例伤害，净 Δ 为负。 |
| **预期证据** | `compat_miss_typed_hit` 与 UNBIND 重叠；`compat_hit_typed_miss` 主导。 |
| **检验** | `is_mapper_unbind_audit` × `stratum_at1` 交叉。 |
| **通过则** | **I1** 按缺口桶条件触发，禁止全表默认注入。 |
| **后验** | UNBIND∩伤害=0；救援含 125/187/198/229 等 UNBIND → **支持条件化**；净 Δ@1=−0.30 → **禁止默认开**。 |

---

## R3 / R4·R5 轴

### H5 gap-fill 只补 uncovered hints 不校正轴

| 项 | 内容 |
|----|------|
| **陈述** | R3 开 `recall_hints_gap` 后，ABSENT 轴仍错（hints 有金标串仍选错 MECE）。 |
| **预期证据** | smoke_r3：冻结已 gap_fill；67/231 仍 ABSENT。 |
| **检验** | [`../l1_gold_recall_v1/smoke_r3/`](../l1_gold_recall_v1/smoke_r3/)。 |
| **通过则** | **I4 轴注入白名单**（非再开 gap_fill）。 |
| **后验** | **支持**（R3 无效钉死）。 |

### H6 inject 进 candidate 但 BranchCreator 轴先验过强

| 项 | 内容 |
|----|------|
| **陈述** | Track C 上界 PASS（基线病名可容纳金标），live inject 后仍无对应 L1。 |
| **预期证据** | upper PASS vs live FAIL（TPP/accommodates）。 |
| **检验** | [`../l1_gold_recall_v1/smoke_track_c/`](../l1_gold_recall_v1/smoke_track_c/)。 |
| **通过则** | I4：仅 ABSENT 病种配置极；禁金标驱动推理。 |
| **后验** | **支持**（R4/R5 无效钉死）。 |

---

## 使用顺序

1. 读漏斗 summary → 勾选 H1–H4。  
2. 读 R3/Track C → 勾选 H5–H6。  
3. 仅对 **通过** 的假设打开 [`improvement_gates.md`](improvement_gates.md) 对应 I* 的 Pilot（默认仍 off）。
