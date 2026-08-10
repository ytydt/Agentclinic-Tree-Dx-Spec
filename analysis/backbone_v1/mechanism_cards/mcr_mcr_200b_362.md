# MCR / mcr_200b / case 362

- **gold**: Cryptococcal osteomyelitis
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
An 18-year-old man presented with 20 days of pain and swelling around his right scapula, which had been gradually increasing in size, and 2 days of fever. He had been receiving anti-tubercular therapy for presumed pulmonary tuberculosis for 6 months; the diagnosis had been based on cough, chest radiograph findings, and an elevated erythrocyte sedimentation rate, with negative sputum studies. Despite continued therapy, 3 days before presentation he developed swelling and pain of the left ankle with difficulty walking. Laboratory studies showed an erythrocyte sedimentation rate of 73 mm/h and a positive C-reactive protein level of 96 mg/L. Magnetic resonance imaging of the right shoulder and left ankle demonstrated findings consistent with osteomyelitis involving the scapula and the distal tibia. An aspiration of the scapular swelling was performed, and specimens were sent for culture, sensitivity testing, and histopathologic examination for possible multidrug-resistant tuberculosis.

What is the most likely diagnosis?

Options:
A. Cryptococcal osteomyelitis
B. because lesions persisted despite therapy
C. Tubercular osteomyelitis was the initial consideration given the patient’s hist…

## Backbone e7

- S2 n=51 gold_rank=None
  - clusters: gold=0 near=21 other=30
- S3 shortlist (5):
  - [near] Tuberculous osteomyelitis
  - [near] Chronic osteomyelitis
  - [near] Bacterial osteomyelitis
  - [other] Multidrug-resistant tuberculosis
  - [near] Chronic recurrent multifocal osteomyelitis
    - why_kept(Tuberculous osteomyelitis): Patient is receiving anti-tubercular therapy and has findings consistent with osteomyelitis, suggesting possible spread of tuberculosis to the bones
    - why_kept(Chronic osteomyelitis): Magnetic resonance imaging findings consistent with osteomyelitis involving the scapula and the distal tibia, and patient has been experiencing pain and swelling for 20 days
    - why_kept(Bacterial osteomyelitis): Patient has systemic symptoms such as fever and elevated erythrocyte sedimentation rate, which could indicate a bacterial infection
    - why_kept(Multidrug-resistant tuberculosis): Patient has been receiving anti-tubercular therapy for 6 months but still has active disease, raising the possibility of multidrug-resistant tuberculosis
    - why_kept(Chronic recurrent multifocal osteomyelitis): Patient has multiple sites of osteomyelitis and a prolonged course of disease, which could suggest a chronic recurrent condition
- S4 champion: **Tuberculous osteomyelitis** cluster=near jaccard=0.33
- S4 rationale: The patient's history of receiving anti-tubercular therapy for presumed pulmonary tuberculosis and the development of osteomyelitis involving the scapula and the distal tibia, as shown by magnetic resonance imaging, support this diagnosis.
- S4 rejected:
  - [near] Chronic osteomyelitis: Lack of specific evidence for a chronic infection other than tuberculosis
  - [near] Bacterial osteomyelitis: The patient's context and treatment history suggest a tuberculous rather than a typical bacterial etiology
  - [other] Multidrug-resistant tuberculosis: While the patient is on anti-tubercular therapy, there's no direct evidence provided for multidrug resistance in this context
  - [near] Chronic recurrent multifocal osteomyelitis: The patient's presentation and history are more consistent with a tuberculous infection rather than a recurrent multifocal osteomyelitis

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Multidrug-resistant tuberculosis', 'Osteomyelitis']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Osteomyelitis', 'Multidrug-resistant tuberculosis', 'Chronic osteomyelitis', 'Skeletal tuberculosis', 'Pyogenic osteomyelitis', 'Multidrug-resistant tuberculosis', 'Osteomyelitis', 'Skeletal tuberculosis']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Osteomyelitis due to tuberculosis', 'Multidrug-resistant tuberculosis']
- diagnose: ['Osteomyelitis due to tuberculosis', 'Multidrug-resistant tuberculosis']
- queries: ['osteomyelitis causes', 'tuberculosis osteomyelitis', 'multidrug-resistant tuberculosis symptoms']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['Tuberculous osteomyelitis', 'Multidrug-resistant tuberculosis']
- queries: ['osteomyelitis causes in young adults', 'tuberculosis osteomyelitis diagnosis', 'multidrug-resistant tuberculosis treatment failure', 'differential diagnosis of scapular swelling and fever']
- n_chunks=12

## APHHM
_na_

