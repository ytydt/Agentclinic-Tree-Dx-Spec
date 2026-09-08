# 上游实现完整性审计：抽取、来源、缓存、门控与入口

冻结输入：`cursor4@bbc036e8a6ec93583be915a4609fe86278ed062c`。主引擎的绑定、分组执行、评分和排序另有专项，本文件避免重复认领。

本审计登记26项缺陷，含明确代码bug、可先止损但仍需语义技术补回的缺陷，以及必须显式制定政策的行为。运行40个缺陷反例/边界见证及1个正确行为对照；反例通过表示**旧实现存在该行为**，不是修复通过或临床错误率。无新LLM请求、无生产代码修改、无LFS下载。

上一轮redesign并非完全没有覆盖这些问题：M01/M06/M07/M09/M12/M13/M25已包含多数修复原则。这里新增的是可执行反例、具体代码边界、历史路径适用性和逐项验收；不能把补充缺陷数冒充此前完全忽视的设计目标数。

## 先修什么，为什么

最优先是使观测链可信：不可变run manifest、来源occurrence与actual payload、错误状态、原子缓存写入及配置一致性。这些不需要更强LLM。随后封堵JSON修复改字、量词缺省any、错误数值tokenizer、字段未归一化等确定性错误。此时再评估语义策略，否则来源、缓存或默认值可把新模型输出变成另一种规则。

来源quote对齐、纯语法枚举、稳定ID都不能独立解决疾病主体归属、指代、数值所属指标、必要/充分、workflow语义。对这些问题可先拒绝无证据自动升级，但恢复召回需要有类型的实体/事件/逻辑表示和来源审查；不能把停用所有规则称为能力提升。

## 历史四臂证据边界

| 机械计数 | old_old | free_old | old_v2 | free_v2 |
|---|---:|---:|---:|---:|
| 断言行 | 34338 | 33533 | 36837 | 35944 |
| 有group_id但无logic | 44 | 5 | 57 | 6 |
| 非法/缺失polarity | 4 | 1 | 2 | 1 |
| 有value_high的阈值行 | 870 | 791 | 797 | 742 |
| regex补全findings | 0 | 0 | 0 | 0 |

140,652行均未保存`_passage_sha1/_passage/_cache_key/_source_gid`，但有focus/title等弱来源信息；缓存与retrieval仍能辅助审计追溯。旧/新检索分别3842/3927次曝光、3746/3826个唯一任务：96/101次重复曝光；15/16个窗口超过6000字符。重复曝光不证明发生并发重复调用，阈值上界行数不证明其上界错误。

四臂B1/S7启用F5a和F7；F8、grounded和NL备用抽取不在此历史路径。四臂findings都没有regex backfill。主CLI覆写、当前模型label适配和小索引越界都是可复现边界风险，不是已证历史MRR原因。原始失败/parse错误无状态的缺陷使不能仅据{}缓存恢复可信的失败分母。

**独立复核排除的假阳性：** 初稿误判`--nli`单独开启不执行F8；真实代码为`if FIX_QUOTE_GATE or FIX_NLI`，独立开启可达。UP-C01实际调用run_case并截获gate证明正确分派，UP-22/UP-R33从缺陷登记移除，保留ID缺口以免旧引用错指。

## 缺陷总表

| ID | 缺陷 | 修复类别 | 旧redesign映射 |
|---|---|---|---|
| UP-01 | 缓存键未绑定真实提示词、模块、schema及provider配置 | code_only | M01, M25 |
| UP-02 | 运输、解析失败被永久缓存成成功空结果 | code_only | M25, M24 |
| UP-03 | 并发相同任务无single-flight且直接覆盖缓存文件 | code_only | M25, M01 |
| UP-04 | JSON语法修复会改写引号内来源文本，重复键静默覆写 | code_only | M06, M24, M25 |
| UP-05 | 无效量词数量被强制改为any，浮点和布尔值被截成整数 | code_only | M06, M13, M17 |
| UP-06 | 枚举语法归一化早返回失效；语义alias把风险/包含/未知升级为诊断关系 | hybrid_semantic | M05, M06, M08 |
| UP-07 | 抽取合并产物不保存来源出现身份、cache key及实际发送窗口 | code_only | M01, M12, M13, M24, M25 |
| UP-08 | F7使用默认旧来源表，hash截断不一致及全局缓存使真实arm来源脱节 | code_only | M01, M03, M09, M25 |
| UP-09 | quote不忠实时未拒绝，短窗口回退和邻文关键词替无关断言背书 | hybrid_semantic | M09, M01, M08 |
| UP-10 | 数值解析顺序与贪婪前缀破坏比较符、绑定首数字/年龄范围 | hybrid_semantic | M07, M06, M15 |
| UP-11 | 阈值来源许可只查下界数字子串，任意倍数替代，不校验上界/单位/方向 | hybrid_semantic | M07, M09, M15 |
| UP-12 | 必要/充分cue在quote内无谓词作用域；G1互斥假设删掉合法充要半边 | hybrid_semantic | M05, M09, M18 |
| UP-13 | G2参考范围重写丢等号，并从normal范围直接重建疾病必要条件 | hybrid_semantic | M05, M07, M08, M16 |
| UP-14 | G3把presence句中的or分支也当成必要合取成员 | hybrid_semantic | M04, M05, M08, M17, M18 |
| UP-15 | grounded闭集疾病校验是词袋拼接，先行词只靠nearest名称与宽松membership | hybrid_semantic | M06, M10, M11, M09 |
| UP-16 | grounded病例补全忽视否定、部位并制造时间配对 | hybrid_semantic | M14, M15, M16 |
| UP-17 | 自然语言规则备用抽取以长度代替语义完整性，stage枚举未验证 | hybrid_semantic | M02, M04, M05, M06 |
| UP-18 | NLI缓存忽略极性且未覆盖阈值/组/作用域 | code_only | M09, M25 |
| UP-19 | NLI否定整个关系而非关系内的谓词 | hybrid_semantic | M05, M09, M16 |
| UP-20 | NLI标签适配可把LABEL_1当neutral；skip没有逐行未验证状态 | design_policy | M09, M18, M24, M25 |
| UP-21 | 命令行输出路径未包含配置/完整性，局部运行覆写整臂 | code_only | M01, M24, M25 |
| UP-23 | 派生group_id使用进程随机hash及短模数 | code_only | M12, M13, M25 |
| UP-24 | 检索邻块doc_key空值串接跨文章；dense小索引top-k越界 | code_only | M02, M03, M01 |
| UP-25 | 括号内任意限定词作为疾病alias参与检索锚定 | hybrid_semantic | M10, M11, M03 |
| UP-26 | 程序化配置不验证布尔类型，字符串false实际启用 | code_only | M01, M24 |
| UP-27 | 提示词要求构造未被原文蕴含的converse，并把命名征象集合当必要全组 | hybrid_semantic | M04, M05, M06, M09 |

`code_only`指不需新增语义推断即可定义正确修补；修复已丢历史字段仍可能需要重放。`hybrid_semantic`指可纯代码阻止错误，但忠实补回需要来源或临床语义。`design_policy`指首先须冻结执行/验证政策，不能当作拼写错误直接改。

## 逐项机制、适用范围与验收

### UP-01 · 缓存键未绑定真实提示词、模块、schema及provider配置

**代码锚点：** [run_trial_extraction.py:248 `cache_key`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L248)；[run_trial_extraction.py:272 `Extractor.call`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L272)；[extract_nl_rules.py:91 `Extractor.call`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/extract_nl_rules.py#L91)

**机制：** 两条Extractor.call的key均只有(kind,payload,model)。相同kind但更换prompt/module会直接读旧输出；free-groups以手工kind后缀补丁防碰撞，无法保护后续提示词编辑。

**证据与范围：** `historical_path_enabled; historical_collision_not_established`。反例：`UP-R01-run_trial_extraction`, `UP-R01-extract_nl_rules`。

**修复：** `code_only`。以实际prompt/module/schema/模型与provider约束/完整payload建立版本化键；原始抽取、编译、验证分层缓存。校验依赖hash而非仅相信人工kind版本。

**边界：** 不能据此说历史新旧提示词互读：本次free路径已有独立kind；前轮确认2472个共同job是相同prompt的合法缓存复用。

**验收：** 同payload改prompt/module/schema使缓存miss；同语义依赖不变应hit；迁移旧条目标记legacy_unverified。

### UP-02 · 运输、解析失败被永久缓存成成功空结果

**代码锚点：** [run_trial_extraction.py:272 `Extractor.call`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L272)；[extract_nl_rules.py:91 `Extractor.call`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/extract_nl_rules.py#L91)；[llm_client.py:830 `RobustLLMClient.call_module`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/src/agentclinic_tree_dx/llm_client.py#L830)

**机制：** Extractor.call捕获异常或非dict返回后写{}；下次可正常处理时仍直接命中{}。LLM client本身也用{}表示最终解析失败，状态在调用边界已丢失。

**证据与范围：** `historical_path_enabled; no_historical_failure_count_estimated`。反例：`UP-R02`, `UP-R07`。

**修复：** `code_only`。返回typed status success_empty/success_nonempty/transport_error/parse_error/incomplete；失败有有界重试或TTL，不能当成有效空输出或来源本身没有规则。所有冻结来源单元仍保留在端到端分母，operational failure单列；仅成功调用条件下的内容保真率须另名另报，不得删除失败抬高召回。保留attempt/provider/token/raw记录。

**边界：** {'assertions':[]}是非空dict并可正常结束；UP-R07展示{}通用sentinel混淆，不把所有空规则结果称无效。

**验收：** 首次timeout后恢复能够重试；success_empty可复用；合法{}与非法JSON必须在parser结果中可区分。

### UP-03 · 并发相同任务无single-flight且直接覆盖缓存文件

**代码锚点：** [run_trial_extraction.py:565 `main`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L565)；[run_trial_extraction.py:272 `Extractor.call`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L272)；[extract_nl_rules.py:91 `Extractor.call`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/extract_nl_rules.py#L91)

**机制：** main用seen统计唯一数却不据其去重jobs；call仅对统计计数加锁，不锁exists→request→write。相同payload可同时调用、写同一路径；主Extractor读取半截JSON直接抛异常。

**证据与范围：** `historical_duplicate_jobs_observed; races_or_corruption_not_established`。反例：`UP-R03`, `UP-R04`。

**修复：** `code_only`。按payload键调度唯一任务，维护asker映射；single-flight或per-key锁；temp+fsync+atomic replace；读取损坏条目隔离而非永久空。

**边界：** 旧/新索引96/101次重复曝光不等于96/101次重复付费：缓存可能预存，任务也可能错开。NL主调度已dedup，但共享call仍非原子。

**验收：** 两个并发相同键只请求一次且两个asker获得同一完整结果；中断写入不污染已发布缓存；损坏条目有明确恢复状态。

### UP-04 · JSON语法修复会改写引号内来源文本，重复键静默覆写

**代码锚点：** [llm_client.py:784 `RobustLLMClient._sanitize_jsonish`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/src/agentclinic_tree_dx/llm_client.py#L784)；[llm_client.py:806 `RobustLLMClient._parse_json_object`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/src/agentclinic_tree_dx/llm_client.py#L806)

**机制：** _sanitize_jsonish的正则作用于整串，会把quoted 'A,}'改成'A}'。若对象另有trailing comma导致原串解析失败，错误修复结果随后成功；json.loads同时默许重复语义键取最后值。

**证据与范围：** `shared_parser_on_historical_extraction_path; occurrence_not_established`。反例：`UP-R05`, `UP-R06`。

**修复：** `code_only`。JSON repair必须词法感知string/escape；拒绝重复键；记录raw与每一步修复diff；来源跨度quote在修复后重新验证。

**边界：** 不能因fixture中有A,}就推断历史指南常有该字符组合；缺陷是字符串不变性被破坏，不是已测临床效应。

**验收：** 对任意合法字符串内容，修复外部trailing comma保持字符串字节；duplicate semantic keys报结构错误；保留合法嵌套JSON。

### UP-05 · 无效量词数量被强制改为any，浮点和布尔值被截成整数

**代码锚点：** [run_trial_extraction.py:335 `normalise_group`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L335)

**机制：** normalise_group对n直接int(n)：2.9→2、true→1；缺失/无效at_least_n被改成any。未知logic保留group_id却变null，来源不确定性被传播为可执行宽松结构。

**证据与范围：** `normalizer_executed_in_all_four_arms; original_invalid_count_frequency_not_reconstructed`。反例：`UP-R08`。

**修复：** `code_only`。仅允许非bool的正整数；缺失count或logic标unsupported/incomplete并保留raw，不猜any；完整组要求成员和根签名一致。

**边界：** 禁止错误默认可纯代码完成；补回未知n必须回源语义审查，不能从已归一化any恢复。四臂group_id有值而logic缺失44/5/57/6行为存在，不是该缺陷全部临床错误率。

**验收：** 缺失/float/bool/非数值n不获得新真值；合法n=2原样通过；错误组不可通过单叶硬动作旁路。

### UP-06 · 枚举语法归一化早返回失效；语义alias把风险/包含/未知升级为诊断关系

**代码锚点：** [run_mechanical_engine.py:176 `clamp_relation`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_mechanical_engine.py#L176)

**机制：** clamp_relation计算canonical rel后，若合法就返回原a；' REQUIRED_FOR '仍有空白大写。其risk_factor_for→caused_by、includes→variant_of和unknown→feature_of不是同义语法变换。

**证据与范围：** `F5a_enabled_in_B1_S7; noncanonical_case_space_count_zero_in_four_arm_inputs`。反例：`UP-R09`, `UP-R41`。

**修复：** `hybrid_semantic`。语法归一化必须写回；alias表仅允许可证明同义的符号别名。弱相关、方向不定includes和未知标签保留类型/待审状态，不变成有正贡献的feature。

**边界：** 未观察到四臂relation空白大小写实例，不能据fixture解释MRR；语义恢复则需来源/实体类型/方向判断，不是换映射表就完备。

**验收：** 大小写/空白语义等价得到同一关系；风险不推出因果；includes方向未定则不写parent关系；unknown不得转为诊断投票。

### UP-07 · 抽取合并产物不保存来源出现身份、cache key及实际发送窗口

**代码锚点：** [run_trial_extraction.py:565 `main`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L565)

**机制：** 普通路径只追加_focus/_source/_title/_section/_context_hint，未保留gid/window_gids/cache_key/passage hash/served范围。跨来源、跨窗口同名规则在下游已无法唯一逆向定位。

**证据与范围：** `observed_all_140652_assertion_rows_across_four_arms`。反例：代码/提示词静态审查与历史序列化普查。

**修复：** `code_only`。每个occurrence保存来源版本/doc/窗口gid/实际payload hash/字符边界/quote offsets/cache key/raw ordinal及组namespace；成员链接不得由标题重构。

**边界：** 原始cache、retrieval仍可由审计重建部分链路；不是说来源完全丢失。raw ordinal只在完整输出hash内稳定，不能作为跨版本持久ID。

**验收：** 每条产物能解析到唯一实际served payload；跨窗口同名g1不同ID；来源缺失应明确unknown，不借其他窗口许可。

### UP-08 · F7使用默认旧来源表，hash截断不一致及全局缓存使真实arm来源脱节

**代码锚点：** [gate_assertions.py:319 `_load_passage_index`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L319)；[gate_assertions.py:352 `resolve_passage`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L352)；[run_trial_extraction.py:392 `postprocess_grounded`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L392)；[run_trial_extraction.py:565 `main`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L565)

**机制：** _load_passage_index默认加载trial_retrieval_k30，环境追加不是替换；resolve_passage优先不到hash就按标题/quote选首窗口。grounded hash计算[:6000]payload，表却hash完整passage；全局_PASSAGE_INDEX不随环境改变失效。

**证据与范围：** `historical_B1_S7_default_stale_resolver_confirmed; grounded_hash_branch_optional`。反例：`UP-R19`, `UP-R20`。

**修复：** `code_only`。显式依赖注入本次run immutable payload registry；lookup键绑定实际发送hash，不能回退到同标题别窗口。full_source与served_excerpt分别存储，允许查周边也需标新证据。

**边界：** 前轮已锁定historical_default_stale为历史重放条件；修复实验需双轨，不能悄悄改旧基线。15/16个>6000窗说明边界真实存在，不证明每个门控借尾文。

**验收：** 同标题不同版本不会互换；6000截断hash精确匹配served窗口；改变run source不能读进程旧表；缺源拒绝许可。

### UP-09 · quote不忠实时未拒绝，短窗口回退和邻文关键词替无关断言背书

**代码锚点：** [gate_assertions.py:292 `evidence_span`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L292)；[gate_assertions.py:599 `gate_one`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L599)；[gate_assertions.py:451 `_subject_in_quote`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L451)

**机制：** evidence_span找不到quote时对<=2400字符passage直接返回整窗；gate_one不先做quote containment校验。pathognomonic cue只查licensed整窗，主语约束主要在variant分支触发。

**证据与范围：** `F7_enabled_in_all_four_arms; precise_occurrence_rate_not_estimated`。反例：`UP-R14`。

**修复：** `hybrid_semantic`。先确定quote offsets及完整规则跨度；缺失来源不能自动许可。来源忠实校验要绑定(subject,predicate,arrow,scope)而不是邻文关键词存在。可先纯代码封堵fallback，召回由结构跨度/语义核验补回。

**边界：** quote字符匹配是必要的provenance条件，不足以证明语义；应允许显式有记录的空白/Unicode规范化，不能凭宽松拼字视为蕴含。

**验收：** 伪quote不获得硬许可；邻句另一疾病pathognomonic不许可本句；真正跨句规则可由完整规则source spans通过。

### UP-10 · 数值解析顺序与贪婪前缀破坏比较符、绑定首数字/年龄范围

**代码锚点：** [gate_assertions.py:382 `parse_threshold_from_quote`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L382)；[run_trial_extraction.py:392 `postprocess_grounded`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L392)

**机制：** parse_threshold_from_quote声称优先operator，实际re.search先命中首个数字；[^0-9]{0,20}还吞掉比较符。短'QTc > 480 ms'→None，加长无关前缀反而可解析；年龄12–18范围可覆盖后面的QTc>480。

**证据与范围：** `F7_threshold_refill_enabled_historically; grounded_forced_parser_optional`。反例：`UP-R11`, `UP-R12`, `UP-R39`。

**修复：** `hybrid_semantic`。纯代码先修有符号numeric tokenizer/最长unit匹配/comparator边界；抽取所有带offset比较表达式，再按measurement role/time/unit绑定predicate。无唯一归属不强填。

**边界：** msec截成ms在该例数值上是同单位别名，不单独声称造成误判；此项重要风险是指标归属/比较方向，不是拼写外观。fixture的年龄不代表所有年龄规则都无效。

**验收：** 添加无关前缀不改变同一比较；首年份不遮后operator；负数/范围/闭开边界保持；不同measurement的多个cut不被强制合并。

### UP-11 · 阈值来源许可只查下界数字子串，任意倍数替代，不校验上界/单位/方向

**代码锚点：** [gate_assertions.py:256 `number_in_text`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L256)；[gate_assertions.py:599 `gate_one`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L599)

**机制：** number_in_text允许10/100/1000与倒数变换且用substring匹配，故48在1480、480在48均可通过；gate_one只验证value，value_high/operator/unit/relational不共同绑定。

**证据与范围：** `F7_enabled_historically; rows_with_upper_bound_870_791_797_742`。反例：`UP-R13`。

**修复：** `hybrid_semantic`。数值token全边界+typed unit转换；lower/upper/inclusive/operator/measurement/time必须同源对齐。只允许由已知单位推出的比例变化，不能因相似数字许可。

**边界：** 870/791/797/742是承受未校验upper-bound路径的行数，不是虚构上界数。完全恢复数值语义需要typed span模型或人工审阅。

**验收：** 5不匹配15；480ms只有显式0.48s才允许转换；虚构upper/operator/unit都拒绝；合法阈值完整通过。

### UP-12 · 必要/充分cue在quote内无谓词作用域；G1互斥假设删掉合法充要半边

**代码锚点：** [gate_assertions.py:484 `_necessity_scope`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L484)；[gate_assertions.py:498 `_sufficiency_scope`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L498)；[gate_assertions.py:580 `_g1_drop_dual_patho`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L580)

**机制：** _necessity_scope/_sufficiency_scope只要quote内有cue就返回quote，跳过predicate coverage；同一句多命题或多句quote可借用。G1按(subject,quote[:80])视necessary与pathognomonic不可共存，连不同predicate都未分开。

**证据与范围：** `F7_enabled_historically; broader_semantic_error_previously_observed`。反例：`UP-R15`, `UP-R16`。

**修复：** `hybrid_semantic`。删除'必要与充分互斥'假设，保留双向定义的两个授权方向；每条根结论绑定完整子句/谓词/主语scope；词法cue仅作为待审线索。

**边界：** 合法充分C→D不代表C必要；合法D↔C允许两者。禁用G1可修假阴性却不能认证抽取出来的双向都正确，需完整来源判别。

**验收：** 显式iff保两方向；仅必要不产生充分；句中A必要不许可B；两个不同谓词共享前80字符不得互相降权。

### UP-13 · G2参考范围重写丢等号，并从normal范围直接重建疾病必要条件

**代码锚点：** [gate_assertions.py:529 `_reference_range_recode`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L529)；[gate_assertions.py:599 `gate_one`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L599)

**机制：** _reference_range_recode把normal<k的补集写成>k，正确补集应>=k；normal>k同样应<=k。更深层是仅有参考正常范围并不证明诊断必须异常，却在E4后重建required_for+obligatory。

**证据与范围：** `F7_G2_enabled_historically; boundary_effect_not_estimated`。反例：`UP-R17`。

**修复：** `hybrid_semantic`。集合补集的闭开边界可纯代码修复；疾病必要性必须来源明确授权，不以参考range的存在推导。记录G2前后完整语义diff，禁止越过统一gate直接升级。

**边界：** 修等号不足以证明该疾病存在必要异常；正常值也不能被统称否定证据。

**验收：** <与>=、>与<=成对；范围外与疾病必要性分开；单纯正常range只能规范测量值而不能新造硬排除。

### UP-14 · G3把presence句中的or分支也当成必要合取成员

**代码锚点：** [gate_assertions.py:559 `_presence_limbs`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L559)；[gate_assertions.py:570 `_conjunction_limb`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L570)；[gate_assertions.py:599 `gate_one`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L599)

**机制：** PRESENCE_CLAUSE匹配body后，_conjunction_limb只做词重合，不查and/or或否定；gate_one可把'fever or rash'中的fever从feature_of升级required_for，仍未创建正确完整组。

**证据与范围：** `F7_G3_enabled_historically; synthetic_or_witness_not_rank_effect`。反例：`UP-R18`。

**修复：** `hybrid_semantic`。取消凭词重叠恢复根逻辑的升级；完整句编译成明确递归AST，单叶只有在已证D→(A∧B)时才可派生D→A，并继承scope/权限。

**边界：** G3保留typical modality不等于无害：关系会影响group required判定，且另有后续自动硬升级；具体后果由执行链审计负责。

**验收：** A∨B不能派生D→A；A∧B允许在源授权后派生；unless、双重否定和分支混合必须保持根结构。

### UP-15 · grounded闭集疾病校验是词袋拼接，先行词只靠nearest名称与宽松membership

**代码锚点：** [run_trial_extraction.py:315 `_fuzzy_in_passage`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L315)；[run_trial_extraction.py:392 `postprocess_grounded`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L392)

**机制：** _fuzzy_in_passage仅要求长内容词分别作为子串出现；'Pulmonary arterial hypertension'可由不同句Pulmonary edema/Arterial pressure/Hypertension拼出。postprocess还允许model未列mentioned_diseases的名称，只要fuzzy通过；quote未验证。

**证据与范围：** `grounded_optional_not_used_in_historical_four_arms`。反例：`UP-R10`。

**修复：** `hybrid_semantic`。先存有offset的实体mention与可审alias；跨句指代形成候选antecedents及置信/歧义，未解析不强猜nearest；语义实体链接与规则主语授权分开。

**边界：** 存在精确疾病名字也不证明这条predicate属于它。纯代码可拒绝词袋假阳性，但找回合法缩写/指代需实体链接、上下文指代技术或审阅。

**验收：** 散词不等于实体mention；明确同义缩写可经证据链接；两个最近候选先行词需保留不确定性；未知source subject不得默认retrieval focus。

### UP-16 · grounded病例补全忽视否定、部位并制造时间配对

**代码锚点：** [run_trial_extraction.py:471 `backfill_findings`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L471)

**机制：** 正则命中appendectomy/fluctuant即写present；surgical clips无条件canonical到right iliac fossa。SaO2和platelet分别遍历编号timepoint_i，首个血小板被配到更早首SaO2；只要existing blob有sao2，就整个serial补全关闭。

**证据与范围：** `grounded_optional; zero_backfilled_findings_in_four_frozen_arms`。反例：`UP-R22`, `UP-R23`, `UP-R24`。

**修复：** `hybrid_semantic`。删除病例定制的隐含部位与ordinal伪时间；exact span保留否定/对象/解剖/时点。未解析事件关系不填共享timepoint；按语义观测而非全局token做补全覆盖。

**边界：** 停止无根据补全可纯代码完成；可靠提取时间关系、否定、家族/患者角色仍需要临床事实解析技术。不能把可选路径bug用于解释历史四臂下降。

**验收：** no appendectomy不写已手术；左腋clips保左腋；单次SaO2已抽不阻断其他观测；无证据的时间邻近不假设同一事件。

### UP-17 · 自然语言规则备用抽取以长度代替语义完整性，stage枚举未验证

**代码锚点：** [extract_nl_rules.py:145 `postprocess`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/extract_nl_rules.py#L145)；[extract_nl_rules.py:134 `_disease_in_passage`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/extract_nl_rules.py#L134)

**机制：** postprocess用<6词删除句子，可删'A synthetic marker confirms DiseaseAlpha.'这一完整synthetic五词规则；disease仍词袋匹配，use任意字符串也接受。

**证据与范围：** `alternative_NL_extraction_not_historical_four_arms`。反例：`UP-R25`, `UP-R26`。

**修复：** `hybrid_semantic`。保留短而完整命题，标题用结构/谓词角色识别；use采用受约束schema但无法据合法enum认证stage正确；跨句规则支持多个source spans而非强制单句。

**边界：** 示例只使用虚构DiseaseAlpha，说明完整句可短。删除长度阈值是代码改动，区分heading与规范规则需结构/语义能力。

**验收：** 五词完整规则保留、六词无命题标题不自动通过；非法use待审；整个复合命题的跨句成员不因单句长度丢弃。

### UP-18 · NLI缓存忽略极性且未覆盖阈值/组/作用域

**代码锚点：** [nli_verify_assertions.py:40 `_cache_key`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/nli_verify_assertions.py#L40)；[nli_verify_assertions.py:135 `nli_check_one`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/nli_verify_assertions.py#L135)；[nli_verify_assertions.py:65 `verbalize`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/nli_verify_assertions.py#L65)

**机制：** nli_check_one键为quote,subject,relation,predicate，verbalize使用polarity。相反极性得同一key；threshold/group/scope不在键中也不在当前verbalization中，所谓7-tuple检查实际不完整。

**证据与范围：** `F8_optional_disabled_in_historical_B1_S7`。反例：`UP-R27`。

**修复：** `code_only`。key至少绑定actual premise+hypothesis+完整RuleAST+verbalizer/模型版本；所有影响决策槽位进入完整语义验证而不是只有四个词槽。

**边界：** 修缓存可纯代码完成，却不能让NLI自动获得临床源忠实性保证；当前缓存未包含的槽位不能被称已经核验。

**验收：** 极性/threshold/scope变更必miss；完全相同语义复用；阈值和组合不同不得共享认证。

### UP-19 · NLI否定整个关系而非关系内的谓词

**代码锚点：** [nli_verify_assertions.py:65 `verbalize`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/nli_verify_assertions.py#L65)

**机制：** verbalize对negated一律在句外包'it is not the case that'；absence-of-fever required for D被变成not(required(fever,D))，不是required(not fever,D)。

**证据与范围：** `F8_optional_disabled_in_historical_B1_S7`。反例：`UP-R28`。

**修复：** `hybrid_semantic`。先冻结predicate polarity/decision direction/scope语义，再从AST确定性渲染；不能由自由改写把否定移到箭头外。采用源→AST与AST→countermodel的独立核验，而非仅句面对句面NLI。

**边界：** 修固定模板是代码任务，但旧polarity本身语义混杂时需回源消歧；不能批量将所有negated解释为同一逻辑。

**验收：** ¬C→¬D、C→¬D、D→¬C、¬(D→C)四者可区分；否定不能跨scope移动；有来源相应正反例。

### UP-20 · NLI标签适配可把LABEL_1当neutral；skip没有逐行未验证状态

**代码锚点：** [nli_verify_assertions.py:113 `predict_label`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/nli_verify_assertions.py#L113)；[nli_verify_assertions.py:135 `nli_check_one`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/nli_verify_assertions.py#L135)；[nli_verify_assertions.py:158 `nli_filter_assertions`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/nli_verify_assertions.py#L158)

**机制：** predict_label优先config.id2label，generic LABEL_0/1/2覆盖已知MiniLM映射后全部落neutral；model不可用/无quote返回skip，filter保留硬关系且不写_nli状态。

**证据与范围：** `F8_optional; actual_current_model_label_config_not_loaded`。反例：`UP-R29`, `UP-R30`。

**修复：** `design_policy`。模型适配器固定并校验label语义；unknown labels报适配错误。验证coverage作为状态持久化，研究可选gate与部署必须认证的hard动作分开配置；skip不能伪装verified。

**边界：** generic labels是假设性模型配置fixture，不声称当前远端MiniLM一定如此。是否在模型不可用时阻断硬动作是显式设计政策，不能悄悄把历史no-op改为新算法。

**验收：** known mapping三类都正确；generic/缺失label拒绝适配；skip逐行可见；未验证硬动作按已冻结政策处理。

### UP-21 · 命令行输出路径未包含配置/完整性，局部运行覆写整臂

**代码锚点：** [run_trial_extraction.py:565 `main`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L565)；[run_mechanical_engine.py:689 `main`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_mechanical_engine.py#L689)；[run_trial_retrieval.py:83 `main`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_retrieval.py#L83)

**机制：** 抽取--grounded仅变prompt/kind不变suffix，--only-case/--limit-passages也写同一全臂名；引擎tag仅arm/suffix/loose/disc，weight/groups/F7/F8/embed/tasks等改变仍同路径。产物无run config/hash/completeness manifest。

**证据与范围：** `actual_entrypoints_reproduced; historical_files_overwritten_not_established`。反例：`UP-R31`, `UP-R32`, `UP-R40`。

**修复：** `code_only`。run-id由完整规范配置/输入hash生成，输出不可变；同名已存在若hash不同拒绝；partial/limit/failed分母与complete status入manifest，维护显式latest引用。

**边界：** fixture实际调用main但mock模型/引擎计算，仅证明文件命名和覆写机制；不证明历史四臂文件已遭覆盖。CLI显式--out-tag可人工避免，不能代替默认安全。

**验收：** 不同配置不覆盖；partial不能冒充full；所有产物可查输入/软件/环境/hash；同run重放应一致或显式version。

### UP-23 · 派生group_id使用进程随机hash及短模数

**代码锚点：** [gate_assertions.py:773 `_merge_and_or_required`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py#L773)

**机制：** _merge_and_or_required按abs(hash(key))%10000000构建ID，PYTHONHASHSEED变化时同样来源不同ID；key还只含quote[:80]与subject，窗口身份缺失。

**证据与范围：** `F7_enabled_historically; ID_nondeterminism_reproduced; accidental_collision_not_established`。反例：`UP-R21`。

**修复：** `code_only`。group occurrence使用source doc/version/served window/rootspan/subject signature的稳定加密hash，完整ID不用小模数；跨源归一对象与出现ID分开。

**边界：** 稳定ID本身不修复'quote中任意or就合并'的语义错误，也不允许把所有重复行保留后重复加分。合并与计分需要联动M12/M20。

**验收：** 不同进程相同输入相同ID；不同source/root不冲突；合法共享leaf保持member引用。

### UP-24 · 检索邻块doc_key空值串接跨文章；dense小索引top-k越界

**代码锚点：** [trial_retriever.py:36 `TrialRetriever.__init__`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/trial_retriever.py#L36)；[trial_retriever.py:92 `TrialRetriever.passage`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/trial_retriever.py#L92)；[trial_retriever.py:124 `TrialRetriever._dense_ranks`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/trial_retriever.py#L124)

**机制：** TrialRetriever将source|article_id作为文章边界，article_id空时整个源同doc，只warning；_dense_ranks不如_sparse_ranks把k限制为n。

**证据与范围：** `blank_doc_key_observed_in_old_index_prior_source_audit; dense_small_index_fixture_only`。反例：`UP-R36`, `UP-R38`。

**修复：** `code_only`。缺doc identity禁止自动跨块合并，需稳定来源article映射；索引build校验offset/meta/sourcehash/shape；dense k=min(pool,n)，空索引单独处理。

**边界：** 旧StatPearls空doc_key已由v2修复部分来源结构，不把旧索引问题说成v2仍普遍存在；小索引越界未影响几十万chunk历史索引。

**验收：** 相邻不同article不相接；同article正确闭包；n<pool或n=0不会越界；错版本byteoffset不能读成有效来源。

### UP-25 · 括号内任意限定词作为疾病alias参与检索锚定

**代码锚点：** [run_trial_retrieval.py:44 `label_forms`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_retrieval.py#L44)；[run_trial_retrieval.py:58 `subject_hit`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_retrieval.py#L58)

**机制：** label_forms无条件将括号内容独立加入forms；'Disease Alpha (severe)'产生'severe'，subject_hit把任一form substring当确切主体命中。后续focus进一步把弱相关来源向该候选倾斜。

**证据与范围：** `retrieval_path_enabled_historically; dangerous_alias_prevalence_not_measured`。反例：`UP-R37`。

**修复：** `hybrid_semantic`。区分括号别名/缩写与severity/site/etiology限定；alias需类型与出处，词边界检索只是召回而非归属授权；主体绑定须独立检查。

**边界：** 不是所有括号都应删除：真正缩写/同义名必须保留。语法止损能拦severe一类，但完整分类需要实体结构与医学词表/链接。

**验收：** severe/left/after surgery等限定不独立作为疾病alias；证实缩写可召回；上下位不合并；related页面不当rule subject entailment。

### UP-26 · 程序化配置不验证布尔类型，字符串false实际启用

**代码锚点：** [sweep_fixes.py:81 `configure`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/sweep_fixes.py#L81)

**机制：** sweep_fixes.configure直接把cfg.get('groups')写入global；字符串'false'非空因此下游if视true。CLI argparse store_true实际给bool，不存在同一路输入缺陷。

**证据与范围：** `programmatic_configuration_trust_boundary_only; historical_dicts_are_typed_bools`。反例：`UP-R35`。

**修复：** `code_only`。使用typed immutable RunConfig严格验证bool/float/range；拒绝未知键和字符串真假；一次配置重置所有执行参数（跨run遗留由AUX审计另列）。

**边界：** 这是future JSON/YAML/programmatic输入边界风险，不能把本次明确Python bool配置指为受污染。

**验收：** JSON boolean正常；'false'拒绝或显式解析成false；拼错配置键不静默忽略；有效配置回写manifest。

### UP-27 · 提示词要求构造未被原文蕴含的converse，并把命名征象集合当必要全组

**代码锚点：** [run_trial_extraction.py:565 `main`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L565)；[run_trial_extraction.py:135 `swap_group_block`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L135)；[run_trial_extraction.py:392 `postprocess_grounded`](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py#L392)

**机制：** CONVERSE_ADDENDUM要求对condition方向相反另造assertion且沿用同一quote；原因或one-way条件不普遍支持reverse-condition规则。group prompt将named complete signs直接映射all/every member required，完整列表与必要诊断准则混淆；grounded prompt把nearest antecedent作为默认规则。

**证据与范围：** `group_prompt_historical; converse_and_grounded_options_not_in_frozen_four_arms`。反例：代码/提示词静态审查与历史序列化普查。

**修复：** `hybrid_semantic`。source extraction只提原文授权命题；derived规则单独记录推导法、背景假设、证明与来源，不以原quote伪装逐字内容。named sign set先作为collection，只有来源明确必要/充分才赋诊断effect。

**边界：** 静态prompt审查，不是重新调用LLM实验证明改prompt必提升。某些物理机制可支持方向反转，但必须补齐前提并单独审核，不能笼统禁用一切推导。

**验收：** 相关/因果叙述不自动补逆；全部列出不等于全部必要；合法可证明derived rule可保留，但有parent/source/scope/profile证明链。

## 反例的复跑与覆盖

```bash
python analysis/mechanism_v2/results/IMPLEMENTATION_DEFECT_AUDIT/reproduce_upstream_defects.py
python analysis/mechanism_v2/results/IMPLEMENTATION_DEFECT_AUDIT/build_upstream_catalog.py
```

脚本在临时目录调用仓库真实函数；模型transport全部mock。CLI覆写测试保留真实main，只有模型调用或engine body被stub以隔离产物命名。稀疏工作树未检出的LLM client从冻结Git object读取，AST原方法无修改执行，避开外部客户端初始化。dense边界测试执行真实`_dense_ranks`，tensor/top-k用轻量契约替身，无torch模型。

[结构化缺陷账本](upstream_defects.json)、[反例结果与源码hash](reproduce_upstream_defects_results.json)、[复跑脚本](reproduce_upstream_defects.py)。反例统计包含同一缺陷的不同边界，不等于独立缺陷数量。

本次没有实施修复或重算新临床准确率；新增代码为审计脚本。执行与主体语义专项、技术调研及阶段/适用范围补充构成本轮其他独立产物。
