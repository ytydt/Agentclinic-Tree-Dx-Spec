#!/usr/bin/env python3
"""When a passage does state a criteria set, what logic comes back out?

audit_compound_criteria.py established that the corpus carries compound criteria
and that the extractor's groups are overwhelmingly `any`, which the engine can
never read rigidly.  This joins the two sides: take the passages whose own words
enumerate a criteria set, find the assertions drawn from them, and compare the
logic the extractor assigned against the logic the sentence states.

    python audit_criteria_fidelity.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_compound_criteria import COMPOUND  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

# the sentence says how many of the set are needed
N_OF_M = re.compile(
    r"\b(?:at least\s+)?(two|three|four|five|2|3|4|5|both|all)\b[^.]{0,40}?"
    r"\bof\s+(?:the\s+)?(?:following|these|above|(?:\w+\s+){0,2}criteria)\b", re.I)
ALL_OF = COMPOUND["all_of"]
ANY_OF = COMPOUND["any_of"]


def passages(files: tuple[str, ...] | None = None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for fn in files or ("trial_retrieval_k30all4.json",
                        "trial_retrieval_pool37k30all4.json"):
        p = LEDGER / fn
        if not p.exists():
            continue
        data = json.loads(p.read_text("utf-8"))
        for entry in (data if isinstance(data, list) else data.values()):
            for bundle in (entry.get("retrieved") or {}).values():
                for pas in (bundle.get("passages") or []):
                    if pas.get("text"):
                        out.setdefault(str(pas.get("gid") or pas["text"][:80]), pas)
    return out


def stated_logic(txt: str) -> str | None:
    if ALL_OF.search(txt):
        return "all"
    if ANY_OF.search(txt):
        return "any"
    m = N_OF_M.search(txt)
    if not m:
        return None
    w = m.group(1).lower()
    if w == "all":
        return "all"
    if w == "both":
        return "all"
    return "at_least_n"


def main() -> int:
    pas = passages()
    crit = {g: p for g, p in pas.items() if stated_logic(p["text"])}
    print(f"passages whose own words enumerate a criteria set: "
          f"{len(crit)}/{len(pas)}")
    print("  stated logic:",
          dict(Counter(stated_logic(p["text"]) for p in crit.values())))

    rows = []
    for fn in ("trial_extraction_k30all4clean_groups.json",
               "trial_extraction_pool6k30all4clean_groups.json"):
        p = LEDGER / fn
        if not p.exists():
            continue
        for entry in json.loads(p.read_text("utf-8")):
            for a in entry.get("assertions") or []:
                if isinstance(a, dict) and a.get("quote"):
                    rows.append(a)
    print(f"assertions: {len(rows)}")

    # an assertion belongs to a criteria passage when its quote sits inside one
    texts = [(g, " ".join(p["text"].split())) for g, p in crit.items()]
    linked: dict[str, list[dict]] = defaultdict(list)
    for a in rows:
        q = " ".join((a.get("quote") or "").split())
        if len(q) < 12:
            continue
        for g, t in texts:
            if q in t:
                linked[g].append(a)
                break

    n_link = sum(len(v) for v in linked.values())
    print(f"assertions drawn from a criteria passage: {n_link} "
          f"across {len(linked)} passages\n")

    got: Counter = Counter()
    conf: Counter = Counter()
    for g, items in linked.items():
        want = stated_logic(crit[g]["text"])
        for a in items:
            cg = a.get("criterion_group") or {}
            lg = cg.get("logic") if cg.get("group_id") else None
            got[lg or "NO_GROUP"] += 1
            conf[(want, lg or "NO_GROUP")] += 1

    print("logic the extractor assigned to assertions from criteria passages:")
    for k, v in got.most_common():
        print(f"  {str(k):<14}{v:>6}  {v / n_link:6.1%}")

    print("\nstated in the sentence  ->  emitted by the extractor")
    for (want, gotl), v in sorted(conf.items(), key=lambda x: -x[1]):
        mark = "  <- match" if want == gotl else ""
        print(f"  {str(want):<12} -> {str(gotl):<14}{v:>6}{mark}")

    agree = sum(v for (w, g_), v in conf.items() if w == g_)
    print(f"\nlogic preserved: {agree}/{n_link} = {agree / n_link:.1%}"
          if n_link else "")

    print("\nexamples: a sentence that states a criteria set, and what came out")
    shown = 0
    for g, items in linked.items():
        want = stated_logic(crit[g]["text"])
        if want != "at_least_n" or shown >= 4:
            continue
        m = N_OF_M.search(crit[g]["text"])
        print(f"\n  stated={want}  ...{crit[g]['text'][max(0, m.start() - 90):m.end() + 110]}...")
        for a in items[:4]:
            cg = a.get("criterion_group") or {}
            print(f"    -> [{a.get('relation')}/{cg.get('logic') or 'NO_GROUP'}"
                  f"{'/n=' + str(cg.get('n')) if cg.get('n') else ''}] "
                  f"{(a.get('predicate') or '')[:60]}")
        shown += 1

    json.dump({"n_criteria_passages": len(crit), "n_passages": len(pas),
               "n_linked_assertions": n_link,
               "assigned": {str(k): v for k, v in got.items()},
               "confusion": {f"{w}->{g_}": v for (w, g_), v in conf.items()}},
              (LEDGER / "criteria_fidelity_audit.json").open("w"), indent=2)
    print(f"\nwrote {LEDGER / 'criteria_fidelity_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
