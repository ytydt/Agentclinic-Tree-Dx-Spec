# Transfer harness：Open-XDDx / MedCaseReasoning × compat + synonym_bind

顺序抽取（非随机）100 例 + DiagnosisArena 同款 staged harness。

## 子集

| 数据集 | 子集目录 | n | 扫描至 | 说明 |
|--------|----------|--:|-------:|------|
| Open-XDDx | `data/benchmarks/open_xddx/subsets/ox_seq100_v1/` | 100 | Index 113 | 选项=专家 DDx；**金标为 grounded-rationale 代理**（原数据无单标签） |
| MedCaseReasoning val | `data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/` | 100 | seq 128 | 金标=`final_diagnosis`；干扰项从 `diagnostic_reasoning` 解析 |

抽取命令（复用 `extract_diagnosisarena_subset.py`）：

```bash
PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/extract_diagnosisarena_subset.py \
    --dataset open_xddx --target-size 100

PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/extract_diagnosisarena_subset.py \
    --dataset medcasereasoning --target-size 100
```

Adapters：`open_xddx_adapter.py`、`medcasereasoning_adapter.py`。

正式指标与产物缺口（勿把本 harness 的 @1 当官方主表）：  
`analysis/transfer_metrics_v1/ox_mcr_official_metrics_and_artifact_gaps.md`。

裁判提示词编列：`analysis/transfer_metrics_v1/judge_prompts/README.md`。

门控：与 DiagnosisArena 相同 disease_name / KB 逻辑；转移集对**选项**放宽 KB（金标仍强制），以便长鉴别列表可凑满 100。

## Harness 运行

栈：`granularity-mode=compat` + mapper `--synonym-bind-repair`（默认 off 的 Approach A）。

```bash
PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/run_compat_synonym_transfer_harness.py \
    --subset-dir data/benchmarks/open_xddx/subsets/ox_seq100_v1 \
    --output-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 \
    --workers 8 --resume

PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/run_compat_synonym_transfer_harness.py \
    --subset-dir data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1 \
    --output-dir logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1 \
    --workers 8 --resume
```

日志：`.../compat_synonym_v1/run.log`；完成后看 `annotate/mapper/summary.json`（含 `synonym_bind_repair=true`）。

## 宣称注意

- Open-XDDx option @1/@2 依赖**代理金标**，不得与 Dual-Inf 官方多标签指标混报。
- 正式 DiagnosisArena 主表锚点仍为 0.72/0.78；本目录为转移复现。
