#!/usr/bin/env python3
"""Watch OX C2 suite; on success run DA suite then aggregate ablations_c2_results."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WS = ROOT / "logs/c2_ablation_workspace_v1"
OX_PID = WS / "ox_suite.pid"
OX_LOG = WS / "ox_suite.log"
DA_LOG = WS / "da_suite.log"
DA_PID = WS / "da_suite.pid"
OX_RAW = ROOT / "runs/paper_v1/ablations_c2_ox_raw.json"
DA_RAW = ROOT / "runs/paper_v1/ablations_c2_da_raw.json"
AB16_REUSE = ROOT / "runs/paper_v1/ablations_c2_ab16_reused.json"
AB28_REUSE = ROOT / "runs/paper_v1/ablations_c2_ab28_reused.json"
OUT_MD = ROOT / "runs/paper_v1/ablations_c2_results.md"
OUT_JSON = ROOT / "runs/paper_v1/ablations_c2_results.json"
PY = Path(os.environ.get("C2_PYTHON", sys.executable))
M00_OX = (
    ROOT
    / "logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1"
    / "annotate/official_eval_llm_closed_live_mac/summary.json"
)
BACKUP_PTR = ROOT / "logs/c2_ablation_workspace_v1/meta/backup_path.txt"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wait_pid(pid_path: Path, log_path: Path, label: str) -> int:
    if not pid_path.is_file():
        print(f"[{label}] missing pid file {pid_path}", flush=True)
        return 1
    pid = int(pid_path.read_text().strip())
    print(f"[{label}] waiting pid={pid}", flush=True)
    last = 0
    while _alive(pid):
        if log_path.is_file():
            n = log_path.stat().st_size
            if n != last and n - last > 200:
                # heartbeat: last downstream / arm line
                lines = log_path.read_text(errors="replace").splitlines()
                for line in reversed(lines[-80:]):
                    if "[downstream]" in line or line.startswith("{") and "micro" in line:
                        print(f"[{label}] {line[:200]}", flush=True)
                        break
                last = n
        time.sleep(60)
    # child may have exited; check raw json / log tail
    print(f"[{label}] pid {pid} exited", flush=True)
    return 0


def _run_da() -> int:
    env = {
        **os.environ,
        "PYTHONPATH": "src:scripts:scripts/paper",
        "TREE_DX_USE_PROXY": "1",
        "TREE_DX_EMBED_DEVICE": "cpu",
        "TREE_DX_DIRECT_POST_OUTPUT_CAP": "8192",
    }
    cmd = [
        str(PY),
        "-u",
        str(ROOT / "scripts/paper/run_c2_da_selector_suite.py"),
        "--arms",
        "ab21,ab22",
        "--workers",
        "12",
    ]
    print("RUN DA:", " ".join(cmd), flush=True)
    with DA_LOG.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=fh, stderr=subprocess.STDOUT)
        DA_PID.write_text(str(proc.pid) + "\n", encoding="utf-8")
        return int(proc.wait())


def _micro(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    doc = _read_json(path)
    m = doc.get("metrics") or {}
    dm = m.get("diagnostic_micro") or {}
    return {
        "micro_f1": dm.get("micro_f1"),
        "micro_precision": dm.get("micro_precision"),
        "micro_recall": dm.get("micro_recall"),
        "interpretation_accuracy": m.get("interpretation_accuracy"),
        "n_cases": m.get("n_cases") or doc.get("n_cases_scored"),
    }


def _option_rates(mapper: Any) -> dict[str, Any]:
    if not isinstance(mapper, dict):
        return {}
    # tolerate nested summary shapes
    perf = mapper.get("performance") or mapper.get("option") or mapper
    out: dict[str, Any] = {}
    for k in (
        "option_top1",
        "option_top2",
        "at1_rate",
        "at2_rate",
        "option_at1",
        "option_at2",
    ):
        if k in perf:
            out[k] = perf[k]
        if k in mapper:
            out[k] = mapper[k]
    # common DA mapper summary
    if "n_ok" in mapper:
        out["n_ok"] = mapper["n_ok"]
    if "n_cases" in mapper:
        out["n_cases"] = mapper["n_cases"]
    # typed rates
    for a, b in (
        ("option_top1_rate", "option_top1"),
        ("option_top2_rate", "option_top2"),
        ("top1", "option_top1"),
        ("top2", "option_top2"),
    ):
        if a in mapper and b not in out:
            out[b] = mapper[a]
    return out


def _extract_ab28(summary: Any) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    arms = summary.get("arms") or summary
    out: dict[str, Any] = {}
    for key in ("R_compat", "R_compat_inject_typed", "gate", "claim_allowed"):
        if key in summary:
            out[key] = summary[key]
        if isinstance(arms, dict) and key in arms:
            out[key] = arms[key]
    # dig option rates if present
    for arm_name in ("R_compat", "R_compat_inject_typed"):
        block = arms.get(arm_name) if isinstance(arms, dict) else None
        if isinstance(block, dict):
            out[arm_name] = block
    return out


def aggregate() -> dict[str, Any]:
    ox = _read_json(OX_RAW) if OX_RAW.is_file() else {"arms": {}}
    da = _read_json(DA_RAW) if DA_RAW.is_file() else {"arms": {}}
    # Always prefer archival AB16 reuse (not live-scheduled).
    if AB16_REUSE.is_file():
        reused = _read_json(AB16_REUSE)
        arms = dict(ox.get("arms") or {})
        arms["ab16"] = {
            "label": reused.get("label"),
            "l1": reused.get("l1"),
            "cap": reused.get("cap"),
            "writeback": reused.get("writeback"),
            "micro": reused.get("micro"),
            "n_live_trees": reused.get("n_live_trees", 0),
            "output_dir": reused.get("source_run_dir"),
            "annotate_exit": 0,
            "llm_exit": 0,
            "reused": True,
            "source_eval": reused.get("source_eval"),
            "note": reused.get("note"),
        }
        ox = {**ox, "arms": arms}
    m00 = _micro(M00_OX)
    backup = BACKUP_PTR.read_text(encoding="utf-8").strip() if BACKUP_PTR.is_file() else None

    block3_rows = []
    for key in ("ab13", "ab14", "ab16", "ab17", "ab19"):
        arm = (ox.get("arms") or {}).get(key) or {}
        row = {
            "id": key.upper(),
            "label": arm.get("label"),
            "l1": arm.get("l1"),
            "cap": arm.get("cap"),
            "writeback": arm.get("writeback"),
            "micro": arm.get("micro"),
            "n_live_trees": arm.get("n_live_trees"),
            "output_dir": arm.get("output_dir"),
            "annotate_exit": arm.get("annotate_exit"),
            "llm_exit": arm.get("llm_exit"),
        }
        if arm.get("reused"):
            row["reused"] = True
            row["source_eval"] = arm.get("source_eval")
            row["note"] = arm.get("note")
        block3_rows.append(row)

    block4_rows = []
    for key in ("ab21", "ab22"):
        arm = (da.get("arms") or {}).get(key) or {}
        block4_rows.append(
            {
                "id": key.upper(),
                "label": arm.get("label"),
                "mapper": _option_rates(arm.get("mapper")),
                "raw_mapper_keys": sorted((arm.get("mapper") or {}).keys())
                if isinstance(arm.get("mapper"), dict)
                else None,
                "output_dir": arm.get("output_dir"),
                "exit_code": arm.get("exit_code"),
                "synonym_bind": False,
            }
        )

    ab28 = (da.get("arms") or {}).get("ab28") or {}
    if AB28_REUSE.is_file():
        reused28 = _read_json(AB28_REUSE)
        ab28 = {
            "label": reused28.get("label"),
            "output_dir": reused28.get("source_run_dir"),
            "exit_code": 0,
            "summary": reused28.get("summary"),
            "reused": True,
            "R_compat": reused28.get("R_compat"),
            "R_compat_inject_typed": reused28.get("R_compat_inject_typed"),
            "delta_opt1": reused28.get("delta_opt1"),
            "source_summary": reused28.get("source_summary"),
            "note": reused28.get("note"),
        }
        # Keep DA raw consistent for archival
        da_arms = dict(da.get("arms") or {})
        da_arms["ab28"] = ab28
        da = {**da, "arms": da_arms}
    doc = {
        "schema_version": 1,
        "created_at": _utc(),
        "tier": "C2_compute_reuse_frozen_T",
        "not_for_paper_main_table": True,
        "workers_ox": ox.get("workers"),
        "workers_da": da.get("workers"),
        "backup_path": backup,
        "slice_notes": {
            "block3": "OX ox_seq100 closed_live_mac; decode fixed",
            "block3_ab16": (
                "AB16 reused from compat_synonym_v1 (F6 cold + closed_live_mac); "
                "not live-scheduled in C2"
            ),
            "block4": (
                "Planned D1b-dev-freeze missing; AB21/AB22 on DA d2_seq100 proxy"
            ),
            "block6": (
                "AB28 reused from smoke_typed_remap all100 (@1 0.72→0.42); "
                "not live-scheduled in C2"
            ),
            "da_scoring": "no synonym_bind",
        },
        "ab16_reuse_archive": str(AB16_REUSE),
        "ab28_reuse_archive": str(AB28_REUSE),
        "m00_ox_readonly": m00,
        "m00_da_compat_nominal": da.get("m00_da_compat"),
        "block3_ox": block3_rows,
        "block4_da_proxy": block4_rows,
        "block6_ab28": {
            "label": ab28.get("label"),
            "output_dir": ab28.get("output_dir"),
            "exit_code": ab28.get("exit_code"),
            "reused": bool(ab28.get("reused")),
            "R_compat": ab28.get("R_compat"),
            "R_compat_inject_typed": ab28.get("R_compat_inject_typed"),
            "delta_opt1": ab28.get("delta_opt1"),
            "extracted": _extract_ab28(ab28.get("summary")),
            "summary_present": ab28.get("summary") is not None,
            "source_summary": ab28.get("source_summary"),
            "note": ab28.get("note"),
        },
        "ox_raw": str(OX_RAW),
        "da_raw": str(DA_RAW),
    }

    # Interpretations (pre-registered)
    interpretations: list[str] = []
    m00_f1 = (m00 or {}).get("micro_f1")
    by_id = {r["id"]: r for r in block3_rows}

    def f1(arm_id: str) -> float | None:
        m = (by_id.get(arm_id) or {}).get("micro") or {}
        v = m.get("micro_f1")
        return float(v) if v is not None else None

    if m00_f1 is not None and f1("AB13") is not None:
        d = float(m00_f1) - float(f1("AB13"))
        if abs(float(f1("AB13")) - float(m00_f1)) < 0.03:
            interpretations.append(
                "AB13≈M00: writeback not required for locked-F4 closed_live level"
            )
        else:
            interpretations.append(
                f"AB13 vs M00 ΔF1={-d:+.3f} (M00-AB13={d:+.3f}): writeback may contribute"
            )
    if f1("AB14") is not None and m00_f1 is not None and f1("AB13") is not None:
        # If M00-AB13 explained by AB14 alone (budget)
        gap = float(m00_f1) - float(f1("AB13"))
        ab14_gap = float(f1("AB14")) - float(f1("AB13")) if f1("AB14") and f1("AB13") else None
        if ab14_gap is not None and gap > 0.03 and abs(ab14_gap - gap) < 0.05:
            interpretations.append(
                "M00−AB13 ≈ AB14−AB13: prefer budget-calibration reading over writeback mechanism"
            )
    if f1("AB19") is not None and m00_f1 is not None:
        if float(f1("AB19")) + 0.03 >= float(m00_f1):
            interpretations.append("AB19 does not harm vs M00: cap less likely a core mechanism")
        else:
            interpretations.append("AB19 harms vs M00: retain family cap as contributor")

    # Block4 null check vs nominal 0.71/0.78
    nom = da.get("m00_da_compat") or {"option_top1": 0.71, "option_top2": 0.78}
    for row in block4_rows:
        rates = row.get("mapper") or {}
        t1 = rates.get("option_top1") or rates.get("at1_rate")
        if t1 is not None and nom.get("option_top1") is not None:
            delta = float(t1) - float(nom["option_top1"])
            if delta <= -0.10:
                interpretations.append(
                    f"{row['id']} option@1 drop {delta:+.3f} ≥0.10 vs nominal → escalate contribution"
                )
            else:
                interpretations.append(
                    f"{row['id']} option@1 Δ={delta:+.3f} (null / below 0.10 threshold)"
                )

    # Block6 AB28: expect large @1 drop
    if ab28.get("R_compat") and ab28.get("R_compat_inject_typed"):
        d1 = float(ab28["R_compat_inject_typed"].get("opt1")) - float(
            ab28["R_compat"].get("opt1")
        )
        if d1 <= -0.10:
            interpretations.append(
                f"AB28 reproduces harmful inject: Δ@1={d1:+.3f} "
                f"({ab28['R_compat'].get('opt1')}→{ab28['R_compat_inject_typed'].get('opt1')})"
            )
        else:
            interpretations.append(f"AB28 Δ@1={d1:+.3f}: does not reproduce historical harm")

    doc["interpretations"] = interpretations
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def fmt_micro(m: Any) -> str:
        if not m:
            return "—"
        return (
            f"F1={m.get('micro_f1')} P={m.get('micro_precision')} "
            f"R={m.get('micro_recall')} Interp={m.get('interpretation_accuracy')}"
        )

    lines = [
        "# C2 计算档消融结果（不入论文主表）",
        "",
        f"- created_at: `{doc['created_at']}`",
        f"- tier: **C2**（复用冻结树 T，从 E/W live；非 confirmatory AB10b）",
        f"- backup: `{backup}`",
        f"- OX workers: `{doc.get('workers_ox')}`；DA workers: `{doc.get('workers_da')}`",
        f"- DA scoring: **无 synonym_bind**",
        f"- 块4切片: **DA `d2_seq100` 代理**（计划 D1b-dev-freeze 未物化）",
        f"- AB16: **历史复用** `compat_synonym_v1` closed_live_mac（未 live 排期）；档案 `{AB16_REUSE}`",
        f"- AB28: **历史复用** `smoke_typed_remap` all100 @1 0.72→0.42（未 live 排期）；档案 `{AB28_REUSE}`",
        "",
        "## 锚点（只读）",
        "",
        f"- OX M00 closed_live_mac: {fmt_micro(m00)}",
        f"- DA compat 名义 option@1/@2: {nom}",
        "",
        "## 块3 OX（预算 / 写回 / cap）",
        "",
        "| ID | 设置 | micro | live_trees | exits |",
        "|---|---|---|---|---|",
    ]
    for r in block3_rows:
        reuse_tag = " **[reuse]**" if r.get("reused") else ""
        lines.append(
            f"| {r['id']}{reuse_tag} | L1={r['l1']} wb={r['writeback']} cap={r['cap']} | "
            f"{fmt_micro(r.get('micro'))} | {r.get('n_live_trees')} | "
            f"ann={r.get('annotate_exit')} llm={r.get('llm_exit')} |"
        )
    lines += [
        "",
        "## 块4 DA 选择器（代理切片）",
        "",
        "| ID | 设置 | mapper option | exit |",
        "|---|---|---|---|",
    ]
    for r in block4_rows:
        lines.append(
            f"| {r['id']} | {r.get('label')} | {r.get('mapper')} | {r.get('exit_code')} |"
        )
    lines += [
        "",
        "## 块6 AB28 重核",
        "",
        f"- **reused**: `{ab28.get('reused')}`",
        f"- out: `{ab28.get('output_dir')}`",
        f"- R_compat @1/@2: `{ab28.get('R_compat')}`",
        f"- inject_typed @1/@2: `{ab28.get('R_compat_inject_typed')}`",
        f"- Δ@1: `{ab28.get('delta_opt1')}`",
        f"- exit: `{ab28.get('exit_code')}`",
        f"- note: {ab28.get('note') or ''}",
        f"- extracted: `{json.dumps(doc['block6_ab28'].get('extracted'), ensure_ascii=False)[:800]}`",
        "",
        "## 预注册解读（草稿）",
        "",
    ]
    for s in interpretations:
        lines.append(f"- {s}")
    lines += [
        "",
        "## 路径索引",
        "",
        f"- `{OX_RAW}`",
        f"- `{DA_RAW}`",
        f"- `{OUT_JSON}`",
        "",
        "> 本文件仅供内部消融归档；勿写入论文主结果表。",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("WROTE", OUT_MD, OUT_JSON, flush=True)
    return doc


def _inject_ab16_into_ox_raw() -> None:
    if not AB16_REUSE.is_file():
        return
    reused = _read_json(AB16_REUSE)
    ox = _read_json(OX_RAW) if OX_RAW.is_file() else {"arms": {}, "created_at": _utc()}
    arms = dict(ox.get("arms") or {})
    # Drop any accidental live ab16 stub
    arms["ab16"] = {
        "label": reused.get("label"),
        "l1": reused.get("l1"),
        "cap": reused.get("cap"),
        "writeback": reused.get("writeback"),
        "micro": reused.get("micro"),
        "n_live_trees": 0,
        "output_dir": reused.get("source_run_dir"),
        "annotate_exit": 0,
        "llm_exit": 0,
        "reused": True,
        "source_eval": reused.get("source_eval"),
        "note": reused.get("note"),
    }
    ox["arms"] = arms
    ox["ab16_policy"] = "historical_reuse_not_live"
    OX_RAW.parent.mkdir(parents=True, exist_ok=True)
    OX_RAW.write_text(json.dumps(ox, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("injected AB16 reuse into", OX_RAW, flush=True)


def main() -> int:
    WS.mkdir(parents=True, exist_ok=True)
    _wait_pid(OX_PID, OX_LOG, "ox")
    # If suite was killed before writing raw, assemble from disks + reuse.
    if not OX_RAW.is_file():
        print("OX raw missing — assembling via guard helper", flush=True)
        subprocess.call(
            [str(PY), "-u", str(ROOT / "scripts/paper/c2_guard_skip_ab16.py")],
            cwd=str(ROOT),
        )
    _inject_ab16_into_ox_raw()
    if not OX_RAW.is_file():
        print("OX raw still missing after assemble", flush=True)
        return 2
    ox = _read_json(OX_RAW)
    bad = [
        k
        for k, v in (ox.get("arms") or {}).items()
        if k != "ab16"
        and (
            int(v.get("annotate_exit") or 0) != 0 or int(v.get("llm_exit") or 0) != 0
        )
    ]
    # Require live OX arms except AB16
    for req in ("ab13", "ab14", "ab17", "ab19"):
        if req not in (ox.get("arms") or {}):
            bad.append(f"missing:{req}")
    if bad:
        print("OX arms failed/missing:", bad, flush=True)
    da_code = _run_da()
    print("DA exit", da_code, flush=True)
    aggregate()
    return 0 if not bad and da_code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
