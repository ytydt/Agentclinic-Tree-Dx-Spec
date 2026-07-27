# OX emit_v1 固化与全树 R 验证（Stage 1）

配置：[`ox_emit_v1_config.json`](ox_emit_v1_config.json)
旁路树：`<run>/annotate/emit_v1_overlay/shared_trees/`

## Controller（opt-in，默认 OFF）

```json
{
  "l2_recall_gap_fill": true,
  "l2_gap_force_emit_uncovered": true,
  "l2_gap_force_emit_max": 3
}
```

## 验证

### Smoke (n=10)

| 臂 | 全树 R | Top-5 F1 |
|----|--------|----------|
| baseline | 0.6800 | 0.5200 |
| emit_v1 | 0.8000 | 0.5200 |

- Δ全树 R = **+0.1200**
- Δ后验 F1 = +0.0000（崩塌判定阈 −5pp）
- 门控：**PASS**
- 注入：30 叶 / 10 例有补叶

### Full (n=100)

| 臂 | 全树 R | Top-5 F1 |
|----|--------|----------|
| baseline | 0.7036 | 0.4582 |
| emit_v1 | 0.7910 | 0.4582 |

- Δ全树 R = **+0.0874**
- Δ后验 F1 = +0.0000（崩塌判定阈 −5pp）
- 门控：**PASS**
- 注入：284 叶 / 97 例有补叶

## 复现

```bash
PYTHONPATH=src:scripts/paper python3 scripts/paper/materialize_ox_emit_v1.py \
  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 --smoke 10
```

