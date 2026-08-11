# E1 arm provenance: APHHM hierarchical / options fixed

- Frozen sample: the same 200 cases (100 DA, 100 MCR) as every E1 arm.
- Model: `deepseek/deepseek-v4-flash-0731` through the repository runtime.
- Requested non-RAG concurrency: 50.
- Served: 187/200; all 13 failures had an out-of-range L2 candidate count and remain failures.
- Strict raw-proposal recall: 129/200 intention-to-analyse (DA 76, MCR 53).
- Strict top-1: 94/200 intention-to-analyse (DA 54, MCR 40).
- Mean exact source-option copy fraction among candidates: 0.4759; 119 served champions exactly copied a source option.
- Runtime: 200 semantic calls, 252 physical attempts, 155,126 input tokens and 619,385 output tokens.
- Routing: 18 observed providers; no Groq call was observed.
- Raw cache, responses, telemetry and log are preserved in the adjacent checksummed archive.

Against clean-fixed on 178 cases served in both arms, raw recall had 106
options-only gains versus 4 harms (+57.30 pp; exact McNemar p=9.24e-27), and
strict top-1 had 75 gains versus 2 harms (+41.01 pp; p=3.98e-20). Exact option
copy at the champion rose by 90 gains versus 4 harms (+48.31 pp; p=3.22e-22).
The options arm also used roughly half the output tokens and fewer physical
attempts. This is direct behavioral evidence that visible answer choices both
seed candidate labels and collapse the generative search, so the historical
clean/options comparison cannot be interpreted as an architecture effect.

This is a one-call APHHM-style input-sensitive micro-pipeline, not the full
production APHHM.
