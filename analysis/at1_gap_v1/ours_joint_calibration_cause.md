# 阶段 2a：Joint 首位校准根因

**代码锚点**：`scripts/paper/diagnosisarena_l2_pipeline.py` → `run_joint_primary`；实现细节 `scripts/eval_l2_joint_dynamic_pipeline.py`（`_joint_arbitrate` / `_build_champions`）。  
**Arbiter prompt**：`src/agentclinic_tree_dx/prompts/l2_joint_champion_arbiter.txt`。

## 1. 现行 joint 机制（摘要）

1. 每 L1 家族动态选出 **local champion**（组内竞争 + local audit）。
2. Between-family **evidence selector** 选至多 2 条跨组证据。
3. **A3 arbiter** 对全部 champion 做一次列表排序：输入为 selected_evidence、champions（含 soft `parent_posterior`、可选 local_audit），输出 `ranked_candidate_ids`。
4. `selector_effects` 在本方法主路径中传入为空列表（未做结构化 support/contradict 效应注入）。

## 2. 对照问题答复

| # | 问题 | 结论 |
|---|------|------|
| 1 | Arbiter 是否缺显式 support/contradict 计数？ | **是。** Prompt 要求自然语言 `why`，无 support/contradict 条数；排序不保证可复现的计数破平。对照 Dual-Inf `_rank_by_support`（按 reasons 长度排序）。 |
| 2 | Champion/动态证据是否偏向过窄特异叶？ | **部分是。** Local champion 在家族内用局部证据胜出，易抬高「药物诱导 / 部位特异 / 并发症」叶；跨组 arbiter 又只看 1–2 条 between 证据，特异叶叙事一旦占优，会把更规范的兄弟叶压到 #2（A 集 Fine 挤占多见）。 |
| 3 | Prior 是否压平 Top1–Top2 间隔？ | **可能软化间隔，非主因。** `parent_posterior` 为 soft prior；prompt 写明特异矛盾可推翻 prior。但无数值 margin 输出，无法在线检测「近乎打平」。 |
| 4 | JSON fail-open？ | **历史脚注。** 解析修复后主指标已用官方 merged_100；本调研不以 fail-open 解释当前 @1 gap。 |

## 3. 与 A 集现象的连接

- A 集 19 例中 **13 例 Top1/Top2 标签同义或同谱** → arbiter 在「几乎不可辨」的平行冠军间做硬排序，必然制造 @2∧¬@1。
- 无 support 计数 → 无法像 Dual-Inf 那样在近并列时用证据条数稳定破平。
- 无 Top2 集合护栏 → 任意一次 arbiter 交换都会直接改写 mapper 输入的首位叶。

## 4. 设计含义（喂给阶段 5）

1. 在 **joint 之后**增加封闭候选的 `TopKCalibration`：显式 support/contradict + 可选 pair adjudicate。
2. 对近并列平行叶：**禁止假装打分能根治** → 走 `AdaptiveMergeSiblings`。
3. 校准失败时允许 **回退 L1 代表叶序**（见 2b：A 集上 L1-prior 叶重匹配 @1≈0.63）。

产出完成：本文件。
