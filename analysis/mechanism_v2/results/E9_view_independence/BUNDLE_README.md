# E9 artifact map

- `PREREGISTRATION.md`, `preregistration.json`, `construction_ledger.jsonl`: frozen questions, arm contracts, anchor assignment, payload hashes and offline overlap/capture facts.
- `arms/*/case_results.jsonl`: all 400 intention-to-analyse rows per selector arm; one duplicate-arm schema failure is retained.
- `E9_*_RAW.tar.gz` and adjacent `.sha256`: immutable request caches, responses, logs, telemetry and provenance for each selector arm and the heterogeneous semantic audit.
- `case_conditions.jsonl`, `case_summary.csv`, `summary.json`: joined safe-exact endpoints (some frozen source fields retain historical `strict` names) and primary paired contrasts.
- `semantic_audit/*`: target-blind Gemini proposition partitions. These are subcontractor artifacts, not final clinical judgments.
- `manual_audit_selection.json`, `manual_audit_queue.jsonl`, `manual_audit_queue_provenance.json`: frozen 70-case root-audit source packet and hash provenance.
- `manual_audit.jsonl`, `manual_audit_summary.json`, `manual_audit_manifest.json`: root-agent targeted reclassification of the frozen legacy mechanism queue.
- `analysis_summary.json`: deterministic bootstrap intervals, capture/selection decomposition, exact and semantic overlap, manual recodes and lower-bound telemetry.
- `E9_FINAL_ANALYSIS_BUNDLE.tar.gz` and adjacent `.sha256`: compact final analytic package without raw response caches; use the arm archives for raw-call replay.
- `REPORT.md`: final mechanism interpretation; `INCIDENTS.md`: execution and schema deviations.

For automated synthesis, `analysis_summary.json` is the canonical active view.
`summary.json` and arm-level summaries retain frozen source aliases for replay
provenance and must not be flattened or ingested directly.

## Endpoint interpretation guard

The 70-case manual review is a targeted, outcome-enriched legacy mechanism
reclassification. Its `yes`, `scope_or_surface_artifact`, `no`, and
`not_exposed` labels do **not** implement clinical-complete,
compatible-partial, or their union for every case and arm. Consequently these
manual labels must not be ingested as a clinical-capability leaderboard or
described as complete-equivalence rates. E9's quantitative arm endpoint is
safe-exact; the targeted review supplies bounded mechanism evidence only.

No archive contains an API key or GitHub credential.
