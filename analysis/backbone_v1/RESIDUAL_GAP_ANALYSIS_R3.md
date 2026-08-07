# 残余差分析 R3：骨干与 AB02/APHHM 的落差来自输入不对称，不是机制

**结论先行。** R1/R2 里所有关于机制的假设（输出带宽、判别式证据门控、结构化假设管理、
层级轴、证据条件化写回）都不再需要用来解释骨干与 AB02/APHHM 的性能落差。落差的
绝大部分由一个输入侧事实解释：**管线（M00/AB02）的 `case_summary` 里带着多选题选项块，
gold 答案原文在内；而骨干与已发表基线拿到的是剥除选项后的 vignette。**

把同样的输入喂给 4 次调用的骨干后，它在 DA 上追平 AB02、逼近 APHHM，在 MCR 上从
0.24 跳到 0.47（管线 0.50）。

---

## 1. 泄漏的直接证据

`scripts/paper/diagnosisarena_adapter.py` 自己写着这件事：

```
# DiagnosisArena case_text ends with an MCQ stem + Options block; those are
# answer material, not observed clinical findings.
_MCQ_TAIL_RE = re.compile(r"(?is)\n+\s*What is the most likely diagnosis\?\s*\n+Options:\s*\n.*\Z")
```

两条路径就此分叉：

| 消费者 | 拿到的输入 | 代码位置 |
|---|---|---|
| 基线臂 | `da.vignette_body(case_text)`，选项已剥除；`runtime_payload` 只传 `vignette` + `question` | `baseline_common.py:240,271` |
| 骨干（本工作） | 同上 | `run_backbone_v1.py:123` |
| 评分用 mapper | `case_text.split("\nOptions:")[0]`，选项已剥除 | `run_diagnosisarena_m01.py:1116` |
| **建树管线 annotate** | **完整 `case_text`，含 Options 块** | `run_diagnosisarena_m01.py:251` |

实测（读 `shared_trees/*.json` 的 `state.case_summary`）：

| 运行 | n | 含 `Options:` 块 | 含 gold 原文 |
|---|---:|---:|---:|
| DA `c3_ab02_v1`（AB02） | 100 | 100 | **100** |
| DA `c2_ab21_v1` | 100 | 100 | **100** |
| DA `pilot24_compat_b12_live_v1` | 24 | 24 | **24** |
| 骨干 DA vignette | 100 | 0 | 1（巧合） |
| MCR `c3_shared_no_dedupe_v1` | 100 | 100 | **100，且 gold 恒为选项 A** |

MCR 的形式更糟：选项是合成的，gold 永远排在 A 位，等于把答案放在首位递给管线。

泄漏被实际使用的程度：**AB02 最终 L2 叶子里 63.8% 是选项文本的拷贝**（`leaf_match_score ≥ 0.7`），
候选池里 22.9%。

## 2. 泄漏复现对照（batch8）

给骨干换上管线的 `case_summary`（`--context-source pipeline_summary`），其余不变：

| DA n=100 | 调用/例 | lexical | option@1 |
|---|---:|---:|---:|
| 骨干 v0_s4b_k5，干净输入 | 4 | 0.36 | 0.50 |
| 骨干 e7_k3_comp，干净输入 | 6 | 0.40 | 0.59 |
| 骨干 e22_k7comp，干净输入 | 9 | 0.46 | — |
| **骨干 v0_s4b_k5 + 泄漏** | **4** | **0.65** | **0.67** |
| **骨干 e7_k3_comp + 泄漏** | **6** | **0.65** | **0.67** |
| AB02（原生带泄漏） | ~50 | 0.63 | 0.68 |
| APHHM / M00（原生带泄漏） | ~300 | — | ~0.71 |

| MCR n=100 | 调用/例 | Acc@1 |
|---|---:|---:|
| 骨干 v0_s4b_k5，干净输入 | 4 | 0.24 |
| **骨干 v0_s4b_k5 + 泄漏** | **4** | **0.47** |
| **骨干 e7_k3_comp + 泄漏** | **6** | **0.46** |
| 管线 M00 precompat | ~300 | 0.50 |

拆账：在 DA 上，泄漏值 **+0.29 lexical / +0.17 option@1**；在同样泄漏输入下，管线相对
4 次调用骨干的增量是 **−0.02 ~ +0.04 option@1**。MCR 上泄漏值 **+0.23**，管线增量 **+0.03**。

注意泄漏输入下 `s2_k=3` 相对 `s2_k=1` 增量归零（0.65 = 0.65）：没有召回问题需要解决时，
额外的生成预算不再买到任何东西。这本身就说明泄漏替代了检索/生成工作。

## 3. 通往该结论的中间证据（保留，因为它们各自独立成立）

### 3.1 选择阶段完全不承重（E21 移植实验）

`scripts/paper/run_backbone_e21_transplant.py`，2×2 交叉「候选来源 × 选择方式」，
事实与提示词固定为骨干的：

| DA n=100 | 选择=取首项（0 调用） | 选择=骨干 S4-b（1 调用） |
|---|---:|---:|
| 候选=骨干 shortlist | 0.36 | 0.36 |
| 候选=AB02 叶集 | **0.64**（opt1 0.61） | 0.60（opt1 0.60） |

零调用地取 AB02 后验首项就拿到 lexical 0.64，等于 AB02 端到端。骨干自己的选择器
放在 AB02 候选上条件转化 0.75，放在自己候选上只有 0.61。**选择器从来不是瓶颈。**

对照：AB02 叶集随机排序取首项只有 0.363 ± 0.032，跨调用共识 0.390。所以是候选集
＋后验排序共同承重，而两者都在泄漏输入下产生。

### 3.2 差距发生在候选池，筛选保留率各系统一致

| 系统 | 池大小 | 池覆盖 | top5 覆盖 | 筛选保留率 |
|---|---:|---:|---:|---:|
| AB02（泄漏） | 107.9 | 0.920 | 0.800 | 0.870 |
| 骨干 e8_k3_part | 36.9 | 0.810 | 0.650 | 0.802 |
| 骨干 e7_k3_comp | 47.6 | 0.790 | 0.630 | 0.797 |
| 骨干 v0_s4b | 17.3 | 0.710 | 0.590 | 0.831 |

保留率 0.80–0.87 基本一致，差距全在池覆盖。而池覆盖的差距正是选项拷贝带来的
（AB02 池里 22.9% 来自选项）。

### 3.3 不是「粒度/措辞」伪影

阈值扫描下 AB02 优势稳定（cov@0.5/0.7/0.9 = 0.800/0.800/0.650，骨干 0.630/0.630/0.420），
且「候选是 gold 上位词」判据回收为 **+0.000**——骨干的缺失是真实概念缺失。
但精确匹配率 AB02 0.27 vs 骨干 0.00–0.02、候选中位词数 3 vs 2，正是逐字拷贝选项的指纹。

## 4. 已被证伪的假设（R2 遗留，勿再引用）

| 假设 | 判决 | 证据 |
|---|---|---|
| **N1 输出带宽**：每次调用产出的判断格数过多导致信号退化 | **证伪** | 逐事实拆分越细越差。DA lexical：单次 55 格矩阵 0.31 → 拆成 16 次 0.23 → 28 次 0.28；MCR Acc 0.24 → 0.11。带判别门控的 ordinal 变体（e20，10 次调用）DA option@1 仅 0.36 |
| 判别式证据门控是承重点 | **证伪** | e20 系列（变体 h，含 `DISCRIMINATIVE_LABELS` 门控）全线低于不做选择 |
| 候选多样性 / 集成效应 | **证伪** | 跨调用共识 0.390 < 随机单次首项 0.470 |
| 生成预算（池大小）是主要杠杆 | **证伪** | 干净输入下 s2_k=3→5→7（池 48→~80→~110）lexical 仅 0.44→0.45→0.46，平台化 |
| 证据条件化写回值 +0.277 | **降级** | 该数值成立但产生于泄漏输入之上：AB02 叶集按后验排序 0.640 vs 随机排序 0.363。在干净输入下无对应证据 |

一个副产物结论也应记下：**在干净输入下，骨干里所有 LLM 选择变体（b/c/d/e/f/g/h）都不优于
「直接取实体过滤后的首项」。** 最好的干净输入骨干臂 `e16_k3comp_nos4_k5` 用 0 次 S4 调用
拿到 lexical 0.44 / option@1 0.55。

## 4b. 泄漏注入点的精确定位（更正）

配套备忘录 `INTERNAL_MEMO_mcq_option_leak.md` / `PAPER_CLAIMS_AT_RISK_option_leak.md`
把注入点归给 `static_qa_env.StaticQAEnv.get_case_summary()`。**在论文运行路径上不是它。**
`StaticQAEnv`（确实会拼 `Question + Options`）只被 `scripts/eval_lr_coverage_isolated.py`
与 `scripts/probe_lr_annotation_defects.py` 两个 probe 构造，不参与建树。

实际链路是：

```
da.build_case_text(row)            # vignette + "\nWhat is the most likely diagnosis?\nOptions:\n..."
  → run_case_branches(controller, env, str(case["case_text"]))
      → env.set_case(case_text); state.case_summary = env.get_case_summary()
```

`ThreadLocalEnv`（`scripts/eval_pipeline_medbullets.py:130`）的 `get_case_summary()`
只是原样返回 `set_case()` 存入的字符串，不追加任何东西。**泄漏来自调用方传入未剥除的
`case_text`。** 三家适配器（`diagnosisarena_adapter` / `medcasereasoning_adapter:178` /
`open_xddx_adapter:145`）共用同一个 `da.build_case_text()`，这解释了 DA/MCR/OX 三家同时中招
而 RareArena 干净（`rarearena_adapter:58` 只拼 question，不拼 options）。

需要修的调用点（全部传 `str(case["case_text"])`）：

| 文件 : 行 |
|---|
| `scripts/paper/run_diagnosisarena_m01.py:255`（已加 `--strip-mcq-options`，默认关） |
| `scripts/paper/run_diagnosisarena_stress_process_pool.py:162` |
| `scripts/paper/run_diagnosisarena_stress_p5_compile.py:189` |
| `scripts/paper/run_diagnosisarena_p5_bfs.py:396` |
| `scripts/paper/run_r3_r45_eval.py:495` |
| `scripts/eval_branch_creation_medbullets.py:274` |
| `scripts/eval_branch_talp_composed.py:605` |

改 `static_qa_env.py` 不会修复任何一个论文运行；改动应落在上表或 `da.build_case_text()`
的消费侧。

## 4c. 受影响的主表来源目录（逐行溯源）

| 论文行 | 主 metrics 文件 | 建树/annotate 根 | shared_trees 含 Options |
|---|---|---|---|
| APHHM DA @1/@2/MRR = 0.71/0.78/0.748 | `logs/diagnosisarena_d2_m01_v1/at1_c1_v1/per_case_compat_parallel_all100.tsv`（**离线 rematch**，非原生 mapper） | `pipeline_remaining76_v1` + `downstream_top2_w12_v1` | **100%** |
| APHHM MCR Acc@1 = 0.50 | `logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate/official_eval_llm_compat/summary.json` | `compat_synonym_v1` | **100%** |
| APHHM MCR R-Recall = 0.753 | 同目录 `official_eval_llm_compat_rr/summary.json` | 同上 | **100%** |
| AB01 / AB03 轴消融 | `logs/diagnosisarena_d2_m01_v1/c3_ab0{1,3}_v1/annotate/mapper/summary.json` | 同名目录 | **100%** |
| AB02 flat 0.68 | `logs/diagnosisarena_d2_m01_v1/c3_ab02_v1/annotate/mapper/summary.json` | 同上 | **100%** |
| 全部 Bxx 基线 | `runs/paper_v1/diagnosisarena_*/Bxx/replicate_01/mapper/records.json`；MCR 侧 `.../official_eval_llm/summary.json` | `run_baseline.py` + `load_runtime_cases()` | **无（已剥除）** |

基线的 manifest 里写着 `"input_mode": "open_vignette_no_options"`，`predictions.jsonl`
中无 `Options:`；流水线侧 100%。**主表每一行的"流水线 vs 基线"都是不等输入对比。**

顺带记录一个与本议题无关但已确认的问题：DA 主表的 0.71 是 `at1_c1_v1` 的**离线 rematch**
值（同一 TSV 里 `official_opt1=0.59` 与 `opt1=0.71` 并存），原生 live 加权约 0.700；
而 C3 消融臂（AB01/02/03）走的是原生 compat mapper，与 M00 锚点不同源。

## 5. 需要立刻做的事

1. ~~确认已发表数字的来源目录~~ — 已完成，见 §4c。主表每一行都受影响。
2. **重跑一组等输入对照**：进行中。`c3_ab02_clean_v1` 是最便宜的入口——AB02 是 flat 臂，
   `keep_leaves=False` 意味着 annotate 会从 `case_summary` 重新生成全部 L2 叶与全部分数，
   所以剥掉 summary 再 annotate 就是完全干净的运行，约 50 调用/例而非 300。
   见 `scripts/paper/run_c3_ab02_clean_input.py`。DA 之后按 OX → MCR 顺序推进。
3. **修 §4b 表里的 7 个调用点**（不是 `static_qa_env.py`），让建树与 mapper、基线走同一个
   `vignette_body()` 路径；MCR/OX 共用 `da.build_case_text()`，同一处修复覆盖三家。
4. 若等输入下管线相对基线的增量确实缩小到当前观察的量级（DA option@1 +0.00~0.04，
   MCR +0.03），则内部备忘录 `INTERNAL_MEMO_claims_at_risk_plain.md` 中 3.1/3.2/3.3
   三条主张都需要重写，而不只是弱化。

分级处置清单见 `PAPER_CLAIMS_AT_RISK_option_leak.md`（并行会话产出，四个数据集的波及范围
与逐行论文条目）；本文档与之互补：那份定范围，这份定机制归因与修复位置。

## 5b. 等输入重跑：进行中的运行与将要填的表

目标是把 APHHM / AB02 / 骨干 / 基线放到同一把尺子上。基线本来就是干净输入，骨干的
泄漏与干净两版都已有，缺的是管线侧。

| 运行 | 目录 | 做法 | 状态 |
|---|---|---|---|
| AB02 clean (DA) | `logs/diagnosisarena_d2_m01_v1/c3_ab02_clean_v1` | 剥 `case_summary` 后只重跑 annotate+mapper | annotate 完成，mapper 中 |
| APHHM clean (DA) | `logs/diagnosisarena_d2_m01_v1/aphhm_clean_v1` | 复用 VP 冻结，重跑 trees→p5→annotate→mapper | trees 完成（已校验 0/97 含选项），p5 中 |
| APHHM clean (MCR) | `logs/medcasereasoning_mcr_val_seq100_v1/aphhm_clean_v1` | 同上 + `--synonym-bind-repair` | 排队 |

AB02 与 APHHM 处理方式不同的原因：AB02 是 flat 臂，`keep_leaves=False` 使 annotate
重新生成全部 L2 与全部分数，所以剥 summary 再 annotate 就是完全干净的运行；
而 M00 的冻结树**两层都在泄漏下生成**（|L1|=4.6，14.1% 的 L1 标签命中选项，22% 的病例
gold 已进 L1；|L2|=17.6，30.4% 命中选项），且 annotate 保留这些叶子而非重生成，
候选集在建树时就定死，必须连树一起重建。

VP 冻结两边都复用已发表版本：其证据项不含选项文本（DA 1/100 含 gold、MCR 3/100，
与干净输入骨干的本底巧合率相同），复用可多固定一个变量，使差异只反映树与 L2。

待填的对比表（DA option@1 / MCR Acc@1）：

| 输入 | 骨干 4 调用 | AB02 ~50 调用 | APHHM ~300 调用 | 最佳基线 |
|---|---|---|---|---|
| 泄漏 | 0.67 / 0.47 | 0.68 / — | ~0.71 / 0.50 | 不适用（基线从未泄漏） |
| 干净 | 0.59 / 0.28 | **待填** | **待填** | 0.62 / 0.24 |

驱动脚本 `scripts/paper/run_aphhm_clean_chain.sh`（DA→MCR 顺序），
准备与校验逻辑在 `scripts/paper/run_aphhm_clean_input.py`。

## 6. 复现

```bash
export PYTHONPATH=src:scripts:scripts/paper
# 泄漏复现对照
bash scripts/paper/run_backbone_batch8.sh
# E21 候选集移植
python3 scripts/paper/run_backbone_e21_transplant.py --arm e21b_ab02cand_first \
  --candidates ab02 --selector first --score
python3 scripts/paper/run_backbone_e21_transplant.py --arm e21a_ab02cand_s4b \
  --candidates ab02 --selector s4b --workers 50 --score
# 池预算扫描（干净输入）
python3 scripts/paper/run_backbone_v1.py --dataset diagnosisarena \
  --arm e22_k7comp_nos4_k5 --select a --s2-k 7 --s2-mode complement --max-k 5 --score
```

所有产物在 `logs/backbone_v1/`；未改动任何已发表资产。
