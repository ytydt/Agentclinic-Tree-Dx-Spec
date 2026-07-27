# Track C (R4/R5) ABSENT-only smoke

- generated: `2026-07-23T20:13:59.064857+00:00`

## Upper bound (offline, gold-blind proposals → keyword accommodate)

| arm | helped ABSENT (upper) | verdict |
|-----|----------------------:|---------|
| R4-imedrag | 1/2 | PASS_UPPER |
| R5-dual | 0/2 | REJECT_UPPER |
| R5-mac | 1/2 | PASS_UPPER |

### Per-case accommodating proposals

#### R4-imedrag
- case 67: upper=False hits=[] top2=['Conduction System Disease', 'Sinus Node Disease']
- case 231: upper=True hits=['Urothelial carcinoma'] top2=['Florid cutaneous papillomatosis', 'Urothelial carcinoma']

#### R5-dual
- case 67: upper=False hits=[] top2=['Bradycardia', 'Respiratory Failure']
- case 231: upper=False hits=[] top2=['Invasive Carcinoma with Focal Squamous Differentiation', 'Tylosis with Oesophageal Cancer']

#### R5-mac
- case 67: upper=True hits=['Severe Infection'] top2=['Bradycardia', 'Severe Infection']
- case 231: upper=False hits=[] top2=['Acrokeratosis paraneoplastica (Bazex syndrome)', 'Paraneoplastic pemphigus']

## Live inject (ABSENT-only)

- model: `meta-llama/llama-3.3-70b-instruct`
- live_pass_lite: **False**
- production default: **REJECT_DEFAULT_KEEP_OFF**
- claim_allowed_for_main_table: `False`

| arm | helped live | pass_lite |
|-----|------------:|:---------:|
| R4-imedrag | 0/2 | False |
| R5-mac | 0/2 | False |

- R4-imedrag case 231: accommodates=False l1=['Paraneoplastic Syndrome with Cutaneous Manifestation', 'Infectious Etiology with Cutaneous Involvement', 'Inflammatory Etiology with Cutaneous Involvement', 'Genetic Predisposition with Cutaneous Manifestation', ' OTHER']
- R5-mac case 67: accommodates=False l1=['Infectious Process', 'Cardiovascular Event', 'Neurological Disorder', 'Metabolic or Endocrine Disorder', 'Other']

## Conclusion

- Track C **must not** be default production path for full cohort (90% MISS are UNBIND).
- Even PASS-lite on ABSENT is **not** a main-table AutoCoverage claim.
- Upper default_production: **REJECT**
