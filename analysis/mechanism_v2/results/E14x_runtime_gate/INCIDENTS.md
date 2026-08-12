# E14x incidents and limitations

1. **No primary identical-upstream pair.** Lite and Adaptive-4v2 were historical fresh runs; G1/G2 canonical hashes differ in 300/300 cases. All paired outcome differences are therefore exploratory associations, not an identified A1 effect.
2. **Adaptive-4v2 includes A5.** Thirty-nine non-triggered cases use the pairwise selector, so the historical arm changes more than the Call-4 gate.
3. **Legacy Adaptive-4 lacks `frontier_final`.** Its A1 registry survival can be measured, but final frontier exposure cannot be reconstructed and is reported unavailable rather than zero.
4. **MCR per-case historical judge records are absent from the committed directories.** E14x does not reconstruct paper-aligned LLM-judge outcomes; it reports frozen exact/synonym concept matching and retains aggregate judge files only as provenance.
5. **Frozen identity undercounts clinical equivalence.** Root review identified ordinary scope/synonym repairs (for example maculopapular/morbilliform drug eruption) and one hyphen-only false strict flip. Strict and manual clinical endpoints remain separate.
6. **No threshold confirmation.** The signal scan reads historical outcomes and is explicitly outcome-leaking/descriptive. No threshold from it is proposed for deployment.
7. **No API execution.** E14x is offline and made zero provider calls, so there is no API/dependency incident for this experiment.

