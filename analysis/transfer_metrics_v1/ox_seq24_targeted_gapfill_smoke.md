# OX seq24：标准管线叠加 targeted L2 gapfill 烟测

状态：live smoke 完成（research_only）  
日期：2026-07-26  
栈：`compat_parallel` + `synonym_bind` + **`--targeted-l2-gapfill ALL_B_b1`**  
队列：`ox_seq100` 顺序前 24 例（`1…18,20…25`；对齐 DA pilot24「先 24 live」惯例）

## 1. 接线（默认 OFF）

| 入口 | 作用 |
|------|------|
| `scripts/paper/targeted_l2_gapfill_overlay.py` | Config A 之后、joint 之前叠 hybrid `ALL_B_b1` |
| `run_diagnosisarena_downstream_top2.py --targeted-l2-gapfill` | annotate 钩子 |
| `run_diagnosisarena_pipeline_staged.py` / transfer harness | 透传 flag |
| `run_ox_targeted_gapfill_smoke24.py` | OX 24 例烟测启动器（复用 seq100 frozen） |

产物根：`logs/open_xddx_ox_seq24_smoke_v1/compat_synonym_gapfill_v1/`

## 2. 跑通结果

| 阶段 | 结果 |
|------|------|
| annotate | **24/24 OK**；`targeted_l2_gapfill.enabled=true` 全例 |
| mapper（synonym_bind） | **24/24 OK** |
| 开放 lexical（`compat_then_pad`） | **24/24** scored |
| 墙钟 | ~27 min（workers=8；复用 seq100 annotate cache） |

补叶量：**仅 1/24 例实际加叶**（case `8` 加 `vomiting`）；`mean_n_added=0.042`。  
→ Config A 生成期补叶后，targeted 二次补叶在本 24 例上几乎无空间。

## 3. 对照同 ID 的 seq100 基线（无 gapfill）

| 指标 | 基线 seq100 同 24 | +gapfill smoke | Δ |
|------|-------------------|-----------------|---|
| mapper option@1 | 0.875 | 0.875 | **0** |
| mapper option@2 | 0.917 | 0.875 | **−0.042** |
| human label@1 | 0.375 | 0.375 | 0 |
| human label@2 | 0.417 | 0.375 | −0.042 |
| open lexical μP / μR / μF1 | 0.467 / 0.500 / 0.483 | 0.475 / 0.509 / 0.491 | μF1 **+0.009** |

开放评测：`annotate/official_eval_compat_then_pad/summary.json`（lexical；非 paper-official LLM）。

## 4. 烟测裁定

- **管线叠加可用**：flag 默认 OFF；OX 24 live 端到端通过。
- **效果弱**：几乎不加叶；mapper@1 持平，@2 略降；开放 μF1 仅 +0.9pp（噪声级）。
- **不可 promote**：仍 `research_only`；未过 DA/OX 主表门控；与可用性文档一致。
- **对 OX C 类真缺失**：本 24 例未表现出有效补洞（需更大 / 按 recall miss 分层抽样，或换 GR/gates 臂再测）。

## 5. 复现

```bash
# 1-case ultra-smoke
PYTHONPATH=src:scripts/paper:scripts \
  python -u scripts/paper/run_ox_targeted_gapfill_smoke24.py \
  --n-cases 1 --workers 1 \
  --output-dir logs/open_xddx_ox_seq24_smoke_v1/compat_synonym_gapfill_n1_v1 \
  --from-stage annotate --to-stage annotate

# 24-case live（惯例）
PYTHONPATH=src:scripts/paper:scripts \
  python -u scripts/paper/run_ox_targeted_gapfill_smoke24.py \
  --n-cases 24 --workers 8 --run-official-eval
```

单元测试：`tests/test_targeted_l2_gapfill_overlay.py`（4 passed）。
