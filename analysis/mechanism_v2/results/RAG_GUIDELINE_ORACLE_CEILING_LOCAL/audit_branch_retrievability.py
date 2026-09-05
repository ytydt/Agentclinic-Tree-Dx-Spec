#!/usr/bin/env python3
"""Can retrieval deliver every chunk a hand-built decision flow needs?

Each branch of the 11 separable flows is decomposed into atomic assertions of
the form (subject, predicate, [threshold]).  For every assertion this measures
three things that decide whether a mechanical rule builder could ever be fed:

``containment``   is the whole assertion inside one chunk, or split across
                  chunks of one document, or absent?  A split assertion cannot
                  be extracted from a single retrieved unit.
``anchor``        what is the retrieved chunk *about*?  Exclusion rules live in
                  documents about the competitor, not about the gold, so a
                  vignette-driven query cannot reach them.
``vignette_reach``does the vignette contain the anchor term at all?  If not,
                  retrieval has to be conditioned on the hypothesis rather than
                  on the case text.

No model calls: matching is regex over the frozen corpus.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
LEDGER_DIR = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
WORKSHEET = LEDGER_DIR / "manual_tree_worksheet.md"

SOURCES = {
    "merck": ROOT / "data/corpus/merck/merck_manual_19e_chunks.jsonl",
    "manifest_cpg": ROOT / "data/cpg/processed/manifest_cpg_chunks.jsonl",
    "wikem": ROOT / "data/cpg/processed/wikem_ddx_chunks.jsonl",
    "pmc_oa": ROOT / "data/cpg/processed/pmc_oa_ddx_chunks.jsonl",
    "statpearls": ROOT / "data/corpus/statpearls/statpearls_chunks.jsonl",
    "textbooks": ROOT / "data/corpus/textbooks/textbooks_chunks.jsonl",
}

# subject = the diagnosis the assertion is about; predicate = the finding or
# rule; threshold = a numeric cut-off the mechanical builder would need as a
# first-class value rather than as prose.
ASSERTIONS: list[dict[str, Any]] = [
    # --- DA_d2_heldout200b/522 -------------------------------------------------
    {"case": "DA_d2_heldout200b/522", "id": "522.a", "kind": "inclusion",
     "subject": "Dementia with Lewy bodies", "predicate": "波动性认知是相对特异特征",
     "subject_re": r"lewy bod", "predicate_re": r"fluctuat\w+ cognit|cognitive fluctuat"},
    {"case": "DA_d2_heldout200b/522", "id": "522.b", "kind": "inclusion",
     "subject": "Dementia with Lewy bodies", "predicate": "成形视幻觉",
     "subject_re": r"lewy bod", "predicate_re": r"visual hallucination"},
    {"case": "DA_d2_heldout200b/522", "id": "522.c", "kind": "inclusion",
     "subject": "Catatonia", "predicate": "回声动作/模仿顺从/缄默/凝视为紧张症体征",
     "subject_re": r"catatoni", "predicate_re": r"echopraxia|mutism|waxy flexibility|negativism"},
    # --- DA_d2_heldout200b/773 -------------------------------------------------
    {"case": "DA_d2_heldout200b/773", "id": "773.a", "kind": "exclusion",
     "subject": "Eisenmenger syndrome", "predicate": "需大量左向右分流",
     "subject_re": r"eisenmenger", "predicate_re": r"large (left-to-right |)shunt|large (vsd|asd|pda)"},
    {"case": "DA_d2_heldout200b/773", "id": "773.b", "kind": "exclusion",
     "subject": "Eisenmenger syndrome", "predicate": "肺血管阻力/压力达体循环水平",
     "subject_re": r"eisenmenger", "predicate_re": r"systemic (level|pressure|resistance)",
     "threshold": "PAP >= systemic"},
    {"case": "DA_d2_heldout200b/773", "id": "773.c", "kind": "attribute",
     "subject": "Patent foramen ovale", "predicate": "非大型缺损/不引起容量超负荷",
     "subject_re": r"patent foramen ovale|\bpfo\b", "predicate_re": r"small|not .{0,20}shunt|no .{0,20}shunt"},
    # --- DA_d2_seq100/119 ------------------------------------------------------
    {"case": "DA_d2_seq100/119", "id": "119.a", "kind": "inclusion",
     "subject": "Porokeratosis", "predicate": "角样板层为组织学标志",
     "subject_re": r"porokeratos", "predicate_re": r"cornoid lamella"},
    {"case": "DA_d2_seq100/119", "id": "119.b", "kind": "taxonomy",
     "subject": "Eruptive pruritic papular porokeratosis", "predicate": "为汗孔角化症的变体",
     "subject_re": r"eruptive pruritic papular porokeratosis", "predicate_re": r"variant|form"},
    # --- MCR_seq200b/257 -------------------------------------------------------
    {"case": "MCR_seq200b/257", "id": "257.a", "kind": "exclusion",
     "subject": "Pyogenic flexor tenosynovitis", "predicate": "Kanavel 四征",
     "subject_re": r"flexor tenosynovitis", "predicate_re": r"kanavel",
     "threshold": "4 of 4 signs"},
    {"case": "MCR_seq200b/257", "id": "257.b", "kind": "inclusion",
     "subject": "Collar-button abscess", "predicate": "指蹼/掌间隙脓肿实体",
     "subject_re": r"collar[- ]button abscess", "predicate_re": r"palm|web[- ]space|interdigital"},
    # --- MCR_seq200b/326 -------------------------------------------------------
    {"case": "MCR_seq200b/326", "id": "326.a", "kind": "inclusion",
     "subject": "Brucellosis", "predicate": "绵羊/山羊/未消毒乳制品暴露",
     "subject_re": r"brucell", "predicate_re": r"sheep|goat|unpasteuri[sz]ed|raw milk"},
    {"case": "MCR_seq200b/326", "id": "326.b", "kind": "inclusion",
     "subject": "Brucellosis", "predicate": "累及脊柱/脊柱炎",
     "subject_re": r"brucell", "predicate_re": r"spondylitis|spinal|vertebra"},
    {"case": "MCR_seq200b/326", "id": "326.c", "kind": "attribute",
     "subject": "Brucella", "predicate": "革兰阴性球杆菌",
     "subject_re": r"brucell", "predicate_re": r"gram-negative"},
    # --- MCR_seq200b/475 -------------------------------------------------------
    {"case": "MCR_seq200b/475", "id": "475.a", "kind": "taxonomy",
     "subject": "Parsonage-Turner syndrome", "predicate": "等同神经痛性肌萎缩/急性臂丛神经炎",
     "subject_re": r"parsonage", "predicate_re": r"neuralgic amyotrophy|brachial neuritis"},
    {"case": "MCR_seq200b/475", "id": "475.b", "kind": "exclusion",
     "subject": "Anterior interosseous nerve syndrome", "predicate": "支配范围限于 FDP/旋前方肌",
     "subject_re": r"anterior interosseous", "predicate_re": r"flexor pollicis longus|pronator quadratus|flexor digitorum profundus"},
    # --- MCR_v1_seq100/49 ------------------------------------------------------
    {"case": "MCR_v1_seq100/49", "id": "49.a", "kind": "inclusion",
     "subject": "Stump appendicitis", "predicate": "阑尾切除后残端炎症",
     "subject_re": r"stump appendicitis", "predicate_re": r"append(ectomy|iceal stump)",
     "threshold": "stump length > 5 mm"},
    # --- MCR_v1_seq100/74 ------------------------------------------------------
    {"case": "MCR_v1_seq100/74", "id": "74.a", "kind": "inclusion",
     "subject": "CPVT", "predicate": "心脏结构正常",
     "subject_re": r"catecholaminergic polymorphic", "predicate_re": r"structurally normal"},
    {"case": "MCR_v1_seq100/74", "id": "74.b", "kind": "inclusion",
     "subject": "CPVT", "predicate": "肾上腺素能/运动或情绪应激触发",
     "subject_re": r"catecholaminergic polymorphic", "predicate_re": r"adrenergic|exercise|emotional"},
    {"case": "MCR_v1_seq100/74", "id": "74.c", "kind": "exclusion",
     "subject": "Long QT syndrome", "predicate": "QTc 延长阈值",
     "subject_re": r"long qt syndrome", "predicate_re": r"qtc?[^.]{0,40}(4[4-9]0|5[0-9]0)\s*(ms|msec|milliseconds)",
     "threshold": "QTc >= 440-480 ms"},
    {"case": "MCR_v1_seq100/74", "id": "74.d", "kind": "exclusion",
     "subject": "Hypertrophic cardiomyopathy", "predicate": "室壁厚度阈值",
     "subject_re": r"hypertrophic cardiomyopathy", "predicate_re": r"wall thickness[^.]{0,40}(1[3-9]|\d)\s*mm",
     "threshold": "wall thickness >= 15 mm"},
    # --- MCR_v1_seq100/56 ------------------------------------------------------
    {"case": "MCR_v1_seq100/56", "id": "56.a", "kind": "inclusion",
     "subject": "Spindle cell / sarcomatoid squamous cell carcinoma", "predicate": "p63/p40 阳性提示上皮起源",
     "subject_re": r"sarcomatoid|spindle cell (squamous|carcinoma)", "predicate_re": r"p63|p40"},
    {"case": "MCR_v1_seq100/56", "id": "56.b", "kind": "attribute",
     "subject": "Sarcomatoid SCC", "predicate": "可为细胞角蛋白阴性",
     "subject_re": r"sarcomatoid|spindle cell (squamous|carcinoma)",
     "predicate_re": r"cytokeratin[^.]{0,40}(negative|loss)|negative[^.]{0,30}cytokeratin"},
    # --- MCR_v1_seq100/91 ------------------------------------------------------
    {"case": "MCR_v1_seq100/91", "id": "91.a", "kind": "inclusion",
     "subject": "Angiosarcoma", "predicate": "CD31/Fli-1 内皮标志",
     "subject_re": r"angiosarcoma", "predicate_re": r"cd31|fli-?1"},
    {"case": "MCR_v1_seq100/91", "id": "91.b", "kind": "exclusion",
     "subject": "Solitary fibrous tumour / hemangiopericytoma", "predicate": "CD34/Bcl-2/STAT6 阳性",
     "subject_re": r"solitary fibrous tumou?r|hemangiopericytoma", "predicate_re": r"cd34|bcl-?2|stat6"},
    # --- MCR_v2_seq100/179 -----------------------------------------------------
    {"case": "MCR_v2_seq100/179", "id": "179.a", "kind": "exclusion",
     "subject": "Immune thrombocytopenia", "predicate": "IVIG 无应答不支持免疫机制",
     "subject_re": r"immune thrombocytopen", "predicate_re": r"(ivig|intravenous immunoglobulin)[^.]{0,60}(no |lack|fail|refractor)"},
    {"case": "MCR_v2_seq100/179", "id": "179.b", "kind": "inclusion",
     "subject": "Cyanotic congenital heart disease", "predicate": "低氧致血小板减少",
     "subject_re": r"cyanotic (congenital )?heart", "predicate_re": r"thrombocytopen"},
]


def norm_title(row: dict[str, Any]) -> str:
    return str(row.get("title") or row.get("entry_title") or "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=LEDGER_DIR / "branch_retrievability.json")
    parser.add_argument("--keep", type=int, default=25)
    args = parser.parse_args()

    for a in ASSERTIONS:
        a["s_re"] = re.compile(a["subject_re"], re.I)
        a["p_re"] = re.compile(a["predicate_re"], re.I)
        a["complete"] = []          # one chunk carries subject AND predicate
        a["subject_only_docs"] = set()
        a["predicate_only_docs"] = set()
        a["complete_docs"] = set()

    def doc_key(source: str, row: dict[str, Any]) -> tuple[str, str]:
        if source in {"statpearls", "textbooks"}:
            return (source, str(row.get("article_id") or row.get("title") or ""))
        return (source, str(row.get("source_id") or row.get("article_id") or ""))

    for source, path in SOURCES.items():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                text = row.get("text") or row.get("content") or ""
                if not text:
                    continue
                for a in ASSERTIONS:
                    s = bool(a["s_re"].search(text))
                    p = bool(a["p_re"].search(text))
                    if not (s or p):
                        continue
                    dk = doc_key(source, row)
                    if s and p:
                        a["complete_docs"].add(dk)
                        if len(a["complete"]) < args.keep:
                            a["complete"].append({
                                "source": source,
                                "chunk_id": str(row.get("id", "")),
                                "title": norm_title(row)[:120],
                                "section_path": str(row.get("section_path", ""))[:120],
                                "tokens": row.get("tokens"),
                                "snippet": next(
                                    (x.strip()[:300] for x in re.split(r"(?<=[.;])\s+", text)
                                     if a["p_re"].search(x)), text[:300]),
                            })
                    elif s:
                        a["subject_only_docs"].add(dk)
                    else:
                        a["predicate_only_docs"].add(dk)
        print(f"  scanned {source}", flush=True)

    vignettes = WORKSHEET.read_text(encoding="utf-8")

    out: list[dict[str, Any]] = []
    for a in ASSERTIONS:
        split_docs = (a["subject_only_docs"] & a["predicate_only_docs"]) - a["complete_docs"]
        if a["complete"]:
            containment = "single_chunk"
        elif split_docs:
            containment = "split_across_chunks"
        else:
            containment = "absent"

        anchors = [c["title"] for c in a["complete"][:8]]
        # Does the anchor concept appear in the case's own vignette?  Crude but
        # sufficient: the subject pattern is searched in the worksheet section
        # for this case only.
        block = ""
        marker = f"## {a['case']} "
        if marker in vignettes:
            block = vignettes.split(marker, 1)[1].split("\n## ", 1)[0]
        vign = block.split("### vignette", 1)[1] if "### vignette" in block else ""
        hyps = block.split("### 待分离的假设集", 1)[1].split("### vignette")[0] if "### 待分离的假设集" in block else ""
        out.append({
            "case": a["case"], "id": a["id"], "kind": a["kind"],
            "subject": a["subject"], "predicate": a["predicate"],
            "threshold_needed": a.get("threshold", ""),
            "containment": containment,
            "n_complete_chunks": len(a["complete_docs"]),
            "n_split_docs": len(split_docs),
            "anchor_titles": anchors,
            "subject_in_vignette": bool(a["s_re"].search(vign)),
            "subject_in_hypothesis_set": bool(a["s_re"].search(hyps)),
            "evidence": a["complete"][:2],
        })

    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    c_cont = Counter(r["containment"] for r in out)
    needs_hyp = [r for r in out if not r["subject_in_vignette"] and r["subject_in_hypothesis_set"]]
    unreachable = [r for r in out if not r["subject_in_vignette"] and not r["subject_in_hypothesis_set"]]
    summary = {
        "assertions": len(out),
        "cases": len({r["case"] for r in out}),
        "containment": dict(c_cont),
        "subject_present_in_vignette": sum(1 for r in out if r["subject_in_vignette"]),
        "subject_only_in_hypothesis_set": len(needs_hyp),
        "subject_in_neither": len(unreachable),
        "thresholds_required": sum(1 for r in out if r["threshold_needed"]),
        "absent_assertions": [r["id"] + " :: " + r["subject"] + " / " + r["predicate"]
                              for r in out if r["containment"] == "absent"],
        "split_assertions": [r["id"] for r in out if r["containment"] == "split_across_chunks"],
        "vignette_unreachable": [r["id"] for r in unreachable],
    }
    (LEDGER_DIR / "branch_retrievability_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
