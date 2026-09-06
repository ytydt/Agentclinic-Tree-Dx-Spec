# 773：旧错误压住的干扰项，在v2取得了本应属于其他疾病的证据

病例：`DA_d2_heldout200b/773`。采用四臂B1/S7/default-F7，逐条检查原始vignette、曝光文本、候选绑定、全量软贡献与竞争罚分。

## 终点及患者事实

完整标签是“IPAH合并PFO”。冻结10候选没有该复合概念；历史评价却把 `IPAH`、`PAH`、`PFO` 任一单个标签当成功。旧0第2的PFO是影像已明示的真实组件，不等于找到了肺高压病因与分流结构的完整解释。新0对应v2第3仍是同一组件。free提示两索引的4→7则由IPAH这个组件决定，因为PFO被排除。

病例直接给出7.34mm PFO、持续纯右向左分流、右房右室增大、三尖瓣返流、肺动脉压60/39且低于主动脉压；肺动脉造影无肺栓塞或肺动静脉瘘。它没有提供PVR、PAWP或完整继发病因排查。不要从“PA压低于主动脉压”单独导出所有语境下的Eisenmenger绝对否决，也不要把已有资料强写为已经穷尽所有IPAH排除条件。真正可审计的是：来源描述Eisenmenger所需的起始大左向右分流及随后反向的**有时序因果关系**，不能从现在的右向左分流直接推回已存在这段历史。

## 竞争者并非只是有较多相关文献，而是取得了其他主语的规则

新free `CTEPH` 候选接收417条去重后断言，只有6条原始主语为CTEPH；另411条包括140条 `Pulmonary Hypertension`、100条 `Idiopathic Pulmonary Arterial Hypertension`、88条 `Pulmonary Arterial Hypertension`，其余多为其他PH/PAH写法或限定病种。

这411条不能全部判作医学错误：通用PH证据确实可以支持CTEPH的上位综合征。问题有两层：

- 明确IPAH、PVOD等其他病因/亚型的规则被绑定到CTEPH，是身份和适用范围错误；真实IPAH候选同时失去它们。
- 通用PH的压力、低氧、呼吸困难只能识别PH共同部分，却以大量相近谓词作为CTEPH可累加的分数，没有保留“对血栓性病因无区分力”的标记。

6条原生CTEPH里有4条根本没有事实连接；另外2条“PE后发生率”和“既往PE史”接到本例阴性PE事实，并未构成正面血栓证据。全量记录揭示：新free40.265分的优势不能据此解读成找到了CTEPH特异支持。下面同时提供小范围IPAH身份修复与大范围非同名赋值暂停；后者只是敏感性上界，不能当作临床正确修复。

## 新表格逐步变成无条件正票

v2 gid652023保存了ESC/ERS超声概率表及附加征象表。原文包含TR速度×其他征象的二维关系，以及：RV/LV基底径比>1、TAPSE/PASP<0.55、PA直径>25mm等不同量纲的条件。free原始467/1242/1705、469/1244/1707、472/1247/1710保留了若干数值片段，却在绑定后分别变成：

| 来源测量 | 实际事实连接 | 为什么不能执行成满足 |
|---|---|---|
| RV/LV径比>1 | 右室尺寸“增大” | 分母及比值不存在 |
| TAPSE/PASP<0.55 | PASP=55mmHg | 缺TAPSE，量纲不同 |
| PA直径>25mm | PA压=60mmHg | 解剖长度不是压力 |
| mPAP阈值 | PASP=55或“60/39”中的60 | 收缩压不是平均压 |
| PAWP/PCWP阈值 | PA压或PASP | 楔压不是肺动脉压力 |
| 监测血氧/测血压 | 测过血氧88.5、主动脉压 | 检查行动不是疾病条件 |
| 胸部影像 | 活动后胸痛 | 检查与症状仅共享词根 |

病例确实有PH，并不能使上述无效比较变为有效计算。不同表格和重复定义再次生成几种mPAP/PASP措辞；同一数值被多次计入。正确病例方向与错误计算偶然一致，正是必须单独审计的情形。

## 旧错误刹车消失，潜伏高分才进入可排名集合

旧free原始1872把“在超声提示PH且左心病可解释时无需继续检测”抽为 `PH / left heart disease / argues_against / asserted`。门闸将它升为排除，主语被绑定到CTEPH，谓词又错接 **right-to-left shunt**。于是CTEPH虽有34.836分仍被排在淘汰区。

该原文没有在v2彻底消失。旧PH焦点gid628614为935字符；v2相同核心句在TR焦点gid661576的1157字符扩展窗仍存在，但PH焦点不再曝光，且TR新输出为鉴别关系/评估参数，没有旧排除。故不能把这一变化单纯归因于提示词改善，两臂使用同一个free提示：检索焦点曝光与扩展上下文一起变了。

旧0另有原始1625“exclude other possible causes of pulmonary hypertension”被变为“有PH即排除CTEPH”的错误刹车。这在旧0帮助PFO组件进入第2；IPAH却同时受到另一“rule out thromboembolism→有PH即排除”的伤害。因此旧规则并不是可靠排除了CTEPH且可靠保留IPAH，而是错误作用方向偶然不同。

新free撤掉旧CTEPH刹车后，它从淘汰区进入首位；PFO仍受“潜水员只有轻微减压病不需要PFO检测”→PFO排除→关节痛错接胸痛的错误链影响。v2的主要伤害不是同一个致命错更强，而是**错误集合重新组合**，让常年潜伏的错配软分生效。

## 其他非致命错误也在同时改变目标和竞争项

PFO筛查组的唯一“满足”尤其明显：旧0原始1270、新free1335的 `family history of patent foramen ovale` 被绑定到本人PFO孔径，四臂均得到2.627分。原文是在谈哪些潜水员应接受筛查；家族成员、患者本人和检查指征三个角色被压成一个疾病词。

PFO虽有直接超声支持，分数中仍混入“PFO大小→右房大小”“小孔/大孔/显著大小”反复同事实计分，正常LA>RA压力描述被当前右向左分流当作满足，PFO closure建议被未闭孔径当作治疗命中。不能为保住PFO代理排名而保留这些坏分。删除PFO致命否决与删除PFO软错误，必须分别和联合运行。

Eisenmenger的新free原始1006 `large left-to-right shunts`是来源有依据的病因描述，但绑定成当前 **right-to-left shunt**；`left ventricular hypertrophy`接右室大小，室间压力相似也接右室大小。旧臂还把“肺循环压超过体循环”接PASP一项而忽略已有“低于主动脉”关系。该竞争诊断确实共享紫绀、右向左分流和PH，因此本文不删除所有相符表现，只暂停被错误证明的方向、测量及部位条件。

IPAH本身新free只有3个软贡献，合0.700分：其中“DVT导致PE”原始1529竟绑定到IPAH，且DVT接下肢水肿；另有右室扩大与肺血管病等不特异内容。四条竞争罚分再减2.000，最终−1.300。TR raw2149把左心病鉴别又接右向左分流，以PH comparator同时处罚IPAH和其他PH候选。这里目标下沉既有有用规则被抢占，也有与金标身份无关的惩罚；不是单纯目标命中条数少。

## 本例可以和不可以解释的东西

离线四格干预包括旧错误刹车的去除、在v2恢复该已证错误刹车、暂停数值/检查软错及两者交互。恢复错误刹车是机制验证，绝不是推荐修复。另做只修PFO否决、同时去PFO错误软分、只停Eisenmenger错方向，以及身份绑定探针。

一个必须保留的反证是：旧0清除已列PFO大小、压力、检查/治疗及家族角色错误后，PFO由19.301降到10.193，仍然代理第2；旧提示/v2降到8.911仍第3。旧PFO top-3并非完全由错误制造，它保留了题干直接影像确认的真实组件。在新free中则不同：仅解除PFO错否决得到20.090分、第2，再去上述错误正票后只剩8.044分、第4。所谓“修复有效”高度依赖同时保留哪些错误。

这些能定位“谁因何越过谁”，但还不是一个正确的临床程序：完整IPAH+PFO未生成、PVR/PAWP及全病因调查未提供，源文本/关系/事实均有未解决缺口。具体分值、全部候选及原始行号由下方自动附表和 `../judgments_neuro_cardio.json` 记录；全source与cache定位在 `../source_exposure_ledger.jsonl`，全轨迹在 `../replay_outputs/DA_d2_heldout200b__773__*.json.gz`。


<!-- GENERATED NEURO APPENDICES -->
## 完整四臂候选表
数格为“名次 / 软分 / E=已淘汰”。软分不等于最终排序；排除优先于软分。
| 候选 | 旧提示/旧索引 | 新提示/旧索引 | 旧提示/v2 | 新提示/v2 |
|---|---:|---:|---:|---:|
| Cardiomyopathy | 5 / 0.940 | 5 / 0.830 | 7 / 0.662 | 6 / 1.501 |
| Chronic Thromboembolic Disease | 3 / 3.578 | 10 / 4.382 / E | 5 / 4.549 | 5 / 4.549 |
| Chronic Thromboembolic Pulmonary Hypertension | 8 / 30.121 / E | 8 / 34.836 / E | 9 / 39.760 / E | 1 / 40.265 |
| Congenital Heart Disease | 4 / 3.222 | 3 / 3.013 | 4 / 4.895 | 4 / 4.559 |
| Eisenmenger Syndrome | 1 / 22.378 | 1 / 16.374 | 1 / 25.150 | 3 / 12.454 |
| Idiopathic Pulmonary Arterial Hypertension | 10 / 0.820 / E | 4 / 1.076 | 10 / 0.657 / E | 7 / -1.300 |
| Patent Foramen Ovale | 2 / 19.301 | 9 / 22.735 / E | 3 / 17.160 | 10 / 20.090 / E |
| Pulmonary Arterial Hypertension | 7 / 0.293 | 7 / -0.030 | 6 / 0.953 | 8 / -1.870 |
| Pulmonary Hypertension | 6 / 0.306 | 6 / 0.635 | 8 / -1.237 | 9 / -2.986 |
| Tricuspid Regurgitation | 9 / 10.853 / E | 2 / 9.835 | 2 / 18.195 | 2 / 18.047 |

## 分值差量与未裁决残余
下表是冻结基线上的账面分解，不是可相加的临床因果效应。选定家族仍有范围内的多个原子；其余合法变化、其他未裁决错误、去重/分组和claimant权重相互作用全部留在残余中。舍入误差可达0.001分。
| 对比 | 候选 | 总软分Δ | 已选直接贡献Δ | 残余Δ |
|---|---|---:|---:|---:|
| old_old→old_v2 | Chronic Thromboembolic Pulmonary Hypertension | +9.639 | +0.908 | +8.731 |
| free_old→free_v2 | Chronic Thromboembolic Pulmonary Hypertension | +5.429 | +0.643 | +4.786 |

已选家族：Chronic Thromboembolic Pulmonary Hypertension: `CTEPH_type_result_scope_errors`.

## 已执行的局部干预
下列仅展示旧0与新free-v2的重点切面；四臂全部运行及原始行号见 `../interventions_neuro_cardio.json`。`restore_old_proven_wrong_brake`故意恢复已证错误，只用于机制验证。`suspend_*`关闭证据或连接，并不自动补充遗漏的正确来源程序。
| 臂 | 干预 | 历史代理rank | top1 | 第一/第二名分数 |
|---|---|---:|---|---|
| old_old | `baseline` | 2 | Eisenmenger Syndrome | 22.378 / 19.301 |
| old_old | `suspend_CTEPH_numeric_and_test_votes` | 2 | Eisenmenger Syndrome | 22.378 / 19.301 |
| old_old | `release_CTEPH_old_wrong_brake` | 3 | Chronic Thromboembolic Pulmonary Hypertension | 29.621 / 22.378 |
| old_old | `release_brake_and_suspend_numeric_votes` | 3 | Eisenmenger Syndrome | 22.378 / 21.397 |
| old_old | `release_PFO_wrong_veto` | 2 | Eisenmenger Syndrome | 22.378 / 19.301 |
| old_old | `release_PFO_and_suspend_PFO_soft_errors` | 2 | Eisenmenger Syndrome | 22.378 / 12.820 |
| old_old | `suspend_Eisenmenger_wrong_joins` | 1 | Patent Foramen Ovale | 19.301 / 16.963 |
| free_v2 | `baseline` | 7 | Chronic Thromboembolic Pulmonary Hypertension | 40.265 / 18.047 |
| free_v2 | `suspend_CTEPH_numeric_and_test_votes` | 7 | Chronic Thromboembolic Pulmonary Hypertension | 24.232 / 18.047 |
| free_v2 | `release_CTEPH_old_wrong_brake` | 7 | Chronic Thromboembolic Pulmonary Hypertension | 40.265 / 18.047 |
| free_v2 | `release_brake_and_suspend_numeric_votes` | 7 | Chronic Thromboembolic Pulmonary Hypertension | 24.232 / 18.047 |
| free_v2 | `release_PFO_wrong_veto` | 2 | Chronic Thromboembolic Pulmonary Hypertension | 41.065 / 20.090 |
| free_v2 | `release_PFO_and_suspend_PFO_soft_errors` | 4 | Chronic Thromboembolic Pulmonary Hypertension | 41.065 / 18.096 |
| free_v2 | `suspend_Eisenmenger_wrong_joins` | 7 | Chronic Thromboembolic Pulmonary Hypertension | 41.669 / 18.890 |
| old_old | `restore_exact_IPAH_subject_identity` | 2 | Eisenmenger Syndrome | 21.698 / 19.301 |
| free_v2 | `restore_exact_IPAH_subject_identity` | 4 | Chronic Thromboembolic Pulmonary Hypertension | 27.661 / 16.963 |
| free_v2 | `restore_old_proven_wrong_brake` | 6 | Tricuspid Regurgitation | 18.047 / 12.454 |
| free_v2 | `restore_wrong_brake_and_suspend_numeric_votes` | 6 | Tricuspid Regurgitation | 18.047 / 12.454 |
| old_old | `release_PFO_and_suspend_soft_errors_including_family_role` | 2 | Eisenmenger Syndrome | 22.378 / 10.193 |
| free_v2 | `release_PFO_and_suspend_soft_errors_including_family_role` | 4 | Chronic Thromboembolic Pulmonary Hypertension | 41.065 / 18.096 |

完整重算命令：先运行 `python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/audit_neuro_cardio.py`，再运行同目录 `audit_neuro_cardio_identity.py`、`audit_neuro_cardio_family_scope.py` 与 `build_neuro_case_appendices.py`。未调用新的LLM，未改生产代码。
