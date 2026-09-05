# v2 后 11 例队列：配对复算、终点纠错与跨病例语义审计

本报告审计冻结的 `trial_extraction_x2_*` 四臂与 `trial_engine_x2*.json`，不调用新模型、不修改生产实现。所有结果限定为这 11 个经人工判定“可分”的开发病例；不得外推成全部 MCR/DA 的准确率或规则错误率。主要源码为 `analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/` 下的 `build_trial_tasks.py`、`score_2x2_engine.py`、`run_mechanical_engine.py`、`gate_assertions.py`、`sweep_fixes.py`。

## 1. 可以复现的结论与必须收回的解释

冻结数据确实显示：v2 两臂各比对应旧索引臂少一个 top-1，该病例是 74；这说明当前组合未兑现抽取侧的结构改善。但旧报告 §35.5 的“语料侧与提示词侧的问题已经解决到可用程度”“更好的抽取转化为排名损失”均超出证据：跨行组更多、`required_for`/`sufficient_for` 产量增加，不证明规则的逻辑内容更忠实。下面的逐源审计直接确认，v2 仍把检查建议当排除规则、把其他疾病的预后标准挂给当前疾病、把 3/12 标准移植到三个宽泛表现上、把四个常见体征升为必要条件。

旧报告 §35.2 的“不是判据组的锅”也必须收窄。关闭 `GROUP_ALL_IS_REQUIRED` 只检查 `all` 组的一个刚性否决开关。它没有修正错误组成员、错误阈值、错误主体、组标识碰撞、部分满足加分、组内极性和阈值忽略，不能排除这些机制。

## 2. 冻结结果复算

以下 top-1/top-3/MRR 均为历史 **gold-label proxy**，不是 clinical-complete。复算直接读取逐例名次，同时运行 B1+S7 引擎，结果逐例匹配冻结文件。

| 提示词 / 索引 | top-1 | top-3 | MRR | 被排除的 gold-label proxy 所在病例数 | 组贡献记录 | 组排除记录 |
|---|---:|---:|---:|---:|---:|---:|
| 旧 / 旧 | 2/11 | 7/11 | .4273 | 1 | 124 | 3 |
| 新 / 旧 | 2/11 | 6/11 | .4132 | 1 | 84 | 7 |
| 旧 / v2 | 1/11 | 6/11 | .3667 | 2 | 136 | 6 |
| 新 / v2 | 1/11 | 4/11 | .3071 | 2 | 102 | 7 |

旧/旧→新/v2：逐例名次 5 变差、2 变好、4 不变；双侧配对符号检验 p=.453125。这个小型、经反复开发的病例集无法识别总体平均性能效应。四个独立 MRR 区间是否重叠不是配对效应的检验，配对信息已在 `cohort_metrics.json` 中保留。原文英文“based on Question 11”应理解为中文所述 11 题队列，而不是编号为 11 的单题。

所谓“六次金标淘汰”实际是跨四臂的六个病例×臂记录，并非六个不同病例、六个完整 gold 或六种独立机制：773 在四臂被记入，74 在 v2 两臂被记入；773 的被排除对象只是 PAH/IPAH/PFO 中的一个组件。

`--drop-excludes` 的历史结果依次为 top-1 2/2/1/1，MRR .4197/.4381/.3924/.3600。它把所有 `excludes` **以及** `argues_against` 断言删除，连组成员和软计分也改变，不是纯粹关闭层一否决。因而不能把此消融称为某个层一 guard 的严格收益上界。它消除了记录中的 gold-label proxy 排除，但 74 仅从 4 回到 2，且所有臂 top-1 不变。

## 3. 终点存在比样本量更根本的问题

`build_trial_tasks.py` 将上游 `gold_match == strong` 的注册表标签放进 `gold_labels_in_set`；引擎采用最靠前的任一此类标签作为 gold rank。没有重新判定其临床完整性。

| 例 | 真正 gold | 当前接受标签 | 问题 |
|---|---|---|---|
| 522 | Catatonia related to underlying Lewy body dementia | Catatonia / Dementia | 因果复合诊断被分解为任一组件即可 |
| 773 | IPAH with PFO | IPAH / PFO / PAH | 合取目标被改成组件析取，并接受父类 |
| 119 | Eruptive pruritic papular porokeratosis | Porokeratosis | 丢失具体亚型 |
| 257 | collar button abscess | Abscess | 丢失部位和形态 |
| 56 | Spindle cell squamous cell carcinoma | Carcinoma | 接受父类，却漏掉显式候选 Sarcomatoid squamous cell carcinoma |
| 91 | Angiosarcoma | Hemangioma | 不是等价疾病：错误别名污染 |
| 179 | hypoxia-induced thrombocytopenia | Thrombocytopenia | 丢失病因 |

例 91 可完整溯源：`method_hypothesis_recall_48.jsonl` 的 `MCR_v1_seq100/91 → methods.multistance.gold_registry_entries[0]`，concept C06 的 label 是 Hemangioma，而 aliases 为 Hemangiosarcoma、Angiosarcoma，因此获 `gold_match=strong`；任务构造器原样继承。不能把此标签当成安全同义词。

另有相反方向的漏记：例 475 只接受首字母大写的 Neuralgic Amyotrophy，不接受已有的同名小写标签；例 56 的明确完整候选未进入 gold 集；例 49 同时接受完整 stump appendicitis 和不完整 Appendicitis。这使 MRR、top-3、gold-eliminated 同时受假阳性和假阴性影响。

本轮另存 `cohort_gold_membership.json` 作术语层审核。没有伪称完成独立临床专家盲审，也没有用未审查的安全性假设生成“校正 clinical-complete 准确率”。唯一稳定的顶端标签事实是：旧索引两次 proxy 成功为 Porokeratosis 和完整 CPVT；v2 唯一 proxy 成功为 Porokeratosis。

## 4. 配对实验的实际控制与残余混杂

**固定项。** 四臂病例和候选集相同，病例 findings 的完整内容 SHA-256 相同。主审计的 raw-cache 溯源也确认 findings 输入去除了 MCQ options，因此不能因任务 JSON 包含 options 就声称本轮病例解析发生答案泄漏。

**不等量项。** 报告 §34 称每臂 3,842 passage×hypothesis 任务不准确；实际旧索引 3,842，v2 为 3,927。跨候选去重后的 case×gid 为旧 2,794、v2 2,855。索引修复同时改变了文本、窗口边界、检索选择、任务数量，因此它测的是该索引系统的综合改动，不是固定段落上的纯抽取效应。真正的原始调用/缓存去重分母应以主审计 `extraction_job_manifest.jsonl` 为准。

**提示词不止一个改动。** 新臂同时放开成组范围、过滤文献纳排标准，并做组枚举修复。尤其 `at_least_n` 缺 n 时降为 `any` 不是语义保持的归一化；尚未分离各改动的效应。

**语义接合能力不等。** 引擎 `embed_sim()` 在任一字符串不在 `join_embeddings.npz` 中时静默返回 0。新表达较多的臂更容易失去语义接合回退：

| 臂 | 在缓存中的唯一谓词 / 总唯一谓词 | 在缓存中的断言谓词 / 总断言 |
|---|---:|---:|
| 旧/旧 | 9,191 / 15,437 (59.5%) | 25,839 / 34,338 (75.2%) |
| 新/旧 | 7,684 / 15,322 (50.1%) | 23,237 / 33,533 (69.3%) |
| 旧/v2 | 8,348 / 16,584 (50.3%) | 24,983 / 36,837 (67.8%) |
| 新/v2 | 7,175 / 16,396 (43.8%) | 22,778 / 35,944 (63.4%) |

这些是**回退可用性**计数，不等于真实接合损失：许多谓词可以词法接合、不需要 embedding。但是，在相同 tau=.60 名义配置下，四臂并未获得完整、等量的语义回退。本轮没有补调用 embeddings 并把新结果冒充冻结实验。

**F7 来源接线实测。** 默认 F7 读取旧 `trial_retrieval_k30.json`，未自动读取本臂 x2 源。我们分别重放 (a) 明确清空 `F7_EXTRA_RETRIEVAL` 的默认来源；(b) 直接设置 F7 索引为本臂实际 extractor 的 `text[:6000]` 窗口，并在每臂重置缓存。全部八个重放 trace 落盘。默认配置逐例复现历史；来源修正改变了少量 gate 结果、bound 数及一个接合，但**四臂的每例 gold-proxy rank、top-1、MRR、排除数与组活动数均不变**。所以接线缺陷不能被当作这 11 题性能下降的已证原因；历史运行 shell 环境未被凭空重建。

**组统计非独立。** §34 将 390–612 个组视为各臂独立样本做 z 检验，忽略同病例、同文档、重叠 passage、多候选 focus 和同一原始响应的重复。跨行率上升是可复算描述，所给极小 p 值不能直接当成语义改进或独立泛化证据。跨索引还改变了参考文本分布；TVD 和“保真”代理也不是逐规则真值证明。

## 5. 四例、八个原文对照事件

完整证据与原始缓存编号见 `cohort_manual_ledger.json`。每条存 normalized assertion 的零基索引、完整抽取字段、source gid、原文窗口与 SHA-256，并连接主审计 exact job manifest。以下是人工式逐段阅读的判断，未经独立临床专家复审；选例是机制富集，不能据此计算总体错误率。

### 773：测试指征、病因排查和疾病排除混在同一关系中

新/v2 的 assertion 1336/1337/1338 把 PFO 的 joint pain、swelling、type 1 skin rash 写成 `excludes/asserted/typical`。原文 v2 gid 710361–710363 说的是：只有轻微减压病症状的潜水员**不需要进行 PFO 检查**。这是限定人群中的检查建议，不是有这些症状就没有 PFO。运行中 joint pain 还被接到 post-activity chest pain，随后硬排除 PFO。这条实际伤害链至少含“建议→诊断效力”和“关节痛→胸痛”两处独立错误；单把典型情态降权并不能修复语义。

旧/v2 assertion 1733/1734（gid 652189）则把“应排查其他 PH 原因”“V/Q scan 用于排查肺血栓栓塞”变成 left-heart-disease PH / pulmonary thromboembolism 的 `pulmonary hypertension excludes`。工作目标被误当成检查结果，谓词方向被翻转；再经宽泛主体绑定把规则送给 PAH/IPAH。正确表示需要区分“拟排查 X”和“某结果已足以排除 X”。

### 522：一个量词能被移植到错误集合、错误疾病和错误任务

- assertion 648–650、gid 889590/889591：DSM 三项以上的量词本来作用于指定十二种精神运动征象；抽取却将其作用于下句 “may involve A, B, or C” 的三个宽泛表现类别，变成这三个类别必须达到三项。成员数和 n 虽合法，逻辑对象完全改变。
- assertion 692–693、gid 889480：原文是 schizophreniform disorder 的“伴良好预后特征”至少两项标准。附近另列“伴紧张症”specifier，被错误连到 query focus；抽取将主体全部写作 Catatonia。这不是量词读取能力提高，而是量词正确、辖域错误。
- assertion 2134–2145、gid 11807：ACR 列出怀疑 DLB 时的十二种初始影像检查选项。抽取将每项写成 `sufficient_for`、组 `any`。源中没有“做任一种检查即可确诊”，也没有特定阳性结果。这直接反驳把 sufficient_for 数量上升视作净收益。

此外，这些 DSM 子组复用同一 book/title、空 section、Catatonia focus、`g1`，却来自不同 passage；序列化后原始抽取调用边界丢失，组键不能可靠区分临床标准和其他规则集。

### 257：源已经提供“不能这样排除”的例外，仍不能制约 all 组

新/v2 assertion 1177–1180 将 Kanavel 四体征写成 `all/feature_of/typical`。gid 413927 同时明说：屈肌腱鞘压痛出现较晚，不能因缺该体征排除 PFT；引用队列只有约半数患者具备四项。抽取并非完全没有读到例外：assertion 1340 写成 `required_for/negated`，但它是独立原子，不能约束另一个 all 组。执行时 F4b 又把 all 当作必要性。

因此，解决办法不是把 Kanavel 的 `all` 换成 `any` 然后恢复硬规则；需要区分描述性体征集、充分规则、必要规则和限制必要性的反例。此例证明非刚性集合被刚性化的路径；冻结日志没有显示该组误杀本例 gold，因此本轮不把它记成 gold 排除的因果病例。

### 475：负向语句的 polarity 以及查询焦点都可能造成错误

- assertion 23、gid 468793/468794：原文明确把直接外伤造成的 AIN injury 排除在该源所定义的 spontaneous AIN syndrome 之外。应为 `positive trauma → not this narrowly defined syndrome`；抽取却为 `excludes/negated`，在 asserted-only 层一不能执行。当前 vignette 并无直接外伤，因此是潜在漏排除，不是已经证实的本例 top-1 败因。
- assertion 53、gid 707478：关于腕部病变的检查说明说 AIN 在前臂分支，因此该远端病变中不应出现 AIN deficit。抽取把它挂成 AIN syndrome 自身的 “thumb flexion strength excludes/negated”。局部提到 AIN 并不允许把 query focus 当源命题主语；错误来自解剖/疾病作用域丢失。

## 6. 实际组结构怎样在执行前改变

`cohort_group_stages.py` 在对应臂的实际 F7 证据窗口下重建 gate、主体绑定、按 `(norm(predicate), relation, polarity)` 去重以及组装，取得以下真实队列计数：

| 臂 | 绑定后多成员组，去重前→后 | 降为单原子的组 | 剩余组跨原始调用 | 剩余组 logic 不一致 | n 不一致 | 同一 present finding 被多成员重复计数 |
|---|---:|---:|---:|---:|---:|---:|
| 旧/旧 | 455→299 | 36 | 11 | 5 | 1 | 13 |
| 新/旧 | 348→227 | 29 | 3 | 3 | 1 | 6 |
| 旧/v2 | 495→329 | 42 | 11 | 5 | 1 | 22 |
| 新/v2 | 424→269 | 41 | 8 | 6 | 4 | 17 |

这些是结构变换的暴露量，不是临床错误总数。重复提取的等价组被去重可以无害，不能把新/v2 消失的 155 组全部计作真实标准缺失；但降成单原子后改走原子执行、或把共享成员从另一个不同规则中删除，确实需要逐规则检查。新/v2 剩余组还有 14 个包含 negated 成员，46 个含数值阈值，不能用只数 present finding 的组执行器完整求值。

有完整 raw-cache 证据的实际碰撞不是推测：例 522 的 DSM `g1` 最终同时包含 n=3 的 broad categories 和 n=2 的 schizophreniform good-prognosis 条目，来自缓存 `3d023f1b95525a9c84c81b8f6e7616e611b29a5d` 与 `682ee483d163bca407163f388c3cfe3a742b0971`。组求值读取第一个成员的 n，并不进行成员共识校验。

同例 ACR 的 DLB 检查 any 组经 F7 从 sufficient_for 降为 feature_of 后仍保留；主体绑定把它送给 Chronic ischemic encephalopathy，七个检查谓词接到同一个 MRI brain。这不是七份独立阳性检查，也不是源对该候选的诊断支持。它显示语义不合格的断言仅被降级后仍可沿软分数路径发挥作用。此处未进行逐组删除后的名次因果归因。

## 7. 实验结论需要怎样收紧

现有证据支持“补齐列表并不足以让诊断规则可执行”，不支持“组语义已经解决，剩下只需降低刚性”。一个忠实的排除规则可以刚性执行，一个错误的非组合原子即使来自完整原文也不能因 `obligatory` 就取得否决权。真实干预应固定 source window 与候选概念身份，分别替换：原文→正确规则表达、正确规则→正确接合、正确接合→正确执行，保留每层判断的原文和实际轨迹。

优先评测单位应是完整规则：作用域、成员域、逻辑连接、量词、正反极性、阈值、诊断/分级/工作流效力、例外均正确才算一条有效规则。组产量、跨行跨度、高权关系数量、名义合法 JSON 只能作结构诊断指标。队列端点应先修复 gold-label proxy，并把这些 11 例保留为开发与回归用例；新的排名主张必须来自冻结配置后的独立病例。

## 文件

- `cohort_recompute.py` / `cohort_metrics.json`：四臂原始计数、缓存可用性、配对指标和两种 F7 来源重放。
- `cohort_trace_{0,1,2,3}_{default_stale,exact_arm_window}.json`：八个完整重放轨迹（含候选排名、否决、匹配对）。
- `build_cohort_manual_ledger.py` / `cohort_manual_ledger.json`：四病例八个 source-grounded 事件。
- `cohort_gold_membership.json`：十一例 gold 术语与粒度审核。
- `cohort_group_stages.py` / `cohort_group_stages.json`：组在实际 gate→绑定→去重→接合各阶段的计数及错误组实例。
