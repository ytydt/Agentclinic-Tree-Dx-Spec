# MCR / mcr_200b / case 298

- **gold**: Warthin tumor
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_near_crowd_out`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 71-year-old Hispanic man was referred for a 2-month history of dysphagia and left oropharyngeal fullness. His medical history included hypertension, dyslipidemia, atrial fibrillation, and a left superficial parotidectomy in 2008 for a Warthin tumor, followed by Frey syndrome. He is an active smoker with a 27.5–pack-year history. On examination, there was left soft-palate fullness without ulceration. Review of contrast-enhanced CT images from 2008 showed an enlarged left intraparotid lymph node with central hypodensity and, retrospectively, a small left oropharyngeal nodule. In early 2014, MRI of the head and neck demonstrated a small (8 mm), submucosal, ovoid nodule in the left oropharyngeal airway with a peripheral ring of enhancement.

What is the most likely diagnosis?

Options:
A. Warthin tumor
B. other parotid tumors
C. lymph node enlargement
D. branchial cleft cyst
E. minor salivary gland tumor
F. mucocele
G. parotid WT should include other parotid tumors, lymph node enlargement, or branchial cysts
H. None


## Backbone e7

- S2 n=48 gold_rank=3
  - clusters: gold=1 near=6 other=41
- S3 shortlist (5):
  - [other] Squamous cell carcinoma of the oropharynx
  - [other] Mucoepidermoid carcinoma
  - [other] Lymphoma of the oropharynx
  - [other] Metastatic disease to the oropharynx
  - [near] Minor salivary gland tumor
    - why_kept(Squamous cell carcinoma of the oropharynx): Patient's history of smoking and symptoms of dysphagia and oropharyngeal fullness
    - why_kept(Mucoepidermoid carcinoma): Submucosal nodule in the oropharyngeal airway and history of salivary gland tumor
    - why_kept(Lymphoma of the oropharynx): Enlarged intraparotid lymph node and oropharyngeal symptoms
    - why_kept(Metastatic disease to the oropharynx): Patient's history of smoking and multiple medical conditions increasing the risk of metastasis
    - why_kept(Minor salivary gland tumor): Submucosal nodule in the oropharyngeal airway and history of salivary gland tumor
- S4 champion: **Squamous cell carcinoma of the oropharynx** cluster=other jaccard=0.00
- S4 rationale: The patient's 27.5-pack-year smoking history and symptoms of dysphagia and oropharyngeal fullness are consistent with squamous cell carcinoma of the oropharynx, which is a common malignancy in this region, especially in smokers.
- S4 rejected:
  - [other] Mucoepidermoid carcinoma: Less common than squamous cell carcinoma and not as strongly associated with smoking history
  - [other] Lymphoma of the oropharynx: Would likely present with more systemic symptoms and lymphadenopathy
  - [other] Metastatic disease to the oropharynx: No mention of a known primary malignancy
  - [near] Minor salivary gland tumor: Less likely given the patient's smoking history and the location of the tumor

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Squamous cell carcinoma', 'Salivary gland malignancy']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Squamous cell carcinoma', 'Warthin tumor recurrence', 'Lymphoma', 'Salivary gland malignancy', 'Metastatic disease', 'Squamous cell carcinoma', 'Salivary gland malignancy', 'Warthin tumor recurrence']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Oropharyngeal cancer', 'Metastatic disease from a previous head and neck cancer']
- diagnose: ['Oropharyngeal cancer', 'Metastatic disease from a previous head and neck cancer']
- queries: ['oropharyngeal cancer risk factors', 'Warthin tumor association with other cancers', 'Frey syndrome complications', 'intraparotid lymph node enlargement causes']

## B01 (code=`b01_judge_miss` locus=`gen_hit_judge_miss`)
- top2: ['Squamous cell carcinoma of the oropharynx', 'Warthin tumor with malignant transformation']
- queries: ['oropharyngeal dysphagia causes', 'intraparotid lymph node enlargement differential diagnosis', 'submucosal oropharyngeal nodule diagnostic criteria', 'Frey syndrome association with oropharyngeal masses']
- n_chunks=12

## APHHM
_na_

