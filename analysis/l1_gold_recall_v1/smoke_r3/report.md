# R3 gap-fill smoke (`smoke_r3`)

- generated: `2026-07-23T20:31:18.085626+00:00`
- protocol: `r3_gapfill_lite_v1`

## Verdict

- UNBIND coverage lever: **REJECT** — All 18 MAPPER_UNBIND cases already have clinical/tree parents; R3 cannot repair AutoCoverage for mapper false MISS.
- ABSENT subset: **REJECT** — Frozen trees already used branch_mode=recall_hints_gap (gap_fill ON); cases 67 and 231 remain clinical TREE_PARENT_ABSENT (axis mismatch). R3 does not fix wrong MECE axis when gold-ish hints exist (231) or when sepsis-like hints fail to force a systemic-shock L1 (67).
- `claim_allowed`: `False`
- production default: **leave off / unchanged** (build already used gap_fill)

## Build evidence (frozen ≡ R3-on)

```json
{
  "m01_build_trees_branch_mode": "recall_hints_gap",
  "pipeline_staged_branch_mode": "recall_hints_gap",
  "config_mapping": "recall_hints_gap → branch_kb_recall_hints=True + branch_recall_gap_fill=True",
  "provenance_mode_field": "recall_hints",
  "note": "Frozen DiagnosisArena shared_trees were built with gap_fill ON. Re-running identical R3-on rebuild is non-informative; ABSENT persistence under R3-on is decisive."
}
```

## Mechanism: MAPPER_UNBIND (n=18)

Gap-fill only repairs uncovered *recall candidates* into the MECE partition. It cannot create mapper leaf binds. Clinical audit parents already present → R3 **cannot** raise AutoCoverage on these 18.

- v2 proxy TreeParentPresent: **16/18**

## ABSENT applicability (67, 231)

| case | goldish in top10 hints | any L1 keyword-fit | clinical TPP | frozen gap_fill |
|------|------------------------|-------------------:|-------------:|:---------------:|
| 67 | — | 0 | 0 | yes |
| 231 | ['Stage IV invasive renal urothelial carcinoma'] | 0 | 0 | yes |

### Notes

- Case **231**: exact gold string already in hints under R3-on build; BranchCreator still chose paraneoplastic/skin axis → gap-fill insufficient for axis correction.
- Case **67**: systemic septic-shock L1 absent; CNS-involvement axis dominates.
- Live identical `recall_hints_gap` rebuild **skipped** (non-informative vs frozen).

## Conclusion

**REJECT R3** as coverage main lever and as ABSENT fix on this cohort.
