# MCR / mcr_v1 / case 35

- **gold**: Petersen’s hernia
- **layer**: `aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=1
- **loci**: e7=`s2_miss` B06=`agents_hit_supervisor_drop` B07=`draft_miss` B01=`rag_hit_gen_miss` APHHM=`tree_miss`
- **primary_locus**: APHHM=tree_miss
- **covariates**: vig_words=301; gold_words=2; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: layer=aphhm_win; primary loci above.

## Vignette (trunc)
A 36-year-old woman presented with sudden-onset, sharp upper abdominal pain rated 9/10, which awakened her early in the morning. The pain was minimally relieved by oxycodone and worsened with oral intake. She reported associated nausea and vomiting and was unable to tolerate liquids or a soft diet. Three weeks earlier, she had undergone Roux-en-Y gastric bypass for weight management, after which she experienced intermittent nausea. She denied bloating, changes in bowel habits, or urinary symptom...

## Backbone e7
- S1 key_facts: 36-year-old woman; Sudden-onset, sharp upper abdominal pain; Pain awakened her early in the morning; Pain rated 9/10; Pain minimally relieved by oxycodone; Pain worsened with oral intake; Associated nausea and vomiting; Unable to tolerate liquids or a soft diet
- S2 mode=complement k=3 pool_n=47 gold_in_s2=False
  - call1: ['Internal Hernia', 'Small Bowel Obstruction', 'Intussusception', 'Volvolus', 'Mesenteric Ischemia', 'Gastrointestinal P
  - call2: ['Mesenteric Venous Thrombosis', 'Small Bowel Volvulus', 'Closed Loop Obstruction', 'Intestinal Malrotation', 'Sigmoid V
  - call3: ['Abdominal Cocoon', 'Ehlers-Danlos Syndrome', 'Familial Mediterranean Fever', 'Henoch-Schonlein Purpura', 'Intra-abdomi
- S3 shortlist n=5 gold=False: Internal Hernia, Small Bowel Obstruction, Roux-en-Y Gastric Bypass Complication, Mesenteric Ischemia, Adhesional Band Syndrome
- S4 champion: **Internal Hernia** gold=False
- S4 raw (trunc): {"champion": "Internal Hernia", "rationale": "The contrast-enhanced abdominal CT demonstrated a cluster of small-bowel loops in the left upper quadrant with a spiral pattern of central mesenteric vessels, which is consistent with internal hernia, especially given the patient's re

## Backbone v0 (compact)
- S1 key_facts: 36-year-old woman presented with acute abdominal pain; Pain awakened her early in the morning; Pain was minimally relieved by oxycodone; Patient had undergone Roux-en-Y gastric bypass three weeks earlier; Patient had intermittent nausea after surgery; Patient denied bloating, changes in bowel habits, or urinary symptoms; Medical history included type 2 diabetes mellitus; Patient was taking pantoprazole, metformin, and semaglutide
- S2 mode=None k=None pool_n=16 gold_in_s2=False
  - pool gold matches: []
  - pool head: Intestinal obstruction, Internal hernia, Volvolus of small intestine, Mesenteric ischemia, Gastrointestinal perforation, Pancreatitis, Cholecystitis, Hepatic infarction
- S3 shortlist n=5 gold=False: Internal hernia, Adhesive bowel obstruction, Intestinal obstruction, Mesenteric ischemia, Small bowel strangulation
- S4 champion: **Internal hernia** gold=False
- S4 raw (trunc): {"champion": "Internal hernia", "rationale": "The patient's symptoms of acute abdominal pain, nausea, and vomiting, combined with the CT findings of a cluster of small-bowel loops and a spiral pattern of central mesenteric vessels, are consistent with an internal hernia, particul

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's symptoms of sudden-onset, sharp upper abdominal pain, nausea, and vomiting, particularly after a recent Roux-en-Y gastric bypass, along with the C
  - turn1 gold_mention=True diag=
    The patient's presentation and imaging findings align with Doctor A's assessment, suggesting internal herniation as the primary concern, given the recent gastri
  - turn2 gold_mention=True diag=
    The patient's symptoms and CT findings, including a cluster of small-bowel loops and a spiral pattern of the central mesenteric vessels, are consistent with int
- supervisor votes=3 top2=['Internal Hernia', 'Adhesive Bowel Obstruction'] gold=False

## Baseline B07
- draft=['Internal Herniation', 'Adhesive Bowel Obstruction'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['internal herniation after Roux-en-Y gastric bypass', 'adhesive bowel obstruction symptoms', 'small bowel obstruction CT findings']
- diagnose=['Internal Herniation', 'Adhesive Bowel Obstruction'] gold=False

## Baseline B01
- queries=['abdominal pain after Roux-en-Y gastric bypass', 'internal herniation vs adhesive bowel obstruction', 'small bowel obstruction diagnosis', 'CT findings of mesenteric whirl pattern']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Internal Hernia', 'Adhesive Small Bowel Obstruction'] gold=False

## APHHM
- tree_n=29 tree_recall=False
- gold_leaf=None
- final_n=1 final_recall=False ranking=['Internal Hernia after Roux-en-Y Gastric Bypass']
- human_at1=False fail_mode=tree_miss

