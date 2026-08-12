# E9：Forest 三视图的独立性、角色标签与重复投票机制解剖

## 判定

E9 支持一个有限但重要的结论：Forest 的三视图不是三张独立选票，也不只是三个换名副本。它们是**中度重叠、偶尔补足关键候选或证据、同时会把 selector 推入不同错误吸引域的相关视图**。

固定 400 例上，真实三视图 `real_views` 相对单锚点 `single_anchor` 的严格 top-1 从 29/400 提高到 38/400（`+2.25 pp`，病例 bootstrap 95% CI `[+0.75,+4.00] pp`；独赢 10/1，精确 McNemar `p=0.0117`）。这不是纯 selector 效应，因为真实视图把 reference 暴露从 39 例扩到 48 例。把候选可达性与选择转化拆开后：

- 39 个共同暴露病例中，single 为 29 个 top-1，real 为 32 个；real-only 4、single-only 1，净增 3；
- 9 个 real-only 暴露病例中，real 将 6 个推到严格 top-1；
- 因而严格净增 9 由“新增可达候选”和“共同候选上的重新排序”共同产生，不是单一的 recall 故事。

但根代理对全部 11 个 real↔single 严格胜负病例逐例复核后，10 个 strict real-only 中只有 6 个是真实临床收益：3 个来自新候选捕获，3 个来自已有候选上的选择/重复效应；另 4 个只是疾病范围、部位、亚型或同义表面的 benchmark 口径收益。single 的 1 个独赢则是真实误伤。换言之，严格净胜 `+9` 经这组完整 discordance 的临床重编码后变成 6 gain、1 harm、4 neutral；不能把 `+2.25 pp` 原样解释为临床净收益。

两个更干净的干预没有显示稳定方向：

- 只轮换 syndrome/mechanism/modality 角色名，候选、证据、顺序和模型均不变，400 例有 58 次 champion flip（14.5%），正确数 38→36（`−0.50 pp`，95% CI `[−1.50,+0.50] pp`，`p=0.625`）；
- 把同一个 anchor 内容精确复制三遍，不增加任何信息，399 个双成功病例有 51 次 flip（12.8%），正确数 29→29（3 gain、3 harm；95% CI `[−1.25,+1.25] pp`，`p=1`）。

这些 flip 证明 selector 对无信息增益的叙事扰动和重复呈现不稳定，却不能全部归因于角色名或重复本身：四臂是 fresh calls，DeepSeek 经多 provider 路由，即使温度为 0 也没有固定随机轨迹。审计中没有一条解释显式把角色名当权威；角色变化主要把同一内容重新叙述成不同诊断。重复则确实会被注意：在机制富集的 70 例队列中，38 条轨迹显式表现出重复/多条同义支持的权重，16 条明确识别并折扣重复；方向既可 rescue，也可 harm。因此，角色/重复 flip 是**扰动敏感性的上界证据**，不是一个已隔离的稳定因果系数。

异质 Gemini 审计进一步否定“三次独立投票”。387 个合法病例的 5,867 条观察被聚成 3,241 个命题簇；全局 cluster/observation 比为 0.552，病例均值 0.550、中位数 0.545。病例级平均语义 Jaccard 为 syndrome↔mechanism 0.496、syndrome↔modality 0.450、mechanism↔modality 0.460；1,709 个簇跨至少两个视图，879 个同时跨三个视图。约一半语义重叠意味着相关性很强，但另一半非重叠内容仍有真实边际价值。

最可靠的结论是：**保留多视图的边际候选覆盖，但禁止把视图数、角色名或重复支持当票数；先把证据压成保留时间/对象/范围的命题，再对共享候选作显式对比排序。**

## 设计：四臂分别问三个机制问题

样本完全冻结为 E4 的 400 个开发病例，DA/MCR 各 200。历史 Forest 代码对 syndrome/anatomy、mechanism/etiology 和 definitive modality 三个生成器分别只传同一 clean vignette，没有跨视图 history；因此历史 `real_views` 已是所要求的 no-history 三调用条件，不另造一个同义臂。

每例先从三个历史视图重建候选 registry、候选 assessment 和证据。单锚点按 outcome-blind、近似均衡的冻结分配选取：mechanism 134、syndrome 134、modality 132。四个 fresh-selector 臂为：

| 臂 | 输入内容 | 能识别的问题 |
|---|---|---|
| `real_views` | 三个真实视图及其 union registry | 真实额外内容的联合价值 |
| `role_rotated` | 与 real 完全相同，只循环轮换三个角色名 | 角色标签敏感性 |
| `single_anchor` | 一个冻结 anchor 及其 registry | 单视图基线 |
| `duplicate_anchor` | anchor 内容精确复制三次，registry 不变 | 无新增信息的重复/伪投票效应 |

selector 看不到 gold、选项、历史 champion、来源模型、旧 rank/score、arm 名或实验假设。primary endpoint 是 mapper 前 exact-or-frozen-synonym top-1；所有 schema/transport 失败 fail-closed，不修剪、不补值、不因结果重试。

这一设计能把 `real↔rotated` 和 `single↔duplicate` 的 payload 内容差异压到指定干预，但 `single↔real` 有意同时改变候选 registry 与证据内容。后者从预注册起就只被解释为“额外视图内容的联合效果”，再用 capture/conditional-selection 分解，而不是伪称 selector-only 因果效应。

## 主结果与家族异质性

| 比较（右−左） | 双成功 n | champion flip | 正确数左→右 | 独赢左/右 | 净差 | bootstrap 95% CI | McNemar p |
|---|---:|---:|---:|---:|---:|---:|---:|
| real → role-rotated | 400 | 58 (14.5%) | 38→36 | 3 / 1 | −0.50 pp | −1.50, +0.50 | 0.625 |
| single → duplicate | 399 | 51 (12.8%) | 29→29 | 3 / 3 | 0 | −1.25, +1.25 | 1.000 |
| single → real | 400 | 154 (38.5%) | 29→38 | 1 / 10 | +2.25 pp | +0.75, +4.00 | 0.0117 |
| duplicate → real | 399 | 149 (37.3%) | 29→38 | 1 / 10 | +2.26 pp | +0.75, +4.01 | 0.0117 |

结果主要来自 MCR：single→real 为 27→35（`+4.00 pp`，95% CI `[+1.00,+7.50] pp`，独赢 1/9，`p=0.0215`）；DA 只有 2→3（`+0.50 pp`，CI `[0,+1.50] pp`，`p=1`）。这首先反映可达性 floor：DA 的 anchor/union reference 暴露仅 3/4 例，MCR 为 36/44 例。不能据此声称多视图只对某一临床来源天然有效。

四臂的 intention accuracy 分别为 real 9.50%、rotated 9.00%、single 7.25%、duplicate 7.25%。这些低绝对值不是一个适合解释为端到端模型性能的数字：real 的 reference 也只在 48/400 个 registry 中可达。条件在暴露后，real 为 38/48（79.2%），single 为 29/39（74.4%）；E9 的首要瓶颈仍是候选对象可达性，而非最后一次排序的平均能力。

## “九个新增 reference”并不等于九个真实捕获收益

三个视图的严格 reference 捕获为 syndrome 40、mechanism 42、modality 38；union 48，冻结 anchor 39。九个 union-only reference 按唯一来源分成 mechanism 5、syndrome 3、modality 1。

根代理审查全部九例后得到：

- 真正捕获并转成正确 top-1 3 例：Brucellosis、HHRH、Livedoid vasculopathy；
- 真正捕获但未转化 2 例：Ischemic colitis、Polymyalgia rheumatica；
- 主要是 scope/surface 口径 4 例：Cutaneous malakoplakia、adrenal/general myelolipoma、Sarcoidosis/cardiac sarcoidosis、gastric/general lipoma。

三个成功捕获的共同模式不是“多数同意”，而是某一视图引入了别处没有的诊断对象或决定性关系：

- Brucellosis：mechanism view 同时给出诊断对象和羊组织暴露，使答案从局部 spinal epidural abscess 上移到系统病因；
- HHRH：mechanism view 补足 FGF23-independent phosphate wasting、1,25-D 和 nephrocalcinosis 对应的具体亚型；
- Livedoid vasculopathy：syndrome view 提供对象，modality/形态证据补上白色萎缩瘢痕和踝周复发疼痛溃疡。

两个 capture-without-conversion 暴露了更重要的下一瓶颈。Ischemic colitis 已在 syndrome view 中出现且有出血/黏膜下病理，selector 却因“缺少常规危险因素”把它降到 ulcerative colitis；这是低先验压过病例特异证据。PMR 虽被捕获，但局灶单侧无力与髂腰肌附着 MRI 同时使 benchmark reference 本身支持不完整。候选召回和候选可证伪性必须分开记录。

在更宽的 70 例机制队列中另有两个严格 bridge 没记作成功、但临床上明确的捕获：heterozygous HTRA1-CSVD 被输出为 HTRA1-related hereditary CSVD；carcinoma erysipelatoides 只少了 triple-negative 原发修饰。这解释 `trajectory_mechanism=capture_gain` 总数为何是 5，而九个 strict union-only 集合中的真 capture-to-top1 是 3。

## 共同候选上的选择收益与选择伤害

39 个 reference 在 single 和 real 中共同暴露。real 从 29/39 转成 32/39，4 gain、1 harm。完整逐例复核显示其中三项真正的排序收益都不是新候选捕获：

- Visceral leishmaniasis 已在 anchor 内，额外 leukopenia/CRP 和重复支持改变 malaria 锚定；
- Sturge-Weber 已在 anchor 内，重复/多视图使 port-wine 分布压过 negative brain MRI 和 ocular pigmentation；
- LAM 已在所有池内，真实视图或精确重复使年轻女性、弥漫圆形肺囊肿和双侧复发气胸压过 Birt-Hogg-Dubé。

唯一真实 harm 是 Cryptococcal meningitis：single/duplicate 正确优先阳性 cryptococcal antigen；real/rotated 加入并重复 mass-lesion、低 CD4 和梗死图像后，反而覆盖高特异检测而选择 toxoplasmosis。这是典型的**证据量战胜证据特异度**，也是不能把 view count 当 confidence 的直接反例。

另一个非 strict-discordance 的关键 harm 是 IPAH+PFO：两个对象分散在不同视图，selector 非法把它们合成为 Eisenmenger syndrome，尽管 PFO 不是造成肺高压的因果分流且肺动脉压低于主动脉压。union 不只扩 recall，也扩大错误组合空间；typed entity aggregation 必须禁止无关系边的跨视图拼接。

## 角色名：改变叙事吸引域，没有识别出稳定权重

角色轮换造成 58/400 个 champion label flip，却只产生 4 个严格正确性 discordance。根审计的临床重编码为 real better 2、rotated better 1、同义口径 neutral 1：

- Warthin tumor 与 LAM 在真实角色下更好；
- cone-rod dystrophy 在轮换角色后反而被救回；
- retropharyngeal calcific tendinitis 与 longus colli tendinitis 是同义偏好，不是临床变化。

审计词表允许 `explicit_role_weighting`，但 70 例中为 0；21 例只见叙事改变，49 例没有可见角色机制。典型轨迹中，模型不会写“因为这是 mechanism view 所以权重更高”，而是用同一证据重新讲出不同故事：家系 ERG 被叙成 cone-rod，FAF 被叙成 Stargardt；cartilaginous pathology 被叙成 chondrosarcoma，面神经定位又可被叙成 schwannoma。

因此不能把三个 role label 设计成三种固定 vote weight。更安全的用途是 provenance：标记该视图试图覆盖哪个信息域，供缺口检测和审计使用；最终权重必须落在可引用的命题、时间、对象和候选对 contrast 上。

## 精确重复：不是额外证据，却能改变答案

single 与 duplicate 的 registry 和事实完全相同，后者只是把 anchor 内容放到三个 role block。仍有 51/399 个 champion flip，说明“提示中已写重复不是多票”不足以消除表示路径依赖。

六个严格 outcome discordance 经临床重编码后为：

- duplicate better 3：visceral leishmaniasis、Sturge-Weber、LAM；
- single better 2：syphilitic aortitis、Warthin tumor；
- neutral 1：generic subacute thyroiditis 与 vaccine-associated trigger 的范围差。

重复有时强化正确 pattern，有时把具体诊断退化为泛类，或放大错误影像锚。比如 syphilitic aortitis 在 single/real 中能结合主动脉关闭不全、冠脉开口狭窄和 Treponema，duplicate 却退到 generic infectious aortitis；Warthin 的长期微小稳定结节被重复/角色变化推成 SCC。反方向上，LAM 的 duplicate trace 明确说三个 block 是复制并应折扣，却仍从 BHD 翻到 LAM。这说明模型“知道重复”与其内部排序真正不受重复影响是两回事。

重复臂还有一个保留的 schema failure：`MCR_seq200b/285` 引用了 4 个 decisive IDs，超过最大 3 个。响应明确把 V2/V3 描述为重复，故失败本身也是重复增加接口负荷的证据；但它仍 fail-closed，不截断、不重试。该例的 `Pyknodysostosis` 又是 reference `Pycnodysostosis` 的标准拼写差，进一步说明接口失败与严格本体桥错误可以叠加。

## 三视图有多独立：精确重叠与语义重叠的联合证据

在不调用 LLM 的 exact 统计中，三对 view 的候选 Jaccard 均值为 0.442–0.461，证据文本 Jaccard 均值为 0.346–0.408。异质语义聚类后，三对证据 Jaccard 上升到 0.450–0.496。这个差异符合预期：不少文本不是字面重复，却表达相同临床命题。

语义聚类并非 ground truth。400 个 Gemini 输出有 13 个违反精确 partition 合同：9 个重复 observation ID、3 个遗漏 ID、1 个发明 ID；全部保留为失败，不修补。根代理又审查了所有 13 个失败和高/低 merge 样本。在 70 例队列的 57 个合法聚类中，52 faithful、2 minor、3 major：

- Warthin：合并历史小结节与后续 8-mm MRI 时抹掉时间限定，正好删除“长期稳定”这一鉴别点；
- Dengue encephalitis：把 V3 MRI 与短版 V2 合并，丢掉 diffusion restriction、blooming 和 double-doughnut pattern；
- MIS-C 轨迹：把 rising creatinine 从合并命题中丢失，低估肾系统受累。

另两例 minor 是 LED photic maculopathy 和 tricuspid aneurysm 的 contained observation under-merge。审计队列是机制富集抽样，52/57 不能当全 387 例的质量率；它只能证明聚类总体可用来估计重叠，同时会在时间、影像限定和复合观察上系统性失真。RCR-3 的生产 dedup 不能直接委托给一次自由文本 clustering call。

## 手工审计范围与责任边界

根代理在任何病例级判断前冻结 70 例队列，DA 28、MCR 42。队列包含：三个主对照的全部 strict outcome discordance、全部九个 unique capture、角色/重复同 outcome flip 的 SHA 冻结样本、语义高低 merge 样本和全部 13 个 partition failure。类别可重叠，70 不是各类别数量之和。

每例读取 clean vignette、三个历史视图、anchor、四个 fresh selector trace 和合法时的完整语义 partition。`manual_audit.jsonl` 保存最终判断和逐例 clinical note；Gemini 只承担 target-blind proposition clustering 分包，未承担最终审计。

70 例中有 17 例被判为严格 reference 的 scope/surface artifact，另有 6 例临床不等价；这再次表明 strict endpoint 需要保留，但不能取代病例级机制判断。轨迹主标签为 capture gain 5、selection harm 3、repetition instability 15、label instability 18、interface failure 1、stable 27、other 1。因为队列故意富集 flip/failure，这些计数只能描述机制谱，不是总体发生率。

## 运行、依赖与可复核性

四个 DeepSeek selector 臂记录到 1,586 个 semantic calls、2,052 个 physical attempts、342.7 万 input tokens、838.8 万 output tokens；Gemini 语义分包另记录 399 calls、399 attempts、31.3 万 input 和 29.5 万 output tokens。合计已记录下界为 1,985 calls、2,451 attempts、374.0 万 input、868.3 万 output tokens；latency 求和 185,797 秒，在并发下不能当墙钟时间。

15 个成功/结果病例缺少 per-call telemetry（selector 14、semantic audit 1），所以 token、attempt、provider 和 latency 总量全部明确标为下界，不重跑补账。四个 selector 结果为 real 400/400、rotated 400/400、single 400/400、duplicate 399/400；语义 partition 为 387/400。

DeepSeek 经多个 OpenRouter provider 路由，没有形成 Groq 单点。当前 Python 环境缺少 `openai`、`httpx` 和 `requests`，生产 `RobustLLMClient` 因而自动使用 dependency-free `stdlib_openrouter`；代码仍保留由依赖和环境参数选择的官方 OpenAI SDK 分支，没有用实验专用简易终端替换生产调用合同。API credential 可用，未写入代码、结果、日志或归档。

每个 arm 的 raw cache、原始响应、telemetry、run log 和 provenance 已分别归档并带 SHA-256；joined endpoint、语义分包、冻结审计队列、根审计和最终分析也有独立清单。技术失败、schema failure 和审计分歧均未静默删除。

## 对 RCR-3 的直接约束

1. 三视图输出先转成带 `entity/scope/time/anatomy/polarity/modality` 的命题；相同命题只出现一次，view provenance 作为元数据而非票数。
2. union registry 保留，因为真实收益中至少有五条临床 capture trajectory；但每个新增候选必须绑定引入它的原文 span 和关系，不允许 IPAH+PFO 式无边组合。
3. comparator 先问“reference/candidate 是否可达”，再问“共享候选为何胜负”；禁止把 recall gain 与 ranking gain 合成一个无法解释的总分。
4. 支持强度按特异度、时间一致性和候选对反事实区分，不按同义证据条数累加；positive specific test 不能被大量泛影像描述淹没。
5. syndrome/mechanism/modality 角色用于缺口覆盖检查，不作为固定权重。若角色轮换能在不改变命题时改写 champion，应触发低稳定性标记。
6. 对重复/角色/顺序 perturbation 的 champion 不一致应进入安全聚合：比较 decisive contrast、检查 cycle/margin，并在必要时回看原文，而不是多数表决。
7. 输出本体要允许 diagnosis、etiology、manifestation、subtype 和 composite 分层；严格字符串与临床等价分别报告，不能靠危险 substring bridge 掩盖 scope 错误。
8. LLM semantic clustering 可作候选分包，但生产去重必须有 exact-partition gate，并对时间、对象、极性和影像限定做确定性校验。

E9 是开发集机制实验，不是确认性性能试验。它足以否定“独立三票”和“重复即置信度”，也识别了多视图确有的候选覆盖价值；它没有证明当前三视图 selector 已是稳定最优实现。
