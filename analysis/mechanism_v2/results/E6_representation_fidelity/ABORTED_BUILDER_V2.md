# E6 aborted builder v2

This second pre-endpoint builder attempt applied the compact prompt authorised
by protocol amendment 02 and reduced concurrency from 50 to 25.  It confirmed
that the shape constraint worked: the seven completed responses contained
12-14 flat facts, 11-16 graph nodes and 8-15 relations, typically around
1.8-2.3k output tokens.  Nevertheless, more than twenty concurrent DeepSeek
requests reached the 180-second timeout together after length retries, so the
process-storm exception was triggered again and the run was stopped.

At stop time the immutable state contained seven response-cache objects and
seven telemetry records, representing seven semantic and at least eight
physical calls, 7,307 recorded input tokens and 23,557 recorded output tokens.
No complete case table, matched representation, selector response or endpoint
existed.  All seven raw validators rejected the generated objects: five because
an exact source quote exceeded the prompt's 18-word compactness target and two
because a quote was not an exact vignette substring.  This showed that treating
the field-length request as a case-level semantic failure was too brittle;
exact longer quotations are fidelity evidence, while selector serialization
already omits them.

The complete raw directory is preserved in
`E6_BUILDER_ABORTED_V2_RAW.tar.gz` with an adjacent checksum.  None of these
responses will be reused.  The final builder keeps the compact count shape,
uses the repository-proven `google/gemini-2.5-flash` structured annotator, and
treats field word limits as generation guidance rather than a rejection rule.
The diagnostic selector remains the preregistered DeepSeek model.
