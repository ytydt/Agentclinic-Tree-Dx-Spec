# E6 representation-construction provenance

The final target-blind builder completed all 300 calls with
`google/gemini-2.5-flash` at 25 workers.  The immutable cache contains 300
responses.  One telemetry record is absent across the concurrent write
boundary, so telemetry totals are explicit lower bounds (299 semantic/physical
attempts, 294,254 input tokens and 693,289 output tokens); no response row is
missing.

The raw online schema accepted 174/300 cases.  Frozen deterministic
normalization rescued 84 additional cases, yielding 258/300 usable dual
representations: 126/150 DA and 132/150 MCR.  It applied at least one logged
action in 99 cases, chiefly copying the exact original span for punctuation-only
quote drift (106 flat and 88 graph quote actions).  The 42 fail-closed cases
were 31 ungrounded flat quotes, eight ungrounded node quotes and three invalid
edge types.  No gold label or selector result entered either construction or
normalization.

Every successful case has exactly equal whitespace-word counts across raw,
flat and graph selector payloads, with no 1,200-word truncation.  Flat facts
needed substantially more neutral padding (mean 128.46 words) than raw (20.50)
or graph (18.79); the selector is explicitly told to ignore the pad token, but
this asymmetric amount remains a design limitation to inspect in trajectory
audit.

The 30-case first-pass fidelity sample was frozen at 15 DA and 15 MCR cases.
`representation_audit_sample_blind.jsonl` removes gold labels for the initial
source-fidelity judgment; the sealed companion retains gold for the later
diagnostic-salience pass.  `E6_REPRESENTATIONS_RAW.tar.gz` contains the complete
builder directory (responses, cache, telemetry, environment and run log) plus
the expanded matched-representation manifest.  The adjacent SHA-256 file
verifies the archive.
