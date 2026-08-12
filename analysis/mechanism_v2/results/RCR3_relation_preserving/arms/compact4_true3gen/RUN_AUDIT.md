# RCR-3 `compact4_true3gen` run audit

The frozen 300-case four-call arm completed with 175 served cases.
Intention-to-analyse strict Top-1 was 8/300, strict Top-2 15/300, and both
raw-registry and bounded-frontier reference exposure were 24/300.  The first
two generator records equal the corresponding frozen Lite records as complete
JSON objects for 300/300 cases; the contrast did not resample shared stages.

Of 125 fail-closed cases, 123 failed in the newly added subtype/exception
generator, one inherited Lite's already frozen generator-schema failure, and
one failed the newly run selector.  The added generator returned exactly one
candidate in 108 cases despite the required 3--5, and 15 further calls did not
produce the required view/schema after three parse attempts.  It supplied a
valid 2--5-candidate response in only 177 cases.  Across all parseable
candidates it emitted 586 `disease` labels but only six `subtype` labels, so
the supposedly subtype-focused call mostly repeated the generic object level.

Among the 174 cases served by both Lite and Compact-4, strict Top-1 changed by
one gain and four losses (Compact 8 versus Lite 11).  Frontier reference
exposure was 24 versus 23: the third generator's net one-case exposure gain did
not translate into net strict selection gain.  This common-served comparison
is sensitivity evidence only; the pre-registered intention-to-analyse endpoint
retains all 125 Compact failures.

Only the new third-generator and selector calls appear in live telemetry: 476
semantic-call records, 581 physical attempts, 752,144 input and 201,981 output
tokens, and 8,019.64 summed provider-latency seconds.  The other 600 logical
generator calls are explicitly marked reused.  Provider-response associations
were 239 Groq and 274 DeepInfra, including fallback attempts; neither the 108
single-candidate violations nor the 15 parse failures were confined to one
provider.  No credential is present in committed stages, logs, telemetry,
manifest, or archive.
