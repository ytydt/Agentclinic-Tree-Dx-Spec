# Payload 瘦身方案（P0–P2）

## 背景与问题

完整 pipeline 在高 turn 数下向 LLM 模块发送的 USER payload 无界增长，最终突破 qwen3-32b 的上下文窗口，触发 `Token limit exceeded` → 180s 超时 → 5×futile 重试，是 case 17 等"马拉松"耗时数小时的根因。

实测（`scripts/analyze_payload_breakdown.py` / `scan_max_payload.py`）单次 payload 的部件构成（token）：

| 部件 | 典型/峰值 tok | 占比 | 性质 |
|---|---|---|---|
| `actions_taken` | 578 / **5945** | ≤45% | 逐轮追加整段 `result_summary` 散文，无界增长 |
| `branches` | 3764 / 3786 | 28–42% | 全分支携带 `rationale`/`evidence_*` 散文 |
| `lr_reference` | 1200 | 13% | 注入知识（必要但冗长） |
| `static_evidence_items`+`case_summary`+`static_vignette` | 757+301+230 | ~13% | **同一病历三份拷贝** |
| `raw_result` | 872 | 10% | 回灌的原始 LLM 输出 |
| `differential_history` | 460 | 3–5% | 累积快照，与当前 branches 冗余 |
| `candidate_leaves` | 1013（RootSelector） | 8% | 非消费方无需 |
| ~25 个空/标量字段 | 各 1 | — | 序列化噪声 |

`RootSelector` 尤其严重：经 `_root_selector_payload` 走 `state.to_dict()`（全量，未压缩），被喂入 `actions_taken`(5945)+`branches`(3786)+`candidate_leaves`(1013) ≈ 10.7k tok，而它仅需病历+选项。

## 设计原则

1. **投影而非全量**：以 `state.project_for(module)` 替代各处 `state.to_payload()`/`to_dict()` 全量倒出；每模块按策略取字段。
2. **散文转结构**：膨胀全在自然语言（`result_summary`/`rationale`/`evidence_*`），蒸馏为有界结构化信号而非整段丢弃。
3. **病历单一真相源**：保 `static_evidence_items`（结构化原子事实）+ 截断的 `case_summary`；删冗余 `static_vignette`。
4. **偏差接口前置预留**：不删未来"防锚定/确认偏差"部件所需历史，而是蒸馏进**固定、有界、立即填充**的 `reasoning_ledger` 块。瘦身与可扩展由此统一。
5. **无损原子证据**：`_gather_atomic_findings` 改用 VignetteParser 已解析的 `static_evidence_items[*].content`（无损边界）做检索，替代对原始文本的 phrase-split + embedding（有损、引噪）路径。
   - **两阶段映射（B1 接入，见 `B1_LAB_NORMALIZATION_PLAN.md` §12）**：每条原子事实先过 `FindingNormalizer`（数值方向感知：`35% blasts → Elevated blast count`），正常生命体征直接跳过以杜绝方向盲误映射；归一化未识别的定性 finding 再走受控词表嵌入匹配，无映射时无损回退原文。

## P0 — 机制层

- `DiagnosticState.project_for(module, max_action_records=6) -> dict`：在压缩基底上按 `_MODULE_DROP[module]` 删除该模块不需要的重字段，并始终附带 `reasoning_ledger`。
- `Controller._state_payload(state, module)` 包装；所有 `_call_module` 的 state 入参改走它。
- `RootSelector` 改用 `project_for("RootSelector")`（含选项脱敏逻辑），剔除 `actions_taken/branches/candidate_leaves/...`。
- `llm_client._MAX_TOKENS_BY_MODEL` 补 `qwen/qwen3-32b`；token 超限**快速失败**（不再 5×180s 空转）。

## P1 — 压缩

- `actions_taken` → 结构化账本：每条 `{t,type,content(≤200ch),summary(≤300ch)}`，保最近 6 条。
- `branches`(active)：`evidence_for/against` 各保 1 条且截 ≤160ch；`unresolved_questions` ≤2 条 ≤120ch；剔除 `reopen_triggers`/`askable_discriminators`/`requestable_discriminators` 等内部冗长字段。closed/parked 维持精简 stub。
- 病历：删 `static_vignette`；`case_summary` 截 ≤800ch（RootSelector 例外，保留脱敏后的完整叙述）。
- `differential_history` → 数值 top-3 `[{t, top:[[label,prob]...]}]`，保最近 3。

## P2 — 偏差缓解接口

`reasoning_ledger`（由 state 自身字段派生，零额外 LLM 成本，有界 ~300–500 tok），始终下发，schema 稳定：

```json
"reasoning_ledger": {
  "anchor":          {"hypothesis": "...", "t": 0, "posterior_at_anchor": 0.0},
  "leader":          {"branch_id": "B?", "label": "...", "posterior": 0.0,
                      "leading_since_t": 0, "n_revisions": 0},
  "leader_evidence": {"confirming": 0, "disconfirming": 0,
                      "last_disconfirming_digest": "..."},
  "action_intents":  [{"t": 0, "intent": "confirm|refute|broaden"}],
  "considered_alternatives": ["B2", "B3"]
}
```

- **防锚定**消费 `anchor` + `leader.leading_since_t/n_revisions`（领先者是否长期未被修正）。
- **确认偏差**消费 `leader_evidence`（for/against 平衡）+ `action_intents`（是否只挑能证实的检查）。
- 当前模块不读该块；以"空读测试"锁定 schema，未来部件挂载无需改编排。

## 验证

- 复测 `analyze_payload_breakdown.py`：目标单次 user payload p95 < 8k tok，峰值 `actions_taken`/`branches` 不再无界。
- 回归：`tests/` 既有用例 + 新增 `test_payload_slimming.py`（投影白名单、账本 schema、原子证据无损提取）。
