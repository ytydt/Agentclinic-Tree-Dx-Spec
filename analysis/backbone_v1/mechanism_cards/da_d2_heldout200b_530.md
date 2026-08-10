# DA / d2_heldout200b / case 530

- **gold**: Calcinosis cutis in Sjögren syndrome
- **layer**: `e7_win_recall` · **layer_aphhm**: ``
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `near_synonym_prefer`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 56-year-old woman with a history of hypothyroidism and hyperlipidemia presented for follow-up. Medical history includes 20-year history of oral and ocular sicca symptoms, asymptomatic elevation of creatinine kinase levels with negative myositis and muscular dystrophy panel, negative muscle biopsy results, and chronic stable autoimmune thrombocytopenia. Previous medications included methotrexate and low-dose steroids. Currently on hydroxychloroquine 200 mg daily. Does not take calcium or vitamin D supplements. Review of systems was positive for mild dryness of mouth and throat and Raynaud phenomenon. No skin tightening, esophageal reflux, dysphagia, or telangiectasis reported.

Vital signs were within normal limits. Oral mucosa was dry. Painless pinpoint white nodules present in the subcutaneous plane of the right fifth finger. No lymphadenopathy, telangiectasis, skin lesions, or mucosal or skin ulcers observed. Joints had full range of motion without erythema, swelling, or tenderness. Remainder of physical examination findings were normal.

- Laboratory Tests:
Hemoglobin: 13.0 g/dL (12-16)
Platelets: 115 × 1000/µL (150-440)
Leukocytes: 4.9 × 1000/µL (3.6-11.0)
Neutrophils: 47.4% …

## Options
- A: Calcinosis cutis in Sjögren syndrome **←gold**
- B: Scleroderma-Sjögren’s overlap syndrome
- C: Primary Sjögren’s syndrome
- D: Rheumatoid arthritis with secondary Sjögren’s syndrome

## Backbone e7

- S2 n=52 gold_rank=2
  - clusters: gold=1 near=14 other=37
- S3 shortlist (5):
  - [other] Limited systemic scleroderma
  - [near] Sjögren's syndrome
  - [other] Mixed connective tissue disease
  - [gold] Calcinosis cutis
  - [near] CREST syndrome
    - why_kept(Limited systemic scleroderma): Patient has Raynaud phenomenon, calcinosis, and positive antinuclear antibody, which are characteristic features of limited systemic scleroderma
    - why_kept(Sjögren's syndrome): Patient has 20-year history of oral and ocular sicca symptoms, which is a hallmark of Sjögren's syndrome
    - why_kept(Mixed connective tissue disease): Patient has overlapping features of different autoimmune diseases, including sicca symptoms, Raynaud phenomenon, and positive antinuclear antibody
    - why_kept(Calcinosis cutis): Patient has biopsy-proven calcinosis and soft-tissue calcifications in the distal fingers
    - why_kept(CREST syndrome): Patient has Calcinosis, Raynaud phenomenon, Esophageal dysmotility is not mentioned but has sicca symptoms, and Telangiectasia is not mentioned, but has a positive antinuclear antibody
- S4 champion: **CREST syndrome** cluster=near jaccard=0.20
- S4 rationale: The patient's symptoms, including Raynaud phenomenon, calcinosis, and esophageal reflux are not mentioned but the presence of Raynaud phenomenon and calcinosis are key features of CREST syndrome. The patient also has a positive antinuclear antibody and anti-Ro, which are common in autoimmune diseases. The combination of these features makes CREST syndrome the most likely diagnosis.
- S4 rejected:
  - [other] Limited systemic scleroderma: While the patient has some features of limited systemic scleroderma, such as Raynaud phenomenon and calcinosis, the absence of skin tightening and other features of scleroderma make this diagnosis less likely.
  - [near] Sjögren's syndrome: The patient's oral and ocular sicca symptoms are consistent with Sjögren's syndrome, but the presence of calcinosis and Raynaud phenomenon suggest a more complex autoimmune disease.
  - [other] Mixed connective tissue disease: The patient's combination of autoimmune features, including positive antinuclear antibody and anti-Ro, could suggest mixed connective tissue disease, but the specific features of CREST syndrome are more prominent in this case.
  - [gold] Calcinosis cutis: While the patient has calcinosis, this is a feature of CREST syndrome, and the diagnosis of calcinosis cutis alone does not account for the other autoimmune features present.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Limited Systemic Sclerosis', "Sjögren's Syndrome"]
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Limited Systemic Sclerosis', "Sjögren's Syndrome", 'Calcinosis Cutis', 'Mixed Connective Tissue Disease', 'Undifferentiated Connective Tissue Disease', 'Limited Systemic Sclerosis', "Sjögren's Syndrome", 'Calcinosis Cutis']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Limited Systemic Scleroderma (CREST Syndrome)', "Sjögren's Syndrome"]
- diagnose: ['Limited Systemic Scleroderma (CREST Syndrome)', "Sjögren's Syndrome"]
- queries: ['limited systemic scleroderma', 'calcinosis cutis', 'CREST syndrome', 'autoimmune disease with sicca symptoms and calcinosis']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

