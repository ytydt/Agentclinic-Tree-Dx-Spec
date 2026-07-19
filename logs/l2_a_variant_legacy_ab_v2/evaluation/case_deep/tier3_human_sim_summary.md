# Tier-3 Human-Sim Medical Adjudication Summary (V2)

Reviewer: `cursor-grok-4.5-high-human-sim` (`human_sim_medical`)  
Source disagreements: `logs/l2_a_variant_matrix_v2/judge/tier3_true_disagreements.json` (n=55)  
Output: `logs/l2_a_variant_matrix_v2/judge/tier3_human_sim_decisions.json`

## Overall

| Side | Count |
|------|------:|
| Agrees tier1 | 17 |
| Agrees tier2 | 36 |
| Neither (S. aureus vs genus-level staph IE split) | 2 |
| Items with web-verified sources | 11 |
| Changed from AI proxy | 24 |

The prior AI proxy mostly rubber-stamped tier2 and **omitted many LeafQuality disagreements**. Human-sim re-judged from rubrics + medical knowledge.

## Most consequential medical disagreements

### 1. `matches_gold` — Epiglottitis vs pneumococcal epiglottitis (mxh011)

**Decision: false (agree tier2; overturns clinical “core diagnosis” intuition of tier1).**

Gold is **pneumococcal epiglottitis**. Unspecified *Epiglottitis* is the correct anatomic disease but lacks the required *S. pneumoniae* etiology. Under GoldMatch (“unambiguously satisfies”), broader disease ≠ match. Parent branch (URI/LRI/airway/etc.) does not change this.

### 2. `matches_gold` — Hyperparathyroidism vs primary hyperparathyroidism (mb77_hyperpara)

**Decision: false for bare Hyperparathyroidism; true for Parathyroid Carcinoma with Hyperparathyroidism.**

- Bare *Hyperparathyroidism* includes secondary/tertiary disease → **not** an unambiguous match to **primary** hyperparathyroidism.
- *Parathyroid carcinoma with hyperparathyroidism* is a recognized rare etiologic subtype of primary hyperparathyroidism (<1% of PHPT) → **matches_gold=true** ([StatPearls](https://www.ncbi.nlm.nih.gov/books/NBK519038/)).

### 3. `is_parent_valid` — Weill-Marchesani under marfanoid parent (mxh046)

**Decision: false (agree tier2).**

Weill-Marchesani features **short stature, brachydactyly, joint stiffness**—phenotypic opposite of marfanoid habitus—so it is not a plausible child of *Genetic Disorder with Marfanoid Features* ([GeneReviews](https://www.ncbi.nlm.nih.gov/books/NBK1114/)).

### 4. `is_parent_valid` — Homocystinuria under Connective Tissue Disorder (mxh046)

**Decision: false (agree tier2).**

CBS-deficiency homocystinuria is a **metabolic phenocopy** of Marfan/connective-tissue disease, not a primary connective-tissue disorder ([Orphanet](https://www.orpha.net/en/disease/detail/394?mode=name)).

### 5. `is_parent_valid` — Named syndromes under residual `Other` (mxh046)

**Decision: false for Marfan, Loeys-Dietz, EDS, Stickler, Homocystinuria/CBS deficiency, CDG, lysosomal/mitochondrial families (agree tier1).**

`Other` is a taxonomy residual, not a clinically coherent parent for named diseases—especially when connective-tissue/marfanoid/metabolic parents exist elsewhere in the tree.

### 6. `is_parent_valid` — Mycoplasma under Bacterial URI (mxh068)

**Decision: true (agree tier1; differs from tier2).**

CDC/StatPearls document that *M. pneumoniae* commonly causes **URI** (pharyngitis/tracheobronchitis) as well as atypical pneumonia, so the leaf is a plausible child of *Bacterial Upper Respiratory Infection* ([CDC](https://www.cdc.gov/mycoplasma/hcp/clinical-overview/index.html)).

### 7. `is_parent_valid` — Influenza under Acute Airway Obstruction (mxh068)

**Decision: false (agree tier2).**

Influenza is a systemic/respiratory infection, not a primary airway-obstruction diagnosis.

### 8. `is_specific_disease` — Foreign body vs Foreign Body Aspiration; Fibrillinoid; CDG

| Leaf | Decision | Rationale |
|------|----------|-----------|
| `foreign body` (bare) | **false** | Underspecified finding/mechanism prose |
| `Foreign Body Aspiration` | **true** | Accepted clinical/ICD entity |
| `Fibrillinoid syndrome` | **false** | Nonstandard; correct umbrella is *fibrillinopathy* |
| `Congenital Disorder of Glycosylation` | **false** | Disease **family**, not one specific entity |

### 9. Semantic clustering (high-impact splits)

- **NBTE = marantic endocarditis** → shared cluster (verified synonyms).
- **Bacterial/fungal/viral/parasitic sepsis** → separate clusters (reject tier1 over-merge).
- **S. aureus IE ≠ genus-level staphylococcal IE** → **neither** side; invented readable split clusters (tier2 over-merged CoNS-capable genus label with S. aureus).
- **ALL naming variants + lymphoblastic lymphoma** → shared tier2 ALL/LBL cluster (WHO leukemia/lymphoma spectrum).
- **Reactive leukocytosis subtypes** (stress/infectious/inflammatory/other) → keep separate (agree tier2).

## Field tally (agrees_with)

See `summary.by_field` in the JSON for exact counts.
