# 鉴别能力审查证据包

入选标准：至少一个目标方法把金标纳入假设集（strong 或 near），且其中至少一个方法未选中。共 22 例。

---

## DA_d2_heldout100/272 — Window-Period Acute Myocardial Infarction

- 家族 DA / 层 DA_d2_heldout100 / 权重 12.5
- 指南能力：本地扩展 D3_direct_vignette_matched（上游三源 D3_direct_vignette_matched）
- 纳入金标的方法：multistance, impc, forest；其中未选中：multistance, impc, forest

### vignette 全文

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

### collapse3c（召回 miss，判分 True，映射命中 4/4 个选项，金标关系 subtype_of）

- champion：**Acute Coronary Syndrome**　runner-up：Variant Angina　margin：
- selector 理由：The evidence of subtotal occlusion of the proximal left anterior descending artery and the presence of broad-based, asymmetrical, tall upright T waves in precordial leads V2 through V5 on the ECG decided it

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Acute Coronary Syndrome | weak | 0.0 | approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig / Subtotal occlusion of the proximal left anterior descending artery | Serum cardiac troponin I level: <0.05 ng/mL |
| Variant Angina | none | 0.0 | approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig | Subtotal occlusion of the proximal left anterior descending artery |
| Myocardial Infarction with Normal Troponin | weak | 0.0 | approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / Subtotal occlusion of the proximal left anterior descending artery | Serum cardiac troponin I level: <0.05 ng/mL |
| Aortic Dissection | none | 0.0 | approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / accompanied by dyspnea, dizziness, and sweating | ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig |
| Pulmonary Embolism | none | 0.0 | approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / accompanied by dyspnea, dizziness, and sweating | ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Acute Coronary Syndrome** — why: The patient's presentation with acute, severe precordial chest pain and ECG changes is unusual and points towards Acute Coronary Syndrome.
    - 支持：approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig / Subtotal occlusion of the proximal left anterior descending artery
    - 反对：Serum cardiac troponin I level: <0.05 ng/mL
- `c3` **Variant Angina** — why: The patient's ECG changes and chest pain at rest are unusual and point towards Variant Angina.
    - 支持：approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig
    - 反对：Subtotal occlusion of the proximal left anterior descending artery
- `c3` **Myocardial Infarction with Normal Troponin** — why: The patient's presentation with acute chest pain and subtotal occlusion of the proximal left anterior descending artery is unusual and points towards Myocardial Infarction with Normal Troponin.
    - 支持：approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / Subtotal occlusion of the proximal left anterior descending artery
    - 反对：Serum cardiac troponin I level: <0.05 ng/mL
- `c3` **Aortic Dissection** — why: The patient's presentation with acute chest pain and accompanying symptoms is unusual and points towards Aortic Dissection.
    - 支持：approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / accompanied by dyspnea, dizziness, and sweating
    - 反对：ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig
- `c3` **Pulmonary Embolism** — why: The patient's presentation with acute chest pain and accompanying symptoms is unusual and points towards Pulmonary Embolism.
    - 支持：approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / accompanied by dyspnea, dizziness, and sweating
    - 反对：ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig

</details>

### multistance（召回 top2_strong，判分 False，映射命中 4/4 个选项，金标关系 subtype_of）

- champion：**Acute Coronary Syndrome**　runner-up：Myocardial Infarction　margin：
- selector 理由：The champion is chosen because it best accounts for the combination of chest pain, ECG findings, and coronary angiography results, and it is the most specific diagnosis that encompasses the patient's presentation, with the normal troponin level being a less decisive finding in this context.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Myocardial Infarction | strong | 0.0 | approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig / Subtotal occlusion of the proximal left anterior descending artery | Serum cardiac troponin I level: <0.05 ng/mL |
| Acute Coronary Syndrome | weak | 0.0 | approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig / Subtotal occlusion of the proximal left anterior descending artery | — |
| Myocardial Infarction with Normal Troponin | weak | 0.0 | approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / Serum cardiac troponin I level: <0.05 ng/mL / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig | — |
| Variant Angina | none | 0.0 | approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig | Subtotal occlusion of the proximal left anterior descending artery |
| Hypertensive Emergency | none | 0.0 | blood pressure of 188/101 mm Hg | — |
| Cardiac Syndrome X | none | 0.0 | approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig | Subtotal occlusion of the proximal left anterior descending artery |
| Cardiomyopathy | none | 0.0 | ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig | — |
| Pulmonary Embolism | none | 0.0 | accompanied by dyspnea, dizziness, and sweating / respiratory rate at 20 breaths/min | — |
| Unstable Angina | none | 0.0 | approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig / Subtotal occlusion of the proximal left anterior descending artery | — |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Acute Coronary Syndrome** — why: The patient's presentation with acute, severe precordial chest pain and ECG changes, along with the finding of subtotal occlusion of the proximal left anterior descending artery, earned this slot.
    - 支持：approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig / Subtotal occlusion of the proximal left anterior descending artery
- `stance:commit` **Myocardial Infarction with Normal Troponin** — why: The patient's presentation with acute chest pain and ECG changes, along with a normal troponin level, earned this slot.
    - 支持：approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / Serum cardiac troponin I level: <0.05 ng/mL / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig
- `stance:commit` **Variant Angina** — why: The patient's presentation with acute chest pain and ECG changes, particularly the broad-based, asymmetrical, tall upright T waves, earned this slot.
    - 支持：approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig
    - 反对：Subtotal occlusion of the proximal left anterior descending artery
- `stance:commit` **Hypertensive Emergency** — why: The patient's severely elevated blood pressure earned this slot.
    - 支持：blood pressure of 188/101 mm Hg
- `stance:commit` **Cardiac Syndrome X** — why: The patient's presentation with acute chest pain and ECG changes, without evidence of significant coronary artery disease, earned this slot.
    - 支持：approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig
    - 反对：Subtotal occlusion of the proximal left anterior descending artery
- `stance:coverage` **Acute Coronary Syndrome** — why: The patient's symptoms and ECG findings are consistent with acute coronary syndrome, which cannot be skipped due to its high risk of morbidity and mortality.
    - 支持：approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig / Subtotal occlusion of the proximal left anterior descending artery
- `stance:coverage` **Hypertensive Emergency** — why: The patient's elevated blood pressure is a significant finding that requires consideration of hypertensive emergency, which can have severe consequences if left untreated.
    - 支持：blood pressure of 188/101 mm Hg
- `stance:coverage` **Cardiomyopathy** — why: The patient's ECG findings suggest possible cardiomyopathy, which is a significant diagnosis that cannot be skipped due to its potential impact on cardiac function.
    - 支持：ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig
- `stance:coverage` **Pulmonary Embolism** — why: The patient's symptoms of dyspnea, dizziness, and sweating, along with an elevated respiratory rate, raise the possibility of pulmonary embolism, which is a life-threatening condition that must be considered.
    - 支持：accompanied by dyspnea, dizziness, and sweating / respiratory rate at 20 breaths/min
- `stance:mechanism` **Acute Coronary Syndrome** — why: The patient's symptoms and ECG findings are consistent with acute coronary syndrome, which is caused by a sudden reduction in blood flow to the heart, often due to a blockage in a coronary artery.
    - 支持：approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig / Subtotal occlusion of the proximal left anterior descending artery
- `stance:mechanism` **Myocardial Infarction** — why: The patient's symptoms and ECG findings are consistent with myocardial infarction, which is caused by a blockage in a coronary artery that leads to damage to the heart muscle.
    - 支持：approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig / Subtotal occlusion of the proximal left anterior descending artery
    - 反对：Serum cardiac troponin I level: <0.05 ng/mL
- `stance:mechanism` **Unstable Angina** — why: The patient's symptoms and ECG findings are consistent with unstable angina, which is caused by a reduction in blood flow to the heart that does not lead to permanent damage to the heart muscle.
    - 支持：approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig / Subtotal occlusion of the proximal left anterior descending artery
- `stance:mechanism` **Prinzmetal's Angina** — why: The patient's symptoms and ECG findings are consistent with Prinzmetal's angina, which is caused by a temporary spasm in a coronary artery that leads to a reduction in blood flow to the heart.
    - 支持：approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig
    - 反对：Subtotal occlusion of the proximal left anterior descending artery

</details>

### impc（召回 set_strong，判分 False，映射命中 1/4 个选项，金标关系 unrelated）

- champion：**Variant Angina**　runner-up：Unstable Angina　margin：medium
- selector 理由：The presence of broad-based, asymmetrical, tall upright T waves in precordial leads V2 through V5 and the normalization of the T-wave morphology in leads V2 through V5 after the procedure, along with the subtotal occlusion of the proximal left anterior descending artery, support the diagnosis of Variant Angina. The normal serum cardiac troponin I level also suggests that there was no significant myocardial damage, which is consistent with Variant Angina.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Myocardial Infarction | strong | 1.2 | D1E001 / D1E003 / D2E005 | D1E004 / D3E007 |
| Acute Coronary Syndrome | weak | 3.2 | D1E001 / D1E002 / D1E003 / D2E005 | D1E004 / D3E007 |
| Unstable Angina | none | 3.0 | D1E001 / D1E002 / D1E003 | — |
| Variant Angina | none | 3.35 | D1E002 / D1E003 / D3E008 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Acute Coronary Syndrome** — why: The patient's symptoms and ECG findings are consistent with acute coronary syndrome, but the normal troponin level may suggest a different subtype, such as unstable angina.
    - 支持：acute, severe precordial chest pain radiating to their left arm at night, accompanied by dyspnea, dizziness, a / broad-based, asymmetrical, tall upright T waves in precordial leads V2 through V5 / Subtotal occlusion of the proximal left anterior descending artery
    - 反对：Serum cardiac troponin I level: <0.05 ng/mL (normal range, <0.16 ng/mL)
- `D1` **Myocardial Infarction** — why: The patient's symptoms and coronary angiography findings are consistent with myocardial infarction, but the normal troponin level does not support this diagnosis.
    - 支持：acute, severe precordial chest pain radiating to their left arm at night, accompanied by dyspnea, dizziness, a / Subtotal occlusion of the proximal left anterior descending artery
    - 反对：Serum cardiac troponin I level: <0.05 ng/mL (normal range, <0.16 ng/mL)
- `D1` **Unstable Angina** — why: The patient's symptoms, ECG findings, and coronary angiography results are consistent with unstable angina, and the normal troponin level supports this diagnosis.
    - 支持：acute, severe precordial chest pain radiating to their left arm at night, accompanied by dyspnea, dizziness, a / broad-based, asymmetrical, tall upright T waves in precordial leads V2 through V5 / Subtotal occlusion of the proximal left anterior descending artery
- `D2` **Acute Coronary Syndrome** — why: The patient's symptoms and ECG findings are consistent with acute coronary syndrome, but the normal troponin level is somewhat contradictory.
    - 支持：acute, severe precordial chest pain radiating to their left arm / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig / Subtotal occlusion of the proximal left anterior descending artery
    - 反对：Serum cardiac troponin I level: <0.05 ng/mL (normal range, <0.16 ng/mL)
- `D2` **Myocardial Infarction** — why: The patient's symptoms and coronary angiography findings are consistent with myocardial infarction, but the normal troponin level is contradictory.
    - 支持：acute, severe precordial chest pain radiating to their left arm / Subtotal occlusion of the proximal left anterior descending artery
    - 反对：Serum cardiac troponin I level: <0.05 ng/mL (normal range, <0.16 ng/mL)
- `D2` **Variant Angina** — why: The patient's ECG findings and coronary angiography results are consistent with variant angina.
    - 支持：broad-based, asymmetrical, tall upright T waves in precordial leads V2 through V5 / Subtotal occlusion of the proximal left anterior descending artery
- `D3` **Acute Coronary Syndrome** — why: The patient's symptoms and ECG findings are consistent with acute coronary syndrome, but the normal troponin level is unexpected.
    - 支持：acute, severe precordial chest pain radiating to their left arm / broad-based, asymmetrical, tall upright T waves in precordial leads V2 through V5 / Subtotal occlusion of the proximal left anterior descending artery
    - 反对：Serum cardiac troponin I level: <0.05 ng/mL
- `D3` **Myocardial Infarction** — why: The patient's symptoms and coronary angiography findings are consistent with myocardial infarction, but the normal troponin level is unexpected.
    - 支持：acute, severe precordial chest pain radiating to their left arm / Subtotal occlusion of the proximal left anterior descending artery
    - 反对：Serum cardiac troponin I level: <0.05 ng/mL
- `D3` **Variant Angina** — why: The patient's ECG findings are consistent with variant angina, which can cause chest pain and abnormal T waves.
    - 支持：broad-based, asymmetrical, tall upright T waves in precordial leads V2 through V5 / normalization of the T-wave morphology in leads V2 through V5

</details>

<details><summary>selector 淘汰理由</summary>

- **Myocardial Infarction** — Normal serum cardiac troponin I level and lack of significant myocardial damage
- **Acute Coronary Syndrome** — While the patient presents with symptoms of acute coronary syndrome, the normal troponin level and specific ECG findings point more towards Variant Angina

</details>

### forest（召回 set_strong，判分 False，映射命中 3/4 个选项，金标关系 unknown）

- champion：**Acute Coronary Syndrome**　runner-up：Unstable Angina　margin：medium
- selector 理由：The patient's presentation with acute, severe precordial chest pain radiating to their left arm, ECG changes, and subtotal occlusion of the proximal left anterior descending artery supports Acute Coronary Syndrome, despite the normal troponin level

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Myocardial Infarction | strong | 3.0 | AX_SE001 / AX_SE003 / AX_SE002 | AX_SE004 |
| Acute Coronary Syndrome | weak | 4.0 | AX_SE001 / AX_SE002 / AX_SE003 / AX_ME005 | AX_SE004 |
| Unstable Angina | none | 3.25 | AX_SE001 / AX_SE003 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Acute Coronary Syndrome** — why: The patient's symptoms and ECG findings are consistent with acute coronary syndrome, despite the troponin level being within normal range.
    - 支持：acute, severe precordial chest pain radiating to their left arm / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig / Subtotal occlusion of the proximal left anterior descending artery
    - 反对：Serum cardiac troponin I level: <0.05 ng/mL
- `syndrome_anatomy` **Myocardial Infarction** — why: The patient's symptoms and coronary angiography findings suggest myocardial infarction, but the normal troponin level contradicts this diagnosis.
    - 支持：acute, severe precordial chest pain radiating to their left arm / Subtotal occlusion of the proximal left anterior descending artery
    - 反对：Serum cardiac troponin I level: <0.05 ng/mL
- `syndrome_anatomy` **Unstable Angina** — why: The patient's symptoms and coronary angiography findings are consistent with unstable angina.
    - 支持：acute, severe precordial chest pain radiating to their left arm / Subtotal occlusion of the proximal left anterior descending artery
- `mechanism_etiology` **Acute Coronary Syndrome** — why: The patient's symptoms and coronary angiography findings are consistent with acute coronary syndrome.
    - 支持：acute, severe precordial chest pain radiating to their left arm / Subtotal occlusion of the proximal left anterior descending artery
- `mechanism_etiology` **Myocardial Infarction** — why: The patient's symptoms and ECG findings are consistent with myocardial infarction, but the normal troponin level contradicts this diagnosis.
    - 支持：acute, severe precordial chest pain radiating to their left arm / ECG showed a sinus rhythm at a rate of 85 beats/min with the presence of broad-based, asymmetrical, tall uprig
    - 反对：Serum cardiac troponin I level: <0.05 ng/mL
- `mechanism_etiology` **Unstable Angina** — why: The patient's symptoms and coronary angiography findings are consistent with unstable angina.
    - 支持：acute, severe precordial chest pain radiating to their left arm / Subtotal occlusion of the proximal left anterior descending artery
- `definitive_modality` **Acute Coronary Syndrome** — why: The patient's symptoms and ECG findings are consistent with acute coronary syndrome, despite normal troponin levels.
    - 支持：acute, severe precordial chest pain radiating to their left arm / broad-based, asymmetrical, tall upright T waves in precordial leads V2 through V5 / Subtotal occlusion of the proximal left anterior descending artery
    - 反对：Serum cardiac troponin I level: <0.05 ng/mL
- `definitive_modality` **Myocardial Infarction** — why: The patient's symptoms and coronary angiography findings are consistent with myocardial infarction, despite normal troponin levels.
    - 支持：acute, severe precordial chest pain radiating to their left arm / Subtotal occlusion of the proximal left anterior descending artery
    - 反对：Serum cardiac troponin I level: <0.05 ng/mL
- `definitive_modality` **Unstable Angina** — why: The patient's symptoms and coronary angiography findings are consistent with unstable angina.
    - 支持：acute, severe precordial chest pain radiating to their left arm / Subtotal occlusion of the proximal left anterior descending artery

</details>

<details><summary>selector 淘汰理由</summary>

- **Myocardial Infarction** — Normal serum cardiac troponin I level does not support myocardial infarction

</details>

---

## DA_d2_heldout100/348 — Asymptomatic posterior corneal dystrophy

- 家族 DA / 层 DA_d2_heldout100 / 权重 12.5
- 指南能力：本地扩展 D1_parent_component_or_list_only（上游三源 D1_parent_component_or_list_only）
- 纳入金标的方法：multistance, impc；其中未选中：impc

### vignette 全文

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

### collapse3c（召回 miss，判分 True，映射命中 3/4 个选项，金标关系 subtype_of）

- champion：**Corneal Ring Opacities**　runner-up：　margin：
- selector 理由：The presence of 4 symmetric concentric ring-shaped opacities in posterior corneal stroma with specific ring characteristics decided it.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Corneal Ring Opacities | weak | 0.0 | 4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Ring characteristics: Complete rings, outermost ring ~4mm from limbus | — |
| Crocodile Shagreen | weak | 0.0 | Peripheral cornea: posterior crocodile shagreen | — |
| Fuchs Endothelial Corneal Dystrophy | weak | 0.0 | Best spectacle-corrected visual acuity: 20/20 OU / Keratometry readings: 43.4 × 43.4 D OD and 43.0 × 44.8 D OS | — |
| Pterygium | none | 0.0 | Small nasal pterygium | — |
| Nuclear Sclerosis | none | 0.0 | Mild nuclear sclerosis of crystalline lens in both eyes | — |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Corneal Ring Opacities** — why: The presence of 4 symmetric concentric ring-shaped opacities in the posterior corneal stroma is an unusual finding that earned this slot.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Ring characteristics: Complete rings, outermost ring ~4mm from limbus
- `c3` **Crocodile Shagreen** — why: The presence of posterior crocodile shagreen in the peripheral cornea is an unusual finding that earned this slot.
    - 支持：Peripheral cornea: posterior crocodile shagreen
- `c3` **Fuchs Endothelial Corneal Dystrophy** — why: The presence of normal visual acuity and keratometry readings despite corneal opacities is an unusual finding that earned this slot.
    - 支持：Best spectacle-corrected visual acuity: 20/20 OU / Keratometry readings: 43.4 × 43.4 D OD and 43.0 × 44.8 D OS
- `c3` **Pterygium** — why: The presence of a small nasal pterygium is an unusual finding that earned this slot.
    - 支持：Small nasal pterygium
- `c3` **Nuclear Sclerosis** — why: The presence of mild nuclear sclerosis in both eyes is an unusual finding that earned this slot.
    - 支持：Mild nuclear sclerosis of crystalline lens in both eyes

</details>

### multistance（召回 top2_strong，判分 True，映射命中 4/4 个选项，金标关系 subtype_of）

- champion：**Schnyder Corneal Dystrophy**　runner-up：Corneal dystrophy　margin：
- selector 理由：Schnyder Corneal Dystrophy is chosen because it specifically accounts for the ring-shaped opacities and their characteristics, and it has no against evidence, making it a more precise diagnosis than the broader Corneal dystrophy.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Corneal dystrophy | strong | 0.0 | 4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Ring characteristics: Complete rings, outermost ring ~4mm from limbus / Ring measurements (vertical diameters from periphery to center): 6.0mm, 4.8mm, 4.5mm, and 3.6mm / Surface of rings: smooth without obvious deposits, pigmentation, or serrations | — |
| Schnyder Corneal Dystrophy | near | 0.0 | 4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Surface of rings: smooth without obvious deposits, pigmentation, or serrations | — |
| Corneal Arcus | weak | 0.0 | 4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Ring characteristics: Complete rings, outermost ring ~4mm from limbus / Normal conjunctiva with healthy ocular adnexa / Ring measurements (vertical diameters from periphery to center): 6.0mm, 4.8mm, 4.5mm, and 3.6mm | Cornea showed normal luster and even surface with no distinct arcus senilis |
| Posterior Crocodile Shagreen | weak | 0.0 | Peripheral cornea: posterior crocodile shagreen / 4 symmetric concentric ring-shaped opacities in posterior corneal stroma | Normal corneal sensations bilaterally |
| Fuchs Endothelial Corneal Dystrophy | weak | 0.0 | 4 symmetric concentric ring-shaped opacities in posterior corneal stroma | Normal corneal sensations bilaterally |
| Pterygium | none | 0.0 | Small nasal pterygium | — |
| Mild Nuclear Sclerosis | none | 0.0 | Mild nuclear sclerosis of crystalline lens in both eyes | — |
| Keratoconus | none | 0.0 | 4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Surface of rings: smooth without obvious deposits, pigmentation, or serrations | Normal corneal sensations bilaterally |
| Wilson's disease | none | 0.0 | Serum copper levels: Normal | Serum copper levels: Normal |
| Fuchs Endothelial Dystrophy | weak | 0.0 | 4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Surface of rings: smooth without obvious deposits, pigmentation, or serrations | Mild nuclear sclerosis of crystalline lens in both eyes |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Corneal Arcus** — why: The presence of symmetric concentric ring-shaped opacities in the posterior corneal stroma is unusual and points to this disease.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Ring characteristics: Complete rings, outermost ring ~4mm from limbus
    - 反对：Cornea showed normal luster and even surface with no distinct arcus senilis
- `stance:commit` **Posterior Crocodile Shagreen** — why: The presence of posterior crocodile shagreen in the peripheral cornea is a distinctive finding that earned this slot.
    - 支持：Peripheral cornea: posterior crocodile shagreen
- `stance:commit` **Fuchs Endothelial Corneal Dystrophy** — why: The combination of ring-shaped opacities and normal serum copper and iron levels is unusual and points to this disease.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma
    - 反对：Normal corneal sensations bilaterally
- `stance:commit` **Pterygium** — why: The presence of a small nasal pterygium is a distinctive finding that earned this slot.
    - 支持：Small nasal pterygium
- `stance:commit` **Mild Nuclear Sclerosis** — why: The presence of mild nuclear sclerosis is a distinctive finding that earned this slot.
    - 支持：Mild nuclear sclerosis of crystalline lens in both eyes
- `stance:coverage` **Corneal dystrophy** — why: The presence of symmetric concentric ring-shaped opacities in the posterior corneal stroma is a characteristic feature of corneal dystrophy.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Ring characteristics: Complete rings, outermost ring ~4mm from limbus / Ring measurements (vertical diameters from periphery to center): 6.0mm, 4.8mm, 4.5mm, and 3.6mm / Surface of rings: smooth without obvious deposits, pigmentation, or serrations
- `stance:coverage` **Keratoconus** — why: The presence of ring-shaped opacities in the cornea could be mistaken for keratoconus, but the normal corneal sensations and lack of other characteristic features make it less likely.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Surface of rings: smooth without obvious deposits, pigmentation, or serrations
    - 反对：Normal corneal sensations bilaterally
- `stance:coverage` **Arcus senilis** — why: The absence of arcus senilis is noted, but it is still a possible consideration given the patient's age.
    - 支持：Normal conjunctiva with healthy ocular adnexa
    - 反对：Cornea showed normal luster and even surface with no distinct arcus senilis
- `stance:coverage` **Wilson's disease** — why: The normal serum copper levels make Wilson's disease less likely, but it is still a consideration given the corneal findings.
    - 支持：Serum copper levels: Normal
    - 反对：Serum copper levels: Normal
- `stance:mechanism` **Corneal Arcus** — why: The presence of symmetric concentric ring-shaped opacities in the posterior corneal stroma, with smooth surfaces and no deposits, suggests a process of lipid deposition, which is consistent with Corneal Arcus.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Ring characteristics: Complete rings, outermost ring ~4mm from limbus / Ring measurements (vertical diameters from periphery to center): 6.0mm, 4.8mm, 4.5mm, and 3.6mm / Surface of rings: smooth without obvious deposits, pigmentation, or serrations
- `stance:mechanism` **Fuchs Endothelial Dystrophy** — why: The presence of ring-shaped opacities in the posterior corneal stroma, with smooth surfaces, could be indicative of Fuchs Endothelial Dystrophy, which is characterized by endothelial dysfunction and corneal guttae formation.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Surface of rings: smooth without obvious deposits, pigmentation, or serrations
    - 反对：Mild nuclear sclerosis of crystalline lens in both eyes
- `stance:mechanism` **Posterior Crocodile Shagreen** — why: The presence of posterior crocodile shagreen, characterized by ring-shaped opacities in the posterior corneal stroma, suggests a process of corneal degeneration, which is consistent with Posterior Crocodile Shagreen.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma
    - 反对：Normal corneal sensations bilaterally
- `stance:mechanism` **Schnyder Corneal Dystrophy** — why: The presence of ring-shaped opacities in the posterior corneal stroma, with smooth surfaces, could be indicative of Schnyder Corneal Dystrophy, which is characterized by lipid deposition in the cornea.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Surface of rings: smooth without obvious deposits, pigmentation, or serrations
    - 反对：Normal lipid and glucose levels

</details>

### impc（召回 set_strong，判分 False，映射命中 0/4 个选项，金标关系 unknown）

- champion：**Fuchs endothelial corneal dystrophy**　runner-up：Corneal amyloidosis　margin：medium
- selector 理由：4 symmetric concentric ring-shaped opacities in posterior corneal stroma and mild nuclear sclerosis of crystalline lens in both eyes support Fuchs endothelial corneal dystrophy

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Corneal arcus | weak | 0.75 | D1E001 / D1E002 | D1E003 |
| Posterior crocodile shagreen | weak | 1.35 | D1E004 | — |
| Fuchs endothelial corneal dystrophy | weak | 3.7 | D1E001 / D2E006 / D3E008 | — |
| Corneal amyloidosis | weak | 3.35 | D1E001 / D2E005 / D3E007 | — |
| Primary lipoidal degeneration | none | 1.0 | D1E001 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Corneal arcus** — why: The presence of ring-shaped opacities in the posterior corneal stroma is consistent with corneal arcus, but the absence of distinct arcus senilis at the corneal periphery is contradictory.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Ring characteristics: Complete rings, outermost ring ~4mm from limbus
    - 反对：Cornea showed normal luster and even surface with no distinct arcus senilis
- `D1` **Posterior crocodile shagreen** — why: The presence of posterior crocodile shagreen in the peripheral cornea is a specific finding that supports this diagnosis.
    - 支持：Peripheral cornea: posterior crocodile shagreen
- `D1` **Fuchs endothelial corneal dystrophy** — why: The presence of ring-shaped opacities in the posterior corneal stroma is consistent with Fuchs endothelial corneal dystrophy.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma
- `D2` **Corneal amyloidosis** — why: The presence of symmetric concentric ring-shaped opacities in the posterior corneal stroma is a characteristic feature of corneal amyloidosis.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Surface of rings: smooth without obvious deposits, pigmentation, or serrations
- `D2` **Posterior crocodile shagreen** — why: The vignette explicitly mentions the presence of posterior crocodile shagreen in the peripheral cornea.
    - 支持：Peripheral cornea: posterior crocodile shagreen
- `D2` **Fuchs endothelial corneal dystrophy** — why: Although not directly mentioned, the presence of mild nuclear sclerosis and the description of corneal findings could be related to Fuchs endothelial corneal dystrophy.
    - 支持：Mild nuclear sclerosis of crystalline lens in both eyes
- `D3` **Corneal amyloidosis** — why: The presence of ring-shaped opacities and bandlike structures is consistent with corneal amyloidosis.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / long bandlike structures with thin streaks of white lines interspersed
- `D3` **Corneal dystrophy** — why: The combination of ring-shaped opacities and posterior crocodile shagreen is suggestive of a corneal dystrophy.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / peripheral cornea: posterior crocodile shagreen
- `D3` **Primary lipoidal degeneration** — why: The presence of ring-shaped opacities could be indicative of primary lipoidal degeneration.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma

</details>

<details><summary>selector 淘汰理由</summary>

- **Corneal arcus** — contradicted by normal luster and even surface with no distinct arcus senilis
- **Posterior crocodile shagreen** — less specific and does not fully explain the findings
- **Primary lipoidal degeneration** — less specific and does not fully explain the findings

</details>

### forest（召回 miss，判分 True，映射命中 2/4 个选项，金标关系 subtype_of）

- champion：**Crocodile shagreen of the cornea**　runner-up：Corneal amyloidosis　margin：medium
- selector 理由：Direct mention of posterior crocodile shagreen in both eyes supports this diagnosis, with no strong contradictions

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Corneal amyloidosis | weak | 3.25 | AX_SE001 / AX_SE003 | — |
| Crocodile shagreen of the cornea | none | 2.5 | AX_SE002 / AX_ME007 | — |
| Fuchs endothelial dystrophy | weak | 2.0 | AX_SE002 / AX_ME004 | — |
| Corneal iron deposition | weak | -0.25 | AX_ME005 | AX_ME006 |
| Primary lipoidal degeneration of the cornea | none | 2.0 | AX_SE001 / AX_ME008 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Corneal amyloidosis** — why: The presence of ring-shaped opacities in the posterior corneal stroma and the bandlike structures on confocal microscopy are characteristic of corneal amyloidosis.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / long bandlike structures with thin streaks of white lines interspersed
- `syndrome_anatomy` **Crocodile shagreen of the cornea** — why: The presence of posterior crocodile shagreen is a specific finding that suggests a diagnosis of crocodile shagreen of the cornea.
    - 支持：posterior crocodile shagreen
- `mechanism_etiology` **Corneal amyloidosis** — why: The presence of ring-shaped opacities in the cornea and the description of bandlike structures with thin streaks of white lines are consistent with corneal amyloidosis.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / long bandlike structures with thin streaks of white lines interspersed
- `mechanism_etiology` **Fuchs endothelial dystrophy** — why: The presence of posterior crocodile shagreen and mild nuclear sclerosis are consistent with Fuchs endothelial dystrophy.
    - 支持：posterior crocodile shagreen / mild nuclear sclerosis of crystalline lens in both eyes
- `mechanism_etiology` **Corneal iron deposition** — why: The presence of ring-shaped opacities in the cornea could be consistent with corneal iron deposition, but normal serum iron levels contradict this diagnosis.
    - 支持：Ring characteristics: Complete rings, outermost ring ~4mm from limbus
    - 反对：Serum iron levels: Normal
- `definitive_modality` **Corneal amyloidosis** — why: The presence of ring-shaped opacities in the posterior corneal stroma and the specific findings on laser scanning in vivo confocal microscopy are characteristic of corneal amyloidosis.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / long bandlike structures with thin streaks of white lines interspersed
- `definitive_modality` **Primary lipoidal degeneration of the cornea** — why: The smooth surface of the ring-shaped opacities without deposits or pigmentation is consistent with primary lipoidal degeneration of the cornea.
    - 支持：4 symmetric concentric ring-shaped opacities in posterior corneal stroma / Surface of rings: smooth without obvious deposits, pigmentation, or serrations
- `definitive_modality` **Crocodile shagreen of the cornea** — why: The presence of posterior crocodile shagreen in the peripheral cornea is a distinctive feature of this condition.
    - 支持：peripheral cornea: posterior crocodile shagreen

</details>

<details><summary>selector 淘汰理由</summary>

- **Corneal iron deposition** — Normal serum iron levels contradict this diagnosis
- **Fuchs endothelial dystrophy** — Mild nuclear sclerosis is not specific enough to support this diagnosis over others
- **Primary lipoidal degeneration of the cornea** — Lack of specific findings unique to this condition
- **Corneal amyloidosis** — While supportive findings exist, they are not as directly linked to the condition as crocodile shagreen is to its own diagnosis

</details>

---

## DA_d2_heldout200b/522 — Catatonia related to underlying Lewy body dementia

- 家族 DA / 层 DA_d2_heldout200b / 权重 25.0
- 指南能力：本地扩展 D1_parent_component_or_list_only（上游三源 D1_parent_component_or_list_only）
- 纳入金标的方法：collapse3c, multistance, impc, forest；其中未选中：multistance, forest

### vignette 全文

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

### collapse3c（召回 champion_strong，判分 True，映射命中 2/4 个选项，金标关系 subtype_of）

- champion：**Catatonia**　runner-up：　margin：
- selector 理由：The presence of echopraxia, mitmachen, and mutism are specific findings that strongly support the diagnosis of Catatonia.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Catatonia | strong | 0.0 | Echopraxia / Mitmachen / visual and auditory hallucinations / paranoid delusions | — |
| Chronic ischemic encephalopathy | weak | 0.0 | MRI brain: showed white matter changes, likely chronic ischemia / three months of progressive decline in mental status | No focal neurologic deficits |
| Antidepressant-induced psychotic disorder | none | 0.0 | visual and auditory hallucinations / paranoid delusions | Mirtazapine therapy was recently started |
| Hypothyroidism-associated encephalopathy | none | 0.0 | three months of progressive decline in mental status / Labile mood | Thyroid-stimulating hormone: normal |
| Major depressive disorder with psychotic features | none | 0.0 | visual and auditory hallucinations / paranoid delusions / Labile mood | Mirtazapine therapy was recently started |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Catatonia** — why: The presence of echopraxia and mitmachen, which are rare and distinctive features of catatonia, earned this slot.
    - 支持：Echopraxia / Mitmachen / visual and auditory hallucinations / paranoid delusions
- `c3` **Chronic ischemic encephalopathy** — why: The combination of progressive decline in mental status and white matter changes on MRI suggests chronic ischemic encephalopathy.
    - 支持：MRI brain: showed white matter changes, likely chronic ischemia / three months of progressive decline in mental status
    - 反对：No focal neurologic deficits
- `c3` **Antidepressant-induced psychotic disorder** — why: The recent initiation of mirtazapine therapy and the development of psychotic symptoms suggest an antidepressant-induced psychotic disorder.
    - 支持：visual and auditory hallucinations / paranoid delusions
    - 反对：Mirtazapine therapy was recently started
- `c3` **Hypothyroidism-associated encephalopathy** — why: The presence of hypothyroidism in the patient's medical history and the development of encephalopathic symptoms suggest a possible association.
    - 支持：three months of progressive decline in mental status / Labile mood
    - 反对：Thyroid-stimulating hormone: normal
- `c3` **Major depressive disorder with psychotic features** — why: The patient's history of major depressive disorder and the development of psychotic symptoms suggest a possible diagnosis of psychotic depression.
    - 支持：visual and auditory hallucinations / paranoid delusions / Labile mood
    - 反对：Mirtazapine therapy was recently started

</details>

### multistance（召回 champion_strong，判分 False，映射命中 3/4 个选项，金标关系 unknown）

- champion：**Catatonia**　runner-up：Dementia　margin：
- selector 理由：The presence of echopraxia and mitmachen, which are specific to catatonia, decided the final comparison in favor of catatonia over dementia.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Catatonia | strong | 0.0 | Echopraxia / Mitmachen / visual and auditory hallucinations / paranoid delusions | No focal neurologic deficits |
| Dementia with Lewy bodies | near | 0.0 | visual and auditory hallucinations / paranoid delusions / MRI brain: showed white matter changes, likely chronic ischemia / Echopraxia | No focal neurologic deficits / Echopraxia |
| Dementia | strong | 0.0 | three months of progressive decline in mental status / visual and auditory hallucinations / paranoid delusions | — |
| Delirium | none | 0.0 | three months of progressive decline in mental status / Labile mood / Suspicious and withdrawn affect / Electroencephalography: showed diffuse slowing without seizures | No focal neurologic deficits / Lumbar puncture: negative for infectious, autoimmune, malignant causes and paraneoplastic encephalitis |
| Major depressive disorder with psychotic features | none | 0.0 | visual and auditory hallucinations / paranoid delusions / Labile mood / Suspicious and withdrawn affect | Echopraxia / Mitmachen / No focal neurologic deficits |
| Vascular dementia | weak | 0.0 | three months of progressive decline in mental status / MRI brain: showed white matter changes, likely chronic ischemia / No focal neurologic deficits | Echopraxia / Mitmachen / visual and auditory hallucinations |
| Psychotic disorder | none | 0.0 | visual and auditory hallucinations / paranoid delusions | — |
| Neurodegenerative disease | none | 0.0 | three months of progressive decline in mental status / MRI brain: showed white matter changes, likely chronic ischemia | — |
| Antipsychotic-Induced Parkinsonism | none | 0.0 | Mitmachen | — |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Catatonia** — why: The presence of echopraxia and mitmachen, which are rare and distinctive features of catatonia, earned this slot.
    - 支持：Echopraxia / Mitmachen / visual and auditory hallucinations / paranoid delusions
    - 反对：No focal neurologic deficits
- `stance:commit` **Delirium** — why: The combination of progressive decline in mental status, labile mood, and diffuse slowing on EEG is suggestive of delirium.
    - 支持：three months of progressive decline in mental status / Labile mood / Suspicious and withdrawn affect / Electroencephalography: showed diffuse slowing without seizures
    - 反对：No focal neurologic deficits / Lumbar puncture: negative for infectious, autoimmune, malignant causes and paraneoplastic encephalitis
- `stance:commit` **Dementia with Lewy bodies** — why: The presence of visual and auditory hallucinations, paranoid delusions, and white matter changes on MRI are consistent with dementia with Lewy bodies.
    - 支持：visual and auditory hallucinations / paranoid delusions / MRI brain: showed white matter changes, likely chronic ischemia
    - 反对：No focal neurologic deficits / Echopraxia
- `stance:commit` **Major depressive disorder with psychotic features** — why: The combination of hallucinations, delusions, and labile mood is consistent with major depressive disorder with psychotic features.
    - 支持：visual and auditory hallucinations / paranoid delusions / Labile mood / Suspicious and withdrawn affect
    - 反对：Echopraxia / Mitmachen / No focal neurologic deficits
- `stance:commit` **Vascular dementia** — why: The presence of progressive decline in mental status, white matter changes on MRI, and a history of coronary artery disease are consistent with vascular dementia.
    - 支持：three months of progressive decline in mental status / MRI brain: showed white matter changes, likely chronic ischemia / No focal neurologic deficits
    - 反对：Echopraxia / Mitmachen / visual and auditory hallucinations
- `stance:coverage` **Dementia** — why: Progressive decline in mental status and presence of hallucinations and delusions suggest a dementia syndrome.
    - 支持：three months of progressive decline in mental status / visual and auditory hallucinations / paranoid delusions
- `stance:coverage` **Psychotic disorder** — why: Presence of hallucinations and delusions is characteristic of a psychotic disorder.
    - 支持：visual and auditory hallucinations / paranoid delusions
- `stance:coverage` **Delirium** — why: Progressive decline in mental status and labile mood suggest a possibility of delirium.
    - 支持：three months of progressive decline in mental status / Labile mood / Suspicious and withdrawn affect
    - 反对：No focal neurologic deficits
- `stance:coverage` **Neurodegenerative disease** — why: Progressive decline in mental status and white matter changes on MRI suggest a neurodegenerative disease.
    - 支持：three months of progressive decline in mental status / MRI brain: showed white matter changes, likely chronic ischemia
- `stance:mechanism` **Vascular Dementia** — why: Chronic ischemia could explain the progressive decline in mental status and the white matter changes on MRI.
    - 支持：three months of progressive decline in mental status / MRI brain: showed white matter changes, likely chronic ischemia
- `stance:mechanism` **Delirium** — why: Diffuse slowing on EEG and labile mood could indicate delirium, but the absence of focal neurologic deficits is not typical.
    - 支持：Labile mood / Electroencephalography: showed diffuse slowing without seizures
    - 反对：No focal neurologic deficits
- `stance:mechanism` **Lewy Body Dementia** — why: Visual and auditory hallucinations and echopraxia are characteristic features of Lewy Body Dementia.
    - 支持：visual and auditory hallucinations / Echopraxia
- `stance:mechanism` **Antipsychotic-Induced Parkinsonism** — why: Mirtazapine therapy could contribute to the development of parkinsonian symptoms, such as mitmachen.
    - 支持：Mitmachen

</details>

### impc（召回 set_near，判分 True，映射命中 3/4 个选项，金标关系 subtype_of）

- champion：**Dementia with Lewy bodies**　runner-up：Delirium　margin：medium
- selector 理由：Visual and auditory hallucinations, paranoid delusions, echopraxia, and mitmachen are strongly supportive of Dementia with Lewy bodies

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Dementia with Lewy bodies | near | 10.7 | D1E001 / D1E002 / D1E003 / D1E004 | — |
| Delirium | none | 7.35 | D1E006 / D1E007 / D1E008 / D1E009 | — |
| Alzheimer's disease | none | -0.5 | D1E006 / D1E010 | D1E011 / D1E012 |
| Vitamin B12 deficiency | none | 1.1 | D2E013 / D2E014 | D2E014 |
| Chronic ischemia | none | 1.0 | D2E015 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Dementia with Lewy bodies** — why: The patient's symptoms of visual and auditory hallucinations, paranoid delusions, and abnormal behaviors are consistent with Dementia with Lewy bodies.
    - 支持：visual and auditory hallucinations, paranoid delusions / echopraxia / mitmachen / mutism / staring
- `D1` **Delirium** — why: The patient's acute onset of symptoms such as inattention, limited speech, and decreased participation suggest Delirium.
    - 支持：progressive decline in mental status / inattention / limited speech with increased latency / decreased participation
- `D1` **Alzheimer's disease** — why: The patient's progressive decline in mental status and inability to recognize family could be indicative of Alzheimer's disease, but the recent stent placement and mirtazapine therapy may suggest other contributing factors.
    - 支持：progressive decline in mental status / intermittent inability to recognize family
    - 反对：recent stent placement / mirtazapine therapy was recently started
- `D2` **Vitamin B12 deficiency** — why: The patient's homocysteine level is elevated, which can be a sign of vitamin B12 deficiency, despite the B12 level being within normal range.
    - 支持：Homocysteine: 12.3 µmol/L / B12: 1154.67 pmol/L
- `D2` **Chronic ischemia** — why: The MRI brain showing white matter changes likely due to chronic ischemia could explain the patient's progressive decline in mental status.
    - 支持：MRI brain: showed white matter changes, likely chronic ischemia
- `D2` **Dementia with Lewy bodies** — why: The patient's symptoms such as visual and auditory hallucinations, paranoid delusions, and abnormal behaviors are consistent with Dementia with Lewy bodies.
    - 支持：visual and auditory hallucinations, paranoid delusions / Echopraxia- Mitmachen- Mutism- Staring- Withdrawn affect
- `D3` **Dementia with Lewy bodies** — why: The patient's symptoms of visual and auditory hallucinations, paranoid delusions, and abnormal behaviors are consistent with Dementia with Lewy bodies.
    - 支持：visual and auditory hallucinations, paranoid delusions / Echopraxia / Mitmachen / Mutism / Staring
- `D3` **Delirium** — why: The patient's acute onset of symptoms and fluctuating mental status suggest Delirium.
    - 支持：progressive decline in mental status / Labile mood / Inattention / Limited speech with increased latency
- `D3` **Vitamin B12 deficiency** — why: Although the patient's B12 level is within normal range, the elevated homocysteine level could indicate a functional B12 deficiency.
    - 支持：Homocysteine: 12.3 µmol/L / B12: 1154.67 pmol/L
    - 反对：B12: 1154.67 pmol/L

</details>

<details><summary>selector 淘汰理由</summary>

- **Vitamin B12 deficiency** — Normal B12 levels contradict this diagnosis
- **Chronic ischemia** — While MRI shows white matter changes, this is not sufficient to explain the patient's complex symptoms
- **Alzheimer's disease** — Recent stent placement and mirtazapine therapy initiation contradict a diagnosis of Alzheimer's disease

</details>

### forest（召回 champion_strong，判分 False，映射命中 3/4 个选项，金标关系 unknown）

- champion：**Catatonia**　runner-up：Dementia with Lewy Bodies　margin：high
- selector 理由：Mutism, staring, and withdrawn affect are strong indicators of catatonia, with no contradictions in the vignette.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Dementia with Lewy Bodies | near | 4.0 | AX_SE002 / AX_SE009 / AX_SE007 / AX_SE006 | — |
| Catatonia | strong | 5.0 | AX_SE003 / AX_SE004 / AX_SE005 / AX_SE006 | — |
| Chronic Ischemic Encephalopathy | none | 3.75 | AX_SE001 / AX_SE008 / AX_ME016 | — |
| Vitamin B12 deficiency | none | 2.25 | AX_ME011 / AX_ME012 | — |
| Hypothyroidism-related encephalopathy | weak | 2.25 | AX_ME013 / AX_ME014 | — |
| Mirtazapine-induced psychosis | none | 2.25 | AX_ME015 / AX_ME010 | — |
| Vascular Dementia | weak | 2.0 | AX_ME016 / AX_SE008 | — |
| Delirium | none | 4.0 | AX_ME017 / AX_ME018 / AX_ME019 / AX_ME020 | — |
| Neurosyphilis | none | -0.25 | AX_ME021 | AX_ME021 |
| Creutzfeldt-Jakob Disease | none | 1.75 | AX_SE001 / AX_SE002 / AX_ME022 | AX_ME023 |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Chronic Ischemic Encephalopathy** — why: The patient's progressive decline in mental status and the MRI findings of white matter changes suggest chronic ischemic encephalopathy.
    - 支持：progressive decline in mental status / MRI brain: showed white matter changes, likely chronic ischemia
- `syndrome_anatomy` **Dementia with Lewy Bodies** — why: The patient's symptoms of visual and auditory hallucinations, fluctuating cognition, and abnormal behaviors are consistent with dementia with Lewy bodies.
    - 支持：visual and auditory hallucinations / fluctuating cognition with periods of inattention / echopraxia / mitmachen
- `syndrome_anatomy` **Catatonia** — why: The patient's symptoms of mutism, staring, and withdrawn affect, along with the presence of mitmachen and echopraxia, suggest catatonia.
    - 支持：mutism / staring / withdrawn affect / mitmachen / echopraxia
- `mechanism_etiology` **Vitamin B12 deficiency** — why: Elevated homocysteine levels and low-normal B12 levels may indicate a deficiency, which can cause neurological symptoms.
    - 支持：Homocysteine: 12.3 µmol/L / B12: 1154.67 pmol/L
- `mechanism_etiology` **Hypothyroidism-related encephalopathy** — why: Hypothyroidism can cause encephalopathy, and the patient has a history of hypothyroidism, although the TSH is currently normal.
    - 支持：hypothyroidism / Thyroid-stimulating hormone: normal
- `mechanism_etiology` **Mirtazapine-induced psychosis** — why: Mirtazapine can cause psychotic symptoms, especially in elderly patients, and the patient started taking it recently.
    - 支持：Mirtazapine therapy was recently started / visual and auditory hallucinations, paranoid delusions
- `mechanism_etiology` **Chronic ischemic encephalopathy** — why: Chronic ischemia can cause encephalopathy, and the patient has a history of coronary artery disease and shows white matter changes on MRI.
    - 支持：coronary artery disease with recent stent placement / MRI brain: showed white matter changes, likely chronic ischemia
- `definitive_modality` **Vascular Dementia** — why: The patient's history of coronary artery disease and recent stent placement, combined with MRI findings of white matter changes likely due to chronic ischemia, support a diagnosis of vascular dementia.
    - 支持：coronary artery disease with recent stent placement / MRI brain: showed white matter changes, likely chronic ischemia
- `definitive_modality` **Delirium** — why: The patient's presentation of labile mood, suspicious and withdrawn affect, inattention, and limited speech with increased latency are consistent with a diagnosis of delirium.
    - 支持：Labile mood / Suspicious and withdrawn affect / Inattention / Limited speech with increased latency
- `definitive_modality` **Neurosyphilis** — why: Although the patient's presentation could be consistent with neurosyphilis, the negative serum rapid plasma reagin test makes this diagnosis less likely.
    - 支持：Serum rapid plasma reagin: negative
    - 反对：Serum rapid plasma reagin: negative
- `definitive_modality` **Creutzfeldt-Jakob Disease** — why: The patient's rapid progressive decline in mental status and presence of visual and auditory hallucinations could suggest Creutzfeldt-Jakob disease, but the negative lumbar puncture results and lack of myoclonus make this diagnosis less likely.
    - 支持：progressive decline in mental status / visual and auditory hallucinations / myoclonus not mentioned but could be a consideration
    - 反对：Lumbar puncture: negative for infectious, autoimmune, malignant causes and paraneoplastic encephalitis

</details>

<details><summary>selector 淘汰理由</summary>

- **Delirium** — While labile mood and inattention are present, they are not exclusive to delirium and can be seen in catatonia as well.
- **Chronic Ischemic Encephalopathy** — Progressive decline and white matter changes are noted, but catatonia better explains the patient's specific symptoms like mutism and staring.
- **Hypothyroidism-related encephalopathy** — Normal thyroid-stimulating hormone levels contradict this diagnosis.
- **Mirtazapine-induced psychosis** — While mirtazapine could contribute to psychosis, it does not fully account for the patient's catatonic symptoms like mutism and staring.
- **Dementia with Lewy Bodies** — Although visual and auditory hallucinations and fluctuating cognition are present, the prominent catatonic features make catatonia a more specific diagnosis.

</details>

---

## DA_d2_heldout200b/551 — Linagliptin-induced acute pancreatitis

- 家族 DA / 层 DA_d2_heldout200b / 权重 25.0
- 指南能力：本地扩展 D2_direct_but_partial_or_general（上游三源 D2_direct_but_partial_or_general）
- 纳入金标的方法：collapse3c, multistance, impc, forest；其中未选中：multistance

### vignette 全文

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

### collapse3c（召回 champion_strong，判分 True，映射命中 2/4 个选项，金标关系 subtype_of）

- champion：**Acute Pancreatitis**　runner-up：Hypertensive Emergency　margin：
- selector 理由：The evidence of progressively worsening sharp epigastric pain radiating to the back and elevated lipase levels decided it, despite the absence of acute abnormality of the pancreas on imaging.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Acute Pancreatitis | strong | 0.0 | progressively worsening sharp epigastric pain radiating to the back of one-day duration / Lipase: 13.6833 µkat/L (elevated) / generalized abdominal tenderness worst in the epigastrium, without rebound or guarding | No acute abnormality of the pancreas |
| Hypertensive Emergency | none | 0.0 | Blood pressure: 200/100 mm Hg | — |
| Chronic Kidney Disease-Related Abdominal Pain | none | 0.0 | chronic kidney disease stage 4 / generalized abdominal tenderness worst in the epigastrium, without rebound or guarding | — |
| Diabetic Ketoacidosis | none | 0.0 | insulin-dependent type 2 diabetes mellitus / generalized abdominal tenderness worst in the epigastrium, without rebound or guarding | Glucose: 12.33 μmol/L |
| Ischemic Cardiomyopathy-Related Abdominal Pain | none | 0.0 | coronary artery disease / generalized abdominal tenderness worst in the epigastrium, without rebound or guarding | — |
| Cholecystitis | none | 0.0 | — | — |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Acute Pancreatitis** — why: Elevated lipase and abdominal tenderness suggest acute pancreatitis
    - 支持：progressively worsening sharp epigastric pain radiating to the back of one-day duration / Lipase: 13.6833 µkat/L (elevated) / generalized abdominal tenderness worst in the epigastrium, without rebound or guarding
    - 反对：No acute abnormality of the pancreas
- `c3` **Hypertensive Emergency** — why: Severely elevated blood pressure indicates a hypertensive emergency
    - 支持：Blood pressure: 200/100 mm Hg
- `c3` **Chronic Kidney Disease-Related Abdominal Pain** — why: Chronic kidney disease may cause abdominal pain due to various complications
    - 支持：chronic kidney disease stage 4 / generalized abdominal tenderness worst in the epigastrium, without rebound or guarding
- `c3` **Diabetic Ketoacidosis** — why: Diabetic patients are prone to DKA, which can cause abdominal pain
    - 支持：insulin-dependent type 2 diabetes mellitus / generalized abdominal tenderness worst in the epigastrium, without rebound or guarding
    - 反对：Glucose: 12.33 μmol/L
- `c3` **Ischemic Cardiomyopathy-Related Abdominal Pain** — why: Ischemic cardiomyopathy may cause abdominal pain due to decreased cardiac output
    - 支持：coronary artery disease / generalized abdominal tenderness worst in the epigastrium, without rebound or guarding

</details>

### multistance（召回 top2_strong，判分 False，映射命中 3/4 个选项，金标关系 subtype_of）

- champion：**Dehydration**　runner-up：Pancreatitis　margin：
- selector 理由：Dehydration is chosen due to its direct evidence of dry mucus membranes, decreased skin turgor, and elevated creatinine levels, which are more specific and decisive findings in the vignette.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Pancreatitis | strong | 0.0 | progressively worsening sharp epigastric pain radiating to the back of one-day duration / Lipase: 13.6833 µkat/L (elevated) | No acute abnormality of the pancreas and surgically absent gallbladder without significant bile duct dilation |
| Chronic Pancreatitis | weak | 0.0 | Lipase: 13.6833 µkat/L (elevated) / No acute abnormality of the pancreas and surgically absent gallbladder without significant bile duct dilation | generalized abdominal tenderness worst in the epigastrium, without rebound or guarding, and no palpable organo / No acute abnormality of the pancreas |
| Dehydration | none | 0.0 | dry mucus membranes and decreased skin turgor / Creatinine: 198.9 μmol/L | — |
| Hypertensive Emergency | none | 0.0 | Blood pressure: 200/100 mm Hg | — |
| Diabetic Ketoacidosis | none | 0.0 | insulin-dependent type 2 diabetes mellitus / Creatinine: 198.9 μmol/L | No history of fever, chills, previous similar pain, recent illness, abdominal trauma, alcohol, or illicit drug |
| Acute Coronary Syndrome | weak | 0.0 | Blood pressure: 200/100 mm Hg | generalized abdominal tenderness worst in the epigastrium, without rebound or guarding, and no palpable organo |
| Gastrointestinal obstruction | none | 0.0 | progressively worsening sharp epigastric pain radiating to the back of one-day duration / associated with nausea, vomiting, and decreased oral intake | No distention, normal bowel sounds in all quadrants |
| Peptic ulcer disease | none | 0.0 | progressively worsening sharp epigastric pain radiating to the back of one-day duration / generalized abdominal tenderness worst in the epigastrium, without rebound or guarding, and no palpable organo | No history of fever, chills, previous similar pain, recent illness, abdominal trauma, alcohol, or illicit drug |
| Chronic kidney disease | none | 0.0 | insulin-dependent type 2 diabetes mellitus / Creatinine: 198.9 μmol/L | — |
| Hypertensive Crisis | none | 0.0 | Blood pressure: 200/100 mm Hg / progressively worsening sharp epigastric pain radiating to the back of one-day duration | — |
| Renal Artery Stenosis | none | 0.0 | Creatinine: 198.9 μmol/L / Blood pressure: 200/100 mm Hg | — |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Chronic Pancreatitis** — why: Elevated lipase and absence of acute pancreatic abnormality suggest chronic pancreatitis
    - 支持：Lipase: 13.6833 µkat/L (elevated) / No acute abnormality of the pancreas and surgically absent gallbladder without significant bile duct dilation
    - 反对：generalized abdominal tenderness worst in the epigastrium, without rebound or guarding, and no palpable organo
- `stance:commit` **Dehydration** — why: Dry mucus membranes and decreased skin turgor indicate dehydration
    - 支持：dry mucus membranes and decreased skin turgor / Creatinine: 198.9 μmol/L
- `stance:commit` **Hypertensive Emergency** — why: Severely elevated blood pressure indicates hypertensive emergency
    - 支持：Blood pressure: 200/100 mm Hg
- `stance:commit` **Diabetic Ketoacidosis** — why: Insulin-dependent diabetes and elevated creatinine suggest diabetic ketoacidosis
    - 支持：insulin-dependent type 2 diabetes mellitus / Creatinine: 198.9 μmol/L
    - 反对：No history of fever, chills, previous similar pain, recent illness, abdominal trauma, alcohol, or illicit drug
- `stance:commit` **Acute Coronary Syndrome** — why: History of coronary artery disease and severely elevated blood pressure suggest acute coronary syndrome
    - 支持：hypertension, coronary artery disease, coronary artery bypass grafting, and cholecystectomy / Blood pressure: 200/100 mm Hg
    - 反对：generalized abdominal tenderness worst in the epigastrium, without rebound or guarding, and no palpable organo
- `stance:coverage` **Pancreatitis** — why: Cannot be skipped due to elevated lipase levels and severe epigastric pain.
    - 支持：progressively worsening sharp epigastric pain radiating to the back of one-day duration / Lipase: 13.6833 µkat/L (elevated)
    - 反对：No acute abnormality of the pancreas and surgically absent gallbladder without significant bile duct dilation
- `stance:coverage` **Gastrointestinal obstruction** — why: Must be considered due to severe abdominal pain and vomiting.
    - 支持：progressively worsening sharp epigastric pain radiating to the back of one-day duration / associated with nausea, vomiting, and decreased oral intake
    - 反对：No distention, normal bowel sounds in all quadrants
- `stance:coverage` **Peptic ulcer disease** — why: Cannot be ruled out due to severe epigastric pain and abdominal tenderness.
    - 支持：progressively worsening sharp epigastric pain radiating to the back of one-day duration / generalized abdominal tenderness worst in the epigastrium, without rebound or guarding, and no palpable organo
    - 反对：No history of fever, chills, previous similar pain, recent illness, abdominal trauma, alcohol, or illicit drug
- `stance:coverage` **Chronic kidney disease** — why: Must be considered due to patient's medical history and elevated creatinine levels.
    - 支持：insulin-dependent type 2 diabetes mellitus / Creatinine: 198.9 μmol/L
- `stance:mechanism` **Hypertensive Crisis** — why: Severe hypertension can cause end-organ damage, including renal and cardiac complications, which may explain the patient's symptoms and laboratory findings.
    - 支持：Blood pressure: 200/100 mm Hg / progressively worsening sharp epigastric pain radiating to the back of one-day duration
- `stance:mechanism` **Chronic Pancreatitis** — why: Elevated lipase levels suggest pancreatic inflammation, which may be related to the patient's epigastric pain and history of cholecystectomy.
    - 支持：Lipase: 13.6833 µkat/L (elevated)
    - 反对：No acute abnormality of the pancreas
- `stance:mechanism` **Dehydration** — why: The patient's symptoms of dry mucus membranes and decreased skin turgor suggest dehydration, which may be contributing to their acute distress.
    - 支持：dry mucus membranes and decreased skin turgor
- `stance:mechanism` **Renal Artery Stenosis** — why: The patient's elevated creatinine levels and severe hypertension suggest possible renal artery stenosis, which may be contributing to their chronic kidney disease.
    - 支持：Creatinine: 198.9 μmol/L / Blood pressure: 200/100 mm Hg

</details>

### impc（召回 champion_strong，判分 True，映射命中 3/4 个选项，金标关系 subtype_of）

- champion：**Acute Pancreatitis**　runner-up：Peptic Ulcer Disease　margin：medium
- selector 理由：Elevated lipase and radiating epigastric pain support Acute Pancreatitis despite normal CT findings

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Acute Pancreatitis | strong | 1.45 | D1E001 / D1E002 | D2E003 |
| Chronic Kidney Disease Exacerbation | none | 2.0 | D2E004 / D2E005 | — |
| Diabetic Ketoacidosis | none | 2.0 | D2E006 / D2E007 | — |
| Cholecystitis | none | -0.25 | D3E008 | D3E009 |
| Peptic Ulcer Disease | none | 2.0 | D3E010 / D3E011 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Acute Pancreatitis** — why: The patient's symptoms and elevated lipase levels are consistent with acute pancreatitis.
    - 支持：progressively worsening sharp epigastric pain radiating to the back / Lipase: 13.6833 µkat/L (elevated)
- `D2` **Acute Pancreatitis** — why: Elevated lipase levels and sharp epigastric pain radiating to the back are indicative of acute pancreatitis.
    - 支持：progressively worsening sharp epigastric pain radiating to the back / Lipase: 13.6833 µkat/L (elevated)
    - 反对：No acute abnormality of the pancreas
- `D2` **Chronic Kidney Disease Exacerbation** — why: Elevated creatinine levels and decreased oral intake suggest a possible exacerbation of chronic kidney disease.
    - 支持：Creatinine: 198.9 μmol/L / decreased oral intake
- `D2` **Diabetic Ketoacidosis** — why: Hyperglycemia in a patient with insulin-dependent type 2 diabetes mellitus could indicate diabetic ketoacidosis.
    - 支持：Glucose: 12.33 μmol/L / insulin-dependent type 2 diabetes mellitus
- `D3` **Acute Pancreatitis** — why: The patient's symptoms and elevated lipase levels suggest acute pancreatitis, but the imaging study does not show any acute abnormality of the pancreas.
    - 支持：progressively worsening sharp epigastric pain radiating to the back / Lipase: 13.6833 µkat/L (elevated)
    - 反对：No acute abnormality of the pancreas
- `D3` **Cholecystitis** — why: The patient's symptoms could suggest cholecystitis, but the gallbladder is surgically absent.
    - 支持：sharp epigastric pain
    - 反对：surgically absent gallbladder
- `D3` **Peptic Ulcer Disease** — why: The patient's symptoms and lack of relief with pantoprazole could suggest peptic ulcer disease.
    - 支持：progressively worsening sharp epigastric pain / used pantoprazole without relief

</details>

<details><summary>selector 淘汰理由</summary>

- **Cholecystitis** — surgically absent gallbladder
- **Chronic Kidney Disease Exacerbation** — not directly related to acute epigastric pain
- **Diabetic Ketoacidosis** — glucose level not significantly elevated for DKA

</details>

### forest（召回 champion_strong，判分 True，映射命中 3/4 个选项，金标关系 subtype_of）

- champion：**Acute Pancreatitis**　runner-up：Peptic Ulcer Disease　margin：medium
- selector 理由：Elevated lipase level and sharp epigastric pain radiating to the back

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Acute Pancreatitis | strong | 2.0 | AX_SE001 / AX_SE002 | AX_SE007 |
| Chronic Kidney Disease | none | 2.0 | AX_SE003 / AX_SE004 | — |
| Diabetic Ketoacidosis | none | 2.75 | AX_SE005 / AX_SE006 | — |
| Chronic Pancreatitis | weak | 0.5 | AX_SE001 | AX_SE007 |
| Peptic Ulcer Disease | none | 2.25 | AX_SE001 / AX_ME008 | — |
| Pancreatic Insufficiency | weak | 2.0 | AX_ME009 / AX_SE005 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Acute Pancreatitis** — why: Elevated lipase levels and epigastric pain radiating to the back are indicative of acute pancreatitis.
    - 支持：progressively worsening sharp epigastric pain radiating to the back / Lipase: 13.6833 µkat/L (elevated)
    - 反对：No acute abnormality of the pancreas
- `syndrome_anatomy` **Chronic Kidney Disease** — why: Patient has a known history of chronic kidney disease stage 4 and elevated creatinine levels.
    - 支持：Chronic kidney disease stage 4 / Creatinine: 198.9 μmol/L
- `syndrome_anatomy` **Diabetic Ketoacidosis** — why: Patient has a history of insulin-dependent type 2 diabetes mellitus and elevated glucose levels.
    - 支持：insulin-dependent type 2 diabetes mellitus / Glucose: 12.33 μmol/L
- `mechanism_etiology` **Acute Pancreatitis** — why: Elevated lipase levels and epigastric pain radiating to the back are indicative of acute pancreatitis.
    - 支持：progressively worsening sharp epigastric pain radiating to the back / Lipase: 13.6833 µkat/L (elevated)
    - 反对：No acute abnormality of the pancreas
- `mechanism_etiology` **Chronic Pancreatitis** — why: Recurring epigastric pain radiating to the back could be indicative of chronic pancreatitis.
    - 支持：progressively worsening sharp epigastric pain radiating to the back
    - 反对：No acute abnormality of the pancreas
- `mechanism_etiology` **Diabetic Ketoacidosis** — why: Elevated glucose levels and a history of insulin-dependent diabetes could indicate diabetic ketoacidosis.
    - 支持：insulin-dependent type 2 diabetes mellitus / Glucose: 12.33 μmol/L
- `mechanism_etiology` **Peptic Ulcer Disease** — why: Epigastric pain and lack of relief from pantoprazole could indicate peptic ulcer disease.
    - 支持：progressively worsening sharp epigastric pain radiating to the back / used pantoprazole without relief
- `definitive_modality` **Acute Pancreatitis** — why: Elevated lipase levels are a key indicator of acute pancreatitis.
    - 支持：Lipase: 13.6833 µkat/L (elevated)
    - 反对：No acute abnormality of the pancreas
- `definitive_modality` **Chronic Pancreatitis** — why: The patient's symptoms of progressively worsening epigastric pain are consistent with chronic pancreatitis.
    - 支持：progressively worsening sharp epigastric pain radiating to the back
- `definitive_modality` **Pancreatic Insufficiency** — why: The patient's decreased oral intake and history of diabetes mellitus may be related to pancreatic insufficiency.
    - 支持：decreased oral intake / insulin-dependent type 2 diabetes mellitus

</details>

<details><summary>selector 淘汰理由</summary>

- **Diabetic Ketoacidosis** — Glucose level not significantly elevated for DKA
- **Chronic Kidney Disease** — Not directly related to acute symptoms
- **Pancreatic Insufficiency** — Lack of specific evidence for pancreatic insufficiency
- **Chronic Pancreatitis** — No chronic pancreatitis findings on imaging

</details>

---

## DA_d2_heldout200b/566 — High-grade (3A) follicular lymphoma, stage IVB

- 家族 DA / 层 DA_d2_heldout200b / 权重 25.0
- 指南能力：本地扩展 D2_direct_but_partial_or_general（上游三源 D2_direct_but_partial_or_general）
- 纳入金标的方法：multistance, impc, forest；其中未选中：forest

### vignette 全文

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

### collapse3c（召回 miss，判分 False，映射命中 0/4 个选项，金标关系 unknown）

- champion：**Primary Effusion Lymphoma**　runner-up：　margin：
- selector 理由：The high triglyceride level in the pleural fluid and the presence of a mix of small to large B lymphocytes with aberrant expression of BCL2 decided it.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Primary Effusion Lymphoma | weak | 0.0 | Leukocyte count: 9.6 × 10⁹/L with 96% lymphocytes / Triglyceride level: 8.44 mmol/L (747 mg/dL) / Large right effusion with mild mediastinal shift to the left side / Mix of small to large B lymphocytes | — |
| Nodular Lymphocyte-Predominant Hodgkin Lymphoma | weak | 0.0 | nearly absent breath sounds on the right side / Extensive mediastinal and hilar density encasing the right mainstem bronchus with complete right lung atelecta / Mix of small to large B lymphocytes | Triglyceride level: 8.44 mmol/L (747 mg/dL) |
| Castleman Disease | none | 0.0 | unintentional weight loss / Extensive mediastinal and hilar density encasing the right mainstem bronchus with complete right lung atelecta | Leukocyte count: 9.6 × 10⁹/L with 96% lymphocytes |
| Anaplastic Large Cell Lymphoma | weak | 0.0 | Extensive mediastinal and hilar density encasing the right mainstem bronchus with complete right lung atelecta / Mix of small to large B lymphocytes | Aberrant expression of BCL2 |
| Diffuse Large B-Cell Lymphoma | weak | 0.0 | Mix of small to large B lymphocytes / Aberrant expression of BCL2 | Triglyceride level: 8.44 mmol/L (747 mg/dL) |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Primary Effusion Lymphoma** — why: The combination of a large pleural effusion, high triglyceride level in the pleural fluid, and lymphocyte-predominant pleural fluid with aberrant BCL2 expression is unusual and points towards Primary Effusion Lymphoma.
    - 支持：Leukocyte count: 9.6 × 10⁹/L with 96% lymphocytes / Triglyceride level: 8.44 mmol/L (747 mg/dL) / Large right effusion with mild mediastinal shift to the left side / Mix of small to large B lymphocytes / Aberrant expression of BCL2
- `c3` **Nodular Lymphocyte-Predominant Hodgkin Lymphoma** — why: The presence of extensive mediastinal and hilar density, nearly absent breath sounds on one side, and a mix of small to large B lymphocytes could suggest Nodular Lymphocyte-Predominant Hodgkin Lymphoma, although the high triglyceride level in the pleural fluid
    - 支持：nearly absent breath sounds on the right side / Extensive mediastinal and hilar density encasing the right mainstem bronchus with complete right lung atelecta / Mix of small to large B lymphocytes
    - 反对：Triglyceride level: 8.44 mmol/L (747 mg/dL)
- `c3` **Castleman Disease** — why: The combination of unintentional weight loss and extensive mediastinal and hilar density could suggest Castleman Disease, but the lymphocyte-predominant pleural fluid is not typical for this condition.
    - 支持：unintentional weight loss / Extensive mediastinal and hilar density encasing the right mainstem bronchus with complete right lung atelecta
    - 反对：Leukocyte count: 9.6 × 10⁹/L with 96% lymphocytes
- `c3` **Anaplastic Large Cell Lymphoma** — why: The presence of extensive mediastinal and hilar density and a mix of small to large B lymphocytes could suggest Anaplastic Large Cell Lymphoma, but the aberrant BCL2 expression and the context of the other findings make it less likely.
    - 支持：Extensive mediastinal and hilar density encasing the right mainstem bronchus with complete right lung atelecta / Mix of small to large B lymphocytes
    - 反对：Aberrant expression of BCL2
- `c3` **Diffuse Large B-Cell Lymphoma** — why: The mix of small to large B lymphocytes and aberrant BCL2 expression could suggest Diffuse Large B-Cell Lymphoma, but the high triglyceride level in the pleural fluid and the specific context of the other findings are not typical for this condition.
    - 支持：Mix of small to large B lymphocytes / Aberrant expression of BCL2
    - 反对：Triglyceride level: 8.44 mmol/L (747 mg/dL)

</details>

### multistance（召回 top2_strong，判分 True，映射命中 4/4 个选项，金标关系 subtype_of）

- champion：**Primary Effusion Lymphoma**　runner-up：Lymphoma　margin：
- selector 理由：The champion is chosen because it has the most specific and decisive for evidence, including a high leukocyte count with 96% lymphocytes and a high triglyceride level, which are unique to this diagnosis.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Lymphoma | strong | 0.0 | unintentional weight loss / Mix of small to large B lymphocytes / Aberrant expression of BCL2 / Mediastinal, bilateral hilar, cardiophrenic angle, retrocrural, and retroperitoneal adenopathy | — |
| Primary Effusion Lymphoma | weak | 0.0 | Leukocyte count: 9.6 × 10⁹/L with 96% lymphocytes / Triglyceride level: 8.44 mmol/L (747 mg/dL) / Large right effusion with mild mediastinal shift to the left side / Mix of small to large B lymphocytes | — |
| Nodular Lymphocyte-Predominant Hodgkin Lymphoma | weak | 0.0 | Extensive mediastinal and hilar density encasing the right mainstem bronchus with complete right lung atelecta / Mix of small to large B lymphocytes / Aberrant expression of BCL2 | Triglyceride level: 8.44 mmol/L (747 mg/dL) |
| Castleman Disease | none | 0.0 | Extensive mediastinal and hilar density encasing the right mainstem bronchus with complete right lung atelecta / Mix of small to large B lymphocytes / Mediastinal, bilateral hilar, cardiophrenic angle, retrocrural, and retroperitoneal adenopathy | Leukocyte count: 9.6 × 10⁹/L with 96% lymphocytes |
| Anaplastic Large Cell Lymphoma | weak | 0.0 | Extensive mediastinal and hilar density encasing the right mainstem bronchus with complete right lung atelecta / Mix of small to large B lymphocytes | Aberrant expression of BCL2 |
| Diffuse Large B-Cell Lymphoma | weak | 0.0 | Mix of small to large B lymphocytes / Aberrant expression of BCL2 | Leukocyte count: 9.6 × 10⁹/L with 96% lymphocytes |
| Pleural effusion | none | 0.0 | nearly absent breath sounds on the right side / Large right effusion with mild mediastinal shift to the left side | — |
| Hypertriglyceridemia | none | 0.0 | Triglyceride level: 8.44 mmol/L (747 mg/dL) | — |
| Dyslipidemia | none | 0.0 | Cholesterol level: 1.79 mmol/L (69 mg/dL) / Triglyceride level: 8.44 mmol/L (747 mg/dL) | — |
| Chylothorax | none | 0.0 | Triglyceride level: 8.44 mmol/L (747 mg/dL) / Large right effusion with mild mediastinal shift to the left side | — |
| Pseudolymphoma | none | 0.0 | Mix of small to large B lymphocytes | Aberrant expression of BCL2 |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Primary Effusion Lymphoma** — why: The high triglyceride level in the pleural fluid and the presence of a large effusion with lymphocytic predominance are unusual findings that suggest Primary Effusion Lymphoma.
    - 支持：Leukocyte count: 9.6 × 10⁹/L with 96% lymphocytes / Triglyceride level: 8.44 mmol/L (747 mg/dL) / Large right effusion with mild mediastinal shift to the left side / Mix of small to large B lymphocytes
- `stance:commit` **Nodular Lymphocyte-Predominant Hodgkin Lymphoma** — why: The presence of extensive mediastinal and hilar density and the mix of small to large B lymphocytes with aberrant expression of BCL2 are unusual findings that suggest Nodular Lymphocyte-Predominant Hodgkin Lymphoma.
    - 支持：Extensive mediastinal and hilar density encasing the right mainstem bronchus with complete right lung atelecta / Mix of small to large B lymphocytes / Aberrant expression of BCL2
    - 反对：Triglyceride level: 8.44 mmol/L (747 mg/dL)
- `stance:commit` **Castleman Disease** — why: The presence of extensive mediastinal and hilar density is an unusual finding that suggests Castleman Disease.
    - 支持：Extensive mediastinal and hilar density encasing the right mainstem bronchus with complete right lung atelecta / Mix of small to large B lymphocytes
    - 反对：Leukocyte count: 9.6 × 10⁹/L with 96% lymphocytes
- `stance:commit` **Anaplastic Large Cell Lymphoma** — why: The presence of extensive mediastinal and hilar density is an unusual finding that suggests Anaplastic Large Cell Lymphoma.
    - 支持：Extensive mediastinal and hilar density encasing the right mainstem bronchus with complete right lung atelecta / Mix of small to large B lymphocytes
    - 反对：Aberrant expression of BCL2
- `stance:commit` **Diffuse Large B-Cell Lymphoma** — why: The presence of a mix of small to large B lymphocytes with aberrant expression of BCL2 is an unusual finding that suggests Diffuse Large B-Cell Lymphoma.
    - 支持：Mix of small to large B lymphocytes / Aberrant expression of BCL2
    - 反对：Leukocyte count: 9.6 × 10⁹/L with 96% lymphocytes
- `stance:coverage` **Lymphoma** — why: The patient's unintentional weight loss, abnormal lymphocyte count, and aberrant BCL2 expression suggest a diagnosis of lymphoma.
    - 支持：unintentional weight loss / Mix of small to large B lymphocytes / Aberrant expression of BCL2
- `stance:coverage` **Pleural effusion** — why: The patient's absent breath sounds and large right effusion indicate a significant pleural effusion.
    - 支持：nearly absent breath sounds on the right side / Large right effusion with mild mediastinal shift to the left side
- `stance:coverage` **Hypertriglyceridemia** — why: The patient's elevated triglyceride level suggests a diagnosis of hypertriglyceridemia.
    - 支持：Triglyceride level: 8.44 mmol/L (747 mg/dL)
- `stance:coverage` **Dyslipidemia** — why: The patient's history of dyslipidemia and abnormal lipid levels suggest a continued diagnosis of dyslipidemia.
    - 支持：Cholesterol level: 1.79 mmol/L (69 mg/dL) / Triglyceride level: 8.44 mmol/L (747 mg/dL)
- `stance:mechanism` **Lymphoma** — why: The presence of a mix of small to large B lymphocytes and aberrant expression of BCL2, along with extensive mediastinal and hilar density, suggests a diagnosis of lymphoma, which unifies the patient's symptoms and laboratory findings.
    - 支持：Mix of small to large B lymphocytes / Aberrant expression of BCL2 / Mediastinal, bilateral hilar, cardiophrenic angle, retrocrural, and retroperitoneal adenopathy
- `stance:mechanism` **Chylothorax** — why: The high triglyceride level in the pleural fluid is consistent with chylothorax, which can cause a large pleural effusion and mediastinal shift, unifying some of the patient's symptoms and laboratory findings.
    - 支持：Triglyceride level: 8.44 mmol/L (747 mg/dL) / Large right effusion with mild mediastinal shift to the left side
- `stance:mechanism` **Pseudolymphoma** — why: The presence of a mix of small to large B lymphocytes could suggest pseudolymphoma, but the aberrant expression of BCL2 is not typical of this condition, leaving some findings unexplained.
    - 支持：Mix of small to large B lymphocytes
    - 反对：Aberrant expression of BCL2
- `stance:mechanism` **Castleman disease** — why: The presence of a mix of small to large B lymphocytes and extensive adenopathy is consistent with Castleman disease, which can cause a range of symptoms and laboratory findings, unifying some of the patient's presentation.
    - 支持：Mix of small to large B lymphocytes / Mediastinal, bilateral hilar, cardiophrenic angle, retrocrural, and retroperitoneal adenopathy

</details>

### impc（召回 champion_strong，判分 True，映射命中 4/4 个选项，金标关系 subtype_of）

- champion：**Lymphoma**　runner-up：Chylothorax　margin：medium
- selector 理由：Mix of small to large B lymphocytes and aberrant expression of BCL2 support Lymphoma diagnosis

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Lymphoma | strong | 3.7 | D1E001 / D1E002 / D1E003 | — |
| Chylothorax | none | 2.35 | D2E004 / D3E006 | — |
| Castleman disease | none | 1.35 | D2E005 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Lymphoma** — why: The patient's symptoms and test results, including the presence of B lymphocytes and aberrant expression of BCL2, are consistent with a diagnosis of lymphoma.
    - 支持：Mix of small to large B lymphocytes / Aberrant expression of BCL2 / Elevated Ki-67
- `D2` **Chylothorax** — why: The patient's pleural fluid analysis showed a high triglyceride level, which is a characteristic feature of chylothorax.
    - 支持：Pleural fluid analysis showed: - Triglyceride level: 8.44 mmol/L (747 mg/dL)
- `D2` **Lymphoma** — why: The patient's pathological tests showed a mix of small to large B lymphocytes, aberrant expression of BCL2, and elevated Ki-67, which are indicative of lymphoma.
    - 支持：Mix of small to large B lymphocytes / Aberrant expression of BCL2 / Elevated Ki-67
- `D2` **Castleman disease** — why: The patient's PET scan showed extensive lymphadenopathy, which is a characteristic feature of Castleman disease.
    - 支持：Mediastinal, bilateral hilar, cardiophrenic angle, retrocrural, and retroperitoneal adenopathy
- `D3` **Lymphoma** — why: The patient's pleural fluid analysis and pathological tests suggest a lymphoproliferative disorder.
    - 支持：Mix of small to large B lymphocytes / Aberrant expression of BCL2 / Elevated Ki-67
- `D3` **Chylothorax** — why: The high triglyceride level in the pleural fluid is indicative of chylothorax, which can be caused by lymphoma or other conditions.
    - 支持：Triglyceride level: 8.44 mmol/L (747 mg/dL)
- `D3` **Castleman disease** — why: The patient's imaging studies show lymphadenopathy, which can be seen in Castleman disease, a rare lymphoproliferative disorder.
    - 支持：Mediastinal, bilateral hilar, cardiophrenic angle, retrocrural, and retroperitoneal adenopathy

</details>

<details><summary>selector 淘汰理由</summary>

- **Castleman disease** — Less specific evidence and lower score_logit

</details>

### forest（召回 set_strong，判分 False，映射命中 0/4 个选项，金标关系 unknown）

- champion：**Nodular lymphocyte-predominant Hodgkin lymphoma**　runner-up：Primary effusion lymphoma　margin：medium
- selector 理由：Mix of small to large B lymphocytes, negative for CD5 and CD10 expression, and aberrant expression of BCL2 support the diagnosis of Nodular lymphocyte-predominant Hodgkin lymphoma

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Nodular lymphocyte-predominant Hodgkin lymphoma | weak | 5.0 | AX_SE001 / AX_SE002 / AX_SE003 / AX_ME008 | — |
| Castleman disease | none | 2.0 | AX_SE004 / AX_SE005 | — |
| Primary effusion lymphoma | weak | 3.5 | AX_SE006 / AX_SE007 / AX_ME010 | — |
| Chylothorax | none | 1.0 | AX_ME009 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Nodular lymphocyte-predominant Hodgkin lymphoma** — why: The patient's lymph node biopsy showed a mix of small to large B lymphocytes with aberrant expression of BCL2, which is consistent with nodular lymphocyte-predominant Hodgkin lymphoma.
    - 支持：Mix of small to large B lymphocytes / Negative for CD5 and CD10 expression / Aberrant expression of BCL2
- `syndrome_anatomy` **Castleman disease** — why: The patient's presentation with unintentional weight loss and extensive lymphadenopathy is consistent with Castleman disease.
    - 支持：Unintentional weight loss / Mediastinal, bilateral hilar, cardiophrenic angle, retrocrural, and retroperitoneal adenopathy
- `syndrome_anatomy` **Primary effusion lymphoma** — why: The patient's presentation with a large pleural effusion and lymphocytic predominance in the pleural fluid is consistent with primary effusion lymphoma.
    - 支持：Large right effusion with mild mediastinal shift to the left side / Pleural fluid analysis showed: Leukocyte count: 9.6 × 10⁹/L with 96% lymphocytes
- `mechanism_etiology` **Lymphoma** — why: The patient's symptoms and test results, including the presence of lymphocytes in the pleural fluid and the results of the endobronchial ultrasound-guided transbronchial needle aspiration, are consistent with lymphoma.
    - 支持：Mix of small to large B lymphocytes / Aberrant expression of BCL2 / Elevated Ki-67
- `mechanism_etiology` **Chylothorax** — why: The high triglyceride level in the pleural fluid is consistent with chylothorax, which is often associated with lymphoma.
    - 支持：Triglyceride level: 8.44 mmol/L (747 mg/dL)
- `definitive_modality` **Primary Effusion Lymphoma** — why: The patient's pleural fluid analysis and positive Light's criteria support the diagnosis of Primary Effusion Lymphoma.
    - 支持：Pleural fluid analysis showed: Leukocyte count: 9.6 × 10⁹/L with 96% lymphocytes / Positive Light's criteria based on lactate dehydrogenase ratio
- `definitive_modality` **Nodular Lymphocyte-Predominant Hodgkin Lymphoma** — why: The patient's lymph node biopsy results, including a mix of small to large B lymphocytes and negative CD5 and CD10 expression, support the diagnosis of Nodular Lymphocyte-Predominant Hodgkin Lymphoma.
    - 支持：Mix of small to large B lymphocytes / Negative for CD5 and CD10 expression
- `definitive_modality` **Diffuse Large B-Cell Lymphoma** — why: The patient's biopsy results, including aberrant BCL2 expression and elevated Ki-67, support the diagnosis of Diffuse Large B-Cell Lymphoma.
    - 支持：Aberrant expression of BCL2 / Elevated Ki-67

</details>

<details><summary>selector 淘汰理由</summary>

- **Castleman disease** — Lack of specific histopathological features and less comprehensive support
- **Chylothorax** — Although high triglyceride level is present, it is not sufficient to explain the overall clinical and pathological findings

</details>

---

## DA_d2_heldout200b/646 — Radiation-induced solitary rectal ulcer

- 家族 DA / 层 DA_d2_heldout200b / 权重 25.0
- 指南能力：本地扩展 D2_direct_but_partial_or_general（上游三源 D2_direct_but_partial_or_general）
- 纳入金标的方法：collapse3c, multistance, impc, forest；其中未选中：collapse3c, impc, forest

### vignette 全文

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

### collapse3c（召回 top2_strong，判分 False，映射命中 3/4 个选项，金标关系 subtype_of）

- champion：**Radiation Proctitis**　runner-up：　margin：
- selector 理由：The evidence of a large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate, combined with a history of prostate-directed radiation therapy, decided it.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Rectal Ulcer | strong | 0.0 | large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / mild straining with bowel movements and occasional passage of mucus | completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer |
| Radiation Proctitis | weak | 0.0 | large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer | Biopsies of the lesion were negative for malignancy |
| Proctitis | none | 0.0 | large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate | Biopsies of the lesion were negative for malignancy / completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer |
| Rectal Mucosal Injury | weak | 0.0 | large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / spacer positioned between the prostate and rectum | Biopsies of the lesion were negative for malignancy |
| Chronic Radiation Injury | weak | 0.0 | completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer / large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate | Biopsies of the lesion were negative for malignancy |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Radiation Proctitis** — why: The presence of a large deep-cratered solitary ulcer on the anterior rectal wall with a history of prostate-directed radiation therapy earned this slot.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer
    - 反对：Biopsies of the lesion were negative for malignancy
- `c3` **Rectal Ulcer** — why: The presence of a large deep-cratered solitary ulcer on the anterior rectal wall with symptoms of mild straining and passage of mucus earned this slot.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / mild straining with bowel movements and occasional passage of mucus
    - 反对：completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer
- `c3` **Proctitis** — why: The presence of a large deep-cratered solitary ulcer on the anterior rectal wall with a normal appearance of the remainder of the rectum earned this slot.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate
    - 反对：Biopsies of the lesion were negative for malignancy / completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer
- `c3` **Rectal Mucosal Injury** — why: The presence of a large deep-cratered solitary ulcer on the anterior rectal wall with a spacer positioned between the prostate and rectum earned this slot.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / spacer positioned between the prostate and rectum
    - 反对：Biopsies of the lesion were negative for malignancy
- `c3` **Chronic Radiation Injury** — why: The presence of a large deep-cratered solitary ulcer on the anterior rectal wall with a history of prostate-directed radiation therapy earned this slot.
    - 支持：completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer / large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate
    - 反对：Biopsies of the lesion were negative for malignancy

</details>

### multistance（召回 set_strong，判分 True，映射命中 3/4 个选项，金标关系 subtype_of）

- champion：**Radiation Proctitis**　runner-up：Hydrogel Spacer Complication　margin：
- selector 理由：The champion is chosen because it accounts for the most decisive findings in the vignette, including the patient's history of radiation therapy and the presence of a large deep-cratered solitary ulcer, which is more specific than the evidence for the runner-up.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Rectal Ulcer | strong | 0.0 | large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / mild straining with bowel movements and occasional passage of mucus | completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer |
| Radiation Proctitis | weak | 0.0 | large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer / spacer positioned between the prostate and rectum | Biopsies of the lesion were negative for malignancy |
| Proctitis | none | 0.0 | large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / remainder of the rectum appeared normal | completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer |
| Inflammatory Bowel Disease | none | 0.0 | large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / mild straining with bowel movements and occasional passage of mucus | Biopsies of the lesion were negative for malignancy / remainder of the rectum appeared normal |
| Rectal Mucosal Injury | weak | 0.0 | large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / spacer positioned between the prostate and rectum | Biopsies of the lesion were negative for malignancy |
| Hydrogel Spacer Complication | none | 0.0 | spacer positioned between the prostate and rectum / completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer | — |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Radiation Proctitis** — why: The presence of a large deep-cratered solitary ulcer on the anterior rectal wall with a history of prostate-directed radiation therapy earned this slot.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer
    - 反对：Biopsies of the lesion were negative for malignancy
- `stance:commit` **Rectal Ulcer** — why: The presence of a large deep-cratered solitary ulcer on the anterior rectal wall with symptoms of mild straining and passage of mucus earned this slot.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / mild straining with bowel movements and occasional passage of mucus
    - 反对：completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer
- `stance:commit` **Proctitis** — why: The presence of a large deep-cratered solitary ulcer on the anterior rectal wall with a normal appearance of the remainder of the rectum earned this slot.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / remainder of the rectum appeared normal
    - 反对：completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer
- `stance:commit` **Inflammatory Bowel Disease** — why: The presence of a large deep-cratered solitary ulcer on the anterior rectal wall with symptoms of mild straining and passage of mucus earned this slot.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / mild straining with bowel movements and occasional passage of mucus
    - 反对：Biopsies of the lesion were negative for malignancy / remainder of the rectum appeared normal
- `stance:commit` **Rectal Mucosal Injury** — why: The presence of a large deep-cratered solitary ulcer on the anterior rectal wall with a spacer positioned between the prostate and rectum earned this slot.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / spacer positioned between the prostate and rectum
    - 反对：Biopsies of the lesion were negative for malignancy
- `stance:coverage` **Radiation Proctitis** — why: The patient's history of radiation therapy and the presence of a solitary ulcer on the rectal wall are consistent with radiation proctitis.
    - 支持：completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer / large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate
- `stance:coverage` **Inflammatory Bowel Disease** — why: The presence of a deep-cratered ulcer on the rectal wall could be consistent with inflammatory bowel disease, although the biopsies were negative for malignancy.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate
    - 反对：Biopsies of the lesion were negative for malignancy
- `stance:coverage` **Rectal Ulcer** — why: The presence of a solitary ulcer on the rectal wall is consistent with a rectal ulcer, which could be caused by various factors including radiation or inflammatory bowel disease.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate
- `stance:coverage` **Proctitis** — why: The presence of a solitary ulcer on the rectal wall is consistent with proctitis, which could be caused by various factors including radiation, infection, or inflammatory bowel disease.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate
- `stance:mechanism` **Radiation Proctitis** — why: Radiation proctitis is a condition that occurs due to radiation exposure, which in this case is likely caused by the prostate-directed radiation therapy, resulting in a solitary ulcer on the anterior rectal wall.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer / spacer positioned between the prostate and rectum
- `stance:mechanism` **Hydrogel Spacer Complication** — why: The use of a SpaceOAR hydrogel spacer during radiation therapy may have contributed to the development of the rectal ulcer, possibly due to increased radiation exposure or mechanical irritation.
    - 支持：spacer positioned between the prostate and rectum / completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer
- `stance:mechanism` **Rectal Ulcer** — why: The presence of a solitary rectal ulcer could be a primary condition, potentially caused by factors such as chronic straining during bowel movements or other rectal injuries.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate
- `stance:mechanism` **Proctitis** — why: Proctitis, or inflammation of the rectum, could be a unifying diagnosis, potentially caused by radiation, infection, or other factors, resulting in the observed rectal ulceration.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate

</details>

### impc（召回 top2_strong，判分 False，映射命中 3/4 个选项，金标关系 subtype_of）

- champion：**Radiation Proctitis**　runner-up：Rectal Ulcer　margin：medium
- selector 理由：The patient's history of prostate-directed radiation therapy and the presence of a large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate support Radiation Proctitis as the most likely diagnosis.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Rectal Ulcer | strong | 3.35 | D2E003 / D1E001 / D2E004 | — |
| Radiation Proctitis | weak | 4.7 | D1E001 / D1E002 / D2E004 / D3E005 | — |
| Rectal Mucosal Injury | weak | 1.0 | D1E001 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Radiation Proctitis** — why: The patient's history of radiation therapy and the presence of a solitary ulcer on the anterior rectal wall are consistent with radiation proctitis.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / he had completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer
- `D2` **Radiation Proctitis** — why: The patient's history of radiation therapy and the presence of a solitary ulcer on the anterior rectal wall are consistent with radiation proctitis.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / he had completed a course of prostate-directed radiation therapy with a SpaceOAR hydrogel spacer
- `D2` **Rectal Ulcer** — why: The colonoscopy findings of a large deep-cratered solitary ulcer on the anterior rectal wall support the diagnosis of a rectal ulcer.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall
- `D2` **Proctitis** — why: The patient's symptoms of mild straining with bowel movements and occasional passage of mucus are consistent with proctitis.
    - 支持：mild straining with bowel movements and occasional passage of mucus
- `D3` **Radiation Proctitis** — why: The patient's history of radiation therapy and the presence of a solitary ulcer on the anterior rectal wall are consistent with radiation proctitis.
    - 支持：completed a course of prostate-directed radiation therapy / large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate
- `D3` **Solitary Rectal Ulcer Syndrome** — why: The patient's symptoms and the endoscopic findings of a solitary ulcer are consistent with solitary rectal ulcer syndrome.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / mild straining with bowel movements and occasional passage of mucus
- `D3` **Rectal Mucosal Injury** — why: The presence of a deep-cratered ulcer on the anterior rectal wall suggests a mucosal injury, which could be related to the patient's radiation therapy or other factors.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate

</details>

<details><summary>selector 淘汰理由</summary>

- **Rectal Mucosal Injury** — Lack of specific supporting evidence and lower score_logit compared to other options.

</details>

### forest（召回 top2_strong，判分 False，映射命中 3/4 个选项，金标关系 subtype_of）

- champion：**Radiation Proctitis**　runner-up：Rectal Ulcer　margin：high
- selector 理由：History of prostate-directed radiation therapy and presence of a large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Rectal Ulcer | strong | 0.75 | AX_SE001 | AX_ME004 |
| Radiation Proctitis | weak | 4.25 | AX_SE001 / AX_SE002 / AX_SE003 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Radiation Proctitis** — why: The patient's history of radiation therapy and the presence of a solitary ulcer on the anterior rectal wall are consistent with radiation proctitis.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / history of stage IIIc localized prostate cancer / completed a course of prostate-directed radiation therapy
- `syndrome_anatomy` **Rectal Ulcer** — why: The presence of a large deep-cratered solitary ulcer on the anterior rectal wall is consistent with a rectal ulcer.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate
- `mechanism_etiology` **Radiation Proctitis** — why: The patient's history of radiation therapy and the presence of a solitary ulcer on the anterior rectal wall are consistent with radiation proctitis.
    - 支持：history of stage IIIc localized prostate cancer / completed a course of prostate-directed radiation therapy / large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate
- `mechanism_etiology` **Rectal Ulcer** — why: The presence of a solitary ulcer on the anterior rectal wall is consistent with a rectal ulcer.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate
- `definitive_modality` **Radiation Proctitis** — why: The patient's history of radiation therapy and the presence of a solitary ulcer on the anterior rectal wall are consistent with radiation proctitis.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate / history of stage IIIc localized prostate cancer / completed a course of prostate-directed radiation therapy
- `definitive_modality` **Rectal Ulcer** — why: The presence of a deep-cratered solitary ulcer is consistent with a rectal ulcer, but the negative biopsy results for malignancy suggest a non-neoplastic cause.
    - 支持：large deep-cratered solitary ulcer on the anterior rectal wall with firm margins, friability, and exudate
    - 反对：Biopsies of the lesion were negative for malignancy

</details>

<details><summary>selector 淘汰理由</summary>

- **** — 

</details>

---

## DA_d2_heldout200b/773 — Idiopathic Pulmonary Arterial Hypertension (IPAH) with Patent Foramen Ovale (PFO)

- 家族 DA / 层 DA_d2_heldout200b / 权重 25.0
- 指南能力：本地扩展 D3_direct_vignette_matched（上游三源 D3_direct_vignette_matched）
- 纳入金标的方法：collapse3c, multistance, impc, forest；其中未选中：multistance, impc, forest

### vignette 全文

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

### collapse3c（召回 top2_strong，判分 True，映射命中 4/4 个选项，金标关系 subtype_of）

- champion：**Eisenmenger Syndrome**　runner-up：Patent Foramen Ovale　margin：
- selector 理由：The presence of cyanosis after an episode of severe cough and hemoptysis, along with the findings of a right-to-left shunt, decided it.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Idiopathic Pulmonary Arterial Hypertension | strong | 0.0 | Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation / Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 / Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure | cyanotic after an episode of severe cough and hemoptysis |
| Patent Foramen Ovale | strong | 0.0 | patent foramen ovale measuring 7.34 mm in width with a continuous, pure right-to-left shunt on colour flow map | — |
| Eisenmenger Syndrome | none | 0.0 | cyanotic after an episode of severe cough and hemoptysis / Femoral artery oxygen saturation was measured at 88.5% / Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation | — |
| Chronic Thromboembolic Pulmonary Hypertension | weak | 0.0 | Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation / Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 / Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure | No evidence of pulmonary embolism or pulmonary arteriovenous fistulae |
| Tricuspid Regurgitation | none | 0.0 | Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation | — |
| Chronic Thromboembolic Disease | none | 0.0 | — | — |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Eisenmenger Syndrome** — why: The patient's cyanosis, decreased oxygen saturation, and presence of a patent foramen ovale with a right-to-left shunt are unusual findings that suggest Eisenmenger Syndrome.
    - 支持：cyanotic after an episode of severe cough and hemoptysis / Femoral artery oxygen saturation was measured at 88.5% / Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation / Estimated pulmonary artery systolic pressure of 55 mmHg in 2021
- `c3` **Idiopathic Pulmonary Arterial Hypertension** — why: The patient's elevated pulmonary artery pressure and enlarged right atrium and ventricle are unusual findings that suggest Idiopathic Pulmonary Arterial Hypertension.
    - 支持：Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation / Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 / Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure
    - 反对：cyanotic after an episode of severe cough and hemoptysis
- `c3` **Chronic Thromboembolic Pulmonary Hypertension** — why: The patient's elevated pulmonary artery pressure and enlarged right atrium and ventricle are unusual findings that suggest Chronic Thromboembolic Pulmonary Hypertension, although the absence of evidence of pulmonary embolism or arteriovenous fistulae argues ag
    - 支持：Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation / Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 / Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure
    - 反对：No evidence of pulmonary embolism or pulmonary arteriovenous fistulae
- `c3` **Patent Foramen Ovale** — why: The patient's patent foramen ovale with a right-to-left shunt is an unusual finding that suggests Patent Foramen Ovale.
    - 支持：patent foramen ovale measuring 7.34 mm in width with a continuous, pure right-to-left shunt on colour flow map
- `c3` **Tricuspid Regurgitation** — why: The patient's tricuspid regurgitation is an unusual finding that suggests Tricuspid Regurgitation.
    - 支持：Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation

</details>

### multistance（召回 set_strong，判分 False，映射命中 4/4 个选项，金标关系 subtype_of）

- champion：**Eisenmenger Syndrome**　runner-up：Pulmonary Hypertension　margin：
- selector 理由：Eisenmenger Syndrome is chosen because it accounts for the most decisive findings, including cyanosis, patent foramen ovale, and enlarged hilar shadow and widened pulmonary arteries, which are not fully explained by the other finalists.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Idiopathic Pulmonary Arterial Hypertension | strong | 0.0 | Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 / Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure | cyanotic after an episode of severe cough and hemoptysis |
| Patent Foramen Ovale | strong | 0.0 | patent foramen ovale measuring 7.34 mm in width with a continuous, pure right-to-left shunt on colour flow map | — |
| Pulmonary Hypertension | near | 0.0 | Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 / Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure | — |
| Pulmonary Arterial Hypertension | strong | 0.0 | Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 / Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure | — |
| Eisenmenger Syndrome | none | 0.0 | cyanotic after an episode of severe cough and hemoptysis / Femoral artery oxygen saturation was measured at 88.5% / Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / patent foramen ovale measuring 7.34 mm in width with a continuous, pure right-to-left shunt on colour flow map | — |
| Chronic Thromboembolic Pulmonary Hypertension | weak | 0.0 | Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / No evidence of pulmonary embolism or pulmonary arteriovenous fistulae / Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 | Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure / No evidence of pulmonary embolism or pulmonary arteriovenous fistulae |
| Tricuspid Regurgitation | none | 0.0 | Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation | — |
| Congenital Heart Disease | none | 0.0 | patent foramen ovale measuring 7.34 mm in width with a continuous, pure right-to-left shunt on colour flow map | — |
| Cardiomyopathy | none | 0.0 | Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation | Plasma N-terminal pro-brain natriuretic peptide was 94.2 pg/ml in August 2021, indicating normal cardiac funct |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Eisenmenger Syndrome** — why: The patient's cyanosis and decreased oxygen saturation, combined with the presence of a patent foramen ovale and enlarged pulmonary arteries, suggest Eisenmenger Syndrome.
    - 支持：cyanotic after an episode of severe cough and hemoptysis / Femoral artery oxygen saturation was measured at 88.5% / Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / patent foramen ovale measuring 7.34 mm in width with a continuous, pure right-to-left shunt on colour flow map
- `stance:commit` **Idiopathic Pulmonary Arterial Hypertension** — why: The patient's elevated pulmonary artery pressure and lack of evidence for other causes of pulmonary hypertension suggest Idiopathic Pulmonary Arterial Hypertension.
    - 支持：Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 / Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure
    - 反对：cyanotic after an episode of severe cough and hemoptysis
- `stance:commit` **Chronic Thromboembolic Pulmonary Hypertension** — why: The patient's enlarged hilar shadow and widened pulmonary arteries, combined with the lack of evidence for pulmonary embolism, suggest Chronic Thromboembolic Pulmonary Hypertension.
    - 支持：Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / No evidence of pulmonary embolism or pulmonary arteriovenous fistulae
    - 反对：Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure
- `stance:commit` **Tricuspid Regurgitation** — why: The patient's tricuspid regurgitation and enlarged right atrium and ventricle suggest Tricuspid Regurgitation.
    - 支持：Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation
- `stance:commit` **Patent Foramen Ovale** — why: The patient's patent foramen ovale with a right-to-left shunt suggests Patent Foramen Ovale.
    - 支持：patent foramen ovale measuring 7.34 mm in width with a continuous, pure right-to-left shunt on colour flow map
- `stance:coverage` **Pulmonary Hypertension** — why: Pulmonary hypertension is a possible diagnosis given the patient's symptoms and imaging findings, including enlarged pulmonary arteries and elevated pulmonary artery pressure.
    - 支持：Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 / Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure
- `stance:coverage` **Congenital Heart Disease** — why: The presence of a patent foramen ovale with a right-to-left shunt suggests congenital heart disease as a possible diagnosis.
    - 支持：patent foramen ovale measuring 7.34 mm in width with a continuous, pure right-to-left shunt on colour flow map
- `stance:coverage` **Chronic Thromboembolic Pulmonary Hypertension** — why: Chronic thromboembolic pulmonary hypertension is a possible diagnosis given the patient's symptoms and imaging findings, although the lack of evidence of pulmonary embolism or arteriovenous fistulae makes it less likely.
    - 支持：Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / Estimated pulmonary artery systolic pressure of 55 mmHg in 2021
    - 反对：No evidence of pulmonary embolism or pulmonary arteriovenous fistulae
- `stance:coverage` **Cardiomyopathy** — why: Cardiomyopathy is a possible diagnosis given the patient's symptoms and imaging findings, including an enlarged right atrium and ventricle, although the normal cardiac function suggested by the plasma N-terminal pro-brain natriuretic peptide level makes it les
    - 支持：Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation
    - 反对：Plasma N-terminal pro-brain natriuretic peptide was 94.2 pg/ml in August 2021, indicating normal cardiac funct
- `stance:mechanism` **Eisenmenger Syndrome** — why: This disease unifies the findings of cyanosis, enlarged right atrium and ventricle, and a patent foramen ovale with a right-to-left shunt, which are all characteristic of Eisenmenger Syndrome.
    - 支持：recurrent post-activity chest pain and shortness of breath for more than 11 years / Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / patent foramen ovale measuring 7.34 mm in width with a continuous, pure right-to-left shunt on colour flow map
- `stance:mechanism` **Pulmonary Arterial Hypertension** — why: This disease explains the elevated pulmonary artery pressures and the resulting right ventricular enlargement and tricuspid regurgitation.
    - 支持：Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 / Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure
- `stance:mechanism` **Chronic Thromboembolic Pulmonary Hypertension** — why: This disease could explain the pulmonary hypertension and enlarged pulmonary arteries, but the lack of evidence for pulmonary embolism or thromboembolism makes it less likely.
    - 支持：Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / No evidence of pulmonary embolism or pulmonary arteriovenous fistulae
    - 反对：Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure
- `stance:mechanism` **Congenital Heart Disease** — why: This disease explains the presence of a patent foramen ovale, which is a congenital heart defect that can lead to right-to-left shunting and cyanosis.
    - 支持：patent foramen ovale measuring 7.34 mm in width with a continuous, pure right-to-left shunt on colour flow map

</details>

### impc（召回 top2_strong，判分 False，映射命中 4/4 个选项，金标关系 subtype_of）

- champion：**Eisenmenger Syndrome**　runner-up：Idiopathic Pulmonary Arterial Hypertension　margin：medium
- selector 理由：The patient's gradual progression from acyanosis to cyanosis, decreased femoral artery oxygen saturation, and presence of a patent foramen ovale with a right-to-left shunt support Eisenmenger Syndrome

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Idiopathic Pulmonary Arterial Hypertension | strong | 4.35 | D2E006 / D2E007 / D2E008 / D3E013 | — |
| Eisenmenger Syndrome | none | 6.7 | D1E001 / D1E002 / D1E003 / D2E004 | — |
| Chronic Thromboembolic Pulmonary Hypertension | weak | 0.85 | D2E009 / D2E006 / D2E007 | D2E010 / D3E012 |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Eisenmenger Syndrome** — why: The patient's progression from acyanotic to cyanotic, combined with the presence of a patent foramen ovale and a right-to-left shunt, supports the diagnosis of Eisenmenger Syndrome.
    - 支持：The patient was initially acyanotic from 2010 to 2016, but gradually became cyanotic after an episode of sever / Femoral artery oxygen saturation was measured at 88.5% (decreased from a previous measurement of 93.4% in 2016 / Transesophageal Echocardiography ... Revealed a patent foramen ovale measuring 7.34 mm in width with a continu
- `D2` **Eisenmenger Syndrome** — why: The patient's progression from acyanotic to cyanotic, decreased oxygen saturation, and presence of a patent foramen ovale with right-to-left shunt support this diagnosis.
    - 支持：The patient was initially acyanotic from 2010 to 2016, but gradually became cyanotic / Femoral artery oxygen saturation was measured at 88.5% (decreased from a previous measurement of 93.4% in 2016 / Revealed a patent foramen ovale measuring 7.34 mm in width with a continuous, pure right-to-left shunt on colo
- `D2` **Idiopathic Pulmonary Arterial Hypertension** — why: The presence of enlarged pulmonary arteries, elevated pulmonary artery pressure, and absence of parenchymal lesions support this diagnosis.
    - 支持：Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 / Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure
- `D2` **Chronic Thromboembolic Pulmonary Hypertension** — why: The patient's long history of symptoms and presence of enlarged pulmonary arteries support this diagnosis, although the absence of evidence for pulmonary embolism or fistulae is contradictory.
    - 支持：recurrent post-activity chest pain and shortness of breath for more than 11 years / Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions
    - 反对：No evidence of pulmonary embolism or pulmonary arteriovenous fistulae
- `D3` **Eisenmenger Syndrome** — why: The patient's progression from acyanotic to cyanotic, combined with the presence of a patent foramen ovale and right-to-left shunt, suggests Eisenmenger Syndrome.
    - 支持：The patient was initially acyanotic from 2010 to 2016, but gradually became cyanotic / Femoral artery oxygen saturation was measured at 88.5% (decreased from a previous measurement of 93.4% in 2016 / Transesophageal Echocardiography...Revealed a patent foramen ovale measuring 7.34 mm in width with a continuou
- `D3` **Chronic Thromboembolic Pulmonary Hypertension** — why: The patient's symptoms and imaging findings, such as enlarged hilar shadow and widened pulmonary arteries, could be indicative of Chronic Thromboembolic Pulmonary Hypertension, although the lack of evidence of pulmonary embolism or arteriovenous fistulae on pu
    - 支持：Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / Estimated pulmonary artery systolic pressure of 55 mmHg in 2021
    - 反对：Pulmonary Angiography...No evidence of pulmonary embolism or pulmonary arteriovenous fistulae
- `D3` **Idiopathic Pulmonary Arterial Hypertension** — why: The patient's elevated pulmonary artery systolic pressure and right heart enlargement suggest Idiopathic Pulmonary Arterial Hypertension.
    - 支持：Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 / Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation

</details>

<details><summary>selector 淘汰理由</summary>

- **Chronic Thromboembolic Pulmonary Hypertension** — Lack of evidence for pulmonary embolism or arteriovenous fistulae

</details>

### forest（召回 top2_strong，判分 False，映射命中 4/4 个选项，金标关系 subtype_of）

- champion：**Eisenmenger Syndrome**　runner-up：Idiopathic Pulmonary Arterial Hypertension　margin：high
- selector 理由：The patient's symptoms, including recurrent post-activity chest pain and shortness of breath, cyanosis, and the presence of a patent foramen ovale with a right-to-left shunt, along with pulmonary hypertension, best support Eisenmenger Syndrome.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Patent Foramen Ovale | strong | 1.0 | AX_SE005 | — |
| Pulmonary Hypertension | near | 6.0 | AX_SE006 / AX_SE007 / AX_ME008 / AX_SE003 | AX_ME009 |
| Idiopathic Pulmonary Arterial Hypertension | strong | 4.75 | AX_SE004 / AX_ME010 / AX_SE006 / AX_ME012 | — |
| Eisenmenger Syndrome | none | 7.25 | AX_SE001 / AX_SE002 / AX_SE003 / AX_SE004 | — |
| Tricuspid Regurgitation | none | 2.0 | AX_SE004 / AX_ME014 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Eisenmenger Syndrome** — why: The patient's symptoms and imaging findings are consistent with Eisenmenger Syndrome, a condition characterized by pulmonary hypertension and a right-to-left shunt.
    - 支持：recurrent post-activity chest pain and shortness of breath / cyanotic after an episode of severe cough and hemoptysis / Enlarged hilar shadow and widened pulmonary arteries / Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation
- `syndrome_anatomy` **Patent Foramen Ovale** — why: The patient has a patent foramen ovale, which is a congenital heart defect that can cause a right-to-left shunt.
    - 支持：Revealed a patent foramen ovale measuring 7.34 mm in width with a continuous, pure right-to-left shunt on colo
- `syndrome_anatomy` **Pulmonary Hypertension** — why: The patient has elevated pulmonary artery pressures, which is consistent with pulmonary hypertension.
    - 支持：Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 / Pulmonary artery pressure was 60/39 mmHg
- `mechanism_etiology` **Eisenmenger Syndrome** — why: The patient's symptoms and imaging findings are consistent with Eisenmenger Syndrome, a condition characterized by pulmonary hypertension and a right-to-left shunt.
    - 支持：recurrent post-activity chest pain and shortness of breath / cyanotic after an episode of severe cough and hemoptysis / Enlarged hilar shadow and widened pulmonary arteries / Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation
- `mechanism_etiology` **Chronic Thromboembolic Pulmonary Hypertension** — why: The patient's history of hemoptysis and imaging findings could suggest chronic thromboembolic pulmonary hypertension, but the lack of evidence of pulmonary embolism or fistulae makes this less likely.
    - 支持：severe cough and hemoptysis / Enlarged hilar shadow and widened pulmonary arteries
    - 反对：No evidence of pulmonary embolism or pulmonary arteriovenous fistulae
- `mechanism_etiology` **Idiopathic Pulmonary Arterial Hypertension** — why: The patient's imaging findings and elevated pulmonary artery pressure are consistent with idiopathic pulmonary arterial hypertension.
    - 支持：Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation / Estimated pulmonary artery systolic pressure of 55 mmHg
- `definitive_modality` **Chronic Thromboembolic Pulmonary Hypertension** — why: The patient's symptoms and imaging findings are consistent with chronic thromboembolic pulmonary hypertension, but the lack of evidence of pulmonary embolism or arteriovenous fistulae on pulmonary angiography contradicts this diagnosis.
    - 支持：Enlarged hilar shadow and widened pulmonary arteries, with no parenchymal lesions / Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure
    - 反对：No evidence of pulmonary embolism or pulmonary arteriovenous fistulae
- `definitive_modality` **Eisenmenger Syndrome** — why: The patient's progression from acyanosis to cyanosis and the presence of a patent foramen ovale with a right-to-left shunt are consistent with Eisenmenger syndrome.
    - 支持：The patient was initially acyanotic from 2010 to 2016, but gradually became cyanotic after an episode of sever / Revealed a patent foramen ovale measuring 7.34 mm in width with a continuous, pure right-to-left shunt on colo
- `definitive_modality` **Pulmonary Arterial Hypertension** — why: The patient's elevated pulmonary artery pressure is consistent with pulmonary arterial hypertension.
    - 支持：Estimated pulmonary artery systolic pressure of 55 mmHg in 2021 / Pulmonary artery pressure was 60/39 mmHg, lower than aortic pressure
- `definitive_modality` **Tricuspid Regurgitation** — why: The patient's echocardiography findings are consistent with tricuspid regurgitation.
    - 支持：Markedly enlarged right atrium and right ventricle, with tricuspid regurgitation / Showed presence of severe tricuspid regurgitation

</details>

<details><summary>selector 淘汰理由</summary>

- **Pulmonary Hypertension** — While pulmonary hypertension is present, it is not the most specific diagnosis given the additional findings of a patent foramen ovale and cyanosis.
- **Tricuspid Regurgitation** — Tricuspid regurgitation is a finding in the patient but not the primary diagnosis given the broader context of symptoms and other findings.
- **Patent Foramen Ovale** — Patent foramen ovale is a contributing factor but not the primary diagnosis when considering the full spectrum of the patient's condition, including pulmonary hypertension and cyanosis.

</details>

---

## DA_d2_seq100/119 — Eruptive pruritic papular porokeratosis (EPPP)

- 家族 DA / 层 DA_d2_seq100 / 权重 12.5
- 指南能力：本地扩展 D2_direct_but_partial_or_general（上游三源 D0_absent）
- 纳入金标的方法：impc；其中未选中：impc

### vignette 全文

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

### collapse3c（召回 miss，判分 False，映射命中 0/4 个选项，金标关系 unknown）

- champion：**Darier disease**　runner-up：　margin：
- selector 理由：The evidence of mild hyperkeratosis accompanied by parakeratosis, atrophy of the epidermis, well-developed cornoid lamellae with a decreased granular layer, and individual cell dyskeratosis specifically supports Darier disease.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Darier disease | none | 0.0 | Mild hyperkeratosis accompanied by parakeratosis / Atrophy of the epidermis / Well-developed cornoid lamellae with a decreased granular layer / Individual cell dyskeratosis | — |
| Grover disease | none | 0.0 | scattered, erythematous, annular papules measuring up to 5 mm wide / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis | a few asymptomatic brown flat papules scattered on her face |
| Pityriasis rubra pilaris | none | 0.0 | a few asymptomatic brown flat papules scattered on her face / the palms, soles, and oral mucosa were not involved | Mild hyperkeratosis accompanied by parakeratosis |
| Parakeratosis variegata | none | 0.0 | Mild hyperkeratosis accompanied by parakeratosis / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis | Atrophy of the epidermis |
| Sporiasis guttata | none | 0.0 | scattered, erythematous, annular papules measuring up to 5 mm wide / Routine blood, liver and kidney function, antistreptolysin O, C-reactive protein, antinuclear antibody, and rh | Mild hyperkeratosis accompanied by parakeratosis |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Darier disease** — why: The presence of cornoid lamellae and individual cell dyskeratosis are unusual findings that point to Darier disease.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Atrophy of the epidermis / Well-developed cornoid lamellae with a decreased granular layer / Individual cell dyskeratosis
- `c3` **Grover disease** — why: The combination of pruritic papules and a slight infiltrate of lymphocytes, histiocytes, and eosinophils is unusual and points to Grover disease.
    - 支持：scattered, erythematous, annular papules measuring up to 5 mm wide / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis
    - 反对：a few asymptomatic brown flat papules scattered on her face
- `c3` **Pityriasis rubra pilaris** — why: The presence of brown flat papules and the lack of involvement of the palms, soles, and oral mucosa are unusual findings that point to Pityriasis rubra pilaris.
    - 支持：a few asymptomatic brown flat papules scattered on her face / the palms, soles, and oral mucosa were not involved
    - 反对：Mild hyperkeratosis accompanied by parakeratosis
- `c3` **Parakeratosis variegata** — why: The combination of parakeratosis and a slight infiltrate of lymphocytes, histiocytes, and eosinophils is unusual and points to Parakeratosis variegata.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis
    - 反对：Atrophy of the epidermis
- `c3` **Sporiasis guttata** — why: The presence of scattered, erythematous, annular papules and the lack of abnormal laboratory findings are unusual and point to Psoriasus guttata.
    - 支持：scattered, erythematous, annular papules measuring up to 5 mm wide / Routine blood, liver and kidney function, antistreptolysin O, C-reactive protein, antinuclear antibody, and rh
    - 反对：Mild hyperkeratosis accompanied by parakeratosis

</details>

### multistance（召回 miss，判分 False，映射命中 0/4 个选项，金标关系 unknown）

- champion：**Grover disease**　runner-up：Dermatitis　margin：
- selector 理由：The presence of well-developed cornoid lamellae with a decreased granular layer and atrophy of the epidermis in the histopathology findings specifically supports Grover disease.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Darier disease | none | 0.0 | Mild hyperkeratosis accompanied by parakeratosis / Well-developed cornoid lamellae with a decreased granular layer / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis | the palms, soles, and oral mucosa were not involved |
| Grover disease | none | 0.0 | Mild hyperkeratosis accompanied by parakeratosis / Atrophy of the epidermis / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis / Well-developed cornoid lamellae with a decreased granular layer | — |
| Pityriasis rubra pilaris | none | 0.0 | scattered, erythematous, annular papules measuring up to 5 mm wide / a few asymptomatic brown flat papules scattered on her face / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis | the palms, soles, and oral mucosa were not involved |
| Parakeratosis variegata | none | 0.0 | Mild hyperkeratosis accompanied by parakeratosis / Atrophy of the epidermis / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis | — |
| Keratosis pilaris | none | 0.0 | scattered, erythematous, annular papules measuring up to 5 mm wide / Mild hyperkeratosis accompanied by parakeratosis / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis | — |
| Dermatitis | none | 0.0 | a 3-month history of rapidly spreading intensively pruritic papules on her extremities / scattered, erythematous, annular papules measuring up to 5 mm wide | — |
| Psoriasis | none | 0.0 | Mild hyperkeratosis accompanied by parakeratosis / Well-developed cornoid lamellae with a decreased granular layer | — |
| Lichen planus | none | 0.0 | Mild hyperkeratosis accompanied by parakeratosis / Atrophy of the epidermis | — |
| Papular urticaria | weak | 0.0 | a 3-month history of rapidly spreading intensively pruritic papules on her extremities / scattered, erythematous, annular papules measuring up to 5 mm wide | — |
| Sjögren's syndrome | none | 0.0 | Routine blood, liver and kidney function, antistreptolysin O, C-reactive protein, antinuclear antibody, and rh | intensively pruritic papules on her extremities |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Darier disease** — why: The presence of well-developed cornoid lamellae and individual cell dyskeratosis are unusual findings that point towards Darier disease.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Well-developed cornoid lamellae with a decreased granular layer / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis
- `stance:commit` **Grover disease** — why: The combination of hyperkeratosis, parakeratosis, and atrophy of the epidermis, along with a slight infiltrate, are unusual findings that could suggest Grover disease.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Atrophy of the epidermis / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis
- `stance:commit` **Pityriasis rubra pilaris** — why: The presence of scattered, erythematous, annular papules and brown flat papules, along with a slight infiltrate, are unusual findings that could point towards Pityriasis rubra pilaris.
    - 支持：scattered, erythematous, annular papules measuring up to 5 mm wide / a few asymptomatic brown flat papules scattered on her face / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis
- `stance:commit` **Parakeratosis variegata** — why: The combination of hyperkeratosis, parakeratosis, and atrophy of the epidermis, along with a slight infiltrate, are unusual findings that could suggest Parakeratosis variegata.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Atrophy of the epidermis / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis
- `stance:commit` **Keratosis pilaris** — why: The presence of scattered, erythematous, annular papules and hyperkeratosis, along with a slight infiltrate, are unusual findings that could point towards Keratosis pilaris.
    - 支持：scattered, erythematous, annular papules measuring up to 5 mm wide / Mild hyperkeratosis accompanied by parakeratosis / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis
- `stance:coverage` **Dermatitis** — why: The patient's symptoms of pruritic papules and erythematous lesions are consistent with dermatitis.
    - 支持：a 3-month history of rapidly spreading intensively pruritic papules on her extremities / scattered, erythematous, annular papules measuring up to 5 mm wide
- `stance:coverage` **Psoriasis** — why: The histopathological findings of hyperkeratosis, parakeratosis, and cornoid lamellae are characteristic of psoriasis.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Well-developed cornoid lamellae with a decreased granular layer
- `stance:coverage` **Lichen planus** — why: The combination of hyperkeratosis, parakeratosis, and epidermal atrophy is also seen in lichen planus.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Atrophy of the epidermis
- `stance:coverage` **Papular urticaria** — why: The patient's symptoms of pruritic papules and erythematous lesions could also be consistent with papular urticaria.
    - 支持：a 3-month history of rapidly spreading intensively pruritic papules on her extremities / scattered, erythematous, annular papules measuring up to 5 mm wide
- `stance:mechanism` **Grover's disease** — why: The combination of hyperkeratosis, parakeratosis, and atrophy of the epidermis, along with the presence of cornoid lamellae, is consistent with the characteristic histopathological features of Grover's disease.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Atrophy of the epidermis / Well-developed cornoid lamellae with a decreased granular layer
- `stance:mechanism` **Darier's disease** — why: The presence of hyperkeratosis, parakeratosis, and cornoid lamellae is consistent with Darier's disease, although the lack of involvement of the palms, soles, and oral mucosa is not typical.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Well-developed cornoid lamellae with a decreased granular layer
    - 反对：the palms, soles, and oral mucosa were not involved
- `stance:mechanism` **Pityriasis rubra pilaris** — why: The combination of erythematous papules and brown flat papules is consistent with Pityriasis rubra pilaris, although the lack of involvement of the palms, soles, and oral mucosa is not typical.
    - 支持：scattered, erythematous, annular papules measuring up to 5 mm wide / a few asymptomatic brown flat papules scattered on her face
    - 反对：the palms, soles, and oral mucosa were not involved
- `stance:mechanism` **Sjögren's syndrome** — why: The lack of abnormal findings on laboratory tests, including antinuclear antibody and rheumatoid factor, makes Sjögren's syndrome less likely, but the presence of pruritic papules could be consistent with an autoimmune process.
    - 支持：Routine blood, liver and kidney function, antistreptolysin O, C-reactive protein, antinuclear antibody, and rh
    - 反对：intensively pruritic papules on her extremities

</details>

### impc（召回 set_strong，判分 False，映射命中 0/4 个选项，金标关系 unknown）

- champion：**Darier's disease**　runner-up：Grover's disease　margin：medium
- selector 理由：Darier's disease is supported by multiple findings including mild hyperkeratosis, parakeratosis, well-developed cornoid lamellae, and individual cell dyskeratosis, which are characteristic of the condition.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Porokeratosis | strong | 2.0 | D1E002 / D2E005 | — |
| Darier's disease | none | 3.7 | D1E001 / D1E002 / D1E003 | — |
| Grover's disease | none | 3.35 | D1E001 / D2E004 / D2E005 | — |
| Actinic keratosis | none | 1.0 | D3E006 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Darier's disease** — why: The presence of cornoid lamellae, hyperkeratosis, and individual cell dyskeratosis are characteristic features of Darier's disease.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Well-developed cornoid lamellae with a decreased granular layer / Individual cell dyskeratosis
- `D2` **Darier's disease** — why: The presence of individual cell dyskeratosis and well-developed cornoid lamellae are characteristic features of Darier's disease.
    - 支持：Individual cell dyskeratosis / Well-developed cornoid lamellae with a decreased granular layer
- `D2` **Grover's disease** — why: The combination of hyperkeratosis, parakeratosis, and a slight infiltrate of lymphocytes, histiocytes, and eosinophils is consistent with Grover's disease.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis
- `D2` **Porokeratosis** — why: The presence of well-developed cornoid lamellae and vacuolar degeneration of the basal cell layer are characteristic features of porokeratosis.
    - 支持：Well-developed cornoid lamellae with a decreased granular layer / Vacuolar degeneration of the basal cell layer
- `D3` **Darier's disease** — why: The presence of individual cell dyskeratosis and cornoid lamellae are characteristic features of Darier's disease.
    - 支持：Individual cell dyskeratosis / Well-developed cornoid lamellae with a decreased granular layer
- `D3` **Grover's disease** — why: The combination of hyperkeratosis, parakeratosis, and vacuolar degeneration of the basal cell layer can be seen in Grover's disease.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Vacuolar degeneration of the basal cell layer
- `D3` **Actinic keratosis** — why: The presence of keratotic papules, especially on sun-exposed areas like the extremities, is suggestive of actinic keratosis.
    - 支持：Keratotic papules diffusely distributed on an extremity

</details>

<details><summary>selector 淘汰理由</summary>

- **Porokeratosis** — Although it shares some features like cornoid lamellae, the overall clinical and histological picture fits better with Darier's disease.
- **Actinic keratosis** — The presence of keratotic papules is not specific and the lack of other supporting features makes it less likely than Darier's disease.

</details>

### forest（召回 miss，判分 False，映射命中 0/4 个选项，金标关系 unknown）

- champion：**Grover's disease**　runner-up：Darier's disease　margin：medium
- selector 理由：Grover's disease is supported by mild hyperkeratosis, parakeratosis, individual cell dyskeratosis, and vacuolar degeneration of the basal cell layer, which are all consistent with the provided histopathology findings.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Grover's disease | none | 6.25 | AX_SE001 / AX_SE002 / AX_SE003 / AX_ME006 | — |
| Darier's disease | none | 5.25 | AX_SE002 / AX_SE004 / AX_ME005 / AX_SE003 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Grover's disease** — why: The patient's symptoms and histopathology results, including hyperkeratosis, parakeratosis, and individual cell dyskeratosis, are consistent with Grover's disease.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Individual cell dyskeratosis / Vacuolar degeneration of the basal cell layer
- `syndrome_anatomy` **Darier's disease** — why: The presence of individual cell dyskeratosis in the histopathology results could suggest Darier's disease, although other characteristic features are not mentioned.
    - 支持：Individual cell dyskeratosis / Suprabasal acantholytic dyskeratosis is not mentioned but the presence of dyskeratosis is a clue
- `mechanism_etiology` **Darier's disease** — why: The presence of individual cell dyskeratosis, cornoid lamellae, and vacuolar degeneration of the basal cell layer are characteristic histopathological features of Darier's disease.
    - 支持：Individual cell dyskeratosis / Well-developed cornoid lamellae with a decreased granular layer / Vacuolar degeneration of the basal cell layer
- `mechanism_etiology` **Grover's disease** — why: The combination of hyperkeratosis, parakeratosis, and atrophy of the epidermis, along with a slight inflammatory infiltrate, are features that can be seen in Grover's disease.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Atrophy of the epidermis / Slight infiltrate of lymphocytes, histiocytes, and eosinophils in the upper dermis
- `definitive_modality` **Grover's disease** — why: The presence of hyperkeratosis, parakeratosis, and individual cell dyskeratosis in the histopathology results supports the diagnosis of Grover's disease.
    - 支持：Mild hyperkeratosis accompanied by parakeratosis / Individual cell dyskeratosis / Vacuolar degeneration of the basal cell layer
- `definitive_modality` **Darier's disease** — why: The presence of cornoid lamellae and individual cell dyskeratosis in the histopathology results supports the diagnosis of Darier's disease.
    - 支持：Well-developed cornoid lamellae with a decreased granular layer / Individual cell dyskeratosis

</details>

<details><summary>selector 淘汰理由</summary>

- **Darier's disease** — While Darier's disease shares some histopathological features like individual cell dyskeratosis, the presence of well-developed cornoid lamellae and the specific pattern of dyskeratosis and acantholysis are more characteristic of Grover's disease in this conte

</details>

---

## DA_d2_seq100/19 — Follicular thyroid carcinoma with manubrial invasion

- 家族 DA / 层 DA_d2_seq100 / 权重 12.5
- 指南能力：本地扩展 D2_direct_but_partial_or_general（上游三源 D2_direct_but_partial_or_general）
- 纳入金标的方法：multistance, impc, forest；其中未选中：multistance

### vignette 全文

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

### collapse3c（召回 miss，判分 True，映射命中 3/4 个选项，金标关系 equivalent）

- champion：**Recurrent Thyroid Cancer**　runner-up：Thyroid Metastasis to Bone　margin：
- selector 理由：The presence of follicular thyroid cells in both the goiter and the manubrial lesion, along with the patient's history of previous thyroid surgery, decided it.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Thyroid Metastasis to Bone | weak | 0.0 | lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm / Revealed follicular thyroid cells in the goiter and the manubrial lesion / Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae | — |
| Recurrent Thyroid Cancer | weak | 0.0 | 12 years after resection of a large left substernal thyroid lobe through a midline sternotomy approach / residual right goiter / Revealed follicular thyroid cells in the goiter and the manubrial lesion | — |
| Brown Tumor | none | 0.0 | lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm / The posterior aspect is in close proximity to the brachiocephalic artery and the left innominate vein | Revealed follicular thyroid cells in the goiter and the manubrial lesion |
| Giant Cell Tumor | none | 0.0 | lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm | Revealed follicular thyroid cells in the goiter and the manubrial lesion |
| Fibrous Dysplasia | none | 0.0 | lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm | Revealed follicular thyroid cells in the goiter and the manubrial lesion |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Thyroid Metastasis to Bone** — why: The presence of a lytic lesion in the manubrium with thyroid follicles infiltrating adjacent to bone trabeculae is unusual and points to thyroid metastasis to bone.
    - 支持：lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm / Revealed follicular thyroid cells in the goiter and the manubrial lesion / Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae
- `c3` **Recurrent Thyroid Cancer** — why: The history of previous thyroid surgery and the presence of residual goiter with follicular thyroid cells in the manubrial lesion suggest recurrent thyroid cancer.
    - 支持：12 years after resection of a large left substernal thyroid lobe through a midline sternotomy approach / residual right goiter / Revealed follicular thyroid cells in the goiter and the manubrial lesion
- `c3` **Brown Tumor** — why: The presence of a lytic lesion in the manubrium could be consistent with a brown tumor, although the presence of thyroid cells in the lesion argues against this diagnosis.
    - 支持：lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm / The posterior aspect is in close proximity to the brachiocephalic artery and the left innominate vein
    - 反对：Revealed follicular thyroid cells in the goiter and the manubrial lesion
- `c3` **Giant Cell Tumor** — why: The presence of a lytic lesion in the manubrium could be consistent with a giant cell tumor, although the presence of thyroid cells in the lesion argues against this diagnosis.
    - 支持：lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm
    - 反对：Revealed follicular thyroid cells in the goiter and the manubrial lesion
- `c3` **Fibrous Dysplasia** — why: The presence of a lytic lesion in the manubrium could be consistent with fibrous dysplasia, although the presence of thyroid cells in the lesion argues against this diagnosis.
    - 支持：lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm
    - 反对：Revealed follicular thyroid cells in the goiter and the manubrial lesion

</details>

### multistance（召回 set_strong，判分 False，映射命中 3/4 个选项，金标关系 equivalent）

- champion：**Thyroid metastasis to bone**　runner-up：Thyroid cancer with local invasion　margin：
- selector 理由：The champion accounts for the most decisive findings including the lytic lesion and the presence of follicular thyroid cells in the manubrial lesion.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Follicular thyroid carcinoma | strong | 0.0 | Revealed follicular thyroid cells in the goiter and the manubrial lesion / Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae | — |
| Thyroid metastasis to bone | weak | 0.0 | lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm / Revealed follicular thyroid cells in the goiter and the manubrial lesion / Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae | — |
| Recurrent thyroid goiter | weak | 0.0 | 12 years after resection of a large left substernal thyroid lobe through a midline sternotomy approach / residual right goiter / Medical history includes previous substernal left hemithyroidectomy for benign goiter 12 years ago | Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae |
| Thyroid cancer with bone invasion | weak | 0.0 | lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm / The posterior aspect is in close proximity to the brachiocephalic artery and the left innominate vein / Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae | — |
| Bone metastasis from other primary cancer | none | 0.0 | lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm | Revealed follicular thyroid cells in the goiter and the manubrial lesion |
| Thyroid cancer | weak | 0.0 | Revealed follicular thyroid cells in the goiter and the manubrial lesion / Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae | — |
| Bone tumor | none | 0.0 | lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm | — |
| Metastatic disease | none | 0.0 | The posterior aspect is in close proximity to the brachiocephalic artery and the left innominate vein | — |
| Benign bone cyst | none | 0.0 | lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm | Revealed follicular thyroid cells in the goiter and the manubrial lesion |
| Thyroid cancer with local invasion | weak | 0.0 | The posterior aspect is in close proximity to the brachiocephalic artery and the left innominate vein / Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae | — |
| Recurrent goiter | none | 0.0 | residual right goiter / Medical history includes previous substernal left hemithyroidectomy for benign goiter 12 years ago | — |
| Thyroid osteopathy | weak | 0.0 | lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm / The posterior aspect is in close proximity to the brachiocephalic artery and the left innominate vein | — |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Thyroid metastasis to bone** — why: The presence of a lytic lesion in the manubrium with thyroid follicles infiltrating adjacent to bone trabeculae is unusual and points to thyroid metastasis to bone.
    - 支持：lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm / Revealed follicular thyroid cells in the goiter and the manubrial lesion / Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae
- `stance:commit` **Recurrent thyroid goiter** — why: The history of previous substernal left hemithyroidectomy for benign goiter and the presence of a residual right goiter suggest recurrent thyroid goiter.
    - 支持：12 years after resection of a large left substernal thyroid lobe through a midline sternotomy approach / residual right goiter / Medical history includes previous substernal left hemithyroidectomy for benign goiter 12 years ago
    - 反对：Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae
- `stance:commit` **Thyroid cancer with bone invasion** — why: The presence of a lytic lesion in the manubrium with thyroid follicles infiltrating adjacent to bone trabeculae and the close proximity to major vessels suggest thyroid cancer with bone invasion.
    - 支持：lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm / The posterior aspect is in close proximity to the brachiocephalic artery and the left innominate vein / Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae
- `stance:commit` **Follicular thyroid carcinoma** — why: The presence of follicular thyroid cells in the goiter and the manubrial lesion suggests follicular thyroid carcinoma.
    - 支持：Revealed follicular thyroid cells in the goiter and the manubrial lesion / Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae
- `stance:commit` **Bone metastasis from other primary cancer** — why: The presence of a lytic lesion in the manubrium could suggest bone metastasis from another primary cancer, but the presence of thyroid cells in the lesion makes this less likely.
    - 支持：lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm
    - 反对：Revealed follicular thyroid cells in the goiter and the manubrial lesion
- `stance:coverage` **Thyroid cancer** — why: The presence of follicular thyroid cells in the manubrial lesion and the infiltration of thyroid follicles into bone trabeculae suggest a malignant process.
    - 支持：Revealed follicular thyroid cells in the goiter and the manubrial lesion / Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae
- `stance:coverage` **Bone tumor** — why: The lytic lesion in the manubrium could be a primary bone tumor, which needs to be considered in the differential diagnosis.
    - 支持：lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm
- `stance:coverage` **Metastatic disease** — why: The proximity of the lesion to major vessels raises the possibility of metastatic disease, which must be excluded.
    - 支持：The posterior aspect is in close proximity to the brachiocephalic artery and the left innominate vein
- `stance:coverage` **Benign bone cyst** — why: A benign bone cyst is a possible diagnosis, although the presence of follicular thyroid cells in the lesion makes this less likely.
    - 支持：lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm
    - 反对：Revealed follicular thyroid cells in the goiter and the manubrial lesion
- `stance:mechanism` **Thyroid metastasis to bone** — why: The presence of a lytic lesion in the manubrium with follicular thyroid cells suggests metastasis from a thyroid primary.
    - 支持：lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm / Revealed follicular thyroid cells in the goiter and the manubrial lesion
- `stance:mechanism` **Thyroid cancer with local invasion** — why: The close proximity of the thyroid tissue to major vessels and the infiltration of thyroid follicles into bone trabeculae suggest local invasion.
    - 支持：The posterior aspect is in close proximity to the brachiocephalic artery and the left innominate vein / Hematoxylin-eosin stained specimens showing thyroid follicles infiltrating adjacent to bone trabeculae
- `stance:mechanism` **Recurrent goiter** — why: The presence of a residual right goiter and a history of previous goiter resection suggest a recurrent goiter.
    - 支持：residual right goiter / Medical history includes previous substernal left hemithyroidectomy for benign goiter 12 years ago
- `stance:mechanism` **Thyroid osteopathy** — why: The presence of a lytic lesion in the manubrium with proximity to major vessels suggests thyroid osteopathy.
    - 支持：lytic lesion replacing the manubrium measuring 2.7 × 4.4 × 5.8 cm / The posterior aspect is in close proximity to the brachiocephalic artery and the left innominate vein

</details>

### impc（召回 set_near，判分 True，映射命中 3/4 个选项，金标关系 subtype_of）

- champion：**Metastatic follicular thyroid carcinoma**　runner-up：Metastatic Thyroid Cancer　margin：high
- selector 理由：The presence of follicular thyroid cells in the goiter and the manubrial lesion, along with thyroid follicles infiltrating adjacent to bone trabeculae, strongly supports metastatic follicular thyroid carcinoma.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Metastatic follicular thyroid carcinoma | near | 3.0 | D1E001 / D1E002 / D1E003 | — |
| Metastatic Thyroid Cancer | weak | 3.0 | D1E001 / D1E002 / D1E003 | — |
| Thyroid metastasis to bone | weak | 3.0 | D1E001 / D1E002 / D1E003 | — |
| Recurrent goiter | none | 2.0 | D2E004 / D2E005 | — |
| Thyroid cancer with bone metastasis | weak | 2.0 | D1E001 / D1E003 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Metastatic Thyroid Cancer** — why: The presence of thyroid cells in the manubrial lesion and the history of previous thyroid surgery suggest metastatic disease.
    - 支持：lytic lesion replacing the manubrium / follicular thyroid cells in the goiter and the manubrial lesion / thyroid follicles infiltrating adjacent to bone trabeculae
- `D2` **Thyroid metastasis to bone** — why: The presence of follicular thyroid cells in the manubrial lesion and the lytic lesion replacing the manubrium suggests metastasis of thyroid tissue to the bone.
    - 支持：lytic lesion replacing the manubrium / follicular thyroid cells in the goiter and the manubrial lesion / thyroid follicles infiltrating adjacent to bone trabeculae
- `D2` **Recurrent goiter** — why: The patient's history of previous goiter and the presence of a residual right goiter suggest the possibility of recurrent goiter.
    - 支持：previous substernal left hemithyroidectomy for benign goiter 12 years ago / residual right goiter
- `D2` **Thyroid cancer with bone metastasis** — why: The aggressive nature of the lytic lesion and the infiltration of thyroid follicles into bone trabeculae raise the possibility of thyroid cancer with bone metastasis.
    - 支持：lytic lesion replacing the manubrium / thyroid follicles infiltrating adjacent to bone trabeculae
- `D3` **Metastatic follicular thyroid carcinoma** — why: The presence of a lytic lesion in the manubrium with follicular thyroid cells and the infiltration of thyroid follicles into bone trabeculae suggests metastatic disease.
    - 支持：lytic lesion replacing the manubrium / follicular thyroid cells in the goiter and the manubrial lesion / thyroid follicles infiltrating adjacent to bone trabeculae

</details>

<details><summary>selector 淘汰理由</summary>

- **Recurrent goiter** — Lytic lesion replacing the manubrium and thyroid follicles infiltrating bone trabeculae suggest malignancy rather than benign goiter recurrence.
- **Thyroid metastasis to bone** — While this is a possible diagnosis, metastatic follicular thyroid carcinoma is more specific and better supported by the evidence.
- **Thyroid cancer with bone metastasis** — This diagnosis is less specific than metastatic follicular thyroid carcinoma and does not fully capture the nature of the thyroid cells involved.

</details>

### forest（召回 set_near，判分 True，映射命中 4/4 个选项，金标关系 subtype_of）

- champion：**Metastatic thyroid carcinoma**　runner-up：Bone metastasis from well-differentiated thyroid cancer　margin：high
- selector 理由：lytic lesion replacing the manubrium and follicular thyroid cells in the goiter and the manubrial lesion with thyroid follicles infiltrating adjacent to bone trabeculae

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Metastatic thyroid carcinoma | near | 3.0 | AX_SE001 / AX_SE002 / AX_ME005 | — |
| Thyroid metastasis to bone | weak | 2.5 | AX_SE001 / AX_SE002 | — |
| Recurrent goiter | none | 2.0 | AX_SE003 / AX_SE004 | — |
| Recurrent thyroid goiter | weak | 2.0 | AX_SE003 / AX_SE002 | — |
| Bone metastasis from well-differentiated thyroid cancer | weak | 2.0 | AX_SE001 / AX_ME005 | — |
| Thyroid goiter with metastasis | weak | 2.0 | AX_SE003 / AX_SE002 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Thyroid metastasis to bone** — why: The presence of thyroid follicles in the manubrial lesion suggests metastasis from the previous thyroid goiter.
    - 支持：lytic lesion replacing the manubrium / follicular thyroid cells in the goiter and the manubrial lesion
- `syndrome_anatomy` **Recurrent goiter** — why: The history of previous goiter resection and the presence of a residual goiter suggest a recurrent goiter.
    - 支持：residual right goiter / previous substernal left hemithyroidectomy for benign goiter
- `mechanism_etiology` **Thyroid metastasis to bone** — why: The presence of thyroid follicles in the manubrial lesion suggests metastasis from the previous thyroid goiter.
    - 支持：lytic lesion replacing the manubrium / follicular thyroid cells in the goiter and the manubrial lesion
- `mechanism_etiology` **Recurrent thyroid goiter** — why: The presence of residual right goiter and follicular thyroid cells in the manubrial lesion suggests recurrence of the thyroid goiter.
    - 支持：residual right goiter / follicular thyroid cells in the goiter and the manubrial lesion
- `mechanism_etiology` **Bone metastasis from well-differentiated thyroid cancer** — why: The presence of a lytic lesion in the manubrium and thyroid follicles infiltrating bone trabeculae suggests metastasis from a well-differentiated thyroid cancer.
    - 支持：lytic lesion replacing the manubrium / thyroid follicles infiltrating adjacent to bone trabeculae
- `definitive_modality` **Metastatic thyroid carcinoma** — why: The presence of a lytic lesion in the manubrium with follicular thyroid cells and thyroid follicles infiltrating bone trabeculae suggests metastatic thyroid carcinoma.
    - 支持：lytic lesion replacing the manubrium / follicular thyroid cells in the goiter and the manubrial lesion / thyroid follicles infiltrating adjacent to bone trabeculae
- `definitive_modality` **Thyroid goiter with metastasis** — why: The presence of a residual right goiter and follicular thyroid cells in both the goiter and the manubrial lesion suggests a benign goiter with metastasis.
    - 支持：residual right goiter / follicular thyroid cells in the goiter and the manubrial lesion

</details>

<details><summary>selector 淘汰理由</summary>

- **Recurrent goiter** — lack of evidence for goiter recurrence as the primary cause of the lytic lesion
- **Recurrent thyroid goiter** — similar to recurrent goiter, lacks direct evidence linking it as the primary cause of the lytic lesion
- **Thyroid goiter with metastasis** — while it mentions metastasis, it's less specific than metastatic thyroid carcinoma
- **Thyroid metastasis to bone** — less specific and detailed than metastatic thyroid carcinoma in explaining the findings

</details>

---

## DA_d2_seq100/5 — Left maxillary giant cell reparative granuloma (GCRG)

- 家族 DA / 层 DA_d2_seq100 / 权重 12.5
- 指南能力：本地扩展 D3_direct_vignette_matched（上游三源 D1_parent_component_or_list_only）
- 纳入金标的方法：collapse3c, multistance, impc, forest；其中未选中：impc

### vignette 全文

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

### collapse3c（召回 set_near，判分 True，映射命中 3/4 个选项，金标关系 subtype_of）

- champion：**Giant Cell Tumor**　runner-up：　margin：
- selector 理由：The presence of a spindle cell process in a patternless arrangement with significant multinucleated giant cells and the lack of cytologic atypia decided it.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Giant Cell Tumor | near | 0.0 | spindle cell process in a patternless arrangement with significant multinucleated giant cells / Displacement of inferior rectus without muscle invasion / heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus | — |
| Juvenile Nasopharyngeal Angiofibroma | none | 0.0 | Mass eroded the orbital floor, medial and posterior maxillary walls, and anterior ethmoid air cells / Mild left-sided proptosis was present | spindle cell process in a patternless arrangement with significant multinucleated giant cells |
| Maxillary Sinus Squamous Cell Carcinoma | weak | 0.0 | heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus | No cytologic atypia / spindle cell process in a patternless arrangement with significant multinucleated giant cells |
| Fibrous Dysplasia | none | 0.0 | Mass eroded the orbital floor, medial and posterior maxillary walls, and anterior ethmoid air cells | spindle cell process in a patternless arrangement with significant multinucleated giant cells |
| Chordoma | none | 0.0 | spindle cell process in a patternless arrangement with significant multinucleated giant cells | No extension beyond cribriform plate |
| Invasive fungal sinusitis | none | 0.0 | — | — |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Giant Cell Tumor** — why: The presence of significant multinucleated giant cells in a spindle cell process is unusual and points to Giant Cell Tumor.
    - 支持：spindle cell process in a patternless arrangement with significant multinucleated giant cells / Displacement of inferior rectus without muscle invasion / heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus
- `c3` **Juvenile Nasopharyngeal Angiofibroma** — why: The erosion of the orbital floor and presence of proptosis are unusual findings that could suggest Juvenile Nasopharyngeal Angiofibroma, but the histological findings do not support this diagnosis.
    - 支持：Mass eroded the orbital floor, medial and posterior maxillary walls, and anterior ethmoid air cells / Mild left-sided proptosis was present
    - 反对：spindle cell process in a patternless arrangement with significant multinucleated giant cells
- `c3` **Maxillary Sinus Squamous Cell Carcinoma** — why: The presence of a heterogeneous mass in the maxillary sinus could suggest a malignant process like Maxillary Sinus Squamous Cell Carcinoma, but the lack of cytologic atypia and the specific histological findings do not support this diagnosis.
    - 支持：heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus
    - 反对：No cytologic atypia / spindle cell process in a patternless arrangement with significant multinucleated giant cells
- `c3` **Fibrous Dysplasia** — why: The erosion of the surrounding bone could suggest Fibrous Dysplasia, but the histological findings do not support this diagnosis.
    - 支持：Mass eroded the orbital floor, medial and posterior maxillary walls, and anterior ethmoid air cells
    - 反对：spindle cell process in a patternless arrangement with significant multinucleated giant cells
- `c3` **Chordoma** — why: The presence of a spindle cell process with significant multinucleated giant cells could suggest Chordoma, but the location and lack of extension beyond the cribriform plate do not support this diagnosis.
    - 支持：spindle cell process in a patternless arrangement with significant multinucleated giant cells
    - 反对：No extension beyond cribriform plate

</details>

### multistance（召回 set_near，判分 True，映射命中 3/4 个选项，金标关系 subtype_of）

- champion：**Giant Cell Tumor**　runner-up：Nasal tumor　margin：
- selector 理由：The champion is chosen because it provides the most detailed and specific evidence, including histological findings, that directly match the patient's condition, making it a more precise diagnosis than the runner-up.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Giant Cell Tumor | near | 0.0 | spindle cell process in a patternless arrangement with significant multinucleated giant cells / Bony changes showed remodeling and thinning / No cytologic atypia / a heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus | — |
| Juvenile Nasopharyngeal Angiofibroma | none | 0.0 | Mass eroded the orbital floor, medial and posterior maxillary walls, and anterior ethmoid air cells / Left maxillary alveolar ridge and several molar roots involved | No cytologic atypia |
| Sinonasal Undifferentiated Carcinoma | none | 0.0 | heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus / Displacement of inferior rectus without muscle invasion | spindle cell process in a patternless arrangement with significant multinucleated giant cells |
| Fibrous Dysplasia | none | 0.0 | Bony changes showed remodeling and thinning | Mass eroded the orbital floor, medial and posterior maxillary walls, and anterior ethmoid air cells / spindle cell process in a patternless arrangement with significant multinucleated giant cells |
| Chordoma | none | 0.0 | spindle cell process in a patternless arrangement / a heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus | No extension beyond cribriform plate |
| Nasal tumor | none | 0.0 | left nasal mass / heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus | — |
| Sinusitis | none | 0.0 | sinus pressure and facial swelling | — |
| Orbital tumor | none | 0.0 | Mild left-sided proptosis / Displacement of inferior rectus without muscle invasion | — |
| Granulomatosis with polyangiitis | weak | 0.0 | sinus pressure and facial swelling / external deviation of her nasal septum | — |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Giant Cell Tumor** — why: The presence of significant multinucleated giant cells and spindle cell process in a patternless arrangement earned this slot.
    - 支持：spindle cell process in a patternless arrangement with significant multinucleated giant cells / Bony changes showed remodeling and thinning / No cytologic atypia
- `stance:commit` **Juvenile Nasopharyngeal Angiofibroma** — why: The aggressive nature of the mass, eroding the orbital floor and involving the maxillary alveolar ridge, earned this slot.
    - 支持：Mass eroded the orbital floor, medial and posterior maxillary walls, and anterior ethmoid air cells / Left maxillary alveolar ridge and several molar roots involved
    - 反对：No cytologic atypia
- `stance:commit` **Sinonasal Undifferentiated Carcinoma** — why: The presence of a heterogeneous mass with solid and cystic components and displacement of the inferior rectus earned this slot.
    - 支持：heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus / Displacement of inferior rectus without muscle invasion
    - 反对：spindle cell process in a patternless arrangement with significant multinucleated giant cells
- `stance:commit` **Fibrous Dysplasia** — why: The presence of bony changes with remodeling and thinning earned this slot.
    - 支持：Bony changes showed remodeling and thinning
    - 反对：Mass eroded the orbital floor, medial and posterior maxillary walls, and anterior ethmoid air cells
- `stance:commit` **Chordoma** — why: The presence of a spindle cell process in a patternless arrangement earned this slot.
    - 支持：spindle cell process in a patternless arrangement
    - 反对：No extension beyond cribriform plate
- `stance:coverage` **Nasal tumor** — why: The presence of a left nasal mass and a heterogeneous mass in the left maxillary sinus cannot be skipped as it is a significant finding that requires further investigation.
    - 支持：left nasal mass / heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus
- `stance:coverage` **Sinusitis** — why: The symptoms of sinus pressure and facial swelling could be indicative of sinusitis, which is a common condition that needs to be considered in the differential diagnosis.
    - 支持：sinus pressure and facial swelling
- `stance:coverage` **Orbital tumor** — why: The presence of mild left-sided proptosis and displacement of the inferior rectus muscle could be indicative of an orbital tumor, which is a potentially serious condition that requires further evaluation.
    - 支持：Mild left-sided proptosis / Displacement of inferior rectus without muscle invasion
- `stance:coverage` **Granulomatosis with polyangiitis** — why: The combination of sinus pressure, facial swelling, and external deviation of the nasal septum could be indicative of granulomatosis with polyangiitis, which is a rare but potentially serious condition that needs to be considered in the differential diagnosis.
    - 支持：sinus pressure and facial swelling / external deviation of her nasal septum
- `stance:mechanism` **Giant Cell Tumor** — why: The presence of a heterogeneous mass with solid and cystic components, along with the histological findings of a spindle cell process and significant multinucleated giant cells, suggests a Giant Cell Tumor, which is a type of benign but locally aggressive neop
    - 支持：a heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus / spindle cell process in a patternless arrangement with significant multinucleated giant cells
- `stance:mechanism` **Juvenile Nasopharyngeal Angiofibroma** — why: The aggressive nature of the mass, with erosion of surrounding structures and involvement of the maxillary alveolar ridge, is consistent with a Juvenile Nasopharyngeal Angiofibroma, although the lack of cytologic atypia is not typical for this diagnosis.
    - 支持：Mass eroded the orbital floor, medial and posterior maxillary walls, and anterior ethmoid air cells / Left maxillary alveolar ridge and several molar roots involved
    - 反对：No cytologic atypia
- `stance:mechanism` **Fibrous Dysplasia** — why: The bony changes with remodeling and thinning are consistent with Fibrous Dysplasia, a non-neoplastic condition that can cause bone lesions, although the presence of a spindle cell process with multinucleated giant cells is not typical for this diagnosis.
    - 支持：Bony changes showed remodeling and thinning
    - 反对：spindle cell process in a patternless arrangement with significant multinucleated giant cells
- `stance:mechanism` **Chordoma** — why: The presence of a heterogeneous mass with solid and cystic components is consistent with a Chordoma, a rare malignant neoplasm, although the lack of extension beyond the cribriform plate is not typical for this diagnosis.
    - 支持：a heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus
    - 反对：No extension beyond cribriform plate

</details>

### impc（召回 set_near，判分 False，映射命中 0/4 个选项，金标关系 unrelated）

- champion：**Juvenile Nasopharyngeal Angiofibroma**　runner-up：Fibrous Dysplasia　margin：medium
- selector 理由：The presence of a heterogeneous mass with solid and cystic components in the left maxillary sinus, along with significant sinus pressure and facial swelling, best supports Juvenile Nasopharyngeal Angiofibroma.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Giant Cell Tumor | near | 2.7 | D1E007 / D2E009 | — |
| Juvenile Nasopharyngeal Angiofibroma | none | 5.7 | D1E001 / D1E002 / D1E003 / D1E004 | — |
| Fibrous Dysplasia | none | 3.7 | D1E005 / D1E006 / D2E010 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Juvenile Nasopharyngeal Angiofibroma** — why: The patient's symptoms and imaging results are consistent with a highly vascular tumor, such as Juvenile Nasopharyngeal Angiofibroma, which is common in teenage males but can also occur in females.
    - 支持：several months of sinus pressure and facial swelling / a left nasal mass was noted / a heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus / Mass eroded the orbital floor, medial and posterior maxillary walls, and anterior ethmoid air cells
- `D1` **Fibrous Dysplasia** — why: The presence of bony changes and remodeling suggests a possible diagnosis of Fibrous Dysplasia, which can cause expansion and thinning of bone.
    - 支持：bony changes showed remodeling and thinning / displacement of inferior rectus without muscle invasion
- `D1` **Giant Cell Tumor** — why: The biopsy results showing significant multinucleated giant cells are consistent with a Giant Cell Tumor, which can occur in the maxillary sinus.
    - 支持：tissue analysis showed spindle cell process in a patternless arrangement with significant multinucleated giant
- `D2` **Juvenile Nasopharyngeal Angiofibroma** — why: The patient's symptoms and imaging results are consistent with a highly vascular tumor, and the presence of a heterogeneous mass with solid and cystic components in the maxillary sinus is suggestive of Juvenile Nasopharyngeal Angiofibroma.
    - 支持：several months of sinus pressure and facial swelling / a left nasal mass was noted / Mild left-sided proptosis was present / a heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus
- `D2` **Giant Cell Tumor** — why: The biopsy results showing significant multinucleated giant cells are consistent with a Giant Cell Tumor.
    - 支持：Tissue analysis showed spindle cell process in a patternless arrangement with significant multinucleated giant
- `D2` **Fibrous Dysplasia** — why: The bony changes showing remodeling and thinning are consistent with Fibrous Dysplasia, although the presence of a heterogeneous mass is not typical for this condition.
    - 支持：Bony changes showed remodeling and thinning
- `D3` **Juvenile Nasopharyngeal Angiofibroma** — why: The patient's symptoms and imaging results are consistent with a highly vascular tumor, which is typical of Juvenile Nasopharyngeal Angiofibroma.
    - 支持：several months of sinus pressure and facial swelling / a left nasal mass was noted / Mild left-sided proptosis was present / a heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus
- `D3` **Fibrous Dysplasia** — why: The bony changes described in the imaging results could be indicative of Fibrous Dysplasia, a condition that can cause bone lesions and remodeling.
    - 支持：Bony changes showed remodeling and thinning
- `D3` **Giant Cell Tumor** — why: The presence of multinucleated giant cells in the biopsy results is a characteristic feature of Giant Cell Tumor, which could be a possible diagnosis for the patient's condition.
    - 支持：Tissue analysis showed spindle cell process in a patternless arrangement with significant multinucleated giant

</details>

<details><summary>selector 淘汰理由</summary>

- **Giant Cell Tumor** — Although tissue analysis showed significant multinucleated giant cells, the overall clinical and imaging findings better align with Juvenile Nasopharyngeal Angiofibroma.

</details>

### forest（召回 set_near，判分 True，映射命中 3/4 个选项，金标关系 subtype_of）

- champion：**Juvenile Nasopharyngeal Angiofibroma**　runner-up：Giant Cell Tumor　margin：high
- selector 理由：The presence of a left nasal mass, mild left-sided proptosis, and several months of sinus pressure and facial swelling strongly support Juvenile Nasopharyngeal Angiofibroma, which is further confirmed by the imaging studies showing a heterogeneous mass in the left maxillary sinus.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Giant Cell Tumor | near | 2.5 | AX_SE002 / AX_ME012 | — |
| Juvenile Nasopharyngeal Angiofibroma | none | 9.0 | AX_SE003 / AX_SE004 / AX_SE005 / AX_SE001 | — |
| Fibrous Dysplasia | none | 2.5 | AX_SE006 / AX_SE007 | — |
| Granulomatosis with Polyangiitis | weak | 2.0 | AX_ME011 / AX_ME009 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Juvenile Nasopharyngeal Angiofibroma** — why: The patient's symptoms and imaging results are consistent with a vascular tumor in the nasal cavity.
    - 支持：several months of sinus pressure and facial swelling / left nasal mass / Mild left-sided proptosis / heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus
- `syndrome_anatomy` **Fibrous Dysplasia** — why: The patient's imaging results show bony changes consistent with fibrous dysplasia.
    - 支持：bony changes showed remodeling and thinning / left maxillary alveolar ridge and several molar roots involved
- `syndrome_anatomy` **Giant Cell Tumor** — why: The patient's biopsy results are consistent with a giant cell tumor.
    - 支持：tissue analysis showed spindle cell process in a patternless arrangement with significant multinucleated giant
- `mechanism_etiology` **Juvenile Nasopharyngeal Angiofibroma** — why: The presence of a nasal mass, proptosis, and a heterogeneous mass in the maxillary sinus with erosion of surrounding structures is consistent with Juvenile Nasopharyngeal Angiofibroma.
    - 支持：a left nasal mass was noted / a heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus / Mild left-sided proptosis was present
- `mechanism_etiology` **Granulomatosis with Polyangiitis** — why: The presence of sinus pressure, facial swelling, and a heterogeneous mass in the maxillary sinus could be consistent with Granulomatosis with Polyangiitis.
    - 支持：sinus pressure and facial swelling / a heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus
- `mechanism_etiology` **Fibrous Dysplasia** — why: The presence of bony changes with remodeling and thinning could be consistent with Fibrous Dysplasia.
    - 支持：bony changes showed remodeling and thinning
- `definitive_modality` **Juvenile Nasopharyngeal Angiofibroma** — why: The presence of a heterogeneous mass in the maxillary sinus with erosion of surrounding structures is consistent with Juvenile Nasopharyngeal Angiofibroma
    - 支持：a heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus / mass eroded the orbital floor, medial and posterior maxillary walls, and anterior ethmoid air cells
- `definitive_modality` **Giant Cell Tumor** — why: The presence of multinucleated giant cells in the biopsy results is consistent with Giant Cell Tumor
    - 支持：Tissue analysis showed spindle cell process in a patternless arrangement with significant multinucleated giant

</details>

<details><summary>selector 淘汰理由</summary>

- **Fibrous Dysplasia** — Lack of specific evidence for fibrous dysplasia in the tissue analysis and the presence of a distinct mass
- **Granulomatosis with Polyangiitis** — Insufficient evidence for granulomatosis with polyangiitis, as the findings can be explained by other conditions on the shortlist

</details>

---

## MCR_seq200b/257 — collar button abscess

- 家族 MCR / 层 MCR_seq200b / 权重 25.0
- 指南能力：本地扩展 D3_direct_vignette_matched（上游三源 D3_direct_vignette_matched）
- 纳入金标的方法：multistance；其中未选中：multistance

### vignette 全文

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

### collapse3c（召回 miss，判分 False）

- champion：**Pyogenic Flexor Tenosynovitis**　runner-up：Diabetic Hand Infection　margin：
- selector 理由：The presence of a 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit and focal tenderness over the flexor sheath specifically supports Pyogenic Flexor Tenosynovitis.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Pyogenic Flexor Tenosynovitis | none | 0.0 | 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / focal tenderness over the flexor sheath / WBC count was 17.5 × 10^9/L | afebrile |
| Traumatic Hematoma | none | 0.0 | a concrete bench had fallen on the dorsal base of his right fourth digit without skin break / he noted a bruise at that site | 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit |
| Diabetic Hand Infection | none | 0.0 | A 66-year-old man with type 2 diabetes / HbA1c 11.2% / WBC count was 17.5 × 10^9/L | afebrile |
| Cellulitis | none | 0.0 | one-week history of worsening right hand pain, swelling, and erythema / diffuse soft-tissue swelling throughout the palm and into the distal interphalangeal joints of the third and f | 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit |
| Septic Arthritis | none | 0.0 | WBC count was 17.5 × 10^9/L / diffuse soft-tissue swelling throughout the palm and into the distal interphalangeal joints of the third and f | intact bony anatomy and no fracture or dislocation |
| Closed Traumatic Injury | none | 0.0 | — | — |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Pyogenic Flexor Tenosynovitis** — why: The presence of a painful, fluctuant mass and focal tenderness over the flexor sheath, along with a high WBC count, suggests pyogenic flexor tenosynovitis.
    - 支持：1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / focal tenderness over the flexor sheath / WBC count was 17.5 × 10^9/L
    - 反对：afebrile
- `c3` **Traumatic Hematoma** — why: The history of trauma to the digit and the subsequent development of a bruise suggests a traumatic hematoma.
    - 支持：a concrete bench had fallen on the dorsal base of his right fourth digit without skin break / he noted a bruise at that site
    - 反对：1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit
- `c3` **Diabetic Hand Infection** — why: The presence of poorly controlled diabetes and a high WBC count, along with hand pain and swelling, suggests a diabetic hand infection.
    - 支持：A 66-year-old man with type 2 diabetes / HbA1c 11.2% / WBC count was 17.5 × 10^9/L
    - 反对：afebrile
- `c3` **Cellulitis** — why: The presence of diffuse soft-tissue swelling and erythema, along with hand pain, suggests cellulitis.
    - 支持：one-week history of worsening right hand pain, swelling, and erythema / diffuse soft-tissue swelling throughout the palm and into the distal interphalangeal joints of the third and f
    - 反对：1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit
- `c3` **Septic Arthritis** — why: The presence of a high WBC count and diffuse soft-tissue swelling, along with joint involvement, suggests septic arthritis.
    - 支持：WBC count was 17.5 × 10^9/L / diffuse soft-tissue swelling throughout the palm and into the distal interphalangeal joints of the third and f
    - 反对：intact bony anatomy and no fracture or dislocation

</details>

### multistance（召回 set_strong，判分 False）

- champion：**Pyogenic Flexor Tenosynovitis**　runner-up：Infectious tenosynovitis　margin：
- selector 理由：The champion is chosen because it has the most specific findings for the condition, including a painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit, focal tenderness over the flexor sheath, and limited active digit motion, which are not fully explained by the other finalists.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Abscess | strong | 0.0 | 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / WBC count was 17.5 × 10^9/L / focal tenderness over the flexor sheath | he was afebrile |
| Pyogenic Flexor Tenosynovitis | none | 0.0 | 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / focal tenderness over the flexor sheath / limited active digit motion | he was afebrile |
| Diabetic Hand Infection | none | 0.0 | A 66-year-old man with type 2 diabetes / HbA1c 11.2% / WBC count was 17.5 × 10^9/L / 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit | he was afebrile |
| Traumatic Soft Tissue Injury | none | 0.0 | a concrete bench had fallen on the dorsal base of his right fourth digit without skin break / he noted a bruise at that site / diffuse soft-tissue swelling throughout the palm and into the distal interphalangeal joints of the third and f | 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit |
| Cellulitis | none | 0.0 | one-week history of worsening right hand pain, swelling, and erythema / most prominent in the distal palm / WBC count was 17.5 × 10^9/L | he was afebrile |
| Trauma | none | 0.0 | a concrete bench had fallen on the dorsal base of his right fourth digit without skin break / he noted a bruise at that site | — |
| Infectious tenosynovitis | none | 0.0 | 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / focal tenderness over the flexor sheath / limited active digit motion | — |
| Traumatic Tenosynovitis | none | 0.0 | a concrete bench had fallen on the dorsal base of his right fourth digit without skin break / 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit | — |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Pyogenic Flexor Tenosynovitis** — why: The presence of a painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit with focal tenderness over the flexor sheath earned this slot.
    - 支持：1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / focal tenderness over the flexor sheath / limited active digit motion
    - 反对：he was afebrile
- `stance:commit` **Diabetic Hand Infection** — why: The combination of type 2 diabetes with a high HbA1c level and an elevated WBC count earned this slot.
    - 支持：A 66-year-old man with type 2 diabetes / HbA1c 11.2% / WBC count was 17.5 × 10^9/L
    - 反对：he was afebrile
- `stance:commit` **Traumatic Soft Tissue Injury** — why: The history of trauma to the hand with subsequent bruising and soft tissue swelling earned this slot.
    - 支持：a concrete bench had fallen on the dorsal base of his right fourth digit without skin break / he noted a bruise at that site / diffuse soft-tissue swelling throughout the palm and into the distal interphalangeal joints of the third and f
    - 反对：1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit
- `stance:commit` **Cellulitis** — why: The presence of worsening pain, swelling, and erythema in the hand with an elevated WBC count earned this slot.
    - 支持：one-week history of worsening right hand pain, swelling, and erythema / most prominent in the distal palm / WBC count was 17.5 × 10^9/L
    - 反对：he was afebrile
- `stance:commit` **Abscess** — why: The presence of a painful, fluctuant mass with an elevated WBC count earned this slot.
    - 支持：1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / WBC count was 17.5 × 10^9/L
    - 反对：he was afebrile
- `stance:coverage` **Cellulitis** — why: Cannot be skipped due to the presence of worsening hand pain, swelling, and erythema, along with elevated WBC count.
    - 支持：one-week history of worsening right hand pain, swelling, and erythema / WBC count was 17.5 × 10^9/L
    - 反对：he was afebrile
- `stance:coverage` **Abscess** — why: Cannot be skipped due to the presence of a painful, fluctuant mass and focal tenderness over the flexor sheath.
    - 支持：1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / focal tenderness over the flexor sheath
- `stance:coverage` **Trauma** — why: Cannot be skipped due to the history of trauma to the affected area.
    - 支持：a concrete bench had fallen on the dorsal base of his right fourth digit without skin break / he noted a bruise at that site
- `stance:coverage` **Infectious tenosynovitis** — why: Cannot be skipped due to the presence of a painful, fluctuant mass, focal tenderness over the flexor sheath, and limited active digit motion.
    - 支持：1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / focal tenderness over the flexor sheath / limited active digit motion
- `stance:mechanism` **Pyogenic Flexor Tenosynovitis** — why: The process of bacterial infection and purulent collection within the flexor tendon sheath unifies the findings of a painful mass, tenderness, and limited motion.
    - 支持：1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / focal tenderness over the flexor sheath / limited active digit motion
- `stance:mechanism` **Diabetic Hand Infection** — why: The process of impaired glucose regulation and increased susceptibility to infection unifies the findings of diabetes, high HbA1c, and hand infection.
    - 支持：A 66-year-old man with type 2 diabetes / HbA1c 11.2% / 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit
- `stance:mechanism` **Traumatic Tenosynovitis** — why: The process of traumatic injury and subsequent inflammation of the tendon sheath unifies the findings of a painful mass and history of trauma.
    - 支持：a concrete bench had fallen on the dorsal base of his right fourth digit without skin break / 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit
- `stance:mechanism` **Cellulitis** — why: The process of bacterial infection and spread of inflammation through the soft tissues unifies the findings of pain, swelling, erythema, and elevated WBC count.
    - 支持：one-week history of worsening right hand pain, swelling, and erythema / most prominent in the distal palm / WBC count was 17.5 × 10^9/L

</details>

### impc（召回 miss，判分 False）

- champion：**Pyogenic Flexor Tenosynovitis**　runner-up：Infectious Tenosynovitis　margin：medium
- selector 理由：The presence of a painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit, along with focal tenderness over the flexor sheath and limited active digit motion, strongly supports Pyogenic Flexor Tenosynovitis as it specifically involves the flexor tendon sheath.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Infectious Tenosynovitis | none | 4.35 | D1E001 / D1E002 / D1E003 / D1E004 | — |
| Pyogenic Flexor Tenosynovitis | none | 3.35 | D1E002 / D1E003 / D3E007 | — |
| Septic Arthritis | none | 2.35 | D2E005 / D1E004 | — |
| Cellulitis | none | 1.0 | D2E006 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Infectious Tenosynovitis** — why: The patient's symptoms of worsening hand pain, swelling, erythema, and a painful fluctuant mass, along with elevated WBC count, are consistent with infectious tenosynovitis.
    - 支持：worsening right hand pain, swelling, and erythema / painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / focal tenderness over the flexor sheath and limited active digit motion / WBC count was 17.5 × 10^9/L
- `D2` **Pyogenic Flexor Tenosynovitis** — why: The patient's symptoms of a painful, fluctuant mass and focal tenderness over the flexor sheath are consistent with pyogenic flexor tenosynovitis.
    - 支持：painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / focal tenderness over the flexor sheath and limited active digit motion
- `D2` **Septic Arthritis** — why: The patient's elevated WBC count and diffuse soft-tissue swelling into the distal interphalangeal joints suggest septic arthritis.
    - 支持：diffuse soft-tissue swelling throughout the palm and into the distal interphalangeal joints of the third and f / WBC count was 17.5 × 10^9/L
- `D2` **Cellulitis** — why: The patient's symptoms of worsening pain, swelling, and erythema are consistent with cellulitis.
    - 支持：worsening right hand pain, swelling, and erythema, most prominent in the distal palm
- `D3` **Infectious Tenosynovitis** — why: The patient's symptoms and lab results suggest an infectious process, and the location and nature of the mass are consistent with tenosynovitis.
    - 支持：worsening right hand pain, swelling, and erythema / painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / WBC count was 17.5 × 10^9/L
- `D3` **Septic Arthritis** — why: The patient's joint involvement and elevated WBC count suggest a possible septic arthritis.
    - 支持：diffuse soft-tissue swelling throughout the palm and into the distal interphalangeal joints of the third and f / WBC count was 17.5 × 10^9/L
- `D3` **Pyogenic Flexor Tenosynovitis** — why: The patient's symptoms and examination findings are consistent with pyogenic flexor tenosynovitis, a serious infection of the flexor tendon sheath.
    - 支持：painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / focal tenderness over the flexor sheath

</details>

<details><summary>selector 淘汰理由</summary>

- **Septic Arthritis** — While there is diffuse soft-tissue swelling and an elevated WBC count, the primary findings are more localized to the flexor sheath rather than the joint itself, making Septic Arthritis less likely.
- **Cellulitis** — Cellulitis is a broader condition involving skin and subcutaneous tissue infection, but the specific involvement of the flexor sheath and the presence of a fluctuant mass point towards a more localized infection like Pyogenic Flexor Tenosynovitis.

</details>

### forest（召回 miss，判分 False）

- champion：**Pyogenic flexor tenosynovitis**　runner-up：Infectious tenosynovitis　margin：high
- selector 理由：The presence of a painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit, focal tenderness over the flexor sheath, and limited active digit motion strongly supports Pyogenic flexor tenosynovitis.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Pyogenic flexor tenosynovitis | none | 5.0 | AX_SE001 / AX_SE004 / AX_ME007 / AX_SE003 | — |
| Septic arthritis | none | 1.75 | AX_SE002 / AX_SE003 | AX_SE005 |
| Cellulitis | none | 3.5 | AX_SE006 / AX_ME008 / AX_SE003 | — |
| Infectious tenosynovitis | none | 3.0 | AX_SE006 / AX_SE001 / AX_SE003 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Pyogenic flexor tenosynovitis** — why: The patient's symptoms of a painful, fluctuant mass and focal tenderness over the flexor sheath are consistent with pyogenic flexor tenosynovitis.
    - 支持：painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / focal tenderness over the flexor sheath
- `syndrome_anatomy` **Septic arthritis** — why: The patient's symptoms of diffuse soft-tissue swelling and limited active digit motion are consistent with septic arthritis.
    - 支持：diffuse soft-tissue swelling throughout the palm and into the distal interphalangeal joints of the third and f
    - 反对：intact bony anatomy and no fracture or dislocation
- `syndrome_anatomy` **Cellulitis** — why: The patient's symptoms of pain, swelling, and erythema are consistent with cellulitis.
    - 支持：worsening right hand pain, swelling, and erythema
- `mechanism_etiology` **Infectious tenosynovitis** — why: The patient's symptoms and laboratory results suggest an infectious process.
    - 支持：worsening right hand pain, swelling, and erythema / painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / WBC count was 17.5 × 10^9/L
- `mechanism_etiology` **Septic arthritis** — why: The patient's joint involvement and elevated WBC count suggest a possible septic arthritis.
    - 支持：diffuse soft-tissue swelling throughout the palm and into the distal interphalangeal joints of the third and f / WBC count was 17.5 × 10^9/L
- `mechanism_etiology` **Pyogenic flexor tenosynovitis** — why: The patient's symptoms and examination results are consistent with pyogenic flexor tenosynovitis.
    - 支持：painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / focal tenderness over the flexor sheath
- `definitive_modality` **Pyogenic flexor tenosynovitis** — why: The patient's symptoms and examination findings are consistent with pyogenic flexor tenosynovitis, a bacterial infection of the flexor tendon sheath.
    - 支持：painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit / focal tenderness over the flexor sheath and limited active digit motion / WBC count was 17.5 × 10^9/L
- `definitive_modality` **Septic arthritis** — why: The patient's symptoms and laboratory findings are consistent with septic arthritis, a bacterial infection of the joint.
    - 支持：diffuse soft-tissue swelling throughout the palm and into the distal interphalangeal joints of the third and f / WBC count was 17.5 × 10^9/L
- `definitive_modality` **Cellulitis** — why: The patient's symptoms and laboratory findings are consistent with cellulitis, a bacterial infection of the skin and soft tissues.
    - 支持：swelling, and erythema, most prominent in the distal palm / WBC count was 17.5 × 10^9/L

</details>

<details><summary>selector 淘汰理由</summary>

- **Cellulitis** — While cellulitis is supported by swelling, erythema, and elevated WBC count, it does not specifically explain the fluctuant mass and focal tenderness over the flexor sheath.
- **Septic arthritis** — The absence of fracture or dislocation and intact bony anatomy contradicts septic arthritis, despite the presence of soft-tissue swelling and elevated WBC count.

</details>

---

## MCR_seq200b/326 — Brucellosis

- 家族 MCR / 层 MCR_seq200b / 权重 25.0
- 指南能力：本地扩展 D3_direct_vignette_matched（上游三源 D3_direct_vignette_matched）
- 纳入金标的方法：collapse3c, multistance, impc, forest；其中未选中：collapse3c, multistance, impc, forest

### vignette 全文

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

### collapse3c（召回 top2_strong，判分 False）

- champion：**Spinal epidural abscess**　runner-up：Brucellosis　margin：
- selector 理由：The finding of a posterior epidural abscess compressing the spinal cord at T9–T10 on contrast-enhanced thoracic magnetic resonance imaging specifically supports Spinal epidural abscess.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Brucellosis | strong | 0.0 | touching an unpasteurized sheep stomach with an injured hand about 1 month earlier / blood cultures grew a Gram-negative bacillus | — |
| Spinal epidural abscess | none | 0.0 | Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and | — |
| Vertebral osteomyelitis | none | 0.0 | a C-reactive protein level of 3.19 mg/dL / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina | — |
| Discitis | none | 0.0 | progressive back pain / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina | — |
| Pott's disease | none | 0.0 | progressive back pain / a serological test for tuberculosis was negative | a serological test for tuberculosis was negative |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Spinal epidural abscess** — why: The presence of a posterior epidural abscess compressing the spinal cord is a rare and unusual finding that earned this slot.
    - 支持：Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and
- `c3` **Brucellosis** — why: The patient's history of touching an unpasteurized sheep stomach and the growth of a Gram-negative bacillus in blood cultures are unusual findings that suggest Brucellosis.
    - 支持：touching an unpasteurized sheep stomach with an injured hand about 1 month earlier / blood cultures grew a Gram-negative bacillus
- `c3` **Vertebral osteomyelitis** — why: The elevated C-reactive protein level and the presence of an inflammatory lesion of the T9 lamina are unusual findings that suggest Vertebral osteomyelitis.
    - 支持：a C-reactive protein level of 3.19 mg/dL / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina
- `c3` **Discitis** — why: The patient's progressive back pain and the presence of an inflammatory lesion of the T9 lamina are unusual findings that suggest Discitis.
    - 支持：progressive back pain / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina
- `c3` **Pott's disease** — why: The patient's progressive back pain and the negative serological test for tuberculosis are unusual findings that suggest Pott's disease, although the negative test result argues against it.
    - 支持：progressive back pain / a serological test for tuberculosis was negative
    - 反对：a serological test for tuberculosis was negative

</details>

### multistance（召回 set_strong，判分 False）

- champion：**Spondylodiscitis**　runner-up：Spinal epidural abscess　margin：
- selector 理由：The champion accounts for the osteolytic destruction of the neural arch and the inflammatory lesion, and is supported by multiple findings including progressive back pain, elevated erythrocyte sedimentation rate, and positron emission tomography–computed tomography results.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Brucellosis | strong | 0.0 | touching an unpasteurized sheep stomach with an injured hand about 1 month earlier / an erythrocyte sedimentation rate of 35 mm/hour / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and | a serological test for tuberculosis was negative |
| Spinal epidural abscess | none | 0.0 | progressive back pain / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and / a white-cell count of 7170/mm3 | — |
| Osteomyelitis | none | 0.0 | an erythrocyte sedimentation rate of 35 mm/hour / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and / progressive back pain / Positron emission tomography–computed tomography showed osteolytic destruction of the neural arch of T9 | — |
| Discitis | none | 0.0 | progressive back pain / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina | — |
| Gram-negative bacillary infection | none | 0.0 | a white-cell count of 7170/mm3 / 80% neutrophils | — |
| Spondylodiscitis | none | 0.0 | progressive back pain / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and / Positron emission tomography–computed tomography showed osteolytic destruction of the neural arch of T9 / an erythrocyte sedimentation rate of 35 mm/hour | — |
| Spinal tuberculosis | none | 0.0 | — | — |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Brucellosis** — why: The patient's history of touching an unpasteurized sheep stomach with an injured hand is a rare and unusual finding that suggests Brucellosis.
    - 支持：touching an unpasteurized sheep stomach with an injured hand about 1 month earlier / an erythrocyte sedimentation rate of 35 mm/hour / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and
    - 反对：a serological test for tuberculosis was negative
- `stance:commit` **Spinal epidural abscess** — why: The patient's progressive back pain and the imaging findings of an epidural abscess are highly suggestive of Spinal epidural abscess.
    - 支持：progressive back pain / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and
- `stance:commit` **Osteomyelitis** — why: The patient's elevated erythrocyte sedimentation rate and the imaging findings of an inflammatory lesion are consistent with Osteomyelitis.
    - 支持：an erythrocyte sedimentation rate of 35 mm/hour / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and
- `stance:commit` **Discitis** — why: The patient's progressive back pain and the imaging findings of an inflammatory lesion are consistent with Discitis.
    - 支持：progressive back pain / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and
- `stance:commit` **Gram-negative bacillary infection** — why: The patient's elevated white-cell count and neutrophil percentage are consistent with a Gram-negative bacillary infection.
    - 支持：a white-cell count of 7170/mm3 / 80% neutrophils
- `stance:coverage` **Spinal epidural abscess** — why: The patient's symptoms of progressive back pain and the imaging findings of an inflammatory lesion and epidural abscess are consistent with this diagnosis.
    - 支持：progressive back pain / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and
- `stance:coverage` **Osteomyelitis** — why: The patient's symptoms of progressive back pain and elevated inflammatory markers are consistent with this diagnosis.
    - 支持：progressive back pain / an erythrocyte sedimentation rate of 35 mm/hour
- `stance:coverage` **Discitis** — why: The patient's symptoms of progressive back pain and the imaging findings of an inflammatory lesion are consistent with this diagnosis.
    - 支持：progressive back pain / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina
- `stance:coverage` **Spondylodiscitis** — why: The patient's symptoms of progressive back pain and the imaging findings of an inflammatory lesion and epidural abscess are consistent with this diagnosis.
    - 支持：progressive back pain / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and
- `stance:mechanism` **Spinal Epidural Abscess** — why: The process of bacterial infection and abscess formation unifies the findings of back pain, fever, and elevated white-cell count with the imaging findings of an inflammatory lesion and epidural abscess.
    - 支持：Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and / a white-cell count of 7170/mm3
- `stance:mechanism` **Osteomyelitis** — why: The process of bacterial infection and bone destruction unifies the findings of back pain and osteolytic destruction with the history of exposure to an unpasteurized sheep stomach.
    - 支持：Positron emission tomography–computed tomography showed osteolytic destruction of the neural arch of T9 / touching an unpasteurized sheep stomach with an injured hand about 1 month earlier
- `stance:mechanism` **Discitis** — why: The process of bacterial infection and disc space inflammation unifies the findings of back pain and inflammatory lesion with the imaging findings.
    - 支持：Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina / progressive back pain
- `stance:mechanism` **Spondylodiscitis** — why: The process of bacterial infection and vertebral body inflammation unifies the findings of back pain and elevated erythrocyte sedimentation rate with the imaging findings of osteolytic destruction.
    - 支持：Positron emission tomography–computed tomography showed osteolytic destruction of the neural arch of T9 / an erythrocyte sedimentation rate of 35 mm/hour

</details>

### impc（召回 set_strong，判分 False）

- champion：**Spinal epidural abscess**　runner-up：Osteomyelitis　margin：high
- selector 理由：The presence of an inflammatory lesion of the T9 lamina and a posterior epidural abscess compressing the spinal cord at T9–T10, along with difficulty with urination, strongly supports the diagnosis of Spinal epidural abscess.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Brucellosis | strong | 3.7 | D1E005 / D1E006 / D2E007 | — |
| Spinal epidural abscess | none | 3.7 | D1E001 / D1E002 / D2E008 | — |
| Osteomyelitis | none | 3.7 | D1E003 / D1E004 / D2E009 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Spinal epidural abscess** — why: The patient's symptoms of back pain, numbness and weakness in both legs, and difficulty with urination, along with the imaging findings of an epidural abscess compressing the spinal cord, are consistent with a spinal epidural abscess.
    - 支持：difficulty with urination / an inflammatory lesion of the T9 lamina and a posterior epidural abscess compressing the spinal cord at T9–T10
- `D1` **Osteomyelitis** — why: The patient's history of progressive back pain and the imaging finding of osteolytic destruction of the neural arch are consistent with osteomyelitis.
    - 支持：progressive back pain / osteolytic destruction of the neural arch of T9
- `D1` **Brucellosis** — why: The patient's exposure to an unpasteurized sheep stomach and symptoms of high fever and night sweats are consistent with brucellosis.
    - 支持：touching an unpasteurized sheep stomach with an injured hand about 1 month earlier / high fever, night sweats
- `D2` **Brucellosis** — why: The patient's history of touching an unpasteurized sheep stomach is a risk factor for Brucellosis.
    - 支持：He reported touching an unpasteurized sheep stomach with an injured hand about 1 month earlier
- `D2` **Spinal epidural abscess** — why: The MRI findings are consistent with a spinal epidural abscess.
    - 支持：Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and
- `D2` **Osteomyelitis** — why: The PET-CT findings suggest osteomyelitis of the spine.
    - 支持：Positron emission tomography–computed tomography showed osteolytic destruction of the neural arch of T9
- `D3` **Brucellosis** — why: The patient's history of touching an unpasteurized sheep stomach is a risk factor for Brucellosis.
    - 支持：He reported touching an unpasteurized sheep stomach with an injured hand about 1 month earlier
- `D3` **Spinal epidural abscess** — why: The imaging findings are consistent with a spinal epidural abscess.
    - 支持：Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and
- `D3` **Vertebral osteomyelitis** — why: The osteolytic destruction of the neural arch is consistent with vertebral osteomyelitis.
    - 支持：Positron emission tomography–computed tomography showed osteolytic destruction of the neural arch of T9

</details>

<details><summary>selector 淘汰理由</summary>

- **Brucellosis** — While the patient's history of touching an unpasteurized sheep stomach and symptoms of high fever and night sweats are consistent with Brucellosis, the presence of a spinal epidural abscess and osteolytic destruction of the neural arch are more specific findin

</details>

### forest（召回 set_strong，判分 False）

- champion：**Spinal epidural abscess**　runner-up：Discitis　margin：high
- selector 理由：The patient's difficulty with urination and the MRI findings of a posterior epidural abscess compressing the spinal cord at T9–T10 provide strong evidence for Spinal epidural abscess.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Brucellosis | strong | 1.25 | AX_ME006 | — |
| Spinal epidural abscess | none | 3.0 | AX_SE001 / AX_SE002 | — |
| Osteomyelitis | none | 3.0 | AX_SE003 / AX_SE004 | — |
| Discitis | none | 3.5 | AX_SE003 / AX_SE005 / AX_ME007 | — |
| Gram-negative bacillus infection | none | 1.0 | AX_ME008 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Spinal epidural abscess** — why: The patient's symptoms of weakness and numbness in both legs and difficulty with urination, along with the imaging findings, support this diagnosis
    - 支持：difficulty with urination / Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and
- `syndrome_anatomy` **Osteomyelitis** — why: The patient's history of back pain and the imaging findings of osteolytic destruction support this diagnosis
    - 支持：progressive back pain / Positron emission tomography–computed tomography showed osteolytic destruction of the neural arch of T9
- `syndrome_anatomy` **Discitis** — why: The patient's symptoms of back pain and tenderness, along with the imaging findings, support this diagnosis
    - 支持：progressive back pain / tenderness on percussion and palpation of the T9 and T10 spinous processes
- `mechanism_etiology` **Brucellosis** — why: The patient's history of touching an unpasteurized sheep stomach is a risk factor for Brucellosis
    - 支持：He reported touching an unpasteurized sheep stomach with an injured hand about 1 month earlier
- `mechanism_etiology` **Epidural abscess** — why: The patient has a confirmed diagnosis of an epidural abscess
    - 支持：Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and
- `mechanism_etiology` **Osteomyelitis** — why: The patient has osteolytic destruction of the neural arch, which is consistent with osteomyelitis
    - 支持：Positron emission tomography–computed tomography showed osteolytic destruction of the neural arch of T9
- `mechanism_etiology` **Discitis** — why: The patient's symptoms and physical examination findings are consistent with discitis
    - 支持：He had worsening back pain and malaise / tenderness on percussion and palpation of the T9 and T10 spinous processes
- `definitive_modality` **Spinal epidural abscess** — why: The patient's symptoms and imaging findings are consistent with a spinal epidural abscess
    - 支持：Contrast-enhanced thoracic magnetic resonance imaging demonstrated an inflammatory lesion of the T9 lamina and
- `definitive_modality` **Vertebral osteomyelitis** — why: The patient's imaging findings are consistent with vertebral osteomyelitis
    - 支持：Positron emission tomography–computed tomography showed osteolytic destruction of the neural arch of T9
- `definitive_modality` **Gram-negative bacillus infection** — why: The patient's blood culture results are consistent with a Gram-negative bacillus infection
    - 支持：On hospital day 6, blood cultures grew a Gram-negative bacillus

</details>

<details><summary>selector 淘汰理由</summary>

- **Brucellosis** — Lack of specific symptoms and laboratory findings
- **Gram-negative bacillus infection** — While blood cultures grew a Gram-negative bacillus, this finding alone does not explain the patient's symptoms and imaging findings
- **Osteomyelitis** — While osteolytic destruction of the neural arch of T9 is consistent with Osteomyelitis, the patient's symptoms and other imaging findings are more consistent with Spinal epidural abscess

</details>

---

## MCR_seq200b/409 — Chronic necrotizing pancreatitis

- 家族 MCR / 层 MCR_seq200b / 权重 25.0
- 指南能力：本地扩展 D3_direct_vignette_matched（上游三源 D2_direct_but_partial_or_general）
- 纳入金标的方法：collapse3c, multistance, forest；其中未选中：collapse3c, multistance, forest

### vignette 全文

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

### collapse3c（召回 set_strong，判分 False）

- champion：**Pleural effusion due to pancreaticopleural fistula**　runner-up：　margin：
- selector 理由：The high amylase level in the pleural fluid, along with the patient's history of pancreatitis and the presence of a large left pleural effusion, decided it.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Pleural effusion due to pancreaticopleural fistula | weak | 0.0 | bilateral pitting edema to the knees / decreased movement on the left; trachea deviated rightward; decreased fremitus and stony dullness over the ent / Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons / pleural fluid analysis: protein 3.5 g/dL; LDH 1413 U/L; glucose 98 mg/dL; ADA 31.4 U/L; total cell count 100/m | — |
| Acute pancreatitis | weak | 0.0 | central, nonradiating chest pain with coughing / serum amylase 486 U/L, and lipase 416 U/L | denied fever |
| Pulmonary embolism | none | 0.0 | dyspneic at rest (grade 4) / pulse was 116/min / respiratory rate 30/min | Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons |
| Congestive heart failure | none | 0.0 | bilateral pitting edema to the knees / pulse was 116/min / respiratory rate 30/min | decreased movement on the left; trachea deviated rightward; decreased fremitus and stony dullness over the ent |
| Empyema | none | 0.0 | decreased movement on the left; trachea deviated rightward; decreased fremitus and stony dullness over the ent / Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons | pleural fluid analysis: protein 3.5 g/dL; LDH 1413 U/L; glucose 98 mg/dL; ADA 31.4 U/L; total cell count 100/m |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Pleural effusion due to pancreaticopleural fistula** — why: The presence of a high amylase level in the pleural fluid suggests a pancreaticopleural fistula.
    - 支持：bilateral pitting edema to the knees / decreased movement on the left; trachea deviated rightward; decreased fremitus and stony dullness over the ent / Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons / pleural fluid analysis: protein 3.5 g/dL; LDH 1413 U/L; glucose 98 mg/dL; ADA 31.4 U/L; total cell count 100/m
- `c3` **Acute pancreatitis** — why: The patient's history of acute severe pancreatitis and the presence of abdominal pain suggest acute pancreatitis.
    - 支持：central, nonradiating chest pain with coughing / serum amylase 486 U/L, and lipase 416 U/L
    - 反对：denied fever
- `c3` **Pulmonary embolism** — why: The patient's symptoms of dyspnea and tachycardia could suggest a pulmonary embolism.
    - 支持：dyspneic at rest (grade 4) / pulse was 116/min / respiratory rate 30/min
    - 反对：Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons
- `c3` **Congestive heart failure** — why: The patient's symptoms of edema and tachycardia could suggest congestive heart failure.
    - 支持：bilateral pitting edema to the knees / pulse was 116/min / respiratory rate 30/min
    - 反对：decreased movement on the left; trachea deviated rightward; decreased fremitus and stony dullness over the ent
- `c3` **Empyema** — why: The presence of a large pleural effusion could suggest an empyema.
    - 支持：decreased movement on the left; trachea deviated rightward; decreased fremitus and stony dullness over the ent / Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons
    - 反对：pleural fluid analysis: protein 3.5 g/dL; LDH 1413 U/L; glucose 98 mg/dL; ADA 31.4 U/L; total cell count 100/m

</details>

### multistance（召回 set_strong，判分 False）

- champion：**Pleural effusion due to pancreaticopleural fistula**　runner-up：Pleural effusion　margin：
- selector 理由：The champion is chosen because it has the most specific and decisive evidence, including high amylase levels in the pleural fluid, which suggests a pancreaticopleural fistula.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Chronic pancreatitis | near | 0.0 | pulse was 116/min / respiratory rate 30/min / He had a 5-year history of local alcohol consumption but had abstained for 6 months | — |
| Pleural effusion due to pancreaticopleural fistula | weak | 0.0 | bilateral pitting edema to the knees / decreased movement on the left; trachea deviated rightward; decreased fremitus and stony dullness over the ent / Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons / pleural fluid analysis: protein 3.5 g/dL; LDH 1413 U/L; glucose 98 mg/dL; ADA 31.4 U/L; total cell count 100/m | — |
| Acute pancreatitis | weak | 0.0 | central, nonradiating chest pain with coughing / serum amylase 486 U/L, and lipase 416 U/L | denied fever |
| Pulmonary embolism | none | 0.0 | dyspneic at rest (grade 4) / pulse was 116/min / respiratory rate 30/min / 5 days of progressive dyspnea | Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons |
| Congestive heart failure | none | 0.0 | bilateral pitting edema to the knees / pulse was 116/min / respiratory rate 30/min | — |
| Empyema | none | 0.0 | decreased movement on the left; trachea deviated rightward; decreased fremitus and stony dullness over the ent / Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons | culture negative |
| Pleural effusion | none | 0.0 | decreased movement on the left; trachea deviated rightward; decreased fremitus and stony dullness over the ent / Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons | — |
| Hypovolemic shock | none | 0.0 | bilateral pitting edema to the knees | — |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Pleural effusion due to pancreaticopleural fistula** — why: The presence of a high amylase level in the pleural fluid suggests a pancreaticopleural fistula.
    - 支持：bilateral pitting edema to the knees / decreased movement on the left; trachea deviated rightward; decreased fremitus and stony dullness over the ent / Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons / pleural fluid analysis: protein 3.5 g/dL; LDH 1413 U/L; glucose 98 mg/dL; ADA 31.4 U/L; total cell count 100/m
- `stance:commit` **Acute pancreatitis** — why: The patient's history of acute severe pancreatitis and the presence of abdominal pain suggest acute pancreatitis.
    - 支持：central, nonradiating chest pain with coughing / serum amylase 486 U/L, and lipase 416 U/L
    - 反对：denied fever
- `stance:commit` **Pulmonary embolism** — why: The patient's symptoms of dyspnea and tachycardia could suggest a pulmonary embolism.
    - 支持：dyspneic at rest (grade 4) / pulse was 116/min / respiratory rate 30/min
    - 反对：Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons
- `stance:commit` **Congestive heart failure** — why: The patient's symptoms of edema and tachycardia could suggest congestive heart failure.
    - 支持：bilateral pitting edema to the knees / pulse was 116/min / respiratory rate 30/min
    - 反对：Cardiovascular examination was unremarkable
- `stance:commit` **Empyema** — why: The patient's symptoms of decreased movement and dullness to percussion could suggest an empyema.
    - 支持：decreased movement on the left; trachea deviated rightward; decreased fremitus and stony dullness over the ent / Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons
    - 反对：culture negative
- `stance:coverage` **Pleural effusion** — why: The patient's symptoms and imaging results are consistent with a large pleural effusion, which is a significant finding that cannot be skipped.
    - 支持：decreased movement on the left; trachea deviated rightward; decreased fremitus and stony dullness over the ent / Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons
- `stance:coverage` **Pancreatitis** — why: The high amylase level in the pleural fluid suggests a connection to the pancreas, and the patient's history of pancreatitis makes this a relevant consideration.
    - 支持：pleural fluid analysis: ... amylase 11,871 U/L
- `stance:coverage` **Heart failure** — why: The patient's bilateral pitting edema could be a sign of heart failure, which is a common cause of pleural effusions and should be considered in the differential diagnosis.
    - 支持：bilateral pitting edema to the knees
- `stance:coverage` **Pulmonary embolism** — why: The patient's symptoms of progressive dyspnea and chest pain could be consistent with a pulmonary embolism, which is a life-threatening condition that must be excluded.
    - 支持：5 days of progressive dyspnea / central, nonradiating chest pain with coughing
- `stance:mechanism` **Pleural effusion** — why: The process of fluid accumulation in the pleural space unifies the findings of decreased breath sounds, stony dullness, and tracheal deviation.
    - 支持：decreased movement on the left; trachea deviated rightward; decreased fremitus and stony dullness over the ent / Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons
- `stance:mechanism` **Pancreaticopleural fistula** — why: The process of pancreatic enzyme leakage into the pleural space unifies the findings of high amylase levels in the pleural fluid.
    - 支持：pleural fluid analysis: protein 3.5 g/dL; LDH 1413 U/L; glucose 98 mg/dL; ADA 31.4 U/L; total cell count 100/m
- `stance:mechanism` **Chronic pancreatitis** — why: The process of chronic pancreatic inflammation unifies the findings of abdominal pain, respiratory distress, and history of alcohol consumption.
    - 支持：pulse was 116/min / respiratory rate 30/min / He had a 5-year history of local alcohol consumption but had abstained for 6 months
- `stance:mechanism` **Hypovolemic shock** — why: The process of fluid loss and volume depletion unifies the findings of pitting edema and respiratory distress.
    - 支持：bilateral pitting edema to the knees

</details>

### impc（召回 miss，判分 False）

- champion：**Pancreaticopleural fistula**　runner-up：Pleural effusion　margin：high
- selector 理由：High amylase level in pleural fluid and history of acute severe pancreatitis support pancreaticopleural fistula

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Pleural effusion | none | 2.7 | D1E001 / D1E002 | — |
| Pancreatic pseudocyst | weak | 2.7 | D1E003 / D1E004 | — |
| Pancreaticopleural fistula | weak | 2.0 | D1E005 / D1E006 | — |
| Pulmonary Embolism | none | 2.0 | D2E007 / D2E008 | — |
| Pulmonary tuberculosis | none | -1.75 | — | D3E009 |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Pleural effusion** — why: The patient's symptoms and imaging studies are consistent with a large pleural effusion.
    - 支持：complete opacification of the left hemithorax with tracheal shift to the right, consistent with massive left p / a large left pleural effusion with passive basal lung collapse
- `D1` **Pancreatic pseudocyst** — why: The patient has a history of pancreatitis and imaging studies show cystic areas in the pancreas.
    - 支持：multiple non-enhancing cystic areas in the pancreas (largest 23×16 mm in the tail) / a small intrapancreatic collection at the tail
- `D1` **Pancreaticopleural fistula** — why: The high amylase level in the pleural fluid and the patient's history of pancreatitis suggest a possible connection between the pancreas and the pleural space.
    - 支持：amylase 11,871 U/L in the pleural fluid / a history of acute severe pancreatitis
- `D2` **Pleural Effusion** — why: The patient has a large left pleural effusion with passive basal lung collapse and the chest radiograph revealed complete opacification of the left hemithorax.
    - 支持：complete opacification of the left hemithorax with tracheal shift to the right, consistent with massive left p / a large left pleural effusion with passive basal lung collapse
- `D2` **Pancreatic Pseudocyst** — why: The patient has a history of acute severe pancreatitis and the imaging studies show multiple non-enhancing cystic areas in the pancreas.
    - 支持：a small intrapancreatic collection at the tail / multiple non-enhancing cystic areas in the pancreas (largest 23×16 mm in the tail)
- `D2` **Pulmonary Embolism** — why: The patient has progressive dyspnea and central chest pain, which could be indicative of a pulmonary embolism.
    - 支持：progressive dyspnea / central, nonradiating chest pain with coughing
- `D3` **Pleural effusion** — why: The patient has a large left pleural effusion with passive basal lung collapse and the chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right.
    - 支持：complete opacification of the left hemithorax with tracheal shift to the right, consistent with massive left p / a large left pleural effusion with passive basal lung collapse
- `D3` **Pancreatic pseudocyst** — why: The patient has a history of acute severe pancreatitis and the imaging studies show multiple non-enhancing cystic areas in the pancreas and a small intrapancreatic collection at the tail.
    - 支持：a small intrapancreatic collection at the tail / multiple non-enhancing cystic areas in the pancreas (largest 23×16 mm in the tail)
- `D3` **Pulmonary tuberculosis** — why: The patient's symptoms and pleural effusion could be suggestive of pulmonary tuberculosis, but the MTB/RIF PCR is negative.
    - 反对：MTB/RIF PCR negative

</details>

<details><summary>selector 淘汰理由</summary>

- **Pulmonary Embolism** — Lack of specific evidence for pulmonary embolism and presence of other explanatory findings
- **Pulmonary tuberculosis** — MTB/RIF PCR negative
- **Pancreatic pseudocyst** — While present, does not directly explain the pleural effusion

</details>

### forest（召回 set_near，判分 False）

- champion：**Pulmonary effusion due to pancreaticopleural fistula**　runner-up：Pleural effusion　margin：high
- selector 理由：High amylase level in pleural fluid and history of pancreatitis support pancreaticopleural fistula

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Chronic pancreatitis | near | 3.0 | AX_ME007 / AX_ME008 / AX_ME012 | — |
| Pleural effusion | weak | 7.15 | AX_SE001 / AX_SE004 / AX_ME009 / AX_ME011 | — |
| Pancreatic pseudocyst | weak | 4.0 | AX_SE002 / AX_SE005 / AX_ME013 | — |
| Pulmonary effusion due to pancreaticopleural fistula | weak | 5.75 | AX_SE006 / AX_SE003 / AX_ME007 / AX_ME008 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Pleural effusion** — why: The patient has a large left pleural effusion with passive basal lung collapse and tracheal shift to the right.
    - 支持：complete opacification of the left hemithorax with tracheal shift to the right, consistent with massive left p / large left pleural effusion with passive basal lung collapse
- `syndrome_anatomy` **Pancreatic pseudocyst** — why: The patient has multiple non-enhancing cystic areas in the pancreas and a small intrapancreatic collection at the tail, consistent with pancreatic pseudocysts.
    - 支持：multiple non-enhancing cystic areas in the pancreas (largest 23×16 mm in the tail) / a small intrapancreatic collection at the tail
- `syndrome_anatomy` **Pulmonary effusion due to pancreaticopleural fistula** — why: The patient has a high amylase level in the pleural fluid, suggesting a pancreaticopleural fistula.
    - 支持：dark brown, turbid fluid / amylase 11,871 U/L
- `mechanism_etiology` **Pancreaticopleural fistula** — why: The patient's history of pancreatitis and the high amylase level in the pleural fluid suggest a pancreaticopleural fistula.
    - 支持：He had a 5-year history of local alcohol consumption but had abstained for 6 months. / He had three previous hospital admissions, most recently 4 months earlier for acute severe pancreatitis. / serum amylase 486 U/L, and lipase 416 U/L. / amylase 11,871 U/L
- `mechanism_etiology` **Pleural effusion** — why: The patient has a large pleural effusion, which is causing his dyspnea and chest pain.
    - 支持：Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons / Ultrasonography of the chest, abdomen, and pelvis confirmed a large left pleural effusion with passive basal l
- `mechanism_etiology` **Chronic pancreatitis** — why: The patient's history of pancreatitis and the CT findings suggest chronic pancreatitis.
    - 支持：He had a 5-year history of local alcohol consumption but had abstained for 6 months. / He had three previous hospital admissions, most recently 4 months earlier for acute severe pancreatitis. / Contrast-enhanced CT of the abdomen demonstrated multiple non-enhancing cystic areas in the pancreas
- `mechanism_etiology` **Pseudocyst** — why: The patient has a pseudocyst in the pancreas, which may be related to his pancreatitis.
    - 支持：Contrast-enhanced CT of the abdomen demonstrated multiple non-enhancing cystic areas in the pancreas (largest 
- `definitive_modality` **Pleural effusion** — why: The patient has a large left pleural effusion confirmed by chest radiograph and ultrasonography.
    - 支持：Chest radiograph revealed complete opacification of the left hemithorax with tracheal shift to the right, cons / Ultrasonography of the chest, abdomen, and pelvis confirmed a large left pleural effusion with passive basal l
- `definitive_modality` **Pancreatic pseudocyst** — why: The patient has multiple non-enhancing cystic areas in the pancreas, consistent with pancreatic pseudocysts.
    - 支持：Contrast-enhanced CT of the abdomen demonstrated multiple non-enhancing cystic areas in the pancreas (largest 
- `definitive_modality` **Pleural effusion due to pancreatic disease** — why: The patient has a pleural effusion with high amylase levels, suggesting a connection to pancreatic disease.
    - 支持：Diagnostic thoracentesis yielded 900 mL of dark brown, turbid fluid. / Pleural fluid analysis: protein 3.5 g/dL; LDH 1413 U/L; glucose 98 mg/dL; ADA 31.4 U/L; total cell count 100/m

</details>

<details><summary>selector 淘汰理由</summary>

- **Pancreatic pseudocyst** — While present, it doesn't directly explain the pleural effusion
- **Chronic pancreatitis** — It's a contributing factor but doesn't directly explain the acute presentation

</details>

---

## MCR_seq200b/475 — Parsonage Turner Syndrome

- 家族 MCR / 层 MCR_seq200b / 权重 25.0
- 指南能力：本地扩展 D3_direct_vignette_matched（上游三源 D3_direct_vignette_matched）
- 纳入金标的方法：collapse3c, multistance；其中未选中：collapse3c, multistance

### vignette 全文

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

### collapse3c（召回 set_strong，判分 False）

- champion：**Anterior Interosseous Nerve Syndrome**　runner-up：Neuralgic Amyotrophy　margin：
- selector 理由：The specific inability to perform the 'Ok' sign and to form a fist, along with the electromyographic findings of neurogenic atrophy of muscles innervated by the anterior interosseous nerve, decided it.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Neuralgic Amyotrophy | strong | 0.0 | electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice | no sensory deficits |
| Anterior Interosseous Nerve Syndrome | none | 0.0 | episodes of isolated, sudden weakness of the left upper limb / weakness of the distal phalanx of the thumb and middle phalanx of the index finger / inability to perform the “Ok” sign and to form a fist | MRI of the left upper extremity was performed and showed no abnormalities |
| Mononeuritis Multiplex | none | 0.0 | electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice | tendon reflexes were normal throughout |
| Brachial Plexitis | none | 0.0 | electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice | no muscular wasting, pathological reflexes, or focal neurological signs |
| Radial Neuropathy | none | 0.0 | weakness of the distal phalanx of the thumb and middle phalanx of the index finger / inability to perform the “Ok” sign and to form a fist | electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Anterior Interosseous Nerve Syndrome** — why: The unusual finding of isolated weakness of the left upper limb with specific involvement of the distal phalanx of the thumb and middle phalanx of the index finger earned this slot.
    - 支持：episodes of isolated, sudden weakness of the left upper limb / weakness of the distal phalanx of the thumb and middle phalanx of the index finger / inability to perform the “Ok” sign and to form a fist
    - 反对：MRI of the left upper extremity was performed and showed no abnormalities
- `c3` **Neuralgic Amyotrophy** — why: The finding of neurogenic atrophy of multiple muscles in the left upper limb earned this slot.
    - 支持：electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice
    - 反对：no sensory deficits
- `c3` **Mononeuritis Multiplex** — why: The involvement of multiple nerves in the left upper limb earned this slot.
    - 支持：electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice
    - 反对：tendon reflexes were normal throughout
- `c3` **Brachial Plexitis** — why: The finding of neurogenic atrophy of multiple muscles in the left upper limb with no other signs of brachial plexus injury earned this slot.
    - 支持：electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice
    - 反对：no muscular wasting, pathological reflexes, or focal neurological signs
- `c3` **Radial Neuropathy** — why: The specific involvement of the distal phalanx of the thumb and middle phalanx of the index finger earned this slot.
    - 支持：weakness of the distal phalanx of the thumb and middle phalanx of the index finger / inability to perform the “Ok” sign and to form a fist
    - 反对：electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant

</details>

### multistance（召回 set_strong，判分 False）

- champion：**Anterior Interosseous Nerve Syndrome**　runner-up：Mononeuropathy　margin：
- selector 理由：The champion is chosen because it has the most specific and detailed for evidence, including electromyographic evaluation showing neurogenic atrophy of muscles innervated by the anterior interosseous nerve, and no significant against evidence.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Neuralgic Amyotrophy | strong | 0.0 | electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice | no muscular wasting, pathological reflexes, or focal neurological signs |
| Anterior Interosseous Nerve Syndrome | none | 0.0 | electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice / episodes of isolated, sudden weakness of the left upper limb / weakness of the distal phalanx of the thumb and middle phalanx of the index finger | — |
| Mononeuritis Multiplex | none | 0.0 | electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice / weakness of the distal phalanx of the thumb and middle phalanx of the index finger | no sensory deficits |
| Radial Neuropathy | none | 0.0 | weakness of the distal phalanx of the thumb and middle phalanx of the index finger / inability to perform the “Ok” sign and to form a fist / electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice | electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant |
| Ulnar Neuropathy | none | 0.0 | weakness of the distal phalanx of the thumb and middle phalanx of the index finger / inability to perform the “Ok” sign and to form a fist | electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant |
| Mononeuropathy | none | 0.0 | inability to perform the “Ok” sign and to form a fist / electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant | — |
| Neuropathy | none | 0.0 | episodes of isolated, sudden weakness of the left upper limb / electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant | — |
| Musculoskeletal disorder | none | 0.0 | episodes of isolated, sudden weakness of the left upper limb | no muscular wasting, pathological reflexes, or focal neurological signs |
| Brachial Plexitis | none | 0.0 | electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice | MRI of the left upper extremity was performed and showed no abnormalities |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Anterior Interosseous Nerve Syndrome** — why: The unusual finding of neurogenic atrophy of muscles innervated by the anterior interosseous nerve earned this slot.
    - 支持：electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice
- `stance:commit` **Mononeuritis Multiplex** — why: The finding of neurogenic atrophy in multiple nerves earned this slot.
    - 支持：electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice
    - 反对：no sensory deficits
- `stance:commit` **Neuralgic Amyotrophy** — why: The finding of neurogenic atrophy in multiple muscles earned this slot.
    - 支持：electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice
    - 反对：no muscular wasting, pathological reflexes, or focal neurological signs
- `stance:commit` **Radial Neuropathy** — why: The finding of weakness in the distribution of the radial nerve earned this slot.
    - 支持：weakness of the distal phalanx of the thumb and middle phalanx of the index finger / inability to perform the “Ok” sign and to form a fist
    - 反对：electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant
- `stance:commit` **Ulnar Neuropathy** — why: The finding of weakness in the distribution of the ulnar nerve earned this slot.
    - 支持：weakness of the distal phalanx of the thumb and middle phalanx of the index finger / inability to perform the “Ok” sign and to form a fist
    - 反对：electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant
- `stance:coverage` **Mononeuropathy** — why: this cannot be skipped because the patient's symptoms and electromyographic evaluation suggest damage to a single nerve
    - 支持：inability to perform the “Ok” sign and to form a fist / electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant
- `stance:coverage` **Neuropathy** — why: this cannot be skipped because the patient's symptoms and electromyographic evaluation suggest nerve disease
    - 支持：episodes of isolated, sudden weakness of the left upper limb / electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant
- `stance:coverage` **Radial neuropathy** — why: this cannot be skipped because the patient's electromyographic evaluation suggests damage to the radial nerve
    - 支持：electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice
- `stance:coverage` **Musculoskeletal disorder** — why: this cannot be skipped because the patient's symptoms could be related to a musculoskeletal disorder
    - 支持：episodes of isolated, sudden weakness of the left upper limb / decreased grip strength on the left
    - 反对：no muscular wasting, pathological reflexes, or focal neurological signs
- `stance:mechanism` **Anterior Interosseous Nerve Syndrome** — why: This disease unifies the neurogenic atrophy of muscles innervated by the anterior interosseous nerve.
    - 支持：episodes of isolated, sudden weakness of the left upper limb / weakness of the distal phalanx of the thumb and middle phalanx of the index finger / inability to perform the “Ok” sign and to form a fist
- `stance:mechanism` **Neuralgic Amyotrophy** — why: This disease unifies the neurogenic atrophy and changes in multiple muscles of the left upper limb.
    - 支持：electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice
- `stance:mechanism` **Mononeuritis Multiplex** — why: This disease unifies the multiple nerve involvement, but does not fully explain the lack of sensory deficits.
    - 支持：weakness of the distal phalanx of the thumb and middle phalanx of the index finger / electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant
    - 反对：no sensory deficits
- `stance:mechanism` **Brachial Plexitis** — why: This disease unifies the involvement of multiple muscles and nerves, but does not fully explain the normal MRI findings.
    - 支持：electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant / including the flexor digitorum profundus and pronator quadratus, and also changes in the biceps brachii, trice
    - 反对：MRI of the left upper extremity was performed and showed no abnormalities

</details>

### impc（召回 miss，判分 False）

- champion：**Anterior Interosseous Nerve Syndrome**　runner-up：Mononeuropathy　margin：medium
- selector 理由：Specific evidence of neurogenic atrophy of muscles innervated by the anterior interosseous nerve

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Anterior Interosseous Nerve Syndrome | none | 3.7 | D1E001 / D1E002 / D1E003 | — |
| Mononeuropathy | none | 6.35 | D1E001 / D2E004 / D2E005 / D2E006 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Anterior Interosseous Nerve Syndrome** — why: The patient's symptoms and electromyographic evaluation results are consistent with anterior interosseous nerve syndrome.
    - 支持：episodes of isolated, sudden weakness of the left upper limb / weakness of the distal phalanx of the thumb and middle phalanx of the index finger / neurogenic atrophy of muscles innervated by the anterior interosseous nerve
- `D2` **Anterior Interosseous Nerve Syndrome** — why: The patient's symptoms and electromyographic evaluation suggest damage to the anterior interosseous nerve.
    - 支持：weakness of the distal phalanx of the thumb and middle phalanx of the index finger / neurogenic atrophy of muscles innervated by the anterior interosseous nerve
- `D2` **Mononeuropathy** — why: The patient's presentation of isolated weakness in one limb is consistent with mononeuropathy.
    - 支持：episodes of isolated, sudden weakness of the left upper limb / no muscular wasting, pathological reflexes, or focal neurological signs
- `D2` **Neuropathy** — why: The patient's electromyographic evaluation and decreased grip strength suggest neuropathy.
    - 支持：decreased grip strength on the left / electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles
- `D3` **Anterior Interosseous Nerve Syndrome** — why: The patient's symptoms and electromyographic evaluation suggest damage to the anterior interosseous nerve.
    - 支持：episodes of isolated, sudden weakness of the left upper limb / neurogenic atrophy of muscles innervated by the anterior interosseous nerve
- `D3` **Mononeuropathy** — why: The patient's presentation of isolated weakness in one limb suggests a mononeuropathy.
    - 支持：weakness of the distal phalanx of the thumb and middle phalanx of the index finger / decreased grip strength on the left
- `D3` **Neuropathy** — why: The patient's electromyographic evaluation and symptoms suggest a neuropathic process.
    - 支持：inability to perform the “Ok” sign and to form a fist / electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles

</details>

<details><summary>selector 淘汰理由</summary>

- **Mononeuropathy** — Less specific diagnosis compared to Anterior Interosseous Nerve Syndrome

</details>

### forest（召回 miss，判分 False）

- champion：**Anterior Interosseous Nerve Syndrome**　runner-up：Anterior Interosseous Syndrome　margin：high
- selector 理由：The patient's symptoms of weakness in the distal phalanx of the thumb and middle phalanx of the index finger, along with electromyographic evidence of neurogenic atrophy of muscles innervated by the anterior interosseous nerve, most strongly support this diagnosis.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Anterior Interosseous Syndrome | none | 2.0 | AX_SE001 / AX_SE002 | — |
| Mononeuropathy | none | 2.0 | AX_SE003 / AX_SE002 | — |
| Neuralgic amyotrophy | none | 2.0 | AX_SE003 / AX_SE002 | — |
| Mononeuritis multiplex | none | 2.0 | AX_SE001 / AX_SE002 | — |
| Anterior Interosseous Nerve Syndrome | none | 2.0 | AX_SE001 / AX_ME004 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Anterior Interosseous Syndrome** — why: The patient's symptoms and electromyographic evaluation suggest damage to the anterior interosseous nerve.
    - 支持：weakness of the distal phalanx of the thumb and middle phalanx of the index finger / neurogenic atrophy of muscles innervated by the anterior interosseous nerve
- `syndrome_anatomy` **Mononeuropathy** — why: The patient's symptoms are limited to a single nerve distribution, suggesting a mononeuropathy.
    - 支持：episodes of isolated, sudden weakness of the left upper limb / neurogenic atrophy of muscles innervated by the anterior interosseous nerve
- `mechanism_etiology` **Neuralgic amyotrophy** — why: The patient's presentation of sudden weakness and neurogenic atrophy of specific muscles is consistent with neuralgic amyotrophy.
    - 支持：episodes of isolated, sudden weakness of the left upper limb / neurogenic atrophy of muscles innervated by the anterior interosseous nerve
- `mechanism_etiology` **Mononeuritis multiplex** — why: The patient's symptoms and electromyographic findings suggest damage to multiple peripheral nerves.
    - 支持：weakness of the distal phalanx of the thumb and middle phalanx of the index finger / neurogenic atrophy of muscles innervated by the anterior interosseous nerve
- `definitive_modality` **Anterior Interosseous Nerve Syndrome** — why: The patient's symptoms and electromyographic findings are consistent with anterior interosseous nerve syndrome.
    - 支持：weakness of the distal phalanx of the thumb and middle phalanx of the index finger / electromyographic evaluation of the left upper limb showed neurogenic atrophy of muscles innervated by the ant

</details>

<details><summary>selector 淘汰理由</summary>

- **Mononeuritis multiplex** — Lack of evidence for multiple nerve involvement
- **Mononeuropathy** — While the patient has mononeuropathy, the specific involvement of the anterior interosseous nerve points to a more specific diagnosis
- **Neuralgic amyotrophy** — The patient's presentation does not include the typical severe pain of neuralgic amyotrophy

</details>

---

## MCR_v1_seq100/49 — StumpAppendicitis

- 家族 MCR / 层 MCR_v1_seq100 / 权重 12.5
- 指南能力：本地扩展 D3_direct_vignette_matched（上游三源 D2_direct_but_partial_or_general）
- 纳入金标的方法：collapse3c, multistance, impc, forest；其中未选中：impc, forest

### vignette 全文

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

### collapse3c（召回 champion_strong，判分 True）

- champion：**Appendiceal stump appendicitis**　runner-up：　margin：
- selector 理由：the presence of a swollen and thickened tubular structure at the cecal pole, a pericecal collection, and a history of laparoscopic appendectomy, all of which are specifically explained by Appendiceal stump appendicitis.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Appendiceal stump appendicitis | strong | 0.0 | a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole / a 25‐mm pericecal collection adjacent to surgical clips / a laparoscopic appendectomy performed 8 months earlier | — |
| Intestinal obstruction | none | 0.0 | a 24‐hour history of right iliac fossa pain / nausea, and diarrhea / pain in the right lower quadrant without peritoneal signs | a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole |
| Cecal diverticulitis | none | 0.0 | a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole / a 25‐mm pericecal collection adjacent to surgical clips | a laparoscopic appendectomy performed 8 months earlier |
| Intra-abdominal abscess | none | 0.0 | a 25‐mm pericecal collection adjacent to surgical clips | a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole |
| Post-surgical adhesions | none | 0.0 | a laparoscopic appendectomy performed 8 months earlier | a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Appendiceal stump appendicitis** — why: The presence of a swollen and thickened tubular structure at the cecal pole with a pericecal collection adjacent to surgical clips, in a patient with a history of laparoscopic appendectomy, suggests stump appendicitis.
    - 支持：a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole / a 25‐mm pericecal collection adjacent to surgical clips / a laparoscopic appendectomy performed 8 months earlier
- `c3` **Intestinal obstruction** — why: The patient's symptoms of right iliac fossa pain, nausea, and diarrhea could suggest intestinal obstruction, but the presence of a swollen tubular structure at the cecal pole points towards a different diagnosis.
    - 支持：a 24‐hour history of right iliac fossa pain / nausea, and diarrhea / pain in the right lower quadrant without peritoneal signs
    - 反对：a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole
- `c3` **Cecal diverticulitis** — why: The presence of a swollen and thickened tubular structure at the cecal pole with a pericecal collection could suggest cecal diverticulitis, but the history of appendectomy makes stump appendicitis more likely.
    - 支持：a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole / a 25‐mm pericecal collection adjacent to surgical clips
    - 反对：a laparoscopic appendectomy performed 8 months earlier
- `c3` **Intra-abdominal abscess** — why: The presence of a pericecal collection could suggest an intra-abdominal abscess, but the context of the swollen tubular structure and history of appendectomy points towards stump appendicitis.
    - 支持：a 25‐mm pericecal collection adjacent to surgical clips
    - 反对：a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole
- `c3` **Post-surgical adhesions** — why: The history of laparoscopic appendectomy could suggest post-surgical adhesions, but the presence of a swollen tubular structure at the cecal pole with a pericecal collection points towards a different diagnosis.
    - 支持：a laparoscopic appendectomy performed 8 months earlier
    - 反对：a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole

</details>

### multistance（召回 champion_strong，判分 True）

- champion：**Appendiceal stump appendicitis**　runner-up：Appendiceal Stump Abscess　margin：
- selector 理由：The champion is chosen because it accounts for the most decisive findings in the vignette, including the patient's history of laparoscopic appendectomy and the abdominal CT scan findings, and it has no evidence against it.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Appendiceal stump appendicitis | strong | 0.0 | a laparoscopic appendectomy performed 8 months earlier / an abdominal CT scan demonstrated a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal  / a 25‐mm pericecal collection adjacent to surgical clips | — |
| Appendicitis | strong | 0.0 | a 24‐hour history of right iliac fossa pain / a laparoscopic appendectomy performed 8 months earlier / an abdominal CT scan demonstrated a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal  | — |
| Appendiceal Stump Abscess | near | 0.0 | a laparoscopic appendectomy performed 8 months earlier / a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils / a C‐reactive protein level of 180 mg/dL / a 25‐mm pericecal collection adjacent to surgical clips | — |
| Cecal diverticulitis | none | 0.0 | an abdominal CT scan demonstrated a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal  / a 25‐mm pericecal collection adjacent to surgical clips | a laparoscopic appendectomy performed 8 months earlier |
| Intestinal tuberculosis | none | 0.0 | a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils / a C‐reactive protein level of 180 mg/dL | — |
| Typhlitis | none | 0.0 | a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils / an abdominal CT scan demonstrated a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal  | he was febrile |
| Pericecal abscess | none | 0.0 | a 25‐mm pericecal collection adjacent to surgical clips / a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils / a C‐reactive protein level of 180 mg/dL / an abdominal CT scan demonstrated a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal  | — |
| Inflammatory bowel disease | none | 0.0 | a 24‐hour history of right iliac fossa pain / nausea, and diarrhea / a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils | — |
| Diverticulitis | none | 0.0 | a 24‐hour history of right iliac fossa pain / abdominal palpation elicited pain in the right lower quadrant without peritoneal signs / a C‐reactive protein level of 180 mg/dL / a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils | — |
| Surgical Site Infection | none | 0.0 | a laparoscopic appendectomy performed 8 months earlier / a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils / a C‐reactive protein level of 180 mg/dL / a 25‐mm pericecal collection adjacent to surgical clips | — |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Appendiceal stump appendicitis** — why: The presence of a swollen and thickened tubular structure at the cecal pole with a pericecal collection adjacent to surgical clips, in a patient with a history of laparoscopic appendectomy, suggests stump appendicitis.
    - 支持：a laparoscopic appendectomy performed 8 months earlier / an abdominal CT scan demonstrated a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal  / a 25‐mm pericecal collection adjacent to surgical clips
- `stance:commit` **Cecal diverticulitis** — why: The location and appearance of the swollen and thickened tubular structure at the cecal pole, along with the pericecal collection, could suggest cecal diverticulitis.
    - 支持：an abdominal CT scan demonstrated a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal  / a 25‐mm pericecal collection adjacent to surgical clips
    - 反对：a laparoscopic appendectomy performed 8 months earlier
- `stance:commit` **Intestinal tuberculosis** — why: The elevated white blood cell count and C-reactive protein level could indicate an infectious or inflammatory process such as intestinal tuberculosis.
    - 支持：a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils / a C‐reactive protein level of 180 mg/dL
- `stance:commit` **Typhlitis** — why: The presence of a swollen and thickened tubular structure at the cecal pole, along with an elevated white blood cell count, could suggest typhlitis.
    - 支持：a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils / an abdominal CT scan demonstrated a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal 
    - 反对：he was febrile
- `stance:commit` **Pericecal abscess** — why: The presence of a pericecal collection adjacent to surgical clips suggests a pericecal abscess.
    - 支持：a 25‐mm pericecal collection adjacent to surgical clips
- `stance:coverage` **Appendicitis** — why: The patient's history of appendectomy and current presentation of right iliac fossa pain and swollen tubular structure at the cecal pole suggest appendicitis.
    - 支持：a 24‐hour history of right iliac fossa pain / a laparoscopic appendectomy performed 8 months earlier / an abdominal CT scan demonstrated a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal 
- `stance:coverage` **Abscess** — why: The presence of a pericecal collection and elevated inflammatory markers suggests an abscess.
    - 支持：a 25‐mm pericecal collection adjacent to surgical clips / a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils / a C‐reactive protein level of 180 mg/dL
- `stance:coverage` **Inflammatory bowel disease** — why: The patient's symptoms of abdominal pain, nausea, and diarrhea, along with elevated inflammatory markers, could suggest inflammatory bowel disease.
    - 支持：a 24‐hour history of right iliac fossa pain / nausea, and diarrhea / a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils
- `stance:coverage` **Diverticulitis** — why: The patient's presentation of right iliac fossa pain and elevated inflammatory markers could suggest diverticulitis, although the location and absence of peritoneal signs make it less likely.
    - 支持：a 24‐hour history of right iliac fossa pain / abdominal palpation elicited pain in the right lower quadrant without peritoneal signs / a C‐reactive protein level of 180 mg/dL
- `stance:mechanism` **Intra-abdominal Abscess** — why: The patient's symptoms and laboratory results suggest an infectious process, and the abdominal CT scan demonstrates a swollen and thickened tubular structure with a pericecal collection, which is consistent with an intra-abdominal abscess.
    - 支持：a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils / a C‐reactive protein level of 180 mg/dL / an abdominal CT scan demonstrated a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal  / a 25‐mm pericecal collection adjacent to surgical clips
- `stance:mechanism` **Surgical Site Infection** — why: The patient's history of recent surgery and the presence of a pericecal collection adjacent to surgical clips suggest a surgical site infection.
    - 支持：a laparoscopic appendectomy performed 8 months earlier / a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils / a C‐reactive protein level of 180 mg/dL / a 25‐mm pericecal collection adjacent to surgical clips
- `stance:mechanism` **Diverticulitis** — why: The patient's symptoms and laboratory results suggest an inflammatory process, and the abdominal CT scan demonstrates a swollen and thickened tubular structure, which is consistent with diverticulitis.
    - 支持：abdominal palpation elicited pain in the right lower quadrant without peritoneal signs / a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils / a C‐reactive protein level of 180 mg/dL / an abdominal CT scan demonstrated a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal 
- `stance:mechanism` **Appendiceal Stump Abscess** — why: The patient's history of recent appendectomy and the presence of a pericecal collection adjacent to surgical clips suggest an appendiceal stump abscess.
    - 支持：a laparoscopic appendectomy performed 8 months earlier / a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils / a C‐reactive protein level of 180 mg/dL / a 25‐mm pericecal collection adjacent to surgical clips

</details>

### impc（召回 top2_strong，判分 False）

- champion：**Abscess**　runner-up：Appendicitis　margin：medium
- selector 理由：The presence of a 25-mm pericecal collection adjacent to surgical clips is a strong indicator of an abscess, especially given the patient's history of laparoscopic appendectomy.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Appendicitis | strong | 4.45 | D1E001 / D1E002 / D1E003 / D2E005 | D1E004 |
| Intestinal obstruction | none | 3.0 | D2E007 / D2E008 / D2E009 | — |
| Abscess | none | 1.0 | D3E010 | — |
| Intra-abdominal infection | none | 3.0 | D3E011 / D3E012 / D3E013 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Appendicitis** — why: The patient's symptoms and imaging findings are consistent with appendicitis, despite having a history of appendectomy.
    - 支持：right iliac fossa pain / pain in the right lower quadrant / a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole
    - 反对：he had a laparoscopic appendectomy performed 8 months earlier
- `D2` **Appendicitis** — why: The patient's symptoms and imaging results are consistent with appendicitis, despite having a history of appendectomy.
    - 支持：a 24‐hour history of right iliac fossa pain / pain in the right lower quadrant / a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole
    - 反对：he had a laparoscopic appendectomy performed 8 months earlier
- `D2` **Appendiceal stump appendicitis** — why: The presence of a swollen structure near the cecal pole and adjacent to surgical clips suggests a possible appendiceal stump appendicitis.
    - 支持：a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole / adjacent to surgical clips
- `D2` **Intestinal obstruction** — why: The patient's symptoms of nausea and diarrhea, combined with the imaging findings, could indicate an intestinal obstruction.
    - 支持：nausea / diarrhea / a swollen and thickened tubular structure
- `D3` **Appendicitis** — why: The patient's symptoms and imaging results are consistent with appendicitis, but the recent history of appendectomy complicates the diagnosis.
    - 支持：a 24‐hour history of right iliac fossa pain / a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole
    - 反对：he had a laparoscopic appendectomy performed 8 months earlier
- `D3` **Abscess** — why: The presence of a pericecal collection suggests an abscess, which could be related to the previous appendectomy.
    - 支持：a 25‐mm pericecal collection adjacent to surgical clips
- `D3` **Intra-abdominal infection** — why: The patient's fever, elevated white blood cell count, and high C-reactive protein level indicate an infectious process.
    - 支持：febrile / a white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils / a C‐reactive protein level of 180 mg/dL

</details>

<details><summary>selector 淘汰理由</summary>

- **Intestinal obstruction** — While nausea and diarrhea are present, they are not specific enough to outweigh the stronger evidence for abscess.
- **Intra-abdominal infection** — Although the patient is febrile and has elevated inflammatory markers, these findings are not specific enough to rule out abscess, and the presence of a pericecal collection is more indicative of a localized infection like an abscess.
- **Appendicitis** — The patient's history of laparoscopic appendectomy 8 months earlier makes appendicitis less likely, despite the presence of right iliac fossa pain and a swollen tubular structure, which could be consistent with other conditions like an abscess or a complicatio

</details>

### forest（召回 set_strong，判分 False）

- champion：**Appendiceal abscess**　runner-up：Intra-abdominal infection　margin：high
- selector 理由：The patient's presentation with a swollen and thickened tubular structure at the cecal pole, a pericecal collection, and elevated inflammatory markers best supports the diagnosis of an appendiceal abscess, especially given the history of a recent laparoscopic appendectomy.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Appendicitis | strong | 2.0 | AX_ME004 / AX_ME009 / AX_SE003 | AX_ME010 |
| Appendiceal abscess | weak | 5.6 | AX_SE001 / AX_ME005 / AX_SE002 / AX_ME010 | — |
| Cecal diverticulitis | none | 1.0 | AX_SE003 | — |
| Intra-abdominal infection | none | 3.0 | AX_ME006 / AX_ME007 / AX_ME008 | — |
| Complicated diverticulitis | none | 2.0 | AX_ME011 / AX_ME012 | — |
| Neutropenic colitis | none | 2.0 | AX_ME006 / AX_ME007 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Appendiceal abscess** — why: The patient's history of laparoscopic appendectomy and the presence of a pericecal collection adjacent to surgical clips support this diagnosis
    - 支持：a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole, with a 25‐mm pericecal colle
- `syndrome_anatomy` **Cecal diverticulitis** — why: The location of the swollen structure at the cecal pole is consistent with cecal diverticulitis
    - 支持：a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole
- `mechanism_etiology` **Appendicitis** — why: The patient's symptoms and imaging findings are consistent with appendicitis, despite having had an appendectomy in the past.
    - 支持：right iliac fossa pain / pain in the right lower quadrant / a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole
    - 反对：he had a laparoscopic appendectomy performed 8 months earlier
- `mechanism_etiology` **Abscess** — why: The presence of a pericecal collection adjacent to surgical clips suggests an abscess, which is a possible complication of the previous appendectomy.
    - 支持：a 25‐mm pericecal collection adjacent to surgical clips
- `mechanism_etiology` **Intra-abdominal infection** — why: The patient's fever, elevated white blood cell count, and C-reactive protein level suggest an intra-abdominal infection.
    - 支持：febrile / white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils / C‐reactive protein level of 180 mg/dL
- `definitive_modality` **Appendiceal abscess** — why: The patient's history of laparoscopic appendectomy and the presence of a pericecal collection on CT scan support this diagnosis
    - 支持：a swollen and thickened tubular structure measuring 36 × 27 mm at the cecal pole, with a 25‐mm pericecal colle
- `definitive_modality` **Complicated diverticulitis** — why: The presence of a thickened tubular structure and a pericecal collection on CT scan are consistent with complicated diverticulitis
    - 支持：a swollen and thickened tubular structure / a 25‐mm pericecal collection
- `definitive_modality` **Neutropenic colitis** — why: The patient's fever and elevated white blood cell count with a high percentage of neutrophils support this diagnosis
    - 支持：febrile / white‐blood‐cell count of 25,000 cells/mm3 with 85% neutrophils
- `definitive_modality` **Post-surgical abscess** — why: The presence of a collection adjacent to surgical clips on CT scan supports this diagnosis
    - 支持：a 25‐mm pericecal collection adjacent to surgical clips

</details>

<details><summary>selector 淘汰理由</summary>

- **Appendicitis** — The patient had a laparoscopic appendectomy performed 8 months earlier, making appendicitis less likely.
- **Complicated diverticulitis** — While diverticulitis could explain some findings, the specific location and history of appendectomy make appendiceal abscess more likely.
- **Neutropenic colitis** — There is no mention of neutropenia in the patient's presentation.
- **Cecal diverticulitis** — Similar to complicated diverticulitis, cecal diverticulitis is less specific and does not fully explain the patient's presentation as well as appendiceal abscess does.

</details>

---

## MCR_v1_seq100/56 — Spindle cell squamous cell carcinoma

- 家族 MCR / 层 MCR_v1_seq100 / 权重 12.5
- 指南能力：本地扩展 D2_direct_but_partial_or_general（上游三源 D2_direct_but_partial_or_general）
- 纳入金标的方法：collapse3c, multistance, impc, forest；其中未选中：collapse3c, multistance, impc, forest

### vignette 全文

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

### collapse3c（召回 set_near，判分 False）

- champion：**Postradiation Sarcoma**　runner-up：Malignant Spindle Cell Sarcoma　margin：
- selector 理由：The history of chemoradiotherapy 15 years earlier and the presence of a moth-eaten pattern of mandibular bone resorption decided it

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Malignant Spindle Cell Sarcoma | weak | 0.0 | The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils w / Immunohistochemical staining revealed that the spindle cells were positive for vimentin, α-smooth muscle actin | — |
| Postradiation Sarcoma | none | 0.0 | He had undergone chemoradiotherapy 15 years earlier for squamous cell carcinoma of the left buccal mucosa, wit / Panoramic radiography showed a moth-eaten pattern of mandibular bone resorption | — |
| Inflammatory Myofibroblastic Tumor | none | 0.0 | A biopsy specimen showed loose granulation tissue with scattered atypical spindle and pleomorphic cells in a f | Ki-67 labeling index was approximately 50% |
| Leiomyosarcoma | none | 0.0 | The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils w / Immunohistochemical staining revealed that the spindle cells were positive for vimentin, α-smooth muscle actin | — |
| Undifferentiated Pleomorphic Sarcoma | none | 0.0 | A biopsy specimen showed loose granulation tissue with scattered atypical spindle and pleomorphic cells in a f / Ki-67 labeling index was approximately 50% | — |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Malignant Spindle Cell Sarcoma** — why: The presence of atypical spindle cells with basophilic cytoplasm, bizarre nuclei, and atypical mitoses, along with positive immunohistochemical staining for vimentin and other markers, earned this slot.
    - 支持：The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils w / Immunohistochemical staining revealed that the spindle cells were positive for vimentin, α-smooth muscle actin
- `c3` **Postradiation Sarcoma** — why: The history of previous chemoradiotherapy and the development of a new malignant process at the site of previous radiation earned this slot.
    - 支持：He had undergone chemoradiotherapy 15 years earlier for squamous cell carcinoma of the left buccal mucosa, wit / Panoramic radiography showed a moth-eaten pattern of mandibular bone resorption
- `c3` **Inflammatory Myofibroblastic Tumor** — why: The presence of loose granulation tissue with atypical spindle cells and inflammatory cells, although the high Ki-67 labeling index is not typical for this entity.
    - 支持：A biopsy specimen showed loose granulation tissue with scattered atypical spindle and pleomorphic cells in a f
    - 反对：Ki-67 labeling index was approximately 50%
- `c3` **Leiomyosarcoma** — why: The positive staining for α-smooth muscle actin and the presence of atypical spindle cells with basophilic cytoplasm earned this slot, although the positivity for p63, p53, and CD68 is not typical for leiomyosarcoma.
    - 支持：The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils w / Immunohistochemical staining revealed that the spindle cells were positive for vimentin, α-smooth muscle actin
    - 反对：Immunohistochemical staining revealed that the spindle cells were positive for p63, p53, and CD68
- `c3` **Undifferentiated Pleomorphic Sarcoma** — why: The presence of atypical pleomorphic cells, loose granulation tissue, and a high Ki-67 labeling index earned this slot.
    - 支持：A biopsy specimen showed loose granulation tissue with scattered atypical spindle and pleomorphic cells in a f / Ki-67 labeling index was approximately 50%

</details>

### multistance（召回 set_strong，判分 False）

- champion：**Malignant Spindle Cell Sarcoma**　runner-up：Sarcomatoid Carcinoma　margin：
- selector 理由：The champion is chosen because it has the most specific and detailed for evidence, including immunohistochemical staining and atypical mitoses, which are unique to this candidate.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Gingival Squamous Cell Carcinoma | near | 0.0 | A 69-year-old Japanese man presented with pain and a 10-mm polypoid mass on the left lower gingiva / a rough-surfaced polypoid lesion in the left lower molar gingiva covered by a whitish pseudomembrane | The overlying squamous epithelium exhibited only slight nuclear enlargement without dysplasia |
| Carcinoma | strong | 0.0 | He had undergone chemoradiotherapy 15 years earlier for squamous cell carcinoma of the left buccal mucosa, wit | — |
| Malignant Spindle Cell Sarcoma | weak | 0.0 | The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils w / Immunohistochemical staining revealed that the spindle cells were positive for vimentin, α-smooth muscle actin | — |
| Postradiation Sarcoma | none | 0.0 | He had undergone chemoradiotherapy 15 years earlier for squamous cell carcinoma of the left buccal mucosa, wit / Panoramic radiography showed a moth-eaten pattern of mandibular bone resorption / Contrast-enhanced CT demonstrated an enhancing soft-tissue mass with irregular mandibular bone destruction | — |
| Inflammatory Pseudotumor | none | 0.0 | A biopsy specimen showed loose granulation tissue with scattered atypical spindle and pleomorphic cells in a f / Ki-67 labeling index was approximately 50% | The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils w |
| Gingival Granuloma | none | 0.0 | A 69-year-old Japanese man presented with pain and a 10-mm polypoid mass on the left lower gingiva / a rough-surfaced polypoid lesion in the left lower molar gingiva covered by a whitish pseudomembrane | The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils w |
| Sarcoma | weak | 0.0 | a rough-surfaced polypoid lesion in the left lower molar gingiva covered by a whitish pseudomembrane / A biopsy specimen showed loose granulation tissue with scattered atypical spindle and pleomorphic cells in a f / The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils w / These findings prompted consideration of a malignant spindle cell process | — |
| Lymphoma | none | 0.0 | Panoramic radiography showed a moth-eaten pattern of mandibular bone resorption / Contrast-enhanced CT demonstrated an enhancing soft-tissue mass with irregular mandibular bone destruction | The overlying squamous epithelium exhibited only slight nuclear enlargement without dysplasia |
| Gingival hyperplasia | none | 0.0 | A 69-year-old Japanese man presented with pain and a 10-mm polypoid mass on the left lower gingiva / trismus was present | — |
| Sarcomatoid Carcinoma | weak | 0.0 | a rough-surfaced polypoid lesion in the left lower molar gingiva covered by a whitish pseudomembrane / Contrast-enhanced CT demonstrated an enhancing soft-tissue mass with irregular mandibular bone destruction / The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils w / Immunohistochemical staining revealed that the spindle cells were positive for vimentin, α-smooth muscle actin | — |
| Osteosarcoma | none | 0.0 | Panoramic radiography showed a moth-eaten pattern of mandibular bone resorption / Contrast-enhanced CT demonstrated an enhancing soft-tissue mass with irregular mandibular bone destruction | The overlying squamous epithelium exhibited only slight nuclear enlargement without dysplasia |
| Gingival Fibrosarcoma | none | 0.0 | a rough-surfaced polypoid lesion in the left lower molar gingiva covered by a whitish pseudomembrane / A biopsy specimen showed loose granulation tissue with scattered atypical spindle and pleomorphic cells in a f | He had undergone chemoradiotherapy 15 years earlier for squamous cell carcinoma of the left buccal mucosa, wit |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Malignant Spindle Cell Sarcoma** — why: The presence of atypical spindle cells with basophilic cytoplasm, bizarre nuclei, and atypical mitoses, along with positive immunohistochemical staining for vimentin and other markers, earned this slot.
    - 支持：The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils w / Immunohistochemical staining revealed that the spindle cells were positive for vimentin, α-smooth muscle actin
- `stance:commit` **Postradiation Sarcoma** — why: The history of previous chemoradiotherapy and the development of a new malignant process at the site of previous radiation earned this slot.
    - 支持：He had undergone chemoradiotherapy 15 years earlier for squamous cell carcinoma of the left buccal mucosa, wit / Panoramic radiography showed a moth-eaten pattern of mandibular bone resorption
- `stance:commit` **Gingival Squamous Cell Carcinoma** — why: The presence of a polypoid mass on the gingiva and a history of previous squamous cell carcinoma earned this slot, despite the lack of dysplasia in the overlying epithelium.
    - 支持：A 69-year-old Japanese man presented with pain and a 10-mm polypoid mass on the left lower gingiva / a rough-surfaced polypoid lesion in the left lower molar gingiva covered by a whitish pseudomembrane
    - 反对：The overlying squamous epithelium exhibited only slight nuclear enlargement without dysplasia
- `stance:commit` **Inflammatory Pseudotumor** — why: The presence of loose granulation tissue and a high Ki-67 labeling index, along with the presence of inflammatory cells, earned this slot, despite the presence of atypical spindle cells.
    - 支持：A biopsy specimen showed loose granulation tissue with scattered atypical spindle and pleomorphic cells in a f / Ki-67 labeling index was approximately 50%
    - 反对：The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils w
- `stance:commit` **Gingival Granuloma** — why: The presence of a polypoid mass on the gingiva and a rough-surfaced lesion with a whitish pseudomembrane earned this slot, despite the presence of atypical spindle cells.
    - 支持：A 69-year-old Japanese man presented with pain and a 10-mm polypoid mass on the left lower gingiva / a rough-surfaced polypoid lesion in the left lower molar gingiva covered by a whitish pseudomembrane
    - 反对：The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils w
- `stance:coverage` **Sarcoma** — why: The presence of atypical spindle cells with basophilic cytoplasm, bizarre nuclei, and atypical mitoses suggests a malignant spindle cell process, which cannot be skipped.
    - 支持：a rough-surfaced polypoid lesion in the left lower molar gingiva covered by a whitish pseudomembrane / A biopsy specimen showed loose granulation tissue with scattered atypical spindle and pleomorphic cells in a f / The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils w / These findings prompted consideration of a malignant spindle cell process
- `stance:coverage` **Lymphoma** — why: The presence of a moth-eaten pattern of bone resorption and an enhancing soft-tissue mass with irregular bone destruction suggests the possibility of lymphoma, which must be excluded.
    - 支持：Panoramic radiography showed a moth-eaten pattern of mandibular bone resorption / Contrast-enhanced CT demonstrated an enhancing soft-tissue mass with irregular mandibular bone destruction
    - 反对：The overlying squamous epithelium exhibited only slight nuclear enlargement without dysplasia
- `stance:coverage` **Carcinoma** — why: The patient's history of squamous cell carcinoma and the presence of a new lesion in the same region suggest the possibility of carcinoma, which cannot be skipped.
    - 支持：He had undergone chemoradiotherapy 15 years earlier for squamous cell carcinoma of the left buccal mucosa, wit
    - 反对：The spindle cells were negative for pan-cytokeratin and other epithelial markers
- `stance:coverage` **Gingival hyperplasia** — why: The presence of a polypoid mass on the gingiva and trismus suggests the possibility of gingival hyperplasia, which must be considered in the differential diagnosis.
    - 支持：A 69-year-old Japanese man presented with pain and a 10-mm polypoid mass on the left lower gingiva / trismus was present
    - 反对：The biopsy specimen showed loose granulation tissue with scattered atypical spindle and pleomorphic cells in a
- `stance:mechanism` **Sarcomatoid Carcinoma** — why: The presence of atypical spindle cells with basophilic cytoplasm, bizarre nuclei, and atypical mitoses, along with the expression of vimentin, α-smooth muscle actin, p63, p53, and CD68, suggests a malignant spindle cell process, which is consistent with sarcom
    - 支持：a rough-surfaced polypoid lesion in the left lower molar gingiva covered by a whitish pseudomembrane / Contrast-enhanced CT demonstrated an enhancing soft-tissue mass with irregular mandibular bone destruction / The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses; many contained neutrophils w / Immunohistochemical staining revealed that the spindle cells were positive for vimentin, α-smooth muscle actin
- `stance:mechanism` **Osteosarcoma** — why: The moth-eaten pattern of mandibular bone resorption and the presence of an enhancing soft-tissue mass with irregular bone destruction suggest osteosarcoma, although the lack of epithelial dysplasia is not typical for this diagnosis.
    - 支持：Panoramic radiography showed a moth-eaten pattern of mandibular bone resorption / Contrast-enhanced CT demonstrated an enhancing soft-tissue mass with irregular mandibular bone destruction
    - 反对：The overlying squamous epithelium exhibited only slight nuclear enlargement without dysplasia
- `stance:mechanism` **Gingival Fibrosarcoma** — why: The presence of a rough-surfaced polypoid lesion and the biopsy findings of atypical spindle cells in a fibrin-rich stroma suggest gingival fibrosarcoma, although the patient's history of chemoradiotherapy for squamous cell carcinoma is not typical for this di
    - 支持：a rough-surfaced polypoid lesion in the left lower molar gingiva covered by a whitish pseudomembrane / A biopsy specimen showed loose granulation tissue with scattered atypical spindle and pleomorphic cells in a f
    - 反对：He had undergone chemoradiotherapy 15 years earlier for squamous cell carcinoma of the left buccal mucosa, wit
- `stance:mechanism` **Radiation-Induced Sarcoma** — why: The patient's history of chemoradiotherapy and the development of a new malignant spindle cell process suggest radiation-induced sarcoma, which is a known complication of radiation therapy.
    - 支持：He had undergone chemoradiotherapy 15 years earlier for squamous cell carcinoma of the left buccal mucosa, wit / Contrast-enhanced CT demonstrated an enhancing soft-tissue mass with irregular mandibular bone destruction

</details>

### impc（召回 set_near，判分 False）

- champion：**Sarcoma**　runner-up：Spindle cell carcinoma　margin：medium
- selector 理由：The presence of atypical spindle and pleomorphic cells, bizarre nuclei, and atypical mitoses, along with the positive immunohistochemical staining for vimentin and other markers, strongly supports the diagnosis of a malignant spindle cell process, which is most consistent with Sarcoma.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Spindle cell carcinoma | near | 2.1 | D1E002 / D2E006 / D3E011 | D2E007 |
| Sarcoma | none | 5.7 | D1E001 / D1E002 / D1E003 / D2E004 | — |
| Necrotizing sialometaplasia | none | 3.0 | D3E008 / D3E009 / D3E010 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Sarcoma** — why: The presence of atypical spindle cells with bizarre nuclei and atypical mitoses, along with a high Ki-67 labeling index, suggests a malignant process, and the spindle cell morphology is consistent with sarcoma.
    - 支持：a rough-surfaced polypoid lesion / atypical spindle and pleomorphic cells / bizarre nuclei, and atypical mitoses
- `D2` **Sarcoma** — why: The presence of atypical spindle and pleomorphic cells with bizarre nuclei and atypical mitoses suggests a malignant spindle cell process, which is consistent with sarcoma.
    - 支持：a rough-surfaced polypoid lesion / atypical spindle and pleomorphic cells / bizarre nuclei, and atypical mitoses
- `D2` **Osteosarcoma** — why: The radiographic findings of a moth-eaten pattern of mandibular bone resorption and irregular mandibular bone destruction are suggestive of osteosarcoma.
    - 支持：moth-eaten pattern of mandibular bone resorption / irregular mandibular bone destruction
- `D2` **Spindle cell carcinoma** — why: The presence of atypical spindle cells with positive staining for vimentin, α-smooth muscle actin, p63, p53, and CD68, but negative for epithelial markers, suggests a spindle cell carcinoma.
    - 支持：atypical spindle and pleomorphic cells / positive for vimentin, α-smooth muscle actin, p63, p53, and CD68
    - 反对：negative for pan-cytokeratin and other epithelial markers
- `D3` **Sarcoma** — why: The presence of atypical spindle and pleomorphic cells with bizarre nuclei and atypical mitoses suggests a malignant spindle cell process, which is consistent with sarcoma.
    - 支持：a rough-surfaced polypoid lesion / atypical spindle and pleomorphic cells / bizarre nuclei, and atypical mitoses
- `D3` **Necrotizing sialometaplasia** — why: The presence of a whitish pseudomembrane, inflammatory cells, and neutrophils within cytoplasmic vacuoles could be indicative of necrotizing sialometaplasia, although the overall clinical and histological picture seems more complex.
    - 支持：a whitish pseudomembrane / inflammatory cells / neutrophils within cytoplasmic vacuoles
- `D3` **Spindle cell carcinoma** — why: The expression of p63 and p53 in the spindle cells could suggest a spindle cell carcinoma, but the lack of epithelial marker expression makes this less likely.
    - 支持：atypical spindle and pleomorphic cells / p63, p53
    - 反对：negative for pan-cytokeratin and other epithelial markers

</details>

<details><summary>selector 淘汰理由</summary>

- **Necrotizing sialometaplasia** — Lack of specific findings and lower score_logit compared to Sarcoma

</details>

### forest（召回 set_near，判分 False）

- champion：**Sarcomatoid carcinoma**　runner-up：Sarcomatoid squamous cell carcinoma　margin：medium
- selector 理由：The presence of atypical spindle and pleomorphic cells, positive immunohistochemical staining for vimentin, α-smooth muscle actin, p63, p53, and CD68, and the patient's history of squamous cell carcinoma support this diagnosis.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Spindle cell carcinoma | near | 2.0 | AX_SE002 / AX_SE003 | — |
| Sarcomatoid squamous cell carcinoma | near | 2.25 | AX_ME006 / AX_ME007 | — |
| Sarcomatoid carcinoma | weak | 5.5 | AX_SE001 / AX_SE002 / AX_SE004 / AX_ME012 | — |
| Malignant fibrous histiocytoma | none | 4.5 | AX_SE005 / AX_SE004 / AX_ME006 / AX_ME011 | — |
| Inflammatory myofibroblastic tumor | none | 1.25 | AX_ME009 | — |
| Osteosarcoma | none | 2.25 | AX_ME008 / AX_ME010 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Sarcomatoid carcinoma** — why: The presence of atypical spindle cells with positive immunohistochemical staining for vimentin and other markers suggests a sarcomatoid carcinoma.
    - 支持：a rough-surfaced polypoid lesion / atypical spindle and pleomorphic cells / spindle cells were positive for vimentin, α-smooth muscle actin, p63, p53, and CD68
- `syndrome_anatomy` **Spindle cell carcinoma** — why: The biopsy specimen showing loose granulation tissue with scattered atypical spindle cells supports the diagnosis of spindle cell carcinoma.
    - 支持：atypical spindle and pleomorphic cells / spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses
- `syndrome_anatomy` **Malignant fibrous histiocytoma** — why: The presence of atypical spindle cells with positive immunohistochemical staining for CD68 suggests a malignant fibrous histiocytoma.
    - 支持：loose granulation tissue with scattered atypical spindle and pleomorphic cells / spindle cells were positive for vimentin, α-smooth muscle actin, p63, p53, and CD68
- `mechanism_etiology` **Sarcomatoid squamous cell carcinoma** — why: The presence of atypical spindle and pleomorphic cells with positive immunohistochemical staining for p63 and p53 suggests a sarcomatoid transformation of squamous cell carcinoma.
    - 支持：a biopsy specimen showed loose granulation tissue with scattered atypical spindle and pleomorphic cells / The spindle cells had basophilic cytoplasm, bizarre nuclei, and atypical mitoses
- `mechanism_etiology` **Inflammatory myofibroblastic tumor** — why: The presence of atypical spindle cells in a fibrin-rich edematous stroma with inflammatory cells suggests an inflammatory myofibroblastic tumor.
    - 支持：loose granulation tissue with scattered atypical spindle and pleomorphic cells in a fibrin-rich edematous stro
- `mechanism_etiology` **Osteosarcoma** — why: The presence of a moth-eaten pattern of mandibular bone resorption and irregular bone destruction suggests an osteosarcoma.
    - 支持：a moth-eaten pattern of mandibular bone resorption / irregular mandibular bone destruction
- `definitive_modality` **Malignant Fibrous Histiocytoma** — why: The presence of atypical spindle cells with specific immunohistochemical staining patterns suggests a malignant spindle cell process.
    - 支持：a biopsy specimen showed loose granulation tissue with scattered atypical spindle and pleomorphic cells / Immunohistochemical staining revealed that the spindle cells were positive for vimentin, α-smooth muscle actin
- `definitive_modality` **Sarcomatoid Carcinoma** — why: The patient's history of squamous cell carcinoma and the presence of atypical spindle cells suggest a possible sarcomatoid transformation.
    - 支持：He had undergone chemoradiotherapy 15 years earlier for squamous cell carcinoma of the left buccal mucosa / The overlying squamous epithelium exhibited only slight nuclear enlargement without dysplasia

</details>

<details><summary>selector 淘汰理由</summary>

- **Malignant fibrous histiocytoma** — Although it shares some histological features, the patient's history and the specific immunohistochemical profile better support sarcomatoid carcinoma.
- **Osteosarcoma** — The primary findings of a polypoid mass and spindle cell morphology do not strongly support osteosarcoma, despite the bone resorption.
- **Spindle cell carcinoma** — This diagnosis is less specific and does not account for the full range of histological and immunohistochemical findings as well as sarcomatoid carcinoma does.
- **Inflammatory myofibroblastic tumor** — The presence of atypical mitoses and the high Ki-67 labeling index are not typical for inflammatory myofibroblastic tumors, which are usually less aggressive.

</details>

---

## MCR_v1_seq100/74 — Catecholaminergic polymorphic ventricular tachycardia

- 家族 MCR / 层 MCR_v1_seq100 / 权重 12.5
- 指南能力：本地扩展 D3_direct_vignette_matched（上游三源 D3_direct_vignette_matched）
- 纳入金标的方法：collapse3c, multistance, impc, forest；其中未选中：collapse3c, multistance, impc

### vignette 全文

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

### collapse3c（召回 top2_strong，判分 False）

- champion：**Long QT Syndrome**　runner-up：Catecholaminergic Polymorphic Ventricular Tachycardia　margin：
- selector 理由：The evidence of bystander ECG showing ventricular fibrillation and sinus rhythm with interpolated premature ventricular complexes and a QTc of 380 ms specifically supports Long QT Syndrome.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Catecholaminergic Polymorphic Ventricular Tachycardia | strong | 0.0 | bystander ECG showed ventricular fibrillation / sinus rhythm with interpolated premature ventricular complexes | no prior history of syncope, cardiac arrest, or known cardiovascular disease |
| Long QT Syndrome | none | 0.0 | bystander ECG showed ventricular fibrillation / sinus rhythm with interpolated premature ventricular complexes and a QTc of 380 ms | cardiovascular examination was unremarkable |
| Hypertrophic Cardiomyopathy | none | 0.0 | ejection fraction of 45–50%, normal wall thickness, and no valvular abnormalities | normal wall thickness |
| Autism Spectrum Disorder-related Cardiac Dysfunction | none | 0.0 | A 21-year-old woman with autism spectrum disorder (on risperidone) and intellectual disability / ejection fraction of 45–50% | no prior history of syncope, cardiac arrest, or known cardiovascular disease |
| Risperidone-induced Cardiac Dysfunction | none | 0.0 | A 21-year-old woman with autism spectrum disorder (on risperidone) and intellectual disability / ejection fraction of 45–50% | no prior history of syncope, cardiac arrest, or known cardiovascular disease |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Long QT Syndrome** — why: The patient's witnessed collapse and ventricular fibrillation, combined with a QTc of 380 ms, suggest Long QT Syndrome.
    - 支持：bystander ECG showed ventricular fibrillation / sinus rhythm with interpolated premature ventricular complexes and a QTc of 380 ms
    - 反对：cardiovascular examination was unremarkable
- `c3` **Hypertrophic Cardiomyopathy** — why: The patient's reduced ejection fraction and normal wall thickness could be indicative of Hypertrophic Cardiomyopathy, although the normal wall thickness is not typical.
    - 支持：ejection fraction of 45–50%, normal wall thickness, and no valvular abnormalities
    - 反对：normal wall thickness
- `c3` **Catecholaminergic Polymorphic Ventricular Tachycardia** — why: The patient's ventricular fibrillation and premature ventricular complexes, combined with a lack of prior cardiac history, could suggest Catecholaminergic Polymorphic Ventricular Tachycardia.
    - 支持：bystander ECG showed ventricular fibrillation / sinus rhythm with interpolated premature ventricular complexes
    - 反对：no prior history of syncope, cardiac arrest, or known cardiovascular disease
- `c3` **Autism Spectrum Disorder-related Cardiac Dysfunction** — why: The patient's autism spectrum disorder and reduced ejection fraction may be related to cardiac dysfunction, which is a known comorbidity in ASD patients.
    - 支持：A 21-year-old woman with autism spectrum disorder (on risperidone) and intellectual disability / ejection fraction of 45–50%
    - 反对：no prior history of syncope, cardiac arrest, or known cardiovascular disease
- `c3` **Risperidone-induced Cardiac Dysfunction** — why: The patient's use of risperidone, which can cause cardiac dysfunction, combined with her reduced ejection fraction, may suggest a risperidone-induced cardiac dysfunction.
    - 支持：A 21-year-old woman with autism spectrum disorder (on risperidone) and intellectual disability / ejection fraction of 45–50%
    - 反对：no prior history of syncope, cardiac arrest, or known cardiovascular disease

</details>

### multistance（召回 set_strong，判分 False）

- champion：**Long QT Syndrome**　runner-up：Channelopathy　margin：
- selector 理由：The champion is chosen because it is a more specific diagnosis that accounts for the QTc of 380 ms, which is a decisive finding in the vignette.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Catecholaminergic Polymorphic Ventricular Tachycardia | strong | 0.0 | bystander ECG showed ventricular fibrillation | — |
| Long QT Syndrome | none | 0.0 | bystander ECG showed ventricular fibrillation / QTc of 380 ms / on risperidone | — |
| Hypertrophic Cardiomyopathy | none | 0.0 | ejection fraction of 45–50% | normal wall thickness |
| Autism Spectrum Disorder-related Cardiac Dysfunction | none | 0.0 | A 21-year-old woman with autism spectrum disorder / ejection fraction of 45–50% | — |
| Risperidone-induced Cardiac Dysfunction | none | 0.0 | on risperidone / ejection fraction of 45–50% | — |
| Cardiomyopathy | none | 0.0 | ejection fraction of 45–50% | — |
| Channelopathy | none | 0.0 | bystander ECG showed ventricular fibrillation / QTc of 380 ms | — |
| Metabolic disorder | none | 0.0 | witnessed collapse | — |
| Seizure disorder | none | 0.0 | witnessed collapse / comatose (GCS 3) | — |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Long QT Syndrome** — why: The patient's witnessed collapse and ventricular fibrillation, combined with a QTc of 380 ms, are unusual findings that suggest Long QT Syndrome.
    - 支持：bystander ECG showed ventricular fibrillation / QTc of 380 ms
- `stance:commit` **Hypertrophic Cardiomyopathy** — why: The patient's reduced ejection fraction is an unusual finding that could suggest Hypertrophic Cardiomyopathy, although the normal wall thickness argues against it.
    - 支持：ejection fraction of 45–50%
    - 反对：normal wall thickness
- `stance:commit` **Catecholaminergic Polymorphic Ventricular Tachycardia** — why: The patient's ventricular fibrillation, particularly in the context of a noisy environment, is an unusual finding that could suggest Catecholaminergic Polymorphic Ventricular Tachycardia.
    - 支持：bystander ECG showed ventricular fibrillation
- `stance:commit` **Autism Spectrum Disorder-related Cardiac Dysfunction** — why: The patient's autism spectrum disorder and reduced ejection fraction are unusual findings that could suggest a cardiac dysfunction related to her ASD.
    - 支持：A 21-year-old woman with autism spectrum disorder / ejection fraction of 45–50%
- `stance:commit` **Risperidone-induced Cardiac Dysfunction** — why: The patient's use of risperidone and reduced ejection fraction are unusual findings that could suggest a cardiac dysfunction induced by the medication.
    - 支持：on risperidone / ejection fraction of 45–50%
- `stance:coverage` **Cardiomyopathy** — why: reduced ejection fraction suggests cardiomyopathy
    - 支持：ejection fraction of 45–50%
- `stance:coverage` **Channelopathy** — why: abnormal ECG findings and ventricular fibrillation suggest channelopathy
    - 支持：bystander ECG showed ventricular fibrillation / QTc of 380 ms
- `stance:coverage` **Metabolic disorder** — why: sudden collapse could be due to underlying metabolic disorder
    - 支持：witnessed collapse
- `stance:coverage` **Seizure disorder** — why: sudden collapse and coma could be due to seizure disorder
    - 支持：witnessed collapse / comatose (GCS 3)
- `stance:mechanism` **Long QT Syndrome** — why: Prolonged QT interval can lead to ventricular fibrillation, and risperidone is a known risk factor for QT prolongation.
    - 支持：QTc of 380 ms / on risperidone
- `stance:mechanism` **Hypertrophic Cardiomyopathy** — why: Reduced ejection fraction can be a sign of hypertrophic cardiomyopathy, but normal wall thickness is not typical.
    - 支持：ejection fraction of 45–50%
    - 反对：normal wall thickness
- `stance:mechanism` **Catecholaminergic Polymorphic Ventricular Tachycardia** — why: Ventricular fibrillation can be a manifestation of CPVT, which is often triggered by emotional or physical stress.
    - 支持：bystander ECG showed ventricular fibrillation
- `stance:mechanism` **Autism Spectrum Disorder-related Cardiac Dysfunction** — why: Individuals with autism spectrum disorder may be at increased risk for cardiac dysfunction, which can manifest as ventricular fibrillation.
    - 支持：A 21-year-old woman with autism spectrum disorder

</details>

### impc（召回 set_strong，判分 False）

- champion：**Long QT Syndrome**　runner-up：Arrhythmogenic Right Ventricular Cardiomyopathy　margin：medium
- selector 理由：QTc of 380 ms and interpolated premature ventricular complexes support Long QT Syndrome, with no strong contradictions

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Catecholaminergic polymorphic ventricular tachycardia | strong | 2.0 | D2E004 / D2E005 | — |
| Hypertrophic Cardiomyopathy | none | 1.1 | D1E001 / D3E008 | D3E009 |
| Long QT Syndrome | none | 3.7 | D1E002 / D2E005 / D2E007 | — |
| Arrhythmogenic Right Ventricular Cardiomyopathy | weak | 3.35 | D1E003 / D3E010 / D3E011 | — |
| Brugada syndrome | none | 0.75 | D2E004 / D2E005 | D2E006 |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Hypertrophic Cardiomyopathy** — why: The patient's presentation with ventricular fibrillation and a family history that may imply a genetic component, along with the mention of hypertrophic cardiomyopathy in the differential diagnosis, makes it a strong candidate.
    - 支持：her differential diagnosis included channelopathies, hypertrophic cardiomyopathy, and metabolic abnormalities
- `D1` **Long QT Syndrome** — why: The patient's QTc interval of 380 ms is slightly prolonged, which could suggest Long QT Syndrome, a condition known to cause ventricular fibrillation.
    - 支持：Initial electrocardiogram revealed sinus rhythm with interpolated premature ventricular complexes and a QTc of
- `D1` **Arrhythmogenic Right Ventricular Cardiomyopathy** — why: The reduced ejection fraction and the context of ventricular fibrillation could point towards Arrhythmogenic Right Ventricular Cardiomyopathy, although more specific diagnostic criteria are needed for a definitive diagnosis.
    - 支持：Transthoracic echocardiography demonstrated an ejection fraction of 45–50%
- `D2` **Brugada syndrome** — why: The patient's witnessed collapse and ventricular fibrillation, along with the consideration of channelopathies in the differential diagnosis, suggest Brugada syndrome, although the initial electrocardiogram did not show a Brugada pattern.
    - 支持：bystander ECG showed ventricular fibrillation / differential diagnosis included channelopathies
    - 反对：Initial electrocardiogram revealed sinus rhythm with interpolated premature ventricular complexes and a QTc of
- `D2` **Catecholaminergic polymorphic ventricular tachycardia** — why: The patient's ventricular fibrillation and the consideration of channelopathies in the differential diagnosis suggest catecholaminergic polymorphic ventricular tachycardia.
    - 支持：bystander ECG showed ventricular fibrillation / differential diagnosis included channelopathies
- `D2` **Long QT syndrome** — why: The patient's QTc of 380 ms and the consideration of channelopathies in the differential diagnosis suggest long QT syndrome.
    - 支持：differential diagnosis included channelopathies / QTc of 380 ms
- `D3` **Long QT Syndrome** — why: The patient's QTc interval is prolonged at 380 ms, which is a key diagnostic criterion for Long QT Syndrome.
    - 支持：QTc of 380 ms
- `D3` **Hypertrophic Cardiomyopathy** — why: Although hypertrophic cardiomyopathy is included in the differential diagnosis, the normal wall thickness on echocardiography makes this less likely.
    - 支持：differential diagnosis included channelopathies, hypertrophic cardiomyopathy, and metabolic abnormalities
    - 反对：normal wall thickness
- `D3` **Arrhythmogenic Right Ventricular Cardiomyopathy** — why: The patient's presentation with ventricular fibrillation and reduced ejection fraction suggests a possible cardiomyopathic process, such as Arrhythmogenic Right Ventricular Cardiomyopathy.
    - 支持：ventricular fibrillation / ejection fraction of 45–50%

</details>

<details><summary>selector 淘汰理由</summary>

- **Hypertrophic Cardiomyopathy** — normal wall thickness contradicts diagnosis
- **Brugada syndrome** — ECG did not show Brugada pattern
- **Catecholaminergic polymorphic ventricular tachycardia** — less specific evidence and lower score

</details>

### forest（召回 champion_strong，判分 True）

- champion：**Catecholaminergic Polymorphic Ventricular Tachycardia**　runner-up：Long QT Syndrome　margin：medium
- selector 理由：The patient's presentation with ventricular fibrillation and interpolated premature ventricular complexes supports CPVT, and the normal wall thickness contradicts hypertrophic cardiomyopathy.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Catecholaminergic Polymorphic Ventricular Tachycardia | strong | 3.0 | AX_SE002 / AX_SE003 | — |
| Long QT Syndrome | none | 2.25 | AX_SE001 | — |
| Hypertrophic Cardiomyopathy | none | 1.75 | AX_SE004 / AX_ME006 | AX_SE005 |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Long QT Syndrome** — why: The patient's QTc interval is prolonged, which is a characteristic feature of Long QT Syndrome.
    - 支持：QTc of 380 ms
- `syndrome_anatomy` **Hypertrophic Cardiomyopathy** — why: Hypertrophic Cardiomyopathy is a possible diagnosis due to the patient's presentation, but normal wall thickness on echocardiography contradicts this.
    - 支持：her differential diagnosis included channelopathies, hypertrophic cardiomyopathy, and metabolic abnormalities
    - 反对：normal wall thickness
- `syndrome_anatomy` **Catecholaminergic Polymorphic Ventricular Tachycardia** — why: The patient's presentation with ventricular fibrillation and premature ventricular complexes is consistent with Catecholaminergic Polymorphic Ventricular Tachycardia.
    - 支持：ventricular fibrillation / interpolated premature ventricular complexes
- `mechanism_etiology` **Long QT Syndrome** — why: The patient's QTc interval is prolonged, which is a characteristic feature of Long QT Syndrome.
    - 支持：QTc of 380 ms
- `mechanism_etiology` **Hypertrophic Cardiomyopathy** — why: Hypertrophic Cardiomyopathy is a possible diagnosis, but the normal wall thickness on echocardiography makes it less likely.
    - 支持：her differential diagnosis included channelopathies, hypertrophic cardiomyopathy, and metabolic abnormalities
    - 反对：normal wall thickness
- `mechanism_etiology` **Catecholaminergic Polymorphic Ventricular Tachycardia** — why: The patient's presentation with ventricular fibrillation and premature ventricular complexes is consistent with Catecholaminergic Polymorphic Ventricular Tachycardia.
    - 支持：ventricular fibrillation / interpolated premature ventricular complexes
- `definitive_modality` **Long QT Syndrome** — why: Prolonged QT interval is a hallmark of Long QT Syndrome.
    - 支持：QTc of 380 ms
- `definitive_modality` **Hypertrophic Cardiomyopathy** — why: Reduced ejection fraction can be seen in Hypertrophic Cardiomyopathy, but normal wall thickness is not typical.
    - 支持：ejection fraction of 45–50%
    - 反对：normal wall thickness
- `definitive_modality` **Catecholaminergic Polymorphic Ventricular Tachycardia** — why: Ventricular fibrillation and premature ventricular complexes can be seen in Catecholaminergic Polymorphic Ventricular Tachycardia.
    - 支持：ventricular fibrillation / interpolated premature ventricular complexes

</details>

<details><summary>selector 淘汰理由</summary>

- **Hypertrophic Cardiomyopathy** — Normal wall thickness on echocardiogram contradicts this diagnosis.

</details>

---

## MCR_v1_seq100/91 — Angiosarcoma

- 家族 MCR / 层 MCR_v1_seq100 / 权重 12.5
- 指南能力：本地扩展 D2_direct_but_partial_or_general（上游三源 D1_parent_component_or_list_only）
- 纳入金标的方法：multistance；其中未选中：multistance

### vignette 全文

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

### collapse3c（召回 miss，判分 False）

- champion：**Solitary Fibrous Tumor**　runner-up：　margin：
- selector 理由：The histopathological examination and immunohistochemical studies, particularly the strong immunoreactivity for CD31, CD99, and Fli-1, most specifically support Solitary Fibrous Tumor.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Solitary Fibrous Tumor | none | 0.0 | a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage / Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1 | suggesting a cavernous angioma |
| Cavernous Angioma | none | 0.0 | suggesting a cavernous angioma | Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1 |
| Meningioma | none | 0.0 | a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage | Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1 |
| Kaposi's Sarcoma | none | 0.0 | Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature | strong immunoreactivity for CD31, CD99, and Fli-1 |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Solitary Fibrous Tumor** — why: The presence of a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage and histopathological examination demonstrating spindle cells with branching ectatic vasculature earned this slot.
    - 支持：a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage / Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1
    - 反对：suggesting a cavernous angioma
- `c3` **Cavernous Angioma** — why: The initial suggestion of a cavernous angioma based on imaging findings earned this slot, despite contradictory histopathological findings.
    - 支持：suggesting a cavernous angioma
    - 反对：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1
- `c3` **Hemangiopericytoma** — why: The histopathological findings of spindle cells with branching ectatic vasculature and strong immunoreactivity for CD31, CD99, and Fli-1 are characteristic of hemangiopericytoma.
    - 支持：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1
- `c3` **Meningioma** — why: The presence of a left tentorial extra-axial enhancing mass could suggest a meningioma, although histopathological findings do not support this diagnosis.
    - 支持：a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage
    - 反对：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1
- `c3` **Kaposi's Sarcoma** — why: The histopathological finding of spindle cells with branching ectatic vasculature could suggest Kaposi's sarcoma, although immunohistochemical findings do not support this diagnosis.
    - 支持：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature
    - 反对：strong immunoreactivity for CD31, CD99, and Fli-1

</details>

### multistance（召回 set_strong，判分 False）

- champion：**Hemangiopericytoma**　runner-up：Solitary Fibrous Tumor/Hemangiopericytoma　margin：
- selector 理由：The champion is chosen due to its strong evidence from histopathological examination and immunohistochemical studies, which specifically support Hemangiopericytoma over the other finalists.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Hemangioma | strong | 0.0 | a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage / Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1 | — |
| Kaposi's sarcoma | none | 0.0 | Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / up to 20 mitoses per ten high-power fields / strong immunoreactivity for CD31, CD99, and Fli-1 | suggesting a cavernous angioma |
| Hemangiopericytoma | none | 0.0 | a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage / Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / scattered S100-positive cells / up to 20 mitoses per ten high-power fields | suggesting a cavernous angioma |
| Solitary fibrous tumor | none | 0.0 | Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1 / scattered S100-positive cells | up to 20 mitoses per ten high-power fields |
| Meningioma | none | 0.0 | a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage / scattered S100-positive cells / Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature | Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / up to 20 mitoses per ten high-power fields |
| Cavernous angioma | none | 0.0 | suggesting a cavernous angioma | up to 20 mitoses per ten high-power fields / strong immunoreactivity for CD31, CD99, and Fli-1 / Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature |
| Lymphoma | none | 0.0 | complete right homonymous hemianopia / Noncontrast head CT showed a left occipital intraparenchymal hemorrhage | Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature |
| Metastasis | none | 0.0 | complete right homonymous hemianopia / Noncontrast head CT showed a left occipital intraparenchymal hemorrhage | Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature |
| Solitary Fibrous Tumor/Hemangiopericytoma | none | 0.0 | — | — |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Kaposi's sarcoma** — why: The presence of spindle cells with branching ectatic vasculature and high mitotic activity is unusual for a cavernous angioma and points towards Kaposi's sarcoma.
    - 支持：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / up to 20 mitoses per ten high-power fields / strong immunoreactivity for CD31, CD99, and Fli-1
    - 反对：suggesting a cavernous angioma
- `stance:commit` **Hemangiopericytoma** — why: The combination of an extra-axial enhancing mass and spindle cell histology with branching vasculature is unusual and points towards Hemangiopericytoma.
    - 支持：a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage / Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / scattered S100-positive cells
    - 反对：suggesting a cavernous angioma
- `stance:commit` **Solitary fibrous tumor** — why: The presence of spindle cells with branching vasculature and immunoreactivity for CD31, CD99, and Fli-1 is unusual and points towards Solitary fibrous tumor.
    - 支持：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1 / scattered S100-positive cells
    - 反对：up to 20 mitoses per ten high-power fields
- `stance:commit` **Meningioma** — why: The presence of an extra-axial enhancing mass and S100-positive cells is unusual and points towards Meningioma.
    - 支持：a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage / scattered S100-positive cells
    - 反对：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature
- `stance:commit` **Cavernous angioma** — why: The initial suggestion of a cavernous angioma based on imaging is unusual given the subsequent histological findings.
    - 支持：suggesting a cavernous angioma
    - 反对：up to 20 mitoses per ten high-power fields / strong immunoreactivity for CD31, CD99, and Fli-1
- `stance:coverage` **Hemangioma** — why: The patient's history of intracerebral hematoma and the presence of a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage suggest a vascular tumor such as hemangioma.
    - 支持：a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage / Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1
- `stance:coverage` **Meningioma** — why: The presence of a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage could suggest a meningeal tumor such as meningioma, although the high mitotic rate is atypical.
    - 支持：a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage / Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature
    - 反对：up to 20 mitoses per ten high-power fields
- `stance:coverage` **Lymphoma** — why: The patient's presentation with worsening headaches and visual field defect could suggest a CNS lymphoma, although the histopathological findings do not support this diagnosis.
    - 支持：complete right homonymous hemianopia / Noncontrast head CT showed a left occipital intraparenchymal hemorrhage
    - 反对：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature
- `stance:coverage` **Metastasis** — why: The patient's presentation with worsening headaches and visual field defect could suggest a brain metastasis, although the histopathological findings do not support this diagnosis.
    - 支持：complete right homonymous hemianopia / Noncontrast head CT showed a left occipital intraparenchymal hemorrhage
    - 反对：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature
- `stance:mechanism` **Hemangiopericytoma** — why: The combination of histopathological findings, including spindle cells, branching ectatic vasculature, and high mitotic activity, along with specific immunohistochemical staining patterns, suggests a diagnosis of Hemangiopericytoma, a rare vascular tumor.
    - 支持：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / up to 20 mitoses per ten high-power fields / strong immunoreactivity for CD31, CD99, and Fli-1
- `stance:mechanism` **Cavernous Angioma** — why: The initial suggestion of a cavernous angioma based on imaging findings is not supported by the histopathological examination, which reveals features more consistent with a different diagnosis.
    - 支持：suggesting a cavernous angioma
    - 反对：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature
- `stance:mechanism` **Solitary Fibrous Tumor** — why: The presence of spindle cells and specific immunohistochemical staining patterns could suggest a Solitary Fibrous Tumor, but the high mitotic activity is not typical for this diagnosis.
    - 支持：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1
    - 反对：up to 20 mitoses per ten high-power fields
- `stance:mechanism` **Meningioma** — why: The imaging findings of an extra-axial enhancing mass could suggest a Meningioma, but the histopathological examination reveals features not consistent with this diagnosis.
    - 支持：a left tentorial extra-axial enhancing mass with adjacent parenchymal hemorrhage
    - 反对：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature

</details>

### impc（召回 miss，判分 False）

- champion：**Hemangiopericytoma**　runner-up：Solitary Fibrous Tumor　margin：high
- selector 理由：Strong immunoreactivity for CD31, CD99, and Fli-1, and histopathological findings of spindle cells with branching ectatic vasculature support Hemangiopericytoma

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Hemangiopericytoma | none | 4.7 | D1E001 / D1E002 / D2E003 / D2E004 | — |
| Solitary Fibrous Tumor | none | 2.35 | D2E003 / D2E004 | — |
| Cavernous Angioma | none | 0.09999999999999998 | D2E005 | D3E006 |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Hemangiopericytoma** — why: The patient's histopathological examination and immunohistochemical studies are consistent with the diagnosis of Hemangiopericytoma.
    - 支持：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature, fo / Immunohistochemical studies showed strong immunoreactivity for CD31, CD99, and Fli-1, with scattered S100-posi
- `D2` **Hemangiopericytoma** — why: The patient's histopathological examination and immunohistochemical studies are consistent with Hemangiopericytoma.
    - 支持：spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1
- `D2` **Solitary Fibrous Tumor** — why: The patient's histopathological examination and immunohistochemical studies are also consistent with Solitary Fibrous Tumor.
    - 支持：spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1
- `D2` **Cavernous Angioma** — why: The patient's MRI findings are suggestive of Cavernous Angioma.
    - 支持：Contrast-enhanced brain MRI revealed a left tentorial extra-axial enhancing mass with adjacent parenchymal hem
- `D3` **Hemangiopericytoma** — why: The patient's histopathological examination and immunohistochemical studies are consistent with Hemangiopericytoma.
    - 支持：spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1
- `D3` **Solitary Fibrous Tumor** — why: The patient's histopathological examination and immunohistochemical studies are also consistent with Solitary Fibrous Tumor.
    - 支持：spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1
- `D3` **Cavernous Angioma** — why: The initial MRI suggested Cavernous Angioma, but the histopathological examination does not support this diagnosis.
    - 支持：Contrast-enhanced brain MRI revealed a left tentorial extra-axial enhancing mass with adjacent parenchymal hem
    - 反对：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature

</details>

<details><summary>selector 淘汰理由</summary>

- **Cavernous Angioma** — Contradicted by histopathological examination demonstrating spindle cells, not characteristic of Cavernous Angioma

</details>

### forest（召回 miss，判分 False）

- champion：**Hemangiopericytoma**　runner-up：Cavernous Angioma　margin：high
- selector 理由：Histopathological examination and immunohistochemical studies support Hemangiopericytoma, with features like spindle cells, branching ectatic vasculature, and specific immunoreactivity patterns

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Hemangiopericytoma | none | 5.0 | AX_SE001 / AX_SE002 / AX_ME004 / AX_ME005 | — |
| Cavernous Angioma | none | 2.5 | AX_SE003 / AX_ME006 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Hemangiopericytoma** — why: The patient's histopathological examination and immunohistochemical studies are consistent with Hemangiopericytoma.
    - 支持：spindle cells forming masses with branching ectatic vasculature / strong immunoreactivity for CD31, CD99, and Fli-1
- `syndrome_anatomy` **Cavernous Angioma** — why: The patient's MRI findings are suggestive of Cavernous Angioma.
    - 支持：Contrast-enhanced brain MRI revealed a left tentorial extra-axial enhancing mass with adjacent parenchymal hem
- `mechanism_etiology` **Hemangiopericytoma** — why: The patient's histopathological examination and immunohistochemical studies are consistent with Hemangiopericytoma, a rare neoplastic disease.
    - 支持：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature, fo / Immunohistochemical studies showed strong immunoreactivity for CD31, CD99, and Fli-1, with scattered S100-posi
- `mechanism_etiology` **Cavernous angioma** — why: The patient's MRI suggests a cavernous angioma, a type of vascular malformation.
    - 支持：Contrast-enhanced brain MRI revealed a left tentorial extra-axial enhancing mass with adjacent parenchymal hem
- `definitive_modality` **Solitary Fibrous Tumor/Hemangiopericytoma** — why: The combination of histopathological features and immunohistochemical profile is consistent with Solitary Fibrous Tumor/Hemangiopericytoma.
    - 支持：Histopathological examination demonstrated spindle cells forming masses with branching ectatic vasculature, fo / Immunohistochemical studies showed strong immunoreactivity for CD31, CD99, and Fli-1, with scattered S100-posi

</details>

<details><summary>selector 淘汰理由</summary>

- **Cavernous Angioma** — While MRI suggested Cavernous Angioma, histopathological findings and immunohistochemical studies more strongly support Hemangiopericytoma

</details>

---

## MCR_v2_seq100/146 — Diffuse large B cell lymphoma

- 家族 MCR / 层 MCR_v2_seq100 / 权重 12.5
- 指南能力：本地扩展 D3_direct_vignette_matched（上游三源 D2_direct_but_partial_or_general）
- 纳入金标的方法：multistance；其中未选中：multistance

### vignette 全文

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

### collapse3c（召回 miss，判分 False）

- champion：**Intestinal Tuberculosis**　runner-up：Crohn's Disease　margin：
- selector 理由：QuantiFERON-TB Gold was positive, which is specific evidence for Intestinal Tuberculosis.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Intestinal Tuberculosis | none | 0.0 | distal ileitis / a fecal calprotectin of 94 μg/mg / QuantiFERON-TB Gold was positive | he denied hematochezia, diarrhea, or fevers |
| Crohn's Disease | none | 0.0 | distal ileitis / a fecal calprotectin of 94 μg/mg / Stool studies were negative for enteric pathogens | QuantiFERON-TB Gold was positive |
| Helminthic Infection | none | 0.0 | a 2-month history of postprandial abdominal pain / nausea, night sweats, early satiety, and a 10-kg weight loss | — |
| Intestinal Lymphoma | weak | 0.0 | an erythrocyte sedimentation rate of 42 mm/hr / a C-reactive protein level of 35 mg/L | no abdominal tenderness or palpable masses, and no evidence of perianal disease |
| Ileocecal Histoplasmosis | none | 0.0 | distal ileitis / a fecal calprotectin of 94 μg/mg | QuantiFERON-TB Gold was positive |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Intestinal Tuberculosis** — why: The patient's positive QuantiFERON-TB Gold test and persistent distal ileitis despite antibiotic treatment suggest intestinal tuberculosis.
    - 支持：distal ileitis / a fecal calprotectin of 94 μg/mg / QuantiFERON-TB Gold was positive
    - 反对：he denied hematochezia, diarrhea, or fevers
- `c3` **Crohn's Disease** — why: The patient's persistent distal ileitis, elevated fecal calprotectin, and negative stool studies for enteric pathogens are consistent with Crohn's disease.
    - 支持：distal ileitis / a fecal calprotectin of 94 μg/mg / Stool studies were negative for enteric pathogens
    - 反对：QuantiFERON-TB Gold was positive
- `c3` **Helminthic Infection** — why: The patient's recent history of helminthic infection and persistent gastrointestinal symptoms suggest a possible helminthic infection.
    - 支持：a 2-month history of postprandial abdominal pain / nausea, night sweats, early satiety, and a 10-kg weight loss
    - 反对：he had recently treated helminth infection
- `c3` **Intestinal Lymphoma** — why: The patient's elevated inflammatory markers and persistent gastrointestinal symptoms suggest a possible intestinal lymphoma.
    - 支持：an erythrocyte sedimentation rate of 42 mm/hr / a C-reactive protein level of 35 mg/L
    - 反对：no abdominal tenderness or palpable masses, and no evidence of perianal disease
- `c3` **Ileocecal Histoplasmosis** — why: The patient's persistent distal ileitis and elevated fecal calprotectin, combined with his travel history to Honduras, suggest a possible ileocecal histoplasmosis.
    - 支持：distal ileitis / a fecal calprotectin of 94 μg/mg
    - 反对：QuantiFERON-TB Gold was positive

</details>

### multistance（召回 set_near，判分 False）

- champion：**Intestinal Tuberculosis**　runner-up：Inflammatory bowel disease　margin：
- selector 理由：The positive QuantiFERON-TB Gold and the lack of response to antibiotics for the distal ileitis make Intestinal Tuberculosis the most likely diagnosis.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Intestinal Tuberculosis | none | 0.0 | QuantiFERON-TB Gold was positive | he denied hematochezia, diarrhea, or fevers / he was started on isoniazid for latent tuberculosis |
| Crohn's Disease | none | 0.0 | abdominal and pelvic CT scan had shown distal ileitis / fecal calprotectin of 94 μg/mg / a 2-month history of postprandial abdominal pain / no abdominal tenderness or palpable masses, and no evidence of perianal disease | QuantiFERON-TB Gold was positive / he denied hematochezia, diarrhea, or fevers |
| Helminthic Infection | none | 0.0 | nausea, night sweats, early satiety, and a 10-kg weight loss / he denied hematochezia, diarrhea, or fevers / recently treated helminth infection | recently treated helminth infection / stool studies were negative for enteric pathogens |
| Intestinal Lymphoma | weak | 0.0 | erythrocyte sedimentation rate of 42 mm/hr / C-reactive protein level of 35 mg/L | no abdominal tenderness or palpable masses, and no evidence of perianal disease |
| Diverticulitis | none | 0.0 | abdominal and pelvic CT scan had shown distal ileitis / no abdominal tenderness or palpable masses, and no evidence of perianal disease | — |
| Inflammatory bowel disease | none | 0.0 | abdominal and pelvic CT scan had shown distal ileitis / erythrocyte sedimentation rate of 42 mm/hr / C-reactive protein level of 35 mg/L / fecal calprotectin of 94 μg/mg | — |
| Tuberculosis | none | 0.0 | QuantiFERON-TB Gold was positive | — |
| Gastrointestinal lymphoma | weak | 0.0 | nausea, night sweats, early satiety, and a 10-kg weight loss | — |
| Ischemic colitis | none | 0.0 | patchy loss of vascularity throughout the colon | no abdominal tenderness or palpable masses, and no evidence of perianal disease |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Intestinal Tuberculosis** — why: The patient's positive QuantiFERON-TB Gold test and nontraversable distal ileal stricture are unusual findings that suggest intestinal tuberculosis.
    - 支持：QuantiFERON-TB Gold was positive / ileocolonoscopy revealed a nontraversable distal ileal stricture, cecal ulcers, and patchy loss of vascularity
    - 反对：he denied hematochezia, diarrhea, or fevers
- `stance:commit` **Crohn's Disease** — why: The patient's distal ileitis, elevated fecal calprotectin, and nontraversable distal ileal stricture are findings that could suggest Crohn's disease.
    - 支持：abdominal and pelvic CT scan had shown distal ileitis / fecal calprotectin of 94 μg/mg / ileocolonoscopy revealed a nontraversable distal ileal stricture, cecal ulcers, and patchy loss of vascularity
    - 反对：QuantiFERON-TB Gold was positive
- `stance:commit` **Helminthic Infection** — why: The patient's recent travel history and symptoms such as nausea and weight loss could suggest a helminthic infection, despite recent treatment.
    - 支持：nausea, night sweats, early satiety, and a 10-kg weight loss / he denied hematochezia, diarrhea, or fevers
    - 反对：recently treated helminth infection
- `stance:commit` **Intestinal Lymphoma** — why: The patient's elevated inflammatory markers and nontraversable distal ileal stricture could suggest intestinal lymphoma.
    - 支持：erythrocyte sedimentation rate of 42 mm/hr / C-reactive protein level of 35 mg/L / ileocolonoscopy revealed a nontraversable distal ileal stricture, cecal ulcers, and patchy loss of vascularity
    - 反对：no abdominal tenderness or palpable masses, and no evidence of perianal disease
- `stance:commit` **Diverticulitis** — why: The patient's distal ileitis and lack of abdominal tenderness could suggest diverticulitis, although the ileocolonoscopy findings argue against this diagnosis.
    - 支持：abdominal and pelvic CT scan had shown distal ileitis / no abdominal tenderness or palpable masses, and no evidence of perianal disease
    - 反对：ileocolonoscopy revealed a nontraversable distal ileal stricture, cecal ulcers, and patchy loss of vascularity
- `stance:coverage` **Inflammatory bowel disease** — why: The patient's symptoms and laboratory results, including elevated inflammatory markers and fecal calprotectin, are consistent with inflammatory bowel disease.
    - 支持：abdominal and pelvic CT scan had shown distal ileitis / erythrocyte sedimentation rate of 42 mm/hr / C-reactive protein level of 35 mg/L / fecal calprotectin of 94 μg/mg
- `stance:coverage` **Tuberculosis** — why: The positive QuantiFERON-TB Gold test suggests that the patient may have latent tuberculosis, which could be contributing to his symptoms.
    - 支持：QuantiFERON-TB Gold was positive
- `stance:coverage` **Helminth infection** — why: The patient's recent history of helminth infection could be relevant to his current symptoms, and it is possible that the infection was not fully treated.
    - 支持：recently treated helminth infection
- `stance:coverage` **Gastrointestinal lymphoma** — why: The patient's symptoms and endoscopic findings, including a nontraversable distal ileal stricture and cecal ulcers, could be consistent with gastrointestinal lymphoma.
    - 支持：nausea, night sweats, early satiety, and a 10-kg weight loss / ileocolonoscopy revealed a nontraversable distal ileal stricture, cecal ulcers, and patchy loss of vascularity
- `stance:mechanism` **Crohn's disease** — why: Chronic inflammation and stricture formation in the distal ileum, consistent with Crohn's disease, could explain the patient's symptoms and findings.
    - 支持：a 2-month history of postprandial abdominal pain / no abdominal tenderness or palpable masses, and no evidence of perianal disease / ileocolonoscopy revealed a nontraversable distal ileal stricture, cecal ulcers, and patchy loss of vascularity
    - 反对：he denied hematochezia, diarrhea, or fevers
- `stance:mechanism` **Intestinal tuberculosis** — why: The positive QuantiFERON-TB Gold test and ileocolonoscopy findings suggest intestinal tuberculosis, which could cause the patient's symptoms and findings.
    - 支持：QuantiFERON-TB Gold was positive / ileocolonoscopy revealed a nontraversable distal ileal stricture, cecal ulcers, and patchy loss of vascularity
    - 反对：he was started on isoniazid for latent tuberculosis
- `stance:mechanism` **Helminthic infection** — why: The patient's recent helminth infection could be related to the current symptoms and findings, possibly due to a persistent or recurrent infection.
    - 支持：recently treated helminth infection
    - 反对：stool studies were negative for enteric pathogens
- `stance:mechanism` **Ischemic colitis** — why: The patchy loss of vascularity throughout the colon suggests ischemic colitis, which could cause the patient's symptoms and findings.
    - 支持：patchy loss of vascularity throughout the colon
    - 反对：no abdominal tenderness or palpable masses, and no evidence of perianal disease

</details>

### impc（召回 miss，判分 False）

- champion：**Tuberculosis**　runner-up：Crohn's disease　margin：high
- selector 理由：QuantiFERON-TB Gold was positive and the patient has distal ileitis and a nontraversable distal ileal stricture, which are consistent with Tuberculosis

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Crohn's disease | none | 4.7 | D1E001 / D1E002 / D1E003 / D1E004 | — |
| Tuberculosis | none | 5.7 | D1E005 / D1E001 / D1E002 / D2E006 | — |
| Helminthic infection | none | -0.25 | D2E008 | D2E009 |
| Helminth infection | none | -0.25 | D2E008 | D2E009 |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Crohn's disease** — why: The patient's symptoms and findings are consistent with Crohn's disease, including distal ileitis, strictures, and ulcers.
    - 支持：distal ileitis / nontraversable distal ileal stricture / cecal ulcers / patchy loss of vascularity throughout the colon
- `D1` **Tuberculosis** — why: The positive QuantiFERON-TB Gold test suggests latent tuberculosis, which could be contributing to the patient's symptoms and findings.
    - 支持：QuantiFERON-TB Gold was positive
- `D1` **Intestinal tuberculosis** — why: The combination of distal ileitis, strictures, and a positive QuantiFERON-TB Gold test suggests intestinal tuberculosis as a possible diagnosis.
    - 支持：distal ileitis / nontraversable distal ileal stricture / QuantiFERON-TB Gold was positive
- `D2` **Crohn's disease** — why: The patient's symptoms and findings, including distal ileitis, stricture, and ulcers, are consistent with Crohn's disease.
    - 支持：distal ileitis / nontraversable distal ileal stricture / cecal ulcers / patchy loss of vascularity throughout the colon
- `D2` **Intestinal tuberculosis** — why: The positive QuantiFERON-TB Gold test and symptoms such as night sweats and weight loss suggest intestinal tuberculosis.
    - 支持：QuantiFERON-TB Gold was positive / night sweats / weight loss
- `D2` **Helminthic infection** — why: The patient's recent history of helminthic infection could be related to his current symptoms, although stool studies were negative.
    - 支持：recently treated helminth infection
    - 反对：Stool studies were negative for enteric pathogens
- `D3` **Crohn's disease** — why: The patient's symptoms and findings are consistent with Crohn's disease, including distal ileitis, stricture, and ulcers.
    - 支持：distal ileitis / nontraversable distal ileal stricture / cecal ulcers / patchy loss of vascularity throughout the colon
- `D3` **Intestinal tuberculosis** — why: The positive QuantiFERON-TB Gold and the patient's symptoms and findings are consistent with intestinal tuberculosis.
    - 支持：QuantiFERON-TB Gold was positive / distal ileitis / nontraversable distal ileal stricture
- `D3` **Helminth infection** — why: The patient's recent history of helminth infection could be related to his current symptoms, although stool studies were negative.
    - 支持：recently treated helminth infection
    - 反对：Stool studies were negative for enteric pathogens

</details>

<details><summary>selector 淘汰理由</summary>

- **Helminth infection** — Stool studies were negative for enteric pathogens and the patient was recently treated for helminth infection
- **Helminthic infection** — Stool studies were negative for enteric pathogens and the patient was recently treated for helminth infection

</details>

### forest（召回 miss，判分 False）

- champion：**Intestinal tuberculosis**　runner-up：Crohn's disease　margin：medium
- selector 理由：QuantiFERON-TB Gold was positive and the patient has distal ileitis and a nontraversable distal ileal stricture, which are more specific findings for intestinal tuberculosis

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Crohn's disease | none | 5.0 | AX_SE001 / AX_SE002 / AX_SE003 / AX_SE005 | — |
| Intestinal tuberculosis | none | 5.0 | AX_SE004 / AX_SE001 / AX_SE002 / AX_ME008 | — |
| Helminthic infection | none | -0.25 | AX_SE006 | AX_SE007 |
| Helminth infection | none | 1.5 | AX_SE006 | — |
| Latent tuberculosis | none | 1.5 | AX_SE004 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Crohn's disease** — why: The patient's symptoms and findings are consistent with Crohn's disease, including distal ileitis, stricture, and skip lesions.
    - 支持：distal ileitis / nontraversable distal ileal stricture / cecal ulcers / patchy loss of vascularity throughout the colon
- `syndrome_anatomy` **Intestinal tuberculosis** — why: The patient's positive QuantiFERON-TB Gold test and symptoms suggest intestinal tuberculosis.
    - 支持：QuantiFERON-TB Gold was positive / distal ileitis / nontraversable distal ileal stricture
- `syndrome_anatomy` **Helminthic infection** — why: The patient's recent helminth infection could be contributing to his symptoms, although stool studies were negative.
    - 支持：recently treated helminth infection
    - 反对：Stool studies were negative for enteric pathogens
- `mechanism_etiology` **Crohn's disease** — why: The patient's symptoms and findings are consistent with Crohn's disease, a type of inflammatory bowel disease.
    - 支持：distal ileitis / nontraversable distal ileal stricture / cecal ulcers / patchy loss of vascularity throughout the colon
- `mechanism_etiology` **Intestinal tuberculosis** — why: The patient's positive QuantiFERON-TB Gold test and symptoms suggest intestinal tuberculosis.
    - 支持：QuantiFERON-TB Gold was positive / distal ileitis / nontraversable distal ileal stricture
- `mechanism_etiology` **Helminth infection** — why: The patient's recent history of helminth infection could be related to his current symptoms.
    - 支持：recently treated helminth infection
- `mechanism_etiology` **Latent tuberculosis** — why: The patient's positive QuantiFERON-TB Gold test indicates latent tuberculosis.
    - 支持：QuantiFERON-TB Gold was positive
- `definitive_modality` **Crohn's disease** — why: The patient's symptoms and findings on CT scan and ileocolonoscopy are consistent with Crohn's disease.
    - 支持：distal ileitis / nontraversable distal ileal stricture / cecal ulcers / patchy loss of vascularity throughout the colon
- `definitive_modality` **Intestinal tuberculosis** — why: The positive QuantiFERON-TB Gold test and persistent distal ileitis suggest intestinal tuberculosis.
    - 支持：QuantiFERON-TB Gold was positive / persistent distal ileitis
- `definitive_modality` **Helminth infection** — why: The patient's recent history of helminth infection could be related to his current symptoms.
    - 支持：recently treated helminth infection
- `definitive_modality` **Latent tuberculosis** — why: The positive QuantiFERON-TB Gold test indicates latent tuberculosis.
    - 支持：QuantiFERON-TB Gold was positive

</details>

<details><summary>selector 淘汰理由</summary>

- **Helminth infection** — recently treated and stool studies were negative
- **Latent tuberculosis** — not as specific as intestinal tuberculosis for the patient's symptoms and findings
- **Helminthic infection** — similar to helminth infection, recently treated and stool studies were negative

</details>

---

## MCR_v2_seq100/179 — hypoxia-induced thrombocytopenia

- 家族 MCR / 层 MCR_v2_seq100 / 权重 12.5
- 指南能力：本地扩展 D1_parent_component_or_list_only（上游三源 D1_parent_component_or_list_only）
- 纳入金标的方法：multistance, impc, forest；其中未选中：multistance, impc, forest

### vignette 全文

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

### collapse3c（召回 miss，判分 False）

- champion：**Tetralogy of Fallot with pulmonary atresia**　runner-up：　margin：
- selector 理由：The evidence of pulmonary atresia with ventricular septal defect and a patent ductus arteriosus specifically supports Tetralogy of Fallot with pulmonary atresia.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Tetralogy of Fallot with pulmonary atresia | none | 0.0 | pulmonary atresia with ventricular septal defect and a patent ductus arteriosus | — |
| Congenital thrombocytopenia | weak | 0.0 | platelet aggregation time was 127 s | a provisional diagnosis of immune thrombocytopenia |
| Alagille syndrome | none | 0.0 | pulmonary atresia with ventricular septal defect and a patent ductus arteriosus | — |
| Jacobsen syndrome | none | 0.0 | platelet aggregation time was 127 s | — |
| Thrombocytopenia-absent radius syndrome | weak | 0.0 | — | — |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Tetralogy of Fallot with pulmonary atresia** — why: The presence of pulmonary atresia with ventricular septal defect and a patent ductus arteriosus is a distinctive finding that earns this slot.
    - 支持：pulmonary atresia with ventricular septal defect and a patent ductus arteriosus
- `c3` **Congenital thrombocytopenia** — why: The persistent thrombocytopenia and abnormal platelet aggregation time are unusual findings that suggest a congenital cause.
    - 支持：platelet count 68 000/mm3 / platelet aggregation time was 127 s
    - 反对：a provisional diagnosis of immune thrombocytopenia
- `c3` **Alagille syndrome** — why: The combination of congenital heart disease and thrombocytopenia is a distinctive finding that suggests Alagille syndrome.
    - 支持：pulmonary atresia with ventricular septal defect and a patent ductus arteriosus / platelet count 68 000/mm3
- `c3` **Jacobsen syndrome** — why: The thrombocytopenia and abnormal platelet function are unusual findings that suggest Jacobsen syndrome.
    - 支持：platelet count 68 000/mm3 / platelet aggregation time was 127 s
- `c3` **Thrombocytopenia-absent radius syndrome** — why: The thrombocytopenia is a distinctive finding that suggests TAR syndrome, although the absence of radial aplasia is not mentioned.
    - 支持：platelet count 68 000/mm3

</details>

### multistance（召回 set_strong，判分 False）

- champion：**Tetralogy of Fallot with pulmonary atresia**　runner-up：Congenital heart disease　margin：
- selector 理由：The champion is chosen because it specifically accounts for the combination of pulmonary atresia and ventricular septal defect, which is directly supported by the echocardiography findings.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Thrombocytopenia | strong | 0.0 | platelet count of 103 000/mm3 / platelet count 173 000/mm3 / platelet aggregation time was 127 s / platelet count then increased without transfusion | — |
| Tetralogy of Fallot with pulmonary atresia | none | 0.0 | Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus | — |
| Immune thrombocytopenia | weak | 0.0 | a provisional diagnosis of immune thrombocytopenia / platelet aggregation time was 127 s | platelet count then increased without transfusion |
| Postoperative thrombocytosis | weak | 0.0 | platelet count then increased without transfusion | — |
| Cyanotic congenital heart disease | none | 0.0 | oxygen saturation (SaO2) was 80% in room air / Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus | — |
| Pulmonary atresia with ventricular septal defect | none | 0.0 | Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus | — |
| Congenital heart disease | none | 0.0 | Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus | — |
| Bleeding disorder | none | 0.0 | platelet aggregation time was 127 s | Prothrombin time, activated partial thromboplastin time, and INR were normal |
| Pulmonary Atresia | none | 0.0 | Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus | SaO2 was 80% in room air |
| Ventricular Septal Defect | none | 0.0 | Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus | SaO2 was 80% in room air |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Tetralogy of Fallot with pulmonary atresia** — why: The presence of pulmonary atresia with ventricular septal defect and a patent ductus arteriosus is a distinctive finding that earns this slot.
    - 支持：Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus
- `stance:commit` **Immune thrombocytopenia** — why: The prolonged platelet aggregation time and provisional diagnosis of immune thrombocytopenia are unusual findings that argue for this candidate.
    - 支持：a provisional diagnosis of immune thrombocytopenia / platelet aggregation time was 127 s
    - 反对：platelet count then increased without transfusion
- `stance:commit` **Postoperative thrombocytosis** — why: The increase in platelet count without transfusion is an unusual finding that earns this slot.
    - 支持：platelet count then increased without transfusion
- `stance:commit` **Cyanotic congenital heart disease** — why: The presence of cyanosis and low oxygen saturation is a distinctive finding that argues for this candidate.
    - 支持：oxygen saturation (SaO2) was 80% in room air
- `stance:commit` **Pulmonary atresia with ventricular septal defect** — why: The presence of pulmonary atresia with ventricular septal defect is a distinctive finding that earns this slot.
    - 支持：Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus
- `stance:coverage` **Congenital heart disease** — why: The patient's echocardiography results indicate a complex congenital heart defect, which cannot be skipped in the differential diagnosis.
    - 支持：Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus
- `stance:coverage` **Thrombocytopenia** — why: The patient's laboratory results show a low platelet count and abnormal platelet aggregation time, which are indicative of thrombocytopenia.
    - 支持：platelet count of 103 000/mm3 / platelet count 173 000/mm3 / platelet aggregation time was 127 s
- `stance:coverage` **Cyanotic heart disease** — why: The patient's low oxygen saturation and echocardiography results indicate cyanotic heart disease, which is a critical diagnosis to consider.
    - 支持：oxygen saturation (SaO2) was 80% in room air / Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus
- `stance:coverage` **Bleeding disorder** — why: The patient's abnormal platelet aggregation time suggests a possible bleeding disorder, which must be considered in the differential diagnosis.
    - 支持：platelet aggregation time was 127 s
    - 反对：Prothrombin time, activated partial thromboplastin time, and INR were normal
- `stance:mechanism` **Thrombocytopenia** — why: The patient's low platelet count and prolonged platelet aggregation time suggest a thrombocytopenia diagnosis.
    - 支持：platelet count of 103 000/mm3 / platelet count 173 000/mm3 / platelet count then increased without transfusion / platelet aggregation time was 127 s
    - 反对：hematocrit was 47.8%
- `stance:mechanism` **Pulmonary Atresia** — why: The patient's echocardiography results indicate pulmonary atresia, which is a congenital heart defect.
    - 支持：Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus
    - 反对：SaO2 was 80% in room air
- `stance:mechanism` **Ventricular Septal Defect** — why: The patient's echocardiography results indicate a ventricular septal defect, which is a congenital heart defect.
    - 支持：Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus
    - 反对：SaO2 was 80% in room air
- `stance:mechanism` **Cyanotic Congenital Heart Disease** — why: The patient's low oxygen saturation and echocardiography results indicate cyanotic congenital heart disease.
    - 支持：oxygen saturation (SaO2) was 80% in room air / Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus / SaO2 to 90–95% on prostaglandin
    - 反对：hematocrit was 47.8%

</details>

### impc（召回 set_strong，判分 False）

- champion：**Tetralogy of Fallot with pulmonary atresia**　runner-up：Cyanotic congenital heart disease　margin：high
- selector 理由：The patient's echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus, which is a specific finding that supports Tetralogy of Fallot with pulmonary atresia.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Tetralogy of Fallot with pulmonary atresia | none | 3.7 | D1E001 / D2E004 / D3E009 | — |
| Immune thrombocytopenia | weak | 5.7 | D1E002 / D2E005 / D3E006 / D3E007 | — |
| Cyanotic congenital heart disease | none | 2.35 | D1E003 / D3E009 | — |
| Ventricular Septal Defect | none | 1.0 | D2E004 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Tetralogy of Fallot with pulmonary atresia** — why: The patient's echocardiography results show pulmonary atresia with ventricular septal defect and a patent ductus arteriosus, which are characteristic of Tetralogy of Fallot with pulmonary atresia.
    - 支持：pulmonary atresia with ventricular septal defect and a patent ductus arteriosus
- `D1` **Immune thrombocytopenia** — why: The pediatrician made a provisional diagnosis of immune thrombocytopenia based on the patient's low platelet count and normal laboratory results.
    - 支持：provisional diagnosis of immune thrombocytopenia
- `D1` **Cyanotic congenital heart disease** — why: The patient presented with cyanosis and low oxygen saturation, which are characteristic of cyanotic congenital heart disease.
    - 支持：cyanosis; oxygen saturation (SaO2) was 80% in room air
- `D2` **Pulmonary Atresia** — why: The patient was diagnosed with pulmonary atresia based on echocardiography findings.
    - 支持：Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus.
- `D2` **Ventricular Septal Defect** — why: The patient was diagnosed with ventricular septal defect based on echocardiography findings.
    - 支持：Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus.
- `D2` **Immune Thrombocytopenia** — why: The pediatrician made a provisional diagnosis of immune thrombocytopenia based on the patient's low platelet count and other test results.
    - 支持：The pediatrician made a provisional diagnosis of immune thrombocytopenia and administered intravenous immunogl
- `D3` **Thrombocytopenia** — why: The patient has consistently low platelet counts throughout the vignette.
    - 支持：platelet count was 103 000/mm3 / platelet count was 58 000/mm3 / platelet count was 68 000/mm3
- `D3` **Pulmonary Atresia with Ventricular Septal Defect** — why: The patient was diagnosed with this condition via echocardiography.
    - 支持：Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus
- `D3` **Congenital Heart Disease** — why: The patient has symptoms and diagnostic findings consistent with congenital heart disease.
    - 支持：cyanosis; oxygen saturation (SaO2) was 80% in room air / Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus

</details>

<details><summary>selector 淘汰理由</summary>

- **Immune thrombocytopenia** — Although the patient had a low platelet count, the provisional diagnosis of immune thrombocytopenia was not strongly supported by other findings, and the patient's platelet count increased without transfusion after surgery.
- **Ventricular Septal Defect** — While the patient had a ventricular septal defect, this is a component of Tetralogy of Fallot with pulmonary atresia, making the more specific diagnosis the better choice.

</details>

### forest（召回 set_strong，判分 False）

- champion：**Pulmonary Atresia with Ventricular Septal Defect**　runner-up：Tetralogy of Fallot with pulmonary atresia　margin：high
- selector 理由：Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus, which directly supports the diagnosis of Pulmonary Atresia with Ventricular Septal Defect

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Tetralogy of Fallot with pulmonary atresia | none | 1.0 | AX_SE001 | — |
| Immune thrombocytopenia | weak | 5.15 | AX_SE002 / AX_ME003 / AX_ME004 / AX_ME006 | — |
| Pulmonary Atresia with Ventricular Septal Defect | none | 2.5 | AX_SE001 / AX_ME005 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Tetralogy of Fallot with pulmonary atresia** — why: The patient has cyanosis, pulmonary atresia, ventricular septal defect, and a patent ductus arteriosus, which are characteristic of Tetralogy of Fallot with pulmonary atresia.
    - 支持：pulmonary atresia with ventricular septal defect and a patent ductus arteriosus
- `syndrome_anatomy` **Immune thrombocytopenia** — why: The patient has a low platelet count, normal prothrombin time, activated partial thromboplastin time, and INR, and negative antiplatelet antibodies, which are consistent with immune thrombocytopenia.
    - 支持：provisional diagnosis of immune thrombocytopenia
- `mechanism_etiology` **Immune Thrombocytopenia** — why: The patient had a low platelet count and received intravenous immunoglobulins, which is a common treatment for immune thrombocytopenia.
    - 支持：provisional diagnosis of immune thrombocytopenia
- `mechanism_etiology` **Pulmonary Atresia with Ventricular Septal Defect** — why: The patient was diagnosed with this congenital heart defect, which is a specific disease entity.
    - 支持：pulmonary atresia with ventricular septal defect and a patent ductus arteriosus
- `mechanism_etiology` **Thrombocytopenia** — why: The patient had a low platelet count on multiple occasions, which is a characteristic of thrombocytopenia.
    - 支持：platelet count was 103 000/mm3 / platelet count was 58 000/mm3
- `definitive_modality` **Pulmonary Atresia with Ventricular Septal Defect** — why: Echocardiography findings are decisive for this diagnosis
    - 支持：Echocardiography revealed pulmonary atresia with ventricular septal defect and a patent ductus arteriosus
- `definitive_modality` **Immune Thrombocytopenia** — why: Provisional diagnosis based on low platelet count and other test results
    - 支持：The pediatrician made a provisional diagnosis of immune thrombocytopenia and administered intravenous immunogl

</details>

<details><summary>selector 淘汰理由</summary>

- **Immune thrombocytopenia** — provisional diagnosis but not the primary condition explained by the decisive findings of pulmonary atresia and ventricular septal defect

</details>

---

## MCR_v2_seq100/202 — Mantle cell lymphoma

- 家族 MCR / 层 MCR_v2_seq100 / 权重 12.5
- 指南能力：本地扩展 D2_direct_but_partial_or_general（上游三源 D1_parent_component_or_list_only）
- 纳入金标的方法：multistance；其中未选中：multistance

### vignette 全文

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

### collapse3c（召回 miss，判分 False）

- champion：**Torus Palatinus**　runner-up：Giant Cell Granuloma　margin：
- selector 理由：the presence of a firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar area with the palatal bone uninvolved decided it

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Giant Cell Granuloma | weak | 0.0 | a 10–12-week history of a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar / the palatal bone appeared uninvolved | — |
| Palatal Abscess | none | 0.0 | a 10–12-week history of a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar | the wound healed slowly over 4–5 weeks |
| Torus Palatinus | none | 0.0 | a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar / the palatal bone appeared uninvolved | a 10–12-week history of a painless swelling in the molar region of the hard palate |
| Squamous Cell Carcinoma | weak | 0.0 | a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar | denied dysphagia, odynophagia, or systemic symptoms / No cervical lymphadenopathy was detected |
| Granulomatosis with Polyangiitis | none | 0.0 | a 10–12-week history of a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar | denied dysphagia, odynophagia, or systemic symptoms / No cervical lymphadenopathy was detected |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Giant Cell Granuloma** — why: The presence of a painless swelling in the molar region of the hard palate with a firm and elastic texture, and the involvement of both sides of the palate, is unusual and points towards Giant Cell Granuloma.
    - 支持：a 10–12-week history of a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar / the palatal bone appeared uninvolved
- `c3` **Palatal Abscess** — why: The presence of a painless swelling in the molar region of the hard palate could be indicative of a palatal abscess, but the slow healing of the wound and the lack of ulceration argue against it.
    - 支持：a 10–12-week history of a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
    - 反对：the wound healed slowly over 4–5 weeks
- `c3` **Torus Palatinus** — why: The presence of a firm and elastic swelling on both sides of the hard palate, and the involvement of the palatal bone, could be indicative of Torus Palatinus, but the recent onset of symptoms argues against it.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar / the palatal bone appeared uninvolved
    - 反对：a 10–12-week history of a painless swelling in the molar region of the hard palate
- `c3` **Squamous Cell Carcinoma** — why: The presence of a firm and elastic swelling on the hard palate could be indicative of Squamous Cell Carcinoma, but the lack of symptoms and lymphadenopathy argue against it.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
    - 反对：denied dysphagia, odynophagia, or systemic symptoms / No cervical lymphadenopathy was detected
- `c3` **Granulomatosis with Polyangiitis** — why: The presence of a painless swelling in the molar region of the hard palate with a firm and elastic texture could be indicative of Granulomatosis with Polyangiitis, but the lack of systemic symptoms and lymphadenopathy argue against it.
    - 支持：a 10–12-week history of a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
    - 反对：denied dysphagia, odynophagia, or systemic symptoms / No cervical lymphadenopathy was detected

</details>

### multistance（召回 set_strong，判分 False）

- champion：**Giant Cell Granuloma**　runner-up：Granuloma　margin：
- selector 理由：Giant Cell Granuloma is the champion because it has the most specific for evidence, including the location and description of the swelling, and no against evidence.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Lymphoma | strong | 0.0 | No cervical lymphadenopathy was detected | — |
| Giant Cell Granuloma | weak | 0.0 | a 10–12-week history of a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar / the palatal bone appeared uninvolved | — |
| Palatal Abscess | none | 0.0 | a 10–12-week history of a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar | the wound healed slowly over 4–5 weeks |
| Torus Palatinus | none | 0.0 | a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar / the palatal bone appeared uninvolved | a 10–12-week history of a painless swelling in the molar region of the hard palate |
| Squamous Cell Carcinoma | weak | 0.0 | a 10–12-week history of a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar | No cervical lymphadenopathy was detected / the wound healed slowly over 4–5 weeks / he denied dysphagia, odynophagia, or systemic symptoms |
| Pyogenic Granuloma | none | 0.0 | a 10–12-week history of a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar | the palatal bone appeared uninvolved / the wound healed slowly over 4–5 weeks |
| Granuloma | none | 0.0 | a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar | — |
| Fibroma | none | 0.0 | a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar | the wound healed slowly over 4–5 weeks |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Giant Cell Granuloma** — why: The presence of a painless swelling in the molar region of the hard palate with a firm and elastic texture, and the involvement of both sides of the palate, is unusual and points towards Giant Cell Granuloma.
    - 支持：a 10–12-week history of a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar / the palatal bone appeared uninvolved
- `stance:commit` **Palatal Abscess** — why: The presence of a painless swelling in the molar region of the hard palate could be indicative of a palatal abscess, but the slow healing of the wound and the lack of ulceration argue against it.
    - 支持：a 10–12-week history of a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
    - 反对：the wound healed slowly over 4–5 weeks
- `stance:commit` **Torus Palatinus** — why: The presence of a firm and elastic swelling on both sides of the hard palate, and the involvement of the palatal bone, could be indicative of Torus Palatinus, but the recent onset of symptoms argues against it.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar / the palatal bone appeared uninvolved
    - 反对：a 10–12-week history of a painless swelling in the molar region of the hard palate
- `stance:commit` **Squamous Cell Carcinoma** — why: The presence of a painless swelling in the molar region of the hard palate could be indicative of Squamous Cell Carcinoma, but the lack of lymphadenopathy and the slow healing of the wound argue against it.
    - 支持：a 10–12-week history of a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
    - 反对：No cervical lymphadenopathy was detected / the wound healed slowly over 4–5 weeks
- `stance:commit` **Pyogenic Granuloma** — why: The presence of a painless swelling in the molar region of the hard palate could be indicative of Pyogenic Granuloma, but the involvement of the palatal bone and the lack of ulceration argue against it.
    - 支持：a 10–12-week history of a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
    - 反对：the palatal bone appeared uninvolved
- `stance:coverage` **Torus palatinus** — why: This condition is a common cause of a painless swelling in the hard palate and must be considered in the differential diagnosis.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
- `stance:coverage` **Squamous cell carcinoma** — why: This is a dangerous condition that must be excluded, as it can present with a similar swelling in the hard palate.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
    - 反对：No cervical lymphadenopathy was detected
- `stance:coverage` **Lymphoma** — why: Lymphoma can present with a swelling in the hard palate, and the absence of cervical lymphadenopathy does not rule out this condition.
    - 支持：No cervical lymphadenopathy was detected
- `stance:coverage` **Granuloma** — why: A granuloma can present with a similar swelling in the hard palate and must be considered in the differential diagnosis.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
- `stance:mechanism` **Giant Cell Granuloma** — why: This disease is a possible cause of the painless swelling in the molar region of the hard palate due to the formation of granulomatous tissue.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar / the palatal bone appeared uninvolved
- `stance:mechanism` **Pyogenic Granuloma** — why: This disease could explain the swelling, but the slow healing of the wound is not typical for pyogenic granuloma.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
    - 反对：the wound healed slowly over 4–5 weeks
- `stance:mechanism` **Squamous Cell Carcinoma** — why: This disease could explain the swelling, but the lack of symptoms and lymphadenopathy is not typical for squamous cell carcinoma.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
    - 反对：he denied dysphagia, odynophagia, or systemic symptoms / No cervical lymphadenopathy was detected
- `stance:mechanism` **Fibroma** — why: This disease could explain the swelling, but the slow healing of the wound is not typical for fibroma.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
    - 反对：the wound healed slowly over 4–5 weeks

</details>

### impc（召回 miss，判分 False）

- champion：**Torus Palatinus**　runner-up：Palatal fibroma　margin：medium
- selector 理由：The presence of a firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar area, along with the palatal bone appearing uninvolved, best supports Torus Palatinus.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Torus Palatinus | none | 2.7 | D1E001 / D1E002 | — |
| Giant Cell Lesion | weak | 1.0 | D2E003 | — |
| Palatal fibroma | none | 1.35 | D2E004 | — |
| Giant Cell Granuloma | weak | 1.0 | D2E003 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Torus Palatinus** — why: The location and description of the swelling are consistent with Torus Palatinus, a common benign bony growth on the hard palate.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar / the palatal bone appeared uninvolved
- `D2` **Torus palatinus** — why: The location and description of the swelling are consistent with Torus palatinus.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
- `D2` **Giant Cell Lesion** — why: The painless nature of the swelling could suggest a Giant Cell Lesion.
    - 支持：a painless swelling in the molar region of the hard palate
- `D2` **Palatal fibroma** — why: The firm and elastic nature of the swelling is consistent with a palatal fibroma.
    - 支持：a firm, elastic, non-ulcerated swelling
- `D3` **Torus Palatinus** — why: The location and description of the swelling are consistent with Torus Palatinus.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
- `D3` **Giant Cell Granuloma** — why: The painless nature and location of the swelling could suggest Giant Cell Granuloma.
    - 支持：a painless swelling in the molar region of the hard palate
- `D3` **Palatal Fibroma** — why: The firm and elastic nature of the swelling is consistent with Palatal Fibroma.
    - 支持：a firm, elastic, non-ulcerated swelling

</details>

<details><summary>selector 淘汰理由</summary>

- **Giant Cell Granuloma** — Lack of specific findings and lower agent votes
- **Giant Cell Lesion** — Lack of specific findings and lower agent votes

</details>

### forest（召回 miss，判分 False）

- champion：**Torus palatinus**　runner-up：Palatal Torus　margin：high
- selector 理由：The vignette describes a painless swelling in the molar region of the hard palate, which is a characteristic feature of Torus palatinus, and the presence of a firm, elastic, non-ulcerated swelling on both sides of the hard palate further supports this diagnosis.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Torus palatinus | none | 2.5 | AX_SE001 / AX_SE002 | — |
| Giant Cell Tumor | weak | 1.0 | AX_ME003 | — |
| Fibroma | none | 1.0 | AX_ME004 | — |
| Giant Cell Lesion | weak | 1.0 | AX_ME003 | — |
| Palatal Torus | none | 1.0 | AX_SE001 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Torus palatinus** — why: The location and description of the swelling are consistent with Torus palatinus.
    - 支持：a painless swelling in the molar region of the hard palate / a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling on both sides of the hard palate in the molar–premolar ar
- `mechanism_etiology` **Giant Cell Tumor** — why: The description of the swelling as firm and elastic is consistent with a Giant Cell Tumor.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling
- `mechanism_etiology` **Torus Palatinus** — why: The location and description of the swelling are consistent with Torus Palatinus.
    - 支持：a painless swelling in the molar region of the hard palate
- `mechanism_etiology` **Fibroma** — why: The description of the swelling as firm and elastic is consistent with a Fibroma.
    - 支持：a firm, elastic, non-ulcerated swelling
- `definitive_modality` **Giant Cell Lesion** — why: The description of the swelling is consistent with a Giant Cell Lesion, which is a type of benign tumor.
    - 支持：a 1.5 × 3.0 cm firm, elastic, non-ulcerated swelling
- `definitive_modality` **Palatal Torus** — why: The location and description of the swelling are consistent with a Palatal Torus, which is a bony growth.
    - 支持：a painless swelling in the molar region of the hard palate

</details>

<details><summary>selector 淘汰理由</summary>

- **Fibroma** — Lack of specific features unique to fibroma
- **Giant Cell Lesion** — No specific evidence of giant cell pathology
- **Giant Cell Tumor** — No specific evidence of giant cell tumor characteristics

</details>

---

## MCR_v2_seq100/234 — SpindleCellHemangioma

- 家族 MCR / 层 MCR_v2_seq100 / 权重 12.5
- 指南能力：本地扩展 D1_parent_component_or_list_only（上游三源 D1_parent_component_or_list_only）
- 纳入金标的方法：multistance；其中未选中：multistance

### vignette 全文

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

### collapse3c（召回 miss，判分 False）

- champion：**Aneurysmal bone cyst**　runner-up：Giant cell tumor　margin：
- selector 理由：The evidence of a lytic lesion with a soap-bubble appearance and the specific MRI findings of being hypointense on T1-weighted images, hyperintense on T2-weighted images, and showing avid enhancement on postcontrast sequences decided it.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Brown tumor of hyperparathyroidism | none | 0.0 | a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer  | — |
| Giant cell tumor | weak | 0.0 | a lytic lesion of the frontal bone with a soap-bubble appearance | — |
| Aneurysmal bone cyst | none | 0.0 | a lytic lesion of the frontal bone with a soap-bubble appearance / was hypointense on T1-weighted images, hyperintense on T2-weighted images, and showed avid enhancement on post | — |
| Fibrous dysplasia | none | 0.0 | a large, circumscribed radiolucent lesion in the right frontal bone without adjacent soft-tissue swelling | a lytic lesion of the frontal bone with a soap-bubble appearance |
| Osteomyelitis | none | 0.0 | a 2-month history of a painless mass on the right side of the frontal bone | Laboratory studies and neurologic examination were unremarkable |

<details><summary>生成器逐视角候选与理由</summary>

- `c3` **Brown tumor of hyperparathyroidism** — why: The soap-bubble appearance of the lytic lesion is unusual and points to this disease.
    - 支持：a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer 
- `c3` **Giant cell tumor** — why: The soap-bubble appearance of the lytic lesion is unusual and points to this disease, but the nonmobility of the mass argues against it.
    - 支持：a lytic lesion of the frontal bone with a soap-bubble appearance
    - 反对：was nonmobile
- `c3` **Aneurysmal bone cyst** — why: The soap-bubble appearance of the lytic lesion and the imaging characteristics are unusual and point to this disease.
    - 支持：a lytic lesion of the frontal bone with a soap-bubble appearance / was hypointense on T1-weighted images, hyperintense on T2-weighted images, and showed avid enhancement on post
- `c3` **Fibrous dysplasia** — why: The large, circumscribed radiolucent lesion is unusual and points to this disease, but the soap-bubble appearance argues against it.
    - 支持：a large, circumscribed radiolucent lesion in the right frontal bone without adjacent soft-tissue swelling
    - 反对：a lytic lesion of the frontal bone with a soap-bubble appearance
- `c3` **Osteomyelitis** — why: The painless mass is unusual and could point to this disease, but the unremarkable laboratory studies and neurologic examination argue against it.
    - 支持：a 2-month history of a painless mass on the right side of the frontal bone
    - 反对：Laboratory studies and neurologic examination were unremarkable

</details>

### multistance（召回 top2_strong，判分 False）

- champion：**Giant cell tumor**　runner-up：Hemangioma　margin：
- selector 理由：The champion, Giant cell tumor, was chosen because it has the most decisive findings in the vignette, including a lytic lesion of the frontal bone with a soap-bubble appearance and a lobulated frontal-bone mass measuring 3.7 × 3.3 × 2.8 cm, which are not fully explained by the other finalists.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Hemangioma | strong | 0.0 | a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer  / was hypointense on T1-weighted images, hyperintense on T2-weighted images, and showed avid enhancement on post | — |
| Brown tumor of hyperparathyroidism | none | 0.0 | a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer  | Laboratory studies and neurologic examination were unremarkable |
| Giant cell tumor | weak | 0.0 | a lytic lesion of the frontal bone with a soap-bubble appearance / a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer  / a lobulated frontal-bone mass measuring 3.7 × 3.3 × 2.8 cm | was well circumscribed, soft, nonmobile, and non-tender |
| Aneurysmal bone cyst | none | 0.0 | a lytic lesion of the frontal bone with a soap-bubble appearance | was well circumscribed, soft, nonmobile, and non-tender |
| Fibrous dysplasia | none | 0.0 | a large, circumscribed radiolucent lesion in the right frontal bone without adjacent soft-tissue swelling | a lytic lesion of the frontal bone with a soap-bubble appearance |
| Osteomyelitis | none | 0.0 | was hypointense on T1-weighted images, hyperintense on T2-weighted images, and showed avid enhancement on post | Laboratory studies and neurologic examination were unremarkable |
| Osteoma | none | 0.0 | a painless mass on the right side of the frontal bone / was well circumscribed, soft, nonmobile, and non-tender / a large, circumscribed radiolucent lesion in the right frontal bone without adjacent soft-tissue swelling | — |
| Metastatic bone disease | none | 0.0 | a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer  | — |
| Multiple myeloma | weak | 0.0 | a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer  | — |
| Ewing's Sarcoma | none | 0.0 | a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer  / a lobulated frontal-bone mass measuring 3.7 × 3.3 × 2.8 cm | Laboratory studies and neurologic examination were unremarkable |

<details><summary>生成器逐视角候选与理由</summary>

- `stance:commit` **Brown tumor of hyperparathyroidism** — why: The soap-bubble appearance of the lytic lesion is unusual and points to this disease.
    - 支持：a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer 
    - 反对：Laboratory studies and neurologic examination were unremarkable
- `stance:commit` **Giant cell tumor** — why: The soap-bubble appearance and lytic lesion are unusual findings that could suggest this disease.
    - 支持：a lytic lesion of the frontal bone with a soap-bubble appearance
    - 反对：was well circumscribed, soft, nonmobile, and non-tender
- `stance:commit` **Aneurysmal bone cyst** — why: The soap-bubble appearance and lytic lesion are unusual findings that could suggest this disease.
    - 支持：a lytic lesion of the frontal bone with a soap-bubble appearance
    - 反对：was well circumscribed, soft, nonmobile, and non-tender
- `stance:commit` **Fibrous dysplasia** — why: The large, circumscribed radiolucent lesion is an unusual finding that could suggest this disease.
    - 支持：a large, circumscribed radiolucent lesion in the right frontal bone without adjacent soft-tissue swelling
    - 反对：a lytic lesion of the frontal bone with a soap-bubble appearance
- `stance:commit` **Osteomyelitis** — why: The MRI findings are unusual and could suggest an infectious process.
    - 支持：was hypointense on T1-weighted images, hyperintense on T2-weighted images, and showed avid enhancement on post
    - 反对：Laboratory studies and neurologic examination were unremarkable
- `stance:coverage` **Osteoma** — why: The patient's presentation of a painless, well-circumscribed mass on the frontal bone with a radiolucent lesion on imaging suggests a possible osteoma.
    - 支持：a painless mass on the right side of the frontal bone / was well circumscribed, soft, nonmobile, and non-tender / a large, circumscribed radiolucent lesion in the right frontal bone without adjacent soft-tissue swelling
- `stance:coverage` **Metastatic bone disease** — why: The presence of a lytic lesion with cortical destruction and a soft-tissue component on imaging raises the possibility of metastatic bone disease.
    - 支持：a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer 
- `stance:coverage` **Multiple myeloma** — why: The patient's presentation of a lytic lesion with cortical destruction and a soft-tissue component on imaging could be consistent with multiple myeloma.
    - 支持：a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer 
- `stance:coverage` **Giant cell tumor** — why: The presence of a lytic lesion with a soap-bubble appearance and cortical destruction on imaging is suggestive of a giant cell tumor.
    - 支持：a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer 
- `stance:mechanism` **Osteoma** — why: A single process of bone tumor growth could produce all the described findings, including the painless mass, well-circumscribed lesion, and radiolucent appearance.
    - 支持：a painless mass on the right side of the frontal bone / was well circumscribed, soft, nonmobile, and non-tender / a large, circumscribed radiolucent lesion in the right frontal bone without adjacent soft-tissue swelling
- `stance:mechanism` **Giant Cell Tumor** — why: The soap-bubble appearance and cortical destruction are characteristic of giant cell tumors, which could explain the described radiographic findings.
    - 支持：a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer  / a lobulated frontal-bone mass measuring 3.7 × 3.3 × 2.8 cm
- `stance:mechanism` **Hemangioma** — why: The soap-bubble appearance and avid enhancement on postcontrast sequences could be indicative of a hemangioma, which is a type of vascular tumor.
    - 支持：a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer  / was hypointense on T1-weighted images, hyperintense on T2-weighted images, and showed avid enhancement on post
- `stance:mechanism` **Ewing's Sarcoma** — why: The lytic lesion and cortical destruction could be indicative of Ewing's sarcoma, but the lack of systemic symptoms and unremarkable laboratory studies make this diagnosis less likely.
    - 支持：a lytic lesion of the frontal bone with a soap-bubble appearance, cortical destruction of the inner and outer  / a lobulated frontal-bone mass measuring 3.7 × 3.3 × 2.8 cm
    - 反对：Laboratory studies and neurologic examination were unremarkable

</details>

### impc（召回 miss，判分 False）

- champion：**Giant Cell Tumor**　runner-up：Osteolytic lesion　margin：high
- selector 理由：The soap-bubble appearance and lytic lesion of the frontal bone are characteristic of Giant Cell Tumor, with strong support from multiple imaging modalities.

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Osteolytic lesion | none | 3.0 | D1E001 / D1E002 / D1E003 | — |
| Giant Cell Tumor | weak | 4.7 | D1E004 / D1E005 / D1E002 / D1E003 | — |
| Brown Tumor | none | 2.35 | D1E001 / D1E005 | — |
| Eosinophilic Granuloma | none | 2.0 | D1E001 / D1E002 | — |
| Osteomyelitis | none | 1.0 | D3E006 | — |
| Ewing's Sarcoma | none | 2.0 | D1E004 / D1E003 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `D1` **Osteolytic lesion** — why: The presence of a radiolucent lesion and lytic lesion with soap-bubble appearance suggests an osteolytic process.
    - 支持：a large, circumscribed radiolucent lesion in the right frontal bone / lytic lesion of the frontal bone with a soap-bubble appearance / cortical destruction of the inner and outer tables
- `D1` **Giant Cell Tumor** — why: The soap-bubble appearance is characteristic of giant cell tumors.
    - 支持：a soap-bubble appearance / lytic lesion of the frontal bone
- `D1` **Brown Tumor** — why: The presence of a radiolucent lesion and lytic lesion is consistent with a brown tumor.
    - 支持：a large, circumscribed radiolucent lesion in the right frontal bone / lytic lesion of the frontal bone
- `D2` **Eosinophilic Granuloma** — why: The presence of a well-circumscribed radiolucent lesion with a soap-bubble appearance is suggestive of Eosinophilic Granuloma.
    - 支持：a large, circumscribed radiolucent lesion in the right frontal bone / lytic lesion of the frontal bone with a soap-bubble appearance
- `D2` **Giant Cell Tumor** — why: The soap-bubble appearance and cortical destruction are characteristic features of Giant Cell Tumor.
    - 支持：lytic lesion of the frontal bone with a soap-bubble appearance / cortical destruction of the inner and outer tables
- `D2` **Brown Tumor** — why: The presence of a large, circumscribed radiolucent lesion is consistent with Brown Tumor.
    - 支持：a large, circumscribed radiolucent lesion in the right frontal bone / lytic lesion of the frontal bone
- `D3` **Osteomyelitis** — why: The presence of a radiolucent lesion with cortical destruction and an associated soft-tissue component could be indicative of an infectious process such as osteomyelitis.
    - 支持：a large, circumscribed radiolucent lesion in the right frontal bone without adjacent soft-tissue swelling
- `D3` **Ewing's Sarcoma** — why: The soap-bubble appearance and cortical destruction are characteristic features of Ewing's Sarcoma, a malignant bone tumor.
    - 支持：a soap-bubble appearance / cortical destruction of the inner and outer tables
- `D3` **Giant Cell Tumor** — why: The soap-bubble appearance and lytic lesion are consistent with a Giant Cell Tumor, a benign but locally aggressive bone tumor.
    - 支持：lytic lesion of the frontal bone with a soap-bubble appearance

</details>

<details><summary>selector 淘汰理由</summary>

- **Brown Tumor** — Less specific findings and lower score_logit
- **Eosinophilic Granuloma** — Less specific findings and lower score_logit
- **Ewing's Sarcoma** — Less specific findings and lower score_logit
- **Osteomyelitis** — Absence of adjacent soft-tissue swelling and lower score_logit

</details>

### forest（召回 miss，判分 False）

- champion：**Giant Cell Tumor**　runner-up：Brown Tumor　margin：medium
- selector 理由：lytic lesion with soap-bubble appearance and cortical destruction

| 候选 | 与金标 | 分数 | 支持 span | 反对 span |
|---|---|---|---|---|
| Osteoma | none | 4.5 | AX_SE004 / AX_SE002 / AX_ME008 / AX_ME009 | — |
| Giant Cell Tumor | weak | 6.0 | AX_SE005 / AX_SE006 / AX_ME011 / AX_SE003 | — |
| Fibrous Dysplasia | none | 2.0 | AX_SE005 / AX_SE007 | — |
| Ewing's Sarcoma | none | 2.0 | AX_ME010 / AX_SE003 | — |
| Brown Tumor | none | 4.5 | AX_ME012 / AX_ME009 / AX_ME013 / AX_SE005 | — |
| Eosinophilic Granuloma | none | 2.0 | AX_ME013 / AX_SE002 | — |

<details><summary>生成器逐视角候选与理由</summary>

- `syndrome_anatomy` **Osteoma** — why: The patient's presentation of a well-circumscribed, painless mass on the frontal bone with a soap-bubble appearance on radiography is consistent with osteoma.
    - 支持：well circumscribed / lytic lesion of the frontal bone with a soap-bubble appearance
- `syndrome_anatomy` **Giant Cell Tumor** — why: The soap-bubble appearance on radiography and the presence of a lytic lesion are characteristic of giant cell tumor.
    - 支持：lytic lesion of the frontal bone / soap-bubble appearance
- `syndrome_anatomy` **Fibrous Dysplasia** — why: The patient's presentation of a lytic lesion in the frontal bone could be consistent with fibrous dysplasia, although the classic ground-glass appearance is not mentioned.
    - 支持：lytic lesion of the frontal bone / ground-glass appearance is not mentioned but the description is consistent with fibrous dysplasia
- `mechanism_etiology` **Osteoma** — why: The presence of a well-circumscribed mass with a soap-bubble appearance on radiography suggests a benign bone tumor such as osteoma.
    - 支持：a well circumscribed, soft, nonmobile, and non-tender mass / a soap-bubble appearance
- `mechanism_etiology` **Giant Cell Tumor** — why: The soap-bubble appearance and cortical destruction are characteristic of giant cell tumors.
    - 支持：a lytic lesion of the frontal bone with a soap-bubble appearance / cortical destruction of the inner and outer tables
- `mechanism_etiology` **Ewing's Sarcoma** — why: The presence of a lobulated mass with cortical destruction suggests an aggressive bone tumor such as Ewing's sarcoma.
    - 支持：a lobulated frontal-bone mass / cortical destruction of the inner and outer tables
- `mechanism_etiology` **Brown Tumor** — why: The soap-bubble appearance and lytic lesion are characteristic of brown tumors, which are associated with hyperparathyroidism.
    - 支持：a lytic lesion of the frontal bone / a soap-bubble appearance
- `definitive_modality` **Eosinophilic Granuloma** — why: The radiographic and MRI findings are consistent with a bone lesion, and the soap-bubble appearance is characteristic of Eosinophilic Granuloma.
    - 支持：a large, circumscribed radiolucent lesion in the right frontal bone / lytic lesion of the frontal bone with a soap-bubble appearance
- `definitive_modality` **Giant Cell Tumor** — why: The soap-bubble appearance and cortical destruction are typical of Giant Cell Tumor.
    - 支持：lytic lesion of the frontal bone with a soap-bubble appearance / cortical destruction of the inner and outer tables
- `definitive_modality` **Brown Tumor** — why: The radiolucent lesion and lytic bone lesion are consistent with Brown Tumor.
    - 支持：a large, circumscribed radiolucent lesion in the right frontal bone / lytic lesion of the frontal bone

</details>

<details><summary>selector 淘汰理由</summary>

- **Osteoma** — typically presents as a well-circumscribed, bony mass without soap-bubble appearance
- **Eosinophilic Granuloma** — usually presents in the pediatric population and lacks the soap-bubble appearance
- **Ewing's Sarcoma** — typically presents with systemic symptoms and a more aggressive clinical course
- **Fibrous Dysplasia** — usually presents with ground-glass appearance on imaging, which is not mentioned in the vignette

</details>

