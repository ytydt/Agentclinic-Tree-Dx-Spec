# E10：MAC 顺序历史 × 聚合器的案例轨迹级机制解剖

## 结论先行

E10 不支持“MAC 的主要问题是 Supervisor 把本来多样的医生意见压坏了”。真正的主导机制是 **Doctor B/C 读取前文后发生高强度共识压缩**：平均 canonical union 从 6.82 降到 5.21，医生两两 Jaccard 从 0.689 升到 0.954；D2、D3 每例新增概念分别从 1.225、0.613 降到 0.213、0.015。400 例中 276 例的顺序 union 更窄，只有 14 例更宽。D3 在 400 例上合计只新增 6 个概念，已近乎不是独立诊断者。

但“多样性下降”不等同于“总分下降”。本开发样本里，顺序历史以牺牲临床 reference exposure（121→109）换来更高的 exposed-candidate 转换：RRF exposure→Top-2 从 61.2% 升到 84.4%，Supervisor 从 66.9% 升到 86.2%。根审计临床重编码下，顺序相对独立的 Top-2 净效应为：

- RRF：74→92/400，+4.50pp，95% paired bootstrap CI [2.00, 7.25]pp，5/23 反向/正向病例，exact McNemar `p=0.00091`；
- Supervisor：81→94/400，+3.25pp，CI [1.00, 5.50]pp，5/18，`p=0.0106`。

这不是新候选捕获收益。RRF 的 23 个顺序 Top-2 正向分歧全部来自 **rank conversion**，没有一个来自顺序条件独有的 reference capture；Supervisor 的 18 个正向分歧也只有 1 个 capture gain、17 个 rank-conversion gain。顺序历史在这里做对的是“把已有正确候选推前”，不是“让后续医生独立发现更多”。

Supervisor 也不是主要瓶颈。在固定医生输出下，临床重编码的 Supervisor 相对 RRF：独立条件 Top-1 +2.00pp（1/9，`p=0.0215`）、Top-2 +1.75pp（3/10，`p=0.0923`）；顺序条件只剩 Top-1 +0.75pp、Top-2 +0.50pp。独立条件下 Supervisor 有 18 次把仅一名医生支持的候选提到 Top-1，而 RRF 只有 1 次；顺序条件两者分别为 1 和 0。也就是说 Supervisor 在真正存在少数意见时能利用 vignette 做语义救援；历史先把少数意见消灭后，它只能在同质共识中微调。

因此 C006 应修正为：**顺序历史确定性地压低 B06 的候选多样性；该压缩在当前样本上以排序收益超过召回损失，但留下明确、可复现的长尾候选擦除。闭池 Supervisor 不是多样性下降的来源，且在独立意见存在时有小幅语义转换价值。**

## 1. 识别设计

### 1.1 固定病例与处理变量

病例严格复用 E4 在在线调用前冻结的 400 例开发集：DiagnosisArena 200、MedCaseReasoning 200。四臂为：

1. `isolated_rrf`；
2. `isolated_supervisor`；
3. `sequential_rrf`；
4. `sequential_supervisor`。

Doctor A 的 raw JSON、cache identity 和候选列表在两种 history 条件间逐例复用并做相等断言。Doctor B/C 的模型、姓名、prompt、clean vignette 相同；唯一处理变量是 `discussion_history=[]`，或此前有效医生的完整排名与 commentary。这样 history 主效应不混入 Doctor A 重采样。

在每个 history 条件内，RRF 与 Supervisor 消费同一冻结医生输出。候选经 frozen exact-synonym bridge 规范化为随机稳定 ID；Supervisor 只能从 union 选两个 ID，不能新造、合并或改名，因此聚合器比较不混入额外候选生成。RRF 固定 `k=60`，按 canonical concept 累加并确定性破平。

### 1.2 端点层次

预注册主端点是 frozen-exact-synonym pre-mapper Top-1/Top-2、reference union exposure 和 exposure→selection conversion。它完全可重放，但会漏掉拼写、临床可接受亚型与更具体表述。

因此另做异族语义高召回筛查：DeepSeek v4-flash 逐项比较 reference 与候选，只用于扩大根审计队列。最终队列为 166 例，覆盖：

- 全部 53 个严格 reference-exposed 病例；
- 全部 25 个严格 exposure/Top-1/Top-2 分歧病例；
- 全部 125 个筛查等价、可接受或不确定病例；
- 1 个筛查失败病例；
- 按 family 和 SHA 冻结的 20+20 个筛查阴性病例。

最终责任由根审计承担。40 个筛查阴性抽样中未发现漏掉的可接受等价项；根审计对 5 条唯一 surface 规则作了显式覆盖，并在 8 个候选位置与筛查器的二元接受决定不同。临床重编码仍是敏感性端点：未入队的筛查阴性病例一律不升级，不能被解读为 400 例全面双盲临床标注。

## 2. 运行完整性

- 模型为 `meta-llama/llama-3.3-70b-instruct`，非 RAG 并发 50。
- Llama provider policy 为 balanced；实际所有医生/Supervisor 在线组均同时记录 DeepInfra 与 Groq，未使用 Groq 单点，且禁止 Novita。
- 当前容器没有 `openai/httpx/requests`，由仓库 `RobustLLMClient` 的 stdlib OpenRouter fallback 执行；代码仍保留由环境变量选择官方 OpenAI SDK 的生产路径。
- 独立条件 1,200 个医生位置中 1,198 个 schema 有效；45 个 byte-identical semantic payload 命中不可变缓存，实际 1,155 个语义调用、1,156 个物理尝试。
- 顺序条件新增 800 个 D2/D3 调用，1,199/1,200 个医生位置有效；Doctor A 400 条全部复用断言通过。
- 两个 Supervisor 臂均 400/400 有效、无候选越界；两个 RRF 臂均 400/400 可计算。无效医生不插补，病例按 ITA 保留。
- 异族筛查 399/400 通过完整性校验；失败例与少量超时/截断事件见 `INCIDENTS.md`，不影响四个主臂。

## 3. 结果：严格端点与临床重编码必须分开看

| history | aggregator | strict Top-1 | strict Top-2 | root clinical Top-1 | root clinical Top-2 |
|---|---:|---:|---:|---:|---:|
| isolated | RRF | 21/400 (5.25%) | 30/400 (7.50%) | 55/400 (13.75%) | 74/400 (18.50%) |
| isolated | Supervisor | 22/400 (5.50%) | 30/400 (7.50%) | 63/400 (15.75%) | 81/400 (20.25%) |
| sequential | RRF | 26/400 (6.50%) | 36/400 (9.00%) | 67/400 (16.75%) | 92/400 (23.00%) |
| sequential | Supervisor | 26/400 (6.50%) | 39/400 (9.75%) | 70/400 (17.50%) | 94/400 (23.50%) |

严格端点下，history 对 RRF 的 Top-1 为 +1.25pp（CI [0, 2.75]pp，1/6，`p=0.125`），Top-2 +1.50pp（CI [0, 3.00]pp，2/8，`p=0.109`）；对 Supervisor 的 Top-1 +1.00pp（CI [-0.50, 2.50]pp，3/7，`p=0.344`），Top-2 +2.25pp（CI [0.50, 4.25]pp，3/12，`p=0.0352`）。只有最后一个越过传统 0.05 阈值。

临床重编码把多个严格假阴性恢复，例如 `Pyknodysostosis/Pycnodysostosis`、`cardiac sarcoidosis/sarcoidosis`、更具体的 dengue hemorrhagic encephalitic phenotype。history 对 RRF 的 Top-1 为 +3.00pp（CI [1.00, 5.25]pp，3/15，`p=0.00754`），对 Supervisor +1.75pp（CI [-0.25, 3.75]pp，5/12，`p=0.143`）。这显示表面字符串会低估真实排序变化，也显示临床重编码不能替代严格主端点：两套定义回答的是不同问题。

family 分层方向一致但幅度不同。临床 Top-2 的顺序 history 净胜负：DA 上 RRF 0/11、Supervisor 2/7；MCR 上 RRF 5/12、Supervisor 3/11。没有证据表明总效应只由一个 benchmark family 驱动。

## 4. 生成机制：不是协作扩展，而是共识压缩

| 生成指标 | isolated | sequential | 机制含义 |
|---|---:|---:|---|
| 平均 union concepts | 6.820 | 5.210 | 每例平均少 1.61 个概念 |
| 平均医生两两 Jaccard | 0.689 | 0.954 | 顺序列表几乎同构 |
| D2 新增 concepts/例 | 1.225 | 0.213 | 历史抑制 82.7% 的新增量 |
| D3 新增 concepts/例 | 0.613 | 0.015 | 历史抑制 97.6%；400 例只新增 6 个 |
| D2/D3 Top-1 已在前文出现 | 713/800 | 789/800 | 顺序历史把 top-1 回声推到 98.6% |
| D2/D3 整表与前表完全相同 | 372/800 | 414/800 | 无历史时同模型/同 prompt 已高度相关 |

union 的病例级变化为：顺序更窄 276/400，相同 110/400，更宽 14/400。故均值变化不是少数异常值造成。尤其 D3 几乎不再扩大候选空间，说明三调用的名义宽度不等于三份独立证据。

这里也有重要反事实：isolated 的 Jaccard 仍高达 0.689、整表复制 372/800。去掉跨医生 history 只消除了信息级联，没有消除同一模型、同一模板、温度 0 的共同认知偏差。因此 isolated 是“payload 独立”，不是“模型族或知识先验独立”；它给出的 6.82 union 仍是同质专家组的多样性下界。

## 5. 为什么低召回仍能提高总分：capture–conversion 分解

严格 reference exposure 从 isolated 52 降到 sequential 46；严格 exposure→Top-2 却从 57.7% 升到 RRF 78.3%、Supervisor 84.8%。临床重编码也呈同一结构：

| history | clinical exposure | RRF exposure→T1/T2 | Supervisor exposure→T1/T2 |
|---|---:|---:|---:|
| isolated | 121/400 | 45.5% / 61.2% | 52.1% / 66.9% |
| sequential | 109/400 | 61.5% / 84.4% | 64.2% / 86.2% |

顺序条件丢了 12 个可接受 reference exposure，却把幸存 reference 的 RRF Top-2 转换提高 23.2pp。病例分解进一步否定“新增候选带来收益”的简单叙事：

- RRF Top-2：23 个顺序正向病例全部为 rank-conversion gain；负向为 2 个 capture loss + 3 个 rank-conversion loss。
- Supervisor Top-2：18 个正向病例中 1 个 capture gain、17 个 rank-conversion gain；负向为 3 个 capture loss + 2 个 rank-conversion loss。
- RRF Top-1：15 个正向、3 个负向全部发生在两种 history 都已 exposure 的病例。

所以当前 MAC 的主要收益通路是重复/重权重，而不是信息增量。这直接挑战 C001 的强版本：额外调用可在几乎无新 concept 时通过排序共识获益；是否存在独特的“关系证据”仍未被 E10 测量，不能把候选新颖性等同于关系新颖性。

## 6. 聚合器机制：Supervisor 有小幅语义能力，但无法恢复已擦除候选

在 isolated 固定医生输出上，Supervisor 改变 ordered Top-2 116/400、Top-1 60/400；在 sequential 上分别只有 81/400 和 34/400。原因不是 Supervisor 变保守，而是输入候选和排名已经高度同质。

RRF 的优点是确定性、完全可审计、对同一候选的跨医生重复有稳定奖励；缺点是看不到 vignette，只能把重复当信号，因此会系统偏爱常见、宽泛、跨医生易复现的表现层标签。Supervisor 能读取 vignette，并在 isolated 条件下把单医生候选提到 Top-1 达 18 次，解释了临床 Top-1 的 +2.00pp。它的缺点有三类：

1. 症状/并发症偏好：`MCR_seq200b/326` 中 sequential RRF 将 Brucellosis 排第一，而 Supervisor 选 spondylodiscitis/epidural abscess；
2. 同义身份碎裂：`MCR_seq200b/441` 中 isolated Supervisor 把两个更具体但等价的 dengue encephalitic surface 同时塞进 Top-2；
3. 无法复活池外候选：schwannoma、uterine inversion、TEN、chronic subdural hematoma 一旦被顺序 D2/D3 擦除，闭池 Supervisor 没有恢复通路。

Supervisor 在 sequential 条件相对 RRF 的临床 Top-2 仅 +0.50pp（4/6，CI [-1.00, 2.00]pp，`p=0.754`），不能支持“再加一次聚合调用必然有价值”。它的边际价值取决于上游是否保留真正的少数意见。

## 7. 逐轨迹深解剖

### 7.1 正确少数候选被 history 擦除

**`MCR_seq200b/423`（schwannoma）**：isolated D2 唯一明确提出 schwannoma，D1/D3 都停留在 sarcoma、lymphoma、neurogenic tumor。sequential D2/D3 读取 D1 后复制其泛化肿瘤框架，schwannoma 从 union 消失。两种 isolated 聚合虽也未把少数候选转成 Top-2，但顺序 history 删除了未来任何更强聚合器可能利用的正确信息。这里是纯 capture harm，不应因当前 Top-2 同为错误而记作“无影响”。

**`MCR_seq200b/455`（uterine inversion）**：isolated D2/D3 均把 inversion 排第一，RRF Top-2 命中、Supervisor Top-1 命中；sequential D2/D3 则完全接受 D1 的 cervical/uterine/vaginal cancer 锚点，正确候选消失，两个聚合器都错。这是从独立双重发现到错误三人共识的完整因果链。

**`MCR_v1_seq100/28`（TEN）与 `MCR_v2_seq100/173`（chronic subdural hematoma）**：前者只有 isolated D3 跳出 DRESS/肝损伤框架提出 TEN，后者只有 isolated D3 补上关键 chronicity；history 都使 D3 回到前文模板。两例当前聚合未能利用少数意见，但它们证明 D3 的独立搜索能力在顺序协议中被删除。

### 7.2 错误后续共识覆盖正确 Doctor A

**`MCR_v2_seq100/205`（cysticercosis）**：D1 正确 Top-1。isolated D2/D3 也把它排第一，两个聚合器均正确；sequential D2/D3 反而把 neurofibromatosis/fibromatosis 共识推前，将 cysticercosis 降至第四，最终两个聚合器都错。这否定“history 只会复制 D1”的粗略说法：它也会让后续医生形成新的错误共识并覆盖正确锚点。

**`MCR_seq200b/430`（atrial tachycardia）**：D1 正确 Top-1，sequential D2/D3 把 epicardial accessory pathway-mediated tachycardia 推前；RRF 仍保住 reference Top-1，但 Supervisor 跟随后续具体机制，将正确诊断降到第二。具体性在缺乏充分病例约束时会变成错误吸引子。

### 7.3 history 的真实优势：已有候选的排名传播

**`MCR_v1_seq100/22`（adenomatoid tumor）**：三份 isolated 列表都把 reference 放第五，RRF/Supervisor 都选常见 epididymal cyst/spermatocele；sequential D2/D3 将 D1 的低位候选推到第一，RRF Top-2、Supervisor Top-1 均救回。这是纯 rank-conversion，不是 discovery。

同类模式还包括 `DA_d2_heldout100/317`（pyoderma vegetans）、`MCR_seq200b/294`（undifferentiated embryonal sarcoma）、`MCR_seq200b/334`（PRES）、`MCR_seq200b/374`（cryptogenic organizing pneumonia）、`MCR_seq200b/412`（external cervical resorption）、`MCR_v1_seq100/30`（Cronkhite–Canada）、`MCR_v1_seq100/74`（CPVT）。它们共同说明：history 的有效功能是让低位但正确的已有候选获得第二、第三次排序支持。

### 7.4 少数真正的 discovery 与聚合交互

**`MCR_seq200b/345`（HHRH）**：D1 错锚定 X-linked hypophosphatemia；sequential D2 首次发现完整 HHRH，D3 随后复制。RRF 仍被共同的 X-linked 标签压住，只有 Supervisor 用病例特异性将 HHRH 提到 Top-1。这是 400 例中极少数“history 条件产生独有可接受 reference 且聚合成功”的 capture gain。

**`DA_d2_heldout100/334`（phaeohyphomycosis）**：isolated D3 已在第五位发现 reference；sequential D2 把它带到第二、D3 跟随。RRF 仍偏爱重复的 chromoblastomycosis/leprosy，Supervisor 才把 reference 放入 Top-2。该例同时包含 minority discovery、history 共识和语义聚合三个阶段，不能只归功于某一个模块。

### 7.5 严格字符串造成的假机制

**`MCR_seq200b/285`**：isolated Top-1 `Pyknodysostosis` 与 reference `Pycnodysostosis` 是同一疾病；所谓 sequential Top-1 gain 是拼写桥漏配。

**`MCR_seq200b/260`**：顺序条件删除 exact surface `syphilitic aortitis`，但保留 `aortitis due to syphilis`；严格 exposure loss 不是临床 loss。

**`MCR_seq200b/418`**：顺序候选 `cardiac sarcoidosis` 比 generic reference `sarcoidosis` 更贴病例；严格端点把它当错，临床端点反而认为顺序更具体。

**`MCR_seq200b/441`**：`acute hemorrhagic leukoencephalitis due to Dengue` 是更具体的 dengue encephalitic phenotype；严格端点制造 Supervisor harm，同时暴露 registry 没有合并两个临床同义 surface 的缺陷。

这些不是可以随意“宽松打分”的理由，而是要求同时保留严格、临床和身份错误三条 ledger。只报告任意一条都会把 mapper/ontology 界面问题误归因于 reasoning。

## 8. 25 个严格关键病例的机制分类

| case | 根审计方向 | 主机制 |
|---|---|---|
| DA/317 | sequential better | rank propagation rescue |
| DA/334 | sequential better | consensus + Supervisor rescue |
| DA/87 | sequential better | composite-label preservation |
| MCR/260 | strict artifact | equivalent surface retained |
| MCR/285 | strict artifact | orthographic identity miss |
| MCR/294 | sequential better | rank propagation |
| MCR/309 | isolated better | Graves etiology erased |
| MCR/326 | aggregator interaction | RRF retains etiology; Supervisor prefers manifestation |
| MCR/334 | sequential better | rank reversal to PRES |
| MCR/345 | sequential better | specific discovery + Supervisor conversion |
| MCR/374 | sequential better | rank propagation |
| MCR/412 | sequential better | D1-specific ranking restored |
| MCR/418 | sequential clinically better | subtype/reference direction artifact |
| MCR/423 | isolated recall better | unique schwannoma erased |
| MCR/430 | isolated better under Supervisor | wrong specific mechanism anchor |
| MCR/441 | strict artifact | specific subtype + identity fragmentation |
| MCR/455 | isolated better | independently discovered inversion erased |
| MCR/22 | sequential better | rank-five→rank-one propagation |
| MCR/28 | isolated recall better | unique TEN erased |
| MCR/30 | sequential better | correct D1 minority propagated |
| MCR/60 | sequential better | rank propagation + Supervisor rescue |
| MCR/74 | sequential better | rank-three→rank-one propagation |
| MCR/173 | isolated recall better | chronicity erased |
| MCR/178 | sequential better for RRF | rank stabilization; Supervisor redundant |
| MCR/205 | isolated better | correct D1 overridden by wrong later consensus |

完整候选裁决、四臂输出和逐例说明见 `manual_audit.jsonl`，不是由表中标签替代。

## 9. 对各组件优劣势的定位

### Isolated homogeneous panel

优势是保留独立少数候选，clinical exposure 121/400，高于 sequential 的 109；schwannoma、uterine inversion、TEN、chronic subdural hematoma 等长尾发现只能在这里出现。劣势是同模型/同模板本身已经高度相关，且未协调的 surface/specificity 会分裂投票；正确候选常被各自放在低位，RRF conversion 只有 61.2%。

### Sequential homogeneous panel

优势是对 D1 或 D2 已发现的正确候选进行 rank propagation，显著提高 conversion；当前样本的临床净效应为正。劣势是 D3 几乎不提供增量信息，错误锚点和错误后续共识会删除长尾候选。它更像“同一诊断器的三步自洽化”，不是三个独立专家。

### Deterministic RRF

优势是零额外调用、可重复、对正确多医生共识有效；在 sequential 条件已经同质时与 Supervisor 基本相当。劣势是无法读取病例证据，重复的泛化表现层诊断会压过少数但病例特异的病因；也无法识别临床同义 surface。

### Closed-pool Supervisor

优势是在有真正少数意见的 isolated 条件能利用 vignette 做语义选择，尤其提高 clinical Top-1；它比 RRF 更可能选择单医生支持候选。劣势是第四次调用的边际收益小、受身份碎裂影响，并可能偏好具体但错误的机制或临床表现。更关键的是，它不能恢复 generation 阶段已删除的候选。

## 10. 设计含义与下一步接口

E10 不支持直接把 B06 改成“永远 isolated”或“永远 sequential”。更合理的结构是：

1. 前两名医生保持真正独立，保留候选召回；
2. 第三调用读取 **类型化 canonical union + 病例关系骨架**，只做显式对比和排序，不重新生成一个会覆盖少数意见的 Top-5；
3. 聚合器保留每名医生的 Top-1 和所有 singleton 候选的可见性，并对“为何排除少数候选”承担结构化义务；
4. 身份层先处理拼写、临床同义与 directional subtype，禁止把 registry 缺陷算成 reasoning；
5. 把 candidate capture 与 conditional conversion 分开作为门控指标。任何总分增益若伴随 capture 大幅下降，都必须列出被擦除的具体病例。

这与 RCR-3 的设计方向一致：Call 1/2 用于关系化独立候选与安全实体聚合，Call 3 用于时间/范围感知的固定池对比排序；不需要用顺序自由讨论制造伪多代理共识，也不需要默认第四次 Supervisor 调用。

## 11. 限制与可证伪边界

1. 这是冻结开发集，不是新确认集；按用户约束未重复运行、未扩容确认集、未统一 retry/provider。
2. D2/D3 是不同语义调用，虽然温度 0、病例成对且 provider balanced，history 效应仍包含不可消除的单次 provider/model 随机性；Doctor A 和聚合器共享设计已尽量压缩这一混杂。
3. prompt 基于历史 B06，但增加了“不把重复当独立证据”和闭池约束；结论针对受控机制，不等价于历史开放式 Supervisor 的精确重放。观察到的强回声是在已经抑制重复的 prompt 下发生，故方向并非由鼓励附和的措辞造成。
4. 临床重编码采用异族模型做队列扩展而非裁判；166 例根审计和 40 个阴性抽样降低但不能消除漏检。严格端点仍是预注册主结果。
5. “新 concept”不等于“新关系证据”。E10 证明候选新颖性不是获益必要条件，但没有直接测量 D2/D3 commentary 是否加入独特、正确的关系证据；该问题留给 RCR-3 的关系 fidelity ledger。

## 12. 最终裁决

- C006 的“sequential history suppresses diversity”获得强机制支持；“Supervisor aggregation suppresses diversity”被否定/修正。
- 当前 B06 的优势是低成本地强化已有候选排序，弱点是以共识压缩换取转换、并可永久删除正确少数意见。
- 默认架构不应依赖自由文本顺序讨论来制造第三视角；应保留独立生成，再以类型化、闭池、必须解释少数候选排除的 comparator 完成收敛。
- 本实验不证明历史在所有分布上净有益；它明确给出了净益与灾难模式同时存在的机制条件和病例证据。
