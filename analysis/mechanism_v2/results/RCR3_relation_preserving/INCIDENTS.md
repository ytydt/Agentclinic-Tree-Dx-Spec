# RCR-3 execution incidents

## Heterogeneous screen import abort

The first semantic-screen launch failed locally for all 300 submitted jobs
before any network request.  The standalone script added the repository root
to `sys.path` but omitted `src`, so lazy construction of `RobustLLMClient`
raised `ModuleNotFoundError: No module named 'agentclinic_tree_dx'`.  No
telemetry file or cache record was created, confirming zero provider calls and
excluding credential, region, datacenter-IP, or OpenRouter service failure.

The invalid result bundle was moved intact to the recoverable temporary path
`/tmp/rcr3_semantic_screen_aborted_20260812` and is not an experimental result.
The script now adds both the repository root and `src`; an import regression
test was added before relaunch.  No prompt, sample, model, concurrency,
endpoint, or adjudication rule changed.

The corrected launch completed all 300 provider calls and wrote 299 valid
screens plus one fail-closed schema response.  Post-run summarization then
raised `AttributeError` because the failed response used an object instead of
the required candidate-relation list.  The 300 result rows and telemetry were
already durable; no online call was repeated.  Summary/queue construction now
type-checks malformed failed responses, assigns them no proxy credit, and has a
dedicated regression test.  Final artifacts were rebuilt from the frozen
result rows and caches only.
