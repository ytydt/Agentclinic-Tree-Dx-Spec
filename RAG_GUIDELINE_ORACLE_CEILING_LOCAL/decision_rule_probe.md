# 决策流程分支的语料证据核验

## DA_d2_heldout200b/773 — PFO 不是大分流；Eisenmenger 需大缺损且 PVR 达体循环水平

- 用于排除：Eisenmenger Syndrome
- 匹配式：`eisenmenger AND \blarge\b AND (pulmonary vascular resistance|systemic (level|pressure))`
- 结果：命中（9 段）

- `merck` | Chapter 293. Congenital Cardiovascular Anomalies > Congenital Cardiovascular Ano
    Blood flows from left to right initially because systemic pressure and vascular resistance are
    higher than pulmonary artery pressure and resistance.
    If  untreated, elevated pulmonary artery pressure may lead to Eisenmenger's syndrome (.
    Large  left-to-right shunts (eg, large ventricular septal defect [VSD], patent ductus arteriosus
    [PDA]) cause  volume overload, which may lead to HF and during infancy often results in failure
    to thrive.

- `merck` | Chapter 293. Congenital Cardiovascular Anomalies > In infants, symptoms or signs
    Persistent moderate-to-large ASDs result in large shunts, leading to right atrial  and right
    ventricular volume overload and, over a number of years, pulmonary artery hypertension,
    elevated pulmonary vascular resistance, and right ventricular hypertrophy.
    Ultimately, the increase in the pulmonary artery pressure and vascular resistance may result in
    a  bidirectional atrial shunt with cyanosis during adulthood (Eisenmenger's reaction).

---

## MCR_seq200b/257 — Kanavel 四征定义化脓性屈肌腱鞘炎

- 用于排除：Pyogenic Flexor Tenosynovitis
- 匹配式：`kanavel AND (passive extension|fusiform|flexed position)`
- 结果：命中（5 段）

- `statpearls` | Pyogenic Flexor Tenosynovitis: Evaluation and Treatment Strategies. > Introducti
    Kanavel described 3 cardinal signs of pyogenic flexor tenosynovitis: flexor sheath tenderness,
    flexed position of the affected digit, and painful passive digital extension.
    Later, a fourth sign, fusiform swelling of the digit, was also added to become the 4 cardinal
    signs.[4]

- `statpearls` | Pyogenic Flexor Tenosynovitis: Evaluation and Treatment Strategies. > Differenti
    The other cardinal Kanavel signs of PFT, including finger fusiform swelling and flexor sheath
    tenderness, are usually absent.

---

## MCR_seq200b/257 — collar button / web-space 脓肿是独立实体

- 用于排除：Cellulitis
- 匹配式：`(collar[- ]button|web[- ]space) abscess`
- 结果：命中（4 段）

- `merck` | Chapter 43. Hand Disorders > History and physical examination findings are often
    Palm abscesses can include collar-button abscesses, thenar space abscesses, and midpalmar space
    abscesses.

- `textbooks` | Surgery_Schwartz
    / 1944Cubital Tunnel Syndrome / 1944Other Sites of Nerve Compression / 1945Degenerative Joint
    Disease 1945Small Joints (Metacarpophalangeal and Interphalangeal) 1945Wrist / 1945Rheumatoid
    Arthritis / 1946Dupuytren’s Contracture 1947Infections 1947Cellulitis / 1947Abscess /
    1948Collar-Button Abscess / 1948Osteomyelitis / 1949Pyogenic Arthritis / 1949Necrotizing
    Infections / 1949Infectious Flexor Te

---

## MCR_v1_seq100/74 — CPVT：肾上腺素能触发、QT 正常、心脏结构正常

- 用于排除：Long QT Syndrome
- 匹配式：`catecholaminergic polymorphic AND (normal (resting )?(qt|ecg|electrocardiogram)|structurally normal)`
- 结果：命中（3 段）

- `manifest_cpg` | Abnormal electrocardiogram findings in athletes. > Introduction
    increasing in frequency and complexity with adrenergic stimulation), in the context of a
    structurally normal heart.
    CPVT, catecholaminergic polymorphic ventricular tachycardia;

- `pmc_oa` | Catecholaminergic Polymorphic Ventricular Tachycardia: Clinical Characteristics,
    Catecholaminergic polymorphic ventricular tachycardia (CPVT) is a rare genetic cardiac
    channelopathy characterized by unexplained syncopal episodes and sudden cardiac death (SCD) in
    patients with a structurally normal heart.

---

## MCR_seq200b/475 — 神经痛性肌萎缩累及范围超出单一神经，区别于骨间前神经综合征

- 用于排除：Anterior Interosseous Nerve Syndrome
- 匹配式：`(neuralgic amyotrophy|parsonage) AND (anterior interosseous|brachial plexus)`
- 结果：命中（18 段）

- `merck` | Chapter 185. Peripheral Nervous System & Motor Unit Disorders > For myelin dysfu
    Disorders of the  rostral brachial plexus affect the shoulders, those of the caudal brachial
    plexus affect the hands, and  those of the lumbosacral plexus affect the legs.
    In adults, the cause is usually trauma (typically, for the brachial plexus,  a fall that forces
    the head away from the shoulder) or invasion by metastatic cancer (typically, breast or  lung
    cancer for the brachial plexus and intestinal or GU tumors for the lumbosacral plexus).
    Acute brachial neuritis (neuralgic amyotrophy, Parsonage-Turner syndrome) occurs primarily in
    men and  typically in young adults, although it can occur at any age.

- `pmc_oa` | Paralysis of the trapezius muscle: evaluation and surgical management.
    Condition       Cause           Central conditions      Contralateral hemiplegiaLow spinal cord
    lesionsTumors/injuries at the foramen magnum or jugular foramen         Brachial plexus
    conditions      Traumatic brachial plexus injuriesParsonage-Turner syndrome             SAN
    injury at the posterior cervical triangle   Blunt or penetrating traumaIatrogenic (surgery and
    other procedures involving the posterior cervical triangle)          Neck radi

---

## MCR_v1_seq100/91 — CD31/Fli-1 为内皮标志；孤立性纤维性肿瘤/血管外皮瘤为 CD34+/Bcl-2+

- 用于排除：Solitary Fibrous Tumor / Hemangiopericytoma
- 匹配式：`cd31 AND (cd34|bcl-?2) AND (solitary fibrous|hemangiopericytoma|angiosarcoma)`
- 结果：命中（6 段）

- `pmc_oa` | Histological and Molecular Evaluation of Liver Biopsies: A Practical and Updated
    aids assessment of ductopenia and ductular reaction             Identification of liver zonation
     Glutamine synthetase   Marks metabolic zonation, with characteristic peri-terminal venular
    hepatocyte staining         Identification of viral antigens                         HBsAg and
    HBcAg        Confirms hepatitis B infection and indicates HBV replication activity (a)
     Hepatitis D virus      Detects hepatitis D coinfection or superinfection

- `statpearls` | Mohs micrographic surgery in rare cutaneous tumors: a retrospective study at a B
    Immunohistochemical (IHC) stains such as CD34 and CD31 are essential in cases where vascular
    structures are inconspicuous (see Image.
    Histology of Cutaneous Angiosarcoma).[10]

---

## DA_d2_heldout200b/522 — DLB 核心特征：波动性认知 + 反复视幻觉

- 用于排除：Catatonia (单独)
- 匹配式：`(lewy bod) AND (fluctuat\w+) AND (visual hallucination)`
- 结果：命中（19 段）

- `merck` | Chapter 175. Delirium & Dementia > Traditional diagnostic criteria for Alzheimer
    Fluctuations in cognition,  parkinsonian symptoms, well-formed visual hallucinations, and
    relative preservation of short-term memory  suggest Lewy body dementia rather than Alzheimer's
    disease (see  ).

- `merck` | Chapter 175. Delirium & Dementia > As the disease progresses, focal neurologic d
    However, unlike in Parkinson's disease, in Lewy body dementia, cognitive and extrapyramidal
    symptoms usually begin within 1 yr of each other.
    Also the extrapyramidal symptoms differ from those of  Parkinson's disease: In Lewy body
    dementia, tremor does not occur early, rigidity of axial muscles with  gait instability occurs
    early, and deficits tend to be symmetric.
    Fluctuating cognitive function is a relatively specific feature of Lewy body dementia.

---

## MCR_seq200b/326 — 布鲁氏菌病：未消毒乳制品/牲畜暴露 + 脊柱受累

- 用于排除：Spinal epidural abscess（解剖轴答案）
- 匹配式：`brucell AND (unpasteuri[sz]ed|raw milk|livestock|sheep|goat)`
- 结果：命中（40 段）

- `merck` | Chapter 135. Gram-Negative Bacilli > Lymph node aspirates are rarely culture-pos
    Brucellosis  (Undulant, Malta, Mediterranean, or Gibraltar Fever)  Brucellosis is caused by
    Brucella  sp.
    The causative organisms of human brucellosis are  B.
    melitensis  (from sheep and  goats), and  B.

- `merck` | Chapter 135. Gram-Negative Bacilli > 50% of patients have hepatomegaly. > Treatm
    Pasteurization of milk helps prevent brucellosis.
    Cheese that is made from unpasteurized milk and is aged  < 3 mo may be contaminated.

---

## DA_d2_seq100/119 — 角样板层（cornoid lamella）确立汗孔角化症

- 用于排除：Darier / Grover disease
- 匹配式：`cornoid lamella AND porokeratos`
- 结果：命中（6 段）

- `statpearls` | The influence of genetic factors on the clinical manifestations and response to 
    In cases of atrophic, wrinkled, or nonresponsive plaques, porokeratosis (characterized by
    cornoid lamella), Bowen disease or erythroplasia of Queyrat (typically solitary lesions
    requiring biopsy to exclude squamous cell carcinoma in situ), and mycosis fungoides should be
    considered.

- `statpearls` | Genitogluteal porokeratosis: a clinical review. > Introduction
    Porokeratosis is an uncommon disorder of keratinization that presents with keratotic papules or
    annular plaques with an elevated border.[1] The distinct histologic hallmark of porokeratosis is
    cornoid lamella, a column of tightly fitted parakeratotic cells in the upper epidermis.[2][3]
    There are multiple clinical variants of porokeratosis, including:

---

## DA_d2_seq100/5 — 巨细胞修复性肉芽肿无细胞异型性，区别于真性巨细胞瘤

- 用于排除：Giant Cell Tumor
- 匹配式：`giant[- ]cell (reparative granuloma|granuloma) AND (atypia|giant cell tumor)`
- 结果：命中（1 段）

- `statpearls` | Osteosarcoma of the jaws: An overview of the pathophysiological mechanisms. > Ev
    When assessing central giant cell granulomas, it is important to exclude any underlying systemic
    diagnosis.
    Hyperparathyroidism will lead to brown tumors, which will occur as multiple osteoclastic giant
    cell tumors.

---

## MCR_v1_seq100/56 — p63 阳性支持梭形细胞鳞癌（即便 cytokeratin 阴性）

- 用于排除：Sarcoma / Postradiation Sarcoma
- 匹配式：`p63 AND (spindle cell (squamous|carcinoma)|sarcomatoid)`
- 结果：命中（10 段）

- `pmc_oa` | Immunohistochemistry for Skin Cancers: A Comprehensive Approach to the Diagnosis
    The p40 antibody, which binds specifically to the ΔNp63 isoform of the p63 protein, is
    considered the most specific marker for squamous differentiation.
    Although both p40 and p63 are highly sensitive in detecting squamous carcinomas, p40 offers
    superior specificity, minimizing false positives in non-squamous tumors.
    In spindle cell SCC of the head and neck, p40 retained ~82% sensitivity in the sarcomatoid
    component, with patchy nuclear staining.

- `pmc_oa` | Immunohistochemistry for Skin Cancers: A Comprehensive Approach to the Diagnosis
    Sarcomatoid SCC demonstrated focal positivity for p63/p40 and AE1/AE3 in the spindle component,
    confirming epithelial origin.

---

## MCR_v2_seq100/179 — 紫绀型先心病的低氧与血小板减少相关

- 用于排除：Immune thrombocytopenia
- 匹配式：`(cyanotic (congenital )?heart|hypoxem) AND thrombocytopen`
- 结果：命中（21 段）

- `merck` | Chapter 155. Other Viruses > Complications include > Introduction
    Symptomatic hypoxemia may occur.
    Acute thrombocytopenic purpura  may occur after infection resolves and cause a mild, self-
    limited  bleeding tendency, although occasionally bleeding is severe.

- `merck` | Chapter 353. The Dying Patient > Appendix II: Normal Laboratory Values > Introdu
    Acute hypoxemic respiratory failure  2284-2288  ,  Acute interstitial pneumonia  Acute kidney
    injury  2436-2442  ,  ,  ,  Acute lung injury  ,  ,  ,  mechanical ventilation in  ,  Acute
    mountain sickness  ,  Acute necrotizing ulcerative gingivitis  ,  Acute phase reactants  in
    neonatal sepsis  Acute posterior ganglionitis  1420-1421  Acute radiation syndromes  ,
    3256-3257  Acute respiratory distr

---

## DA_d2_heldout100/272 — 肌钙蛋白在发病后 1-3 小时才升高，早期阴性不排除 MI

- 用于排除：Unstable Angina
- 匹配式：`troponin AND (hyperacute t|1 to 3 hours|within 3 hours|3 h(ours)? after|serial)`
- 结果：命中（40 段）

- `merck` | Chapter 206. Approach to the Cardiac Patient > Certain findings raise suspicion 
    If symptoms suggest an acute coronary syndrome or if  no other cause is clear (particularly in
    at-risk patients), troponin and CK levels are measured.
    Because a single normal set of cardiac markers does not rule out a cardiac cause, patients whose
    symptoms suggest an acute coronary syndrome should have serial measurement of cardiac markers
    (troponin and CK-MB fraction) and ECGs.
    Troponin will be elevated in all

- `merck` | Chapter 206. Approach to the Cardiac Patient > Testing typically is done. > Intr
    If there  are no clinical clues, measuring cardiac markers and obtaining serial ECGs to rule out
    MI in older patients  plus ECG monitoring for at least 24 h are prudent.
    Cardiac markers (eg, serum troponin, CK-MB) are measured if acute MI is suspected.

---

## DA_d2_heldout200b/646 — 孤立性直肠溃疡综合征由用力排便/脱垂引起，与放射无关

- 用于排除：Solitary Rectal Ulcer Syndrome
- 匹配式：`solitary rectal ulcer AND (straining|prolapse)`
- 结果：命中（15 段）

- `merck` | Chapter 8. Approach to the Patient With Lower GI Complaints > Dyssynergia) > Dia
    With excessive straining, the anterior rectal wall prolapses into the vagina in patients with
    impaired anal  relaxation;
    Long-standing  dyschezia with chronic straining may cause a solitary rectal ulcer or varying
    degrees of rectal prolapse or  excessive perineal descent or an enterocoele.

- `pmc_oa` | A Practical Approach in Differentiating IBD From Other Causes of Enterocolitis.
    Pathergy test   Image courtesy of Byong Duk‐Ye, Asan Medical Centre             Solitary rectal
    ulcer syndrome (SRUS)   History of manual digital evacuation.Common symptoms are passage of
    mucus and per rectal bleeding.Some patients may complain of tenesmus, straining, altered bowel
    habits, and sensation of incomplete evacuation.
    Endoanal ultrasound typically shows absence of distinction between the mucosa and the muscularis
    propria, thickened muscularis propria, thickening of the internal anal sphincter and external
    sphincter, thickened submucosal layer.Defecating proctography may reveal anorectal prolapse,
    external prolapse of rectum and intussusception on‐relaxing puborectalis muscle.Dynamic MRI may
    be indicated which c

---

