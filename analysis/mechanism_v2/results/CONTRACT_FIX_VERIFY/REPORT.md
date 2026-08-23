# D 的带调用验证：两笔契约修复在 holdout-400 上的配对结果

臂 `aphhm_c_multistance_contractfix_v1` = 冻结臂 `aphhm_c_multistance_v1` 的**同一配置**
（`axis_mode=off`、`meta-llama/llama-3.3-70b-instruct`、`commit,coverage,mechanism`、
`max_facts=12`、`unique_budget=10`）加上 `--strict-identity --enforce-group-quota`。

生成阶段的调用全部命中从冻结臂拷入的内容寻址缓存，所以**下表的每一处差异只可能来自这两个
开关**。400 例（DA holdout-200b 200 + MCR 200b 200），零错误，新增付费调用 **254 次**
（DA 122 / MCR 132）。

分析脚本 `analysis/mechanism_v2/contract_fix_verify.py`。
上游审计：[`IDENTITY_DEBT/REPORT.md`](../IDENTITY_DEBT/REPORT.md)。

端点是 `dc.match`（legacy-chain，对 clinical-complete 的 PPV 0.5648）。**没有临床面板。**

> **后续更正（2026-08-20，[`CLINICAL_RESCORE/REPORT.md`](../CLINICAL_RESCORE/REPORT.md) §6）：
> 临床面板其实早已存在**——判定按 `(case, label)` 冻结、与臂无关，覆盖本实验两臂冠军各
> 400/400，零调用。在真端点上重算，**这两笔修复是中性的**：
>
> | 端点 | DA base → fix | McNemar | MCR base → fix | McNemar |
> |---|---|---|---|---|
> | clinical-complete | 0.030 → 0.030 | 1 vs 1，p=1.00 | 0.285 → 0.295 | 1 vs 3，p=0.625 |
> | complete ∪ partial | 0.565 → 0.560 | 3 vs 2，p=1.00 | 0.390 → 0.415 | 1 vs 6，p=0.125 |
> | 池内完整暴露 | 0.040 → 0.040 | 0 vs 0，p=1.00 | 0.470 → 0.475 | 0 vs 1，p=1.00 |
>
> 也就是说 §1 的池召回 +3pp/+4.5pp 与 §3 的 MCR concept +2.5pp **都没有在真端点上留下来**，
> 这与本报告 §2 与 §5 的限定一致（"不可把池召回涨幅报成召回能力提升"、"不可把 MCR concept
> +2.5pp 报成显著"），现在有了直接读数而不只是限定。**修复应当保留**——它消除了嵌合标签
> （§3 的 `Lipomatous spinal epidural hematoma`）与父子折叠，属正确性；但**不得作为收益写入
> 任何结论**。

## 0. 一句话结论

**两个开关都按设计工作，且没有付出预期中的转化代价；但池召回的涨幅主要是粗父类信用，
不是诊断改善。** 宽度 +0.47/+0.54（离线预测 +0.531，实测吻合），池召回 DA +3pp / MCR +4.5pp
且**零倒退**，concept top-1 DA 持平、MCR +2.5pp（5 增 0 减）。离线报告里"宽度 +0.531 ≈
−2.3pp 转化"的担忧**没有出现**。

## 1. 配对结果

| 指标 | DA base | DA fix | MCR base | MCR fix |
|---|---:|---:|---:|---:|
| 池宽（registry 概念数） | 9.025 | **9.485** | 8.695 | **9.230** |
| 每例 LLM 调用 | 5.135 | 5.380 | 5.165 | 5.370 |
| 池召回 `dc.match` | 0.610 | **0.640** | 0.475 | **0.520** |
| concept top-1 | 0.225 | 0.225 | 0.220 | **0.245** |
| 冠军发生变化的例数 | — | 16 | — | 21 |
| 池变宽的例数 | — | 63 | — | 76 |

配对 McNemar（精确二项，双侧）：

| 端点 | 只有 base 命中 | 只有 fix 命中 | p |
|---|---:|---:|---:|
| DA 池召回 | **0** | 6 | 0.031 |
| MCR 池召回 | **0** | 9 | 0.0039 |
| DA concept top-1 | 1 | 1 | 1.00 |
| MCR concept top-1 | **0** | 5 | 0.0625 |

**池召回在 400 例上是 15 增 0 减的单调改善。** 这是"修复不倒退"最强的一条读数：
不存在任何一例因为解除错误合并而丢掉原本能匹配的标签。

宽度代价的实测：+0.460（DA）、+0.535（MCR），与离线重放预测的 +0.531 一致，验证了离线方法。
但 E5 的 −4.42pp/候选**没有兑现**——concept top-1 一个持平、一个上涨。合理解释是那 0.5 个
新增候选是被错误折掉的父/子标签，与既有候选同核，不构成 E5 意义上的新竞争者；不过本实验
无法把这个解释与"样本量不足以测出 −2pp"区分开。

## 2. 必须写在最前面的限定：池召回的涨幅主要是粗父类信用

15 例新增池召回里，被恢复出来的匹配标签与 gold **完全同串的只有 3 例**：

| 家族 | gold | 恢复出的标签 | 同串 |
|---|---|---|---|
| da | Peri-infarction pericarditis (PIP) | `Pericarditis` | ✗ |
| da | Brucella melitensis soft tissue abscess… | `Abscess` | ✗ |
| da | Multiple liver abscesses infected by Fusobacterium… | `Liver Abscess` | ✗ |
| da | Vertebral osteomyelitis and discitis due to Strept… | `Discitis` | ✗ |
| da | Myopericarditis with cardiac conduction system inv… | `Myopericarditis` | ✗ |
| da | Leptospirosis with severe pneumonia, AKI… | `Pneumonia` | ✗ |
| mcr | Pycnodysostosis | `Pycnodysostosis` | **✓** |
| mcr | Hereditary hypophosphatemic rickets with hypercalc… | `Hypophosphatemic rickets` | ✗ |
| mcr | Cryptococcal osteomyelitis | `Osteomyelitis` | ✗ |
| mcr | Sacrococcygeal teratoma | `Teratoma` | ✗ |
| mcr | Chronic necrotizing pancreatitis | `Pancreatitis` | ✗ |
| mcr | PlexiformSchwannoma | `Schwannoma` | ✗ |
| mcr | Nonbacterial thrombotic endocarditis | `Nonbacterial Thrombotic Endocarditis` | **✓** |
| mcr | spinal epidural lipomatosis | `Spinal Epidural Lipomatosis` | **✓** |
| mcr | keratoameloblastoma | `Ameloblastoma` | ✗ |

**12/15 是被 `dc.match` 当作命中的粗粒度父类。** 换成 clinical-complete 端点，这 12 例不会
计入。所以 §1 的 +3pp / +4.5pp 不能读成"召回真的变好了 3–4.5pp"，只能读成"legacy-chain
此前因为错误合并而少记了 3–4.5pp"。这一条与本对话此前追问的伪召回机制是同一件事：
registry 会把具体标签降级成 alias，只留粗父类在池里可见，`dc.match` 再给它信用。

## 3. concept top-1 的 7 处变化逐例

与池召回不同，冠军层的收益**多数是真的**：MCR 5 例新命中里 4 例是同串精确匹配。

| 变化 | 家族/例 | gold | base 冠军 | fix 冠军 |
|---|---|---|---|---|
| 新命中 | mcr 250 | Toxocariasis | Loeffler's syndrome | **Toxocariasis**（同串） |
| 新命中 | mcr 285 | Pycnodysostosis | Pyknodysostosis | **Pycnodysostosis**（同串） |
| 新命中 | mcr 395 | Kummell disease | Steroid-induced osteoporosis | **Kummell disease**（同串） |
| 新命中 | mcr 467 | spinal epidural lipomatosis | Lipomatous spinal epidural hematoma | **Spinal Epidural Lipomatosis**（同串） |
| 新命中 | mcr 362 | Cryptococcal osteomyelitis | Extrapulmonary Tuberculosis | Osteomyelitis（父类信用） |
| 新命中 | da 766 | Myopericarditis with cardiac conduction… | Acute Pericarditis | Myopericarditis |
| 新失手 | da 592 | Pulmonary Reperfusion Injury after catheter… | Pulmonary Embolism | Post-Embolic Pulmonary Hypertension |

三处值得单独记：

- **`da 766` 闭环了上游 §5.3 的诊断。** 上游举的例子正是"`Myopericarditis` 的载荷只剩
  `Acute Pericarditis`"。解除折叠后 `Myopericarditis` 回到池里并赢下决赛。
- **`mcr 467` 说明错误合并会造出嵌合标签。** base 冠军 `Lipomatous spinal epidural hematoma`
  是 `Spinal Epidural Lipomatosis` 与 `hematoma` 被折在一起后的产物，它赢了决赛。
  这不是粒度问题，是身份污染直接制造了一个不存在的诊断。
- **唯一的新失手 `da 592` 里，base 的"命中"本身可疑。** gold 是
  `Pulmonary Reperfusion Injury after catheter-directed thrombolysis`，base 冠军
  `Pulmonary Embolism` 被 `dc.match` 判为命中。fix 在 quota 补入 `Cardiac Disease` 席位后
  改判 `Post-Embolic Pulmonary Hypertension`。这一例的得失取决于匹配器口径，不宜计入代价。

## 4. group quota 的行为：真实触发，端点中性

| | DA | MCR |
|---|---:|---:|
| 有席位被补的例数 | 49 / 200 | 41 / 200 |
| 补出的席位总数 | 52 | 44 |
| 其中冠军发生变化 | 11 | 11 |
| 其中新命中 | **0** | **0** |
| 其中新失手 | 1 | 0 |

90/400（22.5%）触发，96 个席位，22 例冠军因此改变，端点上净 −1 例。与上游"125/800 例违约，
但只有 3 例是金标所在组被静默"的预测方向一致：**这是契约债，不是性能杠杆**，实测确认。
成本 +0.2 调用/例（上界 +1，因为只有 22.5% 触发）。

## 5. 可写与不可写

**可以写：**
- 两个开关在 400 例 holdout 上零错误运行；池召回 15 增 0 减（DA p=0.031、MCR p=0.0039）。
- 宽度实测 +0.460/+0.535，与离线重放预测 +0.531 一致。
- concept top-1 DA 持平（1 增 1 减）、MCR 5 增 0 减（p=0.0625，未达 0.05）。
- 池召回涨幅中 12/15 是粗父类信用；冠军层 5 例 MCR 新命中里 4 例是同串精确匹配。
- group quota 触发 22.5%、补 96 席、改 22 个冠军、端点净 −1 例。
- 错误合并会制造嵌合标签（`Lipomatous spinal epidural hematoma`）并让它赢下决赛。

**不可以写：**
- 不可把池召回 +3pp/+4.5pp 报成召回能力提升：12/15 是端点口径产物。
- 不可把 MCR concept +2.5pp 报成显著：p=0.0625，未过 0.05，且是**事后**观察的端点，
  本次运行没有预注册效应门槛（它的目的是验证修复不倒退）。
- 不可声称宽度惩罚不存在：本实验只说在 +0.5 宽度、n=200/族 上没测出来。
- 不可把这两个开关写进任何已归档实验的结论：归档臂默认关闭，重放逐字节一致。
- 不可跨族合并这 400 例报单一数字。

## 6. 复现

```bash
ARM=aphhm_c_multistance_contractfix_v1
for D in diagnosisarena_heldout200b medcasereasoning_200b; do
  mkdir -p logs/backbone_v1/$D/$ARM/cache
  cp logs/backbone_v1/$D/aphhm_c_multistance_v1/cache/aphhm_c_llm.json \
     logs/backbone_v1/$D/$ARM/cache/aphhm_c_llm.json
  python3 scripts/paper/run_aphhm_c.py --dataset $D --arm $ARM --mode multistance \
    --axis-mode off --strict-identity --enforce-group-quota --workers 25
done
python3 analysis/mechanism_v2/contract_fix_verify.py
```
