# 手工判别流程工作底稿（深审 22 例）

## DA_d2_heldout100/272 — Window-Period Acute Myocardial Infarction

- 语料判级：D3_direct_vignette_matched　家族：DA
- vignette 决定性线索（账本）：severe precordial pain radiating to left arm；dyspnea and sweating；hyperacute precordial T waves；initially negative troponin；subtotal proximal LAD occlusion
- 缺失限定词（账本）：nonstandard “window-period” label
- 前轮鉴别点：hyperacute broad-based T waves in V2-V5 as the earliest ischaemic sign, plus the rule that troponin only rises 1-2 h after onset and MI is excluded only if it is still normal at 3 h
- 指南中有：yes　vignette 中有：yes　方法抽取到：yes　用对：no　失败模式：polarity

### 四方法最终答案

- collapse3c：Acute Coronary Syndrome（召回 miss）
- multistance：Acute Coronary Syndrome（召回 top2_strong）
- impc：Variant Angina（召回 set_strong）
- forest：Acute Coronary Syndrome（召回 set_strong）

### 待分离的假设集（11 个）

- Acute Coronary Syndrome ← collapse3c,forest,impc,multistance
- Myocardial Infarction ← forest,impc,multistance
- Unstable Angina ← forest,impc,multistance
- Variant Angina ← collapse3c,impc,multistance
- Myocardial Infarction with Normal Troponin ← collapse3c,multistance
- Pulmonary Embolism ← collapse3c,multistance
- Aortic Dissection ← collapse3c
- Cardiac Syndrome X ← multistance
- Cardiomyopathy ← multistance
- Hypertensive Emergency ← multistance
- Prinzmetal's Angina ← multistance

### vignette

```
A patient in their 60s presented to the emergency department with approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night, accompanied by dyspnea, dizziness, and sweating. The patient's medical history was notable for hypertension, cerebral infarction, diabetes, and nicotine addiction.

Vital signs showed blood pressure of 188/101 mm Hg, heart rate at 84 beats/min, and respiratory rate at 20 breaths/min.

- Laboratory tests:
  - Serum cardiac troponin I level: <0.05 ng/mL (normal range, <0.16 ng/mL)
  - Potassium level: 4.1 mEq/L (normal range, 3.5-5.3 mEq/L)

- ECG findings:
  Image A Title: Initial ECG
  Image A Description: ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall upright T waves in precordial leads V2 through V5

  Image B Title: Post-procedural ECG
  Image B Description: Sinus rhythm at 65 beats/min with normalization of the T-wave morphology in leads V2 through V5

- Coronary angiography:
  Finding: Subtotal occlusion of the proximal left anterior descending artery

What is the most likely diagnosis?

Options:
A. Non-ST-segment elevation myocardial infarction (NSTEMI)
B. ST-segment elevation myocardial infarction (STEMI)
C. Non–ST-segment elevation myocardial infarction (NSTEMI)
D. Window-Period Acute Myocardial Infarction
```

---

## DA_d2_heldout100/348 — Asymptomatic posterior corneal dystrophy

- 语料判级：D1_parent_component_or_list_only　家族：DA
- vignette 决定性线索（账本）：asymptomatic bilateral concentric posterior stromal rings；20/20 vision；no deposits or infiltration；posterior crocodile shagreen
- 缺失限定词（账本）：asymptomatic posterior corneal dystrophy entity；concentric-ring phenotype；differential from posterior polymorphous dystrophy and François dystrophy
- 前轮鉴别点：posterior crocodile shagreen with concentric posterior stromal rings in an asymptomatic 20/20 eye
- 指南中有：no　vignette 中有：yes　方法抽取到：yes　用对：no　失败模式：source

### 四方法最终答案

- collapse3c：Corneal Ring Opacities（召回 miss）
- multistance：Schnyder Corneal Dystrophy（召回 top2_strong）
- impc：Fuchs endothelial corneal dystrophy（召回 set_strong）
- forest：Crocodile shagreen of the cornea（召回 miss）

### 待分离的假设集（23 个）

- Corneal amyloidosis ← forest,impc
- Corneal dystrophy ← impc,multistance
- Fuchs Endothelial Corneal Dystrophy ← collapse3c,multistance
- Pterygium ← collapse3c,multistance
- Arcus senilis ← multistance
- Corneal Arcus ← multistance
- Corneal Ring Opacities ← collapse3c
- Corneal arcus ← impc
- Corneal iron deposition ← forest
- Crocodile Shagreen ← collapse3c
- Crocodile shagreen of the cornea ← forest
- Fuchs Endothelial Dystrophy ← multistance
- Fuchs endothelial corneal dystrophy ← impc
- Fuchs endothelial dystrophy ← forest
- Keratoconus ← multistance
- Mild Nuclear Sclerosis ← multistance
- Nuclear Sclerosis ← collapse3c
- Posterior Crocodile Shagreen ← multistance
- Posterior crocodile shagreen ← impc
- Primary lipoidal degeneration ← impc
- Primary lipoidal degeneration of the cornea ← forest
- Schnyder Corneal Dystrophy ← multistance
- Wilson's disease ← multistance

### vignette

```
A man in his 70s presented for a routine ophthalmic examination with no specific ocular symptoms. He had no history of eye surgery. The patient's annual physical examination did not reveal any abnormalities, with lipid and glucose levels within normal range.

- Best spectacle-corrected visual acuity: 20/20 OU- Right eye: Normal conjunctiva with healthy ocular adnexa. Cornea showed normal luster and even surface with no distinct arcus senilis- Normal anterior stroma- 4 symmetric concentric ring-shaped opacities in posterior corneal stroma- Ring characteristics: Complete rings, outermost ring ~4mm from limbus- Ring measurements (vertical diameters from periphery to center): 6.0mm, 4.8mm, 4.5mm, and 3.6mm- Surface of rings: smooth without obvious deposits, pigmentation, or serrations- Peripheral cornea: posterior crocodile shagreen- Normal corneal sensations bilaterally- Keratometry readings: 43.4 × 43.4 D OD and 43.0 × 44.8 D OS- Left eye: Similar findings plus small nasal pterygium- Mild nuclear sclerosis of crystalline lens in both eyes

- Imaging Studies:    1. Laser scanning in vivo confocal microscopy (HRT II with RCM):       Image Description: Revealed long bandlike structures with thin streaks of white lines interspersed. No cellular infiltration seen in both eyes.        2. Slit-lamp examination images:       Image Description: Shows 4 corneal ring opacities in both eyes, alternatively distinct with outermost and third rings more sharply demarcated      - Laboratory Tests:    - Serum copper levels: Normal    - Serum iron levels: Normal

What is the most likely diagnosis?

Options:
A. Asymptomatic posterior corneal dystrophy
B. Posterior polymorphous corneal dystrophy
C. Central Cloudy Dystrophy of François
D. Pre-Descemet corneal dystrophy
```

---

## DA_d2_heldout200b/522 — Catatonia related to underlying Lewy body dementia

- 语料判级：D1_parent_component_or_list_only　家族：DA
- vignette 决定性线索（账本）：fluctuating cognition and failure to recognize family；visual/auditory hallucinations；mutism, staring, echopraxia and mitmachen；negative infectious/autoimmune workup
- 缺失限定词（账本）：catatonia as a manifestation of Lewy body dementia；causal relation between the two diagnoses
- 前轮鉴别点：catatonic signs (echopraxia, mitmachen, mutism, staring) co-occurring with the DLB core features
- 指南中有：partial　vignette 中有：yes　方法抽取到：yes　用对：no　失败模式：grain

### 四方法最终答案

- collapse3c：Catatonia（召回 champion_strong）
- multistance：Catatonia（召回 champion_strong）
- impc：Dementia with Lewy bodies（召回 set_near）
- forest：Catatonia（召回 champion_strong）

### 待分离的假设集（23 个）

- Catatonia ← collapse3c,forest,multistance
- Delirium ← forest,impc,multistance
- Chronic ischemic encephalopathy ← collapse3c,forest
- Dementia with Lewy bodies ← impc,multistance
- Major depressive disorder with psychotic features ← collapse3c,multistance
- Vascular Dementia ← forest,multistance
- Vitamin B12 deficiency ← forest,impc
- Alzheimer's disease ← impc
- Antidepressant-induced psychotic disorder ← collapse3c
- Antipsychotic-Induced Parkinsonism ← multistance
- Chronic Ischemic Encephalopathy ← forest
- Chronic ischemia ← impc
- Creutzfeldt-Jakob Disease ← forest
- Dementia ← multistance
- Dementia with Lewy Bodies ← forest
- Hypothyroidism-associated encephalopathy ← collapse3c
- Hypothyroidism-related encephalopathy ← forest
- Lewy Body Dementia ← multistance
- Mirtazapine-induced psychosis ← forest
- Neurodegenerative disease ← multistance
- Neurosyphilis ← forest
- Psychotic disorder ← multistance
- Vascular dementia ← multistance

### vignette

```
A 68-year-old woman presented with three months of progressive decline in mental status. Medical history included coronary artery disease with recent stent placement, hypothyroidism, and major depressive disorder. Mirtazapine therapy was recently started. Patient experienced visual and auditory hallucinations, paranoid delusions, intermittent inability to recognize family, abnormal behaviors including speaking quietly to herself, and decreased oral intake, leading to significant weight loss.

Initial examination revealed:- Labile mood- Suspicious and withdrawn affect- Inattention- Limited speech with increased latency- Decreased participation- No focal neurologic deficitsAdditional signs observed:- Echopraxia- Mitmachen- Mutism- Staring- Withdrawn affect

Laboratory Tests:- Blood urea nitrogen (BUN): 13.57 mmol/L- Creatinine (Cr): 99.03 µmol/L (baseline 79.58)- Lactate dehydrogenase (LDH): 4.42 µkat/L- Albumin: 41 g/L- Hemoglobin (Hgb): 149 g/L- Platelets: 134 × 10⁹- Homocysteine: 12.3 µmol/L- B12: 1154.67 pmol/L- 25-hydroxyvitamin D: 147.5 nmol/L- Thyroid-stimulating hormone: normal- Ammonia levels: normal- Serum rapid plasma reagin: negative- HIV tests: negative- Urinalysis and blood cultures: negative for infectionImaging and Other Tests:- Lumbar puncture: negative for infectious, autoimmune, malignant causes and paraneoplastic encephalitis- Electroencephalography: showed diffuse slowing without seizures- MRI brain: showed white matter changes, likely chronic ischemia- CT abdomen/pelvis with contrast: unrevealing

What is the most likely diagnosis?

Options:
A. Catatonia (possibly due to major depressive disorder)
B. Dementia with Lewy bodies
C. Catatonia related to underlying Lewy body dementia
D. Lewy Body Dementia
```

---

## DA_d2_heldout200b/551 — Linagliptin-induced acute pancreatitis

- 语料判级：D2_direct_but_partial_or_general　家族：DA
- vignette 决定性线索（账本）：sharp epigastric pain radiating to back；nausea and vomiting；markedly elevated lipase；no gallbladder, alcohol or hypertriglyceridemia
- 缺失限定词（账本）：linagliptin exposure in presented medication list；linagliptin causal association；drug-dechallenge logic
- 前轮鉴别点：exposure to linagliptin
- 指南中有：yes　vignette 中有：no　方法抽取到：no　用对：no　失败模式：benchmark

### 四方法最终答案

- collapse3c：Acute Pancreatitis（召回 champion_strong）
- multistance：Dehydration（召回 top2_strong）
- impc：Acute Pancreatitis（召回 champion_strong）
- forest：Acute Pancreatitis（召回 champion_strong）

### 待分离的假设集（19 个）

- Diabetic Ketoacidosis ← collapse3c,forest,impc,multistance
- Acute Pancreatitis ← collapse3c,forest,impc
- Cholecystitis ← collapse3c,impc
- Chronic Pancreatitis ← forest,multistance
- Hypertensive Emergency ← collapse3c,multistance
- Peptic Ulcer Disease ← forest,impc
- Acute Coronary Syndrome ← multistance
- Chronic Kidney Disease ← forest
- Chronic Kidney Disease Exacerbation ← impc
- Chronic Kidney Disease-Related Abdominal Pain ← collapse3c
- Chronic kidney disease ← multistance
- Dehydration ← multistance
- Gastrointestinal obstruction ← multistance
- Hypertensive Crisis ← multistance
- Ischemic Cardiomyopathy-Related Abdominal Pain ← collapse3c
- Pancreatic Insufficiency ← forest
- Pancreatitis ← multistance
- Peptic ulcer disease ← multistance
- Renal Artery Stenosis ← multistance

### vignette

```
A 60-year-old African American woman presented with progressively worsening sharp epigastric pain radiating to the back of one-day duration, associated with nausea, vomiting, and decreased oral intake. She used pantoprazole without relief. No history of fever, chills, previous similar pain, recent illness, abdominal trauma, alcohol, or illicit drug use. Quit smoking seven years ago. Medical history includes insulin-dependent type 2 diabetes mellitus, hypertension, chronic kidney disease stage 4, coronary artery disease, coronary artery bypass grafting, and cholecystectomy. Current medications include insulin detemir, lispro, amlodipine, aspirin, atorvastatin, carvedilol, bumetanide, duloxetine, hydralazine, isosorbide mononitrate, and lisinopril.

Vital signs:- Temperature: 36.7 °C- Blood pressure: 200/100 mm Hg- Heart rate: 84 beats/min- Respiratory rate: 15 breaths/min with 95% oxygen saturation on room air- Body mass index: 32.66 kg/m²Patient in acute distress, with dry mucus membranes and decreased skin turgor. No rash or jaundice. Abdominal examination showed no distention, normal bowel sounds in all quadrants, generalized abdominal tenderness worst in the epigastrium, without rebound or guarding, and no palpable organomegaly.

Laboratory Tests:- Lipase: 13.6833 µkat/L (elevated)- Triglycerides: 80 mg/dL (0.9 mmol/L)- Hemoglobin: 93 g/L- White blood cells: 9.4 × 10⁹/L- Platelets: 250,000 × 10⁹/L- Glucose: 12.33 μmol/L- Creatinine: 198.9 μmol/L- Other laboratory values within normal ranges or not clinically significantImaging Studies:- Test: Computed helical tomography of abdomen and pelvis with intravenous contrast- Finding: No acute abnormality of the pancreas and surgically absent gallbladder without significant bile duct dilation

What is the most likely diagnosis?

Options:
A. Acute Pancreatitis
B. Linagliptin-induced acute pancreatitis
C. Other causes of acute abdominal pain (e.g., medication-induced irritation)
D. Peptic ulcer disease (e.g., peptic ulcer or gastritis)
```

---

## DA_d2_heldout200b/566 — High-grade (3A) follicular lymphoma, stage IVB

- 语料判级：D2_direct_but_partial_or_general　家族：DA
- vignette 决定性线索（账本）：large chylous pleural effusion；diffuse PET-avid adenopathy；B-cell lymphoid biopsy；BCL2 expression and high Ki-67；later weight loss
- 缺失限定词（账本）：grade 3A histologic rule；stage IVB assignment；gold-immunophenotype reconciliation
- 前轮鉴别点：follicular architecture with grade-3A centroblast counts and stage-IVB assignment
- 指南中有：partial　vignette 中有：no　方法抽取到：n/a　用对：no　失败模式：benchmark

### 四方法最终答案

- collapse3c：Primary Effusion Lymphoma（召回 miss）
- multistance：Primary Effusion Lymphoma（召回 top2_strong）
- impc：Lymphoma（召回 champion_strong）
- forest：Nodular lymphocyte-predominant Hodgkin lymphoma（召回 set_strong）

### 待分离的假设集（14 个）

- Castleman disease ← forest,impc,multistance
- Chylothorax ← forest,impc,multistance
- Diffuse Large B-Cell Lymphoma ← collapse3c,forest,multistance
- Lymphoma ← forest,impc,multistance
- Nodular Lymphocyte-Predominant Hodgkin Lymphoma ← collapse3c,forest,multistance
- Primary Effusion Lymphoma ← collapse3c,forest,multistance
- Anaplastic Large Cell Lymphoma ← collapse3c,multistance
- Castleman Disease ← collapse3c,multistance
- Dyslipidemia ← multistance
- Hypertriglyceridemia ← multistance
- Nodular lymphocyte-predominant Hodgkin lymphoma ← forest
- Pleural effusion ← multistance
- Primary effusion lymphoma ← forest
- Pseudolymphoma ← multistance

### vignette

```
A 64-year-old nonsmoking woman with a history of dyslipidemia presented to the emergency department with one week of progressive dyspnea. She was initially seen at urgent care. She did not report chest pain, cough, fever, chills, weight loss, or night sweats. Later, she developed unintentional weight loss.

Patient was afebrile and normoxic on room air. The pulmonary examination was remarkable for nearly absent breath sounds on the right side. The remainder of the physical examination, including cardiovascular, abdominal, and lymph node examinations, were unremarkable.

- Laboratory Tests:    * Complete blood count and basic metabolic panel results revealed no abnormalities    * Pleural fluid analysis showed:      - Leukocyte count: 9.6 × 10⁹/L with 96% lymphocytes      - Cholesterol level: 1.79 mmol/L (69 mg/dL)      - Triglyceride level: 8.44 mmol/L (747 mg/dL)      - Sterile culture      - Positive Light's criteria based on lactate dehydrogenase ratio  - Imaging Studies:    * Initial chest radiograph      Title: Large right effusion      Description: Large right effusion with mild mediastinal shift to the left side    * Computed tomography angiogram of chest      Description: Extensive mediastinal and hilar density encasing the right mainstem bronchus with complete right lung atelectasis with overlying pleural effusion and leftward mediastinal shift, no evidence of pulmonary embolism    * PET scan      Description: Mediastinal, bilateral hilar, cardiophrenic angle, retrocrural, and retroperitoneal adenopathy; soft tissue hypermetabolic nodularity along the right pleura; no osseous lesions  - Pathological Tests:    * Endobronchial ultrasound-guided transbronchial needle aspiration of station 4R and cervical lymph node biopsy showed:      - Mix of small to large B lymphocytes      - Negative for CD5 and CD10 expression      - Negative for MYC, BCL6, and IRF-4 rearrangements      - Aberrant expression of BCL2      - Elevated Ki-67

What is the most likely diagnosis?

Options:
A. High-grade (3A) follicular lymphoma, stage IVB
B. Marginal zone lymphoma
C. Diffuse large B-cell lymphoma
D. Primary mediastinal (thymic) large B-cell lymphoma
```

---

## DA_d2_heldout200b/646 — Radiation-induced solitary rectal ulcer

- 语料判级：D2_direct_but_partial_or_general　家族：DA
- vignette 决定性线索（账本）：deep solitary anterior rectal ulcer；recent prostate radiation；normal remaining rectum；negative malignancy biopsies；mild straining and mucus
- 缺失限定词（账本）：radiation-induced solitary-ulcer composite；SpaceOAR-specific injury mechanism；latency threshold
- 前轮鉴别点：solitary deep anterior ulcer with an otherwise normal rectum after prostate radiotherapy
- 指南中有：partial　vignette 中有：yes　方法抽取到：yes　用对：n/a　失败模式：options

### 四方法最终答案

- collapse3c：Radiation Proctitis（召回 top2_strong）
- multistance：Radiation Proctitis（召回 set_strong）
- impc：Radiation Proctitis（召回 top2_strong）
- forest：Radiation Proctitis（召回 top2_strong）

### 待分离的假设集（8 个）

- Radiation Proctitis ← collapse3c,forest,impc,multistance
- Rectal Ulcer ← collapse3c,forest,impc,multistance
- Proctitis ← collapse3c,impc,multistance
- Rectal Mucosal Injury ← collapse3c,impc,multistance
- Chronic Radiation Injury ← collapse3c
- Hydrogel Spacer Complication ← multistance
- Inflammatory Bowel Disease ← multistance
- Solitary Rectal Ulcer Syndrome ← impc

### vignette

```
A 57-year-old asymptomatic man with a history of stage IIIc localized prostate cancer. Three months prior, he had completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer. Before colonoscopy, he reported only mild straining with bowel movements and occasional passage of mucus.

Initial colonoscopy examination revealed a large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate. The remainder of the rectum appeared normal.

- Imaging studies:    Image Title: Pelvic Imaging (Figure 1A)    Image Description: Shows spacer positioned between the prostate and rectum  - Endoscopic Findings:    Image Title: Colonoscopy Images (Figure 1B)    Image Description: Large deep-cratered solitary ulcer on the anterior rectal wall        Image Title: Colonoscopy Images (Figure 1C)    Image Description: Normal appearance of remainder of rectum without radiation-induced changes      - Pathology:    Biopsies of the lesion were negative for malignancy

What is the most likely diagnosis?

Options:
A. Radiation-induced solitary rectal ulcer
B. Solitary rectal ulcer syndrome
C. Radiation-induced rectal ulcer (radiation proctopathy)
D. Radiation-induced proctitis with ulceration
```

---

## DA_d2_heldout200b/773 — Idiopathic Pulmonary Arterial Hypertension (IPAH) with Patent Foramen Ovale (PFO)

- 语料判级：D3_direct_vignette_matched　家族：DA
- vignette 决定性线索（账本）：long exertional dyspnea/chest pain；elevated pulmonary artery pressure and enlarged right heart；new cyanosis；TEE-proven PFO with pure right-to-left shunt；PE/AV fistula excluded
- 缺失限定词（账本）：single precomposed gold label
- 前轮鉴别点：a patent foramen ovale is not a large systemic-to-pulmonary shunt, so it cannot produce Eisenmenger physiology; PAH with a coincidental PFO shunting right-to-left is the alternative
- 指南中有：yes　vignette 中有：yes　方法抽取到：yes　用对：no　失败模式：polarity

### 四方法最终答案

- collapse3c：Eisenmenger Syndrome（召回 top2_strong）
- multistance：Eisenmenger Syndrome（召回 set_strong）
- impc：Eisenmenger Syndrome（召回 top2_strong）
- forest：Eisenmenger Syndrome（召回 top2_strong）

### 待分离的假设集（10 个）

- Chronic Thromboembolic Pulmonary Hypertension ← collapse3c,forest,impc,multistance
- Eisenmenger Syndrome ← collapse3c,forest,impc,multistance
- Idiopathic Pulmonary Arterial Hypertension ← collapse3c,forest,impc,multistance
- Patent Foramen Ovale ← collapse3c,forest,multistance
- Tricuspid Regurgitation ← collapse3c,forest,multistance
- Pulmonary Arterial Hypertension ← forest,multistance
- Pulmonary Hypertension ← forest,multistance
- Cardiomyopathy ← multistance
- Chronic Thromboembolic Disease ← collapse3c
- Congenital Heart Disease ← multistance

### vignette

```
A 39-year-old male patient was admitted to hospital with recurrent post-activity chest pain and shortness of breath for more than 11 years and bilateral lower extremity edema for one week in March 2021. His symptoms began in 2010 when he first experienced post-activity chest pain and shortness of breath for half a year. The patient was initially acyanotic from 2010 to 2016, but gradually became cyanotic after an episode of severe cough and hemoptysis (approximately 50ml in volume) following a severe cold leading to pneumonia in July 2016.

The patient presented with mild bilateral lower extremity edema. Femoral artery oxygen saturation was measured at 88.5% (decreased from a previous measurement of 93.4% in 2016).

{'Laboratory Tests': 'Plasma N-terminal pro-brain natriuretic peptide was 94.2 pg/ml in August 2021, indicating normal cardiac function.', 'Imaging Studies': [{'Test Type': 'Chest CT', 'Findings': 'Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions'}, {'Test Type': 'Echocardiography', 'Findings': 'Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation. Estimated pulmonary artery systolic pressure of 55 mmHg in 2021.', 'Images': [{'Title': 'Follow-up echocardiography in 2016', 'Description': 'Demonstrated markedly enlarged right atrium and right ventricle, along with tricuspid regurgitation'}, {'Title': 'Follow-up echocardiography in 2021', 'Description': 'Showed presence of severe tricuspid regurgitation'}]}, {'Test Type': 'Right Heart Catheterization', 'Findings': 'Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure'}, {'Test Type': 'Transesophageal Echocardiography', 'Findings': 'Revealed a patent foramen ovale measuring 7.34 mm in width with a continuous, pure right-to-left shunt on colour flow mapping'}, {'Test Type': 'Pulmonary Angiography', 'Findings': 'No evidence of pulmonary embolism or pulmonary arteriovenous fistulae'}]}

What is the most likely diagnosis?

Options:
A. Idiopathic Pulmonary Arterial Hypertension (IPAH) with Patent Foramen Ovale (PFO)
B. Idiopathic pulmonary arterial hypertension with right-to-left shunt
C. Primary Pulmonary Hypertension
D. Congenital heart disease with progressive pulmonary hypertension leading to a right-to-left shunt
```

---

## DA_d2_seq100/119 — Eruptive pruritic papular porokeratosis (EPPP)

- 语料判级：D2_direct_but_partial_or_general　家族：DA
- vignette 决定性线索（账本）：rapidly eruptive intensely pruritic papules；pre-existing disseminated porokeratotic lesions；extremity distribution
- 缺失限定词（账本）：porokeratosis entity；eruptive pruritic papular variant；cornoid-lamella diagnostic morphology
- 前轮鉴别点：well-developed cornoid lamella
- 指南中有：yes　vignette 中有：yes　方法抽取到：yes　用对：no　失败模式：polarity

### 四方法最终答案

- collapse3c：Darier disease（召回 miss）
- multistance：Grover disease（召回 miss）
- impc：Darier's disease（召回 set_strong）
- forest：Grover's disease（召回 miss）

### 待分离的假设集（15 个）

- Darier's disease ← forest,impc,multistance
- Grover's disease ← forest,impc,multistance
- Darier disease ← collapse3c,multistance
- Grover disease ← collapse3c,multistance
- Parakeratosis variegata ← collapse3c,multistance
- Pityriasis rubra pilaris ← collapse3c,multistance
- Actinic keratosis ← impc
- Dermatitis ← multistance
- Keratosis pilaris ← multistance
- Lichen planus ← multistance
- Papular urticaria ← multistance
- Porokeratosis ← impc
- Psoriasis ← multistance
- Sjögren's syndrome ← multistance
- Sporiasis guttata ← collapse3c

### vignette

```
A woman in her 50s presented with a 3-month history of rapidly spreading intensively pruritic papules on her extremities. The patient had no remarkable medical or family history and was not concurrently being treated with any medications. She had been previously treated with topical steroid ointments and oral compound glycyrrhizin tablets, which had no obvious effect.

The lesions consisted of scattered, erythematous, annular papules measuring up to 5 mm wide. Further examination revealed a few asymptomatic brown flat papules scattered on her face. The palms, soles, and oral mucosa were not involved.

- Laboratory tests: Routine blood, liver and kidney function, antistreptolysin O, C-reactive protein, antinuclear antibody, and rheumatoid factor tests disclosed no abnormal findings.- Histopathology:   Skin biopsy revealed:  - Mild hyperkeratosis accompanied by parakeratosis  - Atrophy of the epidermis  - Well-developed cornoid lamellae with a decreased granular layer  - Individual cell dyskeratosis  - Vacuolar degeneration of the basal cell layer  - Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis- Images:  Image 1 Title: Clinical images of keratotic papules  Image Description: Keratotic papules diffusely distributed on an extremity, shown in original and magnified views  Image 2 Title: Histologic findings (H&E stain)  Image Description: Shows skin hyperkeratosis accompanied by parakeratosis with an inflammatory infiltrate in the upper dermis, and at higher magnification, revealing lymphocytes, histiocytes, and eosinophils in the infiltrate

What is the most likely diagnosis?

Options:
A. Eruptive pruritic papular porokeratosis (EPPP)
B. Disseminated Superficial Actinic Porokeratosis (DSAP)
C. Linear Porokeratosis
D. Disseminated Superficial Porokeratosis (DSP)
```

---

## DA_d2_seq100/19 — Follicular thyroid carcinoma with manubrial invasion

- 语料判级：D2_direct_but_partial_or_general　家族：DA
- vignette 决定性线索（账本）：remote thyroid-lobe resection；new destructive manubrial swelling；thyroid-follicular pathology/metastatic pattern
- 缺失限定词（账本）：direct manubrial invasion/recurrence pattern；case-specific route from thyroid bed to sternum
- 前轮鉴别点：contiguity between the substernal thyroid bed and the manubrium (direct invasion) versus haematogenous bone metastasis
- 指南中有：no　vignette 中有：partial　方法抽取到：yes　用对：no　失败模式：grain

### 四方法最终答案

- collapse3c：Recurrent Thyroid Cancer（召回 miss）
- multistance：Thyroid metastasis to bone（召回 set_strong）
- impc：Metastatic follicular thyroid carcinoma（召回 set_near）
- forest：Metastatic thyroid carcinoma（召回 set_near）

### 待分离的假设集（23 个）

- Recurrent goiter ← forest,impc,multistance
- Thyroid metastasis to bone ← forest,impc,multistance
- Recurrent thyroid goiter ← forest,multistance
- Benign bone cyst ← multistance
- Bone metastasis from other primary cancer ← multistance
- Bone metastasis from well-differentiated thyroid cancer ← forest
- Bone tumor ← multistance
- Brown Tumor ← collapse3c
- Fibrous Dysplasia ← collapse3c
- Follicular thyroid carcinoma ← multistance
- Giant Cell Tumor ← collapse3c
- Metastatic Thyroid Cancer ← impc
- Metastatic disease ← multistance
- Metastatic follicular thyroid carcinoma ← impc
- Metastatic thyroid carcinoma ← forest
- Recurrent Thyroid Cancer ← collapse3c
- Thyroid Metastasis to Bone ← collapse3c
- Thyroid cancer ← multistance
- Thyroid cancer with bone invasion ← multistance
- Thyroid cancer with bone metastasis ← impc
- Thyroid cancer with local invasion ← multistance
- Thyroid goiter with metastasis ← forest
- Thyroid osteopathy ← multistance

### vignette

```
A man in his 70s presented with swelling of the manubrium 12 years after resection of a large left substernal thyroid lobe through a midline sternotomy approach. The swelling was slightly tender and had increased in size markedly over the month prior to presentation. Medical history includes previous substernal left hemithyroidectomy for benign goiter 12 years ago.

Swelling noted over the manubrium, which was slightly tender.

- Imaging Studies:    CT Image Title: Computed Tomographic Image Demonstrating Lytic Mass of Manubrium    CT Image Description: Shows a lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm and residual right goiter. The posterior aspect is in close proximity to the brachiocephalic artery and the left innominate vein.    - Fine-needle aspiration:    Revealed follicular thyroid cells in the goiter and the manubrial lesion.    - Pathological Examination:    Image Title: Thyroid Follicles With Nuclear Features Infiltrating Adjacent to Bone Trabeculae    Image Description: Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae (at ×20 and ×10 magnification).

What is the most likely diagnosis?

Options:
A. Metastatic papillary thyroid carcinoma
B. Metastatic follicular thyroid carcinoma
C. Metastatic thyroid carcinoma
D. Follicular thyroid carcinoma with manubrial invasion
```

---

## DA_d2_seq100/5 — Left maxillary giant cell reparative granuloma (GCRG)

- 语料判级：D3_direct_vignette_matched　家族：DA
- vignette 决定性线索（账本）：teenager；expansile left maxillary mass；sinus pressure, facial swelling and septal deviation；giant-cell reparative pathology
- 缺失限定词（账本）：reparative granuloma entity；maxillary imaging pattern；distinction from giant-cell tumor and aneurysmal bone cyst
- 前轮鉴别点：absence of cytologic atypia in a giant-cell lesion of the maxilla, which separates the reparative granuloma from a true giant cell tumour
- 指南中有：yes　vignette 中有：yes　方法抽取到：yes　用对：partial　失败模式：grain

### 四方法最终答案

- collapse3c：Giant Cell Tumor（召回 set_near）
- multistance：Giant Cell Tumor（召回 set_near）
- impc：Juvenile Nasopharyngeal Angiofibroma（召回 set_near）
- forest：Juvenile Nasopharyngeal Angiofibroma（召回 set_near）

### 待分离的假设集（12 个）

- Fibrous Dysplasia ← collapse3c,forest,impc,multistance
- Giant Cell Tumor ← collapse3c,forest,impc,multistance
- Juvenile Nasopharyngeal Angiofibroma ← collapse3c,forest,impc,multistance
- Chordoma ← collapse3c,multistance
- Granulomatosis with Polyangiitis ← forest
- Granulomatosis with polyangiitis ← multistance
- Invasive fungal sinusitis ← collapse3c
- Maxillary Sinus Squamous Cell Carcinoma ← collapse3c
- Nasal tumor ← multistance
- Orbital tumor ← multistance
- Sinonasal Undifferentiated Carcinoma ← multistance
- Sinusitis ← multistance

### vignette

```
A teenage girl presented with several months of sinus pressure and facial swelling, and several weeks of external deviation of her nasal septum. No significant past medical history was mentioned.

On examination, a left nasal mass was noted. Mild left-sided proptosis was present.

- Imaging Studies:    CT scan (without and with contrast):    - Image Title: Computed tomographic scans of a heterogeneous mass in the left maxillary sinus    - Image Description: Shows a heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus. Mass eroded the orbital floor, medial and posterior maxillary walls, and anterior ethmoid air cells. No extension beyond cribriform plate. Displacement of inferior rectus without muscle invasion. Left maxillary alveolar ridge and several molar roots involved. Bony changes showed remodeling and thinning.    - Biopsy Results:    - Tissue analysis showed spindle cell process in a patternless arrangement with significant multinucleated giant cells    - Rare mitotic activity    - No cytologic atypia    - Largest portion measured 7.0 × 4.0 × 2.0 cm

What is the most likely diagnosis?

Options:
A. Ossifying Fibroma
B. Giant cell tumor of bone
C. Central Giant Cell Granuloma
D. Left maxillary giant cell reparative granuloma (GCRG)
```

---

## MCR_seq200b/257 — collar button abscess

- 语料判级：D3_direct_vignette_matched　家族：MCR
- vignette 决定性线索（账本）：painful fluctuant palmar web-space mass；spread toward flexor sheath；diabetes and leukocytosis；normal bone radiographs
- 缺失限定词（账本）：
- 前轮鉴别点：a fluctuant collection centred on the palmar web space after blunt dorsal trauma, versus the four Kanavel signs required for pyogenic flexor tenosynovitis
- 指南中有：yes　vignette 中有：yes　方法抽取到：yes　用对：no　失败模式：polarity

### 四方法最终答案

- collapse3c：Pyogenic Flexor Tenosynovitis（召回 miss）
- multistance：Pyogenic Flexor Tenosynovitis（召回 set_strong）
- impc：Pyogenic Flexor Tenosynovitis（召回 miss）
- forest：Pyogenic flexor tenosynovitis（召回 miss）

### 待分离的假设集（14 个）

- Cellulitis ← collapse3c,forest,impc,multistance
- Pyogenic Flexor Tenosynovitis ← collapse3c,impc,multistance
- Diabetic Hand Infection ← collapse3c,multistance
- Infectious tenosynovitis ← forest,multistance
- Septic Arthritis ← collapse3c,impc
- Abscess ← multistance
- Closed Traumatic Injury ← collapse3c
- Infectious Tenosynovitis ← impc
- Pyogenic flexor tenosynovitis ← forest
- Septic arthritis ← forest
- Trauma ← multistance
- Traumatic Hematoma ← collapse3c
- Traumatic Soft Tissue Injury ← multistance
- Traumatic Tenosynovitis ← multistance

### vignette

```
A 66-year-old man with type 2 diabetes (HbA1c 11.2%) presented with a one-week history of worsening right hand pain, swelling, and erythema, most prominent in the distal palm. Two weeks earlier, a concrete bench had fallen on the dorsal base of his right fourth digit without skin break; over the following week, he noted a bruise at that site. On examination, there was a 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit, with focal tenderness over the flexor sheath and limited active digit motion. He was afebrile; WBC count was 17.5 × 10^9/L. Plain radiographs of the right hand showed diffuse soft-tissue swelling throughout the palm and into the distal interphalangeal joints of the third and fourth digits with intact bony anatomy and no fracture or dislocation.

What is the most likely diagnosis?

Options:
A. collar button abscess
B. Cellulitis
C. Flexor tenosynovitis
D. Osteomyelitis
E. None
F. None
G. None
H. None
```

---

## MCR_seq200b/326 — Brucellosis

- 语料判级：D3_direct_vignette_matched　家族：MCR
- vignette 决定性线索（账本）：injured-hand contact with unpasteurized sheep stomach；fever and night sweats；progressive back pain；blood-culture gram-negative bacillus；T9 lesion and epidural abscess
- 缺失限定词（账本）：
- 前轮鉴别点：contact with an unpasteurised sheep stomach through an injured hand plus a Gram-negative bacillus in blood culture and failure of cefprozil
- 指南中有：yes　vignette 中有：yes　方法抽取到：yes　用对：no　失败模式：axis

### 四方法最终答案

- collapse3c：Spinal epidural abscess（召回 top2_strong）
- multistance：Spondylodiscitis（召回 set_strong）
- impc：Spinal epidural abscess（召回 set_strong）
- forest：Spinal epidural abscess（召回 set_strong）

### 待分离的假设集（12 个）

- Brucellosis ← collapse3c,forest,impc,multistance
- Spinal epidural abscess ← collapse3c,forest,impc,multistance
- Discitis ← collapse3c,forest,multistance
- Osteomyelitis ← forest,impc,multistance
- Vertebral osteomyelitis ← collapse3c,forest,impc
- Epidural abscess ← forest
- Gram-negative bacillary infection ← multistance
- Gram-negative bacillus infection ← forest
- Pott's disease ← collapse3c
- Spinal Epidural Abscess ← multistance
- Spinal tuberculosis ← multistance
- Spondylodiscitis ← multistance

### vignette

```
A 57-year-old man was admitted with a 1-month history of high fever, night sweats, and progressive back pain. He reported touching an unpasteurized sheep stomach with an injured hand about 1 month earlier. Initial outpatient therapy with oral cefprozil provided no lasting benefit. On admission, he had no fever but complained of worsening back pain and malaise.

Laboratory studies showed a white-cell count of 7170/mm3 with 80% neutrophils, an erythrocyte sedimentation rate of 35 mm/hour, a C-reactive protein level of 3.19 mg/dL, and a procalcitonin level of 0.21 ng/mL. A serological test for tuberculosis was negative. He was started on intravenous sulbactam–cefoperazone. On hospital day 6, blood cultures grew a Gram-negative bacillus. That same day, he developed weakness and numbness in both legs and difficulty with urination. Neurologic examination revealed grade 3/5 strength in the right lower limb, grade 4/5 in the left, hypertonia of both lower extremities, and tenderness on percussion and palpation of the T9 and T10 spinous processes.

Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and a posterior epidural abscess compressing the spinal cord at T9–T10. Positron emission tomography–computed tomography showed osteolytic destruction of the neural arch of T9. He was transferred to the Department of Orthopedics for surgical management.

What is the most likely diagnosis?

Options:
A. Brucellosis
B. — “The fever was initially presumed to be secondary to tuberculosis or a metastatic tumor
C. Tuberculosis was initially suspected
D. Metastatic tumor was considered given systemic symptoms and back pain
E. Brucella spondylitis or spondylodiscitis could explain vertebral infection but typically involves vertebral bodies or
F. Spinal tuberculosis could present with cold abscess and vertebral destruction but usually shows sequestra
G. Brucellosis was confirmed when the Gram
H. None
```

---

## MCR_seq200b/409 — Chronic necrotizing pancreatitis

- 语料判级：D3_direct_vignette_matched　家族：MCR
- vignette 决定性线索（账本）：prior severe pancreatitis and alcohol history；massive left pleural effusion；very high pleural-fluid amylase；pancreatic cystic/nonenhancing areas
- 缺失限定词（账本）：pancreaticopleural fistula rule；single chronic-necrotizing entity；pleural-fluid amylase threshold
- 前轮鉴别点：pleural fluid amylase of 11,871 U/L with pancreatic cystic collections, i.e. the pancreatic disease underlying the effusion rather than the fistula itself
- 指南中有：yes　vignette 中有：yes　方法抽取到：yes　用对：partial　失败模式：axis

### 四方法最终答案

- collapse3c：Pleural effusion due to pancreaticopleural fistula（召回 set_strong）
- multistance：Pleural effusion due to pancreaticopleural fistula（召回 set_strong）
- impc：Pancreaticopleural fistula（召回 miss）
- forest：Pulmonary effusion due to pancreaticopleural fistula（召回 set_near）

### 待分离的假设集（19 个）

- Pancreaticopleural fistula ← forest,impc,multistance
- Pleural effusion ← forest,impc,multistance
- Acute pancreatitis ← collapse3c,multistance
- Chronic pancreatitis ← forest,multistance
- Congestive heart failure ← collapse3c,multistance
- Empyema ← collapse3c,multistance
- Pancreatic pseudocyst ← forest,impc
- Pleural effusion due to pancreaticopleural fistula ← collapse3c,multistance
- Pulmonary embolism ← collapse3c,multistance
- Heart failure ← multistance
- Hypovolemic shock ← multistance
- Pancreatic Pseudocyst ← impc
- Pancreatitis ← multistance
- Pleural Effusion ← impc
- Pleural effusion due to pancreatic disease ← forest
- Pseudocyst ← forest
- Pulmonary Embolism ← impc
- Pulmonary effusion due to pancreaticopleural fistula ← forest
- Pulmonary tuberculosis ← impc

### vignette

```
A 40-year-old man presented with 5 days of progressive dyspnea. On day 1 he was short of breath only with uphill walking (MMRC grade 1), by day 2 he was breathless on level ground (grade 2), and by day 4 he was dyspneic at rest (grade 4). He also noted central, nonradiating chest pain with coughing, without positional change. He denied fever, night sweats, cyanosis, grunting, palpitations, or hemoptysis. He had three previous hospital admissions, most recently 4 months earlier for acute severe pancreatitis. He had a 5-year history of local alcohol consumption but had abstained for 6 months. 

On examination, pulse was 116/min, respiratory rate 30/min, blood pressure 110/70 mmHg, temperature 98 °F, and SpO2 95% on 4 L O2 by nasal prong. He had bilateral pitting edema to the knees. Chest inspection showed decreased movement on the left; trachea deviated rightward; decreased fremitus and stony dullness over the entire left hemithorax; and absent breath sounds on the left. Cardiovascular and abdominal examinations were unremarkable; there were no stigmata of chronic liver disease.

Laboratory studies showed hemoglobin 9.7 g/dL, WBC 5530/mm3, CRP 73.9 mg/L, alkaline phosphatase 145 U/L, serum albumin 3.1 g/dL, serum amylase 486 U/L, and lipase 416 U/L. 

Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, consistent with massive left pleural effusion. 

Ultrasonography of the chest, abdomen, and pelvis confirmed a large left pleural effusion with passive basal lung collapse, and showed a normal-sized pancreas with heterogeneous echotexture and a small intrapancreatic collection at the tail. 

Contrast-enhanced CT of the abdomen demonstrated multiple non-enhancing cystic areas in the pancreas (largest 23×16 mm in the tail), minimal peripancreatic fat stranding, and no main pancreatic duct dilation or parenchymal calcifications. 

Diagnostic thoracentesis yielded 900 mL of dark brown, turbid fluid. Pleural fluid analysis: protein 3.5 g/dL; LDH 1413 U/L; glucose 98 mg/dL; ADA 31.4 U/L; total cell count 100/mm3 (10% neutrophils, 90% lymphocytes); amylase 11,871 U/L; PCV 0.8%; no malignant cells; culture negative; MTB/RIF PCR negative.

What is the most likely diagnosis?

Options:
A. Chronic necrotizing pancreatitis
B. Acute pancreatitis
C. Pancreaticopleural fistula from chronic pancreatitis produces “large single sided recurrent pleural effusion [with]
D. Malignancy can cause amylase
E. Esophageal rupture may lead to elevated pleural fluid amylase, but was similarly excluded by the patient’s history
F. None
G. None
H. None
```

---

## MCR_seq200b/475 — Parsonage Turner Syndrome

- 语料判级：D3_direct_vignette_matched　家族：MCR
- vignette 决定性线索（账本）：young adult；loss of OK sign；multimuscle EMG spanning anterior interosseous and upper-arm muscles；normal MRI；distribution not confined to one nerve/root
- 缺失限定词（账本）：pain may be absent/underreported in this vignette
- 前轮鉴别点：EMG denervation extending beyond the anterior interosseous territory into biceps, triceps and deltoid
- 指南中有：yes　vignette 中有：yes　方法抽取到：partial　用对：no　失败模式：polarity

### 四方法最终答案

- collapse3c：Anterior Interosseous Nerve Syndrome（召回 set_strong）
- multistance：Anterior Interosseous Nerve Syndrome（召回 set_strong）
- impc：Anterior Interosseous Nerve Syndrome（召回 miss）
- forest：Anterior Interosseous Nerve Syndrome（召回 miss）

### 待分离的假设集（13 个）

- Anterior Interosseous Nerve Syndrome ← collapse3c,forest,impc,multistance
- Mononeuropathy ← forest,impc,multistance
- Brachial Plexitis ← collapse3c,multistance
- Mononeuritis Multiplex ← collapse3c,multistance
- Neuralgic Amyotrophy ← collapse3c,multistance
- Neuropathy ← impc,multistance
- Radial Neuropathy ← collapse3c,multistance
- Anterior Interosseous Syndrome ← forest
- Mononeuritis multiplex ← forest
- Musculoskeletal disorder ← multistance
- Neuralgic amyotrophy ← forest
- Radial neuropathy ← multistance
- Ulnar Neuropathy ← multistance

### vignette

```
A previously healthy 22-year-old woman presented with episodes of isolated, sudden weakness of the left upper limb. On examination, she had weakness of the distal phalanx of the thumb and middle phalanx of the index finger, with inability to perform the “Ok” sign and to form a fist. Grip strength was decreased on the left. There were no sensory deficits. Tendon reflexes were normal throughout, and there was no muscular wasting, pathological reflexes, or focal neurological signs. Routine laboratory tests and her personal and family history were unremarkable. An electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the anterior interosseous nerve, including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, triceps brachii, and deltoid muscles. MRI of the left upper extremity was performed and showed no abnormalities.

What is the most likely diagnosis?

Options:
A. Parsonage Turner Syndrome
B. glenohumeral bursitis or as a muscle strain, leading to the patient receiving analgesics that often fail to control
C. due to loss of the “Ok” sign but excluded when EMG revealed additional involvement of biceps, triceps, and deltoid
D. Glenohumeral bursitis or muscle strain was considered but excluded when analgesics failed to control symptoms
E. Cervical spondylosis or radiculopathy was considered but ruled out by normal neuroimaging
F. Adhesive capsulitis and acute calcific tendinitis were considered but lacked supportive findings on examination and
G. An anterior interosseous nerve neuropathy was initially suspected due to loss of the “Ok” sign but excluded when EMG
H. Parsonage
```

---

## MCR_v1_seq100/49 — StumpAppendicitis

- 语料判级：D3_direct_vignette_matched　家族：MCR
- vignette 决定性线索（账本）：right iliac fossa pain and fever；marked neutrophilic leukocytosis；CT tubular structure at cecal pole with collection；appendectomy eight months earlier and adjacent clips
- 缺失限定词（账本）：residual appendiceal stump entity；postappendectomy recurrence mechanism
- 前轮鉴别点：a residual appendiceal stump adjacent to surgical clips eight months after appendectomy
- 指南中有：yes　vignette 中有：yes　方法抽取到：yes　用对：partial　失败模式：grain

### 四方法最终答案

- collapse3c：Appendiceal stump appendicitis（召回 champion_strong）
- multistance：Appendiceal stump appendicitis（召回 champion_strong）
- impc：Abscess（召回 top2_strong）
- forest：Appendiceal abscess（召回 set_strong）

### 待分离的假设集（20 个）

- Abscess ← forest,impc,multistance
- Appendiceal stump appendicitis ← collapse3c,impc,multistance
- Appendicitis ← forest,impc,multistance
- Cecal diverticulitis ← collapse3c,forest,multistance
- Intestinal obstruction ← collapse3c,impc
- Intra-abdominal infection ← forest,impc
- Appendiceal Stump Abscess ← multistance
- Appendiceal abscess ← forest
- Complicated diverticulitis ← forest
- Diverticulitis ← multistance
- Inflammatory bowel disease ← multistance
- Intestinal tuberculosis ← multistance
- Intra-abdominal Abscess ← multistance
- Intra-abdominal abscess ← collapse3c
- Neutropenic colitis ← forest
- Pericecal abscess ← multistance
- Post-surgical abscess ← forest
- Post-surgical adhesions ← collapse3c
- Surgical Site Infection ← multistance
- Typhlitis ← multistance

### vignette

```
A 58‐year‐old man presented to the emergency department with a 24‐hour history of right iliac fossa pain, nausea, and diarrhea. His surgical history was notable for a laparoscopic appendectomy performed 8 months earlier; he had no other significant past medical history. On examination, he was febrile, and his hemodynamic and respiratory parameters were stable. Abdominal palpation elicited pain in the right lower quadrant without peritoneal signs. Laboratory studies showed a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils and a C‐reactive protein level of 180 mg/dL; all other laboratory values were within normal limits. An abdominal CT scan demonstrated a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole, with a 25‐mm pericecal collection adjacent to surgical clips.

What is the most likely diagnosis?

Options:
A. StumpAppendicitis
B. Inflamed residual appendiceal stump considered because CT demonstrated a remaining stump and abscess
C. Cecal diverticulitis considered due to similar right‐lower‐quadrant presentation
D. Duplicated appendix considered owing to a rare anatomic anomaly that can cause post‐appendectomy appendicitis
E. None
F. None
G. None
H. None
```

---

## MCR_v1_seq100/56 — Spindle cell squamous cell carcinoma

- 语料判级：D2_direct_but_partial_or_general　家族：MCR
- vignette 决定性线索（账本）：gingival polypoid mass with bone destruction；malignant spindle cells and atypical mitoses；p63/p53 positivity；remote oral SCC and radiation
- 缺失限定词（账本）：oral/gingival site；p63-positive cytokeratin-negative interpretation；radiation-associated recurrence distinction
- 前轮鉴别点：p63 positivity with epidermal connection marking an epithelial (squamous) rather than mesenchymal origin at a gingival site
- 指南中有：no　vignette 中有：yes　方法抽取到：yes　用对：no　失败模式：source

### 四方法最终答案

- collapse3c：Postradiation Sarcoma（召回 set_near）
- multistance：Malignant Spindle Cell Sarcoma（召回 set_strong）
- impc：Sarcoma（召回 set_near）
- forest：Sarcomatoid carcinoma（召回 set_near）

### 待分离的假设集（23 个）

- Osteosarcoma ← forest,impc,multistance
- Malignant Spindle Cell Sarcoma ← collapse3c,multistance
- Postradiation Sarcoma ← collapse3c,multistance
- Sarcoma ← impc,multistance
- Sarcomatoid Carcinoma ← forest,multistance
- Spindle cell carcinoma ← forest,impc
- Carcinoma ← multistance
- Gingival Fibrosarcoma ← multistance
- Gingival Granuloma ← multistance
- Gingival Squamous Cell Carcinoma ← multistance
- Gingival hyperplasia ← multistance
- Inflammatory Myofibroblastic Tumor ← collapse3c
- Inflammatory Pseudotumor ← multistance
- Inflammatory myofibroblastic tumor ← forest
- Leiomyosarcoma ← collapse3c
- Lymphoma ← multistance
- Malignant Fibrous Histiocytoma ← forest
- Malignant fibrous histiocytoma ← forest
- Necrotizing sialometaplasia ← impc
- Radiation-Induced Sarcoma ← multistance
- Sarcomatoid carcinoma ← forest
- Sarcomatoid squamous cell carcinoma ← forest
- Undifferentiated Pleomorphic Sarcoma ← collapse3c

### vignette

```
A 69-year-old Japanese man presented with pain and a 10-mm polypoid mass on the left lower gingiva. He had undergone chemoradiotherapy 15 years earlier for squamous cell carcinoma of the left buccal mucosa, with no recurrence until now. He denied tobacco or alcohol use. On examination, vital signs were normal; trismus was present. Intraoral inspection revealed a rough-surfaced polypoid lesion in the left lower molar gingiva covered by a whitish pseudomembrane. Panoramic radiography showed a moth-eaten pattern of mandibular bone resorption. Contrast-enhanced CT demonstrated an enhancing soft-tissue mass with irregular mandibular bone destruction. A biopsy specimen showed loose granulation tissue with scattered atypical spindle and pleomorphic cells in a fibrin-rich edematous stroma alongside inflammatory cells. The overlying squamous epithelium exhibited only slight nuclear enlargement without dysplasia. The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils within cytoplasmic vacuoles. Immunohistochemical staining revealed that the spindle cells were positive for vimentin, α-smooth muscle actin, p63, p53, and CD68, but negative for pan-cytokeratin and other epithelial markers; Ki-67 labeling index was approximately 50%. These findings prompted consideration of a malignant spindle cell process.

What is the most likely diagnosis?

Options:
A. Spindle cell squamous cell carcinoma
B. due to absence of lineage differentiation
C. as a mesenchymal neoplasm, given no obvious evidence of osteogenic, muscular, or adipogenic differentiation
D. Spindle cell squamous cell carcinoma was favored because p63 positivity indicates epithelial differentiation
E. Post
F. High
G. Malignant melanoma was ruled out because of negative S
H. Radiation
```

---

## MCR_v1_seq100/74 — Catecholaminergic polymorphic ventricular tachycardia

- 语料判级：D3_direct_vignette_matched　家族：MCR
- vignette 决定性线索（账本）：collapse/VF during emotional-noise stress；young patient；normal electrolytes and structural assessment；normal QT and no Brugada/pre-excitation
- 缺失限定词（账本）：exercise-provocation or genetic confirmation
- 前轮鉴别点：QTc of 380 ms is normal, which excludes long QT syndrome; CPVT is the exertion-triggered polymorphic/bidirectional VT with a structurally normal heart
- 指南中有：yes　vignette 中有：yes　方法抽取到：yes　用对：no　失败模式：polarity

### 四方法最终答案

- collapse3c：Long QT Syndrome（召回 top2_strong）
- multistance：Long QT Syndrome（召回 set_strong）
- impc：Long QT Syndrome（召回 set_strong）
- forest：Catecholaminergic Polymorphic Ventricular Tachycardia（召回 champion_strong）

### 待分离的假设集（13 个）

- Hypertrophic Cardiomyopathy ← collapse3c,forest,impc,multistance
- Long QT Syndrome ← collapse3c,forest,impc,multistance
- Catecholaminergic Polymorphic Ventricular Tachycardia ← collapse3c,forest,multistance
- Autism Spectrum Disorder-related Cardiac Dysfunction ← collapse3c,multistance
- Risperidone-induced Cardiac Dysfunction ← collapse3c,multistance
- Arrhythmogenic Right Ventricular Cardiomyopathy ← impc
- Brugada syndrome ← impc
- Cardiomyopathy ← multistance
- Catecholaminergic polymorphic ventricular tachycardia ← impc
- Channelopathy ← multistance
- Long QT syndrome ← impc
- Metabolic disorder ← multistance
- Seizure disorder ← multistance

### vignette

```
A 21-year-old woman with autism spectrum disorder (on risperidone) and intellectual disability was brought to the hospital after a witnessed collapse. She had no prior history of syncope, cardiac arrest, or known cardiovascular disease, and her family denied any illicit drug or alcohol use. While at a noisy auto mechanic shop, she became pale and lost consciousness; bystander ECG showed ventricular fibrillation. Return of spontaneous circulation was achieved after two defibrillations. On arrival, her blood pressure was 93/70 mmHg, pulse 86 bpm, and oxygen saturation 100% (bag–valve–mask). An intravenous amiodarone infusion (1 mg/min) and oral amiodarone 400 mg were administered. On examination she was comatose (GCS 3), with agonal respirations; cardiovascular examination was unremarkable. In the intensive care unit, her differential diagnosis included channelopathies, hypertrophic cardiomyopathy, and metabolic abnormalities. Laboratory tests showed normal chemistry panel and electrolytes. Initial electrocardiogram revealed sinus rhythm with interpolated premature ventricular complexes and a QTc of 380 ms, without any evidence of infarction, pre-excitation, or Brugada pattern. Transthoracic echocardiography demonstrated an ejection fraction of 45–50%, normal wall thickness, and no valvular abnormalities.

What is the most likely diagnosis?

Options:
A. Catecholaminergic polymorphic ventricular tachycardia
B. Channelopathies were initially considered
C. Hypertrophic cardiomyopathy was excluded because “The transthoracic echocardiogram (TTE) revealed ... normal wall
D. Metabolic abnormalities were excluded as “Her chemistry panel and electrolytes were normal
E. Long QT syndrome was excluded given “Initial electrocardiogram ... no findings of QT prolongation …
F. Ischemic heart disease was excluded because ECG showed “no findings of ... infarct …
G. Pre
H. Brugada syndrome was excluded as ECG showed “no findings of ... Brugada syndrome
```

---

## MCR_v1_seq100/91 — Angiosarcoma

- 语料判级：D2_direct_but_partial_or_general　家族：MCR
- vignette 决定性线索（账本）：recurrent occipital hemorrhage；invasive extra-axial mass；branching vascular channels；CD31 and Fli-1 positivity
- 缺失限定词（账本）：primary intracranial/meningeal angiosarcoma；hemorrhagic imaging phenotype；endothelial immunophenotype
- 前轮鉴别点：CD31 and Fli-1 positive with CD34 and Bcl-2 negative, which is endothelial and excludes solitary fibrous tumour / haemangiopericytoma
- 指南中有：yes　vignette 中有：yes　方法抽取到：yes　用对：no　失败模式：polarity

### 四方法最终答案

- collapse3c：Solitary Fibrous Tumor（召回 miss）
- multistance：Hemangiopericytoma（召回 set_strong）
- impc：Hemangiopericytoma（召回 miss）
- forest：Hemangiopericytoma（召回 miss）

### 待分离的假设集（12 个）

- Cavernous Angioma ← collapse3c,forest,impc,multistance
- Hemangiopericytoma ← collapse3c,forest,impc,multistance
- Solitary Fibrous Tumor ← collapse3c,impc,multistance
- Cavernous angioma ← forest,multistance
- Meningioma ← collapse3c,multistance
- Solitary Fibrous Tumor/Hemangiopericytoma ← forest,multistance
- Hemangioma ← multistance
- Kaposi's Sarcoma ← collapse3c
- Kaposi's sarcoma ← multistance
- Lymphoma ← multistance
- Metastasis ← multistance
- Solitary fibrous tumor ← multistance

### vignette

```
A 36-year-old Asian man presented with a 4-month history of worsening headaches and complete right homonymous hemianopia. Two years earlier, he had a left occipital intracerebral hematoma of unknown cause. On examination, vital signs were normal, and neurologic testing confirmed the visual field defect without other focal deficits.

Noncontrast head CT showed a left occipital intraparenchymal hemorrhage. Contrast-enhanced brain MRI revealed a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage, suggesting a cavernous angioma. The patient underwent a left occipital craniotomy; intraoperatively, the mass was found to invade the falx cerebri and adjacent cortex, limiting resection to subtotal removal. Postoperative CT showed no complications.

Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature, focal collagenous regions, and up to 20 mitoses per ten high-power fields. Immunohistochemical studies showed strong immunoreactivity for CD31, CD99, and Fli-1, with scattered S100-positive cells, and negative staining for CD34, EMA, desmin, muscle-specific actin, and Bcl-2.

What is the most likely diagnosis?

Options:
A. Angiosarcoma
B. based on imaging
C. Cavernous angioma was initially suspected based on imaging
D. Meningeal sarcoma with angiosarcomatous features was favored by pathology
E. Gliosarcoma was considered given the biphasic pattern of glial and mesenchymal differentiation
F. Metastatic malignancy was entertained due to a solitary pulmonary nodule on PET
G. None
H. None
```

---

## MCR_v2_seq100/146 — Diffuse large B cell lymphoma

- 语料判级：D3_direct_vignette_matched　家族：MCR
- vignette 决定性线索（账本）：weight loss and night sweats；persistent distal ileal disease/stricture；negative enteric studies；eventual tissue diagnosis of DLBCL
- 缺失限定词（账本）：DLBCL-specific histology and markers；ileitis/stricture phenotype versus Crohn/TB
- 前轮鉴别点：the histology of the ileal and colonic biopsies
- 指南中有：yes　vignette 中有：no　方法抽取到：no　用对：no　失败模式：benchmark

### 四方法最终答案

- collapse3c：Intestinal Tuberculosis（召回 miss）
- multistance：Intestinal Tuberculosis（召回 set_near）
- impc：Tuberculosis（召回 miss）
- forest：Intestinal tuberculosis（召回 miss）

### 待分离的假设集（15 个）

- Crohn's disease ← forest,impc,multistance
- Helminth infection ← forest,impc,multistance
- Helminthic infection ← forest,impc,multistance
- Intestinal tuberculosis ← forest,impc,multistance
- Crohn's Disease ← collapse3c,multistance
- Helminthic Infection ← collapse3c,multistance
- Intestinal Lymphoma ← collapse3c,multistance
- Intestinal Tuberculosis ← collapse3c,multistance
- Tuberculosis ← impc,multistance
- Diverticulitis ← multistance
- Gastrointestinal lymphoma ← multistance
- Ileocecal Histoplasmosis ← collapse3c
- Inflammatory bowel disease ← multistance
- Ischemic colitis ← multistance
- Latent tuberculosis ← forest

### vignette

```
A 74-year-old Spanish-speaking man visiting the United States from Honduras presented with a 2-month history of postprandial abdominal pain, nausea, night sweats, early satiety, and a 10-kg weight loss. One week earlier, an abdominal and pelvic CT scan had shown distal ileitis, and he had received a course of antibiotics without improvement. On re-presentation, he reported worsening symptoms and difficulty tolerating oral intake. He denied hematochezia, diarrhea, or fevers. His medical history was notable for prior appendectomy and recently treated helminth infection.

On examination, he was afebrile with stable vital signs. There was no abdominal tenderness or palpable masses, and no evidence of perianal disease. Laboratory studies showed an erythrocyte sedimentation rate of 42 mm/hr, a C-reactive protein level of 35 mg/L, and a fecal calprotectin of 94 μg/mg. Stool studies were negative for enteric pathogens. Repeat CT imaging demonstrated persistent distal ileitis.

Ileocolonoscopy revealed a normal terminal ileum, but a nontraversable distal ileal stricture, cecal ulcers, and patchy loss of vascularity throughout the colon. Segmental biopsies of the ileum and colon were obtained. QuantiFERON-TB Gold was positive. Hepatitis B serologies showed a reactive core total antibody, a reactive e antigen, negative surface antigen, and undetectable HBV DNA. He was started on isoniazid for latent tuberculosis.

What is the most likely diagnosis?

Options:
A. Diffuse large B cell lymphoma
B. Crohn’s disease was considered because of “concern for a new presentation of CD given his presentation of abdominal
C. Infectious enteritis (eg, Yersinia) was considered but excluded because “stool studies were negative for enteric
D. Intestinal tuberculosis was considered given the positive QuantiFERON and endemic risk, but clinical suspicion remained
E. Lymphoma was ultimately diagnosed after “the diagnosis of NHL, specifically DLBCL, was confirmed by histologic
F. None
G. None
H. None
```

---

## MCR_v2_seq100/179 — hypoxia-induced thrombocytopenia

- 语料判级：D1_parent_component_or_list_only　家族：MCR
- vignette 决定性线索（账本）：cyanotic congenital heart disease；platelets vary with oxygenation；negative immune tests；no IVIG response；normal coagulation and smear
- 缺失限定词（账本）：hypoxia-induced mechanism；oxygen-saturation/platelet temporal relation；cyanotic-heart-disease association
- 前轮鉴别点：platelet count tracking arterial saturation across four time points, with no response to IVIG
- 指南中有：no　vignette 中有：yes　方法抽取到：yes　用对：no　失败模式：axis

### 四方法最终答案

- collapse3c：Tetralogy of Fallot with pulmonary atresia（召回 miss）
- multistance：Tetralogy of Fallot with pulmonary atresia（召回 set_strong）
- impc：Tetralogy of Fallot with pulmonary atresia（召回 set_strong）
- forest：Pulmonary Atresia with Ventricular Septal Defect（召回 set_strong）

### 待分离的假设集（19 个）

- Tetralogy of Fallot with pulmonary atresia ← collapse3c,forest,impc,multistance
- Immune thrombocytopenia ← forest,impc,multistance
- Thrombocytopenia ← forest,impc,multistance
- Cyanotic congenital heart disease ← impc,multistance
- Immune Thrombocytopenia ← forest,impc
- Pulmonary Atresia ← impc,multistance
- Pulmonary Atresia with Ventricular Septal Defect ← forest,impc
- Ventricular Septal Defect ← impc,multistance
- Alagille syndrome ← collapse3c
- Bleeding disorder ← multistance
- Congenital Heart Disease ← impc
- Congenital heart disease ← multistance
- Congenital thrombocytopenia ← collapse3c
- Cyanotic Congenital Heart Disease ← multistance
- Cyanotic heart disease ← multistance
- Jacobsen syndrome ← collapse3c
- Postoperative thrombocytosis ← multistance
- Pulmonary atresia with ventricular septal defect ← multistance
- Thrombocytopenia-absent radius syndrome ← collapse3c

### vignette

```
A male newborn was referred at 1 day of age for cyanosis; oxygen saturation (SaO2) was 80% in room air. Laboratory findings showed a hematocrit of 47.8% and a platelet count of 103 000/mm3; other values were normal and there were no signs of infection. Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus. A prostaglandin infusion was started, raising SaO2 to 90–95%. On day 11, he underwent a systemic‐to‐pulmonary shunt operation with graft placement and PDA division. Preoperative values on day 10 were hematocrit 38.9%, platelet count 173 000/mm3, and SaO2 95% on prostaglandin. Postoperatively, hematocrit was 52.1% and platelet count was 58 000/mm3; platelet count then increased without transfusion. By postoperative day 6, he was extubated with SaO2 80–85%, hematocrit 41.1%, and platelet count 123 000/mm3. He was discharged on postoperative day 13 with SaO2 85–87%, hematocrit 33.4%, and platelet count 225 000/mm3.

At 10 months of age, he was admitted for a Rastelli operation. His SaO2 was 80%; hematocrit was 49.1% and platelet count was 68 000/mm3. He had no bleeding history or medications. Prothrombin time, activated partial thromboplastin time, and INR were normal; peripheral smear was unremarkable. Antiplatelet antibodies and platelet‐associated immunoglobulins were negative; antinuclear and anti–double‐stranded DNA antibodies were normal. Platelet aggregation time was 127 s (reference, 61–110 s). Viral and bacterial studies were insignificant. The pediatrician made a provisional diagnosis of immune thrombocytopenia and administered intravenous immunoglobulins (2 g/kg) the day before surgery. On the day of operation, hematocrit was 42.6% and platelet count was 77 000/mm3.

What is the most likely diagnosis?

Options:
A. hypoxia-induced thrombocytopenia
B. neonatal alloimmune thrombocytopenia
C. Neonatal alloimmune thrombocytopenia was considered
D. Immune thrombocytopenia was provisionally diagnosed
E. Lack of response to IVIG argued against immune thrombocytopenia
F. Hypoxia
G. None
H. None
```

---

## MCR_v2_seq100/202 — Mantle cell lymphoma

- 语料判级：D2_direct_but_partial_or_general　家族：MCR
- vignette 决定性线索（账本）：slow painless bilateral hard-palate swelling；no nodes or systemic symptoms；excisional pathology expected to define lymphoma
- 缺失限定词（账本）：oral extranodal presentation；cyclin D1/SOX11 or t(11;14)；distinction from benign palatal lesions
- 前轮鉴别点：cyclin D1 / SOX11 / t(11;14) on a palatal biopsy
- 指南中有：partial　vignette 中有：no　方法抽取到：no　用对：no　失败模式：benchmark

### 四方法最终答案

- collapse3c：Torus Palatinus（召回 miss）
- multistance：Giant Cell Granuloma（召回 set_strong）
- impc：Torus Palatinus（召回 miss）
- forest：Torus palatinus（召回 miss）

### 待分离的假设集（16 个）

- Torus Palatinus ← collapse3c,forest,impc,multistance
- Giant Cell Granuloma ← collapse3c,impc,multistance
- Torus palatinus ← forest,impc,multistance
- Fibroma ← forest,multistance
- Giant Cell Lesion ← forest,impc
- Palatal Abscess ← collapse3c,multistance
- Squamous Cell Carcinoma ← collapse3c,multistance
- Giant Cell Tumor ← forest
- Granuloma ← multistance
- Granulomatosis with Polyangiitis ← collapse3c
- Lymphoma ← multistance
- Palatal Fibroma ← impc
- Palatal Torus ← forest
- Palatal fibroma ← impc
- Pyogenic Granuloma ← multistance
- Squamous cell carcinoma ← multistance

### vignette

```
A 41-year-old man with no significant medical history presented with a 10–12-week history of a painless swelling in the molar region of the hard palate that had grown slowly and symmetrically. He denied dysphagia, odynophagia, or systemic symptoms. Family history was unremarkable. On examination, there was a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar area. No cervical lymphadenopathy was detected. Routine serum chemistry, including lactate dehydrogenase (3.95 μmol/l) and albumin (61%), was within normal limits. Serologies for hepatitis A, B, and C were negative. During excision, the palatal bone appeared uninvolved, and the wound healed slowly over 4–5 weeks.

What is the most likely diagnosis?

Options:
A. Mantle cell lymphoma
B. due to the lesion’s slow growth, symmetry, and normal mucosal covering
C. Dento
D. A benign palatal tumor (epithelial hyperplasia or lipoma) was suspected due to the lesion’s slow growth, symmetry, and
E. None
F. None
G. None
H. None
```

---

## MCR_v2_seq100/234 — SpindleCellHemangioma

- 语料判级：D1_parent_component_or_list_only　家族：MCR
- vignette 决定性线索（账本）：adult frontal-bone lytic mass；soap-bubble cortical destruction；avid enhancement；painless circumscribed lesion
- 缺失限定词（账本）：spindle-cell hemangioma entity；osseous/frontal location；histologic spindle and cavernous components
- 前轮鉴别点：histology of the frontal-bone lesion
- 指南中有：no　vignette 中有：no　方法抽取到：no　用对：no　失败模式：benchmark

### 四方法最终答案

- collapse3c：Aneurysmal bone cyst（召回 miss）
- multistance：Giant cell tumor（召回 top2_strong）
- impc：Giant Cell Tumor（召回 miss）
- forest：Giant Cell Tumor（召回 miss）

### 待分离的假设集（15 个）

- Ewing's Sarcoma ← forest,impc,multistance
- Giant Cell Tumor ← forest,impc,multistance
- Osteomyelitis ← collapse3c,impc,multistance
- Aneurysmal bone cyst ← collapse3c,multistance
- Brown Tumor ← forest,impc
- Brown tumor of hyperparathyroidism ← collapse3c,multistance
- Eosinophilic Granuloma ← forest,impc
- Fibrous dysplasia ← collapse3c,multistance
- Giant cell tumor ← collapse3c,multistance
- Osteoma ← forest,multistance
- Fibrous Dysplasia ← forest
- Hemangioma ← multistance
- Metastatic bone disease ← multistance
- Multiple myeloma ← multistance
- Osteolytic lesion ← impc

### vignette

```
A 50-year-old man presented with a 2-month history of a painless mass on the right side of the frontal bone. On examination, the mass measured approximately 4.0 × 3.5 cm, was well circumscribed, soft, nonmobile, and non-tender. Laboratory studies and neurologic examination were unremarkable.

Plain radiography of the skull showed a large, circumscribed radiolucent lesion in the right frontal bone without adjacent soft-tissue swelling. CT of the head demonstrated a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer tables, and an associated soft-tissue component. Contrast-enhanced MRI revealed a lobulated frontal-bone mass measuring 3.7 × 3.3 × 2.8 cm that was hypointense on T1-weighted images, hyperintense on T2-weighted images, and showed avid enhancement on postcontrast sequences.

What is the most likely diagnosis?

Options:
A. SpindleCellHemangioma
B. Eosinophilic granuloma
C. Metastatic tumor
D. Low
E. Spindle cell hemangioma
F. None
G. None
H. None
```

---

