# 本仓 LLM-as-judge 模型契约：Gemini 2.5 Flash

状态：2026-07-25  
适用范围：OX/MCR `paper_aligned_judge_v1` 及一切 transfer 正式评测中的 LLM 裁判调用

## 契约（必须遵守）

| 项 | 冻结值 |
|----|--------|
| **裁判模型** | **Gemini 2.5 Flash**（API slug 以实现时 `llm_client` / OpenRouter 为准，建议 `google/gemini-2.5-flash`） |
| **替换对象** | 论文或旧文档中的 **gpt-4o-mini**、**o4-mini**（及同类 mini 裁判）一律改为上表模型 |
| **运行环境** | conda 环境 **`gnn-llm`**（评测前必须 `conda activate gnn-llm`） |
| **网络 / VPN** | 调用前必须开 VPN：执行 **`clashon`**（`bash /home/wanghongyi/clashctl/clashon.sh`）；与现有 baseline 脚本一致 |
| **并发数** | **`--workers 50`**（正式 LLM 评测默认并发；树系统与基线 OX/MCR 评测共用） |
| **prompt** | 仍用已编列的论文裁判 **提示词原文**（见本目录各 `mcr_prompt*.md`）；**只换模型，不改 prompt 语义** |
| **summary 必填字段** | `judge_model=gemini-2.5-flash`，`judge_env=gnn-llm`，`vpn=clashon`，`workers=50`（或实际并发），并注明相对论文的模型替换 |

### 评测启动清单（`--judge llm`）

```bash
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate gnn-llm
bash /home/wanghongyi/clashctl/clashon.sh
# 然后：
python3 scripts/paper/run_ox_mcr_official_eval.py ... --judge llm --workers 50
# 或基线封装（实现后）：
# python3 scripts/paper/run_baseline_ox_mcr_eval.py ... --judge llm --workers 50
```

未激活 `gnn-llm`、未 `clashon`、或正式 LLM 跑未使用契约并发时，**不得**将结果标为符合本契约的 `paper_aligned_judge_v1` 主表。

论文原文中的模型名（gpt-4o-mini / o4-mini / GPT-4o）保留在 prompt 文档的 **Paper note** 中作溯源，**不得**作为本仓默认裁判。

## 联网验证摘要（人机一致性 / 临床对齐）

支持选用 Gemini 系作医疗相关裁判或临床对齐评估的公开证据（非本仓复现）：

1. **Wu et al., medRxiv 2025 / PSB 2026** — *Automated Evaluation of … eConsult Cases*  
   - https://doi.org/10.1101/2025.08.14.25332839  
   - LLM-as-Judge 评估 AI vs 专科医师 eConsult 一致性；**Gemini 2.5 Pro** LaJ：F1≈0.86，Cohen’s κ≈0.70，接近医师间 κ 区间（文中约 0.69–0.90）。  
   - 说明：证据为 **2.5 Pro** 同代 Gemini；本仓选 **2.5 Flash** 为同系列低成本裁判，summary 须写明该外推。

2. **OrthoArchives / OrthoScience 2025–2026** — orthopaedic MCQ vs 临床医生共识  
   - Gemini **2.5 Flash** 与医生共识对齐率 **69.1%**，高于同测 ChatGPT-5（58.8%）与 Grok-3（66.0%）。  
   - 支持 Flash 在临床决策类对齐上可用；任务为作答对齐而非纯 judge，作旁证。

3. **边界（诚实披露）** — *Human evaluators vs LLM-as-a-Judge … global health*（npj Digital Medicine / medRxiv 2025）  
   - Gemini-2.5-Pro 在部分全球健康准则上偏宽松；跨语言场景需谨慎。  
   - 本仓 OX/MCR 评测为英文病例文本，仍建议在人工抽检子集上报告与医师一致性（若有预算）。

## 与 Dual-Inf / MCR 论文的差异声明

| 论文默认裁判 | 本仓 |
|--------------|------|
| MCR 诊断：gpt-4o-mini | Gemini 2.5 Flash |
| MCR Reasoning Recall：o4-mini | Gemini 2.5 Flash |
| Dual-Inf 解释：GPT-4o（Appendix 3） | Gemini 2.5 Flash + 同 Appendix 3 prompt（已编列） |
| Dual-Inf 诊断自动比对：GPT-4o（Appendix 3） | Gemini 2.5 Flash + 同 Appendix 3 prompt（已编列） |

此替换属于 **判分器实现契约**，不改变 prompt 文本与指标定义；数字不得与论文表静默横比。
