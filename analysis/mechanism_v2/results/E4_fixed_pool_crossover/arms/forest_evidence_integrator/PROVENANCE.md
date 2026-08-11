# E4/Forest evidence-integrator arm provenance

- Frozen conditions: 400; served: 400; invalid schema responses: 0.
- Strict/frozen-synonym gold exposure: 62/400; top-1: 41/400.
- Dataset split: DA 3/200 top-1 with 7/200 exposed; MCR 38/200 top-1
  with 55/200 exposed.
- Against the byte-identical e7-contrast payload, Forest changed 107/400
  champions.  It had 9 exclusive strict wins versus one e7-exclusive win
  (paired delta +2.0 percentage points; exact McNemar p=0.021484375).
- The telemetry ledger contains 399 rows for 400 fresh successful calls.  The
  cache/result set is complete, so aggregate attempt/token totals are treated
  as lower bounds and the missing telemetry association is not imputed.
- All calls used the same model, temperature, 8192 direct-post ceiling,
  bounded/excluded reasoning configuration and source-blind candidate order.
  No evaluator label, options or upstream provenance entered a payload.

The arm-specific raw archive preserves immutable responses, telemetry, result
rows and logs.
