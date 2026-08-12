# E10 MAC 2×2 因子实验：冻结分析计划

## 研究问题

B06 的三医生 MAC 轨迹把两个机制绑在一起：Doctor B/C 顺序读取前文，以及 LLM Supervisor 对三份列表再聚合。E10 将其拆成 `isolated/sequential × RRF/supervisor`，判断低多样性究竟来自生成端的信息级联、聚合端的偏好压缩，还是两者交互。

这是一项机制开发实验，不是新确认集；病例严格复用 E4 在任何在线调用前冻结的 DA 200 + MCR 200。

## 因果隔离

- Doctor A 的原始响应在两种 history 条件间逐字节复用。
- Doctor B/C 的模型、system prompt、姓名和干净 vignette 相同；唯一处理变量是空历史或此前有效医生的讨论。
- 在每个 history 条件内，RRF 与 Supervisor 使用同一冻结 doctor output、同一 exact-synonym canonical union。
- Supervisor 只能从随机稳定编号的 union 中选择两个 ID，不能产生新诊断；因此比较的是聚合而不是额外候选生成。
- RRF 使用 `k=60`，按 canonical concept 累加，平分时按冻结 key 排序。

## 终点与可证伪判据

主终点为 frozen-exact-synonym pre-mapper Top-1/Top-2、union reference exposure、exposure→Top-2 conversion，按病例成对报告净胜负与 exact McNemar。机制终点为 union 宽度、医生两两 Jaccard、D2/D3 新增 concept、后续 top-1 回声、整表复制和 aggregation loss/rescue。

C006 的双重否证条件是：隔离 history 既不提高 unique recall/union 宽度也不降低 Jaccard，且固定医生输出下 RRF 与 Supervisor 的 conversion 无差异。单纯输出翻转不视为临床改善；所有严格终点分歧进入逐例根审计。

## 运行和失败策略

- 模型：`meta-llama/llama-3.3-70b-instruct`，OpenRouter provider primary 在 Groq/DeepInfra 间平衡轮换，transport retry 反转顺序，禁止 Novita；不采用 Groq 单点。
- 非 RAG 并发上限 50，本实验使用 50。
- 保留官方 OpenAI SDK transport 选项；本容器缺依赖时由仓库 `RobustLLMClient` 的 stdlib fallback 执行。
- 无 gold/options 在线外发。无 gold fallback。无效医生从 union 排除但病例保留；无效 Supervisor 计错。
- 不进行重复多次运行、不扩容确认集、不统一 provider/retry 等纯降方差实验。
