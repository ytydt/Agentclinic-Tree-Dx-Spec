# compat → 叶注入 → **typed mapper 重跑**（Harness 增益声明用）

**队列**：`all100`  
**生成**：`2026-07-31T03:59:10.508831+00:00`  
**inject_mode**：`preserve_joint_then_posterior`  
**声明臂**：`R_compat_inject_typed`（无事后字符串 bind-repair）
**对照**：`R_compat`（compat_parallel + 冻结投影 rematch）
**门控 profile**：`default`  

## 主表

| 臂 | @1 | @2 | MRR | coverage | mean_extra |
|----|---:|---:|----:|---------:|-----------:|
| R_compat | 0.720 | 0.780 | 0.753 | — | — |
| **R_compat_inject_typed** | **0.400** | **0.670** | **0.608** | 0.910 | 16.12 |

## 门控

- **决策**：`REJECT`
- **claim_allowed**：`False`
- **production_default**：`off`
- **理由**：
  - typed vs compat Δ@1=-0.320 Δ@2=-0.110
  - opt2 guard (Δ≥-0.02): FAIL
  - errors=0

## 方法说明

1. `compat_parallel`（禁金标 G2）重排 joint 叶序；
2. `build_injected_leaves(mode=preserve_joint_then_posterior)`；
3. `RelationAwareAnswerMapper.map(..., mode=typed_llm)` **完整重跑**；
4. 不以字符串 bind-repair 作为主声明臂。

n=100 ok=100 err=0 mean_extra_leaves=16.1

