# MCR / mcr_200b / case 365

- **gold**: thyroglossal duct cyst
- **layer**: `e7_win_recall`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`ok` B06=`agents_miss` B07=`draft_miss` B01=`rag_miss` APHHM=`na`
- **primary_locus**: e7=ok; B06=agents_miss; B07=draft_miss
- **covariates**: vig_words=298; gold_words=3; eponym=False; subtype=False; e7_s2_rank=1; mapper_rescue=False
- **causal**: layer=e7_win_recall; primary loci above.

## Vignette (trunc)
A 51-year-old man presented with a 2-year history of loud snoring, voice change, and witnessed obstructive sleep apnea with excessive daytime somnolence (Epworth Sleepiness Scale score 13). He denied dyspnea. His medical history was notable for mild hypertension and diabetes. Height was 160 cm, weight 62 kg (BMI 24.2 kg/m2). On examination, his Friedman tongue position was grade III (only the soft palate visible) and the tonsils were hidden in the tonsillar fossa. Flexible laryngoscopy revealed ...

## Backbone e7
- S1 key_facts: 2-year history of loud snoring; Voice change; Witnessed obstructive sleep apnea; Excessive daytime somnolence (Epworth Sleepiness Scale score 13); Mild hypertension; Diabetes; Friedman tongue position grade III; 20×20 mm round cystic mass at the base of the tongue
- S2 mode=complement k=3 pool_n=45 gold_in_s2=True
  - call1: ['Thyroglossal duct cyst', 'Ranula', 'Dermoid cyst', 'Teratoma', 'Lingual thyroid', 'Base of tongue lymphangioma', 'Hema
  - call2: ['Chondroma', 'Osteoma', 'Amyloidosis', 'Plasmacytoma', 'Castleman disease', 'Kimura disease', 'Angiofibroma', 'Rhabdomy
  - call3: ['Branchial cleft cyst', 'Thyroid gland ectopia', 'Lymphatic malformation', 'Venous malformation', 'Cystic hygroma', 'Li
- S3 shortlist n=5 gold=True: Thyroglossal duct cyst, Ranula, Dermoid cyst, Lingual thyroid, Base of tongue lymphangioma
- S4 champion: **Thyroglossal duct cyst** gold=True
- S4 raw (trunc): {"champion": "Thyroglossal duct cyst", "rationale": "The presence of a well-defined cystic lesion in the midline of the tongue base, as shown on contrast CT of the neck, is consistent with a thyroglossal duct cyst, which is a common congenital anomaly that can present in adulthoo

## Backbone v0 (compact)
- S1 key_facts: 2-year history of loud snoring; voice change; Epworth Sleepiness Scale score 13; mild hypertension; diabetes; Friedman tongue position grade III; 20×20 mm round cystic mass at the base of the tongue; respiratory disturbance index of 32.2 events/h
- S2 mode=single k=1 pool_n=16 gold_in_s2=True
  - call1: ['Lingual thyroid', 'Thyroglossal duct cyst', 'Ranula', 'Dermoid cyst', 'Teratoma', 'Lipoma', 'Hemangioma', 'Lymphangiom
- S3 shortlist n=5 gold=True: Thyroglossal duct cyst, Lingual thyroid, Ranula, Dermoid cyst, Teratoma
- S4 champion: **Thyroglossal duct cyst** gold=True
- S4 raw (trunc): {"champion": "Thyroglossal duct cyst", "rationale": "The presence of a well-defined cystic lesion in the midline of the tongue base, as shown on contrast CT of the neck, is consistent with a thyroglossal duct cyst, which is a common congenital anomaly that can cause obstructive s

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's symptoms and examination results, including the presence of a cystic mass at the base of the tongue and significant airway obstruction, suggest a 
  - turn1 gold_mention=False diag=
    The patient's symptoms, examination results, and imaging studies are consistent with a base of tongue cyst causing obstructive sleep apnea, aligning with Doctor
  - turn2 gold_mention=False diag=
    The patient's presentation of loud snoring, voice change, and witnessed obstructive sleep apnea, combined with the physical examination and imaging findings of 
- supervisor votes=3 top2=['Base of tongue cyst', 'Obstructive sleep apnea'] gold=False

## Baseline B07
- draft=['Vallecular cyst', 'Obstructive sleep apnea due to other base of tongue lesions'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['tongue base cystic mass symptoms', 'obstructive sleep apnea causes', 'Friedman tongue position grade III', 'cystic lesion in tongue base treatment']
- diagnose=['Vallecular cyst', 'Obstructive sleep apnea due to other base of tongue lesions'] gold=False

## Baseline B01
- queries=['tongue base cystic mass and obstructive sleep apnea', 'cystic lesion at the base of the tongue causing airway obstruction', 'Friedman tongue position grade III and sleep apnea', 'cystic hygroma or ranula causing obstructive sleep apnea']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Ranula', 'Cystic hygroma'] gold=False

