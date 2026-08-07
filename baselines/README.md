# Paper baselines (DiagnosisArena)

Adapters live under `scripts/paper/`; this directory holds **vendored upstream pins**
and readiness markers. Default runners use the shared OpenRouter/`RobustLLMClient`
backbone and (for RAG arms) `data/corpus/rag_index` + `data/corpus/cpg_index`.

## Arms → runtime

| Arm | Method (real multi-step) | Upstream / reference | Runtime |
|-----|--------------------------|----------------------|---------|
| B00 | Direct CoT | Internal | API |
| B01 | CoT + LLM planner + shared RAG | Internal | API + shared KB |
| B02 | Fixed-query retrieve → candidates → listwise rerank (no planner/L1) | Internal flat control | API + shared KB |
| B02-matched | Same flat algorithm, **compute-matched** to main-method structural budget (`structural_proxy_v1`) | RQ4 / G5 fair flat control | API + shared KB |
| B03 | Flat beam search (no L1) | Internal | API + shared KB |
| B04 | Dual-Inf: forward → backward → examine → optional reflect | https://github.com/betterzhou/Dual-Inf | API (shared model) |
| B05 | MDAgents: complexity → recruit → agents → consensus | https://github.com/mitmedialab/MDAgents | API (shared model) |
| B06 | Single-vendor MAC: 3 doctors + supervisor | https://github.com/rajpurkarlab/mixed-vendor-mac | API (shared model) |
| B07 | MEDDxAgent complete-profile (static; shared KB) | https://github.com/nec-research/meddxagent | API + shared KB |
| B08 / B09 | DeepRare / phenotype tools | RareBench/RareArena only | **gated on DiagnosisArena** |
| B10 | Mixed-vendor MAC | multi-vendor backends | **gated** (use B06 for single-vendor) |
| B11a | Official DiagnosisGPT CoD | https://github.com/FreedomIntelligence/Chain-of-Diagnosis | **GPU** + official disease DB (resource-unmatched) |
| B11b | CoD prompt on shared KB | same paper, shared KB | API + shared KB |
| B12 | SC-CoT-5 (RRF) | Internal | API |
| B13 | Self-Refine-1 | Internal | API |
| B15 | MedPrompt-style: KB exemplars + self-CoT + order-shuffle ensemble | https://github.com/microsoft/promptbase (adapted; no labeled train) | API + shared KB |
| B16 | MedRAG-style: retrieve → elicit diagnostic differences → reason | https://github.com/SNOWTEAM2023/MedRAG (shared KB, no private KG) | API + shared KB |
| B17 | **i-MedRAG**: iterative follow-up queries + per-query RAG | https://github.com/Teddy-XiongGZ/MedRAG (`follow_up=True`) | API + shared KB |

## Fairness policy

- **Same-resource arms** use only the project LLM (`RobustLLMClient`) and shared
  indices `rag_index` / `cpg_index`. They must not load private disease DBs or
  MedRAG/DDXPlus KGs.
- **B02 compute-matched** (`B02-flat-compute-matched`): per-case numeric caps from
  main-method `shared_trees` only (no tree candidates / gold). Explainer:
  [`runs/paper_v1/diagnosisarena_b02_compute_matched_v1/b02_vs_main_method_and_budget_match.md`](../runs/paper_v1/diagnosisarena_b02_compute_matched_v1/b02_vs_main_method_and_budget_match.md).
  Harness: `bash scripts/paper/run_b02_compute_matched_d2_seq100.sh`.
- **B11a** intentionally uses DiagnosisGPT weights + its disease DB; report as
  resource-unmatched.
- **B14 / A13** never fall back to MCQ option text when a freeze `candidate_pool`
  is absent; they propose candidates from the shared KB instead.

## Vendor install (optional, for prompt audit)

```bash
# Dual-Inf
git clone https://github.com/betterzhou/Dual-Inf.git baselines/dual_inf/upstream
git -C baselines/dual_inf/upstream checkout a8ea4a954479e38f318ae8a871192c4daa2b26ec

# MDAgents
git clone https://github.com/mitmedialab/MDAgents.git baselines/mdagents/upstream

# MAC (DiagnosisArena folder)
git clone https://github.com/rajpurkarlab/mixed-vendor-mac.git baselines/mac/upstream

# Chain-of-Diagnosis + DiagnosisGPT weights (GPU)
git clone https://github.com/FreedomIntelligence/Chain-of-Diagnosis.git baselines/chain_of_diagnosis/upstream
# download HF DiagnosisGPT-6B or 34B, then:
# touch baselines/chain_of_diagnosis/READY

# i-MedRAG (Teddy-XiongGZ/MedRAG; prompts/loop only — use shared KB)
git clone https://github.com/Teddy-XiongGZ/MedRAG.git baselines/imedrag/upstream
```

### i-MedRAG (B17)

```bash
bash scripts/paper/run_b17_imedrag_d2_seq100.sh
SMOKE_ONLY=1 bash scripts/paper/run_b17_imedrag_d2_seq100.sh
```

Pinned commit SHAs should be recorded in each arm's `manifest.json` at run time.

## CLI

### Smoke (live, limit=2)

```bash
bash scripts/paper/smoke_fixed_baselines.sh
```

### Full remaining non-ablation B-arms (B00/B03/B07/B12/B13)

```bash
bash scripts/paper/run_remaining_b_arms_d2_seq100.sh
# smoke only:
SMOKE_ONLY=1 bash scripts/paper/run_remaining_b_arms_d2_seq100.sh
```

B08/B09/B10 remain gated on DiagnosisArena (RareBench / multi-vendor).

### Full corrected baselines (d2_seq100_v1)

Writes to `runs/paper_v1/diagnosisarena_fixed_v1` (fresh root; does not resume old placeholder runs):

```bash
bash scripts/paper/run_fixed_baselines_d2_seq100.sh
# RAG only:
SKIP_PURE=1 bash scripts/paper/run_fixed_baselines_d2_seq100.sh
```

Legacy smoke roots (`diagnosisarena_smoke_live`, `diagnosisarena_rag_smoke_live`) contain
pre-fix alias/prompt-only results and must not be resumed for B02/B04–B06/B15/B16.

```bash
conda activate gnn-llm
PYTHONPATH=src:scripts:scripts/paper python scripts/paper/run_baseline.py \
  --arms B02-flat-matched-rerank,B15-medprompt-style,B16-medrag-kg \
  --subset-dir data/benchmarks/diagnosisarena/subsets/d2_seq100_v1 \
  --limit 5 --dry-run --score --mapper-mode deterministic_gold_blind
```
