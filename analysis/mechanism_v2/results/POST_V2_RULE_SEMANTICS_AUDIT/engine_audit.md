# v2 后的规则语义审计：执行器、抽取契约与程序门闸

审计对象为本次同步后的 `cursor4` 工作树。精确 HEAD 和被测代码 SHA-256 见 `engine_repro_results.json`。本文仅分析既有代码及报告，不调用 LLM、不下载外部医学资料、不改写生产实现。`engine_repro.py` 的 27 个确定性反例全部复现；它们证明具体实现缺陷存在，**不是实际病例错误率、v2 净效应量或医学有效性证明**。

路径缩写：

- `engine` = `analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_mechanical_engine.py`
- `extract` = 同目录 `run_trial_extraction.py`
- `gate` = 同目录 `gate_assertions.py`
- `score` = 同目录 `score_2x2_engine.py`
- `sweep` = 同目录 `sweep_fixes.py`
- `report` = `RAG_GUIDELINE_ORACLE_CEILING_LOCAL/MECHANICAL_RULE_TRIAL_REPORT.md`

## 1. 核心裁定

目前不能把问题概括为“补源已经成功，剩下只是 LLM 排除方向偶有误读，给层一降刚性即可”。同一条规则至少有五个彼此独立的真值保持条件：**语境适用范围、疾病主语、条件表达式、从条件到诊断的推理方向、条件与患者事实的绑定**。当前管线在其中每层都有确定性缺口。

最需要先处理的是以下事实：

1. 组求值器并非在执行抽取出的规则命题。它按病例发现的 `present/absent/normal` 数行，忽略组成员的否定、数值阈值和大部分关系标签，随后转换为加权分数。甚至已满足的 `excludes` 组会给被排除疾病加正分。
2. “all”描述表达式内部的合取，**不说明该合取对疾病是必要还是充分**。交付的 B1+S7 开启 F4b，将所有 all 组视为疾病必要条件；这会把充分条件的逆否方向误用成其逆命题。
3. 组进入求值器前已可能被程序破坏：全候选层去重先于建组，去重键不含组 ID、阈值、来源或适用范围；不同组共享成员因此会丢失。随后 passage-local `g1` 又按不含 passage 身份的键并组。一个组可能先被拆，再与无关组拼接。
4. 断言的“quote gate”并非真实性裁判。它既能放过无原文授权的 `excludes`，也会凭邻句词汇授权 `pathognomonic_for`；G2/G3/G1 等程序规则自身还会创造或删除逻辑关系。
5. §35 的“组不是原因”只排除了该样本中一个特定 F4b 开关对头条指标的大效应。它没有验证组命题是否正确，也没有排除组去重、绑定、门闸、真值求值及缺失组的责任。

## 2. “满足即排除 / 不满足即排除”必须分成两根轴

记 `D` 为疾病，`P` 为一个已确定作用域的发现，`E` 为可以包含否定、AND、OR、计数和阈值的完整表达式。正确契约需要分别保存“表达式是什么”和“表达式与 D 是什么关系”。

| 来源授权关系 | 允许的诊断动作 | 不允许的动作 |
|---|---|---|
| `D → E`，E 为必要条件 | E 明确为假时否定 D | E 为真时直接确认 D |
| `E → D`，E 为充分条件 | E 明确为真时确认 D | E 为假时否定 D |
| `E → ¬D`，E 为排除条件 | E 明确为真时否定 D | E 为假时确认 D |
| `D ↔ E`，明示定义/双向等价 | E 真确认；E 假否定 | 用“schema 不许双槽”删除一个方向 |
| E 仅支持/反对 D | 作为经过校准的软证据 | 无条件确认或排除 |

例如 `D → ¬P` 中“P 不存在”是必要条件，因此 P 明确存在时才违反条件；`¬P → ¬D` 中“不存在 P”本身就是排除条件。它们的词面都含否定，却有不同的疾病决策方向。把 `polarity=negated` 统一改成 `feature_of` 或统一视为逻辑冲突，不能解决这个问题。

还必须把 **未报告、未检测、结果不可比较、明确阴性、正常结果、结果自相矛盾** 分开。`normal` 不天然等于条件为假：对条件“正常 ECG”，正常结果恰为真。数值单位不匹配也只能得到 unknown，而非确认成功。

## 3. 组执行的独立缺陷

| 缺陷与代码定位 | 已复现结果 | 必须维持的语义 |
|---|---|---|
| `engine:466–469`，sat/vio 只读患者 polarity | E01：`A AND NOT B`，A 存在、B 明确不存在，仍被淘汰 | 先求 signed literal 真值，再求组真值 |
| `engine:466–509`，组不调用 `threshold_ok` | E02：必要 A≥10，患者 A=1，却算 satisfied | 阈值是 antecedent 的组成部分 |
| `engine:505–509`，any/k-of-n 只生成 delta | E03：必要 any 或至少2项，全部明确不存在，仍无必要条件违反 | 真假判定与方向应对所有表达式通用 |
| `engine:517–519`，已分组成员跳过单条层一/二 | E04：充分 all 组完全满足也不能确认；E06：excludes 组完全满足反给主体加分 | 效力是组级语义，不能丢弃，也不能逐成员硬套 |
| `engine:478–484`，F4b 用 all 推出 required | E05：充分-only 的 A∧B 缺 B 被误排除 | connective 与 implication direction 是独立字段 |
| `engine:462–465`，只读首成员 logic/n | E10：同组成员 n=2/3 冲突，换顺序即变分 | 组内冲突应失效并记录，不可首行决定 |
| `engine:466–469`，计数按成员行 | E17：同一个患者事实被两个近义 predicate 接合，被算为2项 | 需 criterion identity；同一事实可证明哪些不同 criterion 应显式裁决 |
| `engine:485–509`，soft_group 只约束 all veto | E18：单条 table_row 不打分，相同上下文成组后打分 | 组与原子的上下文准入政策一致 |

“at_least_n 没被充分利用”不只是匹配召回不足。它在实现层就没有 true/false/unknown 状态，也没有把状态传入必要/充分/排除解释器。现行 `all` 的 partial score、`at_least_n` 的 partial score 和 `any` 的 hit score 不能作为诊断标准真值的替代。

现有 schema 只含 `{group_id, logic, n}`。它无法原样存放 `A ∧ (B ∨ C)`、`至少2个major ∧ 至少1个minor`、`计分≥阈值`、`在指定患者亚群内适用`、`同一病灶内同时出现`、`同一次事件中`、`先发生A然后B`、`排除其他病因后`或按规则结果给出 definite/probable/possible。这是**表示不可表达**，不是模型输出 JSON 不规整。

也不宜把所有上述结构笼统称为“高阶逻辑”。很多只是有限布尔表达式和计数，递归 AST/DAG 已可表达；跨病灶、重复发作或时序的条件还需要实体/事件变量与 witness 绑定。仅增加 parent_group 而不定义成员身份、作用域和推理方向仍不够。

## 4. 去重和绑定是语义变换，而非中性工程步骤

### 4.1 先去重后建组会破坏本来正确的抽取

`engine:380–394` 使用 `(norm(predicate), relation, polarity)` 去重。阈值、组 ID、source、原文、亚群、时间、量词、comparator 全不在键中。保留首条对象，却把后续更强 modality 写进首条；此时可能形成“原文来自甲、强度来自乙、阈值留甲”的混合规则。`_support` 虽增加，但没有恢复其独立命题和出处。

E07：同名必要发现分别要求 ≥3 和 ≥10，患者值5。先放≥3则不淘汰，先放≥10则淘汰。无论这两条来自不同亚群、不同版本还是冲突来源，按输入顺序选一条都不合法。

E08：真实规则为 `(A∧B)→D` 与 `(A∧C)→D`，A缺失、B缺失、C存在。两个组共享 A。去重删除第二组的 A 后，第二组仅剩 C；`engine:444–445` 再删除 singleton 组身份，C 回到原子充分规则并单独确认。**正确的组被程序转化成了错误确诊。** 该反例启用 `RIGID_SUFFICIENT_CONFIRMS` 展示未来“放开充分性”的具体风险；现行默认关闭此开关会把伤害表现为软打分，结构损坏本身仍存在。

### 4.2 组身份缺少 passage 身份

prompt 明确 `group_id` 为 passage-local（`extract:66–68,189–191`），但 `engine:440` 的键是 `(_title,_section,_focus,gid,norm(subject))`。没有 `_source`、passage ID、chunk offset、hash，也没有 extraction run identity。非 grounded 抽取写出处时甚至不写 passage hash（`extract:697–715`；hash 只在 `postprocess_grounded:426` 写）。

E09：同章同节两篇 passage 各自独立的 `g1={A,B}` 和 `g1={C,D}` 被并成4成员组。虽然样例提供了不同 `_passage_sha1`，引擎仍忽略它。只有 index v2 而没有规则身份契约，更多被恢复的列表恰可能增加碰撞机会；实际发生率须在 cohort 账本中测量，不能由该反例外推。

### 4.3 主语绑定采用候选顺序优先

`engine:359–378` 在遇到**首个任意成功匹配**后跳出候选循环，并不全局选择 exact 最优。`concept_match:235–255` 的“strict”仍允许任一 token-set 包含另一方，因此不意味着临床等价。

E11：规则主体 Bacterial infection，候选为 Infection、Bacterial infection；父类列在前就拿走规则，反向排列则绑定到精确实体。更危险的实际边界是来源写父类的规则能否继承给亚型、来源写亚型的充分规则能否上推父类、候选的 alias 是否真的同义。这些是不同关系，不能统一由双向 containment 决定。

### 4.4 谓词绑定丢限定且对时序无知

`engine:29–43` 在 token join 中去掉 normal/abnormal/increased/decreased/high/low/without 等词，`norm()` 删除整段括号内容。`engine:401–409` 在同等级 join 中保留第一个病例 finding；不比较时间、部位、检查方法、样本、主语或冲突。

E12 证明 normal ECG 与 abnormal ECG 可以命中；E24 证明同名历史阴性/当前阳性只要换输入顺序就能逆转必要规则淘汰结果。阈值字段不能弥补纯定性反义词、同一事件限定和关系绑定的损失。

## 5. 非组合规则仍然有严重问题

| 缺陷 | 代码 | 后果 |
|---|---|---|
| `argues_against` 与 `excludes` 同义执行 | `engine:547–551` | E15：rare 的弱反证也无条件淘汰 |
| excludes 不求数值 antecedent，不查 modality | 同上 | E14：要求≥10的排除规则在患者值1时触发 |
| threshold-aware 确认将 unknown 当通过 | `engine:559–562` | E13：单位不匹配也能被确认 |
| normal 统一作 required violation | `engine:533–537` | 对“必须正常”条件误杀 |
| 单条 sufficient 默认没有确认通路 | `engine:80–83,555–556` | 充分标准降为 feature score |
| relational threshold 不执行 | `engine:316–346` | 例如 A pressure≥B pressure 字段被保存却不参与比较 |
| 部分缺阈值或无法比值仍可正计分 | `engine:581–603` | 未满足/未知数值条件不能阻断普通 presence 奖励 |
| comparator 处理不检查 assertion polarity/context | `engine:630–644` | 即使 asserted 已否定或处于 differential/table 文本，也可能向另一候选施加方向性扣分 |

第6项尤其需要区分“比较不了”与“阈值不适用”。`threshold_ok` 只对两端都声明且不一致的单位返回 unknown；若任一侧单位缺失，裸数仍可直接比较。这种比较通过不等于医疗量纲正确。

## 6. 门闸不能充当人工审计结果

### 6.1 正则修复可以再次制造逻辑错误

- **G2 从正常参考范围创造疾病必要条件**（`gate:529–555`）：从“正常 redsignal <10”加 `excludes/negated` 这一可疑行，直接改为“异常 redsignal >10 对疾病 obligatory”。正常范围并不蕴含某疾病必须异常；且 `<10` 的逻辑补集应为 `>=10`，代码却写 `>10`。E21 同时复现授权不足和边界丢失。
- **G1 禁止同句必要+特异/充分双槽**（`gate:580–596`）：只要 subject 和 quote 前80字符相同，就把 pathognomonic 降为 feature。E22 的明示双向定义是其反例。对偶槽可以源于错误提取，也可以源于真实定义；不能仅凭槽并存裁定。
- **G3 将诊断合取肢升级为 required**（`gate:559–576,759–765`）：代码只检查“diagnosed in presence of”句体包含该 predicate，并不证明该诊断路径是所有可行路径的必要条件。即便全组是充分的，也不推出每一成员对疾病必要。其保留原 modality 仅暂时降低硬否决概率，未使 relation 正确。
- **E9 混合式压成 any**（`gate:773–805`）：只要相同 quote 含 and/or，即把所有 required 行变成同一个 any 组。E25 中 `A AND (B OR C)` 被改成 `ANY(A,B,C)`。生成的 group ID 还使用 Python 随进程种子变化的 `hash()`，不利于跨进程审计身份稳定。
- **`at_least_n` 缺 n 变成 any**（`extract:375–379`）：E19。这是在猜逻辑，不是枚举合法化。合法化应返回 invalid/unresolved，并保存原值。

### 6.2 阈值提取器并不绑定测量实体

`parse_threshold_from_quote`（`gate:382–426`）宣称优先 operator-bearing comparison，实际第一条 regex 接受没有运算符的数字并使用 greedy `[^0-9]{0,20}` 前缀。E20 有三个独立现象：

1. 引导句先出现“2项标准”，会命中裸2后返回 None，后面的真正阈值不再查找。
2. 短文本 `redsignal >= 10` 的 greedy 前缀可以吞掉 `>=`，同样返回 None；换成长前缀后却能读取，形成无语义理由的长度依赖。
3. 原文含 redsignal≥10 和 bluesignal≤5 时，`postprocess_grounded` 对 bluesignal 也调用同一个整 quote parser，拿到 redsignal 的阈值。成员级绑定完全缺失。

E14 的 `number_in_text` 只验证某数字存在（`gate:614–627`），不验证该数字属于这个 predicate、该运算符、该 unit、该人群、该疾病，也不核验 `value_high` 的完整范围语义。

### 6.3 引文与辖域验证不足

`evidence_span` 的 docstring 称不能对齐时“strict fallback”，但代码允许在短 passage 里回退整个 passage（`gate:307–313`）。`pathognomonic_for` 仅要求任意 PATHO_CUE 在 licensed 窗口出现（`gate:674–679`），不要求与主体和 predicate 同句或同子句。E26：主体的 typical redsignal 借用相邻另一疾病的 diagnosed-by bluesignal，仍保住 pathognomonic 槽。

`excludes/asserted` 没有与必要/充分性同等的 source-cue 审查。E23 提供一段完全不在 source 中的 exclusion quote，F7 仍放行。故不能称“经过 F7 的刚性规则已被校验为真”；F7 是有限的启发式后处理。

### 6.4 v2 结果可能由旧 passage 授权

`gate:_load_passage_index:328–329` 默认只加载 `trial_retrieval_k30.json`，额外检索文件依赖环境变量 `F7_EXTRA_RETRIEVAL`；`score_2x2_engine.py` 本身不为四臂设置匹配来源，也不逐臂清空 `_PASSAGE_INDEX`。`resolve_passage:366–373` 先找 quote/quote前80字符，若只剩一篇旧 passage，甚至无须 quote 命中就返回。

这证明执行存在依赖绑定风险，**不单凭代码断言历史运行的环境变量一定为空**。本轮 cohort 审计应复跑 default 与 arm-only source index，并保存逐断言实际许可来源。仅在环境里追加新索引仍先遍历旧文件，不完全等同于 arm-only；最好直接构建该臂的独立内存 provenance map。

## 7. “重复计票”应如何严格描述

并非所有重复字句都会线性加分：exact 的 `(norm(predicate),relation,polarity)` 复本在 `engine:384` 已折叠，`_support` 没有直接乘分。问题是 **语义相同但文字不同** 的 predicate、不同 relation 槽、不同组、错误接合的相关发现仍可重复表决。

E16：`redsignal`、`redsignal finding`、`redsignal feature` 三个字符串去重后仍独立存在，却都接合到同一患者事实，得分从1升到3。B1 的 IDF/corpus_lift 只改变每条正分的倍率，未自动消除重复。F10 的 finding pooling 默认关，且只聚合原子层3；已成组的 contributions、层2 confirmations、层4 comparator penalties 不在同一池中（`engine:459,505–515,565,605–618,630–644`）。

另一方面，用“全体候选都 claim 一个 finding 就无区分力”代替 LR 也不充分。`claimants:421–426` 计入所有 asserted 关系，包括 excludes、argues_against、甚至随后因 context 不计分的条目；语料没提及某候选也不意味着它不具备该发现。文献覆盖频度、重复转述、候选集大小与临床区分力应分别记录。

## 8. 对既有报告结论的必要收窄

| 既有报告表述 | 本轮代码审计后的可支持结论 |
|---|---|
| §22“语料无责” | 被§24–31自身纠正；本轮也不能把有判据关键词等同成员完整、语义完整 |
| §23.4“名为 criteria 即刚性身份”，得到45.8% | 仅命名 criteria 的21.3%应保持效力未定；necessary+explicit sufficient 为24.5%，名称不能补足箭头方向 |
| §23/34 `any` 是唯一永远不能刚性的 logic | 当前代码中 **any 与 at_least_n 都不能刚性**；所有组都没有确认通路 |
| §34跨行增加/logic边际分布更近→抽取变好 | 证明结构可见性指标改善，不证明逐组成员、计数、否定、范围和推理方向联合正确 |
| §35.2“不是判据组的锅” | F4b消融很小只能约束这一个开关；组身份损坏和错误真值求值仍未隔离 |
| §35.4高权 relation 增多→降级问题被修复 | 需要人工核验新增规则 precision；槽计数不能区分找回真规则与制造假必要/假充分 |
| §35.5“语料与提示词问题已解决到可用程度” | 在缺少逐组语义有效率与端到端忠实执行测量时证据不足 |
| §35.6去掉excludes是该修法上界 | 脚本同时删除 `argues_against`、所有此类原子/组成员及其下游作用，是广泛删行干预，不是只关闭硬否决的纯消融 |

此外，CI 重叠不是两个模型差异的配对显著性检验；非显著也不证明“都在噪声内”。n=11 的描述性下降是真实样本观察，但不能外推总体，也不能凭 p>0.05 宣称方法等价。该统计问题由 cohort 账本统一处理。

## 9. 后续修复与实验的最小可识别路径

本轮只提交审计和可重放反例，不把这些局部例子调优为新的生产启发式。下一阶段应固定同一批 source、同一批候选与患者事实，依次引入：

1. **忠实规则对象**：source clause ID + evidence spans + population/context + typed subject + expression AST + group effect + licensing direction；invalid/unresolved 为正常输出，不猜 n，不因名称或列举自动赋予必要性。
2. **独立语义检查**：给人工审计员展示完整原段落、布局、定义/版本，分别判成员、连接词、计数、否定、时间/部位、效力与主语。只有每项通过的规则进入 rigid；记录每个 error 的首次出现阶段。
3. **真值解释器**：首先对事实求 literal 的 true/false/unknown/conflict，执行数值单位和 witness 限定；再递归求表达式；最后根据 necessary/sufficient/exclusion/support 映射动作。不要让 scorer 再“猜”规则的真值。
4. **身份与单元保持**：原子出现 ID、criterion ID、group ID、source provenance 分离；共享原子可被多个组引用，去重只消除等价来源复本，不删除组成员。采用不可碰撞的 source-version/passage-span-local key。
5. **两类 oracle 交叉**：固定自动抽取 vs 人工忠实规则，分别喂原引擎 vs reference interpreter；再固定语义正确规则、比较自动 fact join 与人工 join。这样才区分提取、解释和病例匹配三种瓶颈。
6. **专门不变量检验**：候选顺序、规则顺序、同义复述数量、重叠窗口、重复 source、组内顺序和时间顺序不应任意改变语义结果。E07–E11/E16/E24 已给出最小失败种子。

必须单独报告：source 判据完整率、完整表达式抽取正确率、方向正确率、事实绑定正确率、经检查可执行规则覆盖率、合法 rigid 动作次数、错误 veto/confirmation 次数、组被降为普通加分次数。最终排名只是其后的结果终点，不能替代这些语义终点。

## 10. 复现与产物

运行：

```bash
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/engine_repro.py
```

输出 `engine_repro_results.json` 包含27个完整微型证据、被测代码哈希、版本和作用范围。测试均使用虚构疾病/信号，避免把例子当作临床诊断建议。未触及生产模块；除被测源码外没有数据依赖，不需 embeddings、LR表、索引或 API。

反例 fixture 默认开启组解释器、关闭可选 embeddings/corpus-LR/F7，再按问题开单个相关开关；门闸反例直接测试 gate 函数并使用内存 source，所有这些配置均显式保存在脚本。**这不是对交付 B1+S7 的替代复算**；四臂真实数据的重放由同目录 cohort 产物承担。
