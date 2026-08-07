#!/usr/bin/env python3
"""RA offline isolated within-family eval (no live re-annotate).

Uses the main-run annotated L2 leaf list under the gold L1 family only
(posteriors + children from ``annotate/shared_trees``; labels cross-checked
against ``case_results`` when present).

Cohort (default): gold leaf present ∩ gold family is L1 mass-rank #1
on the reference trees (未缺叶 ∩ L1 选对).

Primary metrics (restricted to gold family's annotated L2 leaves):
  - within_fam_acc: argmax posterior leaf in gold family matches gold
  - mean / median within-family rank of gold leaf
  - hit@k within family
  - contrast: global lex top-1 / LLM Acc on the same cohort

Does **not** sweep live local evidence budgets (that requires re-annotate).
"""
from __future__ import annotations

import argparse
import json
import statistics
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

DEFAULT_RUN = ROOT / "logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1"
DEFAULT_PARQUET = (
    ROOT / "data/benchmarks/rarearena/subsets/ra_rdc_seq100_v1/cases.parquet"
)
DEFAULT_JSON = ROOT / "analysis/transfer_metrics_v1/ra_within_family_offline.json"
DEFAULT_MD = ROOT / "analysis/transfer_metrics_v1/ra_within_family_offline.md"


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


def _climb_l1(br: Mapping[str, Any], leaf: Mapping[str, Any]) -> str | None:
    cur: Mapping[str, Any] | None = leaf
    while cur and int(cur.get("level") or 0) > 1:
        cur = br.get(str(cur.get("parent") or ""))
    if cur and int(cur.get("level") or 0) == 1:
        return str(cur["id"])
    return None


def _gold_leaves_fams(
    br: Mapping[str, Any],
    leaves: Sequence[Mapping[str, Any]],
    gold: str,
    judge: LexicalJudge,
) -> tuple[list[dict[str, Any]], set[str]]:
    gold_leaves = [
        dict(b) for b in leaves if _hit(judge, str(b.get("label") or ""), gold)
    ]
    fams: set[str] = set()
    for b in gold_leaves:
        fid = _climb_l1(br, b)
        if fid:
            fams.add(fid)
    return gold_leaves, fams


def analyze_case(
    cid: str,
    tree: Mapping[str, Any],
    gold: str,
    judge: LexicalJudge,
    case_doc: Mapping[str, Any] | None,
    *,
    require_l1_correct: bool,
) -> dict[str, Any] | None:
    br = tree.get("branches") or {}
    l1 = [b for b in br.values() if int(b.get("level") or 0) == 1]
    leaves = [b for b in br.values() if not (b.get("children") or [])]
    gold_leaves, gold_fams = _gold_leaves_fams(br, leaves, gold, judge)
    if not gold_leaves or not gold_fams:
        return None

    fam_ranked = sorted(
        l1, key=lambda b: (-_fam_mass(br, b), str(b.get("id") or ""))
    )
    top_fam_id = str(fam_ranked[0]["id"]) if fam_ranked else None
    l1_correct = bool(top_fam_id and top_fam_id in gold_fams)
    if require_l1_correct and not l1_correct:
        return None

    # Gold family = highest-mass gold family (usually unique).
    fam_id = max(gold_fams, key=lambda fid: _fam_mass(br, br.get(fid) or {}))
    fam = br.get(fam_id) or {}
    # Annotated L2 leaf list = children recorded on the main-run tree.
    kids = [
        br[c]
        for c in (fam.get("children") or [])
        if isinstance(br.get(c), dict)
    ]
    # Prefer live posterior order; tie-break by id.
    kids_sorted = sorted(
        kids,
        key=lambda b: (
            -float(b.get("posterior") or 0.0),
            str(b.get("id") or ""),
        ),
    )
    gold_ids = {str(b["id"]) for b in gold_leaves if _climb_l1(br, b) == fam_id}
    # If gold leaf not under this fam's children list (shouldn't happen), skip.
    if not gold_ids:
        # gold leaf may sit under another gold fam copy; use that fam's kids
        for alt in gold_fams:
            kids_alt = [
                br[c]
                for c in ((br.get(alt) or {}).get("children") or [])
                if isinstance(br.get(c), dict)
            ]
            gids = {
                str(b["id"])
                for b in gold_leaves
                if _climb_l1(br, b) == alt
            }
            if gids:
                fam_id = alt
                fam = br.get(alt) or {}
                kids_sorted = sorted(
                    kids_alt,
                    key=lambda b: (
                        -float(b.get("posterior") or 0.0),
                        str(b.get("id") or ""),
                    ),
                )
                gold_ids = gids
                break
    if not kids_sorted or not gold_ids:
        return None

    labels = [str(b.get("label") or "") for b in kids_sorted]
    within_top1 = str(kids_sorted[0].get("id")) in gold_ids
    within_rank = None
    for i, b in enumerate(kids_sorted, 1):
        if str(b.get("id")) in gold_ids:
            within_rank = i
            break
    hit_at = {
        k: any(str(b.get("id")) in gold_ids for b in kids_sorted[:k])
        for k in (1, 2, 3, 5)
    }

    global_labs = _labs(scored_active_leaves(tree))
    global_top1 = bool(global_labs and _hit(judge, global_labs[0], gold))

    llm_hit = None
    pred = None
    auto = {}
    if case_doc:
        am = ((case_doc.get("l2") or {}).get("auto_metrics") or {})
        auto = {
            "local_champion_recall": am.get("local_champion_recall"),
            "error_attribution": am.get("error_attribution"),
            "gold_present": am.get("gold_present"),
            "top1": am.get("top1"),
        }
        # ranking labels from main record (global joint), not within-only
        fr = (case_doc.get("l2") or {}).get("final_ranking_labels") or []
        if fr:
            pred = (
                fr[0].get("label")
                if isinstance(fr[0], dict)
                else str(fr[0])
            )

    return {
        "case_id": cid,
        "gold": gold,
        "gold_fam_id": fam_id,
        "gold_fam_label": str(fam.get("label") or ""),
        "l1_correct": l1_correct,
        "n_l2_leaves_in_gold_fam": len(kids_sorted),
        "within_leaf_labels": labels,
        "within_top1_label": labels[0] if labels else "",
        "within_fam_hit": within_top1,
        "within_rank": within_rank,
        "within_hit_at": hit_at,
        "global_lex_top1_hit": global_top1,
        "global_top1_label": (global_labs[0] if global_labs else ""),
        "pred_from_case_ranking": pred,
        "auto_metrics": auto,
        "local_evidence_budget_recorded": (
            (case_doc or {}).get("l2") or {}
        ).get("local_evidence_budget"),
    }


def load_llm_hits(eval_dir: Path) -> dict[str, bool]:
    scores = eval_dir / "case_scores"
    out: dict[str, bool] = {}
    if not scores.is_dir():
        return out
    for p in scores.glob("*.json"):
        try:
            doc = _read_json(p)
        except Exception:  # noqa: BLE001
            continue
        out[p.stem] = bool(doc.get("diagnostic_hit"))
    return out


def summarize(rows: Sequence[Mapping[str, Any]], llm: Mapping[str, bool]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"n": 0}

    def rate(key: str) -> float:
        return sum(1 for r in rows if r.get(key)) / n

    ranks = [int(r["within_rank"]) for r in rows if r.get("within_rank")]
    n_leaves = [int(r["n_l2_leaves_in_gold_fam"]) for r in rows]
    llm_hits = sum(1 for r in rows if llm.get(str(r["case_id"])))
    llm_n = sum(1 for r in rows if str(r["case_id"]) in llm)

    # Confusion: within ok but global miss, etc.
    within_ok_global_miss = sum(
        1
        for r in rows
        if r.get("within_fam_hit") and not r.get("global_lex_top1_hit")
    )
    within_miss_global_ok = sum(
        1
        for r in rows
        if (not r.get("within_fam_hit")) and r.get("global_lex_top1_hit")
    )

    return {
        "n": n,
        "within_fam_acc": rate("within_fam_hit"),
        "n_within_hits": sum(1 for r in rows if r.get("within_fam_hit")),
        "within_hit_at_2": sum(1 for r in rows if (r.get("within_hit_at") or {}).get(2))
        / n,
        "within_hit_at_3": sum(1 for r in rows if (r.get("within_hit_at") or {}).get(3))
        / n,
        "within_hit_at_5": sum(1 for r in rows if (r.get("within_hit_at") or {}).get(5))
        / n,
        "mean_within_rank": round(statistics.mean(ranks), 3) if ranks else None,
        "median_within_rank": statistics.median(ranks) if ranks else None,
        "mean_n_l2_leaves_in_gold_fam": round(statistics.mean(n_leaves), 3),
        "global_lex_acc_on_cohort": rate("global_lex_top1_hit"),
        "llm_acc_on_cohort": (llm_hits / llm_n) if llm_n else None,
        "n_llm_scored": llm_n,
        "n_llm_hits": llm_hits,
        "within_ok_but_global_lex_miss": within_ok_global_miss,
        "within_miss_but_global_lex_ok": within_miss_global_ok,
        "frac_l1_correct": sum(1 for r in rows if r.get("l1_correct")) / n,
    }


def render_md(doc: Mapping[str, Any]) -> str:
    s = doc.get("summary") or {}
    lines = [
        "# RA 孤立组内评测（离线，主测 L2 叶列表）",
        "",
        "协议：`ra_within_family_offline_v1`",
        "主测：`%s`" % doc.get("run_dir"),
        "",
        "## 设定",
        "",
        "| 项 | 值 |",
        "|----|----|",
        "| 队列 | 未缺叶 ∩ L1 mass-rank#1 = gold 家族 |",
        "| n | **%d** |" % int(s.get("n") or 0),
        "| L2 叶来源 | 主测 `shared_trees` 中 gold L1 的 `children`（已标注后验） |",
        "| 证据预算扫描 | **不做**（已停止 live F4→F10） |",
        "| 评测范围 | 仅 gold 所在 L1 族内叶排序 |",
        "",
        "## 主结果",
        "",
        "| 指标 | 值 |",
        "|------|---:|",
        "| **within-fam Acc** | **%.4f** (%d/%d) |"
        % (
            float(s.get("within_fam_acc") or 0),
            int(s.get("n_within_hits") or 0),
            int(s.get("n") or 0),
        ),
        "| within hit@2 | %.4f |" % float(s.get("within_hit_at_2") or 0),
        "| within hit@3 | %.4f |" % float(s.get("within_hit_at_3") or 0),
        "| within hit@5 | %.4f |" % float(s.get("within_hit_at_5") or 0),
        "| mean / median within-rank | %s / %s |"
        % (s.get("mean_within_rank"), s.get("median_within_rank")),
        "| 均 L2 叶数（gold 族） | %s |" % s.get("mean_n_l2_leaves_in_gold_fam"),
        "| 同队列 global lex Acc | %.4f |"
        % float(s.get("global_lex_acc_on_cohort") or 0),
        "| 同队列 LLM Acc | %s |"
        % (
            ("%.4f" % s["llm_acc_on_cohort"])
            if s.get("llm_acc_on_cohort") is not None
            else "—"
        ),
        "| within✓ 但 global lex✗ | %d |"
        % int(s.get("within_ok_but_global_lex_miss") or 0),
        "",
        "## 读法",
        "",
        "- within-fam Acc：只在 gold 家族的已标注 L2 叶里取后验 top-1，是否命中 gold。",
        "- 与 global Acc 对比：若 within 高、global 低 → 瓶颈在组间/联合排序；反之 → 组内叶判别。",
        "- 本评测**固定**主测叶列表与后验，不重跑组内选证；不能替代 live local-F 扫描。",
        "",
        "## 边界",
        "",
        "- Live `within_local_f4..f10` 扫描已按用户要求停止。",
        "- `local_champion_recall` 等 auto_metrics 仅作附录对照。",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--subset-parquet", type=Path, default=DEFAULT_PARQUET)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_MD)
    ap.add_argument(
        "--include-l1-wrong",
        action="store_true",
        help="Also include cases where gold family is not mass-rank #1.",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    run = Path(args.run_dir)
    ann = run / "annotate" if (run / "annotate").is_dir() else run
    trees = ann / "shared_trees"
    cases = ann / "case_results"
    judge = LexicalJudge()
    ids = sorted(
        (p.stem for p in trees.glob("*.json") if not p.name.startswith("_")),
        key=lambda x: int(x) if x.isdigit() else x,
    )
    gold_by = _gold_map(Path(args.subset_parquet), ids)
    llm = load_llm_hits(ann / "official_eval_llm_compat")

    rows: list[dict[str, Any]] = []
    n_no_gold = 0
    n_l1_wrong_skipped = 0
    for cid in ids:
        if cid not in gold_by:
            continue
        tree = bep.load_tree_state(trees / ("%s.json" % cid))
        case_doc = None
        cp = cases / ("%s.json" % cid)
        if cp.is_file():
            try:
                case_doc = _read_json(cp)
            except Exception:  # noqa: BLE001
                case_doc = None
        # Probe gold presence
        br = tree.get("branches") or {}
        leaves = [b for b in br.values() if not (b.get("children") or [])]
        gl, gf = _gold_leaves_fams(br, leaves, gold_by[cid], judge)
        if not gl:
            n_no_gold += 1
            continue
        row = analyze_case(
            cid,
            tree,
            gold_by[cid],
            judge,
            case_doc,
            require_l1_correct=not bool(args.include_l1_wrong),
        )
        if row is None:
            n_l1_wrong_skipped += 1
            continue
        rows.append(row)

    summary = summarize(rows, llm)
    # auto_metrics local_champion_recall on cohort
    lcr = [
        r
        for r in rows
        if (r.get("auto_metrics") or {}).get("local_champion_recall") is not None
    ]
    if lcr:
        summary["local_champion_recall_rate"] = sum(
            1
            for r in lcr
            if (r.get("auto_metrics") or {}).get("local_champion_recall")
        ) / len(lcr)

    doc = {
        "protocol": "ra_within_family_offline_v1",
        "created_at": _utc(),
        "run_dir": str(run),
        "trees": str(trees),
        "n_cases_in_run": len(ids),
        "n_no_gold_leaf": n_no_gold,
        "n_l1_wrong_or_skipped": n_l1_wrong_skipped,
        "require_l1_correct": not bool(args.include_l1_wrong),
        "summary": summary,
        "cases": rows,
        "boundaries": [
            "Offline only: uses main-run annotated L2 children under gold L1.",
            "Live local-evidence F4→F10 sweep cancelled as too expensive.",
            "Does not re-select evidence; posteriors are as stored in main run.",
        ],
    }
    _write_json(Path(args.out_json), doc)
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(render_md(doc), encoding="utf-8")
    print(json.dumps({"summary": summary, "out_md": str(args.out_md)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
