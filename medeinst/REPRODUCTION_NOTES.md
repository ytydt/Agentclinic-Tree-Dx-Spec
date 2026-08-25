# Reproduction Notes: MedEinst / ECR-Agent

> This document records every implementation choice, whether it was specified by the paper,
> and what alternatives exist. If you're reproducing this paper, **read this first.**

---

## Paper

- **Title:** MedEinst: Benchmarking the Einstellung Effect in Medical LLMs through Counterfactual Differential Diagnosis
- **Authors:** Wenting Chen, Zhongrui Zhu, Guolin Huang, Wenxuan Wang
- **Year:** 2026
- **ArXiv:** https://arxiv.org/abs/2601.06636
- **Official code:** None found (abstract: "Source code is to be released.")

---

## What this implements

ECR-Agent inference: dual-pathway perception, three-level dynamic causal graph reasoning, evidence-audit scoring, and CGME critic-driven illness graphs plus exemplar memory (Algorithm 2). Evaluation implements Acc_base / Acc_rob / R_bias (§3.5). MedEinst's 5,383 DDXPlus-derived pairs are **not** available; this repo loads the parent Agentclinic **MCR400** split as the test corpus.

---

## Verified against

- [x] Paper equations (§4.2.3 S(d); Eq. 2 merge-or-prune τ=0.9)
- [x] Paper Algorithm box (Algorithm 2 DCI + CGME; Algorithm 1 not executed)
- [ ] Official code (none released)
- [ ] Well-known reimplementation (none)
- [x] Implementation based solely on paper text + user MCR400 substitution

---

## Unspecified choices

| Component | Our Choice | Alternatives | Paper Quote (if partial) | Section |
|-----------|-----------|--------------|--------------------------|---------|
| Embedding for Eq. 2 | NCBI MedCPT Query-Encoder (`ncbi/MedCPT-Query-Encoder`, CLS, max_length=64, L2 cosine) | bow_l2; Article-Encoder | cos(e_pscript, e_pobs); encoder unnamed | Eq. 2; parent HybridCPGRetriever |
| w_m, w_c, w_s | 1.0, 1.0, 1.0 in `base.yaml`; open held-out uses `audit_mode: auto` instead of retuned weights | Tune on a seed set | "weighting hyperparameters" | §4.2.3 |
| Exemplar count | top-3 cosine on Pobs text | BM25; retrieve by diagnosis | RetrieveExemplars(M, Pobs) | Alg. 2 |
| Diagnosis equality | normalized_exact | Raw string; UMLS; LLM judge | I(f(x)=ygt) | §3.5 |
| Decoding temperature | 0.0 | 0.7 / paper-unspecified | Zero-shot CoT | Appendix C |
| Intuitive CoT prompt | reconstructed JSON CoT | Official unreleased prompt | "Chain-of-Thought prompting" | §4.2.1 |
| Tables A7–A9 bodies | reconstructed from surviving bullets | Official appendix PDF | truncated extract | H.2 |
| OpenTargets query | generic GraphQL search | Author templates | "structured queries" | Appendix C |
| Merge(Gprev, Gsummary) | node/edge union | Critic rewrite of G | "merged ... further refined by the critic" | §4.1 |
| Critic feedback | free-text JSON `feedback` | Structured graph edits | "corrective feedback" | §4.1 |
| Nmatch counting | matching/conflict/penalty only | Also count support as match | "matching, conflict, and penalty" | §4.2.3 |
| LLM serving | OpenAI-compatible HTTP | Official Qwen3-32B endpoint | Qwen3-32B / GPT-5 | Table 1, §4.1 |

---

## Known deviations

| Deviation | Paper says | We do | Reason |
|-----------|-----------|-------|--------|
| Test set | MedEinst 5,383 control/trap pairs from DDXPlus | Parent-repo MCR400 unpaired narratives | User instruction; MedEinst not released |
| Acc_rob / R_bias | Defined on pairs | Reported `null` on MCR400 | MCR has no trap field |
| LiveSearch | PubMed + OpenTargets always | Disabled in demo config; HTTP optional | Offline walkthrough; APIs may 403 |
| Algorithm 2 PDF | Metric prose inserted between CGME lines 15–16 | Reconstruct DCI as lines 17–50 | Extraction artifact |
| Dtop vs Dset | Alg. 2 uses Dtop | Dtop := Dset | Unstated difference |
| Pivot JSON | Table A8 Pivot-only | Also allow type General | §4.2.2 requires Vb |
| Open DA/MCR selector | Table A9 LLM audit always | `audit_mode: auto` — DA keeps LLM audit, MCR keeps CoT@1. S(d) grid (53,760) overfit the even-id split | Held-out autopsy: S override harmed MCR |

---

## Expected results

| Metric | Paper's number | Dataset | Conditions |
|--------|---------------|---------|------------|
| Acc_base | 69.49 | MedEinst | Table 1 ECR-Agent (Qwen3-32B) |
| Acc_rob | 24.21 | MedEinst | Table 1 |
| R_bias | 33.75 | MedEinst | Table 1 |
| Acc_base | 55.49 | MedEinst | Table 2 DCI only |
| Acc_base | 40.25 | MedEinst | Table 2 Qwen3-32B CoT |

These numbers **cannot** be checked on MCR400. MCR400 Acc_base is a different task (free-text diagnosis, not 49 DDXPlus labels).

---

## Debugging tips

1. **JSON parse failures**: Tables A7–A9 require JSON. `src.utils.parse_json_object` strips fences; if the LLM returns prose, Dual-Pathway returns empty Dset.
2. **LiveSearch timeouts**: PubMed/OpenTargets are best-effort; empty retrieval still runs the pivot prompt on parametric knowledge (flagged).
3. **Pair metrics stay None**: MCR400 cases have `is_pair == False`. Supply `x_c`, `x_t`, `y_gt`, `y_bias` to compute Acc_rob / R_bias.
4. **CGME discards cases**: Algorithm 2 line 15 drops samples that never hit y_gt within 3 critic rounds.

---

## Scope decisions

### Implemented
- Dual-pathway perception — core of DCI (§4.2.1)
- DCGR three levels + shadow nodes — core of DCI (§4.2.2)
- S(d) evidence score and Table A9 judge — §4.2.3
- CGME critic loop, illness graphs, exemplar base — §4.1 / Alg. 2
- Acc_base, Acc_rob, R_bias — §3.5
- MCR400 loader — user substitute for MedEinst

### Intentionally excluded
- MDAgent / DyLAN baselines — comparison methods
- Table 2 ablation variants as separate agents — full ECR-Agent only
- MedEinst construction Algorithm 1 on DDXPlus — unreleased KB/pairs
- Physician QC protocol §3.4
- Neural training (Adam, dropout, etc.) — N/A

### Needed for full reproduction (not included)
- Official MedEinst 5,383 pairs and 853-case seed
- Live `qwen/qwen3-32b` OpenRouter endpoints (currently 404; client falls back to parent Set-B `qwen/qwen-2.5-72b-instruct`)
- GPT-5 critic endpoint used in the paper
- Untruncated Appendix H prompts

---

## References

- Pearl & Mackenzie (2018) — causal hierarchy mapping in footnotes 1–3
- Richens et al. (2020) — cited for intervention information gain; not an extra algorithm
- Fansi Tchango et al. (2022) DDXPlus — MedEinst source, not used as the MCR400 test set
- Sackett (1997) — EBM framing
