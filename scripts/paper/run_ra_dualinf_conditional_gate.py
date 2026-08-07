#!/usr/bin/env python3
"""RA conditional fusion gate over Dual-Inf supports + arbiter baseline.

Protocol ``ra_dualinf_conditional_gate_v1``
------------------------------------------
Reuse frozen Dual-Inf examine outputs from ``dualinf_backward_verify_v1``.
Start from arbiter top-1 (main-run projection). Override only when:

  support(challenger) - support(arbiter_top1) >= delta
  AND challenger label ∈ S1-padded ddx (arbiter ∪ posterior pad)

Default delta=2 (report recommendation). Writes side-run projections and
optional LLM Acc. Does not overwrite the F6 Acc=0.47 anchor.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import build_eval_projection as bep  # noqa: E402
from audit_ra_budget_recalib import _gold_map, _hit  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402

DEFAULT_SRC = ROOT / "logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1"
DEFAULT_DUALINF = ROOT / "logs/rarearena_ra_rdc_seq100_v1/dualinf_backward_verify_v1"
DEFAULT_SUBSET = ROOT / "data/benchmarks/rarearena/subsets/ra_rdc_seq100_v1"
DEFAULT_OUT = ROOT / "logs/rarearena_ra_rdc_seq100_v1/dualinf_conditional_gate_v1"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _support_of(refined: Mapping[str, Sequence[str]], lab: str) -> int:
    want = str(lab or "").strip().casefold()
    if not want:
        return 0
    for k, v in refined.items():
        if str(k).strip().casefold() == want:
            return len([x for x in (v or []) if str(x).strip()])
    return 0


def _padded_ddx(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = 5,
) -> list[dict[str, Any]]:
    pred, _meta = bep.ddx_from_compat_ranking(case_doc, tree_state, k=k)
    return pred


def apply_gate(
    *,
    arbiter_ddx: Sequence[Mapping[str, Any]],
    dualinf_row: Mapping[str, Any],
    delta: int,
) -> dict[str, Any]:
    """Return gated pred_ddx + override metadata."""
    if not arbiter_ddx:
        return {
            "pred_ddx": list(dualinf_row.get("pred_ddx") or []),
            "overridden": False,
            "reason": "empty_arbiter",
        }
    arb_top = dict(arbiter_ddx[0])
    arb_lab = str(arb_top.get("label") or "").strip()
    refined = {
        str(k): list(v or [])
        for k, v in (dualinf_row.get("refined") or {}).items()
    }
    pool_labels = {
        str(x.get("label") or "").strip().casefold()
        for x in arbiter_ddx
        if str(x.get("label") or "").strip()
    }
    arb_sc = _support_of(refined, arb_lab)

    best: dict[str, Any] | None = None
    best_sc = -1
    for row in dualinf_row.get("pred_ddx") or []:
        lab = str(row.get("label") or "").strip()
        if not lab or lab.casefold() not in pool_labels:
            continue
        sc = _support_of(refined, lab)
        # Prefer dualinf order among equal support.
        if sc > best_sc:
            best_sc = sc
            best = dict(row)

    overridden = False
    reason = "keep_arbiter"
    chosen = arb_top
    if (
        best is not None
        and str(best.get("label") or "").casefold() != arb_lab.casefold()
        and best_sc - arb_sc >= int(delta)
    ):
        overridden = True
        reason = "support_delta_ge_%d" % int(delta)
        chosen = best

    # Rebuild ranking: chosen first, then remaining arbiter padded order.
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in ([chosen], list(arbiter_ddx), list(dualinf_row.get("pred_ddx") or [])):
        for row in src:
            lab = str(row.get("label") or "").strip()
            if not lab or lab.casefold() in seen:
                continue
            seen.add(lab.casefold())
            item = dict(row)
            item["label"] = lab
            item["rank"] = len(out) + 1
            item["support_count"] = _support_of(refined, lab)
            item["fill_source"] = (
                "conditional_gate_override"
                if overridden and lab.casefold() == str(chosen.get("label") or "").casefold()
                else item.get("fill_source") or "arbiter"
            )
            out.append(item)
            if len(out) >= 5:
                break
        if len(out) >= 5:
            break

    return {
        "pred_ddx": out,
        "pred_diagnosis": str(out[0]["label"]) if out else "",
        "overridden": overridden,
        "reason": reason,
        "arbiter_label": arb_lab,
        "arbiter_support": arb_sc,
        "challenger_label": str((best or {}).get("label") or ""),
        "challenger_support": best_sc if best is not None else None,
        "delta": int(delta),
        "support_gap": (best_sc - arb_sc) if best is not None else None,
    }


def lexical_acc(
    rows: Sequence[Mapping[str, Any]],
    gold_by: Mapping[str, str],
    judge: LexicalJudge,
) -> dict[str, Any]:
    n = hits = hit5 = 0
    for row in rows:
        cid = str(row.get("case_id") or "")
        g = gold_by.get(cid)
        if not g:
            continue
        n += 1
        labs = [
            str(x.get("label") or "")
            for x in (row.get("pred_ddx") or [])
            if str(x.get("label") or "").strip()
        ]
        if labs and _hit(judge, labs[0], g):
            hits += 1
        if any(_hit(judge, x, g) for x in labs[:5]):
            hit5 += 1
    return {
        "n": n,
        "acc_at1": (hits / n) if n else 0.0,
        "n_hits": hits,
        "hit_at5": (hit5 / n) if n else 0.0,
        "n_hit5": hit5,
    }


def run_llm_eval(
    run_dir: Path,
    subset: Path,
    *,
    projection_subdir: str,
    out_name: str,
    workers: int,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "scripts/paper/run_ox_mcr_official_eval.py"),
        "--dataset",
        "rarearena",
        "--run-dir",
        str(run_dir),
        "--subset-parquet",
        str(subset / "cases.parquet"),
        "--judge",
        "llm",
        "--skip-reasoning-recall",
        "--ddx-k",
        "5",
        "--workers",
        str(workers),
        "--ddx-source",
        "compat",
        "--projection-subdir",
        projection_subdir,
        "--out-name",
        out_name,
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
    return {"rc": rc, "acc": None, "hits": None, "summary": str(summary)}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-run", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--dualinf-dir", type=Path, default=DEFAULT_DUALINF)
    ap.add_argument("--subset-dir", type=Path, default=DEFAULT_SUBSET)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--pool",
        choices=("champions", "all_leaves"),
        default="champions",
        help="Which Dual-Inf examine outputs to gate over.",
    )
    ap.add_argument("--delta", type=int, default=2)
    ap.add_argument("--ddx-k", type=int, default=5)
    ap.add_argument("--judge-workers", type=int, default=50)
    ap.add_argument("--skip-llm", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    src = Path(args.source_run)
    ann = src / "annotate"
    trees = ann / "shared_trees"
    dual = Path(args.dualinf_dir)
    cr_dir = dual / ("case_results_%s" % args.pool)
    if not cr_dir.is_dir():
        raise SystemExit("missing dualinf case results: %s" % cr_dir)

    subset = Path(args.subset_dir)
    out = Path(args.out_dir)
    proj_sub = "eval_projection_gate_%s_d%d" % (args.pool, int(args.delta))
    out_proj = out / "annotate" / proj_sub
    out_proj.mkdir(parents=True, exist_ok=True)
    results_dir = out / ("case_results_gate_%s_d%d" % (args.pool, int(args.delta)))
    results_dir.mkdir(parents=True, exist_ok=True)

    # Layout for official eval
    for name in ("normalized_cases.json", "finding_fixture_v1.json"):
        s = ann / name
        d = out / "annotate" / name
        if s.is_file() and not d.exists():
            try:
                d.symlink_to(s.resolve())
            except OSError:
                shutil.copy2(s, d)
    st = out / "annotate" / "shared_trees"
    if not st.exists():
        try:
            st.symlink_to(trees.resolve())
        except OSError:
            pass

    if Path("/home/wanghongyi/clashctl/clashon.sh").is_file():
        subprocess.call(
            ["bash", "/home/wanghongyi/clashctl/clashon.sh"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    ids = sorted(
        (p.stem for p in trees.glob("*.json") if not p.name.startswith("_")),
        key=lambda x: int(x) if x.isdigit() else x,
    )
    gold_by = _gold_map(subset / "cases.parquet", ids)
    judge = LexicalJudge()

    rows: list[dict[str, Any]] = []
    n_override = 0
    for cid in ids:
        case_doc = _read_json(ann / "case_results" / ("%s.json" % cid))
        tree = bep.load_tree_state(trees / ("%s.json" % cid))
        padded = _padded_ddx(case_doc, tree, k=int(args.ddx_k))
        dual_row = _read_json(cr_dir / ("%s.json" % cid))
        gated = apply_gate(
            arbiter_ddx=padded,
            dualinf_row=dual_row,
            delta=int(args.delta),
        )
        if gated.get("overridden"):
            n_override += 1
        row = {
            "case_id": cid,
            **gated,
            "pool": args.pool,
        }
        rows.append(row)
        _write_json(results_dir / ("%s.json" % cid), row)

        base_proj = ann / "eval_projection_compat" / ("%s.json" % cid)
        base = _read_json(base_proj) if base_proj.is_file() else {"case_id": cid}
        base.update({
            "case_id": cid,
            "schema_version": 1,
            "pred_ddx": gated["pred_ddx"],
            "pred_diagnosis": gated["pred_diagnosis"],
            "sources": {
                **dict(base.get("sources") or {}),
                "ddx_source": "dualinf_conditional_gate",
                "ddx_k": len(gated["pred_ddx"]),
                "pool": args.pool,
                "delta": int(args.delta),
                "overridden": gated.get("overridden"),
                "policy_meta": {
                    "reason": gated.get("reason"),
                    "arbiter_support": gated.get("arbiter_support"),
                    "challenger_support": gated.get("challenger_support"),
                    "support_gap": gated.get("support_gap"),
                    "protocol": "ra_dualinf_conditional_gate_v1",
                },
            },
        })
        _write_json(out_proj / ("%s.json" % cid), base)

    lex = lexical_acc(rows, gold_by, judge)
    llm_meta: dict[str, Any] = {"skipped": True}
    if not args.skip_llm:
        llm_meta = run_llm_eval(
            out,
            subset,
            projection_subdir=proj_sub,
            out_name="official_eval_llm_gate_%s_d%d" % (args.pool, int(args.delta)),
            workers=int(args.judge_workers),
        )
        llm_meta["skipped"] = False

    doc = {
        "protocol": "ra_dualinf_conditional_gate_v1",
        "created_at": _utc(),
        "source_run": str(src),
        "dualinf_dir": str(dual),
        "pool": args.pool,
        "delta": int(args.delta),
        "n": len(rows),
        "n_overridden": n_override,
        "lexical": lex,
        "llm": llm_meta,
        "baseline_llm_acc": 0.47,
        "projection_subdir": proj_sub,
        "out_dir": str(out),
    }
    _write_json(out / ("gate_summary_%s_d%d.json" % (args.pool, int(args.delta))), doc)
    print(json.dumps(doc, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
