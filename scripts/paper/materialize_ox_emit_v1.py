#!/usr/bin/env python3
"""Materialize OX emit_v1 overlay trees and validate full-tree R (Stage 1).

Eval-only bypass (does not mutate the source run):
  <run>/annotate/emit_v1_overlay/shared_trees/{id}.json
  <run>/annotate/emit_v1_overlay/summary.json
  analysis/transfer_metrics_v1/ox_emit_v1_validate.md

Smoke (first N ids) then full 100: confirm full-tree R↑ and posterior Top-K F1
does not collapse vs baseline.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import build_eval_projection as bep  # noqa: E402
from audit_ox_c2a_force_emit import (  # noqa: E402
    _labs,
    inject_leaves,
    load_gold,
    mine_cache_pools,
    score_lists,
)
from audit_ox_emit_then_rerank import (  # noqa: E402
    EMIT_BUDGET,
    emit_c2a,
    inject_leaves_soft_pool,
)
from transfer_eval.judges import LexicalJudge  # noqa: E402

DEFAULT_RUN = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1"
DEFAULT_CONFIG = ROOT / "analysis/transfer_metrics_v1/ox_emit_v1_config.json"
DEFAULT_OUT_MD = ROOT / "analysis/transfer_metrics_v1/ox_emit_v1_validate.md"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _case_ids(ann: Path) -> list[str]:
    ids = [
        p.stem
        for p in (ann / "shared_trees").glob("*.json")
        if not p.name.startswith("_")
    ]
    return sorted(ids, key=lambda x: int(x) if x.isdigit() else x)


def materialize(
    run_dir: Path,
    *,
    n_cases: int | None = None,
    soft_pool: bool = True,
    k: int = 5,
    overlay_name: str = "emit_v1_overlay",
) -> dict[str, Any]:
    ann = run_dir / "annotate" if (run_dir / "annotate").is_dir() else run_dir
    overlay = ann / overlay_name
    tree_out = overlay / "shared_trees"
    tree_out.mkdir(parents=True, exist_ok=True)

    judge = LexicalJudge()
    gold_by = load_gold(ann)
    ids = _case_ids(ann)
    if n_cases is not None:
        ids = ids[: max(0, int(n_cases))]

    base_full: dict[str, list[str]] = {}
    emit_full: dict[str, list[str]] = {}
    base_top: dict[str, list[str]] = {}
    emit_top: dict[str, list[str]] = {}
    n_added_total = 0
    n_cases_with_add = 0
    rows = []

    for cid in ids:
        src = ann / "shared_trees" / ("%s.json" % cid)
        cache_path = ann / "cache" / cid / "l2_llm_cache.json"
        raw = _read_json(src)
        tree = bep.load_tree_state(src)
        tree_labs = _labs(bep._scored_leaves(tree))
        cache = _read_json(cache_path) if cache_path.is_file() else {}
        pools = mine_cache_pools(cache if isinstance(cache, Mapping) else {})
        injects = emit_c2a(pools, tree_labs)

        if soft_pool:
            inj_tree, n_add, post = inject_leaves_soft_pool(tree, injects)
        else:
            inj_tree, n_add = inject_leaves(tree, injects, posterior=1e-4)
            post = 1e-4

        # Write full raw wrapper with mutated state when present
        out_doc = json.loads(json.dumps(raw))
        if isinstance(out_doc.get("state"), dict) and "branches" in inj_tree:
            out_doc["state"] = inj_tree
        else:
            out_doc = inj_tree
        out_doc.setdefault("emit_v1", {})
        out_doc["emit_v1"] = {
            "enabled": True,
            "n_added": n_add,
            "injects": injects,
            "posterior": post,
            "budget": EMIT_BUDGET,
            "soft_pool": soft_pool,
        }
        _write_json(tree_out / ("%s.json" % cid), out_doc)

        gold = gold_by.get(cid) or []
        base_full[cid] = tree_labs
        emit_full[cid] = _labs(bep._scored_leaves(inj_tree))
        base_top[cid] = _labs(bep.top_leaf_posterior(tree, k=k))
        emit_top[cid] = _labs(bep.top_leaf_posterior(inj_tree, k=k))
        n_added_total += n_add
        n_cases_with_add += int(n_add > 0)
        rows.append({
            "cid": cid,
            "n_added": n_add,
            "injects": injects,
            "n_gold": len(gold),
        })

    metrics = {
        "baseline": {
            "full_tree": score_lists(base_full, {c: gold_by[c] for c in ids if c in gold_by}, judge),
            "posterior_topk": score_lists(base_top, {c: gold_by[c] for c in ids if c in gold_by}, judge),
        },
        "emit_v1": {
            "full_tree": score_lists(emit_full, {c: gold_by[c] for c in ids if c in gold_by}, judge),
            "posterior_topk": score_lists(emit_top, {c: gold_by[c] for c in ids if c in gold_by}, judge),
        },
    }
    base_r = float(metrics["baseline"]["full_tree"]["micro_recall"] or 0)
    emit_r = float(metrics["emit_v1"]["full_tree"]["micro_recall"] or 0)
    base_f1 = float(metrics["baseline"]["posterior_topk"]["micro_f1"] or 0)
    emit_f1 = float(metrics["emit_v1"]["posterior_topk"]["micro_f1"] or 0)

    summary = {
        "protocol": "ox_emit_v1_materialize_v1",
        "config": str(DEFAULT_CONFIG),
        "run_dir": str(run_dir),
        "overlay_dir": str(overlay),
        "n_cases": len(ids),
        "soft_pool": soft_pool,
        "k": k,
        "n_added_total": n_added_total,
        "n_cases_with_add": n_cases_with_add,
        "metrics": metrics,
        "gate": {
            "full_tree_r_up": emit_r >= base_r - 1e-12,
            "delta_full_tree_r": emit_r - base_r,
            "posterior_f1_collapse": emit_f1 < base_f1 - 0.05,
            "delta_posterior_f1": emit_f1 - base_f1,
            "pass": (emit_r >= base_r - 1e-12) and (emit_f1 >= base_f1 - 0.05),
        },
        "case_rows": rows,
    }
    _write_json(overlay / "summary.json", summary)
    # Convenience symlink-style pointer for projection builders
    _write_json(overlay / "manifest.json", {
        "name": "compat_synonym_emit_v1",
        "shared_trees": "shared_trees",
        "source_run": str(run_dir),
        "controller": _read_json(DEFAULT_CONFIG).get("controller"),
    })
    return summary


def write_md(smoke: Mapping[str, Any], full: Mapping[str, Any], path: Path) -> None:
    def block(title: str, doc: Mapping[str, Any]) -> list[str]:
        m = doc["metrics"]
        g = doc["gate"]
        return [
            "### %s (n=%d)" % (title, int(doc["n_cases"])),
            "",
            "| 臂 | 全树 R | Top-%d F1 |" % int(doc["k"]),
            "|----|--------|----------|",
            "| baseline | %.4f | %.4f |" % (
                float(m["baseline"]["full_tree"]["micro_recall"] or 0),
                float(m["baseline"]["posterior_topk"]["micro_f1"] or 0),
            ),
            "| emit_v1 | %.4f | %.4f |" % (
                float(m["emit_v1"]["full_tree"]["micro_recall"] or 0),
                float(m["emit_v1"]["posterior_topk"]["micro_f1"] or 0),
            ),
            "",
            "- Δ全树 R = **%+.4f**" % float(g["delta_full_tree_r"]),
            "- Δ后验 F1 = %+.4f（崩塌判定阈 −5pp）" % float(g["delta_posterior_f1"]),
            "- 门控：**%s**" % ("PASS" if g["pass"] else "FAIL"),
            "- 注入：%d 叶 / %d 例有补叶"
            % (int(doc["n_added_total"]), int(doc["n_cases_with_add"])),
            "",
        ]

    lines = [
        "# OX emit_v1 固化与全树 R 验证（Stage 1）",
        "",
        "配置：[`ox_emit_v1_config.json`](ox_emit_v1_config.json)",
        "旁路树：`<run>/annotate/emit_v1_overlay/shared_trees/`",
        "",
        "## Controller（opt-in，默认 OFF）",
        "",
        "```json",
        json.dumps(_read_json(DEFAULT_CONFIG)["controller"], indent=2),
        "```",
        "",
        "## 验证",
        "",
    ]
    lines += block("Smoke", smoke)
    lines += block("Full", full)
    lines += [
        "## 复现",
        "",
        "```bash",
        "PYTHONPATH=src:scripts/paper python3 scripts/paper/materialize_ox_emit_v1.py \\",
        "  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 --smoke 10",
        "```",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--smoke", type=int, default=10)
    ap.add_argument("--ddx-k", type=int, default=5)
    ap.add_argument("--hard-posterior", action="store_true",
                    help="Use 1e-4 posterior instead of soft pool floor")
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    args = ap.parse_args(list(argv) if argv is not None else None)

    soft = not bool(args.hard_posterior)
    smoke = materialize(
        args.run_dir, n_cases=int(args.smoke), soft_pool=soft, k=int(args.ddx_k),
        overlay_name="emit_v1_overlay_smoke",
    )
    full = materialize(
        args.run_dir, n_cases=None, soft_pool=soft, k=int(args.ddx_k),
        overlay_name="emit_v1_overlay",
    )
    write_md(smoke, full, args.out_md)
    print(json.dumps({
        "out_md": str(args.out_md),
        "smoke_pass": smoke["gate"]["pass"],
        "full_pass": full["gate"]["pass"],
        "full_delta_r": full["gate"]["delta_full_tree_r"],
        "full_delta_f1": full["gate"]["delta_posterior_f1"],
        "overlay": full["overlay_dir"],
    }, indent=2, ensure_ascii=False))
    return 0 if full["gate"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
