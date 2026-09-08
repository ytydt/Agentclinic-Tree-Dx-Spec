# 既有机械执行器：组身份、去重、真值、证据计数与排序的实现审计

审计基线为 `cursor4@bbc036e8a6ec93583be915a4609fe86278ed062c`。本分项只读生产代码，直接调用未改动的 `run_case` / `threshold_ok` 构造 **34个有限合成见证**，并读取上一轮全部 **44个冻结历史重放包**核对实际路径。所有见证通过不表示修复已实现，更不表示临床准确率提升。本分项无新LLM调用、无生产修改、无新医学事实补写。

主要定位文件为 [run_mechanical_engine.py](../RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_mechanical_engine.py)。完整逐缺陷记录、行号、修复类别和迁移映射见 [engine_defects.json](engine_defects.json)；逐见证输入构造与全部实际输出见 [reproduce_engine_defects.py](reproduce_engine_defects.py) 和 [reproduce_engine_defects_results.json](reproduce_engine_defects_results.json)。疾病身份和数值输入校验由本任务另一分项单列；本文件聚焦输入进入执行器以后发生的结构与效力损坏。

## 1. 结论及对用户疑点的精确裁定

问题确实不止LLM未忠实抽取。**即便输入已经包含正确组成员，后续确定性程序仍可改变其命题含义、删掉成员关系、放行尚未满足的条件，或把同一事实的多次转述当成多次支持/反证。** 但不能把所有问题都叫“尚未进入redesign的新缺陷”：上一轮M12/M13/M16–M20/M22–M24已经明确覆盖大部分根因，只是尚未实施。本轮补足直接代码见证、现行配置/历史暴露范围和更细的旁路。

| 用户指出的问题 | 实际代码机制 | 裁定与边界 |
|---|---|---|
| 不同疾病规则组莫名合并 | group key是`(_title,_section,_focus,gid,norm(subject))`，未含真实passage/cache/run身份；`norm`会删括号限定 | 同标题/焦点下，**相同归一主语**的不同源局部g1可合并。不同归一主语并不会直接合并；错主语绑定和括号归一化可先制造错误身份。S03提供不同主语不合并的负控制 |
| 去重组成员留下空白 | 全候选绑定之后，**各候选内**先按原子key去重，再构造组 | 没有显式null洞；后出现的成员行及其第二组membership被删除。组变短、消失或降singleton；不足2成员的组再被移除，剩余成员回原子L1/L2/L3。应称“成员关系丢失及回落”，不是某数组槽未填 |
| 去重仅字符串，去重不足 | key仅norm(predicate)/relation/polarity；同义改写和不同relation保为多行 | 同时存在**过合并与欠合并**：不同阈值/比较对象被合并，同一个事实的三种复述却仍可投三票。`_support`本身不乘分，完全相同key的原样复制通常已折叠 |
| 竞争语句数被当定向反证数 | L4逐保留行遍历：有comparator、relation在两值内、患者finding为present就每个匹配对手减0.5 | 描述准确，但须补充：它还绕过条件否定、阈值、完整组、非判据准入、source方向和疾病共存语义。加大竞争列表覆盖可增加处罚，却不是增加诊断证据 |
| 原子满足即当组满足 | 通常组sat按行计数而非root truth；singleton回原子；L4直接重遍全部group成员 | 三条不同路径不能混称一条bug。原子L1/L2本来会跳过保留下来的多成员组；真正的旁路是组已损坏成singleton，或L4绕过root，或重复fact凑足count |

“纯代码可修”在本文中严格指：**给定已有字段及经确认的语义合同，确定性代码可保住不变量**。它不意味着修代码就能恢复LLM漏掉的scope、误抽的疾病、未知的同义关系。人工核验词典/本体映射也是可用语义依据；并非每项都必须加一次LLM或新模型。

## 2. 缺陷族与已有redesign覆盖

[engine_defects.json](engine_defects.json)包含22项ENG记录；数值parser鲁棒性由IDN-08记录负责，故ENG-19有意不分配。以下分组不是相互独立错误率，多个机制可作用于同一行。

| 缺陷族 | ENG编号 | 主要代码段 | 修复性质 | 既有迁移覆盖 |
|---|---|---|---|---|
| 根命名空间、成员边、singleton回落 | 01–02 | 380–446、517–519 | 结构身份保存可纯代码；跨块等价/续组需语义依据 | M12/M13/M18已明确 |
| 有损去重、modality嫁接、同义多票 | 03–04 | 380–394、605–618 | 停止不合法合并可纯代码；完整同义/证据家族识别为混合语义任务 | M12/M15/M20已明确 |
| 组首行logic/n、signed/numeric literal、root effect、distinct count、ALL→necessary | 05–09 | 462–519 | 冲突校验及已知literal求值可纯代码；根合同/计数身份需结构或语义设计 | M04/M05/M13/M16–M18已明确 |
| 组绕过soft/F9、全未知CWA旁路 | 10–11 | 470–515、574–576 | 已确定准入的一致执行可纯代码；是否采闭世界为设计政策 | 原有准入原则覆盖，具体旁路本轮细化 |
| claimant污染与重复候选分母 | 12–13 | 421–426、474、598–626 | 一致准入/集合身份可纯代码 | M10/M19；重复label覆盖但增分母为本轮具体化 |
| L4数量、资格旁路、survivor依赖 | 14、16–17 | 527–551、628–644 | 明示错条件可代码止损；真正定向证据需ContrastRule与语义验证 | M18/M19/M22/M23已明确 |
| F10仅L3、原子条件消费者不一致 | 15、18 | 527–618 | 有定义的truth可纯代码；证据聚合需冻结政策 | M16/M18/M20已明确 |
| 确认计数、冲突、账本与tie | 20–21、23 | 563–568、611–667 | 账本可代码修；确认/冲突/tie处理为政策 | M23/M24已明确 |
| `--discriminative-only`死开关 | 22 | 54–55、694–724 | 参数契约可纯代码修 | M01/M24原则覆盖；该无消费开关为新具体发现 |

没有把“重新设计该怎么做”冒充已完成bug修补。本轮的合成脚本有意验证**旧行为确实存在**；生产文件保持原样，便于接下来在同一批输入上做单项修补和反事实比较。

## 3. 三种结构损坏为何可串联放大

### 3.1 共享叶去重没有共享语义，只有删除后行

真实结构可以是`(A∧B)→D`与`(A∧C)→D`。合法存储去重允许两条root edge都引用同一个A节点；当前实现却只保留第一次A所属的g1。g2只剩C后，组构造器把不足2成员的g2从`groups`删掉。于是C不再在`grouped_ids`，重新进入原子硬动作通道。

S04使用虚构疾病和信号：A缺失、B缺失、C存在；成员relation设pathognomonic，旧执行器仅凭C确认D。这里无需打开`RIGID_SUFFICIENT_CONFIRMS`，因为pathognomonic原子确认通道本来可用。与上一轮使用sufficient可选开关的E08不同，这个见证隔离了**当前已有硬确认通道**的结构风险。它不是说任意真实共享叶都应赋pathognomonic，而是给定grouped强规则时程序不应降为独立强原子。

当病例522的mutism因更早组而失去DSM membership时，后续`len(members)`已经不是来源标准成员数；同名g1的跨窗口错误合并又可能把其他来源的成员补进来。最终N既可能缩小也可能膨胀，不能只看“v2提取更多组”判断结构改善。

### 3.2 同一个key会过度合并，本应同一证据的句子又合并不足

S05构造两个同名必要条件，一个阈值≥3且typical，一个≥10且obligatory，患者值5。低阈值先出现则不排除，且借后行modality变成obligatory；高阈值先出现则排除。结果不是原文之一，而可能成为“来源甲的阈值与quote + 来源乙的强度”。S06只改comparator先后，就改变被处罚的疾病。

反过来，S07把一条redsignal分别写为redsignal、redsignal finding、redsignal feature；去重key不同，三行都接同一fact，分数从1变3。S20的同样改写放进differential contrast，即使开启F10，目标仍由-0.5变-1.5。**加宽字符串key与加窄字符串key都不是通用修法。** 应分别保存原文出现、完整逻辑对象、叶语义对象和证据家族。

### 3.3 群体和根效力不能从其他槽猜

组的成员relation可以不同，但当前没有明示这些relation如何构成前提，也没有root effect。强行让它们全部相同仍可能错误：例如根的临床动作是“建议检查”，前提里同时有既往病史、某检查结果与资源条件；这些前提不是各自对疾病的同一种支持。根字段与叶字段需要不同类型。

同理，`all`只是表达式内部联结。现行`GROUP_ALL_IS_REQUIRED`把它变为`D→E`，是方向推断，不是修复语法。缺某一条充分诊断路径只能说明该路径未建立，不能推断疾病不成立。S12直接复现这种方向扩张。

## 4. 同一已知条件在四个执行通道得到不同结果

| 给定条件与患者事实 | 原子硬路径 | 组路径 | 原子软路径 | L4 |
|---|---|---|---|---|
| 条件A≥10，A=1且present | required可否决；excludes仍触发；确认仅某开关检查 | 无视阈值，计一个sat | present先+w，失败仅-0.5w，仍+0.5w | 有comparator就扣对手，不看阈值 |
| 条件¬B，B明确absent | 否定required/excludes不进入asserted硬门 | 按患者absent算vio | 泛化为+0.3w，数值修正还可能反向 | 只要患者present才发，无视条件signed truth |
| 条件“normal A”，患者A normal | required统一读作absent而排除 | 统一vio | -0.5w | 不present所以不发 |
| 单位/数值无法比較 | threshold-aware confirmation的`is not False`允许None | 仍仅看present | presence奖励仍可保留 | 仍仅看present |
| 已判定非诊断/处理语句 | 单条soft context通常不硬/不L3 | 全soft组仍能加分；混合组可硬化 | F9仅在此拦截部分gate | soft context和F9均不检查 |

这些不是“语义近似容忍度不同”的合理设计差异。它们改变了条件是否满足和动作方向。最小共同接口应是单一`eval_literal`返回条件真值及witness，再由root决定诊断/检查/治疗/对比效果，评分器不能再次自行解释字符串。

本轮S27另对IDN-08直接交叉检查数值parser：缺单位可裸数比较，bool可变1，NaN比较False，非法range上界可抛ValueError。这些输入校验缺陷与上表的**消费者错误**分开统计；修正numeric parser后，若确认路径仍把Unknown当通过，危险仍在。

## 5. “竞争语句数量=反证数量”的完整实现链

L4的真实条件只有三项：当前源candidate未被淘汰；行有comparator且relation为`distinguishes_from/argues_against`；已连接finding的患者polarity为present。之后每条行、每个词面匹配的surviving target固定-0.5。

因此至少有六条独立路径：

1. **方向未证明。** 鉴别列表、mimic、建议排查B并不意味着已经获得反对B的患者证据。原文一句话提几个竞争者，不能变成多个有向反证。
2. **条件未证明。** negated行、未达阈值行、治疗行仍能发L4。这里不是只缺source verification；即使字段已经明确，代码也不读取。
3. **组未证明。** S19中A∧B只见A，原子L3虽然跳过组成员，L4又把A重新逐行执行，对B疾病扣分。
4. **证据次数无定义。** 一fact三复述变三条-0.5；F10只平均L3，不能修L4。
5. **目标被去重改写。** 同predicate/relation/polarity但comparator不同的两条真对比，保留首条目标，后条消失。L4既可能多扣也可能漏扣。
6. **survivor形成隐含前提。** 源candidate的任一错误veto会撤销其所有L4，释放该错误veto后多个对手同时掉分。修复前后名次变化不等于那条规则的局部分值。

S21给出了尤其不稳定的例子：一条`argues_against + comparator`若在criteria上下文，先硬排除主体，因主体不survive而不处罚comparator；仅将上下文改成differential，主体免于硬排除，反而开始处罚comparator。**规则反对哪个疾病被控制流决定了。** 修法须保存明确favor_target/against_target/condition/scope/source permission，再集中执行一次有效ContrastEvidence；不能把改一个if当成完整语义恢复。

实际病例179还存在跨阶段证据：old_old raw3053 / old_v2 raw3596的`prophylactic platelet transfusion`，polarity=negated，context=treatment，comparator为“dengue patients without active bleeding or significant coagulopathy”，从Congenital thrombocytopenia向Bleeding disorder发出L4处罚。本轮仅重读历史对象确认这条路径，不补患者输注指征，也不把它改成合法诊断反证。它说明任务2的阶段/目标建模与任务1的准入旁路相互独立：**即使现有字段已经写treatment，L4也照样绕过。**

## 6. 历史暴露范围：发生过，不等于全部已裁决为错误

四臂顺序与上一轮一致。`old_old/free_old/old_v2/free_v2`分别为旧/新提示词×旧/v2索引。下表直接从44包的实际stage与完整L4记录复算，无新模型调用。

| 机械观测量 | old_old | free_old | old_v2 | free_v2 |
|---|---:|---:|---:|---:|
| 组对象数（已组装，可能无任何可读fact） | 299 | 227 | 329 | 269 |
| 一个组含多个cache ID | 11 | 3 | 11 | 8 |
| 同组logic不一致 | 5 | 3 | 5 | 6 |
| 同组n不一致 | 1 | 1 | 1 | 4 |
| 同一个归一finding被同组多次计sat | 13 | 6 | 22 | 17 |
| 患者present却成员negated，仍计sat的成员数 | 4 | 6 | 5 | 6 |
| 数值阈值False仍计sat的成员数 | 2 | 1 | 6 | 4 |
| 实际非零组贡献数 | 124 | 84 | 136 | 102 |
| 其中全部成员均soft context | 27 | 20 | 33 | 24 |
| 实际L4处罚数 | 93 | 87 | 154 | 188 |
| 其中来源行属于group member | 5 | 5 | 21 | 32 |
| 其中来源行polarity=negated | 3 | 1 | 3 | 1 |
| 其中来源行属于soft context | 86 | 72 | 141 | 167 |
| 去重保留代表的modality被升级 | 514 | 488 | 573 | 461 |

**分母与解释限制：**

- 表内“组对象”由当前错误key定义，不是真实临床criterion group分母；“多个cache”是待审身份标志，重复曝光也可能指向同一个正确原规则。522的DSM/Walter错并有额外来源审阅；不能将全部cross-cache自动算错。
- 多个成员关系或context本身不必然非法；有意义的复合前提可能异质。缺陷在于当前没有表达它们如何共同支持根动作，却采用首行/任一required等默认政策。
- soft context含differential，其中可能存在真有方向的鉴别内容；所以141/167等不是错误反证数，也不能用“禁全部differential”作为修复成功标准。
- `present+negated`是输入条件与旧执行器读法不一致的机械证据；来源行本身也可能已抽错极性，须分别评估抽取与执行，不能只按程序应读真值冒充指南正确真值。
- 同归一finding多次计数不是自动临床错计，复合事实可能证明两个不同criterion；522的错误复用有逐例依据，其他仍需criterion级审阅。
- 各计数不互斥，不可相加得到错误数或归因比例；一个L4行可能同时是soft、negated及group成员，且对多个target发处罚。

补充JSON还记录原始membership代表丢失：按`(bound candidate label, extraction cache ID, local group ID, exact raw subject)`收集去重前/后的`_audit_raw_index`集合，至少2个raw行的来源出现分别为502/383/546/458，其中去重后不足2个代表为199/154/210/184。**这些是来源出现的代表行丢失，不是199/154/210/184个独立临床规则组被破坏。** 重复检索曝光可使同一真实规则多次出现；若保留显式shared references，它们本可合法共用语义成员。现行实现没有这种成员引用，但该缺口不能由原始出现数直接量化为语义损坏率。JSON里不同threshold/comparator/subject的桶也只是序列化字段差异，null表现、别名等价等会被计入，不能全部叫错去重。

## 7. 新补充的配置、数值与审计边界

**死开关ENG-22。** `--discriminative-only`的help承诺只计单一claimant的finding，代码却只设置变量和输出tag，未在run_case消费。S32用两candidate共享一fact且on/off严格相同、双方仍各1分来证明，不用“只测唯一claimant，两种实现本来就相同”的无效测试。冻结B1的该变量False，因此这是可造成后续实验标签误报的实现bug，不能归因历史v2下降。

**重复label分母ENG-13。** 同label候选在verdict字典被覆盖，claimant set也只保一个label，但IDF仍使用原始候选列表长度；相同最终可见ranking实体有不同score。纯代码可先验证或规范唯一ID，但不能将不同实体同名未经审阅合成一个concept。本轮仅合成复现；case74的大小写/近似duplicate不是完全同label，不能偷换为此bug的历史实例。

**CWA控制流ENG-11。** 全未知组先continue，根本到不了CLOSED_WORLD补缺失分支；仅见一个成员时剩余未知才变vio。这说明配置实现不一致，不是支持更强闭世界化。四臂关闭CLOSED_WORLD；推荐在新合同中显式Unknown，不能以修bug为由把所有未检测候选淘汰。

**账本ENG-21。** F10平均后总分可以是1，旧contributions却存三条各1；不启F10时30条合法贡献可以得30分但只保存前25条。完整重放器额外插桩解决了研究复算，生产仍未保存同样完整的proof/pool/applied delta。后续任何fix必须配完整账本，否则出现“修了规则但其他候选变化无法解释”的下一轮不可审计性。

**tie与冲突ENG-20/23。** 稳定sort本身不是bug，但它先按是否eliminated，再按confirmed条数，再按score，最后默认输入顺序。确认条数和来源复述数相关；同时确认且排除没有conflicted处理；输入顺序决定并列top1。策略应显式冻结，并列指标/冲突覆盖率应独立报告，不能任意改tie-break后宣称诊断提升。

## 8. 可纯代码实施的最小批次与必须保留的研究边界

可先在现有冻结raw上实施的确定性批次：

1. **不丢身份。** raw occurrence/root occurrence/member edge/source support分离；根命名空间补全；冲突logic/n拒绝执行但保留；禁止max-modality嫁接及singleton退回独立根动作。
2. **不绕过已知合同。** 候选ID一致校验；统一已确定的eligibility；signed literal和threshold三值解释；消费者不把Unknown当True；弱against不硬排除。仍必须保留合法必要/充分/排除正例，而非让所有规则不执行。
3. **不隐去结果。** 参数被真正消费或明确报废；完整贡献和membership/proof日志；pool前后delta、舍入、冲突与tie字段；固定配置快照。

以上批次应在旧source/raw/facts/candidates完全固定下单项和组合重放。不能要求每一个临床名次都单调上升：前轮522/74/49已证明错误会互相抵消，一条真实修复可能先撤去旧排名的偶然保护。

完整修复仍需额外语义技术/数据：

| 必须解决的语义任务 | 可采用的最小路线 | 不能称作修复的替代 |
|---|---|---|
| 同义predicate/criterion与独立证据家族 | 受审术语ID、完整typed签名、源文范围、候选语义对；等价与蕴含分开、正反对照验证 | 提高embedding阈值，或所有相同finding一律平均 |
| 不同source窗口是否同一根/连续组 | source layout/定义/脚注依赖、occurrence图、人工参考标准；只在有依据时显式合并 | local g1相同或标题相同自动合并 |
| 对比方向与是否有诊断作用 | 任务2stage/intent/action slots + explicit ContrastRule + source/countermodel审阅 | DDx名单直接against、仅看relation标签 |
| 计数单位和同一fact是否足够证明多个criterion | criterion域、事件/病灶/测量witness类型、有限计数上下界 | 行数作为计数，或统一按一个fact最多一票 |
| source忠实性与root effect | 完整规则独立审阅/参考IR、合成反模型、结构编译准入 | JSON合法、同模型复述一致、solver可执行即算忠实 |

详细技术调研在本任务统一方案中合并；这里给的是实现缺陷的接口需求及技术选择边界，不重复把前轮35项文献变成“又一次新验证”。

## 9. 复现及验收说明

从仓库根目录运行：

```bash
python analysis/mechanism_v2/results/IMPLEMENTATION_DEFECT_AUDIT/reproduce_engine_defects.py
```

脚本每个fixture重置列明的全局开关，默认启groups、关闭模型/embedding/F7/corpus LR，再按具体见证打开必要选项。这是**有限机制实验配置**，不是替代B1/S7的临床复跑。历史部分读取已有44个完整重放包，核对包数和L4总量，并保存每包SHA256；它不重新调用模型，不重写既有重放包。

34项中包含反例、对照和跨分项数值检查，因此不是34个新独立bug。S03防止任意跨病合并的过度归因；S34要求保留合法真排除与满足必要条件的正例。验收结果存旧引擎实际输出及应满足的不变量；**通过表示旧缺陷见证复现成功，不表示生产已通过新合同**。后续修复应将这些见证改为新不变量测试，并新增合法复杂组、正常条件、作用域不适用、冲突观测、独立新证据等成对控制。
