# RCR-3 `rcr3_default` run audit

The frozen 300-case same-budget arm completed with 262 served cases.
Intention-to-analyse strict Top-1 was 7/300, strict Top-2 12/300, raw-registry
reference exposure 19/300, and bounded-frontier exposure 16/300.  Mean registry
and frontier sizes over the full denominator were 7.9233 and 6.9767.

The 38 fail-closed cases were all schema violations after provider responses,
not network failures: 14 skeletons used a relation outside the frozen ontology,
10 called the requested object `diagnosis`, 13 generators used an unsupported
candidate type, and one selector named a decisive-pair winner outside the
pair.  These cases were not repaired or resampled.  Common ontology expansion
attempts included `risk_factor_for`, `treated_with`, `progressed_to`, `anatomy`,
and `exposure`; their clinical plausibility does not make them compliant with
the frozen treatment contract.

Among 276 schema-valid skeletons, 3,169/3,288 observation spans grounded
exactly and 119 were dropped.  Many drops were near-quotes with inserted
headings, punctuation changes, or reformatted units, showing that apparent
quotation is not equivalent to byte-grounded evidence.  Only 594 relations
survived, and 81/276 valid skeletons contained no surviving relation.  The 263
valid batched generators also emitted 51 evidence references absent from their
own sanitized skeletons; these references were removed before selection.

Telemetry contains 839 actual semantic-call records and 841 physical attempts,
using 1,833,983 input and 755,124 output tokens with 23,769.34 summed
provider-latency seconds.  Routing again was not Groq-only: provider-response
associations were 403 Groq and 437 DeepInfra.  The environment-managed route
showed no regional, datacenter-IP, or network-provider failure.  Credentials
are absent from the committed stages, logs, telemetry, manifest, and archive.
