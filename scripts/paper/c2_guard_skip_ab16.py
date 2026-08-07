#!/usr/bin/env python3
"""Guard: if the in-flight OX suite starts AB16, kill it and assemble ox_raw without live AB16.

Current suite was launched with --arms ...,ab16 before reuse decision.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WS = ROOT / "logs/c2_ablation_workspace_v1"
OX_PID_FILE = WS / "ox_suite.pid"
OX_LOG = WS / "ox_suite.log"
OX_RAW = ROOT / "runs/paper_v1/ablations_c2_ox_raw.json"
AB16_REUSE = ROOT / "runs/paper_v1/ablations_c2_ab16_reused.json"
OUT_ROOT = ROOT / "logs/open_xddx_ox_seq100_v1"
M00 = (
    OUT_ROOT
    / "compat_synonym_noemit_fopt_live_v1/annotate/official_eval_llm_closed_live_mac/summary.json"
)
ARMS = ("ab13", "ab17", "ab19", "ab14")  # live order; ab16 reuse only


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _micro(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    m = doc.get("metrics") or {}
    dm = m.get("diagnostic_micro") or {}
    return {
        "micro_precision": dm.get("micro_precision"),
        "micro_recall": dm.get("micro_recall"),
        "micro_f1": dm.get("micro_f1"),
        "interpretation_accuracy": m.get("interpretation_accuracy"),
        "n_cases": m.get("n_cases") or doc.get("n_cases_scored"),
    }


def _arm_from_disk(key: str) -> dict[str, Any] | None:
    d = OUT_ROOT / f"c2_{key}_v1"
    ev = d / "annotate" / f"official_eval_llm_c2_{key}" / "summary.json"
    launch = d / "c2_launch.json"
    if not ev.is_file():
        return None
    meta = json.loads(launch.read_text(encoding="utf-8")) if launch.is_file() else {}
    n_live = 0
    trees = d / "annotate" / "shared_trees"
    if trees.is_dir():
        for p in trees.glob("*.json"):
            if json.loads(p.read_text(encoding="utf-8")).get("live_reannotated"):
                n_live += 1
    return {
        "label": meta.get("label"),
        "l1": meta.get("l1"),
        "cap": meta.get("cap"),
        "writeback": meta.get("writeback"),
        "output_dir": str(d),
        "annotate_exit": 0,
        "llm_exit": 0,
        "micro": _micro(ev),
        "n_live_trees": n_live,
    }


def assemble_ox_raw() -> Path:
    arms: dict[str, Any] = {}
    for key in ARMS:
        row = _arm_from_disk(key)
        if row:
            arms[key] = row
    if AB16_REUSE.is_file():
        r = json.loads(AB16_REUSE.read_text(encoding="utf-8"))
        arms["ab16"] = {
            "label": r.get("label"),
            "l1": r.get("l1"),
            "cap": r.get("cap"),
            "writeback": r.get("writeback"),
            "output_dir": r.get("source_run_dir"),
            "annotate_exit": 0,
            "llm_exit": 0,
            "micro": r.get("micro"),
            "n_live_trees": 0,
            "reused": True,
            "source_eval": r.get("source_eval"),
            "note": r.get("note"),
        }
    doc = {
        "created_at": _utc(),
        "n_cases": 100,
        "workers": 12,
        "judge_workers": 12,
        "m00_readonly": _micro(M00),
        "arms": arms,
        "ab16_policy": "historical_reuse_not_live",
    }
    OX_RAW.parent.mkdir(parents=True, exist_ok=True)
    OX_RAW.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("WROTE", OX_RAW, "arms=", sorted(arms), flush=True)
    return OX_RAW


def _kill_tree(pid: int) -> None:
    # kill children first
    try:
        out = subprocess.check_output(["pgrep", "-P", str(pid)], text=True)
        for line in out.splitlines():
            c = int(line.strip())
            _kill_tree(c)
    except Exception:
        pass
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    time.sleep(2)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def ab16_starting() -> bool:
    ab16 = OUT_ROOT / "c2_ab16_v1"
    if ab16.is_dir():
        return True
    if OX_LOG.is_file():
        text = OX_LOG.read_text(errors="replace")
        if "c2_ab16_v1" in text or "arm\": \"ab16\"" in text or "\"ab16\":" in text[-5000:]:
            # only if ab14 already done (otherwise false positive from arms list in argv)
            if (OUT_ROOT / "c2_ab14_v1/annotate/official_eval_llm_c2_ab14/summary.json").is_file():
                if "c2_ab16_v1" in text.split("c2_ab14_v1")[-1]:
                    return True
    return False


def ab14_done() -> bool:
    return (
        OUT_ROOT / "c2_ab14_v1/annotate/official_eval_llm_c2_ab14/summary.json"
    ).is_file()


def main() -> int:
    WS.mkdir(parents=True, exist_ok=True)
    if not OX_PID_FILE.is_file():
        print("no ox pid; assemble if possible", flush=True)
        if ab14_done() or (OUT_ROOT / "c2_ab13_v1").is_dir():
            assemble_ox_raw()
        return 0
    pid = int(OX_PID_FILE.read_text().strip())
    print(f"guard watching ox pid={pid}", flush=True)
    while _alive(pid):
        if ab16_starting():
            print("AB16 start detected — killing suite and assembling ox_raw", flush=True)
            _kill_tree(pid)
            # also kill any leftover ab16 annotate
            subprocess.call(
                ["pkill", "-f", "c2_ab16_v1"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(2)
            assemble_ox_raw()
            return 0
        # If suite exits cleanly after ab14 without ab16 (shouldn't with old argv)
        time.sleep(20)
    print("ox suite exited without AB16 trigger", flush=True)
    # If ab16 dir was never created, strip any partial and assemble
    ab16 = OUT_ROOT / "c2_ab16_v1"
    if ab16.is_dir() and not (ab16 / "annotate/official_eval_llm_c2_ab16/summary.json").is_file():
        # incomplete live attempt — remove to avoid confusion
        import shutil

        shutil.rmtree(ab16, ignore_errors=True)
        print("removed incomplete c2_ab16_v1", flush=True)
    assemble_ox_raw()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
