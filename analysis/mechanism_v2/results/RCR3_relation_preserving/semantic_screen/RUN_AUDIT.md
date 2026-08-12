# RCR-3 heterogeneous screen run audit

DeepSeek v4 Flash screened all 300 frozen cases without method identity,
arm outcome, strict score, provider vote, or generator provenance in the
payload.  It separately judged reference identifiability and all deduplicated
candidate-to-reference relations.  The model is outside the Llama family used
for RCR generation and selection and remains a queue-expansion subcontractor,
not the final auditor.

There are 299 schema-valid case screens.  Their 3,522 candidate-relation rows
exactly cover all 3,522 expected candidate IDs in those cases.  The one
fail-closed case (`DA_d2_heldout200b/574`) returned a mapping instead of the
required relation list; it receives no proxy credit and is forced into root
review.  The proxy relation distribution is 178 complete, 1,055 partial,
377 conflicting subtype/scope, 816 manifestation/related, 1,091 not
equivalent, and five uncertain.

Only 160 references were judged uniquely identifiable at their full encoded
specificity.  The proxy classified 111 as family-only, 19 as unsupported
specificity, nine as information-insufficient, and one as allowing multiple
complete answers.  Its provisional complete Top-1 counts are Lite 41, RCR-3
30 and Compact-4 23; these exceed strict counts and must be root-corrected,
especially because prior E12 review found systematic proxy overacceptance.

Telemetry contains 300 semantic calls and 311 physical attempts, 404,394
input and 393,575 output tokens, and 16,279.02 summed provider-latency seconds.
Twenty-one OpenRouter provider names appear, with no region, datacenter-IP, or
authentication failure.  One parse/schema failure and several timeout retries
are preserved.  The successful environment-managed route makes a repository
VPN unnecessary in this runtime.  The raw archive excludes call caches and
contains no credentials.
