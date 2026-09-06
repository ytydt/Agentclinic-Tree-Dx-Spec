# 522：未被完整生成的复合诊断，遇上组污染、疾病身份抢占与错误计量

病例：`DA_d2_heldout200b/522`。本报告阅读真实 vignette、四臂原始断言、实际曝光窗口及完整运行轨迹；数字采用本轮冻结的 B1/S7/default-F7 重放。旧报告截取的前25项并非完整贡献。

## 终点先于归因

完整答案是“紧张症与基础路易体痴呆相关”。23个冻结候选中没有这个复合概念。历史评分接受 `Catatonia` 或甚至 `Dementia`；前者只保留表现综合征，后者连病因亚型和紧张症都丢失。`Dementia with Lewy bodies` 等三个独立标签反而不在历史接受集合。因而本例旧 top-3 是组件命中，不能描述为正确完成病因诊断。

病例直接提供 mutism、echopraxia、mitmachen、staring，以及三个月认知/行为退化、幻觉和间歇性不能认出家属。这足以支持认真考虑紧张症及DLB，但不能把所有相关体征不经映射都计为DSM的不同条目：mitmachen、staring 并不自动构成第三个DSM条目。也不能把“间歇性不能认出家人”直接当作已严格证明的DLB认知波动。此前 manual_flow 的肯定式“满足紧张症→病因DLB”超过此处冻结观测能够自动证明的范围。审计使用原标作为任务标签，不追加未给出的临床事实。

## 新旧内容变化首先改变了可表达的规则

旧 `Schizophrenia with prominent catatonic features ... > History and Physical` 窗口 gid480632 只有“三项/十二项”的总述，随后是Walter的四类症状举例；v2对应gid496392补上完整十二条DSM列表。旧 gid480634 与新gid496395还保留Walter分类和检查建议。这是实际文本改善。

但运行的并不是这两份原文的忠实程序。旧free原子427–433把Walter举例编码成 `any/g1`；新free472–483把恢复的DSM列表编码成 `at_least_n=3/g1`，其连接/基数方向确有进步。随后发生另外三次破坏：

1. 同文章、同focus、空section、同局部 `g1` 被当作同一组，跨窗口的DSM列表与Walter分类合并。新运行组11成员包括新DSM的一部分，也混入另窗 immobility/hyperthermia/stereotypy；它既不是十二项DSM域，也不是独立Walter描述组。
2. 全局原子去重先于完整组执行。Mutism476被先出现的另一组455代表，Negativism、Posturing、Stupor等也不再作为本组独立成员保留。互相独立的原规则不能因为共享叶子就删除各自的引用。
3. 新组的两个“满足”是482 `Echolalia` 和483 `Echopraxia`，两者都绑定病例的 **同一个echopraxia事实**，不是mutism+echopraxia。语言模仿与动作模仿被错误合并，随后又被当作两个不同计数项。

因此，旧组6.029分、新组2.010分的变化不能归因于单独一个“LLM把量词抽错”。原文基数恢复、代表原子选择、组ID碰撞和事实重复使用共同决定了分数。若只看词面十二项恢复或输出 `n=3`，会漏掉主要损坏。

## 非致命错误如何让真正的竞争边界越过紧张症

### 数值被转成可反复投票的检验名称

病例B12为 **1154.67 pmol/L**。引擎却把 low/borderline serum B12、B12摄入/吸收不足、补充治疗等都绑定到 `B12/present`，把测过该项目当作低值或病因成立。显式的 `<300 pmol/L` 比较即使得到1154.67<300为假，也仍能产生正软分。原子措辞不同，重复票便保留下来。

v2又曝光NICE窗口gid37188（ng239 1.3.1–1.3.3）：总B12或活性B12作为初始检查；妊娠优先活性B12；一氧化二氮相关疑似缺乏才选同型半胱氨酸/MMA。新free原始4669、4670、4672将检查菜单的 total B12、active B12、plasma homocysteine 抽成缺乏症 `feature_of`，没有检查结果或人群条件；三项直接新增 **11.326分**。病例有上述检验数值，不等于妊娠、氧化亚氮暴露或异常结果。

因此B12错误是源有依据但语义降格/任务提升，加上事实计量失败，不能归为无来源幻觉。它在所有四臂都保持首位；本例v2新增菜单虽显著扩大错误分，却不是Catatonia从2到4的唯一必要原因。

### 上下位/器官范围与方向一起丢失

`Chronic ischemia` 的原始来源其实是肠系膜缺血：旧gid471533–471535、新gid486414–486415明确讨论慢性肠道缺血风险。新free731/732主语仍是 `Chronic mesenteric ischemia`，787/788仍是同一疾病，说明部位限定不是全都在抽取阶段丢掉的；候选绑定把它们投入由脑MRI“慢性缺血”形成的无限定标签。

731/787的冠心病以及732/788的外周动脉病，都绑定病例既往冠心病。外周动脉病不等于冠心病；同一风险又以 `feature_of` 与规范化后的 `caused_by` 各投票。四票各4.173，合16.692分，几乎解释该候选17.611分的全部正支持。这不是病理或时序更吻合的证据，而是部位丢失、同义规范化未去重和错误病史绑定的叠加。其分数在旧free17.721、新free17.611几乎未变；当紧张症的组分减少，它便被动越过目标。

### DLB证据甚至被竞争标签占走

新free的 `Chronic ischemic encephalopathy` 接收72条主语 `Dementia with Lewy Bodies`、46条 `Dementia with Lewy bodies`、29条 `Lewy Body Dementia`，还包括其他DLB别名；真实DLB标签主要只收到 `DLB` 等少量剩余写法。候选绑定按顺序遇到近似匹配即接受，未先做全局精确身份解析。

这既压低DLB病因组件，又把DLB的幻觉、退行性病理等支持加给缺血标签；`Lewy bodies in the brain` 又错误绑定MRI项目本身。`fluctuating cognition` 则未正确接上病例“间歇性不能认出家人”。随后“无局灶神经缺损”被错误绑定“无认知缺陷”，导致承接这些证据的缺血标签被排除。即使只修复该错误否决，也会让带着错配DLB证据的缺血候选重新竞争；不是完整临床修复。

## 旧top-3为何能够凑巧成立

旧0紧张症22.236分排2，B12错误高分66.320排1；缺血性脑病虽有28.136分却被上述错误否决压在尾部。旧free紧张症25.760还享受跨窗口 `any/10` 症状组完整投票，与 `any/6` 再次投票。v2free紧张症15.662跌到慢性缺血17.611及精神病性抑郁16.994之后，形成第4名。

精神病性抑郁的软分也不是纯正确对照：既往MDD被当作当前/间歇性重性抑郁发作、完整发作标准；labile mood同时满足情绪一致与不一致精神病性特征；不同时间/状态标签可以重复投票。本文不因它属于干扰候选就删除真正相关的抑郁病史或精神病性症状，而是把相关性与未被证明的当前发作、亚型和时间条件分开。

旧高排名同时含有真实综合征线索、无关MRI/weight-loss绑定的正贡献、过宽/碰撞组计分以及竞争者错误淘汰。下方离线干预逐项区分直接分值与跨候选claimant变化。完整答案因候选缺失仍不可获得；任何代理top1增益都不能修复这个终点。

## 可复现空间与识别边界

全源定位见 `../source_exposure_ledger.jsonl`；全断言、门闸、去重前后、事实连接与所有候选分值见 `../replay_outputs/DA_d2_heldout200b__522__*.json.gz`。本例声明的局部判断及原始行号在 `../judgments_neuro_cardio.json`，干预由 `../audit_neuro_cardio.py` 固化。

数值干预只关闭指定分值或连接，不自动重建整套正确医学知识。一个predicate消失还会改变claimant specificity，因而直接贡献和名次作用不满足普遍可加性。其余未逐项裁决贡献作为残余保留，不能把这些选择性案例外推为规则错误率。


<!-- GENERATED NEURO APPENDICES -->
## 完整四臂候选表
数格为“名次 / 软分 / E=已淘汰”。软分不等于最终排序；排除优先于软分。
| 候选 | 旧提示/旧索引 | 新提示/旧索引 | 旧提示/v2 | 新提示/v2 |
|---|---:|---:|---:|---:|
| Alzheimer's disease | 22 / 6.889 / E | 21 / 6.694 / E | 21 / 7.540 / E | 21 / 7.357 / E |
| Antidepressant-induced psychotic disorder | 5 / 10.266 | 6 / 11.105 | 6 / 5.385 | 6 / 2.367 |
| Antipsychotic-Induced Parkinsonism | 12 / 0.000 | 12 / 0.000 | 11 / 0.000 | 11 / 0.000 |
| Catatonia | 2 / 22.236 | 2 / 25.760 | 2 / 18.692 | 4 / 15.662 |
| Chronic Ischemic Encephalopathy | 8 / 1.932 | 8 / 1.891 | 8 / 1.179 | 8 / 1.144 |
| Chronic ischemia | 6 / 9.498 | 3 / 17.721 | 5 / 9.374 | 2 / 17.611 |
| Chronic ischemic encephalopathy | 20 / 28.136 / E | 20 / 28.903 / E | 20 / 27.349 / E | 20 / 29.329 / E |
| Creutzfeldt-Jakob Disease | 4 / 11.544 | 5 / 12.607 | 3 / 14.331 | 5 / 7.467 |
| Delirium | 21 / 7.774 / E | 22 / 5.725 / E | 22 / 6.507 / E | 23 / 4.952 / E |
| Dementia | 13 / 0.000 | 13 / 0.000 | 12 / 0.000 | 12 / 0.000 |
| Dementia with Lewy Bodies | 10 / 0.273 | 11 / 0.273 | 10 / 0.243 | 10 / 0.217 |
| Dementia with Lewy bodies | 9 / 1.328 | 9 / 1.056 | 13 / 0.000 | 13 / 0.000 |
| Hypothyroidism-associated encephalopathy | 14 / 0.000 | 19 / -0.500 | 14 / 0.000 | 19 / -0.500 |
| Hypothyroidism-related encephalopathy | 15 / 0.000 | 14 / 0.000 | 15 / 0.000 | 14 / 0.000 |
| Lewy Body Dementia | 16 / 0.000 | 15 / 0.000 | 16 / 0.000 | 15 / 0.000 |
| Major depressive disorder with psychotic features | 3 / 19.574 | 4 / 17.700 | 4 / 12.862 | 3 / 16.994 |
| Mirtazapine-induced psychosis | 17 / 0.000 | 16 / 0.000 | 17 / 0.000 | 16 / 0.000 |
| Neurodegenerative disease | 11 / 0.185 | 10 / 0.611 | 9 / 0.456 | 9 / 0.876 |
| Neurosyphilis | 23 / 0.783 / E | 23 / 2.815 / E | 23 / 1.211 / E | 22 / 5.536 / E |
| Psychotic disorder | 7 / 2.032 | 7 / 2.942 | 7 / 2.849 | 7 / 1.160 |
| Vascular Dementia | 18 / 0.000 | 17 / 0.000 | 18 / 0.000 | 17 / 0.000 |
| Vascular dementia | 19 / 0.000 | 18 / 0.000 | 19 / 0.000 | 18 / 0.000 |
| Vitamin B12 deficiency | 1 / 66.320 | 1 / 48.178 | 1 / 63.799 | 1 / 55.267 |

## 分值差量与未裁决残余
下表是冻结基线上的账面分解，不是可相加的临床因果效应。选定家族仍有范围内的多个原子；其余合法变化、其他未裁决错误、去重/分组和claimant权重相互作用全部留在残余中。舍入误差可达0.001分。
| 对比 | 候选 | 总软分Δ | 已选直接贡献Δ | 残余Δ |
|---|---|---:|---:|---:|
| old_old→old_v2 | Catatonia | -3.544 | -1.957 | -1.587 |
| old_old→old_v2 | Vitamin B12 deficiency | -2.521 | +11.396 | -13.917 |
| free_old→free_v2 | Catatonia | -10.098 | -7.039 | -3.059 |
| free_old→free_v2 | Vitamin B12 deficiency | +7.089 | +11.326 | -4.237 |

已选家族：Catatonia: `catatonia_group_vote_suspension, catatonia_unentailed_imaging_and_loss`; Vitamin B12 deficiency: `B12_test_menu`.

## 已执行的局部干预
下列仅展示旧0与新free-v2的重点切面；四臂全部运行及原始行号见 `../interventions_neuro_cardio.json`。`restore_old_proven_wrong_brake`故意恢复已证错误，只用于机制验证。`suspend_*`关闭证据或连接，并不自动补充遗漏的正确来源程序。
| 臂 | 干预 | 历史代理rank | top1 | 第一/第二名分数 |
|---|---|---:|---|---|
| old_old | `baseline` | 2 | Vitamin B12 deficiency | 66.320 / 22.236 |
| old_old | `suspend_B12_menu_only` | 2 | Vitamin B12 deficiency | 66.320 / 22.236 |
| old_old | `suspend_B12_value_votes` | 1 | Catatonia | 22.236 / 19.574 |
| old_old | `suspend_mesenteric_assignment` | 2 | Vitamin B12 deficiency | 66.320 / 22.336 |
| old_old | `release_wrong_cognitive_veto` | 3 | Vitamin B12 deficiency | 66.320 / 28.136 |
| old_old | `suspend_catatonia_group_vote` | 3 | Vitamin B12 deficiency | 66.320 / 19.574 |
| old_old | `release_veto_and_suspend_group_vote` | 4 | Vitamin B12 deficiency | 66.320 / 28.136 |
| old_old | `suspend_selected_positive_errors_both_sides` | 2 | Major depressive disorder with psychotic features | 19.574 / 19.328 |
| free_v2 | `baseline` | 4 | Vitamin B12 deficiency | 55.267 / 17.611 |
| free_v2 | `suspend_B12_menu_only` | 4 | Vitamin B12 deficiency | 43.940 / 17.611 |
| free_v2 | `suspend_B12_value_votes` | 4 | Vitamin B12 deficiency | 26.632 / 17.611 |
| free_v2 | `suspend_mesenteric_assignment` | 3 | Vitamin B12 deficiency | 55.354 / 16.994 |
| free_v2 | `release_wrong_cognitive_veto` | 5 | Vitamin B12 deficiency | 55.267 / 29.329 |
| free_v2 | `suspend_catatonia_group_vote` | 4 | Vitamin B12 deficiency | 55.267 / 17.611 |
| free_v2 | `release_veto_and_suspend_group_vote` | 5 | Vitamin B12 deficiency | 55.267 / 29.329 |
| free_v2 | `suspend_selected_positive_errors_both_sides` | 3 | Vitamin B12 deficiency | 26.720 / 16.994 |
| old_old | `restore_explicit_DLB_subject_identity` | 2 | Vitamin B12 deficiency | 66.290 / 21.629 |
| free_v2 | `restore_explicit_DLB_subject_identity` | 4 | Vitamin B12 deficiency | 55.163 / 17.512 |

完整重算命令：先运行 `python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/audit_neuro_cardio.py`，再运行同目录 `audit_neuro_cardio_identity.py`、`audit_neuro_cardio_family_scope.py` 与 `build_neuro_case_appendices.py`。未调用新的LLM，未改生产代码。
