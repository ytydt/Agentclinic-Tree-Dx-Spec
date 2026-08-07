# DA / d2_heldout200b / case 488

- **gold**: Myelodysplastic syndrome (MDS) with refractory anaemia with excess blasts-1 presenting with leukaemic vasculitis
- **layer**: `base_win_recall`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=
- **recall**: e7=0 v0=0 B06=1 B07=0
- **auto_tags**: multiagent_vote
- **manual_tag**: `multiagent_vote`
- **one_liner**: e7 S2未召回金标，基线直接命中→基线入口覆盖骨干盲区

## Backbone e7
- S2 pool n=56 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Leukocytoclastic vasculitis, Erythema multiforme, Sweet syndrome, IgA vasculitis, Cutaneous small-vessel vasculitis; gold_in_s3=False
- S4 champion: **Sweet syndrome**; gold_match=False

## Backbone v0
- S2 pool n=19 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Leukocytoclastic vasculitis, Sweet syndrome, Cutaneous lymphoma, Waldenstrom macroglobulinemia, Mycosis fungoides; gold_in_s3=False
- S4 champion: **Sweet syndrome**; gold_match=False

## Baseline B06 MAC
- pred: Myelodysplastic syndrome; Sweet syndrome
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Myelodysplastic syndrome', 'Sweet syndrome']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Myelodysplastic Syndrome (MDS) with cutaneous involvement; Acute Myeloid Leukemia (AML) with cutaneous involvement
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Myelodysplastic Syndrome (MDS) with cutaneous involvement', 'Acute Myeloid Leukemia (AML) with cutaneous involvement']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
