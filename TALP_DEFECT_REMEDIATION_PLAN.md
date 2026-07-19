# TALP 缺陷修复:实施结果 + 生产侧默认 OFF 设计

> 范围与边界:**评测 + 设计文档**。本轮**不改 controller/config 的默认行为**;所有生产侧修复只出
> 默认 OFF 的设计。所有数字为 9 例、单次运行、llama-3.3-70b(temp=0,±1 抽样噪声)。
> 触发文档:[`TALP_STATUS_EXPLAINER.md`](TALP_STATUS_EXPLAINER.md) §7.10/§9.4、
> [`EVIDENCE_ANNOTATION_LR_DEFECTS_RESEARCH.md`](EVIDENCE_ANNOTATION_LR_DEFECTS_RESEARCH.md)、
> [`QUALITATIVE_KNOWLEDGE_INJECTION_RESEARCH.md`](QUALITATIVE_KNOWLEDGE_INJECTION_RESEARCH.md)。

## 1. 缺陷 → 修复 → 验证 映射

| 缺陷(出处) | 修复类型 | 验证脚本 / 产物 | 结果 | 落地状态 |
| --- | --- | --- | --- | --- |
| 融合 KB 指错方向(§9.4) | 评测算法修复 | `scripts/assert_fused_direction.py`、`eval_evidence_precision.py` | 4/4 方向断言通过;LLM+KB SELECT@1 7/9→8/9 | 已修(评测) |
| 正常/否定被当强 rule-IN(A2/A4/A8) | 评测方向守卫 + 生产设计 | 同上(polarity 双向对照 12/12) | normal lipase 从误指 pancreatitis → 无信号 | 评测已修;生产默认 OFF 设计(§4.1) |
| 不识别共性证据 SHARED-trap(§10-1) | 去噪臂(评测) | `eval_talp_discrimination.py --denoise` | SHARED 50%→70% **但 rule-in 86%→54%**(权衡) | 负向结论:见 §3.2 |
| 决定性证据缺席 SELECT@1(§7.10-2) | KB 注入 | `eval_talp_discrimination.py --kb` | LLM 单独 44~66% → +KB 77~88% | 评测已证 |
| 抽象检索词 + 排名靠后(§10-3) | 检索最佳配置 | `eval_l1_abstraction_retrieval.py` | 45~63% → **95~100%**(深取回+sibling) | 评测已证;生产 drop-in 已存在 |
| dense 塔缺席(§10-3 强化) | hybrid RRF | QUALITATIVE §7.5-7.6 | 方向覆盖 48%→69%,注入 57%→67%,零回归 | 已验证;生产 `HybridCPGRetriever` drop-in |
| 证据塌缩/稀释(§7.10-1) | 判别门控(默认 OFF) | `test_discrimination_gate.py`、`eval_downstream_trace --gate` | 单测 13/13;trace 见 §3.5 | 已挂钩,默认 OFF |
| 父子越级排除(§7.10-4) | 设计文档 | [`PARENT_CHILD_CONSISTENCY_DESIGN.md`](PARENT_CHILD_CONSISTENCY_DESIGN.md) | LLM 侧 trap/lift 2/2;风险在下游 | 默认 OFF 设计 |
| chunk 内异常数值是否操作化(新增) | 核验探针 | 代码走查(§3.4) | 患者值已操作化;语料 chunk 值未结构化 | backlog |
| 量化缺口/定向挖掘/形态学(§10-4) | 长期 backlog | — | — | §5 backlog |

## 2. Workstream 1 — 融合方向 bug 修复(已落地评测侧)

**根因**(见 [`scripts/eval_evidence_precision.py`](scripts/eval_evidence_precision.py) `FusedKB`):旧
`strength` 把方向性似然比与非方向性语料 mention 计数相加取 argmax,mention 能压过 LR,LR 缺失时纯
按热度定向。

**修复:**
- `signal()` 分离 `dir_strength`(仅 LR / grounded layer-B)与 `mention`(cpg+cr 计数,不参与方向)。
- `favored()` 只用 `dir_strength` 定向(需最小间隔);`mention` 仅在 `mention_fallback=True`(**默认 OFF**)
  且比值 ≥1.5 时兜底;否则"无明确信号"。
- **polarity 守卫**:`normal/negative/absent/…` 修饰的发现(polarity −1)一律不得 rule-IN。

**验证**(`scripts/assert_fused_direction.py`,全绿):

| 例 | 旧 argmax | 新 favored | 说明 |
| --- | --- | --- | --- |
| mb57 situs inversus | chronic aspiration | **primary ciliary dyskinesia** | LR~26 现胜过 mention |
| mb55 NME | glucagonoma | glucagonoma | 强 LR,方向稳定 |
| mb65 低 LAP | leukemoid reaction | **无明确信号** | 数据缺口据实呈现,不再热度误指 |
| mb66 normal serum lipase | acute pancreatitis | **无明确信号** | 否定守卫,不再误 rule-IN |

polarity 双向对照 12/12:6 个否定式判 −1、6 个正当异常(elevated lipase / low LAP / elevated PTH /
basophilia / situs / NME)判 +1(不误压)。

## 3. Workstream 2 — 实验臂量化

### 3.1 SELECT+KB(2b)
修复后融合块重跑:LLM 单独 SELECT@1 44~66% → **LLM+KB 77~88%**。原 §E1 结论(33%→77%)成立,方向
修复后进一步稳到 8/9。**KB 的价值在"选择",不在"方向"。**(`logs/talp_discrim_fixdir_kb.json`)

### 3.2 去噪臂(2a)——重要的负向/权衡结论
显式注入"KB 派生的共性 finding 清单":**SHARED-trap 50%→70%,但 rule-in DIRECTION 86%→54%**。
原因:仅凭"语料 mention 均衡"判共性会**误标决定性但被同等书写的项**(elevated PTH、prior surgery、
unilateral discharge),模型据"清单内不得区分"把它们答成 none。**这是 "mention ≠ discrim" 的又一实证。**
结论(见 [`TALP_DISCRIMINATION_CAPABILITY.md`](TALP_DISCRIMINATION_CAPABILITY.md) §E1c):
- 去噪信号应来自**候选表型集合差**(present-in-none-uniquely 交集),而非 mention 计数;
- 去噪的落地形态必须**"只降权、不强制 none"**,避免误伤决定性项。

### 3.3 检索最佳配置(2c)
`eval_l1_abstraction_retrieval.py`:top_k=8 无 sibling 时关键 finding 召回 45~63%;**top_k=20 + sibling
闭包 → 95~100%,实体 100%**。与 QUALITATIVE §7.5-7.6 的 **hybrid(TF-IDF∪MedCPT RRF)** 互补(方向覆盖
48%→69%、注入 57%→67%、零回归)。推荐证据检索形态:**hybrid RRF + 组合入口 `"{L2 具体病} {finding}"`
+ 扩 chunk_type(differential+evaluation+red_flag) + K 与门控联动(8~10)**;sibling 仅小补丁。

### 3.4 chunk 数值操作化核验(value-operationalization-probe)
代码走查 [`controller.py`](src/agentclinic_tree_dx/controller.py) `_build_annotator_payload`(L2183)、
`_gather_atomic_findings`(L2527):
- **患者自身异常值**:经 `FindingNormalizer` 做**值-方向感知**归一(如 "35% blasts"→"Elevated blast
  count"),产出结构化 atomic finding → `lr_reference`,且以原文(`raw_result`/state 投影)进入标注器。
  **已操作化**。正常值被**主动跳过**(与 polarity 守卫同理,避免伪表型)。
- **语料 chunk(CPG/case_report)prose 里的异常/参考值**:**未被结构化**为方向/定量信号。CPG/case_report
  是分支召回源;标注器的 `lr_reference` 来自缓存/marker 层(+ 仅在 `enable_lr_rag_fallback` 时的
  StatPearls/Textbooks RAG 片段,数值仅作文本 prose 出现,不解析)。
- **结论**:患者值已用;**语料 chunk 值未操作化**——列入 backlog(§5),暂不改生产。

### 3.5 证据塌缩门控(collapse-gate)
判别门控 `enable_discrimination_gate` 已挂钩(默认 OFF),单测 `test_discrimination_gate.py` 13/13 通过。
scoped 下游 trace(`eval_downstream_trace_medbullets.py`)结果见下表(no-gate vs gate,同题);trace 产物
`logs/downstream_nogate2.json`、`logs/downstream_gate1.json`。

| 例 | no-gate 轨迹(family maxp) | gate | 读数 |
| --- | --- | --- | --- |
| case1 Pancoast | traj `[0.315,0.331,0.289,0.31,0.153]` rank2 → **pred=A ✓** | pred=A ✓ | 两臂均答对;no-gate 末轮仍见被动下滑(0.331→0.153) |
| case9(类白/CML) | **480s CPU-runaway 超时**(未完成) | — | 下游 trace 谷仓在该题不稳定(与前序 §13 记录一致) |

**读数(诚实结论):** 本次 scoped 2 例 A/B **不足以判定门控对塌缩的净效**——case1 两臂本就答对(仅见
no-gate 末轮被动下滑的塌缩征象,与 §7.10-1 现象吻合),case9 因 CPU-runaway 超时未完成。门控本身
**已挂钩且单测 13/13**;其对"被动降权"的缓解仍以前序受控 A/B(见
[`RESIDUAL_MISS_ROOTCAUSE_AND_MECE.md`](RESIDUAL_MISS_ROOTCAUSE_AND_MECE.md) §13b)为准。下游全 9 题 trace
属重载且历史上不稳定(subprocess 隔离 + 超时),留作专项回归而非本轮阻塞项。

## 4. Workstream 3 — 生产侧默认 OFF 设计(不改行为)

### 4.1 限定词/否定方向感知(对应 A2/A4/A8)
- **现状**:`is_nondiscriminative_finding`([`lr_quant.py`](src/agentclinic_tree_dx/knowledge/lr_quant.py) L103-120)
  只拦"整体正常体检"(within normal limits / unremarkable),**不拦"normal serum lipase"这类带限定词
  的具体化验**;`lookup_fuzzy` 模糊匹配取回裸标志物 "serum lipase→pancreatitis LR100",丢限定词。
- **设计(默认 OFF)**:①扩 `is_nondiscriminative_finding`(或新增 `finding_polarity`)识别
  `normal/negative/absent/not elevated/no evidence of` 修饰的具体化验;②在 `get_lr_reference`/`lookup_fuzzy`
  **透传 polarity**——polarity −1 时该 finding 不得进入某病的强 rule-IN 通道,应映射为 rule-OUT 或 neutral;
  ③以 flag `enable_qualifier_direction`(默认 False)门控,回归验证后再开。评测侧已用 `_finding_polarity`
  验证该逻辑(§2)。

### 4.2 去噪门判据:从"有无数值"改为"有无方向"(对应 §9.4 defect 6)
- **现状**:bundler `min_marginal_ig_threshold`([`config.py`](src/agentclinic_tree_dx/config.py) L47)
  按信息增益/数值有无过滤;§9.4 指出唯一在去噪的门用错了判据。
- **设计(默认 OFF)**:去噪应按 **present-in-favored ∧ absent/weaker-in-competitor**(方向)而非"有无
  数值";信号源用候选表型集合差(见 §3.2 结论),**只降权不强制 none**。挂 `enable_discrimination_gate`
  已有的门控路径,新增判据以 flag 门控。

### 4.3 父子一致性
交叉引用 [`PARENT_CHILD_CONSISTENCY_DESIGN.md`](PARENT_CHILD_CONSISTENCY_DESIGN.md):rule-in=max(children)、
rule-out=min(共性);LLM 侧 trap/lift 全对,风险在下游聚合/清洗代码。保持默认 OFF。

### 4.4 争议证据的"判别编译"门控智能体(默认 OFF 设计;operationalizes backlog #2)
- **动机**:§3.2/§11.2 证明——基于 mention 计数的共性清单无法区分"真共性"与"决定性但被同等书写";
  正确信号是**值感知 + 极性感知的表型集合差**(present-in-favored ∧ absent/negated-in-competitor)。
  与其用语料统计近似,不如让一个**专职门控智能体**在**争议 finding**上,直接把检索到的 chunk **编译
  成结构化的定向规则**。
- **触发范围(成本门控)**:只在 finding 落入"多候选均 mention 且融合 KB 无明确方向"的**争议集**时触发
  (即当前会被误标为共性的那批),而非每条 finding,天然限定调用量。
- **输入 / 输出**:输入=该 finding + 检索到的方向性 prose chunk(hybrid RRF,§3.3);输出=结构化规则
  `{finding, value_condition → {rule_in:[...], rule_out:[...]}}`,如 `PTH 升高 → rule_in: 原发性甲旁亢;
  rule_out: 牛奶-碱`、`PTH 低/正常 → 反向`。此即把"present-in-favored ∧ absent-in-competitor"从语料
  统计升级为**基于证据的按需编译**。
- **消费方**:同一条规则同时供①**拣选器**(据"谁独有"判定该 finding 是否决定性、要不要主动去查)与
  ②**解释器/标注器**(据结果值给出方向,而非把裸检查名当共性抹平)。
- **保险(强制)**:①**grounded/abstain 守卫**——chunk 未明确陈述该对比时必须弃权返回"无明确方向"
  (对齐 `kb_gated_cr` 门控与 fixdir 的 no-clear-signal 原则),严禁自由发挥;②默认 OFF,以 flag
  `enable_discriminator_agent`;③A/B 编排:LLM 单独 ‖ +静态 KB ‖ +门控智能体,分层看强区不回归 +
  争议集 rule-in 回升;④输出规则可缓存复用,降本。
- **风险**:仍是 LLM,受同样能力上限约束;但任务被**收窄为"从给定文本抽取一条对比规则"**且**有出处
  锚定**,比开放式判别可控。列为**默认 OFF 的设计 + 实验臂**,不改本轮生产行为。
- **已落地评测臂并实测(2026-07-10)**:`scripts/eval_talp_discrimination.py --disc-agent`
  (`_contested_findings` + `_gather_evidence` + `_build_disc_blocks`,三重守卫:接地弃权 / 极性 /
  纯增量 USE-only 不进 rule-out)。两种子 LLM+KB vs +智能体:**SELECT@1 7/9→8~9/9、SELECT@2 →9/9,
  DIRECTION 基本不掉(77~81%,对照 E1c 去噪臂 54% 的塌方),RULE-OUT 7/9 保持**;残余代价 SHARED-trap
  50%→40%(偶把真共性项如 hypercalcemia 编成 USE)。**结论:这是目前"既去噪又不误伤"最好的形态**;
  下一步叠加"候选表型集合差"守卫(仅当 finding 不在候选交集才允许 USE)根治 SHARED 残缺。详见
  [`TALP_DISCRIMINATION_CAPABILITY.md`](TALP_DISCRIMINATION_CAPABILITY.md) §E1d。
- **未达预期的根因审计**:12 条 USE 中 6 条完全正确、1 条部分正确、5 条明确误编；直接进入 DIRECTION
  的 11 条规则被消费 LLM **11/11 遵守**，故主因不是目标模型拒绝 instruction。错误链是：检索返回
  “某病可见某表现”的单病种关联块（医学上相关、但缺 competitor-negative/weaker 对照）→编译器违反
  abstain 门槛，把 association 升级为 leaf-level discrimination→消费方忠实放大。下一版保险：
  ①落盘原始 `chunk_id/source/candidate/excerpt`（当前 audit 仅存 `why/n_evidence`，尚不能完全区分
  “未检到反证”与“检到但忽略”）；②USE 必须同时引用 supporting + contrasting excerpt，缺任一则
  abstain；③候选表型交集与父子层级作确定性 veto。

#### 4.4.1 v2 分阶段消融落地(P0..P7,已实测,2026-07-10)

把上面三条"下一版保险"整理成可累加、可单独开关的实验路线图并全部落地
(`scripts/eval_talp_discrimination.py --disc-ablation` / `--disc-stage p0..p7`;`DiscAgentConfig`
+ `_build_disc_blocks_v2` + `_compile_rule`),两个种子(7/11)各跑一遍,得到以下量化结论。**边界不变**:
全部在评测脚本内,生产 controller/config 行为不变,新特性默认 OFF。

- **P0 审计地基**:每条 evidence 落盘 `ev_id/chunk_id/source/candidate` + 比较/否定/数值/高特异标志;
  `_audit_summary` 把每条 USE 拆成"反证未检到 / 反证检到但被忽略"。**实测:所有阶段
  `contrast_not_retrieved=0`、`contrast_retrieved_but_ignored=全部`——反证其实检到了,失败在编译升级
  association 为 discrimination。** 这把 §11.2.2 的悬案钉死在"编译判据",而非"检索缺口"。
- **P1 对称取证**(`_search_evidence`,`cfg.symmetric`):全候选对称 + `expand_ddx_siblings` + 每候选每源
  等额配额 + 比较/否定/数值块优先。**实测:单加检索几乎不动 SEL/SHARED**(印证 P0 结论)。
- **P2 值/极性归一**(`_finding_meta` 复用 `FindingNormalizer`):否定/正常结果**类型化改判 rule-OUT**
  而非丢弃。SHARED 略升。
- **P3 全候选 effect 矩阵**(`_DISC_AGENT_MATRIX_PROMPT`,`neutral`≠`unknown`):**决定性结构修复**——
  过度签发 USE **19→8 腰斩**,同时 **SELECT@1(两种子均)83%→94%、SHARED 50%→55%、RULE-OUT 72%→78%、
  DIRECTION 84% 不掉**。
- **P4 准入门(OR)**(`_admission`:成对证据 / 高特异声明 / 可靠 LR)+ **P5 表型集合差 + 父子 veto**
  (`_pheno_veto` 用 `DxDiscriminatorIndex.get_phenotypes` 集合差,覆盖充分才硬 veto):**保险而非增益**,
  在 P3 上不再抬头条也不回归。**→ 评测头条推荐配置 = P5(P1+P2+P3+P4+P5)。**
- **P6 独立蕴含验证器**(`_entail_check` + `_ENTAIL_PROMPT`,与编译器解耦):按最初"非 yes 即弃权"在稀疏
  语料上**过度弃权(USE→0~1)**;**已软化**为"仅 `conflict`、或 `no` 且无独立锚点(可靠 LR/高特异)时
  弃权"。
- **P7 按字段路由**(`_routed_blocks`):把"中性项→必须答 none"注入 DIRECTION **复现去噪臂过压制,DIR 塌到
  59%**;**已软化**为 neutral 只进 SELECT 的 AVOID、绝不进 DIRECTION,并把结构化 `rule_out` 单独喂给
  RULE-OUT(规避首版 prose 注入 77%→44% 的回归)。软化后 DIR 回到 82%,但 SELECT 的 AVOID 仍偶尔劝退
  决定性项(SEL@1 78%),**仍不如 P5,默认 OFF**。

**两种子平均对照(SEL@1 /18,DIR /44,RULE-OUT /18,SHARED /20):**

| 臂 | SEL@1 | DIR | RULE-OUT | SHARED | USE(s7,s11) |
| --- | --- | --- | --- | --- | --- |
| LLM+KB | 15/18 (83%) | 37/44 (84%) | 13/18 (72%) | 10/20 (50%) | — |
| **v2/P3** | **17/18 (94%)** | 37/44 (84%) | 14/18 (78%) | **11/20 (55%)** | 8,8 |
| **v2/P5(头条)** | **17/18 (94%)** | 37/44 (84%) | 14/18 (78%) | 10/20 (50%) | 8,7 |
| v2/P6 严格(修前) | 16/18 (89%) | 39/44 (89%) | 14/18 (78%) | 9/20 (45%) | 1,0 |
| v2/P7 neutral→none(修前) | 14/18 (78%) | 28/44 (64%)↓(seed7 单独 59%) | 14/18 (78%) | 12/20 (60%) | 0,1 |
| v2/P7 软化后 | 14/18 (78%) | 36/44 (82%) | 14/18 (78%) | 9/20 (45%) | 2,3 |

**生产侧默认 OFF 设计接线(不改本轮行为)**:若采纳 v2,建议以 flag `enable_discriminator_agent` +
`disc_agent_stage="p5"` 暴露头条配置(逐候选 effect 矩阵 + 准入/veto 保险),`p6/p7` 保留但默认关闭;
A/B 编排沿用 §6 保险矩阵(强区不回归 + 争议集去噪回升为验收门)。数据:
`logs/talp_discrim_rm{7,11}_dv2_p*.json`(逐阶段,含 `disc_audit`+`audit_summary`)、
`logs/talp_discrim_fx{7,11}_dv2_p7.json`;详见
[`TALP_DISCRIMINATION_CAPABILITY.md`](TALP_DISCRIMINATION_CAPABILITY.md) §E1e。

#### 4.4.2 残余 SHARED-trap 根因 + "共识否决"组合臂(实测,2026-07-10)

P5 头条 SHARED-trap 停在 50%。逐条归因:**A 类(3/5)从未进入争议集**(mention 入选门:误给方向 /
分布不均衡 / mention 太少);**B 类(2/5)进了但矩阵给 ≥2 候选打 rule_in、取首个签发 USE**,而
`_pheno_veto` 因自由文本无法映射到 DiagRL 表型串(`n_present=0`)抓不住。针对 B 类做了一次多措施组合
(`--disc-stage p5c`/`p5cms`,`consensus_none`:多重支持坍缩 + DIRECTION 答 none 路由,永不压制存活单
rule_in)。两种子平均:**SHARED 50%→65%、SELECT@1→100%,但 DIRECTION 84%→70%↓**——多重支持信号继承
矩阵 rule_in 噪声(真决定性项 `weight loss` 被误标第二 rule_in→误压)。**未过"rule-in 不塌方"验收门**,
且 A 类够不着。两类根因收敛到同一缺失能力:**独立于矩阵与 mention 的结构化表型交集**;而 DiagRL 表型库
对本组关键候选(恶性高钙/牛奶碱/维D中毒/结节病/adhesions/sigmoid volvulus/leukemoid 均 0 表型)零覆盖。
**故残余 SHARED-trap 属数据覆盖受限**,原则修法 = §5 backlog #5(病名归一化)+ 新增"关键候选 HPO 表型集合
补齐";`p5c/p5cms` 代码保留、默认 OFF。数据:`logs/talp_discrim_cn{7,11}_dv2_p5c.json`、
`logs/talp_discrim_cnms{7,11}_dv2_p5cms.json`;详见
[`TALP_DISCRIMINATION_CAPABILITY.md`](TALP_DISCRIMINATION_CAPABILITY.md) §E1f。

#### 4.4.3 Round A 稳健性 + Round B 检索键层级(实测,2026-07-10)

本轮初版入档存在统计与解释错误,现按 §E1j 更正。`talp_ci.py` 已改为**病例 cluster bootstrap +
A/B 配对重采样**:9 个 case ID 才是独立样本,seed×case 行不是独立患者。

- **正确基准**:P5 头条(2 seed)为 SELECT@1 94.4%、DIR 84.1%、SHARED 50%;P7 为
  77.8%/81.8%/45%。初版把 P7 误称为 P5,已纠正。
- **获得支持的信号**:三种子 p5ccv vs P7 的 SHARED 为 73.3% vs 43.3%,配对 delta
  **+30.0 [95% CI +7.4,+51.9]**;相对 P5(两种子)为 +25.0 [+5.6,+45.8]。因此不能概括成
  “全部差异都在噪声内”。但 p5ccv DIR 点估计 71.2%,低于 P7 81.8%/P5 84.1%,方向回归风险仍在。
- **A6 soft-none 未过门**:DIR 68.2%;相对 P5 为 −15.9 [−30.0,−4.3],且 SHARED 从 p5ccv
  75% 降到 70%。当前实现默认 OFF;不能从该负结果反推“硬覆盖不是根因”。
- **A1/A2/A4/A5/B0/B1/B2**:配对 95% CI 均接触/跨 0,当前样本**不能确定增益方向**。
  这不是“证明无效”。A5(SELECT +11.1、SHARED +10 点)与 A2(SHARED +15 点)值得扩样本复核。
- **A4 模型 A/B**:qwen3 compiler 的 SELECT/RO 点估计提高、DIR 略降、SHARED 不变;只能说
  “本次未证明换模型能修复”,不能说“已证明错误不是弱模型伪影”。
- **A3 LOO**只有 seed7,且每臂重新调用 LLM;1–2 例变化混合了组件效应与调用波动,不能作为边际贡献估计。
- **A7**只做 `--disc-dry` 规则级扫描;证明阈值改变 USE/multi-support 数量,**没有测下游阈值敏感性**。
- **A8(a)**:KG vs 语料 `pheno_common` 一致率 40.9%、κ=−0.06,说明操作化严重不一致,不宜未经
  校准就做硬共识门。低 κ **不能证明两源不独立**;需人工金标判断谁更准确。
- **A8(b)**:LLM 与数据集 role 一致 33/41,8 条进入人工复核队列;不能据此声称“20% 金标错误”。
- **B0/B1**没有量化出确定的键层级惩罚/恢复。可能机制包括检索结果重叠、下游仍见具体候选、指标不敏感;
  当前实验不能区分。**B2**生成了正确的层级 provenance,但 PARENT 基线已 100%,不能证明误排除率下降。

所有臂仍默认 OFF。完整绝对性能、配对 delta CI 与文件溯源见
[`TALP_DISCRIMINATION_CAPABILITY.md`](TALP_DISCRIMINATION_CAPABILITY.md) §E1j。

## 4.5 Workstream 4 — 检索键层级的生产设计(B3,默认 OFF,不改行为)

**缺陷定位**:生产 `plan_temporary_leaves`([controller.py](src/agentclinic_tree_dx/controller.py) L1900-1915)以
**抽象族名 `b.label`** 作知识注入键,而决定性表型挂在**具体子病名**下;当前 harness 用具体 `name` 检索,故此缺陷
可能被掩盖。B0/B1 只表明:**在当前 9 例与当前 harness 中,单纯替换检索查询键没有量化出确定惩罚或恢复**。
原因尚未区分(检索结果重叠、下游仍看到具体候选、LLM 补偿或指标不敏感均可能),因此不能宣称已复现生产缺陷。

**设计(本轮只写、不改 controller)**:
1. **注入键改为 `representative_diseases`/预展开实体**:在 `plan_temporary_leaves` 里对每个 L1 分支,先用
   `Branch.representative_diseases`(缺失时 `DiseaseNameResolver.expand_to_entities(b.label)`)展开成具体病实体,
   **以具体实体为 KG/CPG/case_report 的检索与门控键**,而非 `b.label`。
2. **finding × 具体病矩阵 + 层级聚合**(移植评测侧 `_hier_aggregate`):any 存活子病支持 F→支持父族;all 子病冲突→
   排除父族;仅个别子病→child-specific(**不排除父族**,修"大量原始细胞排除 CML"类父子误排除)。聚合带 provenance
   (记录支持来自哪个子病)。
3. **开关点与回滚**:新增 `ControllerConfig.enable_concrete_expansion_keys: bool = False`(+ `enable_hier_aggregate`),
   默认 OFF;打开仅改注入键与聚合、不改分支树与 label;回滚=置回 False。
4. **验收门(落地前)**:须先在扩样本后的 harness 上以 CI 证明"具体键 vs 抽象注入"有越过 CI 的下游增益(B0 现有
   探针在 n=9 无法证明,故**暂不落地生产**),且 DIRECTION 不跌破基线 CI 下界。

## 5. 长期研究 backlog(纯文本检索天花板/需结构化先验)
1. LAP / PTH / 低磷等常见化验的 **grounded LR 量化补全**(带 Sn/Sp + provenance 硬门控)。
2. **present-in-favored ∧ absent-in-competitor 定向挖掘**(超越 mention 覆盖)。
3. **阴性/缺失型鉴别叶**推理(负证据)。
4. **形态学 gestalt 可匹配化**:把"成熟粒细胞谱系 vs 一片原始细胞"转成结构化描述子/模板短语
   (`granulocytic maturation spectrum present` / `blast-predominant marrow`)。
5. **finding 同义桥 / 疾病变体归一化补齐**(A4/A5;病名归一化已有
   [`disease_name_resolver.py`](src/agentclinic_tree_dx/knowledge/disease_name_resolver.py),缺发现侧桥)。
6. **语料 chunk 数值结构化抽取**(§3.4:让 chunk 内异常/参考值成为可用的方向/定量信号)。
7. **关键候选 HPO 表型集合补齐 + HPO-ID 级归一化**(§4.4.2 / §E1g 根因,已实测细化):门控原只读
   DiagRL 单源;本轮改为 **DiagRL ∪ PrimeKG 多源**并加"表型确认共识门 `p5cp`"(两源均已在生产知识层
   加载,`_resolve_disease_keys` 即"抽象标签→具体子型预展开",覆盖从 ≈0 抬到多数候选数百表型)。实测
   (seed7/11):表型确认门**达成保护决定性项的设计目标**(`weight loss` npres=0→塌缩被拦、DIR 未误压),
   **但 SHARED 不涨、DIR 略降,净负**。坐实两条根因:(a)**同义/标签鸿沟**——PrimeKG 无字面
   `hypercalcemia`(只有 `hypercalciuria/elevated calcitonin`)、`leukocytosis` 仅命中 CML 一家,故 B 类
   共性项 salient-token 词面匹配仍确认不出→SHARED 不涨;(b)`adhesions/sigmoid volvulus/milk-alkali/
   malignancy-hypercalcemia` 在 PrimeKG 亦 0 表型(真实缺失)。**故 principled 修法 =(i)finding 与候选
   表型都做 HPO-ID 归一化后再取交集(关闭同义鸿沟,非词面比);(ii)对 CPG/case_report 做"疾病→表型断言"
   抽取补 KG 真实缺失术语(非共现计数)**。到位前多源 provider 仅作 veto 召回补充、不驱动"答 none";
   `p5cp/p5cpms` 代码保留、默认 OFF。数据:`logs/talp_discrim_pk{7,11}.json`、`logs/pkp5_{7,11}.log`、
   `logs/talp_discrim_dry7_dv2_p5cp_audit.json`;详见
   [`TALP_DISCRIMINATION_CAPABILITY.md`](TALP_DISCRIMINATION_CAPABILITY.md) §E1g。
   **§E1h 续测(非结构化源可否补 KG 缺口)**:新增语料成员确认门 `p5cc`(`_corpus_pheno_intersection`
   + `_PHENO_MEMBER_PROMPT`),让 LLM 仅凭各候选自己的 CPG/case_report chunks 判"该 finding 是否此病的
   典型表现"(成员语义,非鉴别语义)。实测(seed7/11 均值)**证实非结构化源确能补上 KG 缺的覆盖**:
   `hypercalcemia` np=5、`SBO pattern` np=2(KG 里 adhesions/sigmoid volvulus 均 0 条目)→SHARED 50%→65%、
   SELECT@1→94%;**但 DIRECTION 掉到 63–68%(比 KG 确认更差),未过"rule-in 不塌方"门**。根因:成员问句
   剥离数值方向,`elevated PTH` 被判 3 家成员(PTH 陷阱换皮),且"答 none"是硬覆盖、放大编译器把决定性项
   (`weight loss`)误判为共性→误压。**故 principled 修法定型为三步**:(i)语料成员 ∪ KG 仅作 **veto 召回补充**
   抬覆盖;(ii)成员问句必须 **value-conditioned**(问"*升高的* PTH 是否此病表现");(iii)以**软信号**
   (降权 / 提示 AVOID)替代"答 none"硬覆盖。`p5cc/p5ccms` 代码保留、默认 OFF。数据:
   `logs/talp_discrim_cc{7,11}.json`、`logs/talp_discrim_cc7dry_dv2_p5cc_audit.json`;详见 §E1h。
   **§E1i 续测(同义/向量检索可用性 + 数值条件化)**:(a)**同义感知/向量检索已在仓内、无需新编码器/联网**——
   `EmbeddingIndex`(SentenceTransformer+`hpo_embeddings.npy`+FAISS)把 finding 语义映射到 HPO ID 且天然
   数值感知(`hypercalcemia→HP:0003072`、`elevated PTH→HP:0003165`、`suppressed PTH→HP:0000829`),PrimeKG
   表现型节点本就是 HPO 型(`y_id`=HPO 数字),可建 disease→{HPO_ID} 按 ID 求交(=对齐文本空间的 KG 向量
   检索,既有资产)。但 HPO-ID 联结证明**残余瓶颈在疾病侧 KG 缺边**(hypercalcemia 在高钙 DDx 疾病上无
   disease→phenotype 边;milk-alkali/adhesions 整病不在 KG),向量/HPO-ID 只补 finding 标签同义、补不出缺失
   疾病表型边。(b)**数值条件化已实施(`p5ccv`)且有增益**:用既有 `FindingNormalizer` 的 value/direction/
   polarity 注入成员问句。两种子均值 **SHARED 65%→75%↑、DIRECTION 66%→70%↑**(比裸语料成员双升),SHARED 达
   项目最高;但 DIR 仍比 KG 头条低 ~14 pts,残因是**"答 none"仍为硬覆盖**。**故 backlog #7 三步中 (ii) 数值
   条件化已验证有效**,最后卡点收敛到 (iii):把"答 none"降级为 DIRECTION 软提示/降权而非硬覆盖。
   `p5ccv/p5ccvms` 代码保留、默认 OFF。数据:`logs/talp_discrim_ccv{7,11}.json`;详见 §E1i。
8. **扩独立病例(最高优先,§4.4.3)**:当前只有 9 个 case cluster;增加 seed 不会增加独立病例数。
   p5ccv 的 SHARED 增益已获配对 bootstrap 支持,但多数单措施 CI 仍接触/跨 0。扩到数十个独立病例后,
   重跑 A5/A2、多种子 LOO 与下游阈值扫描,并重点量化 p5ccv 的 DIRECTION 回归风险。
9. **金标复核与修订(A8b,须临床签字)**:LLM 二次意见对 41 条 role 有 8 条分歧,形成待审队列
   (`leukocytosis w/ normal diff`、`chronic sinusitis`、`elevated ALP`、`many circulating blasts`、`SBO pattern`)。
   这**不等于 20% 金标错误**;任何数据集标签改动须临床签字后另行提交。
   数据 `logs/talp_gold_audit.json`。
10. **校准共识门 + HPO-ID 归一化(A8a)**:KG 与语料 common 判定一致率仅 40.9%、κ≈0,说明两路
    操作化不一致;低 κ 不能判定统计独立性。先以人工金标校准各路 precision/recall,再决定 AND/OR/加权融合。
    同时让 finding 与疾病表型都做 HPO-ID 归一化,并从 CPG/case_report 抽“疾病→表型断言”补 KG 缺边。
11. **检索键层级生产落地(§4.5/B3)**:`plan_temporary_leaves` 以 `representative_diseases`/预展开实体为注入键 +
    层级聚合;须先在扩样本 harness 上以 CI 证明具体键的下游增益(B0 在 n=9 无法证明),再上 `enable_concrete_
    expansion_keys` 默认 OFF 的开关。

## 6. 回归风险 × A/B 保险矩阵

| 改进 | 回归风险 | A/B 设计 | 验收门 | 落地状态 |
| --- | --- | --- | --- | --- |
| W1 融合方向修复 | 低(仅评测) | 修复前后 argmax 对照 + 4 例断言 + polarity 双向 | 4/4 + 12/12 | 已修(评测) |
| 2b KB 注入 SELECT | 中(强区可回归) | LLM 单独 vs +KB 同题同种子 | 强区不跌破基线−噪声带 | 出厂强制门控 `kb_gated_cr` |
| 2c hybrid 检索注入 | **高**(实证伤强区) | `kb_p0`(显示回归)‖ `kb_gated_cr`(证明消回归);LR 桶 × MedBullets+RareArena 分层 | 门控后强区回 15/16 | 门控为出厂形态;默认 OFF |
| 2a 去噪清单 | 中(误压决定性) | KB vs KB+去噪同题 | decisive rule-in 不得跌 | **负向:当前形态不推荐**(§3.2) |
| lr-qualifier 否定守卫 | 中(过度压制) | 否定式 ‖ 正当异常 双向对照 | 正当 rule-in 不被误压(12/12) | 评测已修;生产默认 OFF |
| 判别门控 | 低(默认 OFF) | `--gate` A/B + 单测 | 单测 13/13 | 默认 OFF |
| Round A/B 全臂(A1/A2/A4/A5/A6/A7/B0/B1/B2) | 低(默认 OFF) | 病例聚类配对 bootstrap 95% CI | delta CI 不含 0 + DIR 门 | p5ccv SHARED 获支持;A6 DIR 明确未过;其余未定,默认 OFF |
| B3 检索键层级(具体实体注入) | 高(改注入键) | 具体 vs 抽象注入,扩样本后 CI | 越 CI + DIR 不塌 | 仅设计,默认 OFF(§4.5) |

**保险原则:** 固定基线臂、同题同种子、temp=0;分层报告(LR 桶 × 数据集)暴露"总分升、强区跌"的
隐性回归;知识注入出厂强制门控且并列无门控臂显示回归幅度;两次运行去 ±1 噪声;任何生产落地须先过
验收门,再以 flag 默认 OFF 落地。

## 7. 扩病例执行结果与下一门槛（2026-07-11）

已从 MedXpertQA Hard 筛选 10 个诊断/病因问题，经逐 claim 文献校准后纳入 8 个、排除 2 个。
排除不是清洗失败，而是保险机制生效：无 vignette 的题不能评价 TALP；“男童 CPP 应做 MRI”不能
被错误升级为“已有 CNS 病灶”。正式扩展 fixture 为
`data/eval/talp_medxpert_expansion_cases.json`，保留 `human_clinical_signoff=false`。

17-case、2-seed 配对复跑给出:

- P5：SELECT@1 82.4%、DIR 76.8%、SHARED 60.5%；
- p5ccv：82.4%、65.9%、71.1%；
- p5ccv+A5：82.4%、70.7%、73.7%。

p5ccv 相对 P5 的 DIR 差为 −11.0 [−20.5,−2.6]，已明确越过回归线；SHARED 差 +10.5
[0,+23.7] 仍未越过预设统计门。A5 将 DIR 拉回 4.9 点，但相对 P5 仍低 6.1 点且区间跨 0。
因此:

1. **生产候选仍是 P5；所有 corpus-membership/组合门保持默认 OFF。**
2. backlog #8 从“尚未扩样本”更新为“已扩到 17 个独立病例，下一门槛 30–50 个并完成临床签字”。
3. backlog #9 新增 8 个文献复核病例待临床签字；来源题库 gold 不能覆盖文献裁决。
4. 新的最高优先故障簇是 hard-none/membership 误压有效证据，代表例包括 `weight loss`、
   `prior abdominal surgery`、`unilateral bloody nasal discharge` 与
   `bilateral inferonasal lens dislocation`。
5. A5 作为 p5ccv 的前置保险有正点估计，但只恢复部分新增病例，不是独立可投产修复。

实现边界仍未改变：本轮只改评测脚本、评测数据与设计文档；没有改 controller/config 的生产行为。

### 7.1 新增 8 例低分根因(逐题 + 逐部件，详见 explainer §13)

新增集 SELECT@1 62.5%、DIRECTION 71.1%，明显低于旧 9 例。逐题拆解后归为三类，按可修复性排序：

1. **任务-数据集适配(首要，3/8)**：mxh011/mxh014/mxh068 是"病原体归属"题，决定性是培养、vignette
   不足以唯一推出菌种。这不是算法退化。**动作：评测里单列 `task=organism_attribution` 分层报告**，
   不与表型判别能力混记。
2. **大模型共性陷阱(第二，4/8)**：mxh036/mxh046/mxh055/mxh068 的 DIRECTION 失败都是"共性/干扰
   共享表现被错误定向"，与旧集 §9.4 同源。**动作：沿用 §12.6 的 hard-none→软降权方向，不加硬门控**
   (硬门控会连决定性证据一起压掉，见 §11.2)。
3. **题干信息/主动检查缺口(个别)**：mxh036 的 decisive`空腹低血糖`不在 vignette，需"主动提名缺失
   检查"能力，与 §9.5 第 4 点同类。

结构清晰、互斥强的疾病族(mxh045/mxh075)在新数据上依旧稳，证明低分集中在上述两类，不是新数据普遍
更难。这 8 例仍待临床签字(§4.4.3 backlog #9)，任何据此改标签/改门控的动作须扩到 30–50 例后再定论。

## 8. 类型化证据修复落地状态（2026-07-11）

- **fixture v2**：candidate-conditioned effects、可变长度、引用与 task type；8 case、0 audit
  error，未签字，实验专用。
- **SELECT 对齐**：gold pool、独立 judge、顺序臂、case-normalized；alias/一致性单测通过；
  legacy 保持默认。
- **typed router**：HPO/LOINC/SNOMED/RxNorm/RadLex/temporal + FHIR event shape；
  route/abstain 单测通过，默认 OFF。
- **compound**：atomic/syndrome/dual，entailment 后才接纳 syndrome；正负 probe 4/4，默认 OFF。
- **entry gate**：legacy/all/typed_uncertain + decisive-loss audit；决定性 finding 保留单测通过；
  默认 legacy。
- **pathogen index**：causative/culture/host-factor typed edge + provenance；culture 5/5、无培养
  abstain 5/5、误归因 0；默认 none。
- **A/B 与回归门**：有序多 seed runner、paired CI 输入、DIR/RO/suppression gate；9 个单措施/
  表示臂及 typed-entry 对照已完成，命令与结果 manifest 可复现。

边界保持不变：没有修改生产 `controller.py`/`config.py`，没有覆盖旧 fixture 或 SNOMED JSON，
也没有把语料 mention 次数转换成 LR。组件 precision 达标只允许进入端到端候选臂；默认提升仍须
P5 DIRECTION/RULE-OUT 不下降、无新增 decisive suppression、临床签字，并扩到 30–50 个独立病例。

### 8.1 梯度裁决

完整绝对性能、95% case-cluster CI 与配对 delta 已入档到
`TALP_DISCRIMINATION_CAPABILITY.md` 表 E1l-A/B/C。关键头条对照为：

- P5：SELECT@1 82.4、valid 85.3、DIR 76.8、RO 76.2、SHARED 60.5；
- p5ccv：82.4、82.4、65.9、73.8、71.1（DIR 相对 P5 −11.0
  [−20.3,−2.5]，明确回归）；
- p5ccv+A5：82.4、82.4、70.7、76.2、73.7（DIR −6.1
  [−15.8,+2.3]，SHARED +13.2 [0,+27.5]，均未解决）；
- typed-entry 虽把 SHARED 从 66.7 提到 86.4，但 DIR 74.6→64.9、RO
  81.0→76.2，严格回归门失败。

1. fixture-v2 基线（3 seed）为 SELECT 25.5%、DIR 80.7%、RO 88.9%、SHARED 36.4%。
2. atomic/dual 的主要 delta 均未解决；syndrome 在 `resolved=0` 的无操作状态仍出现显著差，判定为
   远端模型非确定性造成的方法学警报，不算功能增益。
3. 无泄漏 multi-ontology 的 SELECT delta +17.6 [0,39.2]，但概念覆盖仅 2/81，DIR/RO 为负点估计；
   不过门。一次 additional-gold 泄漏试跑已作废并由单测封堵。
4. pathogen-corpus 的 SELECT match +15.7 [5.9,27.5]，DIR/RO 点估计回归门通过；SELECT-valid
   未提高，所以只保留为 `organism_attribution` 分层实验。
5. 真实 20,935-edge pathogen-openkb-v4 的 SELECT +5.9 [−2.0,15.7]，DIR −1.8、
   RO −3.2，全部 unresolved，且零容忍点估计回归门失败。
6. typed-entry 相对同配置 legacy-entry：SHARED +19.7 [4.3,40.7]，但 DIR −9.6、RO −4.8，
   严格回归门失败。
7. 没有措施同时满足互补性和零回归验收，故按预注册规则停止在单措施梯度，不运行组合/LOO，
   不提升任何默认值。

### 8.2 病原体知识库实测

原库不支持细粒度菌种归属：legacy SNOMED 虽保留 18,873 条因果关系，但 organism 端点可解析
为 0；PrimeKG 无 typed pathogen row；HPO LR/Layer-B 在 10 个 probe 上方向信号 0/10；
CPG/CR 虽 mention 10/10，但只能用于召回。

现已用**新路径、默认 OFF**建立 RF2 typed slice + PathoPhenoDB + NCBI Taxonomy 别名桥：
PathoPhenoDB 解析 3,957 条边，融合索引 20,935 条。真实开放 KB 对培养题解析 2/5、无培养
abstain 5/5、误归因 0，故结论是“已部分覆盖，但仍不足以替代带引用的 corpus 补边”。
详细源级审计、缺口和许可见 capability §E1l.2；运行入口仍是
`--pathogen-source`/`--pathogen-open-kb`，默认 `none`。

### 8.3 P5 基线纠偏与回退保护

已纠正“typed 梯度以 LLM-only/p5ccv 而非最优 P5 为基线”的方法学缺陷。新的治理口径是
17 case v2 × seed 7/11/13 × DISC-v2 P5，同批 baseline 为：
SELECT 80.4%、valid 86.3%、DIR 79.8%、RO 82.5%、SHARED 56.1%。

所有 typed 单措施已在该基线上复跑。最强正向点估计来自 pathogen-fused：
DIR 84.2%（+4.4 [0,+9.5]）、SHARED 57.6%（+1.5），但 RO 降至 77.8%（−4.8）且
decisive suppression +2.0，严格门失败。multi-ontology/typed-entry 均约 +3.5 DIR，
也各有 RO 或 SELECT 回归。没有臂全面优于 P5+v2，也没有臂过零回归门。

因此：

1. §8.1 的 LLM-only/p5ccv 结果只作预筛选，不再作为生产提升证据；
2. 后续新实验默认治理基线改为 `--baseline-family=p5`，但该参数本身默认不启用；
3. P5 compiled blocks 以 compiler input/config/P5 asset manifest 指纹缓存，基线与不改变入口的
   措施臂共享同一规则，降低 LLM 编译噪声；
4. 12 个 P5 外部输入以 size+SHA-256 固化，runner 每臂前后验证，10/10 臂及最终复核均
   12/12 unchanged；原 HPO/Guideline/PrimeKG/CPG/CR 文件保留为回退；
5. 所有输出使用 `p5typed_*` 新 tag、新 manifest 和新 cache，不覆盖旧 P5 或 typed 日志。

完整表、CI 和文件溯源见 capability §E1m。
