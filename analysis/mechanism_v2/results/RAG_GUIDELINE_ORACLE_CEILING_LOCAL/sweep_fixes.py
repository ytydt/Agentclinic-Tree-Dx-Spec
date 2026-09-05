#!/usr/bin/env python3
"""Isolation harness for the six fixes in section 8 of the trial report.

Each fix is one switch on the engine.  Every fix is measured twice: against the
plain-sum baseline of section 6 (B0) and against the balanced configuration of
section 11.4 (B1), so an effect that only exists on one baseline is visible as
such.  With 11 cases a one-case swing is noise, so the aggregate table reports
MRR with a bootstrap interval and is read alongside the mechanism checks in
``check_fixes.py``, which ask whether the specific chain the fix targets now
runs.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))
import run_mechanical_engine as eng  # noqa: E402

# B0: the degenerate coverage counter of section 6.
# B1: the balanced cell of section 11.4 (groups + idf + loose).
BASELINES = {
    "B0": dict(weight="none", join="strict", groups=False),
    "B1": dict(weight="idf", join="loose", groups=True),
}

FIXES = {
    "F2a_marker": dict(marker=True),
    "F2b_embed55": dict(embed_tau=0.55),
    "F2b_embed60": dict(embed_tau=0.60),
    "F2b_embed65": dict(embed_tau=0.65),
    "F2b_embed70": dict(embed_tau=0.70),
    "F2_both": dict(marker=True, embed_tau=0.60),
    "F3_organism": dict(organism=True),
    "F5a_enum": dict(enum_clamp=True),
    "F1_lr_clip1": dict(corpus_lr="corpus_lift_table.json", lr_clip=1.0),
    "F1_lr_clip2": dict(corpus_lr="corpus_lift_table.json", lr_clip=2.0),
    "F1_lr_clip3": dict(corpus_lr="corpus_lift_table.json", lr_clip=3.0),
    "F2c_anchor55": dict(embed_tau=0.55, anchor_embed=True),
    "F2c_anchor60": dict(embed_tau=0.60, anchor_embed=True),
    "F2c_anchor65": dict(embed_tau=0.65, anchor_embed=True),
    "F4_groups": dict(groups=True),
    "F4_groups_cwa": dict(groups=True, closed_world=True),
    "F4b_all_required": dict(groups=True, group_all_required=True),
    "F4b_all_required_cwa": dict(groups=True, group_all_required=True, closed_world=True),
    "F7_quote_gate": dict(quote_gate=True),
    "F8_nli": dict(quote_gate=True, nli=True),
}


# Cumulative stack, ordered by the size of the isolated effect on B1.  Each row
# is the previous row plus one switch, so a fix that only helps in isolation
# shows up here as a flat or negative step.
STACK_ORDER = [
    ("S0_baseline", {}),
    ("S1_+F2b60", dict(embed_tau=0.60)),
    ("S2_+F2a", dict(marker=True)),
    ("S3_+F3", dict(organism=True)),
    ("S4_+F5a", dict(enum_clamp=True)),
    ("S5_+F1", dict(corpus_lr="corpus_lift_table_all4.json", lr_clip=1.0)),
    ("S6_+F4b", dict(group_all_required=True)),
    ("S7_+F7", dict(quote_gate=True)),
    ("S8_+F8", dict(nli=True)),
]


def stacks() -> dict[str, dict]:
    out, acc = {}, {}
    for name, step in STACK_ORDER:
        acc = {**acc, **step}
        out[name] = dict(acc)
    return out


def configure(base: dict, fix: dict) -> None:
    cfg = {**base, **fix}
    eng.WEIGHT_SCHEME = cfg.get("weight", "none")
    eng.JOIN_MODE = cfg.get("join", "strict")
    eng.USE_CRITERION_GROUPS = cfg.get("groups", False)
    eng.CLOSED_WORLD = cfg.get("closed_world", False)
    eng.FIX_MARKER = cfg.get("marker", False)
    eng.FIX_EMBED_TAU = cfg.get("embed_tau", 0.0)
    eng.FIX_ORGANISM = cfg.get("organism", False)
    eng.FIX_ENUM = cfg.get("enum_clamp", False)
    eng.FIX_ANCHOR_EMBED = cfg.get("anchor_embed", False)
    eng.GROUP_ALL_IS_REQUIRED = cfg.get("group_all_required", False)
    eng.FIX_QUOTE_GATE = cfg.get("quote_gate", False)
    eng.FIX_NLI = cfg.get("nli", False)
    eng.LR_CLIP = cfg.get("lr_clip", 1.0)
    lr = cfg.get("corpus_lr")
    if lr:
        eng.CORPUS_LR = _LR_CACHE.setdefault(lr, json.loads((LEDGER / lr).read_text("utf-8")))
    else:
        eng.CORPUS_LR = None


_LR_CACHE: dict[str, dict] = {}


def metrics(results: list[dict], boot: int = 4000, seed: int = 0) -> dict:
    ranks = [r["gold_rank"] for r in results]
    rr = [1.0 / r if r else 0.0 for r in ranks]
    rnd = random.Random(seed)
    n = len(results)
    boots = sorted(sum(rr[rnd.randrange(n)] for _ in range(n)) / n for _ in range(boot))
    joined = sum(r["join_stats"]["matched"] for r in results)
    total = sum(r["join_stats"]["matched"] + r["join_stats"]["unmatched"] for r in results)
    return {
        "top1": sum(1 for r in results if r["top1_is_gold"]),
        "top3": sum(1 for r in results if (r["gold_rank"] or 99) <= 3),
        "mrr": round(sum(rr) / n, 4),
        "mrr_ci": [round(boots[int(0.025 * boot)], 4), round(boots[int(0.975 * boot)], 4)],
        "median_rank": sorted(r or 99 for r in ranks)[n // 2],
        "gold_eliminated": sum(1 for r in results if r["gold_eliminated"]),
        "join_rate": round(joined / max(total, 1), 4),
        "n_joined": joined,
        "n_bound": sum(r["n_assertions_bound"] for r in results),
        "per_case": {r["case_key"]: r["gold_rank"] for r in results},
        "top1_labels": {r["case_key"]: r["top1"] for r in results},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="k30oracleclean")
    ap.add_argument("--tasks", default="trial_tasks_11.json")
    ap.add_argument("--only", default="", help="comma-separated subset of fix names")
    ap.add_argument("--out", default="fix_isolation.json")
    ap.add_argument("--stack", action="store_true", help="run the cumulative stack")
    args = ap.parse_args()

    tasks = {t["case_key"]: t
             for t in json.loads((LEDGER / args.tasks).read_text("utf-8"))}
    ppath = LEDGER / f"trial_extraction_{args.arm}.json"
    gpath = LEDGER / f"trial_extraction_{args.arm}_groups.json"
    # When only the group-aware extraction exists, use it for both arms: turning
    # USE_CRITERION_GROUPS off then ablates the group *evaluation* on identical
    # assertions, which is a cleaner contrast than comparing two extractions.
    grouped = ({e["case_key"]: e for e in json.loads(gpath.read_text("utf-8"))}
               if gpath.exists() else None)
    plain = ({e["case_key"]: e for e in json.loads(ppath.read_text("utf-8"))}
             if ppath.exists() else grouped)
    if grouped is None:
        grouped = plain

    table = stacks() if args.stack else FIXES
    names = (list(table) if args.stack
             else ["baseline"] + (args.only.split(",") if args.only else list(FIXES)))
    rows = []
    for bname, base in BASELINES.items():
        for fname in names:
            fix = {} if fname == "baseline" else table[fname]
            configure(base, fix)
            ext = grouped if eng.USE_CRITERION_GROUPS else plain
            res = [eng.run_case(tasks[k], ext[k]) for k in tasks]
            m = metrics(res)
            m.update({"baseline": bname, "fix": fname})
            rows.append(m)
            print(f"{bname} {fname:16s} top1={m['top1']:2d}/11 top3={m['top3']:2d}/11 "
                  f"MRR={m['mrr']:.3f} [{m['mrr_ci'][0]:.3f},{m['mrr_ci'][1]:.3f}] "
                  f"med={m['median_rank']:2d} join={m['join_rate']:.3f} "
                  f"({m['n_joined']}/{m['n_bound']})", flush=True)
        print()

    out = LEDGER / args.out
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
