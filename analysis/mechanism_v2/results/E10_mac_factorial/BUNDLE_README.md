# E10 artifact map

- `preregistration.json`, `E10_ANALYSIS_PLAN.md`: frozen 2×2 design and endpoints.
- `arms/*`: each committed arm's 400 case results, run log, telemetry (Supervisor only), and summary.
- `doctor_runs/*`: frozen isolated/sequential doctor trajectories and telemetry.
- `E10_*_RAW.tar.gz{,.sha256}`: per-arm immutable raw bundles committed immediately after each arm.
- `semantic_screen/*`, `E10_SEMANTIC_AUDIT_PLAN.md`: heterogeneous queue-expansion screen; not final adjudication.
- `manual_audit_queue.jsonl`: exhaustive safe-exact/screen-positive queue plus frozen negative controls.
- `manual_audit.jsonl`: root-owned 166-case binary-acceptable proxy adjudication and 25 deep critical trajectory dissections.
- `summary.json`: safe-exact four-arm summary (with historical source aliases); `analysis_summary.json`: binary-acceptable proxy, paired inference, mediation, diversity and aggregation decomposition.
- `REPORT.md`: critical synthesis and component-level conclusions.
- `INCIDENTS.md`: schema, timeout, transport and provider disclosures.
- `E10_FINAL_ANALYSIS_BUNDLE.tar.gz{,.sha256}`: compact joined analysis bundle; raw call caches are intentionally excluded because committed JSONL/telemetry and per-arm raw archives are the auditable artifacts.

For automated synthesis, only the coverage-gated cross-experiment evidence
view is ingestible. Frozen `summary.json`, arm summaries, and raw audit rows
retain source aliases and must not be flattened into a capability table.

## Endpoint interpretation guard

The manual endpoint is a binary clinically-acceptable proxy. It mixes complete
equivalence, compatible partial/scope variants, and therefore does **not**
measure clinical-complete, compatible-partial, or their union separately. Its
rates, exposure counts, conversions, and legacy binary mechanism labels must
not be ingested as a clinical-complete capability leaderboard. Safe-exact is a
separate deterministic lower-bound endpoint; family-specific task projections
remain separate as well.
