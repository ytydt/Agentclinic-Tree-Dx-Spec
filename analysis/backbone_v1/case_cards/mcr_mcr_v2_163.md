# MCR / mcr_v2 / case 163

- **gold**: Acute appendicitis
- **layer**: `all_miss_but_recalled`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 至少一臂召回金标但无人Acc@1→排序天花板

## Backbone e7
- S2 pool n=49 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Ectopic pregnancy, Ovarian torsion, Ruptured ovarian cyst, Appendicitis, Hemorrhagic corpus luteum cyst; gold_in_s3=True
- S4 champion: **Ectopic pregnancy**; gold_match=False
- S2 gold matches: Appendicitis

## Backbone v0
- S2 pool n=17 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Ectopic pregnancy, Ovarian torsion, Ruptured ovarian cyst, Appendicitis, Corpus luteum cyst; gold_in_s3=True
- S4 champion: **Ectopic pregnancy**; gold_match=False
- S2 gold matches: Appendicitis

## Baseline B06 MAC
- pred: Ectopic Pregnancy; Ovarian Cyst
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Ectopic Pregnancy', 'Ovarian Cyst']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Ectopic Pregnancy; Adnexal Mass or Ovarian Cyst
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Ectopic Pregnancy', 'Adnexal Mass or Ovarian Cyst']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Ectopic Pregnancy; Adnexal Torsion
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Ectopic Pregnancy', 'Adnexal Torsion']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
