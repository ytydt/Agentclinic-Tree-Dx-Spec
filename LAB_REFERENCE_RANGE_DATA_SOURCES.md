# Lab reference-range extension and benchmark audit

> Generated 2026-07-19. Research/benchmark normalization only; not for patient care.

## Outcome

The catalog expands from **83 to 156 tests** (**73 additions**). The pinned numeric-bearing splits produced **2718 catalog measurements across 634 cases**, covering **144 distinct tests**.

The runtime applies an interval printed in the case first. A static interval is used only when the unit and available context match; incompatible units return `unknown`. FEU and DDU are never interconverted.

## Target datasets

| Dataset | Rows | Numeric audit | Measurements | Distinct tests | Notes |
|---|---:|:---:|---:|---:|---|
| [DiagnosisArena test](https://huggingface.co/datasets/SII-SPIRAL-MED/DiagnosisArena) | 915 | yes | 1313 | 131 | 91 incompatible units; 215 unitless; 46 context-dependent |
| [MedCaseReasoning validation](https://huggingface.co/datasets/zou-lab/MedCaseReasoning) | 500 | yes | 838 | 99 | 32 incompatible units; 83 unitless; 13 context-dependent |
| [Open-XDDx](https://github.com/betterzhou/Dual-Inf) | 570 | yes | 567 | 65 | 40 incompatible units; 53 unitless; 6 context-dependent |
| [RareBench public data](https://huggingface.co/datasets/chenxz/RareBench) | 1122 | no | — | — | Public records contain HPO phenotype identifiers and disease identifiers, not raw numeric laboratory results. |

## Detected tests and fallback values

The table is occurrence-ranked. Values are representative benchmark fallbacks, not replacements for the reporting laboratory interval.
The versioned 2026/Mayo/NHS source IDs support this extension; older source IDs are legacy values retained from the pre-existing catalog, as recorded in the source manifest.

| Test | Occurrences / cases | Observed units | Fallback or decision limit | Source |
|---|---:|---|---|---|
| `WBC` | 258 / 239 | <unitless> (91), /mm3 (58), /μL (18), × 109/L (18), ×10^9/L (13), /µL (12), × 10^9/L (10), cells/mm3 (4), × 10^3/µL (4), × 103/μL (3), K/μL (3), cells/µL (3), cells/μL (2), x109/L (2), /uL (1), × 1000/µL (1), k/μl (1), G/L (1), cells/μl (1), x10^9/l (1), ×10^3/µl (1), × 10^3/µL (1), /μl (1), × 10^3/μL (1), ×10^9/l (1), ×10^3/µL (1), × 10^6/µL (1), K/uL (1), ×103/µL (1), ×10^3/μL (1), S (1) | 4500–11000 /μL | Tietz 5th Ed |
| `Hemoglobin` | 249 / 236 | g/dL (173), g/L (58), g/dl (7), <unitless> (5), mmol/L (4), mg/dL (2) | 13.5–17.5 g/dL (male); 12.0–16.0 g/dL (female) | Tietz 5th Ed |
| `Platelets` | 174 / 157 | <unitless> (64), /mm3 (41), ×10^9/L (16), × 109/L (9), × 10^9/L (6), /μL (5), × 103/μL (4), /µL (4), × 10^3/µL (3), K/μL (2), cells/mm3 (2), ×10^3/µL (2), × 10^3/μL (2), ×10^3/μL (2), x 109/L (2), × 103/µL (1), ×103/μL (1), × 1000/µL (1), K/µL (1), × 104/μL (1), /μl (1), ×10^9/l (1), × 10^6/µL (1), K/uL (1), ×103/µL (1) | 150000–400000 /μL | Tietz 5th Ed |
| `Creatinine` | 138 / 127 | mg/dL (84), μmol/L (21), µmol/L (14), <unitless> (8), umol/L (3), g/24 h (2), g/L (1), mg/dl (1), mmol/L (1), mg/L (1), g/dl (1), U/L (1) | 0.74–1.35 mg/dL (male); 0.59–1.04 mg/dL (female) | Tietz 5th Ed |
| `CRP` | 119 / 115 | mg/L (74), mg/dL (36), <unitless> (4), nmol/L (2), mg/dl (2), ng/mL (1) | 0–1.0 mg/dL | Tietz 5th Ed |
| `ESR` | 78 / 77 | mm/h (54), mm/hr (21), <unitless> (3) | 0–15 mm/hr (male); 0–20 mm/hr (female) | Tietz 5th Ed |
| `Glucose_fasting` | 75 / 68 | mg/dL (51), mmol/L (15), g/L (2), <unitless> (2), mg/dl (2), μmol/L (1), mg/L (1), g/dL (1) | 70–100 mg/dL | ADA 2023 |
| `ALT` | 74 / 72 | U/L (53), IU/L (17), <unitless> (2), u/L (1), U/l (1) | 7–56 U/L | Tietz 5th Ed |
| `AST` | 74 / 72 | U/L (54), IU/L (15), <unitless> (4), U/l (1) | 10–40 U/L | Tietz 5th Ed |
| `Neutrophils_abs` | 64 / 58 | % (29), <unitless> (13), /μL (5), × 109/L (4), × 10^9/L (4), ×10^9/L (4), /µL (2), ×10^3/µL (1), × 10^3/µL (1), × 10^3/μL (1) | 1500–8000 /μL | Tietz 5th Ed |
| `BUN` | 58 / 57 | mg/dL (48), mmol/L (6), g/L (1), <unitless> (1), mg/L (1), mg/dl (1) | 7–20 mg/dL | Tietz 5th Ed |
| `ALP` | 55 / 52 | U/L (43), IU/L (10), <unitless> (2) | 44–147 U/L | Tietz 5th Ed |
| `Sodium` | 53 / 49 | mmol/L (26), mEq/L (22), <unitless> (5) | 136–145 mEq/L | Tietz 5th Ed |
| `Potassium` | 52 / 52 | mEq/L (25), mmol/L (24), <unitless> (2), mmol/l (1) | 3.5–5.0 mEq/L | Tietz 5th Ed |
| `Lymphocytes_abs` | 50 / 47 | % (28), <unitless> (8), /μL (4), /mm3 (4), × 10^9/L (3), × 109/L (2), cells/μL (1) | 1000–4800 /μL | Tietz 5th Ed |
| `Albumin` | 49 / 47 | g/L (24), g/dL (21), g/dl (2), g/l (1), mg/dL (1) | 3.5–5.5 g/dL | Tietz 5th Ed |
| `Hematocrit` | 47 / 39 | % (44), <unitless> (3) | 38.3–48.6 % (male); 35.5–44.9 % (female) | Tietz 5th Ed |
| `Total_bilirubin` | 47 / 45 | mg/dL (29), μmol/L (10), µmol/L (2), <unitless> (2), umol/L (1), μmoL/l (1), mg/dl (1), g/dL (1) | 0.1–1.2 mg/dL | Tietz 5th Ed |
| `Bicarbonate` | 43 / 39 | mmol/L (20), mEq/L (15), <unitless> (5), mm Hg (1), meq/L (1), mmHg (1) | 22–29 mEq/L | Tietz 5th Ed |
| `LDH` | 43 / 42 | U/L (34), <unitless> (3), IU/L (3), mmol/L (1), U/l (1), mg/dL (1) | 140–280 U/L | Tietz 5th Ed |
| `Calcium` | 40 / 35 | mg/dL (21), mmol/L (10), <unitless> (8), S (1) | 8.5–10.5 mg/dL | Tietz 5th Ed |
| `Lactate` | 35 / 35 | mmol/L (31), mg/dL (2), <unitless> (1), mEq/L (1) | 0.5–2.2 mmol/L | Tietz 5th Ed |
| `MCV` | 35 / 34 | fL (20), <unitless> (13), fl (2) | 80–100 fL | Tietz 5th Ed |
| `INR` | 31 / 30 | <unitless> (31) | 0.8–1.1 | Tietz 5th Ed |
| `Chloride` | 29 / 28 | mEq/L (15), mmol/L (11), <unitless> (3) | 98–106 mEq/L | Tietz 5th Ed |
| `D-dimer` | 26 / 25 | μg/mL (7), µg/mL (6), mg/L (5), ng/mL (4), ng/ml (2), nmol/L (1), mg/l (1) | 0–500 ng/mL FEU | MAYO_DDIMER_FEU |
| `BNP` | 25 / 25 | pg/mL (16), ng/L (4), pg/ml (2), <unitless> (1), ng/dL (1), pg (1) | 0–100 pg/mL | Tietz 5th Ed |
| `Eosinophils_abs` | 23 / 19 | % (13), <unitless> (6), /uL (1), × 10^9/L (1), cells/µL (1), cells/mm3 (1) | 15–500 /μL | Tietz 5th Ed |
| `Ferritin` | 23 / 23 | ng/mL (15), µg/L (2), ng/ml (2), <unitless> (2), ng/L (1), pmol/L (1) | 12–300 ng/mL (male); 12–150 ng/mL (female) | Tietz 5th Ed |
| `Arterial_PCO2` | 21 / 21 | mmHg (15), mm Hg (5), kPa (1) | 33–45 mmHg | NBME_2026 |
| `RBC` | 20 / 20 | <unitless> (10), /µL (3), × 1012/L (2), cells/μL (1), × 104/μL (1), × 109/L (1), × 10^12/L (1), × 10^6/μL (1) | 4.7–6.1 ×10^6/μL (male); 4.2–5.4 ×10^6/μL (female) | Tietz 5th Ed |
| `Arterial_PO2` | 19 / 19 | mmHg (14), mm Hg (4), kPa (1) | 75–105 mmHg | NBME_2026 |
| `PT` | 18 / 18 | s (8), seconds (6), sec (3), % (1) | 11.0–13.5 seconds | Tietz 5th Ed |
| `Procalcitonin` | 18 / 18 | ng/mL (13), ng/ml (3), ng/dL (1), μg/L (1) | 0–0.1 ng/mL | Tietz 5th Ed |
| `GFR` | 17 / 17 | mL/min (10), mL/min/1.73 m2 (3), <unitless> (2), s (1), ml/min (1) | 90–120 mL/min/1.73m2 | KDIGO 2012 |
| `HbA1c` | 17 / 16 | % (16), g/dL (1) | 4.0–5.6 % | ADA 2023 |
| `Phosphorus` | 17 / 12 | mmol/L (9), mg/dL (6), <unitless> (2) | 2.5–4.5 mg/dL | Tietz 5th Ed |
| `aPTT` | 17 / 16 | s (10), seconds (4), sec (2), <unitless> (1) | 25–35 seconds | Tietz 5th Ed |
| `Monocytes_abs` | 14 / 13 | % (12), ×10^9/L (2) | 200–950 /μL | Tietz 5th Ed |
| `Troponin_I` | 14 / 14 | ng/mL (8), μg/L (2), pg/mL (2), ng/ml (1), mg/L (1) | 0–0.04 ng/mL | Tietz 5th Ed |
| `Direct_bilirubin` | 13 / 13 | mg/dL (5), μmol/L (4), <unitless> (2), µmol/L (1), umol/L (1) | 0.0–0.3 mg/dL | Tietz 5th Ed |
| `Beta_hCG` | 12 / 10 | mIU/mL (6), <unitless> (2), IU/L (2), mIU/L (1), µIU/mL (1) | <1.0 U/L; <7.0 U/L; <1.4 U/L | ABIM_2026 |
| `CEA` | 12 / 12 | ng/mL (9), ng/ml (1), µg/l (1), <unitless> (1) | 0–2.5 ng/mL | ABIM_2026 |
| `PTH` | 12 / 11 | pg/mL (4), ng/L (4), pmol/L (3), pg/ml (1) | 15–65 pg/mL | Tietz 5th Ed |
| `Reticulocytes` | 12 / 12 | % (12) | 0.5–2.5 % | Tietz 5th Ed |
| `Troponin_T` | 12 / 12 | ng/mL (7), µg/L (2), μg/L (1), ng/ml (1), ng/L (1) | 0–0.01 ng/mL | ABIM_2026 |
| `Urea` | 12 / 12 | mmol/L (8), mg/dL (4) | 2.5–7.8 mmol/L | NHS_UREA |
| `CD4_count` | 11 / 11 | cells/µL (4), cells/mm3 (2), <unitless> (2), /μL (1), cells/uL (1), cells/μL (1) | ≥500 /μL | NBME_2026 |
| `CPK` | 11 / 11 | U/L (11) | 39–308 U/L (male); 26–192 U/L (female) | Tietz 5th Ed |
| `GGT` | 11 / 11 | U/L (9), IU/L (2) | 0–65 U/L | Tietz 5th Ed |
| `Lipase` | 11 / 11 | U/L (9), <unitless> (2) | 0–160 U/L | Tietz 5th Ed |
| `Magnesium` | 11 / 11 | mmol/L (5), mEq/L (2), mg/dL (2), <unitless> (1), g/L (1) | 1.7–2.2 mg/dL | Tietz 5th Ed |
| `Amylase` | 10 / 9 | U/L (9), IU/L (1) | 28–100 U/L | Tietz 5th Ed |
| `CA_125` | 10 / 10 | U/mL (6), <unitless> (1), U/ml (1), g/dL (1), KIU/l (1) | 0–35 U/mL | ABIM_2026 |
| `Total_protein` | 10 / 10 | g/dL (4), g/L (3), mg/dL (1), mg/L (1), g/l (1) | 6.0–8.3 g/dL | Tietz 5th Ed |
| `Triglycerides` | 10 / 9 | mg/dL (7), mmol/L (2), mmol/l (1) | 0–150 mg/dL | ATP III |
| `Anion_gap` | 9 / 9 | <unitless> (6), mmol/L (3) | 8–12 mEq/L | Tietz 5th Ed |
| `Immunoglobulin_IgG` | 9 / 9 | mg/dL (5), mg/L (1), g/L (1), <unitless> (1), U/mL (1) | 650–1500 mg/dL | NBME_2026 |
| `PSA` | 9 / 9 | ng/mL (5), ng/ml (3), μg/L (1) | local/context required | ABIM_2026, AUA 2023 |
| `Vitamin_D` | 9 / 7 | ng/mL (5), nmol/L (4) | 30–100 ng/mL | Endocrine Society 2011 |
| `CA_19_9` | 8 / 8 | U/mL (5), U/L (1), U/ml (1), KIU/l (1) | 0–37 U/mL | ABIM_2026 |
| `Cortisol_AM` | 8 / 5 | <unitless> (3), μg/dL (2), nmol/L (2), μg/24 h (1) | 6.2–19.4 μg/dL | Tietz 5th Ed |
| `NT_proBNP` | 8 / 8 | pg/mL (5), ng/L (1), pg/ml (1), <unitless> (1) | <=300 pg/mL; >=450 pg/mL; >=900 pg/mL | ABIM_2026 |
| `Osmolality_serum` | 8 / 5 | mOsm/kg (5), mOsm/kg H2O (2), mOsmol/kg H2O (1) | 275–295 mOsm/kg | Tietz 5th Ed |
| `Complement_C3` | 7 / 7 | mg/dL (5), g/L (2) | 100–233 mg/dL | ABIM_2026 |
| `Fibrinogen` | 7 / 7 | g/L (3), mg/dL (2), μmol/L (1), <unitless> (1) | 200–400 mg/dL | Tietz 5th Ed |
| `Prolactin` | 7 / 7 | ng/mL (5), μg/L (1), ng/ml (1) | 4.0–15.2 ng/mL (male); 4.8–23.3 ng/mL (female) | Tietz 5th Ed |
| `Total_cholesterol` | 7 / 5 | mg/dL (5), mmol/l (1), <unitless> (1) | 0–200 mg/dL | ATP III |
| `AFP` | 6 / 6 | ng/mL (2), ng/ml (2), µg/l (1), IU/mL (1) | 0–10 ng/mL | Tietz 5th Ed |
| `Complement_C4` | 6 / 6 | mg/dL (4), g/L (1), mg/L (1) | 14–48 mg/dL | ABIM_2026 |
| `TSH` | 6 / 5 | <unitless> (3), IU/mL (2), mIU/L (1) | 0.4–4.0 mIU/L | Tietz 5th Ed |
| `Uric_acid` | 6 / 6 | mg/dL (4), <unitless> (1), μmol/L (1) | 3.4–7.0 mg/dL (male); 2.4–6.0 mg/dL (female) | Tietz 5th Ed |
| `Free_T4` | 5 / 5 | pmol/L (2), ng/dL (2), pg/ml (1) | 0.8–1.8 ng/dL | Tietz 5th Ed |
| `Haptoglobin` | 5 / 5 | mg/dL (5) | 30–200 mg/dL | Tietz 5th Ed |
| `Immunoglobulin_IgE` | 5 / 5 | <unitless> (3), μg/L (1), IU/ml (1) | 0–380 IU/mL | NBME_2026 |
| `Immunoglobulin_IgM` | 5 / 4 | <unitless> (3), U/ml (1), g/dL (1) | 50–300 mg/dL | NBME_2026 |
| `LDL` | 5 / 2 | mg/dL (5) | 0–100 mg/dL | ATP III |
| `Rheumatoid_factor` | 5 / 5 | IU/mL (3), kIU/L (1), U/mL (1) | 0–24 IU/mL | ABIM_2026 |
| `Troponin_I_hs` | 5 / 5 | ng/mL (3), pg/mL (2) | 0–15 ng/L (female); 0–20 ng/L (male) | ABIM_2026 |
| `Vitamin_B12` | 5 / 5 | pmol/L (3), pg/mL (1), ng/L (1) | 200–900 pg/mL | Tietz 5th Ed |
| `CSF_glucose` | 4 / 4 | mmol/L (2), mg/dL (2) | 40–70 mg/dL | NBME_2026 |
| `CSF_protein` | 4 / 4 | mg/L (1), mg/l (1), g/L (1), mg/dL (1) | ≤40 mg/dL | NBME_2026 |
| `FSH` | 4 / 4 | IU/L (2), mIU/mL (2) | 2–9 mIU/mL (female_follicular_or_luteal); 4–22 mIU/mL (female_midcycle); >30 mIU/mL | ABIM_2026 |
| `Immunoglobulin_IgG4` | 4 / 4 | mg/dL (4) | 2.4–121.0 mg/dL | MAYO_IGG4 |
| `Indirect_bilirubin` | 4 / 4 | mg/dL (4) | 0.1–0.8 mg/dL | Tietz 5th Ed |
| `Interleukin_6` | 4 / 3 | pg/mL (4) | local/context required | LOINC_2_82 |
| `LH` | 4 / 4 | IU/L (2), mIU/mL (2) | 1–12 mIU/mL (female_follicular_or_luteal); 9–80 mIU/mL (female_midcycle); >30 mIU/mL | ABIM_2026 |
| `Urine_protein_24h` | 4 / 4 | <unitless> (2), mg/dL (1), g/24h (1) | 0–100 mg/24h | ABIM_2026 |
| `Arterial_pH` | 3 / 3 | <unitless> (3) | 7.35–7.45 {pH} | NBME_2026 |
| `Beta_hydroxybutyrate` | 3 / 3 | mmol/L (2), <unitless> (1) | 0–0.4 mmol/L | ABIM_2026 |
| `Estradiol` | 3 / 3 | pmol/L (1), pg/ml (1), pg/mL (1) | 10–180 pg/mL (female_follicular); 100–300 pg/mL (female_midcycle); 40–200 pg/mL (female_luteal) | ABIM_2026 |
| `Ionized_calcium` | 3 / 3 | mg/dL (2), mmol/L (1) | 1.16–1.31 mmol/L | ABIM_2026 |
| `Iron` | 3 / 3 | μmol/L (1), µmol/L (1), <unitless> (1) | 60–170 μg/dL | Tietz 5th Ed |
| `Testosterone_total` | 3 / 3 | ng/dL (2), nmol/L (1) | 18–54 ng/dL (female); 291–1100 ng/dL (male) | ABIM_2026 |
| `Troponin_T_hs` | 3 / 3 | ng/L (3) | 0–10 ng/L (female); 0–15 ng/L (male) | ABIM_2026 |
| `ACTH` | 2 / 2 | ng/L (1), pg/mL (1) | 10–60 pg/mL | ABIM_2026 |
| `Adenosine_deaminase` | 2 / 2 | U/L (2) | local/context required | LOINC_2_82 |
| `Aldolase` | 2 / 2 | U/L (2) | 0.8–3.0 IU/mL | ABIM_2026 |
| `Anti_thyroglobulin_antibody` | 2 / 2 | IU/mL (1), U/mL (1) | 0–20 U/mL | ABIM_2026 |
| `CK_MB` | 2 / 2 | U/L (2) | 0–5 ng/mL | Tietz 5th Ed |
| `Digoxin_level` | 2 / 2 | ng/mL (1), nmol/L (1) | local/context required | LOINC_2_82 |
| `EBV_DNA` | 2 / 2 | IU/mL (1), <unitless> (1) | local/context required | LOINC_2_82 |
| `Gastrin` | 2 / 2 | ng/L (1), pg/mL (1) | 0–100 pg/mL | ABIM_2026 |
| `Globulin` | 2 / 2 | g/L (1), g/l (1) | 2.3–3.5 g/dL | NBME_2026 |
| `Growth_hormone` | 2 / 2 | ng/mL (2) | 0–5 ng/mL | ABIM_2026 |
| `Homocysteine` | 2 / 2 | µmol/L (1), μmol/L (1) | 5–15 μmol/L | Tietz 5th Ed |
| `Immunoglobulin_IgA` | 2 / 2 | mg/L (1), g/L (1) | 76–390 mg/dL | NBME_2026 |
| `Interferon_gamma` | 2 / 1 | pg/mL (2) | local/context required | LOINC_2_82 |
| `MCH` | 2 / 2 | pg (2) | 27–33 pg | Tietz 5th Ed |
| `Methemoglobin` | 2 / 2 | % (2) | 0.5–3.0 % | ABIM_2026 |
| `Sirolimus_level` | 2 / 2 | ng/mL (1), ng/ml (1) | local/context required | LOINC_2_82 |
| `Zinc` | 2 / 2 | μg/dL (2) | 60–120 μg/dL | Tietz 5th Ed |
| `ACE` | 1 / 1 | U/L (1) | 8–53 U/L | ABIM_2026 |
| `Ammonia` | 1 / 1 | μmol/L (1) | 15–45 μg/dL | Tietz 5th Ed |
| `Amyloid_beta_40` | 1 / 1 | pg/mL (1) | local/context required | LOINC_2_82 |
| `Anti_factor_Xa` | 1 / 1 | IU/mL (1) | 0.3–0.7 IU/mL (unfractionated_heparin_therapeutic) | ABIM_2026 |
| `Ascites_cell_count` | 1 / 1 | /μL (1) | local/context required | LOINC_2_82 |
| `Basophils_abs` | 1 / 1 | % (1) | 0–200 /μL | Tietz 5th Ed |
| `Beta_D_glucan` | 1 / 1 | pg/mL (1) | 0–60 pg/mL | ABIM_2026 |
| `CA_50` | 1 / 1 | U/mL (1) | local/context required | LOINC_2_82 |
| `CD8_count` | 1 / 1 | /μL (1) | 430–1060 /μL | ABIM_2026 |
| `CSF_blast_count` | 1 / 1 | × 106/L (1) | local/context required | LOINC_2_82 |
| `Folate` | 1 / 1 | nmol/L (1) | 2.7–17.0 ng/mL | Tietz 5th Ed |
| `Free_T3` | 1 / 1 | pg/ml (1) | 2.3–4.2 pg/mL | Tietz 5th Ed |
| `HDL` | 1 / 1 | mg/dL (1) | 40–60 mg/dL | ATP III |
| `Interleukin_8` | 1 / 1 | pg/mL (1) | local/context required | LOINC_2_82 |
| `Iodine_serum` | 1 / 1 | ng/mL (1) | local/context required | LOINC_2_82 |
| `KL_6` | 1 / 1 | U/mL (1) | local/context required | LOINC_2_82 |
| `MCHC` | 1 / 1 | g/dl (1) | 32–36 g/dL | Tietz 5th Ed |
| `Mercury_blood` | 1 / 1 | μg/L (1) | 0–10 ng/mL | MAYO_MERCURY_BLOOD |
| `Methylmalonic_acid` | 1 / 1 | μmol/L (1) | 0–0.4 μmol/L | ABIM_2026 |
| `Monoclonal_protein` | 1 / 1 | mg/dL (1) | local/context required | LOINC_2_82 |
| `Myoglobin` | 1 / 1 | ng/mL (1) | 0–85 ng/mL | Tietz 5th Ed |
| `Olanzapine_level` | 1 / 1 | ng/mL (1) | local/context required | LOINC_2_82 |
| `RDW` | 1 / 1 | % (1) | 11.5–14.5 % | Tietz 5th Ed |
| `Soluble_CD25` | 1 / 1 | U/mL (1) | local/context required | LOINC_2_82 |
| `TIBC` | 1 / 1 | <unitless> (1) | 250–370 μg/dL | Tietz 5th Ed |
| `TNF_alpha` | 1 / 1 | pg/mL (1) | local/context required | LOINC_2_82 |
| `Tacrolimus_level` | 1 / 1 | ng/ml (1) | local/context required | LOINC_2_82 |
| `Total_T3` | 1 / 1 | ng/dL (1) | 100–200 ng/dL | NBME_2026 |
| `Total_T4` | 1 / 1 | <unitless> (1) | 5–12 μg/dL | NBME_2026 |
| `Total_bile_acids` | 1 / 1 | μmol/L (1) | local/context required | LOINC_2_82 |
| `Transferrin_saturation` | 1 / 1 | % (1) | 20–50 % | Tietz 5th Ed |
| `Valproate_level` | 1 / 1 | mg/L (1) | local/context required | LOINC_2_82 |

## Reference sources

| ID | Source | Version/use |
|---|---|---|
| `Tietz 5th Ed` | [Tietz Textbook of Clinical Chemistry and Molecular Diagnostics](https://shop.elsevier.com/books/tietz-textbook-of-clinical-chemistry-and-molecular-diagnostics/burtis/978-1-4160-6164-9) | 5th edition, 2011; ISBN 978-1-4160-6164-9; Legacy source recorded by the pre-existing catalog; values retained for backward compatibility and not re-derived in this extension. |
| `ATP III` | [Third Report of the NCEP Expert Panel (Adult Treatment Panel III), Final Report](https://www.nhlbi.nih.gov/files/docs/resources/heart/atp-3-cholesterol-full-report.pdf) | NIH Publication No. 02-5215, September 2002; Legacy lipid decision limits recorded by the pre-existing catalog; retained for backward compatibility. |
| `ADA 2023` | [Classification and Diagnosis of Diabetes: Standards of Care in Diabetes—2023](https://diabetesjournals.org/care/article/46/Supplement_1/S19/148056/2-Classification-and-Diagnosis-of-Diabetes) | Diabetes Care 2023;46(Suppl. 1):S19-S40; Legacy fasting-glucose and HbA1c limits recorded by the pre-existing catalog; retained for backward compatibility. |
| `AUA 2023` | [Early Detection of Prostate Cancer: AUA/SUO Guideline](https://www.auanet.org/documents/Guidelines/PDF/Early%20Detection%20Prostate%20Cancer/EDPC%20Unabridged%20FINAL.pdf) | 2023; Legacy PSA source label recorded by the pre-existing catalog. PSA thresholds are context-dependent; the value is retained only for backward compatibility. |
| `KDIGO 2012` | [KDIGO 2012 Clinical Practice Guideline for the Evaluation and Management of Chronic Kidney Disease](https://kdigo.org/wp-content/uploads/2017/02/KDIGO_2012_CKD_GL.pdf) | 2012/2013; Legacy GFR source recorded by the pre-existing catalog; retained for backward compatibility. |
| `Endocrine Society 2011` | [Evaluation, Treatment, and Prevention of Vitamin D Deficiency](https://www.endocrine.org/clinical-practice-guidelines/vitamin-d-for-prevention-of-disease) | 2011; superseded for disease prevention by the 2024 guideline; Legacy vitamin-D interval recorded by the pre-existing catalog. The 2024 guideline no longer endorses a universal target for healthy adults; retained only for backward compatibility. |
| `NBME_2026` | [NBME Laboratory Values](https://www.nbme.org/wp-content/uploads/2026/04/NBME_Laboratory_Reference_Values.pdf) | April 2026; Primary conventional and SI adult fallback intervals for common chemistry, hematology, arterial blood gas, CSF, thyroid, iron, and immunoglobulin tests. |
| `ABIM_2026` | [ABIM Laboratory Test Reference Ranges](https://www.abim.org/media/e2wdwdqu/laboratory-reference-ranges.pdf) | January 2026; Adult fallback intervals and explicitly stratified decision limits absent from NBME, including complement, tumor markers, high-sensitivity troponin, hormones, and NT-proBNP. |
| `MSD_2026` | [Laboratory Reference Ranges](https://www.merckmanuals.com/professional/resources/normal-laboratory-values/laboratory-reference-ranges) | May 2026; Cross-check and policy support: reporting-laboratory intervals supersede generalized tables. |
| `MAYO_DDIMER_FEU` | [D-Dimer, Plasma (DIMER)](https://www.mayocliniclabs.com/test-catalog/overview/602174) | Method-specific FEU cutoff of 500 ng/mL for citrated plasma. |
| `MAYO_IGG4` | [IgG4, Immunoglobulin Subclasses, Serum (IGGS4)](https://www.mayocliniclabs.com/test-catalog/overview/84250) | Method-specific adult serum IgG4 interval of 2.4-121.0 mg/dL and LOINC 2469-5. |
| `MAYO_MERCURY_BLOOD` | [Mercury, Blood (HG)](https://www.mayocliniclabs.com/test-catalog/overview/8618) | Whole-blood mercury method and reference value below 10 ng/mL (numerically equivalent to μg/L). |
| `ASH_DDIMER_UNITS` | [COVID-19 and D-dimer: Frequently Asked Questions](https://www.hematology.org/covid-19/covid-19-and-d-dimer) | 2020-04-20; Safety rule: keep FEU and DDU distinct and do not convert between them without assay validation. |
| `NHS_UREA` | [Urea](https://www.nbt.nhs.uk/severn-pathology/requesting/test-information/urea) | Adult serum/plasma urea fallback interval of 2.5-7.8 mmol/L. |
| `LOINC_2_82` | [Logical Observation Identifiers Names and Codes](https://loinc.org/) | 2.82; Analyte, specimen, scale, method, and unit identity. LOINC does not supply universal reference intervals. |
| `UCUM_2_2` | [Unified Code for Units of Measure Specification](https://ucum.org/ucum) | Specification 2.2, June 2024; NLM validator 4.1.8, 2026-06-17; Canonical unit semantics and exact metric-prefix/volume conversions; analyte-specific molar-mass factors remain explicitly curated. |
| `LOINC2HPO_2026_07_19` | [loinc2hpoAnnotation](https://github.com/TheJacksonLaboratory/loinc2hpoAnnotation) | LOINC result-direction to HPO mappings. |
| `HPO_2026_06_23` | [Human Phenotype Ontology](https://purl.obolibrary.org/obo/hp.obo) | 2026-06-23; HPO labels corresponding to loinc2hpo identifiers. |

## Reproduction

```bash
pip install -e '.[lab-audit]'
python scripts/download_lab_audit_datasets.py
python scripts/extend_lab_reference_data.py --check
python scripts/audit_lab_reference_coverage.py
```

The committed snapshots and downloader are pinned by revision, byte count, and SHA-256. Each dataset retains its upstream terms; see the dataset README and manifest before reuse or redistribution.

## Safety and limitations

- This is a conservative regex and alias audit, not a clinical NLP gold standard; prose-only and unusually formatted measurements may be missed.
- An unsupported unit can be a dataset extraction error, a method-specific unit, or a missing conversion; it is never numerically compared by the runtime.
- Tumor markers, high-sensitivity troponin, D-dimer, reproductive hormones, and NT-proBNP require method or clinical context even when representative limits are listed.
- Raw benchmark files are checksum-verified locally and are not redistributed by this repository.
