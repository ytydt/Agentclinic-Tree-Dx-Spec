# 阶段 3：MAC / DualInf 高 @1 转化机制卡片

**代码**：`scripts/paper/baseline_arms.py`（`run_b04` / `run_b06`）；RRF 回退 `scripts/paper/baseline_aggregate.py`。  
**协议背景**：开放 vignette → Top-2（见 `diagnosisarena_d2_seq100_baselines_summary.md`）。

## 机制卡片 A — Dual-Inf（B04）

| 字段 | 内容 |
|------|------|
| 输入 | vignette；迭代产出 disease→support reasons |
| 流程 | forward → backward recall → examine 精炼 → 可选 reflect（low-conf） |
| 打分式 | `_rank_by_support`：按 **support 条数降序**，并列按名称 |
| 破平 / 自信 | `beta=2`：reasons≤β 标 low-conf，触发 reflect 再跑一轮 |
| Top2 取出 | 优先 parse examine Top2，否则用 support 排序 |
| 对同义叶 | **部分失效**：名称不同但临床同义时，条数破平仍可能随机；无树结构合并 |
| 对粗叶多选项 | **失效**：开放生成不经 MCQ 叶绑定；不能在「单叶绑多选项」结构上创造可分性 |
| 可迁移钩子 | joint 后对 Top-K 叶做 examine 风格 support/contradict 计数；近并列才 reflect/pair |
| 与本方法兼容 | 高：封闭候选 + 计数破平；须加 **Top2 集合护栏** |

## 机制卡片 B — MAC single-vendor（B06）

| 字段 | 内容 |
|------|------|
| 输入 | vignette；3 医生轮询讨论历史 |
| 流程 | Doctor A/B/C 各出有序列表 → **Supervisor** 综合 Top-2 |
| 打分式 | Supervisor LLM 综合；失败则 `rrf_aggregate(doctor_lists)` |
| 破平 | 多列表 RRF / supervisor 显式裁决 |
| 对同义叶 | Supervisor 可语义合并，但 **无保证**；RRF 对近同义字符串仍当不同项 |
| 对粗叶多选项 | **失效**（同 DualInf：开放列表协议） |
| 可迁移钩子 | 仅当 Top1–Top2 分差 &lt; τ 时做 **pair adjudicate**（只交换顺序）；勿嵌入整段多医生建树 |
| 与本方法兼容 | 中高：只借用 pair/RRF 破平，不借用开放重生成 |

## 与 2b / 2c 兼容性

| 本方法根因 | Dual support 重排 | MAC pair | 粒度支线 |
|------------|-------------------|----------|----------|
| 纯排序 | ✅ 首选 | ✅ 辅 | — |
| Fine 同义挤占 | ❌ 不足 | ⚠️ 偶发 | ✅ Merge |
| Coarse 多选项 | ❌ 禁止当唯一对策 | ❌ | ✅ Subdivide |
| L2 相对 L1 伤 @1 | 可与 L1 fallback 组合 | 可 | — |

## 可迁移算子清单（阶段 5 采用）

1. `support_count_rerank`（Dual-Inf）  
2. `pair_adjudicate`（MAC supervisor 缩小版）  
3. `rrf_break_tie`（仅作 pair 失败回退，可选）  
4. **明确不迁移**：整段多医生讨论嵌建树；开放 vignette 重生成主诊断列表

产出完成：本文件。
