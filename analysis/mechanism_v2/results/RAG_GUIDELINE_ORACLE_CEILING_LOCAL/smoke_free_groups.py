#!/usr/bin/env python3
"""Run the old and the new group prompt over the same criteria-bearing passages.

The 2x2 measures the two prompts over everything retrieved, where most passages
carry no criterion set at all and the contrast is diluted.  This picks only
passages that announce an enumeration and runs both prompts on exactly those,
so the difference the prompt makes is visible on a few dozen calls.

  python smoke_free_groups.py --arm x2_v2idx -n 40
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

spec = importlib.util.spec_from_file_location("rte", Path(__file__).parent / "run_trial_extraction.py")
rte = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rte)

# a lead-in that promises members: "the following:", "N criteria", "at least two of"
ANNOUNCE = re.compile(
    r"(?:the\s+following|criteria|at\s+least\s+(?:one|two|three|\d)\s+of"
    r"|\b(?:two|three|four|five|\d)\s+(?:or\s+more\s+)?of\s+(?:the|these)"
    r"|cardinal\s+signs)", re.I)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="x2_v2idx")
    ap.add_argument("-n", type=int, default=40)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    args = ap.parse_args()

    arm = json.loads((LEDGER / f"trial_retrieval_{args.arm}.json").read_text(encoding="utf-8"))
    picked, seen = [], set()
    for rec in arm:
        for label, bucket in rec["retrieved"].items():
            for p in bucket["passages"]:
                t = p["text"]
                # want an announcement AND a plausible member layout below it
                if not ANNOUNCE.search(t) or p["gid"] in seen:
                    continue
                if ":" not in t:
                    continue
                seen.add(p["gid"])
                picked.append((label, p))
    picked.sort(key=lambda x: -len(x[1]["text"]))
    picked = picked[:args.n]
    print(f"{len(picked)} criteria-bearing passages "
          f"(median {sorted(len(p['text']) for _, p in picked)[len(picked)//2]} chars)")

    ex = rte.Extractor(args.model, args.workers)
    prompts = {
        "old": (rte.GUIDELINE_PROMPT, "guideline_groups"),
        "new": (rte.swap_group_block(rte.GUIDELINE_PROMPT), "guideline_groups_free"),
    }

    results: dict[str, list] = {}
    for tag, (prompt, kind) in prompts.items():
        def job(item):
            label, p = item
            payload = {
                "hypothesis": label, "passage": p["text"][:6000],
                "source": p["source"], "document_title": p["title"],
                "section_path": p["section_path"], "context_hint": "",
            }
            return p, ex.call(kind, "GuidelineAssertionExtractor", prompt, payload)

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results[tag] = list(pool.map(job, picked))

    print(f"\ncache: {ex.stats}\n")
    for tag in prompts:
        st: Counter = Counter()
        groups: dict[tuple, list] = {}
        n_a = 0
        for p, out in results[tag]:
            for a in (out.get("assertions") or []) if isinstance(out, dict) else []:
                if not isinstance(a, dict) or not a.get("subject") or not a.get("predicate"):
                    continue
                rte.normalise_group(a, st)
                n_a += 1
                gid = a["criterion_group"]["group_id"]
                if gid is not None:
                    groups.setdefault((p["gid"], gid), []).append(a)
        multi = {k: v for k, v in groups.items() if len(v) >= 2}
        spans = Counter()
        for members in multi.values():
            quotes = [str(m.get("quote") or "") for m in members]
            spans["cross_line" if any("\n" in q for q in quotes)
                  or len({q for q in quotes}) > 1 and any("\n" in q for q in quotes)
                  else ("multi_quote" if len(set(quotes)) > 1 else "one_quote")] += 1
        logic = Counter(v[0]["criterion_group"]["logic"] for v in multi.values())
        print(f"[{tag}] assertions={n_a}  groups>=2={len(multi)}  "
              f"grouped_assertions={sum(len(v) for v in multi.values())}")
        print(f"       logic={dict(logic)}  quote_span={dict(spans)}  repairs={dict(st)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
