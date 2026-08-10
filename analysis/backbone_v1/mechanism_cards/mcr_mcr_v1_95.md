# MCR / mcr_v1 / case 95

- **gold**: Tuberculosis
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=0
- **e7_locus**: `s4_hit_judge_miss` · **e7_fail_code**: `s4_hit_judge_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=0

## Vignette
A 33-year-old man with known HIV/AIDS not on antiretroviral therapy (CD4 count <20 cells/µL), prior intravenous drug use, and active tobacco dependence was brought from his nursing home after abnormal laboratory results. He reported one month of poor appetite, weight loss, and subjective fevers, and several days of diarrhea without abdominal pain, vomiting, cough, or dyspnea. On examination, he was febrile (39.4 °C), hypotensive (91/60 mmHg, improved with IV fluids), tachycardic (130 bpm), and lethargic. Initial labs showed leukocytosis (31 151/µL) and hyponatremia (Na 121 mEq/L). A chest radiograph was clear. Abdominal ultrasound revealed hepatosplenomegaly, ascites, and enlarged peripancreatic lymph nodes. He was admitted to the ICU with presumed sepsis and started on vancomycin, piperacillin–tazobactam, and metronidazole. He then developed acute hypoxic respiratory failure and septic shock requiring intubation; post‐intubation chest radiograph showed new bilateral infiltrates. Blood cultures remained negative. Lumbar puncture demonstrated an opening pressure of 35 cm H₂O, 1825 RBCs/dL, 1 WBC/dL, glucose 65 mg/dL, and protein 36 mg/dL, and acyclovir was started empirically. Bronc…

## Backbone e7

- S2 n=55 gold_rank=1
  - clusters: gold=1 near=0 other=54
- S3 shortlist (5):
  - [gold] Disseminated tuberculosis
  - [other] Pneumocystis jirovecii pneumonia
  - [other] Cytomegalovirus infection
  - [other] Mycobacterium avium complex infection
  - [other] Cryptococcosis
    - why_kept(Disseminated tuberculosis): Patient has HIV/AIDS with CD4 count <20 cells/µL and symptoms consistent with TB, such as fever, weight loss, and hepatosplenomegaly
    - why_kept(Pneumocystis jirovecii pneumonia): Patient has HIV/AIDS with CD4 count <20 cells/µL and developed acute hypoxic respiratory failure, although initial sputum smears and BAL were negative
    - why_kept(Cytomegalovirus infection): Patient has HIV/AIDS with CD4 count <20 cells/µL and symptoms consistent with CMV, such as fever and hepatosplenomegaly
    - why_kept(Mycobacterium avium complex infection): Patient has HIV/AIDS with CD4 count <20 cells/µL and symptoms consistent with MAC, such as fever, weight loss, and hepatosplenomegaly
    - why_kept(Cryptococcosis): Patient has HIV/AIDS with CD4 count <20 cells/µL and symptoms consistent with cryptococcosis, such as fever, headache, and altered mental status
- S4 champion: **Disseminated tuberculosis** cluster=gold jaccard=0.50
- S4 rationale: The patient's symptoms of fever, weight loss, and poor appetite, combined with the findings of hepatosplenomegaly and enlarged peripancreatic lymph nodes on abdominal ultrasound, are consistent with disseminated tuberculosis, particularly in the context of a severely immunocompromised patient with HIV/AIDS and a history of intravenous drug use.
- S4 rejected:
  - [other] Pneumocystis jirovecii pneumonia: Bronchoalveolar lavage was negative for Pneumocystis jirovecii cultures
  - [other] Cytomegalovirus infection: No specific evidence of cytomegalovirus infection is presented in the case
  - [other] Mycobacterium avium complex infection: While possible in an immunocompromised patient, the clinical presentation and laboratory findings do not specifically suggest Mycobacterium avium complex infection over disseminated tuberculosis
  - [other] Cryptococcosis: The lumbar puncture findings, such as the high opening pressure and presence of RBCs, do not specifically indicate cryptococcal meningitis, and other findings are more suggestive of disseminated tuberculosis

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Disseminated tuberculosis', 'Cryptococcal meningitis']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Disseminated tuberculosis', 'Cryptococcal meningitis', 'Pneumocystis jirovecii pneumonia', 'Cytomegalovirus infection', 'Toxoplasmosis', 'Disseminated tuberculosis', 'Cryptococcal meningitis', 'Cytomegalovirus infection']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Disseminated Tuberculosis', 'Sepsis due to an opportunistic infection']
- diagnose: ['Disseminated Tuberculosis', 'Sepsis due to an opportunistic infection']
- queries: ['HIV/AIDS complications', 'sepsis in immunocompromised patients', 'causes of hepatosplenomegaly and ascites in HIV/AIDS', 'diagnosis of disseminated tuberculosis in HIV/AIDS']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Disseminated histoplasmosis', 'Pneumocystis jirovecii pneumonia']
- queries: ['HIV/AIDS opportunistic infections with hepatosplenomegaly and sepsis', 'causes of acute hypoxic respiratory failure in immunocompromised patients', 'differential diagnosis of fever, weight loss, and diarrhea in HIV/AIDS patients', 'diagnostic approach to septic shock with negative blood cultures in immunocompromised patients']
- n_chunks=12

## APHHM
- tree_n=27 final_n=1
- final: ['Disseminated Mycobacterium avium complex']
- tree gold_cluster_n=5 final gold=False

