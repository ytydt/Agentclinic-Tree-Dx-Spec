# E11 B07 retrieval × refine factorial: frozen design

This is a 400-case development/mechanism experiment, not a fresh confirmation.
It tests four forced knowledge conditions (`off`, query-top `relevant`, stable
`random`, and query-near but relevant-article-excluded `hard_negative`) crossed
with generic refine off/on. Historical B07 target-blind orchestrator outputs are
reused byte-for-byte at the semantic-field level; no new query-planner call can
confound a retrieval comparison.

The seven preregistered comparisons are three retrieval contrasts at refine-off
plus four within-retrieval refine contrasts. Frozen-identity Top-1 is primary;
clinical equivalence is adjudicated separately because the exact bridge is
conservative. Hard-negative is an operational IR treatment, not a declaration
that its chunks are false. Gold-support contamination and incumbent-confirming
evidence are audited before any causal interpretation.

The repository `RAGRetriever` remains available through
`TREE_DX_E11_RETRIEVER=production` when its metadata and dependencies are
materialized. `auto` uses it when viable and otherwise falls back to an audited
TF-IDF index over the committed Merck 19e corpus; a pure-Python BM25 fallback
remains available when scikit-learn is absent. LLM transport remains the shared
`RobustLLMClient`, whose official OpenAI SDK route is selected when installed.
