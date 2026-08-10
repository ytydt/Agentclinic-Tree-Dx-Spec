# MCR / mcr_v1 / case 11

- **gold**: Multisystem inflammatory syndrome in children
- **layer**: `base_win_recall`
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=1 APHHM=0
- **loci**: e7=`s2_miss` B06=`supervisor_hit_judge_miss` B07=`diagnose_ok` B01=`gen_ok` APHHM=`final_hit_judge_miss`
- **primary_locus**: e7=s2_miss; B07=diagnose_ok
- **covariates**: vig_words=473; gold_words=5; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: 骨干入口完全未召回；基线直接给出金标/近义。

## Vignette (trunc)
An 18-year-old African male with no prior medical history presented first with a 2-day history of tonsillitis and a new macular rash on his chest that extended to his arms. Three days later he developed abdominal cramping and multiple episodes of non-bloody, watery diarrhea without nausea or vomiting, along with fevers and joint pains in his wrists, elbows, and knees. Initial outpatient care included oral chlorhexidine, lozenges, and symptomatic treatment.  He was then seen at a local health fac...

## Backbone e7
- S1 key_facts: 18-year-old African male with no prior medical history; Presented with 2-day history of tonsillitis; Developed abdominal cramping and diarrhea 3 days later; Fever and joint pains in wrists, elbows, and knees; Initial outpatient care included oral chlorhexidine, lozenges, and symptomatic t; Received ceftriaxone, paracetamol, loperamide, and one dose of IV methylpredniso; Transferred to hospital with high fever, tachycardia, and confusion; Laboratory data showed elevated WBC, procalcitonin, CRP, and creatinine
- S2 mode=complement k=3 pool_n=65 gold_in_s2=False
  - call1: ['Streptococcal toxic shock syndrome', 'Kawasaki disease', 'Toxic epidermal necrolysis', 'Stevens-Johnson syndrome', 'He
  - call2: ["Adult-onset Still's disease", 'Burkholderia pseudomallei infection', 'Brucellosis', 'Cat-scratch disease', 'Cytokine r
  - call3: ['Acute rheumatic fever', 'Babesiosis', 'Capnocytophaga canimorsus infection', 'Coxsackievirus infection', 'Cytomegalovi
- S3 shortlist n=5 gold=False: Streptococcal toxic shock syndrome, Kawasaki disease, Hemophagocytic lymphohistiocytosis, Meningococcemia, Sepsis syndrome
- S4 champion: **Streptococcal toxic shock syndrome** gold=False
- S4 raw (trunc): {"champion": "Streptococcal toxic shock syndrome", "rationale": "The patient's presentation with tonsillitis, followed by abdominal cramping, diarrhea, fever, and joint pains, along with laboratory findings of elevated WBC, procalcitonin, CRP, and creatinine, and the development 

## Backbone v0 (compact)
- S1 key_facts: 18-year-old African male with no prior medical history; Presented with 2-day history of tonsillitis; Developed abdominal cramping and diarrhea 3 days later; Fever and joint pains in wrists, elbows, and knees; Initial treatment included oral chlorhexidine, lozenges, and symptomatic treatme; Received ceftriaxone, paracetamol, loperamide, and IV methylprednisolone; Deteriorated and transferred to hospital; Febrile, hypotensive, tachycardic, and hypoxemic on arrival
- S2 mode=None k=None pool_n=17 gold_in_s2=False
  - pool gold matches: []
  - pool head: Kawasaki disease, Stevens-Johnson syndrome, Toxic epidermal necrolysis, Acute rheumatic fever, Infective endocarditis, Meningococcemia, Rocky Mountain spotted fever, Ehrlichiosis
- S3 shortlist n=5 gold=False: Kawasaki disease, Meningococcemia, Hemophagocytic lymphohistiocytosis, Rickettsial disease, Brucellosis
- S4 champion: **Meningococcemia** gold=False
- S4 raw (trunc): {"champion": "Meningococcemia", "rationale": "The patient's rapid deterioration, high fever, rash, abdominal cramping, diarrhea, and laboratory findings such as elevated WBC, procalcitonin, and CRP, along with the presence of splenic and renal infarcts, are consistent with mening

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation with a macular rash, abdominal cramping, diarrhea, fevers, joint pains, and subsequent development of renal and cardiac involvement, 
  - turn1 gold_mention=True diag=
    The patient's complex presentation with multi-organ involvement and positive antiphospholipid antibody supports the initial differential diagnoses, with antipho
  - turn2 gold_mention=True diag=
    The patient's presentation and laboratory findings, including the positive beta2-glycoprotein IgA antiphospholipid antibody and low C3 and C4 levels, are consis
- supervisor votes=3 top2=['Antiphospholipid syndrome', 'Multisystem inflammatory syndrome'] gold=True

## Baseline B07
- draft=['Multisystem Inflammatory Syndrome', 'Antiphospholipid Syndrome (APS)'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['An 18-year-old African male with no prior medical history presented first with a 2-day history of tonsillitis and a new macular rash on his chest that extended to his arms. Three days later he developed abdominal cramping and multiple episodes of non-bloody, watery diarrhea witho', 'differential diagnosis An 18-year-old African male with no prior medical history presented first with a 2-day history of tonsillitis and a new macular rash on his chest that extended ', 'clinical manifestations diagnosis ut nausea or vomiting, along with fevers and joint pains in his wrists, elbows, and knees. Initial outpatient care included oral chlorhexidine, lozenges, and sy']
- diagnose=['Multisystem Inflammatory Syndrome', 'Antiphospholipid Syndrome (APS)'] gold=True

## Baseline B01
- queries=['macular rash and abdominal cramping and fever in a young adult', 'differential diagnosis of multisystem inflammatory syndrome', 'causes of dilated cardiomyopathy with renal and splenic infarcts', 'antiphospholipid syndrome vs medium-sized vessel vasculitis in a patient with low C3 and C4']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Multisystem Inflammatory Syndrome in Children (MIS-C)', 'Kawasaki Disease'] gold=True

## APHHM
- tree_n=16 tree_recall=True
- gold_leaf=B1.1:Multisystem Inflammatory Syndrome in Children parent=B1
- final_n=4 final_recall=True ranking=['Antiphospholipid syndrome', 'Systemic Lupus Erythematosus', 'Multisystem Inflammatory Syndrome in Children', 'Kawasaki Disease']
- human_at1=False fail_mode=final_ok

