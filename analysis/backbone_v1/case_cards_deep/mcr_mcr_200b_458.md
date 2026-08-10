# MCR / mcr_200b / case 458

- **gold**: Lymphangioleiomyomatosis
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=1 APHHM=
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_hit_judge_miss` B07=`diagnose_ok` B01=`gen_ok` APHHM=`na`
- **primary_locus**: e7=s3_hit_s4_miss; B07=diagnose_ok
- **covariates**: vig_words=294; gold_words=1; eponym=False; subtype=False; e7_s2_rank=1; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 36-year-old woman presented with a 7-day history of right-sided chest pain and dyspnea without fever or cough. She reported two prior spontaneous pneumothoraces: one right-sided in 2018 managed medically, and one left-sided in 2019 treated surgically. She also noted occasional small-volume hemoptysis.   On admission, she was alert, with SpO2 97% on room air. Right chest auscultation revealed hypoventilation; no crackles were appreciated. The remainder of the examination, including endocrine an...

## Backbone e7
- S1 key_facts: 36-year-old woman; 7-day history of right-sided chest pain and dyspnea; No fever or cough; Two prior spontaneous pneumothoraces; Occasional small-volume hemoptysis; SpO2 97% on room air; Hypoventilation on right chest auscultation; Normal laboratory studies
- S2 mode=complement k=3 pool_n=46 gold_in_s2=True
  - call1: ['Lymphangioleiomyomatosis', 'Birt-Hogg-Dube syndrome', 'Pneumocystis jirovecii pneumonia', 'Histoplasmosis', 'Coccidioi
  - call2: ['Neurofibromatosis type 1', 'Tuberous sclerosis complex with lymphangiomyomatosis', 'Pulmonary capillaritis', 'Diffuse 
  - call3: ['Menkes disease', 'Cutis laxa', 'Pseudoxanthoma elasticum', 'Elastosis perforans serpiginosa', 'Acrodermatitis enteropa
- S3 shortlist n=5 gold=True: Lymphangioleiomyomatosis, Birt-Hogg-Dube syndrome, Ehlers-Danlos syndrome, Pulmonary Langerhans cell histiocytosis, Tuberous sclerosis complex
- S4 champion: **Birt-Hogg-Dube syndrome** gold=False
- S4 raw (trunc): {"champion": "Birt-Hogg-Dube syndrome", "rationale": "The patient's history of recurrent spontaneous pneumothoraces and the presence of numerous round, thin-walled air cysts on HRCT are characteristic features of Birt-Hogg-Dube syndrome.", "rejected": [{"label": "Lymphangioleiomy

## Backbone v0 (compact)
- S1 key_facts: 36-year-old woman; 7-day history of right-sided chest pain and dyspnea; No fever or cough; Two prior spontaneous pneumothoraces; Occasional small-volume hemoptysis; SpO2 97% on room air; Hypoventilation on right chest auscultation; Normal laboratory studies
- S2 mode=single k=1 pool_n=15 gold_in_s2=True
  - call1: ['Birt-Hogg-Dube syndrome', 'Lymphangioleiomyomatosis', 'Pneumocystis jirovecii pneumonia', 'Histoplasmosis', 'Coccidioi
- S3 shortlist n=5 gold=True: Birt-Hogg-Dube syndrome, Lymphangioleiomyomatosis, Ehlers-Danlos syndrome, Alpha-1 antitrypsin deficiency, Pulmonary Langerhans cell histiocytosis
- S4 champion: **Birt-Hogg-Dube syndrome** gold=False
- S4 raw (trunc): {"champion": "Birt-Hogg-Dube syndrome", "rationale": "The patient's history of recurrent spontaneous pneumothoraces and the presence of numerous round, thin-walled air cysts on HRCT are characteristic of Birt-Hogg-Dube syndrome, a genetic disorder that affects the lungs, skin, an

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's history of recurrent spontaneous pneumothoraces, presence of small air cysts on HRCT, and lack of other explanatory findings suggest a diagnosis o
  - turn1 gold_mention=True diag=
    The patient's recurrent spontaneous pneumothoraces and small air cysts on HRCT are consistent with Birt-Hogg-Dube syndrome, and the lack of other findings suppo
  - turn2 gold_mention=True diag=
    The patient's history of recurrent spontaneous pneumothoraces and presence of small air cysts on HRCT, along with the lack of other explanatory findings, suppor
- supervisor votes=3 top2=['Birt-Hogg-Dube syndrome', 'lymphangioleiomyomatosis'] gold=True

## Baseline B07
- draft=['Lymphangioleiomyomatosis (LAM)', 'Birt-Hogg-Dube syndrome'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['lymphangioleiomyomatosis diagnosis', 'pneumothorax causes', 'lung cysts differential diagnosis']
- diagnose=['Lymphangioleiomyomatosis (LAM)', 'Birt-Hogg-Dube syndrome'] gold=True

## Baseline B01
- queries=['recurrent spontaneous pneumothorax with bilateral small air cysts', 'differential diagnosis for multiple pneumothoraces in a young woman', 'HRCT findings of thin-walled air cysts in lungs', 'causes of recurrent pneumothorax with normal pulmonary function tests']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Lymphangioleiomyomatosis', 'Pulmonary Langerhans cell histiocytosis'] gold=True

