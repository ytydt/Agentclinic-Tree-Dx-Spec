# E5 runtime and provenance incidents

## Perturbation construction

The builder made 200 semantic calls through 427 physical attempts. It served
166 frozen constructions. Thirty-three cases exhausted validation because a
width candidate semantically/surface-duplicated a typed or base candidate; one
case failed the exact five-relation count. All 34 rows are retained in
`perturbations/case_perturbations.jsonl`. Dependent typed/width arms fail closed
on exactly these constructions; base and removal do not depend on them.

This is partly a desirable validator action and partly a design limitation.
The validator catches normalized surface collisions, but the manual audit
still finds an ADEM semantic duplicate whose acronym punctuation differs.

## Selector schema failures

- `add_sibling5`: one response failed the complete-ranking contract;
- `add_synonym5`: one response failed the contract;
- `nested_width8`: two responses failed `ranking must contain every candidate
  exactly once` after retries.

Failures remain in the 200-row arm tables and are never imputed. Pairwise
comparisons state their successful-pair denominator; the 162-case common
complete analysis verifies that the main directions survive missingness.

## Add-sibling scratch recovery

The first frozen add-sibling execution reported 165/200 served, but its local
scratch workspace was reclaimed before results could be archived, analysed or
committed. Those unavailable predictions enter no endpoint or variance claim.

Recovery began from remote `cursor4` at `0ca125486f88`, which already contained
the frozen preregistration, perturbations and preceding arms. A full checkout
was stopped while Git LFS attempted to smudge unrelated large assets; the
incomplete 1.06-GiB checkout was quarantined under `/tmp` and ran no experiment.
The first sparse checkout omitted package imports and produced 200 local
`ModuleNotFoundError` rows before any API call; that directory was also
quarantined.

The committed reconstruction is the sole analysed add-sibling result. It uses
the same cases, frozen perturbations, payload builder, prompt hash, model and
runtime controls. It serves 165/200: 34 construction failures plus one ranking
schema failure. It is provenance recovery, not a scientific repeat. Details
also remain in `arms/add_sibling5/PROVENANCE.md`.

## Transport and telemetry

The runtime image lacks `openai`, `httpx`, `requests` and `pytest`. Online arms
therefore used the standard-library OpenRouter transport. The production
client still contains the official OpenAI SDK path selected by
`TREE_DX_LLM_TRANSPORT`; this environment-specific fallback did not replace
the portable implementation.

Runtime controls were:

- non-RAG worker cap 50;
- reasoning output excluded with a 64-token reasoning cap;
- direct-post output ceiling 8192;
- balanced multi-provider policy for Llama-family routing (no Groq-only
  dependency; the executed DeepSeek model also routed across many providers).

Recorded totals are lower bounds: 1,753 semantic calls, 2,207 physical
attempts, 1,429,660 input tokens, 6,110,997 output tokens and 110,260.7 summed
call-seconds. Several successful result rows have no corresponding telemetry
row in recovered/earlier arms (for example parent records 164 semantic calls
for 166 served results). No missing token or monetary cost is imputed. The API
key was usable; no credential is present in logs, payloads, caches, reports or
archives.

## Width-8 tail

Width 8 reached 175/200 quickly, then several long/length-terminated responses
used the bounded retry path. It completed 200 ITA rows in approximately nine
minutes, with 164 served, 34 frozen construction failures and two ranking
schema failures. There was no process storm and concurrency remained 50. The
tail is preserved in telemetry and raw cache rather than hidden by rerunning.
