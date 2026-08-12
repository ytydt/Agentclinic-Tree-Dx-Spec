# E2 预注册：严格完整性、reference 可识别性与 mapper 投影盲审

## 冻结对象

- 病例总体：R4/R5/R6 同一 800 例；本实验不是新增确认集。
- 冻结样本：400 例，DA/MCR 各 200；cards SHA-256 `778cb28e080fb808a159fb95ca20476619b586462f1bddb4b919e0e44422fd17`。
- 选择版本：`E2-blinded-clinical-adjudication-v1`；源提交 `59c83063392920d837c5ee1b94167f56bb3cac4c`。
- 两位独立异构审阅员：Gemini 与 DeepSeek；不得复用生成这些轨迹的 Llama 族作为主审。
- 外部模型只作分包盲审；最终裁决、机制归因和结论由根审计负责。

## 抽样与可推断范围

主分层依次为 mapper harm、stable exclusive、mapper rescue、all-method strict failure、
composite/subtype、background。mapper-harm 与 stable-exclusive 单元全纳；其余在
`family × slice × primary_stratum` 单元内按冻结哈希抽样。每例保存 `N/n` 权重。
加权估计可回推此 800 例机制总体；未经权重的比例只能描述审计样本。稳定分歧只在
已有双次运行的 dev400 上定义，不外推到 200b。

## 独立的三个端点

1. **Strict/chain：** 原审计的精确或冻结同义桥命中，只作严格字符串端点。
2. **Clinical completeness：** pre-mapper 输出由盲审分为 complete、parent/component
   partial、conflicting scope、manifestation/related、wrong、uncertain。
3. **Task projection：** `scored_correct` 独立于临床关系；DA 的 mapper rescue/harm
   必须在 pre-mapper clinical relation 之后统计，不得把 option 命中当诊断完整。

Reference identifiability 是另一条轴：unique full、family-only、multiple complete、
unsupported specificity、insufficient、uncertain。不能因候选与 reference 同词就推断
病例能唯一支持该 reference。

## 盲法与候选范围

每例纳入 `r5_dual` 中所有可用终端 champion，按规范化后的**精确表面**去重；不做模糊
或临床合并。候选以冻结随机顺序编号。API 载荷只含病例正文、reference、候选 ID/文本；
不含数据集名、臂名、方法族、strict/task 标记、mapper 状态、分层标签或分数。

## 根级裁决范围

根审计至少覆盖：两审阅员全部 identifiability 分歧、全部候选 complete-vs-wrong/partial
端点分歧、任一方法的 strict/task/clinical 三口径冲突、所有审阅失败，以及按家族冻结的
一致阴性样本。根审计不得用方法声誉覆盖病例证据；查看臂映射只允许在关系裁决冻结之后。

## 否证条件与报告约束

- 若 clinical-complete 不能显著重排 strict 的主要臂序，则“差异主要由标签粒度造成”被削弱。
- 若重排只发生在 reference 非唯一/不支持全特异度病例，不得称为算法诊断能力改善。
- mapper rescue 若主要落在 clinical partial/wrong，说明任务投影在制造界面成功；若主要为
  complete，说明 strict bridge 漏掉临床同义。
- stable-exclusive 若经 clinical/identifiability 裁决消失，专长证据进一步被否证；若保留，
  才进入病例机制解剖，仍不自动代表题型专长。
- 所有模型失败留在 ITA 分母并单列；不得丢弃失败后只分析可服务病例。
