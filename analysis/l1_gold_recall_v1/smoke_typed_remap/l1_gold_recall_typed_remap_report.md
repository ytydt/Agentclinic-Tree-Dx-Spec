# compat → 叶注入 → **typed mapper 重跑**（Harness 增益声明用）

**队列**：`all100`  
**生成**：`2026-07-23T18:11:51.369807+00:00`  
**声明臂**：`R_compat_inject_typed`（无事后字符串 bind-repair）
**对照**：`R_compat`（compat_parallel + 冻结投影 rematch）

## 主表

| 臂 | @1 | @2 | MRR | coverage |
|----|---:|---:|----:|---------:|
| R_compat | 0.720 | 0.780 | 0.753 | — |
| **R_compat_inject_typed** | **0.420** | **0.690** | **0.628** | 0.930 |

## 门控（可否宣称 harness 增益）

- **决策**：`REJECT`
- **claim_allowed**：`False`
- **理由**：
  - typed vs compat Δ@1=-0.300 Δ@2=-0.090
  - opt2 guard (Δ≥-0.02): FAIL
  - errors=0

## 方法说明

1. `compat_parallel`（禁金标 G2）重排 joint 叶序；
2. `build_injected_leaves`：保留 compat 序，按后验追加树上其余叶；
3. `RelationAwareAnswerMapper.map(..., mode=typed_llm)` **完整重跑**；
4. 不以字符串 bind-repair 作为主声明臂。

n=100 ok=100 err=0 mean_extra_leaves=16.1

