# DA / d2_heldout100 / case 381

- **gold**: Good syndrome
- **layer**: `aphhm_win` · **layer_aphhm**: `aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=1
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=0

## Vignette
A White man in his 50s presented with painful oral erosions that began 2 years before. Medical history included recurrent respiratory infections and diarrhea. A previous intestinal biopsy had shown unspecific findings and absence of apoptosis. He reported a 5-kg weight loss attributed to impaired intake due to oral lesions. He was being evaluated for a mediastinal mass detected during chest radiography performed for pneumonia.

Physical examination revealed whitish edematous lacy patches with erosions on the dorsal and lateral aspects of the tongue and buccal mucosa. Skin and nails were not involved.

- Biopsy & Immunofluorescence:    - Lingual biopsy showed epidermal acanthosis with scattered necrotic keratinocytes, basal-layer vacuolation, and band-like lymphohistiocytic infiltrate    - Direct immunofluorescence showed fibrinogen deposition along basement membrane    - Indirect immunofluorescence testing (using monkey esophagus, salt-skin split, and rat bladder) was negative    - ELISA and immunoblot analysis negative for multiple antibodies  - Laboratory Tests:    - Normal liver function    - Negative for hepatitis B and C    - Decreased IgG serum level: 465 mg/dL (normal: 750-1…

## Options
- A: Common variable immunodeficiency
- B: Good syndrome **←gold**
- C: Paraneoplastic pemphigus
- D: Erosive oral lichen planus

## Backbone e7

- S2 n=55 gold_rank=None
  - clusters: gold=0 near=4 other=51
- S3 shortlist (5):
  - [other] Thymoma
  - [other] Paraneoplastic pemphigus
  - [near] Good's syndrome
  - [other] Mucous membrane pemphigoid
  - [near] Autoimmune lymphoproliferative syndrome
    - why_kept(Thymoma): Mediastinal mass detected and histopathology confirmed type AB thymoma
    - why_kept(Paraneoplastic pemphigus): Chronic oral erosions and thymoma, a known association with paraneoplastic pemphigus
    - why_kept(Good's syndrome): Thymoma and decreased IgG serum level, consistent with Good's syndrome
    - why_kept(Mucous membrane pemphigoid): Oral erosions and fibrinogen deposition along basement membrane, consistent with mucous membrane pemphigoid
    - why_kept(Autoimmune lymphoproliferative syndrome): Recurrent infections, decreased IgG, and inverted CD4:CD8 ratio, suggesting an underlying immunodeficiency
- S4 champion: **Paraneoplastic pemphigus** cluster=other jaccard=0.00
- S4 rationale: The patient's oral erosions, lingual biopsy showing epidermal acanthosis with scattered necrotic keratinocytes, and direct immunofluorescence showing fibrinogen deposition along basement membrane are consistent with paraneoplastic pemphigus, which is often associated with thymoma as seen in this patient.
- S4 rejected:
  - [other] Thymoma: While the patient has a thymoma, this is not a diagnosis that explains the oral erosions and skin findings.
  - [near] Good's syndrome: Good's syndrome is characterized by thymoma and immunodeficiency, but it does not typically present with oral erosions and skin findings as seen in this patient.
  - [other] Mucous membrane pemphigoid: Mucous membrane pemphigoid can present with oral erosions, but the presence of a thymoma and the specific biopsy and immunofluorescence findings make paraneoplastic pemphigus a more likely diagnosis.
  - [near] Autoimmune lymphoproliferative syndrome: This condition is characterized by autoimmune symptoms and lymphoproliferation, but it does not typically present with the specific oral and skin findings seen in this patient.

## B06 (code=`b06_agents_miss` locus=`agents_miss`)
- supervisor: ['Paraneoplastic Pemphigus', 'Thymoma-associated multiorgan autoimmunity']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Mycosis Fungoides', 'Lichen Planus', 'Pemphigus', 'Thymoma-associated multiorgan autoimmunity', 'Paraneoplastic Pemphigus', 'Paraneoplastic Pemphigus', 'Lichen Planus', 'Pemphigus']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Paraneoplastic Pemphigus', 'Thymoma-associated Mucocutaneous Disorder']
- diagnose: ['Paraneoplastic Pemphigus', 'Thymoma-associated Mucocutaneous Disorder']
- queries: ['oral erosions and thymoma', 'paraneoplastic pemphigus', 'thymoma associated mucocutaneous disorders']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=25 final_n=2
- final: ['Thymoma-associated Immunodeficiency', 'Paraneoplastic Pemphigus']
- tree gold_cluster_n=2 final gold=False

