# 56：完整诊断先被父类夺走证据，再被更多鉴别列表逐次扣分

病例 `MCR_v1_seq100/56`，原金标 **Spindle cell squamous cell carcinoma**。23 个冻结候选中真实存在相应的 **Sarcomatoid squamous cell carcinoma**；历史 scorer 却只接受 **Carcinoma**。这既将父类当成功，也把完整标签当错误。69岁男性牙龈恶性梭形细胞肿物、既往放化疗、p63阳性和 pan-cytokeratin 阴性必须作为同一病变的关系解释。本文不把某个 marker 单独视为已完成鉴别，也不重新确认原临床金标。

## 1. 报告中低得分的完整候选，并不缺少相关抽取

| 臂 | 父类 Carcinoma 名次/分数 | 完整 SCC 名次/分数 | 完整 SCC 绑定后断言 | Leiomyosarcoma / Osteosarcoma 分数 |
|---|---:|---:|---:|---:|
| old_old | 6 / 8.898 | 21 / -1.500 | 0 | 29.409 / 17.163 |
| free_old | 7 / 6.296 | 22 / -1.500 | 0 | 30.250 / 17.036 |
| old_v2 | 6 / 6.973 | 22 / -4.000 | 0 | 24.840 / 23.922 |
| free_v2 | 7 / 3.897 | 22 / -4.500 | 0 | 25.614 / 22.067 |

四臂完整 SCC 没有 layer1 排除。负分全来自其他候选施加的 L4 处罚。把“0条绑定证据”解释成 LLM 不知道或根本未抽取该病，是错误归因：原始输出中已有多条 **subject 字面就是 Sarcomatoid squamous cell carcinoma** 的断言，包括 p63、梭形形态、年龄与病理说明。生产代码逐候选扫描，遇到早先 `Carcinoma` 的 containment 匹配即退出，不再找后面的精确主体。来源越多，更多精细诊断知识先进入父类池。

并非所有大候选都只是得到自己的知识。Leiomyosarcoma 还通过 `loose` subject match 接收 epithelioid sarcoma、其他 sarcoma 的形态和鉴别列表；同一多层错误会让它得分又让完整 SCC 失分。

## 2. 四种不存在的 IHC 阳性，给竞争者累计加分

旧 raw1052/1164（desmin）、1053/1165（h-caldesmon）、1167（myocardin）、1168（p16），在四臂均有相应断言。来源是 leiomyosarcoma 组织学说明，old gid560792、v2 gid585820/585821：不同平滑肌标志以及在特定形态亚型、对照 leiomyoma 时使用的附加染色。这些大部分具有可追踪原文；问题不应归为无来源幻觉。

患者提供的是 vimentin、α-SMA、p63、p53、CD68 阳性和 pan-cytokeratin 阴性。引擎却把上述 **四种未测/未报告染色** 分别连接到 **vimentin staining**，每种贡献约 +0.305，总实际分差为 **+1.222**。这里不能因为都叫 staining 就承认等价，也不能因患者的 α-SMA 阳性而补出 desmin/h-caldesmon 阳性。p53染色≠p53基因突变、p40核染色≠轻度核增大也在父类池出现，属于相同槽位失守。

仅屏蔽四种错接，old_v2 的 Leiomyosarcoma 从24.840降至23.618，原第2的 Osteosarcoma 保持23.922并成为第1；其他三臂第1不变。**局部软错误已经足以改变两个干扰诊断的顺序**，却仍不足以把完整 SCC 提上来，因为它尚未获得自己的断言。这解释了为什么不能仅用删错前后 top1 是否变成金标评价修复是否抓对机制。

## 3. 从3次到8/9次：v2补充内容怎样进一步压低正确候选

旧索引完整 SCC 受3次 -0.5；v2旧提示词8次、新提示词9次。以下 old_v2 的8条是全部处罚，不是抽取到的前几条展示：

| representative raw | 处罚从哪个候选发出 | 源实际内容 / source gid | 错误触发链 |
|---:|---|---|---|
| 109 | Carcinoma | 真菌/皮肤感染鉴别短列表：atypical mycobacterial disease、BCC等；514240 | 无命题主体的列表→focus Carcinoma；atypical词接患者异型细胞；BCC comparator 广播到完整SCC |
| 113 | Carcinoma | Cystinuria条目下肿瘤鉴别列表，515488 | renal carcinoma只是列表项；变成鉴别谓词并通过 carcinoma 字符匹配处罚SCC |
| 2293 | Carcinoma | 肺黏液表皮样癌的鉴别列表，605952 | 肺/亚型范围丢失，SCC名称接异型细胞，被当作反SCC证据 |
| 3681 | Malignant Spindle Cell Sarcoma | 梭形甲状腺肿瘤应与髓样癌等区别；334584 | “需要鉴别”不等于已有阳性判别项；甲状腺范围丢失 |
| 192 | Gingival Fibrosarcoma | 物理/化学口腔黏膜损伤的鉴别列表；396885 | 来源主体错写Gingival Granuloma，再错绑定Fibrosarcoma；SCC名字变反SCC证据 |
| 2925 | Leiomyosarcoma | **clear-cell SCC** 对clear-cell acanthoma/RCC的鉴别说明，669564 | 上一亚型范围串到Sarcoma；再绑定Leiomyosarcoma |
| 3075 | Leiomyosarcoma | epithelioid sarcoma 的恶性鉴别候选列表，752332 | raw主体是epithelioid sarcoma，不是Leiomyosarcoma；SCC名字接梭形细胞 |
| 2985 | Sarcomatoid Carcinoma | 胸膜肉瘤样间皮瘤和肺肉瘤样癌的GATA3鉴别，133240 | 原主体PSM错绑；未测GATA3接 **nuclear enlargement**，从而反向扣SCC |

这些是 **有来源但没有当前病例可用判别效力** 的断言，非纯粹 random noise。gate 通常保留 `distinguishes_from`，L4 在 survivor 中看见任何 present finding 即扣 comparator；它不要求“病例实际具备区分两病的证据”。同一个 carcinoma comparator 又可经宽泛 concept_match 同时扣完整亚型、父类和大小写重复候选。

来源差量也能定位：514240、515488、605952、396885 对应文档标题在本例旧 retrieval 中不存在；这是新索引检索组成增加的上下文，不是固定同段文本上提示词改变。clear-cell SCC 的对应旧 gid635644 已有该句，v2 raw2925 这一有害输出不能归为“原来源没有”，而是窗口/任务与抽取变化。原来的甲状腺、epithelioid sarcoma、GATA3 三类错误在旧索引已存在。

## 4. 按原始行号逐次阻断，不把总分差臆断成独立效应

`56_wrong_L4_cumulative_N` 逐次屏蔽上表产生的 L4 对比，保留来源断言和其他阶段。old_v2 完整候选分数依次为 -4.0→-3.5→…→0，第22名到第17名。old_old 为 -1.5→-1.0→-0.5→0，第21名到第18名；free_v2 为 -4.5→…→0，第22名到第17名。结果证明它确实遭到渐进污染，但单取消处罚不能产生未分配的正证据。

处罚向多候选传播也使父类 Carcinoma 同时受益。例如 old_old 阻断第1个错误甲状腺对比后，父类由第6上升到第4；这不是完整诊断改善。不要把这个父类变化归给 SCC 的完整病理标准。

## 5. 不改候选顺序的主体归还探针

在冻结候选内容与顺序的条件下，唯一改变是：对 raw.subject **字面完整匹配** `Sarcomatoid squamous cell carcinoma` 的原始行，将生产 first-match 产生的绑定显式移回该既存候选。四臂分别移动80/88/80/84条原始输出行，全部原本落在Carcinoma；去重后数量见下表。每条 `force_bindings` 记录了 raw ID、原候选和目标候选，未增加任何新规则、事实或候选。其余错误照旧，因此这是主体归属的局部反事实，不是可部署“金标优先”策略或完整精确匹配重写。

| 臂 | 原完整名次 | 归还后去重断言 | 归还后名次/分数 | 同时阻断已审错L4与四种IHC错接 |
|---|---:|---:|---:|---:|
| old_old | 21 | 26 | **3 / 10.639** | **3 / 12.139** |
| free_old | 22 | 40 | **3 / 16.389** | **2 / 17.889** |
| old_v2 | 22 | 26 | **5 / 6.458** | **3 / 10.458** |
| free_v2 | 22 | 35 | **5 / 8.949** | **3 / 13.449** |

旧/旧归还后完整标签升到第3，历史唯一“金标”Carcinoma 却从第6降到第7；free_old 第7→8。**终点把临床范围更合适的移动读成proxy性能下降。** 归还后也不是所有被接回的谓词都语义正确：p40被接p63/核增大等问题仍在。新旧差异同样没有因绑定修正完全消失，v2的多余L4仍压完整诊断，两个竞争者的无关形态池仍大。

因此本例支持两层机制的联合解释：前面的父类抢占制造零证据正确候选，后面的列表/marker/比较器错误进一步剥夺它的相对地位。单修量词或单关闭 hard veto 均触不到这条损害链。

## 6. 结论边界

本例不属于旧索引7个proxy top-3。它却证明7/11的分母测量方式不适合回答完整诊断问题，并提供“部分诊断知识已被正确抽到，却在执行时改写归属”的直接反例。完整候选即使进第2/3也没有成为top1，不能宣称一组修复已解决该病例。余下要验证的是 marker身份、来源/患者病理角色、跨器官/亚型门槛、候选身份和同证据去重；不能简单按规则数给常见肉瘤补权。

证据：`judgments_skin_other.json` 中56-*，四臂 full trace，`run_skin_other_additional_probes.py`、`skin_other_additional_probe_results.json` 与完整gzip。
