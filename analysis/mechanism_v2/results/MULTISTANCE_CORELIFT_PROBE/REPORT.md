# MultiStance × CoreLift 200 例探针

实验 `MULTISTANCE_CORELIFT_PROBE_V1`。holdout-200b，DA/MCR 各 100。冻结 MultiStance registry；每例一次共享 append-only 补全；三臂共用与 MultiStance 相同的 Llama 3.3-70B lite 选择器。

## 运行诊断（本轮修补）

DeepSeek 选择器被停用。阻塞原因：

1. **比较器不公平**：CoreLift 默认 `deepseek/deepseek-v4-flash-0731` 不是 MultiStance/APHHM-C 基线（`meta-llama/llama-3.3-70b-instruct`）。
2. **吞吐崩掉**：DeepSeek 大量 `finish_reason=length` 与 300s 超时；12 并发被重试占满，看起来像串行。当时选择器约 362/600，ETA 以小时计。
3. **未服务风险**：Llama CoreLift 旧链 12–18% 未服务来自 `decisive_item is not a verbatim vignette span` 把整次选择作废。本探针把**服务条件收成「champion_id ∈ 供给池」**；非字面子串只记 quality flag。

修补后：25 并发、超时 180s、`max_retries=1`、选择器缓存与 DeepSeek 隔离。600 次 Llama 选择在约 40s 内打完。

## 服务率

| 族 | union | replace | parallel | 未服务条件数 | quality flags |
|---|---:|---:|---:|---:|---|
| DA | 1.00 | 1.00 | 1.00 | 0 | 非字面 decisive 1；未知 rejected id 1 |
| MCR | 1.00 | 1.00 | 1.00 | 0 | 非字面 decisive 2；decisive 截断 1 |

未服务没有再现。附属字段噪声极低，没有再把它们升级成硬门。

## 预注册预测

1. `replace` 宽度 = `union` — **成立**（DA 9.13=9.13，MCR 8.75=8.75）。
2. `parallel` 宽度 > `union` — **成立**（DA 10.46，MCR 9.51）。
3. `replace` 池召回 ≥ `union` — **不成立**（DA 0.60→0.40；MCR 0.53→0.50）。
4. `parallel` 转化 ≤ `union` — **不成立**（MCR 0.396→0.434；DA 略降 0.317→0.279）。
5. DA 上 `replace` concept ≥ `union` — **不成立**（0.19→0.13，Δ −6pp，p=0.146）。

补全接受 223 条（1.115 / 例）。McNemar 均为描述性，n=100/族。

## 结果表

### DA n=100

| arm | width | pool recall | conversion | concept | served |
|---|---:|---:|---:|---:|---:|
| union | 9.13 | 0.60 | 0.3167 | 0.19 | 1.00 |
| replace | 9.13 | 0.40 | 0.3250 | 0.13 | 1.00 |
| parallel | 10.46 | 0.61 | 0.2787 | 0.17 | 1.00 |

- `replace_vs_union`: 3-9，Δ −6.00pp，p=0.146
- `parallel_vs_union`: 3-5，Δ −2.00pp，p=0.727

### MCR n=100

| arm | width | pool recall | conversion | concept | served |
|---|---:|---:|---:|---:|---:|
| union | 8.75 | 0.53 | 0.3962 | 0.21 | 1.00 |
| replace | 8.75 | 0.50 | 0.3800 | 0.19 | 1.00 |
| parallel | 9.51 | 0.53 | 0.4340 | 0.23 | 1.00 |

- `replace_vs_union`: 1-3，Δ −2.00pp，p=0.625
- `parallel_vs_union`: 5-3，Δ +2.00pp，p=0.727

## 怎么读

- **不要**把 `parallel` 的 MCR +2pp 读成宽池上该上 CoreLift；它是负对照，且未过描述性 McNemar。
- DA 上 `replace` 池召回掉 20pp：父类被换成子类后，gold 匹配从父类级同义变成更窄、但不等于 gold 的完成体。这与「均宽 ~9 的宽池上纵向补全会伤覆盖」同向。
- 选择器已与 MultiStance 同模型；补全仍是 Gemini 2.5 Flash（三臂共享，不进入选择器比较）。

产物：`freeze.json`、`completions.json`、`scored.json`、`summary.json`、`selector_cache_llama/`。DeepSeek 半成品在 `selector_cache_deepseek_abandoned/`，不进入本报告。
