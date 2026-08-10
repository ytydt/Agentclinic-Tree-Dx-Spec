# DA / d2_heldout200b / case 698

- **gold**: Concurrent pulmonary and cerebral mucormycosis
- **layer**: `e7_win_recall` · **layer_aphhm**: ``
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 66-year-old man presented with progressive right-sided limb weakness for 3 days. Past medical history included excessive smoking and thyroid nodules. No history of hypertension, diabetes, heart disease, organ transplants, intravenous drug use, or steroid administration. No headache, vomiting, unconsciousness, or seizures were reported.

Physical examination revealed:- Right hemiplegia (MRC 0/5)- Cortical motor aphasia

Laboratory Tests:- WBCs: 14.53*109/L (elevated, normal range: 3.5–9.5*109/L)- Neutrophils: 79% (elevated, normal range: 40-75%)- Blood glucose: 5.82mmol/L (normal range: 3.9–6.1mmol/L)- CSF analysis: Cell count 322*106/L (normal: 0–10*106/L), lymphocytes 64%, total protein 950 mg/L (normal: 150–450 mg/L), chloride 109mmol/L (normal: 110–120 g/L)Imaging Studies:- Head MRI:  Title: Left parietal occupying lesion MRI  Description: Long T1 and T2 signals with severe edema, circular enhancement on contrast-enhanced T1 sequence- Chest CT:  Title: Left lung mass CT  Description: Substantial mass in left lung with pleural invasion, showing irregular mass with lobulation, spiculation, and pleural invasionPathological Examination:- Lung biopsy: Inflammatory cell infiltrates …

## Options
- A: Cerebral fungal abscess (e.g., invasive aspergillosis)
- B: Cerebral fungal infection (likely cerebral aspergillosis)
- C: Fungal brain abscess secondary to pulmonary infection
- D: Concurrent pulmonary and cerebral mucormycosis **←gold**

## Backbone e7

- S2 n=48 gold_rank=12
  - clusters: gold=1 near=11 other=36
- S3 shortlist (5):
  - [other] Lung cancer with brain metastasis
  - [other] Intracranial fungal infection
  - [other] Aspergillosis
  - [near] Cerebral abscess
  - [other] Glioblastoma
    - why_kept(Lung cancer with brain metastasis): Patient has a lung mass with pleural invasion and a brain lesion with severe edema and circular enhancement, suggesting metastasis
    - why_kept(Intracranial fungal infection): Brain lesion pathology shows multiple fungal hyphae, and patient has a compromised immune system due to excessive smoking history
    - why_kept(Aspergillosis): Fungal hyphae in brain lesion pathology and patient's history of excessive smoking, which increases risk of aspergillosis
    - why_kept(Cerebral abscess): Patient has elevated WBC count, neutrophils, and CSF cell count, suggesting an infectious process
    - why_kept(Glioblastoma): Patient has a brain lesion with severe edema and circular enhancement, which could be consistent with a primary brain tumor
- S4 champion: **Intracranial fungal infection** cluster=other jaccard=0.00
- S4 rationale: The presence of multiple fungal hyphae in the brain lesion pathology, along with the patient's symptoms and imaging findings, supports this diagnosis. The elevated WBC count and neutrophils also suggest an infectious process.
- S4 rejected:
  - [other] Lung cancer with brain metastasis: While the patient has a lung mass, the brain lesion pathology shows fungal hyphae, not metastatic cancer cells.
  - [other] Aspergillosis: Although aspergillosis is a type of fungal infection, the brain lesion pathology does not specifically identify Aspergillus species, making 'Intracranial fungal infection' a more general and appropriate diagnosis.
  - [near] Cerebral abscess: The brain lesion pathology shows fungal hyphae, which is more consistent with a fungal infection than a bacterial abscess.
  - [other] Glioblastoma: The brain lesion pathology shows fungal hyphae, not tumor cells, making glioblastoma an unlikely diagnosis.

## B06 (code=`b06_agents_miss` locus=`agents_miss`)
- supervisor: ['Cerebral aspergillosis', 'Brain metastasis from lung cancer']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Cerebral aspergillosis', 'Brain metastasis from lung cancer', 'Primary brain tumor', 'Cerebral abscess', 'Neurosyphilis', 'Cerebral aspergillosis', 'Brain metastasis from lung cancer', 'Primary brain tumor']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Cerebral aspergillosis with lung aspergillosis', 'Cerebral mucormycosis with lung cancer']
- diagnose: ['Cerebral aspergillosis with lung aspergillosis', 'Cerebral mucormycosis with lung cancer']
- queries: ['fungal brain infection with lung mass', 'cerebral fungal abscess with lung cancer', 'fungal hyphae in brain tissue with parietal lobe lesion']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

