# E1 runtime incidents

All eight arms completed and each contains 200 ITA rows. No API credential,
credit or rate-limit incident occurred.

The hierarchical schema rejected 11, 11, 13 and 24 responses in clean-fixed,
clean-reordered, options-fixed and options-reordered respectively. The flat
schema rejected 0, 1, 1 and 1. These rows are retained as failures; no output
was silently repaired or imputed.

After the final flat options-reordered arm had written its result, telemetry,
log and raw archive, the outer execution wrapper reported a cancelled network
poll approval. File counts and hashes were checked locally, so this did not
truncate or alter the experiment.
