# MCR / mcr_v1 / case 116

- **gold**: systemic sclerosis sine scleroderma
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=1
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `parent_vs_subtype`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`final_ok` code=`aphhm_ok` prune_e7_ok=0

## Vignette
A 58-year-old woman presented to the rheumatology clinic with a 2-month history of fatigue, weakness, polyarthritis, and joint swelling. Nine months earlier, she had been diagnosed with idiopathic pulmonary hypertension after a 3-year history of progressive dyspnea (now NYHA class IV) and orthopnea, without cough or sputum, accompanied by low-grade fever and night sweats. Echocardiography at that time showed a pulmonary arterial systolic pressure (PASP) of 80 mm Hg, a left ventricular ejection fraction of 60%, mild mitral regurgitation, and moderate to severe tricuspid regurgitation. Chest CT revealed alveolar infiltrates in the posterior segment of the left basal lobe and multiple 6–8 mm peripheral lung nodules. Vital signs were normal, and pulmonary function testing was within normal limits.

Laboratory studies showed an erythrocyte sedimentation rate of 45 mm/h, an antinuclear antibody titer of 1:320, and an anti-centromere antibody level of 94.8 AU/ml. Tests for anti–Scl-70, hepatitis B surface antigen, hepatitis C virus, and rheumatoid arthritis were negative.

On examination, there was effusion of the right second, third, and fourth metacarpophalangeal joints; right second an…

## Backbone e7

- S2 n=51 gold_rank=1
  - clusters: gold=2 near=3 other=46
- S3 shortlist (5):
  - [gold] Systemic Sclerosis
  - [near] Limited Systemic Sclerosis
  - [other] CREST Syndrome
  - [other] Mixed Connective Tissue Disease
  - [other] Pulmonary Arterial Hypertension associated with Connective Tissue Disease
    - why_kept(Systemic Sclerosis): Presence of anti-centromere antibodies, Raynaud's phenomenon, and pulmonary hypertension
    - why_kept(Limited Systemic Sclerosis): Similar to systemic sclerosis, with a focus on limited skin involvement and prominent pulmonary hypertension
    - why_kept(CREST Syndrome): Characterized by Calcinosis, Raynaud's phenomenon, Esophageal dysmotility, Sclerodactyly, and Telangiectasia, with some features present in the case
    - why_kept(Mixed Connective Tissue Disease): Overlap of features from different autoimmune diseases, including systemic sclerosis, rheumatoid arthritis, and lupus
    - why_kept(Pulmonary Arterial Hypertension associated with Connective Tissue Disease): Direct association between pulmonary hypertension and underlying connective tissue disease
- S4 champion: **Limited Systemic Sclerosis** cluster=near jaccard=0.40
- S4 rationale: The presence of anti-centromere antibodies, Raynaud's phenomenon, and a history of progressive dyspnea with evidence of pulmonary hypertension are consistent with Limited Systemic Sclerosis, which often presents with these features and can have a slower progression compared to other forms of systemic sclerosis.
- S4 rejected:
  - [gold] Systemic Sclerosis: While systemic sclerosis could explain many of the symptoms, the presence of anti-centromere antibodies and the specific pattern of organ involvement suggest a more limited form of the disease.
  - [other] CREST Syndrome: CREST Syndrome is an older term for Limited Systemic Sclerosis, characterized by Calcinosis, Raynaud's phenomenon, Esophageal dysmotility, Sclerodactyly, and Telangiectasia. The patient's presentation lacks some of these classic features, making Limited Systemic Sclerosis a more appropriate diagnosis based on the provided information.
  - [other] Mixed Connective Tissue Disease: Mixed Connective Tissue Disease typically presents with a combination of features from lupus, rheumatoid arthritis, scleroderma, and polymyositis. The patient's anti-nuclear antibody titer is elevated, but other specific autoantibodies and clinical features characteristic of Mixed Connective Tissue Disease are not mentioned.
  - [other] Pulmonary Arterial Hypertension associated with Connective Tissue Disease: While the patient has pulmonary arterial hypertension, the presence of anti-centromere antibodies and other clinical features such as Raynaud's phenomenon and specific autoantibody profile point towards a diagnosis of Limited Systemic Sclerosis as the underlying connective tissue disease.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Systemic Sclerosis', 'Mixed Connective Tissue Disease']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Systemic Sclerosis', 'Mixed Connective Tissue Disease', 'Rheumatoid Arthritis', 'Idiopathic Pulmonary Arterial Hypertension', 'Undifferentiated Connective Tissue Disease', 'Systemic Sclerosis', 'Mixed Connective Tissue Disease', 'Undifferentiated Connective Tissue Disease']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Limited Systemic Sclerosis (CREST syndrome)', 'Systemic Sclerosis']
- diagnose: ['Limited Systemic Sclerosis (CREST syndrome)', 'Systemic Sclerosis']
- queries: ['systemic sclerosis diagnosis criteria', 'limited systemic sclerosis', 'CREST syndrome']

## B01 (code=`b01_judge_miss` locus=`gen_hit_judge_miss`)
- top2: ['Limited Systemic Sclerosis', 'Systemic Sclerosis']
- queries: ['polyarthritis and idiopathic pulmonary hypertension', 'anti-centromere antibody positive diseases', "Raynaud's phenomenon and pulmonary hypertension", 'limited systemic sclerosis diagnosis criteria']
- n_chunks=12

## APHHM
- tree_n=38 final_n=1
- final: ['Systemic Sclerosis']
- tree gold_cluster_n=4 final gold=True

