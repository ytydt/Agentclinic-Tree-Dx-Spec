# 例 257：领扣脓肿：决定性词留在 quote，错误研究阈值却获得最高单票

## 病例与终点

66 岁、糖尿病、右手掌远端感染，1.5 cm 波动性痛性肿物，从掌侧指蹼延至第四指 A2 滑车；有屈肌鞘局限压痛，未发热，WBC 17.5×10⁹/L，X 线骨结构完整。完整 gold 是 collar-button abscess；候选中只有父类 `Abscess`，不存在完整实体。任何 Abscess 排名改善只能说明父类改善。不能沿用历史 manual_flow 的“Kanavel 四征不全即可排除 PFT”或“骨质完整即可排除骨髓炎”当作已证刚性规则：本轮源文本明确允许 some or all Kanavel signs，且未提及不等于明确不存在。

## 正确内容如何先失去执行入口

1. 旧、新输入均有 StatPearls 手感染检查段（旧 gid 533526）：局部红肿/积液伴波动感提示 abscess，并要求记录部位。旧 raw 96/126/127、新 raw 131/474 等已经抽出 `fluctuance`，而不是完全漏提指南规则。
2. 病例 finding 7 却写成 `label=painful mass, canonical=mass`；`fluctuant` 只留在 quote，掌侧指蹼/A2 的关键解剖结构只留在 qualifiers.site。当前 join 不用这些关系重建波动感，故正确断言未匹配。Cellulitis 的 fluctuance 排除也不触发；不能把这里归结为需更强的硬规则。
3. 两索引都把 Merck gid 1174 送到三种 tenosynovitis focus，段落实际明确 Palm Abscess 包含 collar-button abscess，且讨论掌侧间隙相通。四臂没有任何 subject/predicate 保留 collar-button 名称；部分 Palm Abscess 原子存在，但候选 full concept 缺失。增加完整原文并没有自动生成候选身份或跨 focus 提取缺口。

## 非致命错误如何累加成竞争优势

- **术后风险变当前诊断。** 旧 raw 573（gid 213382）把扳机指/腕管手术后伤口愈合并发症在 HbA1c>6.5% 较多，写成当前 Diabetic Hand Infection 的诊断 feature。源是术后结局、局部激素注射失败风险，患者并未接受这些手术。gate 没有阻断，11.2>6.5 命中后得到 **+6.764**，四臂相同；该候选仅一项有效正票就排第三。糖尿病确为感染风险背景，不使这条具体的术后阈值变成该病例当前疾病的诊断判据。
- **血液样本冒充滑液。** Septic Arthritis 的滑液 WBC>50,000、25,000–50,000、50,000–75,000 等不同阈值，都接到同一个血 WBC finding。旧 raw 1608/1887、1741、1897、1898、2032 的五份去重后票累计 **+7.576**。这不仅是重复：互斥区间也同时得分。带 cells/L 与患者 ×10⁹/L 不兼容时 `threshold_ok=None`，仍保留全正票；无单位时数值比较失败，仅扣半票，仍是正支持。
- **关节、手、髋的作用域混合。** Septic Arthritis 还从 RA 预后段得到“发病年龄<30”（旧 raw 1631）；subject 本来是 Rheumatoid Arthritis，松散绑定至 Septic Arthritis，66<30 为假仍有 **+0.932**。肩锁关节 ACJ、髋痛被接到手痛；不同解剖疾病的阳性证据互相转借。
- **手痛被重写成动作阳性。** Infectious Tenosynovitis 的 painful passive extension 接 painful mass（旧 raw 1092 等，**+2.133**）；不能触掌、thenar 部位症状和 hand sonography 也被接成已有手痛、红肿或压痛。并未建立“患者被动伸指引发痛”的关系。真实局限鞘压痛可保留为弱支持，本轮没有删除它。
- **研究人群年龄投票。** Cellulitis 的研究年龄、age of patients、age under18 重复接66岁。年龄分布不是患者已经符合某种疾病的充分特征；多个同一人群描述不是独立证据。

## v2 的局部改善也可能来自误杀竞争者

v2 的 Cellulitis 被 age under18 硬排除（旧提示 raw464，gid239059）。原文是颌面牙源性蜂窝织炎研究的 **研究排除标准**；66岁既不满足该阈值，也不应因此排除手部蜂窝织炎。真实链是 study eligibility→disease excludes，再由 L1 无视数值阈值触发。恢复这条竞争者与阻断其软错误是两种干预，账本分别记录，不能把 v2 的父类排名5→4称作正确临床利用增强。

## 如何理解干预

本例不在旧索引七个 top-3 中。选定软错误家族的 join 阻断使旧/旧父类 Abscess 从5到3，v2两臂从4到3，但所有臂仍由 Septic Arthritis/tenosynovitis 等占据前位，且无完整 collar-button 候选。删除错票无法补回 finding 解析失掉的波动感、解剖连接和不存在的完整候选。此结论支持先修事实表达、主体作用域、样本类型和组求值；不支持继续靠加大 Abscess 权重弥补。


## 四臂名次、分数与局部干预表

| 臂 | 目标分/名次 | 排名第一/分数 | 只屏蔽目标错误join | 只屏蔽竞争错误join | 双侧一起 |
|---|---:|---|---:|---:|---:|
| 旧提示/旧索引 | 2.907 / 5 | Septic Arthritis / 22.681 | — | 3 | 3 |
| 新提示/旧索引 | 0.722 / 7 | Septic Arthritis / 20.855 | — | 6 | 6 |
| 旧提示/v2 | 3.246 / 4 | Septic Arthritis / 19.932 | — | 3 | 3 |
| 新提示/v2 | 1.704 / 4 | Septic Arthritis / 19.478 | — | 3 | 3 |

## 明确证据行与首次损坏层

以下按错误家族列出**旧/旧及新/v2**实际产生贡献的代表原始行；去重support完整集合、数值与gate/bind/join元数据见JSON。正数和负数均照实保留，不把所有被选行都计为同向害处。

| 臂 | 错误家族 | 候选 | 代表raw行 | 实际贡献合计 |
|---|---|---|---|---:|
| 旧提示/旧索引 | D_population_anatomic_scope | Septic Arthritis | 1597, 1598, 1631, 1832, 1837 | 1.689 |
| 旧提示/旧索引 | D_specimen_mismatch | Septic Arthritis | 1608, 1741, 1897, 1898, 2032 | 7.576 |
| 旧提示/旧索引 | D_anatomy_action_join | Infectious Tenosynovitis | 1092, 1101, 1351, 1352, 1353, 1534 | 5.379 |
| 旧提示/旧索引 | D_postoperative_risk_to_current_diagnosis | Diabetic Hand Infection | 573 | 6.764 |
| 旧提示/旧索引 | D_research_population_to_feature | Cellulitis | 340, 395, 424 | 3.370 |
| 新提示/v2 | D_specimen_mismatch | Septic Arthritis | 1546, 1662, 1667 | 2.491 |
| 新提示/v2 | D_population_anatomic_scope | Septic Arthritis | 1767 | 0.246 |
| 新提示/v2 | D_anatomy_action_join | Infectious Tenosynovitis | 1090, 1096, 1101, 1331, 1332 | 4.776 |
| 新提示/v2 | D_postoperative_risk_to_current_diagnosis | Diabetic Hand Infection | 571 | 6.764 |
| 新提示/v2 | D_research_population_to_feature | Cellulitis | 367, 421, 461 | 3.370 |

## 重放与审计口径

本报告使用 `replay_audit.py` 的 historical_default_stale B1/S7，完全冻结来源、病例facts、候选顺序与模型缓存；完整贡献未截至25条。此前exact_arm_window版本的若干竞争者分数略有变化，不能混用；gold名次一致并不等于所有分数一致。所有表格来自 `judgments_infect_neuro.json`，原始行号是**合并病例抽取数组零基索引**，不是局部cache行号。`_audit_source` 同时保存cache、gid、focus、局部行和源hash。

- numeric-only (`remove_contributions`)：只移除指定贡献，保留join、claimants和硬判决，测量固定连线中的票效应。
- join-block (`block_joins`)：在最佳匹配后、claimants/组执行前屏蔽指定连接，不寻找替代匹配；它会改变其他候选权重，属于条件机制干预。
- 本报告只审计指定错误家族，不声称覆盖所有分数的临床正确性。未插入oracle事实、未按gold删合法弱支持、未调用新LLM。病例是既定11题开发样本，不估计总体错误率。
- 由AI审计员逐段阅读与程序复算，不是真实临床专家双盲研究。`*_initial_probe.txt` 是早期定位中间件，可能包含同predicate的多个候选raw匹配，**最终归因以完整trace的deduplicated support IDs为准**。
