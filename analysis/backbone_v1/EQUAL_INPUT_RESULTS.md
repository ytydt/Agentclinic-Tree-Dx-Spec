# 等输入重跑结果汇总：去掉 MCQ 选项泄漏后各系统的真实位置

日期 2026-08-07 · 配套 `RESIDUAL_GAP_ANALYSIS_R3.md`（机制与修复位置）与
`PAPER_CLAIMS_AT_RISK_option_leak.md`（论文条目分级）

> **⚠ 本文档所有"泄漏输入 → 干净输入"的差值都已作废，见 `CONFOUND_AUDIT.md`。**
> 穷举核查发现干净运行与已发表运行之间还隔着一次 annotate 重写（07-28/08-01）、
> 一次 answer mapper 重写（07-29）和一次 provider 路由改动（08-06）。其中 mapper
> 重写在同一批预测上就让 MCR option@1 从 0.81 掉到 0.61，占先前所报"泄漏效应"
> 的一半。**同代码同配置的对照正在跑**，在它们出来之前，本文档只有第 5 节
> 列出的同代次内部比较可用。

**三句话结论（前两句已被 §CONFOUND_AUDIT 推翻，保留供追溯）。**
1. **MCR 上泄漏是决定性的**：同配置逐例配对，APHHM 从 0.81 掉到 0.41
   （41:1，p=2e-11）。这一条无混杂，可直接采信。
2. **DA 上泄漏效应目前测不出来，先前写的 −0.09 是混杂的**：论文的 0.71 用
   `l1_calib=b12`，我的干净运行用 `off`，而 b12 本身在同为泄漏的 76 例上就值 +0.09。
   见 §1.1。同配置对照正在跑。
3. **对内结论（层级有回报）不受影响**：APHHM 与 AB02 的干净对比两边都是 `off`，
   +0.14（22:8，p=0.016）。

---

## 1. DiagnosisArena（n=100，option@1，同一 compat mapper，无 synonym-bind）

| 系统 | 调用/例 | 泄漏输入 | 干净输入 | 差 | l1_calib（泄漏/干净） |
|---|---:|---:|---:|---:|---|
| APHHM（完整管线） | ~300 | 0.71 | 0.62 | ⚠ 混杂 | **b12 / off** |
| AB02（flat / 无 L1） | ~50 | 0.68 | **0.48** | +0.20 | off / off |
| 骨干 e7_k3_comp | 6 | 0.67 | **0.59** | +0.08 | 不适用 |
| 骨干 v0_s4b | 4 | 0.67 | **0.50** | +0.17 | 不适用 |
| 最佳基线 MEDDxAgent (B07) | ~30 | 不适用 | 0.62 | — | 不适用 |

APHHM 干净版另有 @2 = 0.67、MRR = 0.645（已发表泄漏版 0.78 / 0.748）。
除 APHHM 行外各行的两侧配置一致，可直接相减。

### 1.1 APHHM 那一行为什么不能直接相减

论文 DA 的 0.71/0.78 来自 `pilot24_compat_b12_live_v1`（0.75，n=24）与
`remain76_compat_b12_live_v1`（0.6842，n=76）合并，两者都是 `l1_calib=b12`。
**全库里只有这两个运行用 b12**；所有消融臂（AB01/AB02/AB03/AB21/AB22）和所有干净
运行都是 `off`。在同一批 76 例、同为泄漏输入上逐例配对：

| 对比（n=76，逐例配对） | Δ | 独对数 | p |
|---|---:|---|---:|
| 泄漏 off (0.5921) → 泄漏 b12 (0.6842)　纯 l1_calib 效应 | **+0.092** | 7 : 14 | 0.19 |
| 泄漏 off (0.5921) → 干净 off (0.6184)　纯泄漏效应 | **+0.026** | 17 : 19 | **0.87** |
| 泄漏 b12 (0.6842) → 干净 off (0.6184)　先前记的那个数 | −0.066 | 14 : 9 | 0.40 |

先前的 −0.09 是把 l1_calib 的 −0.09 和泄漏的 +0.03 加在了一起。按同配置读，
**DA 上 APHHM 的 option@1 对泄漏不敏感**（36/76 例翻面而净差近零，说明 DA 在
n=76 上的噪声地板本身就很宽）。

两个保留意见：(a) 作为 `off` 对照的 `pipeline_remaining76_v1` 是 7-22 的旧版
产物（带 `PERF_REGRESSION_NOTE.json`，JSON-parse 修复后重生成过 11 例），
schema 里没记 `granularity_mode`，未必只差 l1_calib 一项；
(b) 正在跑 `aphhm_clean_v1_b12_v1`（干净输入 + b12，复用干净 frozen 树只重跑
annotate+mapper），它对论文 0.71 才是唯一无混杂的对照。

**顺带一个与泄漏无关的独立问题**：论文 `tab:org-axis` 把 APHHM(b12)=0.71 与
AB01/AB02/AB03(off)=0.51/0.68/0.37 并排比较，而 b12 只有完整模型享受到。
若 +0.09 稳健，该表三个 Δ 全都被一个只加在完整模型上的校准档位抬高了。

### 配对检验（McNemar 精确检验，逐例 option@1）

| 对比 | A 胜 | B 胜 | p |
|---|---:|---:|---:|
| APHHM 干净 > AB02 干净 | 22 | 8 | **0.016** |
| APHHM 干净 vs 最佳基线 B07 | 16 | 16 | **1.00** |
| AB02 泄漏 > AB02 干净 | 26 | 6 | 5.4e-4 |
| APHHM 干净 vs AB01 泄漏（固定 ICD 轴） | 23 | 12 | 0.089 |

## 2. MedCaseReasoning（n=100，Acc@1，官方 LLM judge / Prompt 7 / Gemini 2.5 Flash）

| 系统 | 泄漏输入 | 干净输入 | 泄漏值 |
|---|---:|---:|---:|
| APHHM（完整管线） | 0.50 | **0.26** | +0.24 |
| AB02（flat / 无 L1） | 0.44 | 运行中 | — |
| 骨干 e7_k3_comp（6 调用） | 0.46 | **0.28** | +0.18 |
| 骨干 v0_s4b（4 调用） | 0.47 | **0.24** | +0.23 |
| 最佳基线 MEDDxAgent | 不适用 | 0.24 | — |

MCR 的泄漏最严重（gold 恒为选项 A），泄漏值 +0.18 ~ +0.24。干净输入下
**6 次调用的骨干（0.28）高于 ~300 次调用的 APHHM（0.26）**。

MCR 两侧配置完全一致（`l1_calib=off`、`granularity=compat`、`synonym_bind_repair=ON`），
不存在 DA 那种混杂。同一 mapper 口径（option@1）下逐例配对：泄漏 0.81 → 干净 0.41，
**泄漏独对 41 例、干净独对 1 例，p = 2.0e-11**。这是全部证据里最硬的一条。

## 3. 怎么读这两张表

**调用预算没有回报。** DA 干净输入下 6 调用 0.59 → 300 调用 0.62，涨 0.03；
MCR 上 6 调用 0.28 → 300 调用 0.26，反而降。论文 `tab:budget` 一节
"structured hypothesis management contributes beyond repeated flat sampling"
的证据基础不存在。

**层级组织有回报，而且比论文声称的更强。** DA 干净输入下 APHHM − AB02 = +0.14，
p=0.016；泄漏下只有 +0.03。同理 AB01（固定 ICD 轴）与 AB03（随机轴）的对比也应在
干净输入下重测——目前 AB01/AB03 仍是泄漏版，与干净版 APHHM 不可直接相减。

**对基线的一切优势陈述都要撤。** DA 上 16:16、p=1.00 是最直接的反证：
不是"优势缩小"，是逐例层面完全无差别。这一条不受 §1.1 的混杂影响——它比的是
两个都在干净输入下的系统。

**泄漏对不同系统的价值不同，这本身有信息量。** 泄漏对 AB02 值 +0.20、对 4 调用骨干
值 +0.17，对 6 调用骨干只值 +0.08，对 APHHM 在 DA 上测不出（+0.03，p=0.87）、
在 MCR 上却值 +0.40。越依赖"把候选列全"的系统，从选项里白拿的越多；已经有自己
候选生成能力的系统，边际收益小。DA 与 MCR 的巨大差别应该出在选项构造上：DA 的
干扰项是同族近邻，抄了也未必对；MCR 的 gold 恒为 A，抄即得分。

## 3.5 干净运行的工作量核验（回应"跑得太快"的疑问）

墙钟看着短是并发和分批造成的错觉，不是少干了活。逐例口径下干净版一律**更慢**：

| 运行 | annotate 耗时/例 | 缓存条目/例 | annotate 后 \|L2\| |
|---|---:|---:|---:|
| APHHM 干净 DA | 364.3 s | 80.8 | 31.75 |
| M00 泄漏 DA | 351.4 s | 73.6 | 17.64 |
| APHHM 干净 MCR | 356.1 s | 81.6 | 30.60 |
| MCR 泄漏 | 246.0 s | 81.6 | 17.90 |

泄漏运行的 annotate 一片叶子都没加（17.64 = frozen 的 17.64），干净运行则把 L2
从 18.3 补到 31.8——没有选项可抄时 targeted gapfill 大量触发。100 例全部
`status=OK`、零 error，mapper `n_ok=100`。两边缓存逐文件比对 0/204 字节相同，
不存在复用。输入剥除也逐例验过：干净 frozen 树 `含 Options: = 0/101`，
泄漏版 `76/77`。

先前"快得反常"的印象来自拿 `pipeline_remaining76_v1/pipeline_summary.json` 的
`total=178s` 做参照——那是一次全部命中缓存的续跑汇总，不是原始构建耗时。

## 4. 尚未完成

- **DA 同配置对照 `aphhm_clean_v1_b12_v1`（干净输入 + l1_calib=b12）运行中**，
  这是 §1.1 里唯一能对齐论文 0.71 的数。在它出来之前，DA 上"泄漏抬高了多少"
  没有可引用的点估计。
- MCR AB02 干净版（`logs/medcasereasoning_mcr_val_seq100_v1/c3_ab02_clean_v1`）运行中。
- AB01 / AB03 的干净版未跑。`tab:org-axis` 的 0.37 → 0.71 三点全部是泄漏版；
  要支撑"层级有效"这一条，应重测该表全部三臂。
- OpenXDDx 未跑。按配套备忘录，OX 的泄漏在截断后存活率最高（97%），预计下修最大。
- 干净输入下的成本统计（case_results 未记录 `llm_calls`，调用数沿用已发表运行的估计）。

## 5. 产物与复现

```bash
export PYTHONPATH=src:scripts:scripts/paper
# APHHM 等输入（DA 后接 MCR，含 VP 冻结复用与剥除校验）
bash scripts/paper/run_aphhm_clean_chain.sh
# AB02 等输入（flat 臂可只重跑 annotate）
python3 scripts/paper/run_c3_ab02_clean_input.py --dataset da  --workers 25
python3 scripts/paper/run_c3_ab02_clean_input.py --dataset mcr --workers 25
# MCR 官方 Acc（口径同已发表：compat_parallel_final_ranking + LLM judge）
python3 scripts/paper/run_ox_mcr_official_eval.py --dataset medcasereasoning \
  --run-dir <run> --subset-parquet data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/cases.parquet \
  --judge llm --ddx-k 5 --ddx-source compat_parallel_final_ranking \
  --projection-subdir eval_projection_compat --build-projection --resume \
  --skip-reasoning-recall --workers 50 --out-name official_eval_llm_compat
```

| 运行 | 目录 |
|---|---|
| APHHM 干净 DA | `logs/diagnosisarena_d2_m01_v1/aphhm_clean_v1` |
| APHHM 干净 MCR | `logs/medcasereasoning_mcr_val_seq100_v1/aphhm_clean_v1` |
| AB02 干净 DA | `logs/diagnosisarena_d2_m01_v1/c3_ab02_clean_v1` |
| AB02 干净 MCR | `logs/medcasereasoning_mcr_val_seq100_v1/c3_ab02_clean_v1` |
| 骨干全部臂 | `logs/backbone_v1/{diagnosisarena,medcasereasoning}/` |

三个干净运行的输入都逐例校验过：`case_summary` 含 `Options:` 块 0/100，含 gold 原文
1/100（DA 的本底巧合病例）。VP 冻结复用已发表版本，其证据项不含选项文本。
