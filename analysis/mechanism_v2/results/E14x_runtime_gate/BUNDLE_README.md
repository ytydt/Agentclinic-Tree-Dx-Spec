# E14x artifact map

- `E14X_ANALYSIS_PLAN.md`: retrospective analysis contract frozen before the case-level outcome join.
- `case_ledger.jsonl`: 300 primary paired historical trajectories with upstream hashes, pre-gate signals, A1 funnel, champions and separate concept/mapper endpoints.
- `analysis_summary_pre_manual.json`: strict-gate aggregate, strata, bootstrap intervals, A1 funnel and descriptive signal scans.
- `secondary_permissive_gate_summary.json`: diagnostic analysis of the older high-activation Adaptive-4 gate.
- `manual_audit_queue.jsonl`: frozen 56-case packet covering every strict flip, A1-new champion, DA projection flip and triggered champion flip.
- `manual_audit.jsonl`, `manual_audit_summary.json`, `manual_audit_manifest.json`: root-owned clinical adjudications and hash manifest; no external LLM made these judgments.
- `source_provenance.json`, `attrition.json`, `analysis_run.log`, `manual_audit_run.log`: input hashes, complete attrition accounting and execution logs.
- `analysis_summary.json`: final machine-readable synthesis and RCR-3 decision.
- `REPORT.md`: critical mechanism report; `INCIDENTS.md`: inferential and artifact limitations.
- `E14X_FINAL_ANALYSIS_BUNDLE.tar.gz` and adjacent `.sha256`: compact final package of all above artifacts.

E14x made zero new LLM/API calls. No archive contains an API key or GitHub credential.

