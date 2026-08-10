# R4 口径对账（R2 34/77 vs R3 10/77）

> 由 `r4_facts.py` 自动生成。零新增 LLM 调用。

## 1. 两个数字用了同一批 77 例

- prune cohort：`APHHM_locus == tree_hit_final_drop`，n=77
- R2（`aphhm_funnel`）用 `e7_scored_correct`（终值分数）→ **34/77 = 44.16%**
- R3（`failure_taxonomy`）用 `e7_correct ∧ e7_locus==ok` → **10/77 = 12.99%**
- R4（本表）用 `e7_chain_correct`（champion 硬匹配金标）→ **13/77 = 16.88%**

## 2. 差额分解

- 差额 n = R2 − R3 = **24**
- 其中 `e7_mapper_rescue=True`：**23/24**
- 按数据集：{"da": 21, "mcr": 3}
- 按 e7_locus：{"s2_miss": 15, "s3_hit_s4_miss": 7, "s2_hit_s3_drop": 2}

**结论：** 不是不同交集、不是不同 mapper 版本。同一 77 例、同一 `e7_correct` 列；
R3 加了全链路门控，把 DA 上的 mapper 捡漏从「救回」里剔掉了。
R4 主叙事一律用 `chain_correct`；`scored_correct` 与 `mapper_rescue` 并列保留。

## 3. 双口径下的 800 题主表（core4）

- n = 800
- scored Acc：{"e7": 0.41625, "v0": 0.40125, "B06": 0.445, "B07": 0.44}
- chain Acc：{"e7": 0.2025, "v0": 0.19375, "B06": 0.3225, "B07": 0.2725}
- scored：e7 独占 vs base = 34 : 119
- chain：e7 独占 vs base = 17 : 152
- chain 独占臂：{"B07": 26, "v0": 9, "B06": 50, "e7": 5}

### layer（scored）

```
{
  "both_correct": 299,
  "base_win_rank": 102,
  "all_miss_but_recalled": 158,
  "all_miss": 190,
  "base_win_recall": 17,
  "e7_win_rank": 21,
  "e7_win_recall": 13
}
```

### layer（chain）

```
{
  "both_correct": 145,
  "base_win_rank": 98,
  "all_miss_but_recalled": 152,
  "all_miss": 334,
  "base_win_recall": 54,
  "e7_win_rank": 1,
  "e7_win_recall": 16
}
```

### mapper_rescue（占该臂 scored 命中的比例）

- e7: n=182，占 scored 命中 54.7%
- v0: n=182，占 scored 命中 56.7%
- B06: n=169，占 scored 命中 47.5%
- B07: n=191，占 scored 命中 54.3%
- B01: n=50，占 scored 命中 32.9%
- APHHM: n=86，占 scored 命中 59.7%

## 4. 可写 / 不可写

- **可写：** R2 的 44%「剪枝后 e7 仍对」被 DA mapper 捡漏灌水；全链路口径约为 13%。
- **不可写：** 把 R2 的 34/77 直接当作「扁平骨干救回了层次剪枝损失」。
- **不可写：** 在未剥离 mapper_rescue 的 scored 口径上比较 DA 臂序优势。

