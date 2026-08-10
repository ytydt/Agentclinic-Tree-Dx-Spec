# MCR / mcr_v1 / case 11

- **gold**: Multisystem inflammatory syndrome in children
- **layer**: `base_win_recall` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=1 APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`final_hit_judge_miss` code=`aphhm_judge_miss` prune_e7_ok=0

## Vignette
An 18-year-old African male with no prior medical history presented first with a 2-day history of tonsillitis and a new macular rash on his chest that extended to his arms. Three days later he developed abdominal cramping and multiple episodes of non-bloody, watery diarrhea without nausea or vomiting, along with fevers and joint pains in his wrists, elbows, and knees. Initial outpatient care included oral chlorhexidine, lozenges, and symptomatic treatment.

He was then seen at a local health facility with high fever, tachycardia, and within 24 hours became confused with rising serum creatinine (from 200 to 400 μmol/L). He received ceftriaxone, paracetamol, loperamide, and one dose of IV methylprednisolone, but continued to deteriorate and was transferred to our hospital.

On arrival he was febrile (40°C), hypotensive (70/40 mmHg), tachycardic (130 bpm), tachypneic (50 breaths/min), and hypoxemic (SaO2 86% on room air). GCS was 14/15. Lung exam revealed bilaterally coarse crepitations; cardiovascular exam an audible S3 gallop; abdomen distended and tense with hypoactive bowel sounds; musculoskeletal exam was normal. He received fluid resuscitation, central line placement, and norepi…

## Backbone e7

- S2 n=65 gold_rank=None
  - clusters: gold=0 near=9 other=56
- S3 shortlist (5):
  - [near] Streptococcal toxic shock syndrome
  - [other] Kawasaki disease
  - [other] Hemophagocytic lymphohistiocytosis
  - [other] Meningococcemia
  - [near] Sepsis syndrome
    - why_kept(Streptococcal toxic shock syndrome): Patient presented with fever, rash, and multisystem involvement, consistent with toxic shock syndrome
    - why_kept(Kawasaki disease): Patient's symptoms, including fever, rash, and cardiovascular involvement, are consistent with Kawasaki disease
    - why_kept(Hemophagocytic lymphohistiocytosis): Patient's laboratory results, including elevated ferritin and triglycerides, are consistent with hemophagocytic lymphohistiocytosis
    - why_kept(Meningococcemia): Patient presented with fever, rash, and multisystem involvement, consistent with meningococcemia
    - why_kept(Sepsis syndrome): Patient's symptoms, including fever, hypotension, and multisystem involvement, are consistent with sepsis syndrome
- S4 champion: **Streptococcal toxic shock syndrome** cluster=near jaccard=0.14
- S4 rationale: The patient's presentation with tonsillitis, followed by abdominal cramping, diarrhea, fever, and joint pains, along with laboratory findings of elevated WBC, procalcitonin, CRP, and creatinine, and the development of shock, renal failure, and cardiac dysfunction, are consistent with streptococcal toxic shock syndrome.
- S4 rejected:
  - [other] Kawasaki disease: The patient's age and lack of typical Kawasaki disease features, such as conjunctivitis and lymphadenopathy, make this diagnosis less likely.
  - [other] Hemophagocytic lymphohistiocytosis: While the patient has elevated liver enzymes and coagulopathy, the primary presentation and laboratory findings do not strongly support this diagnosis.
  - [other] Meningococcemia: The patient's symptoms and laboratory findings do not suggest meningococcal infection, and the absence of a rash typical of meningococcemia makes this diagnosis unlikely.
  - [near] Sepsis syndrome: While the patient is septic, the specific constellation of symptoms and laboratory findings points towards a more specific diagnosis, such as streptococcal toxic shock syndrome, rather than a general diagnosis of sepsis syndrome.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Antiphospholipid syndrome', 'Multisystem inflammatory syndrome']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Antiphospholipid syndrome', 'Multisystem inflammatory syndrome', 'Vasculitis', 'Sepsis', 'Systemic lupus erythematosus', 'Antiphospholipid syndrome', 'Multisystem inflammatory syndrome', 'Vasculitis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Multisystem Inflammatory Syndrome', 'Antiphospholipid Syndrome (APS)']
- diagnose: ['Multisystem Inflammatory Syndrome', 'Antiphospholipid Syndrome (APS)']
- queries: ['An 18-year-old African male with no prior medical history presented first with a 2-day history of tonsillitis and a new macular rash on his chest that extended to his arms. Three days later he developed abdominal cramping and multiple episodes of non-bloody, watery diarrhea witho', 'differential diagnosis An 18-year-old African male with no prior medical history presented first with a 2-day history of tonsillitis and a new macular rash on his chest that extended ', 'clinical manifestations diagnosis ut nausea or vomiting, along with fevers and joint pains in his wrists, elbows, and knees. Initial outpatient care included oral chlorhexidine, lozenges, and sy']

## B01 (code=`b01_ok` locus=`gen_ok`)
- top2: ['Multisystem Inflammatory Syndrome in Children (MIS-C)', 'Kawasaki Disease']
- queries: ['macular rash and abdominal cramping and fever in a young adult', 'differential diagnosis of multisystem inflammatory syndrome', 'causes of dilated cardiomyopathy with renal and splenic infarcts', 'antiphospholipid syndrome vs medium-sized vessel vasculitis in a patient with low C3 and C4']
- n_chunks=12

## APHHM
- tree_n=16 final_n=4
- final: ['Antiphospholipid syndrome', 'Systemic Lupus Erythematosus', 'Multisystem Inflammatory Syndrome in Children', 'Kawasaki Disease']
- tree gold_cluster_n=4 final gold=True

