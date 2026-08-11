# E4/pairwise-tournament arm provenance

- Frozen conditions: 400; served: 400; invalid schema responses: 0.
- Strict/frozen-synonym gold exposure: 62/400; top-1: 38/400.
- Dataset split: DA 2/200 top-1 with 7/200 exposed; MCR 36/200 top-1
  with 55/200 exposed.
- Versus Forest integration it had 3 exclusive wins and 6 losses (-0.75pp;
  95 champion flips; exact McNemar p=0.5078125).
- Versus the APHHM-C ledger it had 4 exclusive wins and 3 losses (+0.25pp;
  109 champion flips; exact McNemar p=1.0).
- Versus e7 contrast it had 8 exclusive wins and 3 losses (+1.25pp; exact
  McNemar p=0.2265625).
- Its telemetry lower bound is 397 semantic rows, 509 physical attempts,
  1,607,448 output tokens and 47,071.6 aggregate seconds.  It did not improve
  on Forest despite the largest observed compute/long-tail burden.
- The telemetry ledger is three rows short of the complete 400-response result
  set; no missing cost records are imputed.  Scientific endpoints use the
  complete cached responses, not the incomplete cost ledger.

The arm-specific raw archive preserves immutable responses, telemetry, result
rows and logs.
