# E2 reviewer C 运行审计

- 冻结病例：400；blinded cards SHA-256
  `778cb28e080fb808a159fb95ca20476619b586462f1bddb4b919e0e44422fd17`。
- 审阅模型：`openai/gpt-4.1`；这是在稀疏 reviewer-consensus 校准被反例推翻后
  增加的事后异质分包审阅员，不改变已冻结的根级补充审计范围，也不以多数票代替
  根判定。
- 并发：50（非 RAG 上限）；未观察到进程风暴。
- 结果：400/400 schema-valid；400 semantic calls、400 physical attempts，零重试、
  零 HTTP/解析错误。OpenRouter provider association 为 OpenAI 399 次、Azure 1 次，
  所有状态码均为 200。
- 用量：438,463 input tokens、262,995 output tokens。
- 路由：`TREE_DX_PROXY_MODE=environment`、`TREE_DX_LLM_TRANSPORT=stdlib`。
  当前最小环境没有官方 `openai` 包，故使用仓库的依赖缺失回退；同一客户端仍保留
  由 `TREE_DX_LLM_TRANSPORT=openai` 选择官方 OpenAI SDK 的原环境路径。未使用
  仓库 VPN/Clash，也未观察到地区、机房 IP 或单 provider 衰退错误。

Reviewer C 的输出只作为高召回反证来源。最终 E2 关系端点仍要求根审计覆盖全部
非精确候选—参考对；本臂本身不构成临床真值。
