"""A0 (noise floor): bootstrap confidence intervals + arm A/B comparison for the
TALP discrimination harness.

The per-arm JSONs written by `eval_talp_discrimination.py` carry per-case `rows`
(each with `direction[]`, `select@1/2`, `select_valid`, `parent_child`). This
tool recomputes the headline metrics and attaches a CASE-CLUSTER bootstrap 95%
CI: the nine case IDs, not 18/27 seed×case rows, are the independent sampling
units. All seed/repeat rows belonging to a sampled case stay together.

For A/B, the same sampled case IDs are used in both arms (paired cluster
bootstrap). This preserves the same-case pairing and avoids the old error of
bootstrapping the two arms independently, which inflated the delta interval and
incorrectly treated repeated seeds of the same case as independent patients.

Pure post-processing: NO LLM calls. Pools one-or-more per-seed JSONs per arm.

Usage:
  # CI for one arm (optionally pooling several seed files):
  python scripts/talp_ci.py --arm P5 logs/talp_discrim_fx7_dv2_p7.json \
                                   logs/talp_discrim_fx11_dv2_p7.json
  # A/B two arms (each may be several seed files):
  python scripts/talp_ci.py \
      --a P5   logs/talp_discrim_fx7_dv2_p7.json  logs/talp_discrim_fx11_dv2_p7.json \
      --b P5ccv logs/talp_discrim_ccv7.json       logs/talp_discrim_ccv11.json
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


# Each metric is a function row -> (numerator, denominator) contribution.
def _m_sel1(r):
    return (int(bool(r.get("select@1"))), 1) if r.get("n_decisive") else (0, 0)


def _m_selvalid(r):
    return (int(bool(r.get("select_valid"))), 1) if r.get("n_decisive") else (0, 0)


def _m_dir(r):
    d = [x for x in r.get("direction", []) if x.get("kind") == "rulein"]
    return (sum(int(x["ok"]) for x in d), len(d))


def _m_ruleout(r):
    d = [x for x in r.get("direction", []) if x.get("kind") == "ruleout"]
    return (sum(int(x["ok"]) for x in d), len(d))


def _m_shared(r):
    d = [x for x in r.get("direction", []) if x.get("kind") == "shared"]
    return (sum(int(x.get("got") == "none") for x in d), len(d))


def _m_parent(r):
    d = r.get("parent_child", [])
    return (sum(int(x["ok"]) for x in d), len(d))


METRICS = {
    "SELECT@1": _m_sel1,
    "SELECT_valid": _m_selvalid,
    "DIRECTION": _m_dir,
    "RULE-OUT": _m_ruleout,
    "SHARED": _m_shared,
    "PARENT": _m_parent,
}


def _load_rows(paths: list[str]) -> list[dict]:
    """Pool per-case rows from one or more per-seed arm JSONs."""
    rows: list[dict] = []
    for p in paths:
        d = json.loads(Path(p).read_text())
        rows.extend(d.get("rows", []))
    return rows


def _clusters(rows: list[dict]) -> dict[str, list[dict]]:
    """Group all seed/repeat observations under the independent case ID."""
    out: dict[str, list[dict]] = {}
    for row in rows:
        out.setdefault(str(row.get("id", "")), []).append(row)
    return out


def _rate(rows: list[dict], metric) -> tuple[float, int, int]:
    num = den = 0
    for r in rows:
        n, d = metric(r)
        num += n
        den += d
    return (num / den if den else 0.0, num, den)


def _bootstrap(rows: list[dict], metric, n_boot: int, rng: random.Random):
    """Case-cluster bootstrap: resample case IDs; retain every seed per case."""
    groups = _clusters(rows)
    ids = list(groups)
    if not ids:
        return []
    out = []
    k = len(ids)
    for _ in range(n_boot):
        sampled_ids = [ids[rng.randrange(k)] for _ in range(k)]
        sample = [row for cid in sampled_ids for row in groups[cid]]
        rate, _, den = _rate(sample, metric)
        if den:
            out.append(rate)
    return out


def _ci(vals: list[float], alpha: float = 0.05):
    if not vals:
        return (0.0, 0.0)
    s = sorted(vals)
    lo = s[int((alpha / 2) * len(s))]
    hi = s[min(len(s) - 1, int((1 - alpha / 2) * len(s)))]
    return (lo, hi)


def summarize(name: str, paths: list[str], n_boot: int, rng: random.Random):
    rows = _load_rows(paths)
    print(f"\n=== {name}  (case_clusters={len(_clusters(rows))}, "
          f"seed×case_rows={len(rows)}, files={len(paths)}) ===")
    result = {}
    for mname, metric in METRICS.items():
        rate, num, den = _rate(rows, metric)
        lo, hi = _ci(_bootstrap(rows, metric, n_boot, rng))
        result[mname] = {"rate": rate, "num": num, "den": den,
                         "ci": [lo, hi]}
        print(f"  {mname:14} {rate*100:5.1f}%  [{lo*100:4.1f}, {hi*100:4.1f}]"
              f"  ({num}/{den})")
    return rows, result


def compare(name_a, rows_a, name_b, rows_b, n_boot: int, rng: random.Random):
    ga, gb = _clusters(rows_a), _clusters(rows_b)
    ids = sorted(set(ga) & set(gb))
    if not ids:
        raise ValueError("A/B arms have no shared case IDs")
    if set(ga) != set(gb):
        print(f"[warning] paired comparison uses {len(ids)} shared case IDs; "
              f"A-only={len(set(ga)-set(gb))}, B-only={len(set(gb)-set(ga))}")
    print(f"\n=== PAIRED A/B: {name_a}  vs  {name_b} "
          f"(delta = B - A, case-cluster bootstrap 95% CI) ===")
    for mname, metric in METRICS.items():
        ra, _, da = _rate(rows_a, metric)
        rb, _, db = _rate(rows_b, metric)
        # Paired cluster bootstrap: same resampled cases in A and B. All
        # seed/repeat observations for that case remain in their arm.
        deltas = []
        k = len(ids)
        for _ in range(n_boot):
            sampled_ids = [ids[rng.randrange(k)] for _ in range(k)]
            sa = [row for cid in sampled_ids for row in ga[cid]]
            sb = [row for cid in sampled_ids for row in gb[cid]]
            xa, _, na = _rate(sa, metric)
            xb, _, nb = _rate(sb, metric)
            if na and nb:
                deltas.append(xb - xa)
        lo, hi = _ci(deltas)
        verdict = "resolved" if (lo > 0 or hi < 0) else "unresolved"
        print(f"  {mname:14} {ra*100:5.1f}% -> {rb*100:5.1f}%   "
              f"delta {(rb-ra)*100:+5.1f}  "
              f"[{lo*100:+5.1f}, {hi*100:+5.1f}]  {verdict}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default=None, help="name for single-arm CI mode")
    ap.add_argument("paths", nargs="*", help="single-arm mode: per-seed JSONs")
    ap.add_argument("--a", nargs="+", default=None,
                    help="A/B mode: NAME file1 [file2 ...] for arm A")
    ap.add_argument("--b", nargs="+", default=None,
                    help="A/B mode: NAME file1 [file2 ...] for arm B")
    ap.add_argument("--n-boot", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    if args.a and args.b:
        na, *pa = args.a
        nb, *pb = args.b
        rows_a, _ = summarize(na, pa, args.n_boot, rng)
        rows_b, _ = summarize(nb, pb, args.n_boot, rng)
        compare(na, rows_a, nb, rows_b, args.n_boot, rng)
        return 0
    if args.paths:
        summarize(args.arm or "arm", args.paths, args.n_boot, rng)
        return 0
    ap.error("give either positional paths (single-arm) or --a/--b (compare)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
