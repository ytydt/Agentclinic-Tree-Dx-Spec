#!/usr/bin/env python3
"""Freeze the hand-built decision flows and their separability verdicts.

Each entry is one adjudicated case: the ordered branches a clinician would
apply, which competing hypothesis each branch removes, whether the branch rests
on a passage found in the local corpus (verified by probe_decision_rules.py),
and the resulting verdict.

Verdicts
    separable_corpus_grounded   every branch is stated in the local corpus
    separable_needs_outside     the flow works but a branch is not in the corpus
    concept_only                the flow reaches the right clinical entity, and
                                what remains is a naming or answer-axis choice
    underivable                 the vignette omits the finding the branch needs
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

VERDICTS: dict[str, dict] = {
    "DA_d2_heldout200b/522": {
        "gold": "Catatonia related to underlying Lewy body dementia",
        "verdict": "separable_corpus_grounded",
        "branches": [
            "回声性动作/模仿顺从/缄默/凝视 → 满足紧张症 → 排除单纯谵妄、抑郁",
            "波动性认知 + 反复视幻觉（DLB 两项核心特征）→ 病因为 DLB 而非 MDD",
            "→ 紧张症继发于路易体痴呆",
        ],
        "excludes": "Catatonia（单列）、Major depressive disorder、Delirium、Vascular dementia",
        "rule_source": "merck: 波动性认知是 DLB 相对特异的特征；成形视幻觉提示 DLB",
        "methods_correct": 0,
    },
    "DA_d2_heldout200b/773": {
        "gold": "Idiopathic Pulmonary Arterial Hypertension with Patent Foramen Ovale",
        "verdict": "separable_corpus_grounded",
        "branches": [
            "肺动脉压 60/39 低于主动脉压 → 未达体循环水平 → 不符合 Eisenmenger",
            "7.34 mm PFO 不是大量左向右分流，无法造成 Eisenmenger 生理",
            "肺动脉造影排除 PE/AVM → 肺动脉高压为特发性，PFO 为并存且右向左分流",
        ],
        "excludes": "Eisenmenger Syndrome（四方法一致答案）、CTEPH、Congenital heart disease",
        "rule_source": "merck: 大量左向右分流（大 VSD/PDA/ASD）才导致 Eisenmenger 反应",
        "methods_correct": 0,
    },
    "DA_d2_seq100/119": {
        "gold": "Eruptive pruritic papular porokeratosis (EPPP)",
        "verdict": "separable_corpus_grounded",
        "branches": [
            "活检见发育良好的角样板层 → 汗孔角化症 → 排除 Darier/Grover/银屑病等",
            "皮损散在于四肢而非沿 Blaschko 线 → 排除线状汗孔角化症",
            "三个月内快速播散 + 剧烈瘙痒 + 真皮嗜酸细胞浸润 → 嗜酸性丘疹型而非 DSAP/DSP",
        ],
        "excludes": "Darier's disease、Grover's disease（四方法答案）、DSAP、DSP",
        "rule_source": "statpearls: 角样板层是汗孔角化症的组织学标志；并列出 eruptive pruritic papular porokeratosis 变体",
        "methods_correct": 0,
    },
    "MCR_seq200b/257": {
        "gold": "collar button abscess",
        "verdict": "separable_corpus_grounded",
        "branches": [
            "1.5 cm 波动性肿块 → 脓肿，排除蜂窝织炎；X 线骨质完整 → 排除骨髓炎",
            "Kanavel 四征只满足腱鞘局部压痛一项，无梭形肿胀、无被动伸指痛 → 不符合化脓性屈肌腱鞘炎",
            "病灶中心位于掌侧指蹼间隙 → 掌间隙脓肿中的领扣状脓肿",
        ],
        "excludes": "Pyogenic Flexor Tenosynovitis（四方法一致答案）、Cellulitis、Septic arthritis",
        "rule_source": "statpearls: Kanavel 四征定义；merck: 掌部脓肿包括 collar-button abscess",
        "methods_correct": 0,
    },
    "MCR_seq200b/326": {
        "gold": "Brucellosis",
        "verdict": "separable_corpus_grounded",
        "branches": [
            "题目问病因诊断而非解剖诊断 → 硬膜外脓肿/脊柱炎是病变而非答案",
            "破损手接触未消毒羊胃 + 发热盗汗一月 → 布鲁氏菌暴露",
            "血培养革兰阴性杆菌 + 头孢丙烯无效 + 结核血清学阴性 → 布鲁氏菌病",
        ],
        "excludes": "Spinal epidural abscess（四方法答案）、Spondylodiscitis、Pott's disease",
        "rule_source": "merck: B. melitensis 来自绵羊与山羊；未消毒乳制品为传播途径",
        "methods_correct": 0,
    },
    "MCR_seq200b/475": {
        "gold": "Parsonage Turner Syndrome",
        "verdict": "separable_corpus_grounded",
        "branches": [
            "肌电图失神经不止于骨间前神经支配肌，还累及肱二头肌、肱三头肌、三角肌 → 超出单一神经",
            "受累范围跨越多神经、MRI 正常、既往健康的青年急性起病 → 臂丛神经炎",
            "→ 神经痛性肌萎缩 / Parsonage-Turner 综合征",
        ],
        "excludes": "Anterior Interosseous Nerve Syndrome（四方法一致答案）、Radial/Ulnar neuropathy",
        "rule_source": "merck: 急性臂丛神经炎（神经痛性肌萎缩、Parsonage-Turner 综合征）多见于青年",
        "methods_correct": 0,
    },
    "MCR_v1_seq100/49": {
        "gold": "StumpAppendicitis",
        "verdict": "separable_corpus_grounded",
        "branches": [
            "CT 见盲肠极部肿胀增厚的管状结构 → 阑尾样结构炎症",
            "八个月前已行阑尾切除、病灶紧邻手术夹 → 为残端而非原阑尾",
            "→ 残端阑尾炎（伴盲肠周围积液）",
        ],
        "excludes": "Abscess、Appendiceal abscess（impc/forest 答案）、Cecal diverticulitis",
        "rule_source": "statpearls: 残端阑尾炎定义为切除不全后残留过长阑尾残端的复发性阑尾炎",
        "methods_correct": 2,
    },
    "MCR_v1_seq100/74": {
        "gold": "Catecholaminergic polymorphic ventricular tachycardia",
        "verdict": "separable_corpus_grounded",
        "branches": [
            "超声心动图室壁厚度正常 → 排除肥厚型心肌病",
            "QTc 380 ms 正常 → 排除长 QT 综合征；无 Brugada 波形 → 排除 Brugada",
            "电解质与生化正常 → 排除代谢性；心脏结构正常青年在嘈杂环境（肾上腺素能应激）下 VF → CPVT",
        ],
        "excludes": "Long QT Syndrome（三方法答案）、Hypertrophic Cardiomyopathy、Brugada syndrome",
        "rule_source": "manifest_cpg/pmc_oa: CPVT 为心脏结构正常者随肾上腺素能刺激加重的多形性室速",
        "methods_correct": 1,
    },
    "MCR_v1_seq100/56": {
        "gold": "Spindle cell squamous cell carcinoma",
        "verdict": "separable_corpus_grounded",
        "branches": [
            "牙龈黏膜部位的恶性梭形细胞增生，伴异型核分裂",
            "p63 阳性提示鳞状上皮分化，即便全角蛋白阴性 → 上皮源性",
            "→ 梭形细胞（肉瘤样）鳞癌，而非放射后肉瘤或真性肉瘤",
        ],
        "excludes": "Postradiation Sarcoma、Malignant Spindle Cell Sarcoma、Osteosarcoma",
        "rule_source": "pmc_oa: 肉瘤样鳞癌梭形成分 p63/p40 灶性阳性可确认上皮起源",
        "methods_correct": 1,
        "note": "推翻前一轮 source-gap 判定：扩展语料确有该免疫组化规则",
    },
    "MCR_v1_seq100/91": {
        "gold": "Angiosarcoma",
        "verdict": "separable_needs_outside",
        "branches": [
            "CD31 与 Fli-1 阳性 → 内皮分化",
            "CD34 阴性、Bcl-2 阴性 → 不支持孤立性纤维性肿瘤/血管外皮瘤",
            "20 个核分裂/10HPF + 侵犯大脑镰与皮质 → 恶性内皮肿瘤，排除海绵状血管瘤",
        ],
        "excludes": "Hemangiopericytoma（三方法答案）、Solitary Fibrous Tumor、Cavernous angioma",
        "rule_source": "缺：语料有 SFT 的 STAT6 重排，但无 CD31/Fli-1 与 CD34/Bcl-2 的对照表述",
        "methods_correct": 0,
    },
    "MCR_v2_seq100/179": {
        "gold": "hypoxia-induced thrombocytopenia",
        "verdict": "separable_needs_outside",
        "branches": [
            "凝血功能与血涂片正常、抗血小板抗体阴性 → 不支持免疫性血小板减少",
            "IVIG 后血小板未升（77 000）→ 进一步否定免疫机制",
            "四个时点血小板随 SaO2 同向变化（80%→103k，95%→173k，85-87%→225k，80%→68k）→ 低氧驱动",
        ],
        "excludes": "Immune thrombocytopenia、Tetralogy of Fallot with pulmonary atresia（四方法答案，答错了轴）",
        "rule_source": "缺：语料仅述紫绀型先心病慢性低氧致继发性红细胞增多，未述低氧致血小板减少；但推断所需数据全在 vignette 内",
        "methods_correct": 0,
    },
    "DA_d2_heldout100/272": {
        "gold": "Window-Period Acute Myocardial Infarction",
        "verdict": "concept_only",
        "branches": [
            "冠脉造影示 LAD 近端次全闭塞 → 冠脉事件，排除 PE/主动脉夹层/高血压急症",
            "无 ST 抬高 → 非 STEMI；V2-V5 超急性 T 波为 STEMI 等危征象",
            "单次肌钙蛋白正常不能排除 MI（需系列检测）→ 处于标志物升高前的时间窗",
        ],
        "excludes": "Acute Coronary Syndrome（三方法答案）、Unstable Angina",
        "rule_source": "merck: 单次心肌标志物正常不排除心源性，需系列检测；pmc_oa: 超急性 T 波为早期 STEMI 等危征象",
        "residual": "假设集中 'Myocardial Infarction with Normal Troponin' 与金标同义，二者之间无临床分支可判",
        "methods_correct": 0,
    },
    "DA_d2_heldout200b/646": {
        "gold": "Radiation-induced solitary rectal ulcer",
        "verdict": "concept_only",
        "branches": [
            "三个月前前列腺放疗且置入 SpaceOAR 间隔物 → 放射相关",
            "直肠其余部分完全正常、无放射性直肠炎改变 → 排除放射性直肠炎/直肠病",
            "孤立性深凿状前壁溃疡 + 活检无恶性 → 放射所致的孤立性溃疡",
        ],
        "excludes": "Radiation Proctitis（四方法一致答案）、Solitary Rectal Ulcer Syndrome",
        "rule_source": "merck/pmc_oa: 孤立性直肠溃疡综合征源于长期用力排便与脱垂，与放射无关",
        "residual": "选项 C 'radiation-induced rectal ulcer (radiation proctopathy)' 与金标近乎同义，选项集本身有缺陷",
        "methods_correct": 0,
    },
    "DA_d2_seq100/5": {
        "gold": "Left maxillary giant cell reparative granuloma (GCRG)",
        "verdict": "concept_only",
        "branches": [
            "活检见多核巨细胞的梭形细胞增生 → 巨细胞病变，排除骨化纤维瘤、青少年鼻咽血管纤维瘤、纤维异常增殖症",
            "无细胞异型性、核分裂罕见 → 反应性/修复性而非真性巨细胞瘤",
            "上颌骨（颌面骨）部位 → 颌骨巨细胞肉芽肿",
        ],
        "excludes": "Giant Cell Tumor（两方法答案）、Juvenile Nasopharyngeal Angiofibroma（两方法答案）",
        "rule_source": "缺：语料未见 GCRG 与真性巨细胞瘤在异型性上的对照表述",
        "residual": "选项 C 'Central Giant Cell Granuloma' 与金标 GCRG 是同一实体的新旧命名，无临床分支可分",
        "methods_correct": 0,
    },
    "MCR_seq200b/409": {
        "gold": "Chronic necrotizing pancreatitis",
        "verdict": "concept_only",
        "branches": [
            "胸水淀粉酶 11 871 U/L → 胰源性胸腔积液，排除心衰/PE/结核/脓胸",
            "CT 见胰腺多发无强化囊性区、无导管扩张与钙化 → 坏死性而非钙化性慢性胰腺炎",
            "四个月前重症急性胰腺炎病史 → 持续的坏死性病程",
        ],
        "excludes": "Pancreaticopleural fistula 系列答案（四方法）、Acute pancreatitis、Empyema",
        "rule_source": "语料有胰源性胸水的淀粉酶判据与胰瘘机制",
        "residual": "问的是胸水机制（胰瘘）还是底层胰腺病，属回答轴之争；且'慢性坏死性胰腺炎'非 Atlanta 标准术语（对应包裹性坏死）",
        "methods_correct": 0,
    },
    "DA_d2_heldout100/348": {
        "gold": "Asymptomatic posterior corneal dystrophy",
        "verdict": "underivable",
        "branches": ["可排除 PPMD（无内皮小泡/滴状赘疣）、Descemet 前营养不良（非同心完整环）"],
        "excludes": "Fuchs endothelial dystrophy、Schnyder、Crocodile shagreen",
        "rule_source": "缺：金标是该病例报告新描述的实体，参考文献中不存在其准入规则",
        "residual": "只能靠排除法落到剩余选项，没有指向该实体的正向规则",
        "methods_correct": 0,
    },
    "DA_d2_heldout200b/551": {
        "gold": "Linagliptin-induced acute pancreatitis",
        "verdict": "underivable",
        "branches": ["可确立急性胰腺炎；可排除胆源性（已胆囊切除）、酒精性、高甘油三酯性"],
        "excludes": "Acute Pancreatitis（三方法答案）、Diabetic Ketoacidosis",
        "rule_source": "n/a",
        "residual": "vignette 列出 11 种在用药物，其中没有 linagliptin，药物归因无法推出",
        "methods_correct": 0,
    },
    "DA_d2_heldout200b/566": {
        "gold": "High-grade (3A) follicular lymphoma, stage IVB",
        "verdict": "underivable",
        "branches": ["可确立 B 细胞淋巴瘤伴 BCL2 异常表达与高 Ki-67"],
        "excludes": "Primary Effusion Lymphoma、DLBCL、Castleman disease",
        "rule_source": "n/a",
        "residual": "活检只报告'小到大 B 淋巴细胞混合'，从未报告滤泡结构或中心母细胞计数，3A 分级无从判定；CD10 阴性也不指向滤泡性",
        "methods_correct": 0,
    },
    "DA_d2_seq100/19": {
        "gold": "Follicular thyroid carcinoma with manubrial invasion",
        "verdict": "underivable",
        "branches": ["可确立滤泡性甲状腺癌（FNA 滤泡细胞、滤泡浸润骨小梁）、排除乳头状"],
        "excludes": "Thyroid metastasis to bone、Metastatic follicular thyroid carcinoma",
        "rule_source": "缺",
        "residual": "'直接侵犯'与'血行骨转移'的分支需要胸骨柄病灶与胸骨后甲状腺床连续性的证据，vignette 未描述",
        "methods_correct": 0,
    },
    "MCR_v2_seq100/146": {
        "gold": "Diffuse large B cell lymphoma",
        "verdict": "underivable",
        "branches": ["可确立回肠狭窄伴溃疡；QuantiFERON 阳性使肠结核成为合理答案"],
        "excludes": "Intestinal Tuberculosis（四方法答案）、Crohn's disease",
        "rule_source": "n/a",
        "residual": "vignette 写明取了回肠与结肠分段活检，但从未报告病理结果；金标只能由未给出的组织学得出",
        "methods_correct": 0,
    },
    "MCR_v2_seq100/202": {
        "gold": "Mantle cell lymphoma",
        "verdict": "underivable",
        "branches": ["可确立硬腭双侧缓慢生长的实性肿物、骨未受累"],
        "excludes": "Torus Palatinus（三方法答案）、Giant Cell Granuloma",
        "rule_source": "n/a",
        "residual": "已行切除但未报告任何组织学或 cyclin D1/SOX11/t(11;14) 结果，金标无从推出",
        "methods_correct": 0,
    },
    "MCR_v2_seq100/234": {
        "gold": "SpindleCellHemangioma",
        "verdict": "underivable",
        "branches": ["可确立额骨溶骨性、皂泡样、明显强化的病变"],
        "excludes": "Giant Cell Tumor（三方法答案）、Aneurysmal bone cyst、Eosinophilic granuloma",
        "rule_source": "n/a",
        "residual": "全文无组织学；影像所见与多种巨细胞/血管性病变重叠，金标需病理确认",
        "methods_correct": 0,
    },
}


def main() -> int:
    rows = []
    for key, v in VERDICTS.items():
        rows.append(
            {
                "case_key": key,
                "gold": v["gold"],
                "verdict": v["verdict"],
                "n_branches": len(v["branches"]),
                "decision_flow": " → ".join(v["branches"]),
                "excludes": v["excludes"],
                "rule_source": v["rule_source"],
                "residual_obstacle": v.get("residual", ""),
                "methods_correct_of_4": v["methods_correct"],
                "note": v.get("note", ""),
            }
        )
    out = OUT_DIR / "manual_decision_tree_verdicts_22.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    tally = Counter(r["verdict"] for r in rows)
    feasible = [r for r in rows if r["verdict"].startswith("separable")]
    summary = {
        "cases": len(rows),
        "verdicts": dict(tally),
        "separable_total": len(feasible),
        "method_pairs_in_separable": 4 * len(feasible),
        "method_correct_in_separable": sum(r["methods_correct_of_4"] for r in feasible),
        "method_accuracy_in_separable": round(
            sum(r["methods_correct_of_4"] for r in feasible) / (4 * len(feasible)), 3
        ),
    }
    (OUT_DIR / "manual_decision_tree_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
