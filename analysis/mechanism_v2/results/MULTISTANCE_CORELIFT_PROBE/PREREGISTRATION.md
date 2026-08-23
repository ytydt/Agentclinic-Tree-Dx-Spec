# 预注册：MultiStance × CoreLift 200 例探针

实验 ID：`MULTISTANCE_CORELIFT_PROBE_V1`  
日期：2026-08-20  
性质：**机制探针，不是确证试验。** n=100/族，McNemar 只作描述，不设硬 Go/No-Go。

## 1. 队列（冻结后不得改）

- 切片：holdout-200b，**不是**选出 MultiStance 的 dev 200。
- 抽样：`sha256(multistance-corelift-probe-v1 | family | source_id)` 升序，每族取 100 例。
- 入选条件：规范化 vignette、gold、非空 MultiStance registry。排名**不看** gold 对错。
- DA 日志：`logs/backbone_v1/diagnosisarena_heldout200b/aphhm_c_multistance_v1/case_stages`
- MCR 日志：`logs/backbone_v1/medcasereasoning_200b/aphhm_c_multistance_v1/case_stages`
- gold：`analysis/backbone_v1/r4_facts/pooled.tsv`（仅 analyze 使用）

## 2. 装置（冻结）

- MultiStance ~9 候选 registry **冻结**；不重跑三取向生成。
- 每例 **1 次** append-only 补全（三臂共享）。
- 三臂 **同一** CoreLift lite 选择器。
- 补全模型：`google/gemini-2.5-flash`
- 选择器：`meta-llama/llama-3.3-70b-instruct`（与 MultiStance / APHHM-C `DEFAULT_MODEL` 相同）。
  **不使用** CoreLift 的 DeepSeek 选择器：那是新比较器，且本环境 300s 超时 / `finish_reason=length` 把 25 并发打成近似串行。
- 并发：25 workers（与 MultiStance 运行档同量级；脚本侧 APHHM-C 为 32，本探针取用户指定的 25）。
- 禁止 C2 merge、C4 关系边、资格化缩窄、C1 residual。

## 3. 三臂

| 臂 | 池 |
|---|---|
| `union` | 冻结父类，不加补全 |
| `replace` | 有效补全则父类退出、子类进入；宽度守恒 |
| `parallel` | 父类与子类并列；额外槽最多 +3 |

`parallel` 是负对照，不把它的正结果读成「宽池上该上 CoreLift」。

## 4. 门控

- `support_spans` 必须是 vignette 逐字子串，否则丢弃该补全。
- 子类不得与父类或其他候选 `equivalent`。
- 每父类最多一个子类。
- 选择器 `champion_id` 必须在供给 ID 内；越界计服务失败，回退到排序第一项，**不用 gold 兜底**。
- `decisive_items` 非逐字子串、`rejected` 含未知 ID 等附属字段记 quality flag，**不**把整次选择打成未服务（Llama CoreLift 旧链 12–18% 未服务即来自该过严门）。
- 在线 payload 禁止 gold / options。

## 5. 预注册预测

1. `replace` 宽度 = `union` 宽度。
2. `parallel` 宽度 > `union` 宽度。
3. `replace` 池召回 ≥ `union`。
4. `parallel` 转化 ≤ `union` 转化。
5. DA 上 `replace` concept ≥ `union` concept。

主端点按族分报：concept top-1、池召回、条件转化、均宽、服务率。  
MCR 上 CoreLift 原实验无收益，本探针**不预期** MCR task 上涨。

## 6. 调用预算

200 例 ×（1 补全 + 3 选择）= **800** 次在线调用。workers 默认 25。
