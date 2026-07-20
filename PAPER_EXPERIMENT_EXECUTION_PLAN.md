# 层级开放式鉴别诊断论文：可执行实验方案

> 文档状态：v1.0（执行基线）  
> 目标分支：`cursor3`  
> 仓库：`ytydt/Agentclinic-Tree-Dx-Spec`  
> 方案制定锚点：`fa27c3990b0b65ab989564189628de43ffcad04f`  
> 制定日期：2026-07-20  
> 适用任务：完整或近完整静态病例上的开放式、单一主要诊断鉴别；不覆盖主动问诊、检查选择、治疗推荐和真实临床部署。

## 0. 执行摘要与不可变决策

本论文的核心问题是开放式困难诊断中的 **Recall–Discrimination Dilemma**：扩大疾病召回可以减少长尾遗漏，却同时引入更多相似、重复、错挂和粒度不一致的候选，进而损害最终判别。论文的主方法必须作为一条完整联合流水线被实现、冻结和评测，而不能把不同实验中单独最优的 L1、L2 与仲裁结果拼接起来。

### 0.1 论文主张

> We formulate difficult differential diagnosis as case-adaptive hierarchical hypothesis-space construction, followed by candidate-relative evidence updating and prior-aware local-to-global arbitration.

中文执行口径：

> 本研究用病例自适应层级将疾病召回、结构组织、候选相对证据选择、家族内判别和跨家族仲裁拆成可测量阶段，以缓解“候选必须召回得足够多、又必须在同一尺度上有效比较”的矛盾。

### 0.2 当前仓库证据边界

截至锚点提交，仓库已经联合实测的端点是：

- `p5_anti_anchor_direct` 的 L1 F6 后验；
- 真实 F2 证据；
- L2 配置 A；
- 完整上下文联合仲裁；
- 清单中 `compiler_rules_injected=false`。

仓库尚没有一个清单同时绑定：

- 完整 P5 compiler blocks；
- P5/B1 或 anti-anchor 的最终 L1 前缀；
- 有界、语义去重后的配置 A；
- 自适应 bounded local frontier；
- 同一个跨家族仲裁端点。

因此：

1. 现有联合端点可作为历史锚点 `M01-legacy-joint` 复现和报告；
2. 论文完整方法 `M00-hier-aa` 必须重新做端到端联合冻结；
3. 若 `M00-hier-aa` 未通过工程与冻结门，论文不得把它写成已有性能结果；
4. 现有 17 例只用于回归、调试和机制发现，不用于论文显著性检验。

### 0.3 唯一主终点

- **数据集**：DiagnosisArena 当前可公开获取并通过预设过滤的完整冻结测试集；
- **比较**：`M00-hier-aa` 对 `B02-flat-compute-matched`；
- **指标**：精确/规范同义疾病级 Top-1；
- **预测汇总**：每例 3 次独立运行；优先使用规范概念级 Top-1 多数票，全异时使用冻结的 Top-5 Borda 规则；
- **检验**：双侧 exact paired McNemar，`alpha=0.05`；
- **效应报告**：绝对准确率差、配对 bootstrap 95% CI、discordant pair 数；
- **规则**：无论显著与否都报告，不以其他数据集或其他基线替代主终点。

关键次终点为 Top-2、Top-5、MRR、L1 parent coverage、L2 disease coverage、local retention、global arbitration success、候选语义重复率和成本。次终点不替代主终点。

## 1. 研究问题、假设与对应实验

| RQ | 预注册假设 | 主要比较 | 主要数据 | 判定指标 |
|---|---|---|---|---|
| RQ1：病例自适应层级是否改善候选空间质量？ | 在相同总候选预算下，病例自适应单轴 L1 比固定 ICD/专科层级和无 L1 平面搜索具有更高 L2 coverage、更低重复/错挂，且不降低最终 Top-1 | `M00` vs `A01-fixed-hierarchy` vs `B02-flat-compute-matched` | DiagnosisArena、DDXPlus | L1 coverage、L2 coverage、duplicate rate、Top-1 |
| RQ2：候选相对证据是否优于显著性/原型驱动证据？ | P5 compiler + anti-anchor 选择减少共享证据误用，并提高 gold-present 条件下的局部保留 | `M00` vs `A03-salience-selector`、`A04-no-p5-compiler`、`A05-p5-forced-selector` | Open-XDDx、MedCaseReasoning dev-freeze | local retention、shared-evidence misuse、MRR |
| RQ3：有界局部—全局仲裁是否优于平面排序和单冠军瓶颈？ | adaptive frontier 在相近成本下优于每家族单冠军，并且 L1 软先验优于统一先验 | `M00` vs `A07-frontier-1`、`A08-frontier-2`、`A09-uniform-prior`、`B02` | DiagnosisArena、DDXPlus | Top-1/2、local elimination、arbiter recovery/harm |
| RQ4：收益是否来自机制而非额外计算？ | 在逐病例 token、LLM call、检索 call 和候选数匹配后，`M00` 仍优于平面 DDx | `M00` vs `B02` | DiagnosisArena | Top-1、MRR、成本/正确例 |
| RQ5：层级分解是否改善长尾诊断？ | 多源召回和家族条件化 L2 生成提高罕见病精确疾病级召回，而不仅是上位类命中 | `M00` vs `B01`、`B02`、`B04`、罕见病专用工具 | RareBench、可选 RareArena-REP | exact Top-k、Orphanet 层级分数、L2 coverage |

## 2. 任务边界

### 2.1 输入

- 已包含病史、体征和检查结果的静态病例文本；
- 仅由题干抽取且可回溯到题干 span 的观察事实目录；
- 对所有同资源基线一致的、经污染清理的外部医学知识库。

### 2.2 输出

- 最多 5 个可作为最终诊断的具体疾病，按可能性排序；
- 病例自适应 L1 家族及其 L2 叶；
- 每条被消费事实对候选的主要支持/反对作用；
- 阶段性审计、运行清单和成本记录。

### 2.3 排除

- 主动问诊、下一项检查或治疗选择；
- 多个并存主要诊断；
- 需要直接读取图像、波形或病理切片但无文字描述的样本；
- 真实患者临床决策支持；
- 将内部相对分数解释为临床校准概率。

若数据集包含混合任务，只保留“最可能诊断/开放式鉴别诊断”样本。筛选规则在查看模型输出前执行并冻结。

## 3. 仓库现状与实施缺口

### 3.1 已存在且可直接复用

| 能力 | 当前入口/资产 | 论文用途 |
|---|---|---|
| 17 例共享树生成 | `scripts/eval_branch_talp_composed.py` | 回归锚点、共享树冻结 |
| L1 Evidence-BFS | `scripts/eval_l1_evidence_bfs.py` | P5/B1、anti-anchor 与证据预算实验 |
| P5 判别编译 | `scripts/eval_talp_discrimination.py`、`src/agentclinic_tree_dx/discrimination/` | 完整 P0–P5 blocks 和 provenance |
| L2 C/A/B 生成 | `scripts/eval_l2_branch_generation_ab.py` | 配置 A、结构覆盖与候选负担 |
| L2 竞争与冻结 | `scripts/eval_l2_competition_strategies.py` | 组内/组间比较、L1 前缀冻结 |
| 联合仲裁 | `scripts/eval_l2_joint_dynamic_pipeline.py` | 真实顺序和端点组件消融 |
| CoT/RAG 内部基线 | `scripts/eval_naive_cot_rag_ablation.py`、`scripts/eval_naive_cot_hierarchy_baselines.py`、`scripts/eval_naive_cot_l2_baselines.py` | 17 例锚点和新统一 runner 的逻辑来源 |
| RareArena 留一召回试验 | `scripts/eval_llm_ddx_rarearena.py` | 长尾召回机制验证；不是完整论文端点 |
| 现有联合清单 | `logs/l2_competition_strategies_v1/l1_full/manifest.json` | 证明当前 anti-anchor 轨迹未注入 compiler blocks |

### 3.2 主测试前必须实现

以下文件名定义为实施合同；它们在本方案提交时尚不存在，不能把示例命令误写成“当前已可运行”。

| 编号 | 必须新增的能力 | 建议入口 | 完成条件 |
|---|---|---|---|
| I01 | 统一病例 schema 与数据集适配器 | `scripts/paper/prepare_dataset.py` | 每个数据集输出 runtime/gold 分离的规范 JSONL 和 flow report |
| I02 | 病例报告污染清理 | `scripts/paper/audit_leakage.py` | 精确 ID、标题/作者、近重复文本三层清理；输出逐文档排除原因 |
| I03 | 确定性诊断名称归一化 | `scripts/paper/normalize_diagnoses.py` | SNOMED/UMLS/ICD/ORPHA 优先；未映射项进入盲法人工裁决 |
| I04 | 统一端到端方法 runner | `scripts/paper/run_experiment.py` | `M00` 从原始 runtime case 一次性产生冻结树、排名、trace 和成本 |
| I05 | 逐病例预算账本与 compute-matched flat baseline | `scripts/paper/build_budget_schedule.py` | `B02` 在每例 token/call/tool/candidate 预算上与 `M00` 偏差不超过 5% |
| I06 | 固定层级与 flat beam 基线 | `scripts/paper/run_baseline.py` | 不读取 gold，复用相同知识库、模型与输出协议 |
| I07 | 外部基线 wrapper | `baselines/` 下各适配器 | 保存上游 commit、环境、模型、提示和原始输出；可统一评分 |
| I08 | 统一评分与统计 | `scripts/paper/score_results.py` | 精确/层级/过程/成本指标、McNemar、case-cluster bootstrap |
| I09 | 冻结发布器 | `scripts/paper/freeze_release.py` | 生成不可变 freeze manifest，绑定代码、数据、语料、提示、模型和预算 |

任何主测试调用开始前，I01–I09 必须通过第 18 节的质量门。

## 4. 待冻结的完整方法

### 4.1 `M00-hier-aa`：论文主方法

`M00` 必须是一个单一端到端 arm，包含：

1. **病例自适应 L1**：多来源具体疾病召回；LLM 构造单一轴、同层级、尽量互斥的家族；一次非缩减 gap-fill；
2. **完整 P5 compiler**：P0 审计、P1 对称取证、P2 数值/极性归一、P3 全候选效应矩阵、P4 USE 准入、P5 表型交集与父子 veto；
3. **anti-anchor selector**：消费冻结 P5 blocks 与 L2 leaf exemplars；可弃权；每条事实提供全 L1 效应矩阵；
4. **稀疏对称更新**：每条事实最多一个主要支持目标和一个不同的主要反对目标；
5. **有界配置 A**：逐 L1 家族条件化 L2 召回与生成，一次 gap-fill，概念级语义去重和父子一致性门；
6. **bounded local frontier**：每家族传入 1–2 个 L2；局部 margin 足够大时传 1 个，否则传 2 个；
7. **跨家族重新比较**：冻结 L1 分数只作可被病例证据推翻的软先验，不直接混合不同家族的局部分数。

### 4.2 预算向量

开发冻结前使用以下起始值；阈值只能在 `D1a-dev-tune` 上调整一次，随后在 `D1b-dev-freeze` 上验证并锁定：

```yaml
l1_family_max: 6
l1_evidence_budget: 4
l2_unique_candidate_total_max: 24
l2_candidate_min_per_live_family: 2
l2_candidate_max_per_live_family: 6
l2_local_evidence_budget: 2
local_frontier_min: 1
local_frontier_max: 2
global_frontier_max: 8
gap_fill_max_calls_l1: 1
gap_fill_max_calls_l2_per_family: 1
temperature: 0.0
replicates: 3
```

若由于家族数导致 `2 × live_family_count > 24`，按冻结 L1 分数与 can't-miss 标记进行确定性配额分配：每家族先分 1 个名额，再按分数分配剩余名额；不得使用 gold。所有被预算截断的候选保留在审计日志中。

adaptive frontier 的阈值只允许在 `D1a` 上按预注册网格 `{0.10, 0.15, 0.20}` 选择；选择规则是先最大化 local retention，再最小化 global frontier size，最后才比较 Top-1。不得在主测试上修改。

### 4.3 `M01-legacy-joint`：历史联合锚点

`M01` 严格复现当前已联合运行的 anti-anchor F6 + F2 + Config A + full-context joint arbitration，保持 `compiler_rules_injected=false`。其用途是：

- 证明新 runner 未改变已有结果口径；
- 显示完整 P5 注入、有界去重和 adaptive frontier 分别带来什么变化；
- 在 `M00` 未完成时提供诚实的可报告系统边界。

`M01` 不能在测试后被重新定义。

## 5. 数据集、冻结样本与优先级

### 5.1 主数据矩阵

| ID | 数据集与冻结规模 | 角色 | 优先级 | 运行说明 |
|---|---|---|---|---|
| D0 | 当前仓库 17 例 | 回归/机制开发 | P0 | 可重复使用；不得做论文显著性推断 |
| D1 | MedCaseReasoning validation 500 | 开发冻结 | P0 | 按 journal、诊断频率桶和病例长度分层，以 seed=`20260720` 固定切成 `D1a=250` tune 与 `D1b=250` freeze；PMCID 用于污染排除 |
| D2 | DiagnosisArena 当前公开快照的全部合格例 | 主要外部测试 | P0 | 公共 HF 快照目前显示 915 例，而论文/仓库描述 1,113；必须记录实际下载 revision、raw N、过滤 N，不手工写死 |
| D3 | Open-XDDx raw 570，预计过滤后约 560 | 解释与差异性证据测试 | P0 | 官方资料为 570；560 仅可作为过滤后预期，不得伪称官方总量 |
| D4 | RareBench Task 4：MME 40 + HMS 88 + LIRICAL 370 = 498 | 长尾主测试 | P0 | 与公开 MAC/DeepRare 设置可比；保留三个来源的分层结果 |
| D5 | DDXPlus 980 | 结构机制测试 | P0 | 49 病种每病种 20 例；按 evidence count 四分位轮转抽样；seed=`20260720` |
| D6 | RareArena-REP-v1 500 | 可选长尾外部验证 | P1 | 当前公开仓库未确认官方低成本代表子集；自行按 Orphanet 顶层类、疾病和表型长度分层并发布 manifest，不称“官方子集” |
| D7 | ER-Reason SCT 194 | 可选真实 EHR/序贯证据验证 | P2 | credentialed access、CITI/DUA 完成后运行；只评 evidence update，不作为静态主排行榜 |

数据来源：

- [DiagnosisArena repository](https://github.com/SPIRAL-MED/DiagnosisArena)；[public dataset snapshot](https://huggingface.co/datasets/shzyk/DiagnosisArena)
- [MedCaseReasoning dataset](https://huggingface.co/datasets/zou-lab/MedCaseReasoning)
- [Open-XDDx / Dual-Inf](https://github.com/betterzhou/Dual-Inf)
- [RareBench](https://github.com/chenxz1111/RareBench)
- [DDXPlus](https://github.com/mila-iqia/ddxplus)
- [RareArena](https://github.com/zhao-zy15/RareArena)
- [ER-Reason](https://physionet.org/content/er-reason/1.0.0/)

### 5.2 预设纳入规则

样本必须同时满足：

1. 单一患者；
2. 有足以构成静态病例的文本；
3. 有一个主要最终诊断；
4. gold 可映射到具体疾病实体或经盲法医生确认；
5. 不要求读取未提供文字描述的图像；
6. 不属于治疗、预后、检查选择或纯知识问答；
7. 污染清理后仍有可用的共享知识库。

### 5.3 预设排除规则

- 多患者或病例集合；
- 多个并存主要疾病且无法指定主诊断；
- gold 仅为症状、解剖部位或过宽上位类；
- 空文本、严重截断、答案直接出现在专门的 `diagnosis` 字段并被拼入 runtime；
- exact source 或高度近重复来源无法从检索库可靠排除；
- 许可不允许本研究处理或发布派生结果。

每个排除样本保存 `case_id`、唯一原因、数据 revision 和操作时间；不得根据模型答对/答错决定排除。

## 6. 规范数据合同与 gold 隔离

### 6.1 运行时病例

```json
{
  "case_id": "diagnosisarena__000123",
  "dataset": "diagnosisarena",
  "split": "test",
  "vignette": "...",
  "observed_facts": [
    {
      "fact_id": "F001",
      "text": "...",
      "source_span": [128, 176],
      "concept_key": "...",
      "polarity": "present|absent|uncertain",
      "value_status": "high|low|normal|positive|negative|na"
    }
  ],
  "source_identifiers_for_exclusion": {
    "pmid": null,
    "pmcid": null,
    "doi": null,
    "title": "...",
    "authors": []
  },
  "runtime_hash": "sha256"
}
```

### 6.2 gold 文件

```json
{
  "case_id": "diagnosisarena__000123",
  "gold_text": "...",
  "canonical_name": "...",
  "concept_ids": {
    "snomed": [],
    "umls": [],
    "icd10": [],
    "orpha": []
  },
  "accepted_aliases": [],
  "adjudication_status": "deterministic|physician_consensus|unresolved"
}
```

运行进程只能读取 runtime bundle。评分进程在全部预测文件封存后才读取 gold。CI 必须扫描运行 payload，禁止出现 `gold`、`final_diagnosis`、`answer`、`gold_option`、未脱敏 DOI/PMCID 对应诊断字段等泄漏字段。

### 6.3 名称归一化

按以下顺序匹配：

1. 规范 concept ID 精确相交；
2. 冻结同义词表精确匹配；
3. 预设父子关系仅用于 HDF1，不计为 exact disease hit；
4. 未映射项由两名对方法盲法的医生独立裁决，分歧交第三人；
5. 不使用与被测模型同厂商的 LLM 作为最终 exact-match judge。

## 7. 检索污染与病例泄漏控制

病例报告型 benchmark 与病例报告检索库重叠是本论文最高风险。仅从题干删除 gold 字符串不构成污染控制。

### 7.1 三层排除

对 D1、D2、D6 以及任何来自病例报告的数据集，逐例构建检索排除表：

1. **标识符排除**：同 PMID、PMCID、DOI、数据集 source ID 的原文、摘要、镜像和 chunk 全部删除；
2. **书目排除**：规范标题完全相同，或标题 token Jaccard `>=0.90` 且作者/年份匹配的文档删除；
3. **文本近重复排除**：任一连续段落 5-gram Jaccard `>=0.80`，或 embedding cosine `>=0.95` 的文档进入人工/规则复核；确认同一病例或派生页面后删除。

阈值只可在 D0/D1a 的已知正负对上校准，随后冻结。每次检索还必须按 `case_id` 运行动态 denylist，防止同一报告的不同抓取版本漏入。

### 7.2 允许与禁止

- 允许一般指南、教材或其他病例报告合法提及 gold 疾病；
- 禁止检索到测试病例本身、其摘要镜像、新闻转述、同文派生页面或带相同患者细节的近重复；
- 不得为了降低模型准确率而从整个知识库删除 gold 疾病名称；
- 外部系统若使用自己的不可清理知识库，单列为 `official-resource` 比较，不进入同资源公平主检验。

### 7.3 泄漏审计产物

每个数据集必须输出：

- `source_registry.jsonl`；
- `leakage_exclusions.jsonl`；
- `near_duplicate_review.csv`；
- `clean_corpus_manifest.json`；
- exact-source 排除率、近重复命中率和人工抽查结果。

人工抽查至少包含 100 个被排除对和 100 个高相似但保留对；报告 precision，并列出仍无法排除的风险。

## 8. 基线与公平性分层

### 8.1 同资源、同 backbone 主比较

| Arm | 方法 | 控制目的 | 资源约束 |
|---|---|---|---|
| B00 | Direct CoT，无 RAG | 最低复杂度诊断基线 | 同模型、同输出长度；1 次主调用 |
| B01 | CoT + shared RAG | 控制外部知识本身 | 与 `M00` 同一 clean corpus、检索器和总 snippet 字符预算 |
| B02 | Compute-matched Flat DDx | 核心公平比较；排除收益来自更多计算 | 逐病例匹配 `M00` 的总 token、LLM calls、retrieval calls、unique candidates，偏差 `<=5%` |
| B03 | Flat Tree/Beam Search | 区分“病例自适应家族层级”与“任意树搜索” | 不生成 L1；相同深度、beam、总候选和调用预算 |
| B04 | Dual-Inf | 控制平面正向生成 + 反向验证 | 官方逻辑，同 backbone；静态完整病例模式 |
| B05 | MDAgents | 控制自适应多智能体协作本身 | 同 backbone；固定官方 agent 数/复杂度策略并记录调用数 |
| B06 | Single-vendor MAC | 控制多个医生 + supervisor 讨论 | 同 backbone、3 doctors + supervisor；与官方代码一致 |

官方代码：

- [Dual-Inf](https://github.com/betterzhou/Dual-Inf)
- [MDAgents](https://github.com/mitmedialab/MDAgents)
- [Single-/Mixed-vendor MAC](https://github.com/rajpurkarlab/mixed-vendor-mac)

### 8.2 官方资源/专用系统比较

| Arm | 方法 | 使用数据 | 解释规则 |
|---|---|---|---|
| B07 | MEDDxAgent | DDXPlus、RareBench；DiagnosisArena 可选 | complete-profile 静态模式；因其自带模块/检索，标记为 resource-unmatched |
| B08 | DeepRare | RareBench、RareArena-REP | 罕见病专用高成本上界；使用官方模型/工具配置 |
| B09a–c | LIRICAL、PhenoBrain、PubCaseFinder | RareBench、RareArena-REP | 非 LLM 表型匹配对照；确定性运行 1 次 |
| B10 | Mixed-vendor MAC | DiagnosisArena、RareBench | 高成本 ensemble 上界；不与同 backbone 主检验混合 |
| B11 | DiagnosisGPT/Chain-of-Diagnosis | DxBench 或兼容静态子集 | 训练型专用模型对照；不强行迁移到不兼容数据 |

官方代码：

- [MEDDxAgent](https://github.com/nec-research/meddxagent)
- [DeepRare](https://github.com/MAGIC-AI4Med/DeepRare)
- [Chain-of-Diagnosis](https://github.com/FreedomIntelligence/Chain-of-Diagnosis)

### 8.3 公平性规则

1. 所有同资源 arm 使用同一 runtime case、clean corpus、名称规范化器和评分器；
2. 先运行 `M00` 生成逐病例预算 schedule，但 schedule 不含其预测或 gold；
3. `B02/B03` 只读取预算上限，不读取 `M00` 的候选、推理或结果；
4. 同一模型版本、provider、temperature、max tokens 和三组 replicate ID；
5. 外部 baseline 无法替换 backbone 时保留官方设置，并单列，不宣称严格计算公平；
6. 缓存命中也计入逻辑调用与原始未缓存成本估计，避免“谁先运行谁更便宜”；
7. 同时报告 native/unconstrained 和 matched-budget 结果，主检验使用 matched-budget。

## 9. 消融臂注册

| Arm | 相对 `M00` 的唯一变化 | 回答问题 | 运行范围 |
|---|---|---|---|
| A01-fixed-hierarchy | L1 改为预先冻结的 ICD/专科家族，其他不变 | 病例自适应结构是否必要 | D1、D2、D5 |
| A02-no-l1-flat-rerank | 删除 L1，保留同一召回池与总预算 | 层级本身是否必要 | D1、D2 |
| A03-salience-selector | anti-anchor 改为显著性选择 | 候选相对选证是否有效 | D1、D3 |
| A04-no-p5-compiler | 不注入 P5 blocks；保留 anti-anchor | P5 编译知识的增量 | D1、D3 |
| A05-p5-forced-selector | anti-anchor 改为 `p5_single_direct` 强制选择 | 可弃权和反锚定的增量 | D1、D3 |
| A06-no-semantic-dedupe | 仅精确字符串去重 | 语义重复的影响 | D1、D5 |
| A07-frontier-1 | 每家族只传 1 个局部冠军 | 单冠军瓶颈 | D1、D2、D5 |
| A08-frontier-2 | 每家族固定传 2 个 | 自适应前沿是否优于固定 Top-2 | D1、D2、D5 |
| A09-uniform-prior | 跨家族仲裁不提供 L1 软先验 | L1 先验的增量 | D1、D2 |
| A10-no-gap-fill | 关闭 L1/L2 gap-fill | 结构性补漏的增量 | D1、D4 |
| A11-source-cpg-only | 只用 CPG/教材召回 | 多源互补性 | D1、D4 |
| A12-source-case-only | 只用病例报告召回 | 长尾召回来源 | D1、D4 |
| M01-legacy-joint | 当前已实测联合端点 | 历史锚点与新主方法差异 | D0、D1b |

除 `A01/A02/A07/A08/A09` 外，消融不在完整 D2 上大规模扩展，除非 D1b 显示其对应机制是主方法性能的必要解释。这样控制多重比较和 API 成本。

## 10. 最低可发表运行矩阵

`R3` 表示 3 次独立调用并按病例聚类；`R1` 表示确定性或官方单次结果。任何新增测试臂必须在主测试开始前写入 freeze manifest。

| 数据 | 样本 | 必跑 arm | 重复 | 用途 |
|---|---:|---|---:|---|
| D0-regression | 17 | M00、M01、B00–B04、A01–A12 | R1 smoke；关键 arm R3 | 接口、泄漏、schema 与历史结果回归 |
| D1a-dev-tune | 250 | M00、M01、B00–B04、A01–A12 | R1；入围 arm 再 R3 | 只调阈值、预算和 prompt；不作论文测试结论 |
| D1b-dev-freeze | 250 | M00、M01、B02、B04、入围消融 | R3 | 选择整条联合端点并冻结；不得回到 D1a 修改后反复窥视 |
| D2-DiagnosisArena | 全部合格例 | M00、B00–B06 | R3 | 主终点与一般疾病外部效度 |
| D3-Open-XDDx | 全部合格例 | M00、B00–B04、A03–A05 | R3 | 解释、差异性证据和候选相对更新 |
| D4-RareBench-498 | 498 | M00、B00–B02、B04、B06–B09 | LLM R3；确定性工具 R1 | 长尾与表型专用系统比较 |
| D5-DDXPlus-980 | 980 | M00、B01–B03、B05、B07、A01/A02/A06–A09 | R3 | 候选覆盖、分支纯度和局部—全局机制 |
| D6-RareArena-REP | 500 | M00、B01、B02、B08、B09 | R3/R1 | 可选长尾泛化与 Orphanet 层级评价 |
| D7-ER-Reason-SCT | 194 | M00 evidence-update、B02、B04 | R3 | 可选序贯 belief update 探索性结果 |

若预算不足，削减顺序为：D7 → D6 → B10/B11 → D2/D4 上的非核心外部系统；不得削减 `M00 vs B02` 主比较、D2 全量、D4 长尾测试或 D3 证据测试。

## 11. 分阶段执行流程

### Phase 0：环境与 17 例历史锚点

目标：确认锚点提交、已有资产和当前结果能够在新输出目录重放。

```bash
git switch cursor3
git pull --ff-only origin cursor3
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m pytest -q
```

使用新目录，禁止覆盖已提交日志：

```bash
export MAIN_MODEL=meta-llama/llama-3.3-70b-instruct
export ANCHOR_ROOT=logs/paper/anchor17_v1

python scripts/eval_l2_competition_strategies.py all \
  --model "$MAIN_MODEL" \
  --temperature 0 \
  --replicates 3 \
  --n-boot 10000 \
  --output-dir "$ANCHOR_ROOT/l2_competition"

python scripts/eval_l2_branch_generation_ab.py freeze-inputs \
  --output-dir "$ANCHOR_ROOT/l2_config_ab" \
  --base-output-dir "$ANCHOR_ROOT/l2_competition"

python scripts/eval_l2_branch_generation_ab.py generate \
  --output-dir "$ANCHOR_ROOT/l2_config_ab" \
  --base-output-dir "$ANCHOR_ROOT/l2_competition" \
  --model "$MAIN_MODEL" \
  --temperature 0 \
  --replicates 3

python scripts/eval_l2_branch_generation_ab.py evaluate \
  --output-dir "$ANCHOR_ROOT/l2_config_ab" \
  --base-output-dir "$ANCHOR_ROOT/l2_competition" \
  --adjudication-fixture eval_fixtures/l2_branch_generation_ab_gold_v1.json \
  --bootstrap 10000
```

验收：

- 所有测试通过，或对锚点已有失败建立独立、可复现清单；
- 17/17 runtime payload 无 gold；
- `M01` 的关键点估计与已提交 summary 的差异不超过 3 个百分点；
- manifest 仍显示历史端点 `compiler_rules_injected=false`；
- 不把重放误写成 `M00`。

### Phase 1：数据准备与污染清理

1. 下载并记录原始 revision、许可和 SHA256；
2. 运行适配器，生成 canonical runtime/gold；
3. 按规则过滤任务类型和多病样本；
4. 构建 source registry；
5. 清理检索语料并冻结 clean corpus；
6. 规范化 gold；
7. 生成每数据集 flow report。

目标 CLI 合同：

```bash
python scripts/paper/prepare_dataset.py \
  --dataset diagnosisarena \
  --raw-dir data/benchmarks/diagnosisarena/raw \
  --revision '<immutable_revision>' \
  --out-dir data/benchmarks/diagnosisarena/normalized/v1

python scripts/paper/audit_leakage.py \
  --runtime data/benchmarks/diagnosisarena/normalized/v1/runtime.jsonl \
  --source-registry data/benchmarks/diagnosisarena/normalized/v1/source_registry.jsonl \
  --corpus-manifest data/corpus/source_manifest.jsonl \
  --out-dir data/benchmarks/diagnosisarena/leakage/v1
```

验收：所有保留样本有 runtime hash；所有病例报告型样本有 source exclusion key；gold 映射/人工待审状态为 100%；未解决污染样本不得进入运行集。

### Phase 2：统一 `M00` 与预算账本

实现并单测：

- P5 blocks 真正进入 anti-anchor selector；
- L1 F4、L2 F2 的含义在 trace 中明确；
- Config A 使用全局 unique candidate budget；
- concept-ID 语义去重和 parent-consistency gate；
- adaptive 1–2 frontier；
- L1 prior 只进入 global arbiter；
- 独占且穷尽的 failure-path 分类；
- token、call、retrieval、candidate、latency 账本。

硬验收：

- `compiler_rules_injected=true`；
- 100% 选择事实来自观察事实白名单；
- 100% L1/L2 ID 可在当前冻结树解析；
- schema-valid `>=99%`，repair rate `<5%`；
- 同一 concept 不重复计分；
- 单元测试显式覆盖单冠军丢失、Top-2 保留和 adaptive frontier 三种路径。

### Phase 3：基线封装与公平性校准

每个 baseline wrapper 必须产生与 `M00` 相同的 `predictions.jsonl`、`trace.jsonl`、`cost.json` 和 `manifest.json`。先在 D0 的 5 例 smoke，再在 D1a 的 20 例预算 pilot。

`B02` 的逐病例预算来自 `M00` 预算清单：

```bash
python scripts/paper/build_budget_schedule.py \
  --main-run runs/paper_v1/d1a/M00-hier-aa \
  --out configs/paper_experiments/paper_v1_budget_schedule.jsonl
```

若 B02 因一次调用最大上下文限制不能消耗同等 token，允许把预算拆成多次平面 evidence-matrix 调用，但不得生成 L1 家族。若实际预算偏差超过 5%，该病例标记 `budget_mismatch`，修复 wrapper 后成对重跑，不得单独删除。

### Phase 4：开发、冻结与 dry run

执行顺序：

1. D1a：阈值和预算开发；
2. 固定全部代码和 prompt；
3. D1b：3 repeats 验证联合端点；
4. 只按预注册整链选择规则决定是否冻结 `M00`；
5. 建立 freeze manifest；
6. 从 D2/D3/D4/D5 各抽 5 例，仅做 schema/cost dry run，不查看准确率；
7. dry run 通过后锁定测试数据读权限和运行队列。

整链冻结规则按顺序判断：

1. 无泄漏和 gold exposure；
2. schema-valid `>=99%`；
3. 相对 `M01` 的 L2 coverage 非劣界为 `-2 pp`；
4. duplicate rate 相对 `M01` 至少降低 20%；
5. local retention 不低于 `M01`；
6. 前五项通过后才查看 D1b Top-1，并将其作为描述性指标，不据此拼换模块。

若失败，回到 D1a 修复一次并生成新的 `freeze_candidate_id`；D1b 每个候选最多完整运行两次。超过两次仍失败则采用 `M01` 作为论文系统并降低方法主张，不访问主测试结果后再修主方法。

### Phase 5：主测试

目标 CLI：

```bash
python scripts/paper/run_experiment.py \
  --freeze-manifest configs/paper_experiments/paper_v1.freeze.json \
  --dataset diagnosisarena \
  --arms M00-hier-aa,B00-direct-cot,B01-cot-rag,B02-flat-compute-matched,B03-flat-beam,B04-dual-inf,B05-mdagents,B06-mac-single-vendor \
  --replicates 1,2,3 \
  --resume
```

队列顺序随机化到 `case_id × arm × replicate`，同时保证每个病例的配对 arm 在同一模型/provider 版本窗口完成。不得先跑完主方法数周后再跑基线而不记录模型版本变化。

主测试启动后只允许：

- 对网络/限流/服务错误按冻结重试策略重试；
- 修复不改变语义的基础设施错误，并使该病例全部配对 arm 重跑；
- 不允许更改 prompt、预算、候选上限、名称映射规则或排除规则。

### Phase 6：评分、统计与人工审计

```bash
python scripts/paper/score_results.py \
  --freeze-manifest configs/paper_experiments/paper_v1.freeze.json \
  --runs-root runs/paper_v1 \
  --bootstrap 10000 \
  --out-dir results/paper_v1
```

评分先生成锁定的 machine metrics，再向人工审阅者提供去方法名、随机顺序的解释与结构审计包。人工评分回收前不得根据初步偏好重写解释提示。

## 12. 冻结清单

`paper_v1.freeze.json` 至少绑定：

```json
{
  "freeze_id": "paper_v1",
  "code_commit": "<full_sha>",
  "method_arm": "M00-hier-aa",
  "joint_endpoint": {
    "p5_compiler": true,
    "l1_selector": "p5_anti_anchor_direct",
    "l1_evidence_budget": 4,
    "l2_generator": "config_a_bounded_semantic_dedupe",
    "local_frontier": "adaptive_1_2",
    "global_arbiter": "l1_soft_prior_full_context"
  },
  "models": {},
  "prompt_sha256": {},
  "dataset_revisions": {},
  "runtime_bundle_sha256": {},
  "gold_bundle_sha256": {},
  "clean_corpus_sha256": {},
  "leakage_exclusion_sha256": {},
  "normalizer_sha256": "...",
  "budget_schedule_sha256": "...",
  "replicate_ids": [1, 2, 3],
  "temperature": 0.0,
  "retry_policy": {
    "max_transport_retries": 2,
    "max_schema_repair": 1
  }
}
```

清单还要保存 Python 版本、关键包 lock、provider endpoint 标识、模型返回版本、时区、硬件、调用 timeout、最大输出 token 和运行调度 seed。

## 13. 指标定义

### 13.1 最终诊断

- `Top-k exact/canonical`：gold concept 或冻结 accepted alias 位于前 k；`k ∈ {1,2,5}`；
- `MRR`：gold 第一次精确/规范匹配名次的倒数，未命中为 0；
- `HDF1`：按冻结 ICD/ORPHA 层级计算的辅助指标；不得替代 exact hit；
- `list precision@5`：输出中可作为具体疾病实体的比例。

### 13.2 候选空间

- `L1 parent coverage`：存在至少一个临床可接受、能容纳 gold 的 L1 家族；
- `L2 disease coverage`：最终排序前，树中存在 gold 具体疾病；
- `clean parent coverage`：gold 存在且挂在经盲法判定可接受的父家族；
- `candidate burden`：每例 unique L2 候选数；
- `semantic duplicate rate`：规范化为相同 concept 或经盲法判定为同义/粒度重复的叶对比例；
- `wrong-parent rate`：具体疾病挂在不相容家族的比例；
- `axis coherence`：所有非 residual L1 是否使用同一分类轴。

### 13.3 局部—全局漏斗

每个病例/replicate 只赋一个 failure path，按顺序：

1. `L1_MISS`：没有可接受 gold parent；
2. `L2_MISS`：有 parent，但 gold 未生成；
3. `LOCAL_ELIMINATION`：gold 已生成，但未进入本家族 bounded frontier；
4. `GLOBAL_MISRANK`：gold 已进入 global frontier，但未进入目标 Top-k；
5. `SUCCESS`。

派生指标：

- `local retention = frontier_contains_gold / L2_gold_present`；
- `global success = final_hit / global_frontier_contains_gold`；
- `arbiter recovery`：仲裁前 gold 非全局 Top-k、仲裁后进入 Top-k；
- `arbiter harm`：仲裁前 gold 在 Top-k、仲裁后退出 Top-k。

### 13.4 证据质量

- selected fact 是否来自题干白名单；
- concept 重复消费率；
- P5 USE 规则 precision；
- shared-evidence misuse：候选共有事实被签为单一候选强区分证据的比例；
- support/opposition target 合法率；
- 与 Open-XDDx 专家支持/反对解释的概念覆盖；
- 删除所选证据后的排名变化，用于检验“解释是否真正影响输出”。

### 13.5 成本与稳健性

- input/output/cached tokens；
- LLM、retrieval、tool、repair、retry calls；
- wall-clock 与 serial-equivalent latency；
- 美元成本，使用运行当日价格表快照；
- cost per correct case、tokens per absolute percentage-point gain；
- 3 次运行 Top-1 agreement、unique Top-1 count、schema-valid 和 repair rate。

## 14. 统计分析

### 14.1 主要分析

每个方法对每例运行 3 次。主要 Top-1 先在规范 concept ID 层汇总：同一诊断获得至少 2 个 Top-1 时取多数票；若三个 Top-1 全异，则对三份 Top-5 使用 `score(d)=Σ(6-rank_r(d))` 的 Borda 分数，未出现记 0；仍并列时依次按 replicate 1 的名次、replicate 2 的名次、规范 concept ID 字典序打破。该规则对所有 arm 一致，并在评分前冻结。汇总后形成每例一个二元结果，`M00` 与 `B02` 使用 exact paired McNemar。报告：

- 两方法各自准确率；
- 绝对差值；
- `M00 only correct` 与 `B02 only correct` 数；
- exact p 值；
- 10,000 次病例级配对 bootstrap 95% CI。

### 14.2 次要分析

- Top-2、Top-5、MRR、HDF1、过程指标和成本：病例级 paired bootstrap 10,000 次；
- 3 个 replicate 作为病例内观测，不当作 3 倍独立样本；bootstrap 以病例为 cluster；
- 预注册的关键次比较使用 Holm 校正；探索性子组只报告效应和 CI，不作“显著/不显著”筛选；
- 稀有/常见、专科、病例长度、gold 频率、检索源和污染风险作为探索性子组；
- 17 例结果只给描述性点估计，不给论文显著性结论。

### 14.3 缺失与失败

- transport/rate-limit 错误：按清单最多重试 2 次；
- schema 错误：只允许 1 次冻结格式修复；
- 某 arm 最终失败时，对相同 `case_id × replicate` 的所有配对 arm 成组重跑；
- 仍失败则按 intention-to-evaluate 计为未命中，并单独报告失败率；
- 不允许只删除表现差的方法输出。

## 15. 人工评估

### 15.1 结构质量

从 D2、D4、D5 各分层抽样，共 120 例。两名临床医生在不知道方法名与 gold 排名的情况下评估：

- L1 单轴一致性；
- 家族互斥性；
- gold parent 可接受性；
- L2 wrong-parent；
- 语义重复。

### 15.2 解释质量

从 D3 分层抽样 120 例，对 `M00/B02/B04` 的解释随机盲排：

- 是否引用已观察事实；
- 是否解释候选间差异，而非只复述疾病典型性；
- 支持/反对方向是否医学合理；
- 是否包含无依据声明；
- 对最终排序是否有实际帮助。

每项 1–5 分，并记录严重事实错误。两名医生独立评分，分歧由第三人裁决；报告 weighted kappa 或 Krippendorff’s alpha。人工审计表、说明书和去标识化输出一并冻结。

## 16. 成本预检与资源闸门

在 D1a 随机 20 例上对全部 P0 LLM arm 各运行 1 次，测量：

```text
estimated_cost =
  input_tokens  × frozen_input_price
  + output_tokens × frozen_output_price
  + tool_calls × tool_unit_cost
```

据此输出数据集 × arm × repeat 的完整外推预算。主测试需要书面确认预算上限；预算不足按第 10 节的固定削减顺序处理，不依据任何测试准确率删臂。

运行监控每 50 个 case-runs 检查：

- API 错误率；
- schema repair；
- token/call 预算偏差；
- provider/model 版本漂移；
- 缓存污染；
- 输出目录剩余空间。

监控只决定暂停和基础设施修复，不显示聚合准确率给开发人员。

## 17. 输出目录与可复现产物

```text
data/benchmarks/<dataset>/
  raw/                         # 不提交受限原始数据
  normalized/<version>/
    runtime.jsonl
    gold.jsonl
    source_registry.jsonl
    flow_report.json
  leakage/<version>/
    leakage_exclusions.jsonl
    near_duplicate_review.csv
    clean_corpus_manifest.json

configs/paper_experiments/
  paper_v1.yaml
  paper_v1.freeze.json
  paper_v1_budget_schedule.jsonl

runs/paper_v1/<dataset>/<arm>/replicate_<n>/
  manifest.json
  predictions.jsonl
  trace.jsonl
  cost.json
  errors.jsonl

results/paper_v1/
  primary_analysis.json
  dataset_flow.tsv
  main_results.tsv
  process_metrics.tsv
  ablations.tsv
  cost.tsv
  human_evaluation.tsv
  tables/
  figures/
```

每个输出文件保存 SHA256。原始 prompt/response 可在许可允许时保存到受控存储；公开复现包至少提供 prompt、结构化输出、哈希、统计脚本和不含受限病例文本的汇总。

## 18. 质量门与停止条件

| Gate | 进入条件 | 失败动作 |
|---|---|---|
| G0 环境 | 锚点测试和 17 例重放完成 | 修环境；不下载主测试 |
| G1 数据 | 100% 样本有 flow、许可、runtime hash、gold 状态 | 排除或补齐；不运行模型 |
| G2 污染 | 病例报告型样本均有 source denylist；near-duplicate 审计完成 | 清理语料或排除样本 |
| G3 主方法 | `M00` 联合清单 `compiler_rules_injected=true`，所有模块在同一 run | 不得报告“完整方法” |
| G4 接口 | schema-valid `>=99%`、repair `<5%`、gold exposure=0 | 修 runner，只用 D0/D1a |
| G5 公平 | B02/B03 逐病例预算偏差 `<=5%` | 重建 budget schedule/wrapper |
| G6 冻结 | D1b 整链门通过；freeze manifest 哈希完整 | 降级为 M01 或停止主测试 |
| G7 dry run | 每测试集 5 例仅看运行健康，不看准确率 | 修基础设施后重新 dry run |
| G8 主测试 | freeze 后一次性运行；无语义变更 | 只允许冻结重试策略 |

满足以下任一条件应暂停整个队列：provider/model 版本变化、预算偏差连续 10 例超过 5%、gold 字段出现在 runtime、污染 denylist 未生效、schema-valid 低于 97%、API 错误率高于 10%。

## 19. 论文表图与实验产物映射

| 论文位置 | 产物 | 来源 |
|---|---|---|
| Table 1 | 数据集、raw/eligible N、排除流、许可 | `dataset_flow.tsv` |
| Table 2 | D2 主结果与 McNemar | `primary_analysis.json` |
| Table 3 | D3/D4/D5 外部与机制结果 | `main_results.tsv` |
| Table 4 | 候选空间和 failure-path 分解 | `process_metrics.tsv` |
| Table 5 | 必要消融 | `ablations.tsv` |
| Table 6 | token/call/latency/美元 | `cost.tsv` |
| Figure 1 | candidate count–coverage–Top-1 的 recall/discrimination 曲线 | D5 + 预算扫描 |
| Figure 2 | L1 miss → L2 miss → local elimination → global misrank 漏斗 | 全数据 failure path |
| Figure 3 | frontier=1/2/adaptive 的 local retention 与成本 | A07/A08/M00 |
| Figure 4 | Open-XDDx 事实 × 候选效应示例与人工评分 | D3 human audit |

## 20. 结果解释与允许的主张

### 20.1 若主终点和机制均支持

可以主张：病例自适应层级和候选相对证据更新在同计算预算下提高最终诊断准确率，并通过阶段性指标解释收益来自何处。

### 20.2 若覆盖改善但 Top-1 不改善

只能主张：方法改善候选召回、结构和错误可定位性，但新增候选的判别收益被局部/全局排序损失抵消。不得写“提高诊断准确率”。

### 20.3 若只在罕见病改善

将贡献限定为长尾叶召回与候选管理；不得推广到一般临床诊断。

### 20.4 若 `M00` 未通过联合冻结

论文必须报告 `M01` 的真实配置和 `compiler_rules_injected=false`，把完整 P5 + bounded frontier 作为未来工作，而不是把独立模块结果合并成主方法。

## 21. Definition of Done

实验阶段完成必须同时满足：

- [ ] I01–I09 全部实现并通过测试；
- [ ] D0 历史锚点复现；
- [ ] D1–D5 的数据、污染和许可清单冻结；
- [ ] `M00` 单一联合 manifest 完成，或明确降级为 `M01`；
- [ ] 主方法与 B02 逐病例预算匹配；
- [ ] 最低可发表运行矩阵无未解释缺口；
- [ ] 3 repeats、配对统计和病例聚类正确处理；
- [ ] 人工结构/解释审计完成并报告一致性；
- [ ] 所有错误按独占 failure path 分解；
- [ ] 表格、图、成本和负结果从冻结产物自动生成；
- [ ] 论文中的每一个数字都可追溯到 `freeze_id + case_id + arm + replicate + output hash`。

## 22. 最短执行顺序

若需要直接按任务卡推进，严格按以下顺序：

1. 重放 D0，保存 `M01` 历史锚点；
2. 实现 canonical dataset contract 和 gold 隔离；
3. 下载 D1–D5、生成 flow report；
4. 完成 source registry 与污染清理；
5. 实现 `M00` 单一联合 runner；
6. 实现 B02 compute-matched flat 与统一成本账本；
7. 封装 B00–B07 和罕见病工具；
8. D1a 调阈值，D1b 做联合冻结；
9. 生成 `paper_v1.freeze.json`；
10. 测试集每集 5 例健康 dry run；
11. 按随机队列运行 D2 → D3 → D4 → D5；
12. 锁定预测后评分、统计和人工审计；
13. 自动生成论文表图；
14. 按第 20 节的证据等级确定最终论文主张。
