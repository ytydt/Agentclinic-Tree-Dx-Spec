# E8 artifact map

- `preregistration.json`, `selected_cases.jsonl`: frozen sample, pools, arms and endpoints.
- `construction/case_results.jsonl`: immutable raw response plus deterministic post-processing and fail-closed status for all 220 cases.
- `arms/*/case_results.jsonl`: all intention-to-analyse selector rows.
- `E8_*_RAW.tar.gz` and adjacent `.sha256`: request caches and per-call telemetry for construction, four selector arms and the heterogeneous proxy audit.
- `case_conditions.jsonl`, `case_summary.csv`, `summary.json`: joined primary endpoint tables.
- `analysis_summary.json`, `trajectory_discordances.jsonl`: payload-integrity checks, paired bootstrap intervals and all trajectory flips.
- `external_audit/*`: opaque-output proxy audit. These are subcontractor findings, not final labels.
- `manual_audit.jsonl`, `manual_audit_summary.json`, `manual_audit_manifest.json`: root-agent review of all critical cases, controls and all nine reference hard vetoes.
- `REPORT.md`: final mechanism interpretation; `INCIDENTS.md`: technical and audit deviations.

No archive contains an API key or GitHub credential.
