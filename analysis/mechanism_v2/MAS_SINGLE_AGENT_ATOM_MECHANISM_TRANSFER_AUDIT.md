# 医疗 MAS：真实机制、官方实现与 Forest/IMPC/Collapse3c 单原子迁移审计

> 研究日期：2026-08-21
> 主项目冻结基线：`cursor4@c39a19d738676f2838994727608291398802e9a1`
> 范围来源：用户提供的 `MAS.md`，再以论文原文、作者官方仓库、随仓产物与主项目冻结日志独立核验
> 新 LLM/API 调用：**0**
> 外部仓库：仅克隆到临时目录做只读审计；未写入主项目

## 0. 结论先行

本轮最重要的判断不是“把 Forest、IMPC、Collapse3c 包装成三个专科医生，再让第四个 LLM 主持讨论”，而是：

> **把三种原型收缩为彼此不可见、状态不可变、输出可验证命题的单 Agent 原子；专用诊断 verifier 只由可观察分歧触发，但对象投影与冻结候选全集的逐对证书是强制步骤，最终只用确定性规则融合验证后的边。**

由论文观察、非全因子消融、公开代码和本项目冻结日志共同约束出的设计原则可归为六类；其中多项仍是**待干预验证的机制假说/必要合同**，不是文献已分别做出受控因果识别的“六个真因”：

1. **independent-first**：先独立计算，避免首个答案通过共享上下文造成锚定；
2. **error-decorrelated channels**：不同模型、信息模态或计算算子只有在错误不共线时才构成有用多样性；
3. **conditional compute**：额外计算应由可观察的失败信号触发，而不是固定人数或自由讨论；
4. **disagreement localization**：通信单位应从整段 opinion 下沉到候选、premise、证据角色与比较边；
5. **dissent-preserving state**：正确少数意见和原始证据必须保留，不能被连续摘要成 consensus；
6. **verification before fusion**：融合器只消费经过来源、对象、时间、极性和方向验证的边，不能以多数票或另一个自由 LLM judge 代替验证。

这些原则并不支持以下常见叙述：specialty persona 天然等于独立专长；agreement 等于正确；summary 无损；case complexity 是可靠路由变量；动态 LLM orchestrator 天然优于固定流程；逻辑树的 premise 自动为真；自我演化 memory 仍是纯 inference；性能提升就证明了“协作”机制。

主项目 800 例、2,400 条真实原子轨迹的离线根审重放给出了直接约束：

| 事实 | 结果 | 含义 |
|---|---:|---|
| 最佳单原子 `clinical-complete` | Collapse3c 122/800 | 不能以旧 legacy-chain 排名选择原子 |
| 任一原子 complete 的 oracle union | 155/800 | 相对最佳单原子有 33 例机会，但只是不可实现上界 |
| 三原子 champion 不全相同 | 515/800 | 分歧充足，但分歧本身不代表信息增益 |
| 恰一原子 complete | 51/800 | 存在真实 correct-minority 场景 |
| 两个错误原子输出同一根审簇 | 27/51 | 若按该簇做多数融合，正确少数会被压制；这是风险诊断，不是假定未来 aggregator |
| 正确原子 champion 的规范化标签存在于任一错误原子主池 | 18/51 | 这部分有明确的 shared-candidate comparison 修复机会 |
| 该规范化标签不存在于两个错误原子主池 | 33/51 | 互补来自正确原子的独特 exposure；union 必须保留它，不能只比较池交集 |

因此，`+33/800` 不是拟发布 MAS 分数，也不是静态 routing 收益。它只说明：如果能在不丢失正确少数、不制造新命题且不过量调用的条件下识别正确原子，存在最多 4.125pp 的原始互补机会。当前证据没有识别出这样的 oracle router。

建议原型名为 **Validated Edge MAS（VE-MAS）**：

```text
raw vignette
   ├─ Forest atom ─────┐
   ├─ IMPC atom ───────┼─ safe identity + immutable claim ledger
   └─ Collapse3c atom ─┘            │
                       typed disputes (conditional) ──┐
                                                     ├─ orthogonal verifiers
                 object projection + all pairs       │
                              (mandatory) ────────────┘
                    polarity / time / scope / interaction /
                    identity / exposure / pair comparator
                                     │
                         validated edge patch (append-only)
                                     │
                     deterministic partial-order aggregation
                                └─ tie / abstain allowed
```

Forest、IMPC、Collapse3c 均可成为原子，但必须修改其接口和若干内部语义；不能原封不动组成“医生团队”。

---

## 1. 研究边界、证据等级与版本血缘

### 1.1 本轮做了什么

本报告逐项覆盖 `MAS.md` 中的 20 个论文/系统单元，并对可确认的作者官方仓库执行：

- exact commit 冻结；
- README、入口、prompt、路由、聚合、memory、评估脚本的静态审计；
- 搜索 committed outputs、logs、results、trajectories、cache；
- 对存在日志的仓库统计文件数、结构与其能证明/不能证明的机制；
- 区分作者官方实现、论文未给仓库、第三方复现与同名无关项目。

完整机器账本见 [paper_code_ledger.json](results/MAS_SINGLE_AGENT_ATOM_RESEARCH/paper_code_ledger.json)，官方仓库提交与日志探测见 [audited_source_manifest.json](results/MAS_SINGLE_AGENT_ATOM_RESEARCH/audited_source_manifest.json)。主项目离线 census 见 [backbone_atom_census.json](results/MAS_SINGLE_AGENT_ATOM_RESEARCH/backbone_atom_census.json)，其生成脚本为 [mas_single_agent_atom_census.py](mas_single_agent_atom_census.py)。公开 census 只保存 800 例汇总、分层和机制计数，不发布逐病例诊断/预测列表；脚本仍会从冻结 source tree 精确重建这些汇总，并由单元测试逐字段比对。

### 1.2 “真正机制”的判定合同

每篇工作分开回答：

1. **干预了什么？** 模型、人数、prompt、角色、信息可见性、候选、工具、memory、监督、调用预算还是评估器；
2. **基线是否可比？** 同病例、同底模、同候选、同 token/call budget、同 endpoint；
3. **消融隔离到哪一层？** bundle 同时改变多个变量时，只能归因于 bundle；
4. **代码实际做什么？** 论文名词不能代替调用图、state mutation 与 aggregation 代码；
5. **日志能证明什么？** 有轨迹可审计仍不等于存在随机化干预或因果识别。

证据等级：

| 等级 | 含义 |
|---|---|
| A | 同病例受控干预/清晰消融，且端点直接测目标机制 |
| B | 论文与官方代码可交叉核验，但缺完整日志或严格因果隔离 |
| C | bundle-level、观察性或叙述性证据；内部 mediator 未识别 |
| D | 主项目冻结日志、Git blob 与根审端点的直接证据 |

“截至研究日未发现作者官方仓库”只表示论文、作者主页、题名及组织检索未定位到官方链接，不是永久不存在的断言。第三方仓库不冒充官方实现。

### 1.3 当前主端点

本报告沿用最新端点合同：

- `clinical-complete`：主能力端点；
- `compatible-partial`：相关父类/组件/欠特异对象，不能报作完整正确；
- `safe-exact`：高精度保守下界；
- `legacy-chain`：历史 substring/resolver 指标，仅用于复现；
- DA task mapper 与 MCR task judge 分层解释。

因此，文献中的 MCQA accuracy、majority agreement、诊断列表 recall 或 simulator reward 均不会直接换算成本项目的完整诊断对象正确率。

---

## 2. 文献不是一条“多人会诊进化史”，而是六个技术根

| 技术根 | 代表工作 | 真正操作对象 | 对本项目的价值 |
|---|---|---|---|
| generic debate | Are We Going MAD? | 独立答案、共享答案、多轮修订与聚合 | 研究信息拓扑与锚定，不迁移医生隐喻 |
| MDT/persona | MedAgents、MAC | 专科角色、总结、协商、supervisor | 提供组织模板，但 persona 多样性未被验证 |
| adaptive collaboration | MDAgents、MCC | case-level complexity 或 disagreement gate | 保留条件计算思想，路由信号需重构 |
| heterogeneity | MCC、Mixed-Vendor MAC | 不同底模/供应商的错误通道 | 支持 error decorrelation，不证明 conversation 必要 |
| structured verification | MedLA、peer-reviewed reasoning、MARC、CF-MAR | premise、reasoning chain、consistency/counterfactual score | 把分歧下沉到边；不能相信自由 premise 或自评 confidence |
| dynamic diagnosis/control | MEDDxAgent、MeDxAgent、MAI-DxO、ClinicalAgents、MDTeamGPT | 操作调度、信息可见性、搜索/backtrack、memory | 借鉴 typed operator、显式 state、回退；静态 posterior ranking 不照搬 simulator |
| audit/negative results | MedAgentBoard、MedAgentAudit、ClinDiag、AgentRx、MedicalAgentsBench | 跨任务 benchmark、过程失败、模态交互、hard-set | 限制“MAS 默认优越”的主张并定义验收指标 |

`MAS.md` 把这些工作按五条讨论线串联是有用的阅读框架，但算法迁移时必须保留上述独立根。许多后作不是前作的直接修补，而是在不同任务、不同 endpoint 上重新发现“多调用如何不浪费或不互相污染”。

---

## 3. 论文与代码机制解剖

### 3.1 Generic debate 与第一代医疗 MDT：增益不能自动归因于“医生协作”

#### Should We Be Going MAD?（早期题名 Are We Going MAD?）

[论文](https://arxiv.org/abs/2311.17371)比较 single、self-reflection、multi-agent debate 等信息拓扑。[官方 DebateLLM `1386095e`](https://github.com/instadeepai/DebateLLM/tree/1386095e4200dec07f6aa11b76df201590f1d075)实现 RoundRobin、Google-style agreement prompt、angel/devil/judge 和 majority。最关键的结果不是“debate 普遍纠错”：完整 MedQA 上 MedPrompt .65、Society of Mind .64、Ensemble Refinement .64，而原始 single 与若干 debate 约 .60；Multi-Persona 反而 .58。在特定 376 条 USMLE 子集上 Multi-Persona 可高约 15pp，但其最终轮低于首轮；高 agreement 对 MedQA/PubMedQA 有利，对反直觉 CIAR 有害，Mixtral 上超参也不迁移。

这支持的是**协议和 agreement prompt 改变答案分布，且高度依赖数据先验**，不支持“交换证据天然有益”。仓库只有 `imgs/results/` 的 16 张静态图、Hydra config 和画图 notebook，没有 raw JSON/CSV 或逐案轨迹；也缺等 token/call 基线。`RoundRobinDebateQA` 逐轮暴露他人回答，末端 majority；early-stop 尚留 TODO。因此不能把结果归因于独立医学知识或 persuasion quality。

对本项目的迁移只应是 **独立先验 + 通信消融**：先冻结三个原子输出，再实验性 reveal；不能让 Forest 的初始 top-1 进入 IMPC/Collapse3c prompt。

#### MedAgents

[论文](https://aclanthology.org/2024.findings-acl.33/)的五阶段是 expert gathering → 独立分析 → report summarization → consultation → unanimous final report。GPT-3.5 平均 MedAgents 72.1，direct 67.8、CoT+SC 70.9；GPT-4 为 86.7 vs 80.6/83.0。MedQA 的顺序加模块是 49→55→62→65→67，但这是 nested bundle，不是 factorial。20 例 domain 消融更具机制意义：删最相关专家 63.8→60.5，删最不相关专家反而 63.8→66.2，说明 relevance/noise gate 比“专家越多”可靠。

[官方代码 `aaeff049`](https://github.com/gersteinlab/MedAgents/tree/aaeff0499e169b41faf810cbca59504e3ee2788c)的 `utils.py:fully_decode` 按 `args.max_attempt_vote` revision，`run.py` 默认和 `inference.sh` 均为最多 3 次，直到所有专家回答 YES；论文实验叙述与此配置边界并不完全一致。这只证明系统追求一致，不证明一致是正确代理。代码所有调用 `temperature=0`，论文却写 1.0；随仓只有 `datasets/MedQA/test.jsonl`、prompt 和代码，没有运行日志或正式结果 config。调用数、persona、summary、讨论和聚合同时改变，+4.3pp 不能独立归为 collaboration。

可迁移：多个候选通道先独立输出、显式记录来源。不可迁移：按专科名称给同一底模分配“知识独立性”、迭代到全票一致、用 summary 覆盖原始 claim。

#### MAC

[npj Digital Medicine 论文](https://www.nature.com/articles/s41746-025-01550-0)在 302 个 rare-disease cases 上模拟多个医生、supervisor 与 case-specific specialty assignment。GPT-4 四医生初始 Top-1/possible diagnosis/tests 为 34.11/48.12/78.26%；两至五医生的 follow-up 是 51.99/53.31/53.86/50.99，并不单调。去 supervisor 只从 34.11 降到 32.67，case-specific specialties 没有显著提升；13→25 rounds plateau，自我修订或 SC 过多也下降。可确认的只是 **MAC 整包改善了若干候选/列表端点，而人数、轮数不单调且专科分配无显著益处**；“独立候选覆盖 + 有限 fusion”只是与结果一致、仍需 equal-budget independent-union/no-chat baseline 验证的解释假说。

[官方仓库 `896a5de`](https://github.com/geteff1/Multi-agent-conversation-for-disease-diagnosis/tree/896a5deb4d6db7a2c872630a6638da4da3b0f4d4)用 AutoGen GroupChat 的 `speaker_selection_method="auto"`，默认 3 doctors、13 rounds，并有无 supervisor/专科分配分支；仓库没有输出 conversation、summary、log 或 result。它也没有等预算 independent-union 或只融合不对话基线。对本项目最多迁移 supervisor 的**合同检查职责**，而不是让 supervisor 再做自由诊断。

### 3.2 Adaptive collaboration：保留条件计算，拒绝粗粒度 router

#### MDAgents

[论文](https://arxiv.org/abs/2404.15155)将任务先判为 low/moderate/high complexity，再映射到 solo、group collaboration 或更强协作。10 datasets × 50 samples × 3 seeds 上 adaptive 81.2，固定 low/moderate/high 为 64.2/71.6/65.8；base 71.8，+MedRAG 75.2，+moderator 77.6，两者 80.3。它支持“预算不必固定”，但复杂度人工可靠性仅 ICC(2,k)=.269、ICC(3,k)=.280，且 router 预测的是主观 difficulty，不是哪个分支对该病例有正 conditional treatment effect。adaptive 平均 9.3 calls，固定高协作 N5 为 20.3；比较仍混合预算、prompt、RAG 和 moderator。

[官方仓库 `3adbd76`](https://github.com/mitmedialab/MDAgents/tree/3adbd760ca809b4e7b0c1085d68314b6e7d91e1b)与论文严重错位：`utils.py:Agent.chat` 把多个 GPT-4/4o variant 实际映射到 `gpt-4o-mini`；difficulty classifier 硬编码 GPT-3.5；advanced 分支最后只消费 `initial_assessment_report`，丢弃后续 compiled team reports；论文的 MedRAG/moderator-review 也未完整实现。仓库缺 data/results/logs/config，不能由公开 commit 重建表格。

本项目不应预测一个全病例的 `complexity`。正确粒度是：只有当某条候选边出现可观察的 identity/polarity/time/scope/interaction/comparator 分歧，才分配对应 verifier。

#### MCC

[Cell Reports Medicine 论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC12866169/)把异构模型 confrontation、critique/self-reflection 与协作组合。MedQA 1,273×10 runs：MCC 92.6±.3，单模型 o1-mini 84.8、QwQ 81.8、DeepSeek-R1 89.7。最有信息量的是条件分解：1,019 个初始 unanimous 中 938 对、81 错；254 个 disagreement 中 initial majority 201/254，MCC 241/254。但也有 13 个“至少一人初始正确→最终错误”，其中 9 persuasion、4 suppression。由此支持的是**分歧门控 critique 有救回机会且有负外部性**，不是 consensus 等于真。

[官方仓库 `56c282b`](https://github.com/sunxinti/MCC/tree/56c282b971c692da285da19c2aafccc999516615)有 2,865 个 `.txt` 逐案日志（MedQA 1,273、PubMedQA 500、六个 MMLU 医学/生物子集 1,089、LFQ 3），记录初答、critique、revision、consensus 和 correctness。`logs/MedQA/case_0.txt` 展示三模型一致选错并直接停止。实现按 GPT→Qwen→DeepSeek 顺序更新、每次更新后检查 consensus，存在次序锚定；`check_consensus` 先过滤解析失败，可能把“两路 None + 一路有效”误判 consensus。日志只有一轮可见 run，不能重建论文 10-run 均值；代码还存在明文 live-looking credential fallback（本报告不复制值）。

这些轨迹能审计 new claim、翻转和 suppression，却没有随机化 reveal、来源匿名、答案-only critique 或等预算静态异构 ensemble，不能证明某次翻转是 evidence 而非 authority/position bias。VE-MAS 只迁移 observable-disagreement gate 和 harmful-persuasion audit。

### 3.3 Diversity：优化错误去相关，不优化角色名或厂商数

#### Mixed-Vendor MAC

[HEALing 2026 论文](https://aclanthology.org/2026.healing-1.1/)保持主要交互结构，改变 single-vendor 与 mixed-vendor team 组成，是相对更干净的 heterogeneity 实验。Combined RareBench mixed R@1/3/5/10 为 39.31/49.82/55.05/61.35，best same-vendor 36.63/48.06/50.53/57.06，best single 37.58/47.79/50.84/56.41。DiagnosisArena 165 例 mixed Top-1/5 为 36.36/49.09，OpenAI same-vendor 35.76/47.88、single o4 32.12/46.06；相对 same-vendor 只有约 1–2 病例且无配对 CI。MME 40 例的结果也受极小样本限制。overlap analysis 同时出现 6.82%–14.1% loss，证明 diversification 会破坏原正确。

[官方仓库 `cb5fd0a`](https://github.com/rajpurkarlab/mixed-vendor-mac/tree/cb5fd0a782fd51ada06e56b6ea57cedef21943e1)可核验 per-vendor agents、round-robin、supervisor 与 trajectory 保存逻辑，但没有 committed logs/results。RareBench mixed 实际使用 Gemini supervisor，而论文称默认 o4（除注明外）；输出 label 仍拼接 `gpt4o`，会污染 provenance。primary judge 又是 o4，只有 HMS 有人工 adjudication，blind protocol 描述不足。

因此不能得出“heterogeneous conversation 必需”：仍缺“相同异构初答 + 无对话 union/vote/frozen selector”的预算匹配基线。本项目已有更直接的日志证据：Forest/IMPC 的平均主池 Jaccard 为 .471，而它们与 Collapse3c 约 .318–.319；但 800 例上稳定题型专长先前没有越过复制噪声门。应在线测量具体 claim/error decorrelation，而不是静态按专科分配原子。

#### MCC 的 model heterogeneity

MCC 的异质性与 confrontation 同时变化，机制隔离弱于 Mixed-Vendor MAC。可迁移变量应从 `vendor_id` 改成：新候选率、独特正确 evidence edge、错误相关、对相同负证据的误读相关和校准后的 marginal information gain。

### 3.4 Structured verification：通信单位必须从 opinion 降到 typed edge

#### MedLA

[论文](https://arxiv.org/abs/2509.23725)用 P/D/M/C agents 构建 premise、atomic subquestion、syllogism tree 与 High/Medium/Low credibility，只交换并修订 low-confidence nodes。MedQA full 62.6，依次去 revision/credibility/logic 为 58.4/57.3/56.1，majority vote 54.8；但这是 nested 顺序消融，不是 factorial。论文正文还把 full→no-revision 的实际 −4.2pp 写成约 −2.2pp，并低报去 logic 的损失。BioASQ latency 3,657s，majority 1,853s，且使用 17 subagents。

[官方仓库 `5c12cfc`](https://github.com/alexander2618/MedLA/tree/5c12cfc8d67170b1f4b131b9c120a54a573c634d)与论文架构严重不一致：现有 `main.py` 只有一个 `LogicAgent` 与 N 个 generic elimination agents，没有 Premise/Decompose/Credibility/tree merge；初轮 logic report 后续不重算，`agents_talk` 对每个独特答案随机留一条 representative 并丢弃支持数。README 所称目录不存在，CLI 还缺 `--wandb` argument、含 `url.ednswith` typo。11 个约 3.6MB HTML 是 Plotly/Sankey 可视化，不含 W&B history、metric/config 或完整日志。

真正可迁移的是把“你同意整个答案吗”改为“你不同意哪条 premise/edge”，而不是 syllogism 名称。若 premise 未绑定原始事实，结构化只会让错误更整齐。

本项目应把 premise 替换为可审计的 typed claim：

```text
(fact_id, candidate_id, role, polarity, temporality, subject,
 episode, object_scope, source_span, provenance, verifier_status)
```

只有 verbatim span、合法 subject/time/scope 和候选相对方向同时成立，edge 才能进入融合。

#### Let LLMs Judge Each Other / peer-reviewed reasoning

[论文](https://arxiv.org/abs/2606.15419)让多个 reasoning chain 独立生成，再由 heterogeneous reviewers 对每个候选打 0–5 分并取均值，选择最高链而非多数答案。同 composition 的 Llama+Phi+GPT-oss peer 为 .816，majority .788；四 agent peer .820，majority .761。它至少是一个**冻结已有候选的 reviewer-score selector**，不会产生新答案；“强 evaluator 真正识别了 reasoning quality”尚未被隔离。成本是 N solver + N² judge calls。

[官方仓库 `a90b957`](https://github.com/Learner4everrr/Multi-agent-peer-reviewed-framework-for-MedQA/tree/a90b9578849c70aa23c8706dd554f923ae791475)无 README、requirements、dataset、results 或 logs。代码对所有 reviewer×candidate 求均值、`np.argmax` 平局取首候选；论文报告的 .820 又是 test 上 sweep 26 个 model combinations 后的最优值。majority baseline 代码用 `np.unique` 先排序，tie 实际选字母序最小答案而非论文所称 generation order；默认 `get_judge_prompt()` 声明 0–5 scale，却没有 0/1/…/5 的细分 rubric，详细 rubric variants 又未由默认 `judge` 路径调用；小数解析还会 exception→0。缺 rationale-shuffle、answer-only、等调用 meta-selector、人类 rationale validity 与 leakage audit。

因此迁移时 peer review 只能变成**镜像、冻结、候选对比较器**，且先做 answer-only/rationale-shuffle 校准；不能把自由 chain 的平均自评作为 posterior。五个模型上 mean peer score 与 single accuracy 的 `r=.91,p=.034` 仅有五个点，rubric 又含 correctness，近乎循环论证。

#### MARC

[论文](https://arxiv.org/abs/2603.24481)让同一个 Qwen2.5-7B 的四个 specialty prompts 各给答案、rationale 和 raw confidence，再从每条 reasoning 生成四个 verification questions；无 explanation 与带 explanation 两条件的答案 token 相似度低则记 inconsistency，`S=C0×(1-I)`，fusion 实际按每个答案支持者的 S 总和选择。初答是 greedy/T=0；verifier 用固定 MD5 seed 的温度采样。

MedQA-250 的 single accuracy/ECE/AUROC 为 .544/.355/.574，full .592/.091/.630；但 MedMCQA-250 multi-no-verification accuracy .468，full 反而 .440。C2 verify-only 在 3/4 数据集降低 AUROC。10k bootstrap 主要确认 ECE 下降，accuracy/AUROC CI 均重叠。底层机理更像把约 .90 的过度自信机械压到约 .55，从而改善 calibration；inconsistency 不是稳定的 casewise error detector，只能软降权/abstain，不能 veto。

[官方仓库 `44e0364`](https://github.com/jraymartinez/marc-medical-calibration/tree/44e0364c77125571f429b4404075b77413a853fa)提交 4 个 main JSON（700 cases×4 configs=2,800 case records）和 5 个 per-specialist JSON（800 question-runs×4 specialists=3,200 records）。C2 每例保存最终 `S_score`，但缺 I；C4 缺各 specialist 的 S、完整 rationale、verification questions、independent/reference answers 与 fusion debug，因而仍无法逐案审计 mediator。当前脚本新增了 C3 `per_specialist` 保存路径，已提交的四个 main artifact 却仍是旧 schema，存在 code–artifact provenance mismatch。high-disagreement 补样脚本也会从 `additional_pool` 随机补而不检查实际 disagreement。

本项目应保留 calibration 的 abstain/tie 功能；多个原子一致重复同一错误，不会因为一致或自洽而变真。

#### CF-MAR

CF-MAR 已在上一轮 [counterfactual 专项审计](COUNTERFACTUAL_INFERENCE_MECHANISM_TRANSFER_AUDIT.md) 中完整处理。结论不重复展开：可用的是 fixed-candidate、signed-direction、validity-gated disputed-edge audit；公开实现的 absolute label-shift、未冻结候选、fail-open SIP 与自由诊断 token probability 不能进入 VE-MAS。

### 3.5 Dynamic diagnosis：借鉴状态机，不照搬互动模拟器

#### MEDDxAgent

[论文](https://arxiv.org/abs/2502.19175)把 history-taking→retrieval→diagnosis 写成模块循环。GPT-4o iter3 fixed/dynamic 的 GTPA@1 分别为 DDxPlus .86/.81、iCraft .54/.52、Rare .50/.46；多数设置 fixed 更好，但 Llama8B/Rare dynamic .18 高于 fixed .07，所以论文的 “consistently” 过强。它识别的是**强制动作覆盖和显式 DDx 随新信息更新**，不是 MAS 医生互补。每域只 100 例，iteration 同时增加问答、RAG 和诊断调用，GTPA 又不是 root clinical-complete。

[官方仓库 `b62a451`](https://github.com/nec-research/meddxagent/tree/b62a451a6a1fcc9a4f8b7fd3f338af2b29c7a323)的 `DDxDriver`、`FixedChoice`、`OpenChoice` 与 patient simulator 可核验。`OpenChoice` 会在无 profile/最后回合强制 history/diagnosis，但缺 gap-value、重复问题或动作覆盖约束；它计算了 conditional `previous_search_content`，实际却始终传全部 final RAG，代码意图与执行不符。MedRAG 分支还直接 `print(...); exit()`，明注未使用。

随仓只有两个 patient logs。更关键的是它们揭示 dynamic few-shot 的答案先验：patient_1 的四个检索示例都明示 `ground truth pathology: Allergic sinusitis`，patient_2 的四个都为 Bronchitis；RAG 还把 allergic sinusitis 检成 allergic fungal sinusitis。故大增益不能全归于迭代/MAS。可迁移的是 fixed/triggered phase、ranked DDx ledger 和 gap→query；静态任务只能检索已有 vignette span/批准知识库，不能模拟患者新答案。

#### MeDxAgent

[论文](https://arxiv.org/abs/2606.03416)最强的受控结果是 information timing：同一个 Differential Questioning 只改启用 turn，turn 2/5/10 的平均 accuracy 为 34.7/50.4/52.8，相差 18.1pp。底层是探索期候选未成熟时的 diagnosis-conditioned questioning 会确认偏误，先候选盲覆盖、后判别提问更安全。Combined Flow 52.8；paragraph/structured summarizer 单独升到约 54.9/54.6，full 57.4、oracle 66.8（paragraph summarizer 在 Appendix Table 7 又写 55.2，论文内部相差 .3pp）。Specialist/KG/Evidence Gap 单独为 51.1/51.7/50.6，均低于 Combined Flow，只有组合后提高；因此信息拓扑含高阶交互，不能把 agent 名单的主效应相加。

[Microsoft Research 页面](https://www.microsoft.com/en-us/research/publication/medxagent-multi-agent-consultation-for-interactive-medical-diagnosis/)明确写代码和数据待正式发表后发布；研究日未发现作者官方仓库，第三方实现不补位。论文的 best-so-far 与 leave-one-out 不是全因子，judge 又接受 synonym/paraphrase，没有 root clinical-complete census；“关闭 early stopping”对比也不证明 confidence calibrated。

对静态 posterior ranking，应预注册 `candidate-blind extraction → prior isolation → independent pair judgment → conflict reveal → verifier` 的信息顺序，并逐段做 ablation。

#### MAI-DxO / Sequential Diagnosis / SDBench

[论文](https://arxiv.org/abs/2506.22405)的 MAI-DxO 其实是**一个 LM 顺序扮演五个功能算子**：Hypothesis、TestChooser、Challenger、Stewardship、Checklist，不是五个独立知识源。对 o3，baseline 78.6%/$7,850，no-budget MAI 81.9%/$4,735；论文 10k paired permutation 明示 accuracy gain 不显著、成本降幅显著。budget 版本 79.9%/$2,396；batch 与 single test accuracy 都 83.9%，single 更便宜。最有力机制是显式 posterior + falsifier + stewardship 移动成本 Pareto 点，不能把 +3.3pp 写成已确认 accuracy gain。

SDBench Gatekeeper 持有完整 CPC 与最终诊断；原文缺结果时会生成不标注为 synthetic 的一致性发现。只审计显式 label leakage 不证明生成环境分布正确。judge 以 5 分 rubric、≥4 为正确，更接近 compatible-parent/near-complete。研究日未发现作者/Microsoft 官方代码；`The-Swarm-Corporation` 自称第三方 paper implementation，已排除。

VE-MAS 对应的 functional operators 应是 `identity_resolve`、`exposure_gap`、`polarity_check`、`temporal_bind`、`object_project`、`interaction_audit`、`mirrored_compare`，而不是专科身份。

#### ClinicalAgents

[论文](https://arxiv.org/abs/2603.26182)用 typed working state、stage-valid action、missing-evidence trigger、snapshot rollback 与 dual memory。Table 6：Backbone .4521，+Dual Memory .4762，+Orchestrator .4962，All .5107；但 +Dual 同时含 working+experience，+Orchestrator 又含 working+search/backtrack，没有 working-only。诊断子任务 Backbone .5754、MedChain-Agents .5863、All .5976，相对最强 MAS 只有 1.13pp；总平均更多来自 referral/test ordering。

[官方仓库 `e7dbd15`](https://github.com/ZhuohanGe/ClinicalAgents-Code/tree/e7dbd15513235e388cbb0dc0afafdfcbacefe420)所谓 PUCT 实际是 `Q + λ×LLM_prior`，没有 visit-dependent exploration bonus；对 Top-K actions 各做相同 N 次 rollout。真正机制是 LLM-prior Top-K + 等额模型模拟 + gap/confidence reward，不是经典 MCTS。专业 action 又用 benchmark `ground_truth` materialize exam/imaging，不适用于静态推理。仓库 29 个 tracked files，但缺 `app_config.py`、`experience_memory.py`、requirements、数据、config 和所有运行结果，不能复现。

可迁移的是 typed immutable snapshot、action validator、gap ledger 和 bounded rollback；不采用 LM 模拟 future evidence 或 self-confidence reward。不可逆删除改为 append-only，验证失败保留 tie/abstain。

#### MDTeamGPT

[ACL Findings 论文](https://aclanthology.org/2026.findings-acl.1427/)把 long-dialog context collapse 与 Residual Context、Lead Physician、CorrectKB/ChainKB 结合。baseline 76.3，Residual-only 75.9（有害），Lead-only 76.8，Residual+Lead 81.0；说明机制是结构化 Consistency/Conflict/**Independence（unique viewpoints）**/Integration/Tools/Experience 分槽与短滑窗的**交互**，不是普通摘要，也不能把 Independence 自动升级成已验证 evidence。再加 CorrectKB 86.4（+5.4），ChainKB 82.3（+1.3），两者 87.7；最大增益来自含 `Question/Answer/final summary` 的 outcome-supervised retrieval，不是纯 T0 self-evolution。

[官方仓库 `9c80d6b`](https://github.com/KaiChenNJ/MDTeamGPT/tree/9c80d6be76fee4eb527c12bace54b3ae474065d7)只有 8 个 demo/code files，无 benchmark、KB、log、result 或 config。论文说 Round 1 不用 KB、Round 2+ 冲突后注入，代码却在 Round 1 前检索并把 KB 传给全部 specialists；论文 K=5，代码默认每库 k=2。Safety reviewer 只看 Lead summary，不看原始 claims。因而 memory 污染、答案泄漏和 context-collapse stress test 都不能由随仓轨迹复查。

VE-MAS v1 只迁移 residual principle：原始 vignette、原始 atom claims、每次 verifier patch 均不可变并可按 hash 重建；任何总结仅为 view，不得成为唯一 state。v1 **无条件关闭全部跨病例 memory**，包括答案、真值、成功/失败 exemplar 与 policy memory；未来若研究 answer-stripped policy memory，必须作为单独预注册扩展，不能混入当前合同。

### 3.6 领域审计与负结果：定义 VE-MAS 必须越过的门

#### MedAgentBoard

[NeurIPS Datasets and Benchmarks 论文](https://proceedings.neurips.cc/paper_files/paper/2025/hash/d59aa09699530c00d4b875a883876641-Abstract-Datasets_and_Benchmarks_Track.html)跨文本 QA、medical VQA、EHR prediction、lay summary 和 workflow 比较单/多 agent 与 conventional methods。强基线常胜：MedQA DeepSeek-V3 CoT-SC 89.90，高于 best MAS 85.25；PathVQA MUMC 91.40，高于 MAS 75.90；MIMIC mortality AdaCare 94.28，高于 single GPT-4o 85.99 和 ColaCare 82.91。workflow agent 的 completeness 收益与 Python 执行、工具、状态和更多 calls 绑定，不能归因 persona discussion。它真正支持的是 **MAS 效用高度 task-conditional**。

[主仓库 `20bd048`](https://github.com/yhzhu99/MedAgentBoard/tree/20bd04818819d84b20264f6d333ea19bd3c16502)与 [Task-4 仓库 `cab28a5`](https://github.com/yhzhu99/MedAgentBoard-WorkflowAutomation/tree/cab28a55e308140f3dde7126911237455608f3b7)链接的[官方日志归档](https://drive.google.com/file/d/18N2ZFc86M6jF5dnDjMXtA7YN3bW02bxu/view?usp=sharing)（Drive file id `18N2ZFc86M6jF5dnDjMXtA7YN3bW02bxu`）为 2,005,920,088 bytes、22,150 entries，解压 3,434,734,626 bytes。主日志含 QA 13,847、lay-summary 2,000、EHR 600 条，`case_history` 保留 rounds/opinions/synthesis/reviews/decision，但无逐例 token usage；MIMIC 受 PhysioNet 限制未发布。

代码 `medagentboard/medqa/single_llm.py:SingleModelInference.process_item` 还有会污染精确表值的 parser：以 `if option in predicted_answer` 搜索 A/B/C/D，verbose response 中普通字母 `a` 即可映射 A。代表日志 `logs/medqa/MedQA/multiple_choice/SingleLLM_zero_shot/medqa_mc_002-result.json` 的 raw 为 `The correct answer is: D`，却持久化为 A；对三个选定 200-case MedQA 设置重放发现 13/17/9 个 mismatch。论文大方向未反转，但精确单体数不能视为无误差机制证据。

#### MedAgentAudit

[论文](https://arxiv.org/abs/2510.10185)把 accuracy 黑箱拆成任务理解、角色/讨论、synthesis/final 三阶段 failure。当前代码 HEAD 是[官方仓库 `82ca645`](https://github.com/MedX-PKU/MedAgentAudit/tree/82ca645bb16f77ace48449b457e2edff76e54767)，数据则冻结于[官方 `datasets_and_logs` release](https://github.com/MedX-PKU/MedAgentAudit/releases/tag/datasets_and_logs) tag commit `5e964353e4c88e7b409d67f4736b39cdd1784695`：195,251,003-byte archive，909 entries，解压 919,812,039 bytes。其 source collaboration 为 36 JSONL/3,600 cases，audit 144/14,370 valid（计划 14,400；GLM PathVQA 过滤），single 24/2,395；另有 extracted open-coding 35 files/677、audit-human 20/400、shared open-coding-human 33/330、invalid 6/27。正文写 shared open-coding 360，而 release/补表为 330，必须保留不一致。`case_history.rounds` 保存 opinions/synthesis/reviews/decision，audit 每步给十种 mode 的 status/reasoning。

观察率包括 minority suppression 514/10,056=5.11%、authority bias 2,893/10,056=28.76%、repetition 9,660/9,815=98.42%、unresolved conflict 916/9,815=9.33%。auditor 在 balanced 400 validation 上 macro-F1 .845、sensitivity .965、specificity .808、Fleiss κ .631；这不是自然流行率抽样。authority bias 从 R1 synthesis 35.30% 到 R3 68.75% 混入只有继续到后轮的 case/framework survivor，不能解释为轮次造成的因果增长。

只读重算 144 个 MAS–matching-single 单元为 57 胜/17 平/70 负，unweighted mean −.42pp；只有 post-hoc 每任务六框架挑最优才 +3.08pp，是 oracle 选择。旧 `yhzhu99/MedAgentAudit` 的 KEU/M1–M4 narrative 不在当前论文中获得量化因果支持，旧 Zenodo 又已不可用；不能混成新仓机制。观察性标签能定位 failure，却不能证明 preserve minority 必然提高最终正确率；VE-MAS 必须随机 preserve/drop edge。

#### ClinDiag

[Nature Communications 论文](https://www.nature.com/articles/s41467-026-70274-w)的主轴是动态诊断 workflow 与 SFT，而不是新的 MAS 聚合算法。4,421 例的 exact ablation：GPT-4o-mini baseline 29.45%、critic 28.93%（ns）、2 doctors 30.04%（ns）、3 doctors 31.51%（+2.06pp，p=.0006308）；Qwen2.5-72B baseline 34.09%，critic 32.05%、2 doctors 29.33%、3 doctors 32.07%，均显著更差。最多支持“同协议高度依赖底模，三 GPT-mini 有小幅 bundle 收益”，不支持通用 MAS 或 critic 机制，而且 calls 未匹配。

[官方仓库 `f9b5c18`](https://github.com/geteff1/ClinDiag/tree/f9b5c181e8d120d6a244accba9422ffb89d1f319)（tag v1.0 同 SHA；[Zenodo](https://doi.org/10.5281/zenodo.18159952)）的 benchmark archive 含 2,021 case directories（1,719 challenging、302 rare）；ZIP 总计 13,141 entries，排除 `__MACOSX` 后为 10,142 payload files。2,400 MIMIC emergency cases 未公开。仓中没有生成 run/result/interaction logs，只有一个 sample 与 scripts。`trial_multidoctor.py` 用 AutoGen round-robin、Doctor0 汇总；`trial_critic.py` 在每 stage 做 doctor↔critic/provider，最多 50 rounds。没有轨迹就无法审计 correct-minority 或 persuasion。

对本项目意味着：645/800 例没有任何原子给出根审 complete，末端 architecture 不能凭组织形式制造缺失能力；这些病例才需要经过独立验证的 typed residual generator/retrieval。另有 33/51 个 unique-correct 病例中，正确原子 champion 的规范化标签未出现在两个错误原子池，但已由正确原子暴露到三池 union；这里的首要任务是保留独特 proposal，而不是要求错误原子也重复生成它。

#### AgentRx（multimodal clinical prediction）

这里指 [NYUAD-CAI 的 multimodal clinical prediction benchmark](https://proceedings.mlr.press/v333/al-jorf26a.html)，不是 Microsoft 同名软件工程 AgentRx。Qwen full-context single zero-shot mortality AUROC/AUPRC/ECE 为 .756/.330/.023，unimodal majority .748/.315/.111；HuaTuo 为 .762/.325/.049 vs .711/.245/.050；conventional MedPatch .877/.546/.019。Qwen debate .631、MetaPrompt .599；Traj-CoA .762，但最终 judge 仍直接见原始多模态。Qwen 4,925/4,925 cases 在 peer exposure 前第一轮已一致，反映 correlated initial outputs/premature consensus，而不是 sycophancy；MedGemma 初始分歧的 75/76 才是在 exposure 后跟随首轮多数的 echo-chamber 现象。

[正确官方仓库 `6b30c7e`](https://github.com/nyuad-cai/AgentRX/tree/6b30c7ed9eae76768e7d4b3b9fd0c43aa1b32159)有 321 tracked files/65MB，主要是 MIMIC extraction resources，没有论文 outputs/results/interaction traces。实现的 unimodal majority 是 probability 算术均值；即使 debate，通常只保存最终 vote summary，不留完整 peer reasoning。结果与“modality partition + arithmetic/free-text fusion 的整包损失 joint information”一致，但 full-context 与 MAS 同时改变了信息切分、prompt、调用图和聚合，cross-modal interaction mediator 未被单独随机化；更不支持“所有 MAS 失败”。

这对三原子系统是硬警告：不能把同一证据按 agent 隔离后只传摘要。原始事实 ledger 和候选相对 claims 必须允许 verifier 检查跨模态/跨事实 interaction。

#### MedicalAgentsBench

[Patterns 2026 论文](https://www.sciencedirect.com/science/article/pii/S2666389926001194)在模型准确率低于 50% 的 hard set 上比较 internalized 与 externalized reasoning。o3 bare zero-shot 约 28.0、CoT 33.05、Self-refine 32.66、MDAgents 35.22；MDAgents 相对强单体 CoT 只有 +2.17pp，却平均 cost .0262 vs .0050、time 77.2s vs 31.3s，且无 paired significance/compute match。GPT-4o 上 AFlow 29.83 又高于 MDAgents 24.18/MedAgents 25.91；GPT-4o-mini Self-refine 20.77 高于 MDAgents 17.16。它只说明某些 hard-set/model/method bundle 互补，不能外推临床能力。

[官方仓库 `fcb5292`](https://github.com/gersteinlab/MedicalAgentsBench/tree/fcb5292720c28f4168992ee37cda944e452cd098)提交主 `output` 1,385 JSON/385,204 records/约 1.06GB，另 MDAgents 108 JSON/10,219 records、MedAgents 118/11,067 records，以及 792-row baseline CSV；paper-hard predictions 精确为 75,764。MultiPersona/SelfRefine 某些 artifact 保留 rounds/raw responses，但 headline MedAgents/MDAgents 只留最终预测、token/time，没有角色意见/消息/轮次，不能系统审计 persuasion。

决定性 paper-code mismatch 是：论文称 standardized two rounds、MDAgents consistently 3 roles；代码实际 `--difficulty adaptive`。发布 repo label `o3`（论文表中 `o3-mini`）的 MDAgents 2,521 cases 中 2,476 basic、8 intermediate、37 advanced，即 98.21% 未进入 multi-agent branch。basic 自身 accuracy 35.4%，但仍约 8 calls（difficulty、5 few-shot rationale、answer、parser），不是 one-call single；整个 headline 高分仍不能归于 multi-agent。S1 mechanism 只有 5 个选择病例，也不能证明总体因果。其 outputs 适合预算/失败复查，不适合作为 VE-MAS aggregation 选择器。

### 3.7 剥去论文命名后，机制证据落在哪一层

| 待检验机制/设计原则 | 相对 baseline 真正观察到的变化 | 底层机理解释 | 当前识别强度 | VE-MAS 算法实现 |
|---|---|---|---|---|
| independent-first / error decorrelation | mixed-vendor、MCC 与本地三池出现非重叠正确集；但缺等预算 no-chat ensemble | 降低共享盲点与 informational cascade；只有错误不共线时有净信息 | B/观察性，conversation mediator 未识别 | peer-blind atom packet；以独特 validated claim yield 而非角色/vendor 数量衡量 |
| disagreement-conditioned compute | MCC disagreement subset 可救回，也有 persuasion/suppression；MDAgents/动态 router 不可靠 | 把调用预算集中到 posterior 未稳定的局部边，避免一致病例冗余调用 | B，gate 粒度仍待因果实验 | deterministic typed-edge router；case complexity 不作 gate |
| frozen-candidate reranking | peer-review bundle 高于其缺陷 majority baseline；E4 同池换 selector 可大幅改 conversion | 比较器可在不新增 exposure 时纠正 shared-candidate rank | 外部 C+/本地 D；reasoning-quality mediator未识别 | 对全部活跃候选无序对做 mirrored frozen comparator；answer-only/rationale-shuffle calibration |
| consistency calibration | MARC 四个 ECE point estimate 均降，3/4 bootstrap intervals 分离；accuracy/AUROC 不稳定 | `C0×(1-I)` 主要压缩过度自信，而非发现病例真错 | B（calibration），不支持 hard veto | soft risk/abstain feature；不进入 evidence likelihood |
| typed state + information timing | MeDx 延迟 differential questioning 显著；MDTeam residual+Lead 有交互；MEDDx fixed 多数优于 free route | 先探索再利用，保留 conflict/independence，减少确认偏误和 context collapse | B/C bundle；依赖交互环境的部分不可迁移 | frozen fact manifest、candidate-blind phase、append-only views、explicit failure state |
| falsifier + rollback | MAI 主要改善 cost Pareto；Clinical bundle有 snapshot/backtrack，但 value/transition由模型或 GT环境生成 | 反证与可撤销状态可防不可逆早删；模拟 future 不等于真实 evidence | C+ | top-pair challenger、bounded rollback；无 LM-simulated test result |
| preserve joint evidence | AgentRx 与 modality-partition/fusion bundle 损失一致；本地病例有低阶 evidence interaction | 切碎信息后只传摘要/均值会抹去跨事实条件关系 | B，interaction mediator未单独随机化 | 原始 fact ledger共享；summary 仅 view；dependency edge 才调用低阶 CF audit |
| dissent preservation | MedAgentAudit/MCC 与本地 27 个风险例显示正确少数会被压制 | consensus compression 删除低频但高价值 edge，且错误相关使多数不可靠 | 观察性 + 本地 D 风险诊断；保留的治疗效应未识别 | immutable phase-1 claims；union保留 unique proposal；随机 preserve/drop 做因果验收 |

这里的“算法实现”是由证据约束出的原型，不等于这些论文已验证 VE-MAS。真正的确认必须使用第 9 节的同病例、同候选、同预算干预。

---

## 4. 官方仓库与随仓日志：什么能复查，什么不能

本轮只把论文或作者组织明确链接的仓库记为官方。exact commit、关键 locator 与 artifact finding 均冻结在机器 manifest；这里给出解释性总览。

| 工作 | 官方代码状态 | 随仓日志/结果状态 | 可用于机制审计的强度 |
|---|---|---|---|
| Should We Be Going MAD? | DebateLLM，协议/评估/图表代码 | 16 张结果图与 notebook，无逐例轨迹 | B− |
| MedAgents | 五阶段会诊与一致循环可见；temperature 与论文不一致 | 无运行日志/结果 | B− |
| MAC | 角色会话/supervisor 可见 | 无全量 committed logs | B− |
| MDAgents | complexity route 可见，但模型映射/advanced output 与论文错位 | 无 data/result/log/config | C+ |
| MCC | confrontation/collaboration 代码可见 | **2,865 个 case 文本日志** | B+（过程可查，仍观察性） |
| Mixed-Vendor MAC | fixed interaction、vendor config 与评估可见 | 无逐例 committed logs | B |
| MedLA | 当前代码未实现论文完整 P/D/C/tree 架构 | 11 个可视化 HTML，无 metric/trace | C+ |
| peer-reviewed reasoning | reviewer×candidate rerank 可见；baseline tie/parser 有缺陷 | 无 data/result/log/config | B− |
| MARC | verification/S-score/fusion 可见 | 2,800 main case records + 3,200 specialist records；无完整 verification trace | B |
| CF-MAR | 上轮已审计官方实现 | 见 counterfactual 专项 | B− |
| MEDDxAgent | modular loop/driver 可见 | 2 个 patient logs + 2-case result；无论文全量轨迹 | B |
| MeDxAgent | 未发现作者官方仓库 | 无 | C |
| MAI-DxO/SDBench | 未发现作者完整官方实现 | 无 | C |
| ClinicalAgents | orchestration/search skeleton 可见，但缺关键模块 | 无 data/config/result/log | C+ |
| MDTeamGPT | residual/memory demo 可见；Round-1 KB 与论文冲突 | 无 benchmark/KB/result/log | C+ |
| MedAgentBoard | benchmark runner + Task-4 仓库 | 官方 Drive 约 3.43GB 解压；QA 13,847、summary 2,000、EHR 600 主日志 | B+（parser 污染精确值） |
| MedAgentAudit | audit pipeline/schema 可见 | 官方 release：3,600 source、14,370 valid audit、2,395 single | B+（观察性 audit） |
| ClinDiag | training/eval/workflow 与 2,021 public cases | 无生成 run/result/interaction log | B |
| AgentRx | multimodal benchmark 与评估管线可见 | 无论文 output/result/interaction trace | B− |
| MedicalAgentsBench | benchmark/framework 可见 | 主 output 1,385 JSON/385,204 records，另 MDAgents/MedAgents 226 JSON | B+（预算可查，内态多缺失） |

“日志很多”不会自动把证据升为 A。MCC、MedAgentBoard、MedAgentAudit 与 MedicalAgentsBench 的输出允许复查 claim、轮数、答案翻转、过程标签、预算或 evaluator 输入，却没有对 reveal、少数保留、summary 或 discussion 做随机化；不能从单条轨迹或观察率推断协作的因果 mediator。

---

## 5. 三个现有原型究竟提供什么互补通道

### 5.1 离线 census 的血缘与限制

[离线脚本](mas_single_agent_atom_census.py)读取六个冻结数据切片、三个原子臂的全部 `case_stages/*.json`：800 病例 × 3 原子 = 2,400 行。每个工作树文件重新计算 Git blob SHA-1，并与基线提交 `c39a19d...` 的 tree object 对比；再一对一连接 E2 full-800 root-adjudicated replay。验证结果：2,400/2,400 文件、2,400/2,400 endpoint rows、缺失和重复均为 0。

限制必须前置：

- 根审标签评价的是**已服务 champion**，没有根审每个 registry candidate；
- 跨池“标签存在”仅用规范化字符串，不冒充临床同义词 resolver；
- oracle union 是机会诊断，不是可以报告的系统成绩；
- 两个错原子共享 E2 输出簇只标记多数压制风险，不假定未来 aggregator 一定投票。

### 5.2 每个原子的实际通道

| 原子 | complete | partial | 主池均宽 | 平均调用 | 日志中可利用结构 | 当前机制缺口 |
|---|---:|---:|---:|---:|---|---|
| Forest | 107 | 279 | 4.486 | 4.061 | syndrome/mechanism/modality 三轴；1,247 protected；1,913 multi-view candidates | substring identity；重复 span/多视图共识进入分数；selector 会主动拒绝正确候选 |
| IMPC | 98 | 275 | 4.094 | 4.000 | common/uncommon/challenge independent-first；1,321 single-view candidates；不按票删 minority | 同底模+近似 prompt 未证明 error-independent；`agent_votes` 受重复出现污染；view 数仍进入分数 |
| Collapse3c | 122 | 263 | 5.246 | 3.278 | polarity/time/epistemic/modality/specificity/reliability fact ledger；verbatim support/against；对象特异性较强 | generation miss；`contradict_spans` 无 `against_fact_ids`；selector 可误读反证；当前 collapse3c 关闭全局 matrix |

这里的“multi-view”与“single-view”是来源 provenance，不是独立投票。[`mosaic.py`](../../src/agentclinic_tree_dx/mosaic.py) 的 registry score 明确加入 `0.35 × (unique generator_views − 1)`；虽然代码注释禁止 `agent_votes` 进入 likelihood，跨视图重复仍通过另一变量抬分。IMPC 还有 127 个 candidate row 的 occurrence vote 大于 unique view 数，说明原始重复/merge 次数不能解释为医生支持人数。相同文件的 `_match()` 还允许规范化字符串双向包含，不能作为跨原子的安全 identity。

[`aphhm_c.py`](../../src/agentclinic_tree_dx/aphhm_c.py) 中 Collapse3c 的 4,197 个 registry candidates 有 4,165 个 `support_fact_ids`、3,914 个 support spans、2,595 个 against spans，但 `against_fact_ids` 为 0。反证仍是一段未绑定 ledger fact 的文本，不能安全做跨原子 edge merge。

### 5.3 互补存在，但不是稳定专科分工

| 原子对 | champion exact agreement | 主池 Jaccard | complete：左共同/左独有/右独有 |
|---|---:|---:|---:|
| Forest–IMPC | 488/800 | .471 | 82 / 25 / 16 |
| Forest–Collapse3c | 385/800 | .318 | 85 / 22 / 37 |
| IMPC–Collapse3c | 343/800 | .319 | 73 / 25 / 49 |

三者全同 285 例、两同 361 例、全异 154 例。这个结构足以建立 disagreement-triggered audit，但不足以支持病例类型静态 router：先前 R6 的跨臂 exclusive specialization 多数没有越过复制噪声门。正确做法是运行时观察“哪条边为什么分歧”，而不是预先宣称某原子擅长心脏或病理。

按 benchmark family 分解后，互补机会也不是同一种机制：

| Family | Forest / IMPC / Collapse complete | 任一 complete oracle | oracle−best | 恰一原子 complete | 两错同簇 | 正确规范化标签在任一错误池 |
|---|---:|---:|---:|---:|---:|---:|
| DA（n=400） | 14 / 13 / 15 | 26 | 11 | 15 | 8 | 2 |
| MCR（n=400） | 93 / 85 / 107 | 129 | 22 | 36 | 19 | 16 |

DA 的 15 个 unique-correct 中只有 2 个规范化正确标签出现在任一错误原子池；MCR 为 16/36。这个字符串级诊断不能当 ontology recall，但提示 DA 更依赖保留某一原子独有的完整标签/对象组件，MCR 则有更多 shared-candidate evidence/comparator 修复机会。它进一步反对“一种全局讨论协议同时解决两个域”。

### 5.4 去标识轨迹模式揭示需要哪种 verifier

逐轨迹复核只在本地完成；公开报告不列病例 id、reference、三臂预测或逐例 relation。可公开复核的汇总约束为：

| 去标识失败模式 | 汇总锚点 | 不能采用的动作 | 所需 verifier/合同 |
|---|---:|---|---|
| 正确少数面对两个同簇错误输出 | 27/51 unique-correct | majority/unanimity | correct-minority preservation + mirrored pair comparator |
| 正确标签也存在于两个错误原子主池 | 8/51 | 再生成更多同义候选 | candidate-relative polarity/threshold audit + frozen comparison |
| 正确标签只存在于一个错误池或两个都不存在 | 43/51，其中 33/51 两池均无 | 只比较池交集 | append-only union + safe identity + exposure-preserving admission |
| disease、mechanism、manifestation、parent/component 混排 | 定性轨迹审计；未建立全量候选根标签 | 用同一标量直接排序 | mandatory requested-object projection + typed relation |
| 单条 evidence 方向相似而组合排序冲突 | 定性轨迹审计；interaction mediator 未随机化 | 自由讨论或取绝对变化 | low-order signed counterfactual edge audit |

这些模式把下一步干预定位到“保留独特候选—校验对象—校验证据方向/组合—冻结逐对比较”四层，而不是增加第四位总体诊断者。前两行有冻结汇总计数；后两行是轨迹审计生成的待验证机制假说，报告不把它们伪装成已完成 census。

---

## 6. VE-MAS：把现有原型变成单 Agent 原子的算法合同

### 6.1 原子不是“医生”，而是受限证据变换器

每个原子接收同一个 `case_hash` 与原始 vignette；在 phase 1 不可见其他原子输出。其返回值必须满足 [atom_contract_v1.json](results/MAS_SINGLE_AGENT_ATOM_RESEARCH/atom_contract_v1.json)：

```json
{
  "atom_id": "forest|impc|collapse3c",
  "atom_status": "success|partial|failed",
  "schema_valid": true,
  "case_hash": "...",
  "vignette_hash": "...",
  "input_visibility_hash": "...",
  "fact_manifest_hash": "...",
  "requested_object_contract": {
    "object_type": "...",
    "derivation_source_type": "task_prompt|task_schema",
    "derivation_source_hash": "...",
    "reference_blind_verified": true
  },
  "proposal_set": [{"local_id": "...", "label": "...", "object_type": "..."}],
  "claims": [{
    "candidate_local_id": "...",
    "fact_id": "...",
    "role": "support|against|unknown",
    "polarity": "present|absent|uncertain",
    "temporality": "...",
    "subject": "patient",
    "episode": "...",
    "object_scope": "...",
    "source_span": "verbatim",
    "provenance": ["..."],
    "status": "unverified"
  }],
  "local_order": ["..."],
  "unresolved": ["..."],
  "call_count": 0,
  "retry_count": 0,
  "call_ledger": [{"phase": "...", "input_hash": "...", "status": "..."}],
  "packet_hash": "..."
}
```

原子不能写 shared rank、删除其他原子候选、把同意次数写成 likelihood，或在 peer reveal 后悄悄重写 phase-1 输出。三个 packet 共享一个冻结 fact manifest：每个 `fact_id` 带 UTF-8 byte half-open offsets、subject、episode、time、polarity，且必须满足 `vignette_bytes[start:end] == source_span_bytes`。Phase 2 另建全局 candidate registry 和 `atom local_id → global_candidate_id` 映射；atom 自报 alias 一律未验证，不能直接进入 resolver。所有 canonical hash 使用 RFC 8785 JSON。

### 6.2 七阶段算法

#### Phase 0：冻结输入与任务对象

冻结 vignette bytes/hash、全局 fact manifest、允许的 episode/subject 与 endpoint contract。requested object（disease / etiology / complication / subtype / composite）的来源只能是 task prompt/schema，并记录 exact source hash；reference label、选项 mapper、根审结果、臂输出或分数都禁止参与推导。`reference_blind=true` 的自报布尔值不构成证明。没有对象与 fact 合同就不运行全局融合。

#### Phase 1：独立原子运行

Forest、IMPC、Collapse3c 各自基于同一原始病例运行，输出不可变 atom packet。当前调用可并行；任何一个失败不得把另一个 packet 改造成代替输出。失败必须产生显式 `failed/partial` packet、phase completion、schema/error 和逐调用 retry ledger，不能被当作“合法空候选”。其余 packet 可进入 degraded ledger，但只有每个 active candidate 都有 validated object projection、全部 active-candidate 无序对仍有 validated mirrored comparator 时才能给结果，否则 tie/abstain；degraded result 不能报作完整三原子 MAS。

#### Phase 2：安全 identity 与 proposition alignment

只允许 exact、冻结安全同义词或已审计 ontology edge；禁止双向 substring/fuzzy。输出全局 candidate registry、registry hash 和逐 atom local→global mapping。parent/component/sibling/manifestation 必须作为有方向的 typed relation 保留，不能 merge 成同一 candidate；未决 identity 继续分立。Phase 2 后任何 residual/retrieval proposal 只能先获得 `temporary_proposal_id + verbatim label + provenance` 并处于 quarantine；必须追加 registry-delta patch，记录 previous/new registry hash，并以 validated temporary→global mapping 重新走相同 safe identity 合同后，才可 admission 或 comparator，不能由 generator 自造 global id。

#### Phase 3：构建 append-only claim ledger

候选 union 不等于 main frontier。所有 proposal 进入 residual ledger；只有 object-compatible、identity-safe 且至少有一个 verbatim candidate-relative claim 的候选进入待比较集合。原始 packet 永久保留。residual expansion 只有一次预声明预算和最大新增候选数，禁止“新候选→新 gap”递归扩张。

检索输出必须分为两种互不转换的类型：`vignette_observation` 只能引用 fact manifest；`external_medical_knowledge_rule` 必须进入 versioned append-only rule ledger，保存 rule id、source locator/hash、query hash、general relation 与状态，只能提供一般候选关系或 temporary proposal，绝不能物化病例中未观察到的症状、检查或病史，也不能写入 `ObservedFact`。每次检索先 append 带 previous-event hash 的 `unverified` rule event，再由固定 verifier append（而非覆盖）`validated/rejected/unknown` 决策 event，并在每个 event 后更新全 ledger hash；空结果也必须以 query hash 记录 `unavailable`。proposal 引用的 rule id 必须存在且 latest event 为 `validated`，否则只能留在 quarantine/residual；即使 rule 已验证，候选仍须有引用既存 `fact_id` 的 candidate-relative patient claim 才能进入待投影集合。

#### Phase 4：定位并分类 disputed edge

只对下列可观察类型触发**专用附加动作**。分歧 gate 不负责最终证书：即使多个原子同序，所有 active candidate 仍必须先获得 validated requested-object projection，随后对按 global id 排序后的**全部无序候选对**取得镜像 frozen comparator 证书；不存在事后选择“decisive pair”的自由度。

| 分歧类型 | 触发信号 | 对应操作 |
|---|---|---|
| exposure | 某原子提出 identity-safe 独特候选；其他原子无此对象 | typed residual generator / targeted retrieval |
| identity | label 近似但 safe bridge 不同一 | resolver + parent/sibling/component audit |
| polarity | 同 fact/candidate 被标 support 与 against | verbatim polarity/threshold verifier |
| time/episode/subject | claim 指向不同时间或主体 | temporal/episode binder |
| object/specificity | disease、机制、表现、parent/subtype 混排 | requested-object projector |
| dependency/interaction | 单条证据方向相同但组合排序冲突 | low-order counterfactual evidence audit |
| comparator/order | claims 已一致但 A>B/B>A 随顺序或原子变化 | mirrored frozen pair comparator |

#### Phase 5：正交、最小 verifier

Verifier 只见完成该问题所需的原始 spans、全局候选 id 和既有 typed claims；不见原子“身份”、多数和未验证 rationale。必须输出按 dispute type 区分的 tagged patch：proposal、registry delta/identity relation、binding、evidence direction、object projection、counterfactual response 或 comparator；共同字段含 `validated/rejected/unknown`、`consumable`、理由代码、引用 span、input/output hash。preprojection admission set 的每个候选都必须完成 object projection，不以“是否出现 scope dispute”为条件；由 compatible projection 得到的冻结 active set 必须完成全 pair certificate。不得自由引入新 observed patient fact 或新 top-1。

#### Phase 6：append-only edge patch

所有 patch——包括 rejected 与 unknown——都 append 到 audit ledger；原 edge 不覆盖，并保留 `supersedes` 与 verifier provenance。external-rule event 使用独立 hash chain：每次 append 校验 previous-event hash、重算全 ledger hash，并以同 rule id 的 latest valid event 作为唯一状态。只有 `validated && consumable` 的 patch 能改变比较图；引用不存在、hash 不匹配或 latest 非 validated rule 的外部 proposal/claim 均不能激活。`unknown` 不自动支持当前第一名，也不触发删除。

#### Phase 7：确定性 partial-order aggregation

先冻结并哈希 identity-safe、evidence-qualified 的 preprojection admission set；对其每个成员做 requested-object projection。projection 缺失、rejected 或 unknown 立即输出 tie/abstain；明确 incompatible 的候选只能由确定性、可审计 scope-transition 移回 residual。随后冻结一次 active-set hash，按该集合的全部无序 pair 生成固定计划并以确定性顺序验证 AB/BA，比较期间禁止增删或改名。只有 expected pair set 与 validated consumable certificates 精确相等、每对 order-consistent 且非 tie/unknown、全图无环，并且某一候选对其他每个 active candidate 都有直接 `>` edge，才签发 unique-top certificate。任何 coverage 缺口、额外 pair、order inconsistency 或 cycle 都输出 tie set/abstain。最后如需自然语言，只允许从 ledger render，不允许重做诊断。

### 6.3 伪代码

```python
shared = freeze_fact_manifest_and_object_contract(
    vignette,
    object_source="task_prompt_or_schema",
    forbid=["reference", "mapper", "adjudication", "arm_output"],
)
packets = parallel_independent_atoms(shared, atom_specs)
packets = materialize_explicit_failure_packets(packets)
assert immutable_and_same_input(packets, canonical_json="RFC8785")

registry, local_to_global = safe_align(packets.proposals, substring=False)
ledger = append_only_union(packets, shared.fact_manifest, registry, local_to_global)
rule_ledger = new_external_rule_ledger(canonical_json="RFC8785")

for edge in classify_disputes(ledger):
    if not observable_gate(edge):
        continue
    verifier = deterministic_route(edge.type)
    output = verifier(edge.minimal_context)

    for retrieval in output.external_retrievals:
        if retrieval.is_empty:
            rule_ledger.append_chained_unavailable(
                retrieval.query_hash,
                previous_ledger_hash=rule_ledger.hash,
            )
            continue
        for raw_rule in retrieval.rules:
            event = materialize_unverified_rule_event(
                raw_rule,
                previous_ledger_hash=rule_ledger.hash,
            )
            rule_ledger.append_chained(event)
            decision = validate_external_rule_event(event)
            rule_ledger.append_chained(
                decision,
                supersedes_rule_event_hash=event.hash,
                previous_ledger_hash=rule_ledger.hash,
            )

    for patch in output.edge_patches:
        if patch.is_externally_sourced_proposal:
            assert rule_ledger.references_exist_and_hash_match(patch.external_rule_ids)
            patch.force_quarantine()  # latest validated status is checked at activation
        ledger.append(patch)  # validated, rejected, and unknown all remain auditable
        if patch.is_validated and patch.consumable and not patch.is_proposal:
            ledger.activate(patch)

for proposal in ledger.post_alignment_temporary_proposals:
    delta = safe_registry_delta_align(proposal, ledger.candidate_registry)
    ledger.append(delta)
    if delta.is_validated:
        ledger.apply_registry_delta_to_residual(delta)  # identity only; not active admission

preprojection = freeze_and_hash(
    ledger.identity_safe_evidence_qualified_candidates(
        external_rule_gate=rule_ledger.all_latest_references_validated,
        require_candidate_relative_existing_fact_claim=True,
    )
)
projections = {}
for candidate in preprojection.sorted_candidates:
    patch = validate_requested_object_projection(candidate, shared.requested_object)
    ledger.append(patch)
    if patch.is_validated and patch.consumable:
        ledger.activate(patch)
        projections[candidate.id] = patch

if not projections_cover_every_member(preprojection, projections):
    return tie_or_abstain("missing_rejected_or_unknown_projection"), ledger.audit_trace

for candidate in preprojection.sorted_candidates:
    if projections[candidate.id].is_explicitly_incompatible:
        ledger.append(deterministic_scope_transition_to_residual(candidate, projections[candidate.id]))

active = freeze_and_hash([
    candidate for candidate in preprojection.sorted_candidates
    if projections[candidate.id].is_compatible
])
if not active.candidates:
    return abstain("no_object_compatible_candidate"), ledger.audit_trace

pair_plan = all_unordered_pairs(active.sorted_candidate_ids)
certificates = {}
for pair in pair_plan:
    patch = get_or_run_mandatory_mirrored_comparator(
        pair,
        ledger.validated_context(pair),
        trigger_kind="mandatory_final_certificate",
        active_set_hash=active.hash,
    )
    ledger.append(patch)
    if patch.is_validated and patch.consumable:
        ledger.activate(patch)
        certificates[pair] = patch

if set(certificates) != set(pair_plan):
    return tie_or_abstain("pair_coverage_mismatch"), ledger.audit_trace
if any(p.is_tie_or_unknown or not p.order_consistent for p in certificates.values()):
    return tie_or_abstain("non_decisive_or_order_inconsistent_pair"), ledger.audit_trace

order = deterministic_partial_order(
    certificates.values(),
    active_set_hash=active.hash,
    requested_object=contract.requested_object,
)
if order.has_cycle:
    return tie_or_abstain("comparison_cycle"), ledger.audit_trace
return order.unique_direct_dominator_or_tie_or_abstain(), ledger.audit_trace
```

不存在 `ask_supervisor_for_final_answer()`，也不存在 `majority_vote()`。

---

## 7. 三个原子的具体改造

### 7.1 Forest atom

保留：

- syndrome / mechanism / definitive-modality 的正交提名；
- gap/adaptive residual capture；
- main + protected 两车道；
- selector 前完整 registry 与 rejected rationale。

修改：

1. 删除 `_match()` 的 `a in b or b in a`；identity 只由安全 bridge 处理；
2. `generator_views`、axis attachment、重复 span 只作 provenance，不能进入 likelihood；
3. 每个 support/against 必须绑定原始 fact id，并校验 absent/negated；
4. selector 改为原子内部 local order，不具全局删除权；
5. export protected/unique candidates，即使不在 local top-1；
6. A1 只根据 typed unresolved gap 触发，禁止自由“再想一次”。

底层机理：Forest 的价值来自**改变候选生成几何**，使不同证据投影暴露互补对象；不是三个 axis 对同一标签重复投票。把重复视图当加分会把 error correlation 误当独立支持。

### 7.2 IMPC atom

保留：

- D1 common、D2 uncommon/high-specificity、D3 challenge；
- peer-blind independent-first；
- union-first 与 single-view minority lane；
- 不按票数删除候选。

修改：

1. `agent_votes` 明确重命名为 `merge_occurrences`；
2. unique `generator_views` 只作为来源，不进入分数；
3. 三个 view 必须具备不同计算合同和不同 error audit，不能只换一句 persona hint；
4. challenge view 输出反例 edge，不直接追加无证据 mimic；
5. 所有 single-view candidate 保留到 residual ledger，但进入 main comparator 必须有 candidate-unique evidence；
6. phase 1 结束前不可见任何其他原子或 view 的答案。

底层机理：IMPC 只有在三个通道产生**误差去相关的证据/候选**时才有增益。当前同底模、同病例、近似 prompt 造成的重复不是三位独立医生；真正应优化的是独特正确 claim yield 与错误相关，而不是 agreement。

### 7.3 Collapse3c atom

保留：

- `ObservedFact` 的 polarity、temporality、epistemic status、modality、specificity、reliability、correlation group；
- verbatim spans 与 object-specific candidate notes；
- specificity retention、gap obligation 与低调用骨架；
- 当前关闭全局 C4 matrix 的选择。

修改：

1. 给 `ConceptNode` 增加 `against_fact_ids`，与 `contradict_spans` 一一绑定；
2. support/against claim 都校验 subject、episode、time、polarity、object scope；
3. 返回 selector 前 proposals 和 unresolved edges，不只返回 champion；
4. generation miss 由 residual typed gap 处理，不能重新启用未经验证的全局矩阵；
5. `missing` 分为未测量、未记录、测得阴性，禁止 hard shadow veto；
6. comparator 不能把 normal threshold（如 QTc 380ms）自由解释为 disease support。

底层机理：Collapse3c 的优势来自**把证据对象化并保留完整诊断粒度**，不是确定性矩阵分数。它的主要上限仍是生成暴露；把 ledger 做得更复杂不会自动生成缺失对象。

### 7.4 共享 counterfactual verifier

上一轮反事实原型只在 dependency/interaction dispute 上调用：冻结候选对、exact-offset 单命题编辑、保留 signed direction、INV/DIR sham 与 fail-closed validity。反事实生成文本永不写入事实 ledger；只写一条“该候选比较边是否对既有证据按预期响应”的审计结果。

---

## 8. 为什么这不是旧 selector 范式的简单加宽

旧 APHHM-C 报告已发现 flat pool 的 coverage–conversion tension。MAS 文献和新日志把它进一步深化为：

\[
P(\text{complete Top1}) =
P(\text{complete object exposed})
\times
P(\text{correctly projected and selected}\mid\text{exposed}).
\]

VE-MAS 不把三池 union 全部一次性塞进 selector。它保留宽 residual ledger，但主比较只纳入 evidence-qualified、object-compatible candidates；额外计算作用于 disputed edge。这样同时避免：

- 33/51 correct-minority 病例的规范化正确标签仅由正确原子的独特 exposure 提供，必须进入 residual union；
- 18/51 的同标签已在至少一个错误原子池内，存在 shared-candidate rank/evidence 修复机会；
- majority 对 27/51 同错簇的放大；
- 全局 width 增长造成的候选干扰；
- summary 把独特证据压平；
- verifier 自由产生新候选后污染候选合同。

因此它是 **wide residual state + narrow validated comparison graph**，不是“池更宽 + selector 更强”。

---

## 9. 必须预注册的验收与因果审计

本轮没有运行新 LLM，以下是下一轮实验设计，不是已获得结果。

### 9.1 同预算对照

至少比较：

1. 最佳单原子；
2. 三原子独立 + 确定性无 verifier 融合；
3. 独立原子 + majority；
4. 独立原子 + 自由 reveal/debate；
5. 独立原子 + 随机等量额外调用；
6. 固定所有 verifier；
7. VE-MAS edge-routed verifier。

必须同病例、同 frozen candidate contract、同调用/token budget，并以 `clinical-complete` 为主端点；DA/MCR 分层。

### 9.2 对 collaboration 本身做干预

对同一 disputed case 随机化：

- preserve vs drop correct-minority edge；
- reveal peer answer vs reveal only typed evidence；
- 原始 claims 可访问 vs 只给 summary；
- verified patch vs 同长度 sham patch；
- true disagreement gate vs 随机 gate；
- mirrored order AB/BA。

只有这些干预能识别 collaboration mediator，不能再从最终 accuracy 反推“讨论有效”。

### 9.3 主要指标

| 指标 | 定义/目的 |
|---|---|
| Clinical-complete Δ | 主效果，case-paired、root-adjudicated |
| Exposure / conversion | 分开定位生成与排序，不使用可变分母制造斜率 |
| Correct-Minority Survival | 正确独特 edge 从原子 packet 到最终 ledger 的保留率 |
| Harmful Persuasion Rate | 原本正确原子在 reveal 后被错误共识改写的比例 |
| Marginal Information Gain per Call | 每次额外调用产生且最终通过验证的新 edge 数及其决策贡献 |
| Redundant-Call Rate | 没有新候选、edge、验证或排名变化的调用比例 |
| Causal Evidence Retention | 随机 preserve/drop 一条正确 edge 后决策改善概率差 |
| Edge Correction / Corruption | verifier 修正与新造错误 edge 的成对计数 |
| Scope retention | 完整对象是否被压成 parent/component/manifestation |
| Order robustness | AB/BA 与候选排列变化下的 pair verdict 一致性 |
| Cost | calls、tokens、latency；失败/重试单列 |

### 9.4 停止门

任一项成立则不进入 800 例确认：

- safe identity 有 substring/fuzzy merge；
- 原子 packet 在 peer reveal 后被覆盖；
- verifier 无 verbatim span 或对象/时间/极性校验；
- requested-object contract 不能证明只来自 task prompt/schema，或 fact/candidate 缺全局 identity；
- failed/partial atom 被当作合法空候选，或 rejected/unknown verifier patch 没有留在 audit ledger；
- preprojection admission set 有候选缺 validated/consumable object projection，或 final comparison 期间 active-set hash 发生变化；
- 任一 active-candidate 无序对没有 mirrored validated comparator，却仍输出唯一 top-1；
- external retrieval 被写成病例已观察事实，找不到时未返回 `unavailable`，rule event 未形成可校验 hash chain，或 proposal 引用不存在/hash 不匹配/latest 非 validated 的 rule；
- correct-minority survival 低于独立无交互基线；
- edge corruption 不低于 correction；
- 相对随机等调用没有额外 information gain；
- 收益只出现在 legacy-chain/task mapper，不出现在 clinical-complete；
- 端点覆盖合同不完整或根审范围不足。

---

## 10. 当前可以落地、尚不能宣称与最终路线

### 可以直接落地的离线/工程改造

1. 冻结 RFC-8785 input、全局 fact manifest 和仅由 task prompt/schema 推导的 requested-object contract；
2. 定义 success/partial/failed atom packet、逐 phase call/retry ledger、全局 candidate registry 与 local→global mapping；
3. 删除 MOSAIC substring identity，将 view/vote 彻底降级为 provenance；
4. 为 Collapse3c 增加 `against_fact_ids` 与 subject/time/scope binding；
5. 实现按 dispute type 区分的 append-only tagged patch，rejected/unknown 也归档；
6. 构建 deterministic verifier router，冻结 preprojection/active-set hash，并对全部 active-candidate 无序对强制 mirrored comparator 与 coverage gate；
7. 把既有 counterfactual audit 只作为 dependency edge 的一个 verifier；
8. 分隔 vignette observation 与 external knowledge rule，实现 rule-event append/validation/hash 状态机，v1 关闭全部跨病例 memory；
9. 在旧日志上先跑 coverage、minority survival、edge schema 与 routing dry-run，不需要新模型调用。

### 当前不能宣称

- 三原子 MAS 会达到 155/800；
- Collapse3c/Forest/IMPC 具有稳定专科分工；
- 多数或一致性可识别正确原子；
- mixed-vendor conversation 比独立异质 ensemble 更优；
- complexity router 已被验证；
- tree、MCTS、memory 或 counterfactual 名称本身导致临床提升；
- 更多 agent 能突破 correct-object exposure ceiling；
- 当前日志足以估计 VE-MAS 的 clinical-complete 增益。

### 最终建议

若只保留三个近期工作项，优先级为：

1. **Typed Claim Graph + Targeted Verifier**：先让原子输出可验证、可对齐、不可覆盖的边；
2. **Edge-conditioned Adaptive Compute**：用 observable dispute 而非 case complexity 分配计算；
3. **Interventional MAS Audit**：随机化少数意见、reveal、summary 与 verifier patch，真正识别协作机制。

Forest、IMPC、Collapse3c 的价值不在于模拟三个医生，而在于分别提供多轴候选几何、独立取向的 residual proposal、以及带对象/极性/时间结构的证据 ledger。只有把这三类输出变成 immutable atoms，并在 edge 层验证后融合，MAS 才可能利用互补证据而不重演多数压制、summary 丢失、候选干扰和共享盲点。
