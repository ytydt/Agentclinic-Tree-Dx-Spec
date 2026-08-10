#!/usr/bin/env python3
"""Encode why MOSAIC (and msplit) rejected the gold candidate."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))

import disagreement_census as dc
import r5_lib as r5
import r6_lib as r6

OUT = r5.OUT / "mosaic_eval" / "r6_reject_reasons.json"

CATEGORIES = (
    "cited_contradiction",
    "less_specific",
    "prefers_common",
    "fails_key_finding",
    "rarity",
    "no_reason",
    "other",
)

RX = {
    "cited_contradiction": re.compile(
        r"contradict|against|inconsistent|does not explain|fails to account|"
        r"rule.?out|incompatib|argues against",
        re.I,
    ),
    "less_specific": re.compile(
        r"less specific|more general|broader|umbrella|parent|"
        r"not specific enough|too broad|subtype|more precise",
        re.I,
    ),
    "prefers_common": re.compile(
        r"more common|commoner|likelier|more likely|prevalent|"
        r"frequently|typical|usual",
        re.I,
    ),
    "fails_key_finding": re.compile(
        r"does not explain|fails to|missing|cannot account|"
        r"key finding|decisive|hallmark|pathognomon",
        re.I,
    ),
    "rarity": re.compile(r"rare|unlikely|exotic|zebras?\b", re.I),
}


def regex_code(why: str) -> str:
    if not (why or "").strip():
        return "no_reason"
    hits = [k for k, rx in RX.items() if rx.search(why)]
    if not hits:
        return "other"
    # priority
    for pref in (
        "cited_contradiction",
        "fails_key_finding",
        "less_specific",
        "prefers_common",
        "rarity",
    ):
        if pref in hits:
            return pref
    return hits[0]


LLM_PROMPT = """Role: RejectReasonCoder

Classify why a diagnosis was rejected from a shortlist. Pick EXACTLY one label:
- cited_contradiction: the text cites evidence against the rejected label
- less_specific: rejected for being too broad / parent of a more specific winner
- prefers_common: rejected because a more common disease is preferred
- fails_key_finding: rejected because it fails to explain a decisive finding
- rarity: rejected mainly for being rare/unlikely
- no_reason: empty or content-free
- other: none of the above

Return strict JSON: {"label": "...", "confidence": "high|medium|low"}
"""


def collect_gold_rejects() -> list[dict[str, Any]]:
    gold = r5.load_gold()
    rows = []
    for arm in ("forest", "lite", "impc", "adaptive4v2", "msplit"):
        for log_ds, dkey, sl in r5.SLICES:
            if arm in r5.DEV_ONLY and sl.endswith("200b"):
                continue
            if r5.run_dir(log_ds, arm) is None:
                continue
            for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
                g = gold[(dkey, sl, cid)]
                doc = r6.load_raw_doc(log_ds, arm, cid)
                if not doc:
                    continue
                if arm == "msplit":
                    sel = (doc.get("stages") or {}).get("frontier_selector") or {}
                    final = sel.get("final") or {}
                    for a in final.get("assessment") or []:
                        if not isinstance(a, dict):
                            continue
                        lab = str(a.get("label") or "")
                        if lab and dc.match(lab, g):
                            fails = a.get("fails") or []
                            why = "; ".join(str(x) for x in fails) if fails else ""
                            if why or fails:
                                rows.append(
                                    {
                                        "dataset": dkey,
                                        "slice": sl,
                                        "case_id": cid,
                                        "arm": arm,
                                        "gold": g,
                                        "why": why,
                                        "source": "msplit_assessment",
                                    }
                                )
                else:
                    info = r6.mosaic_selector_reject_gold(doc, g)
                    if info.get("gold_rejected"):
                        rows.append(
                            {
                                "dataset": dkey,
                                "slice": sl,
                                "case_id": cid,
                                "arm": arm,
                                "gold": g,
                                "why": info.get("gold_reject_why") or "",
                                "source": "mosaic_selector",
                            }
                        )
    return rows


def llm_code(rows: list[dict], limit: int = 120) -> dict[str, str]:
    """Optional LLM coding for a sample; returns id->label."""
    try:
        import baseline_common as bc
        from agentclinic_tree_dx.llm_client import RobustLLMClient
    except Exception as e:
        print("LLM unavailable:", e)
        return {}
    out_dir = r5.OUT / "mosaic_eval" / "r6_reject_cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    client = RobustLLMClient(
        model="meta-llama/llama-3.3-70b-instruct",
        call_timeout=120,
        max_retries=3,
        timeout_retry_cap=1,
        temperature=0.0,
    )
    cached = bc.SimpleCachedLLM(
        client, out_dir / "reject_coder.json", "meta-llama/llama-3.3-70b-instruct"
    )
    coded = {}
    for r in rows[:limit]:
        rid = f"{r['arm']}:{r['dataset']}:{r['slice']}:{r['case_id']}"
        try:
            resp = cached.call(
                "RejectReasonCoder",
                LLM_PROMPT,
                {"rejected_label": r["gold"], "why": r["why"][:800]},
            )
            lab = str((resp or {}).get("label") or "").strip()
            if lab in CATEGORIES:
                coded[rid] = lab
        except Exception as e:
            print("LLM err", rid, e)
    return coded


def main() -> int:
    print("collecting gold rejects…")
    rows = collect_gold_rejects()
    print(f"n_gold_rejected={len(rows)}")
    for r in rows:
        r["regex_label"] = regex_code(r["why"])
    print("LLM coding sample…")
    llm = llm_code(rows, limit=min(150, len(rows)))
    agree = 0
    compared = 0
    for r in rows:
        rid = f"{r['arm']}:{r['dataset']}:{r['slice']}:{r['case_id']}"
        if rid in llm:
            r["llm_label"] = llm[rid]
            compared += 1
            agree += int(llm[rid] == r["regex_label"])
        else:
            r["llm_label"] = ""
    agree_rate = round(agree / compared, 4) if compared else None
    # prefer llm when present else regex
    for r in rows:
        r["final_label"] = r["llm_label"] or r["regex_label"]

    by_arm: dict[str, Counter] = {}
    for r in rows:
        by_arm.setdefault(r["arm"], Counter())[r["final_label"]] += 1

    # only trust category distribution if agree_rate high enough OR report both
    trust = bool(agree_rate is not None and agree_rate >= 0.7)

    summary = {
        "n_gold_rejected": len(rows),
        "by_arm_n": {a: sum(c.values()) for a, c in by_arm.items()},
        "by_arm_label": {a: dict(c) for a, c in by_arm.items()},
        "regex_marginal": dict(Counter(r["regex_label"] for r in rows)),
        "llm_n": compared,
        "regex_llm_agree_rate": agree_rate,
        "trust_final_labels": trust,
        "note": (
            "Final labels use LLM when available else regex. "
            "Distributions are evidentiary only if trust_final_labels."
        ),
        "examples": [
            {
                "arm": r["arm"],
                "case": f"{r['dataset']}/{r['slice']}/{r['case_id']}",
                "label": r["final_label"],
                "why": r["why"][:240],
            }
            for r in rows[:15]
        ],
    }
    r6.write_json(OUT, summary)
    # also dump detail
    r6.write_json(OUT.with_name("r6_reject_reasons_detail.json"), rows)
    print(json.dumps({k: summary[k] for k in (
        "n_gold_rejected", "by_arm_n", "by_arm_label", "regex_llm_agree_rate", "trust_final_labels"
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
