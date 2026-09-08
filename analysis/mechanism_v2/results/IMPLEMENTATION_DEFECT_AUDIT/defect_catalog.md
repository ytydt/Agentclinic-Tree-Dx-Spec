# 统一缺陷索引

冻结输入 `bbc036e8a6ec93583be915a4609fe86278ed062c`。共 **63 个审计工作项**，含共享机制的不同侧面；不是独立 bug 数、临床错误率或因果贡献数。

分类以所提修复边界为准：纯代码能保护已有信息，不能自动恢复源文已经遗失的语义。完整记录、历史路径适用性和重叠关系见 [defect_registry.json](defect_registry.json)。

| ID | 实现问题 | 修复边界 | 具体证据 |
|---|---|---|---|
| IDN-01 | Destructive normalization erases qualifiers and literal constraints | 代码保护＋语义恢复 | [semantic_identity.md](semantic_identity.md)；IDR01, IDR02, IDR03 |
| IDN-02 | First-hit subject routing defeats global exact identity | 确定性代码约束 | [semantic_identity.md](semantic_identity.md)；IDR04, IDR05 |
| IDN-03 | Raw labels and unvalidated alias unions corrupt candidate identity | 代码保护＋语义恢复 | [semantic_identity.md](semantic_identity.md)；IDR06, IDR07 |
| IDN-04 | Symmetric lexical containment conflates equivalence with hierarchy | 代码保护＋语义恢复 | [semantic_identity.md](semantic_identity.md)；IDR08 |
| IDN-05 | Medical stemming treats organism-to-disease relation as identity | 代码保护＋语义恢复 | [semantic_identity.md](semantic_identity.md)；IDR09 |
| IDN-06 | Canonical early-break and first-tie finding selection are order dependent | 代码保护＋语义恢复 | [semantic_identity.md](semantic_identity.md)；IDR10, IDR11 |
| IDN-07 | Marker equality conflates result polarity while true aliases remain unreachable | 代码保护＋语义恢复 | [semantic_identity.md](semantic_identity.md)；IDR12, IDR13, IDR14 |
| IDN-08 | Numeric comparator lacks dimensional identity and robust value validation | 代码保护＋语义恢复 | [semantic_identity.md](semantic_identity.md)；IDR15, IDR16, IDR17, IDR18, IDR19 |
| IDN-09 | Atomic dedup conflates thresholds and fabricates cross-record modality | 确定性代码约束 | [semantic_identity.md](semantic_identity.md)；IDR20 |
| IDN-10 | Surface dedup misses equivalent paraphrases and repeated patient votes | 代码保护＋语义恢复 | [semantic_identity.md](semantic_identity.md)；IDR21 |
| IDN-11 | Existing observed value text is invisible to finding binding | 代码保护＋语义恢复 | [semantic_identity.md](semantic_identity.md)；IDR22 |
| IDN-12 | Existing feature types and qualifier fields are not consulted by joins | 代码保护＋语义恢复 | [semantic_identity.md](semantic_identity.md)；IDR23 |
| ENG-01 | 组身份只用标题/章节/focus/局部ID/归一主语，跨来源窗口碰撞 | 确定性代码约束 | [engine_structures.md](engine_structures.md)；S01, S02, S03 |
| ENG-02 | 先原子去重后建组删除membership，singleton回落原子执行 | 确定性代码约束 | [engine_structures.md](engine_structures.md)；S04 |
| ENG-03 | 去重忽略完整命题槽并嫁接最大modality，造成顺序选择与混合出处 | 确定性代码约束 | [engine_structures.md](engine_structures.md)；S05, S06 |
| ENG-04 | 字符串去重不足与不同relation复述造成同证据多票 | 代码保护＋语义恢复 | [engine_structures.md](engine_structures.md)；S07, S20 |
| ENG-05 | root logic/n冗余存每成员且执行只读首成员 | 确定性代码约束 | [engine_structures.md](engine_structures.md)；S08 |
| ENG-06 | 组literal求值忽略成员否定和数值条件 | 确定性代码约束 | [engine_structures.md](engine_structures.md)；S09 |
| ENG-07 | 完整组丢失充分/排除/必要效果；不同logic执行能力不对称 | 先明确设计政策 | [engine_structures.md](engine_structures.md)；S04, S11 |
| ENG-08 | count按保留行数而非criterion或事件身份，导致同fact多次满足 | 代码保护＋语义恢复 | [engine_structures.md](engine_structures.md)；S10 |
| ENG-09 | ALL connective自动变为疾病必要条件 | 先明确设计政策 | [engine_structures.md](engine_structures.md)；S12 |
| ENG-10 | 组通道绕过soft context和F9非判据准入；混合组可借一临床成员硬化 | 确定性代码约束 | [engine_structures.md](engine_structures.md)；S13, S14 |
| ENG-11 | CLOSED_WORLD对全未知组被提前continue绕过，开关行为不一致 | 确定性代码约束 | [engine_structures.md](engine_structures.md)；S15 |
| ENG-12 | claimants建立早于准入，零分/反证行也作为正向认领重加权 | 确定性代码约束 | [engine_structures.md](engine_structures.md)；S16 |
| ENG-13 | 重复candidate label被verdict覆盖却计入IDF分母 | 确定性代码约束 | [engine_structures.md](engine_structures.md)；S17 |
| ENG-14 | L4把竞争条目数量变成定向证据数量，且绕过条件/root/阶段 | 代码保护＋语义恢复 | [engine_structures.md](engine_structures.md)；S06, S18, S19, S20, S21 |
| ENG-15 | F10仅平均原子L3，组/确认/L4及跨层复用仍重复 | 先明确设计政策 | [engine_structures.md](engine_structures.md)；S20, S28 |
| ENG-16 | 弱argues_against当hard exclusion，且comparator目标解释受context影响 | 确定性代码约束 | [engine_structures.md](engine_structures.md)；S21, S23 |
| ENG-17 | L4依赖来源候选是否survive，局部错否决可删除对其他候选的比较 | 先明确设计政策 | [engine_structures.md](engine_structures.md)；S22 |
| ENG-18 | 原子literal在硬/软通道解释不一致：假阈值仍支持、未知可确认、正常必否决 | 确定性代码约束 | [engine_structures.md](engine_structures.md)；S23, S24, S25, S26, S34 |
| ENG-20 | confirmed按条数优先排序，确认/否决冲突无显式状态 | 先明确设计政策 | [engine_structures.md](engine_structures.md)；S28, S29 |
| ENG-21 | 贡献账本截断且F10记录的是pool前delta，不能从输出复算 | 确定性代码约束 | [engine_structures.md](engine_structures.md)；S30, S31 |
| ENG-22 | --discriminative-only开关未被执行器使用 | 确定性代码约束 | [engine_structures.md](engine_structures.md)；S32 |
| ENG-23 | 同状态同分排序继承candidate输入顺序且未标出tie | 先明确设计政策 | [engine_structures.md](engine_structures.md)；S33 |
| UP-01 | 缓存键未绑定真实提示词、模块、schema及provider配置 | 确定性代码约束 | [upstream_integrity.md](upstream_integrity.md)；UP-R01-run_trial_extraction, UP-R01-extract_nl_rules |
| UP-02 | 运输、解析失败被永久缓存成成功空结果 | 确定性代码约束 | [upstream_integrity.md](upstream_integrity.md)；UP-R02, UP-R07 |
| UP-03 | 并发相同任务无single-flight且直接覆盖缓存文件 | 确定性代码约束 | [upstream_integrity.md](upstream_integrity.md)；UP-R03, UP-R04 |
| UP-04 | JSON语法修复会改写引号内来源文本，重复键静默覆写 | 确定性代码约束 | [upstream_integrity.md](upstream_integrity.md)；UP-R05, UP-R06 |
| UP-05 | 无效量词数量被强制改为any，浮点和布尔值被截成整数 | 确定性代码约束 | [upstream_integrity.md](upstream_integrity.md)；UP-R08 |
| UP-06 | 枚举语法归一化早返回失效；语义alias把风险/包含/未知升级为诊断关系 | 代码保护＋语义恢复 | [upstream_integrity.md](upstream_integrity.md)；UP-R09, UP-R41 |
| UP-07 | 抽取合并产物不保存来源出现身份、cache key及实际发送窗口 | 确定性代码约束 | [upstream_integrity.md](upstream_integrity.md)； |
| UP-08 | F7使用默认旧来源表，hash截断不一致及全局缓存使真实arm来源脱节 | 确定性代码约束 | [upstream_integrity.md](upstream_integrity.md)；UP-R19, UP-R20 |
| UP-09 | quote不忠实时未拒绝，短窗口回退和邻文关键词替无关断言背书 | 代码保护＋语义恢复 | [upstream_integrity.md](upstream_integrity.md)；UP-R14 |
| UP-10 | 数值解析顺序与贪婪前缀破坏比较符、绑定首数字/年龄范围 | 代码保护＋语义恢复 | [upstream_integrity.md](upstream_integrity.md)；UP-R11, UP-R12, UP-R39 |
| UP-11 | 阈值来源许可只查下界数字子串，任意倍数替代，不校验上界/单位/方向 | 代码保护＋语义恢复 | [upstream_integrity.md](upstream_integrity.md)；UP-R13 |
| UP-12 | 必要/充分cue在quote内无谓词作用域；G1互斥假设删掉合法充要半边 | 代码保护＋语义恢复 | [upstream_integrity.md](upstream_integrity.md)；UP-R15, UP-R16 |
| UP-13 | G2参考范围重写丢等号，并从normal范围直接重建疾病必要条件 | 代码保护＋语义恢复 | [upstream_integrity.md](upstream_integrity.md)；UP-R17 |
| UP-14 | G3把presence句中的or分支也当成必要合取成员 | 代码保护＋语义恢复 | [upstream_integrity.md](upstream_integrity.md)；UP-R18 |
| UP-15 | grounded闭集疾病校验是词袋拼接，先行词只靠nearest名称与宽松membership | 代码保护＋语义恢复 | [upstream_integrity.md](upstream_integrity.md)；UP-R10 |
| UP-16 | grounded病例补全忽视否定、部位并制造时间配对 | 代码保护＋语义恢复 | [upstream_integrity.md](upstream_integrity.md)；UP-R22, UP-R23, UP-R24 |
| UP-17 | 自然语言规则备用抽取以长度代替语义完整性，stage枚举未验证 | 代码保护＋语义恢复 | [upstream_integrity.md](upstream_integrity.md)；UP-R25, UP-R26 |
| UP-18 | NLI缓存忽略极性且未覆盖阈值/组/作用域 | 确定性代码约束 | [upstream_integrity.md](upstream_integrity.md)；UP-R27 |
| UP-19 | NLI否定整个关系而非关系内的谓词 | 代码保护＋语义恢复 | [upstream_integrity.md](upstream_integrity.md)；UP-R28 |
| UP-20 | NLI标签适配可把LABEL_1当neutral；skip没有逐行未验证状态 | 先明确设计政策 | [upstream_integrity.md](upstream_integrity.md)；UP-R29, UP-R30 |
| UP-21 | 命令行输出路径未包含配置/完整性，局部运行覆写整臂 | 确定性代码约束 | [upstream_integrity.md](upstream_integrity.md)；UP-R31, UP-R32, UP-R40 |
| UP-23 | 派生group_id使用进程随机hash及短模数 | 确定性代码约束 | [upstream_integrity.md](upstream_integrity.md)；UP-R21 |
| UP-24 | 检索邻块doc_key空值串接跨文章；dense小索引top-k越界 | 确定性代码约束 | [upstream_integrity.md](upstream_integrity.md)；UP-R36, UP-R38 |
| UP-25 | 括号内任意限定词作为疾病alias参与检索锚定 | 代码保护＋语义恢复 | [upstream_integrity.md](upstream_integrity.md)；UP-R37 |
| UP-26 | 程序化配置不验证布尔类型，字符串false实际启用 | 确定性代码约束 | [upstream_integrity.md](upstream_integrity.md)；UP-R35 |
| UP-27 | 提示词要求构造未被原文蕴含的converse，并把命名征象集合当必要全组 | 代码保护＋语义恢复 | [upstream_integrity.md](upstream_integrity.md)； |
| AUX-01 | configure 未复位后来加入的七项全局配置 | 确定性代码约束 | [auxiliary_integrity.md](auxiliary_integrity.md)；AUX-R01 |
| AUX-02 | 病例候选集相对 corpus lift 用不含候选集的全局键覆盖 | 确定性代码约束 | [auxiliary_integrity.md](auxiliary_integrity.md)；AUX-R02, AUX-R03 |
| AUX-03 | 词表外限定被丢弃，部分词计数冒充完整疾病/事实统计 | 代码保护＋语义恢复 | [auxiliary_integrity.md](auxiliary_integrity.md)；AUX-R04, AUX-R05, AUX-R06 |

## 共享机制，不能重复当作独立发现

- ENG-03, IDN-09：same pre-group dedup defect, different consequences
- ENG-04, IDN-10：same repeated-evidence family, semantic and scoring facets
- ENG-13, IDN-03：candidate identity family; exact label overwrite versus alias/case identity
- ENG-18, IDN-08：numeric parser and downstream action consumers are related stages
- UP-10, UP-11, IDN-08：source parse, source license and patient comparison are distinct linked stages
- UP-01, UP-18, AUX-01, AUX-02：incomplete identity/state family with different caches and consumers
