# E1 arm provenance: AB02 flat / options shuffled blocks

- Frozen sample: the same 200 cases (100 DA, 100 MCR) as every E1 arm.
- Model: `deepseek/deepseek-v4-flash-0731` through the repository runtime.
- Requested non-RAG concurrency: 50.
- Served: 199/200. One response had an out-of-range flat candidate count and remains a failure.
- Strict raw-proposal recall: 106/200 intention-to-analyse.
- Strict top-1: 74/200 intention-to-analyse.
- Mean exact source-option copy fraction among candidates: 0.3886; 92 served champions exactly copied a source option.
- Runtime: 200 semantic calls, 233 physical attempts, 138,681 input tokens and 396,021 output tokens.
- Routing: 15 observed providers; no Groq call was observed.
- Raw cache, responses, telemetry and log are preserved in the adjacent checksummed archive.

Against flat clean-shuffled on 198 common served cases, raw recall improved
90/3 (+43.94 pp; exact McNemar p=2.71e-23), strict top-1 improved 64/1
(+31.82 pp; p=3.58e-18), and champion option copy improved 77/3 (+37.37 pp;
p=1.41e-19). Candidate content therefore retains a large effect after stable
random relabeling and order.

Against flat options-fixed on 198 common served cases, shuffled formatting
reduced raw recall by 10.10 pp (36 losses/16 gains), strict top-1 by 10.10 pp
(34/14), and champion option copy by 16.67 pp (46/13). The complete-case
visibility-by-format interaction was +9.14 pp for strict top-1: the explicit
MCQ affordance amplifies leakage, but does not create it.

This is a one-call AB02-style input-sensitive micro-pipeline, not the full
production AB02.
