# Counterfactual inference：机制、公开实现与 Forest/IMPC/Collapse3c 迁移审计

> 研究日期：2026-08-20
> 主项目基线：`cursor4@726e7611780be9419d70fcfdfbacbfc471aab74c`
> 范围来源：用户提供的 `counterfactual.md`，再以论文原文、作者官方仓库和提交历史独立核验
> 新 LLM/API 调用：**0**
> 外部代码：只克隆、只读审计；未把第三方仓库写入主项目

> **2026-08-22 更新：§12 的 P0/P1 已零调用执行完毕，结论与本文的优先级不一致。**
> 见 [`CF_SUBSTRATE_REPLAY/REPORT.md`](results/CF_SUBSTRATE_REPLAY/REPORT.md)。三点分歧：
> ① P0 的五处并非并列——**只有 safe identity 有可测收益**（Forest 净 +16、IMPC 净 +11 个
> addressable-complete），proposition dedup 净 0，移除 view 加分在 IMPC 净 −2；
> ② 这条修复 **Collapse3c 早已实现**：三臂用同一个 containment 谓词，Forest/IMPC 静默折叠
> 561/452 次，Collapse3c 保留为 `narrower_than`/`broader_than` 141 次——这给 §7.2 的
> "Collapse3c 是 specificity-retention 参考" 第一次配上机制和数字；
> ③ **§8/§11 的 `CF_EDGE_AUDIT_V1` 规模比预期小一个量级**：edge 可审计性轻松通过（86.1% 的病例
> 有候选独有高特异判别子），但真实 conversion gap 仅 50/800、带判别子者 15/800，
> top-pair 版本上界 22/800，且 harm 暴露面（109 例 champion 本已正确）是可寻址集的 5 倍。
> 故 §12 的执行顺序应改为：**先做 P0 第 1 处 + 修自相矛盾边，不按现设计预注册 P2。**
>
> **2026-08-22 二次更新：上述两项已落到生产代码并通过零调用验收。**
> `mosaic.py` 的 `_match` 去掉 containment、改由 `_relation()` 产出 typed relation，
> 并加一条有界的父子退坑准入规则（迭代到不动点，上限 2）；`aphhm_c.py` 新增
> `bind_and_quarantine_directions()`，补上 `contradict_fact_ids`（即 §9.3 要的 `against_fact_ids`）
> 并撤回自相矛盾边。补上准入规则后 **harm 在两臂均归零**，Forest 净 +16→**+17**、
> IMPC 净 +11→**+13**（IMPC 的 176 已等于 pool 上限，其剩余损失全部在 selector 侧）。
> 该收益**不依赖分析层的冻结同义桥**，生产 `resolver=None` 下即为此数。
> 44 条自相矛盾边按绑定层拆为 28 条 exact + 16 条 containment-only；生产只自动撤回前 28 条，
> 后 16 条留 review queue——因为 §6.2 已证 containment 正是混淆对象的那一层，
> 不能为了凑数把它装回 evidence 方向上。
> **但两项修复的记账必须分开**：边隔离的端点上界只有 23/800 例 selector payload 变动
> （1 例 rescue 暴露、至多 1 例可能有害、21 例惰性），因为 `score_concept` 不读
> `support_fact_ids`/`contradict_spans`，其确定性效应恒为 0——它是自洽性修复，不是涨分修复。
> 另一个反转：修复后 Forest 173 / IMPC 176 **已超过** Collapse3c 的 168 addressability，
> 但 Collapse3c 仍以 conversion（.726 vs .686/.601）在真端点领先（122 vs 107/98），
> 所以瓶颈已从 recall 移到 conversion。
> 四层依赖次序（identity → 方向自洽 → evidence schema → edge 干预）见报告 §7.0。
>
> **§11.2 的 exact citation closure ≥98% 现在就不过**：against 一侧 2,820 条 span 只有 85.0%
> 能在 exact 层闭合，约 15% 在 §8.1 的数据对象定义下无法构成 intervention card。这是 P2 的
> 硬前置。反之，先前被列为前置成本的「未挂载 fact」经按特异性拆分已撤回：高特异 fact
> 已 99.1% 挂载（未绑定主体是低特异，82.3%），§8.3 step 2 在 Collapse3c 上无需补挂载。
>
> **2026-08-23 三次更新：(B) direction validator 与 §9.3 第 3、5 项已实现，结论是 P2 应停。**
> 见 [`CF_SUBSTRATE_REPLAY/REPORT.md` §「方向校验与 pair-edge audit」](results/CF_SUBSTRATE_REPLAY/REPORT.md)。
> ① **开关形态纠正**：三项都改行为，故一律做成 `AphhmCPipeline` 默认 `False` 的 kwarg，
> 经 CLI 传入并记入 `manifest.json`，与 `strict_identity`/`enforce_group_quota` 同一形态。
> 上一轮把边隔离做成常开是违反该约定的（改行为却不进 manifest），本轮已改为
> `quarantine_direction_conflicts`；绑定与校验保持常开，因为它们不改任何 selector 可见字段。
> ② **闭合率门两侧都不过，且比先前报的更差**：把 support 一侧一并计入后，DA/MCR 的
> combined closure 均为 **92.4%**（against 83.9%/85.9%，support 95.2%/95.1%），
> 逐例只有 62.8%/63.0% 的病例自身达标。§11.2 的 ≥98% 不是差一点，是差 5.6pp。
> ③ **决定性的负面结果：pair-edge audit 够不到 conversion gap，且它瞄错了边。**
> 在 45 例 gap（DA 6 / MCR 39）上，正确完整对象落在 top-2 边内只有 50.0%/48.7%——
> 即 §8.3 step 5 的 top-2 触发器有一半时间根本不含要救的那个候选。更关键的是在
> **真正决定胜负的那条边**（champion vs 完整对象）上，独占高特异判别子落在
> **错误冠军一侧的比例是正确一侧的 2.6–3.4 倍**（DA 33.3% vs 16.7%，MCR 43.6% vs 12.8%）。
> ④ **该不对称已用厚度混淆检验定性**：MCR gap 上完整对象平均只有 **0.97** 个高特异支持
> fact，错误冠军有 **1.95** 个，正好两倍（总支持 fact 1.79 vs 2.85）。所以 gap 不是
> 「selector 读不到判别证据」，而是**生成器给正确答案挂的高特异证据只有胜者的一半**。
> typed cards 与 edge audit 只会忠实地把「错误候选证据更具体」这件事讲得更清楚。
> 结论：§8/§11 的 `CF_EDGE_AUDIT_V1` 不应预注册；下一步的唯一有效目标是
> **evidence attachment（让正确对象拿到它应得的高特异证据）**，而非 edge 干预。
> 副产物：collapsed 臂 `score` 恒为 0.0（矩阵关闭，`score_concept` 无 admitted cell），
> 故 `tied_score` 恒真、无信息量，已从 disputed_reason 降级为 `scores_tied` 字段。
>
> **2026-08-23 四次更新：evidence attachment 也不接替 P2；真正的杠杆是呈现顺序。**
> 见 [`EVIDENCE_ATTACHMENT_AND_ORDER_COUNTERFACTUAL_PLAN.md`](EVIDENCE_ATTACHMENT_AND_ORDER_COUNTERFACTUAL_PLAN.md)。
> ① **先更正上一条的数**：`c4_selector_candev_nomatrix` 属 `selector_all_concepts`，
> `shortlist = ranked`——selector 看到整个池，frontier 只是 lane 标记。上一轮用 4 宽 frontier
> 当 selector 输入，故 conversion gap 应为 **55/800**（DA 9 / MCR 46）而非 45/800；
> 但仅 5 例的完整对象落在 frontier 之外，量级未变。
> ② **挂载路线三种形态全部零调用测死**：补孤儿证据（gap 例平均仅 0.04–0.11 条孤儿高特异 fact）；
> 复活 protected lane（正确对象持有池内独有高特异 fact 仅 19.6%，冠军 39.1%，优先保护的是已赢者）；
> EA-RAG 式生成侧覆盖审计（623 例池内无完整对象中，仅 2.6–4.2% 存在未被解释的高特异发现）。
> 第三条最关键：**EA-RAG 的前提「retrieval 未覆盖 discriminator」在本系统不成立**，
> 池子已解释约 97% 的高特异发现，只是用错误诊断解释——与「高特异 fact 已 99.1% 挂载」互为印证。
> 故失败模式不是证据缺失、也不是覆盖缺失，而是**错误候选把同样证据解释得一样好**。
> ③ **「规模过小」的根不在 selector**：**623/800（77.9%）的病例正确答案根本不在池内**，
> 55/800 有而选丢，其中可干预者仅 21/800。任何 selector/边/挂载侧机制的端点天花板都锁在此。
> ④ **本轮最大发现：selector 有 71.0% 选中池内 index 0，均匀期望 19.2%，集中度 3.69×**
> （DA .688 / MCR .733，n=800）；gap 例中冠军平均位置 0.50、正确对象 1.98。
> 反讽在于 `selector_unanchored` 本是为撤掉分数锚而设，其实现按 `concept_id` 排序，
> 而 concept_id 序就是生成序——撤掉一个锚，装上了另一个更强的锚。
> ⑤ 故下一步主推 `ORDER_COUNTERFACTUAL_V1`：只扰动呈现顺序这一个变量（DeVisE 式受控扰动），
> 预注册 CSS 式方向分与三层（122 controls / 55 gap / 623 inert），成本 400–800 调用。
> 它同时绕开两个障碍——power 来自 800 对配对而非 55 次稀有翻转，
> 且它能判定「错误候选证据更多」究竟是顺序artifact还是真实先验。**两个方向都改变后续判断。**
> 注意：位置集中度是相关量，H1（顺序artifact）与 H2（真实先验）本轮**未分离**。

> **2026-08-23 五次更新（第 ④⑤ 条已结案，顺序路线关闭，未花调用）：**
> 见 [`results/ORDER_COUNTERFACTUAL/REPORT.md`](results/ORDER_COUNTERFACTUAL/REPORT.md)。
> ① 上一条 ⑤ 说的实验**其实早已跑过**：R6 的 X4 探针在同一 Collapse3c 池上以 3 个种子置换过
> 呈现顺序，逐例输出留存于 `logs/backbone_v1/*/r6_x4_c3c_s{0,1,2}`；当年只按准确率
> spread 分析并写下「顺序不敏感」。第 ④ 条断言「H1/H2 未分离」是因为**漏查了归档**。
> ② 换成正确统计量重算（`cf_order_stability.py`，**0 调用**）：冠军身份稳定性 .852（DA）/
> .885（MCR），θ = **.148 / .115**，三种子族内极差 ≤ .055。
> ③ **决定性读数：置换后 index-0 率从 .660/.700 塌到 .190/.243 ≈ 均匀期望 .192。**
> 若 selector 锚定位置，它按定义仍挑第 0 位，该率应维持 .70。**判决 H2**——
> 生成序**预测**冠军但不**驱动**冠军，71.0% 的集中度由共同成因（临床显著性）解释。
> ④ R6 当年的方法论缺口是真的（准确率在 623 例池内无答案上按构造看不见churn：
> DA 89 次改变里 82 次错→错），但缺口里没有效应。残余 12–15% 顺序敏感度**净有害**
> （救回 11、打翻 20），即现状生成序优于随机序，又一次独立确认 H2。
> ⑤ **后果：证据厚度差应照字面理解**——证据确实偏向错误候选。selector 侧三条路线
> （P2 edge 干预、evidence attachment、呈现顺序）**全部关闭**；剩余杠杆在生成/知识侧
> 的 623 例，不在选择侧。
> ⑥ `selector_order` 开关与 7 项测试保留，作为在 X4 未覆盖的 200b 切片上复核的仪器。

> **2026-08-23 六次更新（生成侧亦封闭；瓶颈定位到生成器模型，未花调用）：**
> 见 [`GENERATION_SIDE_HEADROOM_AND_MODEL_CEILING.md`](GENERATION_SIDE_HEADROOM_AND_MODEL_CEILING.md)。
> ① **先修口径**：`reference_identifiability` 显示只有 **455/800（56.9%）**的病例其参考答案
> 被病历文本唯一确定；345 例（43.1%）的完整特异性**不是文本的函数**，端点一直把它们计入分母。
> 分层后 Collapse3c 池可达 DA .0600→**.0772**、MCR .3825→**.6294**。
> ② **43 个真实配置的并集是上界，而它很低**：公平层 DA .1789 / MCR .7471；
> **DA 有 234/285（82.1%）从未被任何配置命名过**。E5 那组 9 个臂池可达全为 1.0000（oracle 构造），
> 已整组剔除，否则并集是循环论证。
> ③ **失败形态是特异性不足而非方向错误**：并集 C∪P 可达 .9825/.9175，几乎每例池内都有正确科属；
> 未命中例中 DA 80.6% 池内已有父类/成分。但 DA 的参考答案是**后组配合成式**
> （「levator scapulae 的 F. necrophorum 化脓性肌炎」「Stage IIA melanoma with…」），
> **本体没有这些类**，故「查知识库枚举子代」不成立；而输出侧组配已由
> `DA_FINALS_AXIS_COMPLETION` 测死（Δ=+2、Holm 1.0、幻觉 .1583 破 .10 硬门）。
> ④ **本轮新杀一条：多臂并池**。换池先前测过（净 −13），并池未测过，故离线测算：
> 公平层贪心加入，第 2 臂 +13（DA）/+7（MCR），**第 3 臂 +1、第 4 臂 +0——两步饱和**。
> **不得把池可达增益折算成端点增益**：`CONTRACT_FIX_VERIFY` 里同量级的池 recall 增益
> （DA +3pp / MCR +4.5pp）实测**转化为零**；而加宽的代价方向已被两次实测
> （`E5` width8 safe-exact **−16.46pp**、MCR width4→8 **−24.0pp**；`E12` k5→k10
> clinical-complete **−1.67pp**，与「k10 池可达 +2pp」同时成立）。判不值得预注册。
> ⑤' **仓库里唯一未被否证的生成侧正信号是「多视图横向提案」，本轮把它定位而非否证**：
> `SLOT_YIELD` A1−A0 在 DA 官方 Acc@4 上 +6.00pp（q=.0184），但
> **clinical-complete 仅 +1.75pp、q=.063 未过门**（需更正一处流传说法：A1 的 clinical-complete
> 是**被测出来**的，只有依赖失败 M2 门的 `B1−A3` 才是扣留）；它显著买到的是
> **C∪P +6.50pp**，即科属级覆盖——而并集口径下 C∪P 已达 **.9825/.9175 近饱和**。
> **A1 加的正是已经不缺的那一层**，与该报告自己的判词「横向槽位买到覆盖却几乎买不到完整对象」一致。
> 另：外部知识注入亦已否证（`E11` TF-IDF RAG clinical-complete **−2.00pp**，仅 6.62% chunk 与病例相符）。
> ⑤ **饱和本身是最有信息量的读数**：`manifest.json` 里 **243/243** 全是
> `meta-llama/llama-3.3-70b-instruct`——43 个「不同方法」是同一个 70B 模型的变体，
> 不是 43 个独立样本。九个机制族的一致零结果在此事实下是可预期的。
> ⑥ 故提议 `MODEL_CEILING_PROBE_V1`：570 次调用、**零面板**、用同义桥做**下界**判定，
> 附「同模型 + 宽松契约」对照臂以分离模型与证据契约两个因素。两个方向都改变后续判断。
> ⑦ **一条纪律**：本轮测到的「特异化靶集」（DA 215 例）由面板关系定义，
> 按 `DA_FINALS_AXIS_COMPLETION` §10 明文禁止（需端点信息选例 → 不可部署），
> **只能作分析分层，不得作干预选例依据**。

## 0. 结论先行

本轮最重要的结论不是“应给现有 selector 再加一个 counterfactual 分数”，而是：

> **应把反事实利用改造成 validity-gated、fixed-candidate、signed-direction、low-order interaction、typed-gap retrieval 的小型 disputed-edge audit。**

它只作用于已经暴露、identity 已安全、对象粒度可寻址的候选边；反事实文本不得成为新事实源，不得直接删除候选，也不得覆盖原病例证据。

这套方法最可能改善的是：

1. 已暴露候选间的 **conversion**；
2. support/against 的 **方向合法性**；
3. parent、component、sibling 与完整诊断对象之间的 **specificity retention**；
4. comparator 对决定性证据、反证和证据组合的真实响应。

它**不能单独解决 exposure/recall ceiling**。如果正确完整对象在生成、identity merge 或 frontier admission 阶段已经消失，就没有候选边可审计。现有病例 `DA 709`、`MCR 173`、`MCR 438` 已直接证明这一点。

最可信、可以迁移的机制不是某一篇论文的整套系统，而是下列组合：

| 层 | 可迁移机制 | 主要来源 | 在本项目中的作用 |
|---|---|---|---|
| 1 | exact-offset、单命题、fail-closed intervention validity | DeVisE、Contrast Sets、MedCounterFact | 防 no-op、多编辑、对象/时间/否定漂移和不可信证据 |
| 2 | 冻结候选集上的 signed A:B margin | Evidence Audit、CSS；CF-MAR 的反例 | 同一诊断/候选边前后比较，禁止自由 top-1 换标签 |
| 3 | 预注册 expected direction 与 INV/DIR sham | CSS、CheckList、DeVisE | 区分“有变化”与“沿临床正确方向变化” |
| 4 | diagnosis-relative role 与低阶 interaction | Evidence Audit、SHAP/STI、Archipelago | 定位 support、competitor support、cancellation、synergy |
| 5 | 只针对 disputed edge 的 typed gap retrieval | MamaBench/EA-RAG、BioRAB | 补 A/B 判别缺口；保留 provenance、冲突隔离和无证据回退 |
| 6 | 只将验证后的 edge 交给一次冻结 comparator | 当前 E4/E5/E9/E10 综合 | 避免全局图、固定填宽、重复投票和不可逆状态写入 |

明确不应复制：CF-MAR 当前公开实现的 CPG；ECR-Agent 的未验证全局“因果图”和 hard shadow penalty；MEDEXA 的生成式 what-if prose/self-reported confidence；CSS 作为 live rank score；Evidence Audit 的全子集在线枚举；BioRAB 的模型覆写标签；当前 C4 ontology edge 作为真值。

---

## 1. 研究边界、证据等级与远端最新状态

### 1.1 版本边界

本轮先 fast-forward 同步 `origin/cursor4`，随后在唯一基线
`726e7611780be9419d70fcfdfbacbfc471aab74c` 上取证。该提交已经包含 recall–conversion ceiling closure 的最新状态，不能与上一轮 `6ed5ccc...` 混用。

新 closure 对本调研有三项直接约束：

- C1 qualified admission、C2 factorization、C3 active evidence 都是 **operational no-go / scientific not evaluated**；没有合法调用或完整标注，不能写成机制被科学否定。
- C4 deterministic relation substrate 是真实 **scientific no-go**：122 条 SNOMED edge 中，mapping、direction、citation、agreement 均未达到预注册门槛；不能把 ontology edge 当方向真值。
- C0 的 19,599 个 relation census 因 reviewer 完成度和可靠性门未通过，只能作 coverage/reliability audit，不能释放新的 clinical width slope。

对应原始报告：

- [C0 pool census](results/CEILING_POOL_CENSUS/REPORT.md)
- [C1 admission](results/CEILING_CLOSURE/C1_admission/REPORT.md)
- [C2 factorization](results/CEILING_CLOSURE/C2_factorization/REPORT.md)
- [C3 active evidence](results/CEILING_CLOSURE/C3_active_evidence/REPORT.md)
- [C4 relation substrate](results/CEILING_CLOSURE/C4_relation_substrate/REPORT.md)

### 1.2 本报告怎样判断“真正机制”

每篇工作分开回答四个问题：

1. **改变了什么？** 候选、证据表示、调用数、检索、教师监督、prompt、模型还是评估器？
2. **与什么基线比较？** 是否同病例、同候选、同预算、同模型、同端点？
3. **哪一部分有独立消融？** 若整包同时改变，只能归因于 bundle，不能归因于名称最吸引人的组件。
4. **公开代码实际计算什么？** 变量名、论文叙述和实现可能不同；没有日志时不得假定论文使用的就是当前提交。

本报告使用下列证据等级：

| 等级 | 含义 |
|---|---|
| A | 同病例受控干预或清晰消融，且端点与机制相符 |
| B | 论文方法与官方代码可交叉核验，但缺完整运行日志或因果隔离 |
| C | 只有论文/数据或 bundle-level 结果，内部机制未识别 |
| D | 主项目既有冻结实验、根审计或 committed logs 的直接证据 |

外部论文的“未发现官方仓库”只表示：论文未给链接、截至 2026-08-20 的题名/作者检索未发现作者官方仓库；不是永久不存在的断言。

完整机器账本见 [paper_code_ledger.json](results/COUNTERFACTUAL_INFERENCE_RESEARCH/paper_code_ledger.json)；每个官方仓库的 exact commit、复查 recipe、关键文件/函数和日志探测结果另见 [audited_source_manifest.json](results/COUNTERFACTUAL_INFERENCE_RESEARCH/audited_source_manifest.json)。

---

## 2. 这不是单一分支，而是四种不同技术对象

附件提出的“三支汇流”判断是正确的，但实现迁移时还应再拆出 training/data：

| 技术对象 | 工作 | 它测量/改变什么 | 是否能直接提高当前推理 |
|---|---|---|---|
| Behavioral benchmark | DeVisE、CSS、CheckList、Contrast Sets、Pearl-ladder study | 输入变化后行为是否保持/翻转/沿正确方向更新 | 否；它们提供测试合同 |
| Inference bundle | ECR-Agent、CF-MAR | 结构化证据、编辑、检索、多代理、教师记忆、讨论 | 可能，但 bundle 内机制多未隔离 |
| Evidence attribution | Evidence Audit、SHAP/STI、Archipelago、IDG | 冻结模型对证据子集/交互的行为响应 | 可作离线 audit，不应直接等同临床因果 |
| Retrieval robustness/gap fill | EA-RAG、BioRAB | 检索是否覆盖 discriminator、是否被错标签/错来源污染 | 只能在 typed gap 下选择性使用 |
| Training/data | Counterfactually Augmented Data | 通过标签翻转最小编辑改变训练后的 feature reliance | 本轮 training-free 范围不能复制 |
| Post-hoc explanation | MEDEXA | 生成 what-if 解释、置信度和患者友好答案 | 不验证推理，不可进入 rank evidence |

因此不能把 `MedEinst → ECR → CF-MAR → Evidence Audit` 当严格算法继承链。更准确的谱系是：behavioral tests、counterfactual inference、feature-interaction attribution 与 retrieval robustness 在 2026 年临床 LLM 研究中汇流。

---

## 3. 核心论文与官方实现解剖

### 3.1 MedEinst / ECR-Agent：有 bundle 增益，但“因果图机制”未被识别

一手来源：[ACL 2026](https://aclanthology.org/2026.acl-long.1847/)、[arXiv](https://arxiv.org/abs/2601.06636)、[官方仓库 `zhui711/MedEinst@984ccda`](https://github.com/zhui711/MedEinst/tree/984ccdaaf55d1877d4082242dee07255cc3b5504)。

MedEinst 构造 5,383 个 control–trap 配对、49 种疾病。control 正确后，trap 将判别证据改变到另一诊断；BTR 衡量模型是否仍固着在 control 诊断。

ECR-Agent 的两个 bundle：

1. **DCI**：直觉 top-k 与 Present/Absent/Missing 证据并行；借 PubMed/OpenTargets 构建疾病关系图；用 match/conflict/rule-out/support 和 expected-but-unobserved shadow evidence 排序。
2. **CGME**：GPT-5 critic 在有真值的训练病例上最多纠错三轮；只有正确轨迹进入 illness graph 和 exemplar memory。

论文给 Qwen3-32B 的消融：

| 系统 | Base | Robust | BTR |
|---|---:|---:|---:|
| base | 40.25 | 11.86 | 43.46 |
| + DCI | 55.49 | 19.94 | 38.32 |
| + DCI + CGME | 69.49 | 24.21 | 33.75 |

可以成立的是：显式正负证据核对的整包和 gold/critic memory 整包都提供增量。不能成立的是“causal graph 本身导致提升”，原因有三：

- DCI 同时改变结构、检索、调用数、图、缺失证据惩罚和 prompt；
- CGME 是带真值、强教师、只存正确轨迹的监督蒸馏，不是 training-free inference；
- 官方仓库明确写 ECR-Agent code `Coming Soon`，没有 query、权重、图合并、shadow observability、memory 去重或日志可核验。

**可迁移：** Present/Absent/Missing、候选特异冲突、expected-evidence obligation。
**条件：** `missing` 必须再拆为 not measured / not documented / measured absent；shadow 只能软提示，不能 veto。
**禁用：** 自由生成全局图、hard shadow penalty、把 teacher/gold memory 说成无监督因果推理。

### 3.2 CF-MAR：公开代码推翻了 CPG 的核心解释

一手来源：[arXiv](https://arxiv.org/abs/2603.27820)、[官方仓库 `FAIRHealth/clinical-counterfactual-reasoning@265d1ae`](https://github.com/FAIRHealth/clinical-counterfactual-reasoning/tree/265d1aea88f705063bb7ff2d686547d373da7e09)。

论文 pipeline 为：专科 triage → 初始 top-3 → negate/remove/replace/weaken/intensify/insert 编辑 → SIP 过滤 → CPG/label shift 排序 → 多轮专科讨论 → 共识/最终 judge。

30 例消融中移除 `CF case editing` pathway，准确率由 43.3% 降至 23.3%。因为其余 specialist reports、multi-round discussion、role playing 与 independent clinician scaffold 保留，该对比只支持“CF-editing pathway 在其余 scaffold 上有增量”；它仍不能在编辑生成、SIP、重跑、CPG/label-shift 排序之间隔离真正 mediator，更不能把 specialist 多样性或讨论的收益记到这个消融名下。

公开实现有六个决定性问题：

1. `evaluate_counterfactual_candidate()` 计算 `abs(baseline_label_prob - cf_prob)`，但两侧连同一评分任务都没有冻结。baseline 侧的 candidate-match prompt 允许“不匹配时输出正确诊断”，实现随后给**实际生成的诊断序列**计 token probability，却不验证该序列仍是 A；编辑侧则在另一套自由 top-1 prompt 下给实际生成序列计分。因此它比较的是两个 prompt/病例下可能不同的生成序列分数，既不保证是 $P(A\mid x)$，更不是固定 A 的反事实效应。
2. `allowed_labels` 未使用；candidate set 没冻结。
3. confidence 将自由诊断文本的 token logprob 求和再取 `exp`，受标签长度影响；无 logprob 时退化为模型自报概率。
4. SIP 无候选通过时执行 `realism_kept if realism_kept else normalized`，即 **fail-open**。
5. 无候选 fallback 统一删除 `fever`，可能与病例/被检验诊断无关或形成 no-op。
6. 最终分数把 label shift 本身赋予高权重，语义漂移也会被奖励。

因此“CPG 定位了 causal evidence”不成立于当前公开实现。当前消融最多支持：在其余多代理 scaffold 不变时，加入整条 CF-editing pathway 有小样本增量；无法再区分是编辑本身、病例重跑、轨迹筛选、label shift 还是讨论注意力重定向造成。

正确的迁移定义应固定候选集合 $C$ 和候选 $d$：

\[
m_d(x;C)=s(d\mid x,C)-\max_{c\in C,c\ne d}s(c\mid x,C)
\]

\[
\Delta_e(d)=m_d(x^{(e)};C)-m_d(x;C)
\]

必须保留符号、candidate-set hash、输入顺序 hash；不得取绝对值。若 API 不给 option logprob，只能报告冻结 pairwise comparator 的 ordinal preference/flip consistency，不能用自报概率伪装 margin。

### 3.3 Evidence Audit：目前最干净的 fixed-hypothesis 证据利用审计

一手来源：[arXiv 2607.20848](https://arxiv.org/abs/2607.20848)。论文未给代码链接，未发现作者官方仓库。

它冻结病例证据单元 $E$ 和候选 $C$，对每个证据子集 $T$ 取得同一 multiple-choice prompt 的 option score：

\[
v_d(T)=s_T(d)-\max_{c\ne d}s_T(c)
\]

并用 Möbius inclusion–exclusion 得到 interaction：

\[
I_d(S)=\sum_{T\subseteq S}(-1)^{|S|-|T|}v_d(T).
\]

其优点不是“用了 Shapley 名称”，而是：候选固定、竞争 margin 固定、诊断相对角色固定、符号保留，且异常 interaction 只进入 review queue，不自动改答案。

定量证据：

- 86.6%–89.6% interaction strength 可解释为合理支持、冲突或抵消；
- singleton/LOO 只覆盖约 18% 强度，二阶约 45.6%，提示单证据删除不足；
- 130 个高强度富集项中 111 valid、8 questionable、11 invalid；invalid 集中在 negated/absent/local；
- 稳定性过滤把富集队列 precision 由约 .55 提到 .80，但这不是总体病例错误率；
- 第三阶发现覆盖 11/11 invalid 具有选择偏差，不能当独立优越性证明。

它是 **prompt-conditioned behavioral attribution**，不是内部因果识别。删除证据表示“模型看不到”，不等于临床世界里证据取反；mask/neutralization 的定义决定解释。

**本项目用途：** 小 frontier 上离线 singleton + 二阶审计；检测 sibling/parent/component 间的 cancellation、negated misuse 和 order fragility。
**禁用：** 在线全子集枚举；负 interaction 自动 veto；把数值当 likelihood ratio。

### 3.4 DeVisE：最有价值的是 validity harness，不是诊断 agent

一手来源：[Findings EACL 2026](https://aclanthology.org/2026.findings-eacl.338/)、[官方仓库 `camztag/DeVisE@d5a0b99`](https://github.com/camztag/DeVisE/tree/d5a0b99e8ebb38a46270b3fe1cd22f3215787159)。

DeVisE 对 1,001 个 MIMIC-IV admission note 构造 166,731 个单变量人口学/生命体征反事实，测 PPL、mortality 与 LOS 的 signed direction/monotonicity。论文自身数字不一致：Table 3 的 Average 为 mortality 67.1%→87.9%、LOS 65.2%→81.0%，正文却写 67.1%→87.5% 和 66.5%→79.9%。无论采用哪一处，方向均支持模板提高信号可见性；但这不是完整诊断能力提升，精确效应值应以表格为主并保留正文冲突。

官方代码还暴露了 validity 为什么必须单独审计：

- SpO₂ 分类阈值与论文表格不一致；
- SBP/DBP 被同时采样到同一 severity，违反单变量定义；
- generator 未排除 `new_value == original_value`，可生成 no-op；
- post-check 脚本确实计算 exactly-one-change、section scope、duplicate/missing original，但失败项先已生成，分析路径未见统一 fail-closed 合同。

**可迁移：** deterministic exact-offset edit、original/CF 绑定、post-diff、signed response curve、monotonicity。
**必要强化：** 任何 no-op、多编辑、跨 subject/episode/time/object 的编辑都必须在执行前隔离。

### 3.5 CSS：正确方向比变化幅度重要，但 intervention oracle 也会错

一手来源：[arXiv 2605.30590](https://arxiv.org/abs/2605.30590)。论文描述 YAML catalog，但没有可访问代码或日志。

CSS 在 224 个 oncology tumor-board cases 上预注册 12 个 intervention template、五个 family 和 expected recommendation direction，以 0/.5/1 评分。

主要结果：

- 六模型 CSS 约 .309–.473；传统 CMS 与 CSS 排名重排；Spearman (-.49,p=.36)，因模型数只有 6，不能称统计确认的负相关。
- surgery-status Family D 所有模型 ≤.172。
- ReAct agent 在 100 个匹配 Family-D case 上 5/6 提高 +2.5 至 +20.3pp；但 agent 同时改变 prompt、retrieval、sectioning 和 cap，不能归因于“工具访问”单因素。
- 862 次 mutation 中 73 次 no-op 被剔除。
- 100 个医学复核中 37 个干预后不连贯；Family C/D 的 judge-human κ 仅约 .07/.16。

所以 CSS 的最强结论是 `access to evidence != correct update`；最弱环节是把某些 regex mutation 的 expected direction 当无争议真值。

本项目应使用三状态结果：`correct direction / appropriate invariant-or-abstain / wrong direction`，并先报告 apply/no-op、传播完整性和 coherence。正确拒绝不能自动记 0。

### 3.6 MamaBench / EA-RAG：最大独立增益来自 comparator scaffold

一手来源：[arXiv 2607.14385](https://arxiv.org/abs/2607.14385)、[作者数据集](https://huggingface.co/datasets/HelpMum-Personal/MamaBench)。未发现官方代码仓库或 inference logs。

MamaBench 含 217 个 base–counterfactual pair、434 个专家叙事、371 个病种。EA-RAG：typed parameter extraction → `k=5` retrieval → 将 coverage < .6 的参数列为 gap → contrastive query → .82 dedupe → cap 8 → taxonomy comparator scaffold。

关键是 additive ablation：

| GPT-4o 变体 | BTR | Robust |
|---|---:|---:|
| k5 | 39.4 | 43.3 |
| + coverage audit | 39.4 | 43.3 |
| + taxonomy scaffold | 38.0 | 46.5 |
| + contrastive gap-fill（full） | 35.9 | 49.3 |

coverage detection 单独 **零收益**；最大独立增益是显式比较 scaffold，gap-fill 在它之后再加约 +2.8pp Robust / −2.1pp BTR。Claude 的 BTR 25.8→20.3、Robust 60.8→65.0，但 Base 82.0→81.6，摘要“不降低”是近似措辞。

因此不能把增益笼统归因于 retrieval。对本项目真正有用的是：

- coverage unit 不是“病例相似度”，而是 A/B disputed edge 的 typed discriminator；
- 发现 gap 后必须实际改变证据输入或比较规则，audit 本身不会提高答案；
- retrieval 必须去重、保留 provenance，并在没有 decisive chunk 时回退原 frontier，不得填满 cap。

### 3.7 MedCounterFact：responsive evidence 之前必须先问 evidence 是否可信

一手来源：[Findings ACL 2026](https://aclanthology.org/2026.findings-acl.1847/)、[官方数据仓库 `Counterfactual-Medical-Evidence@f35b980`](https://github.com/KaijieMo-kj/Counterfactual-Medical-Evidence/tree/f35b98063b51a63e677829b6d173029d98dd3b1e)。

203 个真实 RCT 问题被系统替换为 nonce、medical mismatch、non-medical 或 toxic intervention；公开数据有 809 个实例。论文显示模型常把形式完整、重复出现的“RCT evidence”当真，即使对象荒谬或危险，仍给 confident、uncaveated answer。

这推翻了一个隐含命题：

\[
\text{随 evidence 改变} \not\Rightarrow \text{更可靠}.
\]

更准确的是：

\[
\text{可信 provenance}
+\text{命题蕴含}
+\text{临床可行}
+\text{方向正确}
\Rightarrow \text{有价值的 responsiveness}.
\]

官方仓库只有数据；README 明说代码/输出未来发布。不能从 probe 个案推断普遍内部机制。比较可信的行为解释是正式、重复上下文将陌生实体绑定到 treatment role，压过 prior/safety。

本项目需要四个彼此独立的 gate：source provenance、span→proposition entailment、clinical relation plausibility、action safety。异常证据应隔离/降权并保留在 append-only ledger，不应被无条件删除；否则会拒绝真实新药或罕见关系。

---

## 4. 邻近论文：能提供测试/安全工具，不能冒充 ranking mechanism

### 4.1 MEDEXA

来源：[论文 DOI](https://doi.org/10.1016/j.knosys.2026.116692)、[官方仓库 `imaabay/medexa@f06bea8`](https://github.com/imaabay/medexa/tree/f06bea8ddc15acf6ce1143dbd128bd0dd625da05)。

代码是 LangGraph orchestration：StatPearls/MedCPT/FAISS retrieval → document grading → query rewrite → answer → grounded/helpful judge → 自报 confidence → 生成 2–3 条 what-if prose → human feedback → final renderer。

counterfactual 句子从未真正施加到病例、重跑诊断或验证方向/最小性；CF 不回流候选排序。ablation 一次删除 confidence+CF+human feedback+renderer 整包，不能隔离 CF。仓库只有统计脚本内嵌 metric arrays，没有应生成的 raw `prediction/results.json` 或调用日志。

只可借它做 **validated replay 之后** 的 switch-condition UI；不可把生成 prose、自报概率或 LLM judge 当证据权重。

### 4.2 Pearl-ladder clinical lab study

来源：[npj Digital Medicine](https://doi.org/10.1038/s41746-026-02632-3)、[官方仓库 `LLM_Causality_LabTest@6d0fbd1`](https://github.com/balubhasuran/LLM_Causality_LabTest/tree/6d0fbd1bc42cf604258f0fde4317a542d0b9090f)。

99 场景按 association/intervention/counterfactual 各 33；发布 spreadsheet 含两模型完整响应和四位医学审阅者评分。论文 o1 vs Llama-3.2-8B 总 AUROC .80±.12 vs .73±.15，altered-outcome CF 最差，agreement .04。

但公开 `Causality.py` 只是硬编码参考范围/风险因子后填自然语言模板并调用模型；没有 SCM、DAG、do-calculus 或 abduction–action–prediction。代码实际调用 `gpt-4o`，与论文/README 的 GPT-o1 不同。

可迁移的是 causal-rung 标签和 altered-outcome paired stress test；不可把 Pearl ladder 名称当算法或 selector 插件。

### 4.3 BioRAB

来源：[Science Advances](https://doi.org/10.1126/sciadv.adr1443)、[官方仓库 `ToneLi/...@a76aebf`](https://github.com/ToneLi/ToneLi-Evaluating-Retrival-LLM-in-Biomedical-Domain/tree/a76aebff66a9612a33a21ad80d995216c08ddd24)、[Zenodo](https://zenodo.org/records/17398149)。正式版为 5 任务、11 数据集、5 LLM；附件中 9 数据集/3 LLM 是早期版本数字。

这里的 counterfactual 是把 **retrieval corpus label** 翻转 20/80/100%，不是改变患者 finding。detect-and-correct 让 GPT-4 先修标签；contrastive awareness 依赖 encoder triplet loss + instruction tuning。

当前 main 缺 triplet-loss 实现和大量结果；历史 `c8045f2` 有 MedMCQA 日志。同模型离线首答案复算应使用 Llama2：no-example 1762/4183=.4212，CF20=.3538、CF80=.3720、CF100=.3775。三个污染臂没有随污染率升高而单调恶化，反而从 20% 到 100% 回升；Llama3 no-example .5673 不能与这些 Llama2 污染臂拼成轨迹。negative-awareness 输出又大多仍是 A/B/C/D，且构造脚本把 true/fake noise 写成同一标签。

可迁移的是 retrieval provenance、corruption sham、contradiction quarantine、abstain；不能把 corpus-label repair 当患者级 causal reasoning，也不能无验证让另一模型覆盖标签。

---

## 5. 方法学根：怎样正确借用，怎样避免概念偷换

| Root | 真机制 | 官方代码/日志 | 对本项目的正确用途 |
|---|---|---|---|
| [CheckList](https://aclanthology.org/2020.acl-main.442/) | MFT / invariance / directional expectation 的 capability matrix | [`marcotcr/checklist@4e6e5e3`](https://github.com/marcotcr/checklist/tree/4e6e5e33a26f30c20ed602b2050f6c73e123cc23)，有 release predictions | 临床 MFT、无关扰动 INV、判别证据 DIR；不提高推理本身 |
| [Contrast Sets](https://aclanthology.org/2020.findings-emnlp.117/) | original 与局部最小编辑需同时正确的 family consistency | [`allenai/contrast-sets@e2b8731`](https://github.com/allenai/contrast-sets/tree/e2b87316ba7b30093bc9ffbc340e6550cab79f67)，含 outputs | 报 pair/family consistency；人工/临床有效编辑优先 |
| [CAD](https://openreview.net/forum?id=Sklgs0NFvr) | 用 coherent label-flip revision 再训练，改变 feature reliance | [`acmi-lab/...@6f232a1`](https://github.com/acmi-lab/counterfactually-augmented-data/tree/6f232a1d2a11462a30ce08fb4825b734ab30828e)，只有数据 | 未来审计/训练数据规范；本轮 training-free 不可声称复制其机制 |
| [SHAP](https://proceedings.neurips.cc/paper/2017/hash/8a20a8621978632d76c43dfd28b67767-Abstract.html) | 在指定 masker/background 下分摊冻结模型 coalition value | [`shap/shap@df974a1`](https://github.com/shap/shap/tree/df974a1966294b9c7acebb1373fd6dc5445d1d3d) | 将 value 定义为 A:B margin 的小维度离线 audit；不是 LR/临床因果 |
| [Shapley–Taylor](https://proceedings.mlr.press/v119/sundararajan20a.html) | 低阶 interaction 的公理化分配 | 未发现独立作者官方实现 | 二/三阶 screen；不能在线 (2^d) 枚举 |
| [Archipelago](https://proceedings.neurips.cc/paper/2020/hash/443dec3062d0286986e21dc0631734c9-Abstract.html) | 两个 context 的二阶黑盒有限差分，约 (O(d^2)) | [`mtsang/archipelago@8ff437e`](https://github.com/mtsang/archipelago/tree/8ff437e5672809827d7daa6a5656aeedbc0e1094) | 小 evidence set 的 synergy/cancellation screen |
| [IDG](https://aclanthology.org/2021.acl-long.71/) | embedding path gradient + linguistic group direction | [`integrated-directional-gradients@5e629ce`](https://github.com/parantapa/integrated-directional-gradients/tree/5e629ce3af58e83394227ed6ce754e6c73daf758) | 只有权重/梯度可得时可用；当前 API selector 不可执行 |

所有 attribution 方法解释的是：冻结模型在所选 baseline/masker 下如何变化。相关临床 finding 并不独立；粗暴删除一个词可能改变语法、时间、主体和病例可行域，所以 attribution value 不能被命名为“临床因果效应”。

---

## 6. 2,400 份 Forest/IMPC/Collapse3c 日志告诉我们什么

本轮只读解析每臂 800 例，共 2,400 个 `case_stages`。可重跑脚本和结果：

- [counterfactual_log_census.py](counterfactual_log_census.py)
- [backbone_log_census.json](results/COUNTERFACTUAL_INFERENCE_RESEARCH/backbone_log_census.json)
- [2,400-file input manifest](results/COUNTERFACTUAL_INFERENCE_RESEARCH/input_manifest.json)

脚本会把本地 2,400 个文件逐一与指定 source commit 的 Git blob 校验，冻结六个 dataset 目录及各目录计数，并在产物中记录 script SHA-256 和 manifest SHA-256；日志有改动、缺失或额外插入时直接失败。

### 6.1 总体 substrate

| 指标 | Forest | IMPC | Collapse3c |
|---|---:|---:|---:|
| 病例 | 800 | 800 | 800 |
| evidence/fact | 7,853 | 7,257 | 9,333 |
| 每例均值〔范围〕 | 9.816〔2–24〕 | 9.071〔2–25〕 | 11.666〔5–12〕 |
| candidate | 3,589 | 3,275 | 4,197 |
| 每例均值〔范围〕 | 4.486〔1–11〕 | 4.094〔1–8〕 | 5.246〔3–7〕 |
| frontier 均值〔范围〕 | 4.327〔1–6〕 | 4.053〔1–6〕 | 4.264〔3–6〕 |
| candidate 有 support | 99.53% | 99.48% | 93.26% |
| candidate 有 against | 16.38% | 17.22% | 61.83% |
| 每 candidate support / against | 2.590 / .217 | 2.670 / .222 | 1.836 / .672 |

Forest/IMPC 的 typed fields 是“退化齐全”：

- 15,110 条 evidence 全部 `polarity=present`；
- 全部 `epistemic_status=observed`、`modality=text`、`reliability=1.0`；
- temporality 0 条。

原因可直接追到 [`mosaic.py::_ingest_generator`](../../src/agentclinic_tree_dx/mosaic.py)：创建 `EvidenceFact` 时只传 `raw_span/source_view`；polarity、epistemic status、modality、reliability 退回 dataclass 默认值，而 temporality 根本不是该 dataclass/序列化 schema 的字段。

所以不能直接在现有字段上做“删除阴性”“改变时间”“按可靠性衰减”的 counterfactual；必须先重建 exact-offset typed proposition。

Collapse3c 的 substrate 明显更丰富：

- polarity：8,106 present、1,222 absent、5 uncertain；
- temporality：7,528 current、1,676 past、129 progressive；
- modality：history 2,737、exam 2,355、imaging 1,759、laboratory 1,556、pathology 639、treatment response 207、genetics 80；
- 8,467/8,467 `support_fact_ids` 引用合法；
- 7,330/7,705 support span 与完整 fact 归一化一致；
- against 只有 2,397/2,820（85.00%）能对齐完整 fact，而且没有 `against_fact_ids`；
- 244 个 gap candidate，分布在 222/800 例；当前 mode 800/800 均禁用全局 matrix。

“有 ID”不等于方向正确；`DA 87` 和 `MCR 314` 已出现 support/against 反标。

### 6.2 重复和 identity 风险

| 风险 | Forest | IMPC |
|---|---:|---:|
| 有 normalized duplicate 的病例 | 159/800 | 135/800 |
| 多余 duplicate 实例 | 250 | 204 |
| duplicate 跨 generator view | 158 | 132 |
| alias 数 | 499 | 366 |
| unequal containment alias | 466/499 | 342/366 |

[`GlobalConceptRegistry._match`](../../src/agentclinic_tree_dx/mosaic.py) 在 exact/resolver 后继续接受 `a in b or b in a`。这会把 parent、subtype、etiology 或 composite 静默折叠成 alias。归一化后相同的 raw span 又可用不同 evidence ID 进入 `score()`；而 `score()` 还给多 view 附加分，因此同一表面证据可被双重计权。只有通过 subject/time/scope 校验后，才能把这种 raw-span duplicate 升格称为 proposition duplicate；MCR 463 是已逐例确认的实例。

IMPC 虽注释 `agent_votes MUST NOT enter likelihood`，`generator_views` 仍间接起 vote 作用。doctor/view 应只作为 provenance，不能当独立证据。

### 6.3 六个机制哨兵病例

#### DA 87：方向反标与 partial miss 同现

Collapse3c 将“正常冠脉”放入 Myopericarditis 的 `contradict_spans`；但在 ACS vs myopericarditis 边上，它反而排除 obstructive ACS。最终 Acute Pericarditis 胜出，E2 判为 reference Myopericarditis 的 partial。

路径：[`diagnosisarena/.../87.json`](../../logs/backbone_v1/diagnosisarena/aphhm_c_collapse3c_v1/case_stages/87.json)。

适合作为 expected-direction sentinel：修正该 edge 后，Myopericarditis 相对 Acute Pericarditis 应上升；若不变，说明 comparator 没利用 edge；若下降，说明方向使用错误。

#### MCR 314：高可靠阴性被当真菌感染 support

F11 明确为 hyphae 阴性、培养无真菌，`polarity=absent/high specificity/high reliability`，却进入 invasive fungal sinusitis 的 support。内部 edge 几乎反向，不能当 CF oracle。

路径：[`medcasereasoning_200b/.../314.json`](../../logs/backbone_v1/medcasereasoning_200b/aphhm_c_collapse3c_v1/case_stages/314.json)。

#### MCR 463：同一临床命题跨 view 重复计分

Forest 中 microcephaly、prominent occiput、low-set ears、cleft lip/palate、micrognathia、elbow contractures、short lower limbs 均以大小写/标点变体重复；`exact_duplicates=0` 未发现。C001 得到 11 个 support ID 和 13.25 score。

路径：[`medcasereasoning_200b/.../463.json`](../../logs/backbone_v1/medcasereasoning_200b/mosaic_forest_v1/case_stages/463.json)。

这是 duplicate invariance sham：proposition dedup 后候选边理论上不应改变临床证据，只应消除重复权重。

#### DA 709：完整 composite 已生成，却被 substring identity 压缩

`Disseminated Tuberculosis with Hemophagocytic Lymphohistiocytosis` 被 merge 成 `Tuberculosis` alias；selector 最终只能在 HLH 与 TB component 间选择。E2 三臂均 partial。

路径：[`diagnosisarena_heldout200b/.../709.json`](../../logs/backbone_v1/diagnosisarena_heldout200b/mosaic_forest_v1/case_stages/709.json)。

这是 addressability failure，不是 recall failure；若 identity 不先修，counterfactual pair audit 无法恢复已消失的 composite ID。

#### MCR 173：Collapse3c 保存 chronic modifier

Forest/IMPC 将 `Chronic Subdural Hematoma` 折进 `Subdural Hematoma` alias，最终 parent；Collapse3c 保留两个独立 candidate，凭 imaging/time 选择 chronic，E2 判 complete。

路径：

- [Forest](../../logs/backbone_v1/medcasereasoning_v2/mosaic_forest_v1/case_stages/173.json)
- [IMPC](../../logs/backbone_v1/medcasereasoning_v2/mosaic_impc_v1/case_stages/173.json)
- [Collapse3c](../../logs/backbone_v1/medcasereasoning_v2/aphhm_c_collapse3c_v1/case_stages/173.json)

这是 specificity-retention 的正例，也是“identity validity 先于 direction”的直接证据。

#### MCR 438：完整 etiology rescue 依赖 selector 重读原文，而非绑定 edge

Collapse3c 选对 chemotherapy-induced sclerosing cholangitis；Forest/IMPC 停在 Cholangitis parent。但 Collapse candidate 的 `support_fact_ids` 没绑定 paclitaxel/bevacizumab/cisplatin exposure，selector rationale 却引用 chemotherapy。

路径：

- [Forest](../../logs/backbone_v1/medcasereasoning_200b/mosaic_forest_v1/case_stages/438.json)
- [IMPC](../../logs/backbone_v1/medcasereasoning_200b/mosaic_impc_v1/case_stages/438.json)
- [Collapse3c](../../logs/backbone_v1/medcasereasoning_200b/aphhm_c_collapse3c_v1/case_stages/438.json)

rescue 是真实的，但当前日志不能把它归因给候选 evidence edge；counterfactual audit 必须记录 selector 实际看到并使用的 proposition，而不是从流畅 rationale 反推。

---

## 7. 与既有实验的因果对账

### 7.1 反事实机制解决的不是 universal width law

[跨实验综合](CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md) 已确定：

- E5 在共同服务病例中 width4→8 clinical-complete 约 −17.68pp，局部约 −4.42pp/候选；但 sibling −11.52pp、synonym +4.85pp、component 约 0，DA/MCR 也异质。
- E4 同一 pool/width 只换 evidence integration，Forest/Pairwise 都为 69/400 complete；pairwise 相对 Forest 6 gain/6 loss，净 0。**pairwise 本身不是魔法。**
- E9 real views 相对 single 有 +3.25pp model-panel complete，但 duplicate/role rotation 可扰动 champion；新增独有信息与重复投票不是一回事。
- E10 证明额外调用即使不增加候选，也能通过 rank propagation 改变答案；所以“只有新候选才有价值”也过强。

反事实 edge audit 的作用应写成：在候选已暴露时，提高 candidate-specific discriminator 的利用和方向正确率；它不是“逃离 selector 的唯一范式”。

### 7.2 E2 告诉我们目标应是 complete，而非表面响应

E2 的 full-800 human-root 结果：

| 臂 | clinical-complete |
|---|---:|
| Collapse3c | 122/800 = 15.25% |
| Forest | 107/800 = 13.38% |
| IMPC | 98/800 = 12.25% |

overall 与 DA 没有 coherent Holm survivor；MCR 有 Collapse3c–IMPC family-local survivor，但 family interaction 未确认。Collapse3c 是 specificity-retention 参考，不是 universal winner。

Forest 相对 Collapse3c 为 22 rescue/37 loss，IMPC 25/49；IMPC 有 19 个 object rescue，也有 32 个 catastrophic substitution。新机制必须同时报告 rescue、compression 和 catastrophic substitution，不能只看平均 rank shift。

### 7.3 C4 解释为什么“先建关系图再做 CF”不可接受

C4 的 122 条严格 edge：mapping precision .877、direction fidelity .824、citation closure .303、unresolved .238、agreement .131、AC1 −.273。它不是“图暂时不够大”，而是关系 substrate 本身不可靠。

所以新方案必须：

- 只审计小 frozen frontier 的 A/B edge；
- edge 以 exact source span + typed proposition 为基础；
- unknown 保留 unknown；
- 不通过 validity 的 edge 不进入排序；
- 不复活全局 C4 matrix 或 ontology hard direction。

---

## 8. 建议算法：`CF_EDGE_AUDIT_V1`

该方案应作为新的独立 preregistration；不得事后塞回已冻结 C1–C4 并把 operational no-go 改写成支持证据。

### 8.1 数据对象

每个 intervention card 至少固化：

```text
case_id / dataset / source_commit
candidate_set_hash / candidate_order_hash
candidate_a_id / candidate_b_id / requested_object
evidence_id / exact_start / exact_end / raw_span
subject / episode / anatomy / temporality / polarity / modality
specificity / reliability / correlation_group / provenance
edit_operation / original_proposition / counterfactual_proposition
expected_direction / clinical_rationale_source
no_op / multi_edit / semantic_drift / object_drift / scope_drift
score_before / score_after / margin_before / margin_after
rank_before / rank_after / comparator_payload_hash
placebo_family / order_permutation / duplicate_sham
interaction_order / retrieval_need / retrieval_chunk_ids / citation_hash
```

### 8.2 核心量

对冻结 A/B：

\[
M_{A:B}(x)=s(A\mid x,C)-s(B\mid x,C).
\]

对一个 validated intervention $e$：

\[
\Delta_e^{A:B}=M_{A:B}(x^{(e)})-M_{A:B}(x).
\]

方向命中：

\[
D_e^{A:B}=\mathbb{1}
\left[\operatorname{sign}(\Delta_e^{A:B})=\operatorname{expected\_sign}(e,A,B)\right].
\]

若只做 evidence neutralization，必须称 `visibility intervention`；若把 present 改 absent，才是 value-changing intervention。二者不能混报。

二阶交互只在 singleton 结果冲突/抵消时计算：

\[
I_{e,f}^{A:B}=M(x^{e,f})-M(x^e)-M(x^f)+M(x).
\]

它仍是 comparator behavior，不是临床 SCM effect。

### 8.3 执行顺序

1. **Safe identity/object contract**：exact 或冻结同义；parent/component/subtype/composite 独立 ID。
2. **Typed proposition build**：exact offsets；polarity/time/subject/episode/modality/reliability；normalized proposition dedup。
3. **Validity gate**：single-edit、no-op、scope、clinical coherence、provenance、entailment、safety；fail-closed。
4. **Freeze candidates/order/payload**：CF 不能新增或删除 candidate。
5. **Pick disputed edge**：top-2 加 protected unique-evidence candidate；不做全图。
6. **Singleton replay**：同一 A/B、同一 comparator；base/intervention/neutralization/irrelevant sham/order sham。
7. **Direction screen**：只有 expected direction 超过 sham 且错误方向可解释，才进入 edge feature。
8. **Low-order interaction**：仅对 singleton 冲突、cancellation 或 known correlated group。
9. **Typed retrieval**：只有 validity 已通过但 edge 仍 unresolved，query `(A,B,discriminator,object,time)`；无 decisive citation 则不改状态。
10. **Final comparator**：读取原始证据和 validated edge card；一次冻结比较；counterfactual 只作审计特征，不覆盖事实。

### 8.4 为什么它比 CF-MAR 式完整病例重写更适合本项目

- 主项目最主要的已知失败是关系/对象转换损失；完整病例重写会同时改变更多命题，难以归因。
- 现有 E5/E9 已表明候选 membership、重复和顺序本身会改变答案；固定 candidate/hash 是必要条件。
- Collapse3c 已有短调用和 candidate-specific span 优势；小 edge sidecar 可保留这一优势，不会复活昂贵且失败的全局 matrix。
- Forest/IMPC 当前 evidence fields 退化；直接让 LLM生成 CF 只会把未经验证的字段问题再包装一次。

---

## 9. 三条分支的精确插入方案

### 9.1 Forest

代码：[`src/agentclinic_tree_dx/mosaic.py`](../../src/agentclinic_tree_dx/mosaic.py)。

#### P0：先修 substrate

- 在 `_ingest_generator()` 每个 view 写入后，做 exact-offset proposition validation/dedup。
- 替换 `_match()` 的 substring containment；safe exact/resolver synonym 之外只建 typed relation，不 merge。
- `generator_views` 只保留 provenance；从 `score()` 移除 view-count/axis-count 作为独立证据的加分，或用 unique proposition group 重新计数。
- evidence 必须接受 polarity/time/subject/modality/reliability，而非默认常量。

#### P1：再加 edge audit

- 在 `two_lane_frontier()` 冻结之后、最终 selector 之前；
- 首选 top-1/top-2 和 protected unique-evidence candidate；
- 对每个 A/B 只选 candidate-unique high-specificity proposition；
- validated edge card 与原始 candidate notes 一起给 selector；无通过卡时完全回退原 payload。

Forest 的已证优势是同池证据整合和少量独有 view capture；新机制应保护它们，同时去掉重复命题和 view-as-vote。

### 9.2 IMPC

IMPC 与 Forest 共用 `mosaic.py`，但三个 history-isolated doctor 有不同风险：doctor agreement 容易被误当独立证据，少数正确候选又可能在 union/selector 中丢失。

- doctor ID 只作为 provenance；重复 proposition 只计一次。
- disputed edge 优先覆盖：多数 candidate vs minority unique-evidence candidate。
- 预注册 duplicate doctor、role rotation、order permutation 为 sham；E9 已证明角色/重复会扰动结果。
- edge audit 不以“3/3 医生同意”为 expected direction；direction 必须来自 validated proposition/临床规则。

IMPC 的目标不是再加一个 doctor，而是检验多数共识是否真正响应 discriminator，并保护罕见但有 unique evidence 的少数候选。

### 9.3 Collapse3c

代码：[`src/agentclinic_tree_dx/aphhm_c.py`](../../src/agentclinic_tree_dx/aphhm_c.py)，mode 为 `c4_selector_candev_nomatrix`。

Collapse3c 已做对三件事：

- C1 保存 polarity/time/modality/specificity/reliability；
- candidate-specific support/against spans；
- 全局 C4 matrix 关闭，selector 读原 vignette 和 candidate notes，平均 3.2775 calls。

但最终 candev selector 只收到 `for/against` 字符串；没有结构化 polarity/time/specificity/reliability。`against` 又无 fact ID，方向可反标。

建议：

1. `_build_fact_ledger()` 后验证 fact polarity/time/scope/offset。
2. concept ingestion 后新增 `against_fact_ids`，校验 candidate↔fact direction 和 object type。
3. 在 `shortlist = ...` 冻结之后、`_select_frontier()` 之前插入小型 pair-edge audit。
4. 可以借 `_disputed_top_pair()` 的触发思想，但不能启用 `_annotate_matrix()` 全局矩阵。
5. selector payload 携带 typed fact cards，而非只传无方向元数据的 raw strings。
6. retrieval 只在 top-pair validity 通过、direction 仍 unknown 时使用；返回 edge evidence，不返回新诊断。

这一路最可能把 Collapse3c 的 specificity retention 稳定地迁给 Lite/Forest comparator，而不是把 Collapse3c 整套再叠到 Forest 上。

---

## 10. 本轮不调用 LLM 时，哪些量已经能识别

### 10.1 可以立即、离线完成

1. 2,400 stages 的 substrate/schema census，本报告已完成；它统计字段、引用、归一化 raw-span 重复和 identity-risk，不冒充临床 direction/subject/scope validity 裁决。
2. normalized raw-span dedup 后的 deterministic registry score/frontier replay；只有经 scope/time/subject 核验的具体哨兵才可进一步称 proposition dedup。
3. substring alias safe split 后的 addressability/pool membership replay。
4. Collapse3c support/against fact-ID coverage、polarity/time/scope consistency 检查。
5. 复用既有冻结 intervention：

| 实验 | condition/response | 本轮可重放的量 |
|---|---:|---|
| E4 | 400×5 = 2,000，全部成功 | 同候选池 comparator 差异 |
| E5 | 200×9 = 1,800；1,558 success | candidate 加入/删除、直接夺冠、共享候选重排 |
| E8 | 220×4 = 880；693 success | hard/soft time veto、invalid-time、legal-order |
| E9 | 400×4 = 1,600；1,599 success | single/real/duplicate/role rotation |
| E11 | 400×8 = 3,200 outcome cells | off/random/relevant/hard-negative × refine 的历史转移 |

### 10.2 现有缓存不能识别

- 每条 backbone 只有一个 observed selector payload；没有删 proposition、改 support→against、拆 alias 后的 exact twin response。
- 可以重算 pre-selector deterministic score/frontier，不能声称 final Top-1 的反事实效应。
- E2 根审 observed champion，不根审每个候选和 evidence edge；不能得到 clinical-complete pool exposure 或 edge truth。
- E5 测 candidate-set interaction，不测 evidence-subset interaction。
- E9 没有完整 subset lattice，不能凭现有日志计算新 Shapley-Taylor interaction。
- E11 是历史 retrieval bundle，不等于 `(A,B,typed discriminator)` query。
- C4 relation substrate 已 No-Go，不能补 direction label。

所以本轮严格结论是：**construction substrate 与历史冻结干预可审；新 edge audit 的 clinical-complete 因果效应尚未识别。** 任何报告若从 rationale 反推“删掉该证据会翻转”都越过了日志支持范围。

---

## 11. 下一轮预注册实验，而非本轮追加调用

建议在未来单独冻结 `CF_EDGE_AUDIT_V1`：

| Arm | 目的 | 变量 |
|---|---|---|
| B0 | frozen comparator control | 原 typed evidence、固定 C/order |
| V | validity/dedup only | 只修 identity、offset、polarity、重复；无 CF score |
| D | signed directional singleton | validated edit + expected sign |
| A | absolute-delta placebo | 复制 CF-MAR 式 |Δ|，不用方向 |
| S | shams | irrelevant edit、duplicate、order、role、no-op |
| I | low-order interaction | 仅在 singleton 冲突的预定义 subset |
| R | typed edge retrieval | 只对 unresolved validated edge 补证 |

### 11.1 冻结队列

- E4 的固定 400 例用于同池 comparator；
- E5 gold-exposed 200 例用于 conditional conversion 与 membership interference；
- 预定义 DA/MCR 分层；
- 加入本报告六个哨兵，但这些病例只作机制 sentinel，不能独立证明总体收益。

### 11.2 construction gate

- released intervention 中 no-op = 0、多编辑 = 0、对象/subject/time 漂移 = 0；
- validity ≥95%，invalid ≤5%；
- exact citation closure ≥98%；
- edge direction fidelity ≥95%；
- unknown 不强制多数。

若 gate 不过，只发布 validity audit，不运行/解释 downstream accuracy。

### 11.3 主要端点

1. ITA clinical-complete Top-1；失败/invalid call 计错。
2. complete exposure、actual payload exposure、exposed→complete conversion 分开。
3. expected-direction hit、wrong-direction、appropriate invariant/abstain。
4. rescue / compression / catastrophic substitution / no-change。
5. PP/PF/FP/FF 与 BTR/Robust accuracy，只在有效 pair family 中报告。
6. edge validity、citation、provenance、no-op/multi-edit、order/placebo sensitivity。
7. calls、latency、tokens；额外调用不能被忽略为“免费思考”。

统计使用 paired McNemar、case bootstrap、DA/MCR 分层和每实验 coherent Holm family。共同服务/共同暴露属于 post-treatment sensitivity，不能替代 ITA。

### 11.4 Go / No-Go

Go 至少要求：

- correct direction 明显高于 matched sham；
- wrong direction 不与 sham 等高；
- clinical-complete exposure 不下降；
- complete rescue > complete harm，catastrophic substitution 不超过 rescue；
- sibling/context harm 低于 B0/V；
- R arm 确实提高 decisive edge coverage，而不只是增加 chunk/候选；
- DA/MCR 若方向相反，必须有预注册 interaction 解释，不能合并成总体均值。

任一 validity、direction、citation 或 harm gate 失败，即 No-Go；不能改用 task/legacy-chain/compatible-partial 把失败“救回”。

---

## 12. 优先级与工程路线

### P0：先修无须新调用的硬错误

- Forest/IMPC safe identity，移除 substring merge；
- proposition normalization + exact-offset dedup；
- view/doctor 只作 provenance；
- Collapse3c 新增 `against_fact_ids` 与 direction validator；
- typed polarity/time/subject/object schema；unknown 显式保留。

### P1：离线 deterministic audit

- 重放 2,400 stages 的 safe split/dedup pre-selector score/frontier；
- 生成 edge-validity queue；
- 对 E5/E8/E9/E11 只复算其原冻结 estimand；
- 固化六个 sentinel 和 shams。

### P2：未来小规模 `CF_EDGE_AUDIT_V1`

- 先 V，再 D/S；
- 只有方向超过 sham，才进入 I；
- 只有 edge gap 真实存在，才进入 R。

### P3：通过后移植

- 优先 Collapse3c → Lite/Forest comparator 的 typed fact/against/provenance；
- Forest 保留 residual view capture；IMPC 保留 minority unique-evidence lane；
- 最终仍是一轮冻结 comparator，不做多系统投票。

### P4：只有再训练明确获批时

- 才考虑 CAD 式 clinician-authored revision 或 CGME 式 memory；
- 必须把训练真值、教师、数据来源和 split 泄漏单列，不能与 training-free 结果合并。

---

## 13. 最终判断

这批论文并未证明“生成更多反事实病例”能突破 Forest/APHHM-C 天花板。公开实现反而给出三个强警告：

1. **CF-MAR**：如果不固定 hypothesis，所谓 CPG 会比较不同诊断的不同置信度；如果 validity fail-open，语义漂移会被当信号。
2. **MedCounterFact/CSS/DeVisE**：有响应不等于正确响应；干预本身可能 no-op、不连贯、危险或方向规则错误。
3. **ECR/C4/现有日志**：结构化字段和图的存在不等于关系正确；未观测、阴性、时间、对象与来源若没有合法绑定，结构只会把错误写得更确定。

相较基线，当前证据真正支持的底层机制是：

- **固定同一竞争假设**，避免 label-switch 伪效应；
- **将证据写成可验证、带方向的 proposition**，避免字符串和 rationale 代替关系；
- **预注册期望方向并配 matched shams**，区分 sensitivity、correct responsiveness 与噪声；
- **只在必要时测低阶 interaction**，识别 cancellation/synergy 而不在线指数枚举；
- **只对 disputed edge 定向补证**，避免普通 RAG 对 base/CF 取回同样或污染材料；
- **保持 append-only state 与一次冻结比较**，防止错误关系造成不可逆删除。

因此，Forest/IMPC/Collapse3c 的下一步不是再增加一个“counterfactual agent”，而是先建立可信 proposition/identity substrate，再把小型 counterfactual edge audit 作为 comparator 前的、可关闭的审计侧车。它通过后才有资格影响排序；未通过时应完整回退当前安全基线。

---

## 附录 A：官方仓库与日志摘要

| 工作 | 审计 commit | 代码 | 仓库内结果/日志 |
|---|---|---|---|
| MedEinst/ECR | `984ccda` | ECR 未发布 | 无 |
| CF-MAR | `265d1ae` | 推理/评分较全 | 无结果、配置、测试或日志 |
| Evidence Audit | — | 未发现官方 repo | 无 |
| DeVisE | `d5a0b99` | 生成/推理/分析 | 未提交 data/results/logs |
| CSS | — | 未发现官方 repo | 无 |
| MamaBench | — | 未发现官方 code；有 HF data | 无 inference logs |
| MedCounterFact | `f35b980` | dataset only | 无 |
| MEDEXA | `f06bea8` | LangGraph/RAG/评估 | 统计数组；无 raw results/logs |
| Pearl lab | `6d0fbd1` | data/notebook/script | 有发布 responses/reviewer sheet |
| BioRAB | `a76aebf` | 部分代码 | 当前 main 稀疏；历史 `c8045f2` 有 MedMCQA logs |
| CheckList | `4e6e5e3` | 完整 test harness | release benchmark predictions |
| Contrast Sets | `e2b8731` | data/eval | 多任务 model outputs |
| CAD | `6f232a1` | data only | 无模型日志 |
| SHAP | `df974a1` | 完整库 | 无本任务日志 |
| Archipelago | `8ff437e` | explainer/experiments | notebooks/table outputs |
| IDG | `5e629ce` | gradient implementation | 无本任务日志 |

## 附录 B：可复现产物

- [论文—代码—日志机器账本](results/COUNTERFACTUAL_INFERENCE_RESEARCH/paper_code_ledger.json)
- [官方仓库 commit 与 claim-level locator manifest](results/COUNTERFACTUAL_INFERENCE_RESEARCH/audited_source_manifest.json)
- [2,400 轨迹 substrate census](results/COUNTERFACTUAL_INFERENCE_RESEARCH/backbone_log_census.json)
- [2,400 输入文件 Git blob manifest](results/COUNTERFACTUAL_INFERENCE_RESEARCH/input_manifest.json)
- [离线 census 脚本](counterfactual_log_census.py)
