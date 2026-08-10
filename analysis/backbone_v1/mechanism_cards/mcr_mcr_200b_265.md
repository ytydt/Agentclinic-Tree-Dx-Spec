# MCR / mcr_200b / case 265

- **gold**: Intestinal T-cell lymphoma not otherwise specified
- **layer**: `base_win_recall` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=0 APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 55-year-old man with chronic obstructive pulmonary disease and opioid use disorder presented with worsening abdominal distention and a 60-lb unintentional weight loss over 1 year, along with increasing difficulty with bowel movements. He denied melena, nausea, vomiting, fevers, flank pain, dysphagia, or odynophagia, and had no history of abdominal surgery.

Three weeks before admission, abdominal CT with contrast showed a small-bowel obstruction with a transition point in the right-mid abdomen and focal small-bowel wall thickening, plus mesenteric adenopathy. His symptoms improved without intervention, and he was discharged.

He returned 3 weeks later with diffuse abdominal pain. Repeat CT showed multiple dilated loops of small bowel with air-fluid levels. Colonoscopy revealed two polyps; cold-forceps biopsies showed non-specific chronic inflammation without features of inflammatory bowel disease. Video capsule endoscopy demonstrated erythematous gastritis, multiple small-bowel ulcers, and an atrophic duodenum. Two weeks later, double-balloon enteroscopy identified multiple jejunal strictures and areas suggestive of inflammatory bowel disease, and outpatient IBD management was pl…

## Backbone e7

- S2 n=49 gold_rank=None
  - clusters: gold=0 near=10 other=39
- S3 shortlist (5):
  - [other] Crohn's disease
  - [near] Intestinal lymphoma
  - [other] Ulcerative colitis
  - [near] Enteropathy-associated T-cell lymphoma
  - [other] NSAID-induced enteropathy
    - why_kept(Crohn's disease): Chronic abdominal symptoms, weight loss, bowel obstruction, and small-bowel ulcers
    - why_kept(Intestinal lymphoma): Extensive lymphocytic infiltrates with epitheliotropism and suspicion for lymphoma
    - why_kept(Ulcerative colitis): Chronic inflammation and ulceration in the colon and small bowel
    - why_kept(Enteropathy-associated T-cell lymphoma): Small-bowel ulcers, strictures, and lymphocytic infiltrates
    - why_kept(NSAID-induced enteropathy): History of chronic abdominal symptoms and potential NSAID use
- S4 champion: **Crohn's disease** cluster=other jaccard=0.00
- S4 rationale: The patient's presentation with worsening abdominal distention, unintentional weight loss, and increasing difficulty with bowel movements, along with findings of small-bowel obstruction, multiple jejunal strictures, and perforated ulcer in the terminal ileum, are consistent with Crohn's disease. The presence of non-specific chronic inflammation, erythematous gastritis, and multiple small-bowel ulcers also support this diagnosis.
- S4 rejected:
  - [near] Intestinal lymphoma: While histologic examination revealed extensive lymphocytic infiltrates, there were no definitive atypical morphological features to support a diagnosis of lymphoma.
  - [other] Ulcerative colitis: The patient's symptoms and findings are more consistent with small-bowel involvement, which is less typical of ulcerative colitis.
  - [near] Enteropathy-associated T-cell lymphoma: There is no clear evidence of celiac disease or other enteropathy to support this diagnosis.
  - [other] NSAID-induced enteropathy: There is no mention of NSAID use in the patient's history, making this diagnosis less likely.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Lymphoma', 'Gastrointestinal lymphoma']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Lymphoma', "Crohn's disease", 'Gastrointestinal lymphoma', 'Celiac disease', 'Intestinal lymphangiectasia', 'Lymphoma', 'Gastrointestinal lymphoma', "Crohn's disease"]
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Lymphoma', 'Inflammatory Bowel Disease (IBD)']
- diagnose: ['Lymphoma', 'Inflammatory Bowel Disease (IBD)']
- queries: ['lymphocytic infiltrates with epitheliotropism in ileum', 'differential diagnosis for small bowel obstruction with lymphoid neoplasm', 'chronic obstructive pulmonary disease and opioid use disorder with abdominal symptoms']

## B01 (code=`b01_judge_miss` locus=`gen_hit_judge_miss`)
- top2: ["Crohn's disease", 'Lymphoma']
- queries: ['chronic abdominal distention and weight loss in adults', 'small-bowel obstruction with wall thickening and mesenteric adenopathy', 'jejunal strictures and inflammatory bowel disease', 'lymphocytic infiltrates with epitheliotropism in ileal biopsies']
- n_chunks=12

## APHHM
_na_

