# RA 根因深挖与强基线机制对照

协议：`ra_rootcause_mechanisms_v1`  · 生成：`2026-07-30T19:31:36.296361+00:00`
锚点 Ours F6 LLM Acc = **0.47**（不覆盖）
机器表：[`ra_rootcause_mechanisms.json`](ra_rootcause_mechanisms.json)

## 1. Headline Acc

| 臂 | LLM Acc | Hits |
|----|--------:|------:|
| Ours F6 | **0.47** | 47 |
| B04 Dual-Inf | 0.47 | 47 |
| B00 Direct-CoT (#2) | 0.45 | 45 |
| B06 MAC (并列 #2) | 0.45 | 45 |
| 四者并集 oracle | 0.64 | 64 |

## 2. Ours 转化漏斗

gold∈leaf **74** → champion/ranking 含金 **57** → Lex top-1 **43** → LLM **47**；`final_ranking` 均长 **1.9**。

冠军→Lex 转化率 = **0.7543859649122807**；冠军→LLM = **0.8245614035087719**。

B04（文档口径）：候选约 45 → top-1 LLM 42（转化 ~93%），本表复算：
- B04 LLM hits=47；相对 Ours 独赢 12 / Ours 独赢 12。

## 3. 失败类型学（Ours miss 互斥优先桶）

| bucket | n |
|--------|--:|
| `success` | 47 |
| `no_gold_leaf` | 19 |
| `within_family_wrong_leaf` | 15 |
| `bind_reach_gap` | 8 |
| `arbiter_demote` | 5 |
| `all_miss` | 4 |
| `granularity_name` | 1 |
| `near_neighbor_other` | 1 |

权威对照：无叶≈26、组内错叶、仲裁降位、绑定缝、粒度命名、平坦独赢。

### 代表例（每桶最多 6）

**`all_miss`**
- 12: ours=`Coarctation of the Aorta` | b04=`Complex Congenital Heart Disease` | b00=`Shone syndrome` | gold=`Kabuki syndrome`
- 23: ours=`Chronic Obstructive Pulmonary Disease` | b04=`Anthracosis` | b00=`Anthracosis` | gold=`Pulmonary hypertension owing to lung disease and/or hypoxia`
- 29: ours=`Tuberculous Appendicitis` | b04=`Tuberculous Appendicitis` | b00=`Tuberculous appendicitis` | gold=`Tuberculosis`
- 37: ours=`Ectopic endometriosis in the uterine round ligament` | b04=`Mullerian Adenosarcoma` | b00=`Mullerian cyst` | gold=`Extrapelvic endometriosis`

**`arbiter_demote`**
- 47: ours=`Phyllodes Tumor` | b04=`Phyllodes Tumor` | b00=`Phyllodes tumor` | gold=`Metaplastic carcinoma of the breast`
- 73: ours=`Krukenberg tumor` | b04=`Primary Peritoneal Cancer` | b00=`Primary peritoneal carcinoma` | gold=`Primary peritoneal carcinoma`
- 76: ours=`Vitreous Hemorrhage` | b04=`Vitreoretinal Lymphoma` | b00=`Primary Central Nervous System Lymphoma` | gold=`Primary intraocular lymphoma`
- 83: ours=`IgG4-related disease` | b04=`Castleman Disease` | b00=`Castleman disease` | gold=`Unicentric Castleman disease`
- 99: ours=`Sporotrichosis` | b04=`Cutaneous mucormycosis` | b00=`Mucormycosis` | gold=`Zygomycosis`

**`bind_reach_gap`**
- 15: ours=`Adenomatoid Odontogenic Tumor` | b04=`Calcifying Epithelial Odontogenic Tumor (CEOT)` | b00=`Adenomatoid Odontogenic Tumor` | gold=`Rare odontogenic tumor`
- 17: ours=`Interventricular Septal Hypertrophy` | b04=`Pacemaker-Induced Ventricular Septal Defect` | b00=`Ventricular septal defect` | gold=`Coronary arterial fistula`
- 24: ours=`Multiple Endocrine Neoplasia Type 1` | b04=`Cushing's Syndrome` | b00=`Cushing's syndrome due to ectopic ACTH-producing tumor` | gold=`Cushing syndrome due to ectopic ACTH secretion`
- 53: ours=`Facial Palsy` | b04=`Bilateral Bell's Palsy` | b00=`Guillain-Barré Syndrome` | gold=`Guillain-Barré syndrome`
- 63: ours=`primary malignant melanoma of the oesophagus` | b04=`Oesophageal Melanoma` | b00=`Malignant Melanoma of the Esophagus` | gold=`Malignant melanoma of the mucosa`
- 67: ours=`Deep Soft Tissue Leiomyoma` | b04=`Leiomyoma` | b00=`Leiomyoma` | gold=`Rare soft tissue tumor`

**`granularity_name`**
- 59: ours=`Mammary Tuberculosis` | b04=`Breast Tuberculosis` | b00=`Breast tuberculosis` | gold=`Tuberculosis`

**`near_neighbor_other`**
- 5: ours=`Plasmodium vivax malaria` | b04=`Malaria` | b00=`Malaria` | gold=`Malaria`

**`no_gold_leaf`**
- 1: ours=`myxoma` | b04=`Left Atrial Myxoma` | b00=`Left Atrial Myxoma` | gold=`Rare cardiac tumor`
- 4: ours=`Multifocal Motor Neuropathy` | b04=`Neuroma` | b00=`Neurotrophic ulcer with superimposed median nerve damage` | gold=`perineurioma`
- 8: ours=`Chronic Granulomatous Disease` | b04=`Chronic Granulomatous Disease` | b00=`Chronic Granulomatous Disease` | gold=`Aspergillosis`
- 9: ours=`Blastomycosis` | b04=`Blastomycosis` | b00=`Blastomycosis` | gold=`Pulmonary fungal infections in patients deemed at risk`
- 10: ours=`oesophageal variceal haemorrhage` | b04=`Portal Hypertension` | b00=`Portal Hypertension` | gold=`Hepatoportal sclerosis`
- 18: ours=`Benign myolipoma` | b04=`Leiomyoma` | b00=`Lipoleiomyoma` | gold=`Rare benign breast tumor`

**`within_family_wrong_leaf`**
- 2: ours=`Pseudoxanthoma Elasticum` | b04=`Pseudoxanthoma Elasticum` | b00=`Pseudoxanthoma elasticum` | gold=`Primary anetoderma`
- 27: ours=`Acute Angle Closure Glaucoma` | b04=`Acute Angle Closure Glaucoma` | b00=`Malignant Glaucoma` | gold=`Isolated microspherophakia`
- 34: ours=`Necrotizing Fasciitis` | b04=`Necrotizing Fasciitis` | b00=`Necrotizing fasciitis` | gold=`Pyoderma gangrenosum`
- 44: ours=`Fibromatosis` | b04=`Fibromatosis` | b00=`Nodular fasciitis` | gold=`Nodular fasciitis`
- 46: ours=`schwannoma` | b04=`Neurofibroma` | b00=`Neurofibroma` | gold=`Neurofibroma`
- 50: ours=`Septic Arthritis` | b04=`Reactive Arthritis` | b00=`Reactive Arthritis` | gold=`Reactive arthritis`

## 4. 独赢集合

- B04-only vs Ours (12): `5, 24, 46, 49, 50, 59, 63, 68, 73, 76, 83, 99`
- B00-only vs Ours (12): `5, 24, 40, 44, 46, 50, 53, 68, 73, 79, 83, 99`
- B06-only vs Ours (11): `5, 24, 46, 50, 53, 68, 73, 76, 83, 90, 99`
- B00∩B04 vs Ours miss (8): `5, 24, 46, 50, 68, 73, 83, 99`
- flat-only (B00/B06 hit, Ours+B04 miss) (5): `40, 44, 53, 79, 90`
- strong-baseline recoverable (17): `5, 24, 40, 44, 46, 49, 50, 53, 59, 63, 68, 73, 76, 79, 83, 90, 99`
- Ours-only vs B04 (12): `3, 22, 33, 35, 43, 56, 60, 64, 66, 84, 91, 95`

### 机制短评

- **B04 独赢**：近邻混淆上 examine/support 计数纠偏（Castleman、Cushing、Primary peritoneal、Mucormycosis 等）；转化率高。
- **B00/B06**：与 B04 高度重叠；额外贡献平坦金标粒度命名（flat-only=['40', '44', '53', '79', '90']）。
- **Ours 独赢**：罕见具名实体召回（Desmoid 等）；无条件 Dual-Inf 重排常毁掉这类。

## 5. 机制差异（写死）

1. **Ours 偏低**：召回尚可（叶≈74、冠军池≈58），但 `final_ranking` 极短 + `explanatory_coverage≡0` → 承诺不足；另加 Orpha 无叶天花板与叶名粒度错位。
2. **Dual-Inf 相对优秀**：在已混淆近邻上 backward+examine 做 support 承诺；少受「错细叶绑定」约束。
3. **B00/B06 高**：平坦空间直接以金标粒度命名；MAC 多列表裁决与 CoT 单跳在 RA 上几乎同向。

## 6. 可迁移算子（Phase B）

| 算子 | 借自 | 作用点 | 针对桶 | 护栏 |
|------|------|--------|--------|------|
| `support_examine_gate` | B04 Dual-Inf | frozen champions/padded-ddx; override iff Δsupport≥δ | arbiter_demote / near-neighbor | keep tree top-1 unless delta met |
| `pair_adjudicate` | B06 MAC supervisor (shrunk) | pair LLM choose when top1–top2 near-tie | within_family_wrong_leaf / near ties | only swap order; never open regenerate |
| `grain_alias_align` | B00 Direct-CoT naming | eval-time Orpha/synonym display-name align on top-1/ddx | granularity_name / partial no_gold_leaf | do not change tree posteriors |

**约束**：默认保留树 top-1；不迁整段 MAC 建树 / 开放重生成主诊断；不用 Live S3 coverage 作主信号；正式 F6 Acc 不覆盖。

## 7. Phase C 验证结果（LLM Acc @ ddx_k=5）

| 臂 | LLM Acc | 备注 |
|----|--------:|------|
| F6 正式锚点 | **0.47** | 不覆盖 |
| Gate δ=1 / 2 / 3 | **0.49 / 0.49 / 0.49** | 覆盖 28 / 18 / 14；δ=3 Lex 最好 |
| Pair τ=0.15 | **0.39** | 触发 38、交换 12；单独有害 |
| Grain heuristic | **0.43** | 改名 20；单独有害 |
| Grain oracle Lex 天花板 | Lex **0.72** | 金标知情，仅诊断用 |
| Combo Gate(δ=3)⊕Pair⊕Grain | **0.44** | 被 pair/grain 噪声拖累 |

**未达 ≥0.50。** 侧跑最优仍为 **Gate 0.49**（推荐 δ=3：同 Acc、更少覆盖、Lex 最高）。

## 8. 决策

- 正式锚点保持 **F6 Acc=0.47**。
- 可报告侧跑：Dual-Inf **条件融合门 0.49**（护栏式承诺纠偏）。
- **不采用** MAC pair / 启发式 grain 作为主迁移：单独与组合均回归。
- 下一天花板工程：`no_gold_leaf`（本表 miss 桶 19；权威 Lex 无叶≈26）+ 组内错叶 15——需 Orpha emit / 类别名对齐，而非更多平坦裁决。

## 9. 复现

```bash
PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ra_rootcause_mechanisms.py
PYTHONPATH=src:scripts/paper python3 scripts/paper/run_ra_dualinf_conditional_gate.py --pool champions --delta 3
PYTHONPATH=src:scripts/paper python3 scripts/paper/run_ra_pair_adjudicate.py --tau 0.15
PYTHONPATH=src:scripts/paper python3 scripts/paper/run_ra_grain_alias_align.py --mode heuristic
PYTHONPATH=src:scripts/paper python3 scripts/paper/run_ra_transfer_combo.py --delta 3 --tau 0.15
```

产物：`logs/rarearena_ra_rdc_seq100_v1/{dualinf_conditional_gate_v1,pair_adjudicate_v1,grain_alias_align_v1,transfer_combo_v1}/`

