# RCR-3：关系保留三调用系统的端到端否证与机制解剖

## 摘要

在冻结的 300 例 E6/E12 relation-challenge 开发集上，默认三调用 RCR-3 **没有优于同预算 Lite**。
根校正临床完整 Top-1 为 Lite 29/300、RCR-3 20/300、Compact4 18/300；Top-2 为 42、31、26。
RCR-3 相对 Lite 的完整 Top-1 差 −3.00pp（6 gain/15 loss，Holm q=.1567），Top-2 差 −3.67pp
（8/19，q=.1045）。方向稳定为负，但在三个预注册臂间比较校正后不显著。

更宽松的 complete+partial sensitivity 中，RCR-3 的 ITA Top-1/Top-2 分别低 8.67pp 和 9.33pp
（q=.0112/.00842）；但共同成功 259 例只低 2.70pp/1.93pp，均不显著。这个分解说明较大的
宽松端点损害主要由 RCR 的 38 个 schema failure（Lite 4 个）造成；在都成功的病例里，候选与排序
仍有大量正负翻转，却没有净收益。

机制层给出了明确原因。schema-valid skeleton 中 81/276 没有任何 relation；119 个 exact-span drop
里至少 69 个是根审计确认的物质性诊断证据；60 条 relation-type 分层边只有 29 条既正确又有信息，
20 条方向/类型错误或无支持；三个已经进入 raw registry 的 reference 又被固定 frontier 删除。selector
自称 `complete` 的 66 个冠军只有 9 个根完整，38 个是错误实体。RCR-3 因而未达到预注册的 relation
fidelity、exposure preservation 或 complete conversion 成功条件。

这不是“所有结构化推理无效”的证据。exact/frozen-synonym identity 没有发现危险误合并；typed view
确实救回少数完整复合对象；一次显式 comparator 仍比无比较有价值。被否证的是当前把生成式结构字段
当作可靠事实、用固定 priority 截断、再信任同一模型自报完整性的组合。

## 冻结设计

三个臂使用同一 300 例（DA 150、MCR 150）、同一 Llama 3.3 70B 模型族和相同 fail-closed 原则：

| 臂 | 调用 | 关键处理 |
|---|---:|---|
| `lite3_safe` | 3 | 两个完整病例独立 generator + 一个固定候选池 selector；exact/frozen synonym 聚合 |
| `rcr3_default` | 3 | relation/event skeleton + 一次 batched 三视图 typed generator + time/scope comparator |
| `compact4_true3gen` | 4 | 逐字节复用 Lite 前两 generator，再加第三个独立 subtype view + selector |

RCR-3 的三次调用不是 Lite 的简单重采样：它把一次 generator 预算改为 skeleton，并让第二次调用同时
生成 syndrome/anatomy、etiology/temporal、subtype/exception 三个 view。所有臂使用安全 exact identity，
不以 substring、Jaccard 或宽泛 subtype 自动合并实体。

主要分析集是 300 例 fail-closed ITA；共同成功只作 survivor-selected sensitivity。严格端点先于临床
screen 冻结；异质 DeepSeek v4 Flash 只扩展候选关系队列，最终高影响关系和机制解释由根审计负责。

## 执行完整性与 API 路径

| 臂 | served | semantic records | physical attempts | input tokens | output tokens | latency sum |
|---|---:|---:|---:|---:|---:|---:|
| Lite | 296 | 899 | 900 | 1,096,933 | 348,170 | 15,012.2 s |
| RCR-3 | 262 | 839 | 841 | 1,833,983 | 755,124 | 23,769.3 s |
| Compact4 新调用部分 | 175 | 476 | 581 | 752,144 | 201,981 | 8,019.6 s |

RCR 虽与 Lite 同为三调用，但因为长 skeleton、三视图 JSON 和 assessment，输入/输出 token 与累计延迟
显著更高。RCR 的 38 个失败包括 invalid relation 14、invalid requested object 10、invalid candidate type
13、decisive pair 1；Lite 只有 4 个。Compact4 的新增第三 generator 有 108 次只给一个候选、15 次
view 错误、1 次 type 错误，成为 125 个总失败的主因。

Llama 路由并非 Groq 单点：Lite provider response association 为 DeepInfra 457/Groq 442，RCR 为
437/403，Compact4 新调用为 274/239。运行使用环境提供的网络代理直连 OpenRouter；官方 OpenAI SDK
分支仍保留，当前 Python 环境因 SDK 不可用自动走 stdlib OpenRouter transport。异质 screen 的 Google/
DeepSeek 调用成功完成，没有 Google region unsupported 或公用机房 IP block，也未使用仓库 VPN/Clash。
真正的裸 `direct` 模式在该容器不能解析 DNS；“无需 VPN”指环境网络路径可用，不是取消环境代理。

## 严格端点：先验方向已经不利

严格 exact/frozen-synonym 结果为：

| 臂 | strict Top-1 | strict Top-2 | raw exposure | frontier exposure |
|---|---:|---:|---:|---:|
| Lite | 16 | 24 | 37 | 37 |
| RCR-3 | 7 | 12 | 19 | 16 |
| Compact4 | 8 | 15 | 24 | 24 |

RCR vs Lite strict Top-1 −3.00pp（2 gain/11 loss，Holm q=.0645），Top-2 −4.00pp（4/16，
q=.0355），raw exposure −6.00pp（4/22，q=.00160），frontier exposure −7.00pp（4/25，
q=.000311）。所以严格 Top-2 的显著损害不是 selector 单层造成：reference 在候选生成/保留之前就已少了。

严格命中全部位于 MCR；DA 因复合 stage、病因、部位和时间修饰，exact bridge recall 极低。严格端点
不能作为最终临床准确率，但 exposure 的配对损失仍是有效机制信号：宽松同义审计不能凭空恢复从未生成
或已被 frontier 删除的候选。

## 异质 screen 与根校正

DeepSeek screen 在 300 例中 299 例 schema-valid，覆盖 3,522 个预期 candidate ID；一例 malformed
response fail-closed。代理给出的完整 Top-1/Top-2 是：Lite 41/58、RCR 30/44、Compact4 23/36。

根审计覆盖：

- 每一个被任一臂选中且代理判 complete 的关系；
- 每一个代理/严格端点不一致病例中的被选关系；
- 唯一 screen failure；
- 每族 15 个冻结代理阴性病例；
- 共 109 例、375 个 candidate-reference 关系，且所有最终完整端点 discordance 都在根复核范围内。

代理的 104 个 selected-complete 中，根审计只保留 69 个，25 个降为 partial，10 个改为 not-equivalent。
全部 375 个高影响关系有 107 个三分类分歧。30 个代理阴性病例、106 个被选关系没有发现额外 root-
complete，说明本次 root correction 主要纠正 false positive，而不是只向一个方向压低某个臂。

典型代理错误包括：

- pulmonary syphilis → empyema/pleural empyema；病例可能不唯一支持 reference，但输出-reference 关系
  仍然是错误，不能因 empyema 在病例中真实存在就给 reference credit；
- hypoxia-induced thrombocytopenia → cyanotic congenital heart disease/TOF；后者是上游病因背景，不是
  请求对象；
- adenoid cystic carcinoma → chondroid syringoma；
- vesicular thyroid carcinoma → `vascular thyroid cancer`/`vascularized thyroid cancer`；缩写相同不能
  抵消词义损坏；
- autoimmune gastritis exact label 被 screen 因病例 identifiability 不足降级。根审计恢复其 output-
  reference complete，同时保留“病例是否唯一支持 reference”为独立问题。

最后一点是 E2 的必要性：relation 与 identifiability 必须分栏，不能在一个“equivalence”判断里混合。

## 根校正临床端点

### 完整等价

| 臂 | Top-1 | Top-2 | DA Top-1/2 | MCR Top-1/2 |
|---|---:|---:|---:|---:|
| Lite | 29 (9.67%) | 42 (14.00%) | 3 / 6 | 26 / 36 |
| RCR-3 | 20 (6.67%) | 31 (10.33%) | 3 / 6 | 17 / 25 |
| Compact4 | 18 (6.00%) | 26 (8.67%) | 1 / 2 | 17 / 24 |

RCR vs Lite ITA：

- Top-1：−3.00pp，15 loss/6 gain，bootstrap 95% CI [−6.00, 0.00]pp，raw p=.0784，
  Holm q=.1567；
- Top-2：−3.67pp，19/8，CI [−7.00, −0.33]pp，raw p=.0522，q=.1045。

共同成功 259 例：Top-1/Top-2 都是 −2.70pp（13/6 与 15/8），q=.501/.630。MCR ITA 的
Top-1 差 −6.00pp、Top-2 −7.33pp；DA 为 0，但 DA 的完整事件数太少，不能读成等效。

Compact4 vs Lite ITA Top-1 −3.67pp（15/4，q=.0576），Top-2 −5.33pp（21/5，q=.00748）。共同
成功 174 例 Top-1 为 +0.57pp（3/4），Top-2 为 0（5/5）。显著 Top-2 损害几乎全是第四调用的合同
失败，而不是成功调用中的稳定排序损害。

### Complete + partial sensitivity

| 臂 | Top-1 | Top-2 |
|---|---:|---:|
| Lite | 142 (47.33%) | 189 (63.00%) |
| RCR-3 | 116 (38.67%) | 161 (53.67%) |
| Compact4 | 68 (22.67%) | 106 (35.33%) |

RCR vs Lite ITA 为 −8.67pp（Top-1，q=.0112）和 −9.33pp（Top-2，q=.00842）；共同成功只为
−2.70pp 与 −1.93pp，均不显著。宽松端点强烈惩罚 schema failure，说明服务可靠性是端到端系统的
真实组成部分；但共同成功的大量 gain/loss 互抵也说明 RCR 并没有形成稳定的语义改善。

## 为什么关系骨架没有转化成收益

### 1. Span alignment 删除了决定性证据

119 个 drop 中至少 69 个为物质性证据，包括 May–Thurner 的完整 CT 压迫模式、VTC 的两处活检与
thyroglobulin、GI sarcoidosis 的 ACE/感染排除、TAPS 的双胎生长差、DILI 的 bilirubin、hypoxia-
thrombocytopenia 的 SaO2/Hct/platelet 三联。平均 grounding rate 没有体现 evidence value weighting。

51 个 generator invalid reference 随之出现。sanitizer 只删 ID，不删依赖该 ID 的 candidate，形成
“引用 fail-closed、候选语义 fail-open”。

### 2. Relation 正确性没有被程序验证

60 条分层人工审计中 20 条方向/类型错误或无支持，11 条只是浅共现/重复。特别是 `contradicts`、
`located_at`、`has_result`、`response_to` 会跨不可比较事实或反向连边。模型把 relation 字段填满，并不
等于保留了能区分候选的临床关系。

### 3. Candidate type 没有约束最终对象

typed view 能生成 RVO+CME、sacrococcygeal teratoma、APS、GI sarcoidosis 等有价值候选；但也把
manifestation、etiology、unsupported subtype 送入冠军位。HFrEF、stroke、renal hemorrhage、pelvic
bleeding、cholestasis 等对象退化在 selector 后仍存在，说明 `requested_object=disease` 只是 JSON 字段，
不是可执行 gate。

### 4. Frontier 在正确候选已存在时造成损害

May–Thurner、Takotsubo、pulmonary embolism 三例 raw exposure→frontier loss。PE 病例九候选同分，
exact PE 仅因稳定 ID 次序被删；Takotsubo generic core 被三个 subtype 和 CAD/MI 挤掉；May–Thurner
因 decisive CT drop 而被降分。安全 identity 解决了 overmerge，却没有解决 fixed-width undercoverage。

### 5. Selector 自报字段严重失准

`complete` 冠军只有 9/66 root-complete；38/66 not-equivalent。`strong` 冠军 230 个只有 20 个完整；
`temporal_scope_fit=fits` 仍有 76 个错误实体。没有外部校准时，这些字段只能解释模型如何自洽，不能
证明候选满足 reference scope。

## 真正的 rescue 与真正的 harm

最可信的 rescue：

- `DA_d2_seq100/214`：从 macular edema 提升到 RVO with CME，typed composite + comparator 共同作用；
- `MCR_seq200b/376`：从 shock manifestation 回到 sacrococcygeal teratoma，requested-object rescue；
- `MCR_v1_seq100/117`：从感染候选回到 APS，但 skeleton 零关系，收益不能归因 relation；
- `MCR_v1_seq100/46`：多部位 granuloma 使 GI sarcoidosis 胜 Crohn，虽 ACE 被 drop 仍救回。

最清楚的 harm：

- `MCR_seq200b/320`：pathognomonic CT 被删→May–Thurner support 失效→frontier 删除→DVT 冠军；
- `MCR_v2_seq100/208`：generic Takotsubo 被删→与 apical pattern 冲突的 mid-ventricular subtype 冠军；
- `MCR_v2_seq100/227`：exact PE 平分被删→正常冠脉/RV strain 未形成 veto→STEMI 冠军；
- `MCR_v1_seq100/76`：完整 DILI 候选存在，却被错误 pattern 的 intrahepatic cholestasis 取代；
- `DA_d2_heldout200b/459`、`MCR_seq200b/436/448/456`：从疾病/病因退化为表现或并发症。

这些病例把损害定位到具体阶段，而不是泛称“模型推理不好”。

## 预注册成功条件逐项判决

| 成功条件 | 结果 |
|---|---|
| relation fidelity 明显优于 E6 式生成图 | 否；20/60 分层边明确错误，另 11/60 浅关系 |
| 不降低 complete/reference exposure | 否；RCR raw −6pp、frontier −7pp，且三例 raw→frontier loss |
| complete exposure→Top-1 conversion 提高 | 否；完整 Top-1/2 均低于 Lite |
| 新增 typed candidate 的 gain 多于 interference loss | 否；ITA 6 gain/15 loss（Top-1） |
| 默认三调用优于简单三调用 | 否；共同成功与 ITA 均无正净效应 |
| 第三独立 generator 有边际收益 | 否；共同成功近零，ITA 被 schema failure 显著拖累 |
| 安全实体聚合不发生宽泛误合并 | 本轮通过；但 frontier 另有 undercoverage |

## 解释边界

1. 这是 300 例开发集，不是外部确认集；不做“总体临床模型优劣”的外推。
2. 根审计穷尽 endpoint-critical selected relation，不穷尽 3,533 个所有未选 candidate relation；剩余关系
   明确标记 heterogeneous proxy provenance。
3. relation 分层样本等额而非 prevalence-weighted；29/60 不能直接当总体 precision。
4. 完整关系与 reference identifiability 分离。病例可以不唯一支持 reference，但 exact output 仍与 reference
   相同；反之，病例中真实存在的 manifestation 不因此等价于 reference。E2 专门估计这两轴。
5. provider 路由未随机化；用户已排除纯粹为降方差进行 provider 统一/重复运行，本实验不据路由做因果结论。

## 可执行结论

默认部署应保留 Lite 的两独立 proposal + 一次显式 comparator，而不是切换到当前 RCR-3。下一版只应
保留四个经过本轮支持的思想：原文 provenance、exact/safe identity、显式 typed composite proposal、
一次固定池候选比较。以下部分必须重做后再独立检验：程序 offset span、typed relation ontology、引用闭包、
requested-object hard gate、非支配 frontier、selector completeness calibration。

RCR-3 已完成其可证伪目的：它把一个听起来合理的“关系保留三调用”方案拆成可检查部件，并证明当前
实现的关系、覆盖和校准不足以抵消额外结构与 schema 脆弱性。
