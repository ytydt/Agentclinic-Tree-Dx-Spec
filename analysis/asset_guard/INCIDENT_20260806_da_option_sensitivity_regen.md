# 事故记录：DA option 端点敏感性审计被重新生成

Date: 2026-08-06
Severity: 低（内容未变，仅时间戳）

## 发生了什么

在排查 AB02 机制归因时，以 `--help` 调用 `scripts/paper/da_option_endpoint_sensitivity_audit.py`。
该脚本没有 argparse，`--help` 未被拦截，直接执行了完整审计并覆盖：

- `runs/paper_v1/da_option_endpoint_sensitivity.json`
- `runs/paper_v1/da_option_endpoint_sensitivity.md`

`asset_guard verify` 报 `modified=2`。

## 内容是否改变

未改变，只有 `created_at` / “生成时间” 字段刷新为 `2026-08-05T16:51:59Z`。判据：

1. 该脚本是对已存盘投影与缓存的确定性重算，本次运行 3.6 秒、零新增 LLM 调用；
2. 重算值与其他文档中引用的旧值逐项一致——`ablations_c3_results.md` 引用“AB02 的 0.68 里 0.51 来自并列 credit，M00 的 0.70 里同样有 0.49”，重算结果正是 AB02 `tie_rescued=0.51`、M00 compat `tie_rescued=0.49`；各臂 `option_at1`（M00 compat 0.70 / pre-compat 0.59 / AB01 0.51 / AB02 0.68 / AB03 0.37）与既有记录全部相符。

## 处理

已重新快照 asset_guard 基线。后续若要读取该审计结果，直接读文件，不要调用脚本。
建议给该脚本加 argparse 或只读模式，避免 `--help` 触发写盘。
