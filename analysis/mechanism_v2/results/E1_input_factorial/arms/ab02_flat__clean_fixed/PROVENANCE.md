# E1 arm provenance: AB02 flat / clean fixed

- Frozen sample: the same 200 cases (100 DA, 100 MCR) as every E1 arm.
- Model: `deepseek/deepseek-v4-flash-0731` through the repository runtime.
- Requested non-RAG concurrency: 50.
- Served: 200/200; every response satisfied the flat candidate/champion contract.
- Strict raw-proposal recall: 20/200 intention-to-analyse (DA 4, MCR 16).
- Strict top-1: 13/200 intention-to-analyse (DA 3, MCR 10).
- Mean exact source-option copy fraction among candidates: 0.0698; 23 champions exactly copied a source option despite options being hidden.
- Runtime: 200 semantic calls, 257 physical attempts, 120,480 input tokens and 540,694 output tokens.
- Routing: 17 observed providers; no Groq call was observed.
- Raw cache, responses, telemetry and log are preserved in the adjacent checksummed archive.

The clean flat micro-pipeline had similar low strict proposal/top-1 behavior to
the clean hierarchical arm (20/13 versus 22/16 intention-to-analyse), but used
less than half the output tokens and produced 0 versus 11 contract failures.
The evidence therefore supports an execution-stability and cost advantage for
the flat contract, not a demonstrated clinical-accuracy advantage in clean
input.

This is a one-call AB02-style input-sensitive micro-pipeline, not the full
production AB02.
