# 粒度错误模式混成（A 集）

**n=19**（本方法 @2∧¬@1）。主标签优先级：Agent 确认 Coarse → Fine → 纯排序 → 其他。

| 主模式 | n | 占比 | 含义 |
|--------|--:|-----:|------|
| Fine 平行同义挤占 | **8** | 42% | 合并/规范叶支线 |
| Coarse 单叶多选项 | **7** | 37% | L3 自适应细分支线 |
| 纯排序 | **1** | 5% | TopKCalibration 主适用 |
| 其他（映射/覆盖/reject） | **3** | 16% | mapper / 并发症未挂叶等 |

注：归类优先级 = Agent 确认 `coarse_leaf_multi_option` → 其余 `fine_candidate` → `ranking_failure_rank2` → 其他。Coarse 7 例中 5 例同时带 Fine 旗标。

## 对阶段 5 的硬含义

1. **仅约 5%** 是干净的纯排序失败 → 单独上线 support 重排的 @1 天花板很低。  
2. Fine+Coarse 合计 **约 79%**（15/19）→ `AdaptiveDeepenOrMerge` 为并列一等公民，不是可选项。  
3. 报告与消融必须 **分列**：`+calibration` / `+merge` / `+subdivide`，禁止混报为一个「重排增益」。
