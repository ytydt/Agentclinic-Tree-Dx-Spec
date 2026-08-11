# E5 artifact map

- `preregistration.json`: frozen sample, base-pool hashes, prompts, arms,
  primary contrasts and nested-width contract.
- `perturbations/case_perturbations.jsonl`: 200 frozen construction outcomes;
  `perturbation_audit_sample.jsonl` is the outcome-blind 20-case semantic
  sample frozen before selector calls.
- `arms/*/case_results.jsonl`: 200 ITA rows for each of nine selector arms.
- `E5_*_RAW.tar.gz` + `.sha256`: immutable response caches and telemetry for
  construction and each arm, committed phase by phase.
- `case_summary.csv` and `summary.json`: directly inspectable 1,800-condition
  endpoints and preregistered paired summaries.
- `analysis_summary.json`: Wilson intervals, paired bootstraps, Holm correction,
  common-complete analysis, direct/context decomposition, order/position
  diagnostics and runtime totals.
- `transition_discordances.csv`: all 361 non-stable base-to-arm transitions.
- `manual_adjudications.jsonl` and `manual_analysis_summary.json`: 339 explicit
  primary-analyst semantic and trajectory judgments plus synonym sensitivity.
- `E5_JOINED_RESULTS.tar.gz` + `.sha256`: ignored joined condition table and
  full rich audit queue needed to reproduce every transition.
- `MANUAL_AUDIT.md`: final-responsibility case-level mechanism dissection.
- `REPORT.md`: integrated results and inferential limits.
- `INCIDENTS.md`: construction, schema, recovery, transport and telemetry
  incidents.

Credentials are absent from every artifact. Raw archives contain the
explicitly authorized clean case payloads and model responses.

Phase commits on `cursor4`: construction `179221b60`, base `de6f28690`, remove
`8c876498f`, parent `0ca125486`, sibling `667a7c8`, unrelated `2728c6a`,
synonym `31fa22d`, component `d6dbb36`, width 6 `35160e1`, and width 8
`98bf243`. The integrated analysis/report is committed separately.
