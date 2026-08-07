#!/usr/bin/env python3
"""RA pair-adjudicate side-run (B06 supervisor shrunk).

Protocol ``ra_pair_adjudicate_v1``
---------------------------------
Start from F6 compat projection. When top-1 and top-2 are a near-tie
(|Δposterior| < tau), call a single supervisor-style LLM to choose between
the two labels given the vignette. Otherwise keep arbiter top-1.

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
sys.path.insert(0, str(ROOT / "scripts"))

import build_eval_projection as bep  # noqa: E402
from audit_ra_budget_recalib import _gold_map, _hit  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402

DEFAULT_SRC = ROOT / "logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1"
DEFAULT_SUBSET = ROOT / "data/benchmarks/rarearena/subsets/ra_rdc_seq100_v1"
DEFAULT_OUT = ROOT / "logs/rarearena_ra_rdc_seq100_v1/pair_adjudicate_v1"

PAIR_PROMPT = """You are a supervising physician. Given the case vignette and exactly two
candidate diagnoses that are nearly tied, choose the single more likely diagnosis.
Reply JSON only: {"choice":"<exact candidate label>","reason":"<one short sentence>"}
The choice MUST be exactly one of the two candidate strings.
"""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _vignette(case_doc: Mapping[str, Any], subset_cases: Mapping[str, Any]) -> str:
    cid = str(case_doc.get("case_id") or "")
    for src in (case_doc, subset_cases.get(cid) or {}):
        for k in ("case_text", "vignette", "presentation", "text"):
            v = src.get(k) if isinstance(src, Mapping) else None
            if v:
                return str(v)
    return ""


def _load_subset_cases(subset: Path) -> dict[str, Any]:
    p = subset / "normalized_cases.json"
    if not p.is_file():
        return {}
    raw = _read_json(p)
    if isinstance(raw, list):
        out = {}
        for row in raw:
            cid = str(row.get("id") or row.get("case_id") or "")
            if cid:
                out[cid] = row
        return out
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items()}
    return {}


def _post(row: Mapping[str, Any]) -> float:
    return float(row.get("posterior") or 0.0)


def apply_pair(
    *,
    ddx: Sequence[Mapping[str, Any]],
    vignette: str,
    tau: float,
    cache: Any | None,
    dry_run: bool = False,
) -> dict[str, Any]:
    rows = [dict(r) for r in ddx if str(r.get("label") or "").strip()]
    if len(rows) < 2:
        return {
            "pred_ddx": rows,
            "pred_diagnosis": str(rows[0]["label"]) if rows else "",
            "triggered": False,
            "reason": "lt2",
        }
    a, b = rows[0], rows[1]
    gap = abs(_post(a) - _post(b))
    if gap >= float(tau):
        return {
            "pred_ddx": rows,
            "pred_diagnosis": str(a["label"]),
            "triggered": False,
            "reason": "gap_ge_tau",
            "posterior_gap": gap,
        }

    lab_a = str(a["label"]).strip()
    lab_b = str(b["label"]).strip()
    choice = lab_a
    raw = None
    if dry_run or cache is None:
        # Offline: keep arbiter (no LLM) — used only for trigger counting.
        reason = "dry_keep"
    else:
        payload = {
            "vignette": vignette[:6000],
            "candidate_a": lab_a,
            "candidate_b": lab_b,
            "posterior_a": _post(a),
            "posterior_b": _post(b),
        }
        raw = cache.call(
            "RAPairAdjudicate",
            PAIR_PROMPT,
            payload,
        )
        if isinstance(raw, dict):
            ch = str(raw.get("choice") or "").strip()
            if ch.casefold() == lab_b.casefold():
                choice = lab_b
            elif ch.casefold() == lab_a.casefold():
                choice = lab_a
            else:
                # fuzzy contain
                if lab_b.casefold() in ch.casefold():
                    choice = lab_b
                elif lab_a.casefold() in ch.casefold():
                    choice = lab_a
        reason = "pair_llm"

    if choice.casefold() == lab_b.casefold():
        rows = [b, a] + rows[2:]
        swapped = True
    else:
        swapped = False
    for i, r in enumerate(rows):
        r["rank"] = i + 1
        if i == 0 and swapped:
            r["fill_source"] = "pair_adjudicate"
    return {
        "pred_ddx": rows,
        "pred_diagnosis": str(rows[0]["label"]) if rows else "",
        "triggered": True,
        "swapped": swapped,
        "reason": reason,
        "posterior_gap": gap,
        "raw": raw if isinstance(raw, dict) else None,
    }


def lexical_acc(rows, gold_by, judge) -> dict[str, Any]:
    n = hits = hit5 = 0
    for row in rows:
        cid = str(row.get("case_id") or "")
        g = gold_by.get(cid)
        if not g:
            continue
        n += 1
        labs = [str(x.get("label") or "") for x in (row.get("pred_ddx") or [])]
        if labs and _hit(judge, labs[0], g):
            hits += 1
        if any(_hit(judge, x, g) for x in labs[:5]):
            hit5 += 1
    return {
        "n": n,
        "acc_at1": hits / n if n else 0.0,
        "n_hits": hits,
        "hit_at5": hit5 / n if n else 0.0,
        "n_hit5": hit5,
    }


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


def _make_cache(model: str, cache_path: Path):
    import baseline_common as bc
    from agentclinic_tree_dx.llm_client import RobustLLMClient

    os.environ.setdefault("TREE_DX_USE_PROXY", "1")
    client = RobustLLMClient(model=str(model))
    return bc.SimpleCachedLLM(client, cache_path, str(model))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-run", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--subset-dir", type=Path, default=DEFAULT_SUBSET)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--tau", type=float, default=0.15)
    ap.add_argument("--ddx-k", type=int, default=5)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--judge-workers", type=int, default=50)
    ap.add_argument("--skip-llm", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    src = Path(args.source_run)
    ann = src / "annotate"
    subset = Path(args.subset_dir)
    out = Path(args.out_dir)
    tau = float(args.tau)
    proj_sub = "eval_projection_pair_t%.3f" % tau
    out_proj = out / "annotate" / proj_sub
    out_proj.mkdir(parents=True, exist_ok=True)
    results_dir = out / ("case_results_pair_t%.3f" % tau)
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
    subset_cases = _load_subset_cases(subset)
    cache_root = out / "cache_pair"
    cache_root.mkdir(parents=True, exist_ok=True)

    def _one(cid: str) -> dict[str, Any]:
        case_doc = _read_json(ann / "case_results" / f"{cid}.json")
        tree = bep.load_tree_state(ann / "shared_trees" / f"{cid}.json")
        ddx, _meta = bep.ddx_from_compat_ranking(
            case_doc, tree, k=int(args.ddx_k)
        )
        vignette = _vignette(case_doc, subset_cases)
        if not vignette:
            proj = ann / "eval_projection_compat" / f"{cid}.json"
            if proj.is_file():
                vignette = str(
                    (_read_json(proj).get("pred_reasoning_trace") or "")[:4000]
                )
        cache = None
        if not args.dry_run:
            cache = _make_cache(str(args.model), cache_root / f"{cid}.json")
        got = apply_pair(
            ddx=ddx,
            vignette=vignette,
            tau=tau,
            cache=cache,
            dry_run=bool(args.dry_run),
        )
        row = {"case_id": cid, **got, "tau": tau}
        _write_json(results_dir / f"{cid}.json", row)
        base_proj = ann / "eval_projection_compat" / f"{cid}.json"
        base = _read_json(base_proj) if base_proj.is_file() else {"case_id": cid}
        base.update(
            {
                "case_id": cid,
                "schema_version": 1,
                "pred_ddx": got["pred_ddx"],
                "pred_diagnosis": got["pred_diagnosis"],
                "sources": {
                    **dict(base.get("sources") or {}),
                    "ddx_source": "pair_adjudicate",
                    "tau": tau,
                    "triggered": got.get("triggered"),
                    "swapped": got.get("swapped"),
                    "protocol": "ra_pair_adjudicate_v1",
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

    lex = lexical_acc(rows, gold_by, judge)
    n_trig = sum(1 for r in rows if r.get("triggered"))
    n_swap = sum(1 for r in rows if r.get("swapped"))

    if Path("/home/wanghongyi/clashctl/clashon.sh").is_file():
        subprocess.call(
            ["bash", "/home/wanghongyi/clashctl/clashon.sh"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    llm_meta: dict[str, Any] = {"skipped": True}
    if not args.skip_llm and not args.dry_run:
        llm_meta = run_llm_eval(
            out,
            subset,
            proj_sub,
            "official_eval_llm_pair_t%.3f" % tau,
            int(args.judge_workers),
        )
        llm_meta["skipped"] = False

    doc = {
        "protocol": "ra_pair_adjudicate_v1",
        "created_at": _utc(),
        "source_run": str(src),
        "tau": tau,
        "n": len(rows),
        "n_triggered": n_trig,
        "n_swapped": n_swap,
        "lexical": lex,
        "llm": llm_meta,
        "baseline_llm_acc": 0.47,
        "projection_subdir": proj_sub,
        "out_dir": str(out),
    }
    _write_json(out / ("pair_summary_t%.3f.json" % tau), doc)
    print(json.dumps(doc, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
