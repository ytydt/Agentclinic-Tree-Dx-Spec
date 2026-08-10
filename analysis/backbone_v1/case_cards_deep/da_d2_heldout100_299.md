# DA / d2_heldout100 / case 299

- **gold**: Exophytic Schneiderian papilloma
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=0 B06=1 B07=0 B01= APHHM=1
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_ok` B07=`draft_miss` B01=`na` APHHM=`tree_hit_final_drop`
- **primary_locus**: e7=s3_hit_s4_miss; B06=supervisor_ok
- **covariates**: vig_words=158; gold_words=3; eponym=False; subtype=False; e7_s2_rank=6; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A man in his 30s presented with a mass in the right nostril that had been growing for about 1 year. The lesion bled with minimal trauma but did not obstruct his breathing. The patient did not smoke and denied any medical history of chronic rhinosinusitis.  Physical examination revealed a 1-cm, nontender, exophytic, verrucous, skin-colored plaque on the right nasal vestibule.  - Histologic examination:  Image Title: Histologic sections (Figure C)  Image Description: Papillary fronds with slender ...

## Options
  - A: Nasal papilloma
  - B: Exophytic Schneiderian papilloma
  - C: Squamous Papilloma
  - D: Schneiderian papilloma (Inverted papilloma)

## Backbone e7
- S1 key_facts: The patient is a man in his 30s; The mass has been growing for about 1 year; The lesion bleeds with minimal trauma; The patient does not smoke; The patient denies any medical history of chronic rhinosinusitis; The mass does not obstruct breathing; The plaque is 1-cm in size and located on the right nasal vestibule; Histologic examination shows papillary fronds with slender fibrovascular cores
- S2 mode=complement k=3 pool_n=46 gold_in_s2=True
  - call1: ['Inverted Papilloma', 'Squamous Cell Carcinoma', 'Verrucous Carcinoma', 'Keratoacanthoma', 'Papillomatosis', 'Schneider
  - call2: ['Papillary Squamous Cell Carcinoma', 'Adenoid Cystic Carcinoma', 'Mucoepidermoid Carcinoma', 'Sinonasal Undifferentiate
  - call3: ['Papillary Squamous Cell Carcinoma with spindle cell features', 'Verrucous hyperplasia', 'Focal epithelial hyperplasia'
- S3 shortlist n=5 gold=True: Inverted Papilloma, Schneiderian Papilloma, Verrucous Carcinoma, Squamous Cell Carcinoma, Nasoethmoidal Papilloma
- S4 champion: **Inverted Papilloma** gold=False
- S4 raw (trunc): {"champion": "Inverted Papilloma", "rationale": "The presence of papillary fronds with slender fibrovascular cores lined by nonkeratinizing squamous epithelium and mucin-containing goblet cells, without cytologic atypia or atypical mitotic figures, is characteristic of inverted p

## Backbone v0 (compact)
- S1 key_facts: The patient is a man in his 30s; The mass has been growing for about 1 year; The lesion bleeds with minimal trauma; The patient does not smoke; The patient denies any medical history of chronic rhinosinusitis; The mass does not obstruct breathing; The plaque is 1-cm, nontender, exophytic, verrucous, and skin-colored; Histologic examination shows papillary fronds with slender fibrovascular cores l
- S2 mode=single k=1 pool_n=16 gold_in_s2=True
  - call1: ['Inverted Papilloma', 'Squamous Cell Carcinoma', 'Verrucous Carcinoma', 'Keratoacanthoma', 'Papillomatosis', 'Schneider
- S3 shortlist n=5 gold=True: Inverted Papilloma, Schneiderian Papilloma, Verrucous Carcinoma, Squamous Cell Carcinoma, Nasoethmoidal Papilloma
- S4 champion: **Inverted Papilloma** gold=False
- S4 raw (trunc): {"champion": "Inverted Papilloma", "rationale": "The presence of papillary fronds with slender fibrovascular cores lined by nonkeratinizing squamous epithelium and mucin-containing goblet cells, without cytologic atypia or atypical mitotic figures, is consistent with the histolog

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation of a mass in the right nostril with a history of bleeding and the histologic examination showing papillary fronds with slender fibrov
  - turn1 gold_mention=True diag=
    The presence of mucin-containing goblet cells and the lack of cytologic atypia or atypical mitotic figures support the diagnosis of a Schneiderian papilloma, wh
  - turn2 gold_mention=True diag=
    The histologic findings of papillary fronds with slender fibrovascular cores lined by nonkeratinizing squamous epithelium and the presence of mucin-containing g
- supervisor votes=3 top2=['Schneiderian Papilloma', 'Inverted Papilloma'] gold=True

## Baseline B07
- draft=['Inverted Papilloma', 'Squamous Papilloma'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['nasal vestibule mass', 'exophytic verrucous plaque', 'papillary fronds with fibrovascular cores', 'nonkeratinizing squamous epithelium']
- diagnose=['Inverted Papilloma', 'Squamous Papilloma'] gold=False

## APHHM
- tree_n=19 tree_recall=True
- gold_leaf=B1.4:Papilloma parent=B1
- final_n=2 final_recall=False ranking=['Inverted Papilloma', 'Verrucous Carcinoma']
- human_at1=False fail_mode=prune_loss

