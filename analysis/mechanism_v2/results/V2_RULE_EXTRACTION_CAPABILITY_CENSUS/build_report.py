#!/usr/bin/env python3
"""Render the audit narrative with values computed from saved adjudication ledgers."""
import json
from pathlib import Path
P=Path(__file__).resolve().parent
def pct(x):return f'{100*x:.2f}%'
def ci(x):return '–'.join(f'{100*v:.2f}' for v in x)+'%'
def main():
 m=json.loads((P/'census_metrics.json').read_text());g=json.loads((P/'raw_group_census.json').read_text());e=json.loads((P/'error_dimension_metrics.json').read_text())
 source=[]
 for label,cn in [('faithful','完整忠实'),('distorted','曲解或不完整'),('omitted','完全遗漏')]:
  o=m['source']['old']['adjudicable'];n=m['source']['new']['adjudicable']
  source.append(f"| {cn} | {o['counts'][label]}/272 | {pct(o['weighted_rates'][label])} | {n['counts'][label]}/272 | {pct(n['weighted_rates'][label])} | {ci(n['cluster_bootstrap_ci95'][label])} |")
 outputs=[]
 for label,cn in [('faithful','忠实诊断主张'),('distorted','有来源祖先的曲解'),('out_of_scope_traceable','忠实但属于非诊断目标'),('untraceable_fabrication','严格无源虚构'),('unresolved_provenance','来源未决')]:
  a=m['output']['atomic'];b=m['output']['grouped'];c=m['output']['all']
  outputs.append(f"| {cn} | {a['counts'][label]}/120 ({pct(a['weighted_rates'][label])}) | {b['counts'][label]}/60 ({pct(b['weighted_rates'][label])}) | {pct(c['weighted_rates'][label])} |")
 complexity=[]
 for kind,cn in [('atomic','独立原子'),('association_set','非刚性表现/关联集合'),('scoped_rule','带人群、时间或其他范围的规则'),('flat_group','浅层复合组'),('nested_group','嵌套/域/条件组'),('score','评分程序')]:
  d=m['source']['new']['by_complexity'][kind];c=d['counts'];complexity.append(f"| {cn} | {d['n']} | {c['faithful']} | {c['distorted']} | {c['omitted']} |")
 strata=[]
 for name,nw in [('statpearls',24),('pmc_oa',12),('textbooks',12),('merck',6),('manifest_cpg',6),('wikem',4)]:
  d=m['source']['new']['by_source'][name];c=d['counts'];strata.append(f"| {name} | {nw} | {d['n']} | {c['faithful']} | {c['distorted']} | {c['omitted']} | {c['ambiguous_source']} |")
 groups=[]
 for k,cn in [('group_units','原始局部组数'),('mixed_relation','同组混合relation'),('mixed_subject','同组混合subject'),('mixed_logic','同组混合logic'),('mixed_n','同组混合n'),('singleton','原始singleton组'),('has_negative_literal','包含负极性成员'),('has_threshold','包含非空阈值'),('invalid_or_missing_logic','缺失/非法logic')]:
  groups.append(f"| {cn} | {g['old_v2']['counts'].get(k,0)} | {g['free_v2']['counts'].get(k,0)} |")
 errors=[]
 for k,cn in [('population_time_anatomic_causal_or_exception_scope','人群/时间/部位/因果条件/例外范围'),('relation_direction','relation方向'),('target_identity_or_scope','目标身份/亚型/范围'),('predicate_or_argument_identity','谓词或关系参数身份'),('group_effect_membership_or_nesting','组效力/成员/嵌套'),('task_promotion','非诊断内容升级为诊断效力'),('relation_strength_or_epistemic_status','关系强度/认识状态'),('literal_polarity_or_negation_scope','字面极性/否定辖域'),('numeric_value_comparator_unit_or_domain','数值/比较符/单位/数字所属域'),('connective','连词'),('cardinality_domain_or_distinctness','基数/计数域/对象去重'),('score_program','评分程序')]:
  errors.append(f"| {cn} | {e['output']['multi_label_counts'].get(k,0)} |")
 text=f'''# v2规则抽取能力边界：来源先行、双分母与系统归因

日期：2026-09-05。同步基线：`cursor4@9a9b00b5bfb3cb2b477d0ac1b7fda648d2465313`；真实抽取缓存来自其父版本及此前。研究范围是11例机械规则试验实际检索出的v2窗口与历史抽取输出，**不是全部指南库、800例诊断任务或所有LLM的固有上限**。本轮没有重新调用OpenRouter；保留导致历史回归的真实缓存作为测量对象。未改生产抽取器或执行器，未下载LFS大对象。

**结论：此前缺失的分母现已补上。新提示词/v2条件下，完整来源规则的加权忠实率为15.68%，曲解或不完整42.19%，完全遗漏42.13%；输出原子的诊断语义忠实率45%，完整输出组20%。有出处的曲解远比已确认的无源虚构突出。正确数字、正确引文、正确若干成员，都不能保证整组判据正确。**

## 1. 本次怎样补齐上一轮

上一轮主要给出了故障富集案例、27项程序反例、来源解析与病例74追踪，不能由这些反例推出错误比例。本轮新增：

- 从2,736个**去重实际输入窗口**按六来源分层抽64窗口，先通读来源、独立列规则，冻结清单哈希后才揭示旧/新提示词输出。共286源规则：272可裁定、14来源含糊；14个零目标规则窗口也保留。
- 从新提示词/v2的3,826个唯一原始缓存作业建立输出框：32,725个原子单元、562个完整局部组。随机取120原子、60整组，共180单元；组成员不再重复计为原子分母。
- 每条来源规则有中性逻辑、目标、范围、短原文锚点、可表达性、两臂后裔行号、标签与原因证据；每个输出单元都通读完整实际输入，不能只匹配quote。疑似Niemann–Pick C1错绑进一步查到原始XML。
- 24个预先固定输出单元及初判忠实组交叉复审，合并为32个单元；另对软AND和流行病学范围做两项有记录的校准。根审核员复读固定8来源窗口的70条源规则、两臂输出，并额外核对3条源规则中仅因can/may默认模态而判错的5项臂级判断。初判、修改理由和最终覆盖文件全部保留。
- 对四臂唯一缓存做组结构全量普查；从冻结源规则中选8例，给出中性AST、可见叶覆盖及最小反模型，7项内部形式一致性检查通过。形式反模型不冒称患者实验。

审核者是多个AI审阅代理及根审阅者，不是人类临床专家。先冻结来源确实减少了按输出寻找分母的偏差，但已知研究主题；追加忠实组的选择信息也向复审者披露，不能称完全双盲。

抽样与范围细节见[PROTOCOL.md](PROTOCOL.md)、[METHODS_REVIEW.md](METHODS_REVIEW.md)。来源侧每窗口使用按cache ID选定的一个既有focus调用；749/2736窗口有多个focus，样本中为23/64。**其目标是“去重窗口＋既定focus”的完整规则保留率，不能改称按调用频次加权的暴露率或所有focus平均能力。** 输出侧则针对全部唯一缓存作业的已输出单元，两种目标分布也不同。

## 2. 来源侧：指南的规则有多少被真正保留下来

同一完整规则组/评分程序只算一条，不能因为留下1个成员就算整组成功。普通非刚性表现集合允许由一组正确原子共同覆盖；只剩可识别碎片算distorted，不算完全omitted。以下主分母排除14条来源含糊规则：

| 来源规则结果 | 旧提示词/v2样本数 | 旧加权比例 | 新提示词/v2样本数 | 新加权比例 | 新95%窗口聚类区间 |
|---|---:|---:|---:|---:|---|
{chr(10).join(source)}

样本整数是未加权计数；比例按来源层的窗口纳入概率反加权，所以31/272不直接等于15.68%。纳入全部286条时，新臂为忠实{pct(m['source']['new']['weighted_rates']['faithful'])}、曲解{pct(m['source']['new']['weighted_rates']['distorted'])}、遗漏{pct(m['source']['new']['weighted_rates']['omitted'])}、来源含糊{pct(m['source']['new']['weighted_rates']['ambiguous_source'])}。

有任意可识别后裔的加权比例为57.87%，但完整忠实只有15.68%。这正是“抽到内容”与“保住规则”之间的损失。它是完整规则召回，**不是说每个留下的原子只有15.68%正确**。

新提示词相对旧提示词的加权忠实率增加3.07个百分点，配对95%区间为−0.60至+6.60个百分点，不能据此断言总体改善。两臂恰好均遗漏129条，但遗漏的是不同规则、所在来源权重也不同。转移中，7条遗漏变碎片，3条遗漏变忠实；同时10条碎片变完全遗漏、1条忠实变碎片、3条碎片变忠实。曲解类别减少可以伴随内容消失，不能直接当作语义改善。

按结构分解，新臂为：

| 冻结源规则结构 | 可裁定数 | 忠实 | 曲解/不完整 | 遗漏 |
|---|---:|---:|---:|---:|
{chr(10).join(complexity)}

这里24条浅层组、嵌套/域组与评分程序没有一条达到严格完整保留；这个小样本含分类/限定结构，不能称为“24条独立标准化诊断判据的临床金标”，也不能据0次成功推断真实成功率必为0。输出侧仍有完整2-of-3的DLB组等成功例，因此“抽取器完全不会组”也不成立。

按来源保留整数，避免来源差异被总率遮住：

| 来源 | 窗口数 | 源规则总数 | 忠实 | 曲解/不完整 | 遗漏 | 来源含糊 |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(strata)}

在源审阅认为平面schema可以准确表达的194条规则里，新臂仍只有28条完整忠实，加权忠实19.55%。因此**增加AST是必要的结构改进，却不能单独解决注意、选择、实体、方向和成员保留问题**。相反，12条标为impossible、64条标为lossy是审阅者的可表达性评估，不是对任意英语predicate压缩或外部定义解析器的数学上界证明。

## 3. 输出侧：忠实、曲解、非目标和纯幻觉分别是多少

该分母包含抽取器实际发出的完整输出单元，回答“拿到一条输出能否信任”。全体估计按原子/组的输出框比例加权；原子占98.31%，因此总体数值会遮住组的失败，必须同时看两列。

| 输出结果 | 原子样本 | 完整组样本 | 按输出框加权总体 |
|---|---:|---:|---:|
{chr(10).join(outputs)}

原子忠实率45%的Wilson 95%区间为{ci(m['output']['atomic']['wilson_ci95']['faithful'])}；组忠实率20%的区间为{ci(m['output']['grouped']['wilson_ci95']['faithful'])}。12个忠实组中多数是软性表现/病因集合；20%不能误报为“刚性确诊/排除组成功率”。明确的正例包括O1-027保留DLB的完整2-of-3组；O2-001通过同质obligatory模态隐含保留MND的共同必要性，但relation仍有编码不足风险。

本样本**未确认严格无源虚构：0/180**。这里的定义要求不存在任何可识别来源祖先，不是quote没逐字匹配，更不是“原文没支持这个relation”。若所有审核标签准确，以分层Clopper–Pearson上界及Bonferroni合成，输出框加权95%上界约{pct(m['output']['zero_fabrication_bound']['weighted_upper95'])}；这仍不包含AI误判不确定性。**0/180只说明本次没有检出，不能证明没有幻觉。**

同时，有来源祖先的曲解约48.78%，依然足以制造错误否决。把检查指征改成必要条件、把阴性染色改成排除本病，属于曲解；把正确治疗建议保留为treated_by属于忠实非目标，后者不自动算模型犯错，因为原提示词本就允许治疗关系。

## 4. 错误位点：不仅是量词和极性

下表是180个输出样本中的多标签问题计数；同一输出可出现多种错误，不能相加成错误率。原始代码、统一映射与分层加权结果见[error_dimension_metrics.json](error_dimension_metrics.json)及[error_code_crosswalk.json](error_code_crosswalk.json)。

| 错误维度 | 涉及输出单元数 |
|---|---:|
{chr(10).join(errors)}

源侧112条曲解中，22条仅被标记为不完整/作用域丢失，90条还有其他明确语义位点。“仅范围丢失”也可能直接伤害诊断，不能称无害；但它与方向完全反转不应按同一种损伤解释。对所有错误量纲给一个统一均值，会掩盖少量刚性错误的巨大下游效应。

完整分类、首次损坏阶段、原因证据和修复路线见[ERROR_TAXONOMY_AND_CAUSAL_MAP.md](ERROR_TAXONOMY_AND_CAUSAL_MAP.md)。原因与位点是正交的：量词错可能始于缺域、schema无域或模型生成；relation错可能始于prompt不当默认，也可能始于后处理重写。原始缓存可证明错误在生成输出中已存在；首次损坏仍须与实际输入和上游来源对照定位，更不能单凭缓存区分prompt和模型容量的独占贡献。

## 5. 组不是一等公民：准确诊断这个设计问题

`logic=all/any/at_least_n`已有浅层AND/OR及计数，因此“完全没有连词槽”应改成：**没有独立的连接结构、计数域、嵌套表达式和组级效力对象；所有内容依附在原子行上。** 一个同质浅层组尚可隐式表达，但一致性没有被强制。

两v2臂的唯一原始缓存组普查：

| 结构属性（不是语义错误率） | 旧提示词/v2 | 新提示词/v2 |
|---|---:|---:|
{chr(10).join(groups)}

新臂另有6个组的n不在已输出成员数允许范围内、1个组包含非法成员；820条有效断言行（含组成员）使用非法relation枚举、1,571条使用非法context枚举。它们是接口普查，不能直接当作曲解/幻觉比例。负极性成员与阈值本来就是合法规则组成；存在它们提醒执行器必须实际处理，不能因为有负成员就判组错。

成员relation不同不等于应强制所有叶同一极性。正确结构是组持有唯一target/effect/scope，叶保持自己的P或NOT P。`A AND NOT B`可以整体必要或整体充分。多数所谓“更高阶”需求首先是递归布尔式、一阶域量化、事件/角色绑定，无需笼统诉诸二阶逻辑。

执行器的责任同样具体：

- `all`缺一项时仍可有部分正分；代码未必把布尔met置真，但已经把标准退化成相似度奖励。
- `any`的一项为真本来可满足表达式，问题在于是否正确施加组的必要/充分/排除效力。
- 预先原子去重会删去另一组共享成员，随后singleton丢组身份，可能真的回到“单原子代替整组”。
- 成员极性/数值没有进入统一literal求值，`any/at_least_n`没有通用刚性动作，充分组不能整体确认，满足excludes组反而可能得正分。
- F4b把all直接等同疾病必要条件；这不是抽取模型的错误，而是执行器添加了原文没有的箭头。

这些由上一轮[27项程序见证](../POST_V2_RULE_SEMANTICS_AUDIT/engine_audit.md)支持，本轮不把合成反例频率冒充真实发生率。

一次必要的反证检查也被保留：Possible LBD两成员组的原始cache确有`all,n=1`，可令接受这种坏输入的代码单命中置真；但[逐阶段核验](all_n1_normalization_boundary.json)发现规范化及历史保存对象已经清除该n，局部F7探针也未恢复。因此它是被修复的原始字段错误，**不能当作实际病例单项满足整组的证据**。初始推断与撤回见[FINAL_SEMANTIC_REVIEW.md](FINAL_SEMANTIC_REVIEW.md)。

## 6. 八例深描把“为什么错”拆开

详见[GROUP_SEMANTIC_CASEBOOK.md](GROUP_SEMANTIC_CASEBOOK.md)。关键辨别点：

1. **Sarcomatoid UC**：三路OR与n=1原本可平面表达；旧组的不同relation、新组的上皮来源宏词压缩，是效力/成员问题，不能全怪缺少嵌套AST。
2. **轻链限制**：`所有细胞kappa OR 所有细胞lambda`的域是细胞，不是输出行数；“某些kappa AND 某些lambda”会把混合细胞群误读为限制。历史输出保留宏词，未实际发出这个AND；该反模型用于证明修复要求，避免误报观察事实。
3. **供受者病毒状态**：donor/recipient和同一个病毒v必须绑定；两臂完全丢掉这条关系。仅补AND不能恢复共享变量。
4. **Alvarado**：两臂项名8/8、权重0/8。旧把≥7会诊变充分，新变必要，≤3 unlikely都变硬排除；成员召回很高，整个程序仍错。
5. **Catatonia**：数字3保留，12项域却只剩窗口尾部4项；agitation的限定也丢。来源本身不完整，完整源规则仍标含糊，而可见曲解照样可证。
6. **EEG与癫痫**：原文否定“允许用EEG排除”这个推理关系，输出却否定normal EEG这个事实后保留excludes。关系级否定不等于叶级否定。
7. **AFX**：开放式病因/肿瘤排除流程被缩成竞争名称或IHC检查行为；sparse S100又变negative，阴性HMB45变排除本病。测试、结果、过程完成与单独确诊四者被混淆。
8. **炎性心肌病**：清楚的三项AND，两臂都只留myocarditis 1/3。简单可表达组仍失败，说明升级schema不是充分修复。

另一个原始来源溯源例 **O1-011**：真正书章标题是Niemann–Pick Disease，解析器却采用第一条参考文献的C1标题。一般体征列表因此被绑定到C1。通读输入只能先判来源未决，查到原XML后才能归因为标题污染和亚型收窄。正确处理不是把八个体征记成八次无源幻觉。

## 7. 如何解释v2后的MRR下降，哪些尚未被识别

历史11例代理终点四臂MRR依次为旧prompt/旧index 0.4273、新prompt/旧index 0.4132、旧prompt/v2 0.3667、新prompt/v2 0.3071。它们存在错误金标映射、重复候选与临床范围降格，不能称严格诊断准确率；本轮也没有估计旧索引的完整来源忠实率，**不能把上面的新旧prompt/v2比较冒充纯索引效应**。

所谓反常现象并不要求“每增加一条资料都变差”。与观察结果相容、并在病例74局部获得干预支持的一条机制链是：来源恢复更多可抽内容 → 同时产生更多可用碎片与有方向/范围错误的后裔 → gate/绑定/组执行进一步改变效力 → 少量硬否决压倒大量软支持。新增文献覆盖量与判别正确性并非同一个量；这不是全11例已经识别完毕的因果分解。

病例74提供了具体干预证据：[此前定点消融](../POST_V2_RULE_SEMANTICS_AUDIT/case74_targeted_ablation.json)仅删除病例74合并断言列表中索引1017的CPVT错误否决（不是单次cache局部行号），两v2臂的有证据CPVT均回到top1；全局删除excludes/argues_against却另行复活LQTS，使CPVT仅第2。这证明该错误否决对该轨迹具有决定作用，不能被“全局删除后仍错”掩盖。

同时，旧臂top1也借助过错误事实接合；删掉错误否决后的分数仍有错误匹配。因此这不是新方案临床有效性的证明。全11例的MRR降幅究竟有多少由缺组、错组、原子错、源标题、绑定或重复票数分别造成，**本轮没有把高度交互的因素伪装成可相加的独立贡献百分比**。应继续固定规则/病例事实做分阶段交叉重放。

## 8. 对“当前能力边界”的准确表述

可以肯定：这套已运行的模型＋prompt＋平面schema，在被测v2资料上完整规则保留不足；错误并非以完全无来源虚构为主，组与范围保持尤其弱；平面可表达规则也大量遗漏。可支持部分正确浅层组，不能支持不经语义审核的自动刚性诊断程序。

不能肯定：所有LLM的固有极限、全库临床规则比例、对800例的泛化效应、prompt与容量各自占多少、每种错误对总体MRR的独立因果份额。一次历史cache每臂不能测随机稳定性；cache不存精确prompt哈希/provider版本，而且异常可能被缓存成{{}}，遗漏未必全是理解失败。

统计区间只包括抽样误差，不包括AI审阅、规则分段、scope严格性或来源可信度误差。概率源样本来自55文档，输出样本来自133文档；重叠窗口不能当独立医学事实。来源层级分类/弱关联的纳入会影响分母，完整组的碎片仍可能有用。

已保留判断敏感性：不放宽5项can/may→默认typical的模态校准，新臂忠实率为14.17%，而主口径为15.68%；将两条软AND描述按提示词矛盾的“所有患者必须具备”解释，输出组忠实率会由20%降到16.67%。这说明需要先冻结明确语义契约，也说明主要低保留/组失真结论不依赖某一个边界判断。

## 9. 下一步修复顺序与可证伪实验

首先实现一等Rule对象：`target、use、scope、condition_AST、effect、provenance、completeness`。叶保存局部正负、阈值、实体/事件；组保存AND/OR/NOT与计数域；评分保存有符号权重和结果类型。未知、源不完整、条件不适用须显式区分。编译器拒绝冲突/缺域，不能把缺n猜成any；去重只合并语义相同对象，保留全部组引用。

随后用冻结来源做 `原prompt/明确方向prompt × 现平面schema/一等组schema` 2×2，每格同模型/provider/预算并重复；span-only复制为额外定位基线。主终点为完整来源忠实召回、整组输出精确率、严格无源率、无效契约率；成员覆盖只作次级指标。至少分别覆盖本轮8种结构，病例74只作开发反例。

最后固定原文参照规则、固定病例事实，交叉替换抽取、编译、绑定、执行器；分别检查必要/充分/排除、unknown传播、共享成员、复制不变性、角色/时间一致性和评分程序。只有这些门槛通过后，再在新病例做端到端MRR和clinical-complete准确率实验。不能通过统一降低规则刚性来掩盖语义错误，也不能因为分数改善就倒推抽取忠实。

## 10. 复查与复算入口

- [census_metrics.json](census_metrics.json)：全部分母、权重、区间、分层、结构与配对转移。
- [source_rule_results.json](source_rule_results.json)：572条旧/新最终来源判定；[output_unit_results.json](output_unit_results.json)：180输出最终判定。
- `source_inventory_*.frozen.json`与[inventory_freeze_manifest.json](inventory_freeze_manifest.json)：输出揭示前的来源清单及冻结顺序，含一次提前冻结被明确撤回、在未读输出前重新冻结的记录。
- `source_matches_*.json`、`output_adjudication_*.json`为初判；`*_review_overrides.json`与cross-review文件保留复审修改，不覆盖初判。
- [raw_group_ledger.jsonl](raw_group_ledger.jsonl)：四臂全部原始局部组及结构标志；[group_semantic_panel.json](group_semantic_panel.json)：8例完整逻辑与反模型。
- [SAMPLING_IMPLEMENTATION_CORRECTION.md](SAMPLING_IMPLEMENTATION_CORRECTION.md)：修正建组前丢不合法成员的问题，180样本及哈希均未变化。

运行 `python aggregate_census.py`、`python summarize_error_dimensions.py`、`python structural_census.py`、`python check_group_semantic_countermodels.py`、`python build_report.py`、`python validate_census.py` 可复算汇总与核验。手工式语义判断保存在JSON，重跑汇总不等于重新获得独立临床审阅。
'''
 (P/'REPORT.md').write_text(text)
if __name__=='__main__':main()
