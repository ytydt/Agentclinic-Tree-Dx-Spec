#!/usr/bin/env python3
"""[DEPRECATED] Full-case within-local live reann sweep — too expensive.

Use instead: ``run_ra_within_goldfam_local_prefix.py``
  (gold-family-only selector@F10 + evidence-prefix replay for F4..F10).

Kept for reference only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import build_eval_projection as bep  # noqa: E402
from audit_ox_budget_recalib import scored_active_leaves  # noqa: E402
from audit_ox_c2a_force_emit import _labs  # noqa: E402
from audit_ra_budget_recalib import _gold_map, _hit  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402

DEFAULT_SRC = ROOT / "logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1"
DEFAULT_SUBSET = ROOT / "data/benchmarks/rarearena/subsets/ra_rdc_seq100_v1"
DEFAULT_OUT_ROOT = ROOT / "logs/rarearena_ra_rdc_seq100_v1"
DEFAULT_JSON = ROOT / "analysis/transfer_metrics_v1/ra_within_local_budget_sweep.json"
DEFAULT_MD = ROOT / "analysis/transfer_metrics_v1/ra_within_local_budget_sweep.md"

# High cand so per-family leaf cap does not masquerade as evidence budget.
FIXED_CAND_MAX = 32
FIXED_L1 = 6
FIXED_BETWEEN = 2


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


def _gold_leaves_and_fams(
    br: Mapping[str, Any],
    leaves: Sequence[Mapping[str, Any]],
    gold: str,
    judge: LexicalJudge,
) -> tuple[list[dict[str, Any]], set[str]]:
    gold_leaves = [
        b for b in leaves if _hit(judge, str(b.get("label") or ""), gold)
    ]
    gold_fams: set[str] = set()
    for b in gold_leaves:
        cur: Mapping[str, Any] | None = b
        while cur and int(cur.get("level") or 0) > 1:
            cur = br.get(str(cur.get("parent") or ""))
        if cur and int(cur.get("level") or 0) == 1:
            gold_fams.add(str(cur["id"]))
    return gold_leaves, gold_fams


def select_cohort(
    trees_dir: Path,
    gold_by: Mapping[str, str],
    judge: LexicalJudge,
) -> list[str]:
    """未缺叶 ∩ L1(mass-rank#1)==gold family, using reference F6 trees."""
    ids = sorted(
        (p.stem for p in trees_dir.glob("*.json") if not p.name.startswith("_")),
        key=lambda x: int(x) if x.isdigit() else x,
    )
    out: list[str] = []
    for cid in ids:
        if cid not in gold_by:
            continue
        t = bep.load_tree_state(trees_dir / ("%s.json" % cid))
        br = t.get("branches") or {}
        l1 = [b for b in br.values() if int(b.get("level") or 0) == 1]
        leaves = [b for b in br.values() if not (b.get("children") or [])]
        gold_leaves, gold_fams = _gold_leaves_and_fams(
            br, leaves, gold_by[cid], judge
        )
        if not gold_leaves or not gold_fams:
            continue
        fam_ranked = sorted(
            l1, key=lambda b: (-_fam_mass(br, b), str(b.get("id") or ""))
        )
        if fam_ranked and str(fam_ranked[0]["id"]) in gold_fams:
            out.append(cid)
    return out


def score_trees(
    trees_dir: Path,
    case_ids: Sequence[str],
    gold_by: Mapping[str, str],
    judge: LexicalJudge,
    case_results_dir: Path | None = None,
) -> dict[str, Any]:
    """Within-family + global lex metrics on the cohort."""
    n = 0
    within_hit = 0
    global_hit = 0
    within_ranks: list[int] = []
    evi_on_gold_fam: list[int] = []
    local_evi_ids_n: list[int] = []

    for cid in case_ids:
        if cid not in gold_by:
            continue
        tp = trees_dir / ("%s.json" % cid)
        if not tp.is_file():
            continue
        t = bep.load_tree_state(tp)
        br = t.get("branches") or {}
        leaves = [b for b in br.values() if not (b.get("children") or [])]
        g = gold_by[cid]
        gold_leaves, gold_fams = _gold_leaves_and_fams(br, leaves, g, judge)
        if not gold_fams:
            continue
        n += 1
        # Prefer the gold family with highest mass if multiple.
        fam_id = max(
            gold_fams,
            key=lambda fid: _fam_mass(br, br.get(fid) or {}),
        )
        fam = br.get(fam_id) or {}
        evi_on_gold_fam.append(
            len(fam.get("evidence_for") or [])
            + len(fam.get("evidence_against") or [])
        )
        kids = [
            br[c]
            for c in (fam.get("children") or [])
            if isinstance(br.get(c), dict)
        ]
        kids.sort(
            key=lambda b: (
                -float(b.get("posterior") or 0.0),
                str(b.get("id") or ""),
            )
        )
        gold_ids = {str(b["id"]) for b in gold_leaves}
        # within Acc: top leaf in gold fam matches gold
        if kids and str(kids[0].get("id")) in gold_ids:
            within_hit += 1
        rank = None
        for i, b in enumerate(kids, 1):
            if str(b.get("id")) in gold_ids:
                rank = i
                break
        if rank is not None:
            within_ranks.append(rank)

        top1 = (_labs(scored_active_leaves(t)) or [""])[0]
        if top1 and _hit(judge, top1, g):
            global_hit += 1

        # local evidence ids from case_results if present
        if case_results_dir is not None:
            cp = case_results_dir / ("%s.json" % cid)
            if cp.is_file():
                try:
                    doc = _read_json(cp)
                except Exception:  # noqa: BLE001
                    doc = {}
                champs = (
                    ((doc.get("l2") or {}).get("dynamic_assets") or {}).get(
                        "champions"
                    )
                    or ((doc.get("l2") or {}).get("champions") or [])
                )
                for ch in champs:
                    if str(ch.get("parent_id") or "") == fam_id:
                        ids = ch.get("local_evidence_ids") or []
                        local_evi_ids_n.append(len(ids))
                        break

    return {
        "n_scored": n,
        "within_fam_acc": (within_hit / n) if n else 0.0,
        "n_within_hits": within_hit,
        "global_lex_acc": (global_hit / n) if n else 0.0,
        "n_global_lex_hits": global_hit,
        "mean_within_rank": (
            round(statistics.mean(within_ranks), 3) if within_ranks else None
        ),
        "median_within_rank": (
            statistics.median(within_ranks) if within_ranks else None
        ),
        "n_ranked": len(within_ranks),
        "mean_l1_evi_links_on_gold_fam": (
            round(statistics.mean(evi_on_gold_fam), 3) if evi_on_gold_fam else None
        ),
        "mean_local_evi_ids_on_gold_fam_champion": (
            round(statistics.mean(local_evi_ids_n), 3) if local_evi_ids_n else None
        ),
        "n_with_local_evi_ids": len(local_evi_ids_n),
    }


def _copy_frozen(src: Path, out: Path, case_ids: Sequence[str]) -> None:
    src_f = src / "frozen"
    dst_f = out / "frozen"
    dst_f.mkdir(parents=True, exist_ok=True)
    for name in ("vignette_parser_frozen.json", "p5_headline_frozen.json"):
        p = src_f / name
        if p.is_file():
            shutil.copy2(p, dst_f / name)
    for sub in ("shared_trees", "p5_audit"):
        s = src_f / sub
        d = dst_f / sub
        d.mkdir(parents=True, exist_ok=True)
        if not s.is_dir():
            continue
        for cid in case_ids:
            sp = s / ("%s.json" % cid)
            if sp.is_file():
                shutil.copy2(sp, d / sp.name)


def _prepare_annotate(
    out: Path, case_ids: Sequence[str], src: Path, subset: Path
) -> None:
    ann = out / "annotate"
    ann.mkdir(parents=True, exist_ok=True)
    src_trees = out / "frozen" / "shared_trees"
    dst_trees = ann / "shared_trees"
    dst_trees.mkdir(parents=True, exist_ok=True)
    for cid in case_ids:
        sp = src_trees / ("%s.json" % cid)
        if sp.is_file():
            shutil.copy2(sp, dst_trees / sp.name)
    p5 = out / "frozen" / "p5_headline_frozen.json"
    if p5.is_file():
        shutil.copy2(p5, ann / "p5_headline_frozen.json")
    man = ann / "stage_manifest.json"
    if man.is_file():
        man.unlink()
    for nc_src in (
        src / "annotate" / "normalized_cases.json",
        subset / "normalized_cases.json",
    ):
        if nc_src.is_file():
            shutil.copy2(nc_src, out / "normalized_cases.json")
            shutil.copy2(nc_src, ann / "normalized_cases.json")
            break
    for name in ("finding_fixture_v1.json",):
        s = src / "annotate" / name
        if s.is_file():
            shutil.copy2(s, ann / name)


def _seed_caches(src: Path, out: Path, case_ids: Sequence[str]) -> int:
    n = 0
    src_c = src / "annotate" / "cache"
    if not src_c.is_dir():
        return 0
    for cid in case_ids:
        s = src_c / cid
        if not s.is_dir():
            continue
        d = out / "annotate" / "cache" / cid
        if d.exists():
            continue
        shutil.copytree(s, d)
        n += 1
    return n


def _run_annotate(
    out: Path,
    case_ids: Sequence[str],
    subset: Path,
    *,
    local_n: int,
    workers: int,
    model: str,
) -> int:
    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "scripts/paper/run_diagnosisarena_pipeline_staged.py"),
        "--cases-json",
        str(subset / "normalized_cases.json"),
        "--cases",
        ",".join(case_ids),
        "--output-dir",
        str(out),
        "--workers",
        str(workers),
        "--model",
        model,
        "--granularity-mode",
        "compat",
        "--l1-calib",
        "off",
        "--synonym-bind-repair",
        "--from-stage",
        "annotate",
        "--to-stage",
        "annotate",
        "--fixed-l1-budget",
        str(FIXED_L1),
        "--l2-local-evidence-budget",
        str(local_n),
        "--l2-between-evidence-budget",
        str(FIXED_BETWEEN),
        "--l2-candidate-max-per-live-family",
        str(FIXED_CAND_MAX),
        "--resume",
    ]
    env = {
        **os.environ,
        "PYTHONPATH": "src:scripts/paper:scripts",
        "TREE_DX_DIRECT_POST_OUTPUT_CAP": "4096",
        "TREE_DX_USE_PROXY": "1",
        "TREE_DX_EMBED_DEVICE": "cpu",
    }
    print("RUN:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _run_llm_acc(
    out: Path, subset: Path, case_ids: Sequence[str], *, workers: int
) -> int:
    # Eval whole run dir; we filter metrics to cohort in post.
    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "scripts/paper/run_ox_mcr_official_eval.py"),
        "--dataset",
        "rarearena",
        "--run-dir",
        str(out),
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
        "--build-projection",
        "--projection-subdir",
        "eval_projection_compat",
        "--out-name",
        "official_eval_llm_compat",
    ]
    # Restrict via case filter if supported — else post-filter.
    env = {**os.environ, "PYTHONPATH": "src:scripts/paper:scripts"}
    print("RUN:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _llm_subset_acc(eval_dir: Path, case_ids: Sequence[str]) -> dict[str, Any]:
    scores = eval_dir / "case_scores"
    if not scores.is_dir():
        return {"n": 0, "acc": None, "hits": 0}
    hits = 0
    n = 0
    for cid in case_ids:
        p = scores / ("%s.json" % cid)
        if not p.is_file():
            continue
        doc = _read_json(p)
        n += 1
        if doc.get("diagnostic_hit"):
            hits += 1
    return {"n": n, "acc": (hits / n) if n else None, "hits": hits}


def _render_md(doc: Mapping[str, Any]) -> str:
    lines = [
        "# RA 组内证据预算孤立扫描（local F4→F10）",
        "",
        "协议：`ra_within_local_evidence_sweep_v1`",
        "参考树：`%s`" % doc.get("reference_trees"),
        "机器表：[`ra_within_local_budget_sweep.json`](ra_within_local_budget_sweep.json)",
        "",
        "## 设定",
        "",
        "| 项 | 值 |",
        "|----|----|",
        "| 队列 | 未缺叶 ∩ L1 mass-rank#1 = gold 家族 |",
        "| n | **%d** |" % int(doc.get("n_cohort") or 0),
        "| 扫描 | `l2_local_evidence_budget` ∈ %s |"
        % (doc.get("local_grid") or []),
        "| 固定 L1 / between / cand | %d / %d / %d（cand 抬高，避免叶剪枝混淆） |"
        % (FIXED_L1, FIXED_BETWEEN, FIXED_CAND_MAX),
        "| 含义 | 组内选证 `stop_after`，**不是**候选叶裁剪 |",
        "",
        "## 结果（按 within-fam Acc）",
        "",
        "| local F | within-fam Acc | global lex Acc | LLM Acc | mean within-rank | mean local_evi# |",
        "|--------:|---------------:|---------------:|--------:|-----------------:|----------------:|",
    ]
    rows = list(doc.get("arms") or [])
    rows_sorted = sorted(
        rows,
        key=lambda r: (
            float((r.get("metrics") or {}).get("within_fam_acc") or 0),
            float(((r.get("llm") or {}).get("acc") or -1)),
        ),
        reverse=True,
    )
    for r in sorted(rows, key=lambda x: int(x.get("local") or 0)):
        m = r.get("metrics") or {}
        llm = r.get("llm") or {}
        lines.append(
            "| %s | %.4f | %.4f | %s | %s | %s |"
            % (
                r.get("local"),
                float(m.get("within_fam_acc") or 0),
                float(m.get("global_lex_acc") or 0),
                (
                    ("%.4f" % llm["acc"])
                    if llm.get("acc") is not None
                    else "—"
                ),
                m.get("mean_within_rank"),
                m.get("mean_local_evi_ids_on_gold_fam_champion"),
            )
        )
    best = rows_sorted[0] if rows_sorted else {}
    lines.extend(
        [
            "",
            "## 锁定建议",
            "",
            "- 最优 local（within-fam Acc 优先，其次 LLM Acc）：**F%s**"
            % best.get("local"),
            "- 相对 F4 Δ within-fam Acc：见 JSON `delta_vs_f4`",
            "",
            "## 边界",
            "",
            "- 全部 local 均为 live 重标（cand=32）；仅 cohort 计分。",
            "- 不含缺叶 / L1 选错例；组间 between 固定为 2。",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-run", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--subset-dir", type=Path, default=DEFAULT_SUBSET)
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_MD)
    ap.add_argument("--local-min", type=int, default=4)
    ap.add_argument("--local-max", type=int, default=10)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--judge-workers", type=int, default=50)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument(
        "--skip-annotate",
        action="store_true",
        help="Only score existing arm dirs / F6 for local=4.",
    )
    ap.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM Acc (lex/within metrics only).",
    )
    ap.add_argument(
        "--only-local",
        type=int,
        nargs="*",
        default=None,
        help="If set, only run these local values.",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    src = Path(args.source_run)
    subset = Path(args.subset_dir)
    trees_ref = src / "annotate" / "shared_trees"
    parquet = subset / "cases.parquet"
    judge = LexicalJudge()
    all_ids = sorted(
        (p.stem for p in trees_ref.glob("*.json") if not p.name.startswith("_")),
        key=lambda x: int(x) if x.isdigit() else x,
    )
    gold_by = _gold_map(parquet, all_ids)
    cohort = select_cohort(trees_ref, gold_by, judge)
    grid = list(range(int(args.local_min), int(args.local_max) + 1))
    if args.only_local:
        grid = [int(x) for x in args.only_local]

    cohort_path = (
        Path(args.out_root) / "within_local_sweep_v1" / "cohort_case_ids.json"
    )
    _write_json(
        cohort_path,
        {
            "created_at": _utc(),
            "protocol": "ra_within_local_evidence_sweep_v1",
            "n_cohort": len(cohort),
            "case_ids": cohort,
            "reference_trees": str(trees_ref),
            "fixed": {
                "l1_evidence_budget": FIXED_L1,
                "l2_between_evidence_budget": FIXED_BETWEEN,
                "l2_candidate_max_per_live_family": FIXED_CAND_MAX,
            },
            "local_grid": grid,
        },
    )
    print(
        json.dumps(
            {"n_cohort": len(cohort), "local_grid": grid, "cohort_path": str(cohort_path)},
            indent=2,
        ),
        flush=True,
    )

    arms: list[dict[str, Any]] = []
    f4_within = None
    for local_n in grid:
        out = Path(args.out_root) / ("within_local_f%d_v1" % local_n)
        if not args.skip_annotate:
            out.mkdir(parents=True, exist_ok=True)
            _write_json(
                out / "within_local_launch.json",
                {
                    "created_at": _utc(),
                    "local": local_n,
                    "n_cases": len(cohort),
                    "source_run": str(src),
                    "fixed": {
                        "l1": FIXED_L1,
                        "between": FIXED_BETWEEN,
                        "cand": FIXED_CAND_MAX,
                    },
                },
            )
            _copy_frozen(src, out, cohort)
            _prepare_annotate(out, cohort, src, subset)
            n_cache = _seed_caches(src, out, cohort)
            print("local=%d seeded_caches=%d" % (local_n, n_cache), flush=True)
            rc = _run_annotate(
                out,
                cohort,
                subset,
                local_n=local_n,
                workers=int(args.workers),
                model=str(args.model),
            )
            if rc != 0:
                print("annotate failed local=%d rc=%d" % (local_n, rc), flush=True)
                return rc
        trees = out / "annotate" / "shared_trees"
        cr = out / "annotate" / "case_results"
        if not trees.is_dir():
            print("missing trees for local=%d at %s" % (local_n, trees), flush=True)
            return 2

        metrics = score_trees(trees, cohort, gold_by, judge, cr)
        llm_meta: dict[str, Any] = {"skipped": True}
        if not args.skip_llm:
            if Path("/home/wanghongyi/clashctl/clashon.sh").is_file():
                subprocess.call(
                    ["bash", "/home/wanghongyi/clashctl/clashon.sh"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            rc = _run_llm_acc(
                out, subset, cohort, workers=int(args.judge_workers)
            )
            if rc != 0:
                print("llm eval failed local=%d rc=%d" % (local_n, rc), flush=True)
            llm_meta = _llm_subset_acc(
                out / "annotate" / "official_eval_llm_compat", cohort
            )
            llm_meta["skipped"] = False

        if local_n == 4:
            f4_within = float(metrics.get("within_fam_acc") or 0)

        arm = {
            "local": local_n,
            "run_dir": str(out),
            "trees": str(trees),
            "metrics": metrics,
            "llm": llm_meta,
        }
        arms.append(arm)
        print(json.dumps(arm, ensure_ascii=False, indent=2), flush=True)

    for arm in arms:
        w = float((arm.get("metrics") or {}).get("within_fam_acc") or 0)
        arm["delta_vs_f4_within"] = (
            None if f4_within is None else round(w - f4_within, 4)
        )

    # Lock: max within_fam_acc, tie-break LLM acc, then prefer smaller local.
    def _key(a: Mapping[str, Any]) -> tuple:
        m = a.get("metrics") or {}
        llm = a.get("llm") or {}
        return (
            float(m.get("within_fam_acc") or 0),
            float(llm.get("acc") or -1),
            -int(a.get("local") or 0),
        )

    best = max(arms, key=_key) if arms else {}
    doc = {
        "protocol": "ra_within_local_evidence_sweep_v1",
        "created_at": _utc(),
        "reference_trees": str(trees_ref),
        "n_cohort": len(cohort),
        "case_ids": cohort,
        "local_grid": grid,
        "fixed": {
            "l1_evidence_budget": FIXED_L1,
            "l2_between_evidence_budget": FIXED_BETWEEN,
            "l2_candidate_max_per_live_family": FIXED_CAND_MAX,
            "note": "cand raised to 32 to isolate evidence usage from leaf pruning",
        },
        "arms": arms,
        "locked_local": best.get("local"),
        "locked_arm": best,
        "boundaries": [
            "Evidence stop_after sweep only; not apply_budget_proxy leaf truncation.",
            "Cohort = gold-in-leaves AND gold family mass-rank #1 on F6 trees.",
            "All local values are live side runs with cand_max=32.",
        ],
    }
    _write_json(Path(args.out_json), doc)
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(_render_md(doc), encoding="utf-8")
    print(
        json.dumps(
            {
                "locked_local": doc.get("locked_local"),
                "out_json": str(args.out_json),
                "out_md": str(args.out_md),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
