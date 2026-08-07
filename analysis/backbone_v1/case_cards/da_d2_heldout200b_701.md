# DA / d2_heldout200b / case 701

- **gold**: Arteriocolonic fistula of Inferior Mesenteric Artery Aneurysm (IMAA)
- **layer**: `all_miss_but_recalled`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 至少一臂召回金标但无人Acc@1→排序天花板

## Backbone e7
- S2 pool n=46 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Pseudoaneurysm of the inferior mesenteric artery, Inferior mesenteric artery aneurysm, Intra-abdominal hemorrhage due to trauma, Ruptured abdominal aortic aneurysm, Polyarteritis nodosa; gold_in_s3=True
- S4 champion: **Pseudoaneurysm of the inferior mesenteric artery**; gold_match=False
- S2 gold matches: Inferior mesenteric artery aneurysm

## Backbone v0
- S2 pool n=18 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Pseudoaneurysm of the inferior mesenteric artery, Inferior mesenteric artery aneurysm, Intra-abdominal hemorrhage, Ruptured abdominal aortic aneurysm, Intestinal angiodysplasia; gold_in_s3=True
- S4 champion: **Pseudoaneurysm of the inferior mesenteric artery**; gold_match=False
- S2 gold matches: Inferior mesenteric artery aneurysm

## Baseline B06 MAC
- pred: Ruptured Pseudoaneurysm of the Inferior Mesenteric Artery; Intra-abdominal Hemorrhage
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Ruptured Pseudoaneurysm of the Inferior Mesenteric Artery', 'Intra-abdominal Hemorrhage']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Ruptured Pseudoaneurysm of the Inferior Mesenteric Artery; Intra-Abdominal Hemorrhage due to Arterial Injury
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Ruptured Pseudoaneurysm of the Inferior Mesenteric Artery', 'Intra-Abdominal Hemorrhage due to Arterial Injury']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
