# MCR / mcr_200b / case 365

- **gold**: thyroglossal duct cyst
- **layer**: `e7_win_recall` · **layer_aphhm**: ``
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 51-year-old man presented with a 2-year history of loud snoring, voice change, and witnessed obstructive sleep apnea with excessive daytime somnolence (Epworth Sleepiness Scale score 13). He denied dyspnea. His medical history was notable for mild hypertension and diabetes. Height was 160 cm, weight 62 kg (BMI 24.2 kg/m2). On examination, his Friedman tongue position was grade III (only the soft palate visible) and the tonsils were hidden in the tonsillar fossa. Flexible laryngoscopy revealed a 20×20 mm round cystic mass at the base of the tongue that displaced the epiglottis posteriorly and narrowed the airway; the vocal cords could not be seen. No other lesions were identified.  

Laboratory polysomnography showed a respiratory disturbance index of 32.2 events/h overall and 105.8 events/h in the supine position, a longest apnea of 39.7 s, a lowest SaO2 of 89%, and an average SaO2 of 97.2%.  

Contrast CT of the neck demonstrated a 33×31×27 mm well-defined cystic lesion in the midline of the tongue base, compressing the oropharyngeal airway and displacing the epiglottis posteriorly.  

Sleep videofluoroscopy under midazolam sedation showed complete pharyngeal airway obstruction …

## Backbone e7

- S2 n=45 gold_rank=1
  - clusters: gold=1 near=0 other=44
- S3 shortlist (5):
  - [gold] Thyroglossal duct cyst
  - [other] Ranula
  - [other] Dermoid cyst
  - [other] Lingual thyroid
  - [other] Base of tongue lymphangioma
    - why_kept(Thyroglossal duct cyst): Cystic mass at the base of the tongue, consistent with thyroglossal duct cyst location and characteristics
    - why_kept(Ranula): Cystic lesion in the tongue base, possible ranula given the location and cystic nature
    - why_kept(Dermoid cyst): Well-defined cystic lesion, dermoid cyst is a plausible diagnosis given the clinical presentation
    - why_kept(Lingual thyroid): Cystic mass at the base of the tongue, lingual thyroid is a rare but possible diagnosis
    - why_kept(Base of tongue lymphangioma): Cystic lesion in the tongue base, lymphangioma is a possible diagnosis given the location and cystic nature
- S4 champion: **Thyroglossal duct cyst** cluster=gold jaccard=1.00
- S4 rationale: The presence of a well-defined cystic lesion in the midline of the tongue base, as shown on contrast CT of the neck, is consistent with a thyroglossal duct cyst, which is a common congenital anomaly that can present in adulthood with symptoms of obstructive sleep apnea due to airway compression.
- S4 rejected:
  - [other] Ranula: Ranula typically presents as a blue, translucent lesion in the floor of the mouth, not at the base of the tongue.
  - [other] Dermoid cyst: Dermoid cysts are less common in this location and often contain heterogeneous contents, not consistent with the described cystic mass.
  - [other] Lingual thyroid: Lingual thyroid would likely be associated with thyroid function abnormalities, which are not mentioned in the case.
  - [other] Base of tongue lymphangioma: Lymphangiomas are rare and typically present with a more complex, multicystic appearance on imaging.

## B06 (code=`b06_agents_miss` locus=`agents_miss`)
- supervisor: ['Base of tongue cyst', 'Obstructive sleep apnea']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Base of tongue cyst', 'Obstructive sleep apnea', 'Hypertrophic tonsils', 'Lingual thyroid', 'Raney tongue cyst', 'Base of tongue cyst', 'Obstructive sleep apnea', 'Lingual thyroid']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Vallecular cyst', 'Obstructive sleep apnea due to other base of tongue lesions']
- diagnose: ['Vallecular cyst', 'Obstructive sleep apnea due to other base of tongue lesions']
- queries: ['tongue base cystic mass symptoms', 'obstructive sleep apnea causes', 'Friedman tongue position grade III', 'cystic lesion in tongue base treatment']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Ranula', 'Cystic hygroma']
- queries: ['tongue base cystic mass and obstructive sleep apnea', 'cystic lesion at the base of the tongue causing airway obstruction', 'Friedman tongue position grade III and sleep apnea', 'cystic hygroma or ranula causing obstructive sleep apnea']
- n_chunks=12

## APHHM
_na_

