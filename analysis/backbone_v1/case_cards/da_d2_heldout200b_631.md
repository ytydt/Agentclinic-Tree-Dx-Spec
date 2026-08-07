# DA / d2_heldout200b / case 631

- **gold**: Primary Cardiac Angiosarcoma
- **layer**: `base_win_recall`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=
- **recall**: e7=0 v0=1 B06=1 B07=1
- **auto_tags**: multiagent_vote
- **manual_tag**: `multiagent_vote`
- **one_liner**: e7 S2未召回金标，基线直接命中→基线入口覆盖骨干盲区

## Backbone e7
- S2 pool n=54 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Intravascular lymphoma, Angiosarcoma of the heart, Epithelioid hemangioendothelioma, Intravascular large B-cell lymphoma, Kaposi's sarcoma with pulmonary involvement; gold_in_s3=False
- S4 champion: **Intravascular large B-cell lymphoma**; gold_match=False

## Backbone v0
- S2 pool n=18 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Intravascular lymphoma, Choriocarcinoma, Angiosarcoma, Pulmonary lymphoma, Metastatic adrenal cortical carcinoma; gold_in_s3=True
- S4 champion: **Intravascular lymphoma**; gold_match=False
- S2 gold matches: Angiosarcoma

## Baseline B06 MAC
- pred: Angiosarcoma; Choriocarcinoma
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Angiosarcoma', 'Choriocarcinoma']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Angiosarcoma; Metastatic disease
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Angiosarcoma', 'Metastatic disease']
- cand_recall=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
