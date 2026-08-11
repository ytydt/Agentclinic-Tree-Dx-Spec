# E1 arm provenance: APHHM hierarchical / options shuffled blocks

- Frozen sample: the same 200 cases (100 DA, 100 MCR) as every E1 arm.
- Model: `deepseek/deepseek-v4-flash-0731` through the repository runtime.
- Requested non-RAG concurrency: 50.
- Served: 176/200. Twenty-three responses had an out-of-range L2 count and one had an out-of-range L1 count; all remain failures.
- Strict raw-proposal recall: 84/200 intention-to-analyse.
- Strict top-1: 58/200 intention-to-analyse.
- Mean exact source-option copy fraction among candidates: 0.3094; 74 served champions exactly copied a source option.
- Runtime: 200 semantic calls, 337 physical attempts, 208,614 input tokens and 1,264,072 output tokens.
- Routing: 14 observed providers; no Groq call was observed.
- Raw cache, responses, telemetry and log are preserved in the adjacent checksummed archive.

Against clean-shuffled on 168 cases served in both arms, raw recall improved
68/8 (+35.71 pp; exact McNemar p=5.63e-13), strict top-1 improved 47/8
(+23.21 pp; p=8.07e-8), and champion option copy improved 54/11 (+25.60 pp;
p=6.03e-8). Thus option content still has a large effect after stable random
relabeling/order; it is not only an A/B/C/D or original-position effect.

Against options-fixed on 167 common served cases, shuffled formatting reduced
raw recall by 19.16 pp (43 losses/11 gains), strict top-1 by 15.57 pp (35/9),
and champion option copy by 19.76 pp (43/10). Output tokens doubled and contract
failures rose from 13 to 24. The clean-format contrast was directionally null,
so formatting primarily moderates the model's use of visible candidates: the
explicit MCQ affordance collapses search, whereas the arbitrary diagnostic
appendix reopens verbose generation.

This is a one-call APHHM-style input-sensitive micro-pipeline, not the full
production APHHM.
