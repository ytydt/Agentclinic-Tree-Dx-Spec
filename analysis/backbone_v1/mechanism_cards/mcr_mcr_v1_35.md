# MCR / mcr_v1 / case 35

- **gold**: Petersen’s hernia
- **layer**: `aphhm_win` · **layer_aphhm**: `aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=1
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A 36-year-old woman presented with sudden-onset, sharp upper abdominal pain rated 9/10, which awakened her early in the morning. The pain was minimally relieved by oxycodone and worsened with oral intake. She reported associated nausea and vomiting and was unable to tolerate liquids or a soft diet. Three weeks earlier, she had undergone Roux-en-Y gastric bypass for weight management, after which she experienced intermittent nausea. She denied bloating, changes in bowel habits, or urinary symptoms.

Her medical history included type 2 diabetes mellitus managed with pantoprazole, metformin, and semaglutide. She had undergone laparoscopic cholecystectomy, four lower-segment cesarean sections, bilateral salpingectomy, diagnostic hysteroscopy, and endometrial ablation.

On examination, she appeared uncomfortable. There was generalized abdominal tenderness, most pronounced in the right hypochondrium, without peritoneal signs. Her pain was disproportionate to the physical findings. Vital signs were within normal limits: temperature 36.4 °C, heart rate 89 beats/min, respiratory rate 18 breaths/min, and blood pressure 126/88 mm Hg.

Laboratory studies showed hemoglobin 135 g/L, white-cell c…

## Backbone e7

- S2 n=47 gold_rank=None
  - clusters: gold=0 near=2 other=45
- S3 shortlist (5):
  - [near] Internal Hernia
  - [other] Small Bowel Obstruction
  - [other] Roux-en-Y Gastric Bypass Complication
  - [other] Mesenteric Ischemia
  - [other] Adhesional Band Syndrome
    - why_kept(Internal Hernia): Post-surgical patient with sudden-onset severe upper abdominal pain and CT findings of small-bowel loops in the left upper quadrant with spiral pattern of central mesenteric vessels
    - why_kept(Small Bowel Obstruction): Patient presented with severe abdominal pain, nausea, vomiting, and inability to tolerate oral intake, with CT findings of clustered small-bowel loops
    - why_kept(Roux-en-Y Gastric Bypass Complication): Recent history of Roux-en-Y gastric bypass and presentation with severe abdominal pain and nausea, suggesting a possible complication from the surgery
    - why_kept(Mesenteric Ischemia): Severe abdominal pain out of proportion to physical findings, with CT findings of congestion of mesenteric fat and stretching of vessels
    - why_kept(Adhesional Band Syndrome): History of multiple abdominal surgeries and presentation with severe abdominal pain, suggesting possible adhesional bands causing bowel obstruction
- S4 champion: **Internal Hernia** cluster=near jaccard=0.33
- S4 rationale: The contrast-enhanced abdominal CT demonstrated a cluster of small-bowel loops in the left upper quadrant with a spiral pattern of central mesenteric vessels, which is consistent with internal hernia, especially given the patient's recent history of Roux-en-Y gastric bypass surgery.
- S4 rejected:
  - [other] Small Bowel Obstruction: There were no signs of anastomotic leak, strangulation, or bowel obstruction on the CT scan.
  - [other] Roux-en-Y Gastric Bypass Complication: While the patient had a recent Roux-en-Y gastric bypass, the specific findings on CT are more suggestive of internal hernia than a general complication of the surgery.
  - [other] Mesenteric Ischemia: The patient's laboratory studies, including lactate levels, did not indicate ischemia, and the CT findings did not show signs of bowel ischemia.
  - [other] Adhesional Band Syndrome: The CT findings of a spiral pattern of central mesenteric vessels and the clustering of small-bowel loops are more characteristic of internal hernia than adhesional band syndrome.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Internal Hernia', 'Adhesive Bowel Obstruction']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Internal Hernia', 'Adhesive Bowel Obstruction', 'Gastrointestinal Stricture', 'Bowel Obstruction', 'Intussusception', 'Internal Hernia', 'Adhesive Bowel Obstruction', 'Bowel Obstruction']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Internal Herniation', 'Adhesive Bowel Obstruction']
- diagnose: ['Internal Herniation', 'Adhesive Bowel Obstruction']
- queries: ['internal herniation after Roux-en-Y gastric bypass', 'adhesive bowel obstruction symptoms', 'small bowel obstruction CT findings']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['Internal Hernia', 'Adhesive Small Bowel Obstruction']
- queries: ['abdominal pain after Roux-en-Y gastric bypass', 'internal herniation vs adhesive bowel obstruction', 'small bowel obstruction diagnosis', 'CT findings of mesenteric whirl pattern']
- n_chunks=12

## APHHM
- tree_n=29 final_n=1
- final: ['Internal Hernia after Roux-en-Y Gastric Bypass']
- tree gold_cluster_n=0 final gold=False

