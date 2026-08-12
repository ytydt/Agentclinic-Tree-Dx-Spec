# E9 artifact map

- `PREREGISTRATION.md`, `preregistration.json`, `construction_ledger.jsonl`: frozen questions, arm contracts, anchor assignment, payload hashes and offline overlap/capture facts.
- `arms/*/case_results.jsonl`: all 400 intention-to-analyse rows per selector arm; one duplicate-arm schema failure is retained.
- `E9_*_RAW.tar.gz` and adjacent `.sha256`: immutable request caches, responses, logs, telemetry and provenance for each selector arm and the heterogeneous semantic audit.
- `case_conditions.jsonl`, `case_summary.csv`, `summary.json`: joined strict endpoints and primary paired contrasts.
- `semantic_audit/*`: target-blind Gemini proposition partitions. These are subcontractor artifacts, not final clinical judgments.
- `manual_audit_selection.json`, `manual_audit_queue.jsonl`, `manual_audit_queue_provenance.json`: frozen 70-case root-audit source packet and hash provenance.
- `manual_audit.jsonl`, `manual_audit_summary.json`, `manual_audit_manifest.json`: root-agent trajectory adjudication and complete strict-discordance clinical recoding.
- `analysis_summary.json`: deterministic bootstrap intervals, capture/selection decomposition, exact and semantic overlap, manual recodes and lower-bound telemetry.
- `E9_FINAL_ANALYSIS_BUNDLE.tar.gz` and adjacent `.sha256`: compact final analytic package without raw response caches; use the arm archives for raw-call replay.
- `REPORT.md`: final mechanism interpretation; `INCIDENTS.md`: execution and schema deviations.

No archive contains an API key or GitHub credential.
