# DA / d2_heldout200b / case 549

- **gold**: Systemic Lupus Erythematosus with IgA Nephropathy and Acute Progressive Glomerulonephritis
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01= APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `parent_vs_subtype`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 72-year-old man presented with poor appetite and fatigue for a week. The patient had a history of hypertension for years but no other chronic health problems, and did not take any medications regularly. No history of Raynaud phenomenon, swollen fingers, rashes, joint pain, coughing, or wheezing. Daily urine output decreased to less than 50 mL/d after admission.

Blood pressure: 138/94 mm Hg. Bilateral lower limb edema present. No skin damage to the face, no swelling in the fingers in either hand, and no joint deformation or pain noted.

- Laboratory Tests:    * Blood Tests: Leukocytes 3.9 × 10¹²/L, Erythrocytes 2.9 × 10¹²/L, Hemoglobin 87 × 10⁹/L, Platelets 43 × 10⁹/L    * Serum Tests: Creatinine 869 μmol/L, Urea 32 mmol/L, Albumin 31.4 g/L    * Immunological Tests: ANA positive (1:100), Anti-SM positive, U1-NRNP positive, Complement C3 0.07 g/L, C4 0.16 g/L    * Urine Analysis: Occult blood 3+ (dysmorphic), Protein 1+, Leukocytes 12/HPF, Casts negative- Imaging Studies:    * Kidney ultrasound: Enhanced echogenicity of both renal parenchyma    * Chest CT: Small amount of pleural effusion- Kidney Biopsy Findings:    * Light Microscopy: Large number of cellular crescents    * Immun…

## Options
- A: Crescentic IgA nephropathy (rapidly progressive IgA glomerulonephritis)
- B: Lupus nephritis (class IV) with crescentic glomerulonephritis
- C: Systemic Lupus Erythematosus with IgA Nephropathy and Acute Progressive Glomerulonephritis **←gold**
- D: IgA nephropathy with crescentic transformation

## Backbone e7

- S2 n=42 gold_rank=5
  - clusters: gold=1 near=11 other=30
- S3 shortlist (5):
  - [near] Rapidly progressive glomerulonephritis
  - [near] Lupus nephritis
  - [gold] IgA nephropathy
  - [other] Anti-glomerular basement membrane disease
  - [other] ANCA-associated vasculitis
    - why_kept(Rapidly progressive glomerulonephritis): Patient presents with rapidly progressive renal failure and systemic symptoms, consistent with RPGN
    - why_kept(Lupus nephritis): Positive ANA, anti-SM, and U1-NRNP, along with low complement levels, suggest lupus nephritis as a possible diagnosis
    - why_kept(IgA nephropathy): IgA deposition in mesangial area on immunofluorescence and electron-dense deposits on electron microscopy are characteristic of IgA nephropathy
    - why_kept(Anti-glomerular basement membrane disease): Presence of rapidly progressive renal failure and systemic symptoms, along with positive anti-SM and U1-NRNP, could suggest anti-GBM disease
    - why_kept(ANCA-associated vasculitis): Patient's presentation with rapidly progressive renal failure, systemic symptoms, and positive ANA could be consistent with ANCA-associated vasculitis
- S4 champion: **Lupus nephritis** cluster=near jaccard=0.09
- S4 rationale: The patient has a positive ANA, Anti-SM, and U1-NRNP, which are specific autoantibodies associated with systemic lupus erythematosus (SLE). The presence of low complement levels (C3 and C4) and the kidney biopsy findings of cellular crescents and IgA deposition also support this diagnosis.
- S4 rejected:
  - [near] Rapidly progressive glomerulonephritis: While the patient has rapidly progressive renal failure, the presence of specific autoantibodies and low complement levels points more towards an immune-mediated disease like lupus nephritis
  - [gold] IgA nephropathy: Although the biopsy shows IgA deposition, the clinical presentation and other laboratory findings (e.g., positive ANA, Anti-SM, and U1-NRNP) are more consistent with lupus nephritis
  - [other] Anti-glomerular basement membrane disease: There is no mention of anti-GBM antibodies, which are characteristic of this disease
  - [other] ANCA-associated vasculitis: There is no mention of ANCA positivity or other typical features of vasculitis, such as granulomatosis or eosinophilia

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Rapidly Progressive Glomerulonephritis', 'IgA Nephropathy']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Rapidly Progressive Glomerulonephritis', 'IgA Nephropathy', 'Systemic Lupus Erythematosus', 'ANCA-associated Vasculitis', 'Goodpasture Syndrome', 'Rapidly Progressive Glomerulonephritis', 'IgA Nephropathy', 'Systemic Lupus Erythematosus']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['IgA Nephropathy with Rapidly Progressive Glomerulonephritis (RPGN)', 'Systemic Lupus Erythematosus (SLE) with Renal Involvement']
- diagnose: ['IgA Nephropathy with Rapidly Progressive Glomerulonephritis (RPGN)', 'Systemic Lupus Erythematosus (SLE) with Renal Involvement']
- queries: ['A 72-year-old man presented with poor appetite and fatigue for a week. The patient had a history of hypertension for years but no other chronic health problems, and did not take any medications regula', 'differential diagnosis A 72-year-old man presented with poor appetite and fatigue for a week. The patient had a history of hypertension for years but no other chronic health problems, and did not take any medications regula', 'clinical manifestations diagnosis  noted. - Laboratory Tests: * Blood Tests: Leukocytes 3.9 × 10¹²/L, Erythrocytes 2.9 × 10¹²/L, Hemoglobin 87 × 10⁹/L, Platelets 43 × 10⁹/L * Serum Tests: Creati']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

