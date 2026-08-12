# E2 exhaustive consensus-correction protocol

This supplement was frozen after a falsifying audit observation: two heterogeneous reviewers both called tuberculosis a partial match to IgA nephropathy. The original queue and its hashes are unchanged.

The root auditor reads `consensus_sweep_cards.jsonl` without its index. Every candidate-reference pair not already in the primary root queue and not covered by the frozen exact-synonym bridge is reviewed. The question is the relation between the candidate label and benchmark reference—not whether the candidate is a plausible differential for the clinical record. The record is used only to resolve compatible specificity, anatomy, etiology, time/state and composite scope.

No method identity, arm output, strict/task correctness, mapper status, sampling stratum or queue trigger is visible on the cards. Final E2 relation endpoints therefore use root review for every non-exact pair.
