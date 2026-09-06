# Task 1 — V2 index differential audit

Frozen repository: `cursor4@6fa8fd7aa2548cc01ac81f2d5261801190244d27`.

This directory audits the actual 11-case, four-arm historical mechanical-rule experiment. It does not rerun LLM extraction, download LFS indexes, alter clinical cases, or modify production engine code.

## Navigation

- `REPORT.md`: integrated interpretation and case-level findings.
- `ENDPOINT_ACCOUNTING.md`: what the old 7/11 measures; exact paired-rank arithmetic and complete-label scope.
- `RETRIEVAL_DELTA.md`: actual old/v2 source exposures and retained/changed/removed inputs.
- `cases/`: separate deep reports for every case.
- `replay_outputs/*.json.gz`: all 44 full, source-linked trajectories, including complete contributions, gates, bindings and group members.
- `replay_validation.json`: equality to all frozen historical outputs and reconstruction of all candidate scores.
- `judgments_*.json`, `*_probe_results.json`: source-grounded intervention selections and outcomes. See each case report for interpretation and uncertainty.
- `METHODS_REVIEW.md`: independent methods review and corrections.
- `PROTOCOL.md`: prespecified task boundary and delivery criteria.

## Reproduction

Run from the repository root with the existing local runtime:

```bash
python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/audit_endpoints.py
python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/retrieval_delta.py
python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/source_text_examples.py
python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/replay_audit.py
python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/build_replay_deltas.py
```

The replay API is documented in `replay_audit.py`. It instruments the production function in memory and verifies the unmodified historical behavior before running specified interventions. It is single-process/single-thread because the historical engine uses module-level configuration. Independent case-probe scripts can run in separate processes.

Arm aliases `old_old`, `free_old`, `old_v2`, `free_v2` refer to historical prompts and indexes. `new_old`/`new_v2` in the endpoint ledger mean the same free-prompt arms; no new model generation is implied.

Numeric-only removal retains confirmation and exclusion states. Join blocking changes downstream claimant weights, group behavior and comparisons. Raw deletion may expose a deduplicated alternative. These interventions have different estimands and cannot be interchanged or summed as an additive causal decomposition.

All source passages in the audit come from already authorized repository data. External papers and the proposed future design are delivered separately in `FAITHFUL_RULE_EXTRACTION_LITERATURE_REVIEW/` and `RULE_EXTRACTION_EXECUTION_REDESIGN/`.
