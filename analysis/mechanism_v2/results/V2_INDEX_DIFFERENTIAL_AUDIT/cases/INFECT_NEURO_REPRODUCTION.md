# 257 / 326 / 475 / 49：文件与复算顺序

这四例的主判断在 `case_257.md`、`case_326.md`、`case_475.md`、`case_49.md`。所有脚本、JSON在父目录 `V2_INDEX_DIFFERENTIAL_AUDIT/`。本组未修改生产实现、未调用模型。

在先运行 `replay_audit.py` 生成44份完整历史trace后，按顺序执行：

```bash
python run_infect_neuro_probes.py
python supplement_infect_neuro_probes.py
python infect_neuro_hidden_claimant_probe.py
python build_infect_neuro_case_reports.py
python validate_infect_neuro.py
```

在父目录运行以上命令。第一个脚本会重建 `judgments_infect_neuro.json`，因此补充脚本必须随后执行，避免覆盖后加的敏感性分析。不得并行执行同一个进程内的engine实例。

| 文件 | 范围 |
|---|---|
| `judgments_infect_neuro.json` | 16病例×臂、122条命名干预重放记录（含相同选择集的命名别名），234条选定原始贡献及其所有去重支持行；另有2个后续定位探针 |
| `infect_neuro_source_evidence.json` | 117个实际来源窗口，key为case\|index\|gid |
| `infect_neuro_validation.json` | 行号/来源/分数重建校验；不是临床真值验证 |
| `*_initial_probe.txt` | 早期定位中间件，贡献来自旧exact-arm-window trace且只有前25条；相同predicate列出的raw只是可能匹配，不等于最终绑定。不得用它们替代最终完整trace的来源 |

已冻结的补充范围：326保留粗动物材料暴露桥接的核心敏感性；257/326错误竞争者否决的精确raw删除；49旧raw2181无直接分数但污染claimants，以及v2 restored-list raw651的单票屏蔽。后两者属于先看到完整trace后提出的适应性机制探针，不称预注册。

任何四格结果都只是“保持其余现有缺陷不变时的条件效应”。例如49删竞争错误可获得top1，却仍含错误gold组织学票；不能报告为可靠诊断修复。326的粗动物暴露有临床桥接解释空间，严格字面屏蔽与保留粗桥接的结果均需一起报告。
