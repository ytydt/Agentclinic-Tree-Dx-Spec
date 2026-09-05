# 断言 → 原文 → vignette 命中项 证据包

## DA_d2_heldout200b/522

- 金标：`Catatonia related to underlying Lewy body dementia`
- 候选集中被判为金标等价的标签：['Catatonia', 'Dementia']
- 引擎 top-1：`Delirium`（金标排名 2）

### `Delirium` — top-1（竞争假设），得分 6.15，接合 15/186 条

**断言** `delirium` —[required_for/asserted/obligatory]→ `baseline mental status`

- 出处：`statpearls` / Cognitive assessment and differentiating the 3 Ds (dementia, depression, delirium). > History and Physical · context_type=`criteria`
- 原文：…delirium and dementia. Obtaining a history from both patients and family members is essential. The first step would be to get the patient's baseline mental and functional status. The second step would be to assess the acuity of the symptom onset, following which a timeline of progression needs to be established. Onc…
- 抽取所据引语：“baseline mental and functional status”
- **命中 vignette 项**：`progressive decline in mental status`（canonical=`mental status decline`，极性 `present`，接合方式 `overlap`）
- vignette 原句：“progressive decline in mental status”
- 引擎影响：required_for/asserted/present，Δ=1.0

**断言** `Hyperactive Delirium` —[feature_of/asserted/typical]→ `hallucinations`

- 出处：`statpearls` / Prevention and Management of Delirium in the Intensive Care Unit. > Assessment · context_type=`definition`
- 原文：…n 3 main manifestations.
1) Hyperactive Delirium: Patients present with increased agitation and sympathetic activity. They can present with hallucinations, delusions, and occasionally combative or uncooperative behavior.
- 抽取所据引语：“hallucinations”
- **命中 vignette 项**：`visual hallucinations`（canonical=`visual hallucinations`，极性 `present`，接合方式 `containment`）
- vignette 原句：“visual hallucinations”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Hyperactive Delirium` —[feature_of/asserted/typical]→ `delusions`

- 出处：`statpearls` / Prevention and Management of Delirium in the Intensive Care Unit. > Assessment · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“delusions”
- **命中 vignette 项**：`paranoid delusions`（canonical=`paranoid delusions`，极性 `present`，接合方式 `containment`）
- vignette 原句：“paranoid delusions”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Delirium` —[feature_of/asserted/typical]→ `inappropriate or unsafe behavior`

- 出处：`statpearls` / Prevention and Management of Delirium in the Intensive Care Unit. > History and Physical · context_type=`definition`
- 原文：Other features include alterations in the sleep-wake cycle, perceptual disturbances, delusions, inappropriate or unsafe behavior, and emotional lability.[19] Detection is the first step in evaluation and treatment. The syndrome of delirium presents for hours to days.…
- 抽取所据引语：“inappropriate or unsafe behavior”
- **命中 vignette 项**：`abnormal behaviors`（canonical=`abnormal behaviors`，极性 `present`，接合方式 `containment`）
- vignette 原句：“abnormal behaviors”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Hypoactive delirium` —[feature_of/asserted/typical]→ `withdrawn behavior`

- 出处：`statpearls` / Prevention and Management of Delirium in the Intensive Care Unit. > History and Physical · context_type=`definition`
- 原文：…ases. Hyperactive delirium is much easier to detect because patients are often agitated. However, hypoactive delirium is usually missed, as patients are more withdrawn. Caregivers may provide clues to the presence of hypoactive delirium with comments such as "They are sleeping more than usual," "They haven…
- 抽取所据引语：“patients are more withdrawn”
- **命中 vignette 项**：`abnormal behaviors`（canonical=`abnormal behaviors`，极性 `present`，接合方式 `containment`）
- vignette 原句：“abnormal behaviors”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Delirium` —[feature_of/asserted/typical]→ `inattention`

- 出处：`pmc_oa` / The agitated older adult in the emergency department: a narrative review of common causes and management strategies. › The agitated older adult in the emergency department: a narrative review of common causes and management strategies. > CAUSES OF AGITATION IN OLDER ADULTS > Delirium · context_type=`definition`
- 原文：…a number of diagnostic and screening tools available for use in the ED, 23 , 24 , 25 , 26 all of which include formal tests of attention as inattention is one of the defining features of delirium. Nonetheless, delirium is missed in the ED in up to 67% to 75% of cases. 27 , 28 This is in part due to the short duration of time during w…
- 抽取所据引语：“inattention is one of the defining features of delirium”
- **命中 vignette 项**：`inattention`（canonical=`inattention`，极性 `present`，接合方式 `exact`）
- vignette 原句：“Inattention”
- 引擎影响：feature_of/asserted/present，Δ=0.8

### `Catatonia` — 金标，得分 4.0，接合 5/145 条

**断言** `Catatonia` —[feature_of/asserted/typical]→ `echopraxia`

- 出处：`statpearls` / Schizophrenia with prominent catatonic features: A selective review. > History and Physical · context_type=`definition`
- 原文：…or categories: 1. Motor signs (such as immobility) 2. Behavioral signs (negativism) 3. Autonomic instability (tachycardia, hyperthermia) 4. Inability to suppress motor functions (stereotypy, echolalia, echopraxia).[16]
- 抽取所据引语：“Inability to suppress motor functions (stereotypy, echolalia, echopraxia)”
- **命中 vignette 项**：`echopraxia`（canonical=`echopraxia`，极性 `present`，接合方式 `exact`）
- vignette 原句：“Echopraxia”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Akinetic catatonia` —[feature_of/asserted/typical]→ `mutism`

- 出处：`statpearls` / On the etiology of dementia praecox; a partial review of the literature, 1935 to 1945 and an attempt at conceptualization. > History and Physical · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“mutism”
- **命中 vignette 项**：`mutism`（canonical=`mutism`，极性 `present`，接合方式 `exact`）
- vignette 原句：“Mutism”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Akinetic catatonia` —[feature_of/asserted/typical]→ `staring`

- 出处：`statpearls` / On the etiology of dementia praecox; a partial review of the literature, 1935 to 1945 and an attempt at conceptualization. > History and Physical · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“staring”
- **命中 vignette 项**：`staring`（canonical=`staring`，极性 `present`，接合方式 `exact`）
- vignette 原句：“Staring”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Akinetic catatonia` —[feature_of/asserted/typical]→ `decreased speech`

- 出处：`statpearls` / On the etiology of dementia praecox; a partial review of the literature, 1935 to 1945 and an attempt at conceptualization. > History and Physical · context_type=`definition`
- 原文：…tures may be mundane (eg, sitting or standing in the same position for hours) or unusual (eg, head raised above the bed as if on a pillow). Speech, spontaneous movements, and response to voice or noxious stimuli are decreased. Alertness and awareness may vary. In more severe cases, eating and drinking may cease, and stupor and incontinence may occur.[32]
- 抽取所据引语：“Speech, spontaneous movements, and response to voice or noxious stimuli are decreased”
- **命中 vignette 项**：`limited speech`（canonical=`limited speech`，极性 `present`，接合方式 `containment`）
- vignette 原句：“Limited speech”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `catatonia` —[feature_of/asserted/typical]→ `change in movement and behavior`

- 出处：`statpearls` / On the etiology of dementia praecox; a partial review of the literature, 1935 to 1945 and an attempt at conceptualization. > History and Physical · context_type=`definition`
- 原文：…hdrawal from the senses and the environment in the context of a psychotic or mood disorder.[25] In general, catatonia is characterized by a change in movement and behavior, either increased, decreased, or abnormal, compared to baseline, in the context of intact physical capacity for motor movement.[25] Cataton…
- 抽取所据引语：“change in movement and behavior”
- **命中 vignette 项**：`abnormal behaviors`（canonical=`abnormal behaviors`，极性 `present`，接合方式 `containment`）
- vignette 原句：“abnormal behaviors”
- 引擎影响：feature_of/asserted/present，Δ=0.8

### `Dementia` — 金标，得分 5.6，接合 9/166 条

**断言** `Dementia with Lewy bodies` —[feature_of/asserted/typical]→ `prominent visual hallucinations`

- 出处：`textbooks` / InternalMed_Harrison · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“A form of dementia with parkinsonism, termed dementia with Lewy bodies, is characterized by ... prominent visual hallucinations”
- **命中 vignette 项**：`visual hallucinations`（canonical=`visual hallucinations`，极性 `present`，接合方式 `containment`）
- vignette 原句：“visual hallucinations”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Frontotemporal Dementia` —[feature_of/asserted/typical]→ `disinhibited social behavior`

- 出处：`statpearls` / The basics of brain development. > Clinical Significance · context_type=`definition`
- 原文：…P-43). The clinical manifestations of FTD vary depending on the location of degeneration but often encompass prominent personality changes, disinhibited social behavior, aphasia, and can even be associated with motor neuron disease. The core spectrum of FTD disorders includes behavioral variant FTD (bvFTD),…
- 抽取所据引语：“disinhibited social behavior”
- **命中 vignette 项**：`abnormal behaviors`（canonical=`abnormal behaviors`，极性 `present`，接合方式 `containment`）
- vignette 原句：“abnormal behaviors”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Dementia with Lewy bodies` —[feature_of/asserted/typical]→ `rapid eye movement sleep behavior disorder (RBD)`

- 出处：`statpearls` / [Parkinson "plus"]. > History and Physical · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“rapid eye movement sleep behavior disorder (RBD)”
- **命中 vignette 项**：`abnormal behaviors`（canonical=`abnormal behaviors`，极性 `present`，接合方式 `containment`）
- vignette 原句：“abnormal behaviors”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Dementia` —[feature_of/asserted/typical]→ `delusions`

- 出处：`statpearls` / Classifying neurocognitive disorders: the DSM-5 approach. > Introduction · context_type=`definition`
- 原文：…Behavioral and psychological symptoms of dementia, or BPSD, are neuropsychiatric symptoms that accompany the syndrome of dementia, such as delusions, hallucinations, apathy, anxiety, depression, or disinhibition. BPSD symptoms are prevalent and can significantly impact the prognosis and management of dementia. BPSD includes emotional, perceptual, an…
- 抽取所据引语：“delusions, hallucinations, apathy, anxiety, depression, or disinhibition”
- **命中 vignette 项**：`paranoid delusions`（canonical=`paranoid delusions`，极性 `present`，接合方式 `containment`）
- vignette 原句：“paranoid delusions”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Lewy Body Dementia` —[feature_of/asserted/typical]→ `REM sleep behavior disorder`

- 出处：`merck` / Chapter 175. Delirium & Dementia > As the disease progresses, focal neurologic deficits often develop: > Treatment › Chapter 175. Delirium & Dementia > As the disease progresses, focal neurologic deficits often develop: > Treatment · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“Many patients have rapid eye movement (REM) sleep behavior disorder”
- **命中 vignette 项**：`abnormal behaviors`（canonical=`abnormal behaviors`，极性 `present`，接合方式 `containment`）
- vignette 原句：“abnormal behaviors”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Lewy body dementia` —[feature_of/asserted/typical]→ `hallucination`

- 出处：`statpearls` / Branches of the anterior cerebral artery near the anterior communicating artery complex: an anatomic study and surgical perspective. > Other Issues · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“Lewy body dementia is dementia and hallucination”
- **命中 vignette 项**：`visual hallucinations`（canonical=`visual hallucinations`，极性 `present`，接合方式 `containment`）
- vignette 原句：“visual hallucinations”
- 引擎影响：feature_of/asserted/present，Δ=0.8

## DA_d2_heldout200b/773

- 金标：`Idiopathic Pulmonary Arterial Hypertension (IPAH) with Patent Foramen Ovale (PFO)`
- 候选集中被判为金标等价的标签：['Idiopathic Pulmonary Arterial Hypertension', 'Patent Foramen Ovale', 'Pulmonary Arterial Hypertension']
- 引擎 top-1：`Chronic Thromboembolic Pulmonary Hypertension`（金标排名 6）

### `Chronic Thromboembolic Pulmonary Hypertension` — top-1（竞争假设），得分 11.525，接合 15/103 条

**断言** `Pulmonary Hypertension` —[feature_of/asserted/obligatory]→ `mean pulmonary artery pressure`，阈值 `{'operator': '>', 'value': 25, 'unit': 'mmHg'}`

- 出处：`statpearls` / Obstetric anesthesia management of the patient with cardiac disease. > Clinical Significance · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“mean pulmonary artery pressure of greater than 25 mmHg at rest”
- **命中 vignette 项**：`pulmonary artery pressure`（canonical=`pulmonary artery pressure`，极性 `present`，值 60mmHg，接合方式 `containment`）
- vignette 原句：“Pulmonary artery pressure was 60/39 mmHg”
- 引擎影响：feature_of/asserted/present，Δ=1.5

**断言** `Pulmonary Hypertension` —[required_for/asserted/obligatory]→ `mean pulmonary artery pressure (mPAP) greater than 30 mm Hg`，阈值 `{'operator': '>', 'value': 30, 'unit': 'mm Hg'}`

- 出处：`statpearls` / High-altitude Pulmonary Hypertension: an Update on Disease Pathogenesis and Management. > Evaluation · context_type=`criteria`
- 原文：（未能定位回段落）
- 抽取所据引语：“mPAP greater than 30 mm Hg”
- **命中 vignette 项**：`pulmonary artery pressure`（canonical=`pulmonary artery pressure`，极性 `present`，值 60mmHg，接合方式 `containment`）
- vignette 原句：“Pulmonary artery pressure was 60/39 mmHg”
- 引擎影响：required_for/asserted/present，Δ=1.0

**断言** `Pulmonary Hypertension` —[required_for/asserted/obligatory]→ `systolic pulmonary artery pressure (sPAP) greater than 50 mm Hg`，阈值 `{'operator': '>', 'value': 50, 'unit': 'mm Hg'}`

- 出处：`statpearls` / High-altitude Pulmonary Hypertension: an Update on Disease Pathogenesis and Management. > Evaluation · context_type=`criteria`
- 原文：（未能定位回段落）
- 抽取所据引语：“sPAP greater than 50 mm Hg”
- **命中 vignette 项**：`pulmonary artery systolic pressure`（canonical=`pulmonary artery systolic pressure`，极性 `present`，值 55mmHg，接合方式 `containment`）
- vignette 原句：“Estimated pulmonary artery systolic pressure of 55 mmHg in 2021”
- 引擎影响：required_for/asserted/present，Δ=1.0

**断言** `Pulmonary Hypertension` —[required_for/asserted/obligatory]→ `mean pulmonary artery pressure (mPAP) greater than 25 mm Hg`，阈值 `{'operator': '>', 'value': 25, 'unit': 'mm Hg'}`

- 出处：`statpearls` / High-altitude Pulmonary Hypertension: an Update on Disease Pathogenesis and Management. > Evaluation · context_type=`criteria`
- 原文：（未能定位回段落）
- 抽取所据引语：“mPAP greater than 25 mm Hg”
- **命中 vignette 项**：`pulmonary artery pressure`（canonical=`pulmonary artery pressure`，极性 `present`，值 60mmHg，接合方式 `containment`）
- vignette 原句：“Pulmonary artery pressure was 60/39 mmHg”
- 引擎影响：required_for/asserted/present，Δ=1.0

**断言** `Pulmonary Hypertension` —[required_for/asserted/obligatory]→ `mean pulmonary artery pressure (mPAP) greater than 20 mm Hg`，阈值 `{'operator': '>', 'value': 20, 'unit': 'mm Hg'}`

- 出处：`statpearls` / High-altitude Pulmonary Hypertension: an Update on Disease Pathogenesis and Management. > Evaluation · context_type=`criteria`
- 原文：（未能定位回段落）
- 抽取所据引语：“mPAP greater than 20 mm Hg”
- **命中 vignette 项**：`pulmonary artery pressure`（canonical=`pulmonary artery pressure`，极性 `present`，值 60mmHg，接合方式 `containment`）
- vignette 原句：“Pulmonary artery pressure was 60/39 mmHg”
- 引擎影响：required_for/asserted/present，Δ=1.0

**断言** `Pulmonary Hypertension` —[feature_of/asserted/obligatory]→ `high pulmonary pressures`

- 出处：`statpearls` / 2022 ESC/ERS Guidelines for the diagnosis and treatment of pulmonary hypertension. > Introduction · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“high pulmonary pressures”
- **命中 vignette 项**：`pulmonary artery systolic pressure`（canonical=`pulmonary artery systolic pressure`，极性 `present`，值 55mmHg，接合方式 `containment`）
- vignette 原句：“Estimated pulmonary artery systolic pressure of 55 mmHg in 2021”
- 引擎影响：feature_of/asserted/present，Δ=1.0

### `Idiopathic Pulmonary Arterial Hypertension` — 金标，得分 1.6，接合 2/70 条

**断言** `Pulmonary Arterial Hypertension` —[feature_of/asserted/typical]→ `dilation of the pulmonary artery`

- 出处：`statpearls` / Pulmonary Valve Replacement for Pulmonary Regurgitation in Adults With Tetralogy of Fallot: A Meta-analysis-A Report for the Writing Committee of the 2019 Update of the Canadian Cardiovascular Society Guidelines for the Management of Adults With Congenital Heart Disease. > Etiology · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“Secondary or functional pulmonary regurgitation develops in individuals with a structurally normal pulmonary valve but who exhibit severe pulmonary arterial hypertension and dilation of the pulmonary artery”
- **命中 vignette 项**：`pulmonary artery pressure`（canonical=`pulmonary artery pressure`，极性 `present`，值 60mmHg，接合方式 `overlap`）
- vignette 原句：“Pulmonary artery pressure was 60/39 mmHg”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Pulmonary Arterial Hypertension` —[feature_of/asserted/typical]→ `elevated pulmonary arterial systolic pressure`

- 出处：`statpearls` / The definition of pulmonary hypertension: history, practical implications and current controversies. > Evaluation · context_type=`criteria`
- 原文：（未能定位回段落）
- 抽取所据引语：“elevated pulmonary arterial systolic pressure”
- **命中 vignette 项**：`pulmonary artery systolic pressure`（canonical=`pulmonary artery systolic pressure`，极性 `present`，值 55mmHg，接合方式 `overlap`）
- vignette 原句：“Estimated pulmonary artery systolic pressure of 55 mmHg in 2021”
- 引擎影响：feature_of/asserted/present，Δ=0.8

### `Patent Foramen Ovale` — 金标，得分 3.4，接合 4/73 条

**断言** `Patent Foramen Ovale` —[feature_of/asserted/obligatory]→ `foramen ovale`

- 出处：`statpearls` / Inner-ear decompression sickness in nine trimix recreational divers. > Continuing Education Activity · context_type=`definition`
- 原文：…dditionally, current guidelines recommend divers maintain a hemoglobin A1c below 9%.[7]
Patent Foramen Ovale and Septal Wall Defects
Patent foramen ovale (PFO), atrial, and ventricular septal defects create a right-to-left shunt in the heart. Thus, these findings theoretically increase the ri…
- 抽取所据引语：“foramen ovale”
- **命中 vignette 项**：`patent foramen ovale width`（canonical=`patent foramen ovale width`，极性 `present`，值 7.34mm，接合方式 `containment`）
- vignette 原句：“a patent foramen ovale measuring 7.34 mm in width”
- 引擎影响：feature_of/asserted/present，Δ=1.0

**断言** `Patent Foramen Ovale` —[feature_of/asserted/typical]→ `right-to-left shunt`

- 出处：`statpearls` / Cardiovascular and thermal responses to SCUBA diving. > Issues of Concern · context_type=`definition`
- 原文：…ving. Additionally, current guidelines recommend divers maintain a hemoglobin A1c below 9%.[7]
Patent Foramen Ovale and Septal Wall Defects
Patent foramen ovale (PFO), atrial, and ventricular septal defects create a right-to-left shunt in the heart. Thus, these findings theoretically increase the risk for DCS by creating a pathway for nitrogen bubbles to enter the systemic…
- 抽取所据引语：“Patent foramen ovale (PFO), atrial, and ventricular septal defects create a right-to-left shunt”
- **命中 vignette 项**：`right-to-left shunt`（canonical=`right-to-left shunt`，极性 `present`，接合方式 `exact`）
- vignette 原句：“with a continuous, pure right-to-left shunt on colour flow mapping”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Patent Foramen Ovale` —[feature_of/asserted/occasional]→ `right-to-left shunting`

- 出处：`statpearls` / Incidence of patent ductus arteriosus and patent foramen ovale in normal infants. > Continuing Education Activity · context_type=`definition`
- 原文：…ormally persists into adulthood. It represents a benign finding in the newborn periods. If PFO persists into adulthood, it usually leads to right-to-left shunting of deoxygenated blood, which can be symptomatic or asymptomatic. Additionally, if a PFO is present and venous thromboembolism (VTE) develops, the PFO can lead to…
- 抽取所据引语：“right-to-left shunting of deoxygenated blood”
- **命中 vignette 项**：`right-to-left shunt`（canonical=`right-to-left shunt`，极性 `present`，接合方式 `overlap`）
- vignette 原句：“with a continuous, pure right-to-left shunt on colour flow mapping”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Patent Foramen Ovale` —[caused_by/asserted/typical]→ `shunt`

- 出处：`statpearls` / Fetal Physiology and the Transition to Extrauterine Life. > Introduction · context_type=`definition`
- 原文：…t atrium, the fetal lungs are collapsed and bathed in amniotic fluid. They are not necessary for gas exchange during pregnancy.[1] In turn, the foramen ovale is the primary shunt to circumvent blood away from the lungs. The blood can pass through the right atrium and enter the left atrium through the foramen ovale through a pressure gradient. The collapse…
- 抽取所据引语：“the foramen ovale is the primary shunt to circumvent blood away from the lungs”
- **命中 vignette 项**：`right-to-left shunt`（canonical=`right-to-left shunt`，极性 `present`，接合方式 `containment`）
- vignette 原句：“with a continuous, pure right-to-left shunt on colour flow mapping”
- 引擎影响：caused_by/asserted/present，Δ=0.8

### `Pulmonary Arterial Hypertension` — 金标，得分 0.0，接合 0/14 条

（该候选没有任何断言接合到 vignette 发现）

## DA_d2_seq100/119

- 金标：`Eruptive pruritic papular porokeratosis (EPPP)`
- 候选集中被判为金标等价的标签：（无）
- 引擎 top-1：`Pityriasis rubra pilaris`（金标排名 None）

### `Pityriasis rubra pilaris` — top-1（竞争假设），得分 8.35，接合 11/127 条

**断言** `Seborrheic dermatitis` —[feature_of/asserted/typical]→ `parakeratosis`

- 出处：`statpearls` / Systemic lupus erythematosus. > Histopathology · context_type=`histopathology`
- 原文：（未能定位回段落）
- 抽取所据引语：“parakeratosis”
- **命中 vignette 项**：`parakeratosis`（canonical=`parakeratosis`，极性 `present`，接合方式 `exact`）
- vignette 原句：“Mild hyperkeratosis accompanied by parakeratosis”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `PRP` —[feature_of/asserted/typical]→ `normal or thickened granular layer`

- 出处：`statpearls` / Pityriasis Rubra Pilaris. > Histopathology · context_type=`histopathology`
- 原文：（未能定位回段落）
- 抽取所据引语：“the granular layer is normal or thickened under areas of parakeratosis”
- **命中 vignette 项**：`granular layer`（canonical=`granular layer`，极性 `present`，接合方式 `containment`）
- vignette 原句：“Well-developed cornoid lamellae with a decreased granular layer”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Type V PRP` —[feature_of/asserted/typical]→ `follicular hyperkeratosis`

- 出处：`statpearls` / Pityriasis Rubra Pilaris. > History and Physical · context_type=`definition`
- 原文：…s a chronic, generalized juvenile variant affecting 5% of patients. Griffiths described it in children in the first few years of life, with follicular hyperkeratosis, less prominent erythema, and occasional scleroderma-like changes of the hands. Type V PRP is sometimes used to describe all cases of inher…
- 抽取所据引语：“follicular hyperkeratosis”
- **命中 vignette 项**：`hyperkeratosis`（canonical=`hyperkeratosis`，极性 `present`，接合方式 `containment`）
- vignette 原句：“Mild hyperkeratosis accompanied by parakeratosis”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Pityriasis rubra pilaris` —[feature_of/asserted/typical]→ `severe pruritus`

- 出处：`statpearls` / Pityriasis Rubra Pilaris. > History and Physical · context_type=`definition`
- 原文：…mbs, anhidrosis (ie, lack of sweating), and difficulty with body temperature regulation. Common physical symptoms of widespread PRP include severe pruritus, a burning sensation in the involved skin, painful palmoplantar fissures, arthralgias, poor sleep, and fatigue. These symptoms may lead to…
- 抽取所据引语：“severe pruritus”
- **命中 vignette 项**：`pruritic papules`（canonical=`pruritus`，极性 `present`，接合方式 `containment`）
- vignette 原句：“intensively pruritic papules on her extremities”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Pityriasis Rubra Pilaris` —[feature_of/asserted/typical]→ `palmoplantar hyperkeratosis`

- 出处：`statpearls` / Pityriasis Rubra Pilaris. > History and Physical · context_type=`definition`
- 原文：…CARD14-associated papulosquamous eruption (CAPE).[26] The following are the subtypes of PRP:
The cardinal features across subtypes include palmoplantar hyperkeratosis and hyperkeratotic follicular papules coalescing into well-demarcated red-orange plaques. (see Image. Pityriasis Rubra Pilaris). Limited or…
- 抽取所据引语：“palmoplantar hyperkeratosis”
- **命中 vignette 项**：`hyperkeratosis`（canonical=`hyperkeratosis`，极性 `present`，接合方式 `containment`）
- vignette 原句：“Mild hyperkeratosis accompanied by parakeratosis”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Pityriasis rubra pilaris` —[supports_diagnosis/asserted/typical]→ `biopsy`

- 出处：`merck` / Chapter 78. Psoriasis & Scaling Diseases > Well-identified triggers include > Treatment › Chapter 78. Psoriasis & Scaling Diseases > Well-identified triggers include > Treatment · context_type=`definition`
- 原文：…s rubra pilaris is unknown.
Atypical forms exist in both age groups. Sunlight can trigger a flare.

Diagnosis is by clinical appearance and may be supported by biopsy. Differential diagnosis includes

seborrheic dermatitis (in children) and psoriasis when disease occurs on the scalp, elbows, and knees.

T…
- 抽取所据引语：“may be supported by biopsy”
- **命中 vignette 项**：`skin biopsy`（canonical=`skin biopsy`，极性 `present`，接合方式 `containment`）
- vignette 原句：“Skin biopsy revealed”
- 引擎影响：supports_diagnosis/asserted/present，Δ=0.8

## MCR_seq200b/257

- 金标：`collar button abscess`
- 候选集中被判为金标等价的标签：['Abscess']
- 引擎 top-1：`Septic Arthritis`（金标排名 4）

### `Septic Arthritis` — top-1（竞争假设），得分 5.6，接合 12/114 条

**断言** `Septic Arthritis` —[feature_of/asserted/typical]→ `synovial WBC count >50 000 cells/L`，阈值 `{'operator': '>', 'value': 50000, 'unit': 'cells/L'}`

- 出处：`pmc_oa` / Test characteristics of history, examination and investigations in the evaluation for septic arthritis in the child presenting with acute non-traumatic limp. A systematic review. › Test characteristics of history, examination and investigations in the evaluation for septic arthritis in the child presenting with acute non-traumatic limp. A systematic review. > Results · context_type=`criteria`
- 原文：…f the hip, lateral development of rheumatological disease or Perthes disease or associated proximal femoral osteomyelitis Culture-positive (synovial WBC count >50 000 cells/L with positive blood culture) or culture-negative septic arthritis (synovial WBC count count >50 000 cells/L with negative blood culture) Sy…
- 抽取所据引语：“synovial WBC count >50 000 cells/L”
- **命中 vignette 项**：`WBC count`（canonical=`wbc count`，极性 `present`，值 17.5× 10^9/L，接合方式 `containment`）
- vignette 原句：“WBC count was 17.5 × 10^9/L”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Septic Arthritis` —[feature_of/asserted/typical]→ `elevated WBC count`

- 出处：`pmc_oa` / Test characteristics of history, examination and investigations in the evaluation for septic arthritis in the child presenting with acute non-traumatic limp. A systematic review. › Test characteristics of history, examination and investigations in the evaluation for septic arthritis in the child presenting with acute non-traumatic limp. A systematic review. > Results · context_type=`criteria`
- 原文：…logical culture (blood, synovial fluid aspiration OR bone aspiration)) or presumed infection (purulent aspiration or positive bone scan AND elevated WBC count or CRP, but negative cultures)† Children presenting with a limp and reduced ROM with ‘normal’ laboratory and radiographic findings and symp…
- 抽取所据引语：“elevated WBC count”
- **命中 vignette 项**：`WBC count`（canonical=`wbc count`，极性 `present`，值 17.5× 10^9/L，接合方式 `containment`）
- vignette 原句：“WBC count was 17.5 × 10^9/L”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `ACJ septic arthritis` —[feature_of/asserted/characteristic]→ `erythema`

- 出处：`statpearls` / The Orientation and Variation of the Acromioclavicular Ligament: An Anatomic Study. > Clinical Significance · context_type=`definition`
- 原文：…c arthritis can lead to significant mortality and morbidity. The condition can easily be confused with septic glenohumeral joint arthritis. Pain and erythema overlying the ACJ are characteristic.[28] ACJ septic arthritis is rare but mostly affects immunocompromised patients and men in the 5th and 6th decades of life.
- 抽取所据引语：“Pain and erythema overlying the ACJ are characteristic”
- **命中 vignette 项**：`right hand erythema`（canonical=`hand erythema`，极性 `present`，接合方式 `containment`）
- vignette 原句：“erythema”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Septic Arthritis` —[feature_of/asserted/typical]→ `swelling`

- 出处：`statpearls` / The burden of septic arthritis on the U.S. inpatient care: A national study. > History and Physical · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“swelling”
- **命中 vignette 项**：`right hand swelling`（canonical=`hand swelling`，极性 `present`，接合方式 `containment`）
- vignette 原句：“swelling”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Purulent (septic) arthritis syndrome` —[feature_of/asserted/typical]→ `limited range of motion`

- 出处：`statpearls` / Gonorrhoea. > History and Physical · context_type=`definition`
- 原文：…itis involving 1 or occasionally multiple joints. The affected joint is characteristically painful, swollen, warm, and erythematous, with a limited range of motion. The knee is most commonly involved, followed by the wrist, ankle, and elbow.[13]
- 抽取所据引语：“limited range of motion”
- **命中 vignette 项**：`limited active digit motion`（canonical=`limited motion`，极性 `present`，接合方式 `containment`）
- vignette 原句：“limited active digit motion”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Gout` —[risk factor for/asserted/typical]→ `advancing age`

- 出处：`statpearls` / Acute monoarthritis: what is the cause of my patient's painful swollen joint? > Etiology · context_type=`definition`
- 原文：…y are not able to get rid of all the uric acid that is produced in them as a result of endogenous or exogenous purine metabolism. Male sex, advancing age, chronic kidney disease, alcoholism, and certain drugs such as the diuretics are additional risk factors for hyperuricemia and gout.
Septic…
- 抽取所据引语：“advancing age”
- **命中 vignette 项**：`age`（canonical=`age`，极性 `present`，值 66years，接合方式 `containment`）
- vignette 原句：“66-year-old”
- 引擎影响：risk factor for/asserted/present，Δ=0.8

### `Abscess` — 金标，得分 1.6，接合 5/114 条

**断言** `Abscess` —[feature_of/asserted/typical]→ `pain`

- 出处：`statpearls` / Pseudocyst of the scalp. > Clinical Significance · context_type=`clinical_significance`
- 原文：…cess formation, epidermal inclusion cysts are the most frequent culprit.[75][76][77] The rupture of an epidermal inclusion cyst may lead to pain and swelling, requiring surgical intervention. Rarely, soft tissue extension, cellulitis, and even necrotizing fasciitis have been reported.[78] Dermoid…
- 抽取所据引语：“pain and swelling”
- **命中 vignette 项**：`right hand pain`（canonical=`hand pain`，极性 `present`，接合方式 `containment`）
- vignette 原句：“worsening right hand pain”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Abscess` —[feature_of/asserted/typical]→ `swelling`

- 出处：`statpearls` / Pseudocyst of the scalp. > Clinical Significance · context_type=`clinical_significance`
- 原文：…cess formation, epidermal inclusion cysts are the most frequent culprit.[75][76][77] The rupture of an epidermal inclusion cyst may lead to pain and swelling, requiring surgical intervention. Rarely, soft tissue extension, cellulitis, and even necrotizing fasciitis have been reported.[78] Dermoid…
- 抽取所据引语：“pain and swelling”
- **命中 vignette 项**：`right hand swelling`（canonical=`hand swelling`，极性 `present`，接合方式 `containment`）
- vignette 原句：“swelling”
- 引擎影响：feature_of/asserted/present，Δ=0.8

## MCR_seq200b/326

- 金标：`Brucellosis`
- 候选集中被判为金标等价的标签：['Brucellosis']
- 引擎 top-1：`Spinal Epidural Abscess`（金标排名 5）

### `Spinal Epidural Abscess` — top-1（竞争假设），得分 15.625，接合 24/123 条

**断言** `Spinal Epidural Abscess` —[feature_of/asserted/typical]→ `back pain`

- 出处：`textbooks` / InternalMed_Harrison · context_type=`definition`
- 原文：…ervertebral disk can also be affected by infection (diskitis) and, very rarely, by tumor.
Spinal epidural abscess (Chap. 456) presents with back pain (aggravated by movement or palpation), fever, radiculopathy, or signs of spinal cord compression. The subacute development of two or more of these findings should increase the i…
- 抽取所据引语：“back pain (aggravated by movement or palpation)”
- **命中 vignette 项**：`back pain`（canonical=`back pain`，极性 `present`，接合方式 `exact`）
- vignette 原句：“back pain”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Spinal Epidural Abscess` —[feature_of/asserted/typical]→ `low-grade fever`

- 出处：`textbooks` / Neurology_Adams · context_type=`definition`
- 原文：…r, even if the latter has been adequately treated.
At first, the purulent process in the cervical or thoracic region is accompanied only by low-grade fever and aching local back pain, usually intense, in most cases followed within a day or several days by radicular pain. Headache and nuchal rig…
- 抽取所据引语：“low-grade fever”
- **命中 vignette 项**：`high fever`（canonical=`fever`，极性 `present`，接合方式 `containment`）
- vignette 原句：“high fever”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Spinal Epidural Abscess` —[feature_of/asserted/typical]→ `elevated C-reactive protein`

- 出处：`statpearls` / Brain and Spinal Epidural Abscess. > Treatment / Management · context_type=`definition`
- 原文：Laboratory findings for these patients are typically nonspecific. Patients may have mild leukocytosis and elevated C-reactive protein. Blood cultures are positive in SEA but not so in IEA. Conventional radiography of the spine may not be helpful in SEA, as osseous destruct…
- 抽取所据引语：“elevated C-reactive protein”
- **命中 vignette 项**：`C-reactive protein level`（canonical=`c-reactive protein`，极性 `present`，值 3.19mg/dL，接合方式 `containment`）
- vignette 原句：“C-reactive protein level of 3.19 mg/dL”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Spinal Epidural Abscess` —[feature_of/asserted/typical]→ `fever`

- 出处：`textbooks` / InternalMed_Harrison · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“fever”
- **命中 vignette 项**：`high fever`（canonical=`fever`，极性 `present`，接合方式 `exact`）
- vignette 原句：“high fever”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Spinal Epidural Abscess` —[feature_of/asserted/typical]→ `midline back pain`

- 出处：`statpearls` / Medical and surgical management of spinal epidural abscess: a systematic review. > Introduction · context_type=`definition`
- 原文：…periosteum.[1] Giovanni Morgagni first described SEA in 1761.[2] Although classically, patients with spinal epidural abscesses present with midline back pain, fever, and neurologic deficits, other presentations of this disease process can be highly variable. A spinal epidural abscess is challengi…
- 抽取所据引语：“midline back pain”
- **命中 vignette 项**：`back pain`（canonical=`back pain`，极性 `present`，接合方式 `containment`）
- vignette 原句：“back pain”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Spinal Epidural Abscess` —[feature_of/asserted/typical]→ `midline back or neck pain`

- 出处：`textbooks` / InternalMed_Harrison · context_type=`definition`
- 原文：…ervicomedullary junction. Irregular peripheral enhancement occurs within the mass (arrows).
Spinal Epidural Abscess Spinal epidural abscess presents with midline back or neck pain, fever, and progressive limb weakness. Prompt recognition of this distinctive process may prevent permanent sequelae. Aching pain is almost…
- 抽取所据引语：“presents with midline back or neck pain”
- **命中 vignette 项**：`back pain`（canonical=`back pain`，极性 `present`，接合方式 `containment`）
- vignette 原句：“back pain”
- 引擎影响：feature_of/asserted/present，Δ=0.8

### `Brucellosis` — 金标，得分 2.8，接合 6/152 条

**断言** `Brucellosis` —[feature_of/asserted/obligatory]→ `fever`

- 出处：`textbooks` / InternalMed_Harrison · context_type=`definition`
- 原文：…eases their resistance to reactive oxygen intermediates. A hemolysin-like protein may trigger the release of brucellae from infected cells.
Brucellosis almost invariably causes fever, which may be associated with profuse sweats, especially at night. In endemic areas, brucellosis may be difficult to distinguish from the m…
- 抽取所据引语：“Brucellosis almost invariably causes fever”
- **命中 vignette 项**：`high fever`（canonical=`fever`，极性 `present`，接合方式 `exact`）
- vignette 原句：“high fever”
- 引擎影响：feature_of/asserted/present，Δ=1.0

**断言** `Brucellosis` —[required_for/asserted/obligatory]→ `blood culture`

- 出处：`statpearls` / Biowarfare, bioterrorism and biocrime: A historical overview on microbial harmful applications. > Clinical Significance · context_type=`criteria`
- 原文：…pheral neuropathy, radiculopathy, or cranial nerve palsies.[25] Death occurs in 2% of cases, with endocarditis being the most common cause.
Diagnose Brucellosis by blood or cerebrospinal fluid cultures and treat with doxycycline plus either rifampin or streptomycin; sulfamethoxazole/trimethoprim may be used instead of doxycycline in childr…
- 抽取所据引语：“Diagnose Brucellosis by blood or cerebrospinal fluid cultures”
- **命中 vignette 项**：`blood cultures`（canonical=`blood culture`，极性 `present`，接合方式 `exact`）
- vignette 原句：“blood cultures grew a Gram-negative bacillus”
- 引擎影响：required_for/asserted/present，Δ=1.0

**断言** `Brucellosis` —[feature_of/asserted/typical]→ `undulating fever pattern`

- 出处：`textbooks` / InternalMed_Harrison · context_type=`definition`
- 原文：…s recognized in the nineteenth century distinguish brucellosis from other tropical fevers, such as typhoid and malaria: (1) Left untreated, the fever of brucellosis shows an undulating pattern that persists for weeks before the commencement of an afebrile period that may be followed by relapse. (2) The fever of brucellosis is asso…
- 抽取所据引语：“the fever of brucellosis shows an undulating pattern”
- **命中 vignette 项**：`high fever`（canonical=`fever`，极性 `present`，接合方式 `containment`）
- vignette 原句：“high fever”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Brucellosis` —[feature_of/asserted/typical]→ `low-back or hip pain`

- 出处：`textbooks` / InternalMed_Harrison · context_type=`definition`
- 原文：…brile illness that resembles typhoid but is less severe; fever and acute monoarthritis, typically of the hip or knee, in a young child; and long-lasting fever, misery, and low-back or hip pain in an older man. In an endemic area (e.g., much of the Middle East), a patient with fever and difficulty walking into the clinic would be r…
- 抽取所据引语：“long-lasting fever, misery, and low-back or hip pain”
- **命中 vignette 项**：`back pain`（canonical=`back pain`，极性 `present`，接合方式 `containment`）
- vignette 原句：“back pain”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Brucellosis` —[feature_of/negated/occasional]→ `inflammatory syndrome`

- 出处：`pmc_oa` / Imaging clues for the diagnosis of various pathogenic causes of infectious spondylitis. › Imaging clues for the diagnosis of various pathogenic causes of infectious spondylitis. > Other less common bacterial infection > Brucellosis · context_type=`definition`
- 原文：…MRI features of this type of infectious spondylitis can be helpful, as biopsies and blood cultures often yield negative findings. Moreover, inflammatory syndrome (clinically and biologically) in patients with brucellar spondylitis is less frequent.
A sagittal computed tomography image (a) of the lumbosacral spine of a 70-year-old female patient with brucellar spondylitis. Bone erosion…
- 抽取所据引语：“inflammatory syndrome (clinically and biologically) in patients with brucellar spondylitis is less frequent”
- **命中 vignette 项**：`inflammatory lesion of T9 lamina`（canonical=`inflammatory lesion`，极性 `present`，接合方式 `containment`）
- vignette 原句：“inflammatory lesion of the T9 lamina”
- 引擎影响：feature_of/negated/present，Δ=-0.8

## MCR_seq200b/475

- 金标：`Parsonage Turner Syndrome`
- 候选集中被判为金标等价的标签：['Neuralgic Amyotrophy']
- 引擎 top-1：`Neuropathy`（金标排名 6）

### `Neuropathy` — top-1（竞争假设），得分 7.6，接合 11/266 条

**断言** `high median neuropathy` —[feature_of/asserted/typical]→ `inability to flex the index finger`

- 出处：`statpearls` / Normal Palmar Anatomy and Variations That Impact Median Nerve Decompression. > Clinical Significance · context_type=`definition`
- 原文：Median nerve injury at the elbow or forearm can result in a single-palmar-crease appearance. This finding reflects the combined inability to flex the index finger and distal phalanx of the thumb, weak flexion of the middle finger, and defective opposition of the thumb, all consistent with high median…
- 抽取所据引语：“inability to flex the index finger”
- **命中 vignette 项**：`inability to perform the "Ok" sign`（canonical=`ok sign inability`，极性 `present`，接合方式 `containment`）
- vignette 原句：“inability to perform the "Ok" sign”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Mononeuritis multiplex` —[feature_of/asserted/typical]→ `weakness`

- 出处：`pmc_oa` / A clinical approach to the investigation and management of long COVID associated neuropathic pain. › A clinical approach to the investigation and management of long COVID associated neuropathic pain. > Diagnostic evaluation · context_type=`criteria`
- 原文：…ed, frequent complication of ITU, both motor and sensory symptoms NCS/EMG: Axonal sensorimotor peripheral neuropathy Mononeuritis multiplex Numbness, weakness, pain, presence of risk factors NCS/EMG, HbA1c, vasculitis workup, viral workup, ACE, paraneoplastic screen AIDP/CIDP AIDP: Ascending paralysis, areflexia, motor, and sens…
- 抽取所据引语：“Numbness, weakness, pain, presence of risk factors”
- **命中 vignette 项**：`weakness of the left upper limb`（canonical=`upper limb weakness`，极性 `present`，接合方式 `containment`）
- vignette 原句：“weakness of the left upper limb”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `peripheral neuropathy` —[feature_of/asserted/typical]→ `atrophy`

- 出处：`statpearls` / [Peripheral neuropathies, from diagnosis to treatment, review of the literature and lessons from the local experience]. > Evaluation · context_type=`criteria`
- 原文：（未能定位回段落）
- 抽取所据引语：“atrophy”
- **命中 vignette 项**：`neurogenic atrophy of muscles innervated by the anterior interosseous nerve`（canonical=`neurogenic atrophy`，极性 `present`，接合方式 `containment`）
- vignette 原句：“neurogenic atrophy of muscles innervated by the anterior interosseous nerve”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Radial Neuropathy` —[feature_of/asserted/typical]→ `inability to extend the hand at the wrist`

- 出处：`statpearls` / Developmental biology of the upper limb. > Clinical Significance · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“A radial nerve lesion at any level above or in the forearm will cause an inability to extend the hand at the wrist”
- **命中 vignette 项**：`inability to perform the "Ok" sign`（canonical=`ok sign inability`，极性 `present`，接合方式 `containment`）
- vignette 原句：“inability to perform the "Ok" sign”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Radial Neuropathy` —[feature_of/asserted/typical]→ `finger extension weakness`

- 出处：`textbooks` / InternalMed_Harrison · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“wristdrop; finger extension weakness;”
- **命中 vignette 项**：`weakness of the middle phalanx of the index finger`（canonical=`index finger weakness`，极性 `present`，接合方式 `overlap`）
- vignette 原句：“weakness of the middle phalanx of the index finger”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Radial Neuropathy` —[feature_of/asserted/typical]→ `thumb abduction weakness`

- 出处：`textbooks` / InternalMed_Harrison · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“thumb abduction weakness;”
- **命中 vignette 项**：`weakness of the distal phalanx of the thumb`（canonical=`thumb weakness`，极性 `present`，接合方式 `containment`）
- vignette 原句：“weakness of the distal phalanx of the thumb”
- 引擎影响：feature_of/asserted/present，Δ=0.8

### `Neuralgic Amyotrophy` — 金标，得分 0.0，接合 4/53 条

**断言** `Neuralgic Amyotrophy` —[feature_of/asserted/typical]→ `weakness`

- 出处：`statpearls` / Brachial and Lumbosacral Plexopathies. > Clinical Significance · context_type=`definition`
- 原文：…sment, electrodiagnostic testing, and imaging when evaluating suspected neuralgic amyotrophy and other plexus disorders.[23] In many cases, disorders affecting peripheral nerves or the brachial plexus present with overlapping or nonspecific symptoms such as weakness, sensory disturbances, or pain. Electrodiagnostic testing can help differentiate among conditions that may produce similar clinical finding…
- 抽取所据引语：“disorders affecting peripheral nerves or the brachial plexus present with overlapping or nonspecific symptoms such as weakness”
- **命中 vignette 项**：`weakness of the left upper limb`（canonical=`upper limb weakness`，极性 `present`，接合方式 `containment`）
- vignette 原句：“weakness of the left upper limb”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Neuralgic amyotrophy` —[feature_of/asserted/typical]→ `sensory symptoms`

- 出处：`pmc_oa` / Don't be perplexed by the plexus! A practical approach to brachial plexus ultrasound. › Don't be perplexed by the plexus! A practical approach to brachial plexus ultrasound. > Neuralgic amyotrophy · context_type=`definition`
- 原文：…nage-Turner syndrome” as the disease often manifests beyond the brachial plexus. It is an inflammatory condition of unknown aetiology which leads to both motor and sensory symptoms, particularly in the periscapular region, though also more peripherally in the upper limb. The suprascapular nerve is the most frequently a…
- 抽取所据引语：“leads to both motor and sensory symptoms”
- **命中 vignette 项**：`sensory deficits`（canonical=`sensory deficit`，极性 `absent`，接合方式 `containment`）
- vignette 原句：“There were no sensory deficits”
- 引擎影响：feature_of/asserted/absent，Δ=-0.4

**断言** `Neuralgic Amyotrophy` —[distinguishes_from/asserted/typical]→ `MRI sensitivity`，comparator `ultrasound`

- 出处：`pmc_oa` / Don't be perplexed by the plexus! A practical approach to brachial plexus ultrasound. › Don't be perplexed by the plexus! A practical approach to brachial plexus ultrasound. > Current limitation with brachial plexus ultrasound · context_type=`differential`
- 原文：…ultrasound alone in helping to firm up a clinical diagnosis of inflammatory polyneuropathy.
Recognizing some cases of neuralgic amyotrophy. MRI generally is more sensitive than ultrasound, as MRI can recognize muscle oedema as an early feature of denervation with greater sensitivity than ultrasound. Potentially AI techniques…
- 抽取所据引语：“MRI generally is more sensitive than ultrasound”
- **命中 vignette 项**：`MRI of the left upper extremity`（canonical=`mri`，极性 `normal`，接合方式 `containment`）
- vignette 原句：“MRI of the left upper extremity was performed and showed no abnormalities”
- 引擎影响：feature_of/asserted/normal，Δ=-0.4

## MCR_v1_seq100/49

- 金标：`StumpAppendicitis`
- 候选集中被判为金标等价的标签：['Appendiceal stump appendicitis', 'Appendicitis']
- 引擎 top-1：`Abscess`（金标排名 2）

### `Abscess` — top-1（竞争假设），得分 5.3，接合 11/290 条

**断言** `Abscess` —[feature_of/asserted/typical]→ `pain`

- 出处：`statpearls` / Pseudocyst of the scalp. > Clinical Significance · context_type=`clinical_significance`
- 原文：…cess formation, epidermal inclusion cysts are the most frequent culprit.[75][76][77] The rupture of an epidermal inclusion cyst may lead to pain and swelling, requiring surgical intervention. Rarely, soft tissue extension, cellulitis, and even necrotizing fasciitis have been reported.[78] Dermoid…
- 抽取所据引语：“pain and swelling”
- **命中 vignette 项**：`right iliac fossa pain`（canonical=`abdominal pain`，极性 `present`，接合方式 `containment`）
- vignette 原句：“right iliac fossa pain”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `appendicitis` —[feature_of/asserted/typical]→ `abdominal pain`

- 出处：`textbooks` / Obstentrics_Williams · context_type=`definition`
- 原文：…s by Andersson (2001) and Ueberrueck (2004), the incidence of perforation was approximately 8, 12, and 20 percent in successive trimesters.
Persistent abdominal pain and tenderness are the most reproducible findings. Right-lower quadrant pain is the most frequent, although pain migrates upward with appendiceal displacement CMourad, 2000). For initial ev…
- 抽取所据引语：“Persistent abdominal pain and tenderness are the most reproducible findings”
- **命中 vignette 项**：`right iliac fossa pain`（canonical=`abdominal pain`，极性 `present`，接合方式 `exact`）
- vignette 原句：“right iliac fossa pain”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Intra-abdominal Abscess` —[feature_of/asserted/typical]→ `febrile episodes`

- 出处：`textbooks` / Gynecology_Novak · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“The evolving clinical picture is often one of persistent febrile episodes”
- **命中 vignette 项**：`febrile`（canonical=`fever`，极性 `present`，接合方式 `containment`）
- vignette 原句：“febrile”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Intra-abdominal Abscess` —[feature_of/asserted/typical]→ `rising white blood cell count`

- 出处：`textbooks` / Gynecology_Novak · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“The evolving clinical picture is often one of persistent febrile episodes with a rising white blood cell count.”
- **命中 vignette 项**：`white-blood-cell count`（canonical=`white blood cell count`，极性 `present`，值 25000cells/mm3，接合方式 `containment`）
- vignette 原句：“a white-blood-cell count of 25,000 cells/mm3”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Intra-abdominal Abscess` —[feature_of/asserted/typical]→ `persistent febrile episodes`

- 出处：`textbooks` / Gynecology_Novak · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“persistent febrile episodes”
- **命中 vignette 项**：`febrile`（canonical=`fever`，极性 `present`，接合方式 `containment`）
- vignette 原句：“febrile”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `peritonsillar abscess` —[feature_of/asserted/typical]→ `CT scan`

- 出处：`statpearls` / Variability in Antibiotic Prescribing for Upper Respiratory Illnesses by Provider Specialty. > Evaluation · context_type=`criteria`
- 原文：（未能定位回段落）
- 抽取所据引语：“a computed tomography (CT) scan may help identify a peritonsillar abscess”
- **命中 vignette 项**：`abdominal CT scan`（canonical=`abdominal ct scan`，极性 `present`，接合方式 `containment`）
- vignette 原句：“An abdominal CT scan demonstrated”
- 引擎影响：feature_of/asserted/present，Δ=0.8

### `Appendiceal stump appendicitis` — 金标，得分 2.4，接合 5/101 条

**断言** `Appendicitis` —[feature_of/asserted/typical]→ `febrile illness`

- 出处：`textbooks` / Surgery_Schwartz · context_type=`definition`
- 原文：with a febrile illness with imaging findings sugges-tive of an appendicolith or dilated appendix are classified as having chronic appendicitis.88 Patients often r…
- 抽取所据引语：“with a febrile illness”
- **命中 vignette 项**：`febrile`（canonical=`fever`，极性 `present`，接合方式 `containment`）
- vignette 原句：“febrile”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `appendicitis` —[feature_of/asserted/typical]→ `abdominal pain`

- 出处：`textbooks` / Obstentrics_Williams · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“Persistent abdominal pain and tenderness are the most reproducible findings”
- **命中 vignette 项**：`right iliac fossa pain`（canonical=`abdominal pain`，极性 `present`，接合方式 `exact`）
- vignette 原句：“right iliac fossa pain”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Abscesses` —[feature_of/asserted/typical]→ `tenderness`

- 出处：`merck` / Chapter 129. Biology of Infectious Disease > Serial blood cultures (ideally before antimicrobial therapy) > Key Points › Chapter 129. Biology of Infectious Disease > Serial blood cultures (ideally before antimicrobial therapy) > Key Points · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“Symptoms include local pain, tenderness”
- **命中 vignette 项**：`abdominal palpation pain`（canonical=`abdominal tenderness`，极性 `present`，接合方式 `containment`）
- vignette 原句：“Abdominal palpation elicited pain in the right lower quadrant”
- 引擎影响：feature_of/asserted/present，Δ=0.8

### `Appendicitis` — 金标，得分 4.0，接合 5/90 条

**断言** `Uncomplicated appendicitis` —[feature_of/asserted/typical]→ `intraluminal neutrophils`

- 出处：`statpearls` / Immediate surgery or conservative treatment for complicated acute appendicitis in children? A meta-analysis. > Histopathology · context_type=`histopathology`
- 原文：…racteristic features, including borderline-dilated serosal vessels, indicating increased appendiceal blood flow, and dulling of the serosa. Intraluminal neutrophils are another common finding. Furthermore, neutrophils may also be present within the mucosa and submucosa, and frank erosions may be seen. T…
- 抽取所据引语：“Intraluminal neutrophils”
- **命中 vignette 项**：`neutrophils`（canonical=`neutrophil percentage`，极性 `present`，值 85%，接合方式 `containment`）
- vignette 原句：“85% neutrophils”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Uncomplicated appendicitis` —[feature_of/asserted/typical]→ `neutrophils within the mucosa and submucosa`

- 出处：`statpearls` / Immediate surgery or conservative treatment for complicated acute appendicitis in children? A meta-analysis. > Histopathology · context_type=`histopathology`
- 原文：…, indicating increased appendiceal blood flow, and dulling of the serosa. Intraluminal neutrophils are another common finding. Furthermore, neutrophils may also be present within the mucosa and submucosa, and frank erosions may be seen. These findings indicate the presence of inflammation and tissue damage.[17]
Complicated Appendicitis
Compl…
- 抽取所据引语：“neutrophils may also be present within the mucosa and submucosa”
- **命中 vignette 项**：`neutrophils`（canonical=`neutrophil percentage`，极性 `present`，值 85%，接合方式 `containment`）
- vignette 原句：“85% neutrophils”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Complicated Appendicitis` —[feature_of/asserted/typical]→ `neutrophils within the mucosa, submucosa, and muscularis propria`

- 出处：`statpearls` / Immediate surgery or conservative treatment for complicated acute appendicitis in children? A meta-analysis. > Histopathology · context_type=`histopathology`
- 原文：…ood, indicating vascular congestion. Additionally, inflammation of the mesoappendix is observed, characterized by the presence of exudates. Neutrophils within the mucosa, submucosa, and muscularis propria indicate a widespread inflammatory response. Extensive ulceration, signifying tissue damage and loss of epithelial lining, is commonly obse…
- 抽取所据引语：“Neutrophils within the mucosa, submucosa, and muscularis propria”
- **命中 vignette 项**：`neutrophils`（canonical=`neutrophil percentage`，极性 `present`，值 85%，接合方式 `containment`）
- vignette 原句：“85% neutrophils”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Complicated Perforated Appendicitis` —[feature_of/asserted/typical]→ `neutrophils infiltrating the affected tissue`

- 出处：`statpearls` / Immediate surgery or conservative treatment for complicated acute appendicitis in children? A meta-analysis. > Histopathology · context_type=`histopathology`
- 原文：…the histopathological evaluation may exhibit features indicative of abscess formation, characterized by marked transmural inflammation and neutrophils infiltrating the affected tissue. The inflammation frequently extends beyond the appendix to involve the surrounding mesoappendix. Complicated perforated appendicitis is a…
- 抽取所据引语：“neutrophils infiltrating the affected tissue”
- **命中 vignette 项**：`neutrophils`（canonical=`neutrophil percentage`，极性 `present`，值 85%，接合方式 `containment`）
- vignette 原句：“85% neutrophils”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Appendicitis` —[feature_of/asserted/typical]→ `febrile illness`

- 出处：`textbooks` / Surgery_Schwartz · context_type=`definition`
- 原文：with a febrile illness with imaging findings sugges-tive of an appendicolith or dilated appendix are classified as having chronic appendicitis.88 Patients often r…
- 抽取所据引语：“with a febrile illness”
- **命中 vignette 项**：`febrile`（canonical=`fever`，极性 `present`，接合方式 `containment`）
- vignette 原句：“febrile”
- 引擎影响：feature_of/asserted/present，Δ=0.8

## MCR_v1_seq100/56

- 金标：`Spindle cell squamous cell carcinoma`
- 候选集中被判为金标等价的标签：['Carcinoma']
- 引擎 top-1：`Sarcoma`（金标排名 3）

### `Sarcoma` — top-1（竞争假设），得分 9.1，接合 15/192 条

**断言** `Pleomorphic sarcoma` —[feature_of/asserted/typical]→ `pleomorphic spindle cells`

- 出处：`statpearls` / Dermatopathology 101. Part 2 - Skin tumors. > Clinical Significance · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“Pleomorphic sarcoma is characterized by pleomorphic spindle cell sarcoma”
- **命中 vignette 项**：`atypical spindle cells`（canonical=`atypical cells`，极性 `present`，接合方式 `overlap`）
- vignette 原句：“atypical spindle and pleomorphic cells”
- 引擎影响：feature_of/asserted/present，Δ=1.0

**断言** `Kaposi sarcoma` —[feature_of/asserted/obligatory]→ `proliferating spindle cells`

- 出处：`statpearls` / Neoplasms of the hard palate. > Histopathology · context_type=`histopathology`
- 原文：（未能定位回段落）
- 抽取所据引语：“proliferating spindle cells”
- **命中 vignette 项**：`atypical spindle cells`（canonical=`atypical cells`，极性 `present`，接合方式 `overlap`）
- vignette 原句：“atypical spindle and pleomorphic cells”
- 引擎影响：feature_of/asserted/present，Δ=1.0

**断言** `Synovial Sarcoma` —[feature_of/asserted/typical]→ `spindle cells`

- 出处：`pmc_oa` / Imaging Evaluation of Bone Tumors in the Cervical Spine: A Comprehensive Review. › Imaging Evaluation of Bone Tumors in the Cervical Spine: A Comprehensive Review. > Malignant Primary Tumors > Synovial Sarcoma (SS) · context_type=`criteria`
- 原文：…y are gaining attention as adjuvant postoperative treatments.
Synovial sarcoma is a rare and aggressive malignant soft tissue tumor that is primarily composed of spindle cells and exhibits varying degrees of epithelial components. Despite its name, synovial sarcoma does not originate from synovial tissue. It is a…
- 抽取所据引语：“primarily composed of spindle cells”
- **命中 vignette 项**：`atypical spindle cells`（canonical=`atypical cells`，极性 `present`，接合方式 `containment`）
- vignette 原句：“atypical spindle and pleomorphic cells”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Synovial Sarcoma` —[feature_of/asserted/typical]→ `lytic bone destruction`

- 出处：`pmc_oa` / Imaging Evaluation of Bone Tumors in the Cervical Spine: A Comprehensive Review. › Imaging Evaluation of Bone Tumors in the Cervical Spine: A Comprehensive Review. > Malignant Primary Tumors > Synovial Sarcoma (SS) · context_type=`criteria`
- 原文：…hted imaging (T1WI) sagittal view shows the lesion with intermediate signal intensity. (E–G) CT scan without contrast shows the lesion with lytic bone destruction. (H) HE (×20) shows that tumor cells are spindle-shaped and amorphous (thick arrow), mostly exhibiting degenerative changes, with occasiona…
- 抽取所据引语：“lytic bone destruction”
- **命中 vignette 项**：`mandibular bone destruction`（canonical=`bone destruction`，极性 `present`，接合方式 `containment`）
- vignette 原句：“irregular mandibular bone destruction”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Synovial Sarcoma` —[feature_of/asserted/typical]→ `age 15-40`

- 出处：`pmc_oa` / Imaging Evaluation of Bone Tumors in the Cervical Spine: A Comprehensive Review. › Imaging Evaluation of Bone Tumors in the Cervical Spine: A Comprehensive Review. > Malignant Primary Tumors > Synovial Sarcoma (SS) · context_type=`criteria`
- 原文：…orted in case studies. Cervical spine synovial sarcoma can occur at any age but is more common in young and middle-aged individuals, with a peak incidence between 15 and 40 years. There was a slight male predominance. Clinically, it may present as a painless or slowly enlarging mass, eventually leading to pain or neu…
- 抽取所据引语：“peak incidence between 15 and 40 years”
- **命中 vignette 项**：`age`（canonical=`age`，极性 `present`，值 69years，接合方式 `containment`）
- vignette 原句：“69-year-old”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Vulvar Epithelioid Sarcoma` —[feature_of/asserted/typical]→ `youngest mean age at diagnosis`，阈值 `{'value': 31, 'unit': 'years'}`

- 出处：`statpearls` / Margins for cervical and vulvar cancer. > Histopathology · context_type=`histopathology`
- 原文：（未能定位回段落）
- 抽取所据引语：“Vulvar epithelioid sarcoma is diagnosed at the youngest mean age (31 years)”
- **命中 vignette 项**：`age`（canonical=`age`，极性 `present`，值 69years，接合方式 `containment`）
- vignette 原句：“69-year-old”
- 引擎影响：feature_of/asserted/present，Δ=0.8

### `Carcinoma` — 金标，得分 1.2，接合 8/180 条

**断言** `Squamous cell carcinoma` —[feature_of/asserted/typical]→ `p63`

- 出处：`statpearls` / Cancer treatment and survivorship statistics, 2016. > Pathophysiology · context_type=`definition`
- 原文：…ll pathology is defined by the presence of keratin and/or intercellular desmosomes on cytology or by immunohistochemistry (IHC) evidence of p40, p63, CK5, CK5/6, or desmoglein expression. Subtypes of squamous cell carcinoma include nonkeratinizing, keratinizing, and basaloid. Squamous cell carcinomas show extensive central n…
- 抽取所据引语：“p40, p63, CK5, CK5/6, or desmoglein expression”
- **命中 vignette 项**：`p63 staining`（canonical=`p63 staining`，极性 `present`，接合方式 `containment`）
- vignette 原句：“positive for p63”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Sarcomatoid Carcinoma` —[feature_of/asserted/typical]→ `spindle cell`

- 出处：`statpearls` / Initial symptoms and delay in patients with penile carcinoma. > Histopathology · context_type=`histopathology`
- 原文：…apillary carcinoma (2% to 15%), warty condylomatous tumors (7% to 10%), basaloid carcinoma (4% to 10%), verrucous carcinoma (3% to 7%), and sarcomatoid (spindle cell) carcinoma (1% to 6%).[2][13][49]
The usual type of squamous cell carcinoma demonstrates keratinization, epithelial pearl formation, and various degre…
- 抽取所据引语：“sarcomatoid (spindle cell) carcinoma”
- **命中 vignette 项**：`atypical spindle cells`（canonical=`atypical cells`，极性 `present`，接合方式 `containment`）
- vignette 原句：“atypical spindle and pleomorphic cells”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Synovial Sarcoma` —[feature_of/asserted/typical]→ `spindle cells`

- 出处：`pmc_oa` / Imaging Evaluation of Bone Tumors in the Cervical Spine: A Comprehensive Review. › Imaging Evaluation of Bone Tumors in the Cervical Spine: A Comprehensive Review. > Malignant Primary Tumors > Synovial Sarcoma (SS) · context_type=`criteria`
- 原文：（未能定位回段落）
- 抽取所据引语：“primarily composed of spindle cells”
- **命中 vignette 项**：`atypical spindle cells`（canonical=`atypical cells`，极性 `present`，接合方式 `containment`）
- vignette 原句：“atypical spindle and pleomorphic cells”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Basal Cell Carcinoma` —[feature_of/asserted/typical]→ `cytokeratin staining`

- 出处：`statpearls` / Availability of digital dermoscopy in daily practice dramatically reduces the number of excised melanocytic lesions: results from an observational study. > Histopathology · context_type=`histopathology`
- 原文：（未能定位回段落）
- 抽取所据引语：“it also stains positively for cytokeratin”
- **命中 vignette 项**：`pan-cytokeratin staining`（canonical=`pan-cytokeratin staining`，极性 `absent`，接合方式 `containment`）
- vignette 原句：“negative for pan-cytokeratin”
- 引擎影响：feature_of/asserted/absent，Δ=-0.4

**断言** `Squamous cell carcinomas` —[caused_by/asserted/typical]→ `dysplasia`

- 出处：`statpearls` / Evolution of the Incidence of Oral Cavity Cancers in the Elderly from 1990 to 2018. > Histopathology · context_type=`histopathology`
- 原文：（未能定位回段落）
- 抽取所据引语：“dysplasia, such as erythroplakia and leukoplakia, are associated with the development of squamous cell carcinomas”
- **命中 vignette 项**：`dysplasia`（canonical=`dysplasia`，极性 `absent`，接合方式 `exact`）
- vignette 原句：“without dysplasia”
- 引擎影响：caused_by/asserted/absent，Δ=-0.4

**断言** `Squamous cell carcinomas` —[caused_by/asserted/typical]→ `dysplasia`

- 出处：`statpearls` / Evolution of the Incidence of Oral Cavity Cancers in the Elderly from 1990 to 2018. > Histopathology · context_type=`histopathology`
- 原文：（未能定位回段落）
- 抽取所据引语：“dysplasia, such as erythroplakia and leukoplakia, are associated with the development of squamous cell carcinomas”
- **命中 vignette 项**：`dysplasia`（canonical=`dysplasia`，极性 `absent`，接合方式 `exact`）
- vignette 原句：“without dysplasia”
- 引擎影响：feature_of/asserted/absent，Δ=-0.4

## MCR_v1_seq100/74

- 金标：`Catecholaminergic polymorphic ventricular tachycardia`
- 候选集中被判为金标等价的标签：['Catecholaminergic Polymorphic Ventricular Tachycardia']
- 引擎 top-1：`Long QT Syndrome`（金标排名 2）

### `Long QT Syndrome` — top-1（竞争假设），得分 6.0，接合 13/73 条

**断言** `Long QT Syndrome` —[feature_of/asserted/typical]→ `QT interval`，阈值 `{'operator': '<', 'value': 400, 'unit': 'ms'}`

- 出处：`statpearls` / Historical aspects of electrocardiography. > Clinical Significance · context_type=`definition`
- 原文：…les. The normal QT interval duration is somewhat controversial, and various normal durations have been previously suggested. Generally, the normal QT interval is less than 400 to 440 milliseconds (ms), or 0.4 to 0.44 seconds. Women usually have a slightly longer QT interval than men. A QT interval has an inverse relation to the heart…
- 抽取所据引语：“normal QT interval is less than 400 to 440 milliseconds”
- **命中 vignette 项**：`QTc interval`（canonical=`qt interval`，极性 `present`，值 380ms，接合方式 `exact`）
- vignette 原句：“QTc of 380 ms”
- 引擎影响：feature_of/asserted/present，Δ=1.0

**断言** `Long QT Syndrome` —[feature_of/asserted/obligatory]→ `failure of the QT interval to shorten with increased heart rates`

- 出处：`statpearls` / Investigating the Complex Arrhythmic Phenotype Caused by the Gain-of-Function Mutation KCNQ1-G229D. > Evaluation · context_type=`criteria`
- 原文：…he concept of this testing is that patients with Long QT syndrome have an abnormal response to sympathetic stimulation. Their ECG shows the failure of the QT interval to shorten with increased heart rates, or it may even show prolongation. In patients with LQT2, there is marked shortening with exercise, however, exaggerated lengthening of the…
- 抽取所据引语：“failure of the QT interval to shorten with increased heart rates”
- **命中 vignette 项**：`pulse`（canonical=`heart rate`，极性 `present`，值 86bpm，接合方式 `containment`）
- vignette 原句：“86 bpm”
- 引擎影响：feature_of/asserted/present，Δ=1.0

**断言** `Long QT Syndrome` —[feature_of/asserted/typical]→ `syncope`

- 出处：`statpearls` / [Current practice for the prevention of sudden death in young athletes]. > Evaluation · context_type=`criteria`
- 原文：Long QT syndrome is a known cause of syncope and sudden death among the general population and athletes. The most common cause of prolonged QT on an ECG is secondary to medication use.…
- 抽取所据引语：“Long QT syndrome is a known cause of syncope”
- **命中 vignette 项**：`collapse`（canonical=`syncope`，极性 `present`，接合方式 `exact`）
- vignette 原句：“witnessed collapse”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Catecholaminergic Polymorphic Ventricular Tachycardia` —[feature_of/asserted/typical]→ `QTc`，阈值 `{'operator': '<=', 'value': 420, 'unit': 'ms'}`

- 出处：`pmc_oa` / Catecholaminergic Polymorphic Ventricular Tachycardia: Clinical Characteristics, Diagnostic Evaluation and Therapeutic Strategies. › Catecholaminergic Polymorphic Ventricular Tachycardia: Clinical Characteristics, Diagnostic Evaluation and Therapeutic Strategies. > References · context_type=`criteria`
- 原文：（未能定位回段落）
- 抽取所据引语：“QTc ≤ 420 ms”
- **命中 vignette 项**：`QTc interval`（canonical=`qt interval`，极性 `present`，值 380ms，接合方式 `containment`）
- vignette 原句：“QTc of 380 ms”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Long QT Syndrome` —[risk_factor_for/asserted/typical]→ `heart disease`

- 出处：`statpearls` / Hypomagnesemia and hypermagnesemia. > Etiology · context_type=`definition`
- 原文：…d with certain risk factors that include: older age (older than 65), female gender, hypokalemia, hypocalcemia, hypomagnesemia, bradycardia, heart disease, and diuretic use.[4][5]
Two rare congenital long QT syndromes include Romano-Ward syndrome and Jervell and Lange Nielsen syndrome.
The pre…
- 抽取所据引语：“heart disease”
- **命中 vignette 项**：`pulse`（canonical=`heart rate`，极性 `present`，值 86bpm，接合方式 `containment`）
- vignette 原句：“86 bpm”
- 引擎影响：risk_factor_for/asserted/present，Δ=0.8

**断言** `Long QT Syndrome` —[feature_of/asserted/typical]→ `ventricular fibrillation`

- 出处：`textbooks` / InternalMed_Harrison · context_type=`definition`
- 原文：…lar arrhythmias. Syncope and sudden death in patients with long QT syndrome result from a unique polymorphic ventricular tachycardia called torsades des pointes that degenerates into ventricular fibrillation. The long QT syndrome has been linked to genes encoding K+ channel α-subunits, K+ channel β-subunits, voltage-gated Na+ channel, and a scaf…
- 抽取所据引语：“torsades des pointes that degenerates into ventricular fibrillation”
- **命中 vignette 项**：`ventricular fibrillation`（canonical=`ventricular fibrillation`，极性 `present`，接合方式 `exact`）
- vignette 原句：“ventricular fibrillation”
- 引擎影响：feature_of/asserted/present，Δ=0.8

### `Catecholaminergic Polymorphic Ventricular Tachycardia` — 金标，得分 1.6，接合 6/73 条

**断言** `Catecholaminergic Polymorphic Ventricular Tachycardia` —[feature_of/asserted/typical]→ `QTc`，阈值 `{'operator': '<=', 'value': 420, 'unit': 'ms'}`

- 出处：`pmc_oa` / Catecholaminergic Polymorphic Ventricular Tachycardia: Clinical Characteristics, Diagnostic Evaluation and Therapeutic Strategies. › Catecholaminergic Polymorphic Ventricular Tachycardia: Clinical Characteristics, Diagnostic Evaluation and Therapeutic Strategies. > References · context_type=`criteria`
- 原文：…t HR > 100 bpm 4 Inducible PVCs in bigeminy and bidirectional couplets at HR > 100 bpm 2 Inducible PVCs at HR > 100 bpm 1 Baseline HR QTc ‡ QTc ≤ 420 ms 0.5 421 < QTc < 460 ms 0 QTc ≥ 460 ms −0.5 CPVT genetic test Positive for ACMG-graded pathogenic variant 4 Positive for ACMG-graded likely…
- 抽取所据引语：“QTc ≤ 420 ms”
- **命中 vignette 项**：`QTc interval`（canonical=`qt interval`，极性 `present`，值 380ms，接合方式 `containment`）
- vignette 原句：“QTc of 380 ms”
- 引擎影响：feature_of/asserted/present，Δ=1.2

**断言** `Catecholaminergic Polymorphic Ventricular Tachycardia` —[feature_of/asserted/typical]→ `exercise/activity-associated syncope or generalized seizures`

- 出处：`pmc_oa` / Catecholaminergic Polymorphic Ventricular Tachycardia: Clinical Characteristics, Diagnostic Evaluation and Therapeutic Strategies. › Catecholaminergic Polymorphic Ventricular Tachycardia: Clinical Characteristics, Diagnostic Evaluation and Therapeutic Strategies. > References · context_type=`criteria`
- 原文：…minergic polymorphic ventricular tachycardia diagnostic scorecard.
Clinical Criteria Points Symptoms Exercise/activity-associated ACA/SCA 2 Exercise/activity-associated syncope or generalized seizures 1 Exercise stress test or Holter monitoring during exertional activity(REQUIRES ≥ 1 exercise stress test/ambulatory Holter finding) *† Indu…
- 抽取所据引语：“Exercise/activity-associated syncope or generalized seizures”
- **命中 vignette 项**：`collapse`（canonical=`syncope`，极性 `present`，接合方式 `containment`）
- vignette 原句：“witnessed collapse”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Catecholaminergic Polymorphic Ventricular Tachycardia` —[feature_of/asserted/typical]→ `syncope`

- 出处：`textbooks` / InternalMed_Harrison · context_type=`definition`
- 原文：…ymorphic tachycardia is an inherited, genetically heterogeneous disorder associated with exerciseor stress-induced ventricular arrhythmias, syncope, or sudden death. Acquired QT interval prolongation, most commonly due to drugs, may also result in ventricular arrhythmias and syncope. These disorders are…
- 抽取所据引语：“syncope, or sudden death”
- **命中 vignette 项**：`collapse`（canonical=`syncope`，极性 `present`，接合方式 `exact`）
- vignette 原句：“witnessed collapse”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Ventricular Fibrillation` —[feature_of/asserted/typical]→ `electrolyte imbalances`

- 出处：`statpearls` / ACC/AHA/ESC 2006 Guidelines for Management of Patients With Ventricular Arrhythmias and the Prevention of Sudden Cardiac Death: a report of the American College of Cardiology/American Heart Association Task Force and the European Society of Cardiology Committee for Practice Guidelines (writing commi · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“Reversible factors, including electrolyte imbalances, acidosis, and hypoxia, should be corrected”
- **命中 vignette 项**：`electrolytes`（canonical=`electrolytes`，极性 `normal`，接合方式 `containment`）
- vignette 原句：“normal chemistry panel and electrolytes”
- 引擎影响：caused_by/asserted/normal，Δ=-0.4

**断言** `Ventricular tachycardia` —[caused_by/asserted/typical]→ `illicit drugs`

- 出处：`statpearls` / Diagnosis and management of ventricular tachycardia. > Etiology · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“use of illicit drugs such as cocaine or methamphetamine”
- **命中 vignette 项**：`illicit drug use`（canonical=`illicit drug use`，极性 `absent`，接合方式 `containment`）
- vignette 原句：“denied any illicit drug use”
- 引擎影响：caused_by/asserted/absent，Δ=-0.4

**断言** `Ventricular Fibrillation` —[feature_of/asserted/typical]→ `electrolyte imbalances`

- 出处：`statpearls` / ACC/AHA/ESC 2006 Guidelines for Management of Patients With Ventricular Arrhythmias and the Prevention of Sudden Cardiac Death: a report of the American College of Cardiology/American Heart Association Task Force and the European Society of Cardiology Committee for Practice Guidelines (writing commi · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“Reversible factors, including electrolyte imbalances, acidosis, and hypoxia, should be corrected”
- **命中 vignette 项**：`electrolytes`（canonical=`electrolytes`，极性 `normal`，接合方式 `containment`）
- vignette 原句：“normal chemistry panel and electrolytes”
- 引擎影响：feature_of/asserted/normal，Δ=-0.4

## MCR_v1_seq100/91

- 金标：`Angiosarcoma`
- 候选集中被判为金标等价的标签：['Hemangioma']
- 引擎 top-1：`Cavernous Angioma`（金标排名 5）

### `Cavernous Angioma` — top-1（竞争假设），得分 2.0，接合 7/79 条

**断言** `Cavernous angioma` —[feature_of/asserted/typical]→ `age`，阈值 `{'operator': 'range', 'value': 15, 'value_high': 72, 'unit': 'years'}`

- 出处：`statpearls` / Microsurgical anatomy and approaches to the cavernous sinus. > Pathophysiology · context_type=`other`
- 原文：（未能定位回段落）
- 抽取所据引语：“with a range of 15 to 72 years”
- **命中 vignette 项**：`age`（canonical=`age`，极性 `present`，值 36years，接合方式 `exact`）
- vignette 原句：“36-year-old”
- 引擎影响：feature_of/asserted/present，Δ=1.2

**断言** `Hemangioma` —[feature_of/asserted/typical]→ `neurologic symptoms`

- 出处：`statpearls` / Tumors of the spine. > Deterrence and Patient Education · context_type=`symptom`
- 原文：（未能定位回段落）
- 抽取所据引语：“back pain or neurologic symptoms”
- **命中 vignette 项**：`neurologic testing`（canonical=`neurologic testing`，极性 `normal`，接合方式 `containment`）
- vignette 原句：“without other focal deficits”
- 引擎影响：feature_of/asserted/normal，Δ=-0.4

**断言** `Cavernous Angioma` —[feature_of/asserted/occasional]→ `acute intracerebral hematoma`

- 出处：`statpearls` / Endoscopic Endonasal Surgery for the Resection of a Cavernous Hemangioma with a Sellar Extension. > Pearls and Other Issues · context_type=`definition`
- 原文：…control basic, involuntary functions like respiration or heartbeat. Surgical removal may be considered in any of the below-mentioned cases:
Cavernous angioma may not be diagnosed when it presents as acute intracerebral hematoma on nonenhanced CT or MRI images. Post-contrast enhancement scan reveals cavernous angiomas as areas of nodular enhancement adjacent to the…
- 抽取所据引语：“Cavernous angioma may not be diagnosed when it presents as acute intracerebral hematoma”
- **命中 vignette 项**：`left occipital intracerebral hematoma`（canonical=`intracerebral hematoma`，极性 `present`，接合方式 `containment`）
- vignette 原句：“left occipital intracerebral hematoma”
- 引擎影响：feature_of/asserted/present，Δ=0.35

**断言** `Cavernous Angioma` —[feature_of/asserted/occasional]→ `headache`

- 出处：`statpearls` / Endoscopic Endonasal Surgery for the Resection of a Cavernous Hemangioma with a Sellar Extension. > Evaluation · context_type=`criteria`
- 原文：As earlier mentioned the majority of lesions remain asymptomatic throughout life while others present with a headache, seizure or focal neurological deficit due to hemorrhage. The risk of hemorrhage is more for familial versus sporadic cases. The bleeding t…
- 抽取所据引语：“present with a headache”
- **命中 vignette 项**：`headaches`（canonical=`headache`，极性 `present`，接合方式 `exact`）
- vignette 原句：“worsening headaches”
- 引擎影响：feature_of/asserted/present，Δ=0.35

**断言** `Cavernous Angioma` —[feature_of/asserted/occasional]→ `hemorrhage`

- 出处：`statpearls` / Endoscopic Endonasal Surgery for the Resection of a Cavernous Hemangioma with a Sellar Extension. > Evaluation · context_type=`criteria`
- 原文：…ned the majority of lesions remain asymptomatic throughout life while others present with a headache, seizure or focal neurological deficit due to hemorrhage. The risk of hemorrhage is more for familial versus sporadic cases. The bleeding tendency is also documented more with CMs that are associa…
- 抽取所据引语：“due to hemorrhage”
- **命中 vignette 项**：`left occipital intraparenchymal hemorrhage`（canonical=`intraparenchymal hemorrhage`，极性 `present`，接合方式 `containment`）
- vignette 原句：“left occipital intraparenchymal hemorrhage”
- 引擎影响：feature_of/asserted/present，Δ=0.35

**断言** `Hemangioma` —[feature_of/asserted/rare]→ `hematoma`

- 出处：`statpearls` / Tumors of the spine. > Deterrence and Patient Education · context_type=`complication`
- 原文：（未能定位回段落）
- 抽取所据引语：“causing a hematoma”
- **命中 vignette 项**：`left occipital intracerebral hematoma`（canonical=`intracerebral hematoma`，极性 `present`，接合方式 `containment`）
- vignette 原句：“left occipital intracerebral hematoma”
- 引擎影响：feature_of/asserted/present，Δ=0.15

### `Hemangioma` — 金标，得分 0.0，接合 0/90 条

（该候选没有任何断言接合到 vignette 发现）

## MCR_v2_seq100/179

- 金标：`hypoxia-induced thrombocytopenia`
- 候选集中被判为金标等价的标签：['Thrombocytopenia']
- 引擎 top-1：`Congenital thrombocytopenia`（金标排名 5）

### `Congenital thrombocytopenia` — top-1（竞争假设），得分 4.95，接合 20/109 条

**断言** `Bleeding disorder` —[feature_of/asserted/typical]→ `Platelet count`，阈值 `{'operator': '>', 'value': 30000, 'unit': 'µL'}`

- 出处：`statpearls` / Assessment of bleeding in chronic liver disease and coagulopathy using the IMPROVE bleeding criteria. > Treatment / Management · context_type=`treatment`
- 原文：（未能定位回段落）
- 抽取所据引语：“maintain a count above 30,000/µL”
- **命中 vignette 项**：`platelet count`（canonical=`platelet count`，极性 `present`，值 103000/mm3，接合方式 `exact`）
- vignette 原句：“platelet count of 103 000/mm3”
- 引擎影响：feature_of/asserted/present，Δ=1.0

**断言** `Thrombocytopenia` —[definition/asserted/obligatory]→ `platelet count under 150 x 10^9/L`，阈值 `{'operator': '<', 'value': 150, 'unit': 'x 10^9/L'}`

- 出处：`statpearls` / How I treat thrombocytopenia in pregnancy. > Introduction · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“Thrombocytopenia, a platelet count under 150 x 10^9/L”
- **命中 vignette 项**：`platelet count`（canonical=`platelet count`，极性 `present`，值 103000/mm3，接合方式 `containment`）
- vignette 原句：“platelet count of 103 000/mm3”
- 引擎影响：definition/asserted/present，Δ=1.0

**断言** `Primary Immune Thrombocytopenia` —[feature_of/asserted/typical]→ `low platelet count`

- 出处：`pmc_oa` / Shortage of plasma-derived medicinal products: what is next? narrative literature review on its causes and counteracting policies in Italy. › Shortage of plasma-derived medicinal products: what is next? narrative literature review on its causes and counteracting policies in Italy. > Introduction > Plasma-derived medicinal products: characteristics and therapeutic indications · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“restore platelet count”
- **命中 vignette 项**：`platelet count`（canonical=`platelet count`，极性 `present`，值 103000/mm3，接合方式 `containment`）
- vignette 原句：“platelet count of 103 000/mm3”
- 引擎影响：feature_of/asserted/present，Δ=1.0

**断言** `Thrombocytopenia` —[definition/asserted/obligatory]→ `platelet count under 150 x 10^9/L`，阈值 `{'operator': '<', 'value': 150, 'unit': 'x 10^9/L'}`

- 出处：`statpearls` / How I treat thrombocytopenia in pregnancy. > Introduction · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“Thrombocytopenia, a platelet count under 150 x 10^9/L”
- **命中 vignette 项**：`platelet count`（canonical=`platelet count`，极性 `present`，值 103000/mm3，接合方式 `containment`）
- vignette 原句：“platelet count of 103 000/mm3”
- 引擎影响：feature_of/asserted/present，Δ=1.0

**断言** `Thrombocytopenia` —[feature_of/asserted/typical]→ `platelet count decrease`，阈值 `{'operator': 'range', 'value': 30, 'value_high': 50, 'unit': '%'}`

- 出处：`pmc_oa` / Postoperative Thrombocytopenia in Cardiac Surgery: Patterns, Differential Diagnosis and Management of Heparin-Induced Thrombocytopenia (HIT). › Postoperative Thrombocytopenia in Cardiac Surgery: Patterns, Differential Diagnosis and Management of Heparin-Induced Thrombocytopenia (HIT). > 1. Introduction · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“30–50% decrease”
- **命中 vignette 项**：`platelet count`（canonical=`platelet count`，极性 `present`，值 103000/mm3，接合方式 `containment`）
- vignette 原句：“platelet count of 103 000/mm3”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Thrombocytopenia` —[feature_of/asserted/typical]→ `platelet count <20,000/μL`，阈值 `{'operator': '<', 'value': 20000, 'unit': 'μL'}`

- 出处：`textbooks` / Obstentrics_Williams · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“initial platelet count was <20,000/μL”
- **命中 vignette 项**：`platelet count`（canonical=`platelet count`，极性 `present`，值 103000/mm3，接合方式 `containment`）
- vignette 原句：“platelet count of 103 000/mm3”
- 引擎影响：feature_of/asserted/present，Δ=0.8

### `Thrombocytopenia` — 金标，得分 1.5，接合 11/73 条

**断言** `Thrombocytopenia` —[feature_of/asserted/obligatory]→ `platelet count`，阈值 `{'operator': '<', 'value': 150000, 'unit': 'µL'}`

- 出处：`statpearls` / Drug-induced immune thrombocytopenia. > Continuing Education Activity · context_type=`definition`
- 原文：…e when treating patients with thrombocytopenia. Access free multiple choice questions on this topic.
Thrombocytopenia is characterized by a platelet count that falls below the established normal threshold, specifically 150,000/µL in adults. Platelets are essential blood components involved in the process of hemostasis and wound repair. The associated risks of thrombo…
- 抽取所据引语：“platelet count that falls below the established normal threshold, specifically 150,000/µL”
- **命中 vignette 项**：`platelet count`（canonical=`platelet count`，极性 `present`，值 103000/mm3，接合方式 `exact`）
- vignette 原句：“platelet count of 103 000/mm3”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Alloimmune thrombocytopenia` —[feature_of/asserted/typical]→ `normal platelet count in mother`

- 出处：`textbooks` / Obstentrics_Williams · context_type=`definition`
- 原文：…of therapy.
Alloimmune thrombocytopenia is typically diagnosed following delivery of a neonate with severe and unexplained thrombocytopenia to a woman whose platelet count is normal. Rarely, the diagnosis is ascertained after identiYing fetal ICH. he condition recurs in 70 to 90 percent of subsequent pregnancies, is oft…
- 抽取所据引语：“to a woman whose platelet count is normal”
- **命中 vignette 项**：`platelet count`（canonical=`platelet count`，极性 `present`，值 103000/mm3，接合方式 `containment`）
- vignette 原句：“platelet count of 103 000/mm3”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Fetal thrombocytopenia` —[feature_of/asserted/typical]→ `platelet count <50,000/μL`，阈值 `{'operator': '<', 'value': 50000, 'unit': 'μL'}`

- 出处：`textbooks` / Obstentrics_Williams · context_type=`definition`
- 原文：（未能定位回段落）
- 抽取所据引语：“fetal platelet count was < 50,000/μL”
- **命中 vignette 项**：`platelet count`（canonical=`platelet count`，极性 `present`，值 103000/mm3，接合方式 `containment`）
- vignette 原句：“platelet count of 103 000/mm3”
- 引擎影响：feature_of/asserted/present，Δ=0.8

**断言** `Heparin-induced thrombocytopenia (HIT)` —[feature_of/asserted/obligatory]→ `antiplatelet antibodies`

- 出处：`statpearls` / Drug-induced immune thrombocytopenia. > Etiology · context_type=`definition`
- 原文：…xus yunnanensis (Chinese yew), Rumex crispus (yellow dock), Arctium lappa (burdock), green tea, guarana, and ginseng, have been implicated. HIT involves antiplatelet antibodies that activate platelets, resulting in arterial and venous thrombosis.
- 抽取所据引语：“HIT involves antiplatelet antibodies that activate platelets”
- **命中 vignette 项**：`antiplatelet antibodies`（canonical=`antiplatelet antibodies`，极性 `absent`，接合方式 `exact`）
- vignette 原句：“antiplatelet antibodies were negative”
- 引擎影响：feature_of/asserted/absent，Δ=-0.5

**断言** `Thrombocytopenia` —[feature_of/asserted/typical]→ `bleeding during surgical procedures`，阈值 `{'operator': '<', 'value': 50000, 'unit': 'µL'}`

- 出处：`statpearls` / Drug-induced immune thrombocytopenia. > Etiology · context_type=`definition`
- 原文：…nia (100,000-150,000/µL) is generally asymptomatic. Moderate thrombocytopenia (50,000-100,000/µL) may manifest symptoms, eg, easy bruising. Severe thrombocytopenia (below 50,000/µL) can lead to bleeding during surgical procedures, and individuals with platelet counts under 10,000/µL are more susceptible to spontaneous hemorrhage.[1] Additionally, thrombocytopenia may…
- 抽取所据引语：“Severe thrombocytopenia (below 50,000/µL) can lead to bleeding during surgical procedures”
- **命中 vignette 项**：`bleeding history`（canonical=`bleeding history`，极性 `absent`，接合方式 `containment`）
- vignette 原句：“no bleeding history”
- 引擎影响：feature_of/asserted/absent，Δ=-0.4
