#!/usr/bin/env python3
"""Wait for C2 DA suite to finish, then run C3 block1→block2→analyze."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = Path(os.environ.get("C3_PYTHON", "/home/wanghongyi/.conda/envs/gnn-llm/bin/python3"))
WS = ROOT / "logs/c3_ablation_workspace_v1"
WORKERS = int(os.environ.get("C3_WORKERS", "25"))


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    line = f"[{_utc()}] {msg}"
    print(line, flush=True)
    WS.mkdir(parents=True, exist_ok=True)
    with (WS / "orchestrator.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _c2_running() -> bool:
    try:
        out = subprocess.check_output(["pgrep", "-af", "run_c2_da_selector_suite"], text=True)
    except subprocess.CalledProcessError:
        return False
    return any("run_c2_da_selector_suite.py" in ln and "pgrep" not in ln for ln in out.splitlines())


def _run(cmd: list[str], log_name: str) -> int:
    WS.mkdir(parents=True, exist_ok=True)
    log_path = WS / log_name
    _log("RUN " + " ".join(cmd) + " → " + str(log_path))
    env = {
        **os.environ,
        "PYTHONPATH": "src:scripts/paper:scripts",
        "TREE_DX_DIRECT_POST_OUTPUT_CAP": "8192",
        "TREE_DX_USE_PROXY": "1",
        "TREE_DX_EMBED_DEVICE": "cpu",
    }
    with log_path.open("w", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
        )
        code = proc.wait()
    _log(f"EXIT {code} {log_name}")
    return int(code)


def _analyze() -> int:
    script = ROOT / "scripts/paper/c3_analyze_results.py"
    if not script.is_file():
        _log("analyze script missing")
        return 2
    return _run([str(PY), "-u", str(script)], "analyze.log")


def main() -> int:
    WS.mkdir(parents=True, exist_ok=True)
    _log(f"orchestrator start workers={WORKERS}")
    # Wait for C2
    waited = 0
    while _c2_running():
        if waited % 300 == 0:
            _log("waiting for C2 DA suite to finish...")
        time.sleep(30)
        waited += 30
    _log("C2 clear; refresh C2 results docs")
    _run([str(PY), "-u", str(ROOT / "scripts/paper/c2_refresh_results.py")], "c2_refresh.log")
    _log("starting C3 block1")

    # Optional: drop workers if load high
    workers = WORKERS
    try:
        load1 = float(os.getloadavg()[0])
        if load1 > 40:
            workers = 12
            _log(f"high load {load1:.1f}; workers→{workers}")
    except OSError:
        pass

    code1 = _run(
        [
            str(PY), "-u",
            str(ROOT / "scripts/paper/run_c3_hierarchy_suite.py"),
            "--arms", "ab01,ab03,ab02",
            "--n-cases", "100",
            "--workers", str(workers),
        ],
        "block1_hierarchy.log",
    )
    (WS / "block1_exit.txt").write_text(str(code1) + "\n", encoding="utf-8")

    _log("starting C3 block2")
    code2 = _run(
        [
            str(PY), "-u",
            str(ROOT / "scripts/paper/run_c3_dedupe_site_suite.py"),
            "--arms", "ab04,ab06",
            "--n-cases", "100",
            "--workers", str(workers),
        ],
        "block2_dedupe.log",
    )
    (WS / "block2_exit.txt").write_text(str(code2) + "\n", encoding="utf-8")

    code3 = _analyze()
    summary = {
        "created_at": _utc(),
        "workers": workers,
        "block1_exit": code1,
        "block2_exit": code2,
        "analyze_exit": code3,
    }
    (WS / "orchestrator_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    _log("done " + json.dumps(summary))
    return 0 if code1 == 0 and code2 == 0 and code3 == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
