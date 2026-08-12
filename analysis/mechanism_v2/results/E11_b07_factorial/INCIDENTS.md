# E11 runtime incidents

## Random-context diagnose arm: provider-skew stop and resume

During `random_refine_off`, the first inspection at 175 completed semantic
calls found every actual response served by Groq. Although all calls succeeded,
continuing under that observed single-provider route would violate the E11
robustness constraint. The process was interrupted. Already in-flight requests
were allowed by the runtime to settle, leaving 226 immutable cache records: 208
Groq and 18 DeepInfra, with no failed calls or physical retries.

The arm was resumed with `TREE_DX_LLAMA_PROVIDER_POLICY=balanced`. The 226
completed payloads were cache hits and were not resampled; 166 additional unique
payloads were served. The final arm has 400 case decisions from 392 unique
semantic calls, with actual providers Groq 317 and DeepInfra 75, zero failed
semantic calls, and zero extra physical attempts. Eight case pairs had
byte-identical target-blind payloads and therefore shared immutable responses.

This is runtime provenance, not a provider experiment. No outcome was deleted,
repeated, or selected by correctness. Provider counts are retained in telemetry
and the final analysis must not attribute a random/relevant contrast to a
provider-normalized estimand. Subsequent Llama arms explicitly request balanced
primary routing; actual provider remains recorded because OpenRouter may serve a
different member of the permitted Groq/DeepInfra set.

## Combined heterogeneous screen: length/timeout process storm

The preregistered first screen asked one DeepSeek v4 Flash call to emit candidate
relations, 18 verbose chunk rows, and three verbose bundle rows. At RAG
concurrency 25, eight calls completed successfully, then many in-flight calls
simultaneously entered `finish_reason=length` retries; 18 reached the 180-second
semantic timeout together. The run was interrupted under the process-storm
rule. No merged case-result file was produced and no screen decision entered an
endpoint. The eight finalized telemetry records are preserved as
`semantic_screen/aborted_combined_telemetry.jsonl`; unfinalized in-flight work is
not represented as successful output.

Recovery freezes two independent compact schemas: candidate equivalence and
retrieval evidence. The latter retains every scientific field and all 18 chunk
IDs but returns enum arrays without generated explanations. Separate immutable
caches prevent partial combined responses from being reused. This is an
adaptive runtime repair, not a scientific treatment or a retry-normalization
experiment.

The compact candidate component was then started at 25 workers. After 284
finalized semantic-call telemetry records (327 physical attempts, 18 recorded
physical errors), concurrent 502 responses, `IncompleteRead`, closed
connections and timeouts again formed a network storm. The process was stopped.
The recovery amendment lowers only the audit-subcontractor concurrency to 8;
287 immutable cache records are reused, including six schema-invalid records
that remain failures and force root review. The stop rule used runtime errors,
not candidate correctness or relation labels.

The compact retrieval component still emitted 1,299–2,810 output tokens per
finalized call despite a short visible enum JSON because default hidden
reasoning was active (`reasoning_config=null`). Six calls used 19,118 output
tokens; concurrent length retries and three timeouts began. Before reviewing any
retrieval label, the component was stopped and a second amendment disabled
hidden reasoning (`effort=none`, `exclude=true`). Model, prompt, payload, enum
schema, 8-worker cap and immutable caches remain unchanged.

## Retrieval-screen workspace recovery

The six cache and telemetry records described above had not been committed when
the ephemeral execution workspace was manually stopped. The resumed environment
could recover the remote branch through `9ad279757` but not those uncommitted
files. Their retrieval labels and case correctness were therefore unavailable
and were not reviewed. The recovery amendment was frozen before any replacement
call and applies the already-preregistered hidden-reasoning-disabled settings to
all 400 cases. No result from the unavailable six-record run enters an endpoint;
the recovered retrieval component is one complete and internally consistent
400-case execution. This is environment recovery, not a new treatment arm or a
repeated-run variance experiment.
