#!/usr/bin/env python3
"""Build per-case compute budget schedule for B02 from M00 tree artifacts.

M00 does not yet emit a formal token/call ledger (PAPER I05). This script builds a
**structural proxy schedule** from frozen shared_trees (+ optional case_results):

  unique_candidates  <- n L2 leaves (nodes without children)
  retrieval_snippets <- clamp(n_static_evidence_items, 8, 24)
  llm_calls          <- 1 + n_l1 + ceil(unique_candidates / batch)
                       (cand-gen batches + one flat evidence round per L1 + rerank)

B02 matched mode consumes only these numeric caps (never M00 candidates / gold).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DA_TREE_ROOTS = [
    ROOT
    / "logs/diagnosisarena_d2_m01_v1/pilot24_compat_b12_live_v1/shared_trees",
    ROOT
    / "logs/diagnosisarena_d2_m01_v1/remain76_compat_b12_live_v1/shared_trees",
]
DEFAULT_OX_TREE_ROOTS = [
    ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1/frozen/shared_trees",
]
DEFAULT_MCR_TREE_ROOTS = [
    ROOT
    / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/frozen/shared_trees",
]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _branch_nodes(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    branches = state.get("branches")
    if isinstance(branches, dict):
        return [dict(v) for v in branches.values() if isinstance(v, Mapping)]
    if isinstance(branches, list):
        return [dict(v) for v in branches if isinstance(v, Mapping)]
    return []


def _tree_metrics(tree_doc: Mapping[str, Any]) -> dict[str, Any]:
    state = tree_doc.get("state") if isinstance(tree_doc.get("state"), Mapping) else {}
    nodes = _branch_nodes(state)
    n_l1 = sum(1 for n in nodes if int(n.get("level") or 0) == 1)
    n_leaf = sum(1 for n in nodes if not (n.get("children") or []))
    n_static = tree_doc.get("n_static_evidence_items")
    if n_static is None:
        n_static = len(state.get("static_evidence_items") or [])
    case_id = str(state.get("case_id") or "").strip()
    return {
        "source_id": case_id,
        "n_l1": int(n_l1),
        "n_leaf": int(n_leaf),
        "n_static": int(n_static or 0),
        "n_nodes": len(nodes),
    }


def _schedule_row(
    metrics: Mapping[str, Any],
    *,
    dataset: str,
    cand_batch: int = 8,
    snippet_min: int = 8,
    snippet_max: int = 24,
    per_query_per_index: int = 3,
) -> dict[str, Any]:
    n_leaf = max(1, int(metrics["n_leaf"]))
    n_l1 = max(1, int(metrics["n_l1"]))
    n_static = max(0, int(metrics["n_static"]))
    unique_candidates = n_leaf
    retrieval_snippets = max(snippet_min, min(snippet_max, n_static or snippet_min))
    n_queries = max(2, min(8, int(math.ceil(retrieval_snippets / float(per_query_per_index)))))
    cand_batches = max(1, int(math.ceil(unique_candidates / float(cand_batch))))
    # cand-gen batches + fill reserve + one flat evidence-matrix round per L1 + rerank
    llm_calls = max(3, cand_batches + 1 + n_l1 + 1)
    # 2 indices × per_query_per_index, then capped by max_chunks in retriever
    retrieval_calls = int(n_queries * 2)
    source_id = str(metrics["source_id"])
    prefix = {
        "diagnosisarena": "diagnosisarena",
        "open_xddx": "open_xddx",
        "medcasereasoning": "medcasereasoning",
    }[dataset]
    try:
        case_id = f"{prefix}__{int(source_id):06d}"
    except ValueError:
        case_id = f"{prefix}__{source_id}"
    return {
        "case_id": case_id,
        "source_id": source_id,
        "dataset": dataset,
        "unique_candidates": unique_candidates,
        "retrieval_snippets": retrieval_snippets,
        "retrieval_calls": retrieval_calls,
        "llm_calls": llm_calls,
        "n_queries": n_queries,
        "per_query_per_index": per_query_per_index,
        "max_chunks": retrieval_snippets,
        "cand_batch": cand_batch,
        "evidence_rounds": n_l1,
        "proxy_metrics": {
            "n_l1": n_l1,
            "n_leaf": n_leaf,
            "n_static": n_static,
            "n_nodes": int(metrics["n_nodes"]),
        },
        "matching_policy": "structural_proxy_v1",
        "notes": (
            "Proxy from M00 shared_trees (no official token ledger). "
            "B02 may only read numeric caps."
        ),
    }


def iter_tree_files(roots: Iterable[Path]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.json")):
            if path.name == "summary.json":
                continue
            out.append(path)
    return out


def build_schedule(
    *,
    dataset: str,
    tree_roots: Sequence[Path] | None = None,
    cand_batch: int = 8,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if tree_roots is None:
        if dataset == "diagnosisarena":
            tree_roots = DEFAULT_DA_TREE_ROOTS
        elif dataset == "open_xddx":
            tree_roots = DEFAULT_OX_TREE_ROOTS
        elif dataset == "medcasereasoning":
            tree_roots = DEFAULT_MCR_TREE_ROOTS
        else:
            raise ValueError(dataset)
    files = iter_tree_files(tree_roots)
    if not files:
        raise FileNotFoundError(f"no shared_trees under {tree_roots}")
    by_source: dict[str, dict[str, Any]] = {}
    sources: list[str] = []
    for path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        metrics = _tree_metrics(doc)
        sid = metrics["source_id"] or path.stem
        metrics["source_id"] = sid
        if sid in by_source:
            continue
        by_source[sid] = _schedule_row(
            metrics, dataset=dataset, cand_batch=cand_batch
        )
        sources.append(str(path))
    rows = [by_source[k] for k in sorted(by_source, key=lambda x: (len(x), x))]
    meta = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset,
        "matching_policy": "structural_proxy_v1",
        "n_cases": len(rows),
        "tree_roots": [str(p) for p in tree_roots],
        "n_tree_files_scanned": len(files),
        "source_files_used": sources[:5] + ([f"...+{len(sources)-5}"] if len(sources) > 5 else []),
        "tolerance": 0.05,
        "dimensions": [
            "llm_calls",
            "retrieval_calls",
            "retrieval_snippets",
            "unique_candidates",
        ],
        "token_matching": "deferred_no_m00_ledger",
    }
    return rows, meta


def write_schedule(
    rows: list[dict[str, Any]],
    meta: Mapping[str, Any],
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"_meta": dict(meta)}, ensure_ascii=False) + "\n")
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    meta_path = out_path.with_suffix(".meta.json")
    payload = dict(meta)
    payload["schedule_path"] = str(out_path)
    payload["schedule_sha256"] = _sha256_file(out_path)
    meta_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def load_budget_schedule(path: Path) -> dict[str, dict[str, Any]]:
    """Load schedule keyed by case_id and source_id."""
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if "_meta" in row:
            continue
        out[str(row["case_id"])] = row
        out[str(row["source_id"])] = row
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--dataset",
        default="diagnosisarena",
        choices=("diagnosisarena", "open_xddx", "medcasereasoning"),
    )
    p.add_argument(
        "--tree-roots",
        default="",
        help="comma-separated shared_trees dirs (default: dataset canonical)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
    )
    p.add_argument("--cand-batch", type=int, default=8)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    roots = None
    if args.tree_roots.strip():
        roots = [Path(x.strip()) for x in args.tree_roots.split(",") if x.strip()]
    rows, meta = build_schedule(
        dataset=args.dataset, tree_roots=roots, cand_batch=args.cand_batch
    )
    out = args.out
    if out is None:
        out = (
            ROOT
            / "configs/paper_experiments"
            / f"paper_v1_budget_schedule_{args.dataset}.jsonl"
        )
    write_schedule(rows, meta, out)
    # summary stats
    def avg(key: str) -> float:
        return sum(float(r[key]) for r in rows) / max(1, len(rows))

    print(
        json.dumps(
            {
                "out": str(out),
                "n_cases": len(rows),
                "mean_llm_calls": round(avg("llm_calls"), 2),
                "mean_retrieval_calls": round(avg("retrieval_calls"), 2),
                "mean_retrieval_snippets": round(avg("retrieval_snippets"), 2),
                "mean_unique_candidates": round(avg("unique_candidates"), 2),
                "meta": str(out.with_suffix(".meta.json")),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
