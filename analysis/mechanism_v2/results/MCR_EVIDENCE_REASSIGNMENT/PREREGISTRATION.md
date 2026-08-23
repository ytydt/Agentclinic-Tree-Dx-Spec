# MCR_EVIDENCE_REASSIGNMENT_V1 — 预注册

> **状态：已执行完毕，结论 NO_GO（2026-08-21）。** G1 通过 167/167；dev 与 holdout 全部执行，
> 实际用 1801 次在线调用（与 §3 预算一致）、零 panel 裁决。`sym_evidence − frozen` = **−6**
> （p = 0.362），`sym_shuffle − shuffle_only` = **−1**（p = 1.000），**§7 登记的否证形态成立**。
> 结果与解读见 [`REPORT.md`](REPORT.md)。本预注册以下内容为执行前原文，未作事后修改。

写于 2026-08-21，**在任何在线调用之前**。上游依据：
[`MCR_SELECTION_LAYER_AUDIT`](../MCR_SELECTION_LAYER_AUDIT/REPORT.md)（零调用）与
[`MCR_EVIDENCE_SYMMETRY_GATE_V1`](../MCR_EVIDENCE_SYMMETRY_GATE/REPORT.md)（PASS，128 调用）。

## 0. 靶与已被排除的靶

MCR 在 167 例池内可达队列上丢 63 例（冻结 104/167）。前序工作已用实验或零调用审计排除四条干预：

| 已排除 | 依据 |
|---|---|
| 换候选集来源 | Collapse3c 换池净可达性 **−13**（+9/−22），并集天花板仅 +9；APHHM L2 另有证据契约为空、队列仅 100 例、80% 标签未判定三重阻碍 |
| 收窄名单（截断） | `MCR_SELECTOR_TRUNCATION_V1` NO_GO：5 宽 −2 例（p=0.754），3 宽 −5 例 |
| 改比较器 family-vs-subtype 判据 | `partial_parent_or_component` 仅占 63 例中的 **8** 例 |
| 重排 payload | 生成序在 dev 与 holdout 上同时胜过 8 个离线替代排序 |

剩余唯一存活假设：**逐候选证据分配带有次序性偏置**。门已证实该偏置存在且主要是写法产物——对称重推使支持侧不对称从 48/63 降到 28/63（均数差 1.56 → 0.59，符号检验 p = 0.0031），且收窄几乎全部来自冠军一侧缩水（3.84 → 2.81），集中在 payload 位置 0 的冠军（Δ −1.25 vs 位置 >0 的 −0.53）。

本实验测：**去掉这个偏置之后，比较器会不会改选正确候选。**

## 1. 队列

167 例池内可达病例（registry 含至少一个 panel 判为 `complete_equivalent` 的标签）。
**dev = mcr_v1 + mcr_v2（73 例，26 例损失）；holdout = mcr_200b（94 例，37 例损失）。**
分阶段执行：dev 先跑，过futility 门后才动 holdout。确证性主张只能来自 holdout。

冻结基线（已知，零调用）：complete **104/167**，C∪P **112/167**，均宽 8.54。

## 2. 干预与解缠设计

干预是**替换逐候选证据**：每个候选用 `aphhm_c_symmetric_candidate_evidence.txt` 单独一次调用重推 `support_spans`/`contradict_spans`（输入仅 `{vignette, candidate}`，对手不可见、gold 不可见、stance 与生成序不可见），过运行时同一逐字校验（`AphhmCPipeline._verbatim`），再按 `_note` 的 `[:4]`/`[:3]` 截断填入 payload。除此之外**一切保持字节一致**：同一 tournament prompt、同一候选集合、同一 stance 分组、同一模型与温度 0.0。

必须解缠的混杂：门显示证据膨胀集中在 payload 位置 0，而审计显示比较器有 **77.8%** 的位置顺从性。若只换证据而不动顺序，无法区分"证据不再偏置"与"位置仍在主导"。因此设 2×2：

| 臂 | 证据 | payload 顺序 | 角色 | 在线调用（dev / holdout） |
|---|---|---|---|---|
| `frozen` | 冻结 | 生成序 | 基线 | **0 / 0**（G1 恒等，见 §4） |
| `sym_evidence` | 对称重推 | 生成序 | **唯一可部署臂** | 73 / 94 |
| `shuffle_only` | 冻结 | 定种打乱 | 位置因子的对照 | 73 / 94 |
| `sym_shuffle` | 对称重推 | 定种打乱 | 无位置信号下的证据效应 | 73 / 94 |

- **只有 `sym_evidence` 是候选部署方案。** 打乱两臂是机制探针：生成序已被审计证明是最优可得排序，故意打乱它必然掉点，其价值在于测出 104 里有多少依赖顺序。
- 打乱须可复现：`random.Random(bc.stable_hash({"slice": sl, "case_id": cid})).shuffle(...)`，实际顺序写入产物。
- 证据重推的调用键为 `{module, prompt, {vignette, candidate}}`，**与顺序无关**，因此 `sym_evidence` 与 `sym_shuffle` 共用同一批证据调用，不重复计费。

## 3. 预算

| | 证据重推 | 选择器 | 小计 |
|---|---|---|---|
| dev（73 例 / 634 候选） | 634 | 3 × 73 = 219 | **853** |
| holdout（94 例 / 792 候选） | 792 | 3 × 94 = 282 | **1074** |

门已缓存 63 例损失的 126 个 `(case, candidate)` 证据调用（其中 dev 52 个）。启动前把
`MCR_EVIDENCE_SYMMETRY_GATE/cache/symmetric_evidence.json` 复制为本实验缓存的种子，键完全一致，可直接复用；因此 dev 实际约 **801** 次、holdout 约 **1000** 次。

**零 panel 裁决。** 依据：运行时 `champion_of` 强制冠军落入 shortlist，shortlist 即 registry 的 `preferred_label` 集合，而该池 3500 个标签 **100% 已有临床判定**（0 未判定）。截断实验 501 行实测 off-shortlist 0 行、冠军未判定 0 行。本实验不引入池外标签，故不产生新的裁决需求。若仍出现未判定冠军，按 §6 记为 `unjudged` 并从主端点分母剔除，同时在报告中披露例数。

## 4. 保真门 G1（零调用，先于一切在线调用）

以冻结证据 + 生成序重建 payload，用 `bc.stable_hash({module, prompt, payload})` 查冻结 LLM 缓存，比对 `stages.frontier_selector`。要求 **167/167 字节恒等**。这与 `MCR_SELECTOR_TRUNCATION_V1` 的 G1 是同一检查（当时 400/400 通过），此处复核以确保证据替换管线没有改动基线路径。G1 不通过则整实验作废，不得开任何在线调用。

G1 通过即意味着 `frozen` 臂成本为零。

## 5. 端点

**主端点**：clinical-complete 冠军数（167 例队列），对 `frozen` 做配对精确 McNemar。
三个对比的 Holm-Bonferroni 校正族为 `{sym_evidence, shuffle_only, sym_shuffle}` vs `frozen`。

**共同主端点（保护门）**：C∪P（complete ∪ partial）。登记理由：门测得对称重推使证据**总量下降**（冠军 for 均数 3.84 → 2.81），而截断实验已观察到证据变稀时比较器**退向更粗的父类**。若 complete 上升而 C∪P 显著下降，说明是在拿 partial 换 wrong，不得记为收益。

**次要端点**：task（MCR 冻结 Prompt-7；MCR 上 clinical-complete → task 为 87/87，故两者应同向）、legacy `dc.match`、与 `frozen` 的冠军一致率、**与 payload 位置 0 的一致率**（去偏置后位置顺从性是否下降，是机制的直接读数）。

**机制读数**：新损失集上的 C-vs-W 不对称；被救回的病例是否正是门中不对称收窄最大的那些（配对相关）；`sym_shuffle − shuffle_only` 与 `sym_evidence − frozen` 之差即证据×位置交互。

## 6. 门与判定规则（先于结果固定）

**dev 阶段只设 futility 门，不设疗效门。** 理由：dev 仅 26 例损失，McNemar 在此样本上功效很低；且门报告已记录 holdout 的不对称收窄幅度弱于 dev（均数差 0.86 vs 0.19），按 dev 幅度设阈值会系统性过乐观。

- **futility 停止** = `sym_evidence` 的 Δcomplete ≤ 0 **且** 冠军相对 `frozen` 改变率 < 15%。
  含义：证据去偏置既没带来收益、也没让比较器动起来 → 该假设被否，MCR 选择层项目关闭。
- 否则进入 holdout。**确证性主张仅来自 holdout**，判定为 Δcomplete > 0 且 Holm 校正后 p < .05，**且** C∪P 未显著下降（配对 McNemar p ≥ .05 或 Δ ≥ −3）。
- 若 complete 上升而 C∪P 保护门失败：记为 **换汇失败**，不得写成收益。

## 7. 预测（先于结果登记）

- `sym_evidence` vs `frozen`：**+2 到 +10 例**（167 例上 104 → 106–114）。理由：证据偏置是真的，但比较器 77.8% 顺从位置而本臂不动位置，只有证据本来是决定因素的那部分能翻。
- `shuffle_only` vs `frozen`：**−5 到 −15 例**。理由：生成序是最优可得排序（审计 Q4），打乱它是在毁信号；这也给"任何 payload 扰动都会让约 9% 冠军改变"提供标定（截断实测 15/167）。
- `sym_shuffle` vs `shuffle_only`：**正**，且幅度大于 `sym_evidence − frozen`。理由：位置信号被移除后，证据成为主要判据，去偏置的作用应更充分显现。
- 交互为正：即 `(sym_shuffle − shuffle_only) > (sym_evidence − frozen)`。若观察到交互为负，说明位置与证据是同一信号的两种表现，应据此重写机制叙述。
- 登记的反向风险：C∪P 下降 3 例以上，即比较器在更稀的证据下退向粗父类。

**明确的否证形态**：若 `sym_evidence ≈ frozen` **且** `sym_shuffle ≈ shuffle_only`，则证据不对称虽已被证明是写法产物，却并非比较器实际使用的判据；那 63 例在证据层与选择层均不可干预，本条线结束。此形态是有信息量的负结果，须照实报告。

## 8. 不做什么

- 不改冻结日志与冻结 LLM 缓存（只读）；产物写入 `results/MCR_EVIDENCE_REASSIGNMENT/`。
- 不改 tournament prompt、不改候选集合、不改分组、不改 stance 归属。本实验只替换证据与（在探针臂中）顺序。
- 不用 dev 结果调整 §6 的阈值或 §7 的预测。
- 不把 `shuffle_only` / `sym_shuffle` 写成可部署方案。
- 不把本实验结果外推到 DA：DA 的靶是纵向补全（`DA_FINALS_AXIS_COMPLETION`），其 clinical-complete 仅 17/400、`partial_parent` 210，失败结构与 MCR 不同。
- 不把 800 例开发集上的结果当确证；truth tier 是模型面板（五分类 exact accuracy 0.7082），≤5pp 的对比须做面板误分类敏感性分析。

## 9. 复现

```bash
python3 analysis/mechanism_v2/mcr_evidence_reassignment.py --g1                    # 0 次调用
python3 analysis/mechanism_v2/mcr_evidence_reassignment.py --stage dev              # ~801 次
python3 analysis/mechanism_v2/mcr_evidence_reassignment.py --stage holdout          # ~1000 次
python3 analysis/mechanism_v2/mcr_evidence_reassignment.py --score                  # 0 次调用
```
