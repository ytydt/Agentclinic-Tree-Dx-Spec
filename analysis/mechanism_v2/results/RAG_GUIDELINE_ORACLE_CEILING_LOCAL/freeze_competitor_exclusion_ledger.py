#!/usr/bin/env python3
"""Per-hypothesis exclusion status for the seven underivable cases.

`MANUAL_DECISION_TREE_REPORT.md` established that these seven golds cannot be
derived from their vignettes.  That leaves a separate question: given the same
vignette and the same corpus, can the *other* hypotheses the four methods
proposed be positively ruled out?  The answer decides what kind of defect each
case is.

    可消去到金标   every competitor is excludable, so elimination lands on the
                   gold's clinical content and only the qualifier is missing
    悬而未决       at least one competitor stays fully compatible with the
                   vignette, so no answer is defensible over another
    证据偏向竞争   the vignette positively supports a competitor

Status values per hypothesis:
    excluded      a vignette finding rules it out, with the rule named
    not_excluded  compatible with everything given; no finding rules it out
    supported     the vignette actively favours it
    near_gold     the gold, its parent, or a synonym
    wrong_axis    a finding or complication rather than a candidate diagnosis
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

E, N, S, G, X = "excluded", "not_excluded", "supported", "near_gold", "wrong_axis"

CASES: dict[str, dict] = {
    "MCR_v2_seq100/146": {
        "gold": "Diffuse large B cell lymphoma",
        "verdict": "证据偏向竞争",
        "hypotheses": [
            ("Intestinal tuberculosis", S, "语料列出的活动性肠结核内镜特征包括回盲部炎性肿块、深部横行环形溃疡与狭窄；本例回肠狭窄+盲肠溃疡+来自洪都拉斯+QuantiFERON 阳性，全部吻合"),
            ("Tuberculosis", S, "同上，四方法中三个的答案"),
            ("Latent tuberculosis", S, "IDSA 指南：IGRA 只证明感染，无法区分活动与潜伏；本例 IGRA 阳性且已启动异烟肼，潜伏结核事实成立"),
            ("Crohn's disease", N, "语料明言肠结核是克罗恩病的'great mimic'，某些病例临床上无法区分；粪钙卫蛋白偏低仅为弱反证"),
            ("Inflammatory bowel disease", N, "同上，克罗恩病的上位概念"),
            ("Ileocecal histoplasmosis", N, "未做任何真菌学检查，无法排除，仅先验概率低"),
            ("Helminth infection", E, "既往蠕虫感染已治疗，且粪便病原学阴性"),
            ("Diverticulitis", E, "病变位于末段回肠与盲肠，全文未描述憩室"),
            ("Ischemic colitis", E, "两月病程伴盗汗与 10 kg 体重下降，且为回肠狭窄伴斑片状结肠改变，非缺血分布"),
            ("Intestinal lymphoma", G, "金标的上位概念"),
            ("Gastrointestinal lymphoma", G, "金标的上位概念"),
        ],
        "residual": "肠结核被证据积极支持且不可排除；克罗恩病与组织胞浆菌病亦不可排除。金标所需的组织学在 vignette 中被略去，而语料明确指出这正是区分两者所必需的检查。",
    },
    "DA_d2_heldout200b/566": {
        "gold": "High-grade (3A) follicular lymphoma, stage IVB",
        "verdict": "悬而未决",
        "hypotheses": [
            ("Diffuse Large B-Cell Lymphoma", N, "语料原文：FL grade 3A 与 3B 在此类材料上无法与 DLBCL 区分。即选项 C 在给定材料下不可排除"),
            ("Nodular Lymphocyte-Predominant Hodgkin Lymphoma", N, "未报告 LP 细胞形态与 CD15/CD30/CD20 组合，无法排除"),
            ("Castleman disease", N, "未提供可据以排除的组织学描述"),
            ("Primary Effusion Lymphoma", E, "本例为纵隔肿块伴广泛淋巴结病的结内 B 细胞病变；PEL 为体腔为主、常见于免疫抑制/HHV-8 且免疫表型多为 null"),
            ("Anaplastic Large Cell Lymphoma", E, "活检明确为 B 淋巴细胞群"),
            ("Pseudolymphoma", E, "BCL2 异常表达伴高 Ki-67 提示克隆性肿瘤"),
            ("Chylothorax", X, "乳糜胸是真实存在的并发表现，非诊断答案"),
            ("Pleural effusion", X, "同上"),
            ("Dyslipidemia", X, "为既往史，胸水甘油三酯升高来自乳糜"),
            ("Hypertriglyceridemia", X, "同上"),
            ("Lymphoma", G, "金标上位概念"),
        ],
        "residual": "最关键的竞争假设 DLBCL 不可排除，且语料明确陈述所需的区分在给定材料上做不出来；vignette 从未报告滤泡结构与中心母细胞计数。",
    },
    "DA_d2_seq100/19": {
        "gold": "Follicular thyroid carcinoma with manubrial invasion",
        "verdict": "悬而未决",
        "hypotheses": [
            ("Metastatic follicular thyroid carcinoma", N, "'直接侵犯'与'血行转移'的分支需要病灶与胸骨后甲状腺床连续性的证据，vignette 未描述；此为选项 B"),
            ("Thyroid metastasis to bone", N, "同上"),
            ("Metastatic thyroid carcinoma", N, "同上"),
            ("Recurrent goiter", E, "病灶为溶骨破坏并见甲状腺滤泡浸润骨小梁，良性甲状腺肿不具此行为"),
            ("Brown Tumor", E, "FNA 与组织学证实为甲状腺滤泡细胞"),
            ("Fibrous Dysplasia", E, "同上"),
            ("Giant Cell Tumor", E, "同上"),
            ("Benign bone cyst", E, "同上"),
            ("Bone metastasis from other primary cancer", E, "细胞学明确为甲状腺滤泡来源"),
            ("Thyroid osteopathy", E, "非肿瘤性实体，与溶骨性肿块及滤泡浸润不符"),
            ("Follicular thyroid carcinoma", G, "金标去掉侵犯限定后的本体"),
        ],
        "residual": "除金标本体外，所有非甲状腺来源假设均可排除，但剩下的正是二选一：直接侵犯 vs 血行骨转移，vignette 无法判定。",
    },
    "MCR_v2_seq100/234": {
        "gold": "SpindleCellHemangioma",
        "verdict": "悬而未决",
        "hypotheses": [
            ("Giant Cell Tumor", N, "语料述 GCT 多见 20-40 岁、偏心膨胀性、中度强化；本例 50 岁且位于颅骨属不典型，但无可据以排除的发现"),
            ("Eosinophilic Granuloma", N, "颅骨溶骨性病变符合，年龄偏大而已，无排除依据"),
            ("Ewing's Sarcoma", N, "通常为浸润性骨破坏且年龄更小，但未做活检无法排除"),
            ("Metastatic bone disease", N, "未做任何原发灶筛查"),
            ("Multiple myeloma", N, "未做血清蛋白电泳或轻链检测"),
            ("Aneurysmal bone cyst", E, "语料述 ABC 为多房囊性伴分隔与 CT/MRI 上的液-液平面；本例为明显均一强化的实性病变，未见液-液平面"),
            ("Brown Tumor", E, "实验室检查无异常，无甲状旁腺功能亢进证据"),
            ("Osteomyelitis", E, "无痛、无热、实验室正常且边界清楚"),
            ("Fibrous dysplasia", E, "纤维异常增殖症为磨玻璃样膨胀改变，非伴皮质破坏的溶骨灶"),
            ("Osteoma", E, "骨瘤为致密硬化灶，与透亮病变相反"),
            ("Hemangioma", G, "金标上位概念"),
            ("Osteolytic lesion", X, "影像描述而非诊断"),
        ],
        "residual": "巨细胞瘤、嗜酸性肉芽肿、尤因肉瘤、转移与骨髓瘤五项均不可排除；金标与它们一样都需要组织学。",
    },
    "MCR_v2_seq100/202": {
        "gold": "Mantle cell lymphoma",
        "verdict": "悬而未决",
        "hypotheses": [
            ("Fibroma", N, "良性纤维性病变无法排除，仅双侧对称性生长不典型"),
            ("Palatal fibroma", N, "同上"),
            ("Granuloma", N, "泛化标签，无可据以排除的发现"),
            ("Torus Palatinus", E, "Merck：腭隆突为骨性外生物；本例肿物质地为'firm, elastic'，且术中腭骨未受累 —— 四方法一致答案可排除"),
            ("Torus palatinus", E, "同上"),
            ("Palatal Torus", E, "同上"),
            ("Giant Cell Granuloma", E, "中央性巨细胞肉芽肿为骨内病变，本例腭骨未受累"),
            ("Giant Cell Lesion", E, "同上"),
            ("Giant Cell Tumor", E, "同上"),
            ("Palatal Abscess", E, "无痛、无发热、病程 10-12 周且黏膜完整无溃疡"),
            ("Pyogenic Granuloma", E, "化脓性肉芽肿通常溃疡、易出血、生长迅速"),
            ("Squamous Cell Carcinoma", E, "无痛、无溃疡、双侧对称缓慢生长与腭部鳞癌不符（提示性反证）"),
            ("Granulomatosis with Polyangiitis", E, "无鼻窦破坏、无系统性或肾脏表现"),
            ("Lymphoma", G, "金标上位概念"),
        ],
        "residual": "多数竞争假设确可排除，但消去后并不落在金标上：腭部黏膜下肿物最经典的鉴别是小唾液腺肿瘤（语料有明确条目），而四种方法无一提出；金标本身仍需 cyclin D1/t(11;14)。",
    },
    "DA_d2_heldout200b/551": {
        "gold": "Linagliptin-induced acute pancreatitis",
        "verdict": "可消去到金标",
        "hypotheses": [
            ("Acute Coronary Syndrome", N, "未提供心电图与心肌标志物，严格说不可排除（但不解释脂肪酶显著升高）"),
            ("Cholecystitis", E, "CT 明确胆囊已手术切除"),
            ("Chronic Pancreatitis", E, "CT 示胰腺无急性异常、无钙化与导管改变"),
            ("Pancreatic Insufficiency", E, "为慢性功能状态，不解释急性脂肪酶升高"),
            ("Diabetic Ketoacidosis", E, "血糖仅中度升高，无酸中毒或酮症记录"),
            ("Peptic Ulcer Disease", E, "泮托拉唑无效且脂肪酶显著升高"),
            ("Hypertensive Emergency", E, "血压 200/100 但无靶器官危象，且不解释脂肪酶"),
            ("Chronic Kidney Disease", E, "4 期 CKD 为共病，不解释胰腺炎表现"),
            ("Dehydration", E, "为伴随状态而非诊断"),
            ("Gastrointestinal obstruction", E, "腹部无膨隆、肠鸣音正常、CT 无梗阻征象"),
            ("Renal Artery Stenosis", E, "不解释脂肪酶升高与胰型腹痛"),
            ("Acute Pancreatitis", G, "金标去掉药物归因后的本体，三方法给出的答案"),
            ("Pancreatitis", G, "同上"),
        ],
        "residual": "消去后恰好落在'病因未定的急性胰腺炎'——即金标去掉 linagliptin 归因的部分。用药表列出 11 种药物但不含 linagliptin，该归因不可验证。",
    },
    "DA_d2_heldout100/348": {
        "gold": "Asymptomatic posterior corneal dystrophy",
        "verdict": "可消去到金标",
        "hypotheses": [
            ("Posterior crocodile shagreen", N, "周边确实存在鳄革样变，但不解释 4 个分立完整的同心环"),
            ("Fuchs Endothelial Corneal Dystrophy", E, "共聚焦未见细胞浸润与滴状赘疣，视力 20/20 且无水肿"),
            ("Schnyder Corneal Dystrophy", E, "血脂正常，环表面光滑无沉着物，且无老年环"),
            ("Wilson's disease", E, "血清铜正常"),
            ("Corneal iron deposition", E, "血清铁正常，环表面无色素沉着"),
            ("Arcus senilis", E, "查体明确记载'no distinct arcus senilis'"),
            ("Corneal arcus", E, "同上"),
            ("Corneal amyloidosis", E, "无沉着物，共聚焦无浸润"),
            ("Primary lipoidal degeneration", E, "血脂正常、无沉着物与血管化"),
            ("Keratoconus", E, "角膜曲率 43.4/43.0-44.8 D 正常，无圆锥形态"),
            ("Pterygium", X, "左眼确有小翼状胬肉，但不解释后基质环"),
            ("Nuclear Sclerosis", X, "为晶状体改变，非角膜病变"),
            ("Corneal Ring Opacities", G, "金标的描述性内容"),
            ("Corneal dystrophy", G, "金标上位概念"),
        ],
        "residual": "所有具名竞争假设均可排除，消去后落在'无症状的后基质同心环角膜营养不良'即金标的描述性内容。障碍不在证据，而在该实体不存在于参考文献中，没有指向它的正向规则。",
    },
}


def main() -> int:
    rows = []
    for key, case in CASES.items():
        for label, status, why in case["hypotheses"]:
            rows.append(
                {
                    "case_key": key,
                    "gold": case["gold"],
                    "case_verdict": case["verdict"],
                    "hypothesis": label,
                    "status": status,
                    "reason": why,
                }
            )
    out = OUT_DIR / "competitor_exclusion_ledger.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    per_case = {}
    for key, case in CASES.items():
        c = Counter(s for _, s, _ in case["hypotheses"])
        per_case[key] = {
            "gold": case["gold"],
            "verdict": case["verdict"],
            "n_hypotheses": len(case["hypotheses"]),
            "counts": dict(c),
            "blocking_competitors": [l for l, s, _ in case["hypotheses"] if s in (N, S)],
            "residual": case["residual"],
        }
    summary = {
        "cases": len(CASES),
        "verdicts": dict(Counter(c["verdict"] for c in CASES.values())),
        "hypotheses_total": len(rows),
        "status_totals": dict(Counter(r["status"] for r in rows)),
        "per_case": per_case,
    }
    (OUT_DIR / "competitor_exclusion_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "per_case"},
                     indent=2, ensure_ascii=False))
    for k, v in per_case.items():
        print(f"{k:26s} {v['verdict']:12s} 阻断项={len(v['blocking_competitors'])}/{v['n_hypotheses']}"
              f"  {v['blocking_competitors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
