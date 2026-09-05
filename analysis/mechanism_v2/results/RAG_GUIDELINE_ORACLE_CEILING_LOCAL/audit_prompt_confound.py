#!/usr/bin/env python3
"""Separate the two changes bundled into the passage-scoped group prompt.

The new prompt does two things at once: it lets a group span the whole passage,
and it tells the model to ignore literature inclusion/exclusion criteria (the
S30.4 contamination).  The second one removes groups, so the drop in group
count between the arms cannot be read as the first one failing.  This asks how
many groups in each arm sit in a passage that is about selecting studies.

    python audit_prompt_confound.py
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

STUDY_CRITERIA = re.compile(
    r"\b(?:stud(?:y|ies)|article|paper|manuscript|publication|record|report|"
    r"abstract|literature|review|trial|citation)s?\b[^.]{0,60}\b"
    r"(?:includ|exclud|select|eligib|screen|retriev|search)|"
    r"\b(?:inclusion|exclusion|eligibility)\s+criteri|"
    r"\b(?:peer.?reviewed|full.?text|english.language|grey literature|"
    r"conference abstract|case report)s?\b", re.I)
WS = re.compile(r"\s+")

ARMS = [
    ("old prompt / old index", "trial_extraction_x2_oldidxclean_groups.json",
     "trial_retrieval_x2_oldidx.json"),
    ("new prompt / old index", "trial_extraction_x2_oldidxclean_groups_free.json",
     "trial_retrieval_x2_oldidx.json"),
    ("old prompt / v2 index", "trial_extraction_x2_v2idxclean_groups.json",
     "trial_retrieval_x2_v2idx.json"),
    ("new prompt / v2 index", "trial_extraction_x2_v2idxclean_groups_free.json",
     "trial_retrieval_x2_v2idx.json"),
]


def real(v) -> bool:
    return isinstance(v, str) and v.strip().lower() not in {"", "null", "none"}


def passages(fn: str) -> dict[str, list[str]]:
    data = json.loads((LEDGER / fn).read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for e in data:
        seen, rows = set(), []
        for b in e["retrieved"].values():
            for p in b["passages"]:
                if p["gid"] not in seen:
                    seen.add(p["gid"])
                    rows.append(WS.sub(" ", p["text"]))
        out[e["case_key"]] = rows
    return out


def main() -> int:
    print(f"{'arm':<24}{'groups>=2':>11}{'in study-criteria passage':>28}")
    for name, ext, retr in ARMS:
        pas = passages(retr)
        groups: dict[tuple, list] = {}
        for e in json.loads((LEDGER / ext).read_text(encoding="utf-8")):
            for a in e.get("assertions") or []:
                if not isinstance(a, dict):
                    continue
                gid = (a.get("criterion_group") or {}).get("group_id")
                if not real(gid):
                    continue
                groups.setdefault((e["case_key"], a.get("_source"), a.get("_title"),
                                   a.get("_section"), a.get("_focus"), str(gid)),
                                  []).append(a)
        multi = {k: v for k, v in groups.items() if len(v) >= 2}
        n_study = 0
        for k, v in multi.items():
            q = WS.sub(" ", str(v[0].get("quote") or "")).strip()
            if len(q) < 12:
                continue
            for t in pas.get(k[0], []):
                if q in t:
                    n_study += bool(STUDY_CRITERIA.search(t))
                    break
        print(f"{name:<24}{len(multi):>11}{n_study:>20} {n_study / max(len(multi), 1):>7.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
