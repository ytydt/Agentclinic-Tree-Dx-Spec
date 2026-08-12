# Exhaustive E2 root protocol

The root auditor reads `cards.jsonl` without `index.jsonl`. Cases and candidates are deterministically shuffled. Codes are frozen before restoring case keys, arm provenance, legacy-chain, task, or prior leaderboard results.

Identity codes: `Q` unique full reference; `F` family identifiable but full specificity not compelled; `M` multiple complete answers; `S` reference contains unsupported specificity; `I` insufficient case information; `U` genuinely uncertain.

Relation codes: `C` complete equivalent; `P` compatible parent/component or underspecified object; `X` conflicting subtype/scope; `M` manifestation/related object; `N` different entity; `U` genuinely uncertain. Safe exact/frozen-synonym relations are deterministically `C` and do not consume a manual relation code.
