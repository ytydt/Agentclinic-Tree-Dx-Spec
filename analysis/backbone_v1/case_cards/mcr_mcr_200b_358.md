# MCR / mcr_200b / case 358

- **gold**: Foreign body granuloma
- **layer**: `all_miss_but_recalled`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **recall**: e7=1 v0=0 B06=0 B07=0
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 至少一臂召回金标但无人Acc@1→排序天花板

## Backbone e7
- S2 pool n=51 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Tenosynovial Giant Cell Tumor, Giant cell tumor of the tendon sheath, Osteoarthritis, Carpal Tunnel Syndrome, Idiopathic synovial chondromatosis; gold_in_s3=False
- S4 champion: **Tenosynovial Giant Cell Tumor**; gold_match=False
- S2 gold matches: Foreign Body Granuloma

## Backbone v0
- S2 pool n=20 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Tenosynovial Giant Cell Tumor, De Quervain's Tenosynovitis, Carpal Tunnel Syndrome, Osteoarthritis, Infectious Tenosynovitis; gold_in_s3=False
- S4 champion: **Tenosynovial Giant Cell Tumor**; gold_match=False

## Baseline B06 MAC
- pred: Tenosynovial Giant Cell Tumor; Degenerative Arthritis
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Tenosynovial Giant Cell Tumor', 'Degenerative Arthritis']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Synovitis/Tenosynovitis; Tenosynovial Giant Cell Tumor
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Tenosynovial Giant Cell Tumor', 'Synovitis/Tenosynovitis']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Pigmented Villonodular Synovitis; Giant Cell Tumor of the Tendon Sheath
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Pigmented Villonodular Synovitis', 'Giant Cell Tumor of the Tendon Sheath']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
