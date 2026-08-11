# E1 arm provenance: AB02 flat / clean shuffled blocks

- Frozen sample: the same 200 cases (100 DA, 100 MCR) as every E1 arm.
- Model: `deepseek/deepseek-v4-flash-0731` through the repository runtime.
- Requested non-RAG concurrency: 50.
- Served: 199/200. One response ultimately had an out-of-range candidate count and remains a failure.
- Strict raw-proposal recall: 19/200 intention-to-analyse.
- Strict top-1: 11/200 intention-to-analyse.
- Runtime: 200 semantic calls, 251 physical attempts, 122,302 input tokens and 569,618 output tokens.
- Routing: 15 observed providers; no Groq call was observed.
- Raw cache, responses, telemetry and log are preserved in the adjacent checksummed archive.

Against flat clean-fixed on 199 common served cases, raw recall had 7 gains/8
losses (-0.50 pp; exact McNemar p=1) and strict top-1 had 4 gains/6 losses
(-1.01 pp; p=.754). Yet 165/199 champions changed. Like the hierarchical
clean comparison, block formatting causes pervasive path instability without
a directional strict endpoint benefit. The flat schema is markedly more
executable (1 failure here versus 11 in hierarchical clean-shuffled), but it is
not decision-invariant.

This is a one-call AB02-style input-sensitive micro-pipeline, not the full
production AB02.
