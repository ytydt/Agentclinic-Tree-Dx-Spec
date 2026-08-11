# E1 arm provenance: APHHM hierarchical / clean shuffled blocks

- Frozen sample: the same 200 cases (100 DA, 100 MCR) as every E1 arm.
- Model: `deepseek/deepseek-v4-flash-0731` through the repository runtime.
- Requested non-RAG concurrency: 50.
- Served: 189/200. The 11 contract-invalid responses remain failures; no imputation was used.
- Invalid contracts: ten responses had an out-of-range L2 count and one had an out-of-range L1 count.
- Strict raw-proposal recall: 21/200 intention-to-analyse.
- Strict top-1: 17/200 intention-to-analyse.
- Runtime: 200 semantic calls, 331 physical attempts, 173,200 input tokens and 1,208,051 output tokens.
- Routing: 17 observed providers; no Groq call was observed.
- Raw cache, responses, telemetry and log are preserved in the adjacent checksummed archive.

Paired with clean-fixed on 180 cases served in both arms, raw recall had 8
shuffled-only versus 9 fixed-only cases (delta -0.56 pp; exact McNemar p=1),
while strict top-1 had 9 shuffled-only versus 8 fixed-only cases (delta +0.56
pp; p=1). Yet 133/180 champions changed. Thus block/order formatting caused
large decision instability without directional strict benefit in this run.

This remains a one-call APHHM-style input-sensitive micro-pipeline, not the
full production APHHM.
