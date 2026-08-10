# MCR / mcr_200b / case 374

- **gold**: cryptogenic organizing pneumonia
- **layer**: `e7_win_recall` · **layer_aphhm**: ``
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 56-year-old woman with no significant medical history presented with a 4-week history of dry cough and mild weight loss. She denied fever, haemoptysis, night sweats, and had no known contacts with tuberculosis. Two courses of antibiotics produced no improvement. On examination, coarse crepitations were heard over the right upper and lower lung zones. A chest radiograph showed an air-space opacity in the right upper lobe. CT of the thorax demonstrated multifocal consolidations in the right upper lobe extending to the right lower lobe. Given the clinical and radiographic suspicion for pulmonary tuberculosis, she was started empirically on anti-tuberculosis therapy. After 2 weeks, her symptoms persisted. A Mantoux tuberculin skin test showed 10 mm of induration. Sputum induction for acid-fast bacilli was negative, and bronchoalveolar lavage was negative for Xpert® Mycobacterium tuberculosis/rifampicin assay as well as bacterial and fungal cultures. Hence, a CT-guided lung biopsy was planned.

What is the most likely diagnosis?

Options:
A. cryptogenic organizing pneumonia
B. Pulmonary tuberculosis was considered given the upper
C. Bacterial and fungal pneumonia were considered but r…

## Backbone e7

- S2 n=53 gold_rank=15
  - clusters: gold=1 near=8 other=44
- S3 shortlist (5):
  - [other] sarcoidosis
  - [other] lymphangitic carcinomatosis
  - [other] bronchoalveolar cell carcinoma
  - [gold] organizing pneumonia
  - [other] Wegener's granulomatosis
    - why_kept(sarcoidosis): persistent dry cough and weight loss with negative infectious workup
    - why_kept(lymphangitic carcinomatosis): persistent dry cough and weight loss with multifocal consolidations on CT
    - why_kept(bronchoalveolar cell carcinoma): persistent dry cough and weight loss with negative infectious workup and abnormal CT findings
    - why_kept(organizing pneumonia): persistent dry cough and weight loss with multifocal consolidations on CT and lack of response to antibiotics
    - why_kept(Wegener's granulomatosis): persistent dry cough and weight loss with negative infectious workup and possibility of systemic vasculitis
- S4 champion: **organizing pneumonia** cluster=gold jaccard=0.67
- S4 rationale: The patient's symptoms of dry cough and mild weight loss, lack of response to antibiotics, and radiographic findings of multifocal consolidations are consistent with organizing pneumonia. The negative tests for tuberculosis and other infections also support this diagnosis.
- S4 rejected:
  - [other] sarcoidosis: While possible, the lack of other systemic symptoms and the specific radiographic pattern make it less likely
  - [other] lymphangitic carcinomatosis: There is no mention of a known primary malignancy, making this diagnosis less likely
  - [other] bronchoalveolar cell carcinoma: The radiographic findings and clinical presentation do not strongly suggest a malignant process
  - [other] Wegener's granulomatosis: The absence of systemic symptoms such as fever, haemoptysis, and night sweats, and the lack of renal involvement make this diagnosis less likely

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Lung Cancer', 'Sarcoidosis']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Lung Cancer', 'Sarcoidosis', 'Pulmonary Tuberculosis', 'Cryptogenic Organizing Pneumonia', 'Idiopathic Pulmonary Fibrosis', 'Lung Cancer', 'Sarcoidosis', 'Cryptogenic Organizing Pneumonia']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Lung Cancer', 'Sarcoidosis']
- diagnose: ['Lung Cancer', 'Sarcoidosis']
- queries: ['differential diagnosis for persistent dry cough and weight loss', 'causes of multifocal consolidations on CT thorax', 'alternative diagnoses to pulmonary tuberculosis']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Sarcoidosis', 'Lipoid Pneumonia']
- queries: ['persistent dry cough and weight loss with negative tuberculosis tests', 'multifocal consolidations on CT thorax with negative acid-fast bacilli and cultures', 'differential diagnosis for persistent cough and lung opacities after negative tuberculosis workup', 'causes of air-space opacity in lung with negative infectious disease workup']
- n_chunks=12

## APHHM
_na_

