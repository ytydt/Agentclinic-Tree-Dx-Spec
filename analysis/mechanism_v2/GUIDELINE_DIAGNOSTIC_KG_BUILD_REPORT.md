# 指南诊断知识图谱 v0.1：构建、质量闸门与发布报告

构建日期：2026-08-26

仓库分支：`cursor4`

发布状态：**候选主张账本 + 非排序安全视图；不是临床可用诊断 KG**

## 一、最终决策

本轮已经完成来源清洗、来源级重组、claim-aware rechunking、生产抽取队列、
LinkML/运行时 schema、确定性候选构建、citation/offset 验证、基础边语义抽检、
双模型 LLM pilot 与 fail-closed 安全导出。

但两个质量门均未通过：

1. 旧确定性/template 图的引用坐标精确，但医学语义精度不足；
2. DeepSeek v4 Flash 与 Gemini 2.5 Flash 在已知阳性小样本上的召回/拒绝率不足。

因此没有把 pilot LLM 边写回图谱，也没有启动 16,941 次全量 LLM 调用。公开
产物只作为**未审查、不可用于 ranking 的 authoring ledger**。这不是“构建失败”：
来源层、重切分层、生产队列和验证器已经构建完成；临床 assertion 层被质量闸门
有意阻止进入生产状态。

## 二、是否仍按旧 chunk 输入 LLM

否。最终路径为：

```text
raw source occurrences
  -> 清洗与来源/版本冻结
  -> 按 document/source ordinal 重组
  -> heading/paragraph/list/table 结构块
  -> 保留否定、时间、阈值、比较、k-of-n 的 claim closure
  -> 最多 12 个可引用块的 production call
  -> exact mention / occurrence / Passage offset 回投影
```

旧 chunk 只作为 provenance occurrence，不再作为 LLM 的语义单元。固定 token
overlap 被禁用；必要的标题/作用域副本为 `context_copy`，不能被引用造边。不可分
逻辑块超限时必须 quarantine，绝不做 substring 截断。

这项改造有直接数据依据：重组后发现 **10,993 个 claim blocks 跨越旧 Passage
边界**。若继续逐旧 chunk 调用，这些主张的主语、限定、列表或诊断结论仍会被
分离。

## 三、来源层

| 指标 | 结果 |
|---|---:|
| 原始 occurrences | 49,775 |
| 清洗后 occurrences | 49,547 |
| Merck ch353 附录/索引污染剔除 | 228 |
| 相同文本 occurrence 折叠 | 2,478 |
| 唯一 Passage | 47,069 |
| Section | 34,317 |
| DocumentVersion | 2,768 |
| SourceWork | 2,768 |

所有 49,547 个清洗 occurrence 都进入来源重组。来源层保留文档版本、section、
ordinal、raw id 和多 provenance；相同文本只共享 Passage identity，不共享相邻
上下文。

## 四、claim-aware 窗口与生产队列

第一层重组得到 7,432 个 windows，其中 6,492 个 eligible、940 个
`not_diagnostic`。共检测 257,484 个结构块；173,526 个可引用块进入 eligible
windows。重组覆盖 99.249% 的 admitted source characters；剩余主要是被结构解析
识别为非正文的空白。eligible windows（含 context）覆盖 89.194%，允许生成边的
primary evidence 覆盖 64.413%。这三个分母不同，不能互换为“知识覆盖率”。

production compiler 再按最多 12 个可引用块预切：

| 指标 | 结果 |
|---|---:|
| eligible parents | 6,492 |
| 原样保留 parents | 1,811 |
| 被预切 parents | 4,681 |
| children | 15,130 |
| 最终 production calls | 16,941 |
| citable blocks | 173,526 |
| citable token estimate | 8,448,204 |
| source token estimate（含必要 context） | 11,296,016 |
| 单调用 source token 中位数 / P90 / P95 / 最大 | 425 / 1,416 / 1,975 / 3,874 |
| citable block 缺失 / 重复 | 0 / 0 |
| quarantine | 0 |
| fixed-token overlap | 0 |

7,978 个可引用块跨越原 Passage，全部在输出中保留。criteria/list/table/k-of-n/
threshold/lead-in/enumeration closure 不被物理拆开。`direct_extract` 与
`upstream_only` 是 block-level 互斥标签，但 mixed window 不被粗暴拆成两个 prompt，
以免再次破坏 closure 和 offset。

## 五、确定性候选图与语义审计

基础 authoring ledger 共 95,041 条记录，其中：

| record type | 数量 |
|---|---:|
| Passage | 47,069 |
| Section | 34,317 |
| SourceWork / DocumentVersion | 2,768 / 2,768 |
| DiagnosticAssertion | 3,569 |
| DiagnosisExpression / Concept | 1,723 / 1,723 |
| EvidenceSpan | 658 |
| FeaturePattern | 445 |

3,569 条 assertion 中，3,211 条是已经声明
`listed_differential_for + enumeration_only + ranking_eligible=false` 的 WikEM
列表成员关系；358 条来自 template。

对 72 条 assertion 做独立人工链路审计：

- exact quote/offset：72/72；
- intended core relation：39/72（54.2%）；
- 严格可直接发布：5/72（6.9%）；
- Merck usable core：11/36；
- CPG usable core：8/12；
- WikEM non-ranking membership core：20/24。

主要错误是 Merck 句子型/导航型 `entry_title` 绑定、target-context lag、概念词义
错误、文献/导航污染，以及复杂逻辑全部被压为 atomic。由此得到 **no-go**：
byte-level citation 完整性不能替代医学语义正确性。

冻结的安全导出规则把 3,569 条边恰好分为：

- 5 条 template core candidates；
- 2,521 条 WikEM differential-membership pointers；
- 1,043 条 quarantine。

所有保留项仍为 `review_status=unreviewed`、`ranking_eligible=false`，且 template 与
membership 分开。宽版 `graph.public.jsonl` 也把每条 assertion 的 non-ranking 默认
显式写出，防止消费者把缺失字段误解为可用于排序。

## 六、v0.5 双模型 pilot

v0.5 对 7 个先前人工确认阳性的 root windows 加 1 个 bibliography 负对照进行
生产级重切，共 23 个调用。没有 prompt 越过 10k/12k 线。

| 指标 | DeepSeek v4 Flash | Gemini 2.5 Flash |
|---|---:|---:|
| semantic calls | 23 | 23 |
| provider tokens | 55,186 | 86,858 |
| 实付成本 | $0.007433 | $0.067356 |
| accepted assertions | 0 | 6 |
| definite-positive root coverage | 0/7 | 2/7 |
| atomically rejected responses | 6 | 12 |

Gemini 的 strict-schema transport 23/23 返回 HTTP 400，随后由 JSON-object + 同一
本地严格验证完成；DeepSeek 虽 transport 成功，仍没有 assertion 通过全部验证。
两者均远低于 ≥90% 阳性召回、<5% 拒绝和 ≥95% 严格人工精度门槛。

七轮开发/pilot 总计实际使用 **842,363 provider tokens，$0.159706**。这些费用仅
用于质量校准；失败输出未合并。

## 七、全量 token 与成本口径

生产队列本身含 11,296,016 source tokens。完整 prompt 还必须重复系统约束、候选
inventory、evidence-unit IDs 和 JSON schema，因此总输入明显高于 source tokens。

本轮对全部 16,941 单元执行无网络 dry-run 的最终计数为：

- JSON-Schema rendered input：**49,810,842 token**；
- JSON-object rendered input：**51,284,709 token**；
- 最坏模式 rendered input：**51,284,709 token**；
- 16,941/16,941 全部通过 preflight；超过 10k 软线：**0**；硬线调用在
  preflight 中直接
  拒绝，不会截断。

dry-run 的实际 tokenizer/runner source 计数为 11,263,537 token，与生产编译器的
启发式 11,296,016 相差 0.29%。若把“两模型 × schema/JSON-object 两 transport ×
每次保留完整 3,200 output”的全部失败重试都预留，调度器上界为 419,035,902
token；这是防止并发超支的 reservation ceiling，不是预期账单。

输出不能在失败 pilot 上可靠外推。若仅作容量估计，DeepSeek v0.5 pilot 的实际
output/call 与成本/call 线性外推约为 5.34M output tokens、$5.47；Gemini JSON-
object 回退约为 13.82M output tokens、$49.62。该外推混合了大量坏响应，**不是
推荐预算或可用图成本**。原方案文档中的 3.30M 中心值指“模板/规则先处理、仅将
少量复杂残差送 LLM”的理想混合路线，不适用于把 16,941 个高召回生产单元全部
交给 LLM。

## 八、发布层次

### GitHub（无 LFS）

提交：schema、构建/重组/抽取/验证/安全导出脚本、测试、设计与审计报告、
source-free public graph、residual queue、claim-window pointers、production queue、
safe views 和 source-free pilot ledgers。单文件均低于 GitHub 普通 blob 上限；
不启用 Git LFS。

### 私有 Google Drive

存放：完整 Passage/source layer、内部基础图、含原文的 claim windows、production
internal queue、超过 GitHub 普通对象上限的 block coverage audit，以及含模型
短原文的 rejection/accepted ledgers。GitHub 中的 `drive_manifest.json` 记录实际
file id、URL、bytes 与 SHA-256；不上传 OpenRouter/GitHub 凭据，也不上传原始
Merck PDF。

## 九、与金标指南覆盖审计的关系

先前 48 例人工 source-oracle 审计已经绕过 RAG 检索器直接查阅可见指南来源：
加权 D2+D3 约 51.56%，其中 decisive D3 约 21.88%；约 35.94% 只是父类、组件、
近邻、列表或名称层证据。它证明“来源本身覆盖有限”，也证明不能把图谱缺边全归
咎于 RAG。

本轮解决的是另一个问题：已有来源如何无损地进入结构化抽取。它没有把 51.56%
提升为新的诊断覆盖率，也没有用 benchmark gold 指导 admission。下一阶段必须
在全新样本上分别测 source capacity、assertion extraction recall、graph retrieval
recall、上下文利用和最终诊断增益。

## 十、下一步 go/no-go 实验

1. 100–150 个新 windows 双人完整标注，不能只审模型输出；
2. 把 ordinary diagnostic、definition、test interpretation、pairwise differential
   拆成小 schema；
3. 模型只选择 candidate/mention/role/logic，surface/offset/direction 由 runner 编译；
4. block-level 诊断关系 gate 与 extractor 分开评估；
5. occurrence/candidate 错误做同 evidence-unit 定向 repair；
6. 每个主来源 lane 的 core precision ≥95% 且 Wilson 下界 ≥90%，引用精度 100%，
   阳性召回 ≥90%，原子拒绝 <5% 后，才允许合并和全量扩展；
7. 最终与 raw-chunk RAG 做等 source-token、等模型、等检索候选的配对实验。

在这些条件通过前，当前 KG 的正确用途是审计、schema/检索开发和人工 authoring，
不是临床判断或自动候选排序。
