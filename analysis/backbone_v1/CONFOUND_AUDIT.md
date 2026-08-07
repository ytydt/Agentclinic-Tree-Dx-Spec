# 干净输入运行 vs 已发表运行：配置差异彻底核查

日期 2026-08-07 · 触发于 `EQUAL_INPUT_RESULTS.md` 里 DA 的 l1_calib 混杂，
遂对全部维度做穷举比对。**结论：除 l1_calib 外还有三项差异，其中一项足以
解释 MCR 上"泄漏效应"的一半。**

## 0. 一句话

先前把"干净运行 vs 已发表运行"的全部差值都记在了 MCQ 泄漏头上。实际上这两组运行
**跨越了一次 annotate 重写、一次 answer mapper 重写和一次 provider 路由改动**，
没有任何一个已发表数字与干净数字是同代码同配置的。

**另外**（§7，独立于上述配置漂移）：唯一幸存的对内结论"层级承重"也不成立。
AB02 的单一 L1 家族标签是占位字符串 `Flat candidate pool (no L1 hierarchy)`，
而 L2 生成以父标签为条件，导致它只填满配额的 23%（8.2/36），比一次无约束
wide-DDx 调用的骨干（17.3 个候选）还少一半。等长比较下 APHHM 0.60 对
无层级骨干 0.59，对 AB02 0.48——层级不是必要条件，AB02 也不是层级的干净消融。

---

## 1. 核查方法

| 维度 | 手段 |
|---|---|
| 下游配置键 | `downstream_summary.json` 全键并集逐运行对比 |
| 阶段输入 | `stage_manifest.json` 的 case_ids / mean_findings / mean_p5_rules |
| 冻结产物 | shared_trees / p5_audit / vignette_parser_frozen 逐字节 md5 |
| 代码代次 | `case_results[].l2` 的键集合作指纹 |
| 源码漂移 | `git status` + `git diff --stat` + 各文件 mtime 对齐运行日期 |
| mapper 版本 | 用当前 mapper 重打已发表预测（同参数），看分数变不变 |
| judge 版本 | 用当前 official_eval 重打已发表预测，看分数变不变 |
| provider 路由 | 读 `_get_openrouter_provider` 与本次会话的 diff |

## 2. 核对无差异的维度

| 维度 | 结果 |
|---|---|
| 案例集合 | DA / MCR 的 `case_ids` 完全一致 |
| VP 证据目录 | MCR `mean_findings` 18.28 = 18.28；DA VP 冻结文件 md5 相同 |
| P5 规则 | DA 76 例 `mean_p5_rules` 17.29 = 17.29；MCR 18.28 = 18.28 |
| `granularity_mode` | 全部 `compat` |
| `joint_arm` | 全部 `A3-joint-primary` |
| `fixed_l1_budget` | 全部 6 |
| mapper 参数 | `typed_llm` / `synonym_bind_repair` / `min_score=0.70` 两侧一致 |
| 已发表 DA 两个旧运行的树 | 76/76 逐字节相同（`remain76_compat_b12` = `pipeline_remaining76/frozen`）|
| MCR official eval 脚本 | **实测中性**：同一批已发表预测重打得 0.50，与 07-27 原值一致 |

## 3. 四项真实差异

### 3.1 `l1_calib`：b12（仅已发表 DA）vs off（其余全部）

全库只有 `pilot24_compat_b12_live_v1` 和 `remain76_compat_b12_live_v1` 用 b12。
同一批 76 例、同为泄漏输入：off 0.5921 → b12 0.6842，**+0.092**（7:14，p=0.19）。

### 3.2 annotate 代次：已发表运行缺 6 个 l2 字段

以 `case_results[].l2` 的键作指纹，全库运行干净地分成两代：

| 代次 | 运行 | 特征键 |
|---|---|---|
| 旧（07-24/27） | DA `pilot24/remain76_compat_b12_live_v1`、`pipeline_remaining76_v1`、MCR `compat_synonym_v1` | 0 个新键 |
| 新（07-28 起） | 全部消融臂 `c2_ab*`/`c3_ab*` | 6 个新键 |
| 新（08-07） | 全部干净运行 | 7 个（多一个遥测键 `leaf_score_fidelity`）|

新键：`l2_candidate_max_per_live_family`(=6)、`local_evidence_budget`(=4)、
`between_evidence_budget`(=2)、`posterior_writeback`、`targeted_l2_gapfill`、
`annotated_tree_write`。

**行为后果可观测**：旧代码的 annotate 一片叶子都不加，新代码把 L2 翻近一倍。

| | annotate 前 \|L2\| | annotate 后 \|L2\| |
|---|---:|---:|
| DA 已发表（旧，76 例） | 17.64 | 17.64 |
| DA 干净（新，同 76 例） | 18.39 | **31.43** |
| MCR 已发表（旧） | 17.90 | 17.90 |
| MCR 干净（新） | 18.31 | **30.60** |

两个数据集同步出现约 1.7 倍的一致放大，不是输入剥除能造成的。
`07-28 10:55` 的 `controller.py`(+97) / `config.py`(+8) 与 `08-01 16:56` 的
`run_diagnosisarena_downstream_top2.py` / `diagnosisarena_l2_pipeline.py` 是时间上的对应改动。

### 3.3 answer mapper 重写（`answer_projection_mapper.py`，07-29 02:09）

在**完全相同的已发表预测**上、用**完全相同的 mapper 参数**重打：

| 数据集 | 已发表 mapper | 当前 mapper | Δ | 配对 | p |
|---|---:|---:|---:|---|---:|
| MCR（100 例） | 0.81 | **0.61** | **−0.200** | 25:5 | 3.3e-4 |
| DA（76 例） | 0.6842 | 0.6974 | +0.013 | 0:1 | 1.0 |

`mean_option_rr` 同步从 0.8667 掉到 0.6433，每例耗时从 10.8s 涨到 34.9s——
新 mapper 做的事多得多，但在 MCR 上给分显著更严。
**MCR 上先前报的 −0.40 有一半是这个。**

（副产品：DA 用当前 mapper 重打得 53/76，加 pilot24 的 18/24 正好 71/100 = 论文的 0.71。
先前算出的 0.70 只是旧 mapper 的值，论文数字本身对得上。）

### 3.4 provider 路由改动（`llm_client.py`，08-06 17:44，本次会话所改）

`meta-llama/llama-3.3-70b-instruct` 的路由：

```
改前: order = [groq, google-vertex, novita, deepinfra/base]
改后: order = [groq, deepinfra/base],  ignore = [google-vertex, google-ai-studio, novita]
```

两者都以 groq 开头，但 groq 不可用时的回退目标完全不同。
**实际命中的 provider 没有落盘记录**，无法事后量化。
所有 08-06 之后的运行（全部干净运行 + MCR `c3_ab02_v1`）都在改后路由下，
所有更早的运行都在改前路由下。这是本次审计里唯一**不可量化**的残余混杂。

### 3.5 次要：workers

已发表 8/10，消融臂 12，干净运行 12/25。不改变语义，但会改变超时与重试的触发频率。

## 4. 订正后的分解

### MCR，option@1（内部指标）

| 环节 | 值 | Δ | p |
|---|---:|---:|---:|
| 已发表（旧 annotate + 旧 mapper） | 0.81 | — | — |
| 已发表预测 + **新 mapper** | 0.61 | −0.200 | 3.3e-4 |
| 干净（新 annotate + 新 mapper） | 0.41 | −0.200 | 1.9e-6 |

第三行的 −0.20 仍然打包了三样东西：MCQ 泄漏、annotate 代次、provider 路由。
`aphhm_leaked_newcode_v1`（已发表泄漏树 + 新 annotate + 新 mapper）正在跑，
它与 0.41 的差才是泄漏的净值。

### MCR，Prompt-7 Acc@1（论文口径）

0.50（已发表）→ 0.26（干净）。走 LLM judge 不经过 answer mapper，
且 judge 脚本已实测中性，所以这条**不受 3.3 影响**，但仍受 3.2 与 3.4 影响。
同口径下 AB02：泄漏 0.44 → 干净 **0.19**。

### DA，option@1（76 例配对）

| 环节 | 值 | Δ | p |
|---|---:|---:|---:|
| 已发表（b12，旧 mapper） | 0.6842 | — | — |
| 同预测 + 新 mapper | 0.6974 | +0.013 | 1.0 |
| 干净（off，新 annotate，新 mapper） | 0.6184 | −0.079 | 0.31 |

DA 上 mapper 中性，剩下的 −0.079 由 l1_calib（约 −0.09）、annotate 代次和泄漏
三者共同构成，且整体不显著。

## 5. 哪些比较仍然成立

**成立**——两侧同代码、同 mapper、同路由：

| 比较 | 结果 |
|---|---|
| DA：APHHM 干净 vs AB02 干净（均 08-07） | +0.14，22:8，p=0.016 |
| MCR：APHHM 干净 0.26 vs AB02 干净 0.19（均 08-07，Prompt-7） | +0.07 |
| DA 消融臂互比 AB01/AB02/AB03（均 07-28） | 0.51 / 0.68 / 0.37 |
| DA 基线对比（基线 07-21/27，但 DA mapper 已验中性） | 16:16，p=1.00 |

**不成立**——跨代码代次，`EQUAL_INPUT_RESULTS.md` 里所有"泄漏输入 vs 干净输入"
那一列的差值全部需要重算：

- APHHM DA 0.71 → 0.62（+l1_calib +annotate 代次 +路由）
- APHHM MCR 0.50 → 0.26 与 option@1 0.81 → 0.41（+mapper +annotate 代次 +路由）
- AB02 DA 0.68 → 0.48、AB02 MCR 0.44 → 0.19（跨 07-28/08-07，含 mapper 与路由）
- 骨干各臂 vs 已发表（骨干全部 08-07，已发表 07-27）

## 6. 在跑的对照

| 运行 | 目的 | 状态 |
|---|---|---|
| `logs/diagnosisarena_d2_m01_v1/aphhm_clean_v1_b12_v1` | 干净输入 + b12，对齐论文 DA 0.71 | annotate 进行中 |
| `logs/diagnosisarena_d2_m01_v1/aphhm_leaked_newcode_b12_v1` | 已发表泄漏树 + 新 annotate + b12，隔离 annotate 代次（DA 76 例） | annotate 进行中 |
| `logs/medcasereasoning_mcr_val_seq100_v1/aphhm_leaked_newcode_v1` | 同上，MCR 100 例 | annotate 进行中 |

三者齐了以后，DA 与 MCR 上都能得到 `泄漏 vs 干净` 的净值（仅剩 §3.4 的
provider 路由无法排除）。

## 7. AB02 不是「层级」的干净消融

起点是一个说不通的现象：干净输入下 APHHM 0.62 与骨干最好臂 0.59 同带，而
**没有层级的骨干本该和同样没有 L1 的 AB02（0.48）在一起才对**。查下来 AB02
的落后有明确的结构性来源，与「层级组织是否有助于推理」无关。

### 7.1 AB02 的唯一 L1 节点是个占位字符串

`scripts/paper/c3_l1_axis.py:321`：

```python
parent = _make_l1("FLAT", "Flat candidate pool (no L1 hierarchy)", prior=1.0)
```

DA 上 AB02 的 100 例全部只有这一个 L1 标签；APHHM 有 396 个不同的真实医学类目
（`Inflammatory Skin Disorder`、`Other Cardiac Conditions` …）。而 L2 候选生成
是**以父家族标签为条件**的（`diagnosisarena_l2_pipeline.py:472` 把 `parent.label`
带进 payload）。所以 AB02 实际是在问「请在『Flat candidate pool (no L1 hierarchy)』
这个家族里列出候选诊断」——一个语义为空的锚。

### 7.2 后果一：生成端严重欠填

消融设计其实**做了预算匹配**（把每家族上限从 6 提到 36，1×36 ≈ 4.75×6 = 28.5），
但 AB02 填不满：

| 臂 | 家族数 | 每家族上限 | 实际候选池 \|L2\| | 填充率 |
|---|---:|---:|---:|---:|
| APHHM 干净 DA | 4.75 | 6 | **31.75** | 111% |
| AB02 干净 DA | 1.00 | 36 | **8.23** | 23% |
| AB02 泄漏 DA | 1.00 | 36 | 4.98 | 14% |
| MCR APHHM 干净 | 4.69 | 6 | 30.60 | 109% |
| MCR AB02 干净 | 1.00 | 36 | 6.30 | 18% |

对照：**没有任何层级、只发一次 wide-DDx 调用的骨干 `v0_s4b` 拿到 17.3 个候选**，
是 AB02 的两倍。也就是说 AB02 连"朴素扁平"的水平都不到——把家族标签换成占位符
比根本不分家族更糟。

### 7.3 后果二：输出端被 `champions_per_parent=1` 锁死

`diagnosisarena_l2_pipeline.py` 的动态选择每个 L1 家族只出 1 个冠军，
所以 `final_ranking` 长度上界就是家族数。实测 100/100 例满足该上界：

| 臂 | 家族数 | final_ranking | @1 | @2 |
|---|---:|---:|---:|---:|
| APHHM 干净 DA | 4.75 | 2.48 | 0.62 | 0.67 |
| AB02 干净 DA | 1.00 | **0.99** | 0.48 | **0.48** |
| AB02 泄漏 DA | 1.00 | **1.00** | 0.68 | **0.68** |

AB02 的 @2 恒等于 @1 就是这么来的——它只被允许提交一个答案。

### 7.4 但输出端截断只值 0.02，损失主要在生成端

把 APHHM 干净的 `final_ranking` 截到 1 个候选（69/100 例被截）后用同一 mapper 重打：

| | 候选数 | @1 | @2 |
|---|---:|---:|---:|
| APHHM 干净 原样 | 2.48 | 0.62 | 0.67 |
| APHHM 干净 **截到 1** | 1.00 | **0.60** | 0.60 |
| AB02 干净 | 0.99 | 0.48 | 0.48 |

等长比较下 APHHM 仍高 **+0.12**。所以 §7.3 的接口截断只解释 0.02，
剩下的 0.12 来自 §7.2 的生成端：APHHM 的 top-1 是 4.75 个家族冠军
（各自从约 6.7 个候选里选出）跨家族比赛的赢家，AB02 的 top-1 是 8.23 个
语义无锚候选里的唯一冠军。

### 7.5 结论：`tab:org-axis` 度量的不是层级

APHHM − AB02 这个差值同时包含三样东西：

1. 生成被拆成 N 次窄调用（每次好填）vs 1 次宽调用（填不满）
2. 家族标签是真实医学类目 vs 占位字符串
3. `champions_per_parent=1` 下决赛席位 4.75 个 vs 1 个

**真正的无层级对照是骨干**，它同样没有 L1，但用一次无约束 wide-DDx 提问就拿到
17–48 个候选，落在 0.50–0.59。等长比较下 APHHM 是 0.60：

| 对照 | @1 | 与 APHHM(截1) 0.60 之差 |
|---|---:|---:|
| 骨干 `e7_k3_comp_k5`（3 路互补分区） | 0.59 | −0.01 |
| 骨干 `e10_llm_strict_k5`（单次宽调用） | 0.59 | −0.01 |
| 骨干 `e3_kb_only_k5` | 0.57 | −0.03 |
| 骨干 `v0_s4b_k5`（最朴素） | 0.50 | −0.10 |
| **AB02（"无 L1"）** | **0.48** | **−0.12** |

层级不是必要条件：只要肯把候选列宽，无层级的骨干就能进同一带。
L1 的可辨识贡献是**把一次宽生成拆成若干次窄生成**，而这一点用分区提问同样能拿到
（`e7_k3_comp` 与单次宽调用 `e10_llm_strict` 打平，说明连分区都不是必需）。

另外一个旁证：骨干各臂之间候选池大小**不预测**准确率——池 47.59 的臂从 0.44 到
0.59，池 17.27 的臂从 0.36 到 0.59。真正拉开差距的是选择器变体。所以"列得宽"
只是及格线，不是 APHHM 的独门贡献。

### 7.6 需要补的实验

要把"层级"从"生成拆分"里分离出来，正确的消融是**保持 N 次窄生成调用、只打乱
家族的语义**（即 AB03 随机轴，但要给随机家族真实的医学标签而非
`Random partition family i`）。现有 AB03 用的同样是占位标签
（`Random partition family 1..k`），因此 0.37 这个数也同时包含了标签语义缺失，
不是纯粹的"轴随机化"效应。`tab:org-axis` 的三个点都有这个问题。

## 8. 未触碰已发表资产

mapper / judge 的重打全部写入独立目录：
`logs/_audit_mapper_rescore/{da76,mcr100}` 与
`compat_synonym_v1/annotate/official_eval_llm_compat_audit0807`（新 out-name）。
已发表的 `mapper/summary.json` 与 `official_eval_llm_compat/summary.json` 未改动。
