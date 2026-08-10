# MCR / mcr_v1 / case 117

- **gold**: Antiphospholipid syndrome
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=0 B06=1 B07=1 B01=1 APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A 43-year-old man with no significant medical history presented in December with a 4-day history of fever to 38.8 °C, shaking chills, hemoptysis, and worsening dyspnea. He reported several months of intermittent night sweats, arthralgias of the wrists and ankles, and a 10-kg weight loss. One day before admission, he noted a painful ecchymotic lesion on his left calf; over the next 24 hours, similar lesions appeared on his abdomen, back, right upper arm, and right calf. His 3-year-old son had recently had a respiratory illness. On examination, temperature was 35.3 °C, blood pressure 117/75 mmHg, pulse 112 beats/min, respiratory rate 29 breaths/min, and oxygen saturation 96% on room air. Bilateral wheezes were present, and there were multiple painful ecchymoses with hemorrhagic bullae over the trunk and extremities. Laboratory studies showed a WBC count of 9000/mm3 (87% neutrophils), hemoglobin 13.4 g/dL, normal renal and liver function, lactate dehydrogenase 799 IU/L, erythrocyte sedimentation rate 81 mm/h, and C-reactive protein 38.5 mg/dL. Chest radiography and CT demonstrated multifocal alveolar infiltrates, and CT angiography showed no pulmonary embolism. Empiric intravenous cef…

## Backbone e7

- S2 n=53 gold_rank=None
  - clusters: gold=0 near=8 other=45
- S3 shortlist (5):
  - [gold] Antiphospholipid syndrome
  - [other] Leukocytoclastic vasculitis
  - [other] Granulomatosis with polyangiitis
  - [other] Eosinophilic granuloma with polyangiitis
  - [other] Henoch-Schönlein purpura
    - why_kept(Antiphospholipid syndrome): Positive lupus anticoagulant, anticardiolipin IgM, and anti-phosphatidylserine IgM
    - why_kept(Leukocytoclastic vasculitis): Skin biopsy showing superficial and deep dermal thrombotic paucicellular vasculopathy
    - why_kept(Granulomatosis with polyangiitis): Respiratory and renal involvement, elevated erythrocyte sedimentation rate
    - why_kept(Eosinophilic granuloma with polyangiitis): Respiratory symptoms, elevated lactate dehydrogenase, and eosinophilic pneumonia possibility
    - why_kept(Henoch-Schönlein purpura): Palpable purpura, arthralgias, and abdominal involvement
- S4 champion: **Antiphospholipid syndrome** cluster=gold jaccard=1.00
- S4 rationale: The patient's presentation with fever, weight loss, and multiple painful ecchymoses with hemorrhagic bullae, along with laboratory findings of thrombotic paucicellular vasculopathy and positive tests for lupus anticoagulant, anticardiolipin IgM, and anti-phosphatidylserine IgM, are consistent with antiphospholipid syndrome.
- S4 rejected:
  - [other] Leukocytoclastic vasculitis: The biopsy showed paucicellular vasculopathy without significant neutrophils or leukocytoclasia, which is not typical of leukocytoclastic vasculitis.
  - [other] Granulomatosis with polyangiitis: The patient's presentation and laboratory findings do not suggest granulomatous inflammation or the presence of anti-neutrophil cytoplasmic antibodies, which are characteristic of granulomatosis with polyangiitis.
  - [other] Eosinophilic granuloma with polyangiitis: There is no evidence of eosinophilia or granulomatous inflammation in the patient's presentation or laboratory findings, making this diagnosis unlikely.
  - [other] Henoch-Schönlein purpura: The patient's age and the presence of systemic symptoms such as fever, weight loss, and arthralgias, as well as the laboratory findings, are not typical of Henoch-Schönlein purpura, which is more commonly seen in children and young adults with palpable purpura and abdominal pain.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Antiphospholipid syndrome', 'Infectious mononucleosis due to Epstein-Barr virus']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Antiphospholipid syndrome', 'Vasculitis', 'Infectious mononucleosis due to Epstein-Barr virus', 'Respiratory syncytial virus pneumonia', 'Systemic lupus erythematosus', 'Antiphospholipid syndrome', 'Infectious mononucleosis due to Epstein-Barr virus', 'Respiratory syncytial virus pneumonia']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Antiphospholipid Syndrome', 'Respiratory Syncytial Virus Infection']
- diagnose: ['Antiphospholipid Syndrome', 'Respiratory Syncytial Virus Infection']
- queries: ['antiphospholipid syndrome diagnosis', 'respiratory syncytial virus in adults', 'thrombotic paucicellular vasculopathy', 'lupus anticoagulant positive diagnosis']

## B01 (code=`b01_ok` locus=`gen_ok`)
- top2: ['Antiphospholipid syndrome', 'Respiratory syncytial virus pneumonia']
- queries: ['fever and hemoptysis with skin lesions and thrombotic vasculopathy', 'community-acquired pneumonia with negative bacterial tests and positive respiratory syncytial virus', 'systemic symptoms with positive lupus anticoagulant and anticardiolipin IgM', 'respiratory illness with multifocal alveolar infiltrates and negative CT angiography for pulmonary embolism']
- n_chunks=12

## APHHM
- tree_n=83 final_n=3
- final: ['Cryoglobulinemic vasculitis', 'Systemic Lupus Erythematosus', 'Hemophagocytic lymphohistiocytosis']
- tree gold_cluster_n=0 final gold=False

