# 预注册：`ORDER_COUNTERFACTUAL_V1` —— 呈现顺序是否在驱动冠军

> **⚠️ 已于 2026-08-23 执行前撤回，1600 次调用预算未支出。见 `REPORT.md`。**
>
> 撤回理由：本实验**已经跑过**。R6 的 X4 探针在同一 Collapse3c 池上做了 3 个种子的
> 顺序置换，逐例输出留存于 `logs/backbone_v1/*/r6_x4_c3c_s{0,1,2}`，只是当年仅按
> 准确率 spread 分析。用本预注册指定的统计量重算归档数据（`cf_order_stability.py`，
> 0 调用）得到：θ = **.148**（DA）/ **.115**（MCR），且置换后 index-0 率从 .66/.70
> **塌到 .190/.243 ≈ 均匀期望 .192**。后者直接否掉 H1：若 selector 锚定位置，
> 置换后 index-0 率按定义应维持在 .70。判决为 **H2**——生成序预测冠军但不驱动冠军。
>
> 下文预注册内容原样保留，供核对「预先写死的预测是否被事后调整」。
> 核验结果：预测 1、3、4 成立；预测 2 在 DA 上不成立（但该层 42 对，本预注册第 6 条
> 门控已禁止单独引用）。§0 中「71.0% 集中度可能是位置锚定」的怀疑**不成立**。

实验 ID：`ORDER_COUNTERFACTUAL_V1`
日期：2026-08-23
性质：**既有机制的效度审计（validity audit），不是新机制的涨分试验。**
可行性检查：`analysis/mechanism_v2/cf_order_feasibility.py` → `feasibility.json`，判决 **FEASIBLE**（0 调用）

## 0. 一句话

Collapse3c 的 selector 在 800 例冻结日志上有 **71.0%** 选中呈现序列的第 0 位
（DA .6875 / MCR .7325），而按实际池宽加权的均匀期望是 **.192**——集中度 **3.69×**。
本实验只扰动呈现顺序这一个变量，用以判定这是**位置锚定**还是**真实临床先验的代理**。

反讽之处必须记录在案：`selector_unanchored` 引入的目的正是撤掉分数锚（离线重算显示 ordinal
score 与 gold rank 反相关），其实现为 `sorted(key=concept_id)`，注释写「按生成序呈现使
shortlist 不携带排序」；但 concept_id 序**就是**生成序，因此撤掉一个锚之后装上了另一个。

## 1. 队列（冻结后不得改）

- 臂：`aphhm_c_collapse3c_v1`，**全部 800 例**（DA 400 + MCR 400），不抽样。
- 日志根：`logs/backbone_v1/{diagnosisarena, diagnosisarena_heldout, diagnosisarena_heldout200b,
  medcasereasoning, medcasereasoning_v2, medcasereasoning_200b}/aphhm_c_collapse3c_v1/case_stages`
- 入选条件：池宽 ≥ 2（池 = `ledger_rank`，即该臂 `selector_all_concepts=True` 下的真实 selector 输入）。
- 临床关系来自既有三模型 panel，`drop_conflicts()` 后使用；**analyze 阶段才读，在线 payload 禁止 gold**。

## 2. 装置（冻结）

- **C1/C3 不重跑。** registry 与 fact ledger 逐字取自归档臂，因此三臂共享同一 substrate，
  `generation` 臂**成本为 0**（直接用归档回复）。
- 三臂共用同一 selector prompt（`aphhm_c_frontier_selector_candev.txt`）、同一模型、
  同一 `max_calls`、同一截断窗口（`support_spans[:4]` / `contradict_spans[:3]`）。
- 三个新开关一律**关闭**（`quarantine_direction_conflicts` / `typed_selector_cards` /
  `pair_edge_audit`），以免与顺序效应混淆。
- 唯一变化：`AphhmCPipeline(selector_order=...)`，记入 `manifest.json`。

## 3. 三臂

| 臂 | 呈现序列 | 成本 | 角色 |
|---|---|---:|---|
| `generation` | `sorted(key=concept_id)`（现状） | 0 | 基线，取归档 |
| `reverse` | 完全逆序 | 800 | **主臂**：最大位置扰动，无需defend种子 |
| `permuted` | `sha256("order-cf-v1\|case_id\|concept_id")` 升序 | 800 | 确认臂：与生成序去相关 |

置换只以 `case_id` 与 `concept_id` 为种子，**不看标签、不看分数**，故可从 manifest 复现，
且不携带候选内容信息。

可行性检查已验证非退化性：`reverse` 100% 改变序列且 100% 改变第 0 位；
`permuted` 99.25% 改变序列、78.75% 改变第 0 位。

## 4. 分层（冻结，来自可行性检查）

| 分层 | DA | MCR | 合计 | 预注册的正确响应 |
|---|---:|---:|---:|---|
| `control_champion_already_complete` | 15 | 107 | **122** | 冠军**不应**改变 |
| `gap_complete_in_pool_champion_wrong` | 9 | 46 | **55** | 允许改变，应移向完整对象 |
| `inert_no_complete_in_pool` | 376 | 247 | **623** | 改变不影响正确性；提供纯顺序敏感度基线 |

`control` 层是本设计的核心而非附带：上一轮把这 122 例记作「harm 暴露面」，
在方向响应框架下它们是**特异性对照**——若仅改变顺序就打翻一个本已正确的冠军，
那是过度响应，正是 MedCounterFact 警告的失败模式。

## 5. 主端点与两极标定

**主端点：`stability` = P(冠军在 `reverse` 下与 `generation` 相同)。**

它之所以是主端点，是因为它有两个**预先算得的极点**，而不是一个需要事后解释的方向：

| 假设 | 预测的 `stability` | 理由 |
|---|---:|---|
| H2 纯证据驱动（顺序只是先验的代理） | **≈ 1.00** | 同一候选集、同一证据，位置改变不应改变结论 |
| H1 纯位置锚定 | **≈ 0.00** | 恒选第 0 位；逆序后第 0 位几乎必为另一候选（池宽 ≥ 2） |

因此定义位置驱动份额

    θ = 1 − stability

θ 是一个**可直接解读的效应量**：它估计「由呈现位置而非证据决定的判决占比」。
`permuted` 臂给出第二个 θ 估计，两者一致性是效度检查（不一致则说明存在与逆序特异相关的
artifact，需在报告中单独讨论，不得取平均）。

辅助读数（全部**逐族分报**，禁止合并均值——DA/MCR 池内完整率差 6 倍）：

1. `index0_rate` 在三臂上的值。基线 .710（DA .6875 / MCR .7325）。
2. `p_new_at_index0` = P(新冠军位于新序列第 0 位 \| 冠军改变)。纯位置锚定 → 高；证据驱动 → 趋近 .192。
3. `position_free_accuracy`：三臂 clinical-complete 的**多数投票**与逐臂均值。
   这是本项目至今没有的一个量：扣除位置效应后的准确率。
4. `css_direction_score ∈ {0, 0.5, 1}`，仅在 55 例 `gap` 层评分：
   1 = 移到完整对象；0.5 = 移到另一非完整候选；0 = 不动或移离。

## 6. 预注册预测（写死，不得事后调整）

1. `stability` < 1.0，即 θ > 0。（若 θ = 0，位置集中度 3.69× 完全由先验解释。）
2. `inert` 层的 θ 与 `control` 层的 θ **同量级**。若 `control` 层 θ 显著更低，
   说明选择器在有正确答案时更依赖证据，位置效应是条件性的。
3. `reverse` 与 `permuted` 的 θ 相差 < 0.10。
4. `gap` 层 55 例的 CSS 均分 **不预期** > 0.5——顺序扰动不提供新判别信息，
   预期它把冠军打散而非打准。**本实验不预期涨分。**
5. `position_free_accuracy` ≤ 现状 accuracy。多数投票只去噪，不增信息。

## 7. 停止规则（分阶段，省一半预算）

先只跑 `reverse`（800 调用）。

- 若 **θ ≤ 0.10**：位置效应小，H2 基本成立，「错误候选证据更多」应读作真实先验。
  **停止**，不跑 `permuted`，发布 validity audit 并据此正当关闭 P2 与挂载路线。
- 若 **θ > 0.10**：继续 `permuted`（再 800 调用）以确认并给出第二个 θ 估计。

两个方向都改变后续判断，不存在「白跑」的分支。

## 8. 门控

1. `champion` 必须在供给的 shortlist 内；越界计服务失败并单独报，**不用 gold 兜底**。
2. 候选集合在扰动前后必须是同一 multiset；实现层已 `raise AssertionError`，
   可行性检查在 800 例上 order-only 违规 **0**。
3. 每条 candidate note 在重排后必须逐字不变（可行性检查已验，0 违规）。
4. 在线 payload 禁止 gold / options / 分层标签。
5. `manifest.json` 必须记录 `selector_order` 与三个开关状态。
6. 逐族分报；DA `gap` 仅 9 例，DA 侧该层任何比例**不得单独引用**。

## 9. 调用预算

| 阶段 | 调用 |
|---|---:|
| `generation`（归档，免费） | 0 |
| 阶段一 `reverse` | 800 |
| 阶段二 `permuted`（条件触发） | 800 |
| **上限** | **1600** |

对照：先前评估「重开 C4 全局矩阵」需 400–500 次调用且已被四份报告否掉；
本实验同量级，但它审计的是一个已在生产里生效的机制。

## 10. 可识别性边界（预先声明）

- 本实验判定的是**呈现位置**与冠军的因果关系，**不是** gold 正确性的因果关系。
  θ 高不等于「修掉位置效应就会涨分」——55 例的天花板与 623 例池内无答案的事实不因此改变。
- 800 例是被反复使用的**开发集，不是确认集**；panel 五分类 exact accuracy .7082、Gwet AC1 .6544，
  `complete`/`partial` 恰是其一致性最低的边界。
- `reverse` 是最大扰动，θ 由它估计时是**上界**倾向；`permuted` 的估计更接近平均情形。
- 若 selector 存在与内容无关的「近期性」偏置（偏好末位），逆序会与之混淆；
  `permuted` 臂正是为此设置，两臂不一致时必须分开报告。
- 本实验不改变 `citation closure = .9242 < .98` 这一事实；它不依赖该门，因为它不动引用。
