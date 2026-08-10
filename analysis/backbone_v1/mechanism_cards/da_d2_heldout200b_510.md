# DA / d2_heldout200b / case 510

- **gold**: Overlap syndrome involving diffuse systemic sclerosis and systemic lupus erythematosus
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=
- **e7_locus**: `s4_hit_judge_miss` · **e7_fail_code**: `s4_hit_judge_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 72-year-old woman with a history of type 2 diabetes treated with metformin and osteoarthritis presented with a progressive increase in abdominal girth over the last month. She reported a weight loss of 10 kg, ocular dryness, solid dysphagia, dysgeusia, constipation, and morning stiffness for the past 12 months, along with hand and knee pain, Raynaud phenomenon, and skin thickening over the last 5 years.

- Dry, thickened skin with salt-and-pepper lesions on the face
- Bilateral pleural effusion with oxygen saturation at 87%
- Grade 2 ascites with shifting dullness and fluid wave
- Hardened and hyperpigmented skin on the limbs
- Arthritis in the hands with ulnar deviation of the wrists
- Lower-limb edema
- Muscle strength of 4/5

Laboratory Tests:
- Hemoglobin: 13 g/dL
- Leukocytes: 6.4 (1000/mm³)
- Lymphocytes: 1.38 (1000/mm³)
- C-reactive protein: 4.4 mg/L (elevated)
- Erythrocyte sedimentation rate: 37 mm/hr (elevated)
- Albumin: 1.7 g/dL (low)
- Complement C3: 36.9 mg/dL (low)
- Anti-Sm antibody: 36.22 U (weak positive)
- Antinuclear antibodies: Fine speckled 4+, mitochondrial 3+

Imaging and Other Tests:
- Capillaroscopy Image Description: Late signs with avascular areas
- Co…

## Options
- A: Systemic sclerosis (scleroderma) **←gold**
- B: Systemic lupus erythematosus (SLE) **←gold**
- C: Sjögren’s syndrome
- D: Overlap syndrome involving diffuse systemic sclerosis and systemic lupus erythematosus **←gold**

## Backbone e7

- S2 n=48 gold_rank=1
  - clusters: gold=4 near=17 other=27
- S3 shortlist (5):
  - [gold] Systemic Sclerosis
  - [other] Mixed Connective Tissue Disease
  - [gold] Systemic Lupus Erythematosus
  - [near] Sjögren's Syndrome
  - [near] Limited Systemic Sclerosis
    - why_kept(Systemic Sclerosis): Skin thickening, joint involvement, and internal organ dysfunction are characteristic of this disease
    - why_kept(Mixed Connective Tissue Disease): Overlap of features from systemic lupus erythematosus, rheumatoid arthritis, and systemic sclerosis
    - why_kept(Systemic Lupus Erythematosus): Positive antinuclear antibodies, low complement C3, and kidney involvement
    - why_kept(Sjögren's Syndrome): Ocular dryness, decreased tear secretion, and presence of antinuclear antibodies
    - why_kept(Limited Systemic Sclerosis): Skin thickening limited to the face, hands, and feet, with presence of anti-centromere antibodies not mentioned but possible
- S4 champion: **Systemic Sclerosis** cluster=gold jaccard=0.22
- S4 rationale: The patient's symptoms, including skin thickening, Raynaud phenomenon, esophageal dysmotility (solid dysphagia), and interstitial lung disease, are characteristic of systemic sclerosis. The presence of antinuclear antibodies and a weak positive Anti-Sm antibody also supports this diagnosis.
- S4 rejected:
  - [other] Mixed Connective Tissue Disease: While the patient has overlapping features of different autoimmune diseases, the prominent skin and esophageal involvement points more towards systemic sclerosis.
  - [gold] Systemic Lupus Erythematosus: The lack of more specific lupus criteria such as malar rash, oral ulcers, or nephritis makes this diagnosis less likely.
  - [near] Sjögren's Syndrome: Although the patient has ocular dryness, the primary symptoms and findings are more suggestive of systemic sclerosis than Sjögren's syndrome.
  - [near] Limited Systemic Sclerosis: The patient's widespread skin involvement and internal organ involvement (e.g., interstitial lung disease) suggest a more diffuse form of systemic sclerosis rather than the limited form.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Systemic Sclerosis', 'Mixed Connective Tissue Disease']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Systemic Sclerosis', "Sjögren's Syndrome", 'Mixed Connective Tissue Disease', 'Rheumatoid Arthritis', 'Systemic Lupus Erythematosus', 'Systemic Sclerosis', 'Mixed Connective Tissue Disease', "Sjögren's Syndrome"]
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Systemic Sclerosis (Diffuse Cutaneous)', 'Systemic Sclerosis (Limited Cutaneous)']
- diagnose: ['Systemic Sclerosis (Diffuse Cutaneous)', 'Systemic Sclerosis (Limited Cutaneous)']
- queries: ['systemic sclerosis diagnosis criteria', 'limited systemic sclerosis vs diffuse systemic sclerosis', 'systemic sclerosis with interstitial lung disease treatment']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

