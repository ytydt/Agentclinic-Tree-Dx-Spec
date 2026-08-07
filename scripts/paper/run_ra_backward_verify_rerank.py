#!/usr/bin/env python3
"""RA Dual-Inf transfer: frozen-tree backward-verify rerank (S2+S4).

Protocol ``ra_dualinf_backward_verify_v1``
-----------------------------------------
- Freeze main-run trees + vignette + findings (no live re-annotate).
- Candidate pools:
    * ``champions`` — one max-posterior leaf per L1 family
    * ``all_leaves`` — all L2 leaves (label-dedup)
- Dual-Inf mechanism (no forward regen):
    1. backward: recall textbook manifestations for each candidate
    2. examine: refine supports vs vignette + book knowledge; rank by support count
    3. optional reflect (S4): if top-1 supports ≤ β or top1−top2 gap < 1, re-examine
- Score = support_count (primary) then original posterior (tie-break).
- Writes side-run eval projections; optional LLM Acc via official eval.

Does not overwrite ``compat_synonym_v1`` Acc=0.47 anchor.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
os.environ.setdefault("TREE_DX_DIRECT_POST_OUTPUT_CAP", "8192")

import baseline_arms as arms  # noqa: E402
import baseline_common as bc  # noqa: E402
import build_eval_projection as bep  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
from audit_ra_budget_recalib import _gold_map, _hit  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402

DEFAULT_SRC = ROOT / "logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1"
DEFAULT_SUBSET = ROOT / "data/benchmarks/rarearena/subsets/ra_rdc_seq100_v1"
DEFAULT_OUT = (
    ROOT / "logs/rarearena_ra_rdc_seq100_v1/dualinf_backward_verify_v1"
)
DEFAULT_JSON = ROOT / "analysis/transfer_metrics_v1/ra_dualinf_transfer.json"
DEFAULT_MD = ROOT / "analysis/transfer_metrics_v1/ra_dualinf_transfer.md"

POOL_CHAMPIONS = "champions"
POOL_ALL_LEAVES = "all_leaves"

# Examine prompt adapted for tree candidates (no Dual-Inf forward supports required).
EXAMINE_TREE = """You are Dual-Inf examination over a frozen differential candidate pool.
You receive (1) patient vignette, (2) candidate diagnoses with optional tree-derived
support findings, (3) backward book manifestations per disease.
For each disease:
- drop support reasons that are not consistent with book knowledge for that disease;
- add book manifestations that are clearly present in the vignette but missing from supports;
- keep the refined support list.
Then rank diseases by number of remaining supports (more = higher confidence).
Return JSON only:
{"refined":{"Disease A":["reason",...],"Disease B":["reason",...]},
 "top_diagnoses":[{"diagnosis":"...","reasoning_summary":"..."},
 {"diagnosis":"...","reasoning_summary":"..."},
 {"diagnosis":"...","reasoning_summary":"..."},
 {"diagnosis":"...","reasoning_summary":"..."},
 {"diagnosis":"...","reasoning_summary":"..."}]}
"""

REFLECT_EXAMINE = """You are Dual-Inf examination with self-reflection. Prior ranking had
low confidence (top-1 supports ≤ beta or nearly tied with top-2).
Low-confidence / contested diagnoses: __LOW_CONFIDENCE__.
Re-examine carefully using vignette + book knowledge. You may keep or reorder.
Return the same JSON schema as examination:
{"refined":{"Disease A":["reason",...]}, "top_diagnoses":[{"diagnosis":"...","reasoning_summary":"..."}]}
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


def _fam_mass(br: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    return sum(
        float((br.get(c) or {}).get("posterior") or 0.0)
        for c in (b.get("children") or [])
    )


def _load_cases_fixture(
    ann: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    cases_doc = _read_json(ann / "normalized_cases.json")
    cases = {
        str(c["id"]): c
        for c in (cases_doc.get("cases") or [])
        if str(c.get("id") or "").strip()
    }
    fix = _read_json(ann / "finding_fixture_v1.json")
    fixture = {
        str(r["case_id"]): r
        for r in (fix.get("cases") or [])
        if str(r.get("case_id") or "").strip()
    }
    return cases, fixture


def _finding_text_map(fixture: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in fixture.get("full_findings") or []:
        fid = str(row.get("id") or "").strip()
        text = str(row.get("text") or row.get("finding") or "").strip()
        if fid and text:
            out[fid] = text
    return out


def build_candidate_pool(
    tree_state: Mapping[str, Any],
    *,
    pool: str,
    k: int = 12,
) -> list[dict[str, Any]]:
    """Return candidate leaf rows with id/label/posterior/parent_id."""
    br = tree_state.get("branches") or {}
    leaves = [b for b in br.values() if not (b.get("children") or [])]
    if pool == POOL_CHAMPIONS:
        l1 = [b for b in br.values() if int(b.get("level") or 0) == 1]
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for fam in sorted(l1, key=lambda b: (-_fam_mass(br, b), str(b.get("id")))):
            kids = [
                br[c]
                for c in (fam.get("children") or [])
                if isinstance(br.get(c), dict)
            ]
            if not kids:
                continue
            kids.sort(
                key=lambda b: (
                    -float(b.get("posterior") or 0.0),
                    str(b.get("id") or ""),
                )
            )
            top = kids[0]
            lab = str(top.get("label") or "").strip()
            if not lab or lab.casefold() in seen:
                continue
            seen.add(lab.casefold())
            out.append({
                "id": str(top.get("id") or ""),
                "label": lab,
                "posterior": float(top.get("posterior") or 0.0),
                "parent_id": str(fam.get("id") or ""),
            })
        return out[: max(1, int(k))]
    # all_leaves
    return bep.top_leaf_posterior(tree_state, k=max(1, int(k)))


def _tree_forward_supports(
    tree_state: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    fact_texts: Mapping[str, str],
) -> dict[str, list[str]]:
    """Proxy Dual-Inf forward supports from parent L1 evidence_for texts."""
    br = tree_state.get("branches") or {}
    out: dict[str, list[str]] = {}
    for cand in candidates:
        lab = str(cand.get("label") or "").strip()
        if not lab:
            continue
        pid = str(cand.get("parent_id") or "").strip()
        parent = br.get(pid) or {}
        texts: list[str] = []
        for fid in list(parent.get("evidence_for") or [])[:6]:
            t = fact_texts.get(str(fid))
            if t:
                texts.append(t)
        # leaf-level evidence if any
        leaf = br.get(str(cand.get("id") or "")) or {}
        for fid in list(leaf.get("evidence_for") or [])[:4]:
            t = fact_texts.get(str(fid))
            if t and t not in texts:
                texts.append(t)
        out[lab] = texts
    return out


def _rank_candidates(
    candidates: Sequence[Mapping[str, Any]],
    refined: Mapping[str, Sequence[str]],
) -> list[dict[str, Any]]:
    """Support-count primary, original posterior secondary."""
    by_lab = {
        str(c.get("label") or "").strip(): c
        for c in candidates
        if str(c.get("label") or "").strip()
    }
    scored: list[tuple[int, float, str, dict[str, Any]]] = []
    for lab, cand in by_lab.items():
        # match refined keys case-insensitively
        reasons: list[str] = []
        for rk, rv in refined.items():
            if str(rk).strip().casefold() == lab.casefold():
                reasons = [str(x) for x in (rv or []) if str(x).strip()]
                break
        scored.append(
            (
                len(reasons),
                float(cand.get("posterior") or 0.0),
                lab.casefold(),
                {
                    **dict(cand),
                    "label": lab,
                    "support_count": len(reasons),
                    "supports": reasons,
                    "fill_source": "backward_verify",
                },
            )
        )
    scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
    out: list[dict[str, Any]] = []
    for i, (_sc, _p, _k, row) in enumerate(scored, start=1):
        item = dict(row)
        item["rank"] = i
        out.append(item)
    return out


def _need_reflect(
    ranked: Sequence[Mapping[str, Any]],
    *,
    beta: int,
) -> bool:
    if not ranked:
        return False
    top = int(ranked[0].get("support_count") or 0)
    if top <= int(beta):
        return True
    if len(ranked) >= 2:
        second = int(ranked[1].get("support_count") or 0)
        if top - second < 1:
            return True
    return False


def rerank_case(
    *,
    cid: str,
    tree_state: Mapping[str, Any],
    case: Mapping[str, Any],
    fixture: Mapping[str, Any],
    cache: bc.SimpleCachedLLM,
    pool: str,
    pool_k: int,
    ddx_k: int,
    beta: int,
    enable_reflect: bool,
) -> dict[str, Any]:
    t0 = time.time()
    llm_calls = 0
    vignette = str(case.get("case_text") or "")
    fact_texts = _finding_text_map(fixture)
    candidates = build_candidate_pool(tree_state, pool=pool, k=pool_k)
    if not candidates:
        return {
            "case_id": cid,
            "error": "empty_pool",
            "pred_ddx": [],
            "llm_calls": 0,
            "latency_s": time.time() - t0,
        }
    diseases = [str(c["label"]) for c in candidates]
    forward = _tree_forward_supports(tree_state, candidates, fact_texts)
    base = {
        "case_id": str(case.get("id") or cid),
        "vignette": vignette,
        "question": "What is the most likely diagnosis?",
    }

    backward = cache.call(
        "RADualInfBackward",
        arms.DUAL_INF_BACKWARD,
        {**base, "diagnoses": diseases},
    )
    llm_calls += 1
    book = arms._support_map(backward)

    examine = cache.call(
        "RADualInfExamine",
        EXAMINE_TREE,
        {
            **base,
            "forward_diagnoses": forward,
            "book_knowledge": book or {d: [] for d in diseases},
            "candidates": diseases,
        },
    )
    llm_calls += 1
    refined = arms._support_map(examine) or {d: list(forward.get(d) or []) for d in diseases}
    ranked = _rank_candidates(candidates, refined)
    reflected = False
    if enable_reflect and _need_reflect(ranked, beta=beta):
        low = [
            str(r.get("label") or "")
            for r in ranked[:3]
            if int(r.get("support_count") or 0) <= beta
            or (
                ranked
                and int(ranked[0].get("support_count") or 0)
                - int(r.get("support_count") or 0)
                < 1
            )
        ]
        prompt = REFLECT_EXAMINE.replace("__LOW_CONFIDENCE__", str(low or diseases[:2]))
        examine2 = cache.call(
            "RADualInfExamineReflect",
            prompt,
            {
                **base,
                "forward_diagnoses": forward,
                "book_knowledge": book or {d: [] for d in diseases},
                "candidates": diseases,
                "prior_refined": refined,
                "low_confidence": low,
            },
        )
        llm_calls += 1
        refined2 = arms._support_map(examine2)
        if refined2:
            refined = refined2
            ranked = _rank_candidates(candidates, refined)
            reflected = True

    pred_ddx = ranked[: max(1, int(ddx_k))]
    return {
        "case_id": cid,
        "pool": pool,
        "n_candidates": len(candidates),
        "candidate_labels": diseases,
        "refined": refined,
        "book_knowledge": book,
        "pred_ddx": pred_ddx,
        "pred_diagnosis": str(pred_ddx[0]["label"]) if pred_ddx else "",
        "support_counts": [int(r.get("support_count") or 0) for r in pred_ddx],
        "reflected": reflected,
        "llm_calls": llm_calls,
        "latency_s": round(time.time() - t0, 3),
    }


def write_projection(
    *,
    out_proj: Path,
    cid: str,
    result: Mapping[str, Any],
    baseline_proj: Mapping[str, Any] | None,
) -> None:
    pred_ddx = list(result.get("pred_ddx") or [])
    base = dict(baseline_proj or {})
    base.update({
        "case_id": str(cid),
        "schema_version": 1,
        "pred_ddx": pred_ddx,
        "pred_diagnosis": str(result.get("pred_diagnosis") or ""),
        "sources": {
            **dict(base.get("sources") or {}),
            "ddx_source": "dualinf_backward_verify",
            "ddx_k": len(pred_ddx),
            "pool": result.get("pool"),
            "n_candidates": result.get("n_candidates"),
            "reflected": result.get("reflected"),
            "llm_calls": result.get("llm_calls"),
            "policy_meta": {
                "support_counts": result.get("support_counts"),
                "protocol": "ra_dualinf_backward_verify_v1",
            },
        },
    })
    _write_json(out_proj / ("%s.json" % cid), base)


def lexical_acc(
    results: Sequence[Mapping[str, Any]],
    gold_by: Mapping[str, str],
    judge: LexicalJudge,
) -> dict[str, Any]:
    n = 0
    hits = 0
    hit5 = 0
    for row in results:
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
    # Skip rebuild: projections already written by this script.
    env = {**os.environ, "PYTHONPATH": "src:scripts/paper:scripts"}
    # Official eval may rebuild if --build-projection; we pass existing subdir only.
    # Check if flag exists for skip build
    print("RUN:", " ".join(cmd), flush=True)
    # Use --no-build-projection if available; else build_projection False by omitting
    # Looking at run_ox_mcr_official_eval - need --build-projection to rebuild.
    # Without it, it uses existing projection subdir.
    rc = subprocess.call(cmd, cwd=str(ROOT), env=env)
    summary = (
        run_dir
        / "annotate"
        / out_name
        / "summary.json"
    )
    if summary.is_file():
        doc = _read_json(summary)
        m = doc.get("metrics") or {}
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
    ap.add_argument("--subset-dir", type=Path, default=DEFAULT_SUBSET)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--pool", choices=(POOL_CHAMPIONS, POOL_ALL_LEAVES, "both"), default="both")
    ap.add_argument("--pool-k", type=int, default=12)
    ap.add_argument("--ddx-k", type=int, default=5)
    ap.add_argument("--beta", type=int, default=2)
    ap.add_argument("--no-reflect", action="store_true")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--judge-workers", type=int, default=50)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--skip-llm", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    src = Path(args.source_run)
    ann = src / "annotate"
    trees = ann / "shared_trees"
    subset = Path(args.subset_dir)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if Path("/home/wanghongyi/clashctl/clashon.sh").is_file():
        subprocess.call(
            ["bash", "/home/wanghongyi/clashctl/clashon.sh"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Symlink/copy normalized_cases so official eval can find run-dir layout
    for name in ("normalized_cases.json", "finding_fixture_v1.json"):
        s = ann / name
        d = out / "annotate" / name
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_file() and not d.exists():
            try:
                d.symlink_to(s.resolve())
            except OSError:
                import shutil

                shutil.copy2(s, d)

    ids = sorted(
        (p.stem for p in trees.glob("*.json") if not p.name.startswith("_")),
        key=lambda x: int(x) if x.isdigit() else x,
    )
    if int(args.limit or 0) > 0:
        ids = ids[: int(args.limit)]
    gold_by = _gold_map(subset / "cases.parquet", ids)
    cases, fixture = _load_cases_fixture(ann)
    judge = LexicalJudge()
    llm = RobustLLMClient(model=str(args.model))

    pools = (
        [POOL_CHAMPIONS, POOL_ALL_LEAVES]
        if args.pool == "both"
        else [str(args.pool)]
    )
    arm_summaries: list[dict[str, Any]] = []

    for pool in pools:
        proj_sub = "eval_projection_dualinf_%s" % pool
        out_proj = out / "annotate" / proj_sub
        out_proj.mkdir(parents=True, exist_ok=True)
        results_dir = out / ("case_results_%s" % pool)
        results_dir.mkdir(parents=True, exist_ok=True)
        cache_root = out / ("cache_%s" % pool)
        base_proj_dir = ann / "eval_projection_compat"

        lock = threading.Lock()
        done = 0
        case_results: list[dict[str, Any]] = []

        def _one(cid: str) -> dict[str, Any]:
            nonlocal done
            out_path = results_dir / ("%s.json" % cid)
            if args.resume and out_path.is_file():
                try:
                    existing = _read_json(out_path)
                    if existing.get("pred_ddx") is not None and not existing.get("error"):
                        write_projection(
                            out_proj=out_proj,
                            cid=cid,
                            result=existing,
                            baseline_proj=(
                                _read_json(base_proj_dir / ("%s.json" % cid))
                                if (base_proj_dir / ("%s.json" % cid)).is_file()
                                else None
                            ),
                        )
                        with lock:
                            done += 1
                        return existing
                except Exception:  # noqa: BLE001
                    pass
            tree = bep.load_tree_state(trees / ("%s.json" % cid))
            cache = bc.SimpleCachedLLM(
                llm, cache_root / cid / "dualinf_cache.json", str(args.model)
            )
            result = rerank_case(
                cid=cid,
                tree_state=tree,
                case=cases.get(cid) or {},
                fixture=fixture.get(cid) or {},
                cache=cache,
                pool=pool,
                pool_k=int(args.pool_k),
                ddx_k=int(args.ddx_k),
                beta=int(args.beta),
                enable_reflect=not bool(args.no_reflect),
            )
            _write_json(out_path, result)
            write_projection(
                out_proj=out_proj,
                cid=cid,
                result=result,
                baseline_proj=(
                    _read_json(base_proj_dir / ("%s.json" % cid))
                    if (base_proj_dir / ("%s.json" % cid)).is_file()
                    else None
                ),
            )
            with lock:
                done += 1
                print(
                    "[%s] %d/%d %s top1=%r sc=%s reflect=%s calls=%s"
                    % (
                        pool,
                        done,
                        len(ids),
                        cid,
                        (result.get("pred_diagnosis") or "")[:40],
                        (result.get("support_counts") or [None])[0],
                        result.get("reflected"),
                        result.get("llm_calls"),
                    ),
                    flush=True,
                )
            return result

        print(
            json.dumps(
                {
                    "pool": pool,
                    "n": len(ids),
                    "workers": int(args.workers),
                    "reflect": not bool(args.no_reflect),
                },
                indent=2,
            ),
            flush=True,
        )
        with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as pool_ex:
            futs = [pool_ex.submit(_one, cid) for cid in ids]
            for fut in as_completed(futs):
                case_results.append(fut.result())

        case_results.sort(
            key=lambda r: int(r["case_id"])
            if str(r.get("case_id") or "").isdigit()
            else str(r.get("case_id"))
        )
        lex = lexical_acc(case_results, gold_by, judge)
        calls = [int(r.get("llm_calls") or 0) for r in case_results]
        n_reflect = sum(1 for r in case_results if r.get("reflected"))
        llm_meta: dict[str, Any] = {"skipped": True}
        if not args.skip_llm:
            # Point official eval at our out-dir with written projections.
            # Need shared_trees symlink for eval scaffolding
            st_link = out / "annotate" / "shared_trees"
            if not st_link.exists():
                try:
                    st_link.symlink_to(trees.resolve())
                except OSError:
                    pass
            llm_meta = run_llm_eval(
                out,
                subset,
                projection_subdir=proj_sub,
                out_name="official_eval_llm_dualinf_%s" % pool,
                workers=int(args.judge_workers),
            )
            llm_meta["skipped"] = False

        arm = {
            "pool": pool,
            "n": len(case_results),
            "lexical": lex,
            "llm": llm_meta,
            "mean_llm_calls": round(statistics.mean(calls), 3) if calls else 0.0,
            "n_reflected": n_reflect,
            "projection_subdir": proj_sub,
        }
        arm_summaries.append(arm)
        print(json.dumps(arm, indent=2, ensure_ascii=False), flush=True)

    doc = {
        "protocol": "ra_dualinf_backward_verify_v1",
        "created_at": _utc(),
        "source_run": str(src),
        "baseline_llm_acc": 0.47,
        "arms": arm_summaries,
        "out_dir": str(out),
        "settings": {
            "pool_k": int(args.pool_k),
            "ddx_k": int(args.ddx_k),
            "beta": int(args.beta),
            "reflect": not bool(args.no_reflect),
            "model": str(args.model),
        },
    }
    _write_json(out / "dualinf_rerank_summary.json", doc)
    print(json.dumps(doc, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
