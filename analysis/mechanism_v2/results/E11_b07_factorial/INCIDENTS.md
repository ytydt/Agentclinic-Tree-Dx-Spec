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
