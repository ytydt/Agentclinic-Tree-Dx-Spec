# E4 artifact map

- `preregistration.json`: frozen cases, prompts, pools and endpoints.
- `canonical_pools.jsonl`: source-blind post-cap pools with audit-only source provenance.
- `arms/*/case_results.jsonl`: one completed row per case for each arm.
- `E4_*_RAW.tar.gz` + `.sha256`: immutable online response caches and raw logs per arm.
- `E4_JOINED_RESULTS.tar.gz` + `.sha256`: joined 2,000-condition table and
  extended 318-case flip queue; `case_summary.csv` remains directly visible.
- `summary.json`: preregistered arm and paired endpoint summaries.
- `analysis_summary.json`: source-recall, cap, bootstrap, agreement, provenance and cost analysis.
- `source_recall_and_cap.jsonl`: per-case upstream exposure and width-cap audit.
- `endpoint_discordances.{jsonl,csv}`: all 17 strict online endpoint transitions.
- `audit_queue.jsonl`: all champion-flip cases for extended review.
- `MANUAL_AUDIT.md`: final-responsibility case-level mechanism audit.
- `REPORT.md`: integrated experiment report and limitations.
- `INCIDENTS.md`: preserved runtime incident description.

Credentials are absent from every artifact. Raw archives may contain the
explicitly authorized clean case payloads and model responses.

Arm result commits on `cursor4`: count control `831a28565`, e7 contrast
`286c64f89`, Forest `2bb0da7e2`, APHHM-C ledger `350e20236`, and pairwise
`f6990fd88`. The integrated report/analysis is committed separately.
