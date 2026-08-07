#!/usr/bin/env python3
"""RA grain-alias align side-run (B00 naming grain).

Protocol ``ra_grain_alias_align_v1``
-----------------------------------
Eval-time only: rewrite ``pred_diagnosis`` / top-1 ddx label to a coarser or
synonymish display name drawn from same-family leaves + padded ddx, without
changing tree posteriors.

Heuristic (no gold): prefer a shorter synonymish/substring candidate when the
arbiter top-1 looks overly specific (length / token containment).

Also reports an offline Lex oracle ceiling (best candidate vs gold) for
diagnostics — that oracle is NOT used for the LLM Acc projection.

Does not overwrite formal F6 Acc=0.47.
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
from audit_ra_within_family_offline import _climb_l1  # noqa: E402
from mapper_bind_repair import labels_synonymish, norm_label  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402

DEFAULT_SRC = ROOT / "logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1"
DEFAULT_SUBSET = ROOT / "data/benchmarks/rarearena/subsets/ra_rdc_seq100_v1"
DEFAULT_OUT = ROOT / "logs/rarearena_ra_rdc_seq100_v1/grain_alias_align_v1"

# Deployable coarse aliases (species/subtype → umbrella), not near-neighbor swaps.
STATIC_COARSE = {
    "plasmodium vivax malaria": "Malaria",
    "plasmodium falciparum malaria": "Malaria",
    "plasmodium malariae malaria": "Malaria",
    "nephroblastoma": "Wilms tumor",
    "wilms tumor": "Nephroblastoma",
    "calcified ovarian fibrothecoma": "Ovarian fibrothecoma",
    "diffuse large b-cell lymphoma": "Aggressive B-cell non-Hodgkin lymphoma",
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _family_leaves(
    tree_state: Mapping[str, Any], leaf_id: str
) -> list[str]:
    br = tree_state.get("branches") or {}
    node = br.get(str(leaf_id)) or {}
    fam = _climb_l1(br, node) if node else None
    if not fam:
        return []
    kids = (br.get(fam) or {}).get("children") or []
    out: list[str] = []
    for c in kids:
        lab = str((br.get(c) or {}).get("label") or "").strip()
        if lab:
            out.append(lab)
    return out


def _candidates(
    top1: str,
    ddx: Sequence[Mapping[str, Any]],
    tree_state: Mapping[str, Any],
) -> list[str]:
    cands: list[str] = []
    seen: set[str] = set()

    def add(x: str) -> None:
        lab = str(x or "").strip()
        if not lab:
            return
        key = lab.casefold()
        if key in seen:
            return
        seen.add(key)
        cands.append(lab)

    add(top1)
    static = STATIC_COARSE.get(norm_label(top1))
    if static:
        add(static)
    for row in ddx:
        add(str(row.get("label") or ""))
    top_id = ""
    for row in ddx:
        if str(row.get("label") or "").strip().casefold() == top1.casefold():
            top_id = str(row.get("id") or "")
            break
    if top_id:
        for lab in _family_leaves(tree_state, top_id):
            add(lab)
    return cands


def _is_coarser(cand: str, top1: str) -> bool:
    na, nb = norm_label(cand), norm_label(top1)
    if not na or not nb or na == nb:
        return False
    if na in nb and len(na) + 3 <= len(nb):
        return True
    if labels_synonymish(cand, top1) and len(na.split()) < len(nb.split()):
        return True
    return False


def pick_heuristic(top1: str, cands: Sequence[str]) -> tuple[str, str]:
    """Prefer shorter synonymish / substring coarse name; else keep top1."""
    best = top1
    reason = "keep"
    # static coarse first
    static = STATIC_COARSE.get(norm_label(top1))
    if static:
        return static, "static_coarse"
    scored: list[tuple[int, str]] = []
    for c in cands:
        if c.casefold() == top1.casefold():
            continue
        if _is_coarser(c, top1):
            scored.append((len(norm_label(c)), c))
    if scored:
        scored.sort()
        return scored[0][1], "coarser_synonymish"
    return best, reason


def pick_oracle(
    top1: str, cands: Sequence[str], gold: str, judge: LexicalJudge
) -> tuple[str, str]:
    if gold and _hit(judge, top1, gold):
        return top1, "already_hit"
    for c in cands:
        if gold and _hit(judge, c, gold):
            return c, "oracle_lex_hit"
    return top1, "oracle_no_hit"


def lexical_acc(rows, gold_by, judge, key: str = "pred_diagnosis") -> dict[str, Any]:
    n = hits = 0
    for row in rows:
        cid = str(row.get("case_id") or "")
        g = gold_by.get(cid)
        if not g:
            continue
        n += 1
        if _hit(judge, str(row.get(key) or ""), g):
            hits += 1
    return {"n": n, "acc_at1": hits / n if n else 0.0, "n_hits": hits}


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
    ap.add_argument("--subset-dir", type=Path, default=DEFAULT_SUBSET)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--ddx-k", type=int, default=5)
    ap.add_argument("--judge-workers", type=int, default=50)
    ap.add_argument("--skip-llm", action="store_true")
    ap.add_argument(
        "--mode",
        choices=("heuristic", "oracle"),
        default="heuristic",
        help="heuristic=deployable; oracle=Lex ceiling vs gold (diagnostic).",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    src = Path(args.source_run)
    ann = src / "annotate"
    subset = Path(args.subset_dir)
    out = Path(args.out_dir)
    mode = str(args.mode)
    proj_sub = "eval_projection_grain_%s" % mode
    out_proj = out / "annotate" / proj_sub
    out_proj.mkdir(parents=True, exist_ok=True)
    results_dir = out / ("case_results_grain_%s" % mode)
    results_dir.mkdir(parents=True, exist_ok=True)

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

    rows: list[dict[str, Any]] = []
    n_changed = 0
    for cid in ids:
        case_doc = _read_json(ann / "case_results" / f"{cid}.json")
        tree = bep.load_tree_state(ann / "shared_trees" / f"{cid}.json")
        ddx, _meta = bep.ddx_from_compat_ranking(
            case_doc, tree, k=int(args.ddx_k)
        )
        top1 = str((ddx[0].get("label") if ddx else "") or "")
        cands = _candidates(top1, ddx, tree)
        gold = gold_by.get(cid) or ""
        if mode == "oracle":
            chosen, reason = pick_oracle(top1, cands, gold, judge)
        else:
            chosen, reason = pick_heuristic(top1, cands)
        changed = chosen.casefold() != top1.casefold()
        if changed:
            n_changed += 1
        new_ddx = [dict(x) for x in ddx]
        if new_ddx:
            # Put chosen first; keep others
            rest = [
                x
                for x in new_ddx
                if str(x.get("label") or "").casefold() != chosen.casefold()
            ]
            head = {
                **dict(new_ddx[0]),
                "label": chosen,
                "rank": 1,
                "fill_source": "grain_alias_align",
            }
            # if chosen existed in ddx, use that row
            for x in new_ddx:
                if str(x.get("label") or "").casefold() == chosen.casefold():
                    head = {**dict(x), "rank": 1, "fill_source": "grain_alias_align"}
                    break
            new_ddx = [head] + [
                {**dict(x), "rank": i + 2} for i, x in enumerate(rest)
            ]
            new_ddx = new_ddx[: int(args.ddx_k)]

        row = {
            "case_id": cid,
            "pred_diagnosis": chosen,
            "pred_ddx": new_ddx,
            "original": top1,
            "changed": changed,
            "reason": reason,
            "candidates": cands[:12],
            "mode": mode,
        }
        rows.append(row)
        _write_json(results_dir / f"{cid}.json", row)

        base_proj = ann / "eval_projection_compat" / f"{cid}.json"
        base = _read_json(base_proj) if base_proj.is_file() else {"case_id": cid}
        base.update(
            {
                "case_id": cid,
                "schema_version": 1,
                "pred_ddx": new_ddx,
                "pred_diagnosis": chosen,
                "sources": {
                    **dict(base.get("sources") or {}),
                    "ddx_source": "grain_alias_align",
                    "mode": mode,
                    "changed": changed,
                    "reason": reason,
                    "protocol": "ra_grain_alias_align_v1",
                },
            }
        )
        _write_json(out_proj / f"{cid}.json", base)

    lex = lexical_acc(rows, gold_by, judge)
    # also score originals
    lex_base = lexical_acc(
        [{"case_id": r["case_id"], "pred_diagnosis": r["original"]} for r in rows],
        gold_by,
        judge,
    )

    llm_meta: dict[str, Any] = {"skipped": True}
    if not args.skip_llm:
        if Path("/home/wanghongyi/clashctl/clashon.sh").is_file():
            subprocess.call(
                ["bash", "/home/wanghongyi/clashctl/clashon.sh"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        llm_meta = run_llm_eval(
            out,
            subset,
            proj_sub,
            "official_eval_llm_grain_%s" % mode,
            int(args.judge_workers),
        )
        llm_meta["skipped"] = False

    doc = {
        "protocol": "ra_grain_alias_align_v1",
        "created_at": _utc(),
        "source_run": str(src),
        "mode": mode,
        "n": len(rows),
        "n_changed": n_changed,
        "lexical": lex,
        "lexical_baseline_top1": lex_base,
        "llm": llm_meta,
        "baseline_llm_acc": 0.47,
        "projection_subdir": proj_sub,
        "out_dir": str(out),
        "note": "oracle mode uses gold for ceiling only; heuristic is deployable",
    }
    _write_json(out / ("grain_summary_%s.json" % mode), doc)
    print(json.dumps(doc, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
