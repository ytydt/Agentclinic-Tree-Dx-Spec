# RCR-3 根级机制手工审计

## 审计责任与边界

本审计由根审计员直接读取冻结病例、三臂 stage 文档、候选 registry、selector
assessment 和最终输出完成。DeepSeek v4 Flash 只用于扩大临床关系审计队列；它没有给本文件的
机制结论投票，也没有替代根审计员。`root_relation_reviews.jsonl` 已逐一复核 375 个被任一臂选中的
高影响 candidate-reference 关系；本文件进一步解剖其上游因果链。

机制审计包含四个互补范围：

1. 对 594 条已通过程序校验的关系，按十种 relation type 各固定抽取六条，共 60 条；逐条核对
   source、target、方向、relation type、justification span，局部元组不足时回读病例全文。
2. 穷尽列出 119 个被 exact-span sanitizer 删除的 observation，并逐条标记一个保守的“物质性诊断
   证据”下界；`false` 不代表无临床意义。
3. 穷尽审查 51 个 invalid evidence reference、三个 raw-registry→frontier reference loss，以及
   262 个成功 RCR selector 的冠军自评与根临床关系。
4. 对完整端点的 RCR gain/loss、Compact4 gain/loss 和失败恢复病例回读实际轨迹，避免把计数当成
   机制解释。

60 条关系是 relation-type 等额分层样本，适合证明错误机制存在及跨类型分布，不是对 594 条边的
prevalence-weighted 总体误差率估计。所有可复核明细在 `mechanism_*.jsonl`。

## 先给结论

RCR-3 的负结果不是一个单一 selector 偶然选错，而是三个串联瓶颈相互放大：

- exact-span guard 能阻止伪造 evidence ID，却会非随机删除格式稍有变化的高价值证据；
- 类型化生成确实偶尔补出正确复合对象，但 type 是标签而不是约束，etiology、manifestation、subtype
  仍可被送入同一冠军位；
- exact/frozen-synonym 聚合没有发现宽泛误合并，这是设计中真正成功的安全部件；但固定八位 frontier
  又在三个病例中删除了已经生成的 reference；
- selector 输出了 `completeness`、`temporal_scope_fit` 等看似可审计字段，但这些字段与根关系严重失准，
  因而没有形成可靠 veto。

所以，本实现否证的是“当前生成式 skeleton + 自报类型/完整性 + 固定宽度打分”足以让三次调用优于
简单两生成器加比较器，不是否证保留关系本身的研究方向。

## 关系骨架：有 JSON，不等于有正确关系

276/300 个 skeleton 通过 schema；它们保留 3,169/3,288 个 observation，生成 594 条关系。但
81/276 个 schema-valid skeleton（29.3%）一条关系都没有。换言之，“schema-valid”与“relation-
preserving”不是同一个事件。

根审计的 60 条等额分层关系如下：

| 根判定 | 数量 | 含义 |
|---|---:|---|
| valid informative | 29 | 方向、类型和依据成立，并增加可用的事件/因果/解剖信息 |
| valid but shallow/redundant | 11 | 技术上可成立，但只是共现、重复描述或同一观察的改写 |
| wrong direction/relation type | 11 | 两端事实可能有关，但箭头方向或谓词错误 |
| unsupported | 9 | justification 不支持该边，或两事实根本不构成所声明关系 |

即使不把 11 条浅关系算错，也有 20/60 明确错误；只有 29/60 同时具有语义正确性和信息增量。
几个故障模式很稳定：

- `contradicts` 最危险。`MCR_v1_seq100/3` 把 positive straight-leg raise 与 negative femoral
  stretch 当成互相矛盾；它们测试不同神经牵拉。`MCR_v2_seq100/213` 更把“无肝酶升高/嗜酸细胞
  增多/淋巴结病”编码为与 triamcinolone/hydroxyzine 治疗矛盾，事实类型都不在同一命题空间。
- `located_at` 经常退化为“同段文字里有两个解剖词”。`MCR_v2_seq100/202` 把“腭骨未受累”作为
  source，指向“硬腭肿块”；这是 scope/exclusion，不是 source located at target。
- `has_result` 频繁反向。`DA_d2_seq100/19` 是骨病灶活检见甲状腺滤泡，而骨病灶不是“甲状腺细胞
  的检测结果”；正确结构应是 biopsy/test → histology result，并另建 result supports diagnosis。
- `response_to` 也会倒置或过度解释。`MCR_v1_seq100/112` 把补液/升压/胺碘酮与 agitation 直接相连，
  原文并未说躁动对该组合治疗的响应。
- 大量 `associated_with` 与 `same_episode_as` 只是同一次检查的两个描述。例如 coffee-ground vomit
  与 hematemesis、同一肿块的 X 线与超声表现。它们可用于 provenance grouping，却不是区分诊断的
  独特关系证据。

这解释了为什么“594 条 grounded relation”没有带来稳定收益：程序只验证 fact ID 与原文 span
存在，不能验证命题方向、对象类型和临床蕴含。关系字段本身是新增主张，不是无损格式。

## Grounding：96.4% 的平均数掩盖了高价值尾部

sanitizer 删除 119/3,288 个 observation，表面 grounding rate 为 96.38%。根审计逐条读取全部
119 个 span，至少 69 个、涉及 42 个病例，是诊断确认、重要排除、表型定义或决定性时序/病因证据。
这是保守下界；未列入的 WBC、ECG、阴性检查不因此被宣告无用。

删除不是随机字符噪音，而常由标题式字段、冒号、Unicode、列表化影像文字或模型轻微改写触发：

- `MCR_seq200b/320` 删除了“右髂总动脉压迫左髂总静脉并见充盈缺损”的整条 CT 证据。生成器仍产出
  May–Thurner，但其 support/unique fact 失效，priority 降到 −0.5，随后 reference 被 frontier 删除。
- `DA_d2_seq100/139` 同时删除 thyroglobulin 4432、肋骨活检指向 VTC 转移、鼻窦肿物活检确认 VTC
  转移。之后模型把 `vesicular` 错读成 `vascular/vascularized`，异质代理还曾把该损坏标签判为完整。
- `DA_d2_heldout200b/532` 删除 CT 与 MRI 两条脂肪性 SVC/interatrial mass 证据，继而产生八个 invalid
  fact reference；候选标签仍保留并参与排序。
- `MCR_v1_seq100/46` 删除 elevated ACE 以及三条感染性排除，正好削弱 GI sarcoidosis 相对 IBD 的
  决定性对比。RCR 最终仍救回 sarcoidosis，是依靠其余多部位 non-caseating granuloma，而不是
  sanitizer 成功。
- `MCR_seq200b/345` 删除 phosphate、两种 vitamin D、PTH、FGF23 四联实验室模式；`DA_d2_seq100/29`
  删除 IgG4 和 Streptococcus culture；`MCR_v2_seq100/208` 删除冠脉造影信息。它们都是需要关系化
  的证据，恰恰最容易因长 span/结构化文本失败。

因此，exact containment 适合作为“不得凭空引用”的安全下界，却不适合作为唯一的 source alignment。
下一实现需要保存字符 offset 或由程序从原文切片产生 span；模型只能选择 offset，不能重新抄写 span。

## Invalid reference 的 fail-open 语义

共有 51 个 invalid fact reference，分布于 9 个病例。程序正确地删掉了不存在/已丢弃的 fact ID，
但没有删除依赖这些 ID 的候选。例如 May–Thurner、GI sarcoidosis、follicular thyroid metastasis 和
IgG4-related disease 的 unique evidence 被删后，候选标签仍进入 registry。

这避免了“伪证据 ID 被 selector 当真”，却没有实现候选级 fail-closed。结果是：

1. registry priority 因 evidence 数减少而改变，可能把正确候选送出 frontier；
2. selector 看到一个语义上由病例启发、形式上却证据不足的标签；
3. 模型可再次仅凭标签常识把它评为 `strong/complete`。

所以 evidence sanitizer 的合同应是引用闭包：若 candidate 的声明依赖被删除的 unique/support fact，
必须重算其 obligations/priority，并在零有效 support 时删除或显式降级 candidate，而不是只清空 ID。

## 类型化候选：有真实 rescue，也有“类型贴纸”

三视图确实产生了 Lite 不容易构造的完整对象：

- `DA_d2_seq100/214`：subtype/composite 视图生成 “Retinal Vein Occlusion with Cystoid Macular
  Edema”，selector 将其判为完整并从 Lite 的 “Macular Edema”/“CME”中救回。
- `MCR_seq200b/376`：syndrome/anatomy 视图直接生成 sacrococcygeal teratoma，避免 Lite 把
  hemorrhagic/hypovolemic shock 当最终对象。这是本实验最干净的 requested-object rescue。
- `MCR_v1_seq100/117`：subtype 视图生成 antiphospholipid syndrome/primary APS，压过 Lite 的 RSV
  与 infectious mononucleosis；但 skeleton 在此病例为零关系，收益来自候选覆盖与比较器，不可归因于
  relation graph。
- `MCR_v1_seq100/46`：GI sarcoidosis 压过 Crohn disease，是多解剖部位 granuloma 的有效整合；同样
  伴随 ACE/感染排除被删，说明 rescue 与 grounding 缺陷并存。

但候选 type 只是模型自报字段。RCR 的 262 个冠军中，root-not-equivalent 仍大量带有 `subtype`、
`etiology`、`composite` 标签；贴上 subtype 并不会让其范围正确。代表例：

- `MCR_seq200b/251` 的 “TAPS with Tetralogy of Fallot” 被 selector 自评 `complete/strong`，但 TOF
  是无支持的额外复合组件；
- `MCR_v1_seq100/76` 将 “Intrahepatic Cholestasis” 自评 `complete/strong`，压过完整的 DILI，
  尽管病例是 hepatocellular pattern、MRCP 正常，且该标签遗漏药物病因；
- `DA_d2_heldout200b/459` 选择 HFrEF 这一表现而不是 tachycardia-induced cardiomyopathy；
- `MCR_seq200b/436` 选择 renal hemorrhage 而不是 renal artery aneurysm；`MCR_seq200b/448` 选择
  stroke 而不是 TTP；`MCR_seq200b/456` 选择 renal pelvis hemorrhage 而不是 ureteroarterial fistula。

这些错误不是“候选池没有答案”，而是最终对象类型没有成为硬约束。

## 安全实体聚合成功，但 frontier 保护失败

本实现只按 exact normalized label/frozen synonym 合并，没有发现 E7 式 substring/Jaccard 把不同
亚型或复合对象误合并。这一负面证据很重要：RCR 的主要损害不能归因于宽泛实体合并。

然而 main-6 + protected-2 frontier 在三个病例把已存在 reference 删除：

- `MCR_seq200b/320`：May–Thurner 得分 −0.5，被 DVT、left-leg swelling、venous stasis 等保留；
  根因是决定性 CT span 先被删，导致 support 失效。
- `MCR_v2_seq100/208`：generic Takotsubo 得分 3.5，被 mid-ventricular/apical/atypical 三个 subtype、
  ACS/CAD/MI 等挤掉；selector 只能在错误 subtype 与鉴别诊断中排序，最终选了与 apex akinesia 冲突的
  mid-ventricular subtype。
- `MCR_v2_seq100/227`：九个候选全部同分 5.5，stable ID 次序把 exact pulmonary embolism `C003`
  删除，却保留 STEMI、NSTEMI、cardiac ischemia 和 RV infarction。这里不是证据不足，而是 tie-break
  直接改变临床覆盖。

“protected”只保护模型标记 rare/low-prior 或规则命中的候选，并不保护不同 view 的核心 disease、
包含 requested-object 的候选、或与强 exclusion 成对的候选。安全 frontier 至少要满足：每个 view/对象
类型的非支配候选保留；若 exact core 与其 subtype 同时存在，core 不能因固定 k 被全部 subtype 挤掉；
tie 不得按 opaque ID 产生临床语义。

## Selector 字段没有形成可用的安全证书

把 selector 的冠军自评与根 relation 对齐后：

| selector 自评 | root complete | root partial | root not equivalent |
|---|---:|---:|---:|
| complete | 9 | 19 | 38 |
| partial | 10 | 77 | 104 |
| manifestation | 1 | 0 | 4 |

也就是说，自评 `complete` 的 66 个冠军只有 9 个根完整（13.6%）；38 个是错误实体。`strong` 同样
不是校准概率：230 个 `strong` 冠军里只有 20 个根完整。`temporal_scope_fit=fits` 的冠军为
10 complete、41 partial、76 not-equivalent。

这不是因为根审计对所有短标签都苛刻。错误包括对象类别完全不同的肺梅毒→脓胸、低氧性血小板减少
→发绀型先心病、DILI→胆汁淤积、PE→STEMI，以及把 `vesicular` 改成 `vascular`。这些不是边界同义词。

结构字段之所以失效，有三个可见原因：

1. obligations 是模型先生成的通用词（大量病例都是 anatomy/cause/time/subtype），不是由 reference-
   blind task ontology 或问题语法确定；满足/缺失也由同一模型自评。
2. selector 只在冻结 frontier 内比较。gold 被 pruning 后，任何 `complete` 都只是池内相对自信。
3. counterexample_check 是自由文本声明，没有机器验证它引用的 decisive exclusion。`MCR_v2_seq100/227`
   明明有正常冠脉和 RV strain，仍把 STEMI 选为冠军。

因此 comparator 的输出字段可用于审计日志，不能被当作经过验证的安全信号或停止规则。

## Compact4：第四调用主要测试了合同脆弱性

Compact4 真正增加第三个独立 generator，并逐字节复用 Lite 的前两个 generator 文档。新增调用中：

- 108 个病例只返回一个候选，违反 2..6 行合同；
- 15 个病例 view 不是 `subtype_exception`；
- 另有一例 invalid candidate type；连同继承的一例 selector 错误，最终仅 175/300 served；
- 可解析的新候选中有 586 个 `disease`，只有 6 个 `subtype`，说明“第三 subtype view”实际上大多退化为
  又一份 disease list。

ITA 下完整 Top-2 比 Lite 低 5.33pp（21 loss/5 gain，Holm q=.00748），但共同成功 174 例中 Top-2
正好 5 loss/5 gain，Top-1 为 3 loss/4 gain。故显著损害几乎完全由 schema/可用性失败造成；在成功
子集中，没有可识别的第三生成器边际收益。

少数真实 rescue（basosquamous composite、schwannoma、contrast encephalopathy 等）证明独立新增候选
偶尔有价值；但它同时引入大量错误候选和失败，不能以“更多调用”概括为正机制。

## RCR 相对 Lite 的病例轨迹

根完整 ITA Top-1 的 RCR vs Lite 是 6 gain/15 loss；Top-2 是 8 gain/19 loss。共同成功 259 例仍为
Top-1 6/13、Top-2 8/15，方向未被失败完全解释，但校正后不显著。损失可分为：

1. **上游失败**：38 个 RCR schema failure 对比 Lite 4 个；复杂 schema 本身增加不可用性。
2. **gold 已生成后被 frontier 删除**：May–Thurner、Takotsubo、PE 三例。
3. **对象退化**：tachycardia cardiomyopathy→HFrEF、TTP→stroke、aneurysm→hemorrhage、fistula→bleeding。
4. **错误 subtype/额外组件**：apical Takotsubo→mid-ventricular；TAPS→TAPS+TOF；generic RA→错误
   seronegative/反应性关节炎候选竞争。
5. **benchmark identifiability 混杂**：`MCR_v1_seq100/95` 的 HIV-associated TB 与 reference 关系完整，
   但病例没有培养/分子证据支持 TB；该 RCR gain 是贴合 benchmark reference，不等同于病例推理正确。

收益则主要集中于：完整复合候选首次进入（RVO+CME、sacrococcygeal teratoma）、候选对象从表现回到
病因（APS、sarcoidosis），以及 selector 对冻结池的一次有效比较。只有部分收益需要关系边；APS 的
skeleton 为零关系，证明不能把全部 RCR gain 归给 skeleton。

## 组件级判决

| 组件 | 判决 | 证据 |
|---|---|---|
| 原文 span + provenance | 方向正确，但当前 exact-copy 实现失败 | 阻止伪引用；119 drops 中至少 69 条物质性证据 |
| 关系 skeleton | 当前实现被否证 | 81 个零关系；分层样本 20/60 明确错误、11/60 浅关系 |
| 三种 typed view | 局部有效，未形成硬合同 | 有复合对象 rescue；type 自报且错误 subtype/etiology 可夺冠 |
| exact/frozen synonym aggregation | 通过本轮安全检查 | 未发现宽泛误合并 |
| main-6/protected-2 frontier | 被否证 | 三个已暴露 reference 被删除；一例纯 tie-ID 决定 |
| time/scope-aware comparator | 当前自评字段被否证 | 66 个 self-complete 仅 9 个 root-complete |
| 第三独立 generator | 无可识别净收益，可靠性失败 | ITA 损害；共同成功近零；123 个新增调用合同失败 |

## 可证伪的后续实现约束

若继续研发而不是停在本轮负结果，下一版必须预注册并满足以下硬条件：

1. span 由程序 offset 切片；不得要求模型逐字复制长 span。物质性 evidence drop 必须从 69/119 的
   当前下界显著下降，并单独报告，不能只报总体 grounding rate。
2. relation edge 需要双向类型合同，例如 test→has_result→finding、condition→causes→manifestation；
   `contradicts` 两端必须属于可比较命题并显式记录 time/scope。根分层样本的 wrong/unsupported 必须
   明显低于本轮 20/60。
3. candidate 必须满足 requested-object 类型；manifestation/etiology 只能作为解释节点，除非问题明确
   请求它们。零有效 support 的 candidate fail-closed。
4. frontier 必须证明 raw exposure 不下降；至少按 view/核心 disease/subtype 做非支配保护，不能用
   opaque ID 处理平分。
5. selector 的 `complete` 必须在冻结校准集上达到预注册 precision；本轮 9/66 不能作为可用 gate。
6. 新调用的 marginal utility 必须在共同成功与 ITA 同时报告；若 schema failure 主导结果，不得把
   survivor-only 小幅变动描述为推理收益。

本轮已经足以停止默认部署 RCR-3：它没有达到“关系保存提高完整 exposure→Top-1 conversion”的预注册
成功条件。值得保留的是安全 identity、原文 provenance 的目标、typed composite proposal 以及一次显式
候选比较；需要重做的是 span alignment、relation semantics、candidate-object contract、frontier 和
selector calibration。
