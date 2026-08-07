# DA / d2_heldout200b / case 579

- **gold**: Gas-containing brain abscess
- **layer**: `base_win_rank`  aphhm_layer=``
- **correct**: e7=0 v0=1 B06=1 B07=1 B01= APHHM=
- **recall**: e7=1 v0=1 B06=1 B07=1
- **auto_tags**: s3_s4_ranking
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: e7召回并进短表但S4选错；基线排对

## Backbone e7
- S2 pool n=52 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Brain abscess, Otogenic brain abscess, Post-surgical brain abscess, Pyogenic brain abscess, Cholesteatoma-associated brain abscess; gold_in_s3=True
- S4 champion: **Otogenic brain abscess**; gold_match=False
- S2 gold matches: Brain abscess

## Backbone v0
- S2 pool n=20 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Brain Abscess, Subdural Empyema, Epidural Abscess, Osteomyelitis of the Skull, Proteus Mirabilis Brain Abscess; gold_in_s3=True
- S4 champion: **Brain Abscess**; gold_match=True
- S2 gold matches: Brain Abscess

## Baseline B06 MAC
- pred: Brain Abscess; Subdural Empyema
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Brain Abscess', 'Subdural Empyema']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Brain Abscess; Cerebral Infection or Abscess related to recent surgery
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Brain Abscess', 'Cerebral Infection or Abscess related to recent surgery']
- cand_recall=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
