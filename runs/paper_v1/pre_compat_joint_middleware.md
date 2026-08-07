# Pre-compat joint 中间件（C2 重建）

供后续消融在 **stored-compat 配置** 上复用 A3 joint-arbiter 列表（compat 之前），尤其是 MCR 上 AB07 / AB10。

**不要**用 `case_results.l2.final_ranking_*` 当 AB07/AB10 输入——那是 compat **之后**的列表。

---

## 产物位置

| 项 | 路径 |
|---|---|
| 根目录 | `logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate/pre_compat_joint/` |
| 单案 | `{case_id}.json`（schema `pre_compat_joint_v1`） |
| 清单 | `manifest.json` |
| 不写 | `frozen/`、`case_results/`、`shared_trees/` |

Live 捕获：`run_diagnosisarena_downstream_top2.py` 在 compat 前会写同结构 sidecar（后续 DA/MCR 新跑自动落盘）。

---

## 重建命令

```bash
PYTHONPATH=src:scripts:scripts/paper \
python3 scripts/paper/extract_pre_compat_joint_from_cache.py \
  --run-dir logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1 \
  --verify-replay
```

- 校验用 dry `compat_parallel`（无 live calib）。
- `calib_only` 精确复现需加 `--live-calib`（会打 LLM）。

---

## MCR seq100 校验（2026-07-27）

| 指标 | 值 |
|---|---|
| 恢复 | 98 `gate.n_leaves_match` + 2 empty joint；**0 failed** |
| 空 label | **0 / 457** |
| merge_only exact | **82 / 82 (1.00)** |
| calib_only exact（dry） | 9 / 18（预期：未跑 calib LLM） |
| 全体 exact / top1 | 0.91 / 0.92 |

标签填充优先级：`cache walk` → `post_compat` → 当前树（末位；writeback 后 id 可能复用）。

---

## 消融接入 API

```python
from pathlib import Path
import pre_compat_joint as pcj

annotate = Path("…/compat_synonym_v1/annotate")
ids, labels, art = pcj.load_pre_compat_inputs(annotate, case_id)

# AB07 always-merge / AB10 random-route：在 labels 上改路由，再：
routed = pcj.replay_compat_parallel(
    art, case_doc=case, vignette=vignette,
    cache=calib_cache, dry_run=False, k=5,
)
# 或直接调用 merge_calib_compat / adaptive_merge_siblings，输入用 labels
```

成套补测：

```bash
PYTHONPATH=src:scripts:scripts/paper \
python3 scripts/paper/run_mcr_c1_precompat_ablation.py --live-calib --workers 50
```

核心字段：

- `pre_compat.final_ranking_ids` / `final_ranking_labels` — annotate 时 joint 序
- `post_compat_ref` — 仅对照，非消融输入
- `recovery.method` / `label_enrichment` — 溯源

库：`scripts/paper/pre_compat_joint.py`  
批处理：`scripts/paper/extract_pre_compat_joint_from_cache.py`  
消融：`scripts/paper/run_mcr_c1_precompat_ablation.py`
