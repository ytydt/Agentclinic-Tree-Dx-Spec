import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'analysis/mechanism_v2/results/RULE_EXTRACTION_EXECUTION_REDESIGN'
BASE = 'analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/'
files = {
 'extract': BASE+'run_trial_extraction.py', 'gate': BASE+'gate_assertions.py',
 'engine': BASE+'run_mechanical_engine.py', 'nli': BASE+'nli_verify_assertions.py',
 'nl': BASE+'extract_nl_rules.py', 'tasks': BASE+'build_trial_tasks.py',
 'retrieval': BASE+'run_trial_retrieval.py', 'retriever': BASE+'trial_retriever.py',
 'score': BASE+'score_2x2_engine.py', 'source': 'scripts/build_statpearls_corpus.py',
}
refs = {
 'A1': {'title':'前次语义审计：程序与schema见证','path':'../POST_V2_RULE_SEMANTICS_AUDIT/engine_audit.md'},
 'A1S': {'title':'前次来源解析审计','path':'../POST_V2_RULE_SEMANTICS_AUDIT/source_and_provenance_audit.md'},
 'A2': {'title':'前次能力边界：来源先行与输出双分母','path':'../V2_RULE_EXTRACTION_CAPABILITY_CENSUS/REPORT.md'},
 'A2E': {'title':'前次错误位点与原因正交分类','path':'../V2_RULE_EXTRACTION_CAPABILITY_CENSUS/ERROR_TAXONOMY_AND_CAUSAL_MAP.md'},
 'T1': {'title':'本次差量审计','path':'../V2_INDEX_DIFFERENTIAL_AUDIT/REPORT.md'},
 'T1P': {'title':'本次来源窗口差量账本','path':'../V2_INDEX_DIFFERENTIAL_AUDIT/source_exposure_ledger.jsonl'},
 'T1M': {'title':'本次终点与排名账本','path':'../V2_INDEX_DIFFERENTIAL_AUDIT/endpoint_and_rank_accounting.json'},
}
for c in ['74','522','773','49','56','91','119','179','257','475','326']:
 refs['C'+c]={'title':'本次病例'+c,'path':'../V2_INDEX_DIFFERENTIAL_AUDIT/cases/case_'+c+'.md'}
LIT=ROOT/'analysis/mechanism_v2/results/FAITHFUL_RULE_EXTRACTION_LITERATURE_REVIEW'
studies={}
for fn in ['modern_fol_sources.json','semantic_parsing_sources.json','clinical_llm_sources.json','clinical_standards_sources.json']:
 d=json.loads((LIT/fn).read_text())
 arr=d if isinstance(d,list) else d['sources']
 for s in arr:studies[s['id']]={'title':s['title'],'url':s['url'],'review_ledger':'../FAITHFUL_RULE_EXTRACTION_LITERATURE_REVIEW/'+fn}

rows=[]
def add(id, stage, title, loci, defect, evidence, literature, minimum_fix, structural_redesign, compatibility, acceptance, residual, dependencies=(), evidence_status='code_and_audit'):
 rows.append(dict(id=id,stage=stage,title=title,code_locations=[{'file':files[f],'line':line,'function_or_block':func} for f,line,func in loci],defect=defect,evidence=evidence,literature=literature,minimum_fix=minimum_fix,structural_redesign=structural_redesign,compatibility=compatibility,acceptance=acceptance,residual_risk=residual,depends_on=list(dependencies),evidence_status=evidence_status,implementation_status='proposal_not_implemented'))

add('M01','S0','运行配置与实际来源绑定', [('gate',319,'_load_passage_index'),('gate',352,'resolve_passage'),('score',95,'main:四臂循环'),('extract',697,'main:输出出处')],
 'F7全局可变索引默认加载旧检索文件，标题/章节回退可以取到另一窗口；非grounded输出没有passage hash。仅换v2索引名不保证审核看到v2实际输入。',
 [{'ref':'A1','detail':'§6.4明确default与arm-only来源之别；不能推定历史环境变量。'},{'ref':'T1P','detail':'四臂job/cache/hash证据；本次冻结default-stale必须保留为历史基线。'}],
 [{'id':'CS02','borrow':'将证据材料、版本与可执行资产链接为明确依赖。','limit':'标准化出处不证明段落包含完整规则。'}],
 '将SourceResolver作为run_case显式参数；由该臂job manifest按完整内容hash构建。缺hash或歧义时记unresolved，不按标题回填；保存实际许可source_ref。',
 '不可变RunManifest封存source版本、窗口、raw response、编译器、事实字典、绑定与评分策略。每步产物引用父hash；历史default-stale只可通过显式legacy replay profile运行。',
 '新旧来源配置不可共用一个无版本_PASSAGE_INDEX。逐臂修复会有真实输出差异，不能为了复现旧分数恢复静默fallback。',
 ['同标题/章节但不同正文窗口只能解析指定hash。','四臂顺序反转不改变各臂产物hash；缺窗口返回source_unresolved。','逐动作可回到实际输入，不能仅回到数据库当前同gid。'],
 '来源hash身份正确仍可能缺脚注、跨页成员或源文自身含糊。')

add('M02','S1','保留源布局和诊断完整单元', [('source',77,'render_list'),('source',101,'render_table'),('source',121,'parse_article')],
 'render_list只递归list-item直接子list；p包裹的嵌套list被压平。parse_article首个article-title可能来自参考文献。表格丢空格单元、rowspan/colspan及脚注依赖；这些后者是静态风险，不是全库已量化损失。',
 [{'ref':'A1S','detail':'Memantine/NXML嵌套与标题见证；本次无需重扫LFS原库。'},{'ref':'A2','detail':'已有可见叶子不等于完整表达式保留。'}],
 [{'id':'CL02','borrow':'把树结构与节点抽取作为不同验收对象。','limit':'完整树精确率不能由原子F1代替。'},{'id':'CS02','borrow':'文本证据到领域逻辑再到可执行逻辑的分层资产。','limit':'不能自行补原文未明确的连接关系。'}],
 '递归读取全部容器并保留原XML路径/列表层级；从正文前置信息选择标题；表格保存单元格坐标及跨格信息，不先删除空格单元。',
 'SourceBlock图保留标题、引导句、列表、表头、脚注、例外、版本及precedence。诊断单元标complete/partial/ambiguous及缺失依赖，不以字符长度宣布完整。',
 '保留v1/v2不可变产物；新解析版本需新source_manifest及索引，不能原地改变旧gid含义。',
 ['现有嵌套XML见证恢复父子边；正文标题不读取参考文献。','表头—单元格—脚注的重建快照可与原源对齐。','连接词未明确的来源保持ambiguous，不自动补AND。'],
 'OCR/PDF不可恢复内容、跨文档定义及指南冲突仍需独立来源审阅。',('M01',))

add('M03','S1','检索窗口作为结构闭包而非邻块串接', [('retriever',92,'TrialRetriever.passage'),('retrieval',130,'main:per-candidate passage selection'),('extract',655,'main:passage[:max_passage_chars]')],
 '±1同文档窗口不保证规则域闭合；6000字符截断可再次切断已修复列表。focus相同与窗口相同不是同一干预，内容相同但focus变化仍可能改变LLM输出。',
 [{'ref':'C773','detail':'旧PH误否决出处在v2仍有同核心句，但只在TR focus较大窗口曝光。'},{'ref':'C522','detail':'恢复12项后仍可能与Walter分类邻文混域。'},{'ref':'T1P','detail':'保存source hash及counterpart_refs，禁止以gid相等代表新旧同源。'}],
 [{'id':'SP02','borrow':'保留逻辑依赖与尚未解定的范围。','limit':'范围表示不自动解决检索缺失。'},{'id':'CL02','borrow':'围绕完整结构而非孤立句建抽取单位。','limit':'不保证任意长指南一次抽取可行。'}],
 '截断前检测列表/表/脚注边界，分块时重复必要引导且记录成员全集引用；未闭合单元不得直接发布刚性规则。',
 '先按SourceBlock依赖闭包取证，再向抽取器传source-only诊断单元；focus只是调度元数据。另保留focus-conditioned候选提示臂，用相同曝光和预算检验其价值。',
 '不能声称改变窗口后的准确率差是prompt效应；成本按全部读取tokens、补块请求及重试记账。',
 ['长列表被截断时完整性状态为partial；补块后成员引用无重复。','同内容多focus出现只产生同源支持，不复制独立诊断票。','对比采用冻结曝光与自由检索两套端点，分别解释抽取/检索。'],
 '上下文更长可能引入近邻噪声；结构闭包仍需预算与新来源覆盖实验。',('M02',))

add('M04','S2','完整规则及递归表达式成为抽取对象', [('extract',47,'GUIDELINE_PROMPT'),('extract',100,'FREE_GROUP_BLOCK'),('extract',159,'GUIDELINE_PROMPT_GROUNDED'),('nl',38,'NL_RULE_PROMPT')],
 '当前logic已有浅层all/any/count，但无独立组级目标、效力、量词域和递归结构。逐成员relation无法唯一确定根规则；NL句子复制臂也禁止拼接跨句，不能成为通用组恢复方案。',
 [{'ref':'A2','detail':'原平面schema可表达的194条源规则中仍仅28条新臂忠实，AST必要但不足。'},{'ref':'C74','detail':'替代路径、年龄范围和评分程序相互压平。'},{'ref':'C522','detail':'DSM症状域与Walter分类域混合。'}],
 [{'id':'MF05_CLOVER','borrow':'先识别原子和组合依赖，再组合完整公式并验证。','limit':'模型自己生成的分解不是可信金标。'},{'id':'SP02','borrow':'变量/handle/限制域和歧义保存。','limit':'不必全量迁移MRS实现。'},{'id':'CL01','borrow':'根规则聚合后执行动作及人工树审核。','limit':'其字符串条件列表禁止嵌套，不能当递归抽取解法。'}],
 '新schema至少增加Rule对象、expr节点和rule_effect；叶子不再承载继承自根的relation。旧组无法唯一迁移时留legacy_unresolved，禁自动默认为any或necessary。',
 '分两步抽取source inventory/中性受控释义，再生成带多span锚点的AST/DAG；and/or/not、有限exists/forall、count_distinct、comparison、time、exception分别有语义。CNF/DNF仅为编译视图。',
 '可无损迁移的独立原子和浅层同质组可做adapter；历史混合relation组须逐源重新裁定，不靠多数标签还原根。',
 ['A∧(B∨C)、(A∧B)∨(C∧D)、major/minor计数和共享叶均能无损表示。','每个根有目标、动作方向、范围、完整性和出处；未声明变量/域编译失败。','源清单的faithful/distorted/omitted与输出strict hallucination继续用不同分母。'],
 '逻辑合法不证明源忠实；自然语言谓词可能把未解析复合条件藏在字符串中。',('M03',))

add('M05','S2','决策种类、箭头方向与知识背景分离', [('extract',36,'RELATIONS'),('extract',147,'CONVERSE_ADDENDUM'),('engine',161,'RELATION_ALIASES'),('engine',176,'clamp_relation')],
 'risk_factor_for→caused_by、未知relation→feature_of是语义升级；测试/治疗/预后混入诊断标签。CONVERSE_ADDENDUM鼓励额外反向条件，不等于原句许可的逆否，更不总是源文抽取。',
 [{'ref':'C522','detail':'B12检查菜单变缺乏特征，PAD/CAD风险改因果并重复加分。'},{'ref':'C773','detail':'PFO检测非指征→PFO排除；PH检查流程→疾病反证。'},{'ref':'A2E','detail':'首次损坏阶段与relation错误位点分开。'}],
 [{'id':'CS03','borrow':'诊断决策、查询与行动分属不同任务语义。','limit':'不能用一个统一required标签代表所有任务。'},{'id':'MF06_LOGIC_LM_PP','borrow':'修复回到源文并允许回退。','limit':'自反思没有独立语义保证。'}],
 '仅枚举拼写别名可归一；risk、cause、test_recommendation、treatment、classification、diagnostic_effect单列。停用未明示反向规则的自动抽取；若保留推演，放独立derived知识通道。',
 '中间表示保存if-condition、作用对象、necessary/sufficient/exclusion/equivalent/support/against及source授权；显式双向定义可有两个合法方向。背景知识使用独立出处、推导权限和禁用于“源文忠实”得分。',
 '旧treated_by等行可继续供工作流展示，但不能默认进入诊断soft池；不认识的relation保留invalid而非feature。',
 ['同一E在D→E、E→D、E→¬D下给不同动作；缺E不反驳充分路径。','may test、risk、signed negative points均不自动生成硬排除。','派生反向命题不计入源规则忠实产出，必须有单独推导记录。'],
 '“diagnosis requires”可能指检测过程也可能指结果条件，需要独立范围裁定。',('M04',))

add('M06','S3','归一化只改语法，不猜缺失语义', [('extract',335,'normalise_group'),('gate',773,'_merge_and_or_required'),('gate',580,'_g1_drop_dual_patho')],
 'at_least_n缺n变any；and/or触发整组flat any；同句necessary和pathognomonic被禁止并存。Python hash构造gid不稳定。均可破坏原本合法或未决的逻辑。',
 [{'ref':'A1','detail':'E19缺n、E22双向定义、E25嵌套AND/OR反例。'},{'ref':'A2','detail':'能力边界保留raw与normalization，避免把程序改坏算模型错误。'}],
 [{'id':'SP05','borrow':'用结构约束拒绝非法生成而非随意补语义。','limit':'语法合法仍可能逻辑错误。'},{'id':'SP07','borrow':'类型与作用域约束的可完成性检查。','limit':'同类型错误条件仍会通过。'}],
 '仅null/大小写/确定枚举别名做无损归一；n缺失、组逻辑冲突进入unresolved。删除自动flat any和双槽互斥的语义判定，输出诊断而不覆盖raw。',
 '不可变raw→NormalizationResult→CompiledRule；每条rewrite列before/after、语义保持依据和源span；需选择解释的操作归为repair proposal待独立审核。',
 '不能将invalid成员静默删掉后评估剩余组；原组在编译前仍保留全部成员与错误。',
 ['归一化幂等、raw不可变；n缺失不变成n=1。','明示双向定义能保留双向；A∧(B∨C)不能变any(A,B,C)。','不同进程PYTHONHASHSEED下产物ID一致。'],
 '允许的拼写映射须版本化；来源含糊不会因schema校验而消失。',('M04','M05'))

add('M07','S3','数值、阈值所属指标与评分权重分离', [('gate',382,'parse_threshold_from_quote'),('extract',422,'postprocess_grounded:threshold'),('gate',614,'gate_one:E14'),('gate',529,'_reference_range_recode')],
 '整quote首个数值可能被赋给另一predicate；E14只查数字出现不查对象/上界/单位。G2由正常参考范围造疾病必需异常且严格补集边界不对。',
 [{'ref':'A1','detail':'E20数字/贪婪regex/量词抢阈值，E21参考范围升级。'},{'ref':'C74','detail':'QT正常参考范围造LQTS必要性；表内点数和QT范围混槽。'},{'ref':'C773','detail':'mPAP/PASP/wedge/比例/直径均非同一临床指标。'}],
 [{'id':'CS01','borrow':'带类型、单位、区间与关系运算的表达式。','limit':'CQL不能认定某数字属于哪个原文对象。'},{'id':'SP07','borrow':'量纲和返回类型约束。','limit':'同单位不同指标仍需身份审核。'}],
 '数字parser返回带span和measurement anchor的全部候选；禁止整quote首值覆盖；删除G2自动必要性；区分criterion_count/score_weight/threshold/age/ratio。',
 'Comparison节点引用两端typed term、单位、区间开闭、时间/方法；数值文字与关系词各有span。缺任一必需论元或指标身份时编译unresolved，不补默认数值。',
 '已缓存旧threshold不可静默标为verified；可解析单位别名但不猜检验方法、年龄或参考区间。',
 ['同quote两个指标分别取自己的阈值；count=2不遮盖后续≥10。','<10的逻辑补集为≥10，但参考范围本身不能造疾病必要性。','边界、单位换算、无单位、PASP≠mPAP、比值分母缺失分别有预期结果。'],
 '临床阈值随人群/测量法变化，类型相同仍可能范围错配。',('M04','M05'))

add('M08','S3','取消自动硬升级与诊断降权式洗白', [('gate',599,'gate_one'),('gate',736,'gate_one:G2/G3'),('gate',436,'_demote'),('gate',292,'evidence_span'),('gate',498,'_sufficiency_scope')],
 '邻域diagnosed/pathognomonic可授权错误主语；G3由充分路径的合取肢造普遍必要条件。程序“不支持硬规则”后降为feature，仍可进入计分甚至claimants。',
 [{'ref':'A1','detail':'E23未对齐引文、E26邻句许可、G3强制升级。'},{'ref':'C119','detail':'“once thought pathognomonic”及后续反例不能靠词cue保留绝对充分。'},{'ref':'C522','detail':'B12菜单作为软证据仍有大贡献。'}],
 [{'id':'MF05_CLOVER','borrow':'针对候选解释构造区分反模型。','limit':'选择哪个解释忠实仍需独立原文审阅。'},{'id':'SP08','borrow':'用独立规格约束修复循环。','limit':'模型自产规格与测试会自洽误读。'}],
 'gate改为validate/admit/quarantine，不重写根效力；quote未对齐、对象不符、非诊断任务不得通过改feature复活。合法soft证据须有独立source warrant。',
 '每个根规则按成员、连接、量词、极性、作用域、方向、完整性逐项给裁定；source支持、编译合法与执行权限三种状态分开。反模型覆盖必要/充分混淆及例外。',
 '旧_gate标签只作历史证据；“降级”不等于低风险准入。不得一律禁刚性：全部合同通过的规则保留原效力。',
 ['修改为quarantine后不产生直接票、claimants或L4。','典型feature借邻病diagnosed词仍不能升级。','合法排除/充分/双向定义各有正例，防只会拒绝的过滤器。'],
 '严格准入可能降低覆盖；必须同时报告忠实召回与误准入，不能只报告通过率。',('M05','M06','M07'))

add('M09','S3','验证器审完整语义，不以NLI标签充当证明', [('nli',65,'verbalize'),('nli',135,'nli_check_one'),('nli',158,'nli_filter_assertions')],
 '可选F8将negated改写为not(relation(P,D))，不等于relation(not P,D)；只看quote及单原子，忽略阈值/组/范围。neutral后feature化、模型不可用skip后原样放行。',
 [{'ref':'A1','detail':'F8不能补schema及执行合同；本项否定位置细节来自本次静态读码。'},{'ref':'T1','detail':'冻结四臂不能用未开启F8的缺陷解释历史下降。'}],
 [{'id':'MF05_CLOVER','borrow':'组合后反解释与源文对照。','limit':'不是对任意临床文本零错认证。'},{'id':'MF08_FOVER','borrow':'同一理论多查询，而非一条最终结论。','limit':'全查询通过仍非源级完整忠实率。'}],
 'F8输出只作风险信号，区分not_run、neutral、contradiction；不经其标签直接加硬权或feature化。若继续NLI，verbalize完整根表达式并保存生成句。',
 '结构校验+带源span的语义复述+独立参照/反模型面板；solver只能证明与参照在指定符号/背景理论下的等价。timeout返回unknown，记录修对、修坏、未改。',
 'F8旧缓存不可复用作新合同的“已验证”；未运行验证的历史条目保持legacy_unknown。',
 ['¬P→¬D与¬(P→¬D)必须生成不同验证对象及缓存键。','同原子不同量词/阈值/方向可被面板区分。','验证器缺席不制造verified状态；合法硬规则通过独立正例。'],
 '共用模型、符号映射和自建测试存在相关偏误；需要独立审阅和新源样本。',('M04','M08'), 'static_optional_path_not_frozen_causal_evidence')

add('M10','S4','全局ConceptRegistry与双向别名约束', [('tasks',121,'main.slot_for'),('tasks',139,'main:alias union'),('engine',39,'norm'),('engine',359,'run_case:subject binding')],
 '候选按原label字符串保留，大小写重复成为空实体；任意上游alias被接受，norm删除全部括号可丢部位/亚型。排序结果可由零证据副本提供代理成功。',
 [{'ref':'C74','detail':'真实active CPVT两v2均第10，空副本第4；不能重复13。'},{'ref':'C91','detail':'Hemangioma持有Angiosarcoma错误alias；CD31/PECAM-1又是应保留的真正别名。'},{'ref':'T1M','detail':'完整诊断、组件、父类和错误alias分开。'}],
 [{'id':'MF10_SOLT_MENTAL','borrow':'跨句维持概念—符号环境。','limit':'不能只奖励同义合并而不惩罚错误合并。'},{'id':'CS06','borrow':'等价、子类和不同概念关系显式区分。','limit':'开放世界与本地诊断动作语义不同。'}],
 '先合并安全格式等价候选并保留all_labels/methods；别名白名单须有依据与类型/解剖/病因/良恶性兼容检查，source→alias和alias→candidate两端均校验，不能任一方向containment即同义。',
 'Concept ID与label/alias/父子关系分离；等价双向，is_a方向单独保存。多义alias需上下文消歧，跨不兼容概念的等价连通分量拒绝合并。事实marker和疾病各用不同命名空间。',
 '不从gold生成运行时别名；括号内容先解析成限定再决定是否可忽略；历史label列表保留用于复算，主排序每concept一次。',
 ['CPVT大小写复制和候选顺序变化不改变概念排名。','CD31↔PECAM-1双向可达，Angiosarcoma↔Hemangioma被拒；两者测试同时通过。','父/子概念不合并；新增误alias不能污染等价类。'],
 '白名单召回不足会漏桥接，多义术语或粒度争议需unresolved；不可用指标改善倒推别名正确。',('M01','M05'))

add('M11','S4','主体全局精确优先及显式继承', [('engine',235,'concept_match'),('engine',258,'subject_match'),('engine',363,'run_case:first successful candidate loop')],
 '首个containment可抢走后面exact主体；疾病、算法、器官亚型共享词也能被接合。一般父类特征可以相关，但不等于兄弟病特异规则可移植。',
 [{'ref':'C773','detail':'CTEPH的417行仅6条同名；不能把其余411全部医学判错，其中IPAH特异行抢占是更实质错误。'},{'ref':'C522','detail':'DLB主体被Chronic ischemic encephalopathy吸走。'},{'ref':'C56','detail':'父类Carcinoma顺序抢占亚型证据。'}],
 [{'id':'SP05','borrow':'符号表和引用解析的上下文约束。','limit':'exact名称仍可能多义。'},{'id':'CS06','borrow':'把等价和层级继承分开表示。','limit':'子类关系不自动授权每一种诊断动作。'}],
 '所有候选先查canonical ID/exact/verified alias，再考虑父类；禁列表顺序first-hit。保留unbound/ambiguous，不将无exact自动交给最近父类。',
 'Rule.target直接引用concept；父类事实与亚型规则按逻辑方向、适用范围显式继承并生成派生proof。Dchild→Dparent不允许从parent特征反推某个child，必要/充分继承不能一律同向处理。',
 '父类general PH证据可在明确策略下共享，但不能为CTEPH提供IPAH特异证据；疾病算法同名如Brugada algorithm与syndrome分型。',
 ['Infection列前也不能抢走Bacterial infection exact主体。','交换候选顺序，绑定目标和proof不变。','IPAH exact候选存在时其专属原规则不直接绑定CTEPH；可继承父类例有单独正例。'],
 'exact-before-parent本身不修错误候选池、源主体误抽或parent/child定义错误。',('M10',))

add('M12','S4','去重保留规则出现、共享叶与所有出处', [('engine',380,'run_case:assertion-level dedupe')],
 '去重key仅predicate/relation/polarity，忽略阈值、scope、comparator、组和来源；保留首行却取后行最大modality，产生混合规则。共享叶被删除后组可降singleton并作为独立充分原子。',
 [{'ref':'A1','detail':'E07阈值顺序反转；E08共享A在第二充分组被删除后C单独确认。'},{'ref':'C522','detail':'mutism被更早akinetic组夺走；DSM/Walter组成员改变。'},{'ref':'C74','detail':'同事实重复票与本来无歧义的不同源规则须区分。'}],
 [{'id':'SP02','borrow':'共享子式引用不等于删除节点归属。','limit':'形式共享不代表证据独立。'},{'id':'MF05_CLOVER','borrow':'在完整组合关系中维护原子身份。','limit':'语义等价去重需可信谓词映射。'}],
 '先建立raw occurrence及membership，再去重表达式存储；完整命题相同才共享leaf语义对象，所有member edges和source支持仍保留。不做跨记录最大modality覆盖。',
 '分开occurrence_id、criterion_id、semantic_leaf_id、rule_id和provenance_support_id。等价重复规则只一次动作/票，但冲突阈值或版本保留为不同规则并标conflict。',
 '不能以加入sourcehash到旧key作为最终解法：那会保成员却重新放大来源副本票。存储去重与证据聚合必须分层。',
 ['(A∧B)→D与(A∧C)→D共享A后仍各有两条member edges。','≥3与≥10规则顺序不改变真值；不合并成来源甲+强度乙。','复制完全相同来源/窗口不加分、不增加确认数，完整出处可追溯。'],
 '同义叶等价及独立来源识别仍需字典或审阅；同事实能满足多个不同criterion必须显式裁定。',('M04','M10'))

add('M13','S4','组ID命名空间、一致性及singleton身份', [('engine',433,'run_case:groups construction'),('engine',440,'group key'),('engine',444,'singleton removal'),('engine',461,'group first-member fields'),('gate',798,'Python hash group_id')],
 'passage-local g1被按标题/章节/focus/subject合并，不含完整source/版本/正文；读取首成员logic/n。singleton丢组身份，可能回原子动作。',
 [{'ref':'A1','detail':'E09跨窗口g1、E10首行n改变；真实新臂有跨cache与不一致组。'},{'ref':'C522','detail':'DSM与Walter同名g1合并，不能称忠实3-of-12。'}],
 [{'id':'SP02','borrow':'稳定子式handle及范围引用。','limit':'hash相同只是身份，不证明语义。'},{'id':'CS02','borrow':'可执行资产与源版本依赖。','limit':'尚需项目定义规则occurrence粒度。'}],
 'group instance ID由source版本+完整输入hash+extraction artifact ID+local root ID构造，focus/run来源单独保留；不以标题或Python hash命名。根logic/n只能存在一处，成员不得各写一份决定执行。',
 '持久RuleOccurrence连接SourceBlock和根expr；跨窗口同规则需显式equivalence/continuation证据后合并，而非恰好同gid。singleton保留根和效果，缺成员标incomplete。',
 '旧局部g1不能跨cache恢复为同根；已丢的membership必须回raw和原文，不能由当前dedup结果猜。',
 ['同名g1来自两个cache不合并；有证据的跨块连续规则才合并。','组内矛盾n/logic编译拒绝，不随顺序变化。','singleton不自动获得独立刚性效力，完整一叶规则仍可合法执行。'],
 '窗口hash变化可能生成多个同源occurrence，需M12及M20防重复票。',('M01','M04','M12'))

add('M14','S5','病例事实读取完整值、事件和角色', [('extract',215,'CASE_PROMPT'),('extract',471,'backfill_findings'),('extract',628,'main.do_case'),('engine',350,'run_case:findings loading')],
 'schema虽有value/qualifiers，执行join忽略多数限定；缺乏标本、方法、经验主体、前后事件、干预与观测状态。regex已覆盖label会阻止补齐数值，并按出现次序猜timepoint。',
 [{'ref':'C74','detail':'noisy shop诱发情境漏入事实；既往无骤停与当前VF易混。'},{'ref':'C522','detail':'B12=1154.67 pmol/L不能只记“有B12检查”。'},{'ref':'C49','detail':'血液与组织嗜酸粒细胞不是同一观测。'},{'ref':'C179','detail':'基础病与本次诊断目标、SaO2/platelet时点要分开。'}],
 [{'id':'CS01','borrow':'typed Retrieve、事件及Quantity/Interval。','limit':'结构化读入不保证病例抽取无误。'},{'id':'CS04','borrow':'时间状态和任务目标。','limit':'Asbru全架构不必照搬。'},{'id':'CL06','borrow':'纵向事件和临床关系保留。','limit':'关系图可能仍将缺测误当阴性。'}],
 '对每个finding核验quote跨度，value、unit、specimen、method、site、timing、experiencer、status独立存；已有label但缺value可补齐并记录，不靠label关键词判全部已覆盖。',
 'Observation/Event/Situation图保存measure_performed与result、historical/current、before/after intervention。正常是观测结果或属性，不是统一absence；not_assessed与not_reported保持unknown。',
 '只从vignette补事实，不读gold/options；case特定regex保留为legacy并与通用typed抽取对照，不能把11例定制覆盖当泛化能力。',
 ['B12测试已做而高值不满足低值；当前VF不被既往无骤停覆盖。','血/组织、患者/亲属、休息/运动后、药前/药后同名数据不合并。','paired事件必须有真实关系，不按两个独立列表相同序号默配。'],
 '病例隐含信息、时间歧义和测量不完整仍需unknown；不能补成有利金标事实。',('M01','M07'))

add('M15','S5','Typed join及多见证消歧', [('engine',30,'GENERIC'),('engine',273,'predicate_match'),('engine',294,'_anchored'),('engine',399,'run_case:best finding selection')],
 'normal/abnormal、high/low、without等被剥离；同等级取首finding；marker或embedding可覆盖指标/解剖/角色/方法错误。只比较短noun phrase不能决定患者满足何条件。',
 [{'ref':'C773','detail':'RA size→PFO size、PASP→mPAP、chest pain→joint pain。'},{'ref':'C74','detail':'VF→Holter burden、ROSC aftershock→spontaneous termination。'},{'ref':'C91','detail':'已抽取Kaposi PECAM-1未接患者CD31，不能误报源未曝光。'},{'ref':'C522','detail':'echolalia/echopraxia共接同fact。'}],
 [{'id':'SP07','borrow':'类型环境限制可接受接合。','limit':'同类型近邻仍有语义歧义。'},{'id':'MF09_FINE_TUNED_FOL','borrow':'把谓词身份识别单独评估。','limit':'给定金标谓词的成绩不是自动符号桥接能力。'}],
 '匹配先判concept、对象、方法、标本、时点和方向兼容，再匹配字词/verified alias；embedding仅召回候选pair。多个适用观测不首个胜出，保留witness集合或ambiguous。',
 'Binder输出BindingProof：原子论元→具体观测/事件ID、类型检查、别名依据、scope检查、值读取及失败原因。引入typed relation匹配而非把复合关系压进predicate字符串。',
 '旧高召回pair可保留为candidate_binding但不能计分；临床等价的marker仍需正例，不能用禁embedding作为完整修法。',
 ['正常ECG可满足normal ECG且不满足abnormal ECG；换finding顺序不变。','Holter负荷需计数分母/监测事件，VF存在不能替代；同单位错指标被拒。','CD31/PECAM-1接合成功同时保持Kaposi主体，不将该规则迁给Angiosarcoma。'],
 'typed schema有限、数据缺测与术语多义会降低join召回；须测错绑与漏绑双方。',('M10','M11','M14'))

add('M16','S6','统一literal真值与数值关系解释', [('engine',316,'threshold_ok'),('engine',466,'group sat/vio'),('engine',532,'required threshold'),('engine',559,'confirmation threshold'),('engine',581,'soft delta')],
 '同一literal在group/hard/soft用不同判定；unknown比较被允许确认，阈值失败仍可获半正分，normal固定读作false，relational字段不执行。',
 [{'ref':'A1','detail':'E01/E02/E13/E14及关系阈值反例。'},{'ref':'C522','detail':'低B12不满足却获正分。'},{'ref':'C74','detail':'QT380可给多个高QT区间票；normal physical exam被扣分。'}],
 [{'id':'CS01','borrow':'类型化比较和三值逻辑。','limit':'AllTrue忽略null的集合语义不可直接照搬本合同。'},{'id':'CS06','borrow':'不把未观测自动闭世界化。','limit':'OWL推理与诊断动作仍分层。'}],
 '单一eval_literal返回true/false/unknown/conflict及proof；所有消费者只读该结果。阈值是完整条件，比较不适用或缺单位不以presence补正票。',
 '带适用性状态的多值解释器执行定性not、Quantity/Interval、双测量关系与事件约束；明确normal对象的属性。缺值/冲突不靠bool/0转换。',
 '统一解释会改变旧softscore数值，不能为追旧MRR保留“失败仍半分”。合法模糊支持须另有source模型，不从硬阈值失败自动产生。',
 ['同literal在组、硬动作、soft准入返回一致真值。','单位冲突unknown不确认；A=1不满足A≥10；正常结果满足normal谓词。','关系A≥B要求两个兼容观测及同scope；缺B时unknown。'],
 '多值逻辑选择及冲突策略须与上层合同冻结；浮点、公差和定性范围需临床依据。',('M07','M14','M15'))

add('M17','S6','递归组求值与distinct计数', [('engine',461,'run_case:criterion group loop'),('engine',478,'GROUP_ALL_IS_REQUIRED'),('engine',488,'all/any/at_least_n')],
 '组按present行数判sat，忽略signed literal及阈值；all被赋必要性；any/k仅打分。多个同义行接同fact可重复满足k，成员数不等于原文规定域大小。',
 [{'ref':'A1','detail':'E03/E04/E05/E06/E17/E18组动作和同fact计数反例。'},{'ref':'C522','detail':'恢复≥3却仍以同患者echopraxia满足两个症状类别。'},{'ref':'A2','detail':'8个源级结构反模型提供回归种子。'}],
 [{'id':'MF05_CLOVER','borrow':'按逻辑依赖组合原子而非行池求和。','limit':'组根动作要另存。'},{'id':'CL01','borrow':'完整成员汇总后再执行一次动作。','limit':'不采用其无unknown二元判读。'},{'id':'CS01','borrow':'集合、计数和谓词运算。','limit':'须另定义空域/未知/去重单位。'}],
 '停用all⇒necessary；按根expr递归调用eval_literal。有限k-of-n按criterion类别及有效witness计数；未决成员给上下界：T≥k真，T+U<k假，否则unknown，conflict另列。',
 '根expr支持not/and/or/exists/forall/count_distinct和嵌套；量词domain、计数key和witness角色明确。空或不完整域不自动vacuuous confirmed；数学真值与临床适用/完整性权限分离。',
 '旧不完整组不能用当前剩余members重定义N；同一fact可合法证明两个不同criterion的情况须有显式规则，而非一律禁重复。',
 ['A∧¬B、A∧(B∨C)、2-of-3在true/false/unknown输入中有固定真值表。','同一症状别名不凑足DSM三类；不同合格发作可按event_id计数。','共享叶、组顺序和原始行复制不改变组真值；完整必要any全假可否决。'],
 '自由FOL的可判定性与临床范围不同；首版限制有界变量/有限可证明域，超界返回unsupported。',('M04','M12','M13','M16'))

add('M18','S7','根级动作授权与硬软分离', [('engine',476,'group required inference'),('engine',517,'grouped members skip atomic layers'),('engine',527,'Layer1'),('engine',554,'Layer2')],
 '组relation被忽略或从任一叶推根必要；argues_against与excludes同硬否决；充分组缺确认路径；unknown/阈值未满足仍可能确认。',
 [{'ref':'C74','detail':'评分负项被解释为CPVT硬排除；修其否决不自动证明CPVT完整标准满足。'},{'ref':'C773','detail':'PFO检查指征与疾病排除不同。'},{'ref':'C119','detail':'确认项可来自原文已撤回绝对性的特征。'}],
 [{'id':'CS03','borrow':'决策依据、查询动作及执行条件分开。','limit':'本项目须新增源文授权合同。'},{'id':'CS02','borrow':'经审核逻辑与行动对象分层。','limit':'FHIR结构不提供自然语言正确性保证。'}],
 '集中apply_effect(rule, truth, applicability, completeness, verification)；necessary仅在适用且E明确假时否定D，sufficient在E真时确认D，exclusion在E真时否定D。against仅soft。',
 '根RuleEffect一次触发并保存proof/目标/范围；组叶不独立发根动作。bidirectional保留两方向；route_failed不等于disease_excluded，分类/概率分档不能升级为完整诊断。',
 '全部合同通过的硬规则保留硬效力，不靠统一降权消除误杀。旧rule可语义未决且不执行，但必须计覆盖损失。',
 ['必要、充分、排除、双向四类完整真假/未知矩阵通过。','已满足exclusion组真正排除而非加分；充分组全真能确认。','age scope不适用、路径未满足或score负项均不得独立排病。'],
 '来源冲突及同时有效确认/否定需conflicted，不能选对gold有利的一条。',('M08','M16','M17'))

add('M19','S8','先证据准入，再建claimants和计算权重', [('engine',421,'run_case:claimants'),('engine',571,'Layer3 admission'),('engine',195,'specificity'),('engine',219,'lr_weight')],
 'claimants读取所有asserted已join行，包含后来无分、非诊断、阈值失败和反证；无直接分的行可改变别人IDF。语料提及频率被当临床区分力。',
 [{'ref':'C49','detail':'无直接分条目改变claimants而影响排名，需全候选重算。'},{'ref':'C522','detail':'删菜单/错绑后的score变化含权重交互，不能简单减行。'},{'ref':'C773','detail':'释放PFO后CTEPH分数也随claimants/L4变化。'}],
 [{'id':'CS03','borrow':'进入决策的支持/反对论据需已准入。','limit':'PROforma不提供本仓IDF校准。'},{'id':'MF08_FOVER','borrow':'使用可追溯推导而非任一理论行存在。','limit':'不能把证明次数当独立医学证据。'}],
 '先生成AdmittedEvidence事件，再建正支持claimants；quarantined、unknown、workflow、未适用、无合法literal/根动作的行不能claim。反证单独计，不混正支持集合。',
 '权重以去重concept和经审核evidence unit为输入；将source覆盖、临床似然、候选相关性分别建模。若无校准证据，IDF只能标heuristic feature，不称LR或诊断标准。',
 '不要按最终survivor循环删claimant导致自洽选择；先冻结逻辑准入集合与概念池，再一次计算权重；硬淘汰是否参与对比的策略须明确。',
 ['增加一条无资格行不改变任何候选分数/claimants。','输入复制、无证据duplicate候选不改变权重。','删除合法证据允许改变权重，但必须给全候选delta与residual账本。'],
 '即使全部claim合法，候选集合改变仍会影响经验IDF；须做候选干扰和校准实验。',('M10','M12','M15','M18'))

add('M20','S8','跨L2/L3/L4的证据聚合及复制不变性', [('engine',459,'pooled'),('engine',511,'group score'),('engine',563,'confirmation score'),('engine',605,'FINDING_POOL_BETA'),('engine',630,'Layer4')],
 'F10仅pool原子L3；组票、确认票、L4扣分不在同一证据账户。不同relation或同义predicate可以绕过去重，同一个患者事实重复奖励。',
 [{'ref':'A1','detail':'E16一fact三表述变三票；不能说所有exact复制均会加分。'},{'ref':'C522','detail':'mesenteric CAD/PAD跨relation四票总16.692。'},{'ref':'C74','detail':'同QT380给多个相斥区间和正常参考范围票。'}],
 [{'id':'SP02','borrow':'共享语义对象与其多次出现区分。','limit':'没有自动独立来源假设。'},{'id':'CS03','borrow':'明确证据论据而非字符串次数。','limit':'聚合公式仍须项目单独校准。'}],
 '统一EvidenceLedger标root rule、criterion、patient witness、support family和effect；严格重复证据只保一次状态/票。保留真正不同临床观测，不用“一finding平均”强行抹平。',
 '按可解释证据家族聚合，独立指南复述作为可信度元数据，未经外部校准不重复加临床log-odds；支持和反对分开记录，不能互相抹掉溯源。',
 'group与leaf不可双计；不同规则共享事实不一定冗余，按意义判family。严禁为了复现旧7/11定义family。',
 ['同源转载/同义重复/组叶并行曝光不增加证据份数、确认优先级或L4扣分。','新增真正独立合格检测可改变证据；新增同检查改写不变。','每个score delta均能归到唯一聚合账本条目及其支持集。'],
 '支持家族归类错误会过合并或低估证据，需双向审阅和消融。',('M12','M18','M19'))

add('M21','S8','评分表是有符号程序，不是诊断关系', [('extract',47,'GUIDELINE_PROMPT:threshold schema'),('engine',505,'at_least_n scoring'),('engine',547,'excludes branch'),('engine',581,'Layer3')],
 'schema无score program；负分项可被LLM写成excludes，点数可写成threshold，“任一行满足”替代总分与区间。缺项或未知被当无代价。',
 [{'ref':'C74','detail':'CPVT负分误杀；LQTS多个QT档接同380。完整评分程序与替代诊断路径应分别评价。'},{'ref':'A2','detail':'来源侧评分程序忠实率的分母不是逐表行。'}],
 [{'id':'CS01','borrow':'类型化算术、区间及有符号表达式。','limit':'null聚合策略须显式冻结。'},{'id':'CL07','borrow':'可执行决策程序与可复算运算。','limit':'能运行不证明原文映射正确。'}],
 '引入ScoreProgram类型：每行condition、signed_weight、互斥档/组、总分规则和输出类别；原始负分不编译成exclusion。未知项目不能静默按0而把总分当确定。',
 '以已知总分/可能区间推分类，来源明确允许的缺失处理单列；diagnostic route、risk score、likelihood category与疾病效力分别连接。评分程序可编译受限Python/CQL，保留原AST及测试。',
 '不能从旧已扁平原子自动重建完整评分表；回原表、脚注与版本，评分适用人群独立检查。',
 ['负1项与足够其他正分同时存在时可仍达阈值，不触发硬排除。','QT相斥区间最多取合法档，380不给460–479档分。','复制表行不重复累加；未知项输出区间/unknown而非偷偷归零。'],
 '评分标准本身可能过时或并非确诊条件；需来源版本和临床应用边界。',('M04','M07','M16','M20'))

add('M22','S8','L4只执行已证明的定向对比', [('gate',648,'gate_one:E8_mimic'),('engine',628,'Layer4 survivors'),('engine',635,'comparator relation filter'),('engine',641,'comparator concept_match')],
 '有comparator且患者present便扣另一候选0.5；未核polarity、context、阈值、组根或方向。DDx名单/mimics两病共现可成定向扣分；淘汰谁又决定谁能发L4。',
 [{'ref':'C49','detail':'列表型比较与无资格证据的间接效应。'},{'ref':'C773','detail':'IPAH承受4条L4−2，包括不合法病因/事实连接。'},{'ref':'C119','detail':'确认优先与软票/比较票交互不能当可加效应。'}],
 [{'id':'CS03','borrow':'支持与反对论据需有明确目标和成立条件。','limit':'不从竞争名单自动生成against。'},{'id':'MF05_CLOVER','borrow':'对方向提出反模型检查。','limit':'形式上可区分仍需源文选定方向。'}],
 '仅admitted ContrastRule进入L4；保存favor_target、against_target、condition和scope。DDx_list、mimic、同段共现保留为检索导航，不生成扣分。',
 '在统一EvidenceLedger中求对比规则一次，按完整条件和目标类型分配signed支持，消除独立词面扣分通道；若源只说应鉴别，输出test/workflow action。',
 '真正有方向的鉴别规则不能因context=differential一律禁用；用规则语义裁定而非章节名准入。',
 ['DDx名单无论增删/排列均不改变诊断分。','否定条件或未满足阈值不能触发contrast；两个目标须经ConceptRegistry解析。','合法A证据支持A反对B的正例保留，复制原文只计一次。'],
 '双病共存与候选非互斥时对比效力需明确；对比证据不能自动全局排除B。',('M05','M10','M18','M20'))

add('M23','S9','诊断状态与排序，confirmed不是计数竞赛', [('engine',620,'verdicts'),('engine',628,'survivors'),('engine',666,'ranked sort')],
 '排序按eliminated、confirmed条数、score；一条错误确认可越过大量软分，复制确认影响排序。同候选可有确认及否定却按布尔淘汰直接排序，证据冲突不可见。',
 [{'ref':'C119','detail':'Porokeratosis源有反例而pathognomonic抽绝对；confirmation tier遮住软票。'},{'ref':'C74','detail':'空重复CPVT占代理rank4；解除两个硬刹车暴露LQTS潜伏高分。'},{'ref':'C773','detail':'旧组件PFO top3并非所选错误必要，勿把新排序目标定为重现7/11。'}],
 [{'id':'CS03','borrow':'论据到决策状态与行动分离。','limit':'不意味着存在通用临床排序公式。'},{'id':'CS02','borrow':'正式推荐/行动与证据资产链接。','limit':'标准未给本任务最佳MRR排序。'}],
 '每concept一个状态：unresolved/eligible/confirmed/excluded/conflicted等与score独立；confirmed保持布尔合法状态及proof集合，不以数量排序。冲突先显式标注并阻止自动无争议硬裁定。',
 '在已声明任务角色/范围的同粒度候选中确定性排序，合法完整确认保留刚性地位；soft仅比较未被决定的候选。多个可共存确认不能靠票数选一个完整金标；复合诊断单独评估组成关系。',
 '历史ranking保持可重放；新concept与clinical-complete端点单列，不能将修复后的MRR同旧alias代理MRR混表。',
 ['确认来源复制不改排序；弱证据不能推翻合法硬排除/完整确认。','同时有合法确认与排除输出conflicted，不隐匿其中一条。','组件/父类不能升级完整复合诊断；tie按稳定concept_id且标明无临床区分证据。'],
 '候选池可能缺完整诊断；正确规则执行也不能自动完成缺失候选生成或临床因果归属。',('M10','M18','M20','M22'))

add('M24','S9','完整审计账本与正确终点保持', [('engine',624,'contributions[:25]'),('engine',668,'gold_labels_in_set'),('score',103,'main:drop-excludes intervention'),('tasks',156,'gold_in_set')],
 '生产trace截断25贡献；gold_labels_in_set接受历史别名/组件，诊断rank与测量口径混杂；drop-excludes在gate前删行，还改变group/soft/claimants/L4，并非只关层1。',
 [{'ref':'T1','detail':'11例全候选/全阶段trace和定点干预替代历史简单归因。'},{'ref':'T1M','detail':'旧7/11包含522/773/119组件父类，另4例完整标签。'},{'ref':'A2','detail':'源侧遗漏分母和输出侧虚构分母独立。'}],
 [{'id':'MF08_FOVER','borrow':'多查询检验整包知识，不只单答案。','limit':'不能代替原文完整性裁定。'},{'id':'CL02','borrow':'完整结构终点与原子终点分开。','limit':'下游准确率仍需独立病例。'}],
 '生成不截断的raw→rewrite→binding→truth→effect→claimant→score→rank账本，UI可截断但持久数据不截断；干预明确phase/目标/root/member并保存实际命中。',
 '运行API仅接候选与病例，gold进入独立EvaluationContext；完整标签/组件/父类/近似/错误alias分层。源规则双分母保留，strict hallucination须无可追溯祖先而非quote不逐字。',
 '保持历史代理指标单独列，禁止以重新定义gold“修复”系统；11例仅开发回归，新确认集单独冻结。',
 ['score=全部贡献+明确L4/聚合项可精确复算；每次裁定可定位raw/source。','局部hard-only干预不得静默删除soft/claimants，联合效应给全重放。','完整目标不在池时指标标coverage failure，不以父类排名代替确诊。'],
 '自动账本验证只保证算术/出处一致，不保证AI审阅医学判断正确。',('M01','M18','M19','M23'))

add('M25','S0','分层缓存版本化与失败状态', [('extract',248,'cache_key'),('extract',272,'Extractor.call'),('extract',595,'main:kind suffix'),('nl',67,'cache_key'),('nli',40,'_cache_key'),('nli',145,'nli_check_one')],
 '抽取key仅kind+payload+model，prompt变化靠人工kind后缀；失败{}永久写成正常结果。F8 key漏polarity（verbalize实际读取）、scope/group/threshold/model。编译与运行阶段又依赖隐式global flags。',
 [{'ref':'A1','detail':'F7来源配置必须与抽取身份对齐。'},{'ref':'A2','detail':'真实raw/normalized边界与失败、遗漏分母要分开。'},{'ref':'T1','detail':'本次用四臂cache/job hashes冻结，不能因可选F8静态风险推定历史因果。'}],
 [{'id':'CS02','borrow':'知识资产版本及依赖关系。','limit':'具体hash规范是本项目工程提议，不是论文实证结果。'},{'id':'SP06','borrow':'生成环境/约束作为可执行产物条件。','limit':'缓存一致性不证明语义正确。'}],
 'key加入实际prompt/schema/完整payload/model/provider配置；cache entry区分success_empty、success_nonempty、transport_error、parse_error、incomplete。错误可有TTL或重试策略，不能计为“来源无规则”。',
 'raw extraction cache、compiled rule cache、validation cache、patient evaluation cache分层：分别hash全部影响该阶段的依赖，不将engine版本迫使原始LLM重抽。NLI缓存以实际premise+hypothesis+model+verbalizer版本为最小键，并附AST完整hash。',
 '旧key映射保留但只能标legacy；无实际prompt digest不能伪造verified。缓存迁移只读复制、原始输出不覆盖，带执行status及重试账本。',
 ['只改prompt/polarity/threshold/scope/字典版本分别触发对应阶段miss。','只改rank策略复用raw/compile，但重新evaluate/rank；失败{}不与合法空结果同类。','并发写入采用原子替换，半写结果不能视为成功；全运行profile无隐式global泄漏。'],
 'provider同名模型更新仍可能漂移；记录可得版本、时间、tokens、retry与原响应，不能承诺temperature0可复现。',('M01',), 'code_verified_with_optional_F8_risk_not_frozen_causal_evidence')

manifest={}
for key, rel in files.items():
 p=ROOT/rel
 text=p.read_text()
 tree=ast.parse(text)
 manifest[key]={'path':rel,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'line_count':len(text.splitlines()),'functions':[{'name':n.name,'line':n.lineno,'end_line':n.end_lineno} for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]}
for r in rows:
 for loc in r['code_locations']:
  assert (ROOT/loc['file']).exists()
  assert 1 <= loc['line'] <= len((ROOT/loc['file']).read_text().splitlines())
  loc['source_line_excerpt']=(ROOT/loc['file']).read_text().splitlines()[loc['line']-1].strip()
 for e in r['evidence']:
  assert e['ref'] in refs
  assert (OUT/refs[e['ref']]['path']).exists(),refs[e['ref']]['path']
 for l in r['literature']:assert l['id'] in studies,l
 for dep in r['depends_on']:assert dep in {x['id'] for x in rows}
 assert r['acceptance'] and r['residual_risk'] and r['compatibility']

rows_by_id={r['id']:r for r in rows}
visited=set()
visiting=set()
def check_dependency_dag(item_id):
 if item_id in visited:
  return
 assert item_id not in visiting, 'dependency_cycle:'+item_id
 visiting.add(item_id)
 for dependency in rows_by_id[item_id]['depends_on']:
  check_dependency_dag(dependency)
 visiting.remove(item_id)
 visited.add(item_id)
for item_id in rows_by_id:
 check_dependency_dag(item_id)

obj={
 'schema_version':'migration_matrix/1.0',
 'date':'2026-09-06',
 'repository_baseline':'cursor4@6fa8fd7aa2548cc01ac81f2d5261801190244d27',
 'scope':'本仓机械规则试验链函数级迁移提议；不是所有APHHM-C/Forest生产运行链；未修改或部署被审生产代码。',
 'status':'design_only',
 'phase_naming':{'I0-I5':'工程接口迁移顺序，仅本迁移图','P0-P5':'主报告和研究路线图的研究晋级阶段，不同于I序列','S0-S9':'migration_items.stage的运行处理层'},
 'evidence_policy':'code_and_audit代表静态行为与已冻结见证的结合；标optional/static的新增风险不能当冻结四臂下降因果。验收均为未来要求，不称已通过。',
 'source_code_manifest':manifest,'audit_references':refs,'literature_references':studies,
 'migration_items':rows,
 'delivery_validation':{'items':len(rows),'code_locations':sum(len(r['code_locations']) for r in rows),'all_code_files_and_lines_exist':True,'all_audit_references_exist':True,'all_literature_ids_resolve':True,'all_dependency_ids_resolve':True,'dependency_graph_acyclic':True,'production_implementation_changed':False,'engine_or_llm_rerun':False},
}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'migration_matrix.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

header='''# 抽取器与执行器函数级迁移图

日期：2026-09-06。代码参照 `cursor4@6fa8fd7aa2548cc01ac81f2d5261801190244d27`。这是第三任务中的可操作迁移设计，不是已部署实现或性能提升报告。范围是 `RAG_GUIDELINE_ORACLE_CEILING_LOCAL` 机械试验链；不能外推为所有 APHHM-C / Forest 方法已经有同样的诊断时 RAG 接口。

**先冻结身份与证据，再更换语义合同，最后调整评分。** 当前问题分布在多个独立阶段，不能用“AST更丰富”“改一个prompt”或“所有硬规则降权”替代迁移。前次来源先行能力审计显示，即使在被认为平面schema可以表达的194条源规则中，新臂也只有28条完整忠实；因此结构改造必须与源级审核、符号身份、事实接合和执行合同共同验证。[能力边界](../V2_RULE_EXTRACTION_CAPABILITY_CENSUS/REPORT.md)

本图实读10个源码文件，给出25项迁移、代码锚点、旧审计/本次病例证据、文献可借部件、最小修补、结构改造、兼容限制和验收条件。机器可读逐项账本及源码SHA-256见 [migration_matrix.json](migration_matrix.json)。以下验收条件均是下一阶段要求；本任务仅核验文档引用与映射一致性，没有实施改造、重跑大引擎或调用新LLM。

## 1. 阶段边界与迁移次序

本文件的 **I0–I5是工程接口迁移顺序**，与主报告及研究路线图的 **P0–P5研究晋级阶段**分别编号；M01–M25为稳定迁移项ID。JSON中的S0–S9只标运行数据流所在层，不是研究晋级门槛。

| 顺序 | 新阶段合同 | 本文件迁移项 | 必须先解决的原因 |
|---|---|---|---|
| I0 | 不可变运行、来源、缓存、观测账本 | M01、M25；M24的只读日志部分 | 不能让新输出借旧窗口许可，也不能让失败缓存冒充完整遗漏 |
| I1 | 概念、来源块和规则出现身份 | M02、M03、M10–M13 | 先保住组成员和精确主体，才有可审查表达式 |
| I2 | 中性释义、递归规则、编译准入 | M04–M09 | 连接词、量词域和根效力独立；无证据的语义改写不能叫归一化 |
| I3 | 病例事件、typed join、literal与组真值 | M14–M18 | 值、正常/异常、时点、对象和未知要在动作前正确求值 |
| I4 | 合法证据账本、评分程序与对比 | M19–M22 | 先准入后claimants；共享证据不反复投票；评分负项不能硬排病 |
| I5 | 状态、排序、终点评估 | M23、M24 | 不以确认条数或父类代理排名代替完整诊断 |

这不是要求I1完成后才能开始研究I2。可并行实现独立组件，但只有接口先决条件满足才组合上线；`migration_matrix.json`的`depends_on`列给具体依赖。I0保留历史冻结重放，I1以后另设新profile，不把修复后的分数伪装成历史同配置结果。

关键数据流应是：**SourceBlock → RuleOccurrence / RuleAST → CompiledRule与准入 → BindingProof → LiteralTruth / ExpressionTruth → DiagnosticEffect / AdmittedEvidence → EvidenceLedger → CandidateState与rank**。每个箭头都保存输入与输出身份，不允许score层再次猜literal含义。ConceptRegistry和患者Observation/Event图分别为主体与事实提供引用。

## 2. 不能妥协的兼容边界

1. **旧输出是历史观察，不是新合同的金标。** 完整独立原子和唯一可确定的浅层组可迁移；混合relation、缺n、丢成员、评分扁平化都不能靠adapter猜回根逻辑。保留`legacy_unresolved`并计入覆盖损失。
2. **安全别名是双向等价，继承是另一种方向关系。** CPVT大小写格式副本应该合并；Angiosarcoma/Hemangioma不能合并；PECAM-1/CD31应桥接。要同时测漏合并和误合并，不能只优化其中一端。父类优先级或候选排列不得夺走exact主体。
3. **组成员的存储去重与证据去重分开。** 共享叶只共享语义对象，不能删除第二组的member edge。给旧去重key加sourcehash虽能保叶，但会重新放大同源票；M12和M20必须联动。
4. **准入失败不能靠改成feature洗白。** 没有源支持、未适用、检查流程或未知比较不产生诊断票、claimants、L4。合法soft与合法hard都应保留本来效力，前者不是后者被拒后的默认回收站。
5. **刚性能力不能取消。** 合法充分/排除组应当一次独立生效；未知、冲突、缺域和路径失败不应冒充合法否决。全面降低刚性无法修复方向、scope或事实绑定。
6. **历史代理终点独立保留。** 旧7/11包含组件/父类接受，并非7次完整确诊；773清理选定错误后旧PFO仍可top3。不能把“重现旧7/11”作为迁移验收目标。[差量报告](../V2_INDEX_DIFFERENTIAL_AUDIT/REPORT.md)

## 3. 逐项函数级迁移

代码锚点是本次冻结版本的行号，不保证未来版本不移动。`最小修补`指可独立实现的行为更正；`结构改造`指使同类规则一般化的接口替换。文献部件的有效性限制逐项保留，不能将引用当成已经适用于本仓的实验结果。

'''
parts=[header]
for r in rows:
 parts.append(f"### {r['id']} · {r['title']}\n\n")
 loclinks=[]
 for loc in r['code_locations']:
  relpath=Path(loc['file'])
  import os
  target=os.path.relpath(ROOT/relpath,OUT)
  loclinks.append(f"[{relpath.name}:{loc['line']}]({target}#L{loc['line']}) `{loc['function_or_block']}`")
 parts.append('**代码：** '+'；'.join(loclinks)+'。\n\n')
 parts.append('**现行缺陷：** '+r['defect']+'\n\n')
 ev=[]
 for e in r['evidence']:
  q=refs[e['ref']]
  ev.append(f"[{e['ref']}]({q['path']}) {e['detail']}")
 parts.append('**证据：** '+' '.join(ev)+'\n\n')
 lit=[]
 for l in r['literature']:
  q=studies[l['id']]
  lit.append(f"[{l['id']}]({q['url']})：{l['borrow']} 限制：{l['limit']}")
 parts.append('**借鉴：** '+' '.join(lit)+'\n\n')
 parts.append('| 迁移维度 | 可审查变更 |\n|---|---|\n')
 for label,k in [('最小修补','minimum_fix'),('结构改造','structural_redesign'),('兼容边界','compatibility'),('残余风险','residual_risk')]:
  parts.append(f"| {label} | {r[k]} |\n")
 parts.append('\n**验收：**\n\n')
 for t in r['acceptance']:parts.append('- '+t+'\n')
 parts.append('\n')
 if r['evidence_status']!='code_and_audit':
  parts.append('**因果边界：** 本项含可选F8或新静态风险；不作为冻结四臂下降的既证因果。\n\n')
parts.append('''## 4. 最小实施批次与停止条件

**批次A：可追溯性和身份。** 先实现M01/M25和M24的完整账本，再实现安全ConceptRegistry、exact优先、稳定group occurrence及不删member的存储。以冻结raw缓存做双轨重放；只要求已声明的不变量和合法行为通过，不要求临床rank一律提高。522/773的错误相互抵消说明“修正后局部rank变差”并不足以回滚语义正确修补。

**批次B：参考语义解释器。** 先用人工式源审阅的完整RuleAST和冻结typed facts验证M16–M18；再接自动抽取和自动join。借用既有27个程序反例作为失败种子，但必须增加合法充分、合法排除、合法必要、双向定义、正常条件、共享叶和未知传播的正反成对验收。不能把“27旧反例全变不执行”叫通过。

**批次C：抽取和验证实验。** 固定source与预算比较旧flat、仅AST、结构分解/受控释义+AST、加入独立验证；源规则先行冻结，病例gold不得进入源级裁定。每个层次报告faithful/distorted/omitted及严格无源虚构，而非只报通过验证的剩余条目。记录repair修对、修坏、未改和拒绝的覆盖代价。

**批次D：证据与排序。** M19–M23逐项替换，先用合法固定RuleAST/BindingProof，再用自动版本，分别记录硬动作错误、完整概念终点和全候选分差。含parent/sibling增删、同源复制、真实新观测、L4竞争者复活的干预。不能以相关文献频度默认校准为临床似然。

任一批次出现候选/组/观测顺序改变语义、缺值变硬真/假、scope不兼容仍可硬执行、无资格行改变claimants、source/缓存不一致或复制改变确认优先级，即停止合并下一批并定位首次损坏阶段。对于类型检查无法区分的语义错误，停止条件应来自独立源审阅，不得由gold rank倒推。11例仅作开发回归；新确认集与能力边界源样本分别冻结，完整诊断和代理标签分别报告。

## 5. 缓存依赖设计的具体边界

| 缓存层 | 至少进入身份的依赖 | 不应迫使上游无谓重算的变化 |
|---|---|---|
| Raw抽取 | 实际prompt hash、schema、source payload/布局、模型/provider配置、解码参数、代码提取版本 | 排序政策改变不重新请求LLM |
| 编译 | raw artifact hash、normalizer/compiler版本、语义合同、概念/单位字典、source manifest | 仅显示格式改变不重新编译 |
| 验证 | 完整AST及源spans、验证器/模型、verbalizer、参照/背景理论和测试面板版本 | rank系数改变不重做源忠实审核 |
| 患者求值 | compiled rule、病例Observation/Event图、concept映射、join/evaluator/admission策略 | 仅UI展示改变不重新绑定 |
| 聚合/排序 | admitted evidence账本、候选concept集、pool/L4/rank策略、任务角色 | benchmark mapper不能反向改写诊断排名 |

缓存有效性是依赖完整性，不能只在文件名加`v3`。`success_empty`是模型明确返回合法空结果；transport/parse/incomplete错误单独记账。无法验证旧prompt或来源版本的缓存可以继续历史重放，但不能获得新schema的verified标志。F8还存在一项明确静态风险：key不含polarity，但生成NLI句子读取polarity；本项应修复，但未启用F8的冻结四臂不能由它解释。

## 6. 本分项核验与未完成事项

已完成：10份实际源码的静态审读，25项迁移映射，所有代码锚点、审计文件和文献ID可解析，记录源码SHA-256及函数范围。未完成：生产实现、外部框架安装/复现、新的模型抽取、真实临床专家审核、新病例准确率验证。文献保证边界沿用第二任务的逐原始来源核验；本图的接口、批次和验收是据此提出的项目设计推论。

可用 [build_migration_map.py](build_migration_map.py) 重新生成本图和JSON矩阵；脚本只读取源码与冻结审计/文献账本，不调用执行引擎或模型。

本图不试图用迁移计划“解释剩余所有分差”。第一任务保留的residual包含合法来源变化、未审条目和权重交互。改造后的评价应保持这种诚实分解，而不是让更复杂的执行器再次以最终答案掩盖源文误译。
''')
(OUT/'MIGRATION_MAP.md').write_text(''.join(parts))
print(json.dumps(obj['delivery_validation'],ensure_ascii=False))
