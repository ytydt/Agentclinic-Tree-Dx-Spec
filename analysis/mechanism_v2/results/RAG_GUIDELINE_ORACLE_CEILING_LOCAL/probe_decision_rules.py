#!/usr/bin/env python3
"""Verify that each branch of a hand-built decision flow is actually stated.

A hand-built flow is only worth anything if every branch rests on a rule that
exists in the reference corpus rather than on the adjudicator's recall.  Each
probe below is one branch: a regex that must appear in the same passage for the
rule to count as stated, plus the case and the competitor the branch is meant
to exclude.  Passages are printed so the wording can be checked, not just the
hit count.
"""

from __future__ import annotations

import argparse
import json
import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SOURCES = {
    "merck": ROOT / "data/corpus/merck/merck_manual_19e_chunks.jsonl",
    "manifest_cpg": ROOT / "data/cpg/processed/manifest_cpg_chunks.jsonl",
    "wikem": ROOT / "data/cpg/processed/wikem_ddx_chunks.jsonl",
    "pmc_oa": ROOT / "data/cpg/processed/pmc_oa_ddx_chunks.jsonl",
    "statpearls": ROOT / "data/corpus/statpearls/statpearls_chunks.jsonl",
    "textbooks": ROOT / "data/corpus/textbooks/textbooks_chunks.jsonl",
}

PROBES = [
    {
        "case": "DA_d2_heldout200b/773",
        "branch": "PFO 不是大分流；Eisenmenger 需大缺损且 PVR 达体循环水平",
        "excludes": "Eisenmenger Syndrome",
        "all_of": [r"eisenmenger", r"\blarge\b", r"(pulmonary vascular resistance|systemic (level|pressure))"],
    },
    {
        "case": "MCR_seq200b/257",
        "branch": "Kanavel 四征定义化脓性屈肌腱鞘炎",
        "excludes": "Pyogenic Flexor Tenosynovitis",
        "all_of": [r"kanavel", r"(passive extension|fusiform|flexed position)"],
    },
    {
        "case": "MCR_seq200b/257",
        "branch": "collar button / web-space 脓肿是独立实体",
        "excludes": "Cellulitis",
        "all_of": [r"(collar[- ]button|web[- ]space) abscess"],
    },
    {
        "case": "MCR_v1_seq100/74",
        "branch": "CPVT：肾上腺素能触发、QT 正常、心脏结构正常",
        "excludes": "Long QT Syndrome",
        "all_of": [r"catecholaminergic polymorphic", r"(normal (resting )?(qt|ecg|electrocardiogram)|structurally normal)"],
    },
    {
        "case": "MCR_seq200b/475",
        "branch": "神经痛性肌萎缩累及范围超出单一神经，区别于骨间前神经综合征",
        "excludes": "Anterior Interosseous Nerve Syndrome",
        "all_of": [r"(neuralgic amyotrophy|parsonage)", r"(anterior interosseous|brachial plexus)"],
    },
    {
        "case": "MCR_v1_seq100/91",
        "branch": "CD31/Fli-1 为内皮标志；孤立性纤维性肿瘤/血管外皮瘤为 CD34+/Bcl-2+",
        "excludes": "Solitary Fibrous Tumor / Hemangiopericytoma",
        "all_of": [r"cd31", r"(cd34|bcl-?2)", r"(solitary fibrous|hemangiopericytoma|angiosarcoma)"],
    },
    {
        "case": "DA_d2_heldout200b/522",
        "branch": "DLB 核心特征：波动性认知 + 反复视幻觉",
        "excludes": "Catatonia (单独)",
        "all_of": [r"(lewy bod)", r"(fluctuat\w+)", r"(visual hallucination)"],
    },
    {
        "case": "MCR_seq200b/326",
        "branch": "布鲁氏菌病：未消毒乳制品/牲畜暴露 + 脊柱受累",
        "excludes": "Spinal epidural abscess（解剖轴答案）",
        "all_of": [r"brucell", r"(unpasteuri[sz]ed|raw milk|livestock|sheep|goat)"],
    },
    {
        "case": "DA_d2_seq100/119",
        "branch": "角样板层（cornoid lamella）确立汗孔角化症",
        "excludes": "Darier / Grover disease",
        "all_of": [r"cornoid lamella", r"porokeratos"],
    },
    {
        "case": "DA_d2_seq100/5",
        "branch": "巨细胞修复性肉芽肿无细胞异型性，区别于真性巨细胞瘤",
        "excludes": "Giant Cell Tumor",
        "all_of": [r"giant[- ]cell (reparative granuloma|granuloma)", r"(atypia|giant cell tumor)"],
    },
    {
        "case": "MCR_v1_seq100/56",
        "branch": "p63 阳性支持梭形细胞鳞癌（即便 cytokeratin 阴性）",
        "excludes": "Sarcoma / Postradiation Sarcoma",
        "all_of": [r"p63", r"(spindle cell (squamous|carcinoma)|sarcomatoid)"],
    },
    {
        "case": "MCR_v2_seq100/179",
        "branch": "紫绀型先心病的低氧与血小板减少相关",
        "excludes": "Immune thrombocytopenia",
        "all_of": [r"(cyanotic (congenital )?heart|hypoxem)", r"thrombocytopen"],
    },
    {
        "case": "DA_d2_heldout100/272",
        "branch": "肌钙蛋白在发病后 1-3 小时才升高，早期阴性不排除 MI",
        "excludes": "Unstable Angina",
        "all_of": [r"troponin", r"(hyperacute t|1 to 3 hours|within 3 hours|3 h(ours)? after|serial)"],
    },
    {
        "case": "DA_d2_heldout200b/646",
        "branch": "孤立性直肠溃疡综合征由用力排便/脱垂引起，与放射无关",
        "excludes": "Solitary Rectal Ulcer Syndrome",
        "all_of": [r"solitary rectal ulcer", r"(straining|prolapse)"],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-show", type=int, default=2)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL/decision_rule_probe.md")
    args = parser.parse_args()

    for p in PROBES:
        p["regex"] = [re.compile(r, re.I) for r in p["all_of"]]
        p["hits"] = []

    for source, path in SOURCES.items():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                text = row.get("text") or row.get("content") or ""
                if not text:
                    continue
                for p in PROBES:
                    if len(p["hits"]) >= 40:
                        continue
                    if all(r.search(text) for r in p["regex"]):
                        p["hits"].append((source, row.get("title", ""), text))
        print(f"  scanned {source}", flush=True)

    lines = ["# 决策流程分支的语料证据核验", ""]
    for p in PROBES:
        status = "命中" if p["hits"] else "**未命中**"
        lines += [
            f"## {p['case']} — {p['branch']}",
            "",
            f"- 用于排除：{p['excludes']}",
            f"- 匹配式：`{' AND '.join(p['all_of'])}`",
            f"- 结果：{status}（{len(p['hits'])} 段）",
            "",
        ]
        for source, title, text in p["hits"][: args.max_show]:
            sentences = [s.strip() for s in re.split(r"(?<=[.;])\s+", text)
                         if any(r.search(s) for r in p["regex"])]
            lines.append(f"- `{source}` | {str(title)[:80]}")
            for s in sentences[:3]:
                lines.append(textwrap.indent(textwrap.fill(s[:400], 96), "    "))
            lines.append("")
        lines.append("---")
        lines.append("")

    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    hit = sum(1 for p in PROBES if p["hits"])
    print(json.dumps({"probes": len(PROBES), "with_evidence": hit,
                      "missing": [p["case"] + " :: " + p["branch"]
                                  for p in PROBES if not p["hits"]]},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
