# Live option @1/@2（compat_parallel 基线 × 测试臂）

- generated: `2026-07-23T22:47:20.225910+00:00`

## 基线

| 队列 | 协议 | @1 | @2 |
|------|------|---:|---:|
| all100 | compat rematch | **0.72** | **0.78** |
| Pilot24 | compat rematch | **0.75** | **0.75** |
| Pilot24 | w12 typed mapper | 0.583 | 0.750 |

## R3 gap-fill

冻结树已是 `recall_hints_gap` → **live option = compat 基线** (all100 **0.72/0.78**)。无独立增量。

## R4/R5 Track C（ABSENT）

Live inject 未修好 TreeParentPresent。官方 mapper：

- case 67: @1=0 @2=0 (rank=4)
- case 231: @1=0 @2=0 (rank=3)

**判定**：ABSENT live option 仍为 **0/0**；REJECT 全表宣称。

## B12 + compat（Pilot24 live annotate）

- annotate 注意：merge_only=24/24；rematch 正式口径可比性=`False`
- rematch（参考，可能无效）: @1=0.4583333333333333 / @2=0.4583333333333333 (n=24)
- **typed_llm（主 live）**: **@1=0.750 / @2=0.833** (n=24)

- 相对 Pilot24 compat rematch (0.75/0.75): Δ@1=0.0 Δ@2=0.0833
- **REJECT** — typed_llm 0.750/0.833 vs Pilot24 compat rematch 0.75/0.75; merge_only=24/24 → rematch comparator invalid
- claim_allowed=`False`；all100=`not_run`

## 总表（L2 mapping / rematch 后 option）

| 臂 | 队列 | @1 | @2 | 备注 |
|----|------|---:|---:|------|
| compat_parallel | all100 | 0.72 | 0.78 | 正式主表 |
| R3 | all100 | 0.72 | 0.78 | =compat（gap_fill已开） |
| R4/R5 ABSENT | 2 | 0.00 | 0.00 | inject 未修 TPP |
| B12+compat | Pilot24 | 0.750 | 0.833 | typed_llm 主 live |
| B12+compat | Pilot24 | 0.458 | 0.458 | rematch（merge坍缩，不可比） |

