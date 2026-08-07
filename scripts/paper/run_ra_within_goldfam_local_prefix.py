#!/usr/bin/env python3
"""RA gold-family isolated local-evidence prefix sweep (efficient).

Protocol ``ra_within_goldfam_local_prefix_v1``
---------------------------------------------
- Cohort: gold leaf present AND gold L1 family is mass-rank #1 on F6 main trees.
- L2 leaf list: frozen from main-run ``shared_trees`` (no L2 regen).
- Scope: **only the gold L1 family** — one selector run with ``stop_after=10``.
- Prefix property: selected_fact_ids[:k] for k∈{4..10} is the Fk evidence set
  (dynamic selector is sequential; larger budget = prefix-extension of smaller).
- Per k: local annotator on gold-family L2 leaves with facts[:k] → within-fam Acc.

Much cheaper than full-case re-annotate × 7 budgets.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
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

import eval_l1_evidence_bfs as bfs  # noqa: E402
import eval_l2_competition_strategies as competition  # noqa: E402
import eval_l2_dynamic_evidence_marginals as dynamic  # noqa: E402
import eval_l2_joint_dynamic_pipeline as joint  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
from audit_ra_budget_recalib import _gold_map, _hit  # noqa: E402
from diagnosisarena_l2_pipeline import (  # noqa: E402
    deserialize_state,
    l1_posterior_rows,
)
from transfer_eval.judges import LexicalJudge  # noqa: E402

DEFAULT_SRC = ROOT / "logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1"
DEFAULT_SUBSET = ROOT / "data/benchmarks/rarearena/subsets/ra_rdc_seq100_v1"
DEFAULT_OUT = (
    ROOT / "logs/rarearena_ra_rdc_seq100_v1/within_goldfam_local_prefix_v1"
)
DEFAULT_JSON = (
    ROOT / "analysis/transfer_metrics_v1/ra_within_goldfam_local_prefix.json"
)
DEFAULT_MD = (
    ROOT / "analysis/transfer_metrics_v1/ra_within_goldfam_local_prefix.md"
)

SELECTOR_MODULE = "L2GoldFamLocalEvidenceSelector_prefix"
ANNOTATOR_MODULE = "L2GoldFamLocalAnnotator_prefix"


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


def _gold_fams(
    br: Mapping[str, Any],
    leaves: Sequence[Mapping[str, Any]],
    gold: str,
    judge: LexicalJudge,
) -> tuple[list[dict[str, Any]], set[str]]:
    gold_leaves = [
        b for b in leaves if _hit(judge, str(b.get("label") or ""), gold)
    ]
    fams: set[str] = set()
    for b in gold_leaves:
        cur: Mapping[str, Any] | None = b
        while cur and int(cur.get("level") or 0) > 1:
            cur = br.get(str(cur.get("parent") or ""))
        if cur and int(cur.get("level") or 0) == 1:
            fams.add(str(cur["id"]))
    return gold_leaves, fams


def select_cohort(
    trees_dir: Path, gold_by: Mapping[str, str], judge: LexicalJudge
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ids = sorted(
        (p.stem for p in trees_dir.glob("*.json") if not p.name.startswith("_")),
        key=lambda x: int(x) if x.isdigit() else x,
    )
    for cid in ids:
        if cid not in gold_by:
            continue
        raw = _read_json(trees_dir / ("%s.json" % cid))
        state_doc = raw.get("state") or raw
        br = state_doc.get("branches") or {}
        l1 = [b for b in br.values() if int(b.get("level") or 0) == 1]
        leaves = [b for b in br.values() if not (b.get("children") or [])]
        gold_leaves, fams = _gold_fams(br, leaves, gold_by[cid], judge)
        if not gold_leaves or not fams:
            continue
        fam_ranked = sorted(
            l1, key=lambda b: (-_fam_mass(br, b), str(b.get("id") or ""))
        )
        if not fam_ranked or str(fam_ranked[0]["id"]) not in fams:
            continue
        # Prefer mass-top gold fam (usually the unique top-1).
        fam_id = str(fam_ranked[0]["id"])
        child_ids = [
            str(c) for c in (br.get(fam_id) or {}).get("children") or []
        ]
        rows.append(
            {
                "case_id": cid,
                "gold_fam_id": fam_id,
                "gold_fam_label": str((br.get(fam_id) or {}).get("label") or ""),
                "l2_leaf_ids": child_ids,
                "n_l2": len(child_ids),
            }
        )
    return rows


def _load_cases_and_fixture(
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


def _within_hit(
    posteriors: Sequence[Mapping[str, Any]],
    gold: str,
    judge: LexicalJudge,
) -> tuple[bool, int | None, str]:
    if not posteriors:
        return False, None, ""
    ranked = sorted(
        posteriors,
        key=lambda r: (-float(r.get("posterior") or 0.0), str(r.get("id") or "")),
    )
    top = ranked[0]
    top_lab = str(top.get("label") or "")
    hit = bool(top_lab and _hit(judge, top_lab, gold))
    rank = None
    for i, row in enumerate(ranked, 1):
        if _hit(judge, str(row.get("label") or ""), gold):
            rank = i
            break
    return hit, rank, top_lab


def run_case(
    *,
    cohort_row: Mapping[str, Any],
    tree_path: Path,
    case: Mapping[str, Any],
    fixture: Mapping[str, Any],
    gold: str,
    judge: LexicalJudge,
    llm: RobustLLMClient,
    cache_dir: Path,
    local_max: int,
    local_grid: Sequence[int],
    model: str,
) -> dict[str, Any]:
    cid = str(cohort_row["case_id"])
    fam_id = str(cohort_row["gold_fam_id"])
    raw = _read_json(tree_path)
    state = deserialize_state(raw.get("state") or raw)
    # Freeze L2 children to main-run list (drop any extras if tree drifted).
    want = set(cohort_row.get("l2_leaf_ids") or [])
    parent = state.branches.get(fam_id)
    if parent is None:
        return {"case_id": cid, "error": "missing_gold_fam", "by_k": {}}
    parent.children = [c for c in (parent.children or []) if str(c) in want]
    # Drop non-kept sibling leaves from state? annotator scopes via rescale.
    l1_rows = l1_posterior_rows(state)
    # Keep only gold fam in l1_rows for scope helpers that iterate parents.
    l1_rows = [r for r in l1_rows if str(r.get("id")) == fam_id]
    if not l1_rows:
        l1_rows = [
            {
                "id": fam_id,
                "label": parent.label,
                "posterior": float(parent.posterior or 0.0),
            }
        ]

    case_text = str(case.get("case_text") or "")
    findings = list(fixture.get("full_findings") or [])
    if not findings or not case_text:
        return {"case_id": cid, "error": "missing_findings_or_text", "by_k": {}}

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = bfs.CachedLLM(llm, cache_dir / "goldfam_local_cache.json", model)
    selector_prompt = dynamic.PROMPT_PATH.read_text(encoding="utf-8")
    annotator_prompt = competition.ANNOTATOR_PROMPT_PATH.read_text(encoding="utf-8")

    branches = competition.rescale_l2_scope(
        state, l1_rows, [fam_id], use_parent_mass=False
    )
    # Restrict candidates to frozen main-run L2 ids.
    branches = {bid: b for bid, b in branches.items() if str(bid) in want}
    if not branches:
        return {"case_id": cid, "error": "empty_l2_scope", "by_k": {}}

    candidate_rows = competition._candidate_rows(branches, state)
    selection = dynamic.dynamic_l2_evidence_order(
        cache=cache,
        module=SELECTOR_MODULE,
        prompt=selector_prompt,
        case_text=case_text,
        findings=findings,
        candidates=joint._selector_candidates(candidate_rows),
        stop_after=int(local_max),
    )
    ordered_ids = [str(x) for x in (selection.get("selected_fact_ids") or [])]
    # Prefix property: Fk = ordered_ids[:k]

    by_k: dict[str, Any] = {}
    for k in local_grid:
        k = int(k)
        fact_ids = ordered_ids[:k]
        try:
            selected_facts = joint._facts_for_ids(findings, fact_ids)
        except ValueError as exc:
            by_k[str(k)] = {"error": str(exc)}
            continue
        if selected_facts:
            output = competition._annotate_scope(
                cache=cache,
                module=ANNOTATOR_MODULE,
                prompt=annotator_prompt,
                case_text=case_text,
                findings=findings,
                selected_facts=selected_facts,
                branches=branches,
                tree_state=state,
            )
        else:
            output = {
                "schema_valid": True,
                "posteriors": [
                    {
                        "id": b.id,
                        "label": b.label,
                        "posterior": float(b.posterior or 0.0),
                    }
                    for b in branches.values()
                ],
            }
        posts = list(output.get("posteriors") or [])
        hit, rank, top_lab = _within_hit(posts, gold, judge)
        by_k[str(k)] = {
            "n_evidence": len(fact_ids),
            "evidence_ids": fact_ids,
            "within_hit": hit,
            "within_rank": rank,
            "top_label": top_lab,
            "schema_valid": bool(output.get("schema_valid")),
            "n_candidates": len(branches),
        }

    return {
        "case_id": cid,
        "gold": gold,
        "gold_fam_id": fam_id,
        "gold_fam_label": cohort_row.get("gold_fam_label"),
        "n_l2_frozen": len(want),
        "selector_stop_after": int(local_max),
        "selected_fact_ids_fmax": ordered_ids,
        "n_selected_fmax": len(ordered_ids),
        "stop_reason": selection.get("stop_reason"),
        "by_k": by_k,
    }


def aggregate(
    case_results: Sequence[Mapping[str, Any]], local_grid: Sequence[int]
) -> list[dict[str, Any]]:
    arms = []
    for k in local_grid:
        hits = 0
        n = 0
        ranks: list[int] = []
        evi_ns: list[int] = []
        for row in case_results:
            cell = (row.get("by_k") or {}).get(str(k))
            if not cell or cell.get("error"):
                continue
            n += 1
            if cell.get("within_hit"):
                hits += 1
            if cell.get("within_rank") is not None:
                ranks.append(int(cell["within_rank"]))
            evi_ns.append(int(cell.get("n_evidence") or 0))
        arms.append(
            {
                "local": int(k),
                "n": n,
                "within_fam_acc": (hits / n) if n else 0.0,
                "n_within_hits": hits,
                "mean_within_rank": (
                    round(statistics.mean(ranks), 3) if ranks else None
                ),
                "median_within_rank": (
                    statistics.median(ranks) if ranks else None
                ),
                "mean_n_evidence": (
                    round(statistics.mean(evi_ns), 3) if evi_ns else None
                ),
            }
        )
    return arms


def _render_md(doc: Mapping[str, Any]) -> str:
    lines = [
        "# RA gold 族内孤立组内证据前缀扫描（F4←F10）",
        "",
        "协议：`ra_within_goldfam_local_prefix_v1`",
        "参考：`%s`" % doc.get("source_run"),
        "",
        "## 设定",
        "",
        "| 项 | 值 |",
        "|----|----|",
        "| 队列 | 未缺叶 ∩ L1 mass#1=gold 族 |",
        "| n | **%d** |" % int(doc.get("n_cohort") or 0),
        "| L2 叶 | 主测 `shared_trees` 冻结（不重生成） |",
        "| 选证 | 仅 gold L1 族；一次 `stop_after=%s` |"
        % doc.get("local_max"),
        "| Fk | `selected_fact_ids[:k]` 前缀回放 |",
        "| 指标 | gold 族内 within-fam Acc / within-rank |",
        "",
        "## 结果",
        "",
        "| local F | within-fam Acc | hits | mean within-rank | mean #evi |",
        "|--------:|---------------:|-----:|-----------------:|----------:|",
    ]
    for a in doc.get("arms") or []:
        lines.append(
            "| %s | %.4f | %s/%s | %s | %s |"
            % (
                a.get("local"),
                float(a.get("within_fam_acc") or 0),
                a.get("n_within_hits"),
                a.get("n"),
                a.get("mean_within_rank"),
                a.get("mean_n_evidence"),
            )
        )
    lines.extend(
        [
            "",
            "## 锁定",
            "",
            "- 最优 local（within-fam Acc，并列取更小 F）：**F%s**"
            % doc.get("locked_local"),
            "",
            "## 边界",
            "",
            "- 非全案 live reann；不改组间 / L1 证据。",
            "- 前缀合法性依赖动态选证的顺序累积；annotator 对各 Fk 独立调用。",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-run", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--subset-dir", type=Path, default=DEFAULT_SUBSET)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_MD)
    ap.add_argument("--local-min", type=int, default=4)
    ap.add_argument("--local-max", type=int, default=10)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--limit", type=int, default=0, help="Smoke: first N cohort cases")
    args = ap.parse_args(list(argv) if argv is not None else None)

    src = Path(args.source_run)
    ann = src / "annotate"
    trees = ann / "shared_trees"
    subset = Path(args.subset_dir)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cache_root = out / "cache"
    results_dir = out / "case_results"
    results_dir.mkdir(parents=True, exist_ok=True)

    if Path("/home/wanghongyi/clashctl/clashon.sh").is_file():
        import subprocess

        subprocess.call(
            ["bash", "/home/wanghongyi/clashctl/clashon.sh"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    judge = LexicalJudge()
    all_ids = sorted(
        (p.stem for p in trees.glob("*.json") if not p.name.startswith("_")),
        key=lambda x: int(x) if x.isdigit() else x,
    )
    gold_by = _gold_map(subset / "cases.parquet", all_ids)
    cohort = select_cohort(trees, gold_by, judge)
    if int(args.limit or 0) > 0:
        cohort = cohort[: int(args.limit)]
    local_grid = list(range(int(args.local_min), int(args.local_max) + 1))
    local_max = int(args.local_max)

    _write_json(
        out / "cohort.json",
        {
            "created_at": _utc(),
            "protocol": "ra_within_goldfam_local_prefix_v1",
            "n_cohort": len(cohort),
            "local_grid": local_grid,
            "local_max": local_max,
            "cases": cohort,
        },
    )
    print(
        json.dumps(
            {"n_cohort": len(cohort), "local_grid": local_grid, "workers": args.workers},
            indent=2,
        ),
        flush=True,
    )

    cases, fixture = _load_cases_and_fixture(ann)
    llm = RobustLLMClient(model=str(args.model))
    lock = threading.Lock()
    done = 0

    def _one(row: Mapping[str, Any]) -> dict[str, Any]:
        nonlocal done
        cid = str(row["case_id"])
        out_path = results_dir / ("%s.json" % cid)
        if out_path.is_file():
            try:
                existing = _read_json(out_path)
                if existing.get("by_k") and not existing.get("error"):
                    with lock:
                        done += 1
                        print(
                            "[resume] %d/%d %s" % (done, len(cohort), cid),
                            flush=True,
                        )
                    return existing
            except Exception:  # noqa: BLE001
                pass
        result = run_case(
            cohort_row=row,
            tree_path=trees / ("%s.json" % cid),
            case=cases.get(cid) or {},
            fixture=fixture.get(cid) or {},
            gold=gold_by[cid],
            judge=judge,
            llm=llm,
            cache_dir=cache_root / cid,
            local_max=local_max,
            local_grid=local_grid,
            model=str(args.model),
        )
        _write_json(out_path, result)
        with lock:
            done += 1
            hit4 = ((result.get("by_k") or {}).get("4") or {}).get("within_hit")
            hit10 = ((result.get("by_k") or {}).get(str(local_max)) or {}).get(
                "within_hit"
            )
            print(
                "[ok] %d/%d %s fam=%s n_evi=%s hit@4=%s hit@%d=%s"
                % (
                    done,
                    len(cohort),
                    cid,
                    result.get("gold_fam_id"),
                    result.get("n_selected_fmax"),
                    hit4,
                    local_max,
                    hit10,
                ),
                flush=True,
            )
        return result

    case_results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
        futs = [pool.submit(_one, row) for row in cohort]
        for fut in as_completed(futs):
            case_results.append(fut.result())

    case_results.sort(
        key=lambda r: int(r["case_id"])
        if str(r.get("case_id") or "").isdigit()
        else str(r.get("case_id"))
    )
    arms = aggregate(case_results, local_grid)
    f4 = next((a for a in arms if int(a["local"]) == 4), None)
    for a in arms:
        a["delta_vs_f4"] = (
            None
            if f4 is None
            else round(
                float(a["within_fam_acc"]) - float(f4["within_fam_acc"]), 4
            )
        )

    def _key(a: Mapping[str, Any]) -> tuple:
        return (float(a.get("within_fam_acc") or 0), -int(a.get("local") or 0))

    best = max(arms, key=_key) if arms else {}
    doc = {
        "protocol": "ra_within_goldfam_local_prefix_v1",
        "created_at": _utc(),
        "source_run": str(src),
        "n_cohort": len(cohort),
        "local_grid": local_grid,
        "local_max": local_max,
        "arms": arms,
        "locked_local": best.get("local"),
        "locked_arm": best,
        "out_dir": str(out),
        "boundaries": [
            "Gold-family-only local evidence; main-run L2 leaves frozen.",
            "Fk via prefix of Fmax selection order; annotator per k.",
            "Not full-case live reann; not between/L1 budget.",
        ],
    }
    _write_json(Path(args.out_json), doc)
    Path(args.out_md).write_text(_render_md(doc), encoding="utf-8")
    print(json.dumps({"locked_local": doc["locked_local"], "arms": arms}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
