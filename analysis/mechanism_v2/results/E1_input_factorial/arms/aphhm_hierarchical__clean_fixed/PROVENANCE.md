# E1 arm provenance: APHHM hierarchical / clean fixed

- Frozen sample: 200 cases (100 DA, 100 MCR).
- Model: `deepseek/deepseek-v4-flash-0731` through the repository runtime.
- Requested non-RAG concurrency: 50.
- Reasoning controls: maximum 64 reasoning tokens; reasoning excluded from the returned answer.
- Served: 189/200. All 11 invalid responses remain endpoint failures; no imputation was used.
- Invalid contracts: 10 responses had an out-of-range L2 count and one champion did not reference a candidate.
- Strict raw-proposal recall: 22/200 intention-to-analyse (DA 5, MCR 17).
- Strict top-1: 16/200 intention-to-analyse (DA 5, MCR 11).
- Runtime: 200 semantic calls, 315 physical attempts, 172,864 input tokens and 1,181,395 output tokens.
- Routing: 15 observed providers; DeepInfra 74, Cloudflare 23, Inceptron 20, Io Net 20, SiliconFlow 19, and smaller shares from ten others. Groq was not used.
- Raw cache, responses, telemetry and log are preserved in the adjacent checksummed archive.

This is a one-call input-sensitive APHHM-style hierarchical proposal and
selection micro-pipeline. It is not the full multi-call production APHHM and
must not be used as an estimate of production APHHM cost or accuracy.
