#!/usr/bin/env python3
"""RA transfer combo: Gate(best δ) ⊕ Pair(untouched) ⊕ Grain(heuristic).

Protocol ``ra_transfer_combo_v1``
--------------------------------
1. Start from gate projection (champions, chosen delta).
2. On cases NOT overridden by gate, optionally apply pair adjudicate if
   |Δposterior| < tau (using original F6 posteriors for the pair).
3. Finally apply grain heuristic rename on the resulting top-1.

Does not overwrite formal F6 Acc=0.47.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

os.environ.setdefault("TREE_DX_USE_PROXY", "1")

import build_eval_projection as bep  # noqa: E402
import run_ra_dualinf_conditional_gate as gate_mod  # noqa: E402
import run_ra_grain_alias_align as grain_mod  # noqa: E402
import run_ra_pair_adjudicate as pair_mod  # noqa: E402
from audit_ra_budget_recalib import _gold_map, _hit  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402

DEFAULT_SRC = ROOT / "logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1"
DEFAULT_DUALINF = ROOT / "logs/rarearena_ra_rdc_seq100_v1/dualinf_backward_verify_v1"
DEFAULT_SUBSET = ROOT / "data/benchmarks/rarearena/subsets/ra_rdc_seq100_v1"
DEFAULT_OUT = ROOT / "logs/rarearena_ra_rdc_seq100_v1/transfer_combo_v1"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def run_llm_eval(run_dir, subset, proj_sub, out_name, workers) -> dict[str, Any]:
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_ox_mcr_official_eval.py"),
        "--dataset", "rarearena",
        "--run-dir", str(run_dir),
        "--subset-parquet", str(subset / "cases.parquet"),
        "--judge", "llm",
        "--skip-reasoning-recall",
        "--ddx-k", "5",
        "--workers", str(workers),
        "--ddx-source", "compat",
        "--projection-subdir", proj_sub,
        "--out-name", out_name,
    ]
    env = {**os.environ, "PYTHONPATH": "src:scripts/paper:scripts"}
    print("RUN:", " ".join(cmd), flush=True)
    rc = subprocess.call(cmd, cwd=str(ROOT), env=env)
    summary = run_dir / "annotate" / out_name / "summary.json"
    if summary.is_file():
        m = (_read_json(summary).get("metrics") or {})
        return {
            "rc": rc,
            "acc": m.get("diagnostic_accuracy_single_trajectory"),
            "hits": m.get("n_diagnostic_hits"),
            "summary": str(summary),
        }
    return {"rc": rc, "acc": None, "hits": None}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-run", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--dualinf-dir", type=Path, default=DEFAULT_DUALINF)
    ap.add_argument("--subset-dir", type=Path, default=DEFAULT_SUBSET)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--delta", type=int, default=2)
    ap.add_argument("--tau", type=float, default=0.15)
    ap.add_argument("--ddx-k", type=int, default=5)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--judge-workers", type=int, default=50)
    ap.add_argument("--skip-llm", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    src = Path(args.source_run)
    ann = src / "annotate"
    dual = Path(args.dualinf_dir)
    cr_dir = dual / "case_results_champions"
    subset = Path(args.subset_dir)
    out = Path(args.out_dir)
    delta = int(args.delta)
    tau = float(args.tau)
    proj_sub = "eval_projection_combo_d%d_t%.3f" % (delta, tau)
    out_proj = out / "annotate" / proj_sub
    out_proj.mkdir(parents=True, exist_ok=True)
    results_dir = out / ("case_results_combo_d%d_t%.3f" % (delta, tau))
    results_dir.mkdir(parents=True, exist_ok=True)
    cache_root = out / "cache_combo"
    cache_root.mkdir(parents=True, exist_ok=True)

    for name in ("normalized_cases.json", "finding_fixture_v1.json"):
        s = ann / name
        d = out / "annotate" / name
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_file() and not d.exists():
            try:
                d.symlink_to(s.resolve())
            except OSError:
                shutil.copy2(s, d)
    st = out / "annotate" / "shared_trees"
    if not st.exists():
        try:
            st.symlink_to((ann / "shared_trees").resolve())
        except OSError:
            pass

    ids = [
        ln.strip()
        for ln in (subset / "case_ids.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    gold_by = _gold_map(subset / "cases.parquet", ids)
    judge = LexicalJudge()
    subset_cases = pair_mod._load_subset_cases(subset)

    def _one(cid: str) -> dict[str, Any]:
        case_doc = _read_json(ann / "case_results" / f"{cid}.json")
        tree = bep.load_tree_state(ann / "shared_trees" / f"{cid}.json")
        padded = gate_mod._padded_ddx(case_doc, tree, k=int(args.ddx_k))
        dual_row = _read_json(cr_dir / f"{cid}.json")
        gated = gate_mod.apply_gate(
            arbiter_ddx=padded, dualinf_row=dual_row, delta=delta
        )
        ddx = list(gated["pred_ddx"])
        stages: dict[str, Any] = {
            "gate_overridden": bool(gated.get("overridden")),
            "gate_reason": gated.get("reason"),
        }

        # Pair only if gate did not override.
        pair_applied = False
        swapped = False
        if not gated.get("overridden"):
            vignette = pair_mod._vignette(case_doc, subset_cases)
            if not vignette:
                proj = ann / "eval_projection_compat" / f"{cid}.json"
                if proj.is_file():
                    vignette = str(
                        (_read_json(proj).get("pred_reasoning_trace") or "")[:4000]
                    )
            cache = pair_mod._make_cache(
                str(args.model), cache_root / f"{cid}.json"
            )
            paired = pair_mod.apply_pair(
                ddx=ddx, vignette=vignette, tau=tau, cache=cache, dry_run=False
            )
            stages["pair_triggered"] = paired.get("triggered")
            stages["pair_swapped"] = paired.get("swapped")
            stages["pair_reason"] = paired.get("reason")
            ddx = list(paired["pred_ddx"])
            pair_applied = bool(paired.get("triggered"))
            swapped = bool(paired.get("swapped"))
        else:
            stages["pair_triggered"] = False
            stages["pair_skipped"] = "gate_overrode"

        top1 = str((ddx[0].get("label") if ddx else "") or "")
        cands = grain_mod._candidates(top1, ddx, tree)
        chosen, grain_reason = grain_mod.pick_heuristic(top1, cands)
        grain_changed = chosen.casefold() != top1.casefold()
        stages["grain_changed"] = grain_changed
        stages["grain_reason"] = grain_reason

        new_ddx = [dict(x) for x in ddx]
        if new_ddx and grain_changed:
            rest = [
                x
                for x in new_ddx
                if str(x.get("label") or "").casefold() != chosen.casefold()
            ]
            head = None
            for x in new_ddx:
                if str(x.get("label") or "").casefold() == chosen.casefold():
                    head = {
                        **dict(x),
                        "rank": 1,
                        "fill_source": "grain_alias_align",
                    }
                    break
            if head is None:
                head = {
                    **dict(new_ddx[0]),
                    "label": chosen,
                    "rank": 1,
                    "fill_source": "grain_alias_align",
                }
            new_ddx = [head] + [
                {**dict(x), "rank": i + 2} for i, x in enumerate(rest)
            ]
            new_ddx = new_ddx[: int(args.ddx_k)]
        elif new_ddx:
            for i, x in enumerate(new_ddx):
                x["rank"] = i + 1

        row = {
            "case_id": cid,
            "pred_ddx": new_ddx,
            "pred_diagnosis": str(new_ddx[0]["label"]) if new_ddx else "",
            "stages": stages,
            "delta": delta,
            "tau": tau,
            "pair_applied": pair_applied,
            "pair_swapped": swapped,
            "grain_changed": grain_changed,
        }
        _write_json(results_dir / f"{cid}.json", row)

        base_proj = ann / "eval_projection_compat" / f"{cid}.json"
        base = _read_json(base_proj) if base_proj.is_file() else {"case_id": cid}
        base.update(
            {
                "case_id": cid,
                "schema_version": 1,
                "pred_ddx": new_ddx,
                "pred_diagnosis": row["pred_diagnosis"],
                "sources": {
                    **dict(base.get("sources") or {}),
                    "ddx_source": "transfer_combo",
                    "delta": delta,
                    "tau": tau,
                    "stages": stages,
                    "protocol": "ra_transfer_combo_v1",
                },
            }
        )
        _write_json(out_proj / f"{cid}.json", base)
        return row

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as ex:
        futs = {ex.submit(_one, cid): cid for cid in ids}
        for fut in as_completed(futs):
            rows.append(fut.result())
    rows.sort(key=lambda r: int(r["case_id"]) if str(r["case_id"]).isdigit() else 0)

    # Lexical
    n = hits = 0
    for row in rows:
        g = gold_by.get(str(row["case_id"]))
        if not g:
            continue
        n += 1
        if _hit(judge, str(row.get("pred_diagnosis") or ""), g):
            hits += 1
    lex = {"n": n, "acc_at1": hits / n if n else 0.0, "n_hits": hits}

    if Path("/home/wanghongyi/clashctl/clashon.sh").is_file():
        subprocess.call(
            ["bash", "/home/wanghongyi/clashctl/clashon.sh"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    llm_meta: dict[str, Any] = {"skipped": True}
    if not args.skip_llm:
        llm_meta = run_llm_eval(
            out,
            subset,
            proj_sub,
            "official_eval_llm_combo_d%d_t%.3f" % (delta, tau),
            int(args.judge_workers),
        )
        llm_meta["skipped"] = False

    doc = {
        "protocol": "ra_transfer_combo_v1",
        "created_at": _utc(),
        "source_run": str(src),
        "delta": delta,
        "tau": tau,
        "n": len(rows),
        "n_gate_override": sum(
            1 for r in rows if (r.get("stages") or {}).get("gate_overridden")
        ),
        "n_pair_swap": sum(1 for r in rows if r.get("pair_swapped")),
        "n_grain_changed": sum(1 for r in rows if r.get("grain_changed")),
        "lexical": lex,
        "llm": llm_meta,
        "baseline_llm_acc": 0.47,
        "projection_subdir": proj_sub,
        "out_dir": str(out),
    }
    _write_json(
        out / ("combo_summary_d%d_t%.3f.json" % (delta, tau)), doc
    )
    print(json.dumps(doc, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
