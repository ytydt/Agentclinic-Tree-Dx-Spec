# MCR / mcr_200b / case 249

- **gold**: Organizing pneumonia
- **layer**: `base_win_recall`
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=0 APHHM=
- **loci**: e7=`s2_miss` B06=`agents_hit_supervisor_drop` B07=`diagnose_ok` B01=`rag_hit_gen_miss` APHHM=`na`
- **primary_locus**: e7=s2_miss; B07=diagnose_ok
- **covariates**: vig_words=362; gold_words=2; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: 骨干入口完全未召回；基线直接给出金标/近义。

## Vignette (trunc)
A 36-year-old man with end-stage renal disease secondary to IgA nephropathy underwent a live-related renal transplant 6 months ago and has been maintained on tacrolimus 3.5 mg daily, mycophenolate sodium 720 mg daily, and prednisolone 7.5 mg daily. He presented with a 14-day history of low-grade fever, dry cough, and anorexia without dyspnea, chest pain, hemoptysis, or weight loss. He was afebrile on admission, heart rate 88 beats/min, blood pressure 122/76 mm Hg, respiratory rate 28 breaths/min...

## Backbone e7
- S1 key_facts: 36-year-old man with end-stage renal disease secondary to IgA nephropathy; Underwent live-related renal transplant 6 months ago; Maintained on tacrolimus 3.5 mg daily, mycophenolate sodium 720 mg daily, and pr; Presented with a 14-day history of low-grade fever, dry cough, and anorexia; Afebrile on admission with heart rate 88 beats/min, blood pressure 122/76 mm Hg,; Bilateral inspiratory crackles on examination; Hemoglobin 14.6 g/dL, total lymphocyte count 9900/μL, absolute neutrophil count ; Arterial blood gas analysis demonstrated PaO₂ 68 mm Hg and an A–a gradient of 22
- S2 mode=complement k=3 pool_n=54 gold_in_s2=False
  - call1: ['Pneumocystis jirovecii pneumonia', 'Cytomegalovirus pneumonia', 'Invasive aspergillosis', 'Candida pneumonia', 'Histop
  - call2: ['Mucormycosis', 'Fusariosis', 'Scedosporiosis', 'Trichosporonosis', 'Pulmonary alveolar proteinosis', 'Lymphomatoid gra
  - call3: ['Rhinovirus pneumonia', 'Coronavirus pneumonia', 'Human metapneumovirus pneumonia', 'Parainfluenza virus pneumonia', 'H
- S3 shortlist n=5 gold=False: Pneumocystis jirovecii pneumonia, Cytomegalovirus pneumonia, Invasive aspergillosis, Nocardiosis, Idiopathic pneumonia syndrome
- S4 champion: **Pneumocystis jirovecii pneumonia** gold=False
- S4 raw (trunc): {"champion": "Pneumocystis jirovecii pneumonia", "rationale": "The patient's BAL fluid was positive for Pneumocystis jirovecii on Grocott’s methenamine silver stain, and he responded to treatment with trimethoprim-sulfamethoxazole and a prednisone taper, which is consistent with 

## Backbone v0 (compact)
- S1 key_facts: 36-year-old man with end-stage renal disease secondary to IgA nephropathy; Underwent live-related renal transplant 6 months ago; Maintained on tacrolimus, mycophenolate sodium, and prednisolone; Presented with 14-day history of low-grade fever, dry cough, and anorexia; Afebrile on admission with heart rate 88 beats/min and blood pressure 122/76 mm ; Respiratory rate 28 breaths/min and oxygen saturation 95% on room air; Bilateral inspiratory crackles on examination; Hemoglobin 14.6 g/dL, total lymphocyte count 9900/μL, and absolute neutrophil co
- S2 mode=single k=1 pool_n=21 gold_in_s2=False
  - call1: ['Pneumocystis jirovecii pneumonia', 'Cytomegalovirus pneumonia', 'Invasive aspergillosis', 'Candida pneumonia', 'Histop
- S3 shortlist n=5 gold=False: Pneumocystis jirovecii pneumonia, Cytomegalovirus pneumonia, Invasive aspergillosis, Idiopathic pneumonia syndrome, Pulmonary nocardiosis
- S4 champion: **Pneumocystis jirovecii pneumonia** gold=False
- S4 raw (trunc): {"champion": "Pneumocystis jirovecii pneumonia", "rationale": "The patient's diagnosis is supported by the presence of Pneumocystis jirovecii in the bronchoalveolar lavage fluid, which is a definitive diagnostic finding, and the clinical and radiographic resolution of infiltrates

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's history of low-grade fever, dry cough, and anorexia, along with bilateral inspiratory crackles and diffuse alveolar infiltrates on chest radiograp
  - turn1 gold_mention=True diag=
    The patient's initial response to treatment for Pneumocystis jirovecii pneumonia, followed by the development of new symptoms and radiographic findings after di
  - turn2 gold_mention=True diag=
    The patient's clinical presentation, radiographic findings, and histopathological results from the transbronchial lung biopsy, along with the discussion from Do
- supervisor votes=3 top2=['Bronchiolitis obliterans syndrome', 'Acute rejection'] gold=False

## Baseline B07
- draft=['Bronchiolitis Obliterans Organizing Pneumonia (BOOP)', 'Pneumocystis jirovecii Pneumonia (PCP)'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['A 36-year-old man with end-stage renal disease secondary to IgA nephropathy underwent a live-related renal transplant 6 months ago and has been maintained on tacrolimus 3.5 mg daily, mycophenolate sod', 'differential diagnosis A 36-year-old man with end-stage renal disease secondary to IgA nephropathy underwent a live-related renal transplant 6 months ago and has been maintained on tacrolimus 3.5 mg daily, mycophenolate sod', 'clinical manifestations diagnosis /μL; platelets 285 000/μL; serum creatinine 1.05 mg/dL. Arterial blood gas analysis demonstrated PaO₂ 68 mm Hg and an A–a gradient of 22 mm Hg. HIV ELISA was ne']
- diagnose=['Bronchiolitis Obliterans Organizing Pneumonia (BOOP)', 'Pneumocystis jirovecii Pneumonia (PCP)'] gold=True

## Baseline B01
- queries=['immunosuppressed patient with bilateral diffuse alveolar infiltrates', 'Pneumocystis jirovecii pneumonia treatment failure', 'leukopenia after trimethoprim-sulfamethoxazole discontinuation', 'transbronchial lung biopsy findings in immunocompromised patients']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Pneumocystis jirovecii pneumonia', 'Trimethoprim-sulfamethoxazole-induced leukopenia'] gold=False

