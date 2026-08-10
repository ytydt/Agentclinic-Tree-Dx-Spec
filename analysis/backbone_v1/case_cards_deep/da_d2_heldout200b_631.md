# DA / d2_heldout200b / case 631

- **gold**: Primary Cardiac Angiosarcoma
- **layer**: `base_win_recall`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=
- **loci**: e7=`s2_miss` B06=`supervisor_ok` B07=`diagnose_ok` B01=`na` APHHM=`na`
- **primary_locus**: e7=s2_miss; B06=supervisor_ok
- **covariates**: vig_words=249; gold_words=3; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: 骨干入口完全未召回；基线直接给出金标/近义。

## Vignette (trunc)
A 31-year-old active duty man with no significant medical history presented with:- One week of worsening fatigue- Dyspnea- Hemoptysis- Nausea- Ataxia- Acute-onset headache  Initial vital signs:- Blood pressure: 110/56 mm Hg- Heart rate: 104 beats/min- Respiratory rate: 29 breaths/min- Oxygen saturation: 83% to 87% on 6 L nasal cannulaPhysical findings:- Tachycardic- Shallow respirations- Diffuse crackles in the upper and lower lung fields  Laboratory Tests:- Hemoglobin: 9.3 g/dL (showing anemia)...

## Options
  - A: Primary Cardiac Angiosarcoma
  - B: Primary cardiac lymphoma
  - C: Metastatic angiosarcoma with pulmonary and central nervous system involvement
  - D: Metastatic melanoma

## Backbone e7
- S1 key_facts: One week of worsening fatigue; Dyspnea; Hemoptysis; Nausea; Ataxia; Acute-onset headache; Tachycardic; Shallow respirations
- S2 mode=complement k=3 pool_n=54 gold_in_s2=False
  - call1: ['Choriocarcinoma', 'Embryonal carcinoma', 'Yolk sac tumor', 'Teratoma with malignant transformation', 'Pulmonary lympho
  - call2: ['Alveolar soft part sarcoma', 'Clear cell sarcoma', 'Desmoplastic small round cell tumor', 'Extramedullary hematopoiesi
  - call3: ['Chordoma', 'Hemangiopericytoma', 'Malignant granular cell tumor', 'Pulmonary artery intimal sarcoma', 'Intracardiac le
- S3 shortlist n=5 gold=False: Intravascular lymphoma, Angiosarcoma of the heart, Epithelioid hemangioendothelioma, Intravascular large B-cell lymphoma, Kaposi's sarcoma with pulmonary involvement
- S4 champion: **Intravascular large B-cell lymphoma** gold=False
- S4 raw (trunc): {"champion": "Intravascular large B-cell lymphoma", "rationale": "The presence of malignant cells lining vascular spaces on biopsy, along with symptoms such as worsening fatigue, dyspnea, hemoptysis, and markedly elevated lactate dehydrogenase, are consistent with intravascular l

## Backbone v0 (compact)
- S1 key_facts: One week of worsening fatigue; Dyspnea; Hemoptysis; Nausea; Ataxia; Acute-onset headache; Tachycardic; Shallow respirations
- S2 mode=single k=1 pool_n=18 gold_in_s2=True
  - call1: ['Choriocarcinoma', 'Embryonal carcinoma', 'Yolk sac tumor', 'Teratoma with malignant transformation', 'Pulmonary lympho
- S3 shortlist n=5 gold=True: Intravascular lymphoma, Choriocarcinoma, Angiosarcoma, Pulmonary lymphoma, Metastatic adrenal cortical carcinoma
- S4 champion: **Intravascular lymphoma** gold=False
- S4 raw (trunc): {"champion": "Intravascular lymphoma", "rationale": "Malignant cells lining vascular spaces on biopsy, marked elevation of lactate dehydrogenase, and presence of multiple systemic masses and nodules are consistent with intravascular lymphoma, a rare and aggressive lymphoma that c

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    Given the patient's presentation with multiple masses, including a right atrial mass, and the pathology results showing malignant cells lining vascular spaces w
  - turn1 gold_mention=True diag=
    The patient's presentation with multiple masses, including a right atrial mass, and the pathology results showing malignant cells lining vascular spaces with po
  - turn2 gold_mention=True diag=
    The patient's presentation with multiple masses, including a right atrial mass, and the pathology results showing malignant cells lining vascular spaces with po
- supervisor votes=3 top2=['Angiosarcoma', 'Choriocarcinoma'] gold=True

## Baseline B07
- draft=['Angiosarcoma', 'Metastatic disease'] gold=True
- has_refine=True refine=[] gold=None
- queries(4): ['hemoptysis and fatigue and hemoglobin 9.3', 'elevated lactate dehydrogenase and thrombocytopenia', 'right atrial mass and pulmonary nodules', 'subacute hemorrhage and pulmonary emboli']
- diagnose=['Angiosarcoma', 'Metastatic disease'] gold=True

