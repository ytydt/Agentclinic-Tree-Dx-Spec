# MCR / mcr_200b / case 361

- **gold**: Anaplastic thyroid carcinoma
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `near_synonym_prefer`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 60-year-old woman presented with a 6-month history of sore throat, progressive dysphonia, dysphagia to solids, choking and aspiration episodes. She also noted left-sided otalgia and weight loss but denied dyspnoea. There was no personal or family history of cancer.  
   
On flexible nasoendoscopy, a left pyriform fossa mass was seen invading and compressing the left hemilarynx; the larynx was fixed, the airway significantly narrowed but no stridor was present. The neck laryngeal framework appeared broadened with loss of the laryngeal click.  
   
MRI of the neck demonstrated a large necrotic mass centred on the left pyriform fossa extending superiorly along the posterolateral pharyngeal wall, invading the left glottis and strap muscles, crossing the midline into the retrovisceral space and abutting the right carotid sheath. Enlarged, rounded, heterogeneously enhancing cervical lymph nodes were present bilaterally in level II, left level III and IV.  
   
FDG PET–CT confirmed high metabolic activity in the hypopharyngeal mass and a right level II lymph node, and detected focal uptake with sclerotic changes in the left femoral neck, suggesting bony metastasis.  
   
Neck ultrasound…

## Backbone e7

- S2 n=52 gold_rank=12
  - clusters: gold=1 near=16 other=35
- S3 shortlist (5):
  - [near] Hypopharyngeal squamous cell carcinoma
  - [near] Laryngeal squamous cell carcinoma
  - [other] Pyriform sinus cancer
  - [near] Oropharyngeal squamous cell carcinoma
  - [gold] Anaplastic thyroid carcinoma
    - why_kept(Hypopharyngeal squamous cell carcinoma): Matches case facts of progressive upper aerodigestive tract obstruction with local invasion and distant spread, and is consistent with the presence of a necrotic mass in the left pyriform fossa and cervical lymphadenopathy
    - why_kept(Laryngeal squamous cell carcinoma): Consistent with the fixed larynx, significantly narrowed airway, and invasion of the left glottis and strap muscles
    - why_kept(Pyriform sinus cancer): Specific location of the mass in the left pyriform fossa and clinical presentation of sore throat, dysphonia, and dysphagia
    - why_kept(Oropharyngeal squamous cell carcinoma): Possible given the proximity of the tumor to the oropharynx and the presence of cervical lymphadenopathy
    - why_kept(Anaplastic thyroid carcinoma): Although less likely, the involvement of the thyroid lobe and the presence of a poorly differentiated malignant tumor on fine-needle aspiration keep this diagnosis in consideration
- S4 champion: **Hypopharyngeal squamous cell carcinoma** cluster=near jaccard=0.17
- S4 rationale: The patient's symptoms, including progressive dysphonia, dysphagia to solids, and choking and aspiration episodes, along with the presence of a left pyriform fossa mass on flexible nasoendoscopy and a necrotic mass on MRI centered on the left pyriform fossa, are consistent with hypopharyngeal squamous cell carcinoma. The high metabolic activity on FDG PET-CT and the presence of bony metastasis also support this diagnosis.
- S4 rejected:
  - [near] Laryngeal squamous cell carcinoma: Although the larynx is involved, the primary site of the tumor is the left pyriform fossa, which is more consistent with hypopharyngeal squamous cell carcinoma.
  - [other] Pyriform sinus cancer: Pyriform sinus cancer is a type of hypopharyngeal cancer, and the patient's symptoms and tumor location are consistent with hypopharyngeal squamous cell carcinoma, which is a more specific diagnosis.
  - [near] Oropharyngeal squamous cell carcinoma: The tumor is located in the hypopharynx, not the oropharynx, and the patient's symptoms are more consistent with hypopharyngeal squamous cell carcinoma.
  - [gold] Anaplastic thyroid carcinoma: The tumor is not centered on the thyroid gland, and the patient's symptoms and imaging findings are more consistent with hypopharyngeal squamous cell carcinoma. The involvement of the thyroid lobe is likely secondary to the primary tumor in the pyriform fossa.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Hypopharyngeal cancer', 'Squamous cell carcinoma']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Hypopharyngeal cancer', 'Laryngeal cancer', 'Thyroid cancer', 'Metastatic cancer', 'Squamous cell carcinoma', 'Hypopharyngeal cancer', 'Laryngeal cancer', 'Squamous cell carcinoma']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Hypopharyngeal carcinoma', 'Poorly differentiated squamous cell carcinoma']
- diagnose: ['Hypopharyngeal carcinoma', 'Poorly differentiated squamous cell carcinoma']
- queries: ['hypopharyngeal cancer symptoms', 'hypopharyngeal cancer diagnosis', 'poorly differentiated malignant tumor hypopharynx']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Hypopharyngeal cancer', 'Squamous cell carcinoma of the hypopharynx']
- queries: ['hypopharyngeal cancer symptoms and diagnosis', 'pyriform fossa mass differential diagnosis', 'progressive dysphonia and dysphagia causes', 'poorly differentiated malignant tumor of the head and neck']
- n_chunks=12

## APHHM
_na_

