# RA gold 族内孤立组内证据前缀扫描（F4←F10）

协议：`ra_within_goldfam_local_prefix_v1`
参考：`/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1`

## 设定

| 项 | 值 |
|----|----|
| 队列 | 未缺叶 ∩ L1 mass#1=gold 族 |
| n | **66** |
| L2 叶 | 主测 `shared_trees` 冻结（不重生成） |
| 选证 | 仅 gold L1 族；一次 `stop_after=10` |
| Fk | `selected_fact_ids[:k]` 前缀回放 |
| 指标 | gold 族内 within-fam Acc / within-rank |

## 结果

| local F | within-fam Acc | hits | mean within-rank | mean #evi |
|--------:|---------------:|-----:|-----------------:|----------:|
| 4 | 0.6212 | 41/66 | 1.803 | 3.848 |
| 5 | 0.5758 | 38/66 | 1.909 | 4.758 |
| 6 | 0.5909 | 39/66 | 1.864 | 5.652 |
| 7 | 0.5909 | 39/66 | 1.894 | 6.5 |
| 8 | 0.6212 | 41/66 | 1.864 | 7.303 |
| 9 | 0.5606 | 37/66 | 1.738 | 7.97 |
| 10 | 0.5152 | 34/66 | 2.062 | 8.5 |

## 锁定

- 最优 local（within-fam Acc，并列取更小 F）：**F4**

## 边界

- 非全案 live reann；不改组间 / L1 证据。
- 前缀合法性依赖动态选证的顺序累积；annotator 对各 Fk 独立调用。

