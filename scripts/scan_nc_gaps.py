#!/usr/bin/env python3
"""List nc_ reps that are incomplete and not currently running.

Skips reps still owned by an active driver (queued or awaiting auto-REQUEUE).
Only includes reps the driver has abandoned (PERSISTENT FAIL / ACCEPT PARTIAL)
or that remain incomplete after the driver finished.
"""
from __future__ import annotations

import json
import glob
import os
import re
import subprocess
import sys

CASES = 9
REMATRIX_K = 5

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

K10_ARMS = {
    "nc_bk_on",
    "nc_u29_full",
    "nc_n5_detox",
    "nc_n5_phase",
    "nc_rp_on_bk_on",
    "nc_nrq_cc",
    "nc_u29_mand",
    "nc_nrq_mg_cc",
}

K10_REMATRIX_ARMS = [
    "bk_off",
    "bk_on",
    "rp_on_bk_off",
    "rp_on_bk_on",
    "rq_mg",
    "rq_cc",
    "rq_mg_cc",
    "n5_detox",
    "n5_mand",
    "n5_phase",
    "n5_full",
    "n5_rp_full",
    "nrq_mg",
    "nrq_cc",
    "nrq_mg_cc",
    "u29_bk",
    "u29_mand",
    "u29_clean",
    "u29_mand_clean",
    "u29_full",
]

# Drivers that may own reps. Queued / auto-REQUEUE reps stay with the driver;
# PERSISTENT FAIL / ACCEPT PARTIAL → gap fill. gap_fill itself is listed so a
# second gap-fill instance won't duplicate an in-flight batch.
DRIVERS = (
    {
        "id": "k10",
        "pgrep": "run_variance_k10_extend.sh",
        "log": "logs/run_variance_k10_extend_driver.out",
        "jobs": lambda: [f"{arm}_{k}" for arm in K10_ARMS for k in range(6, 11)],
    },
    {
        "id": "k10b2",
        "pgrep": "run_variance_k10_extend_batch2.sh",
        "log": "logs/run_variance_k10_extend_batch2_driver.out",
        "jobs": lambda: [
            f"{arm}_{k}"
            for arm in ("nc_nrq_cc", "nc_u29_mand", "nc_nrq_mg_cc")
            for k in range(6, 11)
        ],
    },
    {
        "id": "rematrix",
        "pgrep": "run_nocache_rematrix.sh",
        "log": "logs/run_nocache_rematrix_driver.out",
        "jobs": lambda: [
            f"nc_{arm}_{k}"
            for arm in K10_REMATRIX_ARMS
            for k in range(1, REMATRIX_K + 1)
        ],
    },
    {
        "id": "billing",
        "pgrep": "run_billing_recovery_nc.sh",
        "log": "logs/run_billing_recovery_nc_driver.out",
        "jobs": lambda: _billing_recovery_job_tags(),
    },
    {
        "id": "gap_fill",
        "pgrep": "run_nc_gap_fill.sh",
        "log": "logs/run_nc_gap_fill_driver.out",
        "jobs": lambda: _gap_fill_job_tags(),
    },
)

_DRIVER_LOGS = [
    "logs/run_nocache_rematrix_driver.out",
    "logs/run_variance_k10_extend_driver.out",
    "logs/run_nc_gap_fill_driver.out",
    "logs/run_billing_recovery_nc_driver.out",
]

_TERMINAL = frozenset({"DONE", "SKIP", "PERSISTENT FAIL", "ACCEPT PARTIAL"})

_LOG_RE = re.compile(
    r"\] (DISPATCH|REQUEUE|DONE|SKIP|PERSISTENT FAIL|ACCEPT PARTIAL) (\S+)"
)


def _driver_running(pgrep_pat: str) -> bool:
    r = subprocess.run(["pgrep", "-f", pgrep_pat], capture_output=True)
    return r.returncode == 0


def _parse_driver_log(log_path: str) -> dict[str, str]:
    """Last scheduler event per tag from a run_* driver log."""
    states: dict[str, str] = {}
    if not os.path.isfile(log_path):
        return states
    with open(log_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _LOG_RE.search(line)
            if m:
                states[m.group(2)] = m.group(1)
    return states


def _gap_fill_job_tags() -> list[str]:
    """Tags touched by the gap-fill driver log (dynamic batch, not fixed manifest)."""
    states = _parse_driver_log("logs/run_nc_gap_fill_driver.out")
    return [t for t in states if t.startswith("nc_")]


def _billing_recovery_job_tags() -> list[str]:
    states = _parse_driver_log("logs/run_billing_recovery_nc_driver.out")
    return [t for t in states if t.startswith("nc_")]


def _driver_abandoned_tags() -> dict[str, str]:
    """tag -> terminal abandon reason from any driver log; incomplete reps only."""
    abandoned: dict[str, str] = {}
    for log_path in _DRIVER_LOGS:
        for tag, last in _parse_driver_log(log_path).items():
            if last not in ("PERSISTENT FAIL", "ACCEPT PARTIAL"):
                continue
            done, _ = _rep_done(tag)
            if not done:
                abandoned[tag] = last
    return abandoned


def _driver_pending_tags(running: set[str] | None = None) -> dict[str, str]:
    """tag -> driver_id for reps still queued or awaiting driver auto-REQUEUE."""
    if running is None:
        running = _running_tags()
    pending: dict[str, str] = {}
    for drv in DRIVERS:
        if not _driver_running(drv["pgrep"]):
            continue
        jobs = set(drv["jobs"]())
        states = _parse_driver_log(drv["log"])
        for tag in jobs:
            done, _ = _rep_done(tag)
            if done:
                continue
            # gap_fill watcher: only block while eval is live. A stale DISPATCH left
            # when the driver shell was killed must not permanently hide the rep.
            if drv["id"] == "gap_fill":
                if tag not in running:
                    continue
                pending[tag] = drv["id"]
                continue
            last = states.get(tag)
            if last in _TERMINAL:
                continue
            # None = never dispatched (queued); DISPATCH/REQUEUE = in-flight / will retry
            pending[tag] = drv["id"]
    return pending


def _drivers_active_count() -> int:
    """Reps still owned by a running driver (not yet abandoned)."""
    return len(_driver_pending_tags())


def _running_tags() -> set[str]:
    out = subprocess.run(
        ["pgrep", "-af", "eval_pipeline_medbullets"],
        capture_output=True,
        text=True,
    ).stdout
    tags: set[str] = set()
    for line in out.splitlines():
        m = re.search(r"--tag\s+(\S+)", line)
        if m:
            tags.add(m.group(1))
    return tags


def _rep_done(tag: str) -> tuple[bool, str]:
    js = sorted(
        glob.glob(f"logs/medbullets_conc_{tag}_*.json"),
        key=os.path.getmtime,
        reverse=True,
    )
    if js:
        d = json.load(open(js[0], encoding="utf-8"))
        sc = sum(1 for r in d if r.get("status") in ("OK", "XX"))
        bad = sum(
            1
            for r in d
            if r.get("status") in ("PROTO", "ERR", "NOANS", "TIMEOUT")
        )
        if sc >= CASES and len(d) >= CASES:
            return True, "done"
        if bad:
            return False, f"json_bad={bad},scored={sc}"
        if sc:
            return False, f"partial_json={sc}/9"
    sd = f"logs/_case_results/{tag}"
    side_sc = side_bad = 0
    if os.path.isdir(sd):
        for f in glob.glob(os.path.join(sd, "case_*.json")):
            try:
                st = json.load(open(f, encoding="utf-8")).get("status")
            except Exception:
                continue
            if st in ("OK", "XX"):
                side_sc += 1
            elif st in ("PROTO", "ERR", "NOANS", "TIMEOUT"):
                side_bad += 1
    if side_bad:
        return False, f"side_bad={side_bad},side_sc={side_sc}"
    if side_sc:
        return False, f"sidecar_only={side_sc}/9"
    return False, "never_started"


def main() -> int:
    if "--drivers-active" in sys.argv:
        print(_drivers_active_count())
        return 0

    running = _running_tags()
    driver_pending = _driver_pending_tags(running)
    driver_abandoned = _driver_abandoned_tags()
    gaps: list[tuple[str, str, str]] = []
    skipped: list[tuple[str, str]] = []
    for arm, flags in ARMS_FLAGS.items():
        reps = list(range(1, 6))
        if arm in K10_ARMS:
            reps += list(range(6, 11))
        for k in reps:
            tag = f"{arm}_{k}"
            done, reason = _rep_done(tag)
            if done:
                continue
            if tag in running:
                skipped.append((tag, "running"))
                continue
            if tag in driver_pending:
                skipped.append((tag, f"driver_pending:{driver_pending[tag]}"))
                continue
            if tag in driver_abandoned:
                reason = f"driver_abandoned:{driver_abandoned[tag]};{reason}"
            gaps.append((tag, flags, reason))

    if "--json" in sys.argv:
        import json as _json

        print(
            _json.dumps(
                {
                    "gaps": [{"tag": t, "flags": f, "reason": r} for t, f, r in gaps],
                    "skipped": [{"tag": t, "reason": r} for t, r in skipped],
                },
                indent=2,
            )
        )
        return 0

    for tag, flags, reason in gaps:
        print(f"{tag}|{flags}|{reason}")
    for tag, reason in skipped:
        print(f"# skip {tag}: {reason}", file=sys.stderr)
    print(f"# gaps: {len(gaps)}, skipped: {len(skipped)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
