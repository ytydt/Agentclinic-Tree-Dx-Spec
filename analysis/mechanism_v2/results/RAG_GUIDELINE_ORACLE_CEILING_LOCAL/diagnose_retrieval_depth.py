#!/usr/bin/env python3
"""How deep would retrieval have to go to reach each required assertion?

For every one of the 26 assertions, the candidate hypotheses whose label (or
alias) denotes the assertion's subject are found, the same four query templates
are issued, and the rank of the best oracle chunk is reported per lane.  This
separates "the passage is far outside any plausible top-k" from "it sat just
past the cut".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))
from run_trial_retrieval import QUERY_TEMPLATES, case_terms  # noqa: E402
from trial_retriever import RRF_K, TrialRetriever  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth", type=int, default=2000)
    ap.add_argument("--device", default="cuda:1")
    args = ap.parse_args()

    tasks = json.loads((LEDGER / "trial_tasks_11.json").read_text(encoding="utf-8"))
    R = TrialRetriever(device=args.device)

    rows = []
    for task in tasks:
        terms = case_terms(R, task["vignette"])
        for a in task["assertions"]:
            s_re = re.compile(a["subject_re"], re.I)
            owners = [c for c in task["candidates"]
                      if s_re.search(c["label"]) or any(s_re.search(x) for x in c.get("aliases") or [])]
            oracle = set(a["oracle_gids"])
            row = {"case": task["case_key"], "id": a["id"], "subject": a["subject"],
                   "predicate": a["predicate"], "n_oracle": len(oracle),
                   "owner_labels": [c["label"] for c in owners]}
            if not owners or not oracle:
                row["best_rank"] = None
                row["reason"] = "no_candidate_denotes_subject" if not owners else "no_oracle_chunk"
                rows.append(row)
                continue

            best = None
            for cand in owners:
                queries = [tpl.format(h=cand["label"], case_terms=terms) for _, tpl in QUERY_TEMPLATES]
                sparse = R._sparse_ranks(queries, args.depth)
                dense = R._dense_ranks(queries, args.depth)
                fused: dict[int, float] = {}
                for lane_ranks in (sparse, dense):
                    for ranks in lane_ranks:
                        for rank, gid in enumerate(ranks):
                            fused[gid] = fused.get(gid, 0.0) + 1.0 / (RRF_K + rank + 1)
                order = sorted(fused, key=lambda g: -fused[g])
                pos = {g: i + 1 for i, g in enumerate(order)}
                for (tname, _), s_ranks, d_ranks in zip(QUERY_TEMPLATES, sparse, dense):
                    for lane, ranks in (("sparse", s_ranks), ("dense", d_ranks)):
                        for rank, gid in enumerate(ranks):
                            if gid in oracle:
                                cand_best = (rank + 1, lane, tname, cand["label"], pos.get(gid))
                                if best is None or cand_best[0] < best[0]:
                                    best = cand_best
                                break
                fused_hit = min((pos[g] for g in oracle if g in pos), default=None)
                if fused_hit is not None:
                    row.setdefault("fused_ranks", {})[cand["label"]] = fused_hit
            if best:
                row.update({"best_rank": best[0], "best_lane": best[1], "best_template": best[2],
                            "best_label": best[3], "reason": "reachable"})
            else:
                row.update({"best_rank": None, "reason": f"outside_top_{args.depth}"})
            rows.append(row)
            print(f"  {row['id']:7s} {row['reason']:28s} best_lane_rank={row.get('best_rank')} "
                  f"fused={row.get('fused_ranks')}", flush=True)

    (LEDGER / "retrieval_depth_diagnosis.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {LEDGER / 'retrieval_depth_diagnosis.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
