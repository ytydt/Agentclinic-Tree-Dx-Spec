# DA / d2_seq100 / case 4

- **gold**: Microvenular hemangioma (MVH)
- **layer**: `base_win_rank`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=0 APHHM=1
- **recall**: e7=1 v0=1 B06=0 B07=1
- **auto_tags**: s3_s4_ranking
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: e7 S2有金标但S3剪掉；基线排对→骨干剪枝/排序弱点

## Backbone e7
- S2 pool n=40 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Kaposi's sarcoma, Tufted angioma, Kaposiform hemangioendothelioma, Retiform hemangioendothelioma, Targetoid hemosiderotic hemangioma; gold_in_s3=False
- S4 champion: **Retiform hemangioendothelioma**; gold_match=False
- S2 gold matches: Hemangioma, Microvenular hemangioma

## Backbone v0
- S2 pool n=16 mode=None k=None; gold_in_s2=True
- S3 shortlist (5): Kaposiform hemangioendothelioma, Tufted angioma, Epithelioid hemangioma, Retiform hemangioendothelioma, Hemangioma; gold_in_s3=True
- S4 champion: **Kaposiform hemangioendothelioma**; gold_match=False
- S2 gold matches: Hemangioma

## Baseline B06 MAC
- pred: Targetoid hemosiderotic hemangioma; Kaposiform hemangioendothelioma
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Targetoid hemosiderotic hemangioma', 'Kaposiform hemangioendothelioma']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Kaposi's Sarcoma; Hemangioma
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ["Kaposi's Sarcoma", 'Hemangioma']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Kaposi's sarcoma; Jessner's lymphocytic infiltration of the skin
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ["Kaposi's sarcoma", "Jessner's lymphocytic infiltration of the skin"]
- cand_recall=False

## APHHM
- tree_n=27 tree_recall=True
- final_n=2 final_recall=True fail_mode=final_ok
- final_ranking: angioma, Arteriovenous Malformation
- human_adjudication.at1=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
