# Backbone v1 实验结果总览

Updated: 2026-08-07

> **⚠ 全表读法已变更（2026-08-07）。**
> 本文件中所有"骨干 vs AB02 / M00"的对比**输入不对等**：流水线臂的
> `case_summary` 逐字包含金标准（MCQ 选项块，MCR 上 100% 位于选项 A），
> 骨干与基线的病历被 `vignette_body()` 剥离。把同一份上下文喂给骨干后，
> **4 次调用追平 84 次调用的 AB02**（MCR 0.47 vs 0.44；DA 0.65/0.67 vs 0.64/0.68），
> 残差落差消失。详见 `INTERNAL_MEMO_mcq_option_leak.md`。
>
> 下表中骨干各臂之间的横向比较仍然有效（输入一致）；
> 与 AB02 / M00 / 已刊基线的纵向比较在重跑之前不成立。

## 方法

四步独立骨干（`src/agentclinic_tree_dx/backbone.py`），不经 `controller`：

1. S1 parse → syndrome_frame + salient_findings + key_facts  
2. S2 wide_ddx（或 kb_only RRF 消融）→ 病名列表  
3. S3 entity_filter → shortlist k  
4. S4 select（a=首项 / b=自由 / c=粒度约束）→ champion  

预算：llm_ddx 路径约 **4 calls/例**（k 消融重跑 S3+S4 时为 2）。

产物：`logs/backbone_v1/`。评测复用 DA `typed_llm_disagreement_rag` mapper 与 MCR Prompt-7 judge。

## 批 0（零调用）

见 `z1_mcr_diag.json`、`z2_da_funnel.md`。MCR 与 DA 同构：最终标签 ≥95% 出自首次 DDx；C 桶（选错）仍是最大单一损失。

## 批 1–3 主表（DA option@1 同标度）

| 配置 | calls/例 | lexical | option@1 | 备注 |
|---|---:|---:|---:|---|
| B02 native（已刊） | ~2 | — | 0.56 | flat retrieve-rerank |
| B02 compute-matched（已刊） | ~9 | — | ~0.48 | |
| AB02 / M00（已刊） | ~84 | 0.64 | 0.68 / 0.70 | 完整流水线 |
| **骨干 v0 s4b k5** | **4** | 0.36 | **0.50** | E1 |
| 骨干 s4a k5 | 3* | 0.36 | — | *复用 S1–S3 |
| 骨干 s4c k5 | 4* | 0.31 | — | C 桶未改善，未通过 |
| **骨干 s4b k8** | 4 | 0.37 | **0.52** | E5；llm_ddx 族最优 |
| **骨干 kb_only k5** | 2+retr | 0.44 | **0.57** | E3；消融无效，见下 |
| 骨干 k=2 complement | 5 | 0.41 | **0.58** | E7 |
| 骨干 k=3 complement | 6 | 0.40 | **0.59** | E7 |
| 骨干 k=3 partition | 6 | **0.43** | 0.57 | E8；池最小、覆盖最高 |
| 骨干 严格 S3（下标式） | 4 | 0.38 | **0.59** | E10；应作为默认实现 |
| 骨干 k=3 + 删除 S4 | 6 | **0.44** | 0.55 | E16；lexical 最优 |
| 骨干 kb_only + 严格 S3 | 2+retr | 0.28 | 0.43 | E10；E3 的正确版本 |

\* 相对复用臂的边际调用。

> option@1 不构成独立机制：上述 llm_ddx / kb_only 四臂均满足
> `option@1 ≈ lexical + 0.20×(1−lexical)`，残差 ≤0.03。
> **例外**：S4-d/S4-e 等会按证据分重排整个 shortlist 的臂偏离该关系达 +0.10
> （S4-d：lexical 0.31 但 option@1 0.55），因为 option@1 读的是整张排序表。
> 跨臂比较 option@1 时必须先确认 `ordered_diagnoses` 的排序来源相同。

### E3 判定 —— ⚠ 已作废，由 E10 取代（2026-08-07）

原判定：0.57 − 0.50 = +0.07 → 不确认 LLM-DDx 为主机制。

**该消融无效。** `backbone.py` 的 S3 不校验 `shortlist ⊆ S2`，kb_only 臂里
20%（98/500）的 shortlist 条目、36% 的最终 champion 不在 KB 池中，
17 例的金标准仅经 S3 才出现——S3 把 LLM 的生成式召回重新灌了回来。

**E10（S3 改为返回池内下标，越池 0/500）给出正确判定**：同一严格 S3 下
LLM 入口 option@1 0.59 vs KB 入口 0.43，**Δ=0.16 → LLM-DDx 入口确认为承重机制**。

### E4/E5 判定 —— ⚠ 已降级为"未测出差异"（2026-08-07）

`e7_k3_comp` 与 `e8_k3_part` 的首次 S2 调用载荷完全相同，可作天然重测：
temperature=0 下 96/100 的列表逐项不同，首项正确率 0.36 vs 0.41。
**n=100 的噪声地板为 ±0.05，臂间差异小于约 0.10 不可解释。**

- S4-c vs S4-b（Δ 0.05）、k=8 vs k=5（Δ 0.02）**均在噪声内**，原判定作废。
- 骨干 vs AB02 的 0.28、E10 的 0.16 不受影响。

### 第二轮（E7–E20，25 个臂）

见 `RESIDUAL_GAP_ANALYSIS_R2.md`。三条主要结论：

1. **入口广度是唯一可移植且跨数据集复现的机制。** S2 改 k 次异条件调用取并集，
   +1 次调用即 DA option@1 0.50→0.58、MCR 0.24→0.28，k=2 饱和。
   等预算下 partition 条件化优于 complement 重采样（池小 23%、覆盖更高）。
2. **选择阶段不存在可移植机制。** 八种实现（稀疏单胜者 / top-3 秩权重 /
   稠密序数+§13 门控 / 单次全矩阵；双向分离 vs 合并；4→32 次调用；
   复合 vs 原子化事实）在两个数据集上**全部低于"0 次调用取 S3 首项"**。
   删掉 S4 反而最好（lexical 0.44 vs 0.40）。
3. **AB02 的 71% 预算在 flat 臂里是死算力。** 97/100 病例的 level-2 分支
   `prior` 仍是精确的 1/k，即叶后验只经历**一次**序数更新；
   bfs 缓存里 38.6 次/例的证据裁决作用于被压平成单节点的 L1 轴，
   数学上不可能移动最终排序。

## MCR

| 配置 | 切片一 | 切片二 | 合并 |
|---|---:|---:|---:|
| B02 | 0.17 | — | — |
| 骨干 s4b（k5 / k8） | **0.24** | **0.22** | 0.23 |
| 骨干 k=3 complement（E7） | **0.28** | — | — |
| AB02 flat（本轮新增） | 0.44 | 0.47 | 0.455 |
| M00 | 0.50 | 0.46 | 0.48 |

骨干高于 B02，低于完整系统。
**M00 − AB02 合并 Δ=0.025，符号检验 p=0.405，方向在两切片间翻转 → L1 层级轴在 MCR 上无显著贡献**
（DA 上同为 0.02）。配对明细见 `analysis/mcr200_ab02_v1/`。

## E6 确认集

见 `e6_preregistration.md`（已锁定）。  
配置：`confirm_v2_s4b_k8`，MCR 切片二，阈值 Acc ≥ 0.22。

**结果：Acc@1 = 0.22（22/100）→ 达到预注册主判定阈值，通过。**  
切片一同族 v0_s4b_k5 为 0.24；B02=0.17；不与 M00 比。

## RA

已下线。见 `INTERNAL_MEMO_rarearena_retired.md`。

## 资产

跑前快照：`analysis/asset_guard/20260806T065220Z/`。  
本轮只写 `logs/backbone_v1/` 与 `analysis/backbone_v1/`。
