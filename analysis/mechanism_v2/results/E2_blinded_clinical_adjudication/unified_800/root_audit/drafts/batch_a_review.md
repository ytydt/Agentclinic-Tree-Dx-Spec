# Batch A blinded root-audit review notes

## Frozen scope and review status

- Coverage: `U0001`-`U0134` (134/134 cards), preserving candidate order on each card.
- Inputs consulted: `ROOT_PROTOCOL.md` and lines 1-134 of `cards.jsonl` only.
- No external API or LLM call was used. No index, arm provenance, prior endpoint, leaderboard, mapping, or other adjudication was consulted.
- There are no `low`-confidence rows. There are 36 `medium`-confidence rows; all are enumerated below.

## Identity-level cases requiring second review

These decisions can change whether a candidate is evaluated against a uniquely identifiable full reference (`Q`) or against a family/unsupported reference (`F`/`S`).

| Case | Current | Review issue |
|---|---:|---|
| U0002 | Q | Organism plus immune-thrombocytopenia mechanism is strongly integrated, but the card does not display final species naming in the culture paragraph; confirm that morphology/dog bite is sufficient for the full causal label. |
| U0004 | F | Gastric broad nonseptate hyphae establish phycomycotic infection, but do not securely separate Mucorales from pythiosis/entomophthorales without culture or definitive histology. |
| U0006 | S | Disseminated B-cell lymphoma is clear; grade 3A follicular morphology and IVB staging are not independently displayed by the limited immunophenotype. |
| U0019 | S | Malignancy is plausible, but diffuse sausage pancreas/capsule and duct narrowing retain autoimmune pancreatitis as a serious mimic; no tissue diagnosis is shown. |
| U0023 | Q | Leptomeningeal lymphoma and plasmacytoid cells are compelling when integrated with prior LPL, but subtype depends on the historical hematologic diagnosis. |
| U0026 | Q | Fatty interatrial mass and SVC compression are direct; pathologic distinction between a discrete lipoma and lipomatous hypertrophy remains a terminology boundary. |
| U0027 | S | Infected mediastinal cyst is proven; bronchogenic histogenesis is not shown. |
| U0032 | F | Multifocal temporal/parietal osteolysis is highly suggestive of LCH, but there is no tissue confirmation. |
| U0034 | Q | Rare vascular nomenclature: verify that the described papillary CD31-positive/D2-40-negative lesion is papillary hemangioma rather than an angioendothelioma synonym dispute. |
| U0035 | Q | Dengue myositis is clinically coherent and rhabdomyolysis is definite, but the visible card summary should be checked for explicit dengue confirmation. |
| U0038 | Q | Topical steroid withdrawal and steroid-induced rosacea-like dermatitis overlap; current decision treats rebound after cessation as the defining discriminator. |
| U0040 | F | Otogenic fungal meningoencephalitis is supported; Candida tropicalis species evidence is not visible in the displayed microbiology details. |
| U0042 | Q | Atypical tuberous myxoedema is a rare scleromyxoedema variant; classification depends on deep mucin and clinical morphology. |
| U0044 | Q | Puffy-hand syndrome is supported by the sharply demarcated chronic edema and relevant exposure context; verify the IV-drug-use history is explicit on the card. |
| U0045 | S | Clear-cell sarcoma is suggested by deep soft-tissue melanocytic differentiation, but S100 is negative and no EWSR1 rearrangement is shown. |
| U0046 | Q | OCT-associated recurrent plaque erosion is plausible, but current OCT wording is not a fully explicit histologic confirmation. |
| U0062 | Q | Histology and somatic KDR variant support tufted angioma; check whether anti-VEGF-associated vascular proliferation changes the preferred entity name. |
| U0063 | Q | Infarcted epididymo-orchitis is clear; confirm that Pseudomonas culture is explicitly present rather than inferred from the reference. |
| U0064 | S | Acute pancreatitis is likely; normal CT does not exclude it, but linagliptin causation is not uniquely established by temporal association. |
| U0065 | S | CD56-positive intravascular NK-lineage lymphoma is supported, but “nasal type” requires EBV/lineage evidence not displayed. |
| U0066 | Q | Characteristic bilateral retinal crystals support the adverse phenotype; causality remains association after anastrozole exposure. |
| U0069 | Q | Serum sickness is the best post-streptokinase integrated diagnosis, although the key rash/arthralgia/complement details are only partly visible in the card summary. |
| U0073 | Q | Leukemia cutis is supported; assigning JMML depends on integrating NF1, extreme leukocytosis and the cutaneous myeloid phenotype. |
| U0075 | Q | aHUS versus TTP depends on ADAMTS13/complement workup not fully visible in the concise card fields. |
| U0079 | S | Myopericarditis and conduction disease are supported; partitioning causality between monkeypox and concurrent Lyme disease is not uniquely possible. |
| U0080 | Q | Metastatic Crohn disease is a diagnosis by integrated exclusion because luminal evaluation is normal; histologic granulomas and serology carry the classification. |
| U0083 | Q | Rowell syndrome versus SJS/bullous lupus is a recognized nosologic boundary; current decision follows targetoid EM-like eruption with lupus/interface context. |
| U0086 | Q | MIS-C with ischemic stroke is supported; “COVID cerebral vasculitis” was treated as a competing narrower mechanism rather than a complete equivalent. |
| U0090 | F | Exposure and spinal syndrome strongly indicate brucellosis, but explicit Brucella serology/culture is not visible in the card details reviewed. |
| U0092 | Q | Volitional, incentive-linked behavior favors malingering, but external incentive versus sick-role motivation should be explicitly confirmed when separating factitious disorder. |
| U0099 | F | Ocular phenotype fits MMP/OCP, but nonspecific conjunctival DIF prevents unique etiologic identification. |
| U0102 | F | Imaging strongly favors neurenteric cyst over the listed alternatives, but histologic confirmation is absent. |
| U0116 | Q | COVID-associated TAMOF is coherent; second review should verify separation from TTP and other pediatric thrombotic microangiopathies. |
| U0118 | Q | Neuro-Behcet classification depends on integrating systemic mucosal criteria with characteristic brainstem-diencephalic lesions. |
| U0122 | Q | Morphology and timing support a COVID-associated papulovesicular eruption, but causal attribution remains temporal/exclusion based. |
| U0125 | S | RBBB is definite; the complete causal chain from COPD exacerbation to hypoxemia to arrest is only partly demonstrated. |

## Candidate relations that can change complete versus partial counts

| Case/candidate | Current | Plausible alternative | Boundary rationale |
|---|---:|---:|---|
| U0004C02 gastric phycomycosis | C | P | Historical usage often means gastric mucormycosis, but “phycomycosis” can be broader. |
| U0012C02/C03 melanoma with perineural invasion | P | C | Neurotropism is captured; current `P` requires the reference's orbital-spread component to be explicitly named. |
| U0013C02 discoid lupus erythematosus | C | P | Current `C` treats the visible periorbital site as contextual rather than an indispensable label component. |
| U0019C01 pancreatic cancer | P | C | Current `P` preserves the histologic specificity of adenocarcinoma; ordinary clinical use often treats these as equivalent in this setting. |
| U0025C02 lacrimal-sac abscess | P | M | It is the localized infectious component of dacryocystitis, but not the secondary optic-nerve injury. |
| U0026C06 lipomatous hypertrophy with SVC obstruction | X | C/P | Site/effect match exactly, but true lipoma versus lipomatous hypertrophy is a pathologic distinction. |
| U0044C04 IV-drug-use scleroderma-like disorder | C | P | Current `C` treats this as a descriptive synonym of puffy-hand syndrome; it may be judged merely compatible if used nonspecifically. |
| U0046C03 MINOCA | P | M/X | MINOCA is a syndrome-level description; compatibility depends on whether the recorded stenosis meets the nonobstructive definition. |
| U0051C01/C02 NMOSD | C | P | Current `C` follows modern nomenclature in which AQP4-positive NMO lies within NMOSD. |
| U0052C05 arteriovenous malformation | P | X | A pial AVF is an arteriovenous shunt without a nidus; “AVM” may be read broadly or as a conflicting nidus lesion. |
| U0059C02/C03 alfuzosin DILI | C | C | Candidate is more etiologically specific than the generic reference, but the cause is strongly supplied by the card. |
| U0060C02/C04/C07 prostate-to-cerebellum metastasis | C | P | Semantically complete relative to the reference; identity remains `S` because origin is not proven on the card. |
| U0061C02 mucinous ovarian cyst | P | X | Broad compatible cyst label versus histologically conflicting mucinous classification. |
| U0062C04 hemangioma | P | X | “Hemangioma” may be used as a broad benign vascular parent, but tufted angioma is a distinct entity. |
| U0066C01/C02 crystalline maculopathy | C | P | Current `C` treats maculopathy as the site-specific form of crystalline retinopathy. |
| U0070C01-C04 sepsis labels | P | M/X | They are compatible systemic formulations of bacteremia, but may overstate organ dysfunction and omit species. |
| U0078C04 coccidioidomycosis meningitis | C | P | Current `C` treats the pseudo-SAH presentation as a modifier, not part of disease identity. |
| U0081C03 abducens palsy | C | P | Current `C` treats transient timing/procedural context as modifiers visible in the vignette. |
| U0085C01-C03 HLRCC | X | P | FH-deficient leiomyoma is a syndrome sentinel, but a tumor FH variant/loss does not by itself establish germline HLRCC. |
| U0086C05 COVID cerebral vasculitis | X | P | It may be a mechanism of the stroke, but the reference is the broader MIS-C-plus-stroke object and does not require proven vasculitis. |
| U0091C01/C02/C05 LMNA cardiomyopathy | P | C | Current `P` preserves the specific AV-block/tachyarrhythmia phenotype; LMNA cardiomyopathy is sometimes used as the full umbrella diagnosis. |
| U0097C02/C04 ICI/immune-related myocarditis | C | P | Sintilimab identity is contextually explicit, so current coding treats the class label as complete. |
| U0098C02 auricular angiosarcoma | C | C | Site-specific complete semantic match despite identity `S` from absent histology. |
| U0099C01 ocular cicatricial pemphigoid | C | P | OCP is generally the ocular form of MMP, but isolated ocular disease and negative DIF create etiologic uncertainty. |
| U0104C01 embryonal rhabdomyosarcoma | C | P | Current `C` treats the primary cutaneous site as supplied by the card rather than required in the candidate string. |
| U0110C01 base-of-tongue cyst | P | M | Correct anatomic cyst family but lacks thyroglossal embryology. |
| U0114C04 sildenafil allergic interstitial nephritis | C | P | It is semantically complete relative to AIN, although card-level identity is `S` because biopsy is absent. |
| U0116C01 myocarditis | M | P | Cardiac injury is a component; whether it reaches myocarditis is not explicit. |
| U0120C01/C02 internal hernia | P | C | Petersen hernia is a specific post-bypass internal hernia; current `P` requires anatomic defect specificity. |
| U0123C01 choriocarcinoma | P | C | Core histology is correct, but current `P` retains primary adrenal site and pulmonary metastatic extent as diagnostic components. |
| U0125C03/C05 COPD exacerbation | P | M | It is the proposed causal component but not the RBBB/arrest composite object. |
| U0128C01/C02 ARVC | P | X | Right-dominant disease is compatible with, but omits, demonstrated biventricular involvement; it would be conflicting only if interpreted as RV-exclusive. |
| U0131C03 primary urethral amyloidosis | C | P | Current `C` treats negative systemic workup as making “primary” equivalent to localized. |

## Recommended adjudicator attention order

1. Reference-validity decisions with direct endpoint impact: `U0008`, `U0015`, `U0019`, `U0028`-`U0030`, `U0033`, `U0037`, `U0045`, `U0050`, `U0052`, `U0054`-`U0055`, `U0060`-`U0061`, `U0064`-`U0065`, `U0074`, `U0076`-`U0077`, `U0079`, `U0082`, `U0087`-`U0089`, `U0093`, `U0098`-`U0102`, `U0106`-`U0107`, `U0109`-`U0111`, `U0114`-`U0115`, `U0117`, `U0125`, `U0127`, `U0130`, `U0132`.
2. Complete/partial semantic boundaries listed in the preceding table.
3. Rare-entity nomenclature cases: `U0004`, `U0034`, `U0042`, `U0062`, `U0083`, `U0099`, `U0100`.
