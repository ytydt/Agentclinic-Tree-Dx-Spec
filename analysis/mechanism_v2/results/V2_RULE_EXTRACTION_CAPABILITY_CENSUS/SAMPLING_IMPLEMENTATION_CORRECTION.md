# 抽样实现复核记录

独立方法复核发现初版 `build_samples.py` 在建组前过滤没有 subject/predicate 的不合法行。2条不合法行中，一条为独立原子，另一条是缓存 `e3f34571985a2c4d0deacb3bc932b20ceaa97f15` 的 g1 成员（raw index 4，Ebstein anomaly 缺 predicate）。后一条应作为坏组成员保留，不能在审计前静默删除。

该 g1 还有5条有效成员，因此修正不会增加或减少输出单元：框仍为32725原子、562组。该cache没有被抽中，180个样本及其payload、成员、纳入权重全部不变。修正后的生成器在组内保留不合法成员并标记 `invalid_member`；独立不合法原子仍另列、不混进有效原子语义分母。原始2条不合法行已从一开始保存在sampling_summary，未隐藏。

重跑前后对全部样本包和manifest进行SHA256一致性检查；记录在 `sampling_regeneration_check.json`。此修正是抽样实现问题，不是对模型输出的修复，也未据初审结果改换样本。
