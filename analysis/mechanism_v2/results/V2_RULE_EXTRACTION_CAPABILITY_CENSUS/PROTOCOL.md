# v2规则抽取能力：预先冻结的审计协议

冻结日2026-09-05；输入基线cursor4@9a9b00b5（实际抽取缓存产生于96938384及此前）。本轮补齐上一轮缺少的有分母语义审核，不把故障富集反例当成总体错误率。

## 抽样框与双分母

S：v2实际送达抽取器的去重(source, text[:6000] SHA256)窗口，共2736。按来源分层，不按模型是否成功/是否成组筛选。固定样本量：statpearls24、pmc_oa12、textbooks12、merck6、manifest_cpg6、wikem4，共64窗口。每层按SHA256(seed+window_id)排序取前n，seed为V2-SEMANTIC-CENSUS-20260905-v1。纳入概率n_h/N_h。窗口重叠意味着目标是实际窗口暴露分布；另报告文档数、重复规则与同源聚类，不能外推全部指南库或800病例。

每个窗口选择其中一个既有focus调用（按cacheID排序），同一原文规则清单同时核验旧提示词/v2和新提示词/v2的原始输出；原文审核员先只见来源，写入并冻结source inventory后才揭示两个输出。审核员是AI，不冒称临床专家独立金标；冻结阅读顺序不等于完全不知道研究主题/既有病例。

O：新提示词/v2的**唯一原始缓存作业**中的输出规则单元。每个非空group_id聚合为一个输出组（包括混合subject/relation的坏组）；每个无组断言为一个原子输出。不把组成员再次纳入原子分母。原始不合法对象另列。按grouped/atomic分层抽样，各60/120，总180单元。记录纳入概率；两个审核员各90个。输出审核需要完整输入窗口和同调用所有组成员，不能仅看quote或字面匹配。使用已存在原始缓存，不以重抽结果代替历史结果。

## 原文规则单位

对象为来源对明确疾病/诊断类别所作的诊断性主张：必要、充分、排除、支持/反证、特征、定义与可诊断因果限定。一个完整共同效力的复合判据/评分程序是一条规则；叶节点不再独立计入源分母。单句若有两个独立效力/目标，分为两条。描述性症状列表可以记一条非刚性的association_set，允许多个忠实原子共同覆盖；不得把常见表现集臆定成必要AND。

工作流程、治疗、预后、研究纳排和纯病理机制若不构成诊断性主张，另列non_target_source，仍用来溯源错误输出，不能把它们的转写误称“无来源幻觉”。完整文本没有可审定规则时记零；不能丢弃此窗口。来源含糊、截断或层级不足使唯一解释不能确定时保留ambiguous_source，不强造金标。

每条源规则必须记录：source_rule_id、短原文锚点/精确跨度、疾病目标、类型、完整中性语言转述/AST、必要的scope/例外/阈值、可表达性(flat schema exact / lossy / impossible / ambiguous)。先冻结这些字段，再对应输出。

## 来源侧标签（相互排斥）

- faithful：在所有关键身份、条件/逻辑、极性、方向、强度和作用域上有完整正确表示，未被同一来源的冲突输出破坏。
- distorted：存在可识别的该规则后裔，但至少一处关键语义错误，或只剩碎片而不能恢复整个规则；同时标partial/mixed_correct_and_wrong等子码。
- omitted：没有任何可识别后裔。不是“缺一个成员”就把整个组算完全遗漏。
- ambiguous_source：来源本身无法可靠审定或对齐仍有争议，分列，不强行放进faithful/distorted/omitted。

主分母为可审定源规则faithful+distorted+omitted；同时显示包含ambiguous_source的全分母及未决比例。严格组faithful要求完整表达与组效力，不因某一个成员正确而判整组成功。另报告member coverage作为次级指标。

## 输出侧标签（相互排斥）

- faithful：完整输出规则忠实于可识别的来源诊断主张。
- distorted：有可识别来源祖先，但目标、原子、组、方向、范围或任务被改变；明确不将此类计入无来源幻觉。
- out_of_scope_traceable：忠实转写了治疗/预后等非目标内容；若把它改成诊断效力则属distorted。
- untraceable_fabrication：通读实际输入及可用同文档上下文后，无任何可识别来源祖先的新增主张。记录搜索范围及拒绝其他解释的理由。quote未逐字命中、主语被错绑、某关系不获原文支持本身均不够判此类。
- unresolved_provenance：无法回连或来源范围不足，不能因没有查到就断言幻觉。

主文分别报告源侧与输出侧比例，不把它们硬拼成四项和100%。纯幻觉仅指上述严格类，并限已审查来源范围；不能声称全世界不存在该医学主张。

## 错误位点与原因（正交、多标签）

位点：target/entity、predicate identity、relation direction、relation strength、literal polarity、negation scope、numeric comparator/value/unit、connective、cardinality n/domain/distinctness、nesting/branch、group membership/effect、scope/population/time/exception、score semantics、provenance、non-diagnostic task、unsupported new claim。

原因：source structure/ambiguity、prompt explicit wrong instruction、prompt underspecification、schema unrepresentable、model violated clear instruction、normalisation/compiler mutation、cache/provenance mutation、binding/evaluator mutation。首次损坏必须沿source→payload→raw→normalised→gate→binding→execution定位。

原因证据等级：A确定性程序见证/文本硬矛盾；B同源同模型受控干预或完整原始缓存直接定位；C机制相容但未隔离的归因假说；U未识别。不能因为模型输出错就自动断言模型容量不足，也不能因为补一句prompt后某次变好就宣称唯一原因是prompt。

## 汇总与审阅

用层内纳入概率逆权重估计窗口暴露总体的规则总量及比率；同时给出未加权样本整数。窗口作为抽样cluster，对分层窗口进行设计一致的bootstrap比率区间，并给出来源分层表。输出侧按grouped/atomic权重估计，各自给出整数与区间。小样本、同源重叠和AI审阅误差明确保留；不能用输出行数充当独立医学规则样本。

第二次复核覆盖所有疑似纯幻觉/未决项、组faithful项及一份预先固定的抽样复核子集。保留初判与复审差异；不得为得到预设结论调整样本。其余规则不冒称已双人审核。证据和中间产物均提交Git。
