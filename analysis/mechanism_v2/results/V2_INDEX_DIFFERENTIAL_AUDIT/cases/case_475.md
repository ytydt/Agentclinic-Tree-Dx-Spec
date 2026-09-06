# 例 475：神经痛性肌萎缩：单神经特征堆票，跨神经关系被压平

## 病例与终点

22岁女性突发孤立左上肢无力、不能OK与握拳、无感觉缺失、反射正常；EMG不仅累及AIN支配肌，也有肱二头、肱三头、三角肌改变；MRI正常。gold Parsonage–Turner Syndrome 与 `Neuralgic Amyotrophy` 按仓内别名对应。另有同名小写 `Neuralgic amyotrophy` 却不被历史gold集合接受；两者均未获同等绑定。`Brachial Plexitis` 相关，但本轮不自动把所有臂丛炎和单神经病变都认作完整同义实体。

## 真正的区分信息被拆成“不相连的名字”

源（v2 gid149129）明确NA可超出臂丛，累及前/后骨间、腋、正中、桡神经；其他AIN源给出分支与肌肉支配限制。患者的多肌肉EMG异常只存成一个“changes in biceps/triceps/deltoid”finding，没有论元图说明每条肌肉对应何神经、与AIN分布是否相容。正确判断需要结合两组信息；仅出现某一个神经名不足以作排除或确认。

## AIN 的错误支持如何逐项叠加

- 旧 gid149691 在AIN小节附近带入CTS的 thenar atrophy/APB weakness；旧 raw22/237把APB条目主体写成AIN syndrome。患者拇指远端屈曲无力不是APB外展功能阳性，但该原子仍接中 **+2.877**。
- 旧 gid669879说腕部正中神经损伤时AIN在前臂分支而获保留，所以患者 **仍能做OK**。旧 raw77将其挂到AIN syndrome并保留 `ability to make OK sign`。join却与患者 **不能OK**正向匹配 **+3.746**；源主体、解剖层级及文字否定均未受约束。
- 不能OK、拇指不能屈曲、食指远端不能屈曲、pincer movement弱、thumb-index coordination等多个表达对同一小组体征分别加票。这些并非全部来源规则错误；问题是同一患者观察被算作多份独立证据，而跨神经EMG关系只有一个压平finding。所选局部干预没有为了削弱AIN而删除全部真实AIN支配肌异常。

这三个直接审计的AIN错误项旧/旧累计 **+6.916**，删除后AIN仍为24.581而NA仍3.945。说明仅修旧审计提到的trauma极性或一个错误OK命题不会解决该病例，真正的剩余瓶颈是关系表示、身份绑定与重复投票。

## gold并不是清洁的弱者

NA的 `posterior interosseous nerve involvement` 接患者 anterior interosseous involvement，四臂各 **+1.124**。MRI可见肌肉水肿这一源结果又接EMG的“肌肉改变”，旧/旧 **+1.365**、其余 **+1.124**，患者实际MRI正常。仅有EMG失神经改变不能被视作患者已见MRI肌肉水肿。

负向污染也存在：旧两提示与旧提示/v2把MRI/影像本身当特征，因患者MRI正常扣分；新/v2把方法比较“MRI比超声敏感”两次转为 `MRI sensitivity` 特征/比较关系，又各扣0.4，甚至把“肩及上肢感觉丧失”接到normal MRI而扣分。方法层面的敏感度不是该患者阴性的疾病发现。

旧/旧只去除NA上述两种虚假正票，numeric-only 后NA仍第三；在claimants前真正阻断join，NA1.456而Mononeuritis Multiplex1.462，第三变第四。**重加权使Mononeuritis Multiplex增加0.427分，最终以0.006分超过NA，改变top3**，不应当用各贡献delta静态相减推断修复效果。新/v2则从1.959减到负分、降至第十；其top3非常依赖这两张错误正票。

## 新旧索引差量与错误抵消

NA得分四臂约3.945/3.997/3.704/1.959；AIN虽从31.498逐步降至18.793，金标并未追上：竞争者错误减少不是正确关系获得利用。新/旧的gold名次3→2，还伴随Mononeuropathy被错误 `all` 必要组排除；旧/v2和新/v2同样有其组否决，只是Brachial Plexitis升到NA之前。不能把新提示的第二名归因于正确地发现跨神经病变。

源差量示例旧463851→v2477657加入长腋神经解剖段；更多解剖文字并未转为带肌肉论元、层级与否定范围的可执行证据。本例的正确下一步应是“分布相容性”关系程序，而不是用出现过AIN就排除NA、或把宽泛正常MRI当万能排除。


## 四臂名次、分数与局部干预表

| 臂 | 目标分/名次 | 排名第一/分数 | 只屏蔽目标错误join | 只屏蔽竞争错误join | 双侧一起 |
|---|---:|---|---:|---:|---:|
| 旧提示/旧索引 | 3.945 / 3 | Anterior Interosseous Nerve Syndrome / 31.498 | 4 | 3 | 4 |
| 新提示/旧索引 | 3.997 / 2 | Anterior Interosseous Nerve Syndrome / 27.964 | 3 | 2 | 3 |
| 旧提示/v2 | 3.704 / 3 | Anterior Interosseous Nerve Syndrome / 23.511 | 3 | 3 | 3 |
| 新提示/v2 | 1.959 / 3 | Anterior Interosseous Nerve Syndrome / 18.793 | 10 | 3 | 10 |

## 明确证据行与首次损坏层

以下按错误家族列出**旧/旧及新/v2**实际产生贡献的代表原始行；去重support完整集合、数值与gate/bind/join元数据见JSON。正数和负数均照实保留，不把所有被选行都计为同向害处。

| 臂 | 错误家族 | 候选 | 代表raw行 | 实际贡献合计 |
|---|---|---|---|---:|
| 旧提示/旧索引 | D_carpal_scope_and_ability_polarity | Anterior Interosseous Nerve Syndrome | 21, 22, 77 | 6.916 |
| 旧提示/旧索引 | T_nerve_identity_mismatch | Neuralgic Amyotrophy | 1660 | 1.124 |
| 旧提示/旧索引 | T_mri_result_to_emg_change | Neuralgic Amyotrophy | 1667 | 1.365 |
| 旧提示/旧索引 | H_test_method_to_negative_result | Neuralgic Amyotrophy | 1668, 1671 | -0.800 |
| 新提示/v2 | D_carpal_scope_and_ability_polarity | Anterior Interosseous Nerve Syndrome | 18, 19, 54 | 5.935 |
| 新提示/v2 | T_nerve_identity_mismatch | Neuralgic Amyotrophy | 1796 | 1.124 |
| 新提示/v2 | T_mri_result_to_emg_change | Neuralgic Amyotrophy | 1801 | 1.124 |
| 新提示/v2 | H_test_method_to_negative_result | Neuralgic Amyotrophy | 1855, 2008, 2040 | -1.200 |

## 重放与审计口径

本报告使用 `replay_audit.py` 的 historical_default_stale B1/S7，完全冻结来源、病例facts、候选顺序与模型缓存；完整贡献未截至25条。此前exact_arm_window版本的若干竞争者分数略有变化，不能混用；gold名次一致并不等于所有分数一致。所有表格来自 `judgments_infect_neuro.json`，原始行号是**合并病例抽取数组零基索引**，不是局部cache行号。`_audit_source` 同时保存cache、gid、focus、局部行和源hash。

- numeric-only (`remove_contributions`)：只移除指定贡献，保留join、claimants和硬判决，测量固定连线中的票效应。
- join-block (`block_joins`)：在最佳匹配后、claimants/组执行前屏蔽指定连接，不寻找替代匹配；它会改变其他候选权重，属于条件机制干预。
- 本报告只审计指定错误家族，不声称覆盖所有分数的临床正确性。未插入oracle事实、未按gold删合法弱支持、未调用新LLM。病例是既定11题开发样本，不估计总体错误率。
- 由AI审计员逐段阅读与程序复算，不是真实临床专家双盲研究。`*_initial_probe.txt` 是早期定位中间件，可能包含同predicate的多个候选raw匹配，**最终归因以完整trace的deduplicated support IDs为准**。
