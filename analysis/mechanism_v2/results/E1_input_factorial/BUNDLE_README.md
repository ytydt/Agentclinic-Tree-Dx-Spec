# E1 artifact map

- `preregistration.json`: frozen sample, prompts, condition inputs and endpoints.
- `arms/*/case_results.jsonl`: 200 ITA rows for each of eight factorial arms.
- `E1_*_RAW.tar.gz` + `.sha256`: immutable response caches, telemetry and logs
  committed with each arm.
- `case_summary.csv`: directly inspectable 1,600-condition endpoint table.
- `summary.json`: preregistered arm counts and paired endpoint summaries.
- `analysis_summary.json`: bootstraps, interactions, family strata, candidate
  instability and runtime/provider analysis.
- `E1_JOINED_RESULTS.tar.gz` + `.sha256`: full joined condition rows and the
  complete trajectory flip queue.
- `MANUAL_AUDIT.md`: final-responsibility, case-level mechanism dissection.
- `REPORT.md`: integrated findings and inferential limits.
- `INCIDENTS.md`: schema and outer-runner incidents.

Credentials are absent from every artifact. Raw archives contain the
explicitly authorized clean case payloads and model responses.

Arm commits on `cursor4`: H clean fixed `8ded03393`, H clean reordered
`3c60b6d0d`, H options fixed `aba772700`, H options reordered `573d6a992`, F
clean fixed `508c51a73`, F clean reordered `eab4137f3`, F options fixed
`4f53752f4`, and F options reordered `2a50921fa`.
