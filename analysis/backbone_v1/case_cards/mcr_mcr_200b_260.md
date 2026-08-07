# MCR / mcr_200b / case 260

- **gold**: syphilitic aortitis
- **layer**: `e7_win_recall`  aphhm_layer=``
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: entrance_breadth
- **manual_tag**: `entrance_breadth`
- **one_liner**: e7 S2召回且S4命中；基线候选未召回→入口/覆盖优势

## Backbone e7
- S2 pool n=51 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Infectious aortitis, Aortic valve endocarditis, Syphilitic aortitis, Takayasu arteritis, Aortitis due to Salmonella species; gold_in_s3=True
- S4 champion: **Syphilitic aortitis**; gold_match=True
- S2 gold matches: Syphilitic aortitis

## Backbone v0
- S2 pool n=19 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Syphilitic aortitis, Takayasu arteritis, Aortic valve endocarditis, Acute aortic dissection, Staphylococcal aortitis; gold_in_s3=True
- S4 champion: **Syphilitic aortitis**; gold_match=True
- S2 gold matches: Syphilitic aortitis

## Baseline B06 MAC
- pred: Aortic insufficiency due to infective endocarditis; Aortitis due to syphilis (Treponema pallidum infection)
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Aortic insufficiency due to infective endocarditis', 'Aortitis due to syphilis (Treponema pallidum infection)']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Aortic Valve Disease; Infectious Aortitis
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Infectious Aortitis', 'Aortic Valve Disease']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Bicuspid Aortic Valve Disease; Infectious Aortitis
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Bicuspid Aortic Valve Disease', 'Infectious Aortitis']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
