#!/usr/bin/env python3
"""Adjudicate whether each located chunk actually *asserts* its rule.

audit_branch_retrievability.py can only show that a chunk contains both the
subject and the predicate pattern.  Reading the retrieved passages shows that
co-occurrence is frequently vacuous -- a liver-biopsy marker table matches
"angiosarcoma + CD31", and a paediatrics table matches "cyanotic heart disease
+ thrombocytopenia" because they are different rows of the same table.  This
freezes the reading of each passage so the coverage figures reflect assertions
rather than string hits.

status
    stated              top passage states the rule
    stated_but_buried   the rule exists in the corpus, but the highest-ranked
                        co-occurring passage is vacuous
    partial             only part of the rule is stated
    split               subject and predicate never share a chunk
    absent              no passage states it
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
AUDIT = OUT_DIR / "branch_retrievability.json"

ADJUDICATION: dict[str, dict] = {
    "522.a": {"status": "stated", "note": "merck: 波动性认知是路易体痴呆相对特异的特征"},
    "522.b": {"status": "stated", "note": "merck: 波动性认知+帕金森症状+成形视幻觉提示 DLB"},
    "522.c": {"status": "stated", "note": "merck: 紧张症亚型含回声动作与言语模仿"},
    "773.a": {"status": "stated_but_buried",
              "note": "首位命中是心衰章节；真正陈述在 merck Ch.293（大量左向右分流未治疗可致 Eisenmenger）"},
    "773.b": {"status": "stated", "note": "merck Ch.293: 体循环压力与阻力高于肺循环，逆转即 Eisenmenger 反应"},
    "773.c": {"status": "absent", "note": "未见任何段落陈述 PFO 不构成大量分流；首位命中为卒中章节腔隙性梗死"},
    "119.a": {"status": "stated", "note": "statpearls: 汗孔角化症以角样板层为特征"},
    "119.b": {"status": "stated", "note": "statpearls 单篇列出 eruptive pruritic papular porokeratosis 变体"},
    "257.a": {"status": "stated", "note": "merck 标题即 Kanavel 征；statpearls 给出四征完整定义"},
    "257.b": {"status": "stated", "note": "merck: 掌部脓肿包含 collar-button abscess"},
    "326.a": {"status": "stated", "note": "merck: B. melitensis 来自绵羊与山羊"},
    "326.b": {"status": "stated", "note": "manifest_cpg（IDSA 椎体骨髓炎指南）述布鲁氏菌脊柱受累"},
    "326.c": {"status": "stated_but_buried",
              "note": "首位命中为革兰阴性菌致 DIC；布鲁氏菌属革兰阴性的陈述在 merck 第 135 章标题层"},
    "475.a": {"status": "stated", "note": "merck: 急性臂丛神经炎=神经痛性肌萎缩=Parsonage-Turner"},
    "475.b": {"status": "stated", "note": "pmc_oa: AIN 支配 FPL、FDP II-III、旋前方肌"},
    "49.a": {"status": "stated", "note": "statpearls: 残端阑尾炎定义，并给出残端 ≤5 mm 的阈值"},
    "74.a": {"status": "stated", "note": "manifest_cpg/pmc_oa: CPVT 见于心脏结构正常者"},
    "74.b": {"status": "stated", "note": "manifest_cpg: 运动诱发的多形性室早提示 CPVT"},
    "74.c": {"status": "stated", "note": "manifest_cpg: QTc >480 ms 为延长阈值，可直接与 vignette 的 380 ms 比较"},
    "74.d": {"status": "stated", "note": "pmc_oa: 室壁厚度 ≥15 mm 定义肥厚型心肌病"},
    "56.a": {"status": "stated", "note": "pmc_oa: p40/p63 为鳞状分化最特异标志"},
    "56.b": {"status": "stated_but_buried",
             "note": "首位命中为间皮瘤；肉瘤样鳞癌可仅灶性表达角蛋白的陈述在同刊另一段"},
    "91.a": {"status": "stated_but_buried",
             "note": "首位命中为肝活检标志物表；真正陈述在 statpearls 皮肤血管肉瘤段（CD34/CD31 为必要染色）"},
    "91.b": {"status": "partial",
             "note": "语料有孤立性纤维性肿瘤的 STAT6 重排，但无 CD34+/Bcl-2+ 与内皮标志的对照表述"},
    "179.a": {"status": "split", "note": "免疫性血小板减少与 IVIG 无应答从未同处一个切片"},
    "179.b": {"status": "absent",
              "note": "唯一命中是 Nelson 表 149-1：红细胞增多与血小板减少是同一表格的不同行，属表格伪共现"},
}

# Which assertions a case actually needs.  773.c is dispensable because 773.b
# already excludes Eisenmenger on the pressure criterion; 56.b is dispensable
# because 56.a alone establishes epithelial origin.
REQUIRED = {
    "DA_d2_heldout200b/522": ["522.a", "522.b", "522.c"],
    "DA_d2_heldout200b/773": ["773.a", "773.b"],
    "DA_d2_seq100/119": ["119.a", "119.b"],
    "MCR_seq200b/257": ["257.a", "257.b"],
    "MCR_seq200b/326": ["326.a", "326.b", "326.c"],
    "MCR_seq200b/475": ["475.a", "475.b"],
    "MCR_v1_seq100/49": ["49.a"],
    "MCR_v1_seq100/74": ["74.a", "74.b", "74.c", "74.d"],
    "MCR_v1_seq100/56": ["56.a"],
    "MCR_v1_seq100/91": ["91.a", "91.b"],
    "MCR_v2_seq100/179": ["179.a", "179.b"],
}
USABLE = {"stated", "stated_but_buried"}


def main() -> int:
    audit = {r["id"]: r for r in json.loads(AUDIT.read_text(encoding="utf-8"))}
    rows = []
    for aid, adj in ADJUDICATION.items():
        a = audit[aid]
        rows.append({
            "assertion_id": aid,
            "case": a["case"],
            "kind": a["kind"],
            "subject": a["subject"],
            "predicate": a["predicate"],
            "containment_by_pattern": a["containment"],
            "adjudicated_status": adj["status"],
            "usable_from_single_chunk": adj["status"] in USABLE,
            "threshold_needed": a["threshold_needed"],
            "subject_in_vignette": a["subject_in_vignette"],
            "needs_hypothesis_conditioned_retrieval": not a["subject_in_vignette"],
            "n_cooccurring_docs": a["n_complete_chunks"],
            "note": adj["note"],
        })

    out = OUT_DIR / "assertion_adjudication_26.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    by_id = {r["assertion_id"]: r for r in rows}
    case_ready = {}
    for case, need in REQUIRED.items():
        missing = [i for i in need if not by_id[i]["usable_from_single_chunk"]]
        case_ready[case] = {"required": need, "missing": missing, "ready": not missing}

    summary = {
        "assertions": len(rows),
        "cases": len(REQUIRED),
        "status": dict(Counter(r["adjudicated_status"] for r in rows)),
        "usable_from_single_chunk": sum(1 for r in rows if r["usable_from_single_chunk"]),
        "needs_hypothesis_conditioned_retrieval": sum(
            1 for r in rows if r["needs_hypothesis_conditioned_retrieval"]),
        "thresholds_required": sum(1 for r in rows if r["threshold_needed"]),
        "cases_fully_covered": sum(1 for v in case_ready.values() if v["ready"]),
        "cases_blocked": {k: v["missing"] for k, v in case_ready.items() if not v["ready"]},
        "median_cooccurring_docs_per_assertion": sorted(
            r["n_cooccurring_docs"] for r in rows)[len(rows) // 2],
    }
    (OUT_DIR / "assertion_adjudication_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
