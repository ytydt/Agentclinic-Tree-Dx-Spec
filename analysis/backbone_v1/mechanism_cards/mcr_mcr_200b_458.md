# MCR / mcr_200b / case 458

- **gold**: Lymphangioleiomyomatosis
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=1 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `rationale_overfit`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 36-year-old woman presented with a 7-day history of right-sided chest pain and dyspnea without fever or cough. She reported two prior spontaneous pneumothoraces: one right-sided in 2018 managed medically, and one left-sided in 2019 treated surgically. She also noted occasional small-volume hemoptysis. 

On admission, she was alert, with SpO2 97% on room air. Right chest auscultation revealed hypoventilation; no crackles were appreciated. The remainder of the examination, including endocrine and genitourinary systems, was unremarkable. 

Laboratory studies (CBC, chemistry, urinalysis) were within normal limits; microbiological tests for tuberculosis and other bacteria were negative. 

Chest radiography showed lung hyperinflation without focal parenchymal abnormalities. HRCT of the chest revealed a small right pneumothorax and numerous round, thin-walled air cysts (2–5 mm) scattered in both lungs; no irregular cyst shapes were noted. 

Pulmonary function testing demonstrated a 6-minute walk distance of 67% predicted, normal DLCO, and a negative bronchodilator response. 

Thirteen days later, she developed left-sided chest pain and dyspnea. Chest X-ray confirmed a new left pneumotho…

## Backbone e7

- S2 n=46 gold_rank=1
  - clusters: gold=1 near=0 other=45
- S3 shortlist (5):
  - [gold] Lymphangioleiomyomatosis
  - [other] Birt-Hogg-Dube syndrome
  - [other] Ehlers-Danlos syndrome
  - [other] Pulmonary Langerhans cell histiocytosis
  - [other] Tuberous sclerosis complex
    - why_kept(Lymphangioleiomyomatosis): Recurrent spontaneous pneumothoraces and small air cysts on HRCT
    - why_kept(Birt-Hogg-Dube syndrome): Recurrent spontaneous pneumothoraces and presence of lung cysts
    - why_kept(Ehlers-Danlos syndrome): Recurrent pneumothoraces and possible connective tissue disorder
    - why_kept(Pulmonary Langerhans cell histiocytosis): Presence of lung cysts and possible interstitial lung disease
    - why_kept(Tuberous sclerosis complex): Possible association with lymphangiomyomatosis and lung cysts
- S4 champion: **Birt-Hogg-Dube syndrome** cluster=other jaccard=0.00
- S4 rationale: The patient's history of recurrent spontaneous pneumothoraces and the presence of numerous round, thin-walled air cysts on HRCT are characteristic features of Birt-Hogg-Dube syndrome.
- S4 rejected:
  - [gold] Lymphangioleiomyomatosis: Typically presents with progressive respiratory symptoms and cystic changes on imaging, but often with a more extensive and irregular cystic pattern
  - [other] Ehlers-Danlos syndrome: Primarily associated with skin, joint, and vascular manifestations, and not typically characterized by the specific lung findings in this case
  - [other] Pulmonary Langerhans cell histiocytosis: Usually presents with nodular infiltrates and cavitation on imaging, which is not the primary finding in this case
  - [other] Tuberous sclerosis complex: Characterized by a wide range of manifestations including skin, neurological, and renal, but the specific lung findings and clinical presentation in this case do not align closely with tuberous sclerosis complex

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Birt-Hogg-Dube syndrome', 'lymphangioleiomyomatosis']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Birt-Hogg-Dube syndrome', 'lymphangioleiomyomatosis', 'pulmonary Langerhans cell histiocytosis', 'alpha-1 antitrypsin deficiency', 'cystic lung disease', 'Birt-Hogg-Dube syndrome', 'lymphangioleiomyomatosis', 'pulmonary Langerhans cell histiocytosis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Lymphangioleiomyomatosis (LAM)', 'Birt-Hogg-Dube syndrome']
- diagnose: ['Lymphangioleiomyomatosis (LAM)', 'Birt-Hogg-Dube syndrome']
- queries: ['lymphangioleiomyomatosis diagnosis', 'pneumothorax causes', 'lung cysts differential diagnosis']

## B01 (code=`b01_ok` locus=`gen_ok`)
- top2: ['Lymphangioleiomyomatosis', 'Pulmonary Langerhans cell histiocytosis']
- queries: ['recurrent spontaneous pneumothorax with bilateral small air cysts', 'differential diagnosis for multiple pneumothoraces in a young woman', 'HRCT findings of thin-walled air cysts in lungs', 'causes of recurrent pneumothorax with normal pulmonary function tests']
- n_chunks=12

## APHHM
_na_

