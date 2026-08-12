# E2 reviewer A 运行审计

- 冻结病例：400；blinded cards SHA-256
  `778cb28e080fb808a159fb95ca20476619b586462f1bddb4b919e0e44422fd17`。
- 审阅模型：`google/gemini-2.5-flash`；角色仅为方法盲临床分包审阅员。
- 并发：50（非 RAG 上限）；未观察到进程风暴。
- 结果：396 个 schema-valid，4 个 fail-closed；400 个 semantic calls、400 个
  physical attempts，全部 provider association 为 Google。
- 路由：`TREE_DX_PROXY_MODE=environment`；`auto` 因当前环境没有官方 `openai`
  包而进入仓库保留的 `stdlib_openrouter` 回退。没有 Google 地区不支持、数据中心
  IP 阻断、429 或 transport 重试。

四个失败为 `DA_d2_seq100/202`、`MCR_seq200b/330`、
`MCR_seq200b/369`、`MCR_v2_seq100/229`。模型把
`case_quality_flags` 返回为非列表；候选关系内容仍保存在原始 review 中，但预注册
validator 将整例标为失败。为保持不可变调用和 ITA，未删除缓存重抽。这四例必须进入
根审计，且 reviewer A 的代理端点不得把它们从分母移除。

当前 relation/identifiability 计数只是分包输出的描述，不是最终临床端点。根审计在
冻结关系裁决前不能用臂名或已有 strict/task 标记影响判断。
