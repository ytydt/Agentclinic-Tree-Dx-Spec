# DA / d2_heldout100 / case 299

- **gold**: Exophytic Schneiderian papilloma
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01= APHHM=1
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `near_synonym_prefer`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=0

## Vignette
A man in his 30s presented with a mass in the right nostril that had been growing for about 1 year. The lesion bled with minimal trauma but did not obstruct his breathing. The patient did not smoke and denied any medical history of chronic rhinosinusitis.

Physical examination revealed a 1-cm, nontender, exophytic, verrucous, skin-colored plaque on the right nasal vestibule.

- Histologic examination:  Image Title: Histologic sections (Figure C)  Image Description: Papillary fronds with slender fibrovascular cores that are lined by nonkeratinizing squamous epithelium (original magnification ×200)    Image Title: Higher magnification histology (Figure D)  Image Description: Shows mucin-containing goblet cells. Neither cytologic atypia nor atypical mitotic figures are present (original magnification ×400)    Clinical Images:  Image Title: Clinical presentation (Figure A and B)  Image Description: An exophytic, verrucous, and skin-colored plaque on the right nasal vestibule

What is the most likely diagnosis?

Options:
A. Nasal papilloma
B. Exophytic Schneiderian papilloma
C. Squamous Papilloma
D. Schneiderian papilloma (Inverted papilloma)


## Options
- A: Nasal papilloma
- B: Exophytic Schneiderian papilloma **←gold**
- C: Squamous Papilloma
- D: Schneiderian papilloma (Inverted papilloma) **←gold**

## Backbone e7

- S2 n=46 gold_rank=6
  - clusters: gold=1 near=4 other=41
- S3 shortlist (5):
  - [near] Inverted Papilloma
  - [gold] Schneiderian Papilloma
  - [other] Verrucous Carcinoma
  - [other] Squamous Cell Carcinoma
  - [near] Nasoethmoidal Papilloma
    - why_kept(Inverted Papilloma): Histologic examination shows papillary fronds with slender fibrovascular cores, consistent with inverted papilloma
    - why_kept(Schneiderian Papilloma): Papillary fronds and nonkeratinizing squamous epithelium are characteristic of Schneiderian papilloma
    - why_kept(Verrucous Carcinoma): Exophytic and verrucous appearance of the plaque, along with mucin-containing goblet cells, are consistent with verrucous carcinoma
    - why_kept(Squamous Cell Carcinoma): Nonkeratinizing squamous epithelium and presence of mucin-containing goblet cells could be seen in squamous cell carcinoma
    - why_kept(Nasoethmoidal Papilloma): Location on the right nasal vestibule and histologic features are consistent with nasoethmoidal papilloma
- S4 champion: **Inverted Papilloma** cluster=near jaccard=0.25
- S4 rationale: The presence of papillary fronds with slender fibrovascular cores lined by nonkeratinizing squamous epithelium and mucin-containing goblet cells, without cytologic atypia or atypical mitotic figures, is characteristic of inverted papilloma.
- S4 rejected:
  - [other] Verrucous Carcinoma: Verrucous carcinoma typically shows keratinizing squamous epithelium, which is not present in this case.
  - [other] Squamous Cell Carcinoma: Squamous cell carcinoma typically shows cytologic atypia and atypical mitotic figures, which are not present in this case.
  - [gold] Schneiderian Papilloma: Schneiderian papilloma is a broader category that includes inverted papilloma, but the specific histologic features described are more characteristic of inverted papilloma.
  - [near] Nasoethmoidal Papilloma: Nasoethmoidal papilloma is not a commonly recognized term, and the histologic features described are more consistent with inverted papilloma.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Schneiderian Papilloma', 'Inverted Papilloma']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Inverted Papilloma', 'Squamous Cell Carcinoma', 'Verrucous Carcinoma', 'Papillomatosis', 'Schneiderian Papilloma', 'Schneiderian Papilloma', 'Inverted Papilloma', 'Verrucous Carcinoma']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Inverted Papilloma', 'Squamous Papilloma']
- diagnose: ['Inverted Papilloma', 'Squamous Papilloma']
- queries: ['nasal vestibule mass', 'exophytic verrucous plaque', 'papillary fronds with fibrovascular cores', 'nonkeratinizing squamous epithelium']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=19 final_n=2
- final: ['Inverted Papilloma', 'Verrucous Carcinoma']
- tree gold_cluster_n=2 final gold=False

