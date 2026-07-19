# TALP 判别能力检测(隔离层,9 例 MedBullets)

目标:隔离评估 TALP 的核心能力——**选定最佳证据以区分候选叶**。做法是喂入人工构建的 L2 候选集
(正确叶 + 强干扰项,部分位于不同 L1 父支),分两块:

- **Block 1 — LLM 自身能力边界(llama,无 KB)**:给定 vignette + 候选集,LLM 能否指出决定性
鉴别证据、并判对每个 finding 的方向?
- **Block 2 — 三源关键证据覆盖审计**:每个关键鉴别 finding,生产 **LR 源** / 新 **CPG** 语料 /
新 **case_report** 语料能否提供可用的判别信号?缺口何在?

数据集:`[data/eval/talp_discrimination_cases.json](data/eval/talp_discrimination_cases.json)`
(9 例,`candidates` 带 `l1_parent`+`is_gold`、每例含 ≥1 个跨父支强干扰项;`findings` 带
`decisive`/`shared` 标记)。脚本:`[scripts/eval_talp_discrimination.py](scripts/eval_talp_discrimination.py)`、
`[scripts/eval_discriminator_coverage.py](scripts/eval_discriminator_coverage.py)`(复用
`[scripts/eval_lr_coverage_isolated.py](scripts/eval_lr_coverage_isolated.py)` 的 LIRICAL/layer_b/sibling_lr)。
模型 llama-3.3-70b-instruct,单次运行,n=25 个关键 finding。

> 为什么隔离层:`controller.plan_temporary_leaves`(L1891-1963)对鉴别候选的打分**完全是 LLM
> 自报 LeafScore,无确定性 value-of-information**,且 bundler 按列表顺序而非分数选取。所以这条
> 机制的**能力天花板就是原始 LLM**——Block 1 直接测它。

---

## Block 1:LLM 能力边界(无 KB)


| 指标                                    | 结果              | 含义                                     |
| ------------------------------------- | --------------- | -------------------------------------- |
| SELECT@1(首选 = 金标决定性鉴别项)               | **2/9 (22%)**   | 严格:LLM 的第一鉴别项须命中人工标注的 decisive finding |
| SELECT@2(前二命中)                        | 2/9 (22%)       | 放宽到前二仍很低                               |
| SELECT valid(首选是"临床上有效的鉴别项")          | **6/9 (66%)**   | 宽松:judge 只问"这个检查能否有意义地区分"              |
| DIRECTION(逐 finding 判对favored候选)      | **20/25 (80%)** | 给定 finding,LLM 判方向的准确率                 |
| **SHARED-trap 规避(把共性 finding 判为非判别)** | **0/9 (0%)**    | 共性 finding 应答 "none",LLM **无一次**做到     |


**关键读数:**

1. **LLM 是不错的"方向判断者"(80%),但不是好的"鉴别项选择者"**:让它主动挑最优鉴别检查,严格
  命中金标 decisive 仅 22%;即便放宽到"临床有效"也只 66%。它常挑一个"泛化确诊检查"(如 mb82
   直接 "abdominal X-ray"、mb83 "nasal endoscopy"),而非能在候选间**制造分离**的那一个。
2. **最尖锐的缺陷:共性陷阱 0/9。** 对家族共有的 finding(白细胞增多、高钙、腹胀、RUQ 痛……),
  LLM **每次都把它归给某一个候选**而非判为"不可区分"。这正是产生**虚假分离 / 过度自信错叶**的
   根源(与下游 MAP_FAIL、后验塌缩同源)。这是 TALP 当前最需要防护的能力短板。

---

## Block 2:三源关键证据覆盖

两条覆盖线:**mention**(证据在源中至少出现)与 **discrim**(源能把 favored 与竞争者分开——LR
grounded/LIRICAL/sibling-LR,或语料对 favored 疾病的 mention 数 > 最强竞争者)。


| 源                   | mention 覆盖       | discrim 覆盖      |
| ------------------- | ---------------- | --------------- |
| LR 源(生产)            | —                | **8/25 (32%)**  |
| CPG 语料(新挖掘)         | 22/25 (88%)      | 5/25 (20%)      |
| case_report 语料(新挖掘) | 22/25 (88%)      | 5/25 (20%)      |
| **任一源合并**           | **25/25 (100%)** | **14/25 (56%)** |
| 仅 decisive(12 个)    | 12/12            | 8/12            |


**关键读数:**

1. **语料里"有料"但被浪费。** CPG/case_report 的 DDx chunk **mention 覆盖 88%**,把合并 mention
  拉到 100%——鉴别信息确实存在于新语料中。但它们**当前只被用于疾病名召回**
   (`guideline_branch_source`/`case_report_source` 从不逐 finding 挖掘)。
2. **"提到"≠"能区分"。** 朴素词面挖掘下,语料 discrim 仅 20%:因为同一 finding 在 favored 与
  竞争者**双方的 DDx chunk 里都被讨论**(鉴别诊断段落本就并列列举),mention 数拉不开差距。
   mention(100%) 与 discrim(56%) 之间的落差,就是"召回式用法"没兑现的价值。
3. **LR 源稀疏但精准**:只 grounded 覆盖 32%,主要靠 pathognomonic 标记(NME、Horner、
  basophilia)与 LIRICAL 表型 LR(situs inversus、splenomegaly)。大量普通实验室/体征
   (PTH、低磷、低 LAP)在 LR 缓存里没有 grounded 数值。

---

## 交叉分析:Block 1(LLM 是否已知方向) × Block 2(是否有源能区分)

把每个关键 finding 归入四类(n=25):


| 类别                       | 数量     | 含义 / 处置                             |
| ------------------------ | ------ | ----------------------------------- |
| **LLM+源**(两者都行)          | **12** | KB 冗余但可确认,低风险                       |
| **仅 LLM**(LLM 知方向,无源能区分) | **8**  | KB 不是杠杆,LLM 才是资产;但若不信 LLM 则**无后备**  |
| **源修正**(LLM 判错,源能区分)     | **2**  | KB 真正加值:mb11"疼痛不随头颈位置变化"、mb34"近期感染" |
| **真缺口**(LLM 判错 且 无源能区分)  | **3**  | 残余研究目标                              |


**3 个真缺口**(既非 LLM 已知、也无源可分离):

- `[mb57] normal growth and weight gain`(favors 排除 CF):**阴性/缺失型判别**(生长正常→反对 CF),
正负证据都难处理。
- `[mb65] full spectrum of maturing myeloid cells on smear`(favors CML):**形态学 gestalt**,
难以词面命中。
- `[mb77] elevated alkaline phosphatase`(favors 甲旁亢):**弱/共性实验室**,区分力本就低。

**4 个 decisive 落在 discrim 缺口**(源无法量化,只能靠 LLM):low LAP(CML)、elevated PTH、
hypophosphatemia、unilateral foul purulent discharge——这些恰是"仅 LLM"类里的高价值项。

---

## 结论与后续杠杆

1. **能力边界清楚**:TALP 的天花板是 LLM;LLM 判方向尚可(80%),但**主动挑最优鉴别项(22%)**、
  尤其**识别共性/不可区分证据(0%)**很弱。**共性陷阱 0/9 是最应优先修的能力缺陷**——它直接
   制造虚假分离。可行方向:给 TALP 显式注入"候选共有 vs 独有表型差集"(现有
   `get_discriminator_hints` 已能产出集合差,但 prompt 未消费),并要求它显式标注"该证据是否
   family-shared"。
2. **新语料是未兑现的判别资产**:CPG/case_report mention 覆盖 88%,但当前只做召回。把落差
  (mention 100% vs discrim 56%)转化,需要一个**逐 finding 的方向性挖掘步骤**(present-in-favored
   且 absent/negated-in-competitor),而非并列 mention 计数——这是把语料 DDx 文本变成判别证据的
   关键改造。
3. **LR 源精准但稀疏(32%)**:适合作为高置信锚点(pathognomonic + LIRICAL),不适合覆盖普通
  实验室/体征;普通判别项要靠语料挖掘或 LLM。
4. **残余真缺口是"阴性判别 / 形态 gestalt / 弱共性实验室"**(3/25):这类无法靠现有 RAG 词面
  挖掘补齐,是纯 RAG 的天花板,需负证据推理或结构化实验室先验。

(数据:`logs/talp_discrim_llm.json`、`logs/discriminator_coverage_cov.json`;n=25 finding、
单次运行、llama-3.3-70b;语料挖掘为词面 mention 下界。)

> 说明:以上 Block 1/2 基于 **v1 数据集**(favors/shared 二分,n=25 关键 finding,其中 24 rule-in、
> 仅 1 rule-out)。下方「扩展评测(v2)」在**重写后的数据集**上复测:显式 `role`
> (`rule_in_gold`/`rule_out_distractor`/`shared_nondiscriminating`/`parent_child_trap`)、补齐 rule-out
> (9 个)、并加入 `parent_child` 块与 LLM+KB 潜力臂。v1 的读数作为历史保留。

---

# 扩展评测(v2):rule-out / 父子一致性 / LLM+KB / L1 抽象 / 精度

数据集 v2 findings 构成:**rule_in_gold 22 · rule_out_distractor 9 · shared_nondiscriminating 8 ·
parent_child_trap 2**(mb65 CML、mb82 adhesions 带 `parent_child` 块)。脚本新增:
`[scripts/eval_l1_abstraction_retrieval.py](scripts/eval_l1_abstraction_retrieval.py)`、
`[scripts/eval_evidence_precision.py](scripts/eval_evidence_precision.py)`(含
`build_fused_discriminator_hints` 融合块,被 Block 1 的 LLM+KB 臂复用)。

## E1:Block 1 扩展 —— rule-out / 父子 / LLM 单独 vs LLM+KB

| 指标 | LLM 单独 | LLM+KB | 读数 |
| --- | --- | --- | --- |
| SELECT@1(首选=金标 decisive) | 3/9 (33%) | **7/9 (77%)** | KB 融合块把「主动挑最优鉴别项」从 33%→77%,**最大增益** |
| SELECT valid(首选临床有效) | 6/9 (66%) | 6/9 (66%) | 有效性本就可以,KB 主要修「是否命中决定性那一个」 |
| DIRECTION(rule-in 判方向) | 19/22 (86%) | 20/22 (90%) | 本就强,KB 略增 |
| **RULE-OUT(判对"反对哪个干扰项")** | **7/9 (77%)** | 7/9 (77%) | rule-out 是独立能力,LLM 单独已不错;KB 无额外增益 |
| **SHARED-trap 规避(共性答 none)** | **1/10 (10%)** | **4/10 (40%)** | 仍是最弱项;KB 有帮助但远不够,LLM 仍过度归因共性证据 |
| PARENT trap(不排除父家族) | 2/2 | 2/2 | 子型特征(原始细胞/SBO)未被误读为排除父 |
| PARENT lift(子阳性→支持父) | 2/2 | 2/2 | 子确诊上浮父,方向正确 |

**关键读数:**

1. **KB 对「选择」的杠杆最大(SELECT@1 33%→77%)**:注入融合的 grounded 信号(LR + CPG/CR 挖掘)后,
   LLM 更常锁定人工标注的决定性鉴别项。这与 v1 结论一致(LLM 是好的方向判断者、差的选择者),
   并新证明:**这条短板可由 KB 显著补偿**——即"接入 KB 有必要"的正面证据。
2. **rule-out 是独立且不弱的能力(77%)**:补齐 9 个 rule-out 后,LLM 单独就能判对"该证据反对哪个
   干扰项"约 3/4;KB 在此不加值。v1 只有 1 个 rule-out,严重低估了这块。
3. **共性陷阱依旧是首要缺陷(10%→40%)**:即便给了 KB,LLM 仍倾向把家族共有 finding 归给某个候选。
   这印证 v1:**TALP 最该补的是"识别不可区分证据"的护栏**,KB 只能部分缓解。
4. **父/子一致性:LLM 本身没问题(trap 2/2、lift 2/2)**。即"原始细胞不排除 CML""子确诊上浮父"
   LLM 都判对——所以层级不一致的风险**不在 LLM,而在下游聚合/清洗规则**(见
   [`PARENT_CHILD_CONSISTENCY_DESIGN.md`](PARENT_CHILD_CONSISTENCY_DESIGN.md))。

(数据:`logs/talp_discrim_llm.json`、`logs/talp_discrim_kb.json`。)

### E1b:融合方向 bug 修复后的重跑(增补,2026-07-09)

上表的 LLM+KB 臂注入的融合块 `build_fused_discriminator_hints` 曾把**方向性的似然比与非方向性的
语料 mention 计数相加取 argmax**,致 mb57(situs LR~26 却指向慢性误吸)、mb65(低 LAP 无 LR 却指向
类白血病)等**指错方向**。已修复(方向只由 grounded 方向性信号决定;mention 仅作默认 OFF 的比较性
回退;`normal/absent` 等否定发现不得 rule-IN)。修复后**同题重跑**(seed 保持;`logs/talp_discrim_fixdir.json`
与 `logs/talp_discrim_fixdir_kb.json`):

| 指标 | LLM 单独(fixdir 重跑) | LLM+KB(**旧融合块**) | LLM+KB(**修复后融合块**) |
| --- | --- | --- | --- |
| SELECT@1 | 4/9 (44%) | 7/9 (77%) | **8/9 (88%)** |
| SELECT valid | 7/9 (77%) | 6/9 (66%) | **8/9 (88%)** |
| DIRECTION | 21/22 (95%) | 20/22 (90%) | **21/22 (95%)** |
| RULE-OUT | 7/9 (77%) | 7/9 (77%) | 7/9 (77%) |
| SHARED-trap 规避 | 0/10 (0%) | 4/10 (40%) | 4/10 (40%) |
| PARENT trap / lift | 2/2 · 2/2 | 2/2 · 2/2 | 2/2 · 2/2 |

**读数(增补,不替代上表结论):**
- **修复融合方向后,LLM+KB 的 SELECT@1 7/9→8/9、SELECT valid 6/9→8/9、DIRECTION 20→21/22**:去掉误
  导性方向提示后,KB 注入不再把模型带偏,"选择"增益进一步坐实(旧结论 33%→77% 仍成立,方向修复
  再抬一格)。
- **LLM 单独臂的数字与上表(sel1 33%、dir 86%、shared 10%)有 ±1 波动纯属 temp=0 抽样噪声**:融合方向
  修复只改 KB 注入块内容,不改 LLM 单独臂,故差异非本次修复所致。
- **确定性方向断言**(`scripts/assert_fused_direction.py`,4/4 通过):mb57 situs `chronic aspiration→PCD`、
  mb55 NME→glucagonoma、mb65 低 LAP `leukemoid→无明确信号`(数据缺口据实呈现,而非热度偏置误指)、
  mb66 `normal serum lipase` 因否定守卫从 `acute pancreatitis→无明确信号`。

### E1c:去噪臂 —— 显式注入"共性 finding"清单(增补,2026-07-09)

在 LLM+KB 之上再注入一个**KB 派生的"共性 finding"清单**(`scripts/eval_talp_discrimination.py --denoise`,
`_build_common_blocks`):清单只由**融合 KB 判为无方向 + 在多数候选都被 mention + mention 分布均衡**
的 finding 组成,**从不使用数据集的 role/favors 标签**(避免泄漏)。提示明确"清单内的 finding 不得
用于区分"。同一 seed 下 KB 臂 vs KB+去噪臂:

| 指标 | LLM+KB | LLM+KB+去噪(均衡版) | 读数 |
| --- | --- | --- | --- |
| SHARED-trap 规避 | 5/10 (50%) | **7/10 (70%)** | 显式共性清单**确能抬升**共性陷阱规避 |
| DIRECTION(rule-in) | 19/22 (86%) | **12/22 (54%)** | **但重伤 rule-in**:清单误含决定性项,模型对其一律答 none |
| SELECT@1 | 7/9 | 7/9 | 选择不变 |
| RULE-OUT / PARENT | 7/9 · 2/2 · 2/2 | 7/9 · 2/2 · 2/2 | 不变 |

(未加均衡守卫的朴素版更极端:SHARED-trap 冲到 10/10,但 DIRECTION 塌到 7/22。)

**关键读数(这是一个重要的负向/权衡结果):**
1. **仅凭"语料 mention 是否均衡"来判定共性是不安全的**:像"甲状旁腺激素升高""既往腹部手术史"
   "单侧脓涕"这些**临床决定性**的 finding,在语料里对所有候选都被均衡讨论(高钙血症检查本就对每个
   病因都提 PTH),于是被误标为共性 → 模型据"清单内不得区分"把它们答成 none,rule-in 直接崩。这正是
   本工作反复出现的 **"mention ≠ discrim"** 命题的又一实证:mention 分布分不开"真共性"与"决定性但被
   同等书写"。
2. **正确的去噪信号应来自集合差(候选表型的交集),而非 mention 计数**:即用
   `get_discriminator_hints` 的表型**交集**(present-in-none-uniquely)作共性集,决定性项因是某病独有
   不会落入交集。这需要 DxDiscriminatorIndex/PrimeKG 对这些常见病有覆盖,列为下一步。
3. **去噪步骤的落地形态必须"只抑制、不强制 none"**:当前提示"清单内必须答 none"过刚;应改为"清单内
   降权/不作为唯一依据",避免误伤决定性项。

(数据:`logs/talp_discrim_fixdir2_kb.json`、`logs/talp_discrim_fixdir2_denoise.json`。)

### E1d:判别编译门控智能体臂(增补,2026-07-10)

E1c 的教训是"基于 mention 计数的共性清单"会误伤决定性证据(rule-in 86%→54%)。本臂改用一个**判别
编译门控智能体**(`scripts/eval_talp_discrimination.py --disc-agent`,`_build_disc_blocks`)落地设计
[`TALP_DEFECT_REMEDIATION_PLAN.md`](TALP_DEFECT_REMEDIATION_PLAN.md) §4.4:

- **只在"争议 finding"上触发**(`_contested_findings`:多候选均 mention、分布均衡、融合 KB 无方向——
  即 E1c 会误标为共性的那批;数据缺口型如低 LAP 因 mention 不足被排除,永不被压)。
- **逐条检索证据**(CPG + case_report,`_gather_evidence`)喂给编译智能体,令其**只依据证据**判定该
  finding 是 `use`(带**结果值条件**的定向规则,如"PTH 升高→支持原发性甲旁亢、反对牛奶-碱")还是
  `common`(证据未给出明确对比 → 弃权)。
- **三重保险**:①**接地/弃权守卫**(证据未陈述对比必须判 common,禁止凭先验);②**极性守卫**(否定/
  正常结果不得 rule-IN);③**纯增量**——只把 `use` 规则注入,`common` **不**作"必须答 none"的指令
  (避免 E1c 的过压制),且规则只进 SELECT/DIRECTION、不进 RULE-OUT(否则实测拖累 rule-out)。

两个种子(seed 7 / 11)下,同题 LLM+KB 臂 vs LLM+KB+判别智能体臂:

| 指标 | LLM+KB | +判别智能体(seed7) | +判别智能体(seed11) | 读数 |
| --- | --- | --- | --- | --- |
| SELECT@1 | 7/9 (77%) | **8/9 (88%)** | **9/9 (100%)** | **头条增益**:编译出的 USE 规则帮模型锁定决定性项 |
| SELECT@2 | 7/9 | **9/9** | **9/9** | 决定性项几乎必进前二 |
| DIRECTION(rule-in) | 20/22 · 18/22 | 18/22 (81%) | 17/22 (77%) | **仅小幅波动,未塌缩**——与 E1c 的 54% 形成对照,证明"纯增量 + 接地"设计有效 |
| RULE-OUT | 7/9 (77%) | 7/9 | 7/9 | 保持(规则不进 rule-out 后) |
| SHARED-trap 规避 | 5/10 (50%) | 4/10 (40%) | 4/10 (40%) | **残余代价**:偶把真共性项编译成 USE |
| PARENT trap / lift | 2/2 · 2/2 | 2/2 · 2/2 | 2/2 · 2/2 | 不变 |

**关键读数:**
1. **这是"安全去噪/增益"迄今最好的形态**:SELECT@1 从 KB 臂的 77% 抬到 88~100%,且 **rule-in 不塌缩**
   (81/77% vs E1c 去噪臂的 54%)——正是"纯增量 USE + 接地弃权 + 极性守卫"三条保险共同作用的结果。
2. **智能体把"值条件"编译对了那几条决定性项**:`elevated PTH → 支持原发性甲旁亢 / 反对牛奶-碱`、
   `unilateral foul/bloody discharge → 支持鼻腔异物`——这些正是 SELECT@1 上台阶的来源;而真数据缺口
   (mb11 各项、mb55 高血糖)被如实判为 common、不硬编。
3. **残余风险仍是"过度提升真共性项"**:智能体偶尔把 `hypercalcemia→甲旁亢`、`RUQ 痛→Budd-Chiari`、
   `SBO 征象→粘连` 这类**本属家族共性**的 finding 编译成 USE(它们在证据里确会被写成"支持某病"),
   于是 SHARED-trap 从 50% 微降到 40%。**根治需再叠加"候选表型集合差"守卫**:仅当该 finding 不在
   候选交集里才允许 USE(与 §E1c 结论 2 同源)——列为下一步。
4. **故障主要在规则生成/准入，不在消费方拒绝指令**:两个种子中，直接进入 DIRECTION 的 USE 规则
   共 11 条，目标 LLM **11/11 按 `rule_in` 执行**，包括错误规则。12 条总 USE 中 6 条完全正确、
   1 条方向部分正确但 rule-out 目标不完整、5 条明确误编(42%)。误编理由通常只证明“某病可见该表现”，
   没有证明竞争病 absent/weaker；即检索块多为**医学上相关但任务上不具比较性**，编译器又把 association
   升级成 discrimination。当前日志未保存原始 excerpts，只保存 `why/n_evidence`，下一版须落盘
   chunk 引用并强制同时提供 supporting + contrasting excerpt，才能进一步分解“没检到反证”与“检到
   但编译器忽略反证”。

(数据:`logs/talp_discrim_da2_kb.json`、`logs/talp_discrim_da2_disc_agent.json`、
`logs/talp_discrim_da3_disc_agent.json`;含 `disc_audit` 逐条编译规则供审计。默认 OFF,仅评测。)

### E1e:判别编译智能体 v2 —— 分阶段消融 P0..P7(增补,2026-07-10)

E1d 遗留两条硬骨头:①SHARED-trap 只到 40%(偶把真共性项编成 USE);②审计只存 `why/n_evidence`,
无法区分"没检到反证"与"检到但被编译器忽略"。本轮把 §11.2.2 错误链条上的诸项改进整理成一条
**可累加、可独立消融**的路线图(`scripts/eval_talp_discrimination.py --disc-ablation`,或
`--disc-stage p0..p7`;`_build_disc_blocks_v2`),两个种子(7/11)各跑一遍。各阶段含义:

- **P0 审计地基** —— 每条 evidence 落盘 `ev_id/chunk_id/source/candidate` 与
  比较/否定/数值/高特异标志;审计把每条 USE 分成"反证未检到 / 反证检到但被忽略"两类。
- **P1 对称取证** —— 对**所有候选**对称检索 + `expand_ddx_siblings` 文章闭包 + 每候选每源等额配额,
  比较/否定/数值块优先排序(去热度偏置)。
- **P2 值/极性归一** —— 复用 `FindingNormalizer`,把否定/正常结果**类型化改判为 rule-OUT**(而非丢弃)。
- **P3 全候选 effect 矩阵** —— 智能体对每候选输出 `rule_in/rule_out/neutral/unknown`,
  **`neutral`(有据判无区分力)与 `unknown`(资料不足)严格分开**。
- **P4 USE 准入门(OR)** —— 放行需满足其一:成对(support+contrast)证据 / 高特异声明 / 可靠 LR。
- **P5 表型集合差 + 父子 veto** —— 落在候选表型交集的 finding 禁止 leaf-level USE(覆盖充分时硬 veto)。
- **P6 独立蕴含验证器** —— 一个与编译器解耦的 NLI 校验:引用证据是否**同时**蕴含 favored-present
  ∧ competitor-absent;矛盾则 abstain。
- **P7 按字段路由** —— SELECT 读 PREFER/AVOID、DIRECTION 只读 USE 方向、RULE-OUT 只读结构化 `rule_out`。

**两种子平均(总量翻倍,SEL@1 分母 18、DIR 44、RULE-OUT 18、SHARED 20):**

| 臂(两种子平均) | SELECT@1 | DIRECTION(rule-in) | RULE-OUT | SHARED-trap 规避 | 编译 USE 数(s7,s11) |
| --- | --- | --- | --- | --- | --- |
| LLM 单独 | 8/18 (44%) | 37/44 (84%) | 15/18 (83%) | 7/20 (35%) | — |
| LLM+KB(旧融合块修复后) | 15/18 (83%) | 37/44 (84%) | 13/18 (72%) | 10/20 (50%) | — |
| **v2 / P3(effect 矩阵)** | **17/18 (94%)** | 37/44 (84%) | 14/18 (78%) | **11/20 (55%)** | 8, 8 |
| **v2 / P5(+准入门+veto)= 头条** | **17/18 (94%)** | 37/44 (84%) | 14/18 (78%) | 10/20 (50%) | 8, 7 |
| v2 / P6(严格蕴含,修复前) | 16/18 (89%) | 39/44 (89%) | 14/18 (78%) | 9/20 (45%) | **1, 0** |
| v2 / P7(neutral→none 路由,修复前) | 14/18 (78%) | **28/44 (64%)↓**(seed7 单独塌到 59%) | 14/18 (78%) | 12/20 (60%) | 0, 1 |
| v2 / P7(软化修复后) | 14/18 (78%) | 36/44 (82%) | 14/18 (78%) | 9/20 (45%) | 2, 3 |

**关键读数(增补,不替代 E1d):**

1. **P0 一锤定音地回答了 §11.2.2 的悬案**:在**所有阶段**,USE 规则的审计都是
   `contrast_not_retrieved = 0`、`contrast_retrieved_but_ignored = 全部`。即**反证证据其实检到了**,
   失败在**编译器把 association 升级成 discrimination**,不是检索缺口。这坐实了路线图前提,也说明
   "单纯加检索(P1)"不解决问题(P1 的 SEL/SHARED 与 P0 基本持平)。
2. **P3 的"neutral≠unknown 全候选矩阵"是决定性的结构修复**:它把过度签发的 USE 从 **19 条腰斩到 8 条**
   (智能体被迫对每个候选表态,把"到处都提到"的项判成 neutral 而非 rule_in),同时 **SELECT@1 抬到 94%、
   DIRECTION 稳在 84%、SHARED 抬到 55%**——一举兼顾"去噪"与"不误伤",这是 E1c/E1d 一直没做到的平衡。
3. **P4 准入门 + P5 veto 是稳定器/保险**:在 P3 之上不再抬升头条指标,但也不回归(SEL@1 94%、DIR 84%
   保持),作用是把"association 型误编"再压一层、并给父子/表型交集加确定性闸。**故推荐的评测头条配置
   是 P5(=P1+P2+P3+P4+P5)。**
4. **P6/P7 按原设计会回归,已定位并软化**:
   - **P6 严格蕴含在稀疏语料上过度弃权**(USE→0~1),等于退回纯 KB;已改为**只对 `conflict`、或
     `no` 且无独立锚点(可靠 LR / 高特异声明)时才 abstain**。
   - **P7 把 neutral 项当作"必须答 none"注入 DIRECTION,复现了 E1c 的过压制**——单条误判的 neutral 就把
     rule-in 拖垮(**DIR 塌到 59%**)。已改为 **neutral 只进 SELECT 的 AVOID、绝不进 DIRECTION**;
     修复后 DIR 从 59% 回到 82%,但 SELECT 的 AVOID 引导仍偶尔把决定性项劝退(SEL@1 78%),故
     **P7 仍不如 P5,默认 OFF**。
5. **结论**:判别编译智能体的正确形态是 **"全候选 effect 矩阵(P3)+ 准入/veto 保险(P4/P5)"**,把
   LLM+KB 的 SELECT@1 83%→**94%**、SHARED 50%→55%、RULE-OUT 72%→78%,而 DIRECTION 84% 不掉;
   **蕴含验证与 neutral 路由(P6/P7)在当前语料密度下弊大于利,保留代码但默认关闭**。

(数据:`logs/talp_discrim_rm7_dv2_p*.json`、`logs/talp_discrim_rm11_dv2_p*.json`(逐阶段,含
`disc_audit` + `audit_summary`);`logs/talp_discrim_fx{7,11}_dv2_p7.json`(P7 软化后)。全部默认 OFF,仅评测。)

### E1f:残余 SHARED-trap 的根因 + 多措施组合的"共识否决"臂(增补,2026-07-10)

P5 头条配置把 SHARED-trap 规避停在 **10/20 (50%)**。逐条核对两个种子下仍答错的 5 个共性 finding
(把 `disc_audit` 的 effect 矩阵、`_contested_findings` 的入选判据、`_pheno_veto` 覆盖三者对齐),**残余分成
两类互不相交的根因**:

| 根因 | 涉及 finding | 机理 |
| --- | --- | --- |
| **A. 从未进入编译器(3/5)** | `leukocytosis`、`bronchiectasis`、`many circulating blasts` | 基于 mention 的**入选门**把它们挡在争议集外:`leukocytosis` 因融合 KB 误给方向(favored=CML)被跳过;`bronchiectasis` 因 mention 分布不均衡(12/7/5/2,次位 < 2/3)被判非争议;`blasts` 因 mention 数不足(3<4)被排除。→ 根本没有 neutral 信号产生,DIRECTION 只能盲猜 |
| **B. 编译了但被误判(2/5)** | `hypercalcemia`、`small bowel obstruction pattern` | effect 矩阵给 **≥2 个候选**都打了 `rule_in`(高钙→原发甲旁亢 + 结节病;SBO→粘连 + 乙状结肠扭转),而 `_compile_rule` 取首个 rule_in 就签发 USE。表型集合差 veto **抓不住**:`_pheno_veto` 返回 `n_present=0`(自由文本 finding 无法映射到 DiagRL 表型串) |

**针对 B 类,做了一次"多措施并举"的组合实验——共识否决门(consensus-none gate)**
(`--disc-stage p5c` / `p5cms`,`DiscAgentConfig.consensus_none`):在 P5 之上叠加①**多重支持坍缩**
(一个 finding 若 rule_in ≥2 个候选,逻辑上不可能有鉴别力→改判 common)②把这类高置信共性项**按字段路由**为
DIRECTION 的"必须答 none"。两个子模式:`p5cms` 只用最高精度信号(多重支持),`p5c` 额外纳入智能体自报
的"全 neutral / discriminating=false"。**永不压制仍存活的单 rule_in USE**(即决定性项)。两种子平均:

| 臂(两种子平均) | SELECT@1 | DIRECTION | RULE-OUT | SHARED-trap 规避 |
| --- | --- | --- | --- | --- |
| LLM+KB | 15/18 (83%) | 37/44 (84%) | 13/18 (72%) | 10/20 (50%) |
| **P5(头条)** | 17/18 (94%) | **37/44 (84%)** | 14/18 (78%) | 10/20 (50%) |
| P5c-strict(仅多重支持) | 18/18 (100%) | 31/44 (**70%↓**) | 13/18 (72%) | **13/20 (65%↑)** |
| P5c-full(+全 neutral) | 17/18 (94%) | 29/44 (**66%↓**) | 13/18 (72%) | **13/20 (65%↑)** |

**读数(诚实的负向/权衡结论):**
1. **共识否决确实把 SHARED-trap 抬了 15 个百分点(50%→65%)、SELECT@1 抬到满分**——它成功把
   `hypercalcemia`、`SBO` 这类 B 类误编译项改判为"答 none"。
2. **但它以 DIRECTION 塌 14 个百分点(84%→70%)为代价,未通过"rule-in 不塌方"验收门。** 根因是
   **多重支持信号继承了 effect 矩阵 rule_in 标注的噪声**:一个真正的决定性项(`weight loss`→Pancoast)被矩阵
   顺手多打了一个错误的第二 rule_in(→subclavian steal),于是"≥2 rule_in 即坍缩"把它也误压成 none。
   "一个 finding 不能同时 rule-in 两个竞争病"在逻辑上成立,但它**只和矩阵 rule_in 一样可靠**。
3. **A 类的 3 项完全没被触及**——它们根本没进编译器,任何"共识路由"都够不着。
4. **两类根因收敛到同一个缺失能力:一个独立于(噪声)矩阵、也独立于 mention 统计的结构化表型交集信号。**
   而能提供它的 DiagRL 表型索引对本组关键候选**恰好零覆盖**:mb77 五个候选中
   `malignancy-associated hypercalcemia / milk-alkali / vitamin D intoxication / sarcoidosis` 全为 0 表型、
   mb82 的 `adhesions` 与 `sigmoid volvulus` 均为 0、mb34 金标 `leukemoid reaction` 为 0。这正是 P5 veto
   `n_present=0`、以及表型确认型共识门无法触发的**直接原因**。

**结论**:在当前**语料 + 表型库成熟度**下,残余 SHARED-trap **无法安全修复**——可行的组合(共识否决)能压
共性但会误伤决定性方向。**原则性修法是一个数据/覆盖项**(对应
[`TALP_DEFECT_REMEDIATION_PLAN.md`](TALP_DEFECT_REMEDIATION_PLAN.md) §5 backlog #5 病名归一化 + 新增
"关键候选 HPO 表型集合补齐"):为这些疾病名补齐结构化 HPO 表型集合(或加病名归一化),使 P5 veto 与
"表型确认型共识门"变为高精度,才能在**不动决定性 rule-in** 的前提下压住 B 类;A 类还需把入选门从
"mention 均衡"改为"表型交集触发"。**故 `p5c/p5cms` 保留
代码但默认 OFF**,头条仍为 P5。

(数据:`logs/talp_discrim_cn{7,11}_dv2_p5c.json`、`logs/talp_discrim_cnms{7,11}_dv2_p5cms.json`;
表型覆盖探针见正文。全部默认 OFF,仅评测。)

## E2:L1 抽象标签的预展开检索探针

对同一 CPG+case_report 语料,分别用**抽象 L1 父标签** / **具体金标 L2 叶名** / **L2 展开(全部候选叶名)**
作检索键,统计金标关键鉴别 finding 的召回与金标疾病实体的召回(top-8,9 例):

| 检索键 | finding 召回(top-8) | +sibling 闭包 | 实体召回(top-8) | +sibling |
| --- | --- | --- | --- | --- |
| L1 抽象标签 | 10/22 (45%) | **21/22 (95%)** | 6/9 (66%) | 7/9 (77%) |
| L2 金标叶名 | **14/22 (63%)** | **22/22 (100%)** | **9/9 (100%)** | 9/9 (100%) |
| L2 展开(候选拼接) | 12/22 (54%) | 19/22 (86%) | 7/9 (77%) | 8/9 (88%) |

### E2b:检索最佳配置确认(增补,2026-07-09)

固定"具体病种键 + sibling 闭包 + 加深 top_k"后单点复现召回天花板
(`scripts/eval_l1_abstraction_retrieval.py`):

| 配置 | L1 抽象 | L2 金标 | L2 展开 | 实体(金标) |
| --- | --- | --- | --- | --- |
| top_k=8,无 sibling | 10/22 (45%) | 14/22 (63%) | 12/22 (54%) | 6~9/9 |
| **top_k=20 + sibling** | **22/22 (100%)** | **22/22 (100%)** | **21/22 (95%)** | **9/9(L2)** |

**读数:** 关键鉴别 finding 的召回从 45~63%(浅取回)拉到 95~100%(深取回 + 同篇闭包);深到 top_k=20
时连抽象 L1 键也追到 100%——**说明"召回问题"确是排序/深度问题,信息本就在库里,非数据缺失**。这与
[`QUALITATIVE_KNOWLEDGE_INJECTION_RESEARCH.md`](QUALITATIVE_KNOWLEDGE_INJECTION_RESEARCH.md) §7.5-7.6 的
**dense 塔(MedCPT hybrid RRF)**结论互补:hybrid 把方向性块 top-6 覆盖 48%→69%、注入准确率 57%→67%、
**零回归**——即在证据检索路推荐 **hybrid(TF-IDF∪MedCPT RRF)+ 组合入口 `"{L2 具体病} {finding}"` +
门控注入(`kb_gated_cr`)+ K 与门控联动(8~10)**;sibling 闭包对本路是小补丁(§6.2 仅补救 2/12 排序),
但对深取回下的召回天花板有帮助。数据:`logs/l1_abstraction_retrieval_k8.json`、`_k20sib.json`。

**关键读数:**

1. **抽象在 top-8 有代价,但根因是排序/散布而非语料缺失**:L2 金标 → L1 抽象,top-8 finding 召回
   63%→45%(-18 pts)、实体 100%→66%(-34 pts)。但**开启 sibling 闭包**(按 `source_id` 拉同篇
   散落块,CPG §18)后,L1 抽象 finding 召回直接 45%→**95%**、抽象代价从 -18 pts 收窄到 **-4 pts**。
   → 判别 finding 一直在语料里,只是被挤出 top-8 或散在入口块的兄弟块中(见下方深度扫描)。
2. **top_k 深度扫描印证排序问题**(L2 金标叶名,无 sibling):top-8 63% → top-20 90% → top-50 95%。
   正确块存在于索引,只是排名靠后。
3. **拼接候选会稀释,逐叶检索更好**:L2 展开(候选拼进一条 query)始终不及单独用金标叶名。
   **建议:检索前把 L1 展开为 L2、对每个叶名分别检索,并对判别证据路径默认开 sibling 闭包 +
   top_k≥20**——这三者叠加可把 finding 召回拉到 ~100%。

> 与分支创建阶段的对比:sibling 闭包在**分支创建**评测里收益不大甚至有害(灌爆 40 槽候选池、被
> `_retrieve_snippets` 的 24 条 FIFO cap 挡在 LLM 外,composite 0.702→0.634)。但在**判别证据检索**
> 这一用途上它是大收益(finding 召回 63%→100%)。**同一机制、目标函数不同、结论相反**——两条路径
> 应各自配置,判别检索路径应默认开 sibling。

(数据:`logs/l1_abstraction_retrieval.json`、`logs/l1_abstraction_retrieval_l1abs_sib.json`。)

## E2b:sibling 闭包对「三源覆盖」的影响(mention vs discrim,n=22)

在 v2 数据集上以 sibling 闭包重跑三源覆盖(`eval_discriminator_coverage.py --sibling`):

| 指标 | top-8 基线 | +sibling |
| --- | --- | --- |
| CPG mineable(mention) | 19/22 (86%) | **22/22 (100%)** |
| CPG discrim | 5/22 (22%) | **8/22 (36%)** |
| **DISCRIM-covered by ANY** | 13/22 (59%) | **15/22 (68%)** |
| decisive discrim | 7/11 | **8/11** |
| discrim-GAP | 9 | **7** |

**关键读数:sibling 大幅补 mention,但只小补 discrim。** mention(召回"提到")从 86%→100%,
说明 sibling 确实把散落的鉴别 finding 捞了回来;但 discrim(能把 favored 与竞争者**分开**)只
59%→68%。原因不是召回,而是**同一 finding 在 favored 与竞争者双方的 DDx chunk 里都被讨论**——
词面 mention 数拉不开差距。**结论:排序/散布问题(mention)靠 sibling+深度基本解决;真正剩下的
discrim 缺口(≈32%)是"方向性"问题,需 present-in-favored 且 absent/negated-in-competitor 的
定向挖掘,而非更多召回。** 残余 discrim 缺口集中在阴性判别、形态 gestalt、弱共性实验室
(mb65 低 LAP、mb77 低磷等),与 v1 结论一致。

(数据:`logs/discriminator_coverage_cov_v2.json`、`logs/discriminator_coverage_cov_v2_sib.json`。)

## E3:超越覆盖 —— 精度 / 噪声 与「在哪一步过滤」

覆盖只问"源能否供给信号";精度问相反的一面:真正到达标注器的证据里,**多少是判别信号、多少是
稀释后验的噪声**(即 §13b 证据塌缩的机制来源)。用融合 KB 信号近似标注器可见的 finding 池,
按数据集 `role` 把每条分为 signal(rule_in_gold/rule_out_distractor/decisive)或 noise
(shared_nondiscriminating/parent_child_trap):

- **标注器精度 = 24/34 (70%)**:到达标注器的 finding 中约 30% 是共性/陷阱噪声。逐例精度 33%–80%
  (mb82 adhesions 最低 33%——它候选多、共性 finding 多)。

**四过滤点研究(噪声移除 vs 信号损失,累计):**

| 过滤点 | 噪声移除 | 信号损失 |
| --- | --- | --- |
| atomic 抽取(仅保留 vignette 内 top-8) | 0 | 6 |
| TALP 选择 | 0 | 0 |
| bundler `min_marginal_ig` 门 | **5** | **11** |
| 标注器 LR 注入 | 0 | 1 |

**关键读数:**

1. **TALP 选择步不过滤任何噪声(0)**——与 SHARED-trap 10% 一致:它不承担去噪职责。
2. **bundler IG 门是当前唯一显著去噪点,但过度**:移除 5 条噪声的同时误杀 11 条信号(信噪比 <1),
   因为很多决定性证据(低 LAP、PTH 等)在 KB 里拿不到 grounded 数值 → 被当"低信息"一并砍掉。
3. **atomic top-8 会漏掉 vignette 外的关键项(6 条信号损失)**:如需检查才知的 finding(Ph 染色体、
   低 LAP)不在 vignette 里,当前不进入池。

**「在哪一步去噪」建议:** 去噪职责应放在 **TALP 选择步**(它现在不做),用显式的"family-shared
差集"标注把共性/陷阱 finding 标为**非判别、不进证据环**;而 **bundler IG 门不应再兼任去噪**——
它把"无 grounded LR"误当"低信息",正在误杀高价值决定性证据(应改为"无判别方向"而非"无数值 LR"
作为剔除条件)。

(数据:`logs/evidence_precision.json`。)

## 扩展结论

1. **接入 KB 有明确价值,主要体现在"选择"**(SELECT@1 33%→77%),这是"KB 引入是否值得"的正面
   量化证据;但 KB 对"共性陷阱"只能小补(10%→40%),该护栏仍需在 TALP 侧显式实现。
2. **rule-out 是被 v1 低估的、独立且尚可的能力(77%)**;父/子一致性在 LLM 侧无问题(trap/lift 全对),
   风险在下游聚合规则,已在 [`PARENT_CHILD_CONSISTENCY_DESIGN.md`](PARENT_CHILD_CONSISTENCY_DESIGN.md)
   给出仅设计的落点。
3. **L1 抽象标签在 top-8 有代价,但根因是排序/散布,不是语料缺失或类型过滤**:CPG/CR 索引本就
   保留 4 类/全 differential(非 differential-only),mention 覆盖已 86–100%;开 sibling 闭包 +
   top_k≥20 后 finding 召回 45%→95–100%、抽象代价从 -18 收窄到 -4 pts。**判别检索路径应默认开
   sibling + 逐叶检索 + 更深 top_k**(与分支创建路径分开配置)。
4. **剩下的是"方向性"而非"召回"缺口**:sibling 把 mention 拉满,但 discrim 只 59%→68%——同一
   finding 在双方 DDx 文本里都出现,需定向挖掘(present-in-favored ∧ absent-in-competitor)而非更
   多召回。
5. **去噪应移到 TALP 选择步**;当前 bundler IG 门"以无数值 LR 为由剔除"会误杀决定性证据,是精度
   缺陷的主因。

### E1g:多源表型库(DiagRL ∪ PrimeKG)+ 表型确认门 P5cp(增补,2026-07-10)

E1f 把残余 SHARED-trap 归到"表型交集信号缺失",并把根因暂记为 DiagRL 表型库对关键候选零覆盖。
本轮回应"门控是否只用 DiagRL、能否补 PrimeKG/CPG、抽象标签能否预展开到具体病再门控"三问,做了三件事:
**(1)** 把门控的表型 provider 从 DiagRL 单源改成 **DiagRL ∪ PrimeKG** 多源(两者都已在生产知识层加载,
非新依赖);PrimeKG 自带的模糊子型解析(`_resolve_disease_keys`)正是"抽象标签→具体病预展开"——
`chronic myeloid leukemia→atypical CML/myeloid leukemia`(166 表型)、`primary hyperparathyroidism→
familial primary hyperparathyroidism`(150)、`cystic fibrosis`(542)、`sarcoidosis`(400)、`PCD`(103)。
覆盖从"≈0"抬到多数候选数百表型。**(2)** 新增表型确认门 `p5cp/p5cpms`:仅当独立的表型集合交集
(present-in ≥2 候选且非 rule_in 独占)确认某 finding 确属共性,才允许把它路由到 DIRECTION 答 none;
否则不塌方(修 E1f 里"weight loss 被矩阵误标多重支持→误压"的 DIR 掉分)。**(3)** 两种子跑 `p5`(多源 veto)
与 `p5cp`,并 dump 逐 finding 门控溯源。

| 臂(seed7/11 均值) | SELECT@1 | DIRECTION | RULE-OUT | SHARED |
|---|---|---|---|---|
| P5 头条(DiagRL 单源,E1e) | 88% | **84%** | 82% | 50% |
| P5(DiagRL∪PrimeKG veto) | 88% | 79% | 77% | 50% |
| P5cp(+表型确认共识门) | 88% | 74–77% | 77% | 50% |

**结论:多源表型确实把覆盖抬满,且表型确认门达成了它的设计目标——保护决定性项**(溯源确证:
`weight loss` multi_support=1 但 `pheno_common=0/npres=0`→塌缩被拦→DIR 未误压;`elevated PTH` npres=1
独占 hyperpara→不 veto),**但 SHARED 一点没涨、DIR 反而略降,净负**。两个根因都被溯源坐实:

- **同义/标签鸿沟(词面匹配失效)**:PrimeKG 里根本没有字面 `hypercalcemia`,只有 `hypercalciuria`/
  `elevated calcitonin`/`nephrocalcinosis`;`leukocytosis` 只字面命中 CML 一家(其余白血病表型串缺这个词)。
  于是恰恰是要抓的 B 类共性项 `hypercalcemia`(npres=0)、`SBO pattern`(npres=0)仍确认不出→SHARED 不涨。
  **富覆盖不等于可匹配**;需 HPO-ID 级归一化(finding 与表型都映到 HPO ID 再比),而非 salient-token 词面比。
- **真实缺失**:`adhesions`、`sigmoid volvulus`、`milk-alkali syndrome`、`malignancy-associated hypercalcemia`
  在 PrimeKG 里也是 0 表型——是知识图谱真没有这些术语,不是匹配问题。
- **DIR 略降**:PrimeKG 的大表型集(数百条)在词面 jaccard≥0.6 下产生少量假阳交集,`_pheno_veto` 偶把
  真判别项误判进交集,是本轮唯一的净损来源。

**净判定:补 PrimeKG/CPG 表型是对的方向,但当前以词面匹配落地弊大于利(默认 OFF,`p5cp/p5cpms` 代码保留)。
残余 SHARED-trap 的principled 修法收敛为 backlog #7 的更精确形态**:①把 finding 与候选表型都做 HPO-ID
归一化后再取交集(关闭同义鸿沟);②对 CPG/case_report 语料做"疾病→表型断言"抽取(不是共现计数)以补 KG
真实缺失的术语。二者到位前,多源 provider 只作为 veto 的召回补充、不驱动"答 none"。数据:
`logs/talp_discrim_pk{7,11}.json`(p5cp)、`logs/pkp5_{7,11}.log`(多源 veto p5)、
`logs/talp_discrim_dry7_dv2_p5cp_audit.json`(逐 finding 门控溯源)。

### E1h:非结构化语料成员确认 P5cc(增补,2026-07-10)

E1g 的 KG 确认门(p5cp)因**同义/标签鸿沟**和**真实缺失**而在 B 类共性项上失效(`hypercalcemia`
在 PrimeKG 无字面、`adhesions/sigmoid volvulus` 无条目)。本轮回应"分支创建与 TALP 都已接入的
CPG/case_report(含 Merck)这类**非结构化源**能否补上、LLM 能否把 chunks+sibling 自行整理成有效表型
信息"。做法:新增一道**语料成员确认**(`_corpus_pheno_intersection` + `_PHENO_MEMBER_PROMPT`,
stage `p5cc/p5ccms`),对每个争议 finding 单次调用 LLM,**仅凭各候选自己检索到的 chunks**回答"该
finding 是不是**这个病**的公认/典型表现"——刻意用**成员**语义(而非鉴别语义),以免继承效应矩阵把"共现对比"
升格为 rule_in 的噪声。其交集(present-in ≥2 且非 rule_in 独占)替代 KG 交集驱动共识门。两种子(7/11)均值:

| 臂 | SELECT@1 | DIRECTION | RULE-OUT | SHARED |
|---|---|---|---|---|
| P5 头条(KG 单源) | 88% | **84%** | 82% | 50% |
| p5cp(KG 结构化确认) | 88% | 74–77% | 50%→50 | 50% |
| **p5cc(语料成员确认)** | **94%** | **63–68%↓** | 77% | **65%↑** |

**核心结论(直接回答"非结构化源是否有帮助"):有帮助——但只在覆盖层,不在"答 none"的确认层。**
逐 finding 溯源(`logs/talp_discrim_cc7dry_dv2_p5cc_audit.json`)证实**LLM 确实把 chunks 整理成了有效成员
信息**,且恰好补上了 KG 缺的那些:`hypercalcemia` np=5(五候选皆识别为成员)、`SBO pattern` np=2
(adhesions+sigmoid volvulus,KG 里两者都 0 条目)、`abdominal distension` np=4——这些正是 KG 抓不到、
现在被抓到的 B 类共性项,SHARED 因此 50%→65%(seed7 到 70%)。**但 DIRECTION 掉到 63–68%,比 KG 确认更差,
未过"rule-in 不塌方"验收门**。根因两条,都和"成员语义"本身有关:

- **成员≠数值条件判别(§11.2.2 PTH 陷阱换皮重现)**:成员问句剥离了数值方向,`elevated PTH` 被判为
  hyperpara + 恶性高钙 + 维D中毒 三家的成员(np=3),因为文本里三者都"谈到 PTH"——可生理上恶性高钙/维D
  中毒是 **PTH 受抑**。幸而"绝不压制存活 USE"的护栏使其 verdict 仍为 use、未被误压;真正的损失来自
  **本已被编译器判 common 的病例内决定性项**(`weight loss` 被语料判为 Pancoast+锁骨下动脉盗血两家成员→
  np=2→路由 answer none),硬覆盖锁死了下游 LLM 本可自救的方向判断。
- **"答 none"是硬覆盖,放大编译器误判**:KG 确认保守、极少触发覆盖;语料确认更"敢判共性",于是多赢
  SHARED 的同时也多输 DIR。两者在同一 Pareto 前沿上换位,**没有把前沿推出去**。

**净判定:非结构化成员信号应作为 veto 的召回补充(与 KG 取并集、抬覆盖),而非驱动"答 none"的硬门;
且必须做成数值条件化(问"*升高的* PTH 是不是该病表现"而非"PTH 是不是该病表现",即把 P2 数值归一化下沉到
成员问句)才能不重蹈 PTH 陷阱。** `p5cc/p5ccms` 达成了"验证非结构化源可补 KG 覆盖缺口"这一诊断目的,
代码保留、默认 OFF。修法收敛到 backlog #7 的精确形态:**(i) 语料成员 ∪ KG 作为 veto 召回;(ii) 成员问句
value-conditioned;(iii) 用"答 none"以外的软信号(降权/提示 AVOID)而非硬覆盖**。数据:
`logs/talp_discrim_cc{7,11}.json`、`logs/cc{7,11}_p5cc.log`、`logs/talp_discrim_cc7dry_dv2_p5cc_audit.json`。

### E1i:同义感知/向量检索的可用性 + 数值条件化 P5ccv(增补,2026-07-10)

回应两问:"PrimeKG/扩展源能否做同义感知或向量检索(KG 向量化或需另配对齐文本空间的编码器)"、"能否实施数值
条件化"。**结论:两者都已具备,且数值条件化实测有增益。**

**(1)同义感知/向量检索——已在仓内,无需新编码器、无需联网**:`EmbeddingIndex`
(SentenceTransformer + 预算 `hpo_embeddings.npy` + FAISS)把自由文本 finding 语义映射到 HPO 术语/ID,实测
质量极高且**天然数值感知**:`hypercalcemia→HP:0003072 (1.00)`、`elevated PTH→HP:0003165 (0.96)`、
`suppressed PTH→HP:0000829 "Low PTH" (0.90)`——升高/受抑落到**不同** HPO ID。PrimeKG 的表现型节点本就是
**HPO 型**(`kg.csv` 的 `y_id`=HPO 数字、`y_source=HPO`),故可建 disease→{HPO_ID} 集合(实测 6744 病有
HPO-ID 集)并**按 HPO-ID 求交**——这就是"对齐到文本空间的 KG 向量检索",且是既有资产。**但 HPO-ID 联结证明
残余瓶颈在疾病侧 KG 缺边,而非 finding 同义鸿沟**:finding→HPO 完美后,`bronchiectasis→PCD+CF`、
`elevated PTH→hyperpara` 正确命中,但 `hypercalcemia` 在这组高钙 DDx 疾病上**根本没有 disease→phenotype 边**,
`milk-alkali/vitamin-D/malignancy-高钙/adhesions` 则**整个疾病都不在 KG**。所以向量/HPO-ID 只能补 finding 标签
同义,补不出缺失的疾病表型边——这正是 §E1h 语料成员能补而结构化 KG 补不了的原因。

**(2)数值条件化——已实施(`p5ccv`,`value_conditioned`)且有增益**:把 §E1h 的语料成员问句改为
**数值条件化**——用既有 `FindingNormalizer` 解析出的 value_state/direction/polarity(升高/受抑/正常/否定)注入
`_PHENO_MEMBER_PROMPT`,强制"判断**该数值下**是否此病表现"(升高 PTH 是甲旁亢表现、但对 milk-alkali/恶性高钙
答 no,因二者 PTH 受抑)。两种子均值:

| 臂 | SELECT@1 | DIRECTION | SHARED |
|---|---|---|---|
| P5 头条(KG 单源) | 88% | **84%** | 50% |
| p5cp(KG 结构化确认) | 88% | 75% | 50% |
| p5cc(语料成员,无数值条件) | **94%** | 66% | 65% |
| **p5ccv(语料成员 + 数值条件化)** | 88% | **70%↑** | **75%↑** |

**数值条件化比裸语料成员 p5cc 同时抬 DIRECTION(+4–5)与 SHARED(+10),坐实 PTH 陷阱被部分修好**;SHARED 达
本项目最高 75%。**但 DIR 仍比 KG 头条低 ~14 pts**——残因不再是"数值方向搞错",而是**"答 none"仍是硬覆盖**:
语料成员偶尔仍把某决定性项算作 ≥2 家成员,一旦触发硬覆盖就锁死下游。**故最后一步定型为软信号**(backlog #7
(iii):把"答 none"降级为 DIRECTION 提示/降权而非硬覆盖),预计可保住 SHARED 75% 的同时把 DIR 拉回头条附近。
`p5ccv/p5ccvms` 达成"验证数值条件化可行且有效",代码保留、默认 OFF。数据:`logs/talp_discrim_ccv{7,11}.json`、
`logs/ccv{7,11}_p5ccv.log`。

(以上 v2 数据:`logs/talp_discrim_llm.json`、`logs/talp_discrim_kb.json`、
`logs/l1_abstraction_retrieval.json`(+`_l1abs_sib`)、`logs/discriminator_coverage_cov_v2.json`
(+`_sib`)、`logs/evidence_precision.json`;单次运行、llama-3.3-70b;语料挖掘为词面 mention 下界。
本轮为**评测 + 设计文档**,不改动生产 `controller.py`/`config.py`。)

### E1j:Round A(稳健性/归因)+ Round B(检索键层级)——性能与归因更正(2026-07-10)

本节更正初版入档的三个问题:①把 **P7** 的 77.8% SELECT@1 误称为"P5 头条";真正的 P5 头条为
94.4%;②只报 delta、没有报各臂绝对性能;③旧 `talp_ci.py` 把 seed×case 行当作独立病例,并对 A/B 两臂
独立重采样。现已改为**以 9 个 case ID 为独立 cluster、同一病例的所有 seed 一起重采样、A/B 使用同一组
病例做配对 bootstrap**。因此下列数字取代本节初版数字。

#### E1j.1 评测口径与基准

- 绝对性能表和大多数 A/B 使用 seed 7/11:9 个独立病例、18 个 seed×case 观测;各指标分母分别为
  SELECT 18、DIRECTION 44、RULE-OUT 18、SHARED 20、PARENT 8。
- A0 另为 P7 与 p5ccv 补跑 seed 13:仍只有 **9 个独立病例**,不是 n=27 个独立病例;27 只是重复观测。
- 95% CI 衡量的是**病例构成不确定性**。只有 9 个 cluster,区间必然较宽;seed 重复可观察运行波动,不能替代扩病例。
- “resolved”只表示配对 delta 的 percentile 95% CI 不含 0;“unresolved”表示当前样本不能确定方向,
  **不等于两臂相同,也不等于差异是随机噪声**。

三种子 A0 基准:

| 臂 | SELECT@1 | SELECT valid | DIRECTION | RULE-OUT | SHARED | PARENT |
|---|---:|---:|---:|---:|---:|---:|
| P7 | 22/27=81.5% [59.3,100] | 21/27=77.8% [51.9,100] | 54/66=81.8% [71.2,92.6] | 21/27=77.8% [44.4,100] | 13/30=43.3% [16.7,70.0] | 12/12=100% |
| p5ccv | 24/27=88.9% [66.7,100] | 21/27=77.8% [51.9,100] | 47/66=71.2% [54.4,86.7] | 21/27=77.8% [44.4,100] | 22/30=73.3% [43.3,100] | 12/12=100% |

配对比较 p5ccv−P7:SELECT@1 +7.4 [0,+18.5]、DIRECTION −10.6 [−28.1,+4.3]、
SHARED **+30.0 [+7.4,+51.9]**。因此不能再写成“所有差异都在噪声内”:**p5ccv 对 SHARED 的提升在
三种子配对病例 bootstrap 下得到支持**,但 DIRECTION 的下降仍不能排除;这是明确的去噪/方向权衡。

真正的两种子 **P5 头条**为 SELECT@1 17/18=94.4%、SELECT valid 16/18=88.9%、
DIRECTION 37/44=84.1%、RULE-OUT 14/18=77.8%、SHARED 10/20=50%、PARENT 8/8=100%。
p5ccv 相对 P5 的 SHARED 为 +25.0 [+5.6,+45.8](resolved),DIRECTION 为 −13.6 [−28.6,0]
(未 resolved,但点估计和验收门均不利)。

#### E1j.2 各实验臂绝对性能(两种子)

单元格均为百分比:“点估计 [病例 cluster-bootstrap 95% CI]”:

| 臂 | SELECT@1 | SELECT valid | DIRECTION | RULE-OUT | SHARED | PARENT |
|---|---:|---:|---:|---:|---:|---:|
| P5 头条 | 94.4 [83.3,100] | 88.9 [66.7,100] | **84.1 [71.1,95.7]** | 77.8 [44.4,100] | 50.0 [22.2,77.8] | 100 [100,100] |
| P7 基线 | 77.8 [55.6,100] | 77.8 [55.6,100] | 81.8 [71.7,92.1] | 77.8 [44.4,100] | 45.0 [18.2,72.2] | 100 [100,100] |
| p5ccv 基线 | 88.9 [66.7,100] | 77.8 [55.6,100] | 70.5 [52.6,86.4] | 77.8 [44.4,100] | **75.0 [44.4,100]** | 100 [100,100] |
| A1 p5ccv+self-consistency K=3 | 94.4 [83.3,100] | 83.3 [61.1,100] | 65.9 [47.5,83.3] | 72.2 [38.9,100] | 70.0 [40.0,100] | 100 [100,100] |
| A6 p5ccv+soft-none | 88.9 [66.7,100] | 77.8 [44.4,100] | 68.2 [50.0,85.0] | 72.2 [38.9,100] | 70.0 [40.0,100] | 100 [100,100] |
| A5 P7+assert-filter | 88.9 [72.2,100] | 83.3 [61.1,100] | 77.3 [66.7,90.0] | 77.8 [44.4,100] | 55.0 [27.8,80.0] | 100 [100,100] |
| A4 P7+qwen3 compiler | 88.9 [66.7,100] | 83.3 [61.1,100] | 79.5 [64.8,94.4] | 83.3 [56.2,100] | 45.0 [16.7,77.8] | 100 [100,100] |
| A2 P7+local decision set | 83.3 [61.1,100] | 83.3 [61.1,100] | 79.5 [69.6,90.9] | 77.8 [44.4,100] | 60.0 [36.4,83.3] | 100 [100,100] |
| B0 P7+abstract key | 77.8 [44.4,100] | 83.3 [61.1,100] | 79.5 [69.6,90.9] | 77.8 [44.4,100] | 55.0 [27.8,80.0] | 100 [100,100] |
| B1 expand key | 83.3 [61.1,100] | 83.3 [61.1,100] | 79.5 [69.2,90.9] | 72.2 [38.9,100] | 55.0 [27.8,80.0] | 100 [100,100] |
| B2 expand+hierarchical aggregation | 83.3 [61.1,100] | 83.3 [61.1,100] | 79.5 [69.6,90.9] | 72.2 [38.9,100] | 55.0 [27.8,80.0] | 100 [100,100] |

#### E1j.3 配对增量与逐臂结论

| 实验臂−指定基线 | SELECT@1 Δ[95% CI] | DIRECTION Δ[95% CI] | RULE-OUT Δ[95% CI] | SHARED Δ[95% CI] |
|---|---:|---:|---:|---:|
| A1−p5ccv | +5.6 [−16.7,+33.3] | −4.5 [−10.9,0] | −5.6 [−18.8,0] | −5.0 [−16.7,0] |
| A6−p5ccv | 0 [0,0] | −2.3 [−7.9,0] | −5.6 [−18.8,0] | −5.0 [−16.7,0] |
| A5−P7 | +11.1 [0,+27.8] | −4.5 [−16.7,+5.0] | 0 [0,0] | +10.0 [0,+25.0] |
| A4−P7 | +11.1 [0,+27.8] | −2.3 [−9.6,+5.3] | +5.6 [0,+18.8] | 0 [−20.8,+22.2] |
| A2−P7 | +5.6 [0,+16.7] | −2.3 [−9.5,+5.0] | 0 [0,0] | +15.0 [−5.6,+44.4] |
| B0−P7 | 0 [−16.7,+16.7] | −2.3 [−9.5,+5.0] | 0 [0,0] | +10.0 [0,+25.0] |
| B1−B0 | +5.6 [0,+16.7] | 0 [−6.8,+6.8] | −5.6 [−18.8,0] | 0 [0,0] |
| B2−B1 | 0 [0,0] | 0 [−6.8,+6.8] | 0 [0,0] | 0 [0,0] |

除上文 p5ccv 的 SHARED 提升外,本表各单措施的 95% CI 均接触或跨过 0,故当前只能给出以下
**受限结论**,不能写成“已证明无效”:

- **A1 自一致**:SELECT 点估计上升,但方向、排除和 SHARED 均下降;没有证据证明 3× 调用成本带来净收益。
- **A6 soft-none**:没有保住 p5ccv 的 SHARED,也未把 DIRECTION 拉回 P5。相对 P5 头条,
  DIRECTION 84.1%→68.2%,配对差 −15.9 [−30.0,−4.3],**明确未过验收门**。这只证明当前 soft-none
  实现失败,不能据此断言硬覆盖不是 p5ccv 缺口的原因。
- **A5 assertion filter**:SELECT/SHARED 点估计提高而 DIRECTION 略降,是值得扩样本复核的候选,当前未 resolved。
- **A4 compiler model**:换 qwen3 后 SELECT/RO 点估计提高、DIR 略降、SHARED 不变。结论应为
  **“本次 A/B 未证明模型替换能修复编译错误”**,不能反推“编译错误不是弱模型伪影”。
- **A2 local decision set**:SHARED 45%→60%,但 CI 跨 0。现有 8 个 `decision_set` 没有
  `decision_set_favors` 临床金标,所以该臂主要测“缩小候选后是否仍答 none”,尚未完整检验
  “全局共性、局部可鉴别”。
- **B0/B1**:抽象键没有显示可确定的惩罚,预展开也没有恢复可确定增益。该探针没有复现生产缺陷;
  可能原因包括检索结果高度重叠、下游仍看到具体候选、指标不敏感。现有实验**不能区分这些机制**,
  也不能称为对“抽象键必然有害”的证伪。
- **B2**:总体指标与 B1 相同,但个别病例的方向判定有互相抵消的变化(DIRECTION delta CI ±6.8)。
  审计中层级 provenance 正确生成,如 elevated PTH 支持甲旁亢父族、排除肿瘤旁分泌父族;
  这证明结构输出存在,**不证明已降低父子误排除率**,因为当前 PARENT 基线已 100%、缺少阳性错误样本。

#### E1j.4 A3/A7/A8 的正确解释边界

**A3 LOO(seed7 单种子,无 CI)**:

| 配置 | SELECT@1 | DIRECTION | RULE-OUT | SHARED |
|---|---:|---:|---:|---:|
| P7 | 88% | 81% | 77% | 50% |
| −normalize | 77% | 77% | 77% | 50% |
| −gate | 77% | 77% | 77% | 50% |
| −veto | 77% | 81% | 77% | 60% |
| −entail | 77% | 72% | 77% | 50% |
| −route | 77% | 81% | 77% | 50% |

这些是单种子描述值。因为每个 LOO 臂会重新调用 LLM,变化同时包含“抽掉组件”和“重新采样调用”的影响,
不能把 1–2 例差异直接解释为组件边际贡献。需要多种子配对 LOO 才能归因。

**A7 threshold sweep**只运行了 `--disc-dry`,因此只有规则层输出,没有下游性能:
jaccard .5/.6/.7 的 USE=8/8/10、multi_support=3/4/2、pheno_common=4/4/3;
multi_support 阈值 ≥2/≥3 的 USE=8/12、触发数=5/1;per_cand 1/2/3 的 USE=10/8/9。
它证明阈值会改变编译结果,**不能据此声称下游指标对阈值不敏感**;下游 sweep 尚未做。

**A8(a)**:KG 与语料 `pheno_common` 原始一致率 40.9%、Cohen's κ=−0.06;KG common 18.2%,
语料 common 59.1%。这说明两路对“共性”的操作化严重不一致,不适合作为未经校准的硬共识门。
但**低 κ 不能证明两路“不独立”**;判断独立性和谁更准确需要人工金标或第三方校准集。

**A8(b)**:LLM 二次意见与数据集 role 一致 33/41(80%),产生 8 条待审分歧。它只是一份
**复核队列**,不能推出“约 20% 金标错误”,因为审计 LLM 本身也可能错;任何标签改动仍需临床人工裁决。

#### E1j.5 最终结论与状态

1. p5ccv 的 SHARED 增益是本轮唯一获得配对 cluster-bootstrap 支持的下游改善,但伴随显著的
   DIRECTION 点估计下降风险;它仍不是可直接投产的无回归配置。
2. A6 soft-none 明确未通过“DIRECTION 回到 P5 头条”验收门;A1/A2/A4/A5/B0/B1/B2
   在 9 个独立病例下均不足以定论,全部保持默认 OFF。
3. 下一步优先扩**独立病例数**,而不是仅增加 seed;随后重跑多种子配对 LOO、A5、A2 与真正的
   下游 threshold sweep。
4. B3 仍只保留生产默认-OFF 设计;现有 B0/B1 没有量化出可确定的检索键惩罚。

数据:`logs/talp_discrim_{p5seed,ccvseed,sc,sn,af,cm,lds,ab,ex,bh}*.json`、
`logs/talp_discrim_loo7_dv2_*.json`、`logs/talp_discrim_sw7_dv2_*_audit.json`、
`logs/talp_gold_audit.json`;工具:`scripts/talp_ci.py`(配对病例聚类 bootstrap)、
`scripts/talp_signal_corr.py`、`scripts/talp_gold_audit.py`。全部为评测/设计文档改动,生产默认 OFF。

### E1k. MedXpertQA Hard 扩病例 + 文献校准 + p5ccv×A5（2026-07-11）

#### E1k.1 数据扩展不是把题库答案直接当金标

从
`/home/wanghongyi/LLM-Structured-Data-main/som/MMLU/test/medxpertqar_hard_test.tsv`
的 100 题中先筛出 10 个诊断/病因型问题。LLM 只生成结构化草案；随后逐 claim 检索医学文献并重写
candidate/finding role。最终:

- 8 例进入文献校准扩展集，和原 9 例合并为 **17 个独立 case cluster**；
- `mxh042` 因没有患者 vignette、草案还虚构了“题干内 finding”而排除；
- `mxh098` 因题干只能支持“男童中枢性性早熟应做脑 MRI”，不能证明“已经存在 CNS 病灶”而排除；
- 8 例状态为 `literature_reviewed`，但 `human_clinical_signoff=false`。它们可用于内部扩样本 A/B，
  尚不能宣称为最终临床金标准。

主要校准来源包括 Merck Manual 的 epiglottitis、bacterial tracheitis、truncus arteriosus 条目，
GeneReviews 的 GSD-I 与 CBS deficiency 条目，RSNA 的儿童 malrotation 综述，以及 Wilderness
Medical Society 2024 heat-illness guideline。逐条 URL 已写入
`data/eval/talp_medxpert_expansion_cases.json` 的 `evidence_refs`。

生成链:

- `scripts/build_medxpert_talp_cases.py`：只产出 `draft`，禁止直接评分；
- `scripts/calibrate_medxpert_talp_cases.py`：显式修订 claim、写入引用并保留排除审计；
- `scripts/eval_talp_discrimination.py --extra-dataset ...`：默认数据集不变，显式追加扩展病例；
- `--stage-only`：在多臂复跑时跳过重复的 LLM-alone/plain-KB 回答调用，不改变目标 stage。

#### E1k.2 17-case、2-seed 的正确数字

每臂 17 个独立病例、2 个 seed，共 34 个 seed×case 观测；CI 仍以病例 ID 做 cluster bootstrap，
不是把 34 行当成独立病例。

- **P5**：SELECT@1 82.4% [64.7,97.1]；SELECT-valid 85.3% [67.6,100]；
  DIRECTION 76.8% [68.9,84.7]；RULE-OUT 76.2% [57.1,92.0]；
  SHARED 60.5% [38.9,80.6]；PARENT 100%。
- **p5ccv**：SELECT@1 82.4% [67.6,94.1]；SELECT-valid 82.4% [64.7,97.1]；
  DIRECTION 65.9% [55.4,76.2]；RULE-OUT 73.8% [52.5,91.7]；
  SHARED 71.1% [50.0,87.5]；PARENT 100%。
- **p5ccv+A5 assertion filter**：SELECT@1 82.4% [64.7,97.1]；
  SELECT-valid 82.4% [67.6,94.1]；DIRECTION 70.7% [60.0,81.2]；
  RULE-OUT 76.2% [57.5,91.3]；SHARED 73.7% [52.8,90.5]；PARENT 100%。

配对差值给出更直接的判断:

1. p5ccv 相对 P5：DIRECTION **−11.0** [−20.5,−2.6]，扩样本后已是明确回归；
   SHARED +10.5 [0,+23.7]，下界接触 0，按预设门仍为 unresolved。
2. p5ccv+A5 相对 P5：DIRECTION −6.1 [−15.6,+2.4]；SHARED +13.2 [0,+27.5]；
   两者都 unresolved。A5 缩小方向回归，但没有证明消除回归。
3. p5ccv+A5 相对 p5ccv：DIRECTION +4.9 [0,+10.7]；RULE-OUT +2.4
   [−5.9,+10.0]；SHARED +2.6 [−5.9,+11.1]。三个方向均有正点估计，但独立病例数仍不足。

#### E1k.3 域外分层与残余机制

P5 在原 9 例的 SELECT@1 为 100%、DIRECTION 81.8%；在新增 8 例分别只有 62.5%、71.1%。
这说明旧 9 例头条值对新疾病族的外推明显乐观，扩样本确实测到了新难度，而非仅重复旧题。

A5 的恢复主要发生在新增病例：p5ccv→p5ccv+A5 的新增病例 DIRECTION 从 63.2% 到 73.7%，
原 9 例则都为 68.2%。它能过滤部分“只共现、不构成断言”的 chunk，但不能解决所有 hard-none/
membership 过压。p5ccv 仍错误压掉 `weight loss`、`elevated alkaline phosphatase`、
`prior abdominal surgery`、`unilateral bloody nasal discharge`、`bilateral inferonasal lens
dislocation` 等有效方向证据；A5 只恢复其中一部分。

#### E1k.4 配置结论

**P5 仍是当前最稳的头条配置。** p5ccv 不应替代 P5；p5ccv+A5 是继续研究 corpus-membership
门控时更合理的实验基座，但保持默认 OFF。下一轮不是继续堆门，而是:

1. 由临床人员签字 8 个新增病例及原 A8 分歧标签；
2. 把 hard-none 改成带置信度的软权重，保留消费者恢复通道；
3. 对上述被误压的决定性 finding 做逐条“检索断言→membership→路由”故障定位；
4. 扩到至少 30–50 个独立病例后再决定是否提升组合臂。

数据:
`logs/talp_discrim_expanded_{p5,p5ccv,p5ccv_a5}_s{7,11}r0_dv2_*.json`。

#### E1k.5 新增 8 例低分的逐题 + 逐部件根因

按 §7/§9 范式对新增 8 例(P5 头条、两 seed)做拆解,完整逐题版见
[`TALP_STATUS_EXPLAINER.md`](TALP_STATUS_EXPLAINER.md) §13。要点:

- **首要原因是任务-数据集适配,不是算法退化。** mxh011/mxh014/mxh068 是"病原体归属"题,决定性证据是
  培养、vignette 不足以唯一推出菌种;TALP 的表型判别范式天然不适配"同一综合征下分菌种"。这 3 题独立
  压低 SELECT@1(62.5%)与 DIRECTION。应单列 `task=organism_attribution`,不计入表型判别缺陷。
- **第二原因是老问题:大模型共性陷阱。** mxh036(高甘油三酯→误判 LPL)、mxh046(marfanoid 体型→误判
  Marfan)、mxh055(共性高热→过度归金标)、mxh068(吸气性喘鸣→误判会厌炎)四题的 DIRECTION 失败都源
  于"把共性/干扰共享表现错误定向",与旧集 §9.4 同源。
- **检索/数据缺失退居次要:** 失败方向判断几乎都在"证据已在标注/vignette 内"的条目上,属推理非召回;
  仅 mxh036 的 decisive`空腹低血糖`属题干信息缺口。
- **结构清晰、互斥性强的疾病族依旧稳:** mxh045(肠旋转不良)、mxh075(永存动脉干)方向近乎全对,
  说明低分集中在"病原体归属 + 高共性综合征"两类,而非"新数据一律更难"。

逐部件矩阵(SELECT@1 主导失效部件):mxh011 大模型 / mxh014 任务+大模型 / mxh036 大模型+题干数据 /
mxh045 大模型(轻微)/ mxh046 大模型 / mxh055 大模型 / mxh068 任务+大模型 / mxh075 无。

### E1l. 类型化证据修复实验层（2026-07-11）

本轮新增内容全部是**评测/可复用知识适配器，默认 OFF**，未接线生产 controller/config：

- v2 fixture：`talp_medxpert_expansion_cases_v2.json` 使用可变长度、
  candidate-conditioned `candidate_effects[]`，纠正 mxh014 慢性病程、mxh036 乳糜样血浆、
  mxh045 非特异梗阻的强迫方向；3 个病原体题标为 `organism_attribution`。只读审计为
  8 case、0 error；均未临床签字，只能进入 experimental 分层。
- 评分：新增 `--select-gold-pool`、`--judge-model`、`--candidate-order`；非 legacy SELECT@1
  必须同时满足 match 与 clinical validity，并同时输出 finding-weighted 与 case-normalized 指标。
- 多本体：`--concept-router legacy|hpo|multi` 记录 HPO/LOINC/SNOMED/RxNorm/RadLex/时间路由、
  coverage 与 abstention；FHIR 只作为事件结构。SNOMED typed slice 由脚本自动生成，不覆盖旧资产。
- 复合 finding：`--compound-mode legacy|atomic|syndrome|dual`。syndrome 必须有 ontology/corpus
  provenance 与 entailment，否则 abstain；4 个正负 probe 的 atom 与 syndrome precision 均为 100%
  （仅组件 probe，不是端到端临床效能证明）。
- 入口门：`--entry-gate legacy|all_findings|typed_uncertain` 输出每例 decisive 漏入清单，legacy
  行为不变。
- 病原体：`--pathogen-source none|snomed|open_kb|corpus|fused`。10 个独立行为 probe 中，fused
  的 culture resolution 5/5、无培养 abstain 5/5、false attribution 0；none 臂 culture resolution
  0/5。该 probe 只证明“培养确认边 + 安全 abstain”机制，不把语料 mention 冒充 LR。

有序多 seed 梯度由 `scripts/run_talp_typed_ab_ladder.py` 执行；回归门由
`scripts/talp_regression_gate.py` 检查 DIRECTION、RULE-OUT 与 decisive suppression。17 case
仍只作探索；任何候选默认提升继续要求临床签字及 30–50 个独立病例。

#### E1l.1 三 seed 梯度结果与验收

在 17 case、seed 7/11/13 上，fixture-v2 LLM-alone 基线为 SELECT@1 25.5%、
SELECT-valid 66.7%、DIRECTION 80.7%、RULE-OUT 88.9%、SHARED 36.4%。本轮模型调用的
SELECT 绝对值明显低于 §E1k 的旧运行，因此只解释本轮同批配对差，不跨批比较绝对头条。

**表 E1l-A：冻结 P5 家族（17 case × 2 seed；同一旧 fixture/评分）**

| 实验臂 | SELECT@1 | SELECT-valid | DIRECTION | RULE-OUT | SHARED | 相对 P5 裁决 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| **P5 冻结头条** | **82.4** [64.7,97.1] | **85.3** [67.6,100] | **76.8** [68.9,84.8] | **76.2** [57.1,92.3] | 60.5 [38.9,80.6] | 当前头条 |
| p5ccv | 82.4 [67.6,94.1] | 82.4 [64.7,97.1] | 65.9 [55.7,76.1] | 73.8 [52.5,91.7] | 71.1 [52.4,87.5] | DIR −11.0 [−20.3,−2.5]，明确回归 |
| p5ccv+A5 | 82.4 [64.7,97.1] | 82.4 [67.6,94.1] | 70.7 [60.0,81.2] | 76.2 [57.1,91.7] | **73.7** [52.8,91.2] | DIR −6.1 [−15.8,+2.3]；SHARED +13.2 [0,+27.5]，均未解决 |

**表 E1l-B：typed 单措施梯度（17 case × 3 seed；fixture-v2 LLM-alone 为本表基线）**

| 实验臂 | SELECT@1 | SELECT-valid | DIRECTION | RULE-OUT | SHARED | 相对 fixture-v2 / 验收 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| **fixture-v2 基线** | 25.5 | 66.7 | 80.7 | **88.9** | 36.4 | 本表配对基线；非 P5 |
| scoring-aligned | 16.7¹ | 66.7¹ | 82.5 | **88.9** | 36.4 | SELECT 分母/定义改变，不作头条比较 |
| multi-ontology（无泄漏） | **43.1** | 68.6 | 77.2 | 85.7 | 34.8 | SELECT +17.6 [0,+39.2]；DIR/RO 负点估计；不过门 |
| atomic | 35.3 | 56.9 | **82.5** | 87.3 | 36.4 | 各 delta CI 含 0；不过门 |
| syndrome | 35.3 | 62.7 | **82.5** | 87.3 | 28.8 | resolved=0 的无操作臂；显著差视为模型噪声 |
| dual | 31.4 | 54.9 | **82.5** | 84.1 | 31.8 | RO/SHARED 负点估计；不过门 |
| pathogen-corpus | 41.2 | 58.8 | **82.5** | **88.9** | **43.9** | SELECT +15.7 [5.9,27.5]；valid 未升，仅任务分层候选 |
| pathogen-fused² | 31.4 | 64.7 | 81.6 | 82.5 | 42.4 | 当时无新增 open-KB 边，不能解释为融合增益 |
| pathogen-openkb-v4 | 31.4 | 62.7 | 78.9 | 85.7 | 34.8 | SELECT +5.9 [−2.0,15.7]；DIR −1.8、RO −3.2；零回归门失败 |

¹ `typed_effect` 只覆盖有 candidate-effect matrix 的 v2 子集，24 个 seed×case 行；其 SELECT
不能和 51 行 legacy 绝对比例直接比较。  
² 该次 fused 运行只有实验 corpus edge；SNOMED organism endpoint 与开放病原体 KB 尚未建成，
因此与 corpus 臂的差主要反映远端模型非确定性。

**表 E1l-C：typed entry-gate（17 case × 3 seed；同配置 p5ccv 配对）**

| 入口臂 | SELECT@1 | SELECT-valid | DIRECTION | RULE-OUT | SHARED | 配对裁决 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| legacy-entry | 68.6 [47.1,88.2] | 80.4 [62.7,94.1] | **74.6** [61.9,85.8] | **81.0** [63.0,94.7] | 66.7 [44.4,85.2] | 对照 |
| typed-uncertain | **78.4** [60.8,94.1] | **86.3** [70.6,100] | 64.9 [54.2,76.5] | 76.2 [58.3,90.3] | **86.4** [71.8,97.5] | SHARED +19.7 [4.3,40.7]；DIR −9.6、RO −4.8；回归门失败 |

- atomic 相对 v2：SELECT +9.8、DIR +1.8、RO −1.6、SHARED 0 点，所有 CI 均含 0。
- syndrome：SELECT +9.8 [3.9,17.6]，但 SHARED −7.6 [−15.9,−1.4]；实际端到端病例
  `syndrome_resolved=0`，提示这是**无操作臂暴露的远端模型非确定性/假阳性**，不能归因为
  syndrome mapping。它同时证明病例聚类 bootstrap 不能替代受控的模型采样配对。
- dual：DIR +1.8，但 RO −4.8、SHARED −4.5；均未越统计门，且未过零容忍回归门。
- multi-ontology（修复 SELECT 只可见 `in_vignette` typed context 后）：SELECT 43.1%
  （+17.6 [0,39.2]，unresolved），DIR −3.5、RO −3.2、SHARED −1.5；概念 ID 仅命中
  2/81（2.5%），不能提升。一次把 additional gold typed findings 误传给 SELECT 的试跑已判为
  gold leakage、从汇总中排除，并增加防泄漏单测。
- pathogen-corpus：SELECT +15.7 [5.9,27.5]，DIR +1.8、RO 0，严格点估计回归门通过；
  但 SELECT-valid −7.8 且 CI 跨 0，所以只保留为任务分层候选，不组成生产组合臂。
- pathogen-openkb-v4（20,935 条真实开放边）：SELECT +5.9 [−2.0,15.7]、valid −3.9、
  DIR −1.8 [−7.6,3.1]、RO −3.2 [−7.9,0]、SHARED −1.5，均 unresolved；按零容忍
  点估计门因 DIR/RO 下降而失败。开放边覆盖增加没有转化为端到端胜出。
- typed-entry（同配置 p5ccv legacy gate 对照）：SELECT 68.6→78.4，SHARED
  66.7→86.4（+19.7 [4.3,40.7]），但 DIR 74.6→64.9、RO 81.0→76.2；严格回归门失败。

结论：没有同时满足“统计互补 + 保住 DIRECTION/RULE-OUT”的措施，因此按预注册顺序**不运行
组合臂/LOO**。P5 冻结头条不变；全部新开关继续默认 OFF。

#### E1l.2 病原体细粒度知识覆盖审计与开放 KB 补充

对 10 个病原体—综合征 probe 的**现有项目资产**做了逐源审计
（`logs/pathogen_kb_coverage_audit.json`）：

| 现有源 | 结构化 causative-agent 能力 | 10 对 probe 结果 | 裁决 |
| --- | --- | --- | --- |
| legacy SNOMED JSON | 有 18,873 条 `causative_agent` relation，但 organism 端点 18,873/18,873 均被旧 RF2 tag 过滤 | 双端可解析 0 | **不支持** |
| PrimeKG | typed pathogen row=0 | 命中的菌名只出现在 drug/protein/phenotype/disease 等非病原体身份行 | **不支持因果归属** |
| DiagRL / phenotype index | disease→phenotype | 无 organism relation | **不支持** |
| Layer-A HPO LR / Layer-B | phenotype LR / disease anchor | 10/10 均无 LR、无 grounded directional signal | **不支持** |
| CPG + case report | 非结构化文本 | 10/10 有 mention，但 0/10 有可直接采用的方向边 | 只可召回，**不得把 mention 变 LR** |

因此，原知识库不能可靠完成“同一感染综合征下区分菌种”。本轮新增了不覆盖旧资产的自动构建链：

1. 获许可 RF2 → 独立 `snomed_typed_rf2_eval.json`，保留 organism/specimen/observable/
   procedure/product 等 tag；
2. PathoPhenoDB v1.2.1（CC-BY-4.0，Zenodo DOI `10.5281/zenodo.2592933`）→
   3,957 条可解析 `RO:0002556 has_pathogen` 边（2,814 manual assertion，1,143
   text-mined）；
3. NCBI Taxonomy taxdump → 1,515 个目标 taxon、9,071 个别名的自动身份桥；
4. SNOMED + PathoPhenoDB 融合后得到 20,935 条 provenance-bearing 实验边。

真实开放 KB probe 的结果是：培养题 2/5 可由“培养命名菌种 + causative-agent 边”解析，
无培养题 abstain 5/5，false attribution=0。缺失的 3/5（肺炎链球菌会厌炎、金葡菌气管炎、
表皮葡萄球菌人工瓣膜心内膜炎）说明开放图谱仍不完整；文献校准 corpus assertion probe 可达
5/5，但它只能作为带引用的实验补边，不能伪装成总体流行病学 LR。

参数化入口保持：
`--pathogen-source none|snomed|open_kb|corpus|fused` 与可重复
`--pathogen-open-kb PATH`；默认 `none`，所有缓存使用新路径，不覆盖旧实验结果或生产配置。
真实开放索引三 seed A/B 的 SELECT@1 31.4%、valid 62.7%、DIR 78.9%、RO 85.7%、
SHARED 34.8%；相对 fixture-v2 无一主要 delta 解决，且零回归门因 DIR/RO 负点估计失败。
KG-Microbe 可作为后续补源，但其 disease edge 多为 `associated_with` 且完整构建资源需求极高，
不能直接当 causative-agent 或临床先验；PHI-base 同样只限实际临床疾病覆盖，不把毒力基因关系当诊断 LR。

### E1m. P5 + typed evidence 同批基线（2026-07-11）

#### E1m.1 为什么必须重建基线

§E1l 的 typed 单措施梯度主要使用 LLM-only；typed-entry 则以 p5ccv 为对照。它们适合做组件
筛选，但**不能回答新措施叠加到当前最优 P5 后是否仍增益**。本节将所有措施统一改为：

- 原 9 例 + MedXpert v2 8 例，共 17 case；
- `--disc-stage=p5 --stage-only`；
- seed 7/11/13，同题配对、case-cluster bootstrap；
- 同一 P5 compiler input/config 使用相同 fingerprinted compiled-block cache，避免每臂重新
  编译导致的远端模型噪声；改变 finding 文本或入口的 atomic/syndrome/dual/typed-entry 使用
  独立 cache；
- 所有 tag 为 `p5typed_*`，不读取或覆盖 §E1k/§E1l 的结果文件。

P5+v2 新基线为 SELECT@1 80.4%、SELECT-valid 86.3%、DIRECTION 79.8%、
RULE-OUT 82.5%、SHARED 56.1%。它与旧 P5 头条（82.4/85.3/76.8/76.2/60.5）
不能直接作因果比较：v2 修订了 finding/gold，DIRECTION/SHARED 分母改变，seed 数从 2 变 3，
且本轮固定 compiler blocks。它的作用是成为后续 typed 研究的**同批 P5 基线**。

#### E1m.2 完整性能表

**17 case × 3 seed；除 scoring-aligned 外均为 51 个 seed×case SELECT 行。**

| P5 实验臂 | SELECT@1 | SELECT-valid | DIRECTION | RULE-OUT | SHARED | 相对 P5+v2 / 裁决 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| **P5+v2 baseline** | **80.4** [62.7,96.1] | 86.3 [70.6,100] | 79.8 [70.7,88.9] | **82.5** [64.8,95.8] | 56.1 [35.0,74.4] | 新治理基线 |
| scoring-aligned¹ | 54.2 [20.0,87.5] | 75.0 [50.0,100] | 81.6 [72.5,90.8] | **82.5** [64.7,96.2] | **60.6** [38.6,79.5] | SELECT 定义/分母不同；decisive suppression +13.7，门失败 |
| multi-ontology | 78.4 [58.8,94.1] | 82.4 [64.7,96.1] | 83.3 [74.3,91.7] | 81.0 [62.5,94.4] | 54.5 [34.8,72.5] | DIR +3.5 [0,7.8]；RO −1.6、suppression +2.0，失败 |
| atomic | 78.4 [60.8,94.1] | 82.4 [64.7,96.1] | 81.6 [73.1,90.6] | 79.4 [60.0,94.4] | 54.5 [33.3,73.9] | DIR +1.8；RO −3.2，失败 |
| syndrome | 78.4 [60.8,94.1] | 80.4 [62.7,96.1] | 79.8 [71.2,88.6] | 81.0 [63.2,94.7] | 54.5 [33.3,72.7] | 无方向增益；RO −1.6 |
| dual | **80.4** [62.7,94.1] | **90.2** [76.5,100] | 78.9 [66.7,90.0] | 77.8 [59.7,92.1] | 51.5 [29.6,72.2] | valid +3.9；DIR/RO/SHARED 均下降 |
| typed-entry | 72.5 [52.9,90.2] | 80.4 [62.7,94.1] | 83.3 [75.2,91.7] | 81.0 [62.1,94.7] | 53.0 [28.6,74.6] | DIR +3.5；SELECT −7.8、RO −1.6，失败 |
| pathogen-corpus | 78.4 [58.8,94.1] | 80.4 [62.7,94.1] | 78.9 [70.8,87.5] | 79.4 [61.1,93.3] | 53.0 [31.7,72.7] | DIR/RO/SHARED 均下降 |
| pathogen-fused | 78.4 [58.8,96.1] | 84.3 [66.7,98.0] | **84.2** [74.7,93.3] | 77.8 [59.5,92.4] | **57.6** [38.3,75.9] | DIR +4.4 [0,9.5]；RO −4.8、suppression +2.0，失败 |
| pathogen-openkb | **80.4** [60.8,96.1] | 80.4 [60.8,96.1] | 80.7 [72.5,89.2] | 77.8 [60.3,92.6] | 53.0 [31.7,73.3] | DIR +0.9；RO −4.8，失败 |

¹ scoring-aligned 的 SELECT 只覆盖 typed-effect 子集（24 行），不能与 baseline 的 51 行
SELECT 比例作头条比较。

#### E1m.3 裁决

1. **没有 P5-based 新臂通过零回归门，也没有臂全面优于 P5+v2。**
2. pathogen-fused 的 DIRECTION 点估计最高（84.2%，+4.4 点），但其 95% CI 下界为 0，
   RULE-OUT 同时下降 4.8 点；不能提升。
3. multi-ontology 与 typed-entry 均出现约 +3.5 点 DIR，但同时损失 RO；typed-entry 在 P5
   上不再复现 p5ccv 对照下的 SHARED 大涨，说明旧结论依赖较弱基线。
4. scoring-aligned 是评分定义实验，不是能力增益；即使 DIR/RO 点估计不降，decisive
   suppression 从 19.6% 升至 33.3%，仍失败。
5. 因此 §E1l 的 LLM-only/p5ccv 结果降级为**预筛选证据**；任何生产候选必须以后续
   P5+v2 同批梯度为准。P5 仍是冻结头条。

#### E1m.4 P5 外部资产回退保护

P5 依赖的 12 个外部输入已写入
`data/eval/p5_external_asset_manifest.json`（size + SHA-256）：
HPO `phenotype.hpoa`/`hp.obo`、Guideline common/rare、PrimeKG `kg.csv`、
三份 finding normalizer 资产、CPG 与 case-report index config/metadata。

`scripts/run_talp_typed_ab_ladder.py --baseline-family=p5` 在全梯度开始前及**每个臂结束后**
调用 `scripts/audit_p5_asset_integrity.py --verify`；任一字节变化立即停止。10 个臂均返回
asset integrity=0，最终复核为 12/12 unchanged。新 typed SNOMED、PathoPhenoDB、Taxonomy、
P5 block cache 和实验日志全部位于新路径；原 P5 外部数据既未覆盖，也未作为输出目标，可直接回退。

可复现数据：
`logs/talp_p5_typed_ab_manifest.json`、
`logs/talp_p5_typed_ladder_summary.json`、
`logs/talp_discrim_p5typed_*_s{7,11,13}r0_dv2_p5.json`。

### E1n. CCEG pilot：G0/G1 同批结果与质量门状态（2026-07-12）

CCEG pilot 已完成 schema、无标签 scope、CPG 抽取和 L0/L1：259 条 raw claim 全部通过
结构/来源权限门，96 条通过独立蕴含门。100 条临床审核包覆盖全部 18 条 direction 和
3 条 common claim，但尚未由两名真实临床审核者签署，因此 validated/oracle index 与
临床 lane 的 G2–G6 被硬阻断。

在阻断前可合法运行的 G0/G1 结果为：

- G0（冻结 P5+v2 同批复现）：SELECT@1 84.3%、valid 82.4%、DIR 79.8%、RO 79.4%、
  SHARED 59.1%。
- G1（仅增强 CPG query/rerank，保留原 case-report 通道）：SELECT@1 78.4%、
  valid 80.4%、DIR 82.5%、RO 76.2%、SHARED 62.1%。
- G1−G0 配对 delta 分别为 −5.9、−2.0、+2.6、−3.2、+3.0 个百分点；五项 95% CI
  均跨 0。
- G1 因 RO/valid 点估计下降且 decisive suppression 增加而未通过零回归门。

E1n 的结论只到此为止：raw RAG 增强未胜出；临床 GraphRAG、validated direct claim 与
oracle 上限尚无端到端结果。后续 research-only 模拟见 E1o。数据见
`data/cceg/pilot/p5kg_g01_summary.json`、
`logs/talp_p5kg_g01_manifest.json` 与
`logs/talp_discrim_p5kg_g{0,1}_s{7,11,13}r0_dv2_p5.json`。

### E1o. CCEG v2 research-only 跨 Chunk 梯度（2026-07-12）

该梯度不改变 E1n 的临床质量门：它使用双 LLM + 独立 adjudicator 的
`synthetic_dual_llm` 状态，只进入独立 research consumer/tag/manifest，默认 OFF。

资产漏斗为：401 条 unary scope query、2,005 个 top-5 chunk 作业、170 条 L0 claim、
118 条 L1 grounded、38 条 synthetic-review accepted（34 support、4 against）。
双审在 118 条中分歧 96 条。旧 pair claim 的 96 条 L1 grounded 中只有 1 条属于
G2PR 许可的 direction/common/test 类型，且被模拟审核拒绝，因此有效 pair 输入为 0。
一次未过滤类型的试跑接入了 11 条 membership 和 1 条 phenotype assertion，已判无效并排除。
在“同 article、同 finding-state、一正一负”约束下没有任何可组合候选，
`derived_contrast=0`；冻结二部图只有 38 条 unary edge、20 个 candidate node 和
23 个 finding-state node。

三 seed 结果及 G0 配对 delta：

- G2UR：SELECT@1 80.4%（−3.9 [−17.6,+7.8]），valid 86.3%
  （+3.9 [−3.9,+11.8]），DIR 86.0%（+6.1 [0,+13.7]），RO 82.5%
  （+3.2 [0,+10.0]），SHARED 60.6%（+1.5 [−6.1,+14.0]）。
- G2PR/G2CR 因有效输入为空而跳过；G3R/G4R 因没有 derived claim 跳过。旧 G2PR/G2CR
  日志保留作编排审计，但不进入能力比较。

唯一有效端到端臂 G2UR 因 decisive suppression 增加 3.9 点且关键增益 unresolved
而未过严格门。结论是 G2UR 有方向性信号但不能晋级，P5 头条不变，当前 pilot 尚未形成可测试的
GraphRAG 拓扑增益。

### E1p. P5/G2UR 生产接线与 17 题两轮部分流程（2026-07-12）

P5 headline 与 G2UR 已作为 `off|p5_headline|g2ur` 显式 production profile 接入
controller。测试固定复用 `eval_branch_creation_medbullets.py` 的
`recall_hints_gap`，轮次 1 后强制展开全部 L1，轮次 2 在 EvidenceAnnotator 返回后截断；
34/34 条 trace 均未调用 AnswerMapper。

真实运行结果：

- 两 profile 各完成 17/17，错误和最终超时均为 0；L1 recall 与全 L1 展开率均为
  100%，EvidenceAnnotator 两轮 coverage 均为 100%。
- P5 profile 在 17 题中产生 66 次规则命中及 66 个 provenance 命中；G2UR 两项均为
  0。后者说明当前 38 条 unary 研究边无法匹配生产树的候选标签与 vignette atomic
  finding，并不构成生产证据贡献。
- L2 leaf 总数为 P5 311、G2UR 322；两臂独立调用非确定性分支模型，且 profile 在
  L1 创建后才注入，因此该差值不能归因于 profile。
- 本实验故意不运行答案映射，也不产生诊断准确率或 P5/G2UR 胜负裁决。它证明的是生产
  接线、两轮解释、强制展开、provenance 与截断边界；不能替代 E1o 的能力门结论。

运行中发现 LR fuzzy lookup 对每个 finding 重扫完整疾病索引，可令单题超过 15 分钟；
已增加保持匹配规则不变的 disease-candidate cache 与 trigram prefilter，失败项 resume
后完成。最终产物见
`logs/partial_flow_talp17/talp17_p5_g2ur_partial_20260712/{manifest,summary}.json`
及其 `traces/` 目录，run fingerprint 为
`d8c415140d919fe449eb125b1bd91b7070e4fa3e8cfda17f1f16ee1e30737e14`。

### E1q. 共享树轻量 TALP 组合管线（2026-07-12）

为排除 E1p 的完整 controller 主循环及双臂独立建树干扰，新增
`scripts/eval_branch_talp_composed.py` 与
`src/agentclinic_tree_dx/composed_pipeline.py`。每题仅执行一次
`recall_hints_gap` 的 root/L1 创建和全 L1→L2 展开，随后冻结树并深拷贝给 P5/G2UR；
下游只保留“已观察静态事实 Top-2 选择→EvidenceAnnotator→gated ordinal update→
parent posterior 汇总”。Safety、TemporaryLeafPlanner、action execution、state
revision、ExpansionGate、termination 和 AnswerMapper 均未调用。

离线 P5/G2UR 语义来自 P5KG ladder 已冻结的 seed-7 P5 compiler audit：
P5 使用 G0/P5 输出，G2UR 使用 research unary 输出；按 observed fact 对齐后重新
`_routed_blocks`，而不是退化成 production `DiscriminationRuntime`。34 条 profile
trace 共享 17 个 tree hash，最终 L2 概率质量均为 1，AnswerMapper 调用为 0。

17 题真实配对结果：

- 两臂 L2 strict gold branch 存在率相同，均为 12/17（70.6%）；不存在的 5 题不参与
  “存在时排名”，但在 Top-k/MRR 分母中按未命中计。
- 初始 gold probability@1 均为 1/17（5.9%）。P5 在第 1/2 条证据后为
  5/17（29.4%）→6/17（35.3%）；G2UR 为 3/17（17.6%）→3/17（17.6%）。
- 最终 P5 MRR=0.426、存在时平均/中位排名=4.58/1.5；G2UR
  MRR=0.328、平均/中位排名=4.92/2.5。两者 Top-3/Top-5 都为 8/17（47.1%）。
- 12 个双方均存在 gold branch 的病例中，G2UR 相对 P5 为 1 个排名改善、3 个变差、
  8 个持平，平均 `rank(G2UR)-rank(P5)=+0.33`；没有优于 P5 的描述性信号。
- 选中证据对应的 compiler evidence hit 为 P5 211、G2UR 7；但 G2UR 冻结 audit
  `n_use=0`，说明少量 retrieved row 没有形成可注入的 USE contrast。该结果再次把
  blocker 定位到 unary evidence→可用对比规则，而不是 controller 接线。
- observed-fact 限制后的 SELECT@1/SELECT@2/valid 两臂均为
  23.5%/35.3%/47.1%，显著低于原离线“可建议额外检查”口径；两者不能直接横比。
  selected-subset 的 SHARED/RULE-OUT 样本很小且表现差，只作为错误审计，不作总体
  TALP 能力替代估计；完整原口径指标仍以 E1o 的 ladder 输出为准。

因此，去除主程序干扰并固定树后，P5 的 posterior 排名收益仍强于 G2UR；当前 G2UR
不能仅凭离线 DIRECTION/RO 的点估计提升晋级。产物见
`logs/branch_talp_composed/talp17_shared_tree_p5_g2ur/`，run fingerprint 为
`07d64b8fa5e0813feee3aed029d7ddbb2254b26dfb562b95cee4f976c48bd84f`。

### E1r. L1 Evidence-BFS 双轨实验（2026-07-13）

新实验完全冻结 E1q 的 `recall_hints_gap` L1 树，只沿 observed-fact 队列更新全部
L1；不运行 L2、controller、动作、终止或 AnswerMapper。实现包含 immutable
case/fact/compiler master、P5 单目标回退、稀疏 0–3 rule-in/rule-out、专用
rule-out selector、对称 log-score、B0–B6 和 branch-proposal。四分片合并 934 条
有效记录、0 错误；Track B 为 17 题，Track A 因 `mxh014` 只有一个唯一 L1 而为 16 题。

最强结果是 B1 `p5_single_direct`，不是预注册主臂 B2：

- P5/B1 的 probability@1、Top-3、MRR 为 82.4%、100%、0.892，B0 legacy 为
  52.9%、76.5%、0.674；B1−B0 的 probability@1 `+29.4` 点
  `[+11.8,+52.9]`、MRR `+0.219` `[+0.083,+0.375]`、平均 rank 改善
  `0.882` `[0.353,1.471]`，三项均 resolved。
- G2UR/B1 为 64.7%、100%、0.804；相对 G2UR/B0 的 probability@1 `+17.6`
  点未 resolved，但 MRR `+0.170` `[+0.018,+0.337]` 与平均 rank 改善
  `0.824` `[0.235,1.471]` resolved。G2UR/B1 只有 15 个 compiler hit，P5/B1
  为 352，因此不归因于 G2UR 知识资产。
- P5/B2 退至 52.9%/94.1%/0.718；相对 B1 的 probability@1 `−29.4` 点
  `[−52.9,−11.8]`、MRR `−0.175` `[−0.329,−0.037]`。P5/B3 与 B2
  头条值相同。G2UR/B2/B3 也低于其 B1。

Track A 解释了 Top-K 回归：P5/B2 的 rule-in target@3 虽升到 70.8%，target@1
只有 58.3%，且显式 shared 上只有 1/16 次两个 consumer 都正确 `none`；
G2UR/B2 为 0/16。所有 abstaining selector 在显式 depleted pool 上均 100%
false-select，说明 schema 支持 `none` 并没有转化为实际 abstention。

专用 rule-out selector 在 12 个有 observed cross-L1 rule-out 的病例上，P5/G2UR
RO-SELECT-valid 分别为 7/12 和 8/12，但固定预算均 displacement 10 次，其中
5/3 次挤掉有效 global 事实；最终没有改善 P5 L1 排名。该部件只保留 feasibility
signal。B2/B3、branch-proposal 均未过晋级门，生产 controller 不变。

研究裁决是把 B1 作为下一轮候选锚点：优先修复 shared/depleted abstention，不继续扩大
Top-K。详细算法、消融和边界见 `TALP_L1_EVIDENCE_BFS_ALGORITHM.md`；合并结果见
`logs/l1_evidence_bfs/formal_l1_bfs_v1_merged/summary.json`，run fingerprint
`49f5814328d584117b4f0ef6bf3a00370292cb895e37139acb82f0e6a51447d2`。

### E1s. Evidence-BFS 自适应停止前缀实验（2026-07-13）

以 P5/B1 为冻结锚点生成 17 个病例的完整 F8 轨迹，再对 F2/F4/F6/F8、gold-only
oracle、确定性 saturation（S1）、saturation + 受限 challenge advisor（S2）和
LLM-only 负对照（S3）做同轨迹 prefix replay。运行时 `StopSnapshot/Decision`
不含 gold；oracle 仅用于评测上限。

- F2 为 gold-rank@1 70.6%、Top-3 94.1%、MRR 0.809；
- F4 为 82.4%、100%、0.892，仍是最佳固定预算；
- F6 为 76.5%、100%、0.863；
- F8 为 64.7%、100%、0.824，并有 3/17 overthinking-to-error；
- oracle 平均只需 2.65 facts、p90 4 facts，即达 82.4%、100%、0.912。

该差距证明病例级自适应预算存在 headroom，但当前停止信号无效：S1 平均 7.88 facts，
S2/S3 均为 8 facts，三者 gold-rank@1/MRR 都为 64.7%/0.824。探索性 LOCO 的
S1 平均 7 facts但仍只有 64.7%/0.814；S2 仍运行到 F8。S1/S2 均未通过相对 F4
的质量非回归和 facts 减少 20% 门。

裁决：F4 保持默认；S1/S2 只保留 shadow/replay，不能解释为已获得 agentic
诊断停止能力。17 题已经参与开发，独立验证状态为 `not_evaluated`。结果见
`logs/l1_bfs_adaptive_stop/talp17_adaptive_stop_v1/summary.json`。

### E1t. 自适应失败归因、S5 与 F4 重复性（2026-07-13）

逐 cycle 审计显示 S1/S2 不是“偶尔错停”，而是几乎没有停止机会：69 个 snapshot
中 `effective_updates <= 0` 及全部 saturation 合取各只通过 2 个；S1 因而有
16/17 运行到 F8。S2 advisor 的 52 次调用全部返回 challenge，17/17 运行到 F8。
同时 F4→F8 的 gold top-1 变化为获得 0、丢失 3，说明该 advisor 只识别“还能找
到证据”，不能识别“继续处理是否有净收益”。

新 S5 `EvidenceQuorumF4Policy` 不再寻找静态饱和点：只有 F2 的两个事实都支持
同一个新 leader、均不 rule-out 该 leader 且 margin ≥ `log(1.5)` 才早停，其余
病例硬停 F4。它在 5/17 个病例 F2 退出，平均 facts 3.41；gold-rank@1/Top-3/MRR
保持 F4 的 82.4%/100%/0.892。病例级 bootstrap 的平均 facts saved 为 0.588，
95% CI `[0.235, 1.059]`。但 14.7% 节省未达到 20% 门，LOCO 又出现 Top-3 回退，
故 S5 仅替代 S1/S2 成为首选 shadow 候选，仍不替代 F4。

重复性审计区分 direct B1 fixed-4 与 adaptive F8-prefix F4。两个 direct B1
空缓存、temperature=0 运行均为 70.6% gold-rank@1，MRR 为 0.828/0.819；但两个
严格 full-horizon 运行的 F4 前缀仅为 58.8%/52.9%，Top-3 为 100%/94.1%，MRR
为 0.755/0.721。后两次的 leader、gold-rank 一致率均为 88.2%，证据序列完全
一致率为 82.4%。因此 direct B1 不能被当作严格 F4 prefix 重跑，原单次 82.4%
也不再是可信绝对 headline。

S5 在两个 direct B1 轨迹上平均 3.41 facts，在两个严格 full-horizon 轨迹上平均
3.53 facts，并在四次重跑中保持各自 F4 的逐病例 gold rank 完全不变。该结果支持
“S5 是稳定的成本削减 shadow 候选”，但同一 17 题仍不能提供独立泛化保证。后续
headline 必须报告协议类型、temperature、缓存隔离和重复运行分布。比较产物为
`logs/l1_evidence_bfs/f4_rerun_comparison.json`。

### E1u. S5 在线自适应截断测试（2026-07-13）

新增在线 `S5` arm 后，以同一 temperature=0、空缓存前缀配对执行 B1/F4 与 S5。
S5 有 6/17 题在 F2 实际终止，其余 11 题到 F4；平均 facts 为 3.294，相对 F4
节省 17.6%。病例级 bootstrap 的 facts saved 为 0.706，95% CI
`[0.235, 1.176]`。

S5 与配对 F4 的 gold-rank@1、Top-3、MRR 完全相同，分别为 70.6%、94.1%、
0.819，且 17/17 的最终 gold rank 一致。这证明 S5 的节省在真实控制路径成立，
不是 prefix replay 的统计假象；但仍未达到 20% 成本门，也没有新病例独立验证，
故继续保持 shadow。产物见 `logs/l1_evidence_bfs/s5_online_t0_v1/`。

### E1v. F4/F6/F8 九次同指纹重复性核验（2026-07-13）

此前两个 F8-prefix F4 的 58.8%/52.9% 与 standalone F4 的 70.6% 差异不足以
判定协议优劣。现补齐 9 条 `temperature=0`、空缓存、相同 run fingerprint 的
完整 F8 轨迹，并从每条轨迹配对回放 F4/F6/F8。统计以病例为外层 cluster、运行重复
为内层，153 个观察不按独立病例处理。

- F4 平均 gold-rank@1 为 64.7%，运行间 SD 7.8 点，范围 52.9%–76.5%，
  MRR 0.788；
- F6 同为 64.7%，SD 7.2 点，MRR 0.801；
- F8 为 71.9%，SD 6.4 点，范围 64.7%–82.4%，MRR 0.837。

F6−F4 的 @1 差为 0，95% CI `[-16.3,+13.1]` 点，11 次纠正和 11 次破坏抵消。
F8−F4 的 @1 差为 `+7.2` 点，95% CI `[-9.2,+24.2]`；MRR 差
`+0.049`，95% CI `[-0.039,+0.142]`。F8 共纠正 19 个病例×运行观察、破坏
8 个，说明存在正向趋势，但病例聚类 CI 仍跨 0，不能宣称严格优于 F4。

预算效应高度病例化：`mxh036` 9/9 被 F8 纠正，`mb66_peliosis` 5/9 被纠正且
其余 4/9 保持正确；相反 `mb11_pancoast` 7/9 被 F8 从正确变为错误。
`mb65_cml`、`mxh045` 在 9/9 次中均未被更高预算解决。F4 有 5/17 个病例在重复
间发生 top-1 翻转，F8 为 6/17；精确前缀的平均 modal share 从 F4 的 47.1%
降到 F8 的 28.1%，表明更长轨迹仍会放大 selector/allocator 路径分叉。

因此原“F4 是最佳固定预算”的单轨迹结论被撤回。F4 仅作为低成本保守参考；
固定 F6 不晋级；固定 F8 保留研究候选，但要等 label-blind harmful-update guard
和新增病例验证。主结果见
`logs/l1_bfs_adaptive_stop/f4_f6_f8_t0_replicate_verification_v1.json`。

### E1v. P5 Capability 与 BFS F2/F4 的指标不可传递性（2026-07-14）

9-run F30 BFS 实验与 P5 冻结 arm 的同口径复核表明：**本文件的 SELECT/DIRECTION headline
不能直接解释 BFS 对题干内决定性证据的 @1/@2。**

#### E1v.1 三套 headline 回答不同问题

| 指标 | 典型 headline | 实际问什么 | 能否推出 BFS F2 @1 |
|------|--------------|-----------|-------------------|
| SELECT@1/@2 | 82.4% / 88.2% | 能否从**含题干外检查**的 decisive 池挑出金标 | **否**——池含 BCR-ABL、培养等 BFS 不可用项 |
| DIRECTION (rule-in) | 76.8%（17 题冻结） | 给定一条 rule-in finding，能否判对 **L2 叶向** | **否**——不测选择、不测 L1 排名 |
| BFS gold-rank@1 | F2 56.9%（9-run） | case 级 **L1 posterior** 第一 | 独立指标 |

#### E1v.2 observed-decisive 公平比较（审计重算）

限制到 14 例有题干内 decisive finding、126 obs（14×9 runs）：

| 指标 | P5（审计重算，Jaccard 匹配） | BFS F2 |
|------|---------------------------|--------|
| SELECT@1 | 6/14 = **42.9%** | 41/126 = **32.5%** |
| SELECT@2 | 8/14 = **57.1%** | 61/126 = **48.4%** |

差距约 **9–10pp**，不是“低于 80% 约 40pp”。上述 P5 值为启发式重算，非
`eval_talp_discrimination.py` 正式输出（原脚本无 observed-only SELECT 报告）。

#### E1v.3 方向能力在选中后仍可兑现

- P5 in-vignette rule-in DIRECTION：19/26 = **73.1%**（15 例可评分）。
- BFS 选到“P5 判对且 decisive”的前缀后：F2 条件 @1 = **93.3%**（42/45），
  F4 = **90.6%**（58/64）。

**正确表述**：决定性证据的**方向能力没有明显丢失**；主要损失在**早期选择召回**、
**L2→L1 投影**、**等权累积覆盖**与 **tie-break 伪影**。

#### E1v.4 对 Capability 文档的使用建议

1. SELECT@1=82.4% 引用时必须注明评分池含题干外检查；observed-only 子集应单独报告。
2. DIRECTION 76.8% 是 finding 级 L2 条件准确率，不能与 BFS case 级 L1 @1 横比。
3. “P5 方向 >80% ⇒ BFS F2>80%” 在 17 题数据下**逻辑不成立**（F2 实测 56.9%，
   P5 冻结 DIRECTION 点估计 76.8%）。
4. 完整根因与修复方向见 [`subagent_audit_smmary.md`](subagent_audit_smmary.md)
   “P5 → BFS F2/F4 方向落差与选择召回审计”及
   [`TALP_L1_EVIDENCE_BFS_ALGORITHM.md`](TALP_L1_EVIDENCE_BFS_ALGORITHM.md) §10.6。