# E11：B07 检索 × refine 八臂因子实验的病例轨迹与机制解剖

## 判定

E11 没有证明“检索增强”优于无检索，也没有证明“检索本身必然有害”。它更精确地证明了三件事。

第一，当前被命名为 `relevant` 的处理只是**病例 query 与 Merck 段落的 TF-IDF query-top bundle**，不是经临床验证的高质量 RAG。325 个可审计病例中，`relevant` 的 1,950 个 chunk 只有 129 个（6.62%）被判为 case-specific fit，1,397 个（71.64%）无病例适配；160/325 个 bundle 对 reference 的支持完全 absent。相反，`hard_negative` 仍含 51 个同病 chunk、9 个病例定义亚型 chunk，84/325 个 bundle 对 reference 有 direct/partial support。处理操纵因此只足以识别“弱词法 bundle 被强制注入后的行为”，不能识别理想 RAG 与 no-RAG 的差异。

第二，在该处理定义下，query-top `relevant` 相对 `off` 的方向稳定地偏负，但证据没有通过七重比较校正。预注册 strict Top-1 为 29/400→24/400（`−1.25 pp`，5 loss/0 gain，McNemar `p=.0625`，Holm `q=.4375`）；根审计校正临床完整等价后为 77/400→69/400（`−2.00 pp`，10/2，`p=.0386`，`q=.2700`）。Top-2 临床完整等价为 97/400→90/400（`−1.75 pp`，9/2，`p=.0654`，`q=.4580`）。一旦允许疾病族正确但部位、病因、慢性度或分子修饰不完整，Top-1 变为 164/400→166/400（`+0.50 pp`），Top-2 为 219/400→220/400（`+0.25 pp`）。这说明主要损伤不是把所有病例推到完全无关疾病，而是**把具体诊断压平为泛病种、把病因降为表现、或删除少见而具体的第二候选**。

第三，generic refine 是高行为强度、低净端点效应的模块。四个条件合计有 176/400 个病例至少一次改变，单臂 Top-1 改变 39–70 例，但 strict 和临床完整等价的七个主比较无一通过 Holm 校正。仅在“完整或部分正确”的代理敏感性端点，`off` 条件 refine 为 164/400→178/400（`+3.50 pp`，5 loss/19 gain，`p=.00661`，`q=.0463`）。这个结果符合 refine 把错误或过窄候选拉回正确疾病族的机制，但它不是预注册 primary，且多数非关键病例仍使用异质 LLM proxy，不能把它升级为确认性收益。

最可靠的系统结论是：**当前 B07 的主要问题不是有没有一次 generic refine，而是检索入口缺少临床相关性和实体/范围约束；refine 偶尔能修复粒度与排序，却也会系统性删除少见候选、把病因降为表现，无法作为安全兜底。**

## 设计与可识别边界

E11 在同一 400 个开发病例上冻结历史 B07 target-blind orchestrator 输出，DA/MCR 各 200。每例构造四个字符量级匹配的知识条件，再与 refine off/on 正交交叉：

| 检索条件 | 操作定义 | 可回答的问题 |
|---|---|---|
| `off` | 不提供 knowledge chunks | 无外部上下文的生成/排序基线 |
| `relevant` | 病例 query 的 query-top 段落 | 当前词法检索注入的联合效应 |
| `random` | outcome-blind 稳定随机段落 | 同量无关上下文负载 |
| `hard_negative` | query-near、排除命中 article 的段落 | 邻近竞争上下文；不是临床假证据保证 |

refine-off 直接生成 Top-2；refine-on 看到同一病例、同一知识 bundle、该条件 draft Top-2 后再排序或替换。七个预注册比较为三项 refine-off 检索比较，以及四项检索条件内的 refine 比较。病例是配对推断单位；Top-1 为 primary，Top-2 secondary。所有 schema/transport 失败 fail-closed，不按结果筛选或补跑。

该 4×2 设计隔离的是“传入模型的 bundle 条件”和“是否进行第二次 refine”，并未固定 OpenRouter 的实际后端 provider。因此它不是 provider-normalized 模型重复性试验。按用户明确排除，也没有把重复多跑、统一 provider/retry 或扩容确认集重新包装成科学臂。

## 审计责任与端点层级

三个端点被有意分开：

1. `strict`：冻结 exact/safe-synonym bridge，是预注册 primary，但对拼写、同义、部位/修饰语敏感；
2. `clinical_complete`：候选与 reference 临床完整等价；
3. `complete_or_partial`：进一步接受疾病族正确但范围欠具体的候选，只作敏感性分析。

DeepSeek v4 flash 只承担候选关系与检索证据的队列扩展分包。根审计逐候选覆盖全部 17 个 strict Top-1/Top-2 discordance 病例、全部 clinical-complete `relevant↔off` Top-1/Top-2 discordance，以及 7 个 candidate-screen 失败病例；去重后为 32 条深轨迹、39 个候选审计病例、624 个 arm-rank occurrence。其余 5,776 个 occurrence 保留异质 proxy，而不是被称为人工 gold。

代码设有硬断言：当前 6,400 个 arm×rank occurrence 必须全部解析；7 个 candidate-screen 失败必须全部有根 override；所有 clinical-complete `relevant↔off` discordance 必须在 deep-review 集合中。根判断与有效 proxy 在 16 个候选关系上分歧，其中包括把 cryptococcosis 当作 cutaneous histoplasmosis 的可接受变体，以及把 severe sepsis 当作“septic shock with anuric kidney failure”的完整等价。报告以下关于关键翻转的判断以根审计为准。

## 八臂端点全景

| 臂 | strict Top-1 / Top-2 | clinical complete Top-1 / Top-2 | complete+partial Top-1 / Top-2 |
|---|---:|---:|---:|
| off, refine off | 29 / 34 | 77 / 97 | 164 / 219 |
| off, refine on | 27 / 33 | 80 / 99 | 178 / 223 |
| relevant, refine off | 24 / 30 | 69 / 90 | 166 / 220 |
| relevant, refine on | 23 / 27 | 73 / 89 | 171 / 220 |
| random, refine off | 24 / 29 | 73 / 95 | 166 / 228 |
| random, refine on | 25 / 28 | 77 / 94 | 174 / 228 |
| hard-negative, refine off | 27 / 32 | 73 / 94 | 160 / 223 |
| hard-negative, refine on | 27 / 31 | 76 / 95 | 170 / 222 |

绝对 strict 率只有 5.75%–8.50%，临床完整等价约 17.25%–24.75%，而疾病族完整或部分正确的 Top-1 为 40.0%–44.5%。同一输出在三层端点间的巨大跃迁说明 E11 的首要诊断对象问题是**本体身份、复合范围和具体度**，不是可以被一个 exact accuracy 概括的模型能力差。

### 七个预注册 Top-1 比较

表中 discordance 为 left-only/right-only；差值均为右减左。

| 比较 | strict 差值；discordance；p/q | clinical complete 差值；discordance；p/q |
|---|---:|---:|
| off → relevant，无 refine | −1.25 pp；5/0；.0625/.4375 | −2.00 pp；10/2；.0386/.2700 |
| random → relevant，无 refine | 0；2/2；1/1 | −1.00 pp；7/3；.3438/1 |
| hard-negative → relevant，无 refine | −0.75 pp；4/1；.375/1 | −1.00 pp；7/3；.3438/1 |
| off 条件 refine | −0.50 pp；3/1；.625/1 | +0.75 pp；3/6；.5078/1 |
| relevant 条件 refine | −0.25 pp；3/2；1/1 | +1.00 pp；1/5；.2188/1 |
| random 条件 refine | +0.25 pp；0/1；1/1 | +1.00 pp；0/4；.125/.750 |
| hard-negative 条件 refine | 0；1/1；1/1 | +0.75 pp；1/4；.375/1 |

clinical-complete 的 relevant-vs-off bootstrap 95% CI 为 `[−3.75,−0.50] pp`，但 McNemar 的七重 Holm 校正不显著；不能用未校正区间跨不过零替代预注册多重比较合同。Top-2 同样没有 Holm survivor。DA 与 MCR 的 clinical-complete Top-1 relevant-vs-off 都恰为 `−2.00 pp`（各 5 loss/1 gain），不是单一数据源驱动；Top-2 分别为 DA `−2.50 pp`、MCR `−1.00 pp`。

历史 gate=false 的 61 例表现为 Top-1 `−6.56 pp`（4/0），gate=true 的 339 例为 `−1.18 pp`（6/2），但两层内七重校正均不显著。gate 是历史产物且不是 E11 随机因素，这一差异只能用于定位病例，不能称为已验证 moderator。

### 部分正确敏感性端点

| 比较 | complete+partial Top-1 差值 | discordance | p | Holm q |
|---|---:|---:|---:|---:|
| off → relevant，无 refine | +0.50 pp | 13/15 | .8506 | 1 |
| random → relevant，无 refine | 0 | 6/6 | 1 | 1 |
| hard-negative → relevant，无 refine | +1.50 pp | 6/12 | .2379 | .9515 |
| off 条件 refine | +3.50 pp | 5/19 | .00661 | .0463 |
| relevant 条件 refine | +1.25 pp | 8/13 | .3833 | 1 |
| random 条件 refine | +2.00 pp | 4/12 | .0768 | .3841 |
| hard-negative 条件 refine | +2.50 pp | 5/15 | .0414 | .2483 |

只有 off-refine 的 broad sensitivity endpoint 通过七重校正。它与 clinical-complete 只有 +0.75 pp 的差别联合说明：refine 更常把答案从无关或错误实体拉回正确疾病族，而不是恢复 benchmark 所要求的部位、病因、亚型和复合对象。由于该端点非 primary，且并未对其全部 24 个 discordance 作 root candidate-by-candidate override，它是下一版 comparator 的机制线索，不是确认性优越结论。

## 检索操纵实际上提供了什么

检索证据 screen 对 400 个病例均完成 HTTP 调用，325 个通过严格 schema，75 个格式/枚举错误原样保留。以下只在 325 个有效病例上描述 bundle；该 screen 看到生成 Top-1，属于 post-treatment manipulation audit，不能把其分层当随机 moderator。

| bundle | reference absent | direct/partial reference support | misleading=yes | case-specific chunks | no-fit chunks |
|---|---:|---:|---:|---:|---:|
| relevant | 160/325 | 154/325 | 38/325 | 129/1,950 | 1,397/1,950 |
| random | 312/325 | 3/325 | 24/325 | 13/1,950 | 1,879/1,950 |
| hard-negative | 226/325 | 84/325 | 31/325 | 41/1,950 | 1,532/1,950 |

chunk 关系进一步揭示命名误导。`relevant` 中 933/1,950 为 generic/unrelated，471 为 broader context，只有 213 为 direct same disease、24 为 defining subtype，同时含 71 个 competing-diagnosis chunk。`hard-negative` 中有 128 个 competitor chunk，符合设计意图，但也混入 60 个 direct/subtype reference chunk。`random` 最接近纯上下文负载，却仍有 12 个同病 chunk。

在这 325 个 screen-valid 病例上，`relevant` 相对 off 的 clinical-complete Top-1 为 `−1.85 pp`（7/1，`p=.0703`）；random 为 `−1.54 pp`（6/1），hard-negative 为 `−1.23 pp`（5/1）。三种 bundle 都偏负、且 relevant 没有明显优于 random，符合“上下文负载、注意力稀释和邻近概念锚定”多于“外部知识补足”的解释。但 screen-valid 是事后子集，只是与全 ITA 方向一致的描述证据。

## relevant 检索为何损失完整诊断

完整审计的 10 个 clinical Top-1 loss、2 个 gain，以及 Top-2 新增损失显示四类机制。

### 1. 疾病族仍在，但范围被压平

- `DA_d2_heldout100/254`：off 保留 organism、intramuscular abscess 与 levator-scapulae 部位；六个 query-top chunk 都不覆盖病原或肌肉，relevant 退化为 generic deep-neck infection。
- `DA_d2_heldout200b/568`：SS18 易位支持 synovial sarcoma；relevant draft 误到 intimal sarcoma，refine 虽找回组织学却漏掉 primary cardiac site，只能算部分修复。
- `DA_d2_heldout200b/660`：off 保留 ovarian、papillary-serous 与 BRCA1 的复合诊断；relevant 分裂成 generic recurrent ovarian cancer 和 site-unspecified BRCA-mutated cancer。
- `DA_d2_seq100/15`：chunk 支持 histoplasmosis，却不支持 defining primary oral site；完整等价丢失，疾病族端点不丢。
- `MCR_seq200b/345`：relevant draft 只有 generic hypophosphatemic rickets；refine 利用 high vitamin D、undetectable FGF23 与 nephrocalcinosis 恢复 HHRH。这是检索先降粒度、refine 再救回的同案链路。

### 2. 泛主题把表现或常见病推到病因之前

- `MCR_seq200b/263`：noncaseating granulomatous hepatitis、low PTH 和 polyclonal gammopathy 支持 sarcoidosis；query-top bundle 却含 plasma-cell/myeloma 材料，multiple myeloma 被推至第一，refine 看见反证仍维持锚点。
- `DA_d2_heldout200b/615`：off 命名 invasive hypervirulent Klebsiella syndrome；relevant 的 generic sepsis/bacteremia 文本把 liver abscess 这一表现放到病因之前。
- `MCR_seq200b/442`：长期 potent steroid 突停三天支持 topical corticosteroid withdrawal；generic dermatitis bundle 把 perioral dermatitis 推到第一。
- `MCR_v1_seq100/11`：relevant 放大 beta2-glycoprotein 与 infarcts，选择 APS，却压低 shock、myocarditis、rash 和 GI inflammation 对 MIS-C 的联合支持。

### 3. 少见而具体的 Top-2 被常见邻居删除

- `DA_d2_heldout100/452`：off 保留 anti-envoplakin/periplakin pemphigus；泛 bullous-disease 上下文将第二候选替换为 pemphigus vulgaris。
- `DA_d2_seq100/194`：off 保留 hyperoleon within lamellar hole；query-similar ophthalmology 文本未描述 defining finding，却把它替换成 generic silicone-oil maculopathy。
- `MCR_seq200b/277`：off 的第二候选是 adult Wilms/nephroblastoma；renal-cancer chunk 强化常见 RCC 并删除罕见候选。
- `MCR_seq200b/430`：off 保留经 epicardial pathway 的 atrial tachycardia；generic arrhythmia 文本换成 atrial fibrillation，丢失 vein-of-Marshall 机制。

### 4. 真实收益存在，但不是稳定知识归因

- `MCR_v1_seq100/93`：relevant 唯一生成 streptokinase-induced serum sickness，正确结合两周时距、发热与关节痛；hypersensitivity passage 提供了方向正确的支持。这是 E11 最可信的检索收益。
- `DA_d2_heldout100/289`：relevant 产生正确 FTD/ALS spectrum，off 为 TBK1-linked FTD-parkinsonism；但六个 served chunks 是泛神经科内容，并不编码 FTLD-MND，故 outcome gain 真实，retrieval-causal attribution 很弱。

另有一个跨 bundle 的强反例：`MCR_seq200b/480` 只有 no-retrieval draft 保留 myasthenia gravis；三种 bundle 都临床 off-target，把答案推向血管、偏头痛或脱髓鞘解释。即便 off refine 也因血管危险因素和阴性 bedside tests 把 TIA 提到 MG 之前。这说明不受约束的上下文与 generic refine 可以共享同一种“常见替代解释”吸引域。

## hard-negative 不是干净安慰剂

`MCR_seq200b/252` 给出可证伪的真实链路：reference visceral leishmaniasis/Kala-azar，hard-negative bundle 含 malaria passage；refine 明确依据 prevalence 与 cyclic fever 把 malaria 移到第一，造成临床 rank harm。这里 context→理由→排序变化同向，因果解释比纯输出 flip 强。

但不能据此把 hard-negative 平均效应解释为“错误证据伤害”，因为它有 60 个 direct/subtype reference chunks、315 个 broader-related chunks，且 84 个 bundle 对 gold 有 direct/partial support。article-exclusion 只阻止同一来源文档，不保证实体、病因或亚型排除。未来 hard-negative 必须按 typed entity/relation 构造，并单独标记 competitor、broader context 与 accidental gold support。

## refine：何时救回，何时删除

行为层面，off/relevant/random/hard-negative refine 分别为 unchanged 288/324/336/323，reorder-only 58/47/35/41，至少一个候选 replacement 54/29/29/36；Top-1 改变 70/56/39/50。改变很多、净端点很小，意味着大量变化发生在两个错误或部分正确候选之间。

可复核收益包括：

- `MCR_v1_seq100/69`：四个检索条件的 refine 都用 CT fat attenuation 与 benign biopsy 把 GIST 反转为 gastric lipoma，是最稳定的跨上下文病例证据排序收益；
- `MCR_seq200b/345`：从 generic hypophosphatemic rickets 恢复 HHRH，是具体度修复；
- `MCR_v1_seq100/45`：off refine 把 ambiguous rheumatoid-nodule-or-GA composite 拆开，将 exact granuloma annulare 恢复到 Top-2；但 relevant/hard 条件又被 recent surgery 锚定到 foreign-body granuloma，说明同一 refine 逻辑受上下文吸引域控制；
- `MCR_seq200b/441`：refine 输出 dengue encephalitis with hemorrhagic transformation，临床是病例支持的 subtype；strict 把它记作 loss，是 mapper 假阴性而非 reasoning harm。

可复核伤害包括：

- `MCR_v2_seq100/230`：四种 draft 都把 mucormycosis 保留在 Top-2，四种 refine 都将其删除，换成 bacterial abscess/pyomyositis，同时保留 aspergillosis；这是**跨上下文重复的少见候选覆盖删除**，不是偶发 provider flip；
- `MCR_seq200b/326`：relevant refine 把 Brucellosis 与 spinal epidural abscess 反转，偏好影像表现而非羊暴露和 Gram-negative bacteremia 指向的病因；
- `MCR_seq200b/252`：hard-negative refine 把 malaria passage 转成错误排序理由；
- `MCR_seq200b/480`：off refine 以 vascular risk 和阴性 bedside tests 锚定 TIA；
- `MCR_seq200b/317`：off refine 将 focal cryptococcoma 放到 cryptococcal meningitis 之前。前者临床可解释，但与 reference 不完整等价，属于 manifestation-level 重排而非纯无关错误。

历史 B07 draft/final 有 375/400（93.75%）ordered-equal，而 E11 fresh refine 明显更活跃；两者 prompt、路由与执行时点不同，不能把差异当同代码的因果复现。它只说明当前 refine prompt 有足够自由度改写候选，必须用“保留/删除了哪个实体、依据哪条 decisive contrast”约束，而不能只要求再想一次。

## strict mapper 如何制造假机制

17 个 strict discordance 的根审计显示多类非临床 flip：

- `Peeling Skin Syndrome` 与 `peeling skin disease` 同实体；
- `Pyknodysostosis` 是 `Pycnodysostosis` 常见拼写变体；
- `thyrotoxicosis due to Graves disease` 与 Graves 病因诊断等价；
- `adenomatoid tumor of the epididymis` 只是词序/修饰变化；
- `angiomyolipoma with renal-vein extension` 是 reference 加病例支持并发症；
- `dengue encephalitis with hemorrhagic transformation` 是支持充分的具体化。

根临床重编码后，32 个 deep case 中 strict discordance 有 5 个 Top-1、7 个 Top-2 被完全消解。这解释为什么 strict 下 refine 方向略负，而 clinical-complete 或 partial 下方向转正。strict 必须保留用于复现冻结 benchmark，但任何机制结论都必须读取候选对象层级；否则会把“模型说得更具体”错误记成伤害，也会把 disease-family 泛化错误记成完全正确。

## provider 路由是混杂，而不是完整解释

八臂均由 Llama 3.3 70B 通过 OpenRouter 路由，实际结果来自 DeepInfra 与 Groq 两类 provider，并非 Groq 单点。off draft 为 199/201，relevant draft 为 91/303，random draft为 75/317，hard-negative draft 为 194/206；refine 臂分别为 196/203、124/276、176/224、212/179。另有 24/3,200 个结果病例无法从 runtime payload hash 回接 telemetry provider；结果本身完整，缺失只限制 provider 描述。

分析代码此前错误地用 canonical cache hash 连接 runtime JSON hash，产生空的病例-provider 表；现已按客户端实际 `json.dumps(..., ensure_ascii=False)` 重建 payload SHA，并以测试冻结。修复后 provider join 为 3,176/3,200，所有缺失病例显式列入 JSON。

clinical Top-1 relevant-vs-off 的 10 个 loss 中，2 个是 DeepInfra→DeepInfra，3 个 Groq→Groq，4 个 DeepInfra→Groq，1 个 Groq→DeepInfra；两个 gain 各发生于一种跨 provider 方向。因而 relevant 臂的 Groq 偏斜可能贡献方差或系统差，但至少一半 loss 在同 provider 下发生，不能把负向轨迹全部归因于换 provider。反过来，由于 provider 未随机固定，也不能把 `−2.00 pp` 全归因于 bundle。E11 报告的是当前实际路由合同下的联合处理效应，并明确拒绝 provider-specific 因果系数。

## 运行完整性、依赖与恢复事件

八个主臂均有 400/400 成功病例。记录到 3,176 个 semantic calls/physical attempts、543.4 万 input tokens、41.3 万 output tokens；233 个病例行来自冻结 cache。telemetry 与病例的 24 个缺口不被伪报为 API failure。

异质 candidate screen 为 393/400 schema-valid，397 个 semantic calls、450 attempts；7 个失败全部由根审计补齐候选关系。compact retrieval screen 为 325/400 schema-valid，400 calls、401 attempts、101,580 output tokens，跨 24 个 OpenRouter provider。75 个 retrieval schema failure 没有按输出好坏重试或人工修补；candidate/retrieval 交集为 319/400。

早期 combined screen 因进程风暴中止，telemetry 原样保留。恢复后拆成 candidate 与 compact retrieval 两个有界任务；上一临时 workspace 中未提交的 6 个 retrieval cache/telemetry 记录无法证明对应未审标签，故冻结 recovery amendment 并在同一 hidden-reasoning-off 配置下重跑全部 400，而不是挑选补跑。此次 OpenRouter 调用成功，credential 未写入代码、结果、日志或归档。

当前环境缺少 `openai`、`httpx` 和 `requests`，共享 `RobustLLMClient` 在 `auto` 模式选择 dependency-free `stdlib_openrouter`。生产代码仍保留由环境参数选择的官方 OpenAI SDK 分支及其测试，没有以实验专用 HTTP terminal 替代原调用合同。retrieval screen 使用 DeepSeek v4 flash 作为异质分包审计者，避免复用 Llama 家族作最终裁判；最终 candidate 关系、病例机制与报告判断由根审计负责。

## 对各组件优劣的定位

### B07 orchestrator / draft

优点是冻结后能为八臂提供相同上游状态，使检索与 refine 的病例配对可复核；无检索 draft 在完整临床端点上仍是本实验最佳单臂。弱点是绝对 reference 暴露和具体诊断率低，容易产生同疾病族但范围不完整的候选，给后续检索/排序留下很低的上限。

### 当前 retriever

优点是 deterministic、可归档、无 gold 目标泄漏，并能稳定构造 query-top/random/query-near 三种量级相近 bundle。弱点是其“相关”只代表词法近邻，不代表同实体、同对象、同时间或同诊断层级；article-level exclusion 也无法产生干净 hard negative。它擅长找主题，不能保证找 decisive clinical relation。

### Llama draft/refine backbone

优点是能在少数病例真正利用时距、影像特异征和生化关系，且 refine 可跨四种上下文稳定救回 gastric lipoma。弱点是对泛主题、常见病与表现层锚定强；第二次调用会删除 rare-but-plausible Top-2，且 provider/上下文变化可使大量错候选互换。更多 reasoning 并不天然等于更安全的 coverage。

### strict bridge 与异质语义 screen

strict bridge 可重复、不会把宽泛相关性偷换成正确，但对拼写、词序、临床 subtype 和复合修饰的 recall 明显不足。异质 screen 大幅扩大临床等价审计覆盖，并成功暴露 bundle 操纵失败；但它也出现 distinct fungus 合并、复合 reference 过度接受和 75 个 retrieval schema failure。因此 proxy 适合扩队列与敏感性分析，不适合替代根审计。

## 对 RCR-3 的直接约束

1. Call-1 的关系型事件骨架必须把实体、对象、时间、解剖、极性和证据来源绑定原文 span；不能用病例全文直接作检索 query。
2. 检索应由 typed information need 驱动，例如“病因实体与表现的关系”“亚型定义条件”“特异检查的反证”，而不是按全文相似度返回六段主题文本。
3. bundle admission 必须区分 `same entity/subtype`、`broader context`、`competitor` 与 `generic`；没有病例适配或只重复泛主题的 chunk 不进入 comparator。hard-negative 要在实体/关系层排除 reference support，不只排除 article ID。
4. 安全实体聚合必须保留部位、病因、慢性度、分子修饰和复合对象。不能把 oral histoplasmosis、invasive hypervirulent Klebsiella、BRCA1 ovarian cancer 压成泛病种，也不能把 liver abscess/spinal abscess 当成病因替代。
5. Call-3 comparator 对共享候选作成对 decisive-contrast 排序；证据按特异度、时间和反事实区分，不按 chunk 数或主题重复投票。
6. refine 默认保留 draft union，删除候选必须给出能击败该候选的显式反证。对 rare-but-plausible Top-2 设置 coverage guard，直接针对四条件都删除 mucormycosis 的失败模式。
7. 输出同时记录 exact identity、clinical complete 与 partial/scope relation；系统可以选择更具体候选，但评估不得把安全具体化记作错误，也不得把缺部位/病因的泛化记作完整正确。
8. retrieval quality gate 应在入模前完成；若没有通过 typed relevance 的 chunk，安全行为是回到 no-retrieval comparator，而不是为了“用了 RAG”强制注入上下文。
9. provider、payload hash、候选删除和 decisive evidence 全部进入病例级 provenance；provider 分布不均时只作敏感性限制，不从结果倒推 provider 优劣。

E11 是开发集机制实验，不是新确认集。它足以否定“query-top 就等于 relevant evidence”和“再 refine 一次可自动兜底”这两个实现假设；它没有否定经 typed need、临床相关性 gate、实体安全聚合和对比排序约束后的 RAG。后续 RCR-3 应把 E11 暴露的诊断粒度损失与少见候选删除设为显式可证伪失败条件。
