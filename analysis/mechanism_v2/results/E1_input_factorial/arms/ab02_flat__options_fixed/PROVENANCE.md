# E1 arm provenance: AB02 flat / options fixed

- Frozen sample: the same 200 cases (100 DA, 100 MCR) as every E1 arm.
- Model: `deepseek/deepseek-v4-flash-0731` through the repository runtime.
- Requested non-RAG concurrency: 50.
- Served: 199/200. One response had an out-of-range flat candidate count and remains a failure.
- Strict raw-proposal recall: 125/200 intention-to-analyse (DA 79, MCR 46).
- Strict top-1: 93/200 intention-to-analyse (DA 54, MCR 39).
- Mean exact source-option copy fraction among candidates: 0.4822; 124 served champions exactly copied a source option.
- Runtime: 200 semantic calls, 215 physical attempts, 125,193 input tokens and 300,510 output tokens.
- Routing: 17 observed providers; no Groq call was observed.
- Raw cache, responses, telemetry and log are preserved in the adjacent checksummed archive.

Against flat clean-fixed on 199 common served cases, raw recall improved 107/2
(+52.76 pp; exact McNemar p=1.85e-29), strict top-1 improved 82/2 (+40.20
pp; p=3.69e-22), and champion option copy improved 105/4 (+50.75 pp;
p=1.78e-26). Output tokens fell from 540,694 to 300,510. The approximately
40-point strict effect reproduces the hierarchical options contrast, locating
the main behavior in input visibility rather than hierarchical versus flat
organization.

This is a one-call AB02-style input-sensitive micro-pipeline, not the full
production AB02.
