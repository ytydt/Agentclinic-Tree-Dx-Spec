# D：两笔契约债的审计与修复

上游：[`CORE_REGROUP_HEADROOM/REPORT.md`](../CORE_REGROUP_HEADROOM/REPORT.md) §5.2（15.6% 的
病例有非空 stance 组不产出 finalist）与 §5.3（21 例金标进不了选择器载荷）。两者都被上游
判为"契约缺陷，不是性能杠杆"。本次把它们量化并修掉，代码开关默认关闭，冻结基线逐字节不变。

审计脚本 `analysis/mechanism_v2/identity_debt_audit.py`（零 LLM 调用，800 例）。
单测 `tests/test_aphhm_c_contract_fixes.py`（19 项）。

## 1. 债务二的真实规模比上游估计大一个量级

上游只看到"21 例金标进不了载荷"。把 `merge_audit` 里全部 `same_as` 判定重放一遍：

| `same_as` 判定 | n | 占比 |
|---|---:|---:|
| 归一化后同一字符串（合法） | 2944 | 85.8% |
| **非同一字符串** | **488** | **14.2%** |
| └ 其中形态学等价（`strict_key` 仍应合并） | 10 | |
| └ **粗粒度被折入具体标签** | 131 | |
| └ **具体标签被折入粗粒度** | 55 | |
| └ 词法部分重叠 | 154 | |
| └ 词法完全不相交 | 138 | |

被折掉的样本（`cases.jsonl`）：`Pericarditis → Acute Pericarditis`、
`Schwannoma → Facial nerve schwannoma`、`Myoclonus → Palatal Myoclonus`、
`Dermatitis → Contact dermatitis`、`Cystoid Macular Edema → Macular Edema`、
`Myocardial Ischemia → Myocardial Infarction`、`Hyperlipidemia → Dyslipidemia`、
`Epiretinal Membrane → Retinal Disease`、`Neurally Mediated Hypotension → Vasovagal Syncope`。

### 根因

`ConceptRegistry._same_as` 本身是对的（注释明确写了 substring 不是 same_as）。漏在
`add()` 的两处旁路：

1. 生成器自报的 `aliases` 被写进 `_alias_index` 当作身份键（`aliases` 直接来自 c3 的 LLM 输出）；
2. `existing` 找不到时，还会拿每个自报 alias 再查一遍。

于是 DA 87 例的实际轨迹是：`commit` 先注册 `Acute Pericarditis` 并自报别名
`["Pericarditis", "Inflammatory Pericardial Disease"]`；随后 `coverage` 和 `mechanism` 各自
独立提出 `Pericarditis`，两次都被折进 `C02`。**粗粒度父类从池里消失，只剩一个 alias 字符串。**

这条通道同时也是 MultiStance"三 stance 交叉验证"的记账漏洞：跨 stance 的一致被压成单个概念，
而保留下来的标签取决于哪个 stance 先注册。方向随机——131 次保留了具体标签，55 次保留了粗粒度。

### 修复后的反事实（离线重放身份判定，不重跑冠军）

| 量 | 值 |
|---|---:|
| 被阻止的合并 | 478 / 3432 |
| 涉及的病例 | 314 / 800 |
| 恢复出一个能 `dc.match` 金标的池内标签 | **21 例（29 次合并）** |
| 载荷宽度 | 8.898 → 9.429（**+0.531**） |
| `subset_only` 核数 | 7.777 → 8.010（+0.232） |
| 同核冗余（宽度 − 核数） | 1.120 → 1.419 |

两个方向都要记：legacy-chain 池召回被低估了 21/800 = 2.6pp（这正是上游 §5.3 的 21 例，
独立复现）；代价是宽度 +0.531，按 E5 在 width 4→8 上的 −4.42pp/候选，约 −2.3pp 转化。

> **后续实测更正**（[`CONTRACT_FIX_VERIFY/REPORT.md`](../CONTRACT_FIX_VERIFY/REPORT.md)）：
> 宽度代价的预测吻合（实测 +0.460/+0.535），但**那个 −2.3pp 的转化代价没有出现**——
> holdout-400 上 concept top-1 是 DA 持平、MCR +2.5pp。同时该实测也指出，池召回的涨幅里
> 12/15 是粗父类信用，所以召回收益比本节的 legacy-chain 计数更弱。
>
> **真端点更正**（[`CLINICAL_RESCORE/REPORT.md`](../CLINICAL_RESCORE/REPORT.md) §6）：
> 在冻结 clinical-complete 判定下重算，这笔修复在 clinical-complete、complete ∪ partial、
> 池内完整暴露三个端点上**均无显著变化**（最强的一格是 MCR complete ∪ partial 1 vs 6，
> p=0.125）。所以本节"legacy-chain 池召回被低估 2.6pp"应读成**匹配器口径的账**，
> 而不是可兑现的召回收益。

这笔修复的定位仍然是**正确性**，不是性能杠杆：它要和"同核只占一席"的选择器配套才能在
宽度上算账，而 [`CORE_REGROUP_HEADROOM`](../CORE_REGROUP_HEADROOM/REPORT.md) §3 已经测出
同席位下核分组不优于平铺 sham。

也要记一条否证：修好身份并**没有**把上游的核分组结论救回来。同核冗余从 1.120 升到 1.419，
在 9.43 的宽度上仍然只有 1.4 席可压。上游"核分组无独立贡献"的结论不因这个混淆而翻转。

## 2. 代码修复

两个开关，**默认关闭**，`--enforce-group-quota` / `--strict-identity`（`run_aphhm_c.py`），
写入 manifest。

### 2.1 `enforce_group_quota`

`aphhm_c.py::AphhmCPipeline._enforce_group_quota`。tournament 单次调用的回包里 `finalists`
此前完全没有校验：不在 shortlist 的标签会留下，整组缺席也不会被发现。修复后

- 丢弃不在 shortlist 的提名（此前会留在日志里）；
- 每个非空 stance 组若无提名，**确定性**补上该组自己排名最高的成员（`candidates[0]`，因为
  groups 是按 ledger rank 遍历 frontier 构造的）——与结果无关，不看金标；
- 只有真的补了席位才追加一次 `AphhmCFinalAdjudicator` 重裁（合规回包 0 额外调用），
  并保留 `champion_before_quota` 以便审计。

`max_calls` 在开启且非 split 模式时 +1。

### 2.2 `strict_identity`

身份只认形态学等价（`_strict_key`：去所有格、去连字符/标点、去非缩写词的复数）。
`Grover's disease` ≡ `Grover disease`、`Right Bundle-Branch Block` ≡ `Right Bundle Branch Block`
仍合并；`Pericarditis` vs `Acute Pericarditis`、`Leukemic cutis` vs `Leukemia Cutis`
（派生词）不再合并。缩写按全大写识别后不去复数，避免 `AIDS → AID`、`ARDS → ARD`。

开启后：生成器自报的 alias 不进 `_alias_index`、不参与 `existing` 查找；resolver 若把父类与
子类映射到同一码也不再据此合并。信息不丢——alias 仍留在节点上，且冲突记为
`claimed_alias_not_merged` 审计项。父子对因此落回 `add()` 原本就会建的
`broader_than` / `narrower_than` 边，也就是 design 2.2 本来要的格。

### 2.3 单测

`tests/test_aphhm_c_contract_fixes.py`，19 项全通过。覆盖：静默组补席并重裁、补的是组内
最高排名成员、合规回包零额外调用且不改冠军、幻觉提名被丢弃后该组重新补席、两个开关默认
关闭、`_strict_key` 的合并与不合并边界（含缩写）、默认行为下父类被折入子类（归档行为，
锁定住以防意外修改冻结基线）、strict 下父子分离并生成 broader/narrower 边、strict 下同标签
仍正常合并且 span/stance 正常累积、strict 下坍缩型 resolver 被忽略。

## 3. 可写与不可写

**可以写：**
- 归档的 multistance 轨迹里 14.2% 的 `same_as` 合并不是同一字符串，186 次把父类与子类折成一个概念。
- 根因是生成器自报 alias 被当作身份键，与 `_same_as` 的设计意图相反。
- 修复后 legacy-chain 池召回恢复 21/800 例，代价是宽度 +0.531。
- 同核冗余 1.120 → 1.419：修身份不改变"核分组无独立贡献"的上游结论。
- 15.6% 的病例存在整组无提名，已用确定性补席 + 重裁修掉，合规回包零额外成本。

**不可以写：**
- 不可仅凭本节声称修复会提高任何端点分数：本节是离线身份重放，没有重跑池子和冠军。
  带调用的配对验证见 [`CONTRACT_FIX_VERIFY`](../CONTRACT_FIX_VERIFY/REPORT.md)，
  其结论受该报告 §5 的限定约束。
- 不可把 `dc.match` 恢复的 21 例读成临床收益：它是 legacy-chain 计数，PPV 0.5648。
- 不可把 `_strict_key` 当同义词消解：它只做形态学，`Leukemic cutis`/`Leukemia Cutis`
  这类真同义会被保留成两个概念（保守方向，代价是宽度）。
- 任何已归档的实验结果都不因这次修复而改变：两个开关默认关闭，冻结臂重放逐字节一致。

## 4. 复现

```bash
python3 analysis/mechanism_v2/identity_debt_audit.py \
  --out analysis/mechanism_v2/results/IDENTITY_DEBT
python3 -m pytest tests/test_aphhm_c_contract_fixes.py -q
```
