# MCR / mcr_v1 / case 111

- **gold**: Giant cell tumor of bone
- **layer**: `e7_win_recall`  aphhm_layer=`aphhm_lose`
- **correct**: e7=1 v0=0 B06=0 B07=0 B01=0 APHHM=0
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: entrance_breadth, aphhm_prune_loss
- **manual_tag**: `entrance_breadth`
- **one_liner**: e7 S2召回且S4命中；基线候选未召回→入口/覆盖优势

## Backbone e7
- S2 pool n=49 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Chordoma, Osteolytic metastasis, Giant cell tumor, Plasmacytoma, Multiple myeloma; gold_in_s3=True
- S4 champion: **Giant cell tumor**; gold_match=True
- S2 gold matches: Giant cell tumor

## Backbone v0
- S2 pool n=18 mode=None k=None; gold_in_s2=True
- S3 shortlist (5): Osteolytic metastasis, Chordoma, Giant cell tumor, Plasmacytoma, Spinal tuberculosis; gold_in_s3=True
- S4 champion: **Osteolytic metastasis**; gold_match=False
- S2 gold matches: Giant cell tumor

## Baseline B06 MAC
- pred: Metastatic disease; Primary bone tumor
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Metastatic disease', 'Primary bone tumor']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Vertebral Osteomyelitis; Vertebral Tumor
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Vertebral Osteomyelitis', 'Vertebral Tumor']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Metastatic spinal tumor; Vertebral osteomyelitis
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Metastatic spinal tumor', 'Vertebral osteomyelitis']
- cand_recall=False

## APHHM
- tree_n=24 tree_recall=True
- final_n=3 final_recall=False fail_mode=prune_loss
- final_ranking: Chordoma, Pancoast tumor, Tuberculous spondylitis
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
