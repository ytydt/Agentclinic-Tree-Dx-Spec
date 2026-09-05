#!/usr/bin/env python3
"""Is a gate a rule or a lookup table for one case?

Two questions, both answered on the 11-case trial set:
  1. how many *cases* does each gate code fire in (a code that only ever fires
     on one case is a case-specific patch, whatever its regex looks like);
  2. after gating, which required_for rows survive per case, so the survivors
     can be read for false necessities that the mechanism checks do not name.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import gate_assertions as ga

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"


def main() -> int:
    ext = json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))

    code_cases: dict[str, set[str]] = defaultdict(set)
    code_rows: Counter = Counter()
    survivors: dict[str, list[dict]] = {}
    n_raw_req = n_kept_req = 0

    for entry in ext:
        case = entry["case_key"].split("/")[-1]
        raw = [a for a in entry.get("assertions") or [] if isinstance(a, dict)]
        n_raw_req += sum(1 for a in raw
                         if (a.get("relation") or "").lower() == "required_for")
        gated = ga.gate_assertions(raw)
        rows = []
        for a in gated:
            for code in filter(None, str(a.get("_gate") or "").split("+")):
                code_cases[code].add(case)
                code_rows[code] += 1
            if (a.get("relation") or "").lower() == "required_for":
                rows.append({
                    "subject": a.get("subject"),
                    "predicate": a.get("predicate"),
                    "modality": a.get("modality"),
                    "gate": a.get("_gate") or "",
                    "quote": (a.get("quote") or "")[:140],
                })
        seen, uniq = set(), []
        for r in rows:
            key = (str(r["subject"]).lower(), str(r["predicate"]).lower(),
                   r["quote"][:80].lower())
            if key in seen:
                continue
            seen.add(key)
            uniq.append(r)
        survivors[case] = uniq
        n_kept_req += len(uniq)

    print(f"=== gate firing across {len(ext)} cases ===", flush=True)
    for code, cases in sorted(code_cases.items(),
                              key=lambda kv: (-len(kv[1]), kv[0])):
        tag = "  <-- single case" if len(cases) == 1 else ""
        print(f"  {code:<34} cases={len(cases):>2}  rows={code_rows[code]:>4}"
              f"  {sorted(cases)[:6]}{tag}", flush=True)

    print("\n=== surviving required_for per case (unique) ===", flush=True)
    for case, rows in sorted(survivors.items(), key=lambda kv: -len(kv[1])):
        print(f"  {case:>4}: {len(rows)}", flush=True)

    print("\n=== case 74 survivors ===", flush=True)
    for r in survivors.get("74", []):
        print(f"  [{r['modality']}] {str(r['predicate'])[:46]:<46} "
              f"| {r['gate'][:38]:<38} | {r['quote'][:70]}", flush=True)

    out = LEDGER / "gate_generality_census.json"
    out.write_text(json.dumps({
        "raw_required_for_rows": n_raw_req,
        "unique_required_for_after_gate": n_kept_req,
        "codes": {c: {"cases": sorted(v), "rows": code_rows[c]}
                  for c, v in code_cases.items()},
        "survivors": survivors,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
