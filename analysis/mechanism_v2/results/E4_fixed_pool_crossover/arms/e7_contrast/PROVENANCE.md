# E4/e7 contrast arm provenance

- Frozen conditions: 400; served: 400; invalid schema responses: 0.
- Strict/frozen-synonym gold exposure: 62/400; top-1: 33/400.
- Dataset split: DA 3/200 top-1 with 7/200 exposed; MCR 30/200 top-1
  with 55/200 exposed.
- The first launch failed before making a call because direct-script execution
  did not place `src/` on `sys.path`.  The runner now adds the production
  package path itself.
- A second launch used a 2048-token direct-post cap.  It produced immutable
  cache records but its PTY ended while two tail calls were unresolved.  The
  resumed launch used an 8192-token cap and reused every available cache record.
- `case_results.jsonl` reports 398 cache hits and two fresh completions.  The
  telemetry file has 398 rows: two cache records survived the interrupted
  process before their corresponding telemetry lines were flushed.  Therefore
  physical-attempt/token totals are lower bounds, not a complete cost ledger.
- No evaluator label, answer option, historical champion, source identity,
  rank, score or vote was present in any online payload.

The raw archive preserves both incident attempts, successful immutable cache
records, telemetry, result rows and logs.  Empty atomic-write temporary files
left by the interrupted process are intentionally retained in that archive.
