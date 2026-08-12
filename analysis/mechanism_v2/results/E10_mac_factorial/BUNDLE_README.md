# E10 artifact map

- `preregistration.json`, `E10_ANALYSIS_PLAN.md`: frozen 2×2 design and endpoints.
- `arms/*`: each committed arm's 400 case results, run log, telemetry (Supervisor only), and summary.
- `doctor_runs/*`: frozen isolated/sequential doctor trajectories and telemetry.
- `E10_*_RAW.tar.gz{,.sha256}`: per-arm immutable raw bundles committed immediately after each arm.
- `semantic_screen/*`, `E10_SEMANTIC_AUDIT_PLAN.md`: heterogeneous queue-expansion screen; not final adjudication.
- `manual_audit_queue.jsonl`: exhaustive strict/screen-positive queue plus frozen negative controls.
- `manual_audit.jsonl`: root-owned 166-case candidate adjudication and 25 deep critical trajectory dissections.
- `summary.json`: strict four-arm summary; `analysis_summary.json`: clinical recode, paired inference, mediation, diversity and aggregation decomposition.
- `REPORT.md`: critical synthesis and component-level conclusions.
- `INCIDENTS.md`: schema, timeout, transport and provider disclosures.
- `E10_FINAL_ANALYSIS_BUNDLE.tar.gz{,.sha256}`: compact joined analysis bundle; raw call caches are intentionally excluded because committed JSONL/telemetry and per-arm raw archives are the auditable artifacts.
