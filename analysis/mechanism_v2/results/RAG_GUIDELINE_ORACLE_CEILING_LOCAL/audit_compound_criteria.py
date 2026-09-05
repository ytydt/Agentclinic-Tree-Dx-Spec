#!/usr/bin/env python3
"""Where do compound diagnostic criteria get lost?

Guidelines state rigid criteria as combinations -- "2 of the following four",
"A and B", "all of the following" -- yet the engine settles almost everything by
weighted summation.  Three places that could be responsible, measured in order:

  corpus      do the retrieved passages actually contain such language;
  extraction  does the extractor emit a criterion_group for them;
  engine      do those groups survive grouping and reach a rigid outcome.

    python audit_compound_criteria.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_mechanical_engine as eng  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

# Wording guidelines use when a criterion is a combination rather than a single
# finding.  Kept deliberately literal: each alternative is a phrase a clinician
# would recognise as introducing a criteria set.
COMPOUND = {
    "n_of_m": re.compile(
        r"\b(?:at least|a minimum of|two|three|four|five|2|3|4|5)\s+"
        r"(?:or more\s+)?(?:of\s+(?:the\s+)?(?:following|these|above)|criteria|"
        r"features|findings|signs|symptoms)\b", re.I),
    "all_of": re.compile(r"\ball of the (?:following|above)\b|"
                         r"\beach of the (?:following|above)\b", re.I),
    "any_of": re.compile(r"\bany of the (?:following|above)\b|"
                         r"\bone or more of the (?:following|above)\b", re.I),
    "and_or": re.compile(r"\band/or\b", re.I),
    "criteria_word": re.compile(r"\bcriteri(?:on|a)\b", re.I),
    "in_addition_to": re.compile(r"\bin addition to\b|\btogether with\b|"
                                 r"\baccompanied by\b", re.I),
    "plus_conj": re.compile(r"\bdiagnos\w+.{0,60}\b(?:both|combination of)\b", re.I),
}


def corpus_side() -> dict:
    hits: Counter = Counter()
    n_pass = 0
    seen: set[str] = set()
    for fn in ("trial_retrieval_k30all4.json",
               "trial_retrieval_pool37k30all4.json"):
        p = LEDGER / fn
        if not p.exists():
            continue
        data = json.loads(p.read_text("utf-8"))
        entries = data if isinstance(data, list) else list(data.values())
        for entry in entries:
            for bundle in (entry.get("retrieved") or {}).values():
                for pas in (bundle.get("passages") or []):
                    txt = pas.get("text") or ""
                    gid = pas.get("gid") or txt[:120]
                    if not txt or gid in seen:
                        continue
                    seen.add(gid)
                    n_pass += 1
                    for name, rx in COMPOUND.items():
                        if rx.search(txt):
                            hits[name] += 1
                    if any(rx.search(txt) for rx in COMPOUND.values()):
                        hits["ANY"] += 1
    return {"n_passages": n_pass, "hits": dict(hits)}


def extraction_side() -> dict:
    out = {}
    for fn, tag in (("trial_extraction_k30all4clean_groups.json", "11cases"),
                    ("trial_extraction_pool6k30all4clean_groups.json", "pool6")):
        p = LEDGER / fn
        if not p.exists():
            continue
        data = json.loads(p.read_text("utf-8"))
        n = n_grouped = 0
        logic: Counter = Counter()
        gid_size: Counter = Counter()
        quote_compound = 0
        grouped_quote_compound = 0
        for entry in data:
            per_gid: dict[tuple, int] = defaultdict(int)
            for a in entry.get("assertions") or []:
                if not isinstance(a, dict):
                    continue
                n += 1
                q = a.get("quote") or ""
                is_comp = any(rx.search(q) for rx in COMPOUND.values())
                quote_compound += is_comp
                cg = a.get("criterion_group") or {}
                gid = cg.get("group_id")
                lg = cg.get("logic")
                if gid and lg in {"all", "any", "at_least_n"}:
                    n_grouped += 1
                    logic[lg] += 1
                    grouped_quote_compound += is_comp
                    per_gid[(entry.get("case_key"), a.get("_title"),
                             a.get("_section"), a.get("_focus"), gid,
                             eng.norm(a.get("subject")))] += 1
            for k, v in per_gid.items():
                gid_size[v] += 1
        out[tag] = {
            "n_assertions": n,
            "n_with_group": n_grouped,
            "pct_with_group": round(100 * n_grouped / n, 2) if n else 0,
            "logic": dict(logic),
            "group_member_counts": dict(sorted(gid_size.items())),
            "singleton_groups": gid_size.get(1, 0),
            "usable_groups": sum(v for k, v in gid_size.items() if k >= 2),
            "quotes_with_compound_language": quote_compound,
            "pct_quotes_compound": round(100 * quote_compound / n, 2) if n else 0,
            "compound_quotes_that_got_a_group": grouped_quote_compound,
        }
    return out


def main() -> int:
    print("=== corpus: does the retrieved text contain compound criteria? ===")
    c = corpus_side()
    n = c["n_passages"]
    print(f"unique passages: {n}")
    for k, v in sorted(c["hits"].items(), key=lambda x: -x[1]):
        print(f"  {k:<18}{v:>7}  {v / n:6.1%}")

    print("\n=== extraction: does it emit criterion_group for them? ===")
    e = extraction_side()
    for tag, d in e.items():
        print(f"\n[{tag}] assertions={d['n_assertions']}")
        print(f"  carry a criterion_group      : {d['n_with_group']:>7}"
              f"  ({d['pct_with_group']}%)   logic={d['logic']}")
        print(f"  quotes with compound language: "
              f"{d['quotes_with_compound_language']:>7}"
              f"  ({d['pct_quotes_compound']}%)")
        print(f"    of which got a group       : "
              f"{d['compound_quotes_that_got_a_group']:>7}")
        print(f"  group sizes (members per id) : {d['group_member_counts']}")
        print(f"  singleton groups (dropped)   : {d['singleton_groups']}")
        print(f"  groups with >=2 members      : {d['usable_groups']}")

    json.dump({"corpus": c, "extraction": e},
              (LEDGER / "compound_criteria_audit.json").open("w"), indent=2)
    print(f"\nwrote {LEDGER / 'compound_criteria_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
