#!/usr/bin/env python3
"""Assemble four manually reasoned case reports with reproducible numerical tables."""
import json,collections
from pathlib import Path
OUT=Path(__file__).resolve().parent
D=json.loads((OUT/'judgments_infect_neuro.json').read_text())
ARMS=['旧提示/旧索引','新提示/旧索引','旧提示/v2','新提示/v2']
TEXT={
'257':('领扣脓肿：决定性词留在 quote，错误研究阈值却获得最高单票',r'''
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
'''),
'326':('布鲁氏菌病：病原字段不可达、同义名当体征与病因—病灶竞争',r'''
## 病例与终点

57 岁男性，破损手接触未经处理的羊胃后一个月高热、盗汗、背痛；血培养长出 Gram-negative bacillus；T9 椎弓炎性破坏及后方硬膜外脓肿压迫脊髓。gold `Brucellosis` 是完整且适当的病因实体。Epidural abscess、椎骨感染等可以是真实共存病灶，不应称“医学上不存在的错误诊断”；它们只是当前病因问题的竞争答案。实验把病因、病灶和病原类别放进同一互斥排序，没有表达 `Brucellosis causes vertebral infection with epidural abscess`。

## 病因信息确实到达，损坏发生在表示与连接

旧 raw14/17/23/25 已有 Brucella 为 Gram-negative/coccobacilli。患者 finding24 的 label/canonical 只有 blood culture，结果 **Gram-negative bacillus 被放进 value.text**。join 比较 label/canonical，不能将这个结果绑定到病原形态；同时 `blood culture` 与 `cerebrospinal fluid culture` 都能接到该 finding。该机制与是否有更多菌种文献无关。

动物材料暴露与 injured hand 被拆为 finding3、4。旧 raw301 的 skin penetration of those in contact with livestock 比“饮奶”更接近该病例，但缺少复合暴露事件与共同论元，未形成其预期支持。饮用未消毒奶却因共享词被接到接触羊胃，出现多份同一暴露票。这里必须区分：严格谓词“饮用奶”不成立；较粗的动物产品暴露可以保留有界弱先验。因此账本同时给出**保留所有 exposure bridge 的核心敏感性**，没有把所有近义临床桥接都视作应删除。

## 双向污染，而非只压低金标

- **同义标签当患者体征。** 源（旧 gid701410）忠实列 Brucellosis 的 Mediterranean/Malta/Undulant fever 别名。旧 raw11/12/13 的 `synonym_of` 本身可忠实，但 engine 按 feature agreement 接患者 high fever，各 **+0.959**。旧提示/v2 这三份票消失；新提示/v2 又恢复，各 **+1.241**。因此一部分 prompt×index 差量是命名方式造成的票数变化，不是病因证据变强或变弱。
- **金标也得到错位证据。** reactive bone sclerosis 接 C-reactive protein；腹痛/阴囊痛接背痛；CSF culture 接血培养。另一方面 positive Brucella serology 接阴性的 tuberculosis serology，旧/旧和旧/v2各 **−0.4**。病原检测对象丢失可以同时造成虚假支持和虚假反证。
- **竞争病因 Pott 的高权错票。** 源（旧 gid298060）讨论活检中“缺乏多形核粒细胞浸润/干酪坏死”提示结核。raw650 的 absence 保留在谓词文字、polarity=asserted，执行器将它接血中80%中性粒细胞，正加 **+2.777**。此处叠加组织/血样、缺乏/存在两类错误；字符串仍可溯源，故不是无来源幻觉。
- **同名异病与部位错接。** v2 中 Pott puffy tumor 的额部骨膜下脓肿（新提示 raw1731，gid644467）松散绑定为 Pott's disease，并接脊柱后硬膜外脓肿 **+0.938**。源对前者的描述正确，binder 的 Pott 词重合毁坏疾病身份。
- **真实病灶的错误额外票。** 本轮保留硬膜外脓肿、背痛、脊髓受压的真实支持，只阻断例如 epidural tumor→epidural abscess、elevated WBC→仅报告7170/mm³且未标升高等额外错票。不能为了让 Brucellosis 获胜而删除患者实际存在的病灶证据。

## 七个旧 top-3 中，本例为何“看似成功”

四臂 gold均排第三，掩盖病因链未被编译。旧/旧 Brucellosis16.054中，选定严格目标错误票累计约6.57；阻断它们后变9.483并排第四。只阻断所选竞争错误使其排第二，两侧一起阻断仍排第四。但是这个反事实包括对饮奶→羊胃的严格字面阻断；若为粗动物暴露保留弱先验，不能宣称旧top3必定消失。核心敏感性单独给出，以免把更严格的谓词正确性直接等同“该信息毫无诊断价值”。

另一个 v2 错误反而帮它维持top3：gid392067是 **腰椎椎间盘造影的禁忌证**，旧提示 raw603 把“known/suspected infectious discitis”改成 Discitis 的 infection excludes，再接highfever，误杀 Discitis。恢复该竞争者的精确干预也单列。本例说明名次不变可以包含正确证据失联、金标错票消长、错误病因扩张及竞争病灶误杀的共同作用。

## 能与不能识别的结论

确认的是局部程序链与条件反事实；并未证明布鲁氏菌暴露加一般革兰阴性培养对所有病例都是刚性确诊，也未新增临床判据。本例需要的是 typed diagnostic target、因果复合候选、检验结果的实体/样本/时间槽位和受限事件桥接，而非让所有病灶候选退场。疾病名称同义关系不应进入症状匹配求和。
'''),
'475':('神经痛性肌萎缩：单神经特征堆票，跨神经关系被压平',r'''
## 病例与终点

22岁女性突发孤立左上肢无力、不能OK与握拳、无感觉缺失、反射正常；EMG不仅累及AIN支配肌，也有肱二头、肱三头、三角肌改变；MRI正常。gold Parsonage–Turner Syndrome 与 `Neuralgic Amyotrophy` 按仓内别名对应。另有同名小写 `Neuralgic amyotrophy` 却不被历史gold集合接受；两者均未获同等绑定。`Brachial Plexitis` 相关，但本轮不自动把所有臂丛炎和单神经病变都认作完整同义实体。

## 真正的区分信息被拆成“不相连的名字”

源（v2 gid149129）明确NA可超出臂丛，累及前/后骨间、腋、正中、桡神经；其他AIN源给出分支与肌肉支配限制。患者的多肌肉EMG异常只存成一个“changes in biceps/triceps/deltoid”finding，没有论元图说明每条肌肉对应何神经、与AIN分布是否相容。正确判断需要结合两组信息；仅出现某一个神经名不足以作排除或确认。

## AIN 的错误支持如何逐项叠加

- 旧 gid149691 在AIN小节附近带入CTS的 thenar atrophy/APB weakness；旧 raw22/237把APB条目主体写成AIN syndrome。患者拇指远端屈曲无力不是APB外展功能阳性，但该原子仍接中 **+2.877**。
- 旧 gid669879说腕部正中神经损伤时AIN在前臂分支而获保留，所以患者 **仍能做OK**。旧 raw77将其挂到AIN syndrome并保留 `ability to make OK sign`。join却与患者 **不能OK**正向匹配 **+3.746**；源主体、解剖层级及文字否定均未受约束。
- 不能OK、拇指不能屈曲、食指远端不能屈曲、pincer movement弱、thumb-index coordination等多个表达对同一小组体征分别加票。这些并非全部来源规则错误；问题是同一患者观察被算作多份独立证据，而跨神经EMG关系只有一个压平finding。所选局部干预没有为了削弱AIN而删除全部真实AIN支配肌异常。

这三个直接审计的AIN错误项旧/旧累计 **+6.916**，删除后AIN仍为24.581而NA仍3.945。说明仅修旧审计提到的trauma极性或一个错误OK命题不会解决该病例，真正的剩余瓶颈是关系表示、身份绑定与重复投票。

## gold并不是清洁的弱者

NA的 `posterior interosseous nerve involvement` 接患者 anterior interosseous involvement，四臂各 **+1.124**。MRI可见肌肉水肿这一源结果又接EMG的“肌肉改变”，旧/旧 **+1.365**、其余 **+1.124**，患者实际MRI正常。仅有EMG失神经改变不能被视作患者已见MRI肌肉水肿。

负向污染也存在：旧两提示与旧提示/v2把MRI/影像本身当特征，因患者MRI正常扣分；新/v2把方法比较“MRI比超声敏感”两次转为 `MRI sensitivity` 特征/比较关系，又各扣0.4，甚至把“肩及上肢感觉丧失”接到normal MRI而扣分。方法层面的敏感度不是该患者阴性的疾病发现。

旧/旧只去除NA上述两种虚假正票，numeric-only 后NA仍第三；在claimants前真正阻断join，NA1.456而Mononeuritis Multiplex1.462，第三变第四。**0.006的跨候选重加权差足以改变top3**，不应当用各贡献delta静态相减推断修复效果。新/v2则从1.959减到负分、降至第十；其top3非常依赖这两张错误正票。

## 新旧索引差量与错误抵消

NA得分四臂约3.945/3.997/3.704/1.959；AIN虽从31.498逐步降至18.793，金标并未追上：竞争者错误减少不是正确关系获得利用。新/旧的gold名次3→2，还伴随Mononeuropathy被错误 `all` 必要组排除；旧/v2和新/v2同样有其组否决，只是Brachial Plexitis升到NA之前。不能把新提示的第二名归因于正确地发现跨神经病变。

源差量示例旧463851→v2477657加入长腋神经解剖段；更多解剖文字并未转为带肌肉论元、层级与否定范围的可执行证据。本例的正确下一步应是“分布相容性”关系程序，而不是用出现过AIN就排除NA、或把宽泛正常MRI当万能排除。
'''),
'49':('残端阑尾炎：错误组织学票保住top3，检查菜单又推高近邻',r'''
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
''')}

FOOT=r'''
## 重放与审计口径

本报告使用 `replay_audit.py` 的 historical_default_stale B1/S7，完全冻结来源、病例facts、候选顺序与模型缓存；完整贡献未截至25条。此前exact_arm_window版本的若干竞争者分数略有变化，不能混用；gold名次一致并不等于所有分数一致。所有表格来自 `judgments_infect_neuro.json`，原始行号是**合并病例抽取数组零基索引**，不是局部cache行号。`_audit_source` 同时保存cache、gid、focus、局部行和源hash。

- numeric-only (`remove_contributions`)：只移除指定贡献，保留join、claimants和硬判决，测量固定连线中的票效应。
- join-block (`block_joins`)：在最佳匹配后、claimants/组执行前屏蔽指定连接，不寻找替代匹配；它会改变其他候选权重，属于条件机制干预。
- 本报告只审计指定错误家族，不声称覆盖所有分数的临床正确性。未插入oracle事实、未按gold删合法弱支持、未调用新LLM。病例是既定11题开发样本，不估计总体错误率。
- 由AI审计员逐段阅读与程序复算，不是真实临床专家双盲研究。`*_initial_probe.txt` 是早期定位中间件，可能包含同predicate的多个候选raw匹配，**最终归因以完整trace的deduplicated support IDs为准**。
'''
for case,(title,body) in TEXT.items():
 rows=[r for r in D['cases'] if r['case']==case]
 lines=[f'# 例 {case}：{title}',body,'\n## 四臂名次、分数与局部干预表\n','| 臂 | 目标分/名次 | 排名第一/分数 | 只屏蔽目标错误join | 只屏蔽竞争错误join | 双侧一起 |','|---|---:|---|---:|---:|---:|']
 for r in rows:
  t=next(x for x in r['baseline']['ranking'] if x['label']==r['target_label']);top=r['baseline']['ranking'][0]
  def rk(name):return str(r['probes'].get('block_joins__'+name,{}).get('gold_rank','—'))
  lines.append(f"| {ARMS[r['arm']]} | {t['score']:.3f} / {t['rank']} | {top['label']} / {top['score']:.3f} | {rk('target_errors')} | {rk('distractor_errors')} | {rk('joint_errors')} |")
 if case=='326':
  lines+=['\n核心敏感性保留全部粗动物暴露桥接，其他所选目标错误照常阻断：\n','| 臂 | 核心目标错票阻断后rank | 核心目标+竞争错票阻断后rank |','|---|---:|---:|']
  for r in rows:lines.append(f"| {ARMS[r['arm']]} | {r['probes'].get('block_joins__target_core_preserve_exposure',{}).get('gold_rank','待补')} | {r['probes'].get('block_joins__joint_core_preserve_exposure',{}).get('gold_rank','待补')} |")
 lines+=['\n## 明确证据行与首次损坏层\n','以下按错误家族列出**旧/旧及新/v2**实际产生贡献的代表原始行；去重support完整集合、数值与gate/bind/join元数据见JSON。正数和负数均照实保留，不把所有被选行都计为同向害处。\n','| 臂 | 错误家族 | 候选 | 代表raw行 | 实际贡献合计 |','|---|---|---|---|---:|']
 for r in rows:
  if r['arm'] not in [0,3]:continue
  fs=collections.defaultdict(list)
  for s in r['selected_rows']:fs[s['family'],s['candidate']].append(s['contribution'])
  for (fam,cand),cs in fs.items():lines.append(f"| {ARMS[r['arm']]} | {fam} | {cand} | {', '.join(str(c['_audit_representative_raw_id']) for c in cs)} | {sum(c['_audit_effective_score_delta'] for c in cs):.3f} |")
 lines+=[FOOT]
 (OUT/'cases'/f'case_{case}.md').write_text('\n'.join(lines))
print('wrote4')
