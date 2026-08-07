# 事故：d2_seq100_v1 已发表切片被覆盖并已恢复

日期：2026-08-07 20:55 (UTC+8)

## 发生了什么

为构造 DA 留出切片，运行：

```bash
python3 scripts/paper/extract_diagnosisarena_subset.py --dataset diagnosisarena \
  --target-size 100 --version d2_heldout100_v1 --skip-rows 249 \
  --exclude-ids-file .../d2_seq100_v1/case_ids.txt
```

`--version` **只写进 manifest 字段，不改变输出目录**；`--out-dir` 默认仍指向
`data/benchmarks/diagnosisarena/subsets/d2_seq100_v1/`。结果新切片（id 252–452）
覆盖了已发表切片（id 3–249）的全部 5 个文件。

该目录未纳入 git（`git status` 显示 `??`），无版本可回滚；
`analysis/asset_guard/` 的历史快照也不含 benchmark 切片。

## 影响范围

- 仅数据切片定义文件被覆盖。**所有已发表的运行产物（`logs/`、`runs/`）未受影响**，
  它们各自内嵌 `normalized_cases.json` 副本。
- 覆盖窗口内没有任何评测运行读取该目录。

## 恢复

1. 新切片 5 个文件移到 `subsets/d2_heldout100_v1/`，manifest 的 `outputs` 路径已修正。
2. 权威 id 列表从运行产物取回：
   `logs/diagnosisarena_d2_m01_v1/aphhm_clean_v1/annotate/mapper/records.json`
   的 100 个 `case_id` → 3..249，与原 manifest `id_range` 完全一致。
3. `cases.parquet` 由 `raw/test.parquet` 按该 id 列表重建；`case_ids.txt` 同源重写。
4. `normalized_cases.json` 从 `logs/diagnosisarena_d2_m01_v1/normalized_cases.json` 复制。
5. `selection_manifest.json` 按覆盖前打印的原文重建，并加 `restored_note` 字段。

## 校验

| 项 | 结果 |
|---|---|
| `d2_seq100_v1` n / id 范围 | 100 / 3..249 ✅ |
| 逐例 `Final Diagnosis` vs 运行产物 `gold` | 0/100 不一致 ✅ |
| 逐例 `Right Option` vs 运行产物 `gold_option` | 0/100 不一致 ✅ |
| `d2_heldout100_v1` n / id 范围 | 100 / 252..452 |
| 两切片 id 重叠 | 0 ✅ |

## 未恢复项

`d2_seq100_v1/exclusion_log.jsonl` 记录的是被跳过行的逐行原因，不可从运行产物反推。
manifest 里的 `exclusion_reason_counts` 汇总已恢复，逐行明细丢失。
该文件不参与任何评测路径。

## 后续动作

1. `extract_diagnosisarena_subset.py` 的 `--version` 应同时决定 `--out-dir`，
   或在目标目录非空时拒绝写入。**未修改**（本轮不动已发表资产的生成脚本），
   在此登记为待办。
2. `data/benchmarks/*/subsets/` 应纳入版本控制或 asset_guard 快照。
