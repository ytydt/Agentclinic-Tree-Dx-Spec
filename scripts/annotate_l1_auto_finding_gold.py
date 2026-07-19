#!/usr/bin/env python3
"""Apply the manually adjudicated L1 evidence gold labels to the frozen fixture."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l1_evidence_bfs as bfs  # noqa: E402


DEFAULT_FIXTURE = ROOT / "eval_fixtures" / "l1_auto_finding_selection_v1.json"

# These labels were adjudicated against the frozen L1 families and their L2
# exemplars.  Filtering output was hidden during adjudication.  IDs denote only
# production VignetteParser facts; no annotation finding is inserted.
MANUAL_GOLD: dict[str, dict[str, Any]] = {
    "mb11_pancoast": {
        "status": "scorable",
        "target_l1_branch_id": "B1",
        "target_l1_label": "Neoplastic Disorder with Neurological Involvement",
        "best_l1_fact_ids": ["F7"],
        "valid_l1_fact_ids": ["F5", "F17"],
        "best_fact_sets": [["F5", "F7"]],
        "rationale": (
            "一个月快速减重是最强单条肿瘤性线索；重度吸烟与快速减重组合"
            "进一步支持 B1，头颈体位不改变症状可反证压迫/根性 B4。"
        ),
    },
    "mb34_leukemoid": {
        "status": "unscorable",
        "target_l1_branch_id": "",
        "target_l1_label": "",
        "best_l1_fact_ids": [],
        "valid_l1_fact_ids": [],
        "best_fact_sets": [],
        "rationale": (
            "F13+F15 能识别反应性白细胞增多，但 B4 与 OTHER 的冻结叶均"
            "包含感染、炎症和应激性反应性增多，无法确定唯一 L1。"
        ),
    },
    "mb55_glucagonoma": {
        "status": "unscorable",
        "target_l1_branch_id": "",
        "target_l1_label": "",
        "best_l1_fact_ids": [],
        "valid_l1_fact_ids": [],
        "best_fact_sets": [],
        "rationale": (
            "冻结树把 Glucagonoma 同时放入 B1 Metabolic/Endocrine 和 B4 "
            "Neoplastic，B5 还含 Alpha Cell Tumor；任何患者 finding 都无法"
            "区分这些重复叶所属的 L1，故不评分。"
        ),
    },
    "mb57_kartagener": {
        "status": "unscorable",
        "target_l1_branch_id": "",
        "target_l1_label": "",
        "best_l1_fact_ids": [],
        "valid_l1_fact_ids": [],
        "best_fact_sets": [],
        "rationale": (
            "Primary Ciliary Dyskinesia/Kartagener 被重复放入 B1、B4 与 B5；"
            "自出生的鼻窦和支气管表现能识别疾病，却不能决定唯一 L1。"
        ),
    },
    "mb65_cml": {
        "status": "unscorable",
        "target_l1_branch_id": "",
        "target_l1_label": "",
        "best_l1_fact_ids": [],
        "valid_l1_fact_ids": [],
        "best_fact_sets": [],
        "rationale": (
            "自动列表仅含 35% 原始细胞的白细胞增多、贫血及血小板减少，"
            "缺少嗜碱粒细胞增多、脾大或 BCR-ABL；无法可靠区分慢性髓系"
            "增殖性肿瘤与急性髓系肿瘤家族。"
        ),
    },
    "mb66_peliosis": {
        "status": "unscorable",
        "target_l1_branch_id": "",
        "target_l1_label": "",
        "best_l1_fact_ids": [],
        "valid_l1_fact_ids": [],
        "best_fact_sets": [],
        "rationale": (
            "既有动态评测 gold 映射到 B3，但树中 Peliosis Hepatis 明确位于"
            "B5；自动列表又没有显式 AAS 使用或肝血管破裂结果，不能在"
            "不修改 gold 的情况下建立可靠 L1 金标。"
        ),
    },
    "mb77_hyperpara": {
        "status": "unscorable",
        "target_l1_branch_id": "",
        "target_l1_label": "",
        "best_l1_fact_ids": [],
        "valid_l1_fact_ids": [],
        "best_fact_sets": [],
        "rationale": (
            "高钙低磷仍可见于 PTHrP 型恶性高钙血症；标注依赖的 PTH 升高"
            "不在自动列表中，严格口径下不能排除 B3 而确定 B4。"
        ),
    },
    "mb82_adhesions": {
        "status": "scorable",
        "target_l1_branch_id": "B1",
        "target_l1_label": "Gastrointestinal Obstruction",
        "best_l1_fact_ids": ["F16"],
        "valid_l1_fact_ids": ["F15"],
        "best_fact_sets": [["F15", "F16"]],
        "rationale": (
            "右下腹手术瘢痕是机械性粘连梗阻的核心风险线索；鼓音性腹胀"
            "需与瘢痕组合，单独也可见于动力性/假性梗阻。"
        ),
    },
    "mb83_foreignbody": {
        "status": "scorable",
        "target_l1_branch_id": "B2",
        "target_l1_label": "Anatomical Obstruction of the Nasal Cavity",
        "best_l1_fact_ids": ["F11"],
        "valid_l1_fact_ids": ["F3"],
        "best_fact_sets": [],
        "rationale": (
            "单侧脓性并带血鼻分泌物最强地区分机械性异物/解剖性阻塞与"
            "通常双侧的感染、炎症过程。"
        ),
    },
    "mxh011": {
        "status": "unscorable",
        "target_l1_branch_id": "",
        "target_l1_label": "",
        "best_l1_fact_ids": [],
        "valid_l1_fact_ids": [],
        "best_fact_sets": [],
        "rationale": (
            "Epiglottitis 同时作为 B1 Upper Respiratory Infection 与 B3 "
            "Airway Compromise 的冻结叶；流涎、前倾和高热可识别会厌炎，"
            "但无法在两个含同一疾病的 L1 间给出唯一目标。"
        ),
    },
    "mxh014": {
        "status": "scorable",
        "target_l1_branch_id": "B1",
        "target_l1_label": "Infective Endocarditis",
        "best_l1_fact_ids": ["F9"],
        "valid_l1_fact_ids": ["F1", "F4"],
        "best_fact_sets": [["F1", "F9"], ["F4", "F9"]],
        "rationale": (
            "既往人工瓣膜与新发心尖区全收缩期杂音组合，最强地区分"
            "人工瓣膜感染性心内膜炎；慢性低热、消瘦和心动过速为辅助。"
        ),
    },
    "mxh036": {
        "status": "scorable",
        "target_l1_branch_id": "B2",
        "target_l1_label": "Glycogen Storage Disease",
        "best_l1_fact_ids": ["F2"],
        "valid_l1_fact_ids": ["F9"],
        "best_fact_sets": [["F2", "F8"]],
        "rationale": (
            "短时禁食即严重不适与巨大肝脏组合最强地支持肝型糖原贮积病；"
            "无脾大可反证 Gaucher；乳糜血也见于 B1，不能单独计分。"
        ),
    },
    "mxh045": {
        "status": "unscorable",
        "target_l1_branch_id": "",
        "target_l1_label": "",
        "best_l1_fact_ids": [],
        "valid_l1_fact_ids": [],
        "best_fact_sets": [],
        "rationale": (
            "自动列表只有便秘、呕吐和鼓音性腹胀等一般梗阻表现，缺少"
            "胆汁性呕吐、影像或先天旋转异常线索；冻结树的解剖异常与"
            "肠梗阻家族无法由这些事实可靠区分。"
        ),
    },
    "mxh046": {
        "status": "scorable",
        "target_l1_branch_id": "B1",
        "target_l1_label": "Genetic Disorder with Marfanoid Features",
        "best_l1_fact_ids": ["F11"],
        "valid_l1_fact_ids": [],
        "best_fact_sets": [],
        "rationale": (
            "双侧晶状体向下脱位是硫氨基酸代谢病/同型半胱氨酸尿症家族"
            "相对其他马凡样或结缔组织疾病的最佳线索。"
        ),
    },
    "mxh055": {
        "status": "unscorable",
        "target_l1_branch_id": "",
        "target_l1_label": "",
        "best_l1_fact_ids": [],
        "valid_l1_fact_ids": [],
        "best_fact_sets": [],
        "rationale": (
            "Exertional Heat Stroke 同时出现于 B4 和 B5，且 B5 的标签直接"
            "包含伴意识改变的同一诊断；环境与高热事实无法区分重复 L1。"
        ),
    },
    "mxh068": {
        "status": "scorable",
        "target_l1_branch_id": "B2",
        "target_l1_label": "Bacterial Upper Respiratory Infection",
        "best_l1_fact_ids": ["F16"],
        "valid_l1_fact_ids": ["F9"],
        "best_fact_sets": [["F9", "F16"]],
        "rationale": (
            "吸气性喘鸣对消旋肾上腺素无改善最强地区分细菌性气管炎与"
            "病毒性哮吼；高热、脓痰、病容及低氧为辅助。"
        ),
    },
    "mxh075": {
        "status": "unscorable",
        "target_l1_branch_id": "",
        "target_l1_label": "",
        "best_l1_fact_ids": [],
        "valid_l1_fact_ids": [],
        "best_fact_sets": [],
        "rationale": (
            "动态 gold 把 truncus 映射到 B2 Septal Defects，但冻结叶中的"
            "Truncus Arteriosus 明确位于 B4；F12/F14/F15 支持 B4 而非 B2，"
            "应先修 gold-to-tree 映射，当前不评分。"
        ),
    },
}


def apply_manual_gold(payload: dict[str, Any]) -> dict[str, Any]:
    cases = payload.get("cases") or []
    case_ids = {str(row["case_id"]) for row in cases}
    if case_ids != set(MANUAL_GOLD):
        raise ValueError(
            f"manual-gold case mismatch: fixture={sorted(case_ids)}, "
            f"labels={sorted(MANUAL_GOLD)}"
        )
    for row in cases:
        case_id = str(row["case_id"])
        labels = dict(MANUAL_GOLD[case_id])
        allowed = {str(fact["id"]) for fact in row["full_findings"]}
        labeled = set(labels["best_l1_fact_ids"]) | set(
            labels["valid_l1_fact_ids"]
        )
        for fact_set in labels["best_fact_sets"]:
            labeled.update(fact_set)
        if not labeled.issubset(allowed):
            raise ValueError(f"{case_id} gold contains unknown fact IDs")
        labels["shared_or_misleading_fact_ids"] = sorted(
            allowed - labeled,
            key=lambda value: int(value[1:]),
        )
        partition = labeled | set(labels["shared_or_misleading_fact_ids"])
        if partition != allowed:
            raise ValueError(f"{case_id} gold does not cover full catalog")
        row["gold"] = labels
    payload["gold_schema_version"] = 1
    payload["gold_adjudication"] = {
        "target": "best evidence that discriminates frozen L1 families",
        "runtime_visible": False,
        "filter_output_visible_during_adjudication": False,
        "leaf_only_discrimination_counts": False,
        "duplicate_gold_leaf_across_l1_is_unscorable": True,
        "missing_unique_l1_evidence_is_unscorable": True,
        "dynamic_gold_to_tree_conflict_is_unscorable": True,
        "independent_strict_review_applied": True,
        "full_catalog_partitioned": True,
    }
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    bfs._atomic_json(args.fixture, apply_manual_gold(fixture))
    print(json.dumps({
        "cases": len(fixture["cases"]),
        "scorable": sum(
            row["gold"]["status"] == "scorable" for row in fixture["cases"]
        ),
        "unscorable": sum(
            row["gold"]["status"] == "unscorable" for row in fixture["cases"]
        ),
    }, ensure_ascii=False, indent=2))
