# CF_SUBSTRATE_REPLAY：counterfactual 路线 P0/P1 的零调用判决

> 日期：2026-08-22
> 上游方案：[`COUNTERFACTUAL_INFERENCE_MECHANISM_TRANSFER_AUDIT.md`](../../COUNTERFACTUAL_INFERENCE_MECHANISM_TRANSFER_AUDIT.md) §12 P0/P1
> 新 LLM/API 调用：**0**
> 脚本：[`cf_substrate_replay.py`](../../cf_substrate_replay.py)、[`cf_collapse_direction.py`](../../cf_collapse_direction.py)、
> [`cf_identity_port_verify.py`](../../cf_identity_port_verify.py)、[`cf_quarantine_verify.py`](../../cf_quarantine_verify.py)、
> [`cf_quarantine_reach.py`](../../cf_quarantine_reach.py)、[`cf_slice_breakdown.py`](../../cf_slice_breakdown.py)
> 产物：[`verify.json`](verify.json)、[`replay.json`](replay.json)、[`collapse_direction.json`](collapse_direction.json)、
> [`identity_port_verify.json`](identity_port_verify.json)、[`quarantine_verify.json`](quarantine_verify.json)、
> [`quarantine_reach.json`](quarantine_reach.json)、[`slice_breakdown.json`](slice_breakdown.json)

## 0. 结论先行

上游审计把 P0 写成五处并列的 substrate 硬错误，并把 `CF_EDGE_AUDIT_V1`（P2）作为主要科学目标。
本轮零调用重放给出的判决与这个优先级**不一致**，且分歧是量化的：

1. **P0 里只有第一处（safe identity）在端点上有可测收益，另两处为零或负。**
   在同一 substrate、同一确定性打分、同一 frontier 规则下：safe identity 在 Forest 净 **+16**、
   IMPC 净 **+11** 个 addressable-complete 病例；proposition dedup 在两臂**净 0**；
   移除 view/axis 加分在 Forest **净 0**、IMPC **净 −2**。后两者只制造 top-1 抖动（47–78 例）。
   补上配套的父概念准入规则后（即已交付形态），Forest 净 **+17**、IMPC 净 **+13**，
   **两臂 harm 均为 0**，且不依赖分析层的冻结同义桥——生产 `resolver=None` 下即为此数。
   队列是 400 DA + 400 MCR，两族同向为正、六切片无一为负（§3.5），故合并均值合法；
   但收益偏向 MCR（Forest 11/17、IMPC 11/13），因为 DA 的池级 complete 率只有 5–6%
   而 MCR 是 34–38%——**DA 的瓶颈在生成侧，不是本轮修的这一处。**

2. **这条修复不需要发明，Collapse3c 里已经有了。** Forest/IMPC 与 Collapse3c 用的是**同一个**
   containment 谓词 `len(na)>=6 and len(nb)>=6 and (na in nb or nb in na)`。Forest/IMPC 用它**静默合并**
   （561 / 452 次），Collapse3c 用它**建立 `narrower_than`/`broader_than` typed relation**（108 + 33 次）
   而绝不折叠。这给「Collapse3c 是 specificity-retention 参考」第一次配上了机制和数字。

3. **`CF_EDGE_AUDIT_V1` 竞争的空间比预期小一个量级。** Collapse3c 上真正的 conversion gap
   （完整对象已在 frontier 而 selector 仍答错）只有 **50/800**，其中带候选独有高特异判别子的仅 **15/800**。
   §8.3 那种 top-pair 版本上界是 **22/800**。两个数都是**假设每条边都朝正确方向解决**的绝对上界。
   相比之下 V1 的上界（Forest 17、IMPC 12）同量级，但**零调用、且是正确性修复而非投机机制**。

因此的处置：**执行 P0 第一处加自相矛盾边隔离，不按现设计预注册 P2。**
两项均已落到生产代码并通过验收（打过补丁的 `mosaic.py` / `aphhm_c.py` 在同一批冻结 payload 上
精确复现离线测得的 173 / 176 与 28/28）。

**两项的记账必须分开**：identity 修复有端点收益（Forest 净 +17、IMPC 净 +13，harm 0）；
自相矛盾边隔离的端点上界只有 **23/800 例 payload 变动**，其中仅 1 例是 rescue 暴露、
至多 1 例可能有害、21 例惰性——它是自洽性修复，不是涨分修复（§7.1(ii)）。
修复后三臂位置见 §7.1b：Collapse3c 的 addressability 优势被反超，但它仍以 conversion
（.726 vs .686/.601）在真端点领先，所以瓶颈已从 recall 移到 conversion。
四层的依赖次序与交付明细见 §7。

一句必须前置的措辞纪律：本报告测的是 **addressability**（完整对象是否进入 selector 能看见的
shortlist），**不是** conversion。救回一个候选不等于 selector 会选它。任何把 +16 读成
「clinical-complete +16」的说法都越过了本轮日志的支持范围。

---

## 1. 可复现性与保真度

### 1.1 substrate 冻结

上游审计的基线提交 `726e7611780be9419d70fcfdfbacbfc471aab74c` **不在本 clone 内**
（`logs/backbone_v1/` 在当前仓库是未跟踪目录），所以 git blob 比对路径不可用。改为按
`input_manifest.json` 逐文件记录的 `git_blob_sha1` 做内容级校验：

| 项 | 值 |
|---|---:|
| manifest 条目 | 2,400 |
| 逐字节一致 | **2,400** |
| 缺失 / 不一致 | 0 / 0 |

这比「提交存在」是**更强的字节校验、更弱的历史校验**，报告据此措辞。

### 1.2 B0 保真度（这一步不过，下面全部无效）

用日志内冻结的生成器原始 payload（Forest 的 `ax_syndrome`/`ax_mechanism`/`ax_modality` 加 49 例
`a1`；IMPC 的 `D1`/`D2`/`D3`）重跑 `_ingest_generator` → `score` → `two_lane_frontier`，
与日志内 `evidence`/`registry`/`frontier_final` 逐字段比对：

| 项 | 值 |
|---|---:|
| 病例 | 1,600（Forest 800 + IMPC 800）|
| 证据 ID 序列、raw_span 序列全等 | 1,600 |
| registry 全等（含 `score_logit` 到 1e-6）| 1,600 |
| `frontier_final` 顺序全等 | 1,600 |
| **不一致** | **0** |

`resolver=None` 已从 [`run_mosaic.py`](../../../../scripts/paper/run_mosaic.py) 确认（`MosaicPipeline(cached, mode=args.mode)`），
所以重放是完全确定的。脚本在保真度非满分时 `SystemExit` 并拒绝输出下游臂。

第二个独立校验：本轮独立算出的 Collapse3c `champion_complete_cases = 122`，
与 E2 full-800 human-root 的 Collapse3c **122/800** 精确吻合。端点接线未走偏。

---

## 2. P0 硬错误的代码定位

上游审计列了五处；代码里全部确认，并且**第 2 处比审计描述的更糟**。

| # | 位置 | 实际行为 |
|---|---|---|
| 1 | [`mosaic.py::GlobalConceptRegistry._match`](../../../../src/agentclinic_tree_dx/mosaic.py) | 归一化后两名各达 6 字符即 `na in nb or nb in na` 返回 True，composite/subtype 静默成为父概念的 alias |
| 2 | `mosaic.py::_ingest_generator` | 证据去重用 **`e.raw_span == span`（精确字符串）**，非归一化。审计写的是「归一化重复」，实际连大小写/标点变体都各建 ID |
| 3 | `mosaic.py::score` | `z += 0.35*(views-1)` 与 `z += 0.15*(axis_nodes-1)`，provenance 多重性被当独立证据计价；叠加第 2 处后同一表面证据双重计权 |
| 4 | `mosaic.py::EvidenceFact` | 构造只传 `raw_span`/`source_view`；polarity、epistemic_status、modality、reliability 恒为默认常量，`temporality` **根本不是该 dataclass 的字段** |
| 5 | [`aphhm_c.py`](../../../../src/agentclinic_tree_dx/aphhm_c.py) Collapse3c | `contradict_spans` 无 ID 列（实测 `contradict_fact_id_links = 0`） |

第 4 处的后果已由上游 census 记录：Forest/IMPC 15,110 条 evidence 全部
`polarity=present`、`epistemic_status=observed`、`modality=text`、`reliability=1.0`，temporality 0 条。
**所以在 Forest/IMPC 现有字段上做「删阴性 / 改时间 / 按可靠性衰减」的 counterfactual 在物理上不可能**——
没有可改的字段。这点独立成立，与下面的端点结果无关。

---

## 3. 三个修复臂的确定性重放

五个臂共用同一 substrate，只切换策略。`safe identity` 用 exact 归一化**或**冻结同义桥
（`FrozenExactSynonymBridge`，sha256 `b67901c3…`，同时是 `ClinicalEndpoint` 所用的那份），
不含 substring、不含 fuzzy 层；该桥会解析「全名 + 自身括号缩写」，所以去掉 containment
不会把真正的缩写对打散。

### 3.1 Forest（containment 合并 561 次，分布在 324/800 例）

| 臂 | 候选/例 | 证据/例 | frontier/例 | addressable-complete | 率 | pool | alias 掩蔽 | rescue | harm | 净 | top-1 变动 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 观测 | 4.486 | 9.816 | 4.327 | 156 | .1950 | 158 | 17 | — | — | — | — |
| V1 safe identity | 5.036 | 9.816 | 4.714 | 172 | .2150 | 175 | **0** | 17 | 1 | +16 | 118 |
| **V1bp 已交付形态** | 5.089 | 9.816 | 4.914 | **173** | **.2162** | 175 | **0** | **17** | **0** | **+17** | 128 |
| V2 proposition dedup | 4.486 | 9.518 | 4.327 | 156 | .1950 | 158 | 17 | 0 | 0 | **0** | 17 |
| V3 provenance only | 4.486 | 9.816 | 4.327 | 156 | .1950 | 158 | 17 | 0 | 0 | **0** | 47 |
| VA 三项合并 | 5.036 | 9.518 | 4.714 | 172 | .2150 | 175 | 0 | 17 | 1 | +16 | 180 |

### 3.2 IMPC（containment 合并 452 次，分布在 257/800 例）

| 臂 | 候选/例 | 证据/例 | frontier/例 | addressable-complete | 率 | pool | alias 掩蔽 | rescue | harm | 净 | top-1 变动 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 观测 | 4.094 | 9.071 | 4.053 | 163 | .2037 | 164 | 12 | — | — | — | — |
| V1 safe identity | 4.501 | 9.071 | 4.414 | 174 | .2175 | 176 | **0** | 12 | 1 | +11 | 77 |
| **V1bp 已交付形态** | 4.534 | 9.071 | 4.489 | **176** | **.2200** | 176 | **0** | **13** | **0** | **+13** | 85 |
| V2 proposition dedup | 4.094 | 8.834 | 4.053 | 163 | .2037 | 164 | 12 | 0 | 0 | **0** | 19 |
| V3 provenance only | 4.094 | 9.071 | 4.053 | 161 | .2013 | 164 | 12 | 0 | 2 | **−2** | 78 |
| VA 三项合并 | 4.501 | 8.834 | 4.414 | 172 | .2150 | 176 | 0 | 12 | 3 | **+9** | 158 |

IMPC 的 176 等于该臂 pool 上限 176：在这一臂上 addressability 已被打满，
frontier 宽度不再是 IMPC 的约束，剩下的全部损失都在 selector 一侧。

### 3.3 四个必须一起读的读法

**（a）净值不是平均，是配对。** V1 在两臂都是 rescue 17/12、harm 1/1。这不是 +20−4 的粉饰，
是干净的单向修复。harm 的机制也定位清楚了：split 使候选数上升（4.486→5.036），
在 `main_k=4 + protected_k=2` 的固定宽度下挤出原本在 frontier 内的完整候选：

- Forest `medcasereasoning_200b/364`：`Acute Interstitial Nephritis`（complete）被
  新拆出的 `Sildenafil-induced Acute Kidney Injury` 挤出。
- IMPC `diagnosisarena_heldout200b/653`：`Hepatic Artery Thrombosis` 被
  `Pyelonephritis with hepatic involvement` + `Thrombosis` 挤出。

整个 800 例里被挤出的 B0 frontier 成员总数各臂仅 **2** 个，所以这是局部、可寻址的代价，
不是系统性权衡。注意 E5 已证 width4→8 会让 clinical-complete 掉约 17.68pp，
**所以「直接加宽 frontier」不是解**；正确的形状是「拆出子概念时保护它的父概念」这种局部准入规则。

这条规则随后被实现并测量（V1bp 行）：**两臂 harm 双双归零**，Forest 净 +16→**+17**、
IMPC 净 +11→**+13**。会计口径是「一次拆分退一个坑位」——n 个拆分前概念占 n 个坑，
每次拆分额外退 1 个，上限 2。它必须迭代到不动点：Forest `364` 一例内发生**两次**拆分
（`Sildenafil-induced AKI` 从 AKI 拆出、`Sildenafil-induced nephrotic syndrome` 从
Nephrotic Syndrome 拆出），而第二个子概念本身要靠退坑才入座，所以按单次预计数只会退 1 个坑，
`Acute Interstitial Nephritis` 仍被挤出。改为不动点后该例 frontier 恰好从 6 变 8，
与「6 个拆分前概念 + 2 次拆分」精确对账。

代价是有界的：frontier 均宽 Forest 4.327→4.914、IMPC 4.053→4.489，且只在真的发生拆分处扩张，
与 E5 那次宽度翻倍不是同一类操作。

**（b）alias 掩蔽被完全清零，这是可证伪的预测命中。** B0 下 Forest 17 例、IMPC 12 例存在
「完整对象只作为 alias 存在」——而 selector 的 shortlist 是
`[c.preferred_name for c in frontier]`，alias 永不进入。V1 下这两个数都变成 **0**，
且 addressable 增量（+16/+11）与之几乎一一对应。机制与端点是同一件事，不是两个巧合。

**（c）V2 与 V3 的零增益不等于它们是错的，但等于它们不能用这个端点辩护。** 去重针对的是
双重计权、view 加分针对的是投票通胀，addressable-complete 这个端点在结构上看不见它们。
可是它们**确实**改动了 47–78 例的确定性 top-1 而没有换来任何可测收益，
在没有第二个端点之前，这是纯风险。IMPC 上 V3 单独为 −2、VA 比 V1 低 2，方向也不支持它们。

**（d）救回的候选落位很高，且父概念同时保留。** 这决定 P2 是否还有必要：

| | Forest | IMPC |
|---|---|---|
| 救回病例 | 17 | 12 |
| 救回标签的 frontier 排位分布 | {1:1, 2:5, 3:4, 4:5, 5:2} | {1:2, 2:3, 3:4, 4:1, 6:2} |
| 前 4 位内 | 15/17 | 10/12 |
| **裸父概念也同时保留** | **16/17** | **12/12** |

父子同时可寻址 28/29 例，意味着 selector 会面对一次真正的父/子特异性抉择——
正是 `MCR 173` 那个 Collapse3c 做对、Forest/IMPC 做错的模式。这是 V1 之后**最可能**
产生实际 conversion 的位置，也正是本轮无法在零调用下判定的位置。

### 3.4 哨兵复核

`DA 709` 按上游审计的预测精确复现并被救回：

- B0 frontier：`Tuberculosis`, `Hemophagocytic lymphohistiocytosis`, `Hematological malignancy`, `Hematophagocytic Lymphohistiocytosis`, `Lymphoma`
- V1 frontier：额外出现 `Disseminated Tuberculosis with Hemophagocytic Lymphohistiocytosis`（第 4 位）
- 被记录的两次 containment 合并：`… (HLH) → Hematophagocytic Lymphohistiocytosis`（真同义，V1 下由冻结桥保留合并）、
  `Disseminated Tuberculosis with HLH → Tuberculosis`（**composite 被吞进父概念**，V1 下拆出）

同时暴露一个上游审计未记的对偶缺陷：`_match` 不只过度合并，也**合并不足**。DA 709 里
C002 `Hematophagocytic Lymphohistiocytosis` 与 C005 `Hemophagocytic lymphohistiocytosis`
是同一个病（Hemato-/Hemo- 拼写差异），却各自独立存在，证据被劈成 2 和 4 条。
同一个谓词同时造成两个方向的错误，这进一步说明它不该承担 identity 判定。

救回样本的形状高度一致，全是「被吞进裸父概念的修饰语/病因/解剖限定完整对象」：
`Cutaneous Malakoplakia`、`Laryngeal histoplasmosis`、`Ipilimumab-induced dermatomyositis`、
`Tumor-induced osteomalacia`、`Compound odontoma`、`EBV Meningoencephalitis`、
`Cystoid Macular Edema (CME) Secondary to Retinal Vein Occlusion`。

### 3.5 按族拆分（§11.4 要求，合并均值的前提）

上游 §11.4 规定「DA/MCR 若方向相反，必须有预注册 interaction 解释，不能合并成总体均值」，
所以 +17/+13 在拆开验证之前不可报告。队列本身是平衡的：**400 DA + 400 MCR**
（DA `d2_seq100` 100 + `d2_heldout100` 100 + `d2_heldout200b` 200；
MCR `mcr_v1` 100 + `mcr_v2` 100 + `mcr_200b` 200）。已交付形态的逐族结果：

| 臂 | 族 | n | B0 addressable | 修复后 | rescue | harm | 净 |
|---|---|---:|---:|---:|---:|---:|---:|
| Forest | da | 400 | 20 | 26 | 6 | **0** | **+6** |
| Forest | mcr | 400 | 136 | 147 | 11 | **0** | **+11** |
| IMPC | da | 400 | 21 | 23 | 2 | **0** | **+2** |
| IMPC | mcr | 400 | 142 | 153 | 11 | **0** | **+11** |

**两族同向为正、harm 均为 0，六个切片无一为负**，所以合并均值在 §11.4 下合法。
但必须同时写明两件事：

**（a）收益明显偏向 MCR**：Forest 的 17 例里 11 例来自 MCR，IMPC 的 13 例里 11 例来自 MCR。
DA 上 IMPC 只有 +2/400（0.5pp），单独看它接近噪声。

**（b）原因不是测量覆盖，是 DA 的池本身几乎不含完整对象。** 先排除测量解释——
冻结端点对两族的判定覆盖率几乎相同（Forest da .9589 / mcr .9524；IMPC .9647 / .9608；
Collapse3c .9738 / .9728），所以差距不是「DA 判得少」造成的。真实原因是池级 complete 率：

| 臂 | DA 池内有 complete | MCR 池内有 complete |
|---|---:|---:|
| Forest | 20/400（**.0500**）| 138/400（.3450）|
| IMPC | 21/400（**.0525**）| 143/400（.3575）|
| Collapse3c | 24/400（**.0600**）| 153/400（.3825）|

三臂在 DA 上的池级 complete 率一致地只有 5–6%，而 MCR 是 34–38%。面板自身的关系分布
指向同一结论：DA 的 `partial_parent_or_component` 有 3,019 条而 `complete_equivalent` 仅 527 条，
MCR 则是 1,387 对 782。**即 DA 上管线产出的多是父概念/部分对象，完整对象根本没被生成。**

这给 identity 修复划了一条结构性上界：它只能救回「已生成但被折叠」的对象，
DA 上没什么可救，所以 +6/+2 不是实现不力，而是天花板在生成侧。
这与上游 §0 的自述一致——counterfactual 路线不解决 exposure/recall ceiling。
**DA 的瓶颈是生成，MCR 的瓶颈才是本轮修掉的这个 identity 缺陷。**

---

## 4. 因果闭环：Collapse3c 早已实现 V1

[`aphhm_c.py::ConceptRegistry._same_as`](../../../../src/agentclinic_tree_dx/aphhm_c.py) 的注释就是这条修复：

> Only confirmed equivalence merges. Substring is NOT same_as: it is a broader/narrower
> relation and must stay a separate concept.

它把 containment 谓词交给 `_relation()`，产出 `narrower_than`/`broader_than` 并写入
`merge_audit`，而不是折叠。800 例实测：

| 臂 | containment 事件 | 处置 | 真 `same_as` 合并 |
|---|---:|---|---:|
| Forest | 561（324/800 例）| **静默折叠为 alias** | — |
| IMPC | 452（257/800 例）| **静默折叠为 alias** | — |
| Collapse3c | 141（`narrower_than` 108 + `broader_than` 33）| **保留为 typed relation** | 47 |

三臂 E2 clinical-complete 分别是 Collapse3c 122/800、Forest 107/800、IMPC 98/800。
上游 §7.2 只能说「Collapse3c 是 specificity-retention 参考，不是 universal winner」；
现在这句话有了机制和数字：**它的一部分优势就是它没有犯 P0 第 1 处错误**，
而把这一条移植回 Forest/IMPC 是零调用的代码改动，可测上界 +17 / +12。

必须同时说清楚这不是全部归因：Collapse3c 还同时具备 typed fact 字段、candidate-specific
support/against spans 和关闭的全局 matrix。本轮只隔离出 identity 这一条，
没有声称它解释了 122 − 107 的全部差距。

---

## 5. Collapse3c 方向与 provenance 审计

### 5.1 provenance 绑定

| | support | contradict |
|---|---:|---:|
| span 总数 | 7,705 | 2,820 |
| **fact-ID 列** | 8,467 | **0** |
| exact 归一化可绑 | 7,330（95.13%）| 2,397（85.00%）|
| containment 唯一可绑 | 205 | 59 |
| containment 歧义 | 9 | 8 |
| **完全不可绑** | 161（2.09%）| **356（12.62%）** |

`against_fact_ids` 缺口即上游 §9.3 要的数：**2,820 条 contradict span 中 0 条有 ID**；
按 span 反绑最多回收 2,456 条（87.09%），**364 条（12.91%）无法绑定**。
不可绑的 span 无法携带 polarity/时间/特异性进入 intervention card，
因此在 §8.1 的数据对象定义下**根本不可审计**。这是 P2 的一个前置成本，不是一个可选项。

containment 绑定层单独列出是刻意的：上游 §6.2 已证 containment 正是静默混淆对象的那一层，
所以它是高召回标记，不是裁定。

### 5.2 方向审查队列（是队列，不是错误率）

| 项 | 计数 |
|---|---:|
| `polarity=absent` 被用作 support | 292 |
| 其中 specificity=high **且** reliability=high | **192** |
| `polarity=absent` 被用作 contradict | 777 |
| **同一 fact 对同一候选同时作 support 和 contradict** | **44** |
| ├─ 其中 exact 归一化层即可认定 | **28** |
| └─ 仅靠 containment 层才能认定 | 16 |

前三行**都不是错误率**，这点必须写死：某发现缺失去反对一个诊断通常是**正确**推理（777 之大部分），
而缺失也可以靠排除法**正确**支持一个诊断。上游 §3.3 的纪律是异常只进 review queue、不自动改答案，
本报告遵守。

唯一无需临床判断即可断定的缺陷是最后一行的 **44** 条自相矛盾边。样本说明它确实抓到真错：
`diagnosisarena/181` 与 `/4` 的 `Kaposi's Sarcoma` 把 `Negative for HHV-8` 同时列入 support 和 contradict，
而 HHV-8 阴性是排除 Kaposi 的依据。反例同样有教益：`diagnosisarena/220` 的
`Plasmablastic Lymphoma` 用 `CD20-negative` 作 support 本身是**对的**（CD20 阴性是该病特征），
错的只是它同时又被列为 contradict——**缺陷是自相矛盾，不是方向本身**。

44 条按绑定层拆分不是记账癖好，它决定了生产代码允许自动处理哪些：**28 条**在 exact 归一化层
即可认定，已交付的隔离机制全部抓到并撤回；剩余 **16 条**只有启用 containment 绑定才会出现，
而 §5.1 末段刚说过 containment 是高召回标记、不是裁定。为了凑满 44 而在生产数据路径里
放开 containment 绑定，等于把刚从 identity 里拿掉的混淆层重新装到 evidence 方向上。
这 16 条因此留在 review queue，不进自动撤回。

上游哨兵 `MCR 314` 精确复现：F11（`polarity=absent`、`specificity=high`、`reliability=high`，
"histopathology was negative for hyphae … cultures grew no bacteria or fungi"）位于
C04 `Sphenoid Sinus Invasive Fungal Sinusitis` 的 `support_fact_ids`。全案最具判别力的阴性证据被反向使用。

### 5.3 证据利用率

| 项 | 计数 | 占比 |
|---|---:|---:|
| fact 总数 | 9,333 | — |
| **从未绑定到任何候选** | **3,312** | **35.49%** |
| 支持超过一个候选（非判别性）| 2,029 | — |

**这个 35.49% 曾被本报告读成「大缺口」，按特异性拆分后该读法不成立，此处更正。**
只看 `support_fact_ids`（更严格的口径）未绑定 3,950 条（42.32%），但它几乎全部压在低特异一侧：

| specificity | fact 总数 | 未绑定 | 未绑定率 |
|---|---:|---:|---:|
| high | 2,718 | **24** | **0.88%** |
| medium | 3,552 | 1,404 | 39.53% |
| low | 3,063 | 2,522 | 82.34% |

**能判别一条边的高特异 fact 有 99.1% 已经挂上了。** 全 800 例中只有 12 例存在「未绑定、
非 provisional 的高特异 fact」，而其中 16 条已被现成的 `gap_obligations` 机制捕获。
所以未挂载的主体是管线**正确地忽略**了非特异发现，不是判别子流失；
§8.3 step 2 的「typed proposition build」在 Collapse3c 上既不是补字段、也不是补挂载。
真正的挂载缺口在 against 一侧（§5.1），不在 support 一侧。

---

## 6. P2 规模测算：`CF_EDGE_AUDIT_V1` 的上界

edge audit 只能在「完整对象已暴露、只是没被选中」时起作用；对象没暴露就没有边可审
（上游 §0 已声明这一点，本节给出它的数）。

### 6.1 frontier 层（§8.3 承认 top pair **加** protected 候选，故这是正确的口径）

| 项 | 计数 | /800 |
|---|---:|---:|
| champion 已 complete | 122 | .1525 |
| frontier 内存在 complete 对象 | 168 | .2100 |
| **conversion gap（frontier 有 complete 而 champion 不是）** | **50** | **.0625** |
| **其中该 complete 对象带候选独有高特异判别子** | **15** | **.0188** |

### 6.2 top-pair 层（§8.3 step 5 的字面版本）

| 项 | 计数 |
|---|---:|
| 有 disputed pair 的病例 | 800 |
| pair 中有候选独有**高特异**判别子 | 689（86.1%）|
| pair 中有候选独有证据（任意特异性）| 777（97.1%）|
| pair 无高特异判别子 | 111（13.9%）|
| **pair 中含 complete 对象** | **134** |
| 其中 champion 本来就已 complete | 109 |
| **其中 champion 未 complete（可翻转）** | **25** |
| **且带高特异判别子（P2 可寻址集）** | **22** |

### 6.3 怎么读

edge **可审计性**这一关过得很轻松：86.1% 的病例存在候选独有高特异判别子。
不过的是**规模**：

- top-pair 版本上界 **22/800 = 2.75pp**；
- frontier 版本上界 **15/800 = 1.88pp**；
- 两者都假设**每条边都朝正确方向解决**。文献侧的方向命中率并不支持这个假设——
  CSS 六模型 correct-direction 约 .309–.473，且 100 例医学复核里 37 例干预后不连贯。
  按这个量级折算，现实增益约 5–10 例。
- 而 134 例中有 **109 例 champion 本已正确**，这些是 harm 的暴露面。
  上游 §7.2 已记 IMPC 相对 Collapse3c 有 19 个 object rescue 却伴 32 个 catastrophic substitution；
  在 22 : 109 的比例下，一个方向判断有误的 edge 干预很容易净负。

对照 V1：上界 Forest 17 / IMPC 12（同量级甚至更大），**零调用**，且它是
「把 composite 折进父概念」这种不需要端点辩护的正确性修复。

---

## 7. 判决、次序与已交付项

### 7.0 为什么是这个次序

这四层的排序不是工作量排序，而是**依赖排序**：下一层的测量在上一层没修之前不可解释。

1. **identity**（对象是否存在且可寻址）。对象若被折进父概念，它的边、它的
   counterfactual、它的方向全都无处附着。所以这一层必须先修，而且它是**正确性修复**，
   不需要端点收益来辩护。
2. **evidence 方向自洽**（边是否携带非零方向信息）。一个 fact 同时作 support 和 contradict 时，
   任何在其上做的干预都在测量噪声。
3. **evidence schema**（是否存在可干预的字段）。Forest/IMPC 的 15,110 条 evidence 四个字段
   全为常量、`temporality` 不存在字段，所以第 3 层不动，counterfactual 干预**物理上无对象**。
4. **edge 干预**（`CF_EDGE_AUDIT_V1`）。只有 1–3 都成立后，它测到的才是机制效应。

上游审计把这四层写成五处**并列**的 P0 加一个 P2 主目标，本轮的分歧主要在这里：它们不是并列的。

**2026-08-23 更新：第 4 层已被 §9 否掉，取而代之的是新的第 4 层。** 第 2 层（方向自洽）
本轮补齐为完整的 validator 后，两道门同时关着：citation closure 92.4% < §11.2 的 98%；
且在真正决定胜负的边上，独占高特异判别子压在**错误冠军**一侧的比例是正确一侧的 2.0–3.4 倍，
而这已由厚度检验定性为「正确对象只拿到胜者一半的高特异证据」（MCR 0.97 vs 1.95）。
所以第 4 层应改为：

4'. **evidence attachment**（正确对象是否拿到它应得的高特异证据）。在这层修好之前，
    任何 selector 侧干预都只会更清楚地复述一个偏向错误候选的证据集。

### 7.1 已交付（零调用，已通过验收）

**（i）safe identity 移植进 `mosaic.py`。** `_match` 只保留 exact 归一化与既有 resolver 钩子；
containment 交给新的 `_relation()` 产出 `narrower_than`/`broader_than` 并写 `merge_audit`。
配套加一条有界准入规则：父子对同时入选时按「一次拆分退一个坑位」退坑，迭代到不动点，上限 2。

刻意**不**接分析层的冻结同义桥。生产 `run_mosaic.py` 以 `resolver=None` 运行，而带桥变体
（V1p）与不带桥变体（V1bp）在 Forest 完全等价、在 IMPC 同为 176/harm 0；生产侧现成的
`DiseaseNameResolver` 反而带 substring/fuzzy 层，正是本轮要拿掉的东西。
换言之：**这个收益不欠任何分析层依赖**。

**（ii）Collapse3c 的方向绑定与自相矛盾边隔离。**
`ConceptRegistry.audit_directions()` 给 `contradict_spans` 补上
`contradict_fact_ids` 列（即上游 §9.3 要的 `against_fact_ids`），再撤回同一 fact 对同一候选
既 support 又 contradict 的边，两侧同时撤回并写 append-only 的 `direction_quarantine`。
（原名 `bind_and_quarantine_directions`；§9.0 拆开绑定/校验/撤回三层后改名，
撤回改由 `quarantine_direction_conflicts` 控制、默认关闭。）
必须是全部摄取之后的后置扫描：support 可能来自一个 stance、矛盾断言来自另一个，
逐条摄取时看不到冲突（已有回归测试覆盖该跨路径情形）。

哪一侧临床上正确无法离线判定，所以契约是**撤回加记录**，不是猜一个修复——遵守上游 §3.3。

**这一项是正确性修复，端点上界近乎零，必须与 (i) 分开记账。** 理由是结构性的：
`EvidenceLedger.score_concept` 只读 C4 矩阵 cells，**从不读** `support_fact_ids` 或
`contradict_spans`，所以撤回对分数、排序、frontier 的改动**恒为 0**；它唯一的因果通路是
selector 读到的文本。而 Collapse3c 跑在 `c4_selector_candev_nomatrix`
（`enable_matrix=False`、`selector_candidate_evidence=True`），`for`/`against` 恰是 selector
唯一的按候选证据——通路对，但要过两道闸门：概念须在 frontier 内，且撤回的 span 须落在
`support_spans[:4]` / `contradict_spans[:3]` 的截断窗口内。实测（`cf_quarantine_reach.py`）：

| 项 | 计数 | /800 |
|---|---:|---:|
| 确定性分数/排序/frontier 变动 | **0** | — |
| 含被隔离边的病例 | 26 | .0325 |
| 边落在 frontier 候选上 | 25 | — |
| 边落在 selector 截断窗口内 | 25 | — |
| **selector payload 真的变了的病例** | **23** | **.0288** |

23/800 是这项修复能移动答案的绝对上界。再按角色与「失去哪一侧」交叉拆分（撤回同时动两侧，
所以符号取决于 selector 实际少看到什么：对正确答案撤掉一条 against 是**加强**，撤掉 for 才可能有害）：

逐族同样拆开（§11.4）：DA 12 条边 / 10 例 payload 变动 / **0** 条命中 complete 候选；
MCR 16 条边 / 13 例 payload 变动 / 4 条命中 complete 候选。
即这项修复在 DA 上连一条边都没落在完整对象上，其全部端点暴露面都在 MCR。
against 一侧的 exact 闭合率两族都不过 §11.2 的 98% 门：DA **.8391**、MCR **.8586**。

| 受影响候选 | against_only | both | 读法 |
|---|---:|---:|---|
| complete 且是 champion | 2 | 1 | 前 2 例是正确答案少一条虚假反对，非损害；仅 1 例两侧皆失、方向不明 |
| complete 非 champion | 1 | 0 | **唯一真正的 rescue 暴露** |
| 错误 champion、但 frontier 内无 complete | 3 | 0 | 削弱它也换不出正确答案，惰性 |
| 既非 complete 也非 champion | 16 | 2 | 惰性 |

所以端点暴露面是 **1 例可能 rescue、至多 1 例可能有害、21 例惰性**。
在 800 例上这与零不可区分，且本轮无法测量（通路全在 LLM 内）。
**它值得做的理由是「同一 fact 不能同时支持和反对同一候选」这种不需要端点辩护的自洽性，
不是它能涨分。** 任何把它与 (i) 的 +17/+13 并列宣传的说法都超出证据。

**（iii）验收。** 两项都不是「改完就算」，而是要求打过补丁的生产代码在同一批冻结 payload 上
精确复现离线测得的数：

| 验收 | 脚本 | 结果 |
|---|---|---|
| 生产 registry 复现 V1bp 臂 | [`cf_identity_port_verify.py`](../../cf_identity_port_verify.py) | Forest **173**、IMPC **176**，alias 掩蔽双双 **0**，PASS |
| 生产隔离复现 exact 层冲突 | [`cf_quarantine_verify.py`](../../cf_quarantine_verify.py) | 隔离 **28/28**，残留冲突 **0**，against ID 列补上 2,369 条，PASS |

回归测试同时锁住三条不变量（`scripts/paper/test_mosaic_unit.py`、
`tests/test_aphhm_c_direction_quarantine.py`）：containment 不得折叠、exact/大小写变体仍须合并、
拆分不得挤掉无关第三方。全库 797 项通过；5 项既有失败与 3 项既有错误均不加载这两个模块
（失败点在 `controller.py`）。

**（iv）这一步测的仍是 addressability，不是 conversion。** conversion 需要一次在线 selector 重跑，
配对设计现成：frontier 发生变化的只有 Forest 325 例、IMPC 260 例，只需重跑这些例。
IMPC 一侧还有一条更强的先验：它的 176 已等于 pool 上限，说明 IMPC 的剩余损失**全部**在 selector 侧。

### 7.1b 修复后三臂的位置变了：瓶颈从 recall 移到 conversion

三臂同一 `ClinicalEndpoint` + `drop_conflicts()` 口径，addressability 都是
「frontier 内是否存在 complete 对象」，champion 都取日志内实际产出：

| 臂 | frontier 均宽 | addressable | 率 | champion complete | 率 | **转化率** |
|---|---:|---:|---:|---:|---:|---:|
| Forest（日志）| 4.327 | 156 | .1950 | 107 | .1338 | .686 |
| IMPC（日志）| 4.053 | 163 | .2037 | 98 | .1225 | .601 |
| **Collapse3c（日志）** | 4.264 | 168 | .2100 | **122** | **.1525** | **.726** |
| Forest（修复后）| 4.914 | **173** | .2162 | 未知，需在线重跑 | — | — |
| IMPC（修复后）| 4.489 | **176** | .2200 | 未知，需在线重跑 | — | — |

三条必须一起读：

1. **Collapse3c 的 addressability 优势已被抹平并反超**：168 → Forest 173、IMPC 176。
   「Collapse3c 是 specificity-retention 参考」这个说法在 addressability 这一层不再成立，
   因为 Forest/IMPC 的差距本来就**只是**这一处 identity 缺陷造成的。
2. **但 Collapse3c 仍然在真端点上领先（122 vs 107/98），因为它赢在 conversion（.726 vs .686/.601），
   而本轮的修复完全不触碰 conversion。** identity 修复只把对象放进 shortlist，选不选是 selector 的事。
3. 因此可以下一个**可证伪的预测**：若修复后重跑 selector，Forest/IMPC 仍不及 Collapse3c，
   则剩余差距**全部**是 selector/裁决机制问题，不再是召回问题。IMPC 一侧的先验更强——
   它的 176 已等于 pool 上限，addressability 已无余量。

这也重新定位了 Collapse3c 在本轮的角色：它是 identity 修复的**供体**（141 次 typed relation
而非折叠），不是受益方；它本轮唯一收到的改动是 §7.1(ii) 那项端点上界近零的自洽性修复。
它自己尚未修的缺口只剩一处**在 counterfactual 路线范围内**：against 一侧的 exact citation
closure 只有 85.0%（423 条 span 无法绑定），而 §11.2 的 gate 要求 ≥98%。
另一处曾被本报告列为缺口的「未挂载 fact」按 §5.3 更正已撤回：高特异 fact 已 99.1% 挂载。

### 7.2 暂不做：按现设计预注册 `CF_EDGE_AUDIT_V1`

> **2026-08-23：本节从「暂不做（规模太小）」升级为「不应按现设计做（方向压在错误一侧）」。**
> §9.3 补上了本节缺的那个量：可寻址集不只是小，它的判别子还系统性地偏向错误冠军
> （错误侧 : 正确侧 = 2.0–3.4 : 1），且 top-2 触发器有一半时间不含要救的候选。
> §9.1 同时把 closure 从「against 85.0%」修正为「含 support 的合计 92.4%」。

理由是规模，不是机制被否证：

- 可寻址集 15–22/800，是绝对上界；
- 前置成本包含补 `against_fact_ids`（已交付 (ii) 解决其中的 ID 列一项）与 §11.2 的六项
  construction gate。**「给 3,312 条未挂载 fact 建挂载」这条前置成本本报告先前列错了，此处撤回**：
  §5.3 更正后显示高特异 fact 已 99.1% 挂载，不存在需要补建的判别子挂载；
- **但 §11.2 的 exact citation closure ≥98% 这一条现在就不过**：against 一侧 2,820 条 span
  只有 2,397 条（**85.0%**）能在 exact 层闭合，含 containment 层也只到 87.1%。
  也就是说约 15% 的 against span **在 §8.1 的数据对象定义下无法构成 intervention card**，
  这既是 P2 的前置工作量，也进一步压缩它的可寻址集；
- harm 暴露面（109 例已正确的 pair）是可寻址集的 5 倍；
- 上游 §11.2 自己规定 gate 不过就只发布 validity audit，不跑 downstream accuracy。
  本报告就是那份 validity audit，而它给出的结论是**先修 identity，再谈 edge**。

### 7.3 明确不成立的路径

在 Forest/IMPC 现有 `EvidenceFact` 上做「删阴性 / 改时间 / 按可靠性衰减」的 counterfactual：
15,110 条 evidence 的这四个字段是恒定默认值，`temporality` 连字段都没有。
这不是效果小，是物理上没有可干预的对象。任何这类臂必须先完成 P0 第 4 处。

---

## 8. 可识别性边界

可识别：

- 候选 identity、addressability、确定性 pre-selector score、two-lane frontier 成员与顺序（B0 保真 1,600/1,600）；
- Collapse3c 的 span→fact 绑定层级、polarity 方向、边唯一性、fact 挂载率；
- 上述各量在五个策略下的差分。

**不可识别：**

- selector 在它从未见过的 frontier 上会答什么。救回的候选是 **addressable**，不是 **answered**；
- 被标记的边在临床上是否真错。§5.2 是 review queue，不是错误率；
- 任何边修正之后的 clinical-complete 因果效应——这需要新调用；
- 本报告全部 clinical 关系来自三模型 panel（五分类 exact accuracy .7082、Gwet AC1 .6544，
  `complete`/`partial` 边界正是最难的那条），是 **model-panel sensitivity，不是 human root truth**；
  800 例是被反复使用的**开发集，不是确认集**。§3 的 .1950→.2162（Forest）与 .2037→.2200（IMPC）
  属开发集上的机制量，不得当作可发表的效应量。

需要单独说明验收覆盖了什么、没覆盖什么：§7.1(iii) 证明的是**打过补丁的生产代码与离线测量口径一致**
（同一 substrate 上数字精确重合），**不是**该修复在新病例或在线 selector 下的效果。
后者仍然需要 §7.1(iv) 那次重跑。

---

## 9. 方向校验与 pair-edge audit（2026-08-23，零调用）

脚本 `analysis/mechanism_v2/cf_direction_validator.py`，输出 `direction_validator.json`。
落地代码：`aphhm_c.py` 的 `ConceptRegistry.audit_directions()` 与
`AphhmCPipeline._fact_cards()` / `_pair_edge_audit_payload()`。

### 9.0 开关形态：本报告上一轮的一处违规已纠正

`aphhm_c.py` 的既有约定是「改行为的机制一律做成 `__init__` 默认 `False` 的 kwarg，
经 CLI 传入并写进 `manifest.json`」——`near_dedup_shortlist`、`enforce_group_quota`、
`strict_identity` 全部如此，且 `strict_identity` 本身就是正确性修复却仍默认关闭，
这是强先例。上一轮把自相矛盾边隔离做成**常开**，改了 selector 可见字段却不进 manifest，
等于让 `aphhm_c_collapse3c_v1` 未来重跑与归档臂静默不一致。本轮拆成三层：

| 层 | 是否常开 | 理由 |
|---|---|---|
| 绑定 `contradict_fact_ids` | 常开 | 纯新增字段，不改任何既有可见字段 |
| 校验 + review queue | 常开 | 只观测、只报数，不可能改变归档臂 |
| 撤回自相矛盾边 | `quarantine_direction_conflicts`，默认关 | selector 可见 |
| typed fact cards | `typed_selector_cards`，默认关 | selector 可见 |
| pair-edge audit | `pair_edge_audit`，默认关 | selector 可见 |

`mosaic.py` 的 identity 修复取另一档：`MosaicPipeline(safe_identity=True)`，
**做成开关但默认打开**，写入 `manifest.json`，可用 `--legacy-containment-identity`
还原 pre-repair 谓词以逐字复现归档 Forest/IMPC 臂。理由是它与上面三项的性质不同——
上面三项的端点效应未测（故不应默认改变任何人的结果），而 identity 一项已零调用测得
净 +17/+13、harm 归零，让新运行默认继续带 bug 没有道理。legacy 路径有专门回归测试
（`test_legacy_flag_restores_the_fold_so_archived_arms_can_replay`），
否则 manifest 里的 `safe_identity: false` 会是一句没有东西支撑的声明。

### 9.1 citation closure：§11.2 的 ≥98% 门两侧都不过

先前只报了 against 一侧的 85.0%。把 support 一侧一并计入后（§11.2 的门是对 citation 而言，
不限方向）：

| 族 | against span | against 闭合 | support span | support 闭合 | 合计闭合 | 逐例达标率 |
|---|---:|---:|---:|---:|---:|---:|
| DA | 1,243 | .8391 | 3,837 | .9518 | **.9242** | .6275 |
| MCR | 1,577 | .8586 | 3,868 | .9509 | **.9242** | .6300 |

两族合计闭合率同为 92.4%，距 98% 差 5.6pp，且只有约 63% 的病例自身达标。
**这是 P2 的硬前置，不是可以四舍五入过去的余量。** 绑定只用 exact-normalized，
不用 containment——§6.2 已证 containment 正是混淆不同命题的那一层。

review queue（只报数、不自动改）：`absent` 且高特异却被当作 support 的边 DA 92 / MCR 99 条，
这**不是错误**（排除法可以正当地由阴性支持诊断），故只入队不撤回。

### 9.2 pair-edge audit 看到了什么

先修一处标签缺陷：collapsed 臂矩阵关闭，`score_concept` 无 admitted cell 可读，
**全部 800 例的所有候选 `score` 恒为 0.0**，故 `tied_score` 恒真。它曾占据
DA 183/400、MCR 197/400 的 disputed_reason，纯属退化伪信号，已降级为 `scores_tied` 字段。

修正后 top-2 边的分布（每族 400 例全部可审）：

| disputed_reason | DA | MCR |
|---|---:|---:|
| 一侧独占判别子（可裁决） | 183 | 197 |
| 双方各有独占高特异判别子 | 166 | 115 |
| 两侧都无独占高特异判别子 | 30 | 74 |
| broader/narrower 未解（粒度问题，非证据问题） | 15 | 5 |
| 自相矛盾边未隔离时残留 | 6 | 9 |

一个语义修正值得记下：最初把「同一 fact 同时支持 A 和 B」判成 conflicting，
这是错的——那是**共享的非判别证据**，而「支持 A、反对 B」才是干净判别子。
两者混为一格会让大量共享发现看起来像矛盾。现按双角色显式分类，
DA 共享支持 230 条、MCR 318 条，均标 `discriminating: false`。

### 9.3 决定性结果：它够不到 conversion gap，而且瞄错了边

只有「完整对象已在 frontier 但没当上 champion」的病例才是 edge audit 的目标。
45 例（DA 6 / MCR 39）：

| 项 | DA | MCR |
|---|---:|---:|
| gap 例数 | 6 | 39 |
| **完整对象落在 top-2 边内** | **.5000** | **.4872** |
| 决定边上独占判别子在**正确**一侧 | .1667 | **.1282** |
| 决定边上独占判别子在**错误冠军**一侧 | .3333 | **.4359** |
| 两侧都没有判别子 | .1667 | .2051 |

两件事同时成立：

1. **§8.3 step 5 的 top-2 触发器有一半时间不含要救的候选**（50.0% / 48.7%），
   所以按现设计实现的 edge audit 连目标都锁不上；
2. 更要紧的是，在**真正决定胜负的那条边**（champion vs 完整对象）上，独占高特异判别子
   落在**错误冠军**一侧的比例是正确一侧的 **2.0 倍（DA）/ 3.4 倍（MCR）**。

### 9.4 厚度混淆检验：gap 的真实成因是证据挂载，不是选择器阅读

上一条不对称可能只是「完整对象证据本来就更少」的假象，故直接量它：

| 族 | 高特异 support（完整对象） | 高特异 support（错误冠军） | 全部 support（完整） | 全部 support（错误冠军） |
|---|---:|---:|---:|---:|
| DA | 1.83 | 2.00 | 2.33 | 2.83 |
| MCR | **0.97** | **1.95** | 1.79 | 2.85 |

MCR 上正确答案平均只拿到 **0.97** 个高特异支持 fact，胜出的错误候选拿到 **1.95** 个，
**正好两倍**。所以 MCR 的 conversion gap 不是「selector 读不到判别证据」，
而是**生成器给正确对象挂的高特异证据只有胜者的一半**。
typed cards 和 edge audit 做得再对，也只会把「错误候选的证据更具体」这件事讲得更清楚。
DA 的厚度差很小（1.83 vs 2.00），但 DA 只有 6 例 gap，其瓶颈仍是 §3 已定的
「完整对象根本没被生成」（addressable 仅 5–6%）。

**结论：`CF_EDGE_AUDIT_V1` 不应按 §8/§11 现设计预注册。** 两道门同时关着——
citation closure 92.4% < 98%，且即便闭合达标，判别子的方向本身就压在错误一侧。
下一步唯一有效的目标是 **evidence attachment**：让正确对象拿到它应得的高特异证据。
那是生成/挂载层的问题，不是 selector 干预层的问题。

### 9.5 本节不可识别的部分

- 三个开关默认关闭，故**它们对真端点的效应本轮无任何测量**，只有结构量与上界；
- 「错误冠军的判别子」是否临床上真的更强，本节不判定——它只说 panel 认定的完整对象
  在证据厚度上处于劣势；
- 45 例 gap 的分族样本极小（DA 仅 6 例），DA 的三个比例不应单独引用。

---

## 10. 结案：§9.3 指出的下一步也已测死，selector 侧全线关闭

§9.3–§9.4 把下一步定为 **evidence attachment**。该方向随后同样以零调用测死，
并顺带订正了本报告两处口径。两份后续文档：

- [`EVIDENCE_ATTACHMENT_AND_ORDER_COUNTERFACTUAL_PLAN.md`](../../EVIDENCE_ATTACHMENT_AND_ORDER_COUNTERFACTUAL_PLAN.md)
- [`../ORDER_COUNTERFACTUAL/REPORT.md`](../ORDER_COUNTERFACTUAL/REPORT.md)

### 10.1 口径订正（影响 §9.3 的 gap 计数）

`c4_selector_candev_nomatrix` 属 `selector_all_concepts`，`shortlist = ranked`——
**selector 看到整个池，frontier 只是 lane 标记。** §9.3 用 4 宽 frontier 当 selector 输入，
故 conversion gap 应为 **55/800**（DA 9 / MCR 46）而非 45/800；仅 5 例的完整对象落在
frontier 之外，量级未变，§9.4 的厚度结论不受影响。

### 10.2 attachment 三形态的死因

补孤儿证据（gap 例平均仅 0.04–0.11 条孤儿高特异 fact）；复活 protected lane
（正确对象持有池内独有高特异 fact 仅 19.6%，冠军 39.1%——优先保护的是已赢者）；
EA-RAG 式生成侧覆盖审计（623 例池内无完整对象中，仅 2.6–4.2% 存在未被解释的高特异发现）。
第三条最关键：**EA-RAG 的前提「retrieval 未覆盖 discriminator」在本系统不成立**，
池子已解释约 97% 的高特异发现，只是用错误诊断解释——与 §5.3「高特异 fact 已 99.1% 挂载」互为印证。

### 10.3 §9.4 的因果归属已被独立检验并证实

§9.4 把厚度差解读为「证据真的偏向错误候选」。这一步当时是**相关**而非因果：
还存在一个竞争解释——先生成的候选同时获得更厚挂载并占据呈现首位，selector 只是跟随位置
（全 800 例中冠军占池内 index 0 达 71.0%，均匀期望 19.2%，集中度 3.69×）。

R6 的 X4 归档探针（3 个种子的顺序置换）分离了这两者：

| 读数 | DA | MCR | 位置锚定预测 | 先验代理预测 |
|---|---:|---:|---:|---:|
| 冠军身份稳定性 | .852 | .885 | ≈ 0 | ≈ 1 |
| **置换后 index-0 率** | **.190** | **.243** | ≈ .70 | ≈ .192（均匀） |

**判决：先验代理。** 置换后 index-0 率塌到均匀期望，即 selector 把它那个候选带着走。
残余 12–15% 顺序敏感度净有害（救回 11、打翻 20）。
**故 §9.4 的字面解读成立：证据确实偏向错误候选。**

### 10.4 判决

selector 侧三条路线——P2 edge 干预（§7.2）、evidence attachment（§9.3）、
呈现顺序——**全部关闭**。端点天花板锁在 623/800（77.9%）**正确答案根本不在池内**这一事实上；
剩余杠杆在生成/知识侧，不在选择侧。
