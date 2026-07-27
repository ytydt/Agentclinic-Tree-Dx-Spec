# I1 受限注入 → typed mapper（Pilot 门控）

**队列**：`pilot24`  
**生成**：`2026-07-24T12:33:07.606552+00:00`  
**inject_mode**：`restricted_option_synonym`  
**声明臂**：`R_compat_inject_restricted_typed`（无事后字符串 bind-repair）
**对照**：`R_compat`（compat_parallel + 冻结投影 rematch）
**门控 profile**：`i1`  

## 主表

| 臂 | @1 | @2 | MRR | coverage | mean_extra |
|----|---:|---:|----:|---------:|-----------:|
| R_compat | 0.750 | 0.750 | 0.750 | — | — |
| **R_compat_inject_restricted_typed** | **0.417** | **0.542** | **0.576** | 0.833 | 3.29 |

## 门控

- **决策**：`REJECT`
- **claim_allowed**：`False`
- **production_default**：`off`
- **理由**：
  - I1 typed vs compat Δ@1=-0.333 Δ@2=-0.208
  - I1 opt1 guard (Δ≥0): FAIL
  - I1 opt2 guard (Δ≥-0.01): FAIL
  - errors=0
  - mean_extra_leaves=3.29

## 方法说明

1. `compat_parallel`（禁金标 G2）重排 joint 叶序；
2. `build_injected_leaves(mode=restricted_option_synonym)`；
3. `RelationAwareAnswerMapper.map(..., mode=typed_llm)` **完整重跑**；
4. 不以字符串 bind-repair 作为主声明臂。

n=24 ok=24 err=0 mean_extra_leaves=3.3

## 解读

- 相对全树 R2（mean_extra≈16），受限注入成功压叶，但 **option 仍反害**（Δ@1=−0.33）。
- @1 分层：compat 对→typed 错仍占主导；救援不足以抵消。
- **结论**：I1 门 **REJECT**；保持生产 **off**；下一步不宜再靠「少注入几片叶」宣称修复，应另开「避免 typed 全量重绑」或冻结 map 规格（非本轮 I2）。

