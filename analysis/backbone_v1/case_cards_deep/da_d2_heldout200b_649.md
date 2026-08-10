# DA / d2_heldout200b / case 649

- **gold**: Severe COVID-19 pneumonia with ARDS in pregnancy requiring V-V ECMO support
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=
- **loci**: e7=`s2_hit_s3_drop` B06=`supervisor_ok` B07=`diagnose_ok` B01=`na` APHHM=`na`
- **primary_locus**: e7=s2_hit_s3_drop; B06=supervisor_ok
- **covariates**: vig_words=173; gold_words=13; eponym=False; subtype=True; e7_s2_rank=4; mapper_rescue=False
- **causal**: 骨干 S2 已召回，S3 短表丢掉金标。

## Vignette (trunc)
A 38-year-old pregnant patient at 27 weeks and 2 days gestation presented with 1 day of decreased fetal movement following 1 week of dyspnea, cough, chest pain, and headache. Medical history included type 2 diabetes mellitus, mild intermittent asthma, obesity (BMI 40 kg/m²), and 3 uncomplicated vaginal births. Patient had declined SARS-CoV-2 vaccination earlier in pregnancy.  Patient was normotensive. Fetal monitoring was reassuring.  - Laboratory Tests (Initial):  - Thrombocytopenia and mild tr...

## Options
  - A: Severe COVID-19 pneumonia with ARDS in pregnancy requiring V-V ECMO support
  - B: Community-acquired pneumonia
  - C: Acute viral pneumonia (non-COVID)
  - D: COVID-19 pneumonia with respiratory failure

## Backbone e7
- S1 key_facts: Patient is 27 weeks and 2 days pregnant; Patient has type 2 diabetes mellitus; Patient has mild intermittent asthma; Patient is obese with a BMI of 40 kg/m²; Patient has had 3 uncomplicated vaginal births; Patient declined SARS-CoV-2 vaccination; Patient is normotensive; Fetal monitoring is reassuring
- S2 mode=complement k=3 pool_n=48 gold_in_s2=True
  - call1: ['Amniotic fluid embolism', 'Pulmonary thromboembolism', 'Acute respiratory distress syndrome', 'Pneumonia', 'Influenza 
  - call2: ['Churg-Strauss syndrome', "Wegener's granulomatosis", 'Microangiopathic hemolytic anemia', 'Thrombotic microangiopathy'
  - call3: ['Hughes-Stovin syndrome', "Behcet's disease", "Sneddon's syndrome", 'Lupus anticoagulant hypoprothrombinemia syndrome',
- S3 shortlist n=5 gold=False: Pulmonary thromboembolism, Pulmonary embolism with thrombophilic disorder, Amniotic fluid embolism, Disseminated intravascular coagulation, HELLP syndrome
- S4 champion: **Pulmonary embolism with thrombophilic disorder** gold=False
- S4 raw (trunc): {"champion": "Pulmonary embolism with thrombophilic disorder", "rationale": "The patient's presentation with dyspnea, cough, chest pain, and headache, along with a significantly elevated D-dimer level (752 µg/mL) and thrombocytopenia, suggests a pulmonary embolism. The patient's 

## Backbone v0 (compact)
- S1 key_facts: 27 weeks and 2 days gestation; 1 day of decreased fetal movement; 1 week of dyspnea, cough, chest pain, and headache; Type 2 diabetes mellitus; Mild intermittent asthma; Obesity (BMI 40 kg/m²); 3 uncomplicated vaginal births; Declined SARS-CoV-2 vaccination
- S2 mode=single k=1 pool_n=18 gold_in_s2=False
  - call1: ['Amniotic fluid embolism', 'Pulmonary thromboembolism', 'Acute respiratory distress syndrome', 'SARS-CoV-2 pneumonia', 
- S3 shortlist n=5 gold=False: Pulmonary thromboembolism, Amniotic fluid embolism, SARS-CoV-2 pneumonia, Pulmonary embolism with thrombophilic disorder, Acute respiratory distress syndrome
- S4 champion: **Pulmonary thromboembolism** gold=False
- S4 raw (trunc): {"champion": "Pulmonary thromboembolism", "rationale": "The patient's symptoms of dyspnea, cough, chest pain, and headache, combined with laboratory findings of thrombocytopenia, mild transaminitis, and an elevated D-dimer, are consistent with pulmonary thromboembolism. The prese

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    Given the patient's symptoms of dyspnea, cough, chest pain, and headache, along with laboratory findings of thrombocytopenia, mild transaminitis, and elevated D
  - turn1 gold_mention=True diag=
    The patient's presentation of decreased fetal movement, dyspnea, cough, chest pain, and headache, combined with laboratory findings and imaging studies, aligns 
  - turn2 gold_mention=True diag=
    The patient's symptoms and laboratory findings, including thrombocytopenia, mild transaminitis, and elevated D-dimer, along with the use of ECMO and the presenc
- supervisor votes=3 top2=['Pulmonary Embolism', 'COVID-19 Pneumonia'] gold=True

## Baseline B07
- draft=['COVID-19 pneumonia', 'Pulmonary embolism'] gold=True
- has_refine=True refine=[] gold=None
- queries(4): ['pregnancy complications with thrombocytopenia and transaminitis', 'COVID-19 in pregnancy with decreased fetal movement', 'dyspnea and chest pain in pregnancy', 'ECMO therapy in pregnancy']
- diagnose=['COVID-19 pneumonia', 'Pulmonary embolism'] gold=True

