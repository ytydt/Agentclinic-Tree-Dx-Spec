#!/usr/bin/env python3
"""Scan experiment outputs for OpenRouter billing-outage contamination.

Billing signature (§26.10): API returns error JSON without `.choices` →
  llm_client logs: "no attribute 'choices'" / "Failed to unpack choices"
  harness records PROTO (scored==0) or incomplete sidecars.

Usage:
  python scripts/scan_billing_pollution.py              # report only
  python scripts/scan_billing_pollution.py --isolate    # move poisoned JSON
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(ROOT, "logs")
POISON_DIR = os.path.join(LOGS, "_billing_poisoned")

# Shared with scan_nc_gaps.py — arm → eval flags for billing recovery jobs.
ARMS_FLAGS: dict[str, str] = {
    "nc_bk_off": "--fix-a2 --fix-b",
    "nc_bk_on": "--fix-a2 --fix-b --branch-knowledge",
    "nc_rp_on_bk_off": "--fix-a2 --fix-b --retrieval-priority",
    "nc_rp_on_bk_on": "--fix-a2 --fix-b --branch-knowledge --retrieval-priority",
    "nc_rq_mg": "--fix-a2 --fix-b --retrieval-priority --match-guards",
    "nc_rq_cc": "--fix-a2 --fix-b --retrieval-priority --confidence-cascade",
    "nc_rq_mg_cc": "--fix-a2 --fix-b --retrieval-priority --match-guards --confidence-cascade",
    "nc_n5_detox": "--fix-a2 --fix-b --branch-knowledge --lr-detox",
    "nc_n5_mand": "--fix-a2 --fix-b --branch-knowledge --mandatory-kb-branches",
    "nc_n5_phase": "--fix-a2 --fix-b --branch-knowledge --phase-subaxis",
    "nc_n5_full": "--fix-a2 --fix-b --branch-knowledge --lr-detox --mandatory-kb-branches --phase-subaxis",
    "nc_n5_rp_full": (
        "--fix-a2 --fix-b --branch-knowledge --retrieval-priority "
        "--lr-detox --mandatory-kb-branches --phase-subaxis"
    ),
    "nc_nrq_mg": "--fix-a2 --fix-b --match-guards",
    "nc_nrq_cc": "--fix-a2 --fix-b --confidence-cascade",
    "nc_nrq_mg_cc": "--fix-a2 --fix-b --match-guards --confidence-cascade",
    "nc_u29_bk": "--fix-a2 --fix-b --branch-knowledge",
    "nc_u29_mand": "--fix-a2 --fix-b --branch-knowledge --mandatory-kb-branches",
    "nc_u29_clean": "--fix-a2 --fix-b --branch-knowledge --lr-clean",
    "nc_u29_mand_clean": "--fix-a2 --fix-b --branch-knowledge --mandatory-kb-branches --lr-clean",
    "nc_u29_full": (
        "--fix-a2 --fix-b --branch-knowledge --mandatory-kb-branches "
        "--lr-clean --phase-subaxis"
    ),
}


def _arm_from_tag(tag: str) -> str:
    """nc_nrq_cc_10 → nc_nrq_cc"""
    parts = tag.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return tag


def _flags_for_tag(tag: str) -> str | None:
    return ARMS_FLAGS.get(_arm_from_tag(tag))

# OpenRouter billing outage OR malformed response → llama-3.3 silent fallback.
BILLING_SIG = re.compile(
    r"no attribute 'choices'|Failed to unpack choices", re.I
)
NCASES = 9


def _tag_from_json(path: str) -> str:
    base = os.path.basename(path)
    m = re.match(r"medbullets_conc_(.+?)_\d{8}_\d{6}\.json", base)
    return m.group(1) if m else base


def _sidecar_scored(tag: str) -> tuple[int, int, dict]:
    d = os.path.join(LOGS, "_case_results", tag)
    st: dict[str, int] = defaultdict(int)
    if not os.path.isdir(d):
        return 0, 0, dict(st)
    for f in glob.glob(os.path.join(d, "case_*.json")):
        try:
            r = json.load(open(f, encoding="utf-8"))
            st[r.get("status", "?")] += 1
        except Exception:
            st["BAD"] += 1
    sc = st.get("OK", 0) + st.get("XX", 0)
    bad = sum(st.get(x, 0) for x in ("PROTO", "ERR", "NOANS", "TIMEOUT"))
    return sc, bad, dict(st)


def _json_status(tag: str) -> tuple[int, int, str | None]:
    js = sorted(
        glob.glob(os.path.join(LOGS, f"medbullets_conc_{tag}_*.json")),
        key=os.path.getmtime,
        reverse=True,
    )
    if not js:
        return 0, 0, None
    path = js[0]
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return 0, 0, path
    sc = sum(1 for r in d if r.get("status") in ("OK", "XX"))
    bad = sum(
        1
        for r in d
        if r.get("status") in ("PROTO", "ERR", "NOANS", "TIMEOUT")
    )
    return sc, bad, path


def _billing_hits(tag: str) -> int:
    rf = os.path.join(LOGS, f"run_{tag}.out")
    if not os.path.exists(rf):
        return 0
    n = 0
    with open(rf, encoding="utf-8", errors="replace") as f:
        for line in f:
            if BILLING_SIG.search(line):
                n += 1
    return n


def scan(prefix: str = "") -> list[dict]:
    """Return list of rep records with billing + contamination info."""
    tags: set[str] = set()
    pat = os.path.join(LOGS, f"run_{prefix}*.out")
    for f in glob.glob(pat):
        tag = os.path.basename(f).replace("run_", "").replace(".out", "")
        if _billing_hits(tag):
            tags.add(tag)
    # also catch scored==0 PROTO JSON even without run log signature
    for f in glob.glob(os.path.join(LOGS, f"medbullets_conc_{prefix}*.json")):
        if "_billing_poisoned" in f:
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        sc = sum(1 for r in d if r.get("status") in ("OK", "XX"))
        proto = sum(1 for r in d if r.get("status") == "PROTO")
        if sc == 0 and len(d) >= NCASES and proto >= NCASES:
            tags.add(_tag_from_json(f))

    rows = []
    for tag in sorted(tags):
        bill = _billing_hits(tag)
        ss, sb, sst = _sidecar_scored(tag)
        js, jb, jpath = _json_status(tag)
        poison_json = js == 0 and jb >= NCASES
        endpoint_contaminated = bill > 0
        # Any fallback hit invalidates the rep (mixed qwen3 + llama), even 9/9.
        needs_rerun = endpoint_contaminated or (
            js < NCASES and (bill > 0 or jb > 0 or poison_json)
        )
        rows.append(
            {
                "tag": tag,
                "billing_hits": bill,
                "json_scored": js,
                "json_bad": jb,
                "json_path": jpath,
                "sidecar_scored": ss,
                "sidecar_bad": sb,
                "sidecar_status": sst,
                "poison_json": poison_json,
                "endpoint_contaminated": endpoint_contaminated,
                "needs_rerun": needs_rerun,
                "done_clean": js >= NCASES and jb == 0 and not endpoint_contaminated,
            }
        )
    return rows


def isolate(rows: list[dict]) -> list[str]:
    """Move poisoned JSON + PROTO sidecars; return list of actions taken."""
    os.makedirs(POISON_DIR, exist_ok=True)
    actions: list[str] = []
    for r in rows:
        tag = r["tag"]
        # Poison JSON: scored==0 all PROTO/ERR
        for f in glob.glob(os.path.join(LOGS, f"medbullets_conc_{tag}_*.json")):
            try:
                d = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            sc = sum(1 for x in d if x.get("status") in ("OK", "XX"))
            bad = sum(
                1
                for x in d
                if x.get("status") in ("PROTO", "ERR", "NOANS", "TIMEOUT")
            )
            if sc == 0 and len(d) >= NCASES and bad >= NCASES:
                dst = os.path.join(POISON_DIR, os.path.basename(f))
                shutil.move(f, dst)
                actions.append(f"MOVED poison JSON → {dst}")
        # PROTO sidecars only (keep valid OK/XX from partial billing recovery)
        sd = os.path.join(LOGS, "_case_results", tag)
        if os.path.isdir(sd):
            for f in glob.glob(os.path.join(sd, "case_*.json")):
                try:
                    rec = json.load(open(f, encoding="utf-8"))
                except Exception:
                    continue
                if rec.get("status") in ("PROTO", "ERR", "NOANS", "TIMEOUT"):
                    dst = os.path.join(
                        POISON_DIR, f"{tag}_{os.path.basename(f)}"
                    )
                    shutil.move(f, dst)
                    actions.append(f"MOVED poison sidecar → {dst}")
    return actions


def jobs_for_rerun(rows: list[dict], prefix: str = "nc_") -> list[tuple[str, str, dict]]:
    """Return (tag, flags, row) for reps needing billing recovery."""
    out: list[tuple[str, str, dict]] = []
    for r in rows:
        if not r["needs_rerun"] or r["done_clean"]:
            continue
        tag = r["tag"]
        if prefix and not tag.startswith(prefix):
            continue
        flags = _flags_for_tag(tag)
        if not flags:
            continue
        out.append((tag, flags, r))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="nc_", help="run_/JSON tag prefix filter")
    ap.add_argument(
        "--isolate", action="store_true", help="move poisoned artifacts"
    )
    ap.add_argument(
        "--jobs",
        action="store_true",
        help="print tag|flags lines for reps needing rerun (nc_ arms only)",
    )
    ap.add_argument("--manifest", default="", help="write JSON manifest path")
    args = ap.parse_args()

    rows = scan(args.prefix)
    rerun = [r for r in rows if r["needs_rerun"] and not r["done_clean"]]
    clean = [r for r in rows if r["done_clean"]]

    if args.jobs:
        for tag, flags, _ in jobs_for_rerun(rows, prefix=args.prefix):
            print(f"{tag}|{flags}")
        return

    print(f"=== billing scan prefix={args.prefix!r} @ {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    print(f"billing-touched reps: {len(rows)}")
    endpoint = [r for r in rows if r.get("endpoint_contaminated")]
    print(f"  done clean (9/9, no fallback): {len(clean)}")
    print(f"  endpoint fallback (exclude from compare): {len(endpoint)}")
    print(f"  needs rerun: {len(rerun)}")
    for r in rows:
        if r["done_clean"]:
            flag = "OK"
        elif r.get("endpoint_contaminated"):
            flag = "EXCLUDE" if r["json_scored"] >= NCASES else "RERUN"
        elif r in rerun:
            flag = "RERUN"
        else:
            flag = "watch"
        print(
            f"  {r['tag']:28} bill={r['billing_hits']:4d} "
            f"json={r['json_scored']}/9(bad={r['json_bad']}) "
            f"side={r['sidecar_scored']}/9(bad={r['sidecar_bad']}) [{flag}]"
        )

    actions: list[str] = []
    if args.isolate:
        actions = isolate(rows)
        for a in actions:
            print(f"  ISOLATE: {a}")
        if not actions:
            print("  ISOLATE: nothing to move (no scored==0 PROTO JSON / PROTO sidecars)")

    manifest_path = args.manifest or os.path.join(
        POISON_DIR, f"manifest_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    os.makedirs(POISON_DIR, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as mf:
        json.dump(
            {
                "scanned_at": datetime.now().isoformat(),
                "prefix": args.prefix,
                "billing_signature": "no attribute 'choices'",
                "rows": rows,
                "rerun_tags": [r["tag"] for r in rerun],
                "isolate_actions": actions,
            },
            mf,
            indent=2,
            ensure_ascii=False,
        )
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
