#!/usr/bin/env python3
"""Inventory high-stakes extraction slots for the 10 cases besides 475."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))
import run_mechanical_engine as eng  # noqa: E402

SKIP = "MCR_seq200b/475"
FOCUS = {
    "74": [r"long.?qt", r"cpvt", r"catecholaminergic", r"brugada", r"hypertrophic", r"qtc"],
    "49": [r"stump", r"appendic", r"diverticul", r"cecal", r"caecal"],
    "326": [r"brucell", r"epidural", r"abscess", r"tubercul", r"salmonell"],
    "119": [r"porokerat", r"darier", r"grover", r"psoria", r"cornoid", r"eppp"],
    "522": [r"catatonia", r"dementia", r"lewy", r"delirium", r"b12", r"cobalamin", r"vitamin b"],
    "773": [r"eisenmenger", r"foramen", r"pfo", r"pulmonary arterial", r"ipah", r"hypertension"],
    "257": [r"abscess", r"kanavel", r"tenosynov", r"cellulitis", r"osteomyelitis", r"collar", r"web"],
    "56": [r"carcinoma", r"sarcoma", r"leiomyo", r"squamous", r"p63", r"smooth muscle"],
    "91": [r"angiosarcoma", r"hemangioma", r"haemangioma", r"sft", r"solitary fibrous", r"cd31", r"cd34"],
    "179": [r"thrombocytopen", r"hypox", r"atresia", r"vsd", r"platelet"],
}


def uniq_key(a: dict) -> tuple:
    return (
        eng.norm(a.get("subject")),
        (a.get("relation") or "").lower(),
        (a.get("polarity") or "asserted").lower(),
        (a.get("modality") or "").lower(),
        eng.norm(a.get("predicate")),
        (a.get("quote") or "")[:80],
    )


def cid_of(key: str) -> str:
    return key.rsplit("/", 1)[-1]


def focus_hit(cid: str, a: dict) -> bool:
    pats = FOCUS.get(cid) or []
    blob = " ".join(
        str(x or "")
        for x in (a.get("subject"), a.get("predicate"), a.get("quote"), a.get("_focus"), a.get("comparator"))
    )
    return any(re.search(p, blob, re.I) for p in pats)


def dump_slot(title: str, xs: list, limit: int = 80) -> None:
    print(f"\n### {title} n={len(xs)}")
    for i, a in enumerate(xs[:limit], 1):
        th = a.get("threshold") or {}
        ths = ""
        if isinstance(th, dict) and (th.get("operator") or th.get("value") is not None or th.get("relational")):
            ths = f"  thr={th.get('operator')} {th.get('value')} {th.get('unit') or ''} rel={th.get('relational')}"
        cg = a.get("criterion_group") or {}
        gs = ""
        if cg.get("group_id") or cg.get("logic"):
            gs = f"  grp={cg.get('logic')}/{cg.get('n')}"
        print(
            f"[{i}] {a.get('subject')!s}\n"
            f"    {a.get('relation')}/{a.get('polarity')}/{a.get('modality')} ctx={a.get('context_type')} "
            f"kind={a.get('predicate_kind')}{ths}{gs}\n"
            f"    pred={a.get('predicate')}\n"
            f"    quote={(a.get('quote') or '')[:280]}\n"
            f"    title={(a.get('_title') or '')[:90]} focus={a.get('_focus')}"
        )
    if len(xs) > limit:
        print(f"    ... truncated {len(xs) - limit}")


def main() -> int:
    tasks = {t["case_key"]: t for t in json.loads((LEDGER / "trial_tasks_11_all4.json").read_text())}
    ext = json.loads((LEDGER / "trial_extraction_k30all4clean_groups.json").read_text())
    by = {e["case_key"]: e for e in ext}

    for key in sorted(by, key=lambda k: (cid_of(k) != "74", cid_of(k))):
        cid = cid_of(key)
        if key == SKIP:
            continue
        rec = by[key]
        t = tasks[key]
        assertions = [a for a in rec["assertions"] if isinstance(a, dict)]
        seen = {}
        for a in assertions:
            seen.setdefault(uniq_key(a), a)
        uniq = list(seen.values())
        gold = t.get("gold")
        cands = t.get("candidates") or []
        print("\n" + "=" * 92)
        print(f"{key}  gold={gold!r}")
        print(f"raw={len(assertions)} unique={len(uniq)} findings={len(rec.get('findings') or [])} ncand={len(cands)}")
        print("relation unique:", Counter((a.get("relation") or "").lower() for a in uniq).most_common(12))
        illegal = Counter(
            (a.get("relation") or "")
            for a in uniq
            if (a.get("relation") or "").lower() not in eng.LEGAL_RELATIONS
        )
        print("illegal:", illegal.most_common(8))

        req = [a for a in uniq if (a.get("relation") or "").lower() == "required_for"]
        patho = [a for a in uniq if "pathognomonic" in (a.get("relation") or "").lower()]
        suff = [a for a in uniq if (a.get("relation") or "").lower() == "sufficient_for"]
        excl = [a for a in uniq if (a.get("relation") or "").lower() == "excludes"]
        dist = [a for a in uniq if (a.get("relation") or "").lower() == "distinguishes_from"]
        dump_slot("REQUIRED_FOR", req)
        dump_slot("PATHOGNOMONIC", patho)
        dump_slot("SUFFICIENT_FOR", suff)
        dump_slot("EXCLUDES focus-hit", [a for a in excl if focus_hit(cid, a)])
        dump_slot("EXCLUDES other (first 15)", [a for a in excl if not focus_hit(cid, a)], 15)
        dump_slot("DISTINGUISHES focus-hit", [a for a in dist if focus_hit(cid, a)], 20)

        # focus-subject feature_of with threshold or group
        foc_feat = [
            a
            for a in uniq
            if focus_hit(cid, a)
            and (a.get("relation") or "").lower() in {"feature_of", "caused_by", "argues_against"}
            and (
                (isinstance(a.get("threshold"), dict) and (a["threshold"].get("value") is not None or a["threshold"].get("relational")))
                or (a.get("criterion_group") or {}).get("logic")
                or re.search(
                    r"pathognomonic|hallmark|necessary|must|only if|because|when .+ exceed|cornoid|kanavel|qtc|p63|cd34|fluctuan|web space",
                    f"{a.get('predicate')} {a.get('quote')}",
                    re.I,
                )
            )
        ]
        dump_slot("FOCUS FEATURE/CAUSE with thr/group/cue", foc_feat, 40)

        print("\n### FINDINGS")
        for f in rec.get("findings") or []:
            if not isinstance(f, dict):
                continue
            print(
                f"  [{f.get('polarity'):12s}] {str(f.get('label'))[:70]:70s} "
                f"val={f.get('value')} quote={(f.get('quote') or '')[:120]}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
