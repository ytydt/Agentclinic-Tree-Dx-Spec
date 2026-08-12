# E2 reviewer B 运行审计

- 冻结病例：400；与 reviewer A 使用同一 blinded cards SHA-256
  `778cb28e080fb808a159fb95ca20476619b586462f1bddb4b919e0e44422fd17`。
- 审阅模型：`deepseek/deepseek-v4-flash-0731`；角色仅为方法盲临床分包审阅员。
- 并发：50（非 RAG 上限）；未观察到进程风暴。
- 结果：400/400 schema-valid；400 个 semantic calls、406 个 physical attempts。
  6 例发生同一语义调用内的 JSON 解析重试并恢复，没有最终失败。
- 路由：`TREE_DX_PROXY_MODE=environment`，`auto → stdlib_openrouter` 依赖回退；
  provider association 分散到 24 个 OpenRouter provider，其中没有任何单点承载多数请求。
  没有地区不支持、数据中心 IP 阻断或不可恢复限流。

reviewer B 与 reviewer A 的 identifiability 初始分布明显不同：B 把 180 例判为
`family_only_not_full_specificity`，A 为 61；A 把 155 例判为
`unsupported_reference_specificity`，B 为 55。该差异不是可直接平均的“模型噪声”，
而是 reference 可识别性定义边界的实质分歧。全部 case-level 分歧须进入根审计；任何
一个代理的多数或置信度都不能自动成为最终标签。

relation/identifiability 计数仍只是分包输出描述。根审计在冻结病例证据裁决之前不得用
臂名、strict/task 标记或方法总体表现影响单例关系判断。
