# 阶段 2c-Fine：平行同义叶挤占

**表**：`synonym_crowd_cases.tsv`  
**审核**：`granularity_audit_sheet.jsonl`（Cursor-Agent 充当审核员）

## 1. 自动检出

- A 集 `fine_candidate=1`：**13/19（68%）**
- 判定启发式：Top1/Top2 标签同义/包含，或同父且 gold 叶落在 Top2

## 2. 合并模拟（标签同义 Top1–Top2）

| 指标 | 值 |
|------|---:|
| A 集同义 Top1–Top2 合格例 | 13 |
| 合并后 gold 叶落入虚拟 Top1（叶 ID 命中） | 4 |
| 虚拟恢复率 | 0.308 |

说明：叶 ID 恢复率偏低，因多例 gold 映射到 **Top2 以外的平行克隆叶**（同标签不同 parent），合并仅 Top1∪Top2 不够；完整 `AdaptiveMergeSiblings` 需按 **规范标签/ resolver 簇** 合并全榜同义叶后再映射。

## 3. Agent 审核（Fine 为主的病例）

确认 Fine 主导或显著参与 @1 失败的 A 例包括：`4, 40, 100, 122, 165, 233, 246`，以及与 Coarse 共存的 `29, 90, 117, 186, 205` 等。

## 4. 设计含义

- Fine 占比高 → **必须**保留 `AdaptiveMergeSiblings` / `Merge-to-canonical-L2` 支线。
- 仅 TopK support 重排对同义平行叶 **无效或仅偶然有效**。

产出：本文件 + `synonym_crowd_cases.tsv`。
