# MCR / mcr_200b / case 249

- **gold**: Organizing pneumonia
- **layer**: `base_win_recall` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=0 APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=1 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 36-year-old man with end-stage renal disease secondary to IgA nephropathy underwent a live-related renal transplant 6 months ago and has been maintained on tacrolimus 3.5 mg daily, mycophenolate sodium 720 mg daily, and prednisolone 7.5 mg daily. He presented with a 14-day history of low-grade fever, dry cough, and anorexia without dyspnea, chest pain, hemoptysis, or weight loss. He was afebrile on admission, heart rate 88 beats/min, blood pressure 122/76 mm Hg, respiratory rate 28 breaths/min, and oxygen saturation 95% on room air. Examination revealed bilateral inspiratory crackles; other findings were unremarkable.

Laboratory studies showed hemoglobin 14.6 g/dL; total lymphocyte count 9900/μL; absolute neutrophil count 7720/μL; platelets 285 000/μL; serum creatinine 1.05 mg/dL. Arterial blood gas analysis demonstrated PaO₂ 68 mm Hg and an A–a gradient of 22 mm Hg. HIV ELISA was negative. Chest radiograph revealed bilateral diffuse alveolar infiltrates. High-resolution CT of the chest showed bilateral diffuse ground-glass opacities without pleural or mediastinal abnormalities.

Sputum induction was non-diagnostic. Bronchoalveolar lavage (BAL) fluid was positive for Pneumocysti…

## Backbone e7

- S2 n=54 gold_rank=None
  - clusters: gold=0 near=21 other=33
- S3 shortlist (5):
  - [near] Pneumocystis jirovecii pneumonia
  - [near] Cytomegalovirus pneumonia
  - [other] Invasive aspergillosis
  - [other] Nocardiosis
  - [near] Idiopathic pneumonia syndrome
    - why_kept(Pneumocystis jirovecii pneumonia): Confirmed by BAL fluid positive for Pneumocystis jirovecii
    - why_kept(Cytomegalovirus pneumonia): Immunocompromised patient with history of renal transplant, CMV a common opportunistic infection
    - why_kept(Invasive aspergillosis): Immunocompromised patient with history of renal transplant, Aspergillosis a common opportunistic infection
    - why_kept(Nocardiosis): Immunocompromised patient with history of renal transplant, Nocardia a common opportunistic infection
    - why_kept(Idiopathic pneumonia syndrome): Clinical presentation and radiographic findings consistent with idiopathic pneumonia syndrome
- S4 champion: **Pneumocystis jirovecii pneumonia** cluster=near jaccard=0.25
- S4 rationale: The patient's BAL fluid was positive for Pneumocystis jirovecii on Grocott’s methenamine silver stain, and he responded to treatment with trimethoprim-sulfamethoxazole and a prednisone taper, which is consistent with Pneumocystis jirovecii pneumonia
- S4 rejected:
  - [near] Cytomegalovirus pneumonia: CMV inclusion bodies were not found in the BAL fluid
  - [other] Invasive aspergillosis: Fungal hyphae were not found in the BAL fluid
  - [other] Nocardiosis: There is no mention of Nocardia species in the patient's laboratory results
  - [near] Idiopathic pneumonia syndrome: The patient's pneumonia was found to have a specific cause, Pneumocystis jirovecii, making idiopathic pneumonia syndrome less likely

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Bronchiolitis obliterans syndrome', 'Acute rejection']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Pneumocystis jirovecii pneumonia', 'Bronchiolitis obliterans syndrome', 'Acute rejection', 'Cytomegalovirus pneumonia', 'Tacrolimus-induced pneumonitis', 'Bronchiolitis obliterans syndrome', 'Acute rejection', 'Tacrolimus-induced pneumonitis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Bronchiolitis Obliterans Organizing Pneumonia (BOOP)', 'Pneumocystis jirovecii Pneumonia (PCP)']
- diagnose: ['Bronchiolitis Obliterans Organizing Pneumonia (BOOP)', 'Pneumocystis jirovecii Pneumonia (PCP)']
- queries: ['A 36-year-old man with end-stage renal disease secondary to IgA nephropathy underwent a live-related renal transplant 6 months ago and has been maintained on tacrolimus 3.5 mg daily, mycophenolate sod', 'differential diagnosis A 36-year-old man with end-stage renal disease secondary to IgA nephropathy underwent a live-related renal transplant 6 months ago and has been maintained on tacrolimus 3.5 mg daily, mycophenolate sod', 'clinical manifestations diagnosis /μL; platelets 285 000/μL; serum creatinine 1.05 mg/dL. Arterial blood gas analysis demonstrated PaO₂ 68 mm Hg and an A–a gradient of 22 mm Hg. HIV ELISA was ne']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['Pneumocystis jirovecii pneumonia', 'Trimethoprim-sulfamethoxazole-induced leukopenia']
- queries: ['immunosuppressed patient with bilateral diffuse alveolar infiltrates', 'Pneumocystis jirovecii pneumonia treatment failure', 'leukopenia after trimethoprim-sulfamethoxazole discontinuation', 'transbronchial lung biopsy findings in immunocompromised patients']
- n_chunks=12

## APHHM
_na_

