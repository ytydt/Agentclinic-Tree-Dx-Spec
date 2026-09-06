# 四例皮肤/肿瘤/血液案例：范围与重放

涵盖119、56、91、179，四臂：`old_old / free_old / old_v2 / free_v2`。所有行号都是当前冻结 extraction JSON 内、合并病例后的零基行号；不等于原缓存局部行号。`_audit_source`另存cache_id、gid、input hash、normalized_local_index和job起点。

本包由AI直接逐段阅读原指南与病例，再明确指定干预。它是机制富集案例审计，不能估计错误频率，也没有临床专家盲审。`judgments_skin_other.json`中的事件包含忠实参照行和正确伴随知识；事件级error_codes并不表示该事件所有raw行都是错的。

## 产物

- `case_119.md`：真实病理证据、过强确认、假的IgA确认、目标错软分及claimants交互。
- `case_56.md`：正确完整主体的父类抢占、IHC错接、v2新增L4渐进处罚。
- `case_91.md`：错误proxy、缺候选/关键检索内容、错误组与竞争者误杀驱动零分位移。
- `case_179.md`：错指标给proxy全部正分，病因/时间轴缺失，恢复列表通过错误L4偶然提升proxy。
- `../judgments_skin_other.json`：完整事件来源—raw—post_gate—bind/finding—贡献/确认/排除/L4连接。
- `../skin_other_probe_results.json`及`_full.json.gz`：40项119/179逐次屏蔽与91器官/年龄探针。
- `../skin_other_additional_probe_results.json`及`_full.json.gz`：40项56逐次L4、主体归还、IHC及91错误组/误否决探针。
- `../skin_other_179_source_L4_probe_results.json`及`_full.json.gz`：6项来源限制的L4单独/联合探针。
- `../skin_other_validation.json`：索引、来源hash、完整分数重建、probe关键数值检查。

`force_bindings`只移动原始subject字面等于已有完整SCC候选的原行，所有移动都从Carcinoma发出；未增加金标、规则或患者事实。这个病例定位探针不等于最终可部署绑定算法。来源限制L4和错误join屏蔽也不是一组已保证临床正确的全局修复。

## 复算顺序

在仓库根目录，先按本目录的 `REPLAY_API.md` 生成/复核44个冻结基线全阶段包，再运行：

```bash
python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/run_skin_other_probes.py
python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/run_skin_other_additional_probes.py
python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/run_179_source_L4_probe.py
python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/build_skin_other_evidence.py
python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/validate_skin_other_cases.py
```

本包共86项离线引擎干预，不是86次LLM调用。事实、候选内容/顺序、历史抽取缓存和生产源代码保持冻结；各干预仅在审计包装器中实施。完整trace记录全球claimants再计算，因此无需用局部delta直接相加猜测名次。gzip时间戳可能随重跑变化，应比较解压JSON语义内容；逻辑数值与原始行号是可复算对象。
