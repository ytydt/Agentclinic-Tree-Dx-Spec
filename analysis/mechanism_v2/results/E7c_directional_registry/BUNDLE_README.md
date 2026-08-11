# E7c artifact map

Human-auditable files remain directly visible:

- `REPORT.md` — design, estimates, mechanism analysis and decision;
- `MANUAL_AUDIT.md` — full strict-transition audit and clinical relation review;
- `ABORTED_PREFLIGHT.md` — failed engineering attempts;
- `preregistration.json` and `manifest.json` — frozen contract and environment;
- `summary.json`, `analysis_summary.json`, `case_summary.csv` and
  `discordance_cases.csv` — compact machine-readable results;
- `run.log` — progress and terminal counts.

`E7c_directional_registry_FULL_RESULTS.tar.gz` contains the entire directory,
including immutable call caches, per-condition rows, relation classifications,
telemetry and the audit queue. Verify it against the adjacent `.sha256` file
before extracting.
