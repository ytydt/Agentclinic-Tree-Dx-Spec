# Transfer formal metrics (OX / MCR)

离线评测：在已完成的 `compat_synonym_v1` run 上构建 `eval_projection` 并计算 OX/MCR 正式形态指标。

## 快速开始（lexical，默认可复现）

```bash
# Open-XDDx
python3 scripts/paper/run_ox_mcr_official_eval.py \
  --dataset open_xddx \
  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 \
  --subset-parquet data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet \
  --judge lexical --ddx-k 5 --build-projection

# MedCaseReasoning
python3 scripts/paper/run_ox_mcr_official_eval.py \
  --dataset medcasereasoning \
  --run-dir logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1 \
  --subset-parquet data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/cases.parquet \
  --judge lexical --build-projection
```

产物：

| 路径 | 内容 |
|------|------|
| `annotate/eval_projection/{id}.json` | Top-K 叶 DDx + P5 模板解释/推理 |
| `annotate/official_eval/case_scores/{id}.json` | 逐例分数 |
| `annotate/official_eval/summary.json` | 汇总（含 `protocol`） |

- lexical → `protocol=compatible_metrics_lexical_v1`（**非** official）
- llm → `protocol=paper_aligned_judge_v1`，`judge_model=gemini-2.5-flash`

## LLM judge

契约：[`judge_prompts/JUDGE_MODEL_CONTRACT.md`](judge_prompts/JUDGE_MODEL_CONTRACT.md)

| 项 | 冻结值 |
|----|--------|
| 环境 | `conda activate gnn-llm` |
| VPN | `bash /home/wanghongyi/clashctl/clashon.sh`（`clashon`） |
| 并发 | **`--workers 50`**（`--judge llm` 时 CLI 默认；`0` 亦解析为 50） |

```bash
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate gnn-llm
bash /home/wanghongyi/clashctl/clashon.sh

python3 scripts/paper/run_ox_mcr_official_eval.py \
  --dataset open_xddx \
  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 \
  --subset-parquet data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet \
  --judge llm --ddx-k 5 --workers 50
```

## 代码入口

- `scripts/paper/build_eval_projection.py`
- `scripts/paper/run_ox_mcr_official_eval.py`
- `scripts/paper/transfer_eval/`（matching / judges / ox_metrics / mcr_metrics / io_gold）

调研与缺口：[`ox_mcr_official_metrics_and_artifact_gaps.md`](ox_mcr_official_metrics_and_artifact_gaps.md)。

C2a（入口已知未落叶）离线改进：[`ox_c2a_force_emit.md`](ox_c2a_force_emit.md)（`l2_gap_force_emit_uncovered` opt-in）。

评测侧短列表臂（`--ddx-source`）：`posterior`（默认）、`compat`、`compat_then_pad`、`gate_on_post`、`calib_only_post`、`l1_top2_compat`、`gated_hybrid` / `gated_hybrid_compat` / **`gated_hybrid_mcr`**（门控 top2 + MCR R3）、**`post7_mcr` / `post_n_mcr`**（后验 Top-N→MCR，`--pool-n` 默认 7）。LLM 三臂对照：[`ox_llm_three_arm_compare.md`](ox_llm_three_arm_compare.md)。

OX vs MAC 根因 + 移植：[`ox_vs_mac_rootcause.md`](ox_vs_mac_rootcause.md)；残差深挖：[`ox_best_arm_residual.md`](ox_best_arm_residual.md)；移植臂表：[`ox_mac_transfer_arms.md`](ox_mac_transfer_arms.md)。

**正式公平臂：`closed_live_mac_supervisor` LLM F1=0.584**（`--live-closed-mac --pool-n 15`）。`closed_mac_trace_rrf`（0.580）依赖冻结 B06，仅作机制上界。其它源：`multi_arm_rrf`、`closed_pool_rrf`、`tree_mac_pad` / `tree_mac_pad_selective`。

B00/B05 在 OX 上异常高（均 F1=0.543，≈gated）：[`ox_b00_b05_anomaly.md`](ox_b00_b05_anomaly.md)（B05≈B00；相对树独占以 trunc 为主；live vs B00 亦 marginal）。

建树缺叶 × MAC 式补叶可行性：[`ox_mac_style_leaf_emit_feasibility.md`](ox_mac_style_leaf_emit_feasibility.md)（Open FN 约 27% 可被 B00∪MAC 命名；须 force-emit+进窗，单补叶不够）。

**补叶+重排一体化路径（已执行）**：[`ox_emit_rerank_path.md`](ox_emit_rerank_path.md)  
Stage0 离线上界 [`ox_emit_then_rerank_offline.md`](ox_emit_then_rerank_offline.md) → Stage1 emit_v1 [`ox_emit_v1_validate.md`](ox_emit_v1_validate.md) / [`ox_emit_v1_config.json`](ox_emit_v1_config.json) → Stage2 预算锁定 [`ox_budget_recalib.md`](ox_budget_recalib.md) → Stage3 LLM 门控 [`ox_emit_locked_llm_gate.md`](ox_emit_locked_llm_gate.md)（正式臂 F1=0.588；**vs B00 CI 仍含 0 → REJECT**）。

**live 重标注对照（已执行）**：[`ox_live_reann_emit_vs_fopt.md`](ox_live_reann_emit_vs_fopt.md)  
emit+锁定F live → F1=**0.645** / LLM IAcc 0.366；无emit+锁定F live → F1=**0.651** / LLM IAcc **0.355**（当前最优；相对原 closed_live 0.584 约 +0.067）。增益主要来自在线后验写回+锁定预算，非 force-emit。IAcc 为 `ox.interpretation_consistency`（LLM），非 lexical。

**OX 特有机制 explainer（算法 / 起效 / 根因）**：[`ox_specific_mechanisms_explainer.md`](ox_specific_mechanisms_explainer.md)  
闭集 live-MAC 短列表、OX 预算锁定（L1=4…）、在线后验写回在校准预算下的协同与根因入档。

**三分集本方法 vs 基线总表**：[`runs/paper_v1/diagnosisarena_d2_seq100_baselines_summary.md`](../../runs/paper_v1/diagnosisarena_d2_seq100_baselines_summary.md) §7（DA 0.81/0.93 · MCR 0.50/0.753 · OX F1 0.651 / IAcc **0.355** LLM）。

其它：[`ox_gated_hybrid_top2_eval.md`](ox_gated_hybrid_top2_eval.md)、[`ox_gated_hybrid_mcr_compat_eval.md`](ox_gated_hybrid_mcr_compat_eval.md)、[`ox_large_pool_k_sweep.md`](ox_large_pool_k_sweep.md)、[`ox_effective_rank_trunc_gate.md`](ox_effective_rank_trunc_gate.md)。

## Baseline 路径（ordered Top-K → 同指标）

基线 replicate 目录（`predictions.jsonl` + `trace.jsonl`）→ 投影 → 复用 `transfer_eval`。

OX 默认 **`list_k=5`**（允许 7），与树系统 `ddx_k` 对齐；协议 `baseline_ordered_topk_v1`。

```bash
# 1) 推理（开放 vignette；OX 必须 --list-k 5 或 7）
PYTHONPATH=src:scripts:scripts/paper python3 scripts/paper/run_baseline.py \
  --dataset open_xddx --list-k 5 --arms B00-direct-cot --limit 2

# 2) 正式形态评测（lexical）
python3 scripts/paper/run_baseline_ox_mcr_eval.py \
  --dataset open_xddx \
  --pred-dir runs/paper_v1/open_xddx/B00-direct-cot/replicate_01 \
  --judge lexical --list-k 5

# 3) LLM judge（契约：gnn-llm + clashon + workers 50）
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate gnn-llm
bash /home/wanghongyi/clashctl/clashon.sh
python3 scripts/paper/run_baseline_ox_mcr_eval.py \
  --dataset open_xddx \
  --pred-dir runs/paper_v1/open_xddx/B00-direct-cot/replicate_01 \
  --judge llm --list-k 5 --workers 50
```

| 脚本 | 作用 |
|------|------|
| `scripts/paper/build_baseline_eval_projection.py` | predictions+trace → `annotate/eval_projection/` |
| `scripts/paper/run_baseline_ox_mcr_eval.py` | 投影 + `run_eval`（禁止树 `--build-projection`） |
| `scripts/paper/smoke_baseline_ox_mcr_eval.sh` | B00 × OX/MCR limit=2 dry-run 冒烟 |
| `scripts/paper/run_baselines_mcr_val_seq100.sh` | MCR 全量推理 + 正式评测 harness |
| `scripts/paper/run_baselines_ox_seq100.sh` | OX 全量推理 + 正式评测 harness（`list_k=5`） |

DiagnosisArena 仍用 Mapper Top-2；**勿**与 OX/MCR 正式表混表。

### MCR 基线全量结果（已完成，2026-07-25）

- 子集：`mcr_val_seq100_v1`（100 例）× 14 臂，全部 **100/100** 预测 + **LLM** 正式评测（`workers=50`）
- 汇总：[`runs/paper_v1/medcasereasoning_mcr_val_seq100_v1/mcr_val_seq100_baselines_summary.md`](../../runs/paper_v1/medcasereasoning_mcr_val_seq100_v1/mcr_val_seq100_baselines_summary.md)
- Top Acc：B07 (0.24) > B06 (0.23) > B01 (0.22)；协议 `paper_aligned_judge_v1` / `diagnostic_accuracy_single_trajectory`（非 10-shot）

```bash
JUDGE=llm EVAL_WORKERS=50 WORKERS=20 RESUME=1 \
  bash scripts/paper/run_baselines_mcr_val_seq100.sh
```

### OX 基线全量结果（已完成，2026-07-26）

- 子集：`ox_seq100_v1`（100 例）× 14 臂，全部 **100/100** 预测 + **LLM** 正式评测（`list_k=5`，`workers=50`）
- 汇总：[`runs/paper_v1/open_xddx_ox_seq100_v1/ox_seq100_baselines_summary.md`](../../runs/paper_v1/open_xddx_ox_seq100_v1/ox_seq100_baselines_summary.md)
- Top micro-F1：B06 (0.570) > B00/B05 (0.543)；协议 `paper_aligned_judge_v1` / Diagnostic P/R/F1 + Interp Acc

```bash
JUDGE=llm EVAL_WORKERS=50 WORKERS=20 RESUME=1 \
  bash scripts/paper/run_baselines_ox_seq100.sh
```
