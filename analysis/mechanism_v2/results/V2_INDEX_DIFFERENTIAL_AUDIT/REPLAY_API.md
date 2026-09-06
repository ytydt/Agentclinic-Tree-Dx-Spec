# 完整重放与差量账本接口

本接口只读历史四臂提取文件、病例、已有嵌入和 corpus lift 表；不调用模型，不修改生产执行器。`replay_audit.py` 在内存中编译 `run_case` 的带追踪副本。所有文本插入点要求恰好匹配一次，贡献列表解除前 25 条截断。原生产输出删去审计元数据、重新截取前 25 条后，必须与上一提交的 44 条完整历史输出完全相等。

## 复现

从仓库根目录运行：

```bash
python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/replay_audit.py
python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/build_replay_deltas.py
python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/run_system_probes.py
```

`--case 'MCR_v1_seq100/74' --arm 0` 可进行单例重放，但会将汇总/验证文件写为该子集；正式交付应以全量命令最后运行。生产配置是 B1/S7：loose、IDF、groups、embedding fallback 0.60、marker、organism、enum clamp、corpus lift clip 1、all-as-required、F7。F7 使用历史默认来源查找，**不是实际 arm 对应窗口的重新对齐模式**。全部其他 rigidity、closed-world、NLI、F9、F10 开关每次显式复位。默认 F7 索引在本模块内独立建立并缓存，不能被调用者遗留的 arm-specific index 替换。

模块依赖生产全局配置，单一进程内请顺序调用，不可使用多个线程同时跑不同配置。独立进程可并行。

`detailed=False` 只省略阶段追踪，不代表原始提取为空。接口另返回 `original_raw_count`；读取较早的无追踪包且无法重建原始数目时，摘要 `n_raw` 为 null，不能写0。此项仅修正审计元数据，不影响生产结果或数值干预。

## 四臂与文件

| arm | 名称 | 提取文件后缀 |
|---|---|---|
| 0 / `old_old` | 旧提示词、旧索引 | `oldidxclean_groups` |
| 1 / `free_old` | passage-scoped 提示词、旧索引 | `oldidxclean_groups_free` |
| 2 / `old_v2` | 旧提示词、v2 索引 | `v2idxclean_groups` |
| 3 / `free_v2` | passage-scoped 提示词、v2 索引 | `v2idxclean_groups_free` |

历史文件中的 `free/new` 不是本轮新 API 抽取。每例每臂完整记录位于 `replay_outputs/<case_key 将 / 替为 __>__<arm>.json.gz`。

| 顶层字段 | 内容 |
|---|---|
| `task` / `findings` | 原始病例、候选、原始及历史代理金标、冻结患者事实 |
| `stages.raw` | 门闸前的全部规范化提取断言，原始合并病例行号固定 |
| `stages.post_gate` | enum clamp 与 F7 后的断言 |
| `stages.pre_dedup_bound` | 主体绑定后、谓词去重前 |
| `stages.post_dedup_bound` | 去重后、患者事实连接前 |
| `stages.joined_before_intervention` | 生产最佳连接已选定，尚未实施指定连接屏蔽 |
| `stages.bound` | 实际进入 claimants、组和四层执行的断言 |
| `stages.groups` / `claimants` | 实际组成员及每项事实的认领候选 |
| `result.ranking` | 全候选名次、分数、所有贡献、所有否决/确认、L4 处罚 |
| `score_reconstruction` | 用未舍入原子贡献、原生产舍入组贡献、确认及 L4 独立重建每个分数 |
| `applied_interventions` | 实际命中的干预位置与行；命中 hook 不等于改变了语义有效贡献 |

每条贡献/否决/确认/L4 包含 `_audit_raw_ids`，表示所有去重支持原始行，及 `_audit_representative_raw_id`（组则为复数）。`_audit_source` 包含 cache ID、gid、源、focus、输入窗口 SHA256。`normalized_local_index` 是规范化提取行在该 job 中的位置；它不是未经规范化原始 JSON 的行号，尤其不能忽略不合法行在规范化时被移除的情况。

## 有界干预

```python
from replay_audit import run

result = run(
    "DA_d2_seq100/119", 0,
    intervention={
        "block_joins": [{"candidate": "Dermatitis", "raw_ids": [1071]}]
    },
    detailed=False,
)
```

| 参数 | 作用点 | 会传播到哪里 |
|---|---|---|
| `delete_raw_ids: [i]` | enum/F7 前移除原始行 | 去重代表可换行，绑定/连接、组、claimants、分数、否决、确认、L4 全部重跑 |
| `patch_raw: [{raw_id:i,changes:{relation:"feature_of"}}]` | enum/F7 前替换指定槽位 | 同上；仍可能被 F7 再改写 |
| `append_raw: [{assertion:{...},source_arm:"free_old",source_raw_id:i}]` | enum/F7 前追加审计反事实行 | 新行号从原始提取长度开始；保存引入来源，不冒充原 arm 历史输出 |
| `force_bindings: [{raw_ids:[i],target_candidate:label}]` | 常规主体绑定后、去重前显式移行 | 保留候选顺序；可改变目标/原候选组、连接、claimants 等。这是指定路由反事实，不是自动正确实体消歧 |
| `block_joins: [{candidate:label,raw_ids:[i],finding:optional_label}]` | 最佳 predicate→finding 连接后、claimants 前 | 将已选连接设为空，不尝试次佳连接；会改变组、claimant 权重、硬判别及 L4 |
| `remove_contributions: [{candidate:label,raw_ids:[i]}]` | 候选数值计分后、L4 前 | 只减去该数值贡献，保持否决、确认计数、claimants、组和其他候选贡献。它是局部预算分解，不是完整临床修复 |
| `block_layer4: [{candidate:label,raw_ids:[i]}]` | L4 的源断言循环 | 跳过该行方向比较；实际取消处罚数必须比较前后 penalty 列表，不能数 hook 命中次数 |

`block_joins` 和 `remove_contributions` 的行选择匹配代表行或其任一去重支持行。若只删除一个原始支持行，别的重复行仍可能保留同一贡献；这种差别是审计对象，不是隐藏的删除失败。空 selector `{}` 选择全部符合该阶段条件的行，用于明确标注的全局机制探针。

## 差量与系统探针

`build_replay_deltas.py` 为 696 个候选状态和 696 个候选配对产生精确记账：原子正/负、确认、组、L4、舍入；并把事实层变化分为共同事实贡献变化、新增事实、移除事实。共同事实依据规范化患者标签相同，不保证医学意义相同。组贡献保持独立，不虚构分摊到原子的 credit。

`repeated_fact_vote_ledger.json` 记录同候选同患者事实的多条原子票，以及其正向票权重总和超过最强单票的部分。这些计数**不把重复证据全部裁定为错误**；来源独立性、适用范围和临床意义仍需人工检查。已被 predicate 去重合并的多个原始支持行也与保留的多个软票分开。

**完整贡献列表仍不等于完整因果路径。** `claimants` 在软上下文过滤、否决和确认之前，从所有成功连接且 assertion polarity 为 asserted 的绑定行建立。某行可以因 epidemiology/treatment 等上下文完全不产生自己的 L3 票，却增加某项患者事实的 claimant 数，压低其他候选的所有正向票；后来被排除的候选也未从该集合中撤回。病例 49 的 Abdominal-TB 比例被误接到血中 neutrophils 百分比就是这种待逐例验证的路径。应同时检查 `stages.bound`、`claimants` 以及全候选事实权重，不能只按有数值贡献的原始行筛选错误。局部 `block_joins` 会传播此权重变化；`remove_contributions` 故意冻结它，因此两者不同正是识别这种影响的工具。

同理，`candidate_delta_ledger` 的 common/added/removed-fact 分解只是数值恒等式：共同事实的权重变化可能由另一个候选的一条零分断言造成。它没有把每项数值变化宣称为对应打分行独立造成的因果效应。

系统探针包含基线、关闭 embedding fallback、F10 原子事实平均、关闭 all 自动升级必要性、关闭 L4、仅去掉排序键中的确认计数。均是有界机制探针，不能称为经验证改进：no-embedding 仍有词法/marker 错连；F10 不覆盖组/确认/L4；关闭 all 自动必要性不修复错组；去确认优先级保留其数值加分。每个探针保留全部候选及配置哈希。

排序实际优先级是是否排除、确认条数、分数，其次原候选顺序。空候选的零分可越过已排除但高分的候选；纯分数差量无法完整解释名次变化。
