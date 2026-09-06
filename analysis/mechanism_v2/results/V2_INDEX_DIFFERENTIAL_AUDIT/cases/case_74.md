# 74：致命否决之外，正常测量、替代结局和上位心律失常如何被反复计分

病例：`MCR_v1_seq100/74`。全量审计基线固定为B1/S7/default-F7，不能把exact-arm-window重放中的个别软分混入本表。

## 先修正“旧答对、新答错”的测量含义

本例与522/773不同：CPVT完整疾病确实存在于冻结候选中。不过同一疾病有两个大小写变体。真正接收规则的 `Catecholaminergic Polymorphic Ventricular Tachycardia` 在两个v2臂均被淘汰并排 **10**；零断言、零贡献的另一大小写变体位居4，所以历史 `gold_rank=4` 是空重复候选产生的名次，并非部分存活的正确推理。前报告文字曾写“10/13”，与本次冻结trace不符；13没有本配置的重放证据，本轮不猜测该数字的来源。

患者有当次VF心脏骤停、两次电除颤后ROSC、QTc380ms、正常室壁厚度及无Brugada波形。关键的嘈杂汽修店场景完全没有进入冻结34条facts，故旧CPVT top1不是引擎已经成功执行了“肾上腺素能应激触发”的整组诊断。事实抽取另把“既往无心脏骤停”写成不带时间限制的 `cardiac arrest/absent`，后续当次SCD/心脏骤停相关证据受到负分。题干作为诊断任务支持CPVT比较，并不意味着每一个排除声明都是现实世界的充分定律；例如一次正常QTc不宜被无条件提升为所有LQTS的必要标准缺失。

## v2的已知致命错误是真实原因，但不是完整解释

旧0/旧free活跃CPVT分别26.518/19.336分排1；v2旧提示25.783分、新提示22.068分，潜在软分并没有崩溃。两v2原始merged row1017分别把评分表中的结构/缺血性心脏病负分项、室性早搏负分项变成CPVT排除；前者接pulse，后者把急性VF当作“24小时总搏动中室性早搏>2%”。这些局部误杀已在上一轮证明。

但“只去掉CPVT误杀便回到top1”仍然借用了另一个门：LQTS的正常参考范围被G2翻成必须QTc>440ms，故它保持淘汰。本文增加了双门干预及软证据干预，检验当这个错误刹车也被移除时，哪一侧会胜出，而不是停在单一gold救回。

## LQTS如何得到越来越高的潜伏软分

本配置LQTS四臂潜在分为 **19.322、18.482、37.200、25.628**。它在v2旧提示反而比CPVT高11.417分，但被硬门遮住。

### 一次正常QTc变成很多条“延长”命中

“prolonged QTc”“QTc prolongation”“QTc>0.450 sec”“QT interval prolongation”“abnormally prolonged interval between QRS and T”等多种原子都接同一个QTc380ms。没有数值槽时，present被视为异常成立；有数值槽而比较失败时，部分软分仍然为正。谓词不完全同字便未去重。一般性“正常QT<400–440ms”来源（v2gid528580/528581）又被抽为LQTS的正特征，与“延长QT”同时累加。

原始1758 `QT interval duration` 的引用明确讲正常范围，却给LQTS正分3.048；1810等 `QT interval` 又混入正常参考范围、溺水叙述、QT监测建议等不同关系。监测动作、正常值、异常值、运动后恢复行为不是同一个断言。原始1771“晚恢复期QT异常延长”仅接静息QTc，没有恢复阶段观测。

### 恢复的评分表不是已被恢复的评分程序

v2gid678396提供QT区间、运动后QT、TdP、T波形、临床心动过缓、两类晕厥、家族史及不同权重，最后根据总分区间判断概率。新free把它变成 `any/g1` 症状集合。权重并未作为评分权重执行；“stress syncope=2points”中的2还被放入患者测量的 `threshold='='2`。

实际执行组12成员的四个“满足”为：

- 1682 QTc460–479 → QTc380；
- 1683 QTc450–459 → 同一个QTc380；
- 1689应激/运动晕厥 → collapse；
- 1690静息晕厥 → 同一个collapse。

组执行完全没有用前两条的区间比较约束满足，也没有区分晕厥的发生场景。`any`又使一条成功即可获得组票；新内容可以增加有效表格字符，同时制造错误的执行程序。

## 旧CPVT胜出也带着哪些错误正票

这些错误不能因为投给gold就算医学证据：

| 历史断言/来源 | 实际事实 | 首次损坏及后续累积 |
|---|---|---|
| 一般PVT可能自行终止或退化VF（v2gid450507，raw978/1173） | 电除颤后ROSC | 一般PVT主语被归到CPVT；替代的“自终止”接到治疗导致ROSC，与“退化VF”两条都投票；自终止单项+3.746 |
| 一般PVT的停搏、长QT、电解质异常或儿茶酚胺型PVT（gid438270，971–974） | sinus rhythm、QTc380 | 枚举的不同背景/病因被当成CPVT共同病征；窦性节律等于窦停搏/心动过缓，正常QT测量等于延长 |
| VT可以在结构正常心脏发生，但更多发生于结构病（gid702548，1048/1049） | pulse=86 | 上位VT发生背景误给CPVT；“可发生”被抽成否定排除，结构正常与结构异常又接同一个心率，两侧同时产生贡献 |
| CPVT通常正常体检 | cardiovascular exam/normal | 带normal的忠实谓词反而被通用`normal=不满足正谓词`分支处罚−0.4；旧0丢掉normal、只写physical examination却获得+1.071 |
| “无既往心脏骤停” | cardiac arrest/absent | 时间限定丢失，给当次骤停相关规则负分；病例当次VF并未消除旧史否定 |

V2不是只给错误候选更多坏分，gold本身仍同时收到互相冲突、来源范围错误或匹配错误的正负分。删除其错误正票也会明显降低CPVT分数；因此“去错的收益”要同时观察目标与竞争者。

## 癫痫首位是排除后的剩余胜者，也有自己的累计污染

两v2历史top1为Seizure disorder，分6.531/9.190。主要正支持来自失去意识/短暂意识丧失的重复表示，以及一些真实但不特异的苍白。还出现：premature birth→premature ventricular complexes；intracranial pressure→blood pressure；focal EEG patterns→Brugada pattern；brain structural abnormalities→valvular abnormalities。兽医急诊癫痫来源gid84320原句为发作后颅压升高导致儿茶酚胺反应和肺水肿，却被抽为癫痫由颅压升高导致，再套用于本人的肱动脉血压。人口范围、因果方向及测量对象连续损坏。

只清除癫痫这些小额错误通常不会解除CPVT硬排除，故不能改变“空重复CPVT第4”的指标；这不表示小额错误没有机制意义。它们决定了硬门以后哪个干扰项胜出，也能在恢复候选之后通过claimant数重新影响其他候选分值。

## 为什么旧top1不是对整个机制的验证

旧索引同时做到三件并不等价的事：保留了若干真正支持CPVT的心律失常/正常结构描述；由于 source或抽取缺口，尚未给CPVT加上那个错误硬否决；又用一个过强的QT参考范围门屏住已有很高错误软分的LQTS。CPVT包含多次错误正票，但在这个组合下仍排1。

本例新干预不把所有排除全删作为推荐修复。它逐个释放CPVT门、LQTS门，再分别撤销QT正分和CPVT错事实连接。只有这样才能看出“CPVT救回”的表面稳定依赖哪些竞争者仍被挡住，以及新内容如何扩大潜伏LQTS优势。

全源和原始cache记录见 `../source_exposure_ledger.jsonl`；全部36/35/36/32条CPVT贡献、全部候选及门记录在 `../replay_outputs/MCR_v1_seq100__74__*.json.gz`。逐项判断与干预输入分别在 `../judgments_neuro_cardio.json`、`../interventions_neuro_cardio.json`。这些是已选病例的机制反事实，不是新患者或新LLM抽取实验，也不是临床完整准确率估计。


<!-- GENERATED NEURO APPENDICES -->
## 完整四臂候选表
数格为“名次 / 软分 / E=已淘汰”。软分不等于最终排序；排除优先于软分。
| 候选 | 旧提示/旧索引 | 新提示/旧索引 | 旧提示/v2 | 新提示/v2 |
|---|---:|---:|---:|---:|
| Arrhythmogenic Right Ventricular Cardiomyopathy | 11 / 4.765 / E | 12 / 4.454 / E | 12 / 4.369 / E | 13 / 3.978 / E |
| Autism Spectrum Disorder-related Cardiac Dysfunction | 4 / 0.000 | 4 / 0.000 | 3 / 0.000 | 3 / 0.000 |
| Brugada syndrome | 10 / 9.849 / E | 11 / 8.159 / E | 11 / 10.665 / E | 11 / 7.083 / E |
| Cardiomyopathy | 13 / -2.194 / E | 13 / 3.829 / E | 13 / 0.684 / E | 12 / 4.158 / E |
| Catecholaminergic Polymorphic Ventricular Tachycardia | 1 / 26.518 | 1 / 19.336 | 10 / 25.783 / E | 10 / 22.068 / E |
| Catecholaminergic polymorphic ventricular tachycardia | 5 / 0.000 | 5 / 0.000 | 4 / 0.000 | 4 / 0.000 |
| Channelopathy | 3 / 0.017 | 3 / 0.520 | 8 / -0.213 | 8 / -0.252 |
| Hypertrophic Cardiomyopathy | 6 / 0.000 | 6 / 0.000 | 5 / 0.000 | 5 / 0.000 |
| Long QT Syndrome | 9 / 19.322 / E | 10 / 18.482 / E | 9 / 37.200 / E | 9 / 25.628 / E |
| Long QT syndrome | 7 / 0.000 | 7 / 0.000 | 6 / 0.000 | 6 / 0.000 |
| Metabolic disorder | 12 / 1.277 / E | 9 / -0.171 | 2 / 2.404 | 2 / 1.306 |
| Risperidone-induced Cardiac Dysfunction | 8 / 0.000 | 8 / 0.000 | 7 / 0.000 | 7 / 0.000 |
| Seizure disorder | 2 / 5.884 | 2 / 8.112 | 1 / 6.531 | 1 / 9.190 |

## 分值差量与未裁决残余
下表是冻结基线上的账面分解，不是可相加的临床因果效应。选定家族仍有范围内的多个原子；其余合法变化、其他未裁决错误、去重/分组和claimant权重相互作用全部留在残余中。舍入误差可达0.001分。
| 对比 | 候选 | 总软分Δ | 已选直接贡献Δ | 残余Δ |
|---|---|---:|---:|---:|
| old_old→old_v2 | Long QT Syndrome | +17.878 | +14.734 | +3.144 |
| free_old→free_v2 | Long QT Syndrome | +7.146 | +7.161 | -0.015 |

已选家族：Long QT Syndrome: `LQTS_unentailed_QT_positive_votes`.

## 已执行的局部干预
下列仅展示旧0与新free-v2的重点切面；四臂全部运行及原始行号见 `../interventions_neuro_cardio.json`。`restore_old_proven_wrong_brake`故意恢复已证错误，只用于机制验证。`suspend_*`关闭证据或连接，并不自动补充遗漏的正确来源程序。
| 臂 | 干预 | 历史代理rank | top1 | 第一/第二名分数 |
|---|---|---:|---|---|
| old_old | `baseline` | 1 | Catecholaminergic Polymorphic Ventricular Tachycardia | 26.518 / 5.884 |
| old_old | `release_CPVT_wrong_veto` | 1 | Catecholaminergic Polymorphic Ventricular Tachycardia | 26.518 / 5.884 |
| old_old | `release_CPVT_and_suspend_its_bad_joins` | 1 | Catecholaminergic Polymorphic Ventricular Tachycardia | 13.523 / 7.347 |
| old_old | `release_both_QT_and_CPVT_vetoes_probe` | 1 | Catecholaminergic Polymorphic Ventricular Tachycardia | 26.518 / 19.322 |
| old_old | `release_both_vetoes_and_suspend_QT_scores` | 1 | Catecholaminergic Polymorphic Ventricular Tachycardia | 26.518 / 5.884 |
| old_old | `release_both_and_suspend_both_soft_error_families` | 1 | Catecholaminergic Polymorphic Ventricular Tachycardia | 13.523 / 6.693 |
| free_v2 | `baseline` | 4 | Seizure disorder | 9.190 / 1.306 |
| free_v2 | `release_CPVT_wrong_veto` | 1 | Catecholaminergic Polymorphic Ventricular Tachycardia | 22.068 / 9.190 |
| free_v2 | `release_CPVT_and_suspend_its_bad_joins` | 1 | Catecholaminergic Polymorphic Ventricular Tachycardia | 13.096 / 9.320 |
| free_v2 | `release_both_QT_and_CPVT_vetoes_probe` | 2 | Long QT Syndrome | 25.628 / 22.068 |
| free_v2 | `release_both_vetoes_and_suspend_QT_scores` | 1 | Catecholaminergic Polymorphic Ventricular Tachycardia | 22.068 / 9.190 |
| free_v2 | `release_both_and_suspend_both_soft_error_families` | 1 | Catecholaminergic Polymorphic Ventricular Tachycardia | 13.096 / 8.848 |

完整重算命令：先运行 `python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/audit_neuro_cardio.py`，再运行同目录 `audit_neuro_cardio_identity.py`、`audit_neuro_cardio_family_scope.py` 与 `build_neuro_case_appendices.py`。未调用新的LLM，未改生产代码。
