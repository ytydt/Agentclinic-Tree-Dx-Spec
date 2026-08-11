# E4/APHHM-C obligation-ledger arm provenance

- Frozen conditions: 400; served: 400; invalid schema responses: 0.
- Strict/frozen-synonym gold exposure: 62/400; top-1: 37/400.
- Dataset split: DA 3/200 top-1 with 7/200 exposed; MCR 34/200 top-1
  with 55/200 exposed.
- Against e7 contrast, the ledger had 7 exclusive strict wins and 3 losses
  (+1.0pp; 109 champion flips; exact McNemar p=0.34375).
- Against Forest integration, the ledger had 2 exclusive wins and 6 losses
  (-1.0pp; 103 champion flips; exact McNemar p=0.2890625).
- The telemetry ledger contains 397 rows for 400 fresh successful calls; the
  complete response/cache/result set is preserved, so token and physical-call
  totals are lower bounds and no missing telemetry is imputed.
- Model, source-blind payload, candidate order and runtime controls match the
  other online E4 arms.  This isolates selector instruction semantics, not the
  complete APHHM-C architecture.

The arm-specific raw archive preserves immutable responses, telemetry, result
rows and logs.
