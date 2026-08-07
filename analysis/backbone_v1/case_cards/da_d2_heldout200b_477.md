# DA / d2_heldout200b / case 477

- **gold**: Multisystem Inflammatory Syndrome in Children (MIS-C) with COVID-19 associated acute ischemic stroke
- **layer**: `base_win_recall`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=
- **recall**: e7=0 v0=0 B06=1 B07=0
- **auto_tags**: multiagent_vote
- **manual_tag**: `multiagent_vote`
- **one_liner**: e7 S2未召回金标，基线直接命中→基线入口覆盖骨干盲区

## Backbone e7
- S2 pool n=56 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Acute Disseminated Encephalomyelitis, Cerebral Vasculitis, Rasmussen Encephalitis, Herpes Simplex Encephalitis, Acute Hemorrhagic Leukoencephalitis; gold_in_s3=False
- S4 champion: **Acute Disseminated Encephalomyelitis**; gold_match=False

## Backbone v0
- S2 pool n=19 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Acute Disseminated Encephalomyelitis, Cerebral Vasculitis, Rasmussen Encephalitis, Moyamoya Disease, Herpes Simplex Encephalitis; gold_in_s3=False
- S4 champion: **Acute Disseminated Encephalomyelitis**; gold_match=False

## Baseline B06 MAC
- pred: Multisystem Inflammatory Syndrome in Children (MIS-C); Cerebral Vasculitis
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Multisystem Inflammatory Syndrome in Children (MIS-C)', 'Cerebral Vasculitis']
- cand_recall=True

## Baseline B07 MEDDx
- pred: COVID-19 associated cerebral vasculitis; Moyamoya syndrome
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['COVID-19 associated cerebral vasculitis', 'Moyamoya syndrome']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
