# 例 49：残端阑尾炎：错误组织学票保住top3，检查菜单又推高近邻

## 病例与终点

58岁男性，腹腔镜阑尾切除8个月后急性右髂窝痛、发热、恶心/腹泻；血WBC25,000、85%中性粒、CRP180；CT在盲肠极部、手术夹旁显示36×27mm肿胀管状结构及25mm积液。完整目标是残端阑尾炎，候选明确有 `Appendiceal stump appendicitis`。历史还把上位类Appendicitis接受为gold，但本例四臂实际最先gold均为完整残端候选，不把这项top3误判为仅靠上位类标签。

盲肠周围积液/脓肿可为真实组成病变，本轮保留其合法影像支持。Cecal diverticulitis是近部位竞争病因；neutropenic colitis、Typhlitis等又与本例缺少中性粒减少的事实不符。必须区分真实并发病灶与不相容病因，不能把所有非gold候选都当作不应得分。

## 正确残端规则已抽出，但病例桥接无法使用

旧、新均有残端定义与既往阑尾切除的特殊性。旧raw218、241、253、302、383–385等，新raw222、266、408–410、534、543–546、558等保留residual stump/incomplete appendectomy/long stump。v2 Schwartz gid901865/901866还明确“既往阑尾切除不能绝对排除急性阑尾炎”。这些内容没有形成“手术史+盲肠极管状物+夹旁炎症→残端”的执行程序。患者结构化facts中手术史、管状物、部位、手术夹被分存，定义中的stump词无法直接匹配其解剖/事件关系。

同时错误方向也存在：源说≤5mm残端**降低**风险，一些raw转为 stump size caused_by，虽本例缺少可匹配残端长度，不能把这种未执行错误计为已经导致排名下降。

## 金标的幸运票：血象被当作六至七份组织学

源旧gid458477/458481/458483/458488明确为阑尾黏膜、黏膜下、肌层/管腔内的组织学中性粒细胞；旧gid718604已有muscularis propria浸润总述，v2 gid762482补入其后缺失的三类组织学列表，新增完整的黏膜/黏膜下/肌层复合表述。原子本身多可追溯且主体指向具体阑尾炎亚型。主体绑定将它们给残端候选，谓词连接再把患者**血中85%中性粒**当作组织浸润：

- 旧/旧六种独立去重后表述合计 **+8.600**；旧/新提示六种合计 **+10.216**。
- 旧提示/v2七种合计 **+11.918**；新提示/v2六种合计 **+10.216**。

这正是“更完整原文”能同时让评分更错的机制：v2新增真实的组织学列表，旧提示/v2 raw651保留其黏膜/黏膜下/肌层浸润复合表述，向同一个错误样本类型的患者血象再加一票。其他段落早已包含相近组织学，因此是源补齐与跨段去重不足共同增加近重复证据。不能据抽取保真判定context utility增加。

还有一个此前只看contribution会完全漏掉的交互：旧/旧raw2181（gid658715）是**腹部TB占全部TB的6–13%**，被绑定至Appendiceal abscess，再以percentage接血中85%中性粒。它的epidemiology context使L3不直接加分，**却已经进入claimants**，让neutrophils被3个候选认领。其余三臂只有2个认领者，故同一组织学错票由1.433升为1.703。该行没有任何直接contribution，单独屏蔽后gold分数由16.249变18.135、Typhlitis由13.612变14.343，而gold仍第三。另把旧提示/v2新增的raw651单独屏蔽，gold26.016降到24.313仍第二。因此这两个机制实测改变分数，但各自单独不足以解释该臂的完整rank变化；适应性单行屏蔽探针单列于JSON，不伪称预注册。这里既有v2修掉错误认领、又有修掉后反而放大另一条错误支持的效应，不能把增加的总分全算作新增条目。

## 竞争者进一步如何积累高分

NICE段（v2 gid27459/27460）要求疑似复杂憩室炎者做FBC/CRP等，炎症指标高时安排contrast CT；CT禁忌时可选其他影像。新raw1035/1041/1070/1071将检查名称写成sufficient/required，再绑定到Cecal diverticulitis。F7有时降为feature，却仍然加分。contrast CT、ultrasound、CT腹盆、FBC、CRP这类**动作名**都接患者CT/FBC/CRP事实；未验证任何憩室炎特异影像结果。所选程序家族的原始数值票从旧/旧 **+15.131** 到新/v2 **+19.081**。

与此同时，neutropenic colitis把bloody/chronic/watery diarrhea都接患者未限定的24小时diarrhea，把rebound接普通压痛，CT scans再各算一票。Schwartz gid901767把typhlitis限定在低中性粒人群，raw3397保留<1000/μL，但患者finding只有85%；单位不合导致数值无法比较，仍 **+4.628**。实际上由现有血象可算25,000×0.85=21,250/μL，足以说明不能把该数字当作满足源的<1000条件；这里无需另造某种病因硬排除标准。

## 反向审计top3：移除错误为何反而使结果变差

仅阻断金标的组织学错接，四臂rank **3→5、3→4、2→4、3→4**。旧/旧本来16.249，阻断错接后7.649，落到Typhlitis/Abscess之后。因此旧7/11中的本例有明确、无须争论粗暴露桥接的“错误支持保住top3”见证。

但仅阻断所选竞争者错误，四臂变 **2、1、1、1**；两侧同时阻断则为 **5、3、2、2**。这不矛盾：在冻结的不完整事实表达中，正确残端关系尚不可执行，双方删错不会凭空补上它；且claimants数量改变使其他分数重加权。仅修竞争者能制造漂亮top1，却保留gold错误组织学票，不能当作达到可靠诊断。

旧提示下v2的2名比旧索引3名好，也不能自动归因于忠实规则帮助：新增组织学票至少参与抬升目标。新提示下v2 gold原始分也增加，却Cecal/Neutropenic竞争分增长更快，仍第三。这些具体链比“更多规则加权偏常见病”更精确：样本错接、检查动作升格、条件域丢失和候选相对权重在同一患者上相互作用。


## 四臂名次、分数与局部干预表

| 臂 | 目标分/名次 | 排名第一/分数 | 只屏蔽目标错误join | 只屏蔽竞争错误join | 双侧一起 |
|---|---:|---|---:|---:|---:|
| 旧提示/旧索引 | 16.249 / 3 | Cecal diverticulitis / 34.249 | 5 | 2 | 5 |
| 新提示/旧索引 | 21.653 / 3 | Cecal diverticulitis / 37.964 | 4 | 1 | 3 |
| 旧提示/v2 | 26.016 / 2 | Cecal diverticulitis / 36.699 | 4 | 1 | 2 |
| 新提示/v2 | 26.913 / 3 | Cecal diverticulitis / 42.956 | 4 | 1 | 2 |

## 明确证据行与首次损坏层

以下按错误家族列出**旧/旧及新/v2**实际产生贡献的代表原始行；去重support完整集合、数值与gate/bind/join元数据见JSON。正数和负数均照实保留，不把所有被选行都计为同向害处。

| 臂 | 错误家族 | 候选 | 代表raw行 | 实际贡献合计 |
|---|---|---|---|---:|
| 旧提示/旧索引 | D_diagnostic_action_to_disease_evidence | Cecal diverticulitis | 1076, 1078, 1079, 1082, 1144 | 15.131 |
| 旧提示/旧索引 | D_qualifier_test_numeric_scope | Neutropenic colitis | 755, 2197, 3010 | 7.552 |
| 旧提示/旧索引 | T_blood_neutrophils_to_histology | Appendiceal stump appendicitis | 476, 556, 557, 563, 605, 664 | 8.600 |
| 旧提示/旧索引 | D_qualifier_test_numeric_scope | Typhlitis | 3567, 3645 | 5.116 |
| 新提示/v2 | D_diagnostic_action_to_disease_evidence | Cecal diverticulitis | 946, 1035, 1038, 1039, 1041, 1065 | 19.081 |
| 新提示/v2 | D_qualifier_test_numeric_scope | Neutropenic colitis | 803, 1656, 2009, 2801, 2853, 3353 | 15.203 |
| 新提示/v2 | T_blood_neutrophils_to_histology | Appendiceal stump appendicitis | 501, 578, 579, 585, 640, 692 | 10.216 |
| 新提示/v2 | D_qualifier_test_numeric_scope | Typhlitis | 3308, 3322, 3397 | 8.398 |

## 重放与审计口径

本报告使用 `replay_audit.py` 的 historical_default_stale B1/S7，完全冻结来源、病例facts、候选顺序与模型缓存；完整贡献未截至25条。此前exact_arm_window版本的若干竞争者分数略有变化，不能混用；gold名次一致并不等于所有分数一致。所有表格来自 `judgments_infect_neuro.json`，原始行号是**合并病例抽取数组零基索引**，不是局部cache行号。`_audit_source` 同时保存cache、gid、focus、局部行和源hash。

- numeric-only (`remove_contributions`)：只移除指定贡献，保留join、claimants和硬判决，测量固定连线中的票效应。
- join-block (`block_joins`)：在最佳匹配后、claimants/组执行前屏蔽指定连接，不寻找替代匹配；它会改变其他候选权重，属于条件机制干预。
- 本报告只审计指定错误家族，不声称覆盖所有分数的临床正确性。未插入oracle事实、未按gold删合法弱支持、未调用新LLM。病例是既定11题开发样本，不估计总体错误率。
- 由AI审计员逐段阅读与程序复算，不是真实临床专家双盲研究。`*_initial_probe.txt` 是早期定位中间件，可能包含同predicate的多个候选raw匹配，**最终归因以完整trace的deduplicated support IDs为准**。
