# 事故记录：二判打分中的哨兵静默记零（2026-08-01）

## 现象

用户核对 OpenRouter 账单时发现二判（`deepseek/deepseek-v4-flash`）没有任何调用记录，触发核验。

## 结论一：调用真实，但计费主体不是 OpenRouter

`deepseek/deepseek-v4-flash` 未登记在 `src/agentclinic_tree_dx/llm_client.py` 的
`_OPENROUTER_CLIENT_MODELS`（Set A）或 `_OPENROUTER_DIRECT_POST_MODELS`（Set B）中，
因此走默认分支 → **Novita**（`https://api.novita.ai/v3/openai`，`NOVITA_API_KEY`）。

实测：返回 `model = deepseek/deepseek-v4-flash`，带 `CompletionUsage`，为真实计费调用。
一判 `google/gemini-2.5-flash` 在 Set A 内，走 OpenRouter，故账单只见一判。

## 结论二：发现更严重的静默失败路径

`RobustLLMClient.get_robust_completion` 在 3 次重试后返回哨兵串
`[Unable to generate {description} after {max_retries} attempts]`。
`judges.LLMJudge._complete` 把它当正常响应写入 `judge_cache.json`，
`parse_reasoning_matching_dict` 找不到 `matching_dict` 返回 `{}`，
`reasoning_recall_coverage` 于是得到 covered=0 → **recall = 0**。全程无异常、退出码 0。

三重危害：

1. **静默**：失败被记为一个合法分数，而不是缺失值。
2. **方向性偏差**：主方法 2 例、最强基线 3 例，其余基线最多 27 例 → 系统性压低基线、虚增我方边际。
3. **固化**：哨兵进入缓存后，`--resume-scores` 命中缓存不再重试。

失败率与并发强相关：workers=8 时 2–3 例/臂；workers=50 时 8–27 例/臂。一判（Gemini）全臂 0 例。

清点：7 个缓存目录、142 条哨兵（RR + diag_accuracy 两类）。

## 处置

1. `llm_client.py`：`deepseek/deepseek-v4-flash` 加入 `_OPENROUTER_CLIENT_MODELS`，改走 OpenRouter。
2. `judges.py::_complete`：检出哨兵即抛 `RuntimeError` 且**不写缓存**；缓存命中若为哨兵亦拒绝返回。
   `run_ox_mcr_official_eval.py` 本就按案例捕获异常并记入 `errors`，故失败案例只会"未打分"，不会"打 0 分"，且显式可见。
3. `scripts/paper/purge_judge_sentinels.py`：清除 142 条哨兵缓存条目（原缓存备份为 `*.json.presentinel`），
   并删除受影响目录的全部 case_scores 重建——缓存中的成功响应照常复用，实际只有被清除的提示重新调用 API。
4. `run_mcr_second_judge_baselines.sh`：15 臂逐臂重跑，每臂最多 4 轮直到 100 例齐全或无进展。

重跑结果：15 臂全部 100/100，缓存零哨兵，仅 B06 需第二轮补 1 例。

## 资产影响

`asset_guard verify`：17 个文件修改、0 删除，全部位于 `*_dsv4f`（二判输出）目录内。
**一判目录 `official_eval_llm` / `official_eval_llm_compat_rr` 未被触碰**，主表 R-Recall 列的来源完好。
新基线快照：`analysis/asset_guard/20260801T124856Z/manifest.tsv`。

## 对已刊数字的影响

APHHM 二判均值 0.487 → **0.4954**（此前被 2 个哨兵案例拉低）。
对 MDAgents 的边际 +0.101 → **+0.089**（MDAgents 亦修复，由 0.385 升至 0.407）。

## 连带发现：投影提取缺陷（另见 1F 小节）

`build_baseline_eval_projection.py` 只从含 `reasoning_summary` 键的节点提取推理，
导致三臂的 `pred_reasoning_trace` 退化为 `Evidence: (none recorded)`：

| 臂 | 原始 trace 是否含 rationale | 判定 |
|---|---|---|
| B07 MEDDxAgent | **有**（`diagnose.top2_diagnoses[].explanation`） | 提取缺陷，已排除出二判对比 |
| B12 Self-consistent CoT | 无（仅 `samples[].ranked` 诊断名） | 系统本身无 rationale，近零分正确 |
| B15 Medprompt-style | 无（`samples[].ranked` + 检索元数据） | 同上 |

B12/B15 与补充材料 §9 中这两臂在 Open-XDDx 解释端点得 0.000 完全一致。
