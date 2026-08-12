# E6 aborted builder v1

This is a transport/shape pre-endpoint incident, not an analysed experiment
arm.  No diagnostic selector was called and no clinical endpoint was computed.

The original single-call builder requested both a flat representation and a
typed graph.  At an 8,192-token output ceiling many complete JSON objects were
truncated.  Protocol amendment 01 allowed a 16,384-token retry, but with 50
concurrent long generations at least forty requests reached the 180-second
timeout together.  That satisfies the user-specified process-storm exception,
so the run was stopped.

At stop time the immutable state contained:

- 23 complete response-cache objects;
- 22 completed telemetry records (one additional cache was persisted across
  the interrupted concurrent-write boundary);
- 22 semantic and at least 27 physical calls represented in completed
  telemetry;
- at least 23,430 recorded input tokens and 131,328 recorded output tokens;
- 13/23 raw schema passes and 22/23 passes after the separately committed
  target-blind normalization rules; and
- no complete case table, no matched representations and no selector output.

The complete directory is preserved in
`E6_BUILDER_ABORTED_V1_RAW.tar.gz`; the adjacent SHA-256 manifest verifies it.
These responses will not be mixed into the revised builder.  The next protocol
uses a compact hard shape and reduced construction concurrency; selector-arm
concurrency remains governed independently.
