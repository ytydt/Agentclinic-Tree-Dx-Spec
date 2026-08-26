# 指南诊断 KG：v0.5 双模型质量闸门审计

审计日期：2026-08-26

语义输入：`guideline-kg-production-extraction-queue-v1`

抽取器：`guideline_kg_citation_bounded_residual@0.5.0`

## 结论

**不启动全量 LLM 抽取。** 重新聚拢来源、按 claim closure 重切分后，
上下文截断已不再是本轮失败的合理解释；但 DeepSeek 与 Gemini 仍没有达到
预注册的阳性召回、原子拒绝率和严格结构精度门槛。把这些输出合并进主图只会
产生一个可引用但严重欠覆盖、且含结构错误的图谱。

本轮因此只发布：无损生产队列、source-free 调用/拒绝账本、未审查的安全候选
视图以及 quarantine。任何 pilot assertion 都没有写回发布图谱。

## 1. 为什么这不是旧 chunk 截断问题

生产编译器先按来源顺序重组，再在完整主张块边界切分。23 个 pilot 调用满足：

- 每次最多 12 个可引用 claim blocks；
- 23 次 source payload 合计 16,428 估算 token；
- 最坏渲染 prompt 合计 69,305 估算 token；
- 没有调用越过 10,000-token 软线或 12,000-token 硬线；
- 超限策略是显式拒绝，代码中不存在 substring/token truncation；
- 标题和作用域副本只能作 context，不能成为 citation；
- 引用必须通过原 Passage 半开区间逐字符回投影。

因此，本轮仍出现的空响应和拒绝主要属于模型/抽取契约、候选绑定和输出结构
问题，而不是命中后上下文被截短。

## 2. Pilot 设计

选择七个在 v0.4 人工 oracle 中已确认含明确诊断信息的 root windows，并加入
一个 GINA bibliography-heavy 负对照。生产编译后共有 23 个调用单元：19 个来自
七个 definite-positive roots，4 个来自负对照。七个阳性类别覆盖疾病定义、典型
表现、检查/影像、检验解释、时序及鉴别信息，来源包括 ACOG、GINA、IDSA、
Merck、RCOG。

两模型使用同一输入、prompt、candidate inventory、temperature=0 和验证器，
分别独立运行：

- `deepseek/deepseek-v4-flash`，OpenRouter throughput routing；
- `google/gemini-2.5-flash`，同一 routing。

共同安全设置为 `data_collection=deny`，严格 schema 请求设置
`require_parameters=true`。每个模型最多返回 12 条 assertion，输出预算 3,200
token；容量不足必须返回 resplit 状态，禁止以 partial prefix 冒充 complete。

预设 go 条件为：definite-positive window/root 召回至少 90%，已裁决假空不超过
5%，原子拒绝率低于 5%，人工临床/原文忠实精度至少 95%，引用/offset 精确率
100%。

## 3. 结果

| 指标 | DeepSeek v4 Flash | Gemini 2.5 Flash |
|---|---:|---:|
| 语义调用 | 23 | 23 |
| 物理尝试 | 23 | 46 |
| provider success | 23 | 23 |
| provider error | 0 | 23 |
| provider-reported token | 55,186 | 86,858 |
| 实付 pilot 成本 | $0.007433 | $0.067356 |
| 模型报 `nothing_extractable` | 17 | 9 |
| 被闸门隔离的高信号空响应 | 15 | 8 |
| 原子拒绝的响应 | 6 | 12 |
| 接受的 assertion | 0 | 6 |
| 覆盖 definite-positive roots | 0/7 | 2/7 |

Gemini 的 23 个 strict JSON-Schema 请求全部 HTTP 400；同一语义调用随后在
带完整 schema 的 JSON-object 模式成功。因此 46 次物理尝试只对应 23 次语义
调用。这个兼容性回退没有放松本地 closed-inventory、citation、offset 或全图
验证。

DeepSeek 的输出没有一条通过全套原子验证。Gemini 的六条 assertion 全部集中
在两个 RCOG roots（vasa previa 与 placenta praevia），没有覆盖其余五个明确
阳性 roots。按 root 计算的 2/7=28.6% 远低于 90% 门槛。

两模型合计的拒绝原因以 occurrence index 越界为主，另有缺少显式诊断上下文、
把诊断名本身当 feature、不安全 unresolved target 和复合 component index 越界。
这些记录均原子隔离，没有从坏响应中挑选看似正确的局部边。

## 4. 六条接受边的人工复核

单人 source-oracle 复核认为六条都保留了原文的核心 target–finding 关系，且
offset/quote 机械验证为 6/6；但至少两条仍有严格结构问题：

1. “pulsating fetal vessels inside the internal os” 被拆成两个 AND operand，
   把解剖位置误作独立 feature；
2. antenatal ultrasound 被表示成 `typical` imaging feature，混合了诊断过程与
   患者表型。

故严格结构精度至多为 4/6；即使只按宽松 core 关系计 6/6，样本也只有两个
root、未经双人盲审，不能满足 95% 发布门槛或证明跨来源泛化。

## 5. 与 v0.4 的机制区别

v0.5 确实修复了若干工程问题：

- `direction` 不再交给模型，而由 diagnostic role 机械派生；
- occurrence 越界只在 exact surface 唯一出现时允许可审计修复；
- 高信号空响应进入独立 confirmation ledger，永不进入 success cache；
- 主动预切到最多 12 个可引用块，而不等待模型自行请求 resplit；
- Gemini strict schema 失败时可进入 JSON-object transport，并继续执行相同本地
  验证。

这些修复防止了静默污染，却没有使两个低成本模型在当前“大一统 assertion
schema”下达到可用召回。换言之，**安全性提高了，产出率仍未合格**。

## 6. 下一轮最小实验

在任何全量调用前，应先做一个独立的新鲜、双人标注 pilot，并拆分抽取任务：

1. 将普通 diagnostic assertion 与 pairwise differential 分成两个小 schema；
2. 模型只返回 `candidate_id + mention_id + role + logic class`，surface、label、
   direction、offset 和局部组件由 runner 编译；
3. 先做 block-level “是否含可表示诊断关系”的二元 gate，再对阳性块抽取；
4. 对 occurrence/candidate 失败只做同一 evidence unit 的定向 repair，不重跑整窗；
5. 至少 100–150 个新 windows，按来源、显式/隐式关系、逻辑类型和 admission lane
   分层；其中 30–50 个 DeepSeek/Gemini 配对；
6. 继续使用本文 go/no-go 阈值，并报告 token/人工有效 assertion，而非边总数。

本轮完整 source-free selection、preflight、telemetry、rejection、needs-review 与
accepted-pointer 账本位于：

`data/knowledge_graph/guideline_diagnostic_kg_v0_1/quality_audit/model_pilot_v05/`

含模型输出原文的私有 rejection ledger 不进入 GitHub，只进入授权的私有归档。
