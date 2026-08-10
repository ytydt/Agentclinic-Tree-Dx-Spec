# DA / d2_heldout200b / case 649

- **gold**: Severe COVID-19 pneumonia with ARDS in pregnancy requiring V-V ECMO support
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_near_crowd_out`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 38-year-old pregnant patient at 27 weeks and 2 days gestation presented with 1 day of decreased fetal movement following 1 week of dyspnea, cough, chest pain, and headache. Medical history included type 2 diabetes mellitus, mild intermittent asthma, obesity (BMI 40 kg/m²), and 3 uncomplicated vaginal births. Patient had declined SARS-CoV-2 vaccination earlier in pregnancy.

Patient was normotensive. Fetal monitoring was reassuring.

- Laboratory Tests (Initial):  - Thrombocytopenia and mild transaminitis noted  - Hemoglobin: 15.3 g/dL   - WBC count: 5300/µL  - Platelet count: 129 x10³/µL  - Creatinine: 0.70 mg/dL  - AST: 77 U/L  - ALT: 58 U/L  - Procalcitonin: 0.8 ng/dL  - D-dimer: 752 µg/mL- Imaging Studies:  Image Title: Posteroanterior chest radiograph (Admission)  Image Title: Anteroposterior chest radiograph (Hospital day 8)  Image Title: Post-ECMO cannula removal image  Image Description: Tubular clot affixed to the distal ECMO drainage cannula (29F)

What is the most likely diagnosis?

Options:
A. Severe COVID-19 pneumonia with ARDS in pregnancy requiring V-V ECMO support
B. Community-acquired pneumonia
C. Acute viral pneumonia (non-COVID)
D. COVID-19 pneumonia with respir…

## Options
- A: Severe COVID-19 pneumonia with ARDS in pregnancy requiring V-V ECMO support **←gold**
- B: Community-acquired pneumonia
- C: Acute viral pneumonia (non-COVID)
- D: COVID-19 pneumonia with respiratory failure

## Backbone e7

- S2 n=48 gold_rank=4
  - clusters: gold=2 near=5 other=41
- S3 shortlist (5):
  - [other] Pulmonary thromboembolism
  - [other] Pulmonary embolism with thrombophilic disorder
  - [other] Amniotic fluid embolism
  - [other] Disseminated intravascular coagulation
  - [other] HELLP syndrome
    - why_kept(Pulmonary thromboembolism): Elevated D-dimer and thrombocytopenia suggest thrombotic event
    - why_kept(Pulmonary embolism with thrombophilic disorder): Patient's obesity and pregnancy increase thrombophilic risk
    - why_kept(Amniotic fluid embolism): Decreased fetal movement and respiratory symptoms are consistent with this diagnosis
    - why_kept(Disseminated intravascular coagulation): Thrombocytopenia, transaminitis, and elevated D-dimer are indicative of coagulopathy
    - why_kept(HELLP syndrome): Patient's symptoms and lab results, including thrombocytopenia and transaminitis, are consistent with this pregnancy-related complication
- S4 champion: **Pulmonary embolism with thrombophilic disorder** cluster=other jaccard=0.08
- S4 rationale: The patient's presentation with dyspnea, cough, chest pain, and headache, along with a significantly elevated D-dimer level (752 µg/mL) and thrombocytopenia, suggests a pulmonary embolism. The patient's obesity (BMI 40 kg/m²) and history of declining SARS-CoV-2 vaccination increase the risk of thromboembolic events, supporting the diagnosis of pulmonary embolism with a thrombophilic disorder.
- S4 rejected:
  - [other] Pulmonary thromboembolism: While this diagnosis is close, the presence of thrombophilic risk factors (obesity, pregnancy, and possibly COVID-19 infection risk due to vaccination decline) makes 'Pulmonary embolism with thrombophilic disorder' a more comprehensive explanation.
  - [other] Amniotic fluid embolism: This condition typically presents with sudden onset of hypotension, hypoxia, and often cardiac arrest, which does not match the patient's normotensive state and reassuring fetal monitoring.
  - [other] Disseminated intravascular coagulation: Although the patient has thrombocytopenia and elevated D-dimer, the lack of more widespread coagulopathy signs (e.g., significant bleeding, more pronounced laboratory abnormalities) makes this diagnosis less likely.
  - [other] HELLP syndrome: The patient's presentation and laboratory results (e.g., mild transaminitis) do not strongly support HELLP syndrome, which is characterized by hemolysis, elevated liver enzymes, and low platelet count, typically in the context of preeclampsia (which the patient does not have, being normotensive).

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Pulmonary Embolism', 'COVID-19 Pneumonia']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Pulmonary Embolism', 'COVID-19 Pneumonia', 'Acute Respiratory Distress Syndrome', 'Pregnancy-related Thromboembolism', 'Severe Pneumonia', 'Pulmonary Embolism', 'COVID-19 Pneumonia', 'Pregnancy-related Thromboembolism']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['COVID-19 pneumonia', 'Pulmonary embolism']
- diagnose: ['COVID-19 pneumonia', 'Pulmonary embolism']
- queries: ['pregnancy complications with thrombocytopenia and transaminitis', 'COVID-19 in pregnancy with decreased fetal movement', 'dyspnea and chest pain in pregnancy', 'ECMO therapy in pregnancy']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

